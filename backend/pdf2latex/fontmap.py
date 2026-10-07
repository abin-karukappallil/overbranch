"""
fontmap.py — PDF fonts → pdfLaTeX fonts, weights and slants.

Two jobs, both about making the re-typeset page occupy the same space as the
original:

1. **Family.** A substitute font with different glyph widths moves every line
   end. Calibri set in Helvetica comes out ~10–25% wider, which is what pushed
   text past the right border of converted pages and made right-aligned values
   collide with labels. Where a *metric-compatible* TeX font exists it is used
   (Calibri → Carlito, Cambria → Caladea); otherwise the closest classic family.
   Each package is used only if this TeX installation has it.

2. **Weight / slant.** Bold is read from every signal a PDF offers, because
   producers disagree on which one they set: the font name (``Bold``,
   ``Semibold``, ``Demi``, ``Heavy``, ``Black``, ``,Bd``, ``-B``), PyMuPDF's
   flags, the FontDescriptor's ``/FontWeight`` (≥ 600) and ``/Flags`` ForceBold
   bit, and *synthetic* bold — regular glyphs drawn with fill+stroke (text render
   mode 2) and a visible line width.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Dict, Optional, Set, Tuple

from latex_layout.metrics import tex_package_available

BOLD_NAME_RE = re.compile(
    r"(bold|black|heavy|semibold|semibd|demibold|demi|extrabold|ultrabold)|([-,_ ]bd)$|([-,_ ]b)$",
    re.IGNORECASE,
)
ITALIC_NAME_RE = re.compile(r"(italic|oblique|slanted|kursiv)|([-,_ ]it)$|([-,_ ]i)$", re.IGNORECASE)
FORCE_BOLD_FLAG = 1 << 18  # PDF FontDescriptor /Flags bit 19 (ForceBold)

# Metric-compatible substitutes: (name fragments, TeX package / metrics family, generic family)
METRIC_COMPATIBLE: Tuple[Tuple[Tuple[str, ...], str, str], ...] = (
    (("calibri", "carlito"), "carlito", "sans"),
    (("cambria", "caladea"), "caladea", "serif"),
)

_TIMES = ("times", "tinos", "nimbusrom", "liberationserif", "termes", "stix", "georgia", "minion")
_PALATINO = ("palatino", "palladio", "bookantiqua", "pagella", "garamond", "baskerville")
_LMODERN = ("cmr", "cmbx", "cmti", "cmsl", "lmroman", "sfrm", "sfbx", "sfti", "cmss", "lmsans", "cmtt", "lmmono")
_SANS = ("arial", "helvetica", "verdana", "tahoma", "segoe", "roboto", "opensans", "dejavusans",
         "liberationsans", "arimo", "nimbussans", "heros", "sans", "gothic", "lato", "montserrat",
         "myriad", "franklin", "futura", "gill", "trebuchet", "ubuntu", "inter", "poppins", "candara", "corbel")
_MONO = ("courier", "mono", "consolas", "menlo", "inconsolata", "code", "typewriter", "cousine")

FAMILY_OF = {
    "helvetica": "sans", "carlito": "sans", "courier": "mono",
    "times": "serif", "palatino": "serif", "lmodern": "serif", "caladea": "serif",
}

# How each font class is loaded as the main font. Carlito gets tabular lining
# figures (lf,t): that is Calibri's default, so digits keep Calibri's widths.
FONT_LINES: Dict[str, Tuple[str, ...]] = {
    "lmodern": ("\\usepackage{lmodern}",),
    "times": ("\\usepackage{mathptmx}",),
    "palatino": ("\\usepackage{mathpazo}",),
    "helvetica": ("\\usepackage{lmodern}", "\\usepackage{helvet}", "\\renewcommand{\\familydefault}{\\sfdefault}"),
    "courier": ("\\usepackage{lmodern}", "\\usepackage{courier}", "\\renewcommand{\\familydefault}{\\ttdefault}"),
    "carlito": ("\\usepackage{lmodern}", "\\usepackage[sfdefault,lf,t]{carlito}"),
    "caladea": ("\\usepackage{lmodern}", "\\usepackage{caladea}"),
}
# How a secondary family is made available as \sffamily / \ttfamily.
SECONDARY_LINES: Dict[str, str] = {
    "helvetica": "\\usepackage{helvet}",
    "carlito": "\\usepackage[lf,t]{carlito}",
    "courier": "\\usepackage{courier}",
}


def _clean(name: str) -> str:
    return re.sub(r"^[A-Z]{6}\+", "", name or "")


def _norm(name: str) -> str:
    return _clean(name).lower().replace(" ", "").replace("-", "").replace(",", "").replace("_", "")


@lru_cache(maxsize=16)
def _available(pkg: str) -> bool:
    return tex_package_available(pkg)


def font_class(font_name: str, flags: int = 0) -> str:
    """The TeX font class that best reproduces ``font_name``'s widths."""
    n = _norm(font_name)
    if flags & 8 or any(k in n for k in _MONO):
        return "courier"
    for keys, pkg, _family in METRIC_COMPATIBLE:
        if any(k in n for k in keys) and _available(pkg):
            return pkg
    if any(k in n for k in ("calibri", "carlito")):
        return "helvetica"
    if "cambria" in n or "caladea" in n:
        return "times"
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
    return FAMILY_OF.get(cls, "serif")


def name_is_bold(font_name: str) -> bool:
    base = _clean(font_name)
    return bool(BOLD_NAME_RE.search(base))


def name_is_italic(font_name: str) -> bool:
    return bool(ITALIC_NAME_RE.search(_clean(font_name)))


def descriptor_bold_fonts(doc: Any, page: Any) -> Set[str]:
    """
    Base names of the page's fonts whose FontDescriptor says bold
    (/FontWeight >= 600 or the ForceBold flag), even if the name does not.
    """
    bold: Set[str] = set()
    try:
        fonts = page.get_fonts(full=True)
    except Exception:
        return bold
    for f in fonts:
        xref, basefont = f[0], f[3]
        try:
            desc = doc.xref_get_key(xref, "FontDescriptor")
            if desc[0] != "xref":
                # Type0 fonts keep the descriptor on the descendant font
                desc_fonts = doc.xref_get_key(xref, "DescendantFonts")
                m = re.search(r"(\d+) 0 R", desc_fonts[1] or "")
                if not m:
                    continue
                desc = doc.xref_get_key(int(m.group(1)), "FontDescriptor")
                if desc[0] != "xref":
                    continue
            dxref = int(desc[1].split()[0])
            weight = doc.xref_get_key(dxref, "FontWeight")
            flags = doc.xref_get_key(dxref, "Flags")
            w = float(weight[1]) if weight[0] in ("int", "float") else 0.0
            fl = int(flags[1]) if flags[0] == "int" else 0
            if w >= 600 or fl & FORCE_BOLD_FLAG:
                bold.add(_clean(basefont))
        except Exception:
            continue
    return bold


def synthetic_bold_origins(page: Any) -> Set[Tuple[int, int]]:
    """
    Rounded origins of spans drawn as fake bold: glyphs that are filled AND
    stroked with a visible line width. PyMuPDF reports such text either as one
    fill+stroke span (type 2) or as a fill span (type 0) plus a stroke span
    (type 1) at the same origin. A stroke without a fill is outline text, not
    bold. Keys match Span.origin rounded to 1 pt.
    """
    out: Set[Tuple[int, int]] = set()
    try:
        trace = page.get_texttrace()
    except Exception:
        return out
    filled: Set[Tuple[int, int]] = set()
    stroked: Set[Tuple[int, int]] = set()
    for sp in trace:
        chars = sp.get("chars") or []
        if not chars:
            continue
        ox, oy = chars[0][2]
        key = (round(ox), round(oy))
        kind = sp.get("type")
        width = float(sp.get("linewidth") or 0)
        if kind == 2 and width > 0.05:
            out.add(key)
        elif kind == 0:
            filled.add(key)
        elif kind == 1 and width > 0.05:
            stroked.add(key)
    return out | (filled & stroked)


def outline_stroke_bold(page: Any, paths: Optional[list] = None) -> Tuple[Set[Tuple[int, int]], Set[int]]:
    """
    Fake bold drawn as VECTOR PATHS: the glyphs are filled as text and then
    their outlines are stroked as separate stroke-only paths, one per glyph.
    PyMuPDF sees ordinary-weight text plus hundreds of small curves.

    Returns (rounded origins of the spans that are bold this way, indices into
    ``paths`` of the glyph-outline strokes). Those paths are part of the text:
    they must not be reproduced as drawings or baked into a background image —
    that is what overlaid a second, differently-sized copy of every bold label.
    """
    if paths is None:
        try:
            paths = page.get_drawings()
        except Exception:
            return set(), set()
    spans = []
    try:
        for b in page.get_text("dict").get("blocks", []):
            for ln in b.get("lines", []):
                for sp in ln.get("spans", []):
                    text = sp.get("text", "")
                    if text.strip() and sp.get("origin"):
                        spans.append((tuple(sp["bbox"]), sp["origin"], len(text.replace(" ", ""))))
    except Exception:
        return set(), set()
    if not spans:
        return set(), set()

    hits: Dict[int, int] = {}
    strokes: Set[int] = set()
    for i, p in enumerate(paths):
        if (p.get("type") or "") != "s" or not p.get("items"):
            continue
        r = p.get("rect")
        if r is None:
            continue
        pad = max(1.0, float(p.get("width") or 0.0))
        for k, (bb, _origin, _n) in enumerate(spans):
            h = bb[3] - bb[1]
            if not (r.x0 >= bb[0] - pad and r.x1 <= bb[2] + pad and r.y0 >= bb[1] - pad and r.y1 <= bb[3] + pad):
                continue
            # An underline or strike-through is a thin full-width rule, not a glyph.
            if (r.y1 - r.y0) < 0.25 * h and (r.x1 - r.x0) > 0.5 * (bb[2] - bb[0]):
                continue
            hits[k] = hits.get(k, 0) + 1
            strokes.add(i)
            break
    bold = {(round(spans[k][1][0]), round(spans[k][1][1]))
            for k, n in hits.items() if n >= max(1, 0.5 * spans[k][2])}
    return bold, strokes


def span_weight(font: str, flags: int, descriptor_bold: Optional[Set[str]] = None,
                synthetic: bool = False) -> Tuple[bool, bool]:
    """(bold, italic) for one span from every available signal."""
    bold = bool(flags & 16) or name_is_bold(font) or synthetic or (
        descriptor_bold is not None and _clean(font) in descriptor_bold)
    italic = bool(flags & 2) or name_is_italic(font)
    return bold, italic
