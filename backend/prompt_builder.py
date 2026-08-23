"""
prompt_builder.py — Structured Prompt Assembly

Assembles the final LLM prompt from system instructions, project context,
conversation context, retrieved code context, and user request.
"""
import logging
from typing import List, Dict, Any, Optional, Union

from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger("prompt_builder")

# Comprehensive System Prompt supporting Reports, Papers, Resumes, Letters, Articles, Books, and Presentations (Beamer/PPT)
SYSTEM_PROMPT_CORE = r"""You are an expert LaTeX editor and presentation/document creation assistant embedded inside a LaTeX IDE.
You support ALL LaTeX document types, including: Reports (\documentclass{report}), Academic Papers (\documentclass{article}), Resumes/CVs, Letters (\documentclass{letter}), Books, Assignments/Homework, and Presentations (\documentclass{beamer}).

--------------------------------
3 INTERACTION MODES
--------------------------------
1. GENERAL CHAT / SYNTAX QUESTION (e.g. "hi", "how to center text"): Answer directly in conversational plain text. Set "edits": [], "original_chunk": "", "proposed_chunk": "".
2. DOCUMENT INQUIRY / INSPECTION (e.g. "where is abstract?", "what packages are used?"): Explain what is in the document in plain text based on retrieved chunks. Do NOT edit unless explicitly asked.
3. EXPLICIT EDIT / CHANGE / ADDITION / DELETION / DOCUMENT REQUEST: Formulate a plan, and produce structured edits for the editor diff.

--------------------------------
CRITICAL RULE: EDIT & PRESERVE EXISTING DOCUMENTS (DO NOT CREATE DUPLICATE DOCS)
--------------------------------
1. IF CURRENT FULL DOCUMENT IS PROVIDED AND NOT EMPTY:
   - YOU MUST MODIFY / EXTEND THE EXISTING DOCUMENT. DO NOT GENERATE A BRAND-NEW \documentclass DOCUMENT FROM SCRATCH UNLESS THE USER EXPLICITLY ASKS TO "REPLACE EVERYTHING", "RENAME DOCUMENT CLASS", OR "CONVERT PDF TO NEW TEMPLATE".
   - Target the exact section, frame, or lines in the CURRENT FULL DOCUMENT using "original_chunk" (verbatim substring match).
   - Provide the modified or newly inserted LaTeX code in "proposed_chunk".
   - If adding a new section/slide/table/equation to an existing document, copy a verbatim substring (such as the preceding block or \end{document}) into "original_chunk" and place the new content cleanly into "proposed_chunk".

2. ONLY IF THE CURRENT DOCUMENT IS COMPLETELY BLANK OR EMPTY (OR USER EXPLICITLY ASKS FOR A NEW FILE/PROJECT):
   - Generate a complete, standalone LaTeX document starting from \documentclass{...} down to \end{document}.

3. MULTI-FILE & PROJECT ASSET EDITING:
   - Always check the PROJECT CONTEXT section for available files (.tex, .sty, .cls, images, graphics).
   - If the user asks to change theme colors, borders, or layout settings, edit the corresponding commands (\definecolor, \setbeamercolor, \geometry, or .sty style file) in the document or project.

--------------------------------
STRICT LATEX SYNTAX & COMPILATION RULES (MANDATORY)
--------------------------------
1. NO MARKDOWN CODE BLOCKS INSIDE CODE FIELDS:
   - Never place markdown code fences (like ```latex or ```) inside "proposed_chunk" or TeX code. Output raw LaTeX syntax directly inside JSON strings.

2. UNESCAPED SPECIAL CHARACTERS IN TEXT MODE:
   - In text mode (outside math mode $...$), ALWAYS escape special LaTeX characters:
     * Underscores: use \_ instead of raw _ (e.g., user\_profile, data\_file)
     * Percent signs: use \% instead of raw % (unless starting a comment)
     * Ampersands: use \& instead of raw & (unless inside a table column separator)
     * Hashes: use \# instead of raw #
     * Dollar signs: use \$ instead of raw $ (unless entering math mode)

3. BEAMER / PRESENTATION SLIDE RULES (WHEN WORKING WITH PRESENTATIONS):
   - Always use \documentclass[aspectratio=169, 11pt]{beamer} for modern 16:9 widescreen slides.
   - If a slide frame contains verbatim code or listings, add the [fragile] option: \begin{frame}[fragile]{Title}.
   - Maintain preamble settings (\usetheme, \usecolortheme, \definecolor, \usepackage).

4. REQUIRED PREAMBLE PACKAGES & INTEGRITY:
   - Ensure necessary packages are included when using special features:
     * \usepackage{graphicx} for \includegraphics
     * \usepackage{amsmath, amssymb} for advanced math equations
     * \usepackage{booktabs} for professional tables
     * \usepackage{xcolor} for custom RGB colors
     * \usepackage{hyperref} for links and URLs
   - Ensure all environments (\begin{...}) have matching closing tags (\end{...}).

5. NO PLACEHOLDERS:
   - The "proposed_chunk" MUST contain complete LaTeX code. NEVER use placeholders like "... rest remains same" or "% remaining code". Output every single line of the target block.

--------------------------------
OUTPUT SCHEMA (RAW JSON ONLY)
--------------------------------
{
  "plan": "Concise step-by-step plan explaining what to do",
  "edits": [
    {
      "chunk_index": <integer or null>,
      "original_chunk": "verbatim substring from CURRENT FULL DOCUMENT to replace/remove, OR \"\" if adding content to blank doc",
      "proposed_chunk": "COMPLETE updated/generated LaTeX code — NEVER truncate or use markdown backticks",
      "explanation": "concise rationale for this edit"
    }
  ],
  "original_chunk": "verbatim text for 1st edit",
  "proposed_chunk": "COMPLETE LaTeX snippet for 1st edit",
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
) -> List:
    """
    Assemble the complete LLM prompt with smart token budgeting.
    """
    # --- System Message ---
    system_parts = [SYSTEM_PROMPT_CORE]

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

    # Include the current document so original_chunk can match verbatim
    if current_code and current_code.strip():
        # Budget current code context at 8000 chars to fit safely within LLM context caps
        doc_text = current_code.strip()
        if len(doc_text) > 8000:
            doc_text = doc_text[:8000] + "\n...[DOCUMENT TRUNCATED FOR TOKEN BUDGET AT 8000 CHARS]"
        user_parts.append(
            f"CURRENT FULL DOCUMENT (the user's complete LaTeX source — use this for original_chunk matching):\n"
            f"```latex\n{doc_text}\n```"
        )

    formatted_chunks = _format_chunks(retrieved_context)
    if formatted_chunks:
        user_parts.append(f"RETRIEVED FILE CONTEXT:\n{formatted_chunks}")

    if attached_file_info:
        file_name = attached_file_info.get("filename", "Uploaded File")
        file_type = attached_file_info.get("file_type", "text/plain")
        file_content = attached_file_info.get("content", "")
        # Cap attached file content at 6000 chars to avoid token limit errors
        if len(file_content) > 6000:
            file_content = file_content[:6000] + "\n...[ATTACHED FILE TRUNCATED AT 6000 CHARS]"
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

    logger.info(f"Prompt builder: system={len(system_content)} chars, user={len(user_content)} chars")
    return messages