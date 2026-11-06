"""
markers.py — Picture bullets and decorative image strips.

Beamer and some word processors draw list bullets as tiny pictures (a shaded ball, a square) rather
than as a character. Left as images they become stray figures, and the list loses its markers, so
its items merge into one paragraph. A marker-sized image just left of a text row is turned into a
bullet character in the image's colour, at the start of that row; list detection then sees an
ordinary bulleted list. Thin image strips (a box's drop shadow) are decoration: they are dropped from
the content and stay in the page background.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Dict, List, Tuple

from ..models import DocExtract, Line, Span

logger = logging.getLogger("pdf2latex.editable.markers")


def _dominant_size(page) -> float:
    c: Counter = Counter()
    for ln in page.lines:
        for sp in ln.spans:
            c[round(sp.size * 2) / 2] += len(sp.text.strip())
    return c.most_common(1)[0][0] if c else 10.0


def _image_colour(doc, page_no: int, bbox) -> Tuple[int, int, int]:
    """The marker's colour: the mean of its saturated pixels (a shaded ball → its hue)."""
    import pymupdf
    try:
        pix = doc[page_no - 1].get_pixmap(clip=pymupdf.Rect(*bbox), dpi=144, colorspace=pymupdf.csRGB)
        data = pix.samples
        pts = [(data[i], data[i + 1], data[i + 2]) for i in range(0, len(data), 3)]
        sat = [p for p in pts if max(p) - min(p) > 40]
        use = sat or [p for p in pts if sum(p) < 600] or pts
        n = len(use)
        return tuple(int(sum(p[k] for p in use) / n) for k in range(3))
    except Exception:  # noqa: BLE001
        return (0, 0, 0)


def _page_pictures(doc, page) -> List[Tuple[float, float, float, float]]:
    """Every picture on the page, from the PDF itself: the extractor may have folded a slide's
    pictures into its rasterised background and emptied page.images."""
    boxes = [tuple(img.bbox) for img in page.images if img.kind == "image"]
    try:
        boxes += [tuple(i["bbox"]) for i in doc[page.number - 1].get_image_info()]
    except Exception:  # noqa: BLE001
        pass
    out, seen = [], set()
    for bb in boxes:
        key = tuple(round(v, 1) for v in bb)
        if key not in seen:                       # the same picture drawn twice (shading + mask)
            seen.add(key)
            out.append(bb)
    return out


def _vector_bullets(doc, page, size: float) -> List[Tuple[Tuple[float, float, float, float], Tuple[int, int, int]]]:
    """Small filled shapes (Beamer's square bullet is a rule, not a glyph): (box, colour)."""
    out = []
    try:
        paths = doc[page.number - 1].get_drawings()
    except Exception:  # noqa: BLE001
        return out
    for d in paths:
        fill = d.get("fill")
        if not fill or d.get("type") != "f":
            continue
        r = d["rect"]
        w, h = r.x1 - r.x0, r.y1 - r.y0
        if not (2.0 <= w <= 1.1 * size and 2.0 <= h <= 1.1 * size) or not 0.6 <= w / h <= 1.67:
            continue
        rgb = tuple(int(round(c * 255)) for c in fill[:3])
        if min(rgb) >= 245:
            continue
        out.append(((r.x0, r.y0, r.x1, r.y1), rgb))
    return out


def _add_bullet(page, bb, text: str, color, size: float) -> bool:
    """A bullet character at the start of the row just right of ``bb``; False if there is no row."""
    x0, y0, x1, y1 = bb
    cy = (y0 + y1) / 2
    row = [ln for ln in page.lines if ln.text.strip() and ln.bbox[1] - 2 <= cy <= ln.bbox[3] + 2
           and 0 <= ln.bbox[0] - x1 <= 2.5 * size]
    if not row:
        return False
    ln = min(row, key=lambda l: l.bbox[0])
    first = ln.spans[0]
    span = Span(text=text, font=first.font, size=first.size, color=color, flags=first.flags & ~16,
                bbox=(x0, ln.bbox[1], x1, ln.bbox[3]), origin=(x0, ln.baseline))
    page.lines.append(Line(spans=[span], bbox=(x0, ln.bbox[1], x1, ln.bbox[3]), block=ln.block,
                           column=ln.column))
    return True


def convert_image_bullets(doc, extract: DocExtract) -> Dict[int, List[Tuple[float, float, float, float]]]:
    """Rewrite each page in place; returns {page: [marker bboxes]} for the background redaction."""
    markers: Dict[int, List[Tuple[float, float, float, float]]] = {}
    for page in extract.pages:
        for bb, rgb in _vector_bullets(doc, page, _dominant_size(page)):
            if _add_bullet(page, bb, "\u25a0", rgb, _dominant_size(page)):
                markers.setdefault(page.number, []).append(bb)
        pics = _page_pictures(doc, page)
        if not pics:
            continue
        size = _dominant_size(page)
        drop = set()
        for bb in pics:
            x0, y0, x1, y1 = bb
            w, h = x1 - x0, y1 - y0
            if (h <= 4.5 or w <= 4.5) and max(w, h) > 20:
                drop.add(tuple(round(v, 1) for v in bb))   # a thin strip: decoration (a shadow)
                continue
            if w > 1.4 * size or h > 1.4 * size:
                continue
            cy = (y0 + y1) / 2
            row = [ln for ln in page.lines if ln.text.strip()
                   and ln.bbox[1] - 2 <= cy <= ln.bbox[3] + 2
                   and 0 <= ln.bbox[0] - x1 <= 2.5 * size]
            if not row:
                continue
            ln = min(row, key=lambda l: l.bbox[0])
            # a number drawn on the picture (a numbered ball) is the item's label
            on_top = [o for o in page.lines if o is not ln and o.text.strip()
                      and x0 - 1 <= (o.bbox[0] + o.bbox[2]) / 2 <= x1 + 1
                      and y0 - 1 <= (o.bbox[1] + o.bbox[3]) / 2 <= y1 + 1]
            label = on_top[0].text.strip() if on_top and len(on_top[0].text.strip()) <= 3 else ""
            for o in on_top:
                page.lines.remove(o)
            text = f"{label}." if label.isdigit() else (label or "•")
            first = ln.spans[0]
            span = Span(text=text, font=first.font, size=first.size,
                        color=_image_colour(doc, page.number, bb), flags=first.flags & ~16,
                        bbox=(x0, ln.bbox[1], x1, ln.bbox[3]), origin=(x0, ln.baseline))
            page.lines.append(Line(spans=[span], bbox=(x0, ln.bbox[1], x1, ln.bbox[3]),
                                   block=ln.block, column=ln.column))
            markers.setdefault(page.number, []).append(bb)
            drop.add(tuple(round(v, 1) for v in bb))
        page.images = [img for img in page.images
                       if tuple(round(v, 1) for v in img.bbox) not in drop]
    if markers:
        logger.info(f"turned {sum(len(v) for v in markers.values())} picture bullets into bullet characters")
    return markers
