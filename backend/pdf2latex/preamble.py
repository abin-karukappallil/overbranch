"""
preamble.py — Deterministic shared preamble and document assembly.

The preamble comes from the extracted facts only: article class, geometry matching
the page size and content margins, xcolor with one \\definecolor per distinct RGB
found (exact values), graphicx, amsmath/amssymb and the closest pdfLaTeX font
packages for the PDF's fonts. Page bodies (from the LLM or the layout fallback) are
merged under it, separated by \\newpage.
"""

import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional

from .models import RGB, DocExtract
from .texutil import fmt

PAGE_MARK = "%% ==== OB-PAGE {n} ===="
_PAGE_MARK_RE = re.compile(r"^%% ==== OB-PAGE (\d+) ====$", re.MULTILINE)
_INCLUDE_RE = re.compile(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")
MAX_MARGIN = 144.0


@dataclass(frozen=True)
class Geometry:
    paper_w: float
    paper_h: float
    left: float
    top: float
    right: float
    bottom: float

    @property
    def text_w(self) -> float:
        return self.paper_w - self.left - self.right

    @property
    def text_h(self) -> float:
        return self.paper_h - self.top - self.bottom


@dataclass(frozen=True)
class FontPlan:
    main: str  # "times" | "palatino" | "lmodern" | "helvetica" | "courier"
    main_family: str  # "serif" | "sans" | "mono"
    uses_sans: bool
    uses_mono: bool
    body_size: float


def page_geometry(doc: DocExtract) -> Geometry:
    """Most common page size; each margin is the smallest content margin over all pages."""
    sizes = Counter((round(p.width, 1), round(p.height, 1)) for p in doc.pages)
    paper_w, paper_h = sizes.most_common(1)[0][0]
    with_content = [p for p in doc.pages if p.lines or p.images or p.drawings] or doc.pages
    m = [min(p.margins[i] for p in with_content) for i in range(4)]
    left, top, right, bottom = (max(0.0, min(v, MAX_MARGIN) - 1.0) for v in m)
    if paper_w - left - right < 0.3 * paper_w or paper_h - top - bottom < 0.3 * paper_h:
        left = top = right = bottom = 36.0
    return Geometry(paper_w, paper_h, left, top, right, bottom)


def color_name(rgb: RGB) -> str:
    return "c%02X%02X%02X" % tuple(int(v) for v in rgb)


def collect_colors(doc: DocExtract) -> Dict[str, RGB]:
    """Every distinct text / rule / fill color, most used first; black is always defined."""
    counts: Counter = Counter()
    for p in doc.pages:
        for ln in p.lines:
            for sp in ln.spans:
                counts[sp.color] += max(1, len(sp.text.strip()))
        for d in p.drawings:
            for c in (d.stroke, d.fill):
                if c is not None:
                    counts[c] += 1
    counts[(0, 0, 0)] += 0
    return {color_name(rgb): rgb for rgb, _ in counts.most_common()}


_TIMES = ("times", "tinos", "nimbusrom", "liberationserif", "termes", "stix", "cambria", "georgia", "minion")
_PALATINO = ("palatino", "palladio", "bookantiqua", "pagella", "garamond", "baskerville")
_LMODERN = ("cmr", "cmbx", "cmti", "cmsl", "lmroman", "sfrm", "sfbx", "sfti", "cmss", "lmsans", "cmtt", "lmmono")
_SANS = ("arial", "helvetica", "calibri", "verdana", "tahoma", "segoe", "roboto", "opensans", "dejavusans",
         "liberationsans", "arimo", "nimbussans", "heros", "sans", "gothic", "lato", "montserrat", "carlito",
         "myriad", "franklin", "futura", "gill", "trebuchet", "ubuntu", "inter", "poppins", "candara", "corbel")
_MONO = ("courier", "mono", "consolas", "menlo", "inconsolata", "code", "typewriter", "cousine")


def font_class(font_name: str, flags: int = 0) -> str:
    n = re.sub(r"^[A-Z]{6}\+", "", font_name or "").lower().replace(" ", "").replace("-", "")
    if flags & 8 or any(k in n for k in _MONO):
        return "courier"
    if any(k in n for k in _LMODERN):
        return "lmodern"
    if any(k in n for k in _PALATINO):
        return "palatino"
    if any(k in n for k in _TIMES):
        return "times"
    if any(k in n for k in _SANS):
        return "helvetica"
    return "times" if flags & 4 else "helvetica"


def family_of(cls: str) -> str:
    return {"helvetica": "sans", "courier": "mono"}.get(cls, "serif")


def plan_fonts(doc: DocExtract) -> FontPlan:
    by_class: Counter = Counter()
    by_size: Counter = Counter()
    for p in doc.pages:
        for ln in p.lines:
            for sp in ln.spans:
                n = len(sp.text.strip())
                if n:
                    by_class[font_class(sp.font, sp.flags)] += n
                    by_size[round(sp.size * 2) / 2] += n
    main = by_class.most_common(1)[0][0] if by_class else "lmodern"
    families = {family_of(c) for c in by_class}
    main_family = family_of(main)
    return FontPlan(
        main=main,
        main_family=main_family,
        uses_sans="sans" in families and main_family != "sans",
        uses_mono="mono" in families and main_family != "mono",
        body_size=float(by_size.most_common(1)[0][0]) if by_size else 10.0,
    )


_FONT_LINES = {
    "lmodern": ["\\usepackage{lmodern}"],
    "times": ["\\usepackage{mathptmx}"],
    "palatino": ["\\usepackage{mathpazo}"],
    "helvetica": ["\\usepackage{lmodern}", "\\usepackage{helvet}", "\\renewcommand{\\familydefault}{\\sfdefault}"],
    "courier": ["\\usepackage{lmodern}", "\\usepackage{courier}", "\\renewcommand{\\familydefault}{\\ttdefault}"],
}


def build_preamble(geom: Geometry, colors: Dict[str, RGB], fonts: FontPlan) -> str:
    lines = [
        "% Generated by OverBranch PDF import (best-effort reproduction; compile with pdfLaTeX).",
        "\\documentclass{article}",
        "\\usepackage[T1]{fontenc}",
        "\\usepackage[utf8]{inputenc}",
        "\\usepackage{textcomp}",
        *_FONT_LINES[fonts.main],
    ]
    if fonts.uses_sans:
        lines.append("\\usepackage{helvet}")
    if fonts.uses_mono:
        lines.append("\\usepackage{courier}")
    lines += [
        f"\\usepackage[paperwidth={fmt(geom.paper_w)}bp,paperheight={fmt(geom.paper_h)}bp,"
        f"left={fmt(geom.left)}bp,right={fmt(geom.right)}bp,top={fmt(geom.top)}bp,bottom={fmt(geom.bottom)}bp]{{geometry}}",
        "\\usepackage[table]{xcolor}",
        "\\usepackage{graphicx}",
        "\\usepackage{amsmath,amssymb}",
        "\\usepackage{array,tabularx,booktabs,multirow}",
        "\\usepackage{multicol}",
        "\\usepackage{enumitem}",
        "\\usepackage{ragged2e}",
        "\\usepackage{tikz}",
        "\\usepackage{eso-pic}",
        "\\usepackage{url}",
    ]
    lines += [f"\\definecolor{{{name}}}{{RGB}}{{{r},{g},{b}}}" for name, (r, g, b) in colors.items()]
    size, lead = fmt(fonts.body_size), fmt(fonts.body_size * 1.2)
    lines += [
        "\\pagestyle{empty}",
        "\\setlength{\\parindent}{0pt}",
        "\\setlength{\\parskip}{0pt}",
        "\\setlength{\\topskip}{0pt}",
        "\\setlength{\\emergencystretch}{2em}",
        "\\raggedbottom",
        # Shrinks a page body that would spill onto a second page (overflow fallback)
        "\\newsavebox{\\obpagebox}",
        "\\newcommand{\\obfit}[1]{\\sbox{\\obpagebox}{\\begin{minipage}[t]{\\linewidth}#1\\end{minipage}}%",
        "  \\ifdim\\dimexpr\\ht\\obpagebox+\\dp\\obpagebox\\relax>\\dimexpr\\textheight-2pt\\relax"
        "\\resizebox*{!}{\\dimexpr\\textheight-2pt\\relax}{\\usebox{\\obpagebox}}\\else\\usebox{\\obpagebox}\\fi}",
        f"\\AtBeginDocument{{\\fontsize{{{size}bp}}{{{lead}bp}}\\selectfont}}",
    ]
    return "\n".join(lines)


def background_command(file: str) -> str:
    return ("\\AddToShipoutPictureBG*{\\AtPageLowerLeft{\\includegraphics[width=\\paperwidth,"
            f"height=\\paperheight]{{{file}}}}}}}")


_STRIP_LINE_RE = re.compile(r"^\s*\\(documentclass|usepackage|RequirePackage|usetikzlibrary)\b.*$", re.MULTILINE)
_EDGE_BREAK_RE = re.compile(r"^(\s*\\(newpage|clearpage|pagebreak)\b(\[[^\]]*\])?\s*)+|(\s*\\(newpage|clearpage|pagebreak)\b(\[[^\]]*\])?\s*)+$")


def clean_body(text: str) -> str:
    """Keeps only body LaTeX: drops fences, commentary around a fenced block, preamble lines and edge page breaks."""
    b = (text or "").strip()
    fenced = re.search(r"```[a-zA-Z]*\s*\n(.*?)```", b, re.DOTALL)
    if fenced:
        b = fenced.group(1)
    if "\\begin{document}" in b:
        b = b.split("\\begin{document}", 1)[1]
    if "\\end{document}" in b:
        b = b.split("\\end{document}", 1)[0]
    b = _STRIP_LINE_RE.sub("", b)
    prev = None
    while prev != b:
        prev = b
        b = _EDGE_BREAK_RE.sub("", b.strip())
    return b.strip()


def assemble_document(preamble: str, bodies: Dict[int, str]) -> str:
    empty = "\\null"  # keeps an empty page as a page
    parts = [PAGE_MARK.format(n=n) + "\n" + (bodies[n].strip() or empty) for n in sorted(bodies)]
    return preamble + "\n\\begin{document}\n" + "\n\\newpage\n".join(parts) + "\n\\end{document}\n"


def standalone_page(preamble: str, body: str, n: int) -> str:
    return assemble_document(preamble, {n: body})


def page_for_line(tex: str, line_no: int) -> Optional[int]:
    """1-based source line → page number of the OB-PAGE block containing it."""
    page = None
    for i, line in enumerate(tex.splitlines(), start=1):
        if i > line_no:
            break
        m = _PAGE_MARK_RE.match(line)
        if m:
            page = int(m.group(1))
    return page


def body_of(tex: str, n: int) -> Optional[str]:
    """Extracts page n's body from an assembled document."""
    m = re.search(re.escape(PAGE_MARK.format(n=n)) + r"\n(.*?)(?=\n\\newpage\n%% ==== OB-PAGE |\n\\end\{document\})",
                  tex, re.DOTALL)
    return m.group(1) if m else None


def referenced_files(body: str) -> List[str]:
    return sorted({m.group(1).strip() for m in _INCLUDE_RE.finditer(body)})
