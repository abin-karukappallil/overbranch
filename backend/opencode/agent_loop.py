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
from scope_classifier import classify_scope, ScopeType, ScopeClassificationResult
from document_index import DocumentIndex, DocumentChunk
from edit_validator import (
    validate_coverage, CoverageValidationResult, validate_latex_pre_commit, validate_edit,
)
from attached_context import attached_context_store
from trace import trace_manager, AgentTrace
from document_analyzer import analyze_document, generate_compact_summary, generate_preservation_map, build_task_state
from context_strategy import (
    resolve_context_strategy, build_initial_context, compute_step_max_tokens,
    ContextStrategy, ContextDecision, extract_error_context,
)
from latex_error_fixer import parse_compilation_errors, auto_heal_latex_code, format_compilation_fix_prompt

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

YOUR WORKFLOW & FAST EXECUTION MANDATE:
1. When doing a FULL DOCUMENT REWRITE / TOPIC OVERHAUL, use `rewrite_chunk(chunk_id, new_content)` or batched `tool_calls: [...]` to replace content cleanly by chunk ID.
2. When doing a FULL DOCUMENT EXPANSION ("add more content", "expand document", "make longer"), systematically expand chunks using `insert_into_chunk(chunk_id, content)` or `str_replace` or `rewrite_chunk(chunk_id, new_content)`. You can execute multiple chunks in a single turn using `tool_calls: [...]`.
3. To insert new bibliography entries (`\\bibitem`), citations, or list items, use `insert_into_chunk(chunk_id, content, position='end')`. This automatically places items before `\\end{{thebibliography}}` without breaking the environment.
4. For TARGETED EDITS, apply your change directly on Step 1 if the location is known from the outline, or use `read_file_range`/`grep_search` if line inspection is needed.
5. FAST EDIT RULE: Aim to complete your edit in the minimum number of steps possible (1–2 steps for targeted edits). Set `done=true` immediately as soon as your edits are applied.
6. To inspect attached reference documents or PDFs, use `read_attached_document(filename, start_page, end_page)` or `search_uploaded_references(query)`. You can also read reference files via `read_file_range(file=filename)` or search them with `grep_search(query, file=filename)`.
7. After editing, you may call `verify_compile` to check for LaTeX compilation errors, or set `done=true` if your edit is straightforward.
8. When all edits are complete, respond with the done signal.
9. PDF IMPORT: When the user asks to convert / import / recreate an attached PDF as LaTeX, call `convert_attached_pdf()` instead of transcribing it yourself, then finish immediately with done=true (no document edits). Every page is reproduced as compilable LaTeX with the same text, images, colors, font sizes and spacing as closely as possible, then compiled and compared with the original. Results are best-effort and come with measured per-page similarity — never promise an identical copy.
10. CRITICAL STRUCTURAL INVARIANT: NEVER remove or omit `\\begin{{document}}` or `\\end{{document}}`. Every standalone document MUST have `\\begin{{document}}` separating the preamble from the document body, and `\\end{{document}}` at the end.

{tools_block}

RESPONSE FORMAT:
You must respond with ONLY a JSON object in one of these forms:

A) To call a tool (single or batched):
```json
{{
  "thought": "Applying requested edit directly to the document.",
  "tool_call": {{
    "name": "insert_into_chunk",
    "arguments": {{"chunk_id": "section_2", "content": "\\\\bibitem{{ref1}} Author, Title, 2024."}}
  }}
}}
```
Or for multiple edits in a single fast step:
```json
{{
  "thought": "Expanding sections 1 and 2 in parallel.",
  "tool_calls": [
    {{"name": "insert_into_chunk", "arguments": {{"chunk_id": "section_1", "content": "..."}}}},
    {{"name": "insert_into_chunk", "arguments": {{"chunk_id": "section_2", "content": "..."}}}}
  ]
}}
```

B) When you are DONE (edits applied):
```json
{{
  "thought": "All edits are complete.",
  "done": true,
  "explanation": "Applied requested modifications."
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

3. LATEX CORRECTNESS & STRICT COMPILATION INTEGRITY:
   - Exactly ONE `\\begin{{document}}` and `\\end{{document}}`.
   - Complete environment nesting: Every `\\begin{{env}}` (itemize, enumerate, tabular, tabularx, align, equation, frame, etc.) MUST be closed cleanly with `\\end{{env}}`.
   - In Beamer presentations, every frame MUST be enclosed in `\\begin{{frame}} ... \\end{{frame}}`. Never leave a frame unclosed before `\\end{{document}}` or before the next frame. Never place content outside a frame. Max 6 bullets/slide to prevent overflow.
   - LIST & BULLET INTEGRITY: NEVER write `\\item` outside of a list environment! Every single `\\item` MUST be enclosed within `\\begin{{itemize}} ... \\end{{itemize}}` or `\\begin{{enumerate}} ... \\end{{enumerate}}`. A lonely `\\item` outside a list environment is a fatal LaTeX error!
   - TIKZ INTEGRITY: Every statement inside `\\begin{{tikzpicture}}` (`\\draw`, `\\node`, `\\fill`, `\\path`, `\\coordinate`, `\\clip`, `\\shade`) MUST end with a semicolon (`;`). Multi-line commands must terminate with `;` on the final line. When coordinate arithmetic `($...$)` is used, ALWAYS ensure `\\usetikzlibrary{{calc}}` is in the preamble.
   - Escape text-mode special characters: `_ % & # $` outside math mode. Wrap mathematical variables and equations in `$ ... $`, `\\[ ... \\]`, or `\\begin{{equation}} ... \\end{{equation}}`.
   - Table consistency: In `tabular` / `tabularx`, every row must have the exact number of column dividers (`&`) matching the column specification and end with `\\\\`.
   - Image assets: Use `list_assets` to discover existing images. Reference images using `\\includegraphics[width=\\linewidth,keepaspectratio]{{assets/<filename>}}`. Never invent filenames or insert raw multi-page `.pdf` files into `\\includegraphics`.

4. EXACT-MATCH STR_REPLACE:
   - ALWAYS read the file first before attempting any `str_replace` to copy the exact lines to replace.
   - The `old_str` in `str_replace` MUST be an EXACT copy from the file — copy it character-for-character from the `read_file_range` output.
   - If `str_replace` fails with "EXACT MATCH FAILED", re-read the target area and try again with the correct text.
   - Output ONLY valid JSON. No conversational commentary outside the JSON object.

5. GROUNDING IN EXISTING DOCUMENT DATA & MANDATORY EXPANSION / ELABORATION:
   - When asked to "elaborate", "describe", "expand", "explain more", "add one more additional slide for each topic", or "make longer":
     * YOU ARE IN EDIT MODE: YOU MUST MODIFY `main.tex` IMMEDIATELY. NEVER just explain in chat.
     * Analyze all main topics in the document and elaborate each topic thoroughly using rich LLM-generated technical text, math, tables, and diagrams using the exact same context without hesitation.
     * When user asks for "one more additional slide for each topic", for EVERY topic/slide in the presentation, generate a new dedicated slide (e.g. `\\begin{{frame}}{{<Topic>: Detailed Analysis}}...\\end{{frame}}`) with deep technical detail, examples, or equations.
     * If an attached reference document or PDF is provided, treat it as the PRIMARY SOURCE OF TRUTH. Read its contents with `read_attached_document`, `search_uploaded_references`, or `read_file_range`, extract its real architectural diagrams, benchmark numbers, equations, algorithms, and section outlines, and synthesize them directly into the LaTeX code.
     * Ground all new paragraphs, slides, and subsections in real technical explanations from the attached source material (e.g. specific model names, percentage gaps, system components, citations).
     * Never write superficial or repetitive generic filler — write thorough, rigorous, publication-grade academic prose and equations.
     * NEVER declare done=true without having applied the requested content into the file.

6. DOCUMENT CREATION & CONVERSION MANDATE (FROM SCRATCH OR ATTACHED FILES):
   - When asked to CREATE, GENERATE, BUILD, WRITE, DRAFT, or CONVERT a document (e.g. Presentation/Beamer from a paper, Seminar Report/Thesis from a PDF, Research Paper/IEEE, Resume/CV):
   - If the user attached a PDF or document, carefully read through its key sections (Abstract, Introduction, Architecture, Methodology, Experiments, Conclusion) using the attached preview or `read_attached_document`.
   - Map the attached document's core ideas into the target format:
     * For BEAMER PRESENTATIONS (e.g. converting a paper/PDF to slides): Generate 8-12 informative slides covering Background/Motivation, Problem Statement, System Architecture, Core Methodology, Key Algorithms/Formulations, Experimental Evaluation (with LaTeX tables of numbers from the paper), Discussion, and Conclusion.
     * For SEMINAR REPORTS / THESES: Generate multi-chapter report (`\\documentclass{{report}}`) synthesizing the paper's theory, mathematics, and experiments into comprehensive chapters.
   - For BEAMER PRESENTATIONS (PPT / SLIDES):
     * DEFAULT PPT TEMPLATE MANDATE: You MUST use the **Regalia** template (`get_template_theme(category="ppt", theme_name="regalia")`) by default for all Beamer presentations and slide generation!
     * Regalia Styling: `\\documentclass[aspectratio=169]{{beamer}}`, `\\usetheme{{default}}`, `cream` canvas background (`\\setbeamercolor{{background canvas}}{{bg=cream}}`), `navy` (#0B2545) and `gold` (#C9A24B) accent palette, custom frametitle sidebar with TikZ, elegant small-caps titles, and `[plain]` title slide banner with cream text.
     * NEVER default to generic Madrid or bare unstyled slides — ALWAYS use Regalia as the standard presentation theme.
     * Generate 6-12 content slides (`\\begin{{frame}}{{Title}}{{Subtitle}}`) with clear bullet points (max 5-6 bullets/slide), structured blocks, tables, and equations.
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
   - DEFAULT PPT TEMPLATE: Regalia (`regalia`) is the designated default presentation template.
   - MANDATORY TOOL CALL ON DESIGN OR TEMPLATE CHANGE:
     If the user asks to CHANGE DESIGN, CHANGE TEMPLATE, SWITCH THEME, REDESIGN, or RESTYLE:
     * YOU MUST MAKE A TOOL CALL TO `get_template_theme(category="ppt", theme_name=...)` to refer to other PPT templates from the template library.
     * Available PPT themes include: 'nordlight' (dark modern teal/orange), 'prism' (vibrant geometric), 'minimalist' (Focus clean), 'basic' (custom Madrid), 'sorbonne', 'uwm', and 'regalia'.
     * If the user asks for another design or to change template without naming one, call `get_template_theme(category="ppt", theme_name="list")` to see available themes, or select an alternative like 'nordlight' or 'prism' using `get_template_theme(category="ppt", theme_name="nordlight", extract_section="preamble")`.
     * Then use `read_file_range` on the document's preamble and `str_replace` to swap out the styling while PRESERVING all of the user's slide contents, formulas, equations, and text!

9. SURGICAL MINIMAL EDITS & COMPLETE ENVIRONMENT PRESERVATION (CRITICAL INTEGRITY RULES):
   - RETURN MINIMAL EDITS: Emit surgical, minimal edits targeting only the lines that need to change. Do NOT rewrite entire files or large enclosing blocks when only modifying a few lines.
   - NEVER REMOVE OR ALTER \\begin{{...}} OR \\end{{...}} LINES UNLESS REPLACING THE ENTIRE ENVIRONMENT:
     * Never drop an opening `\\begin{{env}}` or closing `\\end{{env}}` tag.
     * When editing content INSIDE an environment (e.g. adding items inside `itemize` or paths inside `tikzpicture`), preserve the outer `\\begin{{...}}` and `\\end{{...}}` intact.
   - COMPLETE OPENING & CLOSING LINES ON REPLACEMENTS:
     * When replacing an environment, ALWAYS include BOTH the opening line (`\\begin{{...}}`) AND closing line (`\\end{{...}}`) in the replacement.
   - NEVER EMIT PARTIAL ENVIRONMENTS:
     * Never output an unclosed `\\begin{{...}}` or an unmatched `\\end{{...}}`.
     * Every environment (especially `frame`, `tikzpicture`, `itemize`, `enumerate`, `tabular`, `align`, `equation`) must be fully closed and balanced within the proposed edit.
   - BALANCED MATH DELIMITERS & BRACES:
     * Ensure all math delimiters (`$ ... $`, `$$ ... $$`, `\\( ... \\)`, `\\[ ... \\]`) and curly braces `{{ ... }}` are strictly balanced.
     * Never emit an odd number of `$` or unclosed `{{`.
"""


# ============================================================================
# Response Parser & LaTeX JSON Sanitizer
# ============================================================================

# LaTeX control words beginning with "n". In JSON, "\n" is the newline escape,
# so a single-backslash LaTeX macro starting with n is indistinguishable from a
# line break by shape alone -- and decoding \nonumber as newline + "onumber"
# writes an undefined control sequence into the user's document.
_N_LATEX_COMMANDS = (
    "nonumber", "notag", "noindent", "nopagebreak", "nolinebreak", "nobreakspace",
    "nobreak", "noalign", "nocite", "normalsize", "normalfont", "normalcolor",
    "normalem", "newline", "newpage", "newcommand", "newenvironment", "newtheorem",
    "newcounter", "newlength", "newcolumntype", "newsavebox", "newgeometry",
    "newblock", "newfont", "needspace", "node", "nodepart", "nameref", "nicefrac",
    "nullfont", "null", "numberline", "number", "nabla", "nearrow", "nwarrow",
    "nexists", "nparallel", "nsubseteq", "nsupseteq", "nrightarrow", "nleftarrow",
    "nleqslant", "ngeqslant", "notin", "nmid", "neq", "neg", "nu", "ne", "ni",
)
# Longest-first so "ne" cannot shadow "neq" / "newline".
_N_LATEX_ALTS = "|".join(sorted(_N_LATEX_COMMANDS, key=len, reverse=True))
_RE_N_LATEX_BODY = re.compile(r"(?:" + _N_LATEX_ALTS + r")(?![a-zA-Z])")
_RE_SLASH_RUN = re.compile(r"(\\+)(.)")


def _emits_unescaped_latex(text: str) -> bool:
    r"""
    True when this response writes LaTeX backslashes raw (``\begin``) instead of
    escaped for JSON (``\\begin``).

    A single odd-length backslash run before anything other than a real JSON
    escape is proof: ``\b``, ``\f`` and ``\t`` are control characters no model
    means to put in a LaTeX string.
    """
    for m in _RE_SLASH_RUN.finditer(text):
        if len(m.group(1)) % 2 == 1 and m.group(2) not in ('"', "n"):
            return True
        if len(m.group(1)) % 2 == 1 and m.group(2) == "n":
            if _RE_N_LATEX_BODY.match(text, m.start(2)):
                return True
    return False


def sanitize_latex_json(text: str) -> str:
    r"""
    Repairs raw JSON emitted by an LLM so that unescaped LaTeX survives
    ``json.loads``.

    A model that writes ``\begin`` instead of ``\\begin`` inside a JSON string
    hands the decoder escape sequences it never meant: ``\b`` becomes a
    backspace, ``\f`` a form feed, ``\t`` a tab. Each odd-length backslash run
    is therefore doubled.

    Two cases are genuinely ambiguous by shape, and both are resolved by first
    deciding whether the *response as a whole* escapes LaTeX
    (``_emits_unescaped_latex``):

    * ``\n`` is both the JSON newline escape and the prefix of real macros. It is
      doubled for known control words always, and for any ``\n<letters>`` when
      the response is unescaped. A model that escapes properly writes
      ``\\nonumber``, so there ``\n`` is left as a newline.
    * ``\\`` is both an escaped backslash and the LaTeX line break. In an
      unescaped response it is the line break, so a run of exactly two is
      widened to four. Left alone, ``\\[0.3em]`` decoded to ``\[0.3em]`` --
      opening display math where a spaced line break was meant. (That exact
      corruption is common enough that ``auto_heal_latex_code`` carries a
      dedicated rule to undo one symptom of it.)

    The whole transform runs in a single pass over the original text, so a run
    this function widens is never reconsidered and widened twice.
    """
    if not text or "\\" not in text:
        return text

    unescaped = _emits_unescaped_latex(text)

    def _fix(m: "re.Match") -> str:
        slashes, ch = m.group(1), m.group(2)
        n_slashes = len(slashes)

        if n_slashes % 2 == 1:
            if ch == '"':
                return m.group(0)  # a real JSON string escape
            if ch == "n":
                if unescaped or _RE_N_LATEX_BODY.match(m.string, m.start(2)):
                    return slashes + "\\" + ch
                return m.group(0)  # genuine newline escape
            return slashes + "\\" + ch

        # Even run. Only a bare pair is ambiguous, and only when this response
        # does not escape LaTeX: there it is the LaTeX line break `\\`.
        # `\\"` is excluded -- widening it would break the JSON string itself.
        if n_slashes == 2 and unescaped and ch != '"':
            return "\\\\\\\\" + ch
        return m.group(0)

    return _RE_SLASH_RUN.sub(_fix, text)


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

    # Apply sanitize_latex_json to protect LaTeX commands (\begin, \frac, \text, \right, etc.)
    # from being decoded into control characters \x08, \x0c, \x09, \x0d
    sanitized = sanitize_latex_json(cleaned)

    # Try direct parse
    try:
        data = json.loads(sanitized, strict=False)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Extract outermost balanced braces
    start = sanitized.find("{")
    end = sanitized.rfind("}")
    if start != -1 and end > start:
        snippet = sanitized[start:end + 1]
        try:
            data = json.loads(snippet, strict=False)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return {}


# ============================================================================
# Document Structure Indexer & Context Optimization
# ============================================================================

def _build_document_outline(workspace: "ShadowWorkspace") -> str:
    """
    Extracts a concise structural index (preamble, chapters, sections, subsections, frames)
    with exact line numbers from the shadow workspace to guide the LLM directly.
    """
    total_lines = workspace.get_line_count()
    if total_lines <= 1:
        return ""

    outline_items = []

    # Find begin{document} to demarcate preamble
    doc_begins = workspace.grep(r"\\begin\{document\}", is_regex=True)
    if doc_begins and "line_no" in doc_begins[0]:
        preamble_end = doc_begins[0]["line_no"]
        outline_items.append(f"  - Lines 1-{preamble_end}: Preamble & Setup (\\documentclass to \\begin{{document}})")

    # Find chapters, sections, subsections, and Beamer frames
    chapters = workspace.grep(r"\\chapter\{([^}]+)\}", is_regex=True)
    sections = workspace.grep(r"\\section\{([^}]+)\}", is_regex=True)
    subsections = workspace.grep(r"\\subsection\{([^}]+)\}", is_regex=True)
    frames = workspace.grep(r"\\begin\{frame\}(?:\{([^}]+)\})?", is_regex=True)

    structural_elements = []
    for c in chapters:
        if "line_no" in c:
            structural_elements.append((c["line_no"], "chapter", c.get("match", "")))
    for s in sections:
        if "line_no" in s:
            structural_elements.append((s["line_no"], "section", s.get("match", "")))
    for ss in subsections:
        if "line_no" in ss:
            structural_elements.append((ss["line_no"], "subsection", ss.get("match", "")))
    for f in frames:
        if "line_no" in f:
            structural_elements.append((f["line_no"], "frame", f.get("match", "")))

    structural_elements.sort(key=lambda x: x[0])

    for line_no, elem_type, match_str in structural_elements[:40]:  # Cap at 40 markers
        clean_match = match_str.strip().replace("\n", " ")
        if len(clean_match) > 80:
            clean_match = clean_match[:80] + "..."
        if elem_type == "chapter":
            outline_items.append(f"  - Line {line_no}: [CHAPTER] {clean_match}")
        elif elem_type == "section":
            outline_items.append(f"    - Line {line_no}: [SECTION] {clean_match}")
        elif elem_type == "subsection":
            outline_items.append(f"      - Line {line_no}: [SUBSECTION] {clean_match}")
        elif elem_type == "frame":
            outline_items.append(f"  - Line {line_no}: [FRAME/SLIDE] {clean_match}")

    if not outline_items:
        return f"DOCUMENT SCALE: {total_lines} lines total."

    return (
        "DOCUMENT STRUCTURE OUTLINE (Target these line numbers directly with `read_file_range` / `str_replace`):\n"
        + "\n".join(outline_items)
    )


def _compact_conversation_history(
    messages: List[Dict[str, Any]],
    keep_recent_turns: int = 2,
) -> List[Dict[str, Any]]:
    """
    Prunes and compacts older conversation turns before sending to the LLM.
    
    Keeps:
    - System message intact (index 0)
    - Initial user instruction intact (index 1)
    - Recent N turns (assistant + user pairs) completely intact
    
    Compacts older turns:
    - Replaces large tool output payloads and assistant drafts with concise markers.
    - Dramatically reduces token count and speeds up LLM processing time.
    """
    if len(messages) <= 2 + (keep_recent_turns * 2):
        return messages

    cutoff_index = len(messages) - (keep_recent_turns * 2)
    compacted: List[Dict[str, Any]] = []

    for idx, msg in enumerate(messages):
        if idx < 2 or idx >= cutoff_index:
            compacted.append(msg)
            continue

        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "assistant":
            # Compact older assistant output: preserve thought + tool name, drop massive LaTeX replacement strings
            if len(content) > 300:
                try:
                    data = json.loads(content)
                    thought_preview = str(data.get("thought", ""))[:120]
                    t_call = data.get("tool_call") or data.get("tool_calls")
                    t_summary = ""
                    if isinstance(t_call, dict):
                        t_summary = f"tool_call={t_call.get('name')}"
                    elif isinstance(t_call, list):
                        t_summary = f"tool_calls={[c.get('name') for c in t_call if isinstance(c, dict)]}"
                    compacted.append({
                        "role": "assistant",
                        "content": json.dumps({
                            "thought": thought_preview + ("..." if len(thought_preview) >= 120 else ""),
                            "status": "Executed in earlier step",
                            "action": t_summary or "edit",
                        })
                    })
                    continue
                except Exception:
                    compacted.append({
                        "role": "assistant",
                        "content": content[:200] + "\n... [previous assistant output compressed]",
                    })
                    continue
            compacted.append(msg)
        elif role == "user":
            if "TOOL RESULT from `read_file_range`:" in content or "TOOL RESULT from read_file_range:" in content:
                compacted.append({
                    "role": "user",
                    "content": "[TOOL RESULT from read_file_range: Lines read and processed in earlier step.]",
                })
            elif "TOOL RESULT from `rewrite_chunk`:" in content or "TOOL RESULT from rewrite_chunk:" in content:
                compacted.append({
                    "role": "user",
                    "content": "[TOOL RESULT from rewrite_chunk: Chunk updated successfully in earlier step.]",
                })
            elif "TOOL RESULT from `str_replace`:" in content or "TOOL RESULT from str_replace:" in content:
                compacted.append({
                    "role": "user",
                    "content": "[TOOL RESULT from str_replace: Text replaced successfully in earlier step.]",
                })
            elif "TOOL RESULT from `insert_into_chunk`:" in content or "TOOL RESULT from insert_into_chunk:" in content:
                compacted.append({
                    "role": "user",
                    "content": "[TOOL RESULT from insert_into_chunk: Content inserted successfully in earlier step.]",
                })
            elif "TOOL RESULT from `get_template_theme`:" in content or "TOOL RESULT from get_template_theme:" in content:
                compacted.append({
                    "role": "user",
                    "content": "[TOOL RESULT from get_template_theme: Template theme retrieved in earlier step.]",
                })
            elif "TOOL RESULT from `grep_search`:" in content or "TOOL RESULT from grep_search:" in content:
                compacted.append({
                    "role": "user",
                    "content": "[TOOL RESULT from grep_search: Search query executed in earlier step.]",
                })
            elif "TOOL RESULT from `search_uploaded_references`:" in content or "TOOL RESULT from search_uploaded_references:" in content:
                compacted.append({
                    "role": "user",
                    "content": "[TOOL RESULT from search_uploaded_references: Uploaded context query executed in earlier step.]",
                })
            elif "BATCH TOOL RESULTS" in content:
                compacted.append({
                    "role": "user",
                    "content": "[BATCH TOOL RESULTS: Batched edits applied successfully in earlier step.]",
                })
            elif "TOOL RESULT from `verify_compile`:" in content or "TOOL RESULT from verify_compile:" in content:
                compacted.append({
                    "role": "user",
                    "content": "[TOOL RESULT from verify_compile: Compilation check completed in earlier step.]",
                })
            elif "COVERAGE CHECK FAILED" in content:
                compacted.append({
                    "role": "user",
                    "content": "[COVERAGE CHECK: Missing chunks reported in earlier step.]",
                })
            elif "COMPILATION ERRORS:" in content:
                compacted.append({
                    "role": "user",
                    "content": "[COMPILATION ERRORS: Compilation errors diagnosed in earlier step.]",
                })
            elif len(content) > 400:
                compacted.append({
                    "role": "user",
                    "content": content[:200] + "\n... [previous step output compressed for efficiency]",
                })
            else:
                compacted.append(msg)
        else:
            compacted.append(msg)

    return compacted


# ============================================================================
# Dynamic Adaptive Step Budgeting
# ============================================================================

MAX_STEP_BUDGET = 32


def determine_adaptive_step_budget(
    user_instruction: str,
    total_lines: int,
    num_chapters: int,
    num_sections: int,
    num_chunks: int = 0,
    scope: str = "TARGETED_EDIT",
    mode: str = "edit",
    requested_steps: Optional[int] = None,
) -> int:
    """
    Dynamically determines the agent reasoning step budget from:
    1. Scope (FULL_DOCUMENT_REWRITE / EXPANSION get room to touch every chunk)
    2. User prompt intent and complexity (creation vs broad overhaul vs single-target fix)
    3. Document scale (number of chapters, sections, and total lines)
    4. Mode (Ask vs Edit)

    The result is capped at MAX_STEP_BUDGET. Every step is a full LLM round trip
    and round trips dominate wall-clock time, so an unbounded budget is an
    uncapped latency bill: the previous ``max(16, chunks * 2 + 4)`` handed a
    20-section report 44 steps and a 40-frame deck 84 -- for work the prompt
    explicitly asks the model to *batch* into a handful of turns.
    """
    return min(MAX_STEP_BUDGET, _raw_step_budget(
        user_instruction=user_instruction,
        total_lines=total_lines,
        num_chapters=num_chapters,
        num_sections=num_sections,
        num_chunks=num_chunks,
        scope=scope,
        mode=mode,
        requested_steps=requested_steps,
    ))


def _raw_step_budget(
    user_instruction: str,
    total_lines: int,
    num_chapters: int,
    num_sections: int,
    num_chunks: int = 0,
    scope: str = "TARGETED_EDIT",
    mode: str = "edit",
    requested_steps: Optional[int] = None,
) -> int:
    """Unclamped heuristic behind determine_adaptive_step_budget."""
    if mode == "ask":
        return requested_steps if (requested_steps and requested_steps > 0) else 4

    # 1. Full document rewrite & expansion: enough room to batch every chunk,
    #    not one step per chunk. The prompt mandates batched `tool_calls: [...]`
    #    and compute_step_max_tokens funds it, so the budget assumes several
    #    chunks land per turn plus headroom for verification and self-correction.
    if scope in (
        ScopeType.FULL_DOCUMENT_REWRITE.value,
        "FULL_DOCUMENT_REWRITE",
        ScopeType.FULL_DOCUMENT_EXPANSION.value,
        "FULL_DOCUMENT_EXPANSION",
    ):
        effective_chunks = max(num_chunks, num_chapters, num_sections, 1)
        full_budget = 8 + (effective_chunks + 1) // 2
        if requested_steps and requested_steps > 0:
            return max(requested_steps, full_budget)
        return full_budget

    if requested_steps and requested_steps > 0:
        return requested_steps

    user_lower = user_instruction.lower()

    # 2. Minor / Quick localized fixes (typos, citations, bibliography, single word)
    minor_keywords = [
        "typo", "spelling", "rename", "change author", "change title",
        "fix date", "replace word", "single word", "line number", "grammar",
        "citation", "cite", "bibitem", "add reference", "add bibitem",
    ]
    if any(kw in user_lower for kw in minor_keywords) and len(user_instruction.split()) <= 15:
        return 4

    # 3. Creation / Conversion requests (from scratch or attached PDF)
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
            return 12
        elif any(k in user_lower for k in ["report", "thesis", "dissertation", "seminar"]):
            return 14
        elif any(k in user_lower for k in ["paper", "article", "ieee"]):
            return 12
        else:
            return 10

    # 4. Redesign / New design / Theme change requests
    redesign_keywords = [
        "redesign", "new design", "change design", "better design", "different design",
        "need new design", "need a new design", "change theme", "switch theme", "apply theme",
        "new theme", "different theme", "better theme", "modern theme", "nordlight", "prism", "regalia",
        "make it look better", "re-theme", "restyle", "improve design", "color theme", "beamer theme",
    ]
    if any(kw in user_lower for kw in redesign_keywords):
        return 10

    # 5. Broad / Multi-chapter requests
    broad_keywords = [
        "all chapter", "every chapter", "each chapter", "all subchapter",
        "each subchapter", "every subchapter", "all section", "every section",
        "each section", "whole document", "entire document", "all topic",
        "each topic", "every topic", "throughout the document", "full report",
        "rewrite document", "complete report", "expand all", "all pages",
        "each slide", "every slide", "all slide", "for each slide",
        "each frame", "every frame", "all frame", "for each frame",
        "for each topic", "for each section", "for each chapter",
        "all topics", "all slides", "all frames",
        "each page", "every page", "for each page",
        "more slides", "more pages", "more frames",
        "additional slide", "additional page", "additional frame",
        "explain more", "elaborate more",
    ]
    if any(kw in user_lower for kw in broad_keywords):
        if num_chapters >= 4:
            return min(18, 6 + num_chapters * 2)
        elif num_chapters >= 2:
            return 14
        elif num_sections >= 5:
            return 12
        else:
            return 10

    # 6. Medium multi-part edits (e.g. "add sections X and Y", "insert figures and tables")
    medium_keywords = [
        "add", "insert", "elaborate", "expand", "explain",
        "table", "figure", "methodology", "literature", "results", "analysis",
    ]
    match_count = sum(1 for kw in medium_keywords if kw in user_lower)
    if match_count >= 2 or num_chapters >= 3:
        return 10


    # 7. Standard single edit default
    return 6


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
    attached_files: Optional[List[Dict[str, Any]]] = None,
    api_keys: Optional[Dict[str, str]] = None,
    max_steps: Optional[int] = None,
    cancel_token: Optional[CancellationToken] = None,
    assets_dir: Optional[str] = None,
    session_id: Optional[str] = None,
    project_files: Optional[Dict[str, str]] = None,
    user_context: Optional[Dict[str, Any]] = None,
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
    effective_session_id = session_id or project_id or "default"

    # 1. Initialize ShadowWorkspace
    workspace = ShadowWorkspace(
        original_code=current_code,
        project_id=project_id,
        file_path=file_path,
        assets_dir=assets_dir,
        session_id=effective_session_id,
    )
    # Caller identity, used by tools that act on the user's behalf (e.g. convert_attached_pdf)
    workspace.user_context = user_context or {}

    # Load auxiliary project files if provided (multi-file workspace support)
    if project_files:
        for p_path, p_content in project_files.items():
            if p_path != file_path and p_content is not None:
                workspace.add_auxiliary_file(p_path, p_content)

    # 1b. Store & mount attached reference document(s) into session cache and ShadowWorkspace
    if attached_file:
        attached_context_store.store_attachment(effective_session_id, attached_file)
    if attached_files:
        for af in attached_files:
            if af:
                attached_context_store.store_attachment(effective_session_id, af)

    stored_attachments = attached_context_store.get_attachments(effective_session_id)
    for sf in stored_attachments:
        s_name = sf.get("filename", "reference.txt")
        s_full = sf.get("full_content") or sf.get("content", "")
        if s_full:
            workspace.add_reference_file(s_name, s_full)

    if stored_attachments:
        ref_summary_parts = []
        for sf in stored_attachments:
            fn = sf.get("filename", "Attached document")
            pg_cnt = sf.get("page_count", 0)
            sz = sf.get("size", len(sf.get("content", "")))
            if pg_cnt > 0:
                ref_summary_parts.append(f"{fn} ({pg_cnt} pages, {sz:,} chars)")
            else:
                ref_summary_parts.append(f"{fn} ({sz:,} chars)")
        yield {
            "type": "status",
            "step": 0,
            "message": f"Attached reference document(s) loaded: {', '.join(ref_summary_parts)}. Grounding agent in reference material.",
        }

    # 2. Classify edit scope (TARGETED_EDIT vs FULL_DOCUMENT_REWRITE vs FULL_DOCUMENT_EXPANSION)
    scope_result = classify_scope(
        user_instruction=user_instruction,
        current_code=current_code,
        model=model,
        api_keys=api_keys,
    )
    scope = scope_result.scope
    is_full_rewrite = scope_result.is_full_rewrite
    is_expansion = scope_result.is_expansion

    # Detect compilation error fix requests ("Ask AI to Fix" / raw compilation logs)
    compilation_error_patterns = [
        r"fix this (?:latex )?compilation error",
        r"compilation error",
        r"latex error:",
        r"package [\w\-]+ error:",
        r"! emergency stop",
        r"!  ==> fatal error occurred",
        r"fatal error occurred",
        r"bad math environment delimiter",
        r"giving up on this path",
        r"did you forget a sem",
        r"ended by \\end",
        r"ask ai to fix",
        r"undefined control sequence",
        r"runaway argument",
        r"missing \\begin\{document\}",
        r"(?:^|\s|\n)\./[\w\-./]+\.tex:\d+:",
        r"(?:^|\s|\n)[\w\-./]+\.tex:\d+:",
    ]
    is_compilation_fix_request = any(
        re.search(pat, user_instruction, re.IGNORECASE) for pat in compilation_error_patterns
    )
    if is_compilation_fix_request:
        scope = ScopeType.TARGETED_EDIT.value
        is_full_rewrite = False
        is_expansion = False

    all_chunks = workspace.get_all_chunks()
    content_chunks = workspace.get_content_chunks()
    num_content_chunks = len(content_chunks)

    yield {
        "type": "status",
        "step": 0,
        "message": f"Edit scope detected: {scope.replace('_', ' ').title()}",
        "scope": scope,
        "is_full_rewrite": is_full_rewrite,
        "is_expansion": is_expansion,
    }

    # 3. Build system prompt with tool definitions
    tools_block = get_tools_prompt_block()
    system_prompt = OPENCODE_SYSTEM_PROMPT.format(tools_block=tools_block)

    total_lines = workspace.get_line_count()
    user_lower = user_instruction.lower()

    # ================================================================
    # 3a. Document Analysis (local, no LLM — fast)
    # ================================================================
    doc_analysis = analyze_document(current_code)
    preservation_map = generate_preservation_map(doc_analysis, user_instruction)
    doc_summary = generate_compact_summary(doc_analysis)

    yield {
        "type": "status",
        "step": 0,
        "message": f"Analyzed document: {doc_analysis.total_lines} lines, {doc_analysis.structural_unit_count} {doc_analysis.primary_structure_type}s, ~{doc_analysis.estimated_tokens} tokens",
    }

    # ================================================================
    # 3b. Context Strategy Resolution
    # ================================================================

    # 4. Detect redesign / theme change requests
    redesign_keywords = [
        "redesign", "change theme", "switch theme", "apply theme", "new theme",
        "better theme", "modern theme", "nordlight", "prism", "regalia",
        "make it look better", "re-theme", "restyle", "improve design", "color theme",
        "change design", "change the design", "change template", "change the template",
        "switch design", "switch the design", "switch template", "switch the template",
        "different design", "different template", "another template", "another theme",
        "new design", "change ppt template", "change ppt design", "switch ppt template",
        "other template", "other theme", "different ppt", "another ppt",
        "change the slide design", "change slide design", "update template", "update design",
        "switch to nordlight", "switch to prism", "switch to regalia",
        "theme to nordlight", "theme to prism", "theme to regalia",
        "template to nordlight", "template to prism", "template to regalia",
    ]
    redesign_patterns = [
        r'\b(?:change|switch|update|replace|modify|alter|choose|use)\s+(?:the\s+)?(?:ppt\s+|beamer\s+|slide\s+)?(?:design|template|theme|style)\b',
        r'\b(?:redesign|restyle|re-style|retheme|re-theme)\b',
        r'\b(?:different|another|new|other|alternative)\s+(?:ppt\s+|beamer\s+|slide\s+)?(?:design|template|theme|style)\b',
        r'\b(?:template|theme)\s+(?:to|for)\s+\w+\b',
        r'\b(?:switch\s+to|use)\s+(?:nordlight|prism|regalia|minimalist|basic|sorbonne|uwm)\b',
    ]
    is_redesign_regex = any(bool(re.search(pat, user_lower)) for pat in redesign_patterns)
    is_redesign_kw = any(kw in user_lower for kw in redesign_keywords)
    is_redesign_request = (is_redesign_regex or is_redesign_kw) and mode == "edit"
    redesign_guidance = ""
    if is_redesign_request:
        redesign_guidance = (
            "\n\n=========================================================\n"
            "REDESIGN / TEMPLATE CHANGE MANDATE (MANDATORY TOOL CALL):\n"
            "The user explicitly asked to CHANGE THE DESIGN or TEMPLATE of the document.\n"
            "MANDATORY WORKFLOW:\n"
            "1. YOU MUST MAKE A TOOL CALL TO `get_template_theme` on Step 1 to fetch the new template/theme styling:\n"
            "   - If user specified a theme name (e.g. 'nordlight', 'prism', 'minimalist', 'regalia', 'basic', 'sorbonne', 'uwm'):\n"
            "     Call `get_template_theme(category='ppt', theme_name='<theme>', extract_section='preamble')`.\n"
            "   - If user asked to change design/template without naming one, call `get_template_theme(category='ppt', theme_name='list')` or fetch an alternative PPT template like 'nordlight' or 'prism':\n"
            "     `get_template_theme(category='ppt', theme_name='nordlight', extract_section='preamble')`.\n"
            "2. Read the current preamble with `read_file_range` from line 1 to \\begin{document}.\n"
            "3. Use `str_replace` to update the styling, color definitions, and packages in the preamble while PRESERVING all user frames, sections, formulas, and text.\n"
            "4. Run `verify_compile` to confirm the redesigned document compiles cleanly with 0 errors.\n"
            "=========================================================\n"
        )

    # 5. Detect broad multi-chapter requests
    broad_keywords = [
        "all chapter", "every chapter", "each chapter", "all subchapter",
        "each subchapter", "every subchapter", "all section", "every section",
        "each section", "whole document", "entire document", "all topic",
        "each topic", "every topic", "throughout the document", "full report",
        "each slide", "every slide", "all slide", "for each slide",
        "each frame", "every frame", "all frame", "for each frame",
        "for each topic", "for each section", "for each chapter",
        "all topics", "all slides", "all frames", "all pages",
        "each page", "every page", "for each page",
        "more slides", "more pages", "more frames",
        "additional slide", "additional page", "additional frame",
        "explain more", "elaborate more",
    ]

    is_broad_request = (any(kw in user_lower for kw in broad_keywords) or is_full_rewrite or is_expansion) and not is_compilation_fix_request

    # 6. Detect document creation / conversion requests
    creation_keywords = [
        "create", "make", "generate", "build", "compose", "prepare", "draft",
        "turn this pdf", "convert this pdf", "using this pdf", "new report",
        "new presentation", "new document", "create a ppt", "create presentation",
        "create beamer", "create report", "create paper", "create resume",
        "create cv", "from scratch", "write a report", "write a paper",
        "write a presentation", "make a presentation", "make a report",
        "convert", "turn into", "from this pdf", "from the attached",
    ]
    is_empty_or_minimal = (
        total_lines <= 5
        or not current_code.strip()
        or (total_lines <= 20 and "\\documentclass" in current_code and "\\end{document}" in current_code and len(current_code.strip().splitlines()) <= 8)
    )
    is_creation_intent = any(kw in user_lower for kw in creation_keywords)
    has_attachment_conversion = bool(stored_attachments) and any(
        kw in user_lower for kw in ["ppt", "presentation", "slides", "beamer", "report", "paper", "convert", "turn", "make", "create"]
    )
    # If the user is explicitly requesting a redesign/template change on an existing document, treat as edit, not creation
    is_creation_request = (
        (is_creation_intent or is_empty_or_minimal or has_attachment_conversion)
        and mode == "edit"
        and not (is_redesign_request and current_code.strip())
        and not is_compilation_fix_request
    )

    # Resolve context strategy based on document analysis + scope + model
    context_decision = resolve_context_strategy(
        analysis=doc_analysis,
        scope=scope,
        model=model,
        user_instruction=user_instruction,
        is_creation=is_creation_request,
    )

    yield {
        "type": "status",
        "step": 0,
        "message": f"Context strategy: {context_decision.strategy.value} ({context_decision.reason})",
    }

    # 7. Detect visibility / contrast bug reports
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

    # 7b. Detect compilation error fix requests ("Ask AI to Fix" / raw compilation logs)
    compilation_fix_diagnostic = ""
    parsed_compilation_errors_list = []
    if is_compilation_fix_request:
        parsed_compilation_errors_list = parse_compilation_errors(user_instruction)
        healed_code, fixes_applied = auto_heal_latex_code(workspace.get_buffer(), user_instruction)
        if healed_code != workspace.get_buffer():
            # replace_all re-validates and may refuse; only report a heal that landed.
            heal_res = workspace.replace_all(healed_code)
            if heal_res.get("success"):
                try:
                    workspace.ensure_document_structure()
                except Exception as e:
                    logger.warning(f"ensure_document_structure note: {e}")
                logger.info(f"Auto-healed workspace buffer on compilation fix request: {fixes_applied}")
                yield {
                    "type": "status",
                    "step": 0,
                    "message": f"Pre-healed document structure: {', '.join(fixes_applied[:3])}",
                }
            else:
                logger.warning(
                    f"Pre-heal rejected by pre-commit validation, buffer left as-is: "
                    f"{heal_res.get('validation_errors', [])[:3]}"
                )
        compilation_fix_diagnostic = format_compilation_fix_prompt(
            raw_error=user_instruction,
            parsed_errors=parsed_compilation_errors_list,
            workspace=workspace,
            fixes_applied=fixes_applied,
        )

    chapters = workspace.grep(r"\\chapter\{([^}]+)\}", is_regex=True)
    sections = workspace.grep(r"\\section\{([^}]+)\}", is_regex=True)
    valid_chapters = [c for c in chapters if "line_no" in c]
    valid_sections = [s for s in sections if "line_no" in s]

    # Calculate flexible, adaptive reasoning step budget (scaled dynamically for full rewrites)
    actual_max_steps = determine_adaptive_step_budget(
        user_instruction=user_instruction,
        total_lines=total_lines,
        num_chapters=len(valid_chapters),
        num_sections=len(valid_sections),
        num_chunks=num_content_chunks,
        scope=scope,
        mode=mode,
        requested_steps=max_steps,
    )

    agent_trace = AgentTrace(
        project_id=project_id,
        model_used=model,
        task_classification={
            "scope": scope,
            "is_full_rewrite": is_full_rewrite,
            "is_expansion": is_expansion,
            "context_strategy": context_decision.strategy.value,
            "doc_tokens": doc_analysis.estimated_tokens,
            "fits_in_context": context_decision.fits_in_context,
        },
        step_budget_allocated=actual_max_steps,
    )

    # Format attached reference document from active session cache
    attached_block = ""
    if stored_attachments:
        stored_files_text = []
        for sf in stored_attachments:
            s_name = sf.get("filename", "Attached Document")
            s_type = sf.get("file_type", "document")
            s_pages = sf.get("page_count", 0)
            s_is_scanned = sf.get("is_scanned", False)
            s_content = sf.get("content", "")

            header = f"ATTACHED REFERENCE FILE: {s_name} (Type: {s_type}"
            if s_pages > 0:
                header += f", Pages: {s_pages}"
            header += ")"

            if s_is_scanned:
                body = (
                    f"{header}\n"
                    f"NOTE: This PDF appears to contain mostly scanned images. Extracted text was sparse:\n"
                    f"{s_content[:5000]}"
                )
            elif s_content:
                fcontent_capped = s_content[:40000]
                body = (
                    f"{header}\n"
                    f"---------------------------------------------------------\n"
                    f"{fcontent_capped}"
                )
                if len(s_content) > 40000:
                    body += f"\n... [Truncated preview: {len(s_content):,} chars total. Use `read_attached_document(filename='{s_name}', start_page=...)` or `search_uploaded_references(query=...)` to read any section/page in full.]"
            else:
                body = f"{header}\n(Empty or unparseable content)"
            stored_files_text.append(body)

        if stored_files_text:
            attached_block = (
                "\n=========================================================\n"
                "ATTACHED REFERENCE DOCUMENTS (PRIMARY SOURCE MATERIAL):\n"
                + "\n\n---------------------------------------------------------\n".join(stored_files_text) +
                "\n=========================================================\n"
                "CRITICAL MANDATE FOR ATTACHED DOCUMENTS:\n"
                "1. The user provided the above reference document(s) as PRIMARY SOURCE MATERIAL for this request.\n"
                "2. You MUST cite, refer to, extract, and incorporate real data, section topics, algorithms, methodologies, benchmark tables, and findings from this reference document into your LaTeX output.\n"
                "3. To inspect specific pages, use `read_attached_document(filename=..., start_page=..., end_page=...)`.\n"
                "4. To search for specific keywords or formulas, use `search_uploaded_references(query=...)` or `grep_search(query=..., file=...)`.\n"
                "5. You can also read reference document lines directly using `read_file_range(file=...)`."
            )

    # Grounding reminder for content creation
    grounding_instruction = (
        "\nGROUNDING RULE: When creating, elaborating, or describing topics, extract and use the specific findings, statistics, "
        "database names, model metrics, formulas, and concepts already present in the existing LaTeX code or in the attached document "
        "to write deep, authentic academic prose and equations directly in the document."
    )

    # Extract document structure outline to guide agent directly to target lines
    doc_outline = _build_document_outline(workspace)

    # ================================================================
    # 3c. Build Task State (compact representation for cross-iteration reuse)
    # ================================================================
    task_state = build_task_state(
        user_instruction=user_instruction,
        analysis=doc_analysis,
        preservation_map=preservation_map,
        scope=scope,
        attached_documents=stored_attachments,
    )

    # ================================================================
    # 3d. Build Smart Initial Context using Context Strategy
    # ================================================================
    smart_document_context = build_initial_context(
        decision=context_decision,
        analysis=doc_analysis,
        workspace=workspace,
        user_instruction=user_instruction,
        doc_outline=doc_outline,
    )

    # Build preservation/transformation guidance for full rewrites
    transformation_guidance = ""
    if is_full_rewrite or is_expansion:
        pres = preservation_map.get("preserve", [])
        change = preservation_map.get("change", [])
        expand = preservation_map.get("expand", [])
        if pres or change or expand:
            parts = ["TRANSFORMATION GUIDE:"]
            if pres:
                parts.append(f"  Preserve: {', '.join(pres)}")
            if change:
                parts.append(f"  Change: {', '.join(change)}")
            if expand:
                expand_str = "all sections" if expand == "all" else ", ".join(expand)
                parts.append(f"  Expand: {expand_str}")
            transformation_guidance = "\n".join(parts)

    # Build initial message context tailored to mode & intent
    trans_block = f"\n\n{transformation_guidance}" if transformation_guidance else ""

    if mode == "ask":
        user_content = (
            f"USER QUESTION (ASK MODE):\n{user_instruction}\n\n"
            f"{attached_block}\n\n"
            f"FILE: {file_path} ({total_lines} lines)\n\n"
            f"{task_state}\n\n"
            f"{smart_document_context}\n\n"
            "This is ASK mode. Answer the user's question directly by reading and citing the attached document and current LaTeX file. "
            "Set done=true and provide your comprehensive answer in the explanation field."
        )
    elif is_full_rewrite and content_chunks and mode == "edit":
        chunk_items = "\n".join([f"  - Chunk ID `{c.chunk_id}`: {c.title} (Lines {c.start_line}–{c.end_line})" for c in content_chunks])
        user_content = (
            f"USER REQUEST (EDIT MODE — FULL DOCUMENT REWRITE / TOPIC OVERHAUL):\n{user_instruction}\n\n"
            f"{attached_block}\n\n"
            f"FILE: {file_path} ({total_lines} lines)\n\n"
            f"{task_state}\n\n"
            f"{smart_document_context}\n\n"
            f"{trans_block}\n\n"
            f"{grounding_instruction}\n\n"
            f"{visibility_diagnostic}\n\n"
            f"{redesign_guidance}\n\n"
            "=========================================================\n"
            "MANDATE: The user explicitly requested a FULL DOCUMENT REWRITE / TOPIC REPLACEMENT.\n"
            f"Detected scope: FULL_DOCUMENT_REWRITE ({num_content_chunks} content chunks to rewrite).\n\n"
            f"ORDERED LIST OF DOCUMENT CHUNKS:\n{chunk_items}\n\n"
            "CRITICAL INSTRUCTIONS FOR FAST FULL REWRITE:\n"
            "1. You MUST rewrite EVERY content chunk using the `rewrite_chunk(chunk_id, new_content)` tool.\n"
            "2. HIGH-SPEED BATCHING MANDATE: Use batched `tool_calls: [...]` to rewrite all content chunks in a single turn (or minimum turns) rather than one round-trip per chunk!\n"
            "3. `rewrite_chunk` uses structural AST byte offsets rather than exact string matches, guaranteeing complete section replacement without needing prior `read_file_range`.\n"
            "4. Completely replace all old topic content and terminology with the new topic/source material.\n"
            "5. After rewriting all chunks, call `verify_compile` ONCE to verify the completed document compiles cleanly.\n"
            "6. Coverage validation will verify that EVERY content chunk was rewritten before allowing completion.\n"
            "Start by applying your rewrites across the content chunks now using batched `tool_calls: [...]`.\n"
            "========================================================="
        )
    elif is_expansion and content_chunks and mode == "edit":
        chunk_items = "\n".join([f"  - Chunk ID `{c.chunk_id}`: {c.title} (Lines {c.start_line}–{c.end_line})" for c in content_chunks])
        user_content = (
            f"USER REQUEST (EDIT MODE — FULL DOCUMENT EXPANSION):\n{user_instruction}\n\n"
            f"{attached_block}\n\n"
            f"FILE: {file_path} ({total_lines} lines)\n\n"
            f"{task_state}\n\n"
            f"{smart_document_context}\n\n"
            f"{trans_block}\n\n"
            f"{grounding_instruction}\n\n"
            f"{visibility_diagnostic}\n\n"
            f"{redesign_guidance}\n\n"
            "=========================================================\n"
            "MANDATE: The user explicitly requested to EXPAND / ADD MORE CONTENT across the document.\n"
            f"Detected scope: FULL_DOCUMENT_EXPANSION ({num_content_chunks} content chunks to expand).\n\n"
            f"ORDERED LIST OF DOCUMENT CHUNKS:\n{chunk_items}\n\n"
            "CRITICAL INSTRUCTIONS FOR FAST FULL EXPANSION:\n"
            "1. You MUST expand EVERY content chunk (chapters, sections, subtopics). Do NOT stop after only expanding the first section!\n"
            "2. HIGH-SPEED BATCHING MANDATE: Use batched `tool_calls: [...]` with `rewrite_chunk(chunk_id, new_content)` or `insert_into_chunk(chunk_id, content)` across all chunks in a single turn to minimize agent latency.\n"
            "3. Add rich academic paragraphs, mathematical formulations, benchmarks, subtopics, and analysis to every section.\n"
            "4. To insert bibliography entries or list items, use `insert_into_chunk(chunk_id, content, position='end')`.\n"
            "5. After expanding all chunks, call `verify_compile` ONCE to confirm zero LaTeX compilation errors before signaling done=true.\n"
            "6. Coverage validation will verify that EVERY content chunk was expanded before allowing completion.\n"
            "Start by expanding the chunks now using batched `tool_calls: [...]`.\n"
            "========================================================="
        )
    elif is_creation_request:
        # Determine archetype guidance
        is_ppt = bool(re.search(r'\b(?:ppt|presentation|beamer|slides?|deck)\b', user_lower))
        is_rep = bool(re.search(r'\b(?:report|thesis|dissertation|seminar\s+report)\b', user_lower))
        is_pap = bool(re.search(r'\b(?:paper|research\s+paper|article|ieee|conference)\b', user_lower))
        is_res = bool(re.search(r'\b(?:resume|cv|curriculum\s+vitae)\b', user_lower))

        if is_ppt:
            archetype_hint = (
                "DOCUMENT TARGET: BEAMER PRESENTATION (SLIDES) — DEFAULT TEMPLATE: REGALIA\n"
                "- DEFAULT PPT TEMPLATE MANDATE: You MUST use the REGALIA presentation template (formal navy & gold, cream background) by default.\n"
                "- Regalia Specification:\n"
                "  * Document class: `\\documentclass[aspectratio=169]{beamer}`\n"
                "  * Theme base: `\\usetheme{default}`\n"
                "  * Packages: `\\usepackage[T1]{fontenc}\\usepackage[utf8]{inputenc}\\usepackage{tikz,booktabs,amsmath}\\usetikzlibrary{calc}`\n"
                "  * Palette:\n"
                "    `\\definecolor{navy}{HTML}{0B2545}\\definecolor{navylight}{HTML}{13315C}\\definecolor{gold}{HTML}{C9A24B}`\n"
                "    `\\definecolor{cream}{HTML}{F7F4EC}\\definecolor{ink}{HTML}{1D1D1D}\\definecolor{muted}{HTML}{5C6270}`\n"
                "  * Colors:\n"
                "    `\\setbeamercolor{background canvas}{bg=cream}\\setbeamercolor{normal text}{fg=ink,bg=cream}`\n"
                "    `\\setbeamercolor{frametitle}{fg=navy}\\setbeamercolor{title}{fg=navy}`\n"
                "    `\\setbeamercolor{itemize item}{fg=gold}\\setbeamercolor{itemize subitem}{fg=navylight}`\n"
                "    `\\setbeamercolor{block title}{fg=cream,bg=navy}\\setbeamercolor{block body}{fg=ink,bg=white}`\n"
                "    `\\setbeamercolor{page number in head/foot}{fg=muted}`\n"
                "  * Fonts & Templates:\n"
                "    `\\setbeamerfont{frametitle}{series=\\bfseries,size=\\Large}\\setbeamerfont{title}{series=\\bfseries,size=\\huge}`\n"
                "    `\\setbeamertemplate{navigation symbols}{}`\n"
                "    `\\setbeamertemplate{itemize item}{\\textcolor{gold}{\\ensuremath{\\blacksquare}}}`\n"
                "    `\\setbeamertemplate{itemize subitem}{\\textcolor{navylight}{\\textendash}}`\n"
                "  * Custom Frametitle with left sidebar TikZ accent:\n"
                "    `\\setbeamertemplate{frametitle}{\\begin{tikzpicture}[remember picture,overlay]\\fill[navy] (current page.north west) rectangle ($(current page.north west)+(0.55,-\\paperheight)$);\\fill[gold] ($(current page.north west)+(0.55,0)$) rectangle ($(current page.north west)+(0.62,-\\paperheight)$);\\node[anchor=north west,navy,font=\\usebeamerfont{frametitle}\\scshape] at ($(current page.north west)+(1.05,-0.55)$) {\\insertframetitle};\\draw[gold,line width=1pt] ($(current page.north west)+(1.05,-1.25)$) -- ($(current page.north west)+(3.4,-1.25)$);\\end{tikzpicture}\\vspace{9mm}}`\n"
                "  * Footline:\n"
                "    `\\setbeamertemplate{footline}{\\begin{tikzpicture}[remember picture,overlay]\\fill[navy] (current page.south west) rectangle ($(current page.south west)+(0.55,\\paperheight)$);\\fill[gold] ($(current page.south west)+(0.55,0)$) rectangle ($(current page.south west)+(0.62,\\paperheight)$);\\node[anchor=south east,muted,font=\\scriptsize] at ($(current page.south east)+(-0.4,0.22)$) {\\insertframenumber\\ / \\inserttotalframenumber};\\end{tikzpicture}}`\n"
                "- Structure:\n"
                "  * Title Slide (`[plain]`): TikZ banner with navy background, gold accent line, cream title text, author, and date.\n"
                "  * Outline Slide (`\\begin{frame}{Outline}`): Key topics.\n"
                "  * 6-12 content frames (`\\begin{frame}{Title}`): Clear bullet points (max 5-6 bullets/slide), structured blocks, tables, and equations. Never place text outside a frame.\n"
                "- TIP: You can also call `get_template_theme(category='ppt', theme_name='regalia', extract_section='all')` to fetch the complete Regalia source if needed."
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
        ref_guidance = (
            "SOURCE MATERIAL GUIDANCE:\n"
            "An attached reference document is provided above. Synthesize its key findings, methodology, and tables directly into this document.\n"
            if stored_attachments else ""
        )
        creation_step_1 = (
            "1. Start by calling `get_template_theme` to retrieve the requested template/theme styling.\n"
            if is_redesign_request
            else "1. Read the current file (if not empty) with `read_file_range`.\n"
        )
        user_content = (
            f"USER REQUEST (DOCUMENT CREATION / CONVERSION MODE):\n{user_instruction}\n\n"
            f"{attached_block}\n\n"
            f"FILE: {file_path} ({total_lines} lines)\n\n"
            f"{task_state}\n\n"
            f"{smart_document_context}\n\n"
            f"FILE PREVIEW:\n{preview}\n\n"
            f"{ref_guidance}\n"
            f"{grounding_instruction}\n\n"
            f"{archetype_hint}\n\n"
            f"{visibility_diagnostic}\n\n"
            f"{redesign_guidance}\n\n"
            "CREATION INSTRUCTIONS:\n"
            f"{creation_step_1}"
            "2. Generate the complete, publication-grade LaTeX code from `\\documentclass` to `\\end{document}`.\n"
            "3. Use `str_replace` to write the newly created document into the workspace.\n"
            "4. Call `verify_compile` to check that the newly created document compiles with 0 errors.\n"
            "5. If compilation succeeds, signal done=true with a summary of what you created."
        )
    elif is_broad_request and valid_chapters:
        ch_list = "\n".join([f"  - Line {c['line_no']}: {c['match']}" for c in valid_chapters])
        sec_list = "\n".join([f"  - Line {s['line_no']}: {s['match']}" for s in valid_sections[:20]])
        user_content = (
            f"USER REQUEST (EDIT MODE — BROAD DOCUMENT EXPANSION):\n{user_instruction}\n\n"
            f"{attached_block}\n\n"
            f"FILE: {file_path} ({total_lines} lines)\n\n"
            f"{task_state}\n\n"
            f"{smart_document_context}\n\n"
            f"{trans_block}\n\n"
            f"{grounding_instruction}\n\n"
            f"{visibility_diagnostic}\n\n"
            f"{redesign_guidance}\n\n"
            "MANDATE: The user explicitly requested to elaborate/expand ALL chapters and subchapters across the document.\n"
            f"Detected chapters in the document:\n{ch_list}\n\n"
            f"Detected sections in the document:\n{sec_list}\n\n"
            "CRITICAL REQUIREMENT: You MUST systematically iterate through EACH chapter and its subchapters.\n"
            "HIGH-SPEED BATCHING: Use batched `tool_calls: [...]` with `rewrite_chunk` or `insert_into_chunk` or `str_replace` across chapters in minimal turns to insert extensive academic content (detailed theory, methodologies, algorithms, benchmarks, equations, and analysis).\n"
            "After applying all edits, run `verify_compile` once and signal done=true."
        )
    else:
        # Edit mode — strictly mandate document modification
        ref_instruction = (
            "REFERENCE MATERIAL ATTACHED: Use the attached reference document(s) as primary source material to extract facts, sections, or tables.\n"
            if stored_attachments else ""
        )
        if is_compilation_fix_request:
            start_instruction = (
                "COMPILATION ERROR SURGICAL REPAIR WORKFLOW:\n"
                "1. Focus strictly on the parsed compilation errors and flagged lines above.\n"
                "2. If needed, inspect the code around the error lines with `read_file_range`.\n"
                "3. Apply surgical syntax/structure corrections using `str_replace`.\n"
                "4. MANDATORY STEP: Call `verify_compile` to confirm that all errors are resolved.\n"
                "5. Only signal done=true after `verify_compile` succeeds."
            )
        elif is_redesign_request:
            start_instruction = (
                "Start by calling `get_template_theme` to retrieve the new template styling, then inspect the preamble with `read_file_range` and apply the theme using `str_replace`."
            )
        else:
            start_instruction = "Start by locating where to make your edits and apply them."

        user_content = (
            f"USER REQUEST (EDIT MODE{' — COMPILATION FIX' if is_compilation_fix_request else ''}):\n{user_instruction}\n\n"
            f"{attached_block}\n\n"
            f"FILE: {file_path} ({total_lines} lines)\n\n"
            f"{task_state}\n\n"
            f"{smart_document_context}\n\n"
            f"{grounding_instruction}\n\n"
            f"{compilation_fix_diagnostic}\n\n"
            f"{visibility_diagnostic}\n\n"
            f"{redesign_guidance}\n\n"
            "MANDATE: You are in EDIT MODE. User preference is absolute. You MUST make the requested changes and write detailed, comprehensive LaTeX content directly into the document using `str_replace`.\n"
            f"{ref_instruction}"
            "If the user asks to elaborate, expand, explain chapters/subchapters, or add content, locate the relevant chapters/sections and insert rich, detailed LaTeX paragraphs, explanations, equations, and subsections into the file.\n"
            "Never conclude with done=true without editing the document or verifying compilation.\n"
            f"{start_instruction}"
        )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    # 4. Agent loop
    steps_taken = 0
    agent_explanation = ""
    compile_verified = False
    compile_available = True
    done_rejections = 0  # Track how many times we rejected a premature done=true
    pdf_conversion_job_id: Optional[str] = None  # set when convert_attached_pdf starts a job

    while steps_taken < actual_max_steps:
        if cancel_token and cancel_token.is_cancelled():
            raise LLMOperationCancelled("Agent loop cancelled by user.")

        steps_taken += 1
        yield {
            "type": "status",
            "step": steps_taken,
            "message": f"Agent reasoning step {steps_taken}/{actual_max_steps}...",
        }

        # Compact older conversation history to keep network payload lightweight and fast
        compact_messages = _compact_conversation_history(messages)

        raw_chars = sum(len(m.get("content", "")) for m in messages)
        compact_chars = sum(len(m.get("content", "")) for m in compact_messages)
        agent_trace.record_step_tokens(
            step=steps_taken,
            raw_chars=raw_chars,
            compacted_chars=compact_chars,
            estimated_tokens=compact_chars // 4,
        )

        # Allocate token budget dynamically based on context strategy, scope, and step
        step_max_tokens = compute_step_max_tokens(
            strategy=context_decision.strategy,
            scope=scope,
            step_number=steps_taken,
            is_creation=is_creation_request,
            total_steps=actual_max_steps,
        )

        # LLM call via provider router
        t_llm_start = time.time()
        try:
            response = provider_router.chat(
                messages=compact_messages,
                model=model,
                temperature=0.1,
                max_tokens=step_max_tokens,
                api_keys=api_keys,
            )
            agent_trace.record_llm_call(
                latency_ms=(time.time() - t_llm_start) * 1000,
                usage=response.get("usage") if isinstance(response, dict) else None,
            )
        except Exception as e:
            agent_trace.record_llm_call(
                latency_ms=(time.time() - t_llm_start) * 1000,
            )
            logger.error(f"LLM call failed at step {steps_taken}: {e}")
            yield {
                "type": "status",
                "step": steps_taken,
                "message": f"LLM call failed: {e}",
            }
            break

        raw_content = response.get("content", "")
        finish_reason = response.get("finish_reason", "stop")

        # Handle truncated responses — LLM ran out of output tokens
        if finish_reason in ("length", "max_tokens") and raw_content:
            logger.warning(f"LLM response truncated (finish_reason={finish_reason}) at step {steps_taken}. Requesting continuation...")
            messages.append({"role": "assistant", "content": raw_content})
            messages.append({
                "role": "user",
                "content": "Your previous response was truncated. Please COMPLETE the JSON object from where you left off. Output ONLY the remaining part of the JSON.",
            })
            cont_succeeded = False
            try:
                continuation = provider_router.chat(
                    messages=_compact_conversation_history(messages),
                    model=model,
                    temperature=0.1,
                    max_tokens=4096,
                    api_keys=api_keys,
                )
                cont_text = continuation.get("content", "")
                cont_finish = continuation.get("finish_reason", "stop")
                if cont_text:
                    if cont_text.strip().startswith("```"):
                        cont_text = re.sub(r"^\s*```(?:json)?\s*", "", cont_text)
                        cont_text = re.sub(r"\s*```\s*$", "", cont_text)
                    combined = raw_content + cont_text
                    # Check if combined text forms a valid complete JSON
                    if cont_finish not in ("length", "max_tokens") and _parse_agent_response(combined):
                        raw_content = combined
                        cont_succeeded = True
            except Exception as e:
                logger.warning(f"Continuation chat failed: {e}")
            finally:
                messages = messages[:-2]

            if not cont_succeeded:
                # Discard truncated edit to prevent document corruption
                logger.warning(f"Discarding truncated model response at step {steps_taken}.")
                yield {
                    "type": "status",
                    "step": steps_taken,
                    "message": "⚠️ AI response was cut off by token limit. Discarding partial edit...",
                }
                messages.append({"role": "assistant", "content": raw_content})
                messages.append({
                    "role": "user",
                    "content": (
                        "DISCARDED: Your response was truncated by the token limit and could not be completed. "
                        "The partial edit was discarded to prevent document corruption. "
                        "Please submit a smaller, more focused edit targeting only one section or slide at a time."
                    ),
                })
                continue

        content = raw_content.strip()
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
        if parsed.get("done") and not parsed.get("tool_call") and not parsed.get("tool_calls"):
            # 0. Enforce mandatory compilation verification on compilation fix requests
            if is_compilation_fix_request and not compile_verified and steps_taken < actual_max_steps:
                logger.info(f"Agent attempted completion without verifying compilation at step {steps_taken}; enforcing verify_compile.")
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": (
                        "REJECTED: This is a COMPILATION FIX request. You CANNOT complete without verifying compilation.\n"
                        "You MUST run `verify_compile` to confirm that the LaTeX document compiles cleanly with 0 errors.\n"
                        "Call `verify_compile` now."
                    ),
                })
                continue

            # 1. Enforce that Edit mode must have actually produced document modifications
            if mode == "edit" and not (is_compilation_fix_request and compile_verified) and not workspace.has_changed() and not pdf_conversion_job_id:
                done_rejections += 1
                logger.info(f"Agent attempted premature done in edit mode at step {steps_taken} (rejection #{done_rejections}); enforcing edits.")

                # Safety cap: after 5 rejections, let the agent exit to prevent infinite loop
                if done_rejections > 5:
                    logger.warning(f"Agent has been rejected {done_rejections} times. Allowing exit to prevent infinite loop.")
                    agent_explanation = parsed.get("explanation", thought or "Agent was unable to apply edits after multiple attempts.")
                    break

                messages.append({"role": "assistant", "content": content})

                if done_rejections >= 3:
                    # Final chance — give an extremely explicit instruction
                    if is_expansion or is_broad_request:
                        rejection_msg = (
                            f"FINAL WARNING (attempt #{done_rejections}): You have declared done=true {done_rejections} times WITHOUT making ANY edits.\n"
                            f"The user asked: \"{user_instruction}\"\n\n"
                            "You MUST expand the document NOW. Here is exactly what to do:\n"
                            "1. Call `read_file_range` with start_line=1 and end_line=50 to read the document structure.\n"
                            "2. Identify the first topic/slide/section.\n"
                            "3. Use `str_replace` to add detailed content AFTER the first section's content.\n"
                            "4. Repeat for each subsequent topic/section.\n"
                            "DO NOT say done=true again without making edits. The user is waiting for content."
                        )
                    else:
                        rejection_msg = (
                            f"FINAL WARNING (attempt #{done_rejections}): You have declared done=true {done_rejections} times WITHOUT making ANY edits.\n"
                            f"The user asked: \"{user_instruction}\"\n\n"
                            "You MUST make edits NOW:\n"
                            "1. Call `read_file_range` to inspect the document.\n"
                            "2. Use `str_replace` to apply the requested changes.\n"
                            "DO NOT say done=true again without making edits."
                        )
                else:
                    if is_expansion or is_broad_request:
                        avail_chunks_str = ", ".join([f"`{c.chunk_id}` ({c.title})" for c in content_chunks[:10]])
                        chunk_hint = f"\nAvailable document chunks to expand:\n{avail_chunks_str}\n" if content_chunks else ""
                        rejection_msg = (
                            f"REJECTED (attempt #{done_rejections}): You are in EDIT MODE and have made 0 edits to the document (0 lines changed).\n"
                            f"The user's prompt is: \"{user_instruction}\".\n"
                            "The user explicitly wants you to EXPAND / ELABORATE / ADD MORE SLIDES / CONTENT to the document.\n"
                            f"{chunk_hint}"
                            "You MUST NOT conclude without modifying the file. You MUST:\n"
                            "1. Generate rich, detailed LLM-written content for each topic/slide (e.g. an additional in-depth slide per topic).\n"
                            "2. Use `rewrite_chunk(chunk_id, new_content)` or `str_replace(old_str, new_str)` to insert the new slides/content into main.tex.\n"
                            "3. Call `verify_compile` to confirm 0 compilation errors.\n"
                            "Do NOT declare done=true until you have actually added content to the file."
                        )
                    else:
                        rejection_msg = (
                            f"REJECTED (attempt #{done_rejections}): You are in EDIT MODE and have made 0 edits to the document (0 lines changed).\n"
                            f"The user's prompt is: \"{user_instruction}\".\n"
                            "User preference is absolute. You MUST modify the LaTeX file using `rewrite_chunk` or `str_replace`.\n"
                            "Do not declare the document complete without applying the requested design, expansions, or edits into the file.\n"
                            "Use `rewrite_chunk` or `str_replace` to apply your modifications now."
                        )

                messages.append({"role": "user", "content": rejection_msg})
                # Don't burn a step on rejections — give the agent its step back
                steps_taken -= 1
                continue

            # 2. Coverage + Leftover validation for FULL_DOCUMENT_REWRITE & EXPANSION
            if mode == "edit" and (is_full_rewrite or is_expansion or is_broad_request):
                t_val_start = time.time()
                cov_report = validate_coverage(
                    workspace=workspace,
                    user_instruction=user_instruction,
                    scope=scope,
                    forbidden_terms=scope_result.forbidden_terms,
                )
                agent_trace.record_validator((time.time() - t_val_start) * 1000)

                yield {
                    "type": "coverage_check",
                    "total_chunks": cov_report.total_chunks,
                    "edited_chunks": cov_report.edited_chunks,
                    "missing_chunk_ids": cov_report.missing_chunk_ids,
                    "passed": cov_report.passed,
                    "message": cov_report.feedback_message,
                }

                if not cov_report.passed and steps_taken < actual_max_steps - 1:
                    logger.info(f"Agent attempted completion at step {steps_taken} but failed coverage check. Missing: {cov_report.missing_chunk_ids}")
                    messages.append({"role": "assistant", "content": content})
                    messages.append({
                        "role": "user",
                        "content": cov_report.feedback_message,
                    })
                    continue

            # 3. For broad multi-chapter requests without explicit chunk IDs, enforce multi-chapter edit count
            min_expected_edits = min(3, len(valid_chapters) or 3)
            if mode == "edit" and not pdf_conversion_job_id and is_broad_request and len(valid_chapters) >= 2 and workspace.get_edit_count() < min_expected_edits and steps_taken < actual_max_steps - 2:
                logger.info(f"Agent attempted early done with only {workspace.get_edit_count()} edits on broad request at step {steps_taken}; prompting to continue.")
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": (
                        f"INCOMPLETE: You have only applied {workspace.get_edit_count()} edit(s) so far, but the user requested to elaborate ALL chapters and subchapters across the document.\n"
                        "You must continue reading the remaining unedited chapters and use `rewrite_chunk` or `str_replace` to add extensive, detailed LaTeX content across all chapters before signaling done=true."
                    ),
                })
                continue

            agent_explanation = parsed.get("explanation", thought or "Edit completed.")
            break

        # Check for tool call(s) (supports single `tool_call` or batch `tool_calls: [...]`)
        raw_tool_calls = parsed.get("tool_calls")
        raw_tool_call = parsed.get("tool_call")

        calls: List[Dict[str, Any]] = []
        if isinstance(raw_tool_calls, list):
            calls = [c for c in raw_tool_calls if isinstance(c, dict)]
        elif isinstance(raw_tool_call, list):
            calls = [c for c in raw_tool_call if isinstance(c, dict)]
        elif isinstance(raw_tool_call, dict):
            calls = [raw_tool_call]

        if calls:
            tool_results_list = []
            for call in calls:
                tool_name = call.get("name", "")
                tool_args = call.get("arguments", {})

                yield {
                    "type": "tool_call",
                    "tool": tool_name,
                    "args": tool_args,
                }

                # Execute tool with timing instrumentation
                t_tool_start = time.time()
                tool_result = execute_tool(
                    tool_name=tool_name,
                    args=tool_args,
                    workspace=workspace,
                )
                t_tool_ms = (time.time() - t_tool_start) * 1000

                is_success = bool(tool_result.get("success", True) if isinstance(tool_result, dict) else True)
                summary_str = str(tool_result)[:100] if isinstance(tool_result, dict) else ""
                agent_trace.record_tool_call(
                    name=tool_name,
                    args=tool_args,
                    result_summary=summary_str,
                    latency_ms=t_tool_ms,
                    success=is_success,
                )

                yield {
                    "type": "tool_result",
                    "tool": tool_name,
                    "result": tool_result,
                }

                if tool_name == "convert_attached_pdf" and isinstance(tool_result, dict) and tool_result.get("job_id") and tool_result.get("success"):
                    pdf_conversion_job_id = tool_result["job_id"]

                # Special handling for compile results
                if tool_name == "verify_compile":
                    agent_trace.record_compile(
                        latency_ms=t_tool_ms,
                        success=bool(tool_result.get("success", False)),
                    )
                    if tool_result.get("infra_skip"):
                        compile_available = False
                        compile_verified = True
                        yield {
                            "type": "status",
                            "step": steps_taken,
                            "message": "✓ Shadow compilation skipped (LaTeX compiler not installed or unavailable in this environment). Edits preserved.",
                        }
                    elif tool_result.get("success"):
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

                tool_results_list.append((tool_name, tool_args, tool_result))

            # Fast 1-turn completion check: If agent signaled done=true in the same response AND tools made valid edits
            if parsed.get("done") and workspace.has_changed():
                if is_compilation_fix_request and not compile_verified and steps_taken < actual_max_steps:
                    # In compilation fix mode, require verified compilation before concluding
                    pass
                # Check coverage if broad / full rewrite / expansion
                elif mode == "edit" and (is_full_rewrite or is_expansion):
                    t_val_start = time.time()
                    cov_report = validate_coverage(
                        workspace=workspace,
                        user_instruction=user_instruction,
                        scope=scope,
                        forbidden_terms=scope_result.forbidden_terms,
                    )
                    agent_trace.record_validator((time.time() - t_val_start) * 1000)
                    if cov_report.passed:
                        yield {
                            "type": "coverage_check",
                            "total_chunks": cov_report.total_chunks,
                            "edited_chunks": cov_report.edited_chunks,
                            "missing_chunk_ids": cov_report.missing_chunk_ids,
                            "passed": True,
                            "message": cov_report.feedback_message,
                        }
                        agent_explanation = parsed.get("explanation", thought or "Edit completed.")
                        break
                else:
                    agent_explanation = parsed.get("explanation", thought or "Edit completed.")
                    break

            # Append to conversation for next LLM turn
            messages.append({"role": "assistant", "content": content})

            # Format observation for the LLM
            if len(tool_results_list) == 1:
                tool_name, tool_args, tool_result = tool_results_list[0]
                result_str = json.dumps(tool_result, indent=2, ensure_ascii=False)
                if len(result_str) > 4000:
                    result_str = result_str[:4000] + "\n... (truncated)"

                # Tailor follow-up instruction based on the tool that just executed
                if tool_name == "rewrite_chunk":
                    touched = workspace.get_touched_chunks()
                    remaining = [c.chunk_id for c in content_chunks if c.chunk_id not in touched]
                    if remaining:
                        followup_msg = (
                            f"TOOL RESULT from `rewrite_chunk`:\n{result_str}\n\n"
                            f"Chunk `{tool_args.get('chunk_id')}` updated successfully in shadow buffer. "
                            f"Remaining unedited chunk(s): {remaining}. "
                            f"Proceed with `rewrite_chunk` for the next chunk: `{remaining[0]}` (or use batched `tool_calls: [...]` to rewrite all remaining chunks in one turn)."
                        )
                    else:
                        followup_msg = (
                            f"TOOL RESULT from `rewrite_chunk`:\n{result_str}\n\n"
                            "All content chunks have now been rewritten! If all edits are complete, set done=true with your final explanation."
                        )
                elif tool_name == "get_template_theme":
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
                        "Now identify the exact text to replace and use `str_replace` or `rewrite_chunk` to apply the edits. "
                        "Remember that old_str in `str_replace` must match the file exactly character-for-character."
                    )
                elif tool_name in ("str_replace", "insert_into_chunk"):
                    followup_msg = (
                        f"TOOL RESULT from `{tool_name}`:\n{result_str}\n\n"
                        "Edit applied successfully to shadow buffer. If all requested changes are complete, you can now set done=true with your final explanation, or continue with additional edits if needed."
                    )
                elif tool_name == "verify_compile":
                    if tool_result.get("infra_skip"):
                        followup_msg = (
                            f"TOOL RESULT from `verify_compile`:\n{result_str}\n\n"
                            "Shadow compilation skipped (compiler unavailable). If all edits are complete, you can now set done=true."
                        )
                    elif tool_result.get("success"):
                        followup_msg = (
                            f"TOOL RESULT from `verify_compile`:\n{result_str}\n\n"
                            "Compilation passed cleanly! If all requested changes are complete, you can now set done=true."
                        )
                    else:
                        err_context = tool_result.get("stderr", "")
                        summary_msg = tool_result.get("summary", "Compilation failed")
                        errors_list = tool_result.get("errors", [])
                        diag_lines = []
                        for e in errors_list[:6]:
                            l_info = f"Line {e.get('line')}" if e.get('line') else "Document / Preamble"
                            action_info = f" -> Fix: {e.get('suggested_action')}" if e.get('suggested_action') else ""
                            diag_lines.append(f"- [{l_info}] {e.get('error')}{action_info}")
                        diag_str = "\n".join(diag_lines) if diag_lines else summary_msg

                        followup_msg = (
                            f"COMPILATION FAILED:\n{diag_str}\n\n"
                            f"Raw Log Snippet:\n{err_context[:1000]}\n\n"
                            "INSTRUCTION: Target ONLY the specific lines flagged above with compilation errors. "
                            "Use `read_file_range` around the error line if needed, then `str_replace` to fix the syntax errors (e.g. unclosed environments, missing TikZ semicolon, missing packages) "
                            "and then call `verify_compile` to confirm the fix."
                        )
                elif tool_name == "search_uploaded_references":
                    followup_msg = (
                        f"TOOL RESULT from `search_uploaded_references`:\n{result_str}\n\n"
                        "Use the retrieved reference details, benchmark metrics, or citations to insert or edit the LaTeX content using `insert_into_chunk` or `str_replace`."
                    )
                else:
                    followup_msg = (
                        f"TOOL RESULT from `{tool_name}`:\n{result_str}\n\n"
                        "If all edits are complete, set done=true with your final explanation, or continue with the next edit."
                    )
            else:
                # Batch results summary
                results_summary = []
                for t_name, t_args, t_res in tool_results_list:
                    res_json = json.dumps(t_res, ensure_ascii=False)
                    if len(res_json) > 150:
                        res_json = res_json[:150] + "..."
                    results_summary.append(f"- `{t_name}`({json.dumps(t_args, ensure_ascii=False)}): {res_json}")

                touched = workspace.get_touched_chunks()
                remaining = [c.chunk_id for c in content_chunks if c.chunk_id not in touched]
                if (is_full_rewrite or is_expansion) and remaining:
                    followup_msg = (
                        f"BATCH TOOL RESULTS ({len(tool_results_list)} actions executed):\n"
                        + "\n".join(results_summary)
                        + f"\n\nRemaining unedited chunk(s): {remaining}. "
                        + f"Proceed with remaining chunks: `{remaining[0]}` (or batch them in `tool_calls: [...]`)."
                    )
                else:
                    followup_msg = (
                        f"BATCH TOOL RESULTS ({len(tool_results_list)} actions executed):\n"
                        + "\n".join(results_summary)
                        + "\n\nAll batched edits have been applied to the shadow buffer! If all changes are complete, set done=true with your final explanation."
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

    # 5. Compute and yield diff & emit trace
    elapsed_ms = int((time.time() - start_time) * 1000)
    agent_trace.total_latency_ms = float(elapsed_ms)
    agent_trace.steps_used = steps_taken
    touched_chunks = workspace.get_touched_chunks()
    agent_trace.nodes_touched = list(touched_chunks)
    if num_content_chunks > 0:
        touched_content = [c.chunk_id for c in content_chunks if c.chunk_id in touched_chunks]
        agent_trace.coverage_pct = round((len(touched_content) / num_content_chunks) * 100.0, 1)
    else:
        agent_trace.coverage_pct = 100.0

    trace_manager.emit_agent_trace(agent_trace)
    trace_summary = agent_trace.summary()

    if workspace.has_changed():
        # One heal, then validate. Every write already healed and validated this
        # buffer, so a second heal here is both redundant work and a chance to
        # mutate code *after* it was checked; `replace_all` re-runs the same
        # gate, so a repair that regresses anything is refused rather than
        # committed.
        healed_final, auto_repairs = auto_heal_latex_code(workspace.get_buffer())
        if auto_repairs:
            heal_res = workspace.replace_all(healed_final)
            if heal_res.get("success"):
                logger.info(f"Auto-healed final buffer before pre-commit: {auto_repairs}")
            else:
                logger.warning(
                    f"Final auto-heal rejected by pre-commit validation: "
                    f"{heal_res.get('validation_errors', [])[:3]}"
                )

        # Final gate: differential, like every write. The user's original
        # document may already contain structure this validator cannot model
        # (a list environment from a .cls, an \end{...} its grammar cannot
        # pair); holding the result to an absolute standard threw away the whole
        # run over a defect the agent neither introduced nor was asked to fix.
        is_valid, val_errors = validate_edit(workspace.get_original(), workspace.get_buffer())
        if not is_valid:
            logger.warning(f"Final buffer introduced new structural errors: {val_errors}. Attempting snapshot rollback...")
            while not is_valid and workspace.undo():
                healed_candidate, _ = auto_heal_latex_code(workspace.get_buffer())
                is_valid, val_errors = validate_edit(workspace.get_original(), healed_candidate)
                if is_valid:
                    heal_res = workspace.replace_all(healed_candidate)
                    if not heal_res.get("success"):
                        # The candidate did not survive commit-time validation;
                        # keep unwinding instead of claiming success.
                        is_valid = False
                        val_errors = heal_res.get("validation_errors", val_errors)
                        continue
                    break

            if not is_valid:
                logger.error(f"Buffer remains invalid after rollback: {val_errors}")
                rejection_msg = (
                    f"The proposed edits could not be safely applied because they introduced LaTeX syntax errors:\n"
                    + "\n".join(f"- {e}" for e in val_errors[:3])
                    + "\n\nThe original document was preserved to prevent compilation failure."
                )
                yield {
                    "type": "compile_error",
                    "message": f"Pre-commit validation failed: {'; '.join(val_errors[:2])}",
                    "errors": val_errors,
                }
                yield {
                    "type": "result",
                    "data": {
                        "original_chunk": workspace.get_original(),
                        "proposed_chunk": workspace.get_original(),
                        "explanation": rejection_msg,
                        "edits": [],
                        "has_changes": False,
                        "steps_taken": steps_taken,
                        "compile_verified": False,
                        "edit_count": 0,
                        "elapsed_ms": elapsed_ms,
                        "trace": trace_summary,
                        "validation_errors": val_errors,
                    },
                }
                yield compute_final_diff(
                    original=workspace.get_original(),
                    modified=workspace.get_original(),
                    file_path=file_path,
                    explanation=rejection_msg,
                )
                return

        # Generate the final_diff payload for main document
        diff_payload = compute_final_diff(
            original=workspace.get_original(),
            modified=workspace.get_buffer(),
            file_path=file_path,
            explanation=agent_explanation,
        )
        yield diff_payload

        # Yield diff payloads for any modified auxiliary files.
        # get_all_modified_files() returns {path: (original, modified)}; the whole
        # block is guarded so a single bad aux file can never prevent the `result`
        # event from being emitted (the frontend treats a missing result as "no
        # changes" and silently discards the run).
        try:
            all_modified = workspace.get_all_modified_files()
        except Exception as e:
            logger.error(f"Could not enumerate modified files: {e}")
            all_modified = {}

        for aux_p, aux_pair in all_modified.items():
            if aux_p == file_path or aux_p == "main.tex":
                continue
            try:
                aux_orig, aux_mod = aux_pair
            except (TypeError, ValueError):
                logger.error(f"Unexpected modified-file entry for {aux_p}; skipping.")
                continue
            try:
                aux_warnings: List[str] = []
                healed_aux, aux_fixes = auto_heal_latex_code(aux_mod)
                aux_valid, aux_errors = validate_edit(aux_orig, healed_aux)
                if not aux_valid:
                    # Never ship an aux file we know to be broken.
                    logger.warning(
                        f"Auxiliary file {aux_p} failed pre-commit validation: {aux_errors[:3]}"
                    )
                    continue
                if aux_fixes:
                    aux_warnings.append(
                        "Auto-repaired while saving: " + "; ".join(aux_fixes[:3])
                    )
                aux_payload = compute_final_diff(
                    original=aux_orig,
                    modified=healed_aux,
                    file_path=aux_p,
                    explanation=f"Updated auxiliary file: {aux_p}",
                )
                if aux_warnings:
                    aux_payload["warnings"] = aux_warnings
                yield aux_payload
            except Exception as e:
                logger.error(f"Failed to build diff for auxiliary file {aux_p}: {e}")
                continue

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
                "trace": trace_summary,
                "modified_files": all_modified,
                "pdf_conversion_job_id": pdf_conversion_job_id,
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
                "compile_verified": compile_verified,
                "edit_count": 0,
                "elapsed_ms": elapsed_ms,
                "trace": trace_summary,
                "pdf_conversion_job_id": pdf_conversion_job_id,
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
    attached_files: Optional[List[Dict[str, Any]]] = None,
    api_keys: Optional[Dict[str, str]] = None,
    max_steps: Optional[int] = None,
    cancel_token: Optional[CancellationToken] = None,
    assets_dir: Optional[str] = None,
    session_id: Optional[str] = None,
    project_files: Optional[Dict[str, str]] = None,
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
        attached_files=attached_files,
        api_keys=api_keys,
        max_steps=max_steps,
        cancel_token=cancel_token,
        assets_dir=assets_dir,
        session_id=session_id,
        project_files=project_files,
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
