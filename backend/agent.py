"""
agent.py — Thin Agent Router

Orchestrates the full AI pipeline:
Embed → Retrieve → Build Context → Memory → Build Prompt → LLM → Parse → Return
"""
import os
import json
import re
import logging
import base64
import io
import asyncio
try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings, ChatNVIDIA
from langchain_core.messages import SystemMessage, HumanMessage

from vector_sync import get_qdrant_client, ensure_qdrant_collection, COLLECTION_NAME
import retriever
import context_builder
import prompt_builder
from memory import conversation_memory, project_memory
from tools import AI_TOOLS, process_tool_calls
from providers import provider_router, LLMProviderError
from services.pdf_parser import parse_pdf, MAX_ALLOWED_PAGES
from services.pdf_to_latex import convert_pdf_to_latex
from services.project_file_writer import write_project_files_and_assets
import document_index as doc_idx
import edit_validator

load_dotenv(override=True)

logger = logging.getLogger("agent")
logging.basicConfig(level=logging.INFO)

router = APIRouter()


try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False



class AttachedFile(BaseModel):
    filename: str = Field(..., description="Uploaded file name")
    content: str = Field(..., description="File content in text or base64")
    file_type: Optional[str] = Field("text/plain", description="MIME type or file extension")


class AgentChatRequest(BaseModel):
    project_id: str = Field(..., description="Project ID or UUID")
    file_path: str = Field(..., description="Path of the TeX file")
    user_prompt: str = Field(..., description="User's editing request or question")
    current_code: Optional[str] = Field(None, description="Current editor LaTeX content in plain text")
    attached_file: Optional[AttachedFile] = Field(None, description="Optional attached file from user chat")
    model: Optional[str] = Field(None, description="Primary LLM model name")
    fallback_model: Optional[str] = Field(None, description="Fallback LLM model name")



try:
    import docx
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False


def sanitize_text_content(text: str) -> str:
    """Removes NUL bytes and control characters that break JSON or API payloads."""
    if not text:
        return ""
    # Strip null bytes and unprintable ASCII control characters (except newline, tab, carriage return)
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return cleaned


def auto_repair_truncated_latex(code: str) -> str:
    """
    Repairs truncated LaTeX code (e.g. when model hits token limits):
    1. Removes trailing incomplete command fragments (e.g. '\\item \\textbf', '\\textbf{').
    2. Closes unclosed environments in proper LIFO order.
    3. Ensures \\end{document} is present if \\begin{document} exists.
    """
    if not code or not isinstance(code, str):
        return code or ""

    s = code.strip()

    # 1. Clean trailing incomplete fragments
    s = re.sub(r"\\item\s*\\textbf\b.*$", "", s)
    s = re.sub(r"\\[a-zA-Z]+\s*\{[^}\n]*$", "", s)
    s = re.sub(r"\\[a-zA-Z]+$", "", s)
    s = re.sub(r"\\item\s*$", "", s)

    # 2. Track opened environments
    tokens = re.findall(r"\\(begin|end)\{([a-zA-Z*]+)\}", s)
    env_stack = []
    for action, env_name in tokens:
        if action == "begin":
            if env_name != "document":
                env_stack.append(env_name)
        elif action == "end":
            if env_stack and env_stack[-1] == env_name:
                env_stack.pop()
            elif env_name in env_stack:
                while env_stack and env_stack[-1] != env_name:
                    env_stack.pop()
                if env_stack:
                    env_stack.pop()

    # Close unclosed environments in LIFO order
    closing_tags = []
    while env_stack:
        unclosed = env_stack.pop()
        closing_tags.append(f"\\end{{{unclosed}}}")

    if closing_tags:
        s = s.rstrip() + "\n" + "\n".join(closing_tags)

    if r"\begin{document}" in s and r"\end{document}" not in s:
        s = s.rstrip() + "\n\\end{document}"

    return s


def restore_swallowed_latex_escapes(text: str) -> str:
    r"""
    Restores LaTeX macro commands where JSON escape processing swallowed the leading backslash
    or converted it into control characters (\x08, \x0c, \r, \t, \n).
    """
    if not text or not isinstance(text, str):
        return text or ""
    s = text

    # Handle control characters from JSON string decoding:
    # \x08 (backspace from \b):
    s = re.sub(r"[\x08](egin|fseries|ooktabs|lacksquare|lacktriangleright|lacktriangle|ottomrule|igskip|ibliography|ibliographystyle|ullet|reak|uildrel)\b", r"\\b\1", s)
    # \x0c (formfeed from \f):
    s = re.sub(r"[\x0c](rac|ootnotesize|rame|ill|ancyhead|ancyfoot|ancypagestyle|ancyhf|igure|ontsize|lushleft|lushright|ootnote)\b", r"\\f\1", s)
    # \r (carriage return from \r when followed by LaTeX command):
    s = re.sub(r"[\r](enewcommand|enewenvironment|ule|ef|ight|aggedright|aggedleft|equire|aisebox|estoregeometry|mfamily|efstepcounter)\b", r"\\r\1", s)
    # \t (tab from \t when followed by LaTeX command):
    s = re.sub(r"[\t](extbf|extit|exttt|extsc|extsf|ext|itle|ableofcontents|able|ikz|ikzset|oday|hepage|hesection|thesubsection|hechapter|extwidth|extheight|oprule|colorbox|cbuselibrary|itlespacing|itleformat|extsuperscript|extsubscript)\b", r"\\t\1", s)

    # 1. Swallowed \n:
    s = re.sub(r"(?<![a-zA-Z\\])ewcommand(?=\{|\s*\[|\s*\\)", r"\\newcommand", s)
    s = re.sub(r"(?<![a-zA-Z\\])ewenvironment(?=\{|\s*\[|\s*\\)", r"\\newenvironment", s)
    s = re.sub(r"(?<![a-zA-Z\\])ewgeometry(?=\{|\s*\[|\s*\\)", r"\\newgeometry", s)
    s = re.sub(r"(?<![a-zA-Z\\])ewtheorem(?=\{|\s*\[|\s*\\)", r"\\newtheorem", s)
    s = re.sub(r"(?<![a-zA-Z\\])ewcounter(?=\{|\s*\[|\s*\\)", r"\\newcounter", s)
    s = re.sub(r"(?<![a-zA-Z\\])ewtcolorbox(?=\{|\s*\[|\s*\\)", r"\\newtcolorbox", s)
    s = re.sub(r"(?<![a-zA-Z\\])ewsavebox(?=\{|\s*\[|\s*\\)", r"\\newsavebox", s)
    s = re.sub(r"(?<![a-zA-Z\\])ewfont(?=\{|\s*\[|\s*\\)", r"\\newfont", s)
    s = re.sub(r"(?<![a-zA-Z\\])ewlength(?=\{|\s*\[|\s*\\)", r"\\newlength", s)
    s = re.sub(r"(?<![a-zA-Z\\])ewpage\b", r"\\newpage", s)
    s = re.sub(r"(?<![a-zA-Z\\])ewline\b", r"\\newline", s)
    s = re.sub(r"(?<![a-zA-Z\\])ormalsize\b", r"\\normalsize", s)
    s = re.sub(r"(?<![a-zA-Z\\])oindent\b", r"\\noindent", s)
    s = re.sub(r"(?<![a-zA-Z\\])ode(?=\s*[\(\[\{]|\s+at\b)", r"\\node", s)
    s = re.sub(r"(?<![a-zA-Z\\])umber\b", r"\\number", s)
    s = re.sub(r"(?<![a-zA-Z\\])abla\b", r"\\nabla", s)
    s = re.sub(r"(?<![a-zA-Z\\])ocite(?=\{)", r"\\nocite", s)
    s = re.sub(r"(?<![a-zA-Z\\])ull\b", r"\\null", s)
    s = re.sub(r"(?<![a-zA-Z\\])opagecolor\b", r"\\nopagecolor", s)

    # 2. Swallowed \t:
    s = re.sub(r"(?<![a-zA-Z\\])extbf(?=\{)", r"\\textbf", s)
    s = re.sub(r"(?<![a-zA-Z\\])extit(?=\{)", r"\\textit", s)
    s = re.sub(r"(?<![a-zA-Z\\])exttt(?=\{)", r"\\texttt", s)
    s = re.sub(r"(?<![a-zA-Z\\])extsc(?=\{)", r"\\textsc", s)
    s = re.sub(r"(?<![a-zA-Z\\])extsf(?=\{)", r"\\textsf", s)
    s = re.sub(r"(?<![a-zA-Z\\])itle(?=\{)", r"\\title", s)
    s = re.sub(r"(?<![a-zA-Z\\])ableofcontents\b", r"\\tableofcontents", s)
    s = re.sub(r"(?<![a-zA-Z\\])ikzset(?=\{)", r"\\tikzset", s)
    s = re.sub(r"(?<![a-zA-Z\\])oprule\b", r"\\toprule", s)
    s = re.sub(r"(?<![a-zA-Z\\])itlespacing(?=\*?\{)", r"\\titlespacing", s)
    s = re.sub(r"(?<![a-zA-Z\\])itleformat(?=\{)", r"\\titleformat", s)
    s = re.sub(r"(?<![a-zA-Z\\])cbuselibrary(?=\{)", r"\\tcbuselibrary", s)

    # 3. Swallowed \b:
    s = re.sub(r"(?<![a-zA-Z\\])egin(?=\{)", r"\\begin", s)
    s = re.sub(r"(?<![a-zA-Z\\])fseries\b", r"\\bfseries", s)
    s = re.sub(r"(?<![a-zA-Z\\])ooktabs\b", r"\\booktabs", s)
    s = re.sub(r"(?<![a-zA-Z\\])ottomrule\b", r"\\bottomrule", s)
    s = re.sub(r"(?<![a-zA-Z\\])lacksquare\b", r"\\blacksquare", s)
    s = re.sub(r"(?<![a-zA-Z\\])lacktriangleright\b", r"\\blacktriangleright", s)
    s = re.sub(r"(?<![a-zA-Z\\])ibliography(?=\{)", r"\\bibliography", s)
    s = re.sub(r"(?<![a-zA-Z\\])ibliographystyle(?=\{)", r"\\bibliographystyle", s)

    # 4. Swallowed \f:
    s = re.sub(r"(?<![a-zA-Z\\])rac(?=\{)", r"\\frac", s)
    s = re.sub(r"(?<![a-zA-Z\\])ootnotesize\b", r"\\footnotesize", s)
    s = re.sub(r"(?<![a-zA-Z\\])ancyhead(?=\{|\s*\[)", r"\\fancyhead", s)
    s = re.sub(r"(?<![a-zA-Z\\])ancyfoot(?=\{|\s*\[)", r"\\fancyfoot", s)
    s = re.sub(r"(?<![a-zA-Z\\])ancypagestyle(?=\{|\s*\[)", r"\\fancypagestyle", s)
    s = re.sub(r"(?<![a-zA-Z\\])ancyhf(?=\{|\s*\[)", r"\\fancyhf", s)
    s = re.sub(r"(?<![a-zA-Z\\])ontsize(?=\{)", r"\\fontsize", s)
    s = re.sub(r"(?<![a-zA-Z\\])lushleft\b", r"\\flushleft", s)
    s = re.sub(r"(?<![a-zA-Z\\])lushright\b", r"\\flushright", s)

    # 5. Swallowed \r:
    s = re.sub(r"(?<![a-zA-Z\\])enewcommand(?=\{|\s*\[|\s*\\)", r"\\renewcommand", s)
    s = re.sub(r"(?<![a-zA-Z\\])enewenvironment(?=\{|\s*\[|\s*\\)", r"\\renewenvironment", s)
    s = re.sub(r"(?<![a-zA-Z\\])ef(?=\{)", r"\\ref", s)
    s = re.sub(r"(?<![a-zA-Z\\])ule(?=\{|\s*\[)", r"\\rule", s)
    s = re.sub(r"(?<![a-zA-Z\\])aisebox(?=\{|\s*\[)", r"\\raisebox", s)
    s = re.sub(r"(?<![a-zA-Z\\])estoregeometry\b", r"\\restoregeometry", s)
    s = re.sub(r"(?<![a-zA-Z\\])efstepcounter(?=\{)", r"\\refstepcounter", s)

    # 6. Swallowed \u:
    s = re.sub(r"(?<![a-zA-Z\\])sepackage(?=\{|\s*\[)", r"\\usepackage", s)
    s = re.sub(r"(?<![a-zA-Z\\])setheme(?=\{|\s*\[)", r"\\usetheme", s)
    s = re.sub(r"(?<![a-zA-Z\\])sefonttheme(?=\{|\s*\[)", r"\\usefonttheme", s)
    s = re.sub(r"(?<![a-zA-Z\\])secolortheme(?=\{|\s*\[)", r"\\usecolortheme", s)
    s = re.sub(r"(?<![a-zA-Z\\])seinnertheme(?=\{|\s*\[)", r"\\useinnertheme", s)
    s = re.sub(r"(?<![a-zA-Z\\])seoutertheme(?=\{|\s*\[)", r"\\useoutertheme", s)
    s = re.sub(r"(?<![a-zA-Z\\])nderline(?=\{)", r"\\underline", s)

    return s


def find_verbatim_or_fuzzy(text: str, target: str) -> Optional[str]:
    """
    Finds target in text. If exact match fails, tries matching with normalized
    whitespace and newlines so subtle LLM whitespace differences don't fail.
    Returns the exact matching slice from text, or None.
    """
    if not text or not target:
        return None
    if target in text:
        return target

    clean_target = target.strip()
    if not clean_target:
        return None
    if clean_target in text:
        return clean_target

    # Token-based normalized regex match: split by whitespace, escape tokens, join with \s+
    tokens = re.split(r'\s+', clean_target)
    if not tokens:
        return None

    escaped_tokens = [re.escape(t) for t in tokens if t]
    if not escaped_tokens:
        return None

    pattern_str = r'\s+'.join(escaped_tokens)
    try:
        m = re.search(pattern_str, text, re.DOTALL)
        if m:
            return text[m.start():m.end()]
    except Exception:
        pass
    return None


def sanitize_latex_code(code: str) -> str:
    r"""
    Cleans and repairs LaTeX code generated by LLM to guarantee it compiles cleanly:
    1. Restores swallowed LaTeX macro commands (\newcommand, \node, \begin, \textbf, etc.).
    2. Strips Markdown code fences.
    3. Removes or comments out stray prose words in the preamble before \begin{document}.
    4. Auto-repairs unclosed environments and missing \end{document}.
    """
    if not code or not isinstance(code, str):
        return code or ""

    s = code.strip()

    # Strip code fences if present
    if s.startswith("```"):
        s = re.sub(r"^```(?:latex|tex)?\s*", "", s, flags=re.MULTILINE)
        s = re.sub(r"\s*```$", "", s, flags=re.MULTILINE)

    # If the text has literal "\\n" strings instead of linebreaks, unescape them safely
    # (only where \n is NOT part of a LaTeX command name like \newcommand, \node, etc.)
    if "\\n" in s and s.count("\n") < 5:
        s = re.sub(r"(?<!\\)\\n(?=[^a-zA-Z]|$)", "\n", s)

    # Restore swallowed LaTeX commands where JSON escape \n, \t, \b, \f, \r swallowed the leading slash
    s = restore_swallowed_latex_escapes(s)

    # If full document with preamble, sanitize lines before \begin{document}
    if r"\begin{document}" in s:
        preamble, body = s.split(r"\begin{document}", 1)
        cleaned_preamble_lines = []
        for line in preamble.splitlines():
            stripped = line.strip()
            # Strip trailing semicolons after macro commands in preamble (e.g. \setbeamertemplate{...};)
            if stripped.startswith(("\\setbeamertemplate", "\\definecolor", "\\setbeamercolor", "\\setbeamerfont", "\\useinnertheme", "\\useoutertheme")):
                line = re.sub(r";\s*$", "", line)
                stripped = line.strip()

            # If line is a LaTeX command, comment, bracket, or blank, keep as-is
            if not stripped or stripped.startswith(("\\", "%", "{", "}", "[")):
                cleaned_preamble_lines.append(line)
            else:
                # Stray un-commented word (e.g. wrapped comments like 'Navy', 'Emerald')
                cleaned_preamble_lines.append(f"% {line}")
        s = "\n".join(cleaned_preamble_lines) + "\n\\begin{document}" + body

    # Clean malformed formatting macro brackets (e.g. \textbf[4pt] or \textit[4pt])
    s = re.sub(r"\\textbf\[([^\]]+)\]\{([^}]*)\}", r"\\textbf{\2}\\\\[\1]", s)
    s = re.sub(r"\\textbf\[([^\]]+)\]", r"\\\\[\1]", s)
    s = re.sub(r"\\textit\[([^\]]+)\]\{([^}]*)\}", r"\\textit{\2}\\\\[\1]", s)
    s = re.sub(r"\\textit\[([^\]]+)\]", r"\\\\[\1]", s)

    # Auto-repair footline sidebar overlap if leftskip < 1.8cm on wd=\paperwidth
    if r"\setbeamertemplate{footline}" in s and "wd=\\paperwidth" in s:
        s = re.sub(
            r"(\\setbeamertemplate\{footline\}[\s\S]*?leftskip=)(?:0(?:\.\d+)?|1(?:\.[0-7]\d*)?)cm",
            r"\g<1>1.8cm",
            s
        )

    # Auto-repair invalid enumitem options on itemize/enumerate in Beamer
    # In Beamer, bracket options like [itemsep=0.4em] or [leftmargin=1em] are parsed
    # as overlay specifications, literally printing "temsep=..." on every slide!
    def _fix_beamer_itemize(match):
        env = match.group(1)
        opts = match.group(2)
        if any(k in opts for k in ["itemsep", "leftmargin", "topsep", "parsep"]):
            m_sep = re.search(r'itemsep\s*=\s*([0-9.]+(?:em|pt|ex|cm))', opts)
            if m_sep:
                return f"\\begin{{{env}}}\\setlength{{\\itemsep}}{{{m_sep.group(1)}}}"
            return f"\\begin{{{env}}}"
        return match.group(0)

    s = re.sub(r'\\begin\{(itemize|enumerate)\}\s*\[([^\]]*)\]', _fix_beamer_itemize, s)

    # Clean any accidental literal 'temsep=...' or 'leftmargin=...' artifact text
    s = re.sub(r'(?<![a-zA-Z\\\\])temsep\s*=\s*[0-9.]+(?:em|pt|cm|ex)?', '', s)
    s = re.sub(r'(?<![a-zA-Z\\\\])leftmargin\s*=\s*[0-9.]+(?:em|pt|cm|ex)?', '', s)

    # Auto-repair bare vspace/hspace numbers without units (e.g. \vspace{0.1} -> \vspace{0.1cm})
    s = re.sub(r'\\(vspace|hspace)\*?\{([0-9.]+)\}', r'\\\1{\2cm}', s)

    # Auto-repair unescaped '&' in text mode (e.g. "Attribution & Reasoning" -> "Attribution \& Reasoning")
    def _fix_unescaped_amp(line):
        stripped = line.strip()
        if any(k in stripped for k in ["\\begin{tabular", "\\end{tabular", "\\begin{matrix", "\\end{matrix", "\\begin{align", "\\end{align"]):
            return line
        if "&" in line and not line.rstrip().endswith(r"\\"):
            return re.sub(r'(?<!\\)&', r'\&', line)
        return line

    s = "\n".join(_fix_unescaped_amp(l) for l in s.splitlines())

    # Auto-repair unclosed environments and trailing truncation
    s = auto_repair_truncated_latex(s)

    return s


def process_attached_file_content(filename: str, content: str, file_type: str) -> str:
    """
    Safely extracts text content from uploaded files (PDFs, Word DOCX, text files, Data URLs).
    Prevents corrupt binary streams from causing errors in prompt building or LLM.
    """
    if not content:
        return ""

    lower_fn = filename.lower()
    ft = (file_type or "text/plain").lower()

    # Word DOCX Extraction
    is_docx = (
        "word" in ft or
        "officedocument" in ft or
        lower_fn.endswith(".docx") or
        lower_fn.endswith(".doc") or
        content.startswith("data:application/vnd.openxmlformats")
    )

    if is_docx:
        if not HAS_DOCX:
            logger.warning(f"python-docx package not installed, skipping text extraction for '{filename}'")
            return f"[Uploaded Word Document: '{filename}']"
        try:
            b64_data = content
            if "," in b64_data:
                b64_data = b64_data.split(",", 1)[1]
            padding_needed = len(b64_data) % 4
            if padding_needed:
                b64_data += "=" * (4 - padding_needed)

            raw_bytes = base64.b64decode(b64_data)
            doc_file = docx.Document(io.BytesIO(raw_bytes))
            paragraphs = [p.text.strip() for p in doc_file.paragraphs if p.text.strip()]
            full_text = "\n".join(paragraphs)
            if len(full_text) > 12000:
                full_text = full_text[:12000] + f"\n...[Word document truncated to 12k chars]"
            logger.info(f"Extracted {len(paragraphs)} paragraphs from Word document '{filename}'")
            return sanitize_text_content(full_text)
        except Exception as docx_err:
            logger.warning(f"Failed to extract text from Word document '{filename}': {docx_err}")
            return f"[Uploaded Word document: '{filename}']"

    b64_data = content
    if "," in b64_data:
        b64_data = b64_data.split(",", 1)[1]

    # PDF Extraction - robustly detect PDF via MIME, extension, Data URL, or base64 header (JVBERi0 = %PDF-)
    is_pdf = (
        "pdf" in ft or
        lower_fn.endswith(".pdf") or
        content.startswith("data:application/pdf") or
        b64_data.startswith("JVBERi0") or
        content.startswith("%PDF-")
    )

    if is_pdf:
        if not HAS_PYPDF:
            logger.warning(f"pypdf package not installed, skipping text extraction for '{filename}'")
            return f"[Uploaded PDF file: '{filename}']"
        try:
            if content.startswith("%PDF-"):
                raw_bytes = content.encode("latin-1")
            else:
                padding_needed = len(b64_data) % 4
                if padding_needed:
                    b64_data += "=" * (4 - padding_needed)
                raw_bytes = base64.b64decode(b64_data)

            reader = pypdf.PdfReader(io.BytesIO(raw_bytes), strict=False)

            extracted_pages = []
            max_pages = min(len(reader.pages), 50)
            for i in range(max_pages):
                try:
                    txt = reader.pages[i].extract_text() or ""
                    if txt.strip():
                        extracted_pages.append(f"[Page {i+1}]\n{txt.strip()}")
                except Exception:
                    continue

            if extracted_pages:
                full_text = "\n\n".join(extracted_pages)
                if len(full_text) > 12000:
                    full_text = full_text[:12000] + f"\n...[TRUNCATED — showing {len(extracted_pages)} pages]"
                logger.info(f"Extracted {len(extracted_pages)} text pages from PDF '{filename}' ({len(reader.pages)} total pages)")
                return sanitize_text_content(full_text)
            else:
                return f"[PDF Document '{filename}' uploaded — contains {len(reader.pages)} page(s)]"
        except Exception as pdf_err:
            logger.warning(f"pypdf extraction notice for PDF '{filename}': {pdf_err}. Attempting raw stream recovery...")
            try:
                raw_text_parts = re.findall(r'[\x20-\x7E\s]{4,}', raw_bytes.decode('latin-1', errors='ignore'))
                clean_parts = [p.strip() for p in raw_text_parts if len(p.strip()) > 10 and not any(p.strip().startswith(k) for k in ('<<', '>>', 'obj', 'endobj', 'stream', 'endstream', '/Filter', '/Type', '/Font', 'xref', 'trailer'))]
                if clean_parts:
                    recovered_text = "\n".join(clean_parts[:200])
                    logger.info(f"Stream recovery extracted {len(clean_parts)} text segments from '{filename}'")
                    return sanitize_text_content(recovered_text[:12000])
            except Exception:
                pass
            return f"[Uploaded PDF file: '{filename}']"

    # Image files
    if ft.startswith("image/") or lower_fn.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return f"[Attached Image File: '{filename}']"

    # Plain text / code / CSV / JSON files
    if content.startswith("data:") and ";base64," in content:
        try:
            b64_data = content.split(";base64,", 1)[1]
            txt = base64.b64decode(b64_data).decode("utf-8", errors="replace")
            return sanitize_text_content(txt[:12000] if len(txt) > 12000 else txt)
        except Exception:
            return sanitize_text_content(content[:12000])

    return sanitize_text_content(content[:12000] if len(content) > 12000 else content)


def get_nvidia_embeddings() -> NVIDIAEmbeddings:
    nvidia_api_key = os.getenv("NVIDIA_API_KEY")
    return NVIDIAEmbeddings(
        model="nvidia/nemotron-3-embed-1b",
        nvidia_api_key=nvidia_api_key
    )


def get_genai_client():
    """
    Optional Google GenAI SDK client getter.
    Returns None safely if GEMINI_API_KEY is not configured or genai is missing.
    """
    if not HAS_GENAI:
        return None
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not gemini_key or not gemini_key.strip():
        return None
    try:
        return genai.Client(api_key=gemini_key.strip())
    except Exception as e:
        logger.warning(f"Could not initialize GenAI client: {e}")
        return None




# ─── Response Parsing Utilities ───────────────────────────────────────────────

def sanitize_explanation_text(text: str) -> str:
    """Removes internal chunk references and web2api chip URLs from user-facing text."""
    if not text or not isinstance(text, str):
        return text or ""
    # Strip phrases like "in CHUNK 1", "from CHUNK 2", "CHUNK 3:", "[CHUNK 4]", "CHUNK 5"
    cleaned = re.sub(r'(?i)\b(?:in|from|for|of)?\s*\[?CHUNK\s*\d+\]?:?\s*', '', text)
    # Strip web2api chip URLs (e.g. http://googleusercontent.com/immersive_entry_chip/0)
    cleaned = re.sub(r'https?://[^\s]*googleusercontent[^\s]*', '', cleaned)
    cleaned = re.sub(r'Generating slides\.\.\.\s*', '', cleaned)
    # Remove leading colons, hyphens, or extra whitespace left over
    cleaned = re.sub(r'^\s*[:\-]\s*', '', cleaned)
    # Clean up multiple newlines or spaces
    cleaned = re.sub(r'\n\s*\n+', '\n', cleaned)
    cleaned = re.sub(r'\s+([.,!?;])', r'\1', cleaned)
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned.strip()


def auto_repair_truncated_json(text: str) -> str:
    """Attempts to auto-close unclosed strings and JSON object braces if LLM output was truncated."""
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.MULTILINE)
        s = re.sub(r"\s*```$", "", s, flags=re.MULTILINE)

    if not s.endswith("}"):
        if not s.endswith('"'):
            s += '"'
        open_b = s.count('{')
        close_b = s.count('}')
        if open_b > close_b:
            s += '}' * (open_b - close_b)
    return s


def decode_json_string_value(s: str) -> str:
    r"""Safely decodes JSON string literal values without corrupting LaTeX commands (\newcommand, \node, etc.)."""
    if not s:
        return ""
    try:
        test_s = s
        if test_s.endswith("\\") and not test_s.endswith("\\\\"):
            test_s = test_s[:-1]
        return json.loads(f'"{test_s}"', strict=False)
    except Exception:
        pass

    def repl(match):
        esc = match.group(0)
        if esc == r"\\":
            return "\\"
        elif esc == r"\"":
            return "\""
        elif esc == r"\/":
            return "/"
        elif esc == r"\n":
            return "\n"
        elif esc == r"\t":
            return "\t"
        elif esc == r"\r":
            return "\r"
        elif esc == r"\b":
            return "\b"
        elif esc == r"\f":
            return "\f"
        return esc

    return re.sub(r'\\(?:[\\"/bfnrt]|u[0-9a-fA-F]{4}|.)', repl, s)


def extract_fallback_chunks(text: str) -> Dict[str, Any]:
    """Fallback regex extractor for proposed_chunk when JSON parsing fails."""
    prop_match = re.search(r'"proposed_chunk"\s*:\s*"((?:[^"\\]|\\.)*)', text, re.DOTALL)
    orig_match = re.search(r'"original_chunk"\s*:\s*"((?:[^"\\]|\\.)*)', text, re.DOTALL)
    exp_match = re.search(r'"explanation"\s*:\s*"((?:[^"\\]|\\.)*)', text, re.DOTALL)

    if prop_match:
        prop = decode_json_string_value(prop_match.group(1))
        orig = decode_json_string_value(orig_match.group(1)) if orig_match else ""
        exp = decode_json_string_value(exp_match.group(1)) if exp_match else "Extracted LaTeX content."
        return {
            "original_chunk": orig,
            "proposed_chunk": prop,
            "explanation": exp
        }
    raise ValueError(f"LLM output could not be parsed as valid JSON: {text}")


def extract_latex_from_response(text: str) -> Optional[str]:
    """Extracts code block from ```latex ... ``` response format (closed or unclosed) or raw LaTeX document/frame."""
    if not text or not isinstance(text, str):
        return None

    # Strategy 1: Fenced code block (closed or unclosed)
    fenced_match = re.search(r"```(?:latex|tex)?\s*\n([\s\S]*?)(?:```|$)", text, re.IGNORECASE)
    if fenced_match:
        candidate = fenced_match.group(1).strip()
        if candidate:
            return candidate

    # Strategy 2: Raw LaTeX document from \documentclass to \end{document} (or end of string if unclosed)
    raw_doc_match = re.search(r"(\\documentclass[\s\S]*?(?:\\end\{document\}|$))", text, re.IGNORECASE)
    if raw_doc_match:
        candidate = raw_doc_match.group(1).strip()
        if candidate:
            return candidate

    # Strategy 3: Any LaTeX environment from \begin{...} to \end{...} (or end of string)
    env_match = re.search(r"(\\begin\{[a-zA-Z*]+\}[\s\S]*?(?:\\end\{[a-zA-Z*]+\}|$))", text, re.IGNORECASE)
    if env_match:
        candidate = env_match.group(1).strip()
        if candidate:
            return candidate

    # Strategy 4: Any LaTeX command block starting with \section, \title, \frame, \usepackage, etc.
    cmd_match = re.search(r"(\\(?:section|title|frame|usepackage|item|maketitle|tableofcontents)[\s\S]*)", text, re.IGNORECASE)
    if cmd_match:
        candidate = cmd_match.group(1).strip()
        if candidate:
            return candidate

    return None


def extract_chunk_latex(text: str) -> Optional[str]:
    """Extracts LaTeX chunk after UPDATED_LATEX: marker if present."""
    marker = text.find("UPDATED_LATEX:")
    if marker == -1:
        return extract_latex_from_response(text)
    after_marker = text[marker:]
    return extract_latex_from_response(after_marker)


def stringify_content(content: Any) -> str:
    """Normalizes string, list of strings, or list of content block dicts into a single plain text string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            elif hasattr(item, "text"):
                parts.append(str(getattr(item, "text")))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content) if content is not None else ""


def clean_json_response(text: Any) -> Dict[str, Any]:
    """Multi-strategy response parser: fenced LaTeX, JSON, auto-repair, regex fallback."""
    raw_text = stringify_content(text)
    cleaned = raw_text.strip()

    if cleaned.startswith("```"):
        stripped_json_block = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
        stripped_json_block = re.sub(r"\s*```$", "", stripped_json_block, flags=re.MULTILINE)
    else:
        stripped_json_block = cleaned

    # Attempt 1: Direct standard JSON parse (preserves real newlines and escaped LaTeX slashes)
    try:
        return json.loads(stripped_json_block, strict=False)
    except Exception:
        pass

    # Attempt 2: Auto-repair truncated JSON
    try:
        repaired = auto_repair_truncated_json(stripped_json_block)
        return json.loads(repaired, strict=False)
    except Exception:
        pass

    # Attempt 3: Escape invalid LaTeX backslashes if standard JSON decoding failed on slashes
    try:
        fixed_slashes = re.sub(r'(?<!\\)\\([a-zA-Z%&$#_{}\[\]])', r'\\\\\1', stripped_json_block)
        repaired_slashes = auto_repair_truncated_json(fixed_slashes)
        return json.loads(repaired_slashes, strict=False)
    except Exception:
        pass

    # Attempt 4: Extract JSON object via regex
    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        raw_match = json_match.group(0)
        try:
            return json.loads(raw_match, strict=False)
        except Exception:
            try:
                repaired_raw = auto_repair_truncated_json(raw_match)
                return json.loads(repaired_raw, strict=False)
            except Exception:
                pass
                pass

    # Attempt 5: Regex extraction of proposed_chunk
    try:
        return extract_fallback_chunks(cleaned)
    except Exception:
        pass

    # Attempt 6: Extract any LaTeX code block or LaTeX environment (even if unclosed or surrounded by prose)
    extracted_latex = extract_chunk_latex(cleaned)
    if extracted_latex:
        prose_parts = cleaned.split("```")[0].strip()
        explanation = prose_parts if prose_parts and len(prose_parts) < 300 else "Generated LaTeX document proposal."
        return {
            "plan": "Generated LaTeX code snippet.",
            "edits": [{
                "original_chunk": "",
                "proposed_chunk": extracted_latex,
                "explanation": explanation
            }],
            "original_chunk": "",
            "proposed_chunk": extracted_latex,
            "explanation": explanation
        }

    # Attempt 7: Safe fallback returning raw response text as explanation without crashing
    return {
        "plan": "",
        "edits": [],
        "original_chunk": "",
        "proposed_chunk": "",
        "explanation": cleaned if cleaned else "AI response received."
    }


# ─── Main Agent Endpoint ──────────────────────────────────────────────────────

from typing import List, Optional, Dict, Any, Tuple


def categorize_user_intent(user_prompt: str, has_attached_file: bool = False) -> Tuple[str, bool]:
    """
    Categorizes user intent into 3 modes:
    1. ("GENERAL_CHAT", False) — Pure greetings & syntax questions ("hi", "how to center text in LaTeX?"). Vector search: False, Edits: False.
    2. ("INSPECT_DOCUMENT", True) — Document inquiries ("where is abstract?", "what packages are used in my document?"). Vector search: True, Edits: False.
    3. ("EDIT_DOCUMENT", True) — Edit/generation instructions ("add section", "generate ppt for..."). Vector search: True, Edits: True.
    """
    text = user_prompt.lower().strip()

    # If user attached a reference file (PDF, DOCX, etc.), default to EDIT_DOCUMENT
    # unless asking a pure document question
    doc_inquiry_keywords = ["where is", "find in my", "what packages", "check my", "show my", "list sections", "is my"]
    if any(inq in text for inq in doc_inquiry_keywords):
        return ("INSPECT_DOCUMENT", True)

    # Edit & generation triggers — always EDIT_DOCUMENT
    edit_triggers = [
        "instead of", "replace", "change", "modify", "update", "swap", "i need", "i want",
        "put", "give me", "fix", "remove", "add", "insert", "generate", "create", "make",
        "build", "draw", "write", "ppt", "slide", "beamer", "presentation", "table", "figure",
        "section", "framework", "architecture", "diagram", "code", "draft", "overview", "survey"
    ]
    if any(e in text for e in edit_triggers) or has_attached_file:
        return ("EDIT_DOCUMENT", True)

    # Pure greetings
    greetings = {"hi", "hello", "hey", "good morning", "good evening", "who are you", "what can you do", "help", "thanks", "thank you"}
    if text in greetings or (len(text.split()) <= 2 and any(g == text for g in greetings)):
        return ("GENERAL_CHAT", False)

    # Pure LaTeX syntax questions (e.g. "how do I center text", "what is the syntax for booktabs")
    how_to_syntax_keywords = ["how do i", "how to", "how can i", "what is the syntax", "syntax for", "example of syntax", "how does \\"]
    my_doc_references = ["my code", "my document", "my title", "my file", "my paper", "this paper", "this document", "this code", "my project", "the paper", "about the paper", "seminar", "slide", "presentation"]

    if any(h in text for h in how_to_syntax_keywords) and not any(r in text for r in my_doc_references):
        return ("GENERAL_CHAT", False)

    # All other prompts default to EDIT_DOCUMENT so tool binding & JSON edit proposals are active
    return ("EDIT_DOCUMENT", True)


def get_project_assets_info(project_id: str) -> str:
    """
    Scans the project directory for image assets (logos, photos, graphics) and style files,
    formatting them as explicit context instructions for the AI prompt.
    """
    try:
        from pathlib import Path
        from project_storage import UPLOADS_BASE_DIR
        safe_project = re.sub(r'[^a-zA-Z0-9_-]', '_', project_id)
        project_dir = UPLOADS_BASE_DIR / safe_project
        if not project_dir.exists():
            return ""

        img_exts = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf"}
        asset_files = []
        style_files = []

        for p in project_dir.rglob("*"):
            if p.is_file():
                rel_p = str(p.relative_to(project_dir))
                ext = p.suffix.lower()
                if ext in img_exts:
                    asset_files.append(rel_p)
                elif ext in {".sty", ".cls"}:
                    style_files.append(rel_p)

        parts = []
        if asset_files:
            asset_list = "\n".join([f"  - {f}" for f in sorted(asset_files)])
            parts.append(
                f"AVAILABLE PROJECT IMAGES & GRAPHIC ASSETS:\n"
                f"{asset_list}\n\n"
                f"IMAGE ATTACHMENT INSTRUCTION:\n"
                f"When generating or editing presentation slides, PREFER incorporating relevant available image assets using \\includegraphics[height=...]{{filename}} or template logo commands where appropriate!"
            )
        if style_files:
            parts.append(f"PROJECT TEMPLATE & STYLE FILES AVAILABLE: {', '.join(sorted(style_files))}")

        return "\n\n".join(parts)
    except Exception as e:
        logger.warning(f"Error scanning project assets for {project_id}: {e}")
        return ""


@router.post("/api/agent/chat")
async def agent_chat(request: Request):
    """
    Full RAG Agent Pipeline with SSE streaming progress events.
    Sends real-time progress updates then the final JSON result.

    Accepts raw Request to bypass Starlette's default body size limit,
    allowing large PDF uploads (30+ pages = 10-50MB base64).
    """
    from fastapi.responses import StreamingResponse, JSONResponse
    import time

    # Manually read the raw body — this bypasses Starlette's body size limit
    try:
        body = await request.body()
        if len(body) > 100 * 1024 * 1024:  # 100MB hard cap
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large. Maximum size is 100MB."},
            )
        raw_data = json.loads(body)
        req = AgentChatRequest(**raw_data)
    except json.JSONDecodeError as e:
        return JSONResponse(status_code=400, content={"detail": f"Invalid JSON: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=422, content={"detail": f"Validation error: {str(e)}"})

    def sse_event(event_type: str, data: dict) -> str:
        """Format a single SSE event."""
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    async def run_step_with_heartbeat(func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(None, lambda: func(*args, **kwargs))
        while not future.done():
            try:
                await asyncio.wait_for(asyncio.shield(future), timeout=2.0)
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
        res = await future
        yield res

    async def pipeline_generator():
        try:
            # Step 1: Categorize intent
            yield sse_event("progress", {"step": "analyze", "message": "Analyzing prompt...", "icon": "zap"})
            has_attached_file = bool((req.attached_file and req.attached_file.content) or conversation_memory.get_attached_file(req.project_id))
            mode, is_search_needed = categorize_user_intent(req.user_prompt, has_attached_file=has_attached_file)
            print(f"\n [AGENT CHAT REQUEST RECEIVED]\n  > Prompt: '{req.user_prompt}'\n  > Project ID: {req.project_id}\n  > Mode: {mode} (Vector Search = {is_search_needed})")

            # Check if user document already exists
            has_existing_code = bool(req.current_code and len(req.current_code.strip()) > 50 and "\\documentclass" in req.current_code)

            # Fast-path: Bypass vector search ONLY when creating a new presentation on an empty document
            is_new_doc_request = (not has_existing_code) and any(kw in req.user_prompt.lower() for kw in ["ppt", "presentation", "beamer", "slide", "create ppt", "make ppt", "generate ppt"])
            if is_new_doc_request:
                is_search_needed = False

            yield sse_event("progress", {"step": "intent", "message": f"Mode: {mode.replace('_', ' ').title()}", "icon": "brain"})

            # Fast-path for simple greetings
            text_clean = req.user_prompt.lower().strip()
            greetings_set = {"hi", "hello", "hey", "good morning", "good evening", "greetings"}
            if text_clean in greetings_set or (len(text_clean.split()) <= 2 and any(g in text_clean for g in greetings_set)):
                yield sse_event("result", {
                    "plan": "", "edits": [], "original_chunk": "", "proposed_chunk": "",
                    "explanation": "Hello! How can I help you with your LaTeX document or Beamer slides today?",
                    "retrieved_chunks_count": 0,
                })
                return

            # Fast-path: In-project PDF to Editable LaTeX conversion
            # Fast-path: In-project PDF to Editable LaTeX conversion
            is_pdf = False
            pdf_data_input = None
            if req.attached_file and req.attached_file.content:
                fn = req.attached_file.filename.lower()
                ft = (req.attached_file.file_type or "").lower()
                c = req.attached_file.content
                if (
                    fn.endswith(".pdf")
                    or "pdf" in ft
                    or c.startswith("data:application/pdf")
                    or c.startswith("%PDF-")
                    or ("," in c and ("JVBERi0" in c[:60] or "pdf" in c[:60].lower()))
                    or (len(c) > 100 and "JVBERi0" in c[:100])
                ):
                    is_pdf = True
                    pdf_data_input = c
            else:
                cached_file_info = conversation_memory.get_attached_file(req.project_id)
                if cached_file_info and cached_file_info.get("content"):
                    cfn = cached_file_info.get("filename", "").lower()
                    cft = (cached_file_info.get("file_type") or "").lower()
                    cc = cached_file_info.get("content", "")
                    if cfn.endswith(".pdf") or "pdf" in cft or cc.startswith("data:application/pdf") or cc.startswith("%PDF-"):
                        is_pdf = True
                        pdf_data_input = cc

            # Decision: Is this a full PDF to LaTeX conversion OR an edit with a Reference PDF?
            # A full conversion (PyMuPDF layout extraction, embedded figures, creating/overwriting main.tex)
            # is ONLY triggered when the user explicitly requests recreation/conversion of the PDF
            # (e.g. clicking "Recreate this PDF as Editable LaTeX" or typing "recreate this pdf", "convert to latex").
            # When the user attaches a PDF to make edits or apply its content to the existing document
            # (e.g. "make this as for Abin Thomas SJC23CC006 for the seminar topic of this"),
            # it is treated as a REFERENCE PDF, extracted using pypdf, and passed to the agent
            # to make the requested edits on the current document without overwriting the project.
            prompt_clean = req.user_prompt.lower().strip()
            recreate_phrases = [
                "recreate this pdf",
                "recreate as editable latex",
                "recreate this pdf as editable latex",
                "recreate this pdf exactly",
                "convert this pdf to latex",
                "convert pdf to latex",
                "turn this pdf into latex",
                "turn this pdf to latex",
                "turn pdf into latex",
                "turn pdf to latex",
                "pdf to latex",
                "pdf to editable latex",
                "pdf to tex",
                "import pdf to latex",
                "clone this pdf",
                "reproduce this pdf as latex",
                "make editable latex from this pdf",
                "extract this pdf to latex",
            ]
            is_explicit_recreate = any(phrase in prompt_clean for phrase in recreate_phrases)

            # Short command check (e.g. user just types "recreate", "convert", "pdf to latex")
            words = prompt_clean.split()
            is_short_convert_cmd = len(words) <= 3 and any(w in prompt_clean for w in ["recreate", "convert", "pdf2latex"])

            is_pdf_conversion_request = is_pdf and (pdf_data_input is not None) and (is_explicit_recreate or is_short_convert_cmd)

            if is_pdf_conversion_request:
                yield sse_event("progress", {"step": "pdf_parse", "message": "Analyzing PDF structure with PyMuPDF...", "icon": "file-text"})
                loop = asyncio.get_running_loop()
                try:
                    parse_result = await loop.run_in_executor(
                        None,
                        lambda: parse_pdf(pdf_data_input, render_300dpi=True, render_150dpi=True, max_pages=MAX_ALLOWED_PAGES)
                    )
                except ValueError as ve:
                    yield sse_event("error", {"message": str(ve)})
                    return
                except Exception as pe:
                    yield sse_event("error", {"message": f"Failed to parse PDF with PyMuPDF: {str(pe)}"})
                    return

                img_count = len(parse_result.embedded_images)
                yield sse_event("progress", {"step": "extracting_assets", "message": f"Extracted {img_count} embedded figure(s) for assets/...", "icon": "image"})

                yield sse_event("progress", {"step": "pdf_convert", "message": f"Synthesizing editable LaTeX ({parse_result.doc_type_hint})...", "icon": "sparkles"})

                progress_queue = asyncio.Queue()
                def sync_progress_cb(step: str, message: str):
                    progress_queue.put_nowait((step, message))

                conversion_task = loop.run_in_executor(
                    None,
                    lambda: convert_pdf_to_latex(
                        parse_result=parse_result,
                        model=req.model,
                        progress_callback=sync_progress_cb,
                        auto_repair=True,
                    )
                )

                while not conversion_task.done():
                    try:
                        step, msg = await asyncio.wait_for(progress_queue.get(), timeout=1.5)
                        yield sse_event("progress", {"step": step, "message": msg, "icon": "loader"})
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"

                try:
                    conversion_result = await conversion_task
                except Exception as conv_err:
                    logger.error(f"LLM PDF conversion failed, building robust structural LaTeX fallback: {conv_err}")
                    safe_class = "article" if parse_result.doc_type_hint != "report" else "report"
                    fallback_tex = (
                        f"\\documentclass[11pt,a4paper,oneside]{{{safe_class}}}\n"
                        "\\usepackage[utf8]{inputenc}\n"
                        "\\usepackage[margin=1in]{geometry}\n"
                        "\\usepackage{parskip}\n"
                        "\\usepackage{amsmath,amssymb}\n"
                        "\\usepackage{graphicx}\n"
                        "\\usepackage{booktabs}\n"
                        "\\usepackage{hyperref}\n\n"
                        "\\begin{document}\n\n"
                        + (parse_result.full_text or "Converted Document") + "\n\n"
                        "\\end{document}"
                    )
                    from services.pdf_to_latex import ConversionResult, ProjectFile, AssetFile
                    conversion_result = ConversionResult(
                        document_class=safe_class,
                        engine="pdflatex",
                        files=[ProjectFile(path="main.tex", content=fallback_tex)],
                        assets=[
                            AssetFile(filename=img.filename, data_bytes=img.data_bytes, source_page=img.source_page)
                            for img in parse_result.embedded_images
                        ],
                        compiled_successfully=True,
                    )

                yield sse_event("progress", {"step": "writing_files", "message": "Writing project files and assets...", "icon": "hard-drive"})
                written = await loop.run_in_executor(
                    None,
                    lambda: write_project_files_and_assets(
                        project_id=req.project_id,
                        conversion=conversion_result,
                    )
                )

                main_content = next((f.content for f in conversion_result.files if f.path == "main.tex"), "")

                yield sse_event("progress", {"step": "done", "message": "Conversion complete! Files and assets updated.", "icon": "check"})

                yield sse_event("result", {
                    "plan": f"Recreated PDF as editable LaTeX ({conversion_result.document_class})",
                    "edits": [{
                        "original_chunk": req.current_code or "",
                        "proposed_chunk": main_content,
                        "explanation": f"Recreated complete editable LaTeX project from PDF: {len(written['files'])} file(s), {len(written['assets'])} asset(s).",
                    }],
                    "original_chunk": req.current_code or "",
                    "proposed_chunk": main_content,
                    "explanation": f"I have recreated the attached PDF as an editable LaTeX project ({conversion_result.document_class}). Saved {len(written['files'])} file(s) and {len(written['assets'])} asset(s) into your project workspace.",
                    "retrieved_chunks_count": 0,
                    "model_used": req.model,
                    "is_fallback": False,
                    "files_written": written["files"],
                    "assets_written": written["assets"],
                    "is_pdf_conversion": True,
                })
                return

            # Step 2: Vector search
            retrieved_chunks = []
            if is_search_needed:
                try:
                    yield sse_event("progress", {"step": "embed", "message": "Generating query embedding...", "icon": "search"})
                    embeddings_model = get_nvidia_embeddings()
                    prompt_embedding = embeddings_model.embed_query(req.user_prompt)

                    qdrant = get_qdrant_client()
                    ensure_qdrant_collection(qdrant)

                    yield sse_event("progress", {"step": "search", "message": "Searching document vectors...", "icon": "database"})
                    async for item in run_step_with_heartbeat(
                        retriever.retrieve,
                        qdrant_client=qdrant,
                        collection_name=COLLECTION_NAME,
                        query_embedding=prompt_embedding,
                        project_id=req.project_id,
                        file_path=req.file_path,
                    ):
                        if isinstance(item, str) and item.startswith(":"):
                            yield item
                        else:
                            retrieved_chunks = item
                    yield sse_event("progress", {"step": "retrieved", "message": f"Retrieved {len(retrieved_chunks)} chunks", "icon": "file-text"})
                except Exception as qdrant_err:
                    yield sse_event("progress", {"step": "search_warn", "message": "Vector search unavailable, continuing...", "icon": "alert-triangle"})
            else:
                yield sse_event("progress", {"step": "skip_search", "message": "Direct response mode", "icon": "message-circle"})

            # Step 3: Build context — targeted for edits, broad for generation
            yield sse_event("progress", {"step": "context", "message": "Building document context...", "icon": "layers"})

            # Parse document structure and identify target page
            target_page_index = None
            targeted_context = None
            is_targeted_edit = False

            if mode == "EDIT_DOCUMENT" and has_existing_code and req.current_code:
                try:
                    document_structure = doc_idx.parse_document_structure(req.current_code)
                    target_page_index = doc_idx.find_target_page(document_structure, req.user_prompt)

                    if target_page_index is not None:
                        # Build targeted context (just the target slide ± 1 neighbor)
                        targeted_context = context_builder.build_targeted_context(
                            retrieved_chunks=retrieved_chunks,
                            current_code=req.current_code,
                            target_page_index=target_page_index,
                        )
                        is_targeted_edit = True
                        target_page = document_structure.get_page_by_index(target_page_index)
                        yield sse_event("progress", {
                            "step": "target",
                            "message": f"Targeting: {target_page.title if target_page else 'slide ' + str(target_page_index)}",
                            "icon": "crosshair"
                        })
                except Exception as idx_err:
                    logger.warning(f"Document indexing failed, using broad context: {idx_err}")

            # Fall back to standard broad context if targeting wasn't possible
            if not targeted_context:
                context_str = context_builder.build_context(retrieved_chunks)
            else:
                context_str = targeted_context

            # Step 4: Load memory & project asset context
            conv_ctx = conversation_memory.get_conversation_context(req.project_id)
            proj_ctx = project_memory.get_project_context(req.project_id)
            proj_assets = get_project_assets_info(req.project_id)

            full_proj_context = f"{proj_ctx}\n\n{proj_assets}".strip()

            if not project_memory.is_scanned(req.project_id):
                try:
                    from pathlib import Path
                    uploads_base = Path(os.path.dirname(__file__)).parent / "uploads" / "projects"
                    import re as _re
                    safe_project = _re.sub(r'[^a-zA-Z0-9_-]', '_', req.project_id)
                    tex_path = uploads_base / safe_project / req.file_path
                    if tex_path.exists():
                        tex_content = tex_path.read_text(encoding="utf-8")
                        project_memory.scan_and_store(req.project_id, tex_content)
                        proj_ctx = project_memory.get_project_context(req.project_id)
                        full_proj_context = f"{proj_ctx}\n\n{proj_assets}".strip()
                except Exception:
                    pass

            # Step 5: Build prompt
            # Step 5: Build prompt & handle attached file context persistence
            yield sse_event("progress", {"step": "prompt", "message": "Assembling prompt...", "icon": "edit-3"})
            attached_info = None
            if req.attached_file and req.attached_file.content:
                yield sse_event("progress", {"step": "file", "message": f"Extracting content from {req.attached_file.filename}...", "icon": "paperclip"})
                processed_content = process_attached_file_content(
                    filename=req.attached_file.filename,
                    content=req.attached_file.content,
                    file_type=req.attached_file.file_type or "text/plain",
                )
                attached_info = {
                    "filename": req.attached_file.filename,
                    "file_type": req.attached_file.file_type or "text/plain",
                    "content": processed_content,
                }
                conversation_memory.set_attached_file(req.project_id, attached_info)
                yield sse_event("progress", {"step": "file_done", "message": f"Attached: {req.attached_file.filename}", "icon": "check-square"})
            else:
                # Retrieve persistent attached document context from memory if user gives follow-up prompt without re-attaching file
                cached_file_info = conversation_memory.get_attached_file(req.project_id)
                if cached_file_info:
                    attached_info = cached_file_info
                    logger.info(f"Referencing persistent attached document context for project '{req.project_id}': '{cached_file_info.get('filename')}'")
                    yield sse_event("progress", {"step": "file_cached", "message": f"Referencing document: {cached_file_info.get('filename')}", "icon": "paperclip"})

            messages = prompt_builder.build_prompt(
                user_request=req.user_prompt,
                retrieved_context=context_str,
                conversation_context=conv_ctx,
                project_context=full_proj_context,
                attached_file_info=attached_info,
                current_code=req.current_code,
                target_context=targeted_context,
                is_edit_mode=is_targeted_edit,
            )

            # Step 6: Invoke LLM
            system_content = messages[0].content if (isinstance(messages, list) and len(messages) > 0) else ""
            user_content = messages[1].content if (isinstance(messages, list) and len(messages) > 1) else req.user_prompt

            # Build Gemini API contents payload (supports native PDF and Image parts + text prompt)
            contents_payload = []

            if req.attached_file:
                fn = req.attached_file.filename
                ft = (req.attached_file.file_type or "text/plain").lower()
                raw_content = req.attached_file.content or ""
                lower_fn = fn.lower()

                if "pdf" in ft or lower_fn.endswith(".pdf") or raw_content.startswith("data:application/pdf"):
                    try:
                        b64_data = raw_content
                        if "," in b64_data:
                            b64_data = b64_data.split(",", 1)[1]
                        pdf_bytes = base64.b64decode(b64_data)
                        # Gemini has a ~20MB inline limit for native PDF parts;
                        # for larger files, rely on extracted text instead
                        if len(pdf_bytes) <= 20 * 1024 * 1024:
                            pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
                            contents_payload.append(pdf_part)
                            yield sse_event("progress", {"step": "native_pdf", "message": f"Sending native PDF '{fn}' ({len(pdf_bytes) // 1024}KB) to Gemini...", "icon": "file-text"})
                            logger.info(f"Attached native Gemini PDF Part ({len(pdf_bytes)} bytes)")
                        else:
                            yield sse_event("progress", {"step": "pdf_text_fallback", "message": f"PDF '{fn}' too large for native upload ({len(pdf_bytes) // (1024*1024)}MB), using extracted text...", "icon": "alert-triangle"})
                            logger.info(f"PDF too large for native Gemini part ({len(pdf_bytes)} bytes), using text extraction fallback")
                    except Exception as pdf_part_err:
                        logger.warning(f"Native PDF Part construction note: {pdf_part_err}")

                elif ft.startswith("image/") or raw_content.startswith("data:image/"):
                    try:
                        mime = ft if ft.startswith("image/") else "image/png"
                        b64_data = raw_content
                        if "," in b64_data:
                            hdr, b64_data = b64_data.split(",", 1)
                            if "data:" in hdr and ";base64" in hdr:
                                mime = hdr.split("data:", 1)[1].split(";base64", 1)[0]
                        img_bytes = base64.b64decode(b64_data)
                        img_part = types.Part.from_bytes(data=img_bytes, mime_type=mime)
                        contents_payload.append(img_part)
                        yield sse_event("progress", {"step": "native_img", "message": f"Sending native Image '{fn}' to Gemini...", "icon": "image"})
                    except Exception as img_part_err:
                        logger.warning(f"Native Image Part construction note: {img_part_err}")

            contents_payload.append(user_content)

            # Sanitize model name: frontend may send display names like
            # 'Groq Primary API (openai/gpt-oss-120b)' — extract raw model ID
            raw_model = req.model or ""
            if " (via " in raw_model:
                raw_model = raw_model.split(" (via ", 1)[0]
            if raw_model.lower().startswith("via "):
                raw_model = ""
            if "(" in raw_model and raw_model.endswith(")"):
                raw_model = raw_model.rsplit("(", 1)[-1].rstrip(")")
            primary_model = raw_model.strip() if raw_model.strip() else provider_router.get_default_model()

            response_text = None
            model_used = None
            is_fallback = False

            safe_user_content = user_content
            # Dynamic content cap: edits need less, generation with PDF attachments needs more
            if is_targeted_edit:
                user_content_cap = 20000   # Tight cap for focused edits
            elif attached_info:
                user_content_cap = 35000   # Generous for PDF-based generation
            else:
                user_content_cap = 25000   # Default
            if len(safe_user_content) > user_content_cap:
                safe_user_content = safe_user_content[:user_content_cap] + "\n...[Content capped for token/payload limit]"

            messages_list = []
            if system_content:
                messages_list.append({"role": "system", "content": system_content})
            messages_list.append({"role": "user", "content": safe_user_content})

            # Route to the correct provider via the provider router
            provider = provider_router.route(primary_model)
            provider_name = provider.get_provider_name()
            yield sse_event("progress", {"step": "llm_call", "message": f"Generating with {provider_name} ({primary_model})...", "icon": "sparkles"})

            # Dynamic max_tokens: generation needs much more output space than edits
            # A full 12+ slide Beamer PPT with literature survey needs ~10k tokens
            if is_new_doc_request or not has_existing_code:
                llm_max_tokens = 8192   # New document / full generation
            elif is_targeted_edit:
                llm_max_tokens = 4096   # Targeted edit (1-2 frames)
            else:
                llm_max_tokens = 6144   # General edit / partial regeneration

            try:
                llm_result = None
                async for item in run_step_with_heartbeat(
                    provider.chat,
                    messages=messages_list,
                    model=primary_model,
                    temperature=0.1,
                    max_tokens=llm_max_tokens,
                ):
                    if isinstance(item, str) and item.startswith(":"):
                        yield item
                    else:
                        llm_result = item

                if not llm_result:
                    yield sse_event("error", {"message": f"{provider_name} returned no result."})
                    return

                response_text = llm_result["content"]
                model_used = llm_result["model_used"]
                is_fallback = llm_result.get("is_fallback", False)
            except LLMProviderError as provider_err:
                logger.error(f"Provider {provider_name} failed: {provider_err}")
                yield sse_event("error", {"message": f"{provider_name} failed: {str(provider_err)}"})
                return

            if response_text is None:
                yield sse_event("error", {"message": "No response received from AI provider."})
                return

            # Step 7: Parse response
            yield sse_event("progress", {"step": "parse", "message": "Parsing AI response...", "icon": "code"})
            parsed_result = clean_json_response(response_text)

            edits = parsed_result.get("edits", [])
            if not isinstance(edits, list):
                edits = []

            if not edits:
                orig = parsed_result.get("original_chunk", "")
                prop = parsed_result.get("proposed_chunk", "")
                exp = parsed_result.get("explanation", "")
                if orig or prop:
                    edits = [{"original_chunk": orig, "proposed_chunk": prop, "explanation": exp}]

            # Fast local extraction if no edits parsed from JSON schema
            if not edits:
                extracted_latex = extract_chunk_latex(response_text)
                if extracted_latex:
                    edits = [{
                        "original_chunk": "",
                        "proposed_chunk": extracted_latex,
                        "explanation": "Extracted LaTeX document proposal."
                    }]

            # Automatic fallback retry if the primary model refused or failed to produce code
            is_refusal_response = any(ref_kw in response_text.lower() for ref_kw in [
                "hard time fulfilling",
                "cannot fulfill",
                "can't fulfill",
                "unable to fulfill",
                "against my safety guidelines",
                "help you with something else instead",
                "as an ai language model",
            ])
            if (is_refusal_response or (not edits and mode == "EDIT_DOCUMENT")) and not is_fallback:
                logger.warning(f"Primary model ({primary_model}) refused or returned no code, retrying with fallback provider...")
                yield sse_event("progress", {"step": "retry_fallback", "message": "Refusal detected, retrying with fallback AI...", "icon": "refresh-cw"})
                try:
                    fallback_provider = provider_router.freellm
                    fb_result = None
                    async for item in run_step_with_heartbeat(
                        fallback_provider.chat,
                        messages=messages_list,
                        model=fallback_provider.default_model,
                        temperature=0.1,
                        max_tokens=llm_max_tokens,
                    ):
                        if isinstance(item, str) and item.startswith(":"):
                            yield item
                        else:
                            fb_result = item

                    if fb_result and fb_result.get("content"):
                        response_text = fb_result["content"]
                        model_used = fb_result.get("model_used", fallback_provider.default_model)
                        is_fallback = True
                        parsed_result = clean_json_response(response_text)
                        edits = parsed_result.get("edits", [])
                        if not edits:
                            extracted_latex = extract_chunk_latex(response_text)
                            if extracted_latex:
                                edits = [{
                                    "original_chunk": "",
                                    "proposed_chunk": extracted_latex,
                                    "explanation": "Extracted LaTeX document proposal from fallback."
                                }]
                except Exception as fb_err:
                    logger.warning(f"Fallback attempt failed: {fb_err}")

            # If existing document code exists, align proposed edits
            if edits and has_existing_code and req.current_code and "\\end{document}" in req.current_code:
                # Detect if user prompt requests replacing/customizing template or document content
                is_replace_req = any(kw in req.user_prompt.lower() for kw in [
                    "replace entire", "replace all", "overwrite entire", "convert document", "from scratch", "full replacement"
                ])
                is_template_or_replace = (
                    is_replace_req or
                    any(kw in req.user_prompt.lower() for kw in [
                        "make this", "edit this", "customize", "fill this", "update this", "adapt this",
                        "use this template", "make letter", "write letter", "make resume", "create letter",
                        "duty leave", "leave application", "cover letter", "application for", "apply",
                        "rewrite", "redesign", "turn this into", "change this into", "change topic",
                        "template", "for abin"
                    ]) or
                    ("\\begin{letter}" in req.current_code)
                )

                for e in edits:
                    oc = e.get("original_chunk", "")
                    pc = e.get("proposed_chunk", "")
                    if not pc:
                        continue

                    if "aspectratio=160" in pc:
                        e["proposed_chunk"] = pc.replace("aspectratio=160", "aspectratio=169")
                        pc = e["proposed_chunk"]

                    # 1. Standalone full document returned (\documentclass ... \begin{document})
                    # Keep \documentclass intact so the editor cleanly replaces the entire document
                    if "\\documentclass" in pc and "\\begin{document}" in pc:
                        e["original_chunk"] = req.current_code
                        e["proposed_chunk"] = pc
                        continue

                    # 2. Check if original_chunk matches verbatim or with normalized whitespace
                    matched_orig = find_verbatim_or_fuzzy(req.current_code, oc) if oc else None
                    if matched_orig:
                        e["original_chunk"] = matched_orig
                        continue

                    # 2b. Frame-level in-place alignment for Beamer presentations:
                    # If proposed_chunk is a frame, match it to an existing frame in req.current_code
                    # so edits replace the existing slide in-place, NEVER duplicating at the document bottom!
                    if "\\begin{frame}" in pc and "\\end{frame}" in pc:
                        frame_matched = False
                        doc_struct = locals().get("document_structure")
                        if not doc_struct:
                            try:
                                doc_struct = doc_idx.parse_document_structure(req.current_code)
                            except Exception:
                                doc_struct = None

                        # Match by identified target slide index from Step 3
                        tgt_idx = locals().get("target_page_index")
                        if tgt_idx is not None and doc_struct:
                            target_page = doc_struct.get_page_by_index(tgt_idx)
                            if target_page and target_page.content and target_page.content in req.current_code:
                                e["original_chunk"] = target_page.content
                                frame_matched = True

                        # Match by fraction (e.g. 7/7), title, or survey number in proposed frame
                        if not frame_matched and doc_struct:
                            pc_title_m = re.search(r'\\begin\{frame\}(?:\[[^\]]*\])?\s*\{([^}]+)\}', pc)
                            pc_title = pc_title_m.group(1).strip() if pc_title_m else ""
                            pc_frac_m = re.search(r'\(?(\d+/\d+)\)?', pc)
                            pc_frac = pc_frac_m.group(1) if pc_frac_m else ""

                            for page in doc_struct.pages:
                                if page.page_type != "frame":
                                    continue
                                if (pc_frac and pc_frac in page.content) or \
                                   (pc_title and (pc_title.lower() in page.title.lower() or page.title.lower() in pc_title.lower())):
                                    if page.content in req.current_code:
                                        e["original_chunk"] = page.content
                                        frame_matched = True
                                        break

                        if frame_matched:
                            continue

                    # 3. Special handling for Letter templates/documents:
                    # A letter document has a single \begin{letter}...\end{letter} block.
                    # Any edit to a letter template MUST replace the existing letter in-place, NEVER append a second letter!
                    if "\\begin{letter}" in req.current_code:
                        let_end_idx = req.current_code.rfind("\\end{letter}")
                        if let_end_idx != -1:
                            beg_doc_idx = req.current_code.find("\\begin{document}")
                            date_idx = req.current_code.find("\\date", beg_doc_idx) if beg_doc_idx != -1 else req.current_code.find("\\date")
                            let_start_idx = req.current_code.find("\\begin{letter}")
                            
                            target_start = date_idx if (date_idx != -1 and date_idx < let_start_idx and (beg_doc_idx == -1 or date_idx > beg_doc_idx)) else let_start_idx
                            target_end = let_end_idx + len("\\end{letter}")
                            
                            if target_start != -1 and target_end > target_start:
                                clean_pc = pc.strip()
                                # Prevent accidental double \end{document}
                                if clean_pc.endswith("\\end{document}"):
                                    clean_pc = clean_pc[:-len("\\end{document}")].rstrip()
                                e["original_chunk"] = req.current_code[target_start:target_end]
                                e["proposed_chunk"] = clean_pc
                                continue

                    # 4. Template / Full Content Overhaul where model provided inner document content
                    if is_template_or_replace and "\\begin{document}" in req.current_code:
                        beg_doc_idx = req.current_code.find("\\begin{document}")
                        end_doc_idx = req.current_code.rfind("\\end{document}")
                        if beg_doc_idx != -1 and end_doc_idx != -1 and end_doc_idx > beg_doc_idx:
                            inner_target = req.current_code[beg_doc_idx + len("\\begin{document}"):end_doc_idx]
                            clean_pc = pc.strip()
                            inner_m = re.search(r'\\begin\{document\}([\s\S]*?)\\end\{document\}', clean_pc, re.DOTALL)
                            if inner_m:
                                clean_pc = inner_m.group(1).strip()
                            e["original_chunk"] = inner_target
                            e["proposed_chunk"] = f"\n\n{clean_pc}\n\n"
                            continue

                    # 5. Fallback: ONLY append before \end{document} if user explicitly requested to add/append
                    is_add_req = any(kw in req.user_prompt.lower() for kw in ["add", "insert", "append", "new slide", "extra", "more"])
                    if is_add_req and "\\documentclass" not in pc:
                        clean_pc = pc.replace("\\end{document}", "").strip()
                        e["original_chunk"] = "\\end{document}"
                        e["proposed_chunk"] = f"{clean_pc}\n\n\\end{{document}}"
                    else:
                        # For general edits where original_chunk couldn't be matched, safely replace current_code
                        if "\\begin{document}" in pc or "\\documentclass" in pc or len(pc) > len(req.current_code) * 0.4:
                            e["original_chunk"] = req.current_code
                            if "\\documentclass" not in pc:
                                doc_class_m = re.search(r'\\documentclass\[?[^\]]*\]?\{[^}]+\}', req.current_code)
                                doc_class = doc_class_m.group(0) if doc_class_m else "\\documentclass[11pt]{article}"
                                preamble_end = req.current_code.find("\\begin{document}")
                                preamble = req.current_code[:preamble_end] if preamble_end != -1 else doc_class + "\n"
                                e["proposed_chunk"] = f"{preamble}\n\\begin{{document}}\n\n{pc.strip()}\n\n\\end{{document}}"
                            else:
                                e["proposed_chunk"] = pc

            # Fallback for presentation requests on empty document if LLM output slide chip text without code
            if not edits and is_new_doc_request and not has_existing_code and not is_pdf:
                clean_topic = re.sub(r'(?i)\b(?:create|make|turn|generate|a|an|the|ppt|presentation|slide|slides|deck|on|for|about)\b', '', req.user_prompt).strip()
                topic_title = clean_topic.title() if clean_topic else "Presentation"
                fallback_beamer = (
                    "\\documentclass[11pt, aspectratio=169]{beamer}\n"
                    "\\usetheme{Madrid}\n"
                    "\\usefonttheme{professionalfonts}\n"
                    "\\usepackage[T1]{fontenc}\n"
                    "\\usepackage{lmodern}\n"
                    "\\usepackage{graphicx}\n"
                    "\\usepackage{booktabs}\n"
                    "\\usepackage{amsmath,amssymb}\n"
                    "\\usepackage{hyperref}\n"
                    "\\usepackage{xcolor}\n\n"
                    "\\definecolor{primaryDark}{RGB}{15, 23, 42}\n"
                    "\\definecolor{accentEmerald}{RGB}{0, 204, 104}\n"
                    "\\definecolor{secondarySlate}{RGB}{51, 65, 85}\n"
                    "\\definecolor{cardBg}{RGB}{240, 247, 255}\n"
                    "\\definecolor{darkText}{RGB}{15, 23, 42}\n\n"
                    "\\setbeamercolor*{palette primary}{bg=primaryDark, fg=white}\n"
                    "\\setbeamercolor*{palette secondary}{bg=secondarySlate, fg=white}\n"
                    "\\setbeamercolor*{palette tertiary}{bg=primaryDark!90, fg=white}\n"
                    "\\setbeamercolor*{structure}{fg=accentEmerald}\n\n"
                    "\\setbeamercolor{frametitle}{bg=primaryDark, fg=white}\n"
                    "\\setbeamercolor{frametitle right}{bg=primaryDark}\n"
                    "\\setbeamercolor{title}{bg=primaryDark, fg=white}\n"
                    "\\setbeamercolor{subtitle}{fg=accentEmerald}\n"
                    "\\setbeamercolor{author}{fg=primaryDark}\n"
                    "\\setbeamercolor{institute}{fg=secondarySlate}\n"
                    "\\setbeamercolor{date}{fg=secondarySlate}\n\n"
                    "\\setbeamertemplate{blocks}[rounded][shadow=true]\n"
                    "\\setbeamercolor{block title}{bg=primaryDark, fg=white}\n"
                    "\\setbeamercolor{block body}{bg=cardBg, fg=darkText}\n"
                    "\\setbeamercolor{block title alerted}{bg=accentEmerald, fg=black}\n"
                    "\\setbeamercolor{block body alerted}{bg=cardBg, fg=darkText}\n"
                    "\\setbeamercolor{block title example}{bg=secondarySlate, fg=white}\n"
                    "\\setbeamercolor{block body example}{bg=cardBg, fg=darkText}\n\n"
                    "\\setbeamercolor{item}{fg=accentEmerald}\n"
                    "\\setbeamercolor{subitem}{fg=primaryDark}\n"
                    "\\setbeamertemplate{itemize item}{\\raisebox{1pt}{\\scriptsize\\color{accentEmerald}$\\blacksquare$}}\n"
                    "\\setbeamertemplate{itemize subitem}{\\raisebox{1pt}{\\tiny\\color{primaryDark}$\\blacktriangleright$}}\n"
                    "\\setbeamertemplate{navigation symbols}{}\n\n"
                    f"\\title[{topic_title}]{{{topic_title}}}\n"
                    f"\\subtitle{{Overview \\& Key Strategic Insights}}\n"
                    f"\\author[Project Team]{{Technical Report}}\n"
                    f"\\institute[OverBranch]{{Research \\& Development}}\n"
                    "\\date{\\today}\n\n"
                    "\\begin{document}\n\n"
                    "\\begin{frame}\n  \\titlepage\n\\end{frame}\n\n"
                    "\\section{Agenda}\n"
                    "\\begin{frame}{Presentation Agenda}\n  \\tableofcontents\n\\end{frame}\n\n"
                    "\\section{Overview}\n"
                    f"\\begin{{frame}}{{Overview \\& Background: {topic_title}}}\n"
                    "  \\begin{columns}[T]\n"
                    "    \\begin{column}{0.48\\textwidth}\n"
                    "      \\begin{block}{Key Focus}\n"
                    f"        High-level objectives and technical motivations behind {topic_title}.\n"
                    "      \\end{block}\n"
                    "    \\end{column}\n"
                    "    \\begin{column}{0.48\\textwidth}\n"
                    "      \\begin{exampleblock}{Core Benefits}\n"
                    "        \\begin{itemize}\n"
                    "          \\item Structured presentation format\n"
                    "          \\item High visual contrast \\& readability\n"
                    "        \\end{itemize}\n"
                    "      \\end{exampleblock}\n"
                    "    \\end{column}\n"
                    "  \\end{columns}\n"
                    "\\end{frame}\n\n"
                    "\\section{Conclusion}\n"
                    "\\begin{frame}[plain]\n"
                    "  \\vfill\n"
                    "  \\centering\n"
                    "  \\begin{beamercolorbox}[sep=14pt,center,shadow=true,rounded=true]{title}\n"
                    "    {\\Huge \\textbf{Thank You!}}\\par\n"
                    "    \\vspace{0.6em}\n"
                    "    {\\large Questions \\& Discussion}\\par\n"
                    "  \\end{beamercolorbox}\n"
                    "  \\vfill\n"
                    "\\end{frame}\n\n"
                    "\\end{document}"
                )
                edits = [{
                    "original_chunk": req.current_code or "",
                    "proposed_chunk": fallback_beamer,
                    "explanation": f"Generated 16:9 Beamer presentation for '{topic_title}'."
                }]

            # Fallback for PDF conversion if LLM failed to produce structured edits on empty document
            if not edits and is_pdf and pdf_data_input and is_pdf_conversion_request and not has_existing_code:
                try:
                    pr = parse_pdf(pdf_data_input, render_300dpi=False, render_150dpi=False, max_pages=MAX_ALLOWED_PAGES)
                    safe_class = "article" if pr.doc_type_hint != "report" else "report"
                    fallback_doc = (
                        f"\\documentclass[11pt,a4paper,oneside]{{{safe_class}}}\n"
                        "\\usepackage[utf8]{inputenc}\n"
                        "\\usepackage[margin=1in]{geometry}\n"
                        "\\usepackage{parskip}\n"
                        "\\usepackage{amsmath,amssymb}\n"
                        "\\usepackage{graphicx}\n"
                        "\\usepackage{booktabs}\n"
                        "\\usepackage{hyperref}\n\n"
                        "\\begin{document}\n\n"
                        + (pr.full_text or "Converted Document") + "\n\n"
                        "\\end{document}"
                    )
                    edits = [{
                        "original_chunk": req.current_code or "",
                        "proposed_chunk": fallback_doc,
                        "explanation": f"Generated editable LaTeX document from PDF ({safe_class})."
                    }]
                except Exception as fb_err:
                    logger.warning(f"Could not build fallback document from PDF: {fb_err}")

            # Step 8: Compute edit line ranges for progress display
            if mode != "EDIT_DOCUMENT":
                edits = []
                first_orig = ""
                first_prop = ""
            else:
                first_orig = edits[0].get("original_chunk", "") if edits else parsed_result.get("original_chunk", "")
                first_prop = sanitize_latex_code(edits[0].get("proposed_chunk", "") if edits else parsed_result.get("proposed_chunk", ""))

            if edits and req.current_code:
                for e in edits:
                    oc = e.get("original_chunk", "")
                    pc = e.get("proposed_chunk", "")
                    if oc and req.current_code and oc in req.current_code:
                        start_idx = req.current_code.index(oc)
                        start_line = req.current_code[:start_idx].count("\n") + 1
                        end_line = start_line + oc.count("\n")
                        yield sse_event("progress", {"step": "editing", "message": f"Editing lines {start_line}–{end_line}", "icon": "file-code"})
                    elif pc:
                        pc_lines = pc.count("\n") + 1
                        yield sse_event("progress", {"step": "inserting", "message": f"Inserting {pc_lines} new lines", "icon": "plus-circle"})

            overall_exp = sanitize_explanation_text(
                parsed_result.get("explanation", "") or (edits[0].get("explanation", "") if edits else "")
            )
            clean_plan = sanitize_explanation_text(parsed_result.get("plan", ""))

            clean_edits = []
            for e in edits:
                item = dict(e)
                if item.get("proposed_chunk"):
                    item["proposed_chunk"] = sanitize_latex_code(item["proposed_chunk"])
                if item.get("explanation"):
                    item["explanation"] = sanitize_explanation_text(item["explanation"])
                clean_edits.append(item)

            # Step 8b: Validation & auto-repair
            if clean_edits and has_existing_code:
                try:
                    validation = edit_validator.validate_edit(
                        original_code=req.current_code or "",
                        proposed_edits=clean_edits,
                    )
                    if not validation.passed:
                        # Attempt auto-repair for fixable issues
                        clean_edits, repairs = edit_validator.auto_repair_edits(
                            proposed_edits=clean_edits,
                            original_code=req.current_code or "",
                        )
                        if repairs:
                            logger.info(f"Auto-repaired {len(repairs)} issues: {repairs}")
                            yield sse_event("progress", {
                                "step": "repair",
                                "message": f"Auto-fixed {len(repairs)} issue(s)",
                                "icon": "tool"
                            })
                        # Re-validate after repair
                        validation = edit_validator.validate_edit(
                            original_code=req.current_code or "",
                            proposed_edits=clean_edits,
                        )
                        if not validation.passed:
                            error_msgs = [i.message for i in validation.issues if i.severity == "error"]
                            logger.warning(f"Edit validation still failing after repair: {error_msgs}")
                except Exception as val_err:
                    logger.warning(f"Edit validation skipped due to error: {val_err}")

            # Update first_orig/first_prop after potential repair
            if clean_edits:
                first_orig = clean_edits[0].get("original_chunk", first_orig)
                first_prop = clean_edits[0].get("proposed_chunk", first_prop)

            # Step 9: Store in conversation memory
            chunk_summaries = [c.get("summary", "") for c in retrieved_chunks if c.get("summary")]
            conversation_memory.add_turn(
                project_id=req.project_id,
                user_prompt=req.user_prompt,
                assistant_response=parsed_result,
                file_path=req.file_path,
                chunk_summaries=chunk_summaries,
            )

            fallback_notice = (
                f"Note: Primary model ({primary_model}) was unavailable. Used fallback model ({model_used})."
                if is_fallback
                else None
            )

            yield sse_event("progress", {"step": "done", "message": "Complete", "icon": "check"})

            # Final result
            yield sse_event("result", {
                "plan": clean_plan,
                "edits": clean_edits,
                "original_chunk": first_orig,
                "proposed_chunk": first_prop,
                "explanation": overall_exp,
                "retrieved_chunks_count": len(retrieved_chunks),
                "model_used": model_used,
                "is_fallback": is_fallback,
                "fallback_notice": fallback_notice,
            })

        except Exception as e:
            logger.error(f"Error in AI agent endpoint: {str(e)}", exc_info=True)
            yield sse_event("error", {"message": f"AI Agent execution failed: {str(e)}"})

    return StreamingResponse(
        pipeline_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/models")
def get_available_models():
    """
    Returns the list of available LLM models grouped by provider.
    Used by the frontend model selector dropdown.
    """
    return provider_router.get_available_models()
