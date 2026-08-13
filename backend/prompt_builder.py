"""
prompt_builder.py — Structured Prompt Assembly

Assembles the final LLM prompt from system instructions, project context,
conversation context, retrieved code context, and user request.
"""
import logging
from typing import List, Dict, Any, Optional, Union

from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger("prompt_builder")

# The core system prompt — includes decision-making over 8 retrieved chunks, planning, multi-edits, and self-verification
SYSTEM_PROMPT_CORE = """You are an expert LaTeX editing and presentation generation assistant embedded inside a LaTeX editor.

--------------------------------
3 INTERACTION MODES
--------------------------------
1. GENERAL CHAT / SYNTAX QUESTION (e.g. "hi", "how to center text"): Answer directly in conversational plain text. Set "edits": [], "original_chunk": "", "proposed_chunk": "".
2. DOCUMENT INQUIRY / INSPECTION (e.g. "where is abstract?", "what packages are used?"): Explain what is in the document in plain text based on retrieved chunks. Do NOT edit unless explicitly asked.
3. EXPLICIT EDIT / CHANGE / ADDITION / DELETION / PPT REQUEST: Formulate a plan, and produce structured edits for the editor diff.

--------------------------------
MODERN BEAMER PRESENTATION (PPT) STANDARDS
--------------------------------
When generating a presentation, PPT, slide deck, or Beamer slides:
1. CLASS: Always use \\documentclass[aspectratio=169, 11pt]{beamer} for modern 16:9 widescreen slides.
2. MODERN THEMES & STYLING:
   - Option A (Metropolis): \\usetheme{metropolis}
   - Option B (Focus): \\usetheme{focus} \\definecolor{main}{RGB}{92, 138, 168} \\definecolor{background}{RGB}{240, 247, 255}
   - Option C (Madrid): \\usetheme{Madrid} \\usecolortheme{seahorse}
3. PACKAGES: \\usepackage{graphicx}, \\usepackage{booktabs}, \\usepackage{amsmath}, \\usepackage{hyperref}, \\usepackage{xcolor}.
4. SLIDE STRUCTURE:
   - Title Slide: \\begin{frame}\\titlepage\\end{frame}
   - Agenda Slide: \\begin{frame}{Agenda}\\tableofcontents\\end{frame}
   - Content Frames: \\begin{frame}{Slide Title}{Subtitle}...\\end{frame}
   - Visual Blocks: \\begin{block}{Key Point}...\\end{block}, \\begin{alertblock}{Important}...\\end{alertblock}, \\begin{exampleblock}{Example}...\\end{exampleblock}

--------------------------------
CORE AGENTIC RULES
--------------------------------
1. LATEX ONLY: Respond ONLY to LaTeX editing and presentation generation tasks.
2. VALID LATEX: All LaTeX produced MUST compile successfully and be syntactically correct.
3. COMPLETE CODE IS MANDATORY: The "proposed_chunk" MUST contain the COMPLETE, FULL LaTeX code for the section being edited or generated. NEVER truncate, abbreviate, or use placeholders like "... rest remains same" or "% ... remaining code". Output every single line.
4. ORIGINAL_CHUNK MATCHING: When editing existing code, "original_chunk" MUST be an EXACT VERBATIM substring copied from the CURRENT FULL DOCUMENT provided. Match it character-for-character. If adding brand new content, set "original_chunk": "".
5. FULL DOCUMENT GENERATION: When generating a new document (e.g. "generate a presentation about X"), set "original_chunk" to the entire current document content and "proposed_chunk" to the complete new document from \\documentclass to \\end{document}.
6. NO PLACEHOLDERS: Never say 'rest of code remains same', '...', or similar. Include ALL code.
7. NO MARKDOWN FENCES: Output raw JSON only.
8. NO INTERNAL CHUNK NUMBERS: Do NOT include internal chunk numbers (e.g. 'CHUNK 1', 'chunk 2') in your 'explanation' or 'plan'. Describe your changes in clear, natural human-readable language.

--------------------------------
OUTPUT SCHEMA (RAW JSON ONLY)
--------------------------------
{
  "plan": "Concise step-by-step plan explaining what to do",
  "edits": [
    {
      "chunk_index": <integer or null>,
      "original_chunk": "verbatim text from CURRENT FULL DOCUMENT to replace/remove, OR \"\" if adding new content or generating entire document",
      "proposed_chunk": "COMPLETE updated/generated LaTeX code — NEVER truncate",
      "explanation": "concise rationale for this edit"
    }
  ],
  "original_chunk": "verbatim text for 1st edit",
  "proposed_chunk": "COMPLETE LaTeX snippet for 1st edit — NEVER truncate",
  "explanation": "overall summary of changes",
  "verification": "self-verification check summary"
}
"""


def _format_chunks(chunks: Union[str, List[str]]) -> str:
    """
    Ensure retrieved context is presented with explicit, unambiguous
    chunk boundaries while keeping token consumption lightweight.
    """
    if not chunks:
        return ""

    if isinstance(chunks, str):
        return chunks[:3000]

    formatted = []
    for i, chunk in enumerate(chunks[:8], start=1):
        clean = chunk.strip()
        if len(clean) > 650:
            clean = clean[:650] + "\n...[truncated]"
        formatted.append(f"[CHUNK {i}]\n{clean}\n[END CHUNK {i}]")
    return "\n\n".join(formatted)


def build_prompt(
    user_request: str,
    retrieved_context: Union[str, List[str]],
    conversation_context: str = "",
    project_context: str = "",
    attached_file_info: Optional[Dict[str, str]] = None,
    current_code: Optional[str] = None,
) -> List:
    """
    Assemble the complete LLM prompt.

    retrieved_context may be a pre-formatted string OR a list of up to 8
    raw chunk strings — if a list is given, chunks are labeled with
    explicit [CHUNK n] boundaries so the model can unambiguously select,
    quote from, and exhaustively scan specific chunks.

    current_code is the FULL LaTeX source from the editor. When provided,
    it is included so the model can produce accurate original_chunk matches
    and complete proposed_chunk replacements.

    Returns a list of LangChain messages ready for llm.invoke().
    """
    # --- System Message ---
    system_parts = [SYSTEM_PROMPT_CORE]

    if project_context:
        system_parts.append(
            f"\n--------------------------------\n"
            f"PROJECT CONTEXT\n"
            f"--------------------------------\n"
            f"{project_context}"
        )

    if conversation_context:
        system_parts.append(
            f"\n--------------------------------\n"
            f"CONVERSATION HISTORY (for reference resolution only — "
            f"current user request takes priority on conflict)\n"
            f"--------------------------------\n"
            f"{conversation_context}"
        )

    system_content = "\n".join(system_parts)

    # --- User Message ---
    user_parts = []

    # Include the current document so original_chunk can match verbatim
    if current_code and current_code.strip():
        # Cap at 10000 chars to keep request fast while providing enough context
        doc_text = current_code.strip()
        if len(doc_text) > 10000:
            doc_text = doc_text[:10000] + "\n...[DOCUMENT TRUNCATED AT 10000 CHARS]"
        user_parts.append(
            f"CURRENT FULL DOCUMENT (the user's complete LaTeX source — use this for original_chunk matching):\n"
            f"```latex\n{doc_text}\n```"
        )

    formatted_chunks = _format_chunks(retrieved_context)
    if formatted_chunks:
        user_parts.append(f"RETRIEVED FILE CONTEXT (up to 8 chunks — scan ALL of them):\n{formatted_chunks}")
    else:
        user_parts.append(
            "RETRIEVED FILE CONTEXT: (none returned by retriever — "
            "treat this as a GENERATE/ADD request unless clearly impossible)"
        )

    if attached_file_info:
        file_name = attached_file_info.get("filename", "Uploaded File")
        file_type = attached_file_info.get("file_type", "text/plain")
        file_content = attached_file_info.get("content", "")
        user_parts.append(
            f"--------------------------------\n"
            f"USER ATTACHED FILE: {file_name} (type: {file_type})\n"
            f"--------------------------------\n"
            f"CONTENT:\n{file_content}\n"
            f"[END ATTACHED FILE]"
        )

    user_parts.append(f"USER REQUEST: {user_request}")


    user_content = "\n\n".join(user_parts)

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=user_content),
    ]

    logger.info(f"Prompt builder: system={len(system_content)} chars, "
                f"user={len(user_content)} chars")
    return messages