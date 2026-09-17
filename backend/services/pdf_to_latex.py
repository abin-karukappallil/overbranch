"""
pdf_to_latex.py — PDF to Editable LaTeX Conversion Engine

Orchestrates:
1. Formatting extracted PDF text, layout blocks, and asset metadata into an LLM prompt.
2. Invoking LLM via provider_router (supporting Gemini, Groq, FreeLLM).
3. Parsing structured JSON response into project files:
   - main.tex
   - additional .tex files / sections
   - bibliography.bib (if references present)
   - assets mapping
4. Verifying compilation with compile_latex() and auto-retrying with compiler error feedback if compilation fails.
"""

import os
import re
import json
import base64
import logging
from typing import List, Dict, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field
import pymupdf as fitz

from .pdf_parser import PDFParseResult, ExtractedImage, ExtractedBlock
from providers import provider_router
from compiler import compile_latex

from .fidelity_checker import fidelity_checker, FidelityReport

logger = logging.getLogger("pdf_to_latex")


@dataclass
class ProjectFile:
    path: str
    content: str


@dataclass
class AssetFile:
    filename: str
    data_bytes: bytes
    source_page: int
    ext: str = "png"
    mime_type: str = "image/png"


@dataclass
class ConversionResult:
    document_class: str
    engine: str
    files: List[ProjectFile]
    assets: List[AssetFile]
    compiled_successfully: bool = False
    compile_log: str = ""
    retry_count: int = 0
    fidelity_score: float = 1.0
    fidelity_defects: List[Dict[str, Any]] = field(default_factory=list)
    flagged_pages: List[int] = field(default_factory=list)
    page_fidelity_scores: Dict[int, float] = field(default_factory=dict)


SYSTEM_PROMPT = r"""You are an elite LaTeX typographer and document engineer embedded in OverBranch.
Your task is to convert the extracted text, layout structure, and figures from a PDF document into a 100% editable, modular, and compilable LaTeX project.

CRITICAL ARCHITECTURAL RULES:
1. EDITABLE LATEX ONLY:
   - NEVER rasterize text into images.
   - All text, headers, paragraphs, lists, and tables must be native LaTeX.
   - Retain mathematical notation using standard LaTeX math environments ($...$, \begin{equation}, \begin{align*}).
   - Use semantic commands (\section, \subsection, \subsubsection, \paragraph).
   - Recreate tables using \begin{table}[h!] and \begin{tabular} with booktabs (\toprule, \midrule, \bottomrule).

2. DOCUMENT CLASS SELECTION:
   - NEVER use \documentclass{beamer} for portrait documents (research papers, reports, theses, articles, resumes). Beamer is ONLY for widescreen slide presentations.
   - If Report / Thesis / Chapter-based document -> Use \documentclass[11pt,a4paper,oneside]{report} with chapters or sections (the 'oneside' option is MANDATORY so odd and even pages have symmetric, centered margins!).
   - If Academic / Research Paper -> Use \documentclass[11pt,a4paper]{article} with \title, \author, \begin{abstract}, standard sections, and \bibliographystyle{plain}.
   - If Resume / CV -> Use \documentclass[10pt,letterpaper]{article} with \usepackage[margin=0.65in]{geometry}, clean sections, and enumitem.
   - If Widescreen Slide Deck (Landscape only) -> Use \documentclass[11pt,aspectratio=169]{beamer} with \begin{frame}{Title}... \end{frame}.

3. PAGE GEOMETRY, MARGINS & ALIGNMENT (CRITICAL TO PREVENT MISALIGNMENT):
   - ALWAYS include:
     \usepackage[margin=1in]{geometry}
     \usepackage{parskip} % ensures modern paragraph spacing without awkward accidental indentations
     \usepackage{amsmath,amssymb}
     \usepackage{booktabs}
     \usepackage{graphicx}
     \usepackage{hyperref}
   - NEVER use \MakeUppercase inside \titleformat (in modern LaTeX, \MakeUppercase inside \titleformat causes a fatal syntax crash). Use standard styles like \normalfont\bfseries\Large.
   - On title pages or vertical spacing, use \par\vspace{1.5cm} or empty lines with \vspace{1.5cm} instead of \\[1.5cm] (which can trigger Bad Math Delimiter errors).
   - ALL tables MUST be centered: \begin{table}[htbp] \centering \begin{tabular}{...} ... \end{tabular} \caption{...} \end{table}.
     If the table has many columns or wide text, wrap it with \resizebox{\textwidth}{!}{...} to prevent overflowing the right margin!
   - ALL figures MUST be centered: \begin{figure}[htbp] \centering \includegraphics[width=0.85\textwidth,keepaspectratio]{assets/filename} \caption{...} \end{figure}.
   - Math equations must be centered using standard \begin{equation} ... \end{equation} or \begin{align*} ... \end{align*}.

4. EMBEDDED IMAGES / ASSETS:
   - Available extracted images are placed in the 'assets/' folder.
   - When figures or logos are present, include them using \begin{figure}[htbp] \centering \includegraphics[width=...]{assets/filename} \caption{...} \end{figure}.
   - ONLY reference filenames that are listed in the AVAILABLE ASSETS list. Do not invent arbitrary image names.

5. SELF-CONTAINED SINGLE-DOCUMENT ARCHITECTURE (CRITICAL):
   - ALL document content must be written DIRECTLY inside main.tex between \begin{document} and \end{document}.
   - DO NOT split content into external section files (NEVER use \input{sections/...} or \include{sections/...}).
   - The user requires the entire document (title, abstract, table of contents, all chapters, sections, methodology, results, equations, tables, figures, conclusions) to be completely and fully written out directly inside main.tex.
   - Everything must be self-contained in main.tex so the user can immediately read, edit, and compile the entire project in one place.
   - For references/bibliography, either provide \begin{thebibliography}{99}...\end{thebibliography} directly inside main.tex, or provide bibliography.bib.

6. OUTPUT FORMAT:
   You MUST respond with a single, strictly valid JSON object. No Markdown code fences before or after the JSON, no surrounding commentary.

JSON Schema:
{
  "document_class": "article | beamer | report",
  "engine": "pdflatex",
  "files": [
    {
      "path": "main.tex",
      "content": "\\documentclass[11pt,a4paper,oneside]{report}\n\\usepackage[utf8]{inputenc}\n\\usepackage[margin=1in]{geometry}\n\\usepackage{parskip}\n\\usepackage{amsmath,amssymb,graphicx,booktabs,hyperref}\n...\n\\begin{document}\n\\chapter{Introduction}\n...\n\\chapter{Methodology}\n...\n\\chapter{Conclusion}\n...\n\\end{document}"
    },
    {
      "path": "bibliography.bib",
      "content": "@article{key,\n  author = {},\n  ...\n}"
    }
  ],
  "assets": [
    {
      "filename": "image_p1_1.png",
      "source_page": 1
    }
  ]
}

Ensure all backslashes in LaTeX strings are properly JSON-escaped (e.g. "\\\\documentclass", "\\\\section").
Ensure the document closes with \end{document}.
"""


def auto_repair_json(text: str) -> str:
    """Repairs unclosed strings and brackets in truncated or malformed JSON."""
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.MULTILINE)
        s = re.sub(r"\s*```$", "", s, flags=re.MULTILINE)

    s = s.strip()
    if not s.endswith("}"):
        if not s.endswith('"'):
            s += '"'
        open_b = s.count('{')
        close_b = s.count('}')
        if open_b > close_b:
            s += '}' * (open_b - close_b)
    return s


def decode_json_string_value(s: str) -> str:
    """Safely decodes JSON string literal values without crashing on LaTeX commands."""
    if not s:
        return ""
    try:
        test_s = s
        if test_s.endswith("\\") and not test_s.endswith("\\\\"):
            test_s = test_s[:-1]
        return json.loads(f'"{test_s}"', strict=False)
    except Exception:
        pass
    def repl(m):
        esc = m.group(0)
        table = {r'\\': '\\', r'\"': '"', r'\/': '/', r'\n': '\n', r'\t': '\t', r'\r': '\r', r'\b': '\b', r'\f': '\f'}
        return table.get(esc, esc)
    return re.sub(r'\\(?:[\\"/bfnrt]|u[0-9a-fA-F]{4}|.)', repl, s)


def restore_latex_escapes(text: str) -> str:
    """Restores swallowed LaTeX commands from JSON control characters."""
    if not text or not isinstance(text, str):
        return text or ""
    s = text
    s = re.sub(r"[\x08](egin|fseries|ooktabs|ottomrule|ibliography)\b", r"\\b\1", s)
    s = re.sub(r"[\x0c](rac|ootnotesize|rame|igure)\b", r"\\f\1", s)
    s = re.sub(r"[\r](enewcommand|ef|ule|aisebox)\b", r"\\r\1", s)
    s = re.sub(r"[\t](extbf|extit|exttt|itle|able|oday)\b", r"\\t\1", s)
    s = re.sub(r"(?<![a-zA-Z\\])usepackage(?=\{|\s*\[)", r"\\usepackage", s)
    s = re.sub(r"(?<![a-zA-Z\\])begin(?=\{)", r"\\begin", s)
    s = re.sub(r"(?<![a-zA-Z\\])section(?=\{)", r"\\section", s)
    s = re.sub(r"(?<![a-zA-Z\\])textbf(?=\{)", r"\\textbf", s)
    return s


def parse_llm_json_response(raw_text: str) -> Dict[str, Any]:
    """Multi-stage robust JSON parser for LLM responses with LaTeX backslashes."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()

    def _sanitize_files(data: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(data, dict):
            return None
        files = data.get("files", [])
        if not isinstance(files, list):
            return None
        for f in files:
            if isinstance(f, dict) and "content" in f and isinstance(f["content"], str):
                f["content"] = restore_latex_escapes(f["content"])
        return data

    # Pass 1: Direct JSON parse
    try:
        data = json.loads(cleaned, strict=False)
        res = _sanitize_files(data)
        if res:
            return res
    except Exception:
        pass

    # Pass 2: Repair truncated brackets
    try:
        repaired = auto_repair_json(cleaned)
        data = json.loads(repaired, strict=False)
        res = _sanitize_files(data)
        if res:
            return res
    except Exception:
        pass

    # Pass 3: Escape lone unescaped backslashes (common in LaTeX inside JSON)
    try:
        escaped_slashes = re.sub(r'\\(?![\\"/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', cleaned)
        data = json.loads(auto_repair_json(escaped_slashes), strict=False)
        res = _sanitize_files(data)
        if res:
            return res
    except Exception:
        pass

    # Pass 4: Find JSON object boundaries via regex
    json_match = re.search(r"\{[\s\S]*\}", cleaned)
    if json_match:
        try:
            raw_obj = json_match.group(0)
            data = json.loads(raw_obj, strict=False)
            res = _sanitize_files(data)
            if res:
                return res
        except Exception:
            try:
                fixed = re.sub(r'\\(?![\\"/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', json_match.group(0))
                data = json.loads(auto_repair_json(fixed), strict=False)
                res = _sanitize_files(data)
                if res:
                    return res
            except Exception:
                pass

    # Pass 5: Regex extraction of files if JSON is partially broken
    files = []
    main_tex_match = re.search(r'"path"\s*:\s*"main\.tex"[\s\S]*?"content"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned)
    if main_tex_match:
        content = decode_json_string_value(main_tex_match.group(1))
        content = restore_latex_escapes(content)
        files.append({"path": "main.tex", "content": content})
        return {
            "document_class": "article",
            "engine": "pdflatex",
            "files": files,
            "assets": []
        }

    # Pass 6: Check if response is raw LaTeX starting with \documentclass and closing with \end{document}
    latex_doc_match = re.search(r"(\\documentclass[\s\S]*?\\end\{document\})", cleaned)
    if latex_doc_match:
        return {
            "document_class": "article",
            "engine": "pdflatex",
            "files": [{"path": "main.tex", "content": latex_doc_match.group(1)}],
            "assets": []
        }

    # Pass 7: Partial raw LaTeX containing \documentclass
    latex_start_match = re.search(r"(\\documentclass[\s\S]+)", cleaned)
    if latex_start_match:
        raw_code = latex_start_match.group(1).strip()
        if "\\end{document}" not in raw_code:
            raw_code = raw_code + "\n\\end{document}\n"
        return {
            "document_class": "article",
            "engine": "pdflatex",
            "files": [{"path": "main.tex", "content": raw_code}],
            "assets": []
        }

    raise ValueError("Could not parse LLM response into valid JSON or LaTeX document structure.")


def is_truncated_latex(latex_content: str, parse_result: PDFParseResult) -> Tuple[bool, str]:
    """
    Checks if synthesized LaTeX shows clear evidence of truncation:
    1. Empty or nearly empty content
    2. Missing \\end{document} tag when \\begin{document} exists
    3. Severe line/word count deficit compared to source PDF
    4. Abrupt termination on incomplete commands
    """
    if not latex_content or not latex_content.strip():
        return True, "Empty LaTeX content"

    stripped = latex_content.strip()
    lines = [l for l in stripped.splitlines() if l.strip()]

    # Cut off mid-command or mid-environment
    if stripped.endswith(("\\begin{", "\\item", "\\frac{", "\\textbf{", "\\section{", "\\", "{")):
        return True, f"Cut off mid-command: ...{stripped[-30:]}"

    # Missing \end{document}
    if "\\begin{document}" in stripped and "\\end{document}" not in stripped:
        return True, "Missing \\end{document} tag"

    # Line count check: 4 lines or fewer for a substantive document
    orig_words = len(re.findall(r"\b\w+\b", getattr(parse_result, "full_text", "") or ""))
    if len(lines) <= 4 and orig_words > 40:
        return True, f"Synthesized output has only {len(lines)} lines despite source having {orig_words} words"

    # Severe word count deficit
    latex_words = len(re.findall(r"\b\w+\b", stripped))
    if orig_words > 80 and latex_words < max(20, int(orig_words * 0.12)):
        return True, f"Severe text deficit: synthesized {latex_words} words vs {orig_words} source words"

    return False, ""

def compute_typography_metrics(parse_result: PDFParseResult) -> Dict[str, Any]:
    """Extracts average line spacing, body font size, and paragraph gaps from layout elements."""
    line_spacings = []
    font_sizes = []
    par_gaps = []
    prev_y1 = None

    for page in getattr(parse_result, "pages", []):
        layout = getattr(page, "layout_data", {}) or {}
        elements = layout.get("elements", [])
        for elem in elements:
            if elem.get("line_spacing"):
                line_spacings.append(elem["line_spacing"])
            if elem.get("type") == "paragraph" and elem.get("font_size"):
                font_sizes.append(elem["font_size"])
            bbox = elem.get("bbox")
            if bbox and prev_y1 is not None:
                gap = bbox[1] - prev_y1
                if 0 < gap < 50:
                    par_gaps.append(gap)
            if bbox:
                prev_y1 = bbox[3]

    avg_spacing = sum(line_spacings) / len(line_spacings) if line_spacings else 1.15
    avg_font = sum(font_sizes) / len(font_sizes) if font_sizes else 11.5
    avg_gap = sum(par_gaps) / len(par_gaps) if par_gaps else 6.0

    return {
        "line_spacing": round(avg_spacing, 2),
        "body_font_size": round(avg_font, 1),
        "par_gap": round(avg_gap, 1),
    }


def build_conversion_prompt(parse_result: PDFParseResult) -> str:
    """Builds the comprehensive user prompt including page texts, layout hints, and asset manifests."""
    parts = []

    palette = parse_result.color_palette
    typography = parse_result.typography
    layout = parse_result.layout

    parts.append(f"DOCUMENT METADATA:")
    parts.append(f"- Total Pages: {parse_result.num_pages}")
    parts.append(f"- Detected Type: {parse_result.doc_type_hint.upper()}")
    parts.append(f"- Aspect Ratio: {parse_result.aspect_ratio_hint}")
    parts.append(f"- Suggested Geometry: {parse_result.page_size_hint}")
    parts.append("")

    # Visual Design Blueprint (Colors, Fonts, Layout)
    parts.append("VISUAL DESIGN BLUEPRINT (EXTRACTED FROM PDF TO REPLICATE EXACT LOOK):")
    parts.append(f"- Primary Header / Brand Color: {palette.primary_hex}")
    parts.append(f"- Secondary Subheader Color: {palette.secondary_hex}")
    parts.append(f"- Accent / Highlight Color: {palette.accent_hex}")
    parts.append(f"- Slide / Background Color: {palette.background_hex} ({'Dark Theme' if palette.is_dark_theme else 'Light Theme'})")
    parts.append(f"- Font Family: {typography.title_font} ({'Serif' if typography.is_serif else 'Sans-Serif'})")
    parts.append(f"- Font Package to Use: {typography.font_package}")
    parts.append(f"- Body Font Size: {typography.body_font_size}pt")
    parts.append(f"- Title / Header Font Size: {typography.title_font_size}pt")
    parts.append(f"- Columns: {layout.columns} ({'Two-Column layout' if layout.is_two_column else 'Single-Column'})")
    parts.append(f"- Margins: {layout.margin_left_pt}pt left/right, {layout.margin_top_pt}pt top/bottom")
    parts.append("")

    parts.append("COLOR, TYPOGRAPHY & ALIGNMENT REQUIREMENTS (CRITICAL FOR VISUAL FIDELITY):")
    parts.append("1. Always define and use the extracted brand colors in the preamble:")
    parts.append("   \\usepackage[table,xcdraw]{xcolor}")
    parts.append(f"   \\definecolor{{pdfprimary}}{{HTML}}{{{palette.primary_hex.lstrip('#')}}}")
    parts.append(f"   \\definecolor{{pdfsecondary}}{{HTML}}{{{palette.secondary_hex.lstrip('#')}}}")
    parts.append(f"   \\definecolor{{pdfaccent}}{{HTML}}{{{palette.accent_hex.lstrip('#')}}}")
    if parse_result.doc_type_hint == "beamer":
        parts.append("2. In Beamer, set theme colors to faithfully match the PDF slide deck:")
        parts.append("   \\setbeamercolor{structure}{fg=pdfprimary}")
        parts.append("   \\setbeamercolor{frametitle}{bg=pdfprimary,fg=white}")
        parts.append("   \\setbeamercolor{title}{fg=pdfprimary}")
        parts.append("   \\setbeamercolor{block title}{bg=pdfprimary,fg=white}")
        parts.append("   \\setbeamercolor{block body}{bg=pdfsecondary!10,fg=black}")
    else:
        parts.append("2. In Articles/Reports, style section headings with the primary color:")
        parts.append("   \\usepackage{titlesec}")
        parts.append("   \\titleformat{\\section}{\\color{pdfprimary}\\Large\\bfseries}{\\thesection}{1em}{}")
        parts.append("   \\titleformat{\\subsection}{\\color{pdfprimary}\\large\\bfseries}{\\thesubsection}{1em}{}")
        parts.append("   \\hypersetup{colorlinks=true, linkcolor=pdfprimary, citecolor=pdfaccent, urlcolor=pdfaccent}")
        if layout.is_two_column:
            parts.append("3. The document has a TWO-COLUMN layout. Use \\documentclass[twocolumn]{article} or \\usepackage{multicol}.")
        parts.append(f"4. FONT MATCHING: Include the exact font package in the preamble: {typography.font_package}")
        parts.append(f"   Set document class font size: \\documentclass[{int(round(typography.body_font_size))}pt,...]")
        parts.append("5. ALIGNMENT FIDELITY (MANDATORY):")
        parts.append("   - If a block is marked 'Align: Center', you MUST center it using \\begin{center} ... \\end{center} or \\centering.")
        parts.append("   - Document titles, authors, and affiliations MUST be centered.")
        parts.append("   - ALL figures and tables MUST be centered (\\begin{figure}[htbp] \\centering ...).")
        parts.append("   - Math display equations MUST be centered (\\begin{equation} ... \\end{equation}).")
    parts.append("")

    # Available assets manifest
    if parse_result.embedded_images:
        parts.append("AVAILABLE ASSETS (Saved in 'assets/' directory):")
        for img in parse_result.embedded_images:
            parts.append(f"- assets/{img.filename} (From PDF Page {img.source_page}, Dimensions: {img.width}x{img.height} px)")
        parts.append("Instruction: Use \\includegraphics[width=...]{assets/filename} to include these figures at relevant locations.")
        parts.append("")
    else:
        parts.append("AVAILABLE ASSETS: None detected. Do not include external image files.")
        parts.append("")

    # Page-by-page text & layout breakdown
    parts.append("EXTRACTED PDF PAGES CONTENT & STRUCTURE:")
    for page in getattr(parse_result, "pages", []) or []:
        p_num = getattr(page, "page_number", 1)
        w = getattr(page, "width", 612.0) or 612.0
        h = getattr(page, "height", 792.0) or 792.0
        ar = getattr(page, "aspect_ratio", w / max(1.0, h)) or 1.0
        parts.append(f"=== PAGE {p_num} (Width: {int(w)}pt, Height: {int(h)}pt, AR: {ar:.2f}) ===")

        # Include structured block layout hints with alignment if available
        sblocks = getattr(page, "structured_blocks", []) or []
        if sblocks:
            parts.append("STRUCTURED LAYOUT BLOCKS (HEADINGS, STYLES, COLORS, ALIGNMENTS):")
            for sb in sblocks[:25]:
                btype = getattr(sb, "block_type", "")
                if hasattr(btype, "value"):
                    btype = btype.value
                txt = getattr(sb, "text", "") or ""
                txt = str(txt).strip().replace("\n", " ")
                if len(txt) > 80:
                    txt = txt[:77] + "..."
                fsize = getattr(sb, "font_size", 10.0) or 10.0
                is_bold = bool(getattr(sb, "is_bold", False))
                fcol = getattr(sb, "font_color", "#000000") or "#000000"
                col_hint = f", Color: {fcol}" if fcol.lower() not in ("#000000", "#000", "black") else ""
                style_hint = "Bold" if is_bold else "Normal"
                align_val = getattr(sb, "alignment", "left") or "left"
                align_hint = f", Align: {align_val.capitalize()}"
                parts.append(f"  [{str(btype).upper()}] ({style_hint}, {fsize:.1f}pt{align_hint}{col_hint}): \"{txt}\"")
            parts.append("")

        # Include figures specifically associated with this page
        page_imgs = [img for img in getattr(parse_result, "embedded_images", []) or [] if getattr(img, "source_page", 0) == p_num]
        if page_imgs:
            parts.append("FIGURES ON THIS PAGE:")
            for pimg in page_imgs:
                parts.append(f"  - assets/{pimg.filename} ({pimg.width}x{pimg.height} px)")
            parts.append("")

        page_text = (getattr(page, "text", "") or "").strip()
        if page_text:
            parts.append("FULL PAGE TEXT:")
            parts.append(page_text)
        else:
            parts.append("[Page contains mostly graphics or scanned elements]")
        parts.append("")

    parts.append("TASK:")
    if getattr(parse_result, "doc_type_hint", "") == "beamer":
        parts.append(
            "CRITICAL: The uploaded document is a SLIDE DECK / PRESENTATION (PowerPoint / Keynote / Beamer). "
            "You MUST use \\documentclass[11pt,aspectratio=169]{beamer}. "
            "Every slide/page MUST be enclosed inside \\begin{frame}{Slide Title} ... \\end{frame}. "
            "Apply the extracted colors (pdfprimary, pdfsecondary, pdfaccent) to \\setbeamercolor. "
            "Do NOT use \\documentclass{report} or \\documentclass{article}. "
            "Do NOT use \\chapter or \\section* as slide dividers. "
            "Use \\begin{itemize}, \\begin{columns}, \\begin{block}{...}, and \\includegraphics inside frames to recreate the slides faithfully. "
            "Write ALL slides DIRECTLY inside main.tex. "
            "Return ONLY the structured JSON with 'document_class': 'beamer', 'engine': 'pdflatex', 'files', and 'assets'."
        )
    else:
        parts.append(
            "Generate the complete, editable LaTeX project replicating the layout, structure, and text of this document. "
            "CRITICAL: Write ALL document content, title, abstract, chapters, sections, paragraphs, tables, and equations "
            "DIRECTLY inside main.tex. DO NOT use \\input{sections/...} or \\include{} to split content into separate files. "
            "The entire document must be fully contained and editable directly within main.tex. "
            "Apply the extracted colors (pdfprimary, pdfsecondary, pdfaccent) using \\usepackage{xcolor} and \\titleformat. "
            "Return ONLY the structured JSON with 'document_class', 'engine', 'files', and 'assets'."
        )

    return "\n".join(parts)


def resolve_and_inline_all_inputs(raw_files: List[Dict[str, Any]], parse_result: PDFParseResult) -> List[Dict[str, Any]]:
    """
    Ensures main.tex is 100% self-contained by inlining any \\input{} or \\include{}
    commands. If the referenced file exists in raw_files, its content is inlined.
    If not, it inlines relevant content from the PDF text to prevent missing file compilation errors.
    """
    if not isinstance(raw_files, list):
        return []

    files_map = {
        str(f.get("path", "")).strip(): str(f.get("content", "") or "")
        for f in raw_files
        if isinstance(f, dict) and f.get("path")
    }
    main_tex = files_map.get("main.tex", "")
    if not main_tex or ("\\input" not in main_tex and "\\include" not in main_tex):
        return [f for f in raw_files if isinstance(f, dict)]

    full_pdf_text = str(getattr(parse_result, "full_text", "") or "")

    def replacer(match):
        raw_path = match.group(1).strip()
        candidates = [
            raw_path,
            f"{raw_path}.tex" if not raw_path.endswith(".tex") else raw_path,
            raw_path.replace("sections/", ""),
            f"sections/{raw_path}" if not raw_path.startswith("sections/") else raw_path,
        ]
        for c in candidates:
            if c in files_map and files_map[c].strip():
                logger.info(f"Inlining referenced section '{c}' directly into main.tex")
                return f"\n% --- Inlined section: {c} ---\n" + files_map[c].strip() + "\n"

        base_name = raw_path.rsplit("/", 1)[-1].replace(".tex", "")
        sec_title = base_name.replace("_", " ").title()

        # Check if text snippet for this section exists in PDF full text
        matched_text = ""
        kw = base_name.lower().replace("_", " ")
        if full_pdf_text and kw in full_pdf_text.lower():
            idx = full_pdf_text.lower().find(kw)
            snippet = full_pdf_text[idx:idx + 800].strip()
            snippet = re.sub(r'--- PAGE \d+ ---', '', snippet).strip()
            if len(snippet) > 50:
                matched_text = snippet

        if matched_text:
            return f"\n\\section{{{sec_title}}}\n{matched_text}\n"
        elif any(k in base_name.lower() for k in ["title", "certificate", "abbreviation", "symbol", "acknowledgement"]):
            return f"\n% [{sec_title}]\n"
        else:
            return f"\n\\section{{{sec_title}}}\n"

    new_main_tex = re.sub(r'\\(?:input|include)\{([^}]+)\}', replacer, main_tex)

    # Sanitize titlesec \MakeUppercase bug in modern LaTeX & bad math delimiter on spacing
    sanitized_lines = []
    for line in new_main_tex.split("\n"):
        if "titleformat" in line and "\\MakeUppercase" in line:
            line = line.replace("\\MakeUppercase", "")
        elif "\\MakeUppercase" in line and any(k in line for k in ["centering", "normalfont", "bfseries"]):
            line = line.replace("\\MakeUppercase", "")
        if "\\\\" in line and any(unit in line for unit in ["cm]", "in]", "mm]", "pt]", "em]"]):
            line = re.sub(r'\\\\\s*\[(\d+(?:\.\d+)?(?:cm|in|mm|pt|em|ex))\]', r'\\par\\vspace{\1}', line)
        sanitized_lines.append(line)
    new_main_tex = "\n".join(sanitized_lines)

    result_files = []
    for f in raw_files:
        if isinstance(f, dict):
            if f.get("path") == "main.tex":
                result_files.append({"path": "main.tex", "content": new_main_tex})
            else:
                result_files.append(f)

    return result_files


def deterministic_repair_latex(tex_code: str, parse_result: PDFParseResult) -> str:
    r"""
    Applies deterministic rules to heal broken LaTeX:
    1. Injects required packages if corresponding commands are present (xcolor, graphicx, amsmath, booktabs, geometry, titlesec, etc.)
    2. Adds color definitions matching the PDF palette
    3. Auto-balances open vs closing braces
    4. Auto-closes unclosed environments (\begin{frame}, \begin{document}, \begin{table}, etc.)
    5. Deduplicates \label{...} tags
    6. Sanitizes \MakeUppercase in \titleformat and bad math delimiter spacing \\[...cm]
    7. Auto-wraps wide tables with \resizebox{\linewidth}{!}{...}
    """
    if not tex_code:
        return tex_code

    s = tex_code

    # 1. Ensure \documentclass exists
    if "\\documentclass" not in s:
        doc_class = "beamer" if parse_result.doc_type_hint == "beamer" else "article"
        s = f"\\documentclass{{{doc_class}}}\n{s}"

    # 2. Check and inject missing packages before \begin{document}
    preamble_end = s.find("\\begin{document}")
    if preamble_end == -1:
        s = s.strip() + "\n\\begin{document}\n"
        preamble_end = s.find("\\begin{document}")

    preamble = s[:preamble_end]
    body = s[preamble_end:]

    packages_to_inject = []

    # xcolor
    if ("\\definecolor" in s or "\\color" in s or "\\textcolor" in s or "\\rowcolor" in s or "\\setbeamercolor" in s) and "\\usepackage{xcolor}" not in preamble and "xcolor" not in preamble:
        if parse_result.doc_type_hint != "beamer":
            packages_to_inject.append("\\usepackage[table,xcdraw]{xcolor}")

    # graphicx
    if ("\\includegraphics" in s) and "\\usepackage{graphicx}" not in preamble and "graphicx" not in preamble:
        if parse_result.doc_type_hint != "beamer":
            packages_to_inject.append("\\usepackage{graphicx}")

    # amsmath, amssymb
    if ("\\align" in s or "\\begin{equation" in s or "\\text{" in s) and "amsmath" not in preamble:
        packages_to_inject.append("\\usepackage{amsmath,amssymb}")

    # booktabs
    if ("\\toprule" in s or "\\midrule" in s or "\\bottomrule" in s) and "booktabs" not in preamble:
        packages_to_inject.append("\\usepackage{booktabs}")

    # geometry & parskip for non-beamer
    if parse_result.doc_type_hint != "beamer":
        if "geometry" not in preamble:
            packages_to_inject.append("\\usepackage[margin=1in]{geometry}")
        if "parskip" not in preamble:
            packages_to_inject.append("\\usepackage{parskip}")

    # titlesec if \titleformat is used
    if "\\titleformat" in s and "titlesec" not in preamble and parse_result.doc_type_hint != "beamer":
        packages_to_inject.append("\\usepackage{titlesec}")

    # hyperref
    if ("\\href" in s or "\\url" in s or "\\hypersetup" in s) and "hyperref" not in preamble:
        packages_to_inject.append("\\usepackage{hyperref}")

    # Font package matching original PDF typography
    typography = getattr(parse_result, "typography", None)
    if typography and typography.font_package and parse_result.doc_type_hint != "beamer":
        pkg_core = "newtxtext" if typography.is_serif else ("roboto" if "roboto" in typography.font_package else "helvet")
        if pkg_core not in preamble:
            packages_to_inject.append(typography.font_package)

    # Inject color definitions matching the PDF palette if not already defined
    palette = getattr(parse_result, "color_palette", None)
    if palette:
        p_hex = palette.primary_hex.lstrip("#")
        s_hex = palette.secondary_hex.lstrip("#")
        a_hex = palette.accent_hex.lstrip("#")
        if "pdfprimary" not in preamble:
            packages_to_inject.append(f"\\definecolor{{pdfprimary}}{{HTML}}{{{p_hex}}}")
        if "pdfsecondary" not in preamble:
            packages_to_inject.append(f"\\definecolor{{pdfsecondary}}{{HTML}}{{{s_hex}}}")
        if "pdfaccent" not in preamble:
            packages_to_inject.append(f"\\definecolor{{pdfaccent}}{{HTML}}{{{a_hex}}}")

    if packages_to_inject:
        inj_str = "\n".join(packages_to_inject) + "\n"
        doc_cls_match = re.search(r"\\documentclass(?:\[[^\]]*\])?\{[^}]+\}", preamble)
        if doc_cls_match:
            insert_pos = doc_cls_match.end()
            preamble = preamble[:insert_pos] + "\n" + inj_str + preamble[insert_pos:]
        else:
            preamble = inj_str + preamble

    s = preamble + body

    # 3. Sanitize titlesec \MakeUppercase bug & spacing delimiter \\[...cm]
    lines = s.split("\n")
    for idx, line in enumerate(lines):
        if ("\\titleformat" in line or "\\section" in line or "\\subsection" in line or "\\centering" in line) and "\\MakeUppercase" in line:
            lines[idx] = line.replace("\\MakeUppercase", "")
    s = "\n".join(lines)
    s = re.sub(r'\\\\\s*\[(\d+(?:\.\d+)?(?:cm|in|mm|pt|em|ex))\]', r'\\par\\vspace{\1}', s)


    # 4. Auto-balance unmatched braces
    open_b = s.count("{")
    close_b = s.count("}")
    if open_b > close_b:
        missing = open_b - close_b
        if "\\end{document}" in s:
            s = s.replace("\\end{document}", ("}" * missing) + "\n\\end{document}")
        else:
            s = s + ("}" * missing)

    # 5. Auto-close environments
    if "\\begin{frame}" in s:
        bf_count = s.count("\\begin{frame}")
        ef_count = s.count("\\end{frame}")
        if bf_count > ef_count:
            parts = re.split(r"(\\begin\{frame\})", s)
            reconstructed = [parts[0]]
            for i in range(1, len(parts), 2):
                frame_token = parts[i]
                frame_body = parts[i+1] if i+1 < len(parts) else ""
                if "\\end{frame}" not in frame_body:
                    if "\\end{document}" in frame_body:
                        frame_body = frame_body.replace("\\end{document}", "\\end{frame}\n\\end{document}")
                    else:
                        frame_body = frame_body.rstrip() + "\n\\end{frame}\n"
                reconstructed.append(frame_token + frame_body)
            s = "".join(reconstructed)

    env_names = ["figure", "table", "tabular", "itemize", "enumerate", "columns", "column"]
    for env in env_names:
        b_cnt = len(re.findall(rf"\\begin\{{{env}(?:\*|\[[^\]]*\])?\}}", s))
        e_cnt = len(re.findall(rf"\\end\{{{env}\*?\}}", s))
        if b_cnt > e_cnt:
            diff = b_cnt - e_cnt
            close_tags = "\n" + "\n".join([f"\\end{{{env}}}" for _ in range(diff)])
            if "\\end{document}" in s:
                s = s.replace("\\end{document}", close_tags + "\n\\end{document}")
            else:
                s = s + close_tags

    # 6. Ensure \end{document} exists
    if "\\end{document}" not in s:
        s = s.strip() + "\n\\end{document}\n"

    # 7. Deduplicate duplicate \label{...} definitions
    label_matches = list(re.finditer(r"\\label\{([^}]+)\}", s))
    if label_matches:
        seen_labels: Dict[str, int] = {}
        for m in label_matches:
            lbl = m.group(1).strip()
            seen_labels[lbl] = seen_labels.get(lbl, 0) + 1

        dupes = {l for l, c in seen_labels.items() if c > 1}
        if dupes:
            counts: Dict[str, int] = {}
            def label_dedup_repl(match):
                l_name = match.group(1).strip()
                if l_name in dupes:
                    cnt = counts.get(l_name, 0) + 1
                    counts[l_name] = cnt
                    if cnt > 1:
                        return f"\\label{{{l_name}_{cnt}}}"
                return match.group(0)

            s = re.sub(r"\\label\{([^}]+)\}", label_dedup_repl, s)

    return s


def test_and_auto_repair_compilation(
    conversion_data: Dict[str, Any],
    parse_result: PDFParseResult,
    model: str,
    progress_callback: Optional[Callable[[str, str], None]] = None,
    max_retries: int = 2,
) -> Tuple[Dict[str, Any], bool, str, Optional[str]]:
    """
    Tests compilation of the generated LaTeX files.
    Applies deterministic auto-repairs first, then compiles with compile_latex.
    If compilation fails, queries LLM with the compiler error log to fix issues (up to max_retries).
    Returns (repaired_conversion_data, success, log, pdf_base64).
    """
    current_data = conversion_data
    if "files" in current_data:
        current_data["files"] = resolve_and_inline_all_inputs(current_data["files"], parse_result)

    # Deterministic pre-repair pass on all files
    for f in current_data.get("files", []):
        if isinstance(f, dict) and f.get("path") == "main.tex" and f.get("content"):
            f["content"] = deterministic_repair_latex(f["content"], parse_result)

    for attempt in range(max_retries + 1):
        files = current_data.get("files", [])
        main_tex = next((f["content"] for f in files if isinstance(f, dict) and f.get("path") == "main.tex"), "")
        if not main_tex:
            return current_data, False, "No main.tex file found in conversion result.", None

        # Prepare images and extra files payload for compiler
        extra_files = []
        for f in files:
            if isinstance(f, dict) and f.get("path") != "main.tex":
                extra_files.append({
                    "filename": f.get("path"),
                    "data": base64.b64encode(str(f.get("content", "")).encode("utf-8")).decode("utf-8")
                })

        images_payload = []
        for img in getattr(parse_result, "embedded_images", []) or []:
            b64_data = base64.b64encode(img.data_bytes).decode("utf-8")
            images_payload.append({"filename": f"assets/{img.filename}", "data": b64_data})
            images_payload.append({"filename": img.filename, "data": b64_data})

        engine = current_data.get("engine", "latexmk")

        if progress_callback:
            if attempt == 0:
                progress_callback("compiling", "Verifying LaTeX compilation...")
            else:
                progress_callback("compiling", f"Verifying corrected LaTeX (attempt {attempt}/{max_retries})...")

        comp_result = compile_latex(
            latex_code=main_tex,
            engine=engine,
            images=images_payload,
            files=extra_files,
            project_id="pdf_verify_temp"
        )

        if comp_result.get("success"):
            logger.info(f"PDF LaTeX compilation verified successfully on attempt {attempt}.")
            return current_data, True, comp_result.get("log", "Compilation successful"), comp_result.get("pdf_base64")

        log = comp_result.get("log", "Compilation failed with unknown error.")
        logger.warning(f"Compilation failed on attempt {attempt}: {log[:300]}")

        # If retries left, ask LLM to fix the compilation error
        if attempt < max_retries:
            if progress_callback:
                progress_callback("repairing", f"Fixing compilation error (attempt {attempt + 1}/{max_retries})...")

            repair_prompt = (
                f"The generated LaTeX project failed to compile with the following error log:\n\n"
                f"```\n{log[-1500:]}\n```\n\n"
                f"CURRENT main.tex:\n"
                f"```latex\n{main_tex[:5000]}\n```\n\n"
                f"Please fix all LaTeX compilation errors, missing packages, syntax errors, or unclosed environments. "
                f"Return the complete corrected JSON object according to the original schema."
            )

            try:
                repair_messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": repair_prompt},
                ]
                provider = provider_router.route(model)
                res = provider.chat(repair_messages, model=model, temperature=0.1, max_tokens=32768)
                new_raw = res.get("content", "")
                parsed_repair = parse_llm_json_response(new_raw)
                if isinstance(parsed_repair, dict) and parsed_repair.get("files"):
                    # Deterministic repair on repaired output
                    for f in parsed_repair["files"]:
                        if isinstance(f, dict) and f.get("path") == "main.tex" and f.get("content"):
                            f["content"] = deterministic_repair_latex(f["content"], parse_result)
                    current_data = parsed_repair
            except Exception as repair_err:
                logger.error(f"Auto-repair LLM call failed: {repair_err}")
                break

    return current_data, False, log, None


def convert_pdf_to_latex(
    parse_result: PDFParseResult,
    model: Optional[str] = None,
    progress_callback: Optional[Callable[[str, str], None]] = None,
    auto_repair: bool = True,
) -> ConversionResult:
    """
    Main conversion orchestrator:
    - Builds LLM prompt from parse_result with visual styling blueprint & structured blocks
    - Calls LLM via provider_router with token budget escalation and truncation detection
    - Parses structured files and assets safely
    - Automatically tests compilation and applies multi-stage auto-repair
    - Runs page-by-page visual verification loop with pure-NumPy SSIM comparison
    """
    target_model = model or provider_router.get_default_model()

    user_prompt = build_conversion_prompt(parse_result)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    provider = provider_router.route(target_model)
    logger.info(f"Converting PDF with provider {provider.get_provider_name()} (model={target_model})...")

    # Token budget escalation loop to prevent truncation
    token_budgets = [16384, 32768, 65536]
    parsed_json = None
    last_error = ""
    retry_count = 0

    for attempt, max_tokens in enumerate(token_budgets):
        retry_count = attempt
        if progress_callback:
            if attempt == 0:
                progress_callback("generating_latex", f"Synthesizing editable LaTeX via {target_model}...")
            else:
                progress_callback("generating_latex", f"Retrying with escalated token budget ({max_tokens} tokens)...")

        attempt_messages = list(messages)
        if attempt > 0:
            attempt_messages.append({
                "role": "user",
                "content": (
                    f"Previous attempt was incomplete or truncated ({last_error}). "
                    f"Please generate the COMPLETE LaTeX document without truncating. "
                    f"Write all pages and sections directly inside main.tex."
                )
            })

        try:
            llm_resp = provider.chat(
                messages=attempt_messages,
                model=target_model,
                temperature=0.1,
                max_tokens=max_tokens,
            )
        except Exception as e:
            logger.warning(f"LLM chat call failed on attempt {attempt}: {e}")
            last_error = str(e)
            continue

        raw_content = llm_resp.get("content", "")
        finish_reason = llm_resp.get("finish_reason", "")
        if not raw_content:
            last_error = "Empty response from LLM"
            continue

        if finish_reason == "length":
            logger.warning(f"LLM output truncated (finish_reason='length') at {max_tokens} tokens.")
            last_error = f"Output truncated at {max_tokens} tokens"
            continue

        try:
            parsed = parse_llm_json_response(raw_content)
        except ValueError as ve:
            logger.warning(f"Failed to parse LLM JSON on attempt {attempt}: {ve}")
            last_error = str(ve)
            continue

        if not isinstance(parsed, dict) or not parsed.get("files"):
            last_error = "No valid files found in parsed LLM response"
            continue

        # Check for truncation in main.tex
        main_tex = next((f.get("content", "") for f in parsed.get("files", []) if isinstance(f, dict) and f.get("path") == "main.tex"), "")
        is_trunc, trunc_reason = is_truncated_latex(main_tex, parse_result)
        if is_trunc:
            logger.warning(f"Synthesized LaTeX detected as truncated: {trunc_reason}")
            last_error = trunc_reason
            continue

        parsed_json = parsed
        break

    if not parsed_json:
        raise RuntimeError(f"Failed to generate complete LaTeX document after {len(token_budgets)} attempts. Last error: {last_error}")

    if "files" in parsed_json:
        parsed_json["files"] = resolve_and_inline_all_inputs(parsed_json["files"], parse_result)

    # Auto-repair verification pass
    compiled_ok = False
    comp_log = ""
    pdf_base64 = None
    if auto_repair:
        parsed_json, compiled_ok, comp_log, pdf_base64 = test_and_auto_repair_compilation(
            conversion_data=parsed_json,
            parse_result=parse_result,
            model=target_model,
            progress_callback=progress_callback,
            max_retries=2,
        )

    # Page-by-page visual verification loop using SSIM
    flagged_pages: List[int] = []
    page_fidelity_scores: Dict[int, float] = {}
    visual_defects: List[Dict[str, Any]] = []

    if compiled_ok and pdf_base64:
        if progress_callback:
            progress_callback("visual_verification", "Performing page-by-page visual fidelity verification...")
        try:
            compiled_pdf_bytes = base64.b64decode(pdf_base64)
            comp_doc = fitz.open(stream=compiled_pdf_bytes, filetype="pdf")
            num_comp_pages = len(comp_doc)

            for page in getattr(parse_result, "pages", []) or []:
                p_num = getattr(page, "page_number", 1)
                orig_png = getattr(page, "rendered_150dpi_png", None) or getattr(page, "rendered_300dpi_png", None)
                if not orig_png or p_num > num_comp_pages:
                    continue

                try:
                    comp_page = comp_doc[p_num - 1]
                    mat = fitz.Matrix(150.0 / 72.0, 150.0 / 72.0)
                    pix = comp_page.get_pixmap(matrix=mat, alpha=False)
                    gen_png = pix.tobytes("png")

                    p_report = fidelity_checker.compute_pixel_fidelity(
                        orig_page_png=orig_png,
                        gen_page_png=gen_png,
                        page_num=p_num,
                        threshold=0.70,
                    )
                    page_fidelity_scores[p_num] = p_report.fidelity_score
                    if not p_report.passed:
                        flagged_pages.append(p_num)
                        visual_defects.extend(p_report.defects)
                except Exception as p_err:
                    logger.warning(f"Error checking page {p_num} visual fidelity: {p_err}")

            comp_doc.close()

            # Attempt single visual calibration pass if pages flagged and auto_repair enabled
            if flagged_pages and auto_repair:
                logger.info(f"Pages {flagged_pages} flagged for visual misalignment. Attempting calibration pass...")
                if progress_callback:
                    progress_callback("visual_calibration", f"Calibrating visual alignment for flagged pages {flagged_pages}...")

                from .layout_verifier import analyze_page_positional_drift
                drift_notes = []
                for fp in flagged_pages[:3]:
                    matched_page = next((p for p in getattr(parse_result, "pages", []) if getattr(p, "page_number", None) == fp), None)
                    if matched_page:
                        d_info = analyze_page_positional_drift(matched_page, compiled_pdf_bytes, page_number=fp)
                        drift_notes.append(
                            f"- Page {fp}: top_drift={d_info.get('top_drift')}pt, "
                            f"left_drift={d_info.get('left_drift')}pt, height_diff={d_info.get('height_diff')}pt"
                        )

                curr_main = next((f.get("content", "") for f in parsed_json.get("files", []) if isinstance(f, dict) and f.get("path") == "main.tex"), "")
                calib_prompt = (
                    f"Visual verification detected layout misalignment on pages {flagged_pages}.\n"
                    f"Page SSIM scores: {page_fidelity_scores}\n"
                    f"Measured layout drifts:\n" + "\n".join(drift_notes) + "\n"
                    f"Key visual defects:\n" + "\n".join(f"- {d.get('description')}" for d in visual_defects[:4]) + "\n\n"
                    f"CURRENT main.tex:\n```latex\n{curr_main[:4000]}\n```\n\n"
                    f"Please adjust the spacing, geometry, figure sizing, or \\vspace offsets in main.tex to better align with the original PDF.\n"
                    f"Return the complete corrected JSON object."
                )

                try:
                    calib_messages = [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": calib_prompt},
                    ]
                    calib_res = provider.chat(calib_messages, model=target_model, temperature=0.1, max_tokens=32768)
                    calib_raw = calib_res.get("content", "")
                    parsed_calib = parse_llm_json_response(calib_raw)
                    if isinstance(parsed_calib, dict) and parsed_calib.get("files"):
                        test_files, test_ok, test_log, test_b64 = test_and_auto_repair_compilation(
                            conversion_data=parsed_calib,
                            parse_result=parse_result,
                            model=target_model,
                            progress_callback=progress_callback,
                            max_retries=1,
                        )
                        if test_ok and test_b64:
                            re_comp_bytes = base64.b64decode(test_b64)
                            re_doc = fitz.open(stream=re_comp_bytes, filetype="pdf")
                            improved_any = False
                            for fp in list(flagged_pages):
                                if fp <= len(re_doc):
                                    p_data = next((p for p in getattr(parse_result, "pages", []) if getattr(p, "page_number", None) == fp), None)
                                    orig_p_img = getattr(p_data, "rendered_150dpi_png", None) or getattr(p_data, "rendered_300dpi_png", None)
                                    if orig_p_img:
                                        mat = fitz.Matrix(150.0 / 72.0, 150.0 / 72.0)
                                        re_gen_png = re_doc[fp - 1].get_pixmap(matrix=mat, alpha=False).tobytes("png")
                                        re_report = fidelity_checker.compute_pixel_fidelity(orig_p_img, re_gen_png, page_num=fp)
                                        if re_report.fidelity_score >= page_fidelity_scores.get(fp, 0.0):
                                            page_fidelity_scores[fp] = re_report.fidelity_score
                                            improved_any = True
                                            if re_report.passed:
                                                flagged_pages.remove(fp)
                            re_doc.close()
                            if improved_any:
                                parsed_json = test_files
                                compiled_ok = True
                                comp_log = test_log
                                pdf_base64 = test_b64
                except Exception as calib_err:
                    logger.warning(f"Visual calibration pass skipped due to error: {calib_err}")
        except Exception as vis_err:
            logger.warning(f"Visual verification loop error: {vis_err}")

    # Build ProjectFiles list
    raw_files = resolve_and_inline_all_inputs(parsed_json.get("files", []), parse_result)
    project_files: List[ProjectFile] = []
    has_main_tex = False

    for f in raw_files:
        if isinstance(f, dict):
            p = str(f.get("path", "")).strip()
            c = str(f.get("content", "") or "")
            if p == "main.tex":
                has_main_tex = True
            if p and c:
                project_files.append(ProjectFile(path=p, content=c))

    # Fallback if main.tex was missing
    if not has_main_tex:
        logger.warning("No main.tex in parsed files, using default document wrapper.")
        default_tex = (
            "\\documentclass{article}\n\\usepackage[utf8]{inputenc}\n\\usepackage{amsmath,amssymb,graphicx}\n"
            "\\begin{document}\n" + (getattr(parse_result, "full_text", "") or "Converted Document") + "\n\\end{document}"
        )
        project_files.insert(0, ProjectFile(path="main.tex", content=default_tex))

    # Map asset files
    assets: List[AssetFile] = [
        AssetFile(
            filename=img.filename,
            data_bytes=img.data_bytes,
            source_page=img.source_page,
            ext=img.ext,
            mime_type=img.mime_type,
        )
        for img in getattr(parse_result, "embedded_images", []) or []
    ]

    # Heuristic fidelity verification check
    main_tex_content = next((f.content for f in project_files if f.path == "main.tex"), "")
    fidelity_report = fidelity_checker.compute_heuristic_fidelity(
        original_text=getattr(parse_result, "full_text", "") or "",
        generated_latex=main_tex_content,
        num_expected_figures=len(getattr(parse_result, "embedded_images", []) or []),
        num_rendered_figures=main_tex_content.count(r"\includegraphics"),
    )

    if page_fidelity_scores:
        avg_pixel_score = sum(page_fidelity_scores.values()) / len(page_fidelity_scores)
        final_fidelity_score = round(0.7 * avg_pixel_score + 0.3 * fidelity_report.fidelity_score, 2)
        combined_defects = fidelity_report.defects + visual_defects
    else:
        final_fidelity_score = fidelity_report.fidelity_score
        combined_defects = fidelity_report.defects

    if progress_callback:
        progress_callback("fidelity_check", f"Visual & structural fidelity score: {int(final_fidelity_score * 100)}%")

    return ConversionResult(
        document_class=parsed_json.get("document_class", getattr(parse_result, "doc_type_hint", "article")),
        engine=parsed_json.get("engine", "pdflatex"),
        files=project_files,
        assets=assets,
        compiled_successfully=compiled_ok,
        compile_log=comp_log,
        retry_count=retry_count,
        fidelity_score=final_fidelity_score,
        fidelity_defects=combined_defects,
        flagged_pages=flagged_pages,
        page_fidelity_scores=page_fidelity_scores,
    )
