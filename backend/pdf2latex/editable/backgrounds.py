"""
backgrounds.py — Page decoration that is not content.

A slide deck's template (side bar, tinted background, footer band with the talk title and slide
number) is drawn the same way on every slide. It is not text a student edits, so instead of turning
it into coordinates it is kept as a background picture of the page with the body text and the
content images removed; the content itself stays ordinary LaTeX laid over it. Pages whose vector art
the extractor already rasterised (``PageExtract.background``) reuse that picture.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Set, Tuple

from ..models import DocExtract

logger = logging.getLogger("pdf2latex.editable.backgrounds")

BG_DPI = 150


def page_backgrounds(doc, extract: DocExtract, furniture_ids: Set[Tuple[int, int]], out_dir: Path,
                     deck: bool, boxes=None, markers=None) -> Dict[int, str]:
    """{page number: project-relative background image} for decorated pages. A deck's slides are
    always rendered here, so content boxes and emitted rules can be taken out of the picture;
    other pages reuse the extractor's rasterised vector art."""
    out: Dict[int, str] = {}
    boxes = boxes or {}
    markers = markers or {}
    for p in extract.pages:
        if deck:
            rel = _render_without_content(doc, p, furniture_ids, out_dir, extract.asset_prefix,
                                          boxes.get(p.number, []), markers.get(p.number, []))
            if rel:
                out[p.number] = rel
        elif p.background:
            out[p.number] = p.background
    return out


def _render_without_content(doc, page, furniture_ids, out_dir: Path, prefix: str, boxes=(),
                            markers=()):
    """The page with its body text and content images redacted: decoration and furniture remain."""
    import pymupdf
    try:
        tmp = pymupdf.open()
        tmp.insert_pdf(doc, from_page=page.number - 1, to_page=page.number - 1)
        pg = tmp[0]
        # Rules the converter emits as content (\rule) and shaded content boxes (emitted as
        # tcolorbox) come out of the picture; only area decoration (tint, bars, bands) stays. A page
        # whose drawings the extractor rasterised has no emitted rules, so its rules stay.
        shapes = [d.rect for d in page.drawings
                  if d.kind == "hrule" and (d.rect[2] - d.rect[0]) >= 0.15 * page.width]
        shapes += [b["bbox"] for b in boxes]
        if shapes:
            for x0, y0, x1, y1 in shapes:
                pg.add_redact_annot(pymupdf.Rect(x0 - 1, y0 - 1.5, x1 + 1, y1 + 1.5))
            pg.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                                graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                                text=pymupdf.PDF_REDACT_TEXT_NONE)
        keep = [ln.bbox for i, ln in enumerate(page.lines)
                if (page.number, i) in furniture_ids and ln.text.strip()]
        for i, ln in enumerate(page.lines):
            if (page.number, i) in furniture_ids or not ln.text.strip():
                continue                       # running footer / slide number stay in the picture
            # the glyphs' own height, not the line box, so a footer just below isn't clipped
            size = max(sp.size for sp in ln.spans)
            base = ln.baseline
            r = pymupdf.Rect(ln.bbox[0] - 0.5, base - 0.82 * size, ln.bbox[2] + 0.5, base + 0.24 * size)
            # nor one just above or below: a redaction removes every glyph it touches
            for k in keep:
                if r.x0 < k[2] and k[0] < r.x1 and r.y0 < k[3] and k[1] < r.y1:
                    if base <= (k[1] + k[3]) / 2:
                        r.y1 = min(r.y1, k[1] - 0.1)
                    else:
                        r.y0 = max(r.y0, k[3] + 0.1)
            if r.y1 > r.y0:
                pg.add_redact_annot(r)
        for img in page.images:
            if img.kind in ("image", "figure"):
                pg.add_redact_annot(pymupdf.Rect(*img.bbox))
        for bb in markers:                       # picture bullets became bullet characters
            pg.add_redact_annot(pymupdf.Rect(*bb))
        pg.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
                            graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
        rel = f"{prefix}/page{page.number}_bg.png"
        path = out_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        pg.get_pixmap(dpi=BG_DPI).save(str(path))
        tmp.close()
        # Pictures reused through a form XObject (Beamer's shaded bullets, a box's drop shadow)
        # survive redaction, so they are painted out of the rendered picture with the colour around
        # them.
        erase = list(markers)
        try:
            for i in doc[page.number - 1].get_image_info():
                x0, y0, x1, y1 = i["bbox"]
                near_box = any(bx0 - 6 <= x0 and x1 <= bx1 + 6 and by0 - 8 <= y0 and y1 <= by1 + 8
                               for bx0, by0, bx1, by1 in (b["bbox"] for b in boxes))
                if near_box:
                    erase.append((x0, y0, x1, y1))
        except Exception:  # noqa: BLE001
            pass
        if erase:
            _paint_out(path, erase, page.width, page.height)
        return rel
    except Exception as e:  # noqa: BLE001 — a missing background never fails the conversion
        logger.debug(f"background render failed for page {page.number}: {e}")
        return None


def _paint_out(path: Path, rects, page_w: float, page_h: float) -> None:
    """Fill each rect (pt) in the PNG with the median colour of a thin ring just outside it."""
    from PIL import Image
    img = Image.open(path).convert("RGB")
    sx, sy = img.width / page_w, img.height / page_h
    px = img.load()
    for x0, y0, x1, y1 in rects:
        a, b = max(0, int(x0 * sx) - 2), max(0, int(y0 * sy) - 2)
        c, d = min(img.width - 1, int(x1 * sx) + 2), min(img.height - 1, int(y1 * sy) + 2)
        ring = []
        for x in range(max(0, a - 3), min(img.width, c + 4)):
            for y in (max(0, b - 3), min(img.height - 1, d + 3)):
                ring.append(px[x, y])
        for y in range(max(0, b - 3), min(img.height, d + 4)):
            for x in (max(0, a - 3), min(img.width - 1, c + 3)):
                ring.append(px[x, y])
        if not ring:
            continue
        col = tuple(sorted(v[k] for v in ring)[len(ring) // 2] for k in range(3))
        for x in range(a, c + 1):
            for y in range(b, d + 1):
                px[x, y] = col
    img.save(path)
