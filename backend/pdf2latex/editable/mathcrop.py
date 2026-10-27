"""
mathcrop.py — Detect math regions and crop them to images.

Equations drawn with Symbol/CM-math private-use glyphs cannot be written as text (latex_text drops
them), so the faithful default is to crop the region to a PNG and place it inline. A region is math
when most of its characters are in a math font or private-use range. Flagged polish="math" only
when the glyphs carry real Unicode (a TeX-produced PDF), where the LLM might reconstruct real math.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List

from ..models import PageExtract
from .columns import is_math_span
from .model import Block, Math

logger = logging.getLogger("pdf2latex.editable.mathcrop")

FIGURE_DPI = 200


def detect_math(pg, page: PageExtract, asset_prefix: str, out_dir: Path, furniture_ids=None) -> List[Block]:
    """Group adjacent math-heavy lines into regions and crop each to a PNG under out_dir."""
    out: List[Block] = []
    try:
        import pymupdf
    except ImportError:  # pragma: no cover
        import fitz as pymupdf
    # running header/footer lines must never be swept into an equation crop (a cases brace whose
    # bottom edge nearly touches the footer)
    furn = {id(page.lines[i]) for (pno, i) in (furniture_ids or ()) if pno == page.number and i < len(page.lines)}
    # A tall assembled delimiter means a displayed structure whose rows the per-line test misses — a
    # cases/piecewise brace (its rows carry condition prose "if P = 0"), a big matrix bracket. Crop
    # the whole band (lead, rows, delimiter, equation number) as one image rather than letting the
    # glyphs shatter into text.
    excluded: set = set()
    for k, (rx0, ry0, rx1, ry1) in enumerate(_delimiter_regions(page), 1):
        band = [ln for ln in page.lines if ln.text.strip() and id(ln) not in furn
                and ry0 - 2 <= (ln.bbox[1] + ln.bbox[3]) / 2 <= ry1 + 2]
        # on a two-column page the band is the delimiter's column only: the other column's lines
        # level with it are text, not part of the equation
        cx = page.width / 2
        two_col = (sum(1 for l in page.lines if l.bbox[2] < cx - 4 and l.bbox[2] - l.bbox[0] > 0.3 * cx) >= 6
                   and sum(1 for l in page.lines if l.bbox[0] > cx + 4 and l.bbox[2] - l.bbox[0] > 0.3 * cx) >= 6)
        if band and two_col and not any(l.bbox[0] < cx - 4 and l.bbox[2] > cx + 4 for l in band):
            left_side = (rx0 + rx1) / 2 < cx
            band = [l for l in band if ((l.bbox[0] + l.bbox[2]) / 2 < cx) == left_side]
        if len(band) < 2:
            continue
        x0 = min(min(l.bbox[0] for l in band), rx0) - 2
        y0 = min(min(l.bbox[1] for l in band), ry0) - 2
        x1 = max(max(l.bbox[2] for l in band), rx1) + 2
        y1 = max(max(l.bbox[3] for l in band), ry1) + 2
        # a tall delimiter's bbox can reach into the page footer below it; the crop rectangle renders
        # whatever pixels it covers, so cap it just short of any header/footer line in the band.
        mid = (ry0 + ry1) / 2
        furn_lines = [page.lines[i] for (pno, i) in (furniture_ids or ())
                      if pno == page.number and i < len(page.lines)]
        below = [l.bbox[1] for l in furn_lines if (l.bbox[1] + l.bbox[3]) / 2 > mid and l.bbox[1] < y1]
        if below:
            y1 = min(y1, min(below) - 1)
        above = [l.bbox[3] for l in furn_lines if (l.bbox[1] + l.bbox[3]) / 2 < mid and l.bbox[3] > y0]
        if above:
            y0 = max(y0, max(above) + 1)
        rel = f"{asset_prefix}/page{page.number}_eqbrace{k}.png"
        try:
            out_path = out_dir / rel
            out_path.parent.mkdir(parents=True, exist_ok=True)
            pg.get_pixmap(clip=pymupdf.Rect(x0, y0, x1, y1), dpi=FIGURE_DPI).save(str(out_path))
        except Exception as e:  # noqa: BLE001
            logger.debug(f"delimiter crop failed p{page.number}: {e}")
            continue
        out.append(Math(page=page.number, bbox=(x0, y0, x1, y1), image=rel,
                        width_frac=min(0.9, round((x1 - x0) / (page.width * 0.8), 2)),
                        polish=None, glyphs=[], number=None))
        excluded.update(id(ln) for ln in band)
    # Computer Modern roman in a document set in another face only ever sets maths (the digits,
    # brackets and "=" of a TeX equation), so there it counts as a maths font
    cm_math = not _body_is_cm(page)
    prose = [ln for ln in page.lines if id(ln) not in excluded and ln.text.strip() and not _is_math_line(ln, cm_math)
             and len(re.findall(r"[A-Za-z]{3,}", ln.text)) >= 1 and not _OPERATOR.match(ln.text.strip())]
    # A symbol standing level with ordinary text on the same row is a table label or an inline
    # symbol ("δ  Variational Symbol"), not a displayed equation, so it stays text.
    math_lines = [ln for ln in page.lines if id(ln) not in excluded and ln.text.strip() and _is_math_line(ln, cm_math)
                  and not any(abs(ln.baseline - o.baseline) <= 3 for o in prose)]
    if not math_lines:
        return out
    # an operator name set in the text font ("log", "max") on an equation's baseline is part of it
    for ln in page.lines:
        if ln in math_lines or not _OPERATOR.match(ln.text.strip()):
            continue
        if any(abs(ln.baseline - m.baseline) <= 4 and min(abs(ln.bbox[2] - m.bbox[0]), abs(m.bbox[2] - ln.bbox[0])) <= 60
               for m in math_lines):
            math_lines.append(ln)
    math_lines.sort(key=lambda l: l.bbox[1])
    clusters = [[math_lines[0]]]
    for ln in math_lines[1:]:
        if ln.bbox[1] - clusters[-1][-1].bbox[3] <= 1.5 * (ln.bbox[3] - ln.bbox[1]):
            clusters[-1].append(ln)
        else:
            clusters.append([ln])
    try:
        import pymupdf
    except ImportError:  # pragma: no cover
        import fitz as pymupdf
    for k, cl in enumerate(clusters, 1):
        x0 = min(l.bbox[0] for l in cl) - 2
        y0 = min(l.bbox[1] for l in cl) - 2
        x1 = max(l.bbox[2] for l in cl) + 2
        y1 = max(l.bbox[3] for l in cl) + 2
        rel = f"{asset_prefix}/page{page.number}_eq{k}.png"
        try:
            out_path = out_dir / rel
            out_path.parent.mkdir(parents=True, exist_ok=True)
            pix = pg.get_pixmap(clip=pymupdf.Rect(x0, y0, x1, y1), dpi=FIGURE_DPI)
            pix.save(str(out_path))
        except Exception as e:  # noqa: BLE001
            logger.debug(f"equation crop failed p{page.number}: {e}")
            continue
        # every glyph inside the crop (not only the maths-heavy lines): the crop shows all of them,
        # so a reconstruction is checked against all of them
        in_box = [ln for ln in page.lines if ln.text.strip()
                  and x0 <= (ln.bbox[0] + ln.bbox[2]) / 2 <= x1 and y0 <= (ln.bbox[1] + ln.bbox[3]) / 2 <= y1]
        glyphs = [{"t": sp.text, "x": round(sp.bbox[0], 1), "y": round(sp.origin[1], 1),
                   "sz": round(sp.size, 1), "f": sp.font.split("+")[-1][-20:]}
                  for ln in in_box for sp in ln.spans if sp.text.strip()]
        # a text model can only rebuild glyphs it can read: no private-use character may remain
        has_unicode = bool(glyphs) and not any(_is_pua(g["t"]) for g in glyphs)
        glyphs.sort(key=lambda g: (round(g["y"] / 3), g["x"]))
        number = None
        last = glyphs[-1]["t"].strip() if glyphs else ""
        if re.fullmatch(r"\(\d{1,3}[a-z]?\)", last):
            number = last
        out.append(Math(page=page.number, bbox=(x0, y0, x1, y1), image=rel,
                        width_frac=min(0.9, round((x1 - x0) / (page.width * 0.8), 2)),
                        polish="math" if has_unicode else None, glyphs=glyphs, number=number))
    return out


_CM_TEXT = re.compile(r"(?:^|[+\W])(?:CMR|CMBX|CMTI|CMSL|CMSS|LMRoman|LMMono)", re.IGNORECASE)


# Fonts that hold the tall assembled delimiters of a displayed structure — a cases/piecewise brace,
# a big matrix bracket, a tall fraction's rule — rather than letters: the TeX/newtx extension sizes.
_EXT_DELIM_RE = re.compile(r"(txexs|cmex|stmary|yhlarge|mnsymbol|fourier.*ex|size\d)", re.IGNORECASE)


def _body_size(page: PageExtract) -> float:
    sizes = sorted(sp.size for ln in page.lines for sp in ln.spans if sp.size)
    return sizes[len(sizes) // 2] if sizes else 10.0


def _delimiter_regions(page: PageExtract) -> List[tuple]:
    """Vertical bands spanned by a tall assembled delimiter (≥2.2× body height) — a cases brace or a
    big matrix bracket. Overlapping/adjacent tall spans merge into one band; the caller crops the
    whole band (lead, rows and delimiter) as a single equation image."""
    body = _body_size(page)
    tall = [sp.bbox for ln in page.lines for sp in ln.spans
            if _EXT_DELIM_RE.search(sp.font or "") and (sp.bbox[3] - sp.bbox[1]) > 2.2 * body]
    if not tall:
        return []
    tall.sort(key=lambda b: b[1])
    regions: List[List[float]] = []
    for b in tall:
        if regions and b[1] <= regions[-1][3] + body:
            r = regions[-1]
            regions[-1] = [min(r[0], b[0]), min(r[1], b[1]), max(r[2], b[2]), max(r[3], b[3])]
        else:
            regions.append([b[0], b[1], b[2], b[3]])
    return [tuple(r) for r in regions]


def _body_is_cm(page: PageExtract) -> bool:
    """Whether the page's text is mostly set in Computer/Latin Modern (then CMR is body text)."""
    total = cm = 0
    for ln in page.lines:
        for sp in ln.spans:
            n = len(sp.text.strip())
            total += n
            if _CM_TEXT.search(sp.font or ""):
                cm += n
    return total > 0 and cm >= 0.5 * total


def _is_math_line(ln, cm_math: bool = False) -> bool:
    """A line is math only if most of it is math glyphs AND it has little prose. A prose line with
    an inline symbol (≥3 ordinary words) is not math, so it is never cropped out of the text."""
    chars = sum(len(sp.text.strip()) for sp in ln.spans) or 1
    mchars = sum(len(sp.text.strip()) for sp in ln.spans
                 if is_math_span(sp) or (cm_math and _CM_TEXT.search(sp.font or "")))
    share = mchars / chars
    import re as _re
    prose_words = len(_re.findall(r"[A-Za-z]{4,}", ln.text))
    return share >= 0.6 and prose_words <= 2


_OPERATOR = re.compile(r"^(?:log|ln|lg|exp|sin|cos|tan|max|min|arg\s?max|arg\s?min|lim|det|sup|inf|"
                       r"Pr|mod|sgn|softmax|tanh|sigmoid|E)$")


def _is_pua(text: str) -> bool:
    return any(0xE000 <= ord(c) <= 0xF8FF for c in text)
