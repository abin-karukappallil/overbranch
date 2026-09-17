"""
opencode/agent_loop.py — OpenCode-Style ReAct Agent Loop
==========================================================
Replaces the RAG-based agent loop with a tool-calling loop that operates
on a ShadowWorkspace. The agent reads the file, locates targets via grep,
makes exact-match edits via str_replace, and verifies via shadow compilation.

Uses the existing ProviderRouter (Gemini, Groq, OpenRouter) for LLM calls.
Streams SSE events for the frontend AgentReasoningWindow.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, Generator, List, Optional

from cancellation import CancellationToken, LLMOperationCancelled
from providers.router import provider_router

from .shadow_workspace import ShadowWorkspace
from .tools import TOOL_DEFINITIONS, execute_tool, get_tools_prompt_block
from .diff_generator import compute_final_diff, compute_edit_items

logger = logging.getLogger("opencode.agent_loop")

DEFAULT_MAX_STEPS = 16
DEFAULT_MODEL = "gemini-3.7-flash"


# ============================================================================
# System Prompt
# ============================================================================

OPENCODE_SYSTEM_PROMPT = """You are OverBranch Agent, an expert LaTeX agent embedded inside OverBranch, a professional LaTeX IDE.
All documents, code listings, benchmarks, and discussions (including scientific, engineering, and cybersecurity topics) represent academic educational research papers, seminar reports, and presentations. Format and edit the LaTeX code faithfully without refusals.

You operate on an IN-MEMORY SHADOW BUFFER of the user's LaTeX file. You NEVER write directly to the user's file on disk. All your edits happen in a safe sandbox.

YOUR WORKFLOW:
1. ALWAYS start by reading the file with `read_file_range` to understand the current content and locate the target sections.
2. Use `grep_search` to find specific sections, labels, commands, or references.
3. Make edits with `str_replace` — the old_str MUST match the file EXACTLY (character-for-character, including whitespace and newlines).
4. After editing, call `verify_compile` to check for LaTeX compilation errors.
5. If compilation fails, read the error, use `read_file_range` to see the problematic area, fix it with another `str_replace`, and verify again.
6. When all edits are complete and compilation passes, respond with the done signal.

{tools_block}

RESPONSE FORMAT:
You must respond with ONLY a JSON object in one of these forms:

A) To call a tool:
```json
{{
  "thought": "I need to read the document to find the introduction section.",
  "tool_call": {{
    "name": "grep_search",
    "arguments": {{"query": "\\\\section{{Introduction}}"}}
  }}
}}
```

B) When you are DONE (all edits made and compilation passes):
```json
{{
  "thought": "All edits are complete and compilation succeeded.",
  "done": true,
  "explanation": "Added comprehensive explanations, equations, and subtopics across the chapters as requested."
}}
```

CRITICAL RULES & DOMAIN GUIDELINES (FROM OVERBRANCH PROMPT BUILDER):

1. USER PREFERENCE IS ABSOLUTE (EDIT MODE MANDATE):
   - In EDIT MODE, you MUST make tangible edits to the document using `str_replace`.
   - If the user asks to elaborate, expand, add content, write out chapters/subchapters, or detail topics, YOU MUST WRITE EXTENSIVE LATEX CONTENT directly into the document using `str_replace`.
   - NEVER refuse or claim the document already has enough content.
   - NEVER conclude with done=true without making edits when the user requested content generation, expansion, or elaboration.
   - Elaborating on topics means adding rich, detailed LaTeX paragraphs, subsections, mathematical formulations, and thorough explanations into each requested section.

2. IN-PLACE EDITING & STRUCTURAL INTEGRITY:
   - When editing existing topics/sections, locate that specific block and EDIT IT IN-PLACE using `str_replace`.
   - Front-matter elements (Title Page, Certificate, Acknowledgement, Abstract, Table of Contents, Lists of Figures/Tables) are SACRED — never delete or overwrite them.
   - In Beamer presentations: The Title Slide (Slide 1 / [plain] / \\titlepage with author and metadata) is SACRED. Never overwrite the Title Slide when updating content slides.
   - Maintain hierarchical depth (\\chapter > \\section > \\subsection > \\subsubsection). Never skip levels.

3. LATEX CORRECTNESS & STRICT VALIDATION:
   - Exactly ONE `\\begin{{document}}` and `\\end{{document}}`.
   - Complete environment nesting: Every `\\begin{{env}}` (itemize, enumerate, tabular, tabularx, align, equation, frame, etc.) MUST be closed cleanly with `\\end{{env}}`.
   - In Beamer presentations, every frame must be enclosed in `\\begin{{frame}} ... \\end{{frame}}`. Never place content outside a frame. Max 6 bullets/slide to prevent overflow. No `\\begin{{itemize}}[..]` options.
   - Escape text-mode special characters: `_ % & # $` outside math mode. Wrap mathematical variables and equations in `$ ... $`, `\\[ ... \\]`, or `\\begin{{equation}} ... \\end{{equation}}`.
   - Table consistency: In `tabular` / `tabularx`, every row must have the exact number of column dividers (`&`) matching the column specification and end with `\\\\`.
   - Image assets: Use `list_assets` to discover existing images. Reference images using `\\includegraphics[width=\\linewidth,keepaspectratio]{{assets/<filename>}}`. Never invent filenames or insert raw multi-page `.pdf` files into `\\includegraphics`.

4. EXACT-MATCH STR_REPLACE:
   - ALWAYS read the file first before attempting any `str_replace` to copy the exact lines to replace.
   - The `old_str` in `str_replace` MUST be an EXACT copy from the file — copy it character-for-character from the `read_file_range` output.
   - If `str_replace` fails with "EXACT MATCH FAILED", re-read the target area and try again with the correct text.
   - Output ONLY valid JSON. No conversational commentary outside the JSON object.

5. GROUNDING IN EXISTING DOCUMENT DATA & ATTACHED DOCUMENTS:
   - When asked to "elaborate", "describe", "expand", or "fill in content":
   - Use the specific data, statistics, benchmark results, mathematical equations, algorithm pipelines, and architectural concepts present in the document and in any attached reference files.
   - Ground all new paragraphs and subsections in real technical explanations based on the document's domain (e.g. specific model names, percentage gaps, database engine vulnerabilities, detection accuracies).
   - Never write superficial or repetitive generic filler — write thorough, rigorous, publication-grade academic prose and equations.

6. DOCUMENT CREATION & CONVERSION MANDATE (FROM SCRATCH OR ATTACHED FILES):
   - When asked to CREATE, GENERATE, BUILD, WRITE, DRAFT, or CONVERT a document (e.g. Presentation/Beamer, Seminar Report/Thesis, Research Paper/IEEE, Resume/CV):
   - You MUST generate a complete, fully compilable, high-quality LaTeX document from `\\documentclass` to `\\end{{document}}`.
   - For BEAMER PRESENTATIONS: Use `\\documentclass[aspectratio=169]{{beamer}}`, modern themes (e.g. Madrid, metropolis), clear Title slide (`[plain]`), Outline slide, and 6-12 content slides (`\\begin{{frame}}{{Title}}{{Subtitle}}`) with clear bullet points (max 5-6 bullets/slide), structured blocks, tables, and equations.
   - For MULTI-CHAPTER REPORTS: Use `\\documentclass[11pt,a4paper,oneside]{{report}}`, standard geometry, setspace, amsmath, graphicx, booktabs, hyperref. Include Title, Abstract, Table of Contents, and 4-6 rich chapters with mathematical formulas, algorithms, tables, and bibliography.
   - For RESEARCH PAPERS / ARTICLES: Use `\\documentclass[conference]{{IEEEtran}}` or `\\documentclass[11pt,twocolumn]{{article}}`, abstract, keywords, numbered sections (Intro, Related Work, Methodology, Results, Conclusion), and references.
   - For RESUMES / CVs: Clean single- or two-page layout with Contact, Education, Technical Skills, Experience, and Projects.
   - If the file is empty or contains a default template, replace the entire buffer with the complete, newly created document using `str_replace`.
   - ALWAYS run `verify_compile` after creating the document to ensure zero compilation errors.

7. BEAMER COLOR CONTRAST & VISIBILITY (INVISIBLE TITLE / TEXT FIX):
   - When user reports that "title is not visible", "invisible text", "cannot see heading", or poor contrast:
   - This is a direct FOREGROUND VS BACKGROUND COLOR CONTRAST BUG.
   - If the title banner has a dark background (e.g. `bg=darknavy` or Madrid default dark box), the title text MUST be explicitly set to white: `\\setbeamercolor{{title}}{{bg=..., fg=white}}` or `\\setbeamercolor*{{title}}{{bg=..., fg=white}}`.
   - If `\\title{{\\color{{black}}{{...}}}}` or `\\title{{\\color{{pdfprimary}}{{...}}}}` has an embedded dark color macro, it causes black text on dark background -> change it to `\\color{{white}}` or remove the embedded color and configure `\\setbeamercolor{{title}}{{fg=white}}`.
   - Ensure `\\setbeamercolor{{frametitle}}{{bg=..., fg=white}}` for slide headers.
   - NEVER simply rephrase the wording when asked to fix invisible titles/headings — FIX THE PREAMBLE COLOR DEFINITIONS (`\\setbeamercolor` or `\\color`).

8. TEMPLATES, THEMES & REDESIGNING (USING `get_template_theme`):
   - When asked to REDESIGN, CHANGE THEME, IMPROVE AESTHETICS, or GENERATE a specific document format (Beamer PPT themes, IEEE papers, theses, resumes, letters, assignments):
   - Call `get_template_theme` to inspect or retrieve curated themes from the OverBranch template library:
     - Categories: "ppt" (Beamer), "papers" (IEEE), "thesis" (Theses/Reports), "resume" (CVs), "letters" (Letters), "assignments" (Lab Reports).
     - Themes include: 'nordlight' (dark modern teal/orange), 'prism' (vibrant geometric), 'regalia' (royal gold/crimson), 'basic' (Madrid custom), 'minimalist' (Focus clean), 'ieee-conference', 'ieee-journal', 'thesis', 'medium-length-professional-cv', 'letter1', 'navy-gold'.
   - FOR REDESIGNING AN EXISTING DOCUMENT OR SLIDES:
     Call `get_template_theme(category="ppt", theme_name="nordlight", extract_section="preamble")` to get the theme color definitions and packages, then use `read_file_range` on the document's preamble and `str_replace` to swap out the styling while PRESERVING all of the user's slide contents, formulas, and text!
"""


# ============================================================================
# Response Parser
# ============================================================================

def _parse_agent_response(text: str) -> Dict[str, Any]:
    """
    Extract and parse JSON object from LLM output.
    Handles markdown code blocks and LaTeX backslash escaping.
    """
    if not text:
        return {}

    cleaned = text.strip()

    # Remove markdown code block wrappers
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    # Try direct parse
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Extract outermost balanced braces
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        snippet = cleaned[start:end + 1]
        try:
            return json.loads(snippet)
        except Exception:
            # Handle LaTeX backslashes in JSON strings
            try:
                sanitized = re.sub(r'\\(?![/"\\bfnrtu])', r'\\\\', snippet)
                return json.loads(sanitized)
            except Exception:
                pass

    return {}


# ============================================================================
# Dynamic Adaptive Step Budgeting
# ============================================================================

def determine_adaptive_step_budget(
    user_instruction: str,
    total_lines: int,
    num_chapters: int,
    num_sections: int,
    mode: str = "edit",
    requested_steps: Optional[int] = None,
) -> int:
    """
    Dynamically determines the optimal agent reasoning step budget based on:
    1. User prompt intent and complexity (creation vs broad overhaul vs single-target fix)
    2. Document scale (number of chapters, sections, and total lines)
    3. Mode (Ask vs Edit)
    """
    if requested_steps and requested_steps > 0:
        return requested_steps

    if mode == "ask":
        return 6

    user_lower = user_instruction.lower()

    # 1. Creation / Conversion requests (from scratch or attached PDF)
    creation_keywords = [
        "create", "make", "generate", "build", "compose", "prepare", "draft",
        "turn this pdf", "convert this pdf", "using this pdf", "new report",
        "new presentation", "new document", "create a ppt", "create presentation",
        "create beamer", "create report", "create paper", "create resume",
        "create cv", "from scratch", "write a report", "write a paper",
        "write a presentation", "make a presentation", "make a report",
    ]
    if any(kw in user_lower for kw in creation_keywords) or (total_lines <= 10 and mode == "edit"):
        if any(k in user_lower for k in ["ppt", "presentation", "beamer", "slide"]):
            return 20
        elif any(k in user_lower for k in ["report", "thesis", "dissertation", "seminar"]):
            return 24
        elif any(k in user_lower for k in ["paper", "article", "ieee"]):
            return 20
        else:
            return 16

    # 2. Redesign / New design / Theme change requests
    redesign_keywords = [
        "redesign", "new design", "change design", "better design", "different design",
        "need new design", "need a new design", "change theme", "switch theme", "apply theme",
        "new theme", "different theme", "better theme", "modern theme", "nordlight", "prism", "regalia",
        "make it look better", "re-theme", "restyle", "improve design", "color theme", "beamer theme",
    ]
    if any(kw in user_lower for kw in redesign_keywords):
        return 18

    # 3. Broad / Full document / Multi-chapter requests
    broad_keywords = [
        "all chapter", "every chapter", "each chapter", "all subchapter",
        "each subchapter", "every subchapter", "all section", "every section",
        "each section", "whole document", "entire document", "all topic",
        "each topic", "every topic", "throughout the document", "full report",
        "rewrite document", "complete report", "expand all", "all pages",
    ]
    if any(kw in user_lower for kw in broad_keywords):
        if num_chapters >= 4:
            return min(32, 12 + num_chapters * 4)
        elif num_chapters >= 2:
            return 24
        elif num_sections >= 5:
            return 20
        else:
            return 18

    # 3. Minor / Quick localized fixes
    minor_keywords = [
        "typo", "spelling", "rename", "change author", "change title",
        "fix date", "replace word", "single word", "line number", "grammar",
    ]
    if any(kw in user_lower for kw in minor_keywords) and len(user_instruction.split()) < 10:
        return 8

    # 4. Medium multi-part edits (e.g. "add sections X and Y", "insert figures and tables")
    medium_keywords = [
        "add", "insert", "elaborate", "expand", "explain",
        "table", "figure", "methodology", "literature", "results", "analysis",
    ]
    match_count = sum(1 for kw in medium_keywords if kw in user_lower)
    if match_count >= 2 or num_chapters >= 3:
        return 16

    # 5. Standard single edit default
    return 12


# ============================================================================
# Streaming Agent Loop
# ============================================================================

def stream_opencode_agent(
    user_instruction: str,
    project_id: str,
    current_code: str,
    file_path: str = "main.tex",
    model: str = DEFAULT_MODEL,
    mode: str = "edit",
    attached_file: Optional[Dict[str, Any]] = None,
    api_keys: Optional[Dict[str, str]] = None,
    max_steps: Optional[int] = None,
    cancel_token: Optional[CancellationToken] = None,
    assets_dir: Optional[str] = None,
) -> Generator[Dict[str, Any], None, None]:
    """
    Generator-based OpenCode agent loop that yields SSE events.

    Yields event dicts:
        {"type": "status",       "step": int, "message": str}
        {"type": "thought",      "content": str}
        {"type": "tool_call",    "tool": str, "args": dict}
        {"type": "tool_result",  "tool": str, "result": dict}
        {"type": "compile_error","summary": str, "errors": list}
        {"type": "final_diff",   "file": str, "original_code": str,
                                 "proposed_code": str, "explanation": str}
        {"type": "result",       "data": dict}  # backward-compatible
    """
    start_time = time.time()

    # 1. Initialize ShadowWorkspace
    workspace = ShadowWorkspace(
        original_code=current_code,
        project_id=project_id,
        file_path=file_path,
        assets_dir=assets_dir,
    )

    yield {
        "type": "status",
        "step": 0,
        "message": "Initializing shadow workspace...",
    }

    # 2. Build system prompt with tool definitions
    tools_block = get_tools_prompt_block()
    system_prompt = OPENCODE_SYSTEM_PROMPT.format(tools_block=tools_block)

    total_lines = workspace.get_line_count()
    user_lower = user_instruction.lower()

    # 3. Detect broad multi-chapter requests
    broad_keywords = [
        "all chapter", "every chapter", "each chapter", "all subchapter",
        "each subchapter", "every subchapter", "all section", "every section",
        "each section", "whole document", "entire document", "all topic",
        "each topic", "every topic", "throughout the document", "full report",
    ]
    is_broad_request = any(kw in user_lower for kw in broad_keywords)

    # 4. Detect document creation / conversion requests
    creation_keywords = [
        "create", "make", "generate", "build", "compose", "prepare", "draft",
        "turn this pdf", "convert this pdf", "using this pdf", "new report",
        "new presentation", "new document", "create a ppt", "create presentation",
        "create beamer", "create report", "create paper", "create resume",
        "create cv", "from scratch", "write a report", "write a paper",
        "write a presentation", "make a presentation", "make a report",
    ]
    is_empty_or_minimal = (
        total_lines <= 5
        or not current_code.strip()
        or (total_lines <= 20 and "\\documentclass" in current_code and "\\end{document}" in current_code and len(current_code.strip().splitlines()) <= 8)
    )
    is_creation_intent = any(kw in user_lower for kw in creation_keywords)
    is_creation_request = (is_creation_intent or is_empty_or_minimal) and mode == "edit"

    # 5. Detect visibility / contrast bug reports (e.g. "title is not visible", "invisible text", "cannot see heading")
    visibility_keywords = [
        "not visible", "invisible", "cannot see", "can't see", "dark on dark",
        "white on white", "contrast", "hidden title", "title is black",
        "disappeared", "text not showing", "title is missing", "title is dark",
        "not readable", "unreadable", "hard to see", "hard to read", "title not visible",
        "title is blank", "blank title", "black on black"
    ]
    is_visibility_issue = any(kw in user_lower for kw in visibility_keywords)
    visibility_diagnostic = ""
    if is_visibility_issue:
        visibility_diagnostic = (
            "\n\n=========================================================\n"
            "CRITICAL BUG FIX INSTRUCTION (VISIBILITY & COLOR CONTRAST):\n"
            "The user explicitly reports that a TITLE or TEXT is NOT VISIBLE / UNREADABLE.\n"
            "Root Cause: In Beamer, title boxes with dark backgrounds (like Madrid/Warsaw dark banners or \\setbeamercolor{title}{bg=darknavy}) render dark/black text when fg is set to dark/black or when \\title{\\color{black}{...}} overrides the font color.\n"
            "REQUIRED ACTION:\n"
            "1. Read the preamble around \\setbeamercolor, \\definecolor, and \\title using `read_file_range`.\n"
            "2. Ensure \\setbeamercolor{title}{bg=..., fg=white} explicitly sets fg=white (or high-contrast color).\n"
            "3. If \\title{\\color{...}{...}} contains an embedded dark color macro (e.g. \\color{black} or \\color{pdfprimary}), change it to \\color{white}{...} or remove the embedded \\color and let \\setbeamercolor{title}{fg=white} control it.\n"
            "4. Also check \\setbeamercolor{frametitle}{bg=..., fg=white} for slide headers.\n"
            "5. Apply the fix using `str_replace` and run `verify_compile`.\n"
            "=========================================================\n"
        )

    # 6. Detect redesign / theme change requests (e.g. "redesign this ppt", "change theme to nordlight", "make it look modern")
    redesign_keywords = [
        "redesign", "change theme", "switch theme", "apply theme", "new theme",
        "better theme", "modern theme", "nordlight", "prism", "regalia",
        "make it look better", "re-theme", "restyle", "improve design", "color theme"
    ]
    is_redesign_request = any(kw in user_lower for kw in redesign_keywords) and mode == "edit"
    redesign_guidance = ""
    if is_redesign_request:
        redesign_guidance = (
            "\n\n=========================================================\n"
            "REDESIGN / THEME SWITCH INSTRUCTION:\n"
            "The user asked to REDESIGN or CHANGE THE THEME of the document.\n"
            "Recommended Workflow:\n"
            "1. Call `get_template_theme` with category='ppt' (or 'papers'/'resume'/'thesis') and extract_section='preamble' to fetch the target theme styling.\n"
            "2. Read the current preamble with `read_file_range` from line 1 to \\begin{document}.\n"
            "3. Use `str_replace` to update the styling, color definitions, and packages in the preamble while PRESERVING all user frames/sections/text.\n"
            "4. Run `verify_compile` to confirm the redesigned document compiles cleanly.\n"
            "=========================================================\n"
        )

    chapters = workspace.grep(r"\\chapter\{([^}]+)\}", is_regex=True)
    sections = workspace.grep(r"\\section\{([^}]+)\}", is_regex=True)
    valid_chapters = [c for c in chapters if "line_no" in c]
    valid_sections = [s for s in sections if "line_no" in s]

    # Calculate flexible, adaptive reasoning step budget
    actual_max_steps = determine_adaptive_step_budget(
        user_instruction=user_instruction,
        total_lines=total_lines,
        num_chapters=len(valid_chapters),
        num_sections=len(valid_sections),
        mode=mode,
        requested_steps=max_steps,
    )

    # Format attached reference document if present
    attached_block = ""
    if attached_file:
        fname = attached_file.get("filename", "Attached Document")
        ftype = attached_file.get("file_type", "document")
        fcontent = attached_file.get("content", "")
        if fcontent:
            fcontent_capped = fcontent[:25000]
            attached_block = (
                f"\n\n---------------------------------------------------------\n"
                f"ATTACHED REFERENCE FILE: {fname} (Type: {ftype})\n"
                f"---------------------------------------------------------\n"
                f"{fcontent_capped}\n"
                f"---------------------------------------------------------\n"
                "INSTRUCTION FOR ATTACHED FILE: Extract and use the domain data, findings, tables, algorithms, and technical concepts from this attached file to create/elaborate the LaTeX document."
            )

    # Grounding reminder for content creation
    grounding_instruction = (
        "\nGROUNDING RULE: When creating, elaborating, or describing topics, extract and use the specific findings, statistics, "
        "database names, model metrics, formulas, and concepts already present in the existing LaTeX code or in the attached document "
        "to write deep, authentic academic prose and equations directly in the document."
    )

    # Build initial message context tailored to mode & intent
    if mode == "ask":
        preview = workspace.read_lines(1, min(100, total_lines))
        user_content = (
            f"FILE: {file_path} ({total_lines} lines)\n\n"
            f"FILE PREVIEW (first 100 lines):\n{preview}\n\n"
            f"USER QUESTION (ASK MODE):\n{user_instruction}\n"
            f"{attached_block}\n\n"
            "This is ASK mode. Answer the user's question directly without editing the file. "
            "Set done=true and provide your comprehensive answer in the explanation field."
        )
    elif is_creation_request:
        # Determine archetype guidance
        is_ppt = bool(re.search(r'\b(?:ppt|presentation|beamer|slides?|deck)\b', user_lower))
        is_rep = bool(re.search(r'\b(?:report|thesis|dissertation|seminar\s+report)\b', user_lower))
        is_pap = bool(re.search(r'\b(?:paper|research\s+paper|article|ieee|conference)\b', user_lower))
        is_res = bool(re.search(r'\b(?:resume|cv|curriculum\s+vitae)\b', user_lower))

        if is_ppt:
            archetype_hint = (
                "DOCUMENT TARGET: BEAMER PRESENTATION (SLIDES)\n"
                "- Document class: `\\documentclass[aspectratio=169]{beamer}`\n"
                "- Modern theme: `\\usetheme{Madrid}` or `\\usetheme{metropolis}`, `\\usecolortheme{whale}`\n"
                "- Structure: Title Frame (`[plain]`), Outline Frame (`\\tableofcontents`), and 6-12 content frames (`\\begin{frame}{Title}{Subtitle}`)\n"
                "- Use `\\begin{itemize}`, `\\begin{block}`, equations, and tables. Max 5-6 bullets per slide. Never place text outside a frame."
            )
        elif is_rep:
            archetype_hint = (
                "DOCUMENT TARGET: MULTI-CHAPTER SEMINAR / TECHNICAL REPORT\n"
                "- Document class: `\\documentclass[11pt,a4paper,oneside]{report}`\n"
                "- Packages: `geometry`, `setspace`, `amsmath,amssymb`, `graphicx`, `booktabs`, `hyperref`, `titlesec`\n"
                "- Structure: Title/Cover page, Abstract, Table of Contents, and 4-6 detailed chapters with rich academic subsections, mathematical formulas, and benchmark tables."
            )
        elif is_pap:
            archetype_hint = (
                "DOCUMENT TARGET: ACADEMIC RESEARCH PAPER / ARTICLE\n"
                "- Document class: `\\documentclass[conference]{IEEEtran}` or `\\documentclass[11pt,twocolumn]{article}`\n"
                "- Structure: Title, Authors, Abstract, Keywords, 5-6 numbered sections (Intro, Related Work, Architecture, Results, Conclusion), References."
            )
        elif is_res:
            archetype_hint = (
                "DOCUMENT TARGET: RESUME / CV\n"
                "- Document class: `\\documentclass[11pt,a4paper]{article}`\n"
                "- Structure: Contact Header, Education, Technical Skills, Professional Experience, Projects, Certifications."
            )
        else:
            archetype_hint = (
                "DOCUMENT TARGET: COMPLETE LATEX DOCUMENT\n"
                "- Choose the appropriate document class (`report`, `article`, or `beamer`) based on the user's prompt.\n"
                "- Generate a complete, elegant, and professional document with all required packages, sections, and content."
            )

        preview = workspace.read_lines(1, min(50, total_lines)) if total_lines > 1 else "(Empty file)"
        user_content = (
            f"FILE: {file_path} ({total_lines} lines)\n\n"
            f"FILE PREVIEW:\n{preview}\n\n"
            f"USER REQUEST (DOCUMENT CREATION / CONVERSION MODE):\n{user_instruction}\n"
            f"{attached_block}\n\n"
            f"{grounding_instruction}\n\n"
            f"{archetype_hint}\n\n"
            f"{visibility_diagnostic}\n\n"
            f"{redesign_guidance}\n\n"
            "CREATION INSTRUCTIONS:\n"
            "1. Read the current file (if not empty) with `read_file_range`.\n"
            "2. Generate the complete, publication-grade LaTeX code from `\\documentclass` to `\\end{document}`.\n"
            "3. Use `str_replace` to write the newly created document into the workspace.\n"
            "4. Call `verify_compile` to check that the newly created document compiles with 0 errors.\n"
            "5. If compilation succeeds, signal done=true with a summary of what you created."
        )
    elif is_broad_request and valid_chapters:
        ch_list = "\n".join([f"  - Line {c['line_no']}: {c['match']}" for c in valid_chapters])
        sec_list = "\n".join([f"  - Line {s['line_no']}: {s['match']}" for s in valid_sections[:20]])
        user_content = (
            f"FILE: {file_path} ({total_lines} lines)\n\n"
            f"USER REQUEST (EDIT MODE — BROAD DOCUMENT EXPANSION):\n{user_instruction}\n"
            f"{attached_block}\n\n"
            f"{grounding_instruction}\n\n"
            f"{visibility_diagnostic}\n\n"
            f"{redesign_guidance}\n\n"
            "MANDATE: The user explicitly requested to elaborate/expand ALL chapters and subchapters across the document.\n"
            f"Detected chapters in the document:\n{ch_list}\n\n"
            f"Detected sections in the document:\n{sec_list}\n\n"
            "CRITICAL REQUIREMENT: You MUST systematically iterate through EACH chapter and its subchapters. "
            "Do NOT stop after editing only one chapter/section! Use `read_file_range` and `str_replace` across Chapter 1, Chapter 2, Chapter 3, etc., to insert extensive, full-page academic content (detailed theory, methodologies, algorithms, benchmarks, equations, and analysis) into every chapter before finishing.\n"
            "Start by reading Chapter 1 with `read_file_range`."
        )
    else:
        # Edit mode — strictly mandate document modification
        user_content = (
            f"FILE: {file_path} ({total_lines} lines)\n\n"
            f"USER REQUEST (EDIT MODE):\n{user_instruction}\n"
            f"{attached_block}\n\n"
            f"{grounding_instruction}\n\n"
            f"{visibility_diagnostic}\n\n"
            f"{redesign_guidance}\n\n"
            "MANDATE: You are in EDIT MODE. User preference is absolute. You MUST make the requested changes and write detailed, comprehensive LaTeX content directly into the document using `str_replace`.\n"
            "If the user asks to elaborate, expand, explain chapters/subchapters, or add content, locate the relevant chapters/sections and insert rich, detailed LaTeX paragraphs, explanations, equations, and subsections into the file.\n"
            "Never conclude with done=true without editing the document.\n"
            "Start by reading the file with `read_file_range` to find where to make your edits."
        )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    # 4. Agent loop
    steps_taken = 0
    agent_explanation = ""
    compile_verified = False

    while steps_taken < actual_max_steps:
        if cancel_token and cancel_token.is_cancelled():
            raise LLMOperationCancelled("Agent loop cancelled by user.")

        steps_taken += 1
        yield {
            "type": "status",
            "step": steps_taken,
            "message": f"Agent reasoning step {steps_taken}/{actual_max_steps}...",
        }

        # LLM call via provider router
        try:
            response = provider_router.chat(
                messages=messages,
                model=model,
                temperature=0.1,
                max_tokens=4096,
                api_keys=api_keys,
            )
        except Exception as e:
            logger.error(f"LLM call failed at step {steps_taken}: {e}")
            yield {
                "type": "status",
                "step": steps_taken,
                "message": f"LLM call failed: {e}",
            }
            break

        content = response.get("content", "").strip()
        parsed = _parse_agent_response(content)

        if not parsed:
            # LLM returned non-JSON — nudge it back
            messages.append({"role": "assistant", "content": content})
            messages.append({
                "role": "user",
                "content": "ERROR: Your response was not valid JSON. Please respond with ONLY a JSON object containing either a tool_call or done=true.",
            })
            continue

        # Extract thought
        thought = parsed.get("thought", "")
        if thought:
            yield {"type": "thought", "content": thought}

        # Check for done signal
        if parsed.get("done"):
            # 1. Enforce that Edit mode must have actually produced document modifications
            if mode == "edit" and not workspace.has_changed() and steps_taken < actual_max_steps:
                logger.info(f"Agent attempted premature done in edit mode at step {steps_taken}; enforcing edits.")
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": (
                        f"REJECTED: You are in EDIT MODE and have made 0 edits to the document (0 lines changed).\n"
                        f"The user's prompt is: \"{user_instruction}\".\n"
                        "User preference is absolute. You MUST modify the LaTeX file using `str_replace`.\n"
                        "Do not declare the document complete without applying the requested design, expansions, or edits into the file.\n"
                        "Inspect the target sections with `read_file_range` and use `str_replace` to apply your modifications now."
                    ),
                })
                continue

            # 2. For broad multi-chapter requests, enforce multi-chapter coverage
            min_expected_edits = min(3, len(valid_chapters) or 3)
            if mode == "edit" and is_broad_request and len(valid_chapters) >= 2 and workspace.get_edit_count() < min_expected_edits and steps_taken < actual_max_steps - 2:
                logger.info(f"Agent attempted early done with only {workspace.get_edit_count()} edits on broad request at step {steps_taken}; prompting to continue.")
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": (
                        f"INCOMPLETE: You have only applied {workspace.get_edit_count()} edit(s) so far, but the user requested to elaborate ALL chapters and subchapters across the document.\n"
                        "You must continue reading the remaining unedited chapters and use `str_replace` to add extensive, detailed LaTeX content across all chapters before signaling done=true."
                    ),
                })
                continue

            agent_explanation = parsed.get("explanation", thought or "Edit completed.")
            break

        # Check for tool call
        tool_call = parsed.get("tool_call")
        if tool_call and isinstance(tool_call, dict):
            tool_name = tool_call.get("name", "")
            tool_args = tool_call.get("arguments", {})

            yield {
                "type": "tool_call",
                "tool": tool_name,
                "args": tool_args,
            }

            # Execute tool
            tool_result = execute_tool(
                tool_name=tool_name,
                args=tool_args,
                workspace=workspace,
            )

            yield {
                "type": "tool_result",
                "tool": tool_name,
                "result": tool_result,
            }

            # Special handling for compile results
            if tool_name == "verify_compile":
                if tool_result.get("success"):
                    compile_verified = True
                    yield {
                        "type": "status",
                        "step": steps_taken,
                        "message": "✓ Shadow compilation passed.",
                    }
                else:
                    compile_verified = False
                    yield {
                        "type": "compile_error",
                        "summary": tool_result.get("stderr", "Compilation failed"),
                        "errors": tool_result.get("errors", []),
                        "message": "Shadow compilation failed. Agent will self-correct...",
                    }

            # Append to conversation for next LLM turn
            messages.append({"role": "assistant", "content": content})

            # Format observation for the LLM
            result_str = json.dumps(tool_result, indent=2, ensure_ascii=False)
            # Truncate very long tool results to prevent context overflow
            if len(result_str) > 8000:
                result_str = result_str[:8000] + "\n... (truncated)"

            # Tailor follow-up instruction based on the tool that just executed
            if tool_name == "get_template_theme":
                followup_msg = (
                    f"TOOL RESULT from `get_template_theme`:\n{result_str}\n\n"
                    "ACTION REQUIRED: You have retrieved the template/theme styling. "
                    "Now use `read_file_range` on the document's preamble (if not yet read) and call `str_replace` "
                    "to apply these theme/color/package changes into the document buffer. "
                    "Do NOT call done=true until you have modified the document using `str_replace`!"
                )
            elif tool_name == "read_file_range":
                followup_msg = (
                    f"TOOL RESULT from `read_file_range`:\n{result_str}\n\n"
                    "Now identify the exact text to replace and use `str_replace` to apply the edits. "
                    "Remember that old_str in `str_replace` must match the file exactly character-for-character."
                )
            elif tool_name == "str_replace":
                followup_msg = (
                    f"TOOL RESULT from `str_replace`:\n{result_str}\n\n"
                    "Edit applied to shadow buffer. Continue with additional `str_replace` edits if needed, "
                    "or call `verify_compile` to verify compilation before setting done=true."
                )
            else:
                followup_msg = (
                    f"TOOL RESULT from `{tool_name}`:\n{result_str}\n\n"
                    "Continue with the next tool call or call `verify_compile` and set done=true when all edits are complete."
                )

            messages.append({
                "role": "user",
                "content": followup_msg,
            })
            continue

        # If LLM produced structured output but no tool_call or done
        # Try to interpret as a direct edit (backward compat with old format)
        if "proposed_chunk" in parsed or "proposed_code" in parsed:
            agent_explanation = parsed.get("explanation", thought or "Edit applied.")
            break

        # Nudge the LLM
        messages.append({"role": "assistant", "content": content})
        messages.append({
            "role": "user",
            "content": (
                "Please respond with a JSON object containing either:\n"
                '- A tool_call: {"thought": "...", "tool_call": {"name": "...", "arguments": {...}}}\n'
                '- Or done signal: {"thought": "...", "done": true, "explanation": "..."}'
            ),
        })

    # 5. Compute and yield diff
    elapsed_ms = int((time.time() - start_time) * 1000)

    if workspace.has_changed():
        # Generate the final_diff payload
        diff_payload = compute_final_diff(
            original=workspace.get_original(),
            modified=workspace.get_buffer(),
            file_path=file_path,
            explanation=agent_explanation,
        )
        yield diff_payload

        # Also yield backward-compatible result event
        edit_items = compute_edit_items(
            original=workspace.get_original(),
            modified=workspace.get_buffer(),
            explanation=agent_explanation,
        )
        yield {
            "type": "result",
            "data": {
                "original_chunk": workspace.get_original(),
                "proposed_chunk": workspace.get_buffer(),
                "explanation": agent_explanation,
                "edits": edit_items,
                "steps_taken": steps_taken,
                "compile_verified": compile_verified,
                "edit_count": workspace.get_edit_count(),
                "elapsed_ms": elapsed_ms,
            },
        }
    else:
        # No changes — return explanation only
        yield {
            "type": "result",
            "data": {
                "original_chunk": "",
                "proposed_chunk": "",
                "explanation": agent_explanation or "Agent completed without modifying the document.",
                "edits": [],
                "steps_taken": steps_taken,
                "compile_verified": False,
                "edit_count": 0,
                "elapsed_ms": elapsed_ms,
            },
        }


# ============================================================================
# Synchronous Wrapper
# ============================================================================

def run_opencode_agent(
    user_instruction: str,
    project_id: str,
    current_code: str,
    file_path: str = "main.tex",
    model: str = DEFAULT_MODEL,
    mode: str = "edit",
    attached_file: Optional[Dict[str, Any]] = None,
    api_keys: Optional[Dict[str, str]] = None,
    max_steps: Optional[int] = None,
    cancel_token: Optional[CancellationToken] = None,
    assets_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Synchronous wrapper around stream_opencode_agent.
    Collects all events and returns the final result dict.
    """
    final_result: Optional[Dict[str, Any]] = None
    events: List[Dict[str, Any]] = []

    for event in stream_opencode_agent(
        user_instruction=user_instruction,
        project_id=project_id,
        current_code=current_code,
        file_path=file_path,
        model=model,
        mode=mode,
        attached_file=attached_file,
        api_keys=api_keys,
        max_steps=max_steps,
        cancel_token=cancel_token,
        assets_dir=assets_dir,
    ):
        events.append(event)
        if event.get("type") == "result":
            final_result = event.get("data", {})

    if not final_result:
        final_result = {
            "original_chunk": "",
            "proposed_chunk": "",
            "explanation": "Agent loop completed without producing a result.",
            "edits": [],
            "steps_taken": 0,
        }

    final_result["events"] = events
    return final_result
