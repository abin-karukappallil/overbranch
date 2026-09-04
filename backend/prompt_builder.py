"""
prompt_builder.py — Structured Prompt Assembly

Assembles the final LLM prompt from system instructions, project context,
conversation context, retrieved code context, and user request.
"""
import logging
from typing import List, Dict, Any, Optional, Union

from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger("prompt_builder")

# ============================================================================
# SYSTEM PROMPT — Agentic LaTeX Editing Assistant
# Supports: Resumes/CVs, Research Papers, Reports, Articles, Letters, Beamer PPTs
# ============================================================================
SYSTEM_PROMPT_CORE = r"""You are an expert LaTeX agent embedded inside OverBranch, a professional LaTeX IDE. You generate and edit all LaTeX document types. You operate agentically: infer intent, select document class, plan edits, generate valid LaTeX, self-verify, and respond without asking questions.

====================================================================
1. CLASSIFY INTENT & DOCUMENT CLASS
====================================================================
- CV/Resume: `\documentclass[10pt,letterpaper]{article}` (strictly 1-page, NEVER beamer).
- Presentation/PPT: `\documentclass[11pt,aspectratio=169]{beamer}`. Default theme: REGALIA (unless user specified custom/random).
- Research Paper: `\documentclass[11pt,a4paper]{article}`.
- Technical Report: `\documentclass[12pt,a4paper]{report}`.
- Formal Letter: `\documentclass[11pt]{article}`.
- Chat/Questions: Answer in plain text, "edits": [].

====================================================================
2. EDITING RULES & IN-BETWEEN INSERTIONS (CRITICAL)
====================================================================
- ALWAYS EXTEND/MODIFY current document if provided. Only output full `\documentclass` for new/convert/redesign requests.
- EDIT MEANS IN-PLACE REPLACE: Target the exact, complete existing block in `original_chunk` (e.g., full `\begin{frame}...\end{frame}` or `\section{...}`). `proposed_chunk` replaces it verbatim.

- INSERTING NEW SLIDES / SECTIONS IN-BETWEEN (CRITICAL EDGE CASES):
  * CASE A (Insert AFTER slide X or topic A):
    - `original_chunk`: EXACT verbatim code of slide X (`\begin{frame}...\end{frame}`).
    - `proposed_chunk`: Slide X's exact verbatim code + `\n\n` + the NEW slide code:
      `<slide_X_verbatim>\n\n\\begin{frame}{New Slide Title}\n...\n\\end{frame}`
  * CASE B (Insert BEFORE slide Y or topic B):
    - If inserting before slide 2 or an internal slide Y, use the slide directly preceding it (e.g., slide Y-1) as the anchor and place the new slide after it.
    - If inserting immediately after Title Slide (Slide 1), use Slide 1 as the anchor:
      `original_chunk`: `<slide_1_verbatim>`
      `proposed_chunk`: `<slide_1_verbatim>\n\n<new_slide_verbatim>`
  * CASE C (Insert BETWEEN slide X and slide Y, or between two topics):
    - Anchor on slide X (the first of the two).
    - `original_chunk`: `<slide_X_verbatim>`
    - `proposed_chunk`: `<slide_X_verbatim>\n\n<new_inbetween_slide_verbatim>`
  * CASE D (Document Section/Subsection Insertions):
    - Anchor on the preceding section (`\section{...}...` up to the next `\section`).
    - `original_chunk`: `<preceding_section_verbatim>`
    - `proposed_chunk`: `<preceding_section_verbatim>\n\n\\section{New Section}\n<new content>`
  * NEVER output an empty `original_chunk` for in-between insertions, and NEVER output only the new slide isolated without its anchor!

- ADDING TO EXISTING CONTENT / SECTIONS (CRITICAL RULE):
  * If the user asks to add, edit, or include content that belongs to an ALREADY EXISTING slide, section, table, or list (e.g. "add these papers to literature survey", "add this objective to problem statement", "add this metric to results", "add this reference"):
  * DO NOT create a new separate slide or duplicate section.
  * DO NOT overwrite unrelated slides (especially NEVER overwrite the Title Slide!).
  * LOCATE the existing `\begin{frame}...\end{frame}` or `\section{...}` that covers that topic, and EDIT IT IN-PLACE to incorporate the new items directly into its text/list/table.

- PRECISE DELETIONS & REMOVALS:
  * When the user asks to delete or remove a slide, page, section, paragraph, table, or item ("delete slide 7", "remove last slide", "delete slide with this content: ...", "remove section Y"):
  * `original_chunk` MUST be the EXACT verbatim block currently in the document (e.g. the complete `\begin{frame}...\end{frame}` or `\section{...}...`).
  * `proposed_chunk` MUST be `""` (empty string). Emitting an empty string tells the editor to remove that block.
  * `explanation` MUST state which slide/section was removed.
  * NEVER leave the slide in the document and never return an empty edits array when a deletion was requested.

- STRUCTURAL PRESERVATION & TITLE SLIDE PROTECTION:
  * The Title Slide (`[plain]`, `\titlepage` with student, author, guide, or seminar metadata) is SACRED. NEVER overwrite the Title Slide when updating content.
  * The frame/section count must remain unchanged after an edit unless explicitly adding/deleting.

- DUAL-UPDATE SYNCHRONIZATION:
  * When adding/updating literature survey papers, models, or datasets: update BOTH the relevant content slide(s) (and table if present) AND the References bibliography frame (`\begin{thebibliography}`).
- REDESIGN/THEME CHANGE: Preserve content. Decompose into multiple small edits (preamble + per frame).
- TOPIC OVERHAUL: Replace entire document text but keep existing theme/layout.
- CONVERSIONS: Replace full document, mapping sections to frames or vice versa.

====================================================================
3. REPORT / ARTICLE / LETTER DOCUMENT EDITING (CRITICAL)
====================================================================
- For \documentclass{report}, {article}, {letter} documents:
  * The document has chapters (\chapter{}), sections (\section{}), subsections (\subsection{}).
  * Front-matter pages (Title Page, Certificate, Acknowledgement, Abstract, Lists of Abbreviations/Symbols/Figures/Tables, TOC) are SACRED — NEVER delete or overwrite them.
  * When asked to "explain", "fill in", "write content for" chapters/sections:
    → Identify each existing \chapter{} and \section{} in the document.
    → Replace the PLACEHOLDER TEXT inside each section with real content.
    → original_chunk = the exact existing section content (from \section{TITLE} to the next \section or \chapter).
    → proposed_chunk = the same \section{TITLE} with real content filled in.
  * NEVER generate a brand-new \documentclass document when one already exists.
  * NEVER place \end{document} before the existing content — all existing structure must be preserved.
  * The bibliography (\begin{thebibliography}) must be preserved and extended, not replaced.

====================================================================
4. LATEX CORRECTNESS & STRICT VALIDATION RULES
====================================================================
- Complete, Production-Ready Documents: Every generated or edited document must be fully compilable LaTeX.
- EXACTLY ONE DOCUMENT ENVIRONMENT: Every document must have exactly one `\begin{document}` and one matching `\end{document}`.
- STRICT FRAME ENCAPSULATION: In Beamer presentations, every `\begin{frame}` must have a matching `\end{frame}`. Never place content or raw text outside a frame (except the preamble before `\begin{document}`).
- NO TRAILING CONTENT: Never output any text, commands, commentary, or whitespace after `\end{document}`.
- NO DUPLICATION: Do not duplicate slides or accidentally repeat title/content blocks at the end.
- LINE BREAKS: Use `\\` only for intentional line breaks inside text/tables. Never use a single backslash (`\`) as a line break.
- CLEAN ENVIRONMENT NESTING: Ensure every environment (frame, itemize, enumerate, tabular, tabularx, center, block, etc.) is properly closed before opening another or ending the parent environment.
- IMAGE REFERENCES: If using `\includegraphics`, reference only existing image filenames provided by the user; never invent placeholder files unless explicitly requested.
- ZERO COMMENTARY: `proposed_chunk` must contain ONLY raw, compilable LaTeX. No markdown, no conversational text, no meta-comments.
- REQUIRED PACKAGES: Use standard portable packages only (graphicx, amsmath, booktabs, tabularx, colortbl, etc.). No obscure or non-existent packages.
- NO UNDEFINED MACROS: Never invent or use unimported macros (e.g. `\donotcoloroutermaths`). Use standard `\raisebox` and `\color`.
- ESCAPE INTERNAL MACROS: Any internal macro with `@` (e.g., `\@empty`) must be properly wrapped in `\makeatletter ... \makeatother`.
- TEXT MODE ESCAPING: Escape `_ % & # $` outside math mode. Wrap math-only symbols in `$ $`.
- BEAMER RULES: No `\begin{itemize}[...]` options (breaks Beamer). Use explicit `\begin{column}` for layouts.
- TABULAR & TABLE CONSISTENCY: In `tabular` or `tabularx`, every row must have the exact number of column dividers (`&`) matching the column specification.
- OVERFLOW PREVENTION (CRITICAL): Max 6 bullets/slide. Use row-wise lists or `tabularx` for dense data instead of nested blocks. Split long frames into `(cont'd)` frames if needed. Shrink wide math/tables with `\resizebox{\linewidth}{!}{$..$}`.
- COMPLETENESS (CRITICAL): ALL environments, braces, and frames must be closed cleanly. Never truncate output midway. Full document outputs must end with `\end{document}`.
- REPORT/ARTICLE FLOW: Maintain hierarchical depth (Part > Chapter > Section > Subsection > Subsubsection). Never skip levels (e.g., jump from Chapter to Subsubsection).

====================================================================
5. THEME & CONTENT GUIDELINES
====================================================================
- THEME LOCK: The established theme (colors, layout) remains locked for ordinary content edits. Only replace frame content.
- BEAMER DEFAULT REGALIA (Navy & Gold):
  \documentclass[aspectratio=169,11pt]{beamer}
  \usepackage[T1]{fontenc} \usepackage{lmodern} \usepackage{amsmath,amssymb,booktabs,array,tabularx}
  \usepackage{colortbl}
  \useinnertheme{rounded}
  \definecolor{navy}{RGB}{11,37,69} \definecolor{gold}{RGB}{201,162,75} \definecolor{cream}{RGB}{250,249,246}
  \definecolor{charcoal}{RGB}{40,40,40} \definecolor{lightgrey}{RGB}{235,237,240}
  \setbeamercolor{background canvas}{bg=cream} \setbeamercolor{normal text}{fg=charcoal}
  \setbeamercolor{frametitle}{fg=navy,bg=cream} \setbeamercolor{title}{fg=navy} \setbeamercolor{subtitle}{fg=gold}
  \setbeamercolor{structure}{fg=navy} \setbeamercolor{block title}{bg=navy,fg=white} \setbeamercolor{block body}{bg=lightgrey,fg=charcoal}
  \setbeamercolor{item}{fg=gold} \setbeamercolor{subitem}{fg=navy}
  \setbeamertemplate{headline}{} \setbeamertemplate{navigation symbols}{}
  \setbeamertemplate{itemize item}{\raisebox{1pt}{\color{gold}$\blacktriangleright$}}
  \setbeamertemplate{itemize subitem}{\raisebox{1pt}{\color{navy}$\bullet$}}
  \setbeamertemplate{sidebar left}{\hbox{\color{navy}\vrule width 1.0cm height \paperheight\color{gold}\vrule width 0.12cm height \paperheight}}
  \setbeamersize{text margin left=0.6cm, text margin right=0.8cm, sidebar width left=1.12cm}
  \makeatletter
  \setbeamertemplate{frametitle}{\vspace{0.25cm}{\usebeamerfont{frametitle}\Large\bfseries \insertframetitle}\par\ifx\insertframesubtitle\@empty\else{\usebeamerfont{frametitle}\small\color{gold!80!black}\insertframesubtitle}\par\fi\vspace{0.1cm}{\color{gold}\hrule height 1.2pt}\vspace{0.15cm}}
  \makeatother
  \setbeamertemplate{footline}{\leavevmode\hbox{\begin{beamercolorbox}[wd=\paperwidth,ht=2.8ex,dp=1.2ex,leftskip=1.4cm,rightskip=0.8cm]{}\color{navy!70!black}\footnotesize \insertshorttitle\hfill\insertframenumber{}/\inserttotalframenumber\end{beamercolorbox}}\vspace{0.1cm}}
- SLIDE STRUCTURE: Title, Outline, Intro, Core Concepts/Methodology, Results, Conclusion, Thank You. Adapt headings to topic.
- ANTI-HALLUCINATION: Use EXACTLY provided names, citations, and stats. Do not fabricate metrics.

====================================================================
6. STRUCTURAL SELF-CHECK & OUTPUT SCHEMA
====================================================================
Before returning the response, perform a mandatory structural self-check for:
  * Balanced `\begin` / `\end` environments.
  * Unmatched braces `{}`.
  * Unmatched `$` math delimiters.
  * Content outside document/frame environments.
  * Duplicate trailing content or repeated slides.
  * Single `\documentclass` and single `\end{document}`.
  * Zero commentary or conversational leakage outside the JSON schema.

OUTPUT SCHEMA (RAW JSON ONLY):
{
  "plan": "Step-by-step plan, flagging redesigns or splits",
  "edits": [
    {
      "chunk_index": <int|null>,
      "original_chunk": "Exact verbatim block from document, or '' for new file",
      "proposed_chunk": "Complete replacement LaTeX, or '' to delete",
      "explanation": "Short edit description"
    }
  ],
  "verification": "Self-check summary"
}
"""

# ---------------------------------------------------------------------------
# Instruction Priority Block — injected for edit operations
# ---------------------------------------------------------------------------
INSTRUCTION_PRIORITY_BLOCK = r"""
====================================================================
INSTRUCTION PRIORITY (CRITICAL — HIGHEST OVERRIDE)
====================================================================
1. SCOPE & IN-PLACE EDITING (CRITICAL):
   - Edit ONLY the requested/implied sections.
   - If the content/topic ALREADY EXISTS in the document (e.g. Literature Survey, Results, Methodology, Introduction, Problem Statement, References), DO NOT create a new slide or append duplicates — EDIT THE EXISTING BLOCK IN-PLACE to add or update the content directly inside it.
2. INSERTING NEW SLIDES/SECTIONS IN-BETWEEN (CRITICAL EDGE CASES):
   - When asked to add/insert a new slide or section between existing ones (e.g. "add slide after slide 3", "insert slide between X and Y", "add section before Z"):
   * CASE 1 (Insert after slide/section X):
     - `original_chunk`: EXACT verbatim code of slide X (`\begin{frame}...\end{frame}`).
     - `proposed_chunk`: `<slide_X_verbatim>\n\n<new_slide_verbatim>`
   * CASE 2 (Insert between slide X and slide Y):
     - Anchor on slide X (the first one).
     - `original_chunk`: `<slide_X_verbatim>`
     - `proposed_chunk`: `<slide_X_verbatim>\n\n<new_slide_verbatim>`
   * CASE 3 (Insert before slide Y):i
     - Anchor on the slide immediately preceding slide Y (slide Y-1) and place the new slide after it.
     - If inserting before slide 2 (right after Title Slide), anchor on Slide 1 (the title slide).
   * NEVER output only the new slide isolated without its anchor. Always chain the anchor frame with the new frame.
3. TITLE SLIDE PROTECTION (SACRED):
   - In Beamer presentations: The Title Slide (Slide 1 / [plain] / \titlepage containing author, student, guide, college, date metadata) is SACRED. NEVER replace or overwrite the Title Slide when updating content slides (Methodology, Literature Survey, Introduction, Architecture, Results, References, etc.).
   - `original_chunk` must target that specific topic's existing block (e.g. `\begin{frame}{...Methodology...}...\end{frame}`), NEVER the first slide in the deck!
4. DELETIONS & REMOVALS:
   - If user asks to delete/remove a slide, section, or content ("delete slide 7", "remove last slide", "delete slide containing X"):
   - Set `original_chunk` to the exact verbatim unit to delete (e.g. `\begin{frame}...\end{frame}`).
   - Set `proposed_chunk` to `""` (empty string).
   - In `explanation`, state which slide/item was deleted.
5. SYNCHRONIZE REFERENCES:
   - When new papers, datasets, or citations are added, update BOTH the relevant content slide AND the `\begin{thebibliography}` bibliography slide.
6. NO COMMENTARY IN LATEX: `proposed_chunk` is raw compilable LaTeX only — no markdown, no conversational commentary.
7. NO OVERFLOW: Adapt content cleanly (max 6 bullets/slide, tabularx for tables, split slide with `(cont'd)` if needed) to prevent vertical overflow.
"""


def _format_chunks(chunks: Union[str, List[str]]) -> str:
    """
    Ensure retrieved context is presented with explicit, unambiguous
    chunk boundaries while keeping token consumption lightweight.
    """
    if not chunks:
        return ""

    if isinstance(chunks, str):
        return chunks[:2000]

    formatted = []
    for i, chunk in enumerate(chunks[:5], start=1):
        clean = chunk.strip()
        if len(clean) > 500:
            clean = clean[:500] + "\n...[truncated]"
        formatted.append(f"[CHUNK {i}]\n{clean}\n[END CHUNK {i}]")
    return "\n\n".join(formatted)


def build_prompt(
    user_request: str,
    retrieved_context: Union[str, List[str]],
    conversation_context: str = "",
    project_context: str = "",
    attached_file_info: Optional[Dict[str, str]] = None,
    current_code: Optional[str] = None,
    target_context: Optional[str] = None,
    is_edit_mode: bool = False,
) -> List:
    """
    Assemble the complete LLM prompt with smart token budgeting.

    Args:
        target_context: Focused context from build_targeted_context() for edits.
                        When provided, replaces retrieved_context and reduces
                        current_code budget for minimal token usage.
        is_edit_mode: When True, injects instruction priority rules and uses
                      tighter token budgets suitable for free-tier LLM APIs.
    """
    # --- System Message ---
    system_parts = [SYSTEM_PROMPT_CORE]

    # Inject instruction priority block for edit operations
    if is_edit_mode:
        system_parts.append(INSTRUCTION_PRIORITY_BLOCK)

    if project_context:
        system_parts.append(
            f"\n--------------------------------\n"
            f"PROJECT CONTEXT\n"
            f"--------------------------------\n"
            f"{project_context[:1500]}"
        )

    if conversation_context:
        system_parts.append(
            f"\n--------------------------------\n"
            f"CONVERSATION HISTORY\n"
            f"--------------------------------\n"
            f"{conversation_context[:1500]}"
        )

    system_content = "\n".join(system_parts)

    # --- User Message ---
    user_parts = []

    # Include the current document — smart budgeting based on mode
    if current_code and current_code.strip():
        doc_text = current_code.strip()
        if is_edit_mode and target_context:
            # For targeted edits, send a reduced document window.
            # The full doc is still needed for original_chunk matching,
            # but we can cap it much tighter since the targeted context
            # already provides the relevant slide/page.
            doc_budget = 4000
        else:
            # Full document for generation/conversion/full edits
            doc_budget = 12000

        if len(doc_text) > doc_budget:
            doc_text = doc_text[:doc_budget] + f"\n...[DOCUMENT TRUNCATED FOR TOKEN BUDGET AT {doc_budget} CHARS]"
        user_parts.append(
            f"CURRENT FULL DOCUMENT (the user's complete LaTeX source — use this for original_chunk matching):\n"
            f"```latex\n{doc_text}\n```"
        )

    # Use targeted context when available, otherwise use retrieved chunks
    if target_context:
        user_parts.append(
            f"TARGETED DOCUMENT CONTEXT (the specific slide/page being edited and its neighbors):\n"
            f"{target_context}"
        )
    else:
        formatted_chunks = _format_chunks(retrieved_context)
        if formatted_chunks:
            user_parts.append(f"RETRIEVED FILE CONTEXT:\n{formatted_chunks}")

    if attached_file_info:
        file_name = attached_file_info.get("filename", "Uploaded File")
        file_type = attached_file_info.get("file_type", "text/plain")
        file_content = attached_file_info.get("content", "")
        # Cap attached file content — generous for generation, tight for edits
        attach_budget = 20000 if not is_edit_mode else 8000
        if len(file_content) > attach_budget:
            file_content = file_content[:attach_budget] + f"\n...[ATTACHED REFERENCE FILE TRUNCATED AT {attach_budget} CHARS]"
        user_parts.append(
            f"--------------------------------\n"
            f"REFERENCE ATTACHED FILE: {file_name} (type: {file_type})\n"
            f"--------------------------------\n"
            f"CONTENT:\n{file_content}\n"
            f"[END REFERENCE FILE]\n"
            f"INSTRUCTION FOR REFERENCE FILE: Use this attached file as reference content to satisfy the USER REQUEST.\n"
            f"1. Extract key topics, names, content, and structure from the PDF.\n"
            f"2. Map the extracted content to EXISTING chapters/sections/slides in the CURRENT DOCUMENT.\n"
            f"3. Replace placeholder/template text inside each matching section with real content.\n"
            f"4. Strictly preserve ALL front-matter (title page, certificate, acknowledgement, abstract) and styling.\n"
            f"5. Preserve ALL back-matter (bibliography, appendices).\n"
            f"6. Do NOT create new chapters/sections unless the existing document has no matching section for that content."
        )

    user_parts.append(f"USER REQUEST: {user_request}")

    user_content = "\n\n".join(user_parts)

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=user_content),
    ]

    logger.info(f"Prompt builder: system={len(system_content)} chars, user={len(user_content)} chars"
                f"{' [EDIT MODE]' if is_edit_mode else ''}")
    return messages


# ============================================================================
# ASK MODE — Question-Only System Prompt (No Edits)
# ============================================================================
ASK_MODE_SYSTEM_PROMPT = r"""You are an expert LaTeX assistant embedded inside OverBranch, a professional LaTeX IDE. You are in ASK MODE — you answer questions about LaTeX, the user's document, and attached files. You NEVER propose code edits, modifications, or generate LaTeX code blocks to replace document content.

RULES:
1. Answer the user's question clearly and concisely using markdown formatting.
2. Use the provided CURRENT DOCUMENT, RETRIEVED CONTEXT, and ATTACHED FILES as reference when answering questions about the user's project.
3. When referencing specific parts of the user's document, mention section names, line numbers, or LaTeX commands by name.
4. For LaTeX syntax questions, provide short inline code examples using backtick formatting (`\command{}`), NOT full document blocks.
5. NEVER output a JSON edit response. NEVER include "original_chunk", "proposed_chunk", or "edits" fields.
6. NEVER suggest replacing or modifying the user's document. If they ask you to edit, politely suggest switching to Edit mode.
7. Format your response in clean markdown with:
   - **Bold** for emphasis
   - `inline code` for LaTeX commands
   - Bullet lists for multiple points
   - > Blockquotes for important notes
8. Keep responses focused and helpful. Avoid unnecessary verbosity.
"""


def build_ask_prompt(
    user_request: str,
    retrieved_context: Union[str, List[str]],
    conversation_context: str = "",
    project_context: str = "",
    attached_file_info: Optional[Dict[str, str]] = None,
    current_code: Optional[str] = None,
) -> List:
    """
    Assemble the prompt for Ask mode — question-only, no edits.
    Uses more generous context budgets since we don't need edit precision.
    """
    # --- System Message ---
    system_parts = [ASK_MODE_SYSTEM_PROMPT]

    if project_context:
        system_parts.append(
            f"\n--------------------------------\n"
            f"PROJECT CONTEXT\n"
            f"--------------------------------\n"
            f"{project_context[:2000]}"
        )

    if conversation_context:
        system_parts.append(
            f"\n--------------------------------\n"
            f"CONVERSATION HISTORY\n"
            f"--------------------------------\n"
            f"{conversation_context[:2000]}"
        )

    system_content = "\n".join(system_parts)

    # --- User Message ---
    user_parts = []

    # Include document with generous budget (Ask mode needs broad context)
    if current_code and current_code.strip():
        doc_text = current_code.strip()
        doc_budget = 10000  # More generous for Ask mode
        if len(doc_text) > doc_budget:
            doc_text = doc_text[:doc_budget] + f"\n...[DOCUMENT TRUNCATED AT {doc_budget} CHARS]"
        user_parts.append(
            f"CURRENT DOCUMENT (the user's complete LaTeX source — use as reference):\n"
            f"```latex\n{doc_text}\n```"
        )

    # Retrieved chunks — include more for Ask mode
    formatted_chunks = _format_chunks(retrieved_context)
    if formatted_chunks:
        user_parts.append(f"RETRIEVED DOCUMENT CONTEXT:\n{formatted_chunks}")

    if attached_file_info:
        file_name = attached_file_info.get("filename", "Uploaded File")
        file_type = attached_file_info.get("file_type", "text/plain")
        file_content = attached_file_info.get("content", "")
        attach_budget = 25000  # Generous for Ask mode
        if len(file_content) > attach_budget:
            file_content = file_content[:attach_budget] + f"\n...[FILE TRUNCATED AT {attach_budget} CHARS]"
        user_parts.append(
            f"ATTACHED REFERENCE FILE: {file_name} (type: {file_type})\n"
            f"CONTENT:\n{file_content}\n"
            f"[END REFERENCE FILE]"
        )

    user_parts.append(f"USER QUESTION: {user_request}")

    user_content = "\n\n".join(user_parts)

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=user_content),
    ]

    logger.info(f"Ask-mode prompt: system={len(system_content)} chars, user={len(user_content)} chars")
    return messages


# ============================================================================
# BROAD EDIT MODE — Per-Chapter/Section Scoped Prompt
# ============================================================================

BROAD_EDIT_SYSTEM_PROMPT = r"""You are an expert LaTeX editing agent embedded inside OverBranch, a professional LaTeX IDE. You are editing ONE SPECIFIC existing chapter/section of a document as part of a multi-section batch edit.

CRITICAL RULES:
1. You are editing an EXISTING section. Do NOT create new sections or chapters. Do NOT use create_content.
2. You MUST use edit_chunk to modify the existing content in-place.
3. The `original_chunk` must be the EXACT existing text provided below.
4. The `proposed_chunk` must be the improved/edited version of that same section.
5. PRESERVE the section heading (e.g. \chapter{...} or \section{...}) — only edit the body content.
6. Your response must be ONLY a JSON object matching this schema — NO freeform prose, NO commentary, NO markdown:

{
  "plan": "Brief description of changes",
  "edits": [
    {
      "original_chunk": "The exact existing text provided",
      "proposed_chunk": "Your improved version",
      "explanation": "What you changed and why"
    }
  ]
}

7. The proposed_chunk must be complete, compilable LaTeX. No truncation. No placeholders.
8. Do NOT add \documentclass, \begin{document}, or \end{document} — you are editing a section WITHIN an existing document.
9. Max output: the edited section only. Keep it focused and complete.
"""


def _extract_relevant_attached_content(
    full_content: str,
    page_title: str,
    budget: int = 4000,
) -> str:
    """
    Extract the portion of attached file content most relevant to a specific
    chapter/section title. Uses keyword matching to find relevant paragraphs.

    If the full content is small enough (≤ budget), returns it as-is.
    Otherwise, finds paragraphs containing title keywords and returns those
    plus a truncated global context.
    """
    import re as _re

    if not full_content or not full_content.strip():
        return ""

    # Small file shortcut — just send the whole thing
    if len(full_content) <= budget:
        return full_content

    # Extract significant keywords from the chapter title
    stop_words = {
        "the", "a", "an", "of", "and", "or", "in", "on", "for", "to",
        "with", "by", "at", "from", "is", "are", "was", "were", "be",
        "this", "that", "it", "its", "as", "not", "but", "if", "can",
    }
    title_words = set(
        w.lower() for w in _re.findall(r"[a-zA-Z]{3,}", page_title)
    ) - stop_words

    if not title_words:
        # No meaningful keywords — return first chunk
        return full_content[:budget] + "\n...[TRUNCATED]"

    # Split into paragraphs and score by keyword overlap
    paragraphs = _re.split(r"\n\s*\n|\n(?=\[Page \d)", full_content)
    scored = []
    for para in paragraphs:
        para_stripped = para.strip()
        if len(para_stripped) < 20:
            continue
        para_words = set(w.lower() for w in _re.findall(r"[a-zA-Z]{3,}", para_stripped))
        overlap = len(title_words & para_words)
        if overlap > 0:
            scored.append((overlap, para_stripped))

    # Sort by relevance (most keyword matches first)
    scored.sort(key=lambda x: x[0], reverse=True)

    if scored:
        # Build relevant content from top-matching paragraphs
        relevant_parts = []
        total_chars = 0
        for score, para in scored:
            if total_chars + len(para) > budget:
                remaining = budget - total_chars
                if remaining > 200:
                    relevant_parts.append(para[:remaining] + "...[TRUNCATED]")
                break
            relevant_parts.append(para)
            total_chars += len(para)
        return "\n\n".join(relevant_parts)
    else:
        # No keyword matches — return first chunk as global context
        return full_content[:budget] + "\n...[TRUNCATED]"


def build_broad_edit_prompt(
    user_request: str,
    page_id: str,
    page_title: str,
    page_content: str,
    page_index: int,
    total_targets: int,
    conversation_context: str = "",
    project_context: str = "",
    attached_file_info: Optional[Dict[str, str]] = None,
) -> List:
    """
    Build a scoped prompt for editing a single chapter/section as part of
    a broad multi-target edit loop.

    This prompt gives the LLM:
    - The exact existing content of ONE chapter/section
    - The user's broad instruction
    - Relevant portions of the attached reference document (if any)
    - Strict instructions to use edit_chunk (not create_content)
    - A tight JSON-only output contract

    Args:
        user_request: The user's original broad instruction
        page_id: Stable ID of this target page (e.g. "sec-introduction")
        page_title: Human-readable title (e.g. "Introduction")
        page_content: Full existing LaTeX source of this page
        page_index: 0-based index of this page in the document
        total_targets: Total number of targets being edited in this batch
        conversation_context: Recent conversation history
        project_context: Project-level context (assets, metadata)
        attached_file_info: Optional attached reference file dict with
                           keys: filename, file_type, content
    """
    # --- System Message ---
    system_parts = [BROAD_EDIT_SYSTEM_PROMPT]

    if project_context:
        system_parts.append(
            f"\n--------------------------------\n"
            f"PROJECT CONTEXT\n"
            f"--------------------------------\n"
            f"{project_context[:800]}"
        )

    if conversation_context:
        system_parts.append(
            f"\n--------------------------------\n"
            f"CONVERSATION HISTORY\n"
            f"--------------------------------\n"
            f"{conversation_context[:800]}"
        )

    system_content = "\n".join(system_parts)

    # --- User Message ---
    user_parts = []

    # Cap page content to prevent overly large prompts (single chapter should be <8k)
    content_budget = 8000
    display_content = page_content.strip()
    if len(display_content) > content_budget:
        display_content = display_content[:content_budget] + "\n...[SECTION TRUNCATED FOR TOKEN BUDGET]"

    user_parts.append(
        f"EDITING TARGET: Section {page_index + 1} of {total_targets}\n"
        f"PAGE ID: {page_id}\n"
        f"SECTION TITLE: {page_title}\n\n"
        f"EXISTING SECTION CONTENT (this is your original_chunk — edit this in-place):\n"
        f"```latex\n{display_content}\n```"
    )

    # Include relevant portions of the attached reference document
    if attached_file_info and attached_file_info.get("content"):
        file_name = attached_file_info.get("filename", "Uploaded File")
        file_content = attached_file_info.get("content", "")

        # Extract only the portion relevant to this chapter's topic
        relevant_content = _extract_relevant_attached_content(
            full_content=file_content,
            page_title=page_title,
            budget=4000,
        )

        if relevant_content:
            user_parts.append(
                f"REFERENCE DOCUMENT: {file_name}\n"
                f"(Relevant content for '{page_title}' section extracted below)\n"
                f"--------------------------------\n"
                f"{relevant_content}\n"
                f"[END REFERENCE CONTENT]\n\n"
                f"INSTRUCTION: Use the REFERENCE DOCUMENT content above as the source "
                f"of real data, names, facts, and details to fill into this section. "
                f"Do NOT invent or hallucinate content — use ONLY what is in the "
                f"reference document. If the reference has no relevant content for "
                f"this section, keep the existing content with minimal improvements."
            )

    user_parts.append(
        f"USER REQUEST (apply to this section): {user_request}\n\n"
        f"REMINDER: Respond with ONLY the JSON edit object. "
        f"original_chunk = the exact existing text above. "
        f"proposed_chunk = your improved version. "
        f"Do NOT create new sections. Do NOT wrap in \\documentclass."
    )

    user_content = "\n\n".join(user_parts)

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=user_content),
    ]

    logger.info(
        f"Broad-edit prompt [{page_index + 1}/{total_targets}]: "
        f"page_id='{page_id}', title='{page_title}', "
        f"system={len(system_content)} chars, user={len(user_content)} chars"
        f"{' [+attached]' if attached_file_info else ''}"
    )
    return messages