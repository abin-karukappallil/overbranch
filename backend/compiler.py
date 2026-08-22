import tempfile
import subprocess
import base64
import os
import re
import io
import time
import shutil
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


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


def compile_latex(
    latex_code: str,
    engine: str = "latexmk",
    images: Optional[List[Dict[str, str]]] = None,
    files: Optional[List[Dict[str, str]]] = None,
    project_id: Optional[str] = None
) -> dict:
    """
    Compiles LaTeX code into PDF using latexmk (with -f forced compilation & error suppression),
    pdflatex, xelatex, lualatex, tectonic, or the instant ReportLab fallback engine.
    Copies all uploaded assets/files belonging to project_id into temporary compilation directory.
    """
    start_time = time.time()
    augment_path_for_latex()

    has_perl = True
    if sys.platform == "win32":
        has_perl = shutil.which("perl") is not None

    with tempfile.TemporaryDirectory() as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        try:
            # 1. Copy project disk assets if project_id is provided
            if project_id and project_id.strip():
                safe_project = re.sub(r'[^a-zA-Z0-9_-]', '_', project_id.strip())
                uploads_base_dir = Path(os.path.join(os.path.dirname(__file__), "..", "uploads", "projects")).resolve()
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

                # Sync text documents from database if present
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
                except Exception as db_err:
                    pass

            # 2. Write current main.tex
            tex_path = tmpdir / "main.tex"
            tex_path.write_text(latex_code, encoding="utf-8")

            # 3. Write extra asset files and images if provided directly in payload
            if images:
                for img in images:
                    write_file_safely(tmpdir, img.get("filename", ""), img.get("data", ""))

            if files:
                for f in files:
                    write_file_safely(tmpdir, f.get("filename", ""), f.get("data", ""))

            # 4. Copy missing or placeholder template fallback assets (like logo.jpg, structure.tex, .sty, .cls)
            templates_base_dir = Path(os.path.join(os.path.dirname(__file__), "templates")).resolve()
            if templates_base_dir.exists():
                for tmpl_file in templates_base_dir.rglob("*"):
                    if tmpl_file.is_file():
                        rel_name = tmpl_file.name
                        dest_file = tmpdir / rel_name

                        # Check if dest_file is missing or is an invalid text placeholder
                        is_valid = True
                        if dest_file.exists():
                            try:
                                if dest_file.stat().st_size < 200:
                                    content = dest_file.read_bytes()
                                    if content.startswith(b"[Binary Asset:"):
                                        is_valid = False
                            except Exception:
                                pass
                        else:
                            is_valid = False

                        if not is_valid and rel_name != "main.tex":
                            try:
                                dest_file.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(tmpl_file, dest_file)
                            except Exception:
                                pass

            # Build environment with augmented TEXINPUTS for nested inputs and assets
            comp_env = os.environ.copy()
            existing_texinputs = comp_env.get("TEXINPUTS", "")
            comp_env["TEXINPUTS"] = f".:{tmpdir}:{tmpdir}/images:{tmpdir}/*:{existing_texinputs}"

            # Build command list
            cmd_list = []
            if engine == "tectonic":
                cmd_list.append(["tectonic", "main.tex"])
            elif sys.platform == "win32" and not has_perl:
                cmd_list.extend([
                    ["pdflatex", "-interaction=nonstopmode", "-c-style-errors", "main.tex"],
                    ["xelatex", "-interaction=nonstopmode", "main.tex"],
                    ["lualatex", "-interaction=nonstopmode", "main.tex"]
                ])
            else:
                cmd_list.extend([
                    ["latexmk", "-pdf", "-f", "-silent", "-interaction=nonstopmode", "main.tex"],
                    ["pdflatex", "-interaction=nonstopmode", "-c-style-errors", "main.tex"],
                    ["xelatex", "-interaction=nonstopmode", "main.tex"],
                    ["lualatex", "-interaction=nonstopmode", "main.tex"]
                ])

            last_output = ""
            for cmd in cmd_list:
                try:
                    # Run primary pass
                    result = subprocess.run(
                        cmd,
                        cwd=tmpdir,
                        capture_output=True,
                        text=True,
                        timeout=35,
                        env=comp_env
                    )
                    last_output = (result.stdout or "") + "\n" + (result.stderr or "")

                    # Run secondary pass for pdflatex/xelatex to resolve \input{}, \maketitle, TOC, and Beamer themes
                    if cmd[0] in ["pdflatex", "xelatex", "lualatex"]:
                        result2 = subprocess.run(
                            cmd,
                            cwd=tmpdir,
                            capture_output=True,
                            text=True,
                            timeout=35,
                            env=comp_env
                        )
                        last_output += "\n" + (result2.stdout or "") + "\n" + (result2.stderr or "")

                    pdf_path = tmpdir / "main.pdf"
                    if pdf_path.exists():
                        pdf_bytes = pdf_path.read_bytes()
                        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
                        elapsed_ms = int((time.time() - start_time) * 1000)
                        return {
                            "success": True,
                            "pdf_base64": pdf_base64,
                            "compile_time_ms": elapsed_ms,
                            "log": last_output[-1000:] if last_output else f"Compiled via {cmd[0]}",
                        }
                except Exception:
                    continue

            # Auto-recovery pass for font metric errors (e.g., ecrm1000 / T1 fontenc without cm-super/lmodern)
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
                    for retry_cmd in [["pdflatex", "-interaction=nonstopmode", "-c-style-errors", "main.tex"]]:
                        try:
                            result = subprocess.run(retry_cmd, cwd=tmpdir, capture_output=True, text=True, timeout=30, env=os.environ)
                            pdf_path = tmpdir / "main.pdf"
                            if pdf_path.exists():
                                pdf_bytes = pdf_path.read_bytes()
                                pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
                                elapsed_ms = int((time.time() - start_time) * 1000)
                                return {
                                    "success": True,
                                    "pdf_base64": pdf_base64,
                                    "compile_time_ms": elapsed_ms,
                                    "log": "Compiled via font auto-recovery (lmodern patch)",
                                }
                        except Exception:
                            pass

        except Exception:
            pass

        # Fallback to instant clean ReportLab TeX renderer if binaries are unavailable, timeout, or fail
        try:
            pdf_base64 = generate_fallback_pdf(latex_code, tmpdir=tmpdir)
            elapsed_ms = int((time.time() - start_time) * 1000)
            return {
                "success": True,
                "pdf_base64": pdf_base64,
                "compile_time_ms": elapsed_ms,
                "log": "Rendered via Fast TeX Engine Fallback",
            }
        except Exception as fallback_err:
            return {
                "success": False,
                "error_log": f"Compilation error: {str(fallback_err)}",
            }

