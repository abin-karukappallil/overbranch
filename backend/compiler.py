import tempfile
import subprocess
import base64
import os
import re
import io
import time
import shutil
import sys
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

logger = logging.getLogger("compiler")


def _run_tex(cmd, *, cwd, timeout, env, capture_output=True):
    """
    Run a TeX engine subprocess and return its output as decoded strings.

    Uses bytes mode instead of ``text=True`` because pdflatex/xelatex/lualatex
    can emit non-UTF-8 bytes in their log output (Latin-1 font metric names,
    Windows-1252 file paths, raw binary from corrupted aux files).  Python's
    ``text=True`` defaults to strict UTF-8 decoding, which raises
    ``UnicodeDecodeError`` — surfaced as ``[INFRASTRUCTURE ERROR] Command
    'pdflatex' failed: 'utf-8' codec can't decode byte 0xed …``.  That
    exception was caught by the generic handler and treated as a compile
    failure, even when pdflatex had already produced a valid PDF.

    By reading raw bytes and decoding with ``errors='replace'``, invalid bytes
    become U+FFFD (�) instead of crashing, and the PDF is still picked up.
    """
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=capture_output,
        timeout=timeout,
        env=env,
    )
    if isinstance(proc.stdout, bytes):
        proc.stdout = proc.stdout.decode("utf-8", errors="replace")
    elif proc.stdout is None:
        proc.stdout = ""
    if isinstance(proc.stderr, bytes):
        proc.stderr = proc.stderr.decode("utf-8", errors="replace")
    elif proc.stderr is None:
        proc.stderr = ""
    return proc


_MAGIC_PROGRAM_RE = re.compile(
    r"^\s*%\s*!\s*TEX\s+(?:TS-)?program\s*=\s*(pdflatex|xelatex|lualatex)\b",
    re.IGNORECASE | re.MULTILINE,
)
_DEFAULT_ENGINES = {"", "latexmk", "pdflatex", "pdf", "latex"}


def detect_magic_engine(latex_code: str) -> Optional[str]:
    """Returns the engine named by a `% !TEX program = ...` magic comment in the file header, if any."""
    head = "\n".join((latex_code or "").splitlines()[:20])
    m = _MAGIC_PROGRAM_RE.search(head)
    return m.group(1).lower() if m else None


_TEX_ERROR_RE = re.compile(r"^(?:\S+\.tex:\d+: .*|! .*)$", re.MULTILINE)


def tex_errors(output: str) -> List[str]:
    """Error lines from a nonstopmode / -file-line-error TeX run (a PDF can still be produced)."""
    return list(dict.fromkeys(m.group(0).strip() for m in _TEX_ERROR_RE.finditer(output or "")))[:20]


def _overfull_boxes(output: str) -> List[Dict[str, Any]]:
    try:
        from latex_layout.overflow import parse_overfull
        return parse_overfull(output)
    except Exception:
        return []


_UNICODE_ENGINE_MARKERS = (
    "{fontspec}", "{unicode-math}", "{polyglossia}",
    r"\setmainfont", r"\setsansfont", r"\setmonofont",
    r"\setmathfont", r"\newfontface", r"\newfontfamily",
    r"\setmainlanguage", r"\directlua", r"\luadirect",
)


def needs_unicode_engine(latex_code: str) -> bool:
    """
    True when the document can only be compiled with XeLaTeX / LuaLaTeX.

    LLM-generated documents that compile on Overleaf (where the project's
    compiler is set to XeLaTeX) routinely load `fontspec`, `unicode-math`,
    `polyglossia`, or select a system font. Under pdfLaTeX those fail with a
    fatal "requires XeTeX or LuaTeX" error, so when the caller left the engine
    at its default we switch to XeLaTeX automatically.
    """
    code = latex_code or ""
    return any(m in code for m in _UNICODE_ENGINE_MARKERS)


def is_heavy_document(latex_code: str) -> bool:
    """Documents with lots of TikZ/pgfplots or great length need a longer budget."""
    code = latex_code or ""
    if len(code) > 60000:
        return True
    if "pgfplots" in code or r"\addplot" in code:
        return True
    if (code.count(r"\begin{tikzpicture}") + code.count(r"\tikz")) >= 6:
        return True
    return False


def _bibliography_backend(latex_code: str) -> Optional[str]:
    """
    Which bibliography tool a direct (non-latexmk) compile must run, or None.

    `biblatex` defaults to biber unless `backend=bibtex` is set; a classic
    `\\bibliography{...}` + `\\bibliographystyle{...}` uses bibtex.
    """
    code = latex_code or ""
    has_biblatex = "biblatex" in code and r"\usepackage" in code
    if has_biblatex or r"\addbibresource" in code or r"\printbibliography" in code:
        return "bibtex" if "backend=bibtex" in code else "biber"
    if r"\bibliography{" in code or r"\bibliographystyle{" in code:
        return "bibtex"
    return None


def augment_path_for_latex():
    """Augments system PATH with common MiKTeX and TeX Live installation locations on Windows."""
    if sys.platform == "win32":
        home = os.path.expanduser("~")
        common_win_paths = [
            r"C:\Program Files\MiKTeX\miktex\bin\x64",
            r"C:\Program Files (x86)\MiKTeX\miktex\bin\x64",
            r"C:\Program Files\MiKTeX\miktex\bin",
            os.path.join(home, r"AppData\Local\Programs\MiKTeX\miktex\bin\x64"),
            r"C:\texlive\2026\bin\windows",
            r"C:\texlive\2025\bin\windows",
            r"C:\texlive\2024\bin\windows",
            r"C:\texlive\2023\bin\windows",
        ]

        current_path = os.environ.get("PATH", "")
        found_paths = [p for p in common_win_paths if os.path.exists(p)]

        if found_paths:
            extra_path = os.path.pathsep.join(found_paths)
            if extra_path not in current_path:
                os.environ["PATH"] = f"{extra_path}{os.path.pathsep}{current_path}"


def clean_tex_syntax(text: str) -> str:
    """Strips TeX formatting commands, dimensions, font sizes, and environment syntax while preserving readable content."""
    if not text:
        return ""
    
    s = text.strip()
    
    # Ignore comments
    if s.startswith('%'):
        return ""
    s = re.sub(r'%.*$', '', s)

    # Ignore markdown code blocks or code fences if present in TeX source
    if s.startswith('```') or s.endswith('```'):
        return ""

    # Ignore TeX setup commands, macro definitions, Beamer color settings, and TikZ
    preamble_patterns = [
        r'^\s*\\documentclass',
        r'^\s*\\usepackage',
        r'^\s*\\renewcommand',
        r'^\s*\\newcommand',
        r'^\s*\\setlength',
        r'^\s*\\addtolength',
        r'^\s*\\cft',
        r'^\s*\\usetikzlibrary',
        r'^\s*\\definecolor',
        r'^\s*\\setbeamercolor',
        r'^\s*\\setbeamertemplate',
        r'^\s*\\setbeamerfont',
        r'^\s*\\titlegraphic',
        r'^\s*\\lstdefinestyle',
        r'^\s*\\lstset',
        r'^\s*\\geometry',
        r'^\s*\\fancy',
        r'^\s*\\captionsetup',
        r'^\s*\\pagestyle',
        r'^\s*\\thispagestyle',
        r'^\s*\\pagenumbering',
        r'^\s*\\setcounter',
        r'^\s*\\hypersetup',
        r'^\s*\\bibliographystyle',
        r'^\s*\\bibliography',
        r'^\s*\\usetheme',
        r'^\s*\\usecolortheme',
        r'^\s*\\usefonttheme',
        r'^\s*\\useoutertheme',
        r'^\s*\\useinnertheme',
        r'^\s*\\onehalfspacing',
        r'^\s*\\doublespacing',
        r'^\s*\\singlespacing',
        r'^\s*\\sloppy',
        r'^\s*\\headrulewidth',
        r'^\s*\\footrulewidth',
        r'^\s*\\node',
        r'^\s*\\draw',
        r'^\s*\\path',
        r'^\s*\\fill',
        r'^\s*\\clip',
        r'^\s*\\pgf',
        r'^\s*\\tikz',
        r'^\s*\\hrule',
        r'^\s*\\vrule',
        r'^\s*\\vspace',
        r'^\s*\\hspace',
        r'^\s*\\rule',
        r'^\s*\\centering',
        r'^\s*\\raggedright',
        r'^\s*\\raggedleft',
        r'^\s*\\vfill',
        r'^\s*\\hfill',
        r'^\s*\\pagebreak',
        r'^\s*\\clearpage',
        r'^\s*\\newpage',
    ]
    for pat in preamble_patterns:
        if re.search(pat, s, re.IGNORECASE):
            return ""

    # Ignore key=value style settings (e.g. backgroundcolor=..., commentstyle=..., tabsize=2, fg=white, bg=primary)
    if (re.match(r'^[a-zA-Z0-9_-]+\s*=\s*.*$', s) or re.match(r'^[a-zA-Z0-9_-]+,?\s*$', s)) and not s.startswith('•') and not s.startswith('\\item') and len(s.split()) < 4:
        return ""

    # Ignore standalone option brackets or raw dimensions like "[display]", "0pt", "40pt", "1822"
    if re.match(r'^\s*\[[^\]]*\]\s*$', s) or re.match(r'^\s*(?:\d+(?:\.\d+)?(?:cm|mm|in|pt|em|ex)?|\d+)\s*$', s):
        return ""

    # Replace inline formatting tags with temporary tokens before HTML escaping
    s = re.sub(r'\\textbf\{([^}]+)\}', r'___BOLD___\1___ENDBOLD___', s)
    s = re.sub(r'\\textit\{([^}]+)\}', r'___ITALIC___\1___ENDITALIC___', s)
    s = re.sub(r'\\cite\{([^}]+)\}', r'[\1]', s)
    s = re.sub(r'\\ref\{([^}]+)\}', r'(\1)', s)
    s = re.sub(r'\\item\s*', '• ', s)

    # Remove font size / spacing / style commands
    s = re.sub(r'\\fontsize\{[^}]*\}\{[^}]*\}', '', s)
    s = re.sub(r'\\selectfont', '', s)
    s = re.sub(r'\\vspace\*?\{[^}]*\}', '', s)
    s = re.sub(r'\\hspace\*?\{[^}]*\}', '', s)
    s = re.sub(r'\\setlength\{[^}]*\}\{[^}]*\}', '', s)
    s = re.sub(r'\\addtolength\{[^}]*\}\{[^}]*\}', '', s)
    s = re.sub(r'\\geometry\{[^}]*\}', '', s)
    s = re.sub(r'\\addcontentsline\{[^}]*\}\{[^}]*\}\{[^}]*\}', '', s)
    s = re.sub(r'\\captionsetup\[[^\]]*\]\{[^}]*\}', '', s)
    s = re.sub(r'\\captionsetup\{[^}]*\}', '', s)
    s = re.sub(r'\\color\{[^}]*\}', '', s)
    s = re.sub(r'\\textcolor\{[^}]*\}\{([^}]*)\}', r'\1', s)

    # Remove structural & environment commands
    s = re.sub(r'\\begin\{[^}]*\}(?:\[[^\]]*\])?(?:\{[^}]*\})*', '', s)
    s = re.sub(r'\\end\{[^}]*\}', '', s)
    s = re.sub(r'\\thispagestyle\{[^}]*\}', '', s)
    s = re.sub(r'\\pagestyle\{[^}]*\}', '', s)
    s = re.sub(r'\\pagenumbering\{[^}]*\}', '', s)

    # Remove image options like [width=4cm]
    s = re.sub(r'\[width=[^\]]+\]', '', s)
    s = re.sub(r'\[height=[^\]]+\]', '', s)

    # Remove remaining \command{arg} -> arg
    s = re.sub(r'\\[a-zA-Z]+\*?\{([^}]*)\}', r'\1', s)
    # Remove remaining standalone \command
    s = re.sub(r'\\[a-zA-Z]+\*?', '', s)
    
    # Remove leftover braces and TeX symbols
    s = re.sub(r'[{}\\]', '', s)
    
    # HTML escape ampersands and angle brackets to prevent ReportLab paraparser syntax errors
    s = s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # Re-inject ReportLab supported HTML tags
    s = s.replace('___BOLD___', '<b>').replace('___ENDBOLD___', '</b>')
    s = s.replace('___ITALIC___', '<i>').replace('___ENDITALIC___', '</i>')

    return s.strip()


def generate_beamer_pdf(latex_code: str) -> str:
    """Renders LaTeX Beamer / Presentation documents into sleek multi-slide PDFs."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    slide_title_style = ParagraphStyle(
        'SlideTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1e1b4b'),
        fontName='Helvetica-Bold',
        spaceAfter=12
    )

    bullet_style = ParagraphStyle(
        'SlideBullet',
        parent=styles['BodyText'],
        fontSize=13,
        leading=18,
        textColor=colors.HexColor('#334155'),
        spaceAfter=8,
        leftIndent=15
    )

    slide_body_style = ParagraphStyle(
        'SlideBody',
        parent=styles['BodyText'],
        fontSize=13,
        leading=18,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=10
    )

    title_slide_title = ParagraphStyle(
        'PresTitle',
        parent=styles['Heading1'],
        fontSize=26,
        leading=32,
        alignment=1,
        textColor=colors.HexColor('#0f172a'),
        fontName='Helvetica-Bold',
        spaceAfter=14
    )

    title_slide_sub = ParagraphStyle(
        'PresSub',
        parent=styles['Normal'],
        fontSize=14,
        leading=18,
        alignment=1,
        textColor=colors.HexColor('#475569'),
        spaceAfter=20
    )

    story = []

    # Title Slide (Only add if explicit title or author metadata exists)
    title_m = re.search(r'\\title\{([^}]+)\}', latex_code)
    author_m = re.search(r'\\author\{([^}]+)\}', latex_code, re.DOTALL)
    institute_m = re.search(r'\\institute\{([^}]+)\}', latex_code, re.DOTALL)

    if title_m or author_m:
        title_text = clean_tex_syntax(title_m.group(1)) if title_m else ""
        author_text = clean_tex_syntax(author_m.group(1)) if author_m else ""
        inst_text = clean_tex_syntax(institute_m.group(1)) if institute_m else ""

        if title_text or author_text:
            story.append(Spacer(1, 40))
            if title_text:
                story.append(Paragraph(title_text, title_slide_title))
            if author_text or inst_text:
                sub_content = f"{author_text}<br/>{inst_text}" if inst_text else author_text
                story.append(Paragraph(sub_content, title_slide_sub))
            story.append(HRFlowable(width="80%", thickness=2, color=colors.HexColor("#6366f1"), spaceAfter=20))
            story.append(PageBreak())

    # Extract body section inside \begin{document}
    doc_match = re.search(r'\\begin\{document\}(.*?)\\end\{document\}', latex_code, re.DOTALL)
    body_code = doc_match.group(1) if doc_match else latex_code

    # Extract frames
    frames = re.findall(r'\\begin\{frame\}(.*?)\\end\{frame\}', body_code, re.DOTALL)

    if not frames:
        # If no explicit \begin{frame}, split by \chapter or \section
        sec_splits = re.split(r'\\(?:chapter|section)\{([^}]+)\}', body_code)
        if len(sec_splits) > 1:
            frames = []
            for i in range(1, len(sec_splits), 2):
                sec_title = sec_splits[i]
                sec_body = sec_splits[i+1] if i+1 < len(sec_splits) else ""
                frames.append(f"\\frametitle{{{sec_title}}}\n{sec_body}")
        else:
            frames = [body_code]

    active_slides = 0
    for idx, frame_content in enumerate(frames):
        lines = frame_content.split('\n')
        body_paras = []
        for line in lines:
            line_str = line.strip()
            if not line_str or 'frametitle' in line_str or '\\begin{document}' in line_str or '\\end{document}' in line_str or line_str.startswith('\\maketitle') or line_str.startswith('\\tableofcontents'):
                continue

            cleaned = clean_tex_syntax(line_str)
            if cleaned:
                if line_str.startswith('\\item') or line_str.startswith('•'):
                    body_paras.append(Paragraph(f"• {cleaned.lstrip('• ')}", bullet_style))
                else:
                    body_paras.append(Paragraph(cleaned, slide_body_style))

        frametitle_m = re.search(r'\\frametitle\{([^}]+)\}', frame_content)
        if not frametitle_m:
            frametitle_m = re.search(r'\\(?:chapter|section)\{([^}]+)\}', frame_content)

        frame_title = clean_tex_syntax(frametitle_m.group(1)) if frametitle_m else ""

        # Skip empty frames that have no title and no body text
        if not frame_title and not body_paras:
            continue

        if not frame_title:
            frame_title = f"Slide {active_slides + 1}"

        if story and not isinstance(story[-1], PageBreak):
            story.append(PageBreak())

        story.append(Paragraph(frame_title, slide_title_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=14))
        story.extend(body_paras)
        story.append(Spacer(1, 15))
        active_slides += 1

    doc.build(story)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")


def generate_fallback_pdf(latex_code: str, tmpdir: Optional[Path] = None) -> str:
    """
    Parses LaTeX code structure and generates a crisp PDF document using ReportLab
    when local TeX binary (pdflatex/tectonic) is missing or times out.
    """
    code_lower = latex_code.lower()
    if 'beamer' in code_lower or 'presentation' in code_lower or '\\begin{frame}' in latex_code or '\\frametitle' in latex_code:
        return generate_beamer_pdf(latex_code)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        alignment=1,
        textColor=colors.HexColor('#0f172a'),
        fontName='Helvetica-Bold',
        spaceAfter=8
    )

    author_style = ParagraphStyle(
        'DocAuthor',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        alignment=1,
        textColor=colors.HexColor('#475569'),
        fontName='Helvetica-Oblique',
        spaceAfter=14
    )

    section_style = ParagraphStyle(
        'DocSection',
        parent=styles['Heading2'],
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#1e1b4b'),
        fontName='Helvetica-Bold',
        spaceBefore=12,
        spaceAfter=6
    )

    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['BodyText'],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=8
    )

    abstract_style = ParagraphStyle(
        'DocAbstract',
        parent=styles['Normal'],
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor('#334155'),
        backColor=colors.HexColor('#f1f5f9'),
        borderColor=colors.HexColor('#cbd5e1'),
        borderWidth=0.5,
        borderPadding=8,
        spaceAfter=12
    )

    math_style = ParagraphStyle(
        'DocMath',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        fontName='Courier-Oblique',
        alignment=1,
        textColor=colors.HexColor('#4338ca'),
        backColor=colors.HexColor('#eef2ff'),
        borderPadding=6,
        spaceAfter=8
    )

    story = []

    # Extract Title
    title_match = re.search(r'\\title\{([^}]+)\}', latex_code)
    title_text = clean_tex_syntax(title_match.group(1)) if title_match else "LaTeX Document"
    story.append(Paragraph(title_text, title_style))

    # Extract Author
    author_match = re.search(r'\\author\{([^}]+)\}', latex_code, re.DOTALL)
    if author_match:
        clean_author = clean_tex_syntax(author_match.group(1))
        if clean_author:
            story.append(Paragraph(clean_author, author_style))

    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#e2e8f0"), spaceAfter=10))

    # Extract Abstract
    abstract_match = re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}', latex_code, re.DOTALL)
    if abstract_match:
        abstract_text = clean_tex_syntax(abstract_match.group(1))
        if abstract_text:
            story.append(Paragraph(f"<b>ABSTRACT — </b> {abstract_text}", abstract_style))

    # Parse body lines inside \begin{document}
    doc_match = re.search(r'\\begin\{document\}(.*?)\\end\{document\}', latex_code, re.DOTALL)
    body_code = doc_match.group(1) if doc_match else latex_code

    lines = body_code.split('\n')
    in_math_block = False
    math_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('%'):
            continue

        if stripped.startswith('\\documentclass') or stripped.startswith('\\usepackage') or stripped.startswith('\\begin{document}') or stripped.startswith('\\end{document}') or stripped.startswith('\\maketitle') or stripped.startswith('\\bibliographystyle') or stripped.startswith('\\bibliography') or stripped.startswith('\\usetheme'):
            continue

        if stripped.startswith('\\begin{equation}') or stripped.startswith('\\begin{align}') or stripped.startswith('\\[') or stripped.startswith('$$'):
            in_math_block = True
            math_lines = []
            continue

        if stripped.startswith('\\end{equation}') or stripped.startswith('\\end{align}') or stripped.startswith('\\]') or stripped.startswith('$$'):
            in_math_block = False
            math_content = " ".join(math_lines)
            cleaned_math = clean_tex_syntax(math_content)
            if cleaned_math:
                story.append(Paragraph(f"[ Equation: {cleaned_math} ]", math_style))
            continue

        if in_math_block:
            math_lines.append(stripped)
            continue

        # Check for \includegraphics
        img_match = re.search(r'\\includegraphics(?:\[.*?\])?\{([^}]+)\}', stripped)
        if img_match:
            img_filename = img_match.group(1).strip()
            found_img_path = None
            if tmpdir:
                candidate = (tmpdir / img_filename).resolve()
                if candidate.exists() and candidate.is_file():
                    found_img_path = candidate
            if found_img_path:
                try:
                    from reportlab.platypus import Image as RLImage
                    story.append(RLImage(str(found_img_path), width=350, height=250, preserveAspectRatio=True))
                    story.append(Spacer(1, 6))
                except Exception:
                    story.append(Paragraph(f"<b>[ Asset Image: {img_filename} ]</b>", body_style))
            else:
                story.append(Paragraph(f"<b>[ Asset Image: {img_filename} ]</b>", body_style))
            continue

        section_match = re.match(r'\\section\{([^}]+)\}', stripped)
        if section_match:
            sec_title = clean_tex_syntax(section_match.group(1))
            if sec_title:
                story.append(Paragraph(sec_title.upper(), section_style))
            continue

        subsection_match = re.match(r'\\subsection\{([^}]+)\}', stripped)
        if subsection_match:
            subsec_title = clean_tex_syntax(subsection_match.group(1))
            if subsec_title:
                story.append(Paragraph(subsec_title, section_style))
            continue

        # Regular line
        cleaned = clean_tex_syntax(stripped)
        if len(cleaned) > 2:
            story.append(Paragraph(cleaned, body_style))

    doc.build(story)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")


def write_file_safely(tmpdir: Path, filename: str, data_base64: str):
    """Safely decodes and writes a base64 file asset to tmpdir preventing path traversal."""
    resolved_path = (tmpdir / filename).resolve()
    if not str(resolved_path).startswith(str(tmpdir.resolve())):
        raise ValueError(f"Path traversal detected in asset filename: {filename}")

    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    raw_bytes = base64.b64decode(data_base64)
    resolved_path.write_bytes(raw_bytes)


def create_sample_image(target_path: Path, label: str):
    """Creates a clean sample/placeholder image file so LaTeX compilation succeeds natively with the real layout."""
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        ext = target_path.suffix.lower()
        if ext == ".pdf":
            try:
                from reportlab.pdfgen import canvas
                c = canvas.Canvas(str(target_path), pagesize=(500, 350))
                c.setFillColorRGB(0.93, 0.95, 0.98)
                c.rect(0, 0, 500, 350, fill=1, stroke=0)
                c.setStrokeColorRGB(0.7, 0.75, 0.85)
                c.setLineWidth(2)
                c.rect(10, 10, 480, 330, fill=0, stroke=1)
                c.setFillColorRGB(0.2, 0.25, 0.35)
                c.setFont("Helvetica-Bold", 18)
                c.drawCentredString(250, 185, "SAMPLE IMAGE")
                c.setFont("Helvetica", 11)
                c.drawCentredString(250, 155, label[:40])
                c.save()
                return
            except Exception:
                pass

        from PIL import Image, ImageDraw
        width, height = 600, 400
        img = Image.new("RGB", (width, height), color=(241, 245, 249))
        draw = ImageDraw.Draw(img)
        # Outer border
        draw.rectangle([(8, 8), (width - 8, height - 8)], outline=(203, 213, 225), width=3)
        # Diagonal accent lines
        draw.line([(8, 8), (width - 8, height - 8)], fill=(226, 232, 240), width=2)
        draw.line([(8, height - 8), (width - 8, 8)], fill=(226, 232, 240), width=2)
        # Center box
        draw.rectangle([(110, 130), (490, 270)], fill=(255, 255, 255), outline=(148, 163, 184), width=2)
        # Text
        draw.text((width // 2, 175), "SAMPLE IMAGE", fill=(30, 41, 59), anchor="mm")
        draw.text((width // 2, 220), label[:45], fill=(100, 116, 139), anchor="mm")

        fmt = "JPEG" if ext in [".jpg", ".jpeg"] else "PNG"
        img.save(str(target_path), format=fmt)
    except Exception as e:
        logger.warning(f"Failed to create sample image at {target_path}: {e}")


def ensure_sample_images_exist(latex_code: str, tmpdir: Path):
    """
    Finds all \\includegraphics{...} references in latex_code.
    If the referenced image file does not exist on disk, creates a clean sample image at that path.
    """
    matches = re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', latex_code)
    for raw_path in matches:
        clean_path = raw_path.strip().strip('"').strip("'")
        if not clean_path:
            continue

        has_ext = bool(re.search(r'\.[a-zA-Z0-9]+$', clean_path))
        candidates = [
            (tmpdir / clean_path),
            (tmpdir / "images" / clean_path),
            (tmpdir / "assets" / clean_path),
        ]

        if not has_ext:
            for ext in [".png", ".pdf", ".jpg", ".jpeg"]:
                candidates.append(tmpdir / f"{clean_path}{ext}")
                candidates.append(tmpdir / "images" / f"{clean_path}{ext}")
                candidates.append(tmpdir / "assets" / f"{clean_path}{ext}")

        exists = any(c.exists() and c.is_file() for c in candidates)
        if not exists:
            target = tmpdir / clean_path
            if not has_ext:
                target = tmpdir / f"{clean_path}.png"
            create_sample_image(target, Path(clean_path).name)


_TEMPLATE_ROOTS_CACHE: Optional[List[Path]] = None

def get_template_roots() -> List[Path]:
    global _TEMPLATE_ROOTS_CACHE
    if _TEMPLATE_ROOTS_CACHE is not None:
        return _TEMPLATE_ROOTS_CACHE
    templates_base_dir = Path(os.path.join(os.path.dirname(__file__), "templates")).resolve()
    template_roots = []
    if templates_base_dir.exists():
        for category_dir in sorted(templates_base_dir.iterdir()):
            if not category_dir.is_dir():
                continue
            if list(category_dir.glob("*.tex")):
                template_roots.append(category_dir)
            else:
                for tmpl_dir in sorted(category_dir.iterdir()):
                    if tmpl_dir.is_dir() and list(tmpl_dir.glob("*.tex")):
                        template_roots.append(tmpl_dir)
    _TEMPLATE_ROOTS_CACHE = template_roots
    return _TEMPLATE_ROOTS_CACHE


def load_project_text_file(project_id: Optional[str], rel_path: str = "main.tex") -> Optional[str]:
    """
    Current text of one of a project's files — the uploads directory first, then
    Supabase's ``latex_documents`` (the same two places ``compile_latex`` reads
    project files from) — or None when it cannot be found.
    """
    if not project_id or not str(project_id).strip():
        return None
    pid = str(project_id).strip()
    safe_project = re.sub(r'[^a-zA-Z0-9_-]', '_', pid)
    base = Path(os.getenv("UPLOADS_BASE_DIR", os.path.join(os.path.dirname(__file__), "..", "uploads", "projects"))).resolve()
    project_dir = (base / safe_project).resolve()
    candidate = (project_dir / rel_path).resolve()
    if str(candidate).startswith(str(project_dir)) and candidate.is_file():
        try:
            return candidate.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass
    try:
        from project_storage import get_supabase_client
        supabase = get_supabase_client()
        if supabase:
            res = (supabase.table("latex_documents").select("raw_code")
                   .eq("project_id", pid).eq("file_path", rel_path).limit(1).execute())
            raw = (res.data or [{}])[0].get("raw_code")
            if raw and not str(raw).startswith("[Binary Asset:"):
                return raw
    except Exception:
        pass
    return None


def _save_synctex_artifacts(tmpdir: Path, project_id: Optional[str]) -> None:
    """Save main.pdf, main.synctex.gz, and source .tex files to persistent build directory."""
    try:
        from synctex_service import get_project_build_dir, invalidate_project_synctex_cache
        build_dir = get_project_build_dir(project_id)
        invalidate_project_synctex_cache(project_id)
        pdf_path = tmpdir / "main.pdf"
        if pdf_path.exists():
            shutil.copy2(pdf_path, build_dir / "main.pdf")
        synctex_gz = tmpdir / "main.synctex.gz"
        if synctex_gz.exists():
            shutil.copy2(synctex_gz, build_dir / "main.synctex.gz")
        synctex_raw = tmpdir / "main.synctex"
        if synctex_raw.exists():
            shutil.copy2(synctex_raw, build_dir / "main.synctex")
        for tex_file in tmpdir.rglob("*.tex"):
            rel_t = tex_file.relative_to(tmpdir)
            target_t = build_dir / rel_t
            target_t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(tex_file, target_t)
    except Exception as synctex_err:
        logger.debug(f"SyncTeX caching note: {synctex_err}")


_RE_TEX_CONTEXT_LINE = re.compile(r"^l\.\d+\b")


def _compile_failure(output: str) -> dict:
    """
    Clean compilation error for the caller to show, or to hand to the AI fixer.

    ``error_log`` keeps TeX's own error lines — ``./main.tex:42: …`` (compiles
    run with -file-line-error) and ``! …`` — each followed by its ``l.N``
    context line, which shows the offending code. It used to keep only lines
    starting with ``!`` or containing ``error:``, which dropped
    ``Undefined control sequence``, ``Missing $ inserted`` and runaway arguments
    and left "Ask AI to Fix" with nothing but "Fatal error occurred". ``errors``
    is the complete list from the full log (``raw_log`` is only its tail).
    """
    clean_err = (output or "").strip() or "LaTeX compilation failed."
    lines = clean_err.split("\n")
    picked: List[str] = []
    for i, line in enumerate(lines):
        s = line.strip()
        low = s.lower()
        if (_TEX_ERROR_RE.match(s) or "fatal error" in low or "emergency stop" in low
                or s.startswith("[TIMEOUT]") or s.startswith("[INFRASTRUCTURE ERROR]")):
            picked.append(s)
            for nxt in lines[i + 1:i + 8]:
                if _RE_TEX_CONTEXT_LINE.match(nxt.strip()):
                    picked.append(nxt.strip())
                    break
    picked = list(dict.fromkeys(picked))
    summary = "\n".join(picked[:20]) if picked else clean_err[-1500:]
    return {"success": False, "error_log": summary, "raw_log": clean_err[-4000:], "errors": tex_errors(clean_err)}


_RE_LOG_LINE_REFS = (
    re.compile(r"(main\.tex:)(\d+)(:)"),                       # -file-line-error
    re.compile(r"(^|\n)(l\.)(\d+)()"),                         # TeX's "l.<n> <context>"
    re.compile(r"((?:on input line|detected at line) )(\d+)()"),
)
_RE_LOG_LINE_RANGE = re.compile(r"(at lines )(\d+)(--)(\d+)")


def _healed_to_source_lines(healed: str, source: str) -> Dict[int, int]:
    """1-based line in ``healed`` -> the line of ``source`` it came from (or was inserted at)."""
    import difflib
    a, b = healed.splitlines(), source.splitlines()
    mapping: Dict[int, int] = {}
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        for k in range(i1, i2):
            if tag == "equal":
                mapping[k + 1] = j1 + (k - i1) + 1
            elif tag == "replace":
                mapping[k + 1] = min(j1 + (k - i1), j2 - 1) + 1
            else:  # a line the heal added: report it at the source line it follows
                mapping[k + 1] = max(1, min(j1, len(b)))
    return mapping


def _remap_result_lines(result: dict, healed: str, source: str) -> None:
    """Rewrites every TeX line reference in ``result`` from ``healed`` to ``source`` numbering."""
    mapping = _healed_to_source_lines(healed, source)

    def to_src(n: str) -> str:
        return str(mapping.get(int(n), int(n)))

    def remap_text(text: str) -> str:
        if not isinstance(text, str) or not text:
            return text
        text = _RE_LOG_LINE_REFS[0].sub(lambda m: m.group(1) + to_src(m.group(2)) + m.group(3), text)
        text = _RE_LOG_LINE_REFS[1].sub(lambda m: m.group(1) + m.group(2) + to_src(m.group(3)), text)
        text = _RE_LOG_LINE_REFS[2].sub(lambda m: m.group(1) + to_src(m.group(2)), text)
        return _RE_LOG_LINE_RANGE.sub(
            lambda m: m.group(1) + to_src(m.group(2)) + m.group(3) + to_src(m.group(4)), text)

    for key in ("log", "error_log", "raw_log"):
        if key in result:
            result[key] = remap_text(result[key])
    if isinstance(result.get("errors"), list):
        result["errors"] = [remap_text(e) for e in result["errors"]]
    for box in result.get("overfull") or []:
        if isinstance(box, dict) and isinstance(box.get("lines"), list):
            box["lines"] = [mapping.get(n, n) if isinstance(n, int) else n for n in box["lines"]]


def compile_latex(
    latex_code: str,
    engine: str = "pdfLaTeX",
    images: Optional[List[Dict[str, str]]] = None,
    files: Optional[List[Dict[str, str]]] = None,
    project_id: Optional[str] = None,
    timeout_seconds: int = 30,
    persist_synctex: bool = True,
    allow_recovery: bool = True,
    pre_heal: Optional[bool] = None,
) -> dict:
    """
    Compiles ``latex_code`` (see ``_compile_latex_impl``), optionally healing it first.

    ``pre_heal`` (default: follows ``allow_recovery``) runs the deterministic
    whole-document healer before TeX — unclosed environments, lonely \\item, TikZ
    semicolons, \\bottom -> \\bottomrule, bare & in frame titles, … — the same
    speculative healer the agent runs on every write, discarded internally if it
    raises the structural error count. The PDF importer (allow_recovery=False)
    must see *its exact* code's errors, and the agent's shadow compiler passes
    pre_heal=False because it heals the lines it edited itself.

    A heal can insert lines (e.g. ``\\usetikzlibrary{calc}`` after
    ``\\usepackage{tikz}``), which shifts every line TeX reports below it, so
    the reported lines are translated back to ``latex_code``'s numbering —
    otherwise the error panel, SyncTeX-free jumps and "Ask AI to Fix" all point
    at the wrong line.
    """
    do_heal = allow_recovery if pre_heal is None else pre_heal
    source = latex_code
    if do_heal:
        try:
            from latex_error_fixer import auto_heal_latex_code
            healed, _fixes = auto_heal_latex_code(latex_code)
            if healed:
                latex_code = healed
        except Exception:
            pass

    result = _compile_latex_impl(
        latex_code, engine=engine, images=images, files=files, project_id=project_id,
        timeout_seconds=timeout_seconds, persist_synctex=persist_synctex,
        allow_recovery=allow_recovery,
    )
    if latex_code != source:
        try:
            _remap_result_lines(result, latex_code, source)
        except Exception as e:
            logger.debug(f"line remap after pre-heal skipped: {e}")
    return result


def _compile_latex_impl(
    latex_code: str,
    engine: str = "pdfLaTeX",
    images: Optional[List[Dict[str, str]]] = None,
    files: Optional[List[Dict[str, str]]] = None,
    project_id: Optional[str] = None,
    timeout_seconds: int = 30,
    persist_synctex: bool = True,
    allow_recovery: bool = True,
) -> dict:
    """
    High-performance TeX compiler pipeline with smart single/double pass dispatch,
    direct binary invocation, template asset caching, and ReportLab fallback.
    """
    start_time = time.time()
    augment_path_for_latex()

    eng_clean = (engine or "pdfLaTeX").strip().lower()

    # Honor `% !TEX program = xelatex|lualatex` when the caller asked for the default engine
    magic_engine = detect_magic_engine(latex_code)
    if magic_engine and eng_clean in _DEFAULT_ENGINES:
        eng_clean = magic_engine
    recovery_engine = eng_clean if eng_clean in ("xelatex", "lualatex") else "pdflatex"

    # Fast ReportLab engine override check
    if eng_clean in ["fast", "reportlab"]:
        try:
            pdf_base64 = generate_fallback_pdf(latex_code)
            elapsed_ms = int((time.time() - start_time) * 1000)
            return {
                "success": True,
                "pdf_base64": pdf_base64,
                "compile_time_ms": elapsed_ms,
                "log": "Rendered via Fast TeX Engine",
            }
        except Exception as fast_err:
            pass

    with tempfile.TemporaryDirectory() as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        try:
            has_disk_files = False
            # 1. Copy project disk assets if project_id is provided
            if project_id and project_id.strip():
                safe_project = re.sub(r'[^a-zA-Z0-9_-]', '_', project_id.strip())
                uploads_base_dir = Path(os.getenv("UPLOADS_BASE_DIR", os.path.join(os.path.dirname(__file__), "..", "uploads", "projects"))).resolve()
                project_dir = uploads_base_dir / safe_project
                if project_dir.exists():
                    for item in project_dir.rglob("*"):
                        if item.is_file():
                            rel_path = item.relative_to(project_dir)
                            if str(rel_path) == "main.tex":
                                continue
                            dest = tmpdir / rel_path
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(item, dest)
                            has_disk_files = True

                # Only query DB if no disk files were present
                if not has_disk_files:
                    try:
                        from project_storage import get_supabase_client
                        supabase = get_supabase_client()
                        if supabase:
                            docs_res = supabase.table("latex_documents").select("file_path, raw_code").eq("project_id", project_id.strip()).execute()
                            if docs_res.data:
                                for doc in docs_res.data:
                                    f_path = doc.get("file_path")
                                    r_code = doc.get("raw_code")
                                    if not f_path or f_path == "main.tex":
                                        continue
                                    dest = tmpdir / f_path
                                    dest.parent.mkdir(parents=True, exist_ok=True)
                                    if r_code and not r_code.startswith("[Binary Asset:"):
                                        dest.write_text(r_code, encoding="utf-8", errors="ignore")
                    except Exception:
                        pass

            # 2. Write current main.tex
            try:
                from document_index import ensure_document_environment
                latex_code = ensure_document_environment(latex_code)
            except Exception:
                pass

            tex_path = tmpdir / "main.tex"
            tex_path.write_text(latex_code, encoding="utf-8")

            # 3. Write extra payload asset files and images
            if images:
                for img in images:
                    write_file_safely(tmpdir, img.get("filename", ""), img.get("data", ""))

            if files:
                for f in files:
                    write_file_safely(tmpdir, f.get("filename", ""), f.get("data", ""))

            # 4. Smart template asset resolution — only copy matched template files
            template_roots = get_template_roots()
            matched_root = None
            for tmpl_root in template_roots:
                tmpl_files = {f.name for f in tmpl_root.rglob("*") if f.is_file() and f.name not in ("main.tex", "metadata.json", "thumbnail.png")}
                for tf_name in tmpl_files:
                    name_no_ext = Path(tf_name).stem
                    if tf_name.endswith((".cls", ".sty")) and (f"\\documentclass{{{name_no_ext}}}" in latex_code or f"\\usepackage{{{name_no_ext}}}" in latex_code):
                        matched_root = tmpl_root
                        break
                    if tf_name == "structure.tex" and r"\input{structure.tex}" in latex_code:
                        matched_root = tmpl_root
                        break
                if matched_root:
                    break

            if matched_root:
                for tmpl_file in matched_root.rglob("*"):
                    if tmpl_file.is_file():
                        rel_path = tmpl_file.relative_to(matched_root)
                        if str(rel_path) == "main.tex" or rel_path.name in ("metadata.json", "thumbnail.png"):
                            continue
                        dest_file = tmpdir / rel_path
                        if not dest_file.exists():
                            try:
                                dest_file.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(tmpl_file, dest_file)
                            except Exception:
                                pass

            # 5. Ensure any referenced images exist as sample images on disk if missing
            ensure_sample_images_exist(latex_code, tmpdir)

            # Environment configuration
            comp_env = os.environ.copy()
            existing_texinputs = comp_env.get("TEXINPUTS", "")
            comp_env["TEXINPUTS"] = f".:{tmpdir}:{tmpdir}/images:{tmpdir}/*:{existing_texinputs}"

            # Heavy TikZ/pgfplots or very long documents take far longer than a
            # plain article; Overleaf lets them run for minutes. Give them a
            # bigger budget than the base request so they are not killed and
            # reported as a "failure" they never really were.
            COMPILE_TIMEOUT = timeout_seconds
            if is_heavy_document(latex_code):
                COMPILE_TIMEOUT = max(timeout_seconds, 90)

            # Unicode-font documents (fontspec / unicode-math / system fonts /
            # polyglossia) only compile under XeLaTeX or LuaLaTeX. Overleaf picks
            # this from the project's compiler setting; detect it from the source
            # when the caller asked for the default engine and no magic comment
            # already pinned one.
            unicode_engine = None
            if eng_clean in _DEFAULT_ENGINES and not magic_engine and needs_unicode_engine(latex_code):
                unicode_engine = "xelatex"
                recovery_engine = "xelatex"

            # Target engine selection (Matching Overleaf nonstopmode behavior with SyncTeX enabled).
            # SyncTeX costs an extra output file per run, so it is only asked for when the
            # artifacts will actually be kept (the editor); the PDF importer compiles throwaway
            # pages and never navigates them.
            sx = ["-synctex=1"] if persist_synctex else []

            def _direct(engine_bin: str) -> List[str]:
                return [engine_bin, *sx, "-interaction=nonstopmode", "-file-line-error", "main.tex"]

            def _latexmk(engine_flag: Optional[str] = None) -> List[str]:
                cmd = ["latexmk", *sx, "-pdf", "-f", "-silent", "-interaction=nonstopmode"]
                if engine_flag:
                    cmd.append(engine_flag)
                cmd.append("main.tex")
                return cmd

            cmd_list = []
            if eng_clean in ["pdflatex", "pdf", "latex"]:
                # The editor and the agent both ask for pdfLaTeX explicitly, so the
                # Unicode-font switch has to apply here too, not only to latexmk.
                cmd_list = [_direct(unicode_engine or "pdflatex")]
            elif eng_clean in ["xelatex", "xe"]:
                cmd_list = [_direct("xelatex")]
            elif eng_clean in ["lualatex", "lua"]:
                cmd_list = [_direct("lualatex")]
            elif eng_clean == "tectonic":
                cmd_list = [["tectonic", "main.tex"]]
            elif eng_clean == "latexmk":
                # latexmk self-manages passes + biber/bibtex. Tell it which engine
                # to use for Unicode-font documents, and fall back to a direct
                # engine run if latexmk is not installed (otherwise a missing
                # latexmk surfaces as an empty, mysterious failure).
                if unicode_engine == "xelatex":
                    cmd_list = [_latexmk("-xelatex"), _direct("xelatex")]
                elif unicode_engine == "lualatex":
                    cmd_list = [_latexmk("-lualatex"), _direct("lualatex")]
                else:
                    cmd_list = [_latexmk(), _direct("pdflatex")]
            else:
                if unicode_engine == "xelatex":
                    cmd_list = [_direct("xelatex"), _direct("lualatex"), _latexmk("-xelatex")]
                else:
                    cmd_list = [_direct("pdflatex"), _direct("xelatex"), _latexmk()]

            bib_backend = _bibliography_backend(latex_code)
            extra_pass_timeout = max(15, COMPILE_TIMEOUT // 2)

            last_output = ""
            for cmd in cmd_list:
                try:
                    # Pass 1
                    result = _run_tex(
                        cmd,
                        cwd=tmpdir,
                        timeout=COMPILE_TIMEOUT,
                        env=comp_env
                    )
                    last_output = (result.stdout or "") + "\n" + (result.stderr or "")

                    pdf_path = tmpdir / "main.pdf"

                    # latexmk/tectonic self-manage passes and bibliography; a direct
                    # engine run has to resolve cross-references/TOC/citations itself.
                    is_direct = cmd[0] in ["pdflatex", "xelatex", "lualatex"]

                    if pdf_path.exists() and is_direct:
                        # Bibliography: run biber/bibtex, then two more passes so the
                        # citations and the bibliography actually resolve (Overleaf's
                        # latexmk does this automatically).
                        if bib_backend:
                            try:
                                _run_tex(
                                    [bib_backend, "main"],
                                    cwd=tmpdir,
                                    timeout=extra_pass_timeout,
                                    env=comp_env,
                                )
                            except Exception:
                                pass
                            for _ in range(2):
                                try:
                                    rb = _run_tex(
                                        cmd,
                                        cwd=tmpdir,
                                        timeout=extra_pass_timeout,
                                        env=comp_env,
                                    )
                                    last_output += "\n" + (rb.stdout or "") + "\n" + (rb.stderr or "")
                                except Exception:
                                    break
                        else:
                            needs_pass2 = (
                                r"\tableofcontents" in latex_code
                                or r"\ref{" in latex_code
                                or r"\cite{" in latex_code
                                or r"\label{" in latex_code
                                or "Rerun" in last_output
                                or "undefined references" in last_output.lower()
                            )
                            if needs_pass2:
                                result2 = _run_tex(
                                    cmd,
                                    cwd=tmpdir,
                                    timeout=extra_pass_timeout,
                                    env=comp_env
                                )
                                last_output += "\n" + (result2.stdout or "") + "\n" + (result2.stderr or "")

                    # If PDF was created, persist artifacts and return it.
                    if pdf_path.exists():
                        if persist_synctex:
                            _save_synctex_artifacts(tmpdir, project_id)
                        pdf_bytes = pdf_path.read_bytes()
                        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
                        elapsed_ms = int((time.time() - start_time) * 1000)
                        return {
                            "success": True,
                            "pdf_base64": pdf_base64,
                            "compile_time_ms": elapsed_ms,
                            "log": last_output[-1000:] if last_output else f"Compiled via {cmd[0]}",
                            "errors": tex_errors(last_output),
                            # Overfull boxes are warnings, so they never reach the
                            # truncated log above; keep them for layout checks.
                            "overfull": _overfull_boxes(last_output),
                        }
                except subprocess.TimeoutExpired:
                    last_output += f"\n[TIMEOUT] {cmd[0]} exceeded {COMPILE_TIMEOUT}s"
                    continue
                except FileNotFoundError as fnf:
                    last_output += f"\n[INFRASTRUCTURE ERROR] Executable '{cmd[0]}' not found: {fnf}"
                    continue
                except Exception as exc:
                    last_output += f"\n[INFRASTRUCTURE ERROR] Command '{cmd[0]}' failed: {exc}"
                    continue

            if not allow_recovery:
                # A caller that only wants to know whether THIS code compiles (the PDF importer,
                # which then hands the errors to the model) must not pay for the cascade below:
                # every patch is another engine run, up to seven of them, and a PDF obtained by
                # silently disabling a package is a result such a caller rejects anyway.
                return _compile_failure(last_output)

            # Every recovery run must still report the TeX errors it saw: a PDF obtained
            # by disabling a package says nothing about the rest of the document, and
            # the agent's compile gate reads ``errors`` to decide whether an edit broke it.
            # A patch that inserts a line (lmodern) shifts TeX's line numbers, so they
            # are mapped back to the code this function was given.
            def _recovery_success(log_text: str, output_text: str, patched: str) -> dict:
                if persist_synctex:
                    _save_synctex_artifacts(tmpdir, project_id)
                res = {
                    "success": True,
                    "pdf_base64": base64.b64encode((tmpdir / "main.pdf").read_bytes()).decode("utf-8"),
                    "compile_time_ms": int((time.time() - start_time) * 1000),
                    "log": log_text,
                    "errors": tex_errors(output_text),
                    "overfull": _overfull_boxes(output_text),
                }
                if patched != latex_code:
                    try:
                        _remap_result_lines(res, patched, latex_code)
                    except Exception:
                        pass
                return res

            # 1. Missing LaTeX package iterative auto-recovery patch
            patched_code = latex_code
            all_disabled_pkgs = []
            cur_output = last_output
            for pass_num in range(4):
                # `! LaTeX Error: …` in a classic log, `./main.tex:3: LaTeX Error: …` with
                # -file-line-error (every direct engine run) — the latter never matched before.
                missing_pkgs = re.findall(
                    r"(?:!|\S+\.tex:\d+:) LaTeX Error: File [`\x27]([^\x27`]+)\.sty[`\x27] not found", cur_output)
                if not missing_pkgs:
                    break
                for pkg in set(missing_pkgs):
                    if pkg not in all_disabled_pkgs:
                        patched_code = re.sub(
                            r'\\usepackage(?:\[[^\]]*\])?\{' + re.escape(pkg) + r'\}',
                            f'% [AUTO-DISABLED: {pkg}.sty not installed on server]',
                            patched_code
                        )
                        all_disabled_pkgs.append(pkg)

                tex_path.write_text(patched_code, encoding="utf-8")
                try:
                    result = _run_tex(
                        [recovery_engine, "-interaction=nonstopmode", "-file-line-error", "main.tex"],
                        cwd=tmpdir,
                        timeout=15,
                        env=comp_env
                    )
                    cur_output = (result.stdout or "") + "\n" + (result.stderr or "")
                    pdf_path = tmpdir / "main.pdf"
                    if pdf_path.exists():
                        pkg_notice = (
                            f"Missing LaTeX package(s) on server: {', '.join(all_disabled_pkgs)}. "
                            f"Install on server: 'pacman -S texlive-latexextra' (Arch) / 'apt-get install texlive-latex-extra' (Ubuntu) / 'tlmgr install <pkg>'."
                        )
                        print(f"✅ [COMPILER RECOVERY] Auto-recovered by disabling missing package(s): {', '.join(all_disabled_pkgs)}")
                        return _recovery_success(
                            f"Compiled via package auto-recovery ({', '.join(all_disabled_pkgs)} disabled)\n\n[PACKAGE NOTICE]\n{pkg_notice}",
                            cur_output, patched_code,
                        )
                except Exception:
                    break

            # 2. Font metric error auto-recovery patch
            font_error_keywords = ["not loadable", "Metric (TFM) file not found", "ecrm1000", "cm-super"]
            if any(kw.lower() in last_output.lower() for kw in font_error_keywords):
                patched_code = latex_code
                if "lmodern" not in patched_code:
                    if r"\usepackage[T1]{fontenc}" in patched_code:
                        patched_code = patched_code.replace(r"\usepackage[T1]{fontenc}", r"\usepackage[T1]{fontenc}" + "\n" + r"\usepackage{lmodern}")
                    elif r"\documentclass" in patched_code:
                        patched_code = re.sub(r'(\\documentclass(?:\[.*?\])?\{.*?\})', r'\1' + "\n" + r"\usepackage{lmodern}", patched_code, count=1)

                if patched_code != latex_code:
                    tex_path.write_text(patched_code, encoding="utf-8")
                    try:
                        result = _run_tex([recovery_engine, "-interaction=nonstopmode", "-file-line-error", "main.tex"], cwd=tmpdir, timeout=15, env=comp_env)
                        pdf_path = tmpdir / "main.pdf"
                        if pdf_path.exists():
                            return _recovery_success(
                                "Compiled via font auto-recovery (lmodern patch)",
                                (result.stdout or "") + "\n" + (result.stderr or ""), patched_code,
                            )
                    except Exception:
                        pass

            # 3. Invalid beamercolorbox bg key auto-recovery patch
            if "Package keyval Error: bg undefined" in last_output or "bg undefined" in last_output:
                patched_code = re.sub(
                    r"\[([^\]]*?),?\s*bg=[^,\]]+([^\]]*)\]",
                    lambda m: f"[{m.group(1)}{m.group(2)}]".replace("[,", "[").replace(",,", ",").replace("[,]", "[]"),
                    latex_code
                )
                if patched_code != latex_code:
                    tex_path.write_text(patched_code, encoding="utf-8")
                    try:
                        result = _run_tex(
                            [recovery_engine, "-interaction=nonstopmode", "-file-line-error", "main.tex"],
                            cwd=tmpdir,
                            timeout=15,
                            env=comp_env
                        )
                        pdf_path = tmpdir / "main.pdf"
                        if pdf_path.exists():
                            return _recovery_success(
                                "Compiled via beamercolorbox bg auto-recovery",
                                (result.stdout or "") + "\n" + (result.stderr or ""), patched_code,
                            )
                    except Exception:
                        pass

            # 4. Modern LaTeX3 titlesec \MakeUppercase / Bad math delimiter auto-recovery patch
            titlesec_error_keywords = [
                "__text_expand_loop:w",
                "Bad math environment delimiter",
                "titlesec Error",
                "has an extra }"
            ]
            if any(kw in last_output for kw in titlesec_error_keywords) or (r"\titleformat" in latex_code and r"\MakeUppercase" in latex_code):
                patched_code = latex_code
                patched_lines = []
                for line in patched_code.split("\n"):
                    if "titleformat" in line and "\\MakeUppercase" in line:
                        line = line.replace("\\MakeUppercase", "")
                    elif "\\MakeUppercase" in line and any(k in line for k in ["centering", "normalfont", "bfseries"]):
                        line = line.replace("\\MakeUppercase", "")
                    if "\\\\" in line and any(unit in line for unit in ["cm]", "in]", "mm]", "pt]", "em]"]):
                        line = re.sub(r'\\\\\s*\[(\d+(?:\.\d+)?(?:cm|in|mm|pt|em|ex))\]', r'\\par\\vspace{\1}', line)
                    patched_lines.append(line)
                patched_code = "\n".join(patched_lines)

                if patched_code != latex_code:
                    tex_path.write_text(patched_code, encoding="utf-8")
                    try:
                        result = _run_tex(
                            [recovery_engine, "-interaction=nonstopmode", "-file-line-error", "main.tex"],
                            cwd=tmpdir,
                            timeout=15,
                            env=comp_env,
                        )
                        pdf_path = tmpdir / "main.pdf"
                        if pdf_path.exists():
                            return _recovery_success(
                                "Compiled via titlesec/spacing auto-recovery",
                                (result.stdout or "") + "\n" + (result.stderr or ""), patched_code,
                            )
                    except Exception:
                        pass

        except Exception:
            pass

        # No fallback PDFs — return clean compilation error directly so user can see it and ask AI to fix it
        return _compile_failure(last_output)

