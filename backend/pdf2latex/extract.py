"""
extract.py — Local fact extraction with PyMuPDF (no LLM).

Per page: size, content margins, text spans (font, size, exact RGB, flags, bbox,
baseline), vector drawings (rules, rectangles, complex paths), images saved as
page{n}_img{k}.<png|jpg>, and scanned-page detection (an invisible OCR layer is
used as the text when present).

Vector art that LaTeX rules cannot express (curves, diagonals, gradients, dense
charts) is rasterized: regions become figure images page{n}_fig{k}.png (their text
included, so those lines leave the facts); art covering most of the page becomes a
text-free background page{n}_bg.png placed behind the real text.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pymupdf

from .fontmap import outline_stroke_bold
from .models import BBox, DocExtract, Drawing, ImageRef, Line, PageExtract, Span

logger = logging.getLogger("pdf2latex.extract")

SCANNED_MAX_CHARS = 20
SCANNED_MIN_IMAGE_COVERAGE = 0.5
FIGURE_DPI = 200
BACKGROUND_DPI = 200
BACKGROUND_MIN_COVERAGE = 0.4
FIGURE_MIN_AREA = 150.0  # pt²; smaller complex paths (bullets, icons) stay as shape marks
CLUSTER_PAD = 6.0
DENSE_DRAWINGS = 400  # beyond this many paths a page's vector art is treated as one region
AXIS_TOL = 0.6


class PdfValidationError(ValueError):
    pass


def open_pdf(pdf_bytes: bytes) -> "pymupdf.Document":
    """Opens and validates PDF bytes. Raises PdfValidationError for non-PDF, broken or encrypted files."""
    if not pdf_bytes or not pdf_bytes.lstrip()[:5].startswith(b"%PDF-"):
        raise PdfValidationError("File is not a PDF (missing %PDF- header).")
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise PdfValidationError(f"PDF could not be parsed: {e}") from e
    if doc.needs_pass:
        doc.close()
        raise PdfValidationError("PDF is password-protected.")
    if doc.page_count == 0:
        doc.close()
        raise PdfValidationError("PDF has no pages.")
    return doc


def normalize_rotation(doc: "pymupdf.Document") -> None:
    """Bakes /Rotate into page contents so every coordinate is in the displayed orientation."""
    for page in doc:
        if page.rotation:
            try:
                page.remove_rotation()
            except Exception as e:  # older PyMuPDF
                logger.warning(f"Could not normalize rotation on page {page.number + 1}: {e}")


def _rgb_from_int(c: int) -> Tuple[int, int, int]:
    return ((c >> 16) & 255, (c >> 8) & 255, c & 255)


def _rgb_from_floats(c) -> Optional[Tuple[int, int, int]]:
    if c is None:
        return None
    if len(c) == 1:  # gray
        v = int(round(c[0] * 255))
        return (v, v, v)
    if len(c) == 4:  # CMYK
        cc, m, y, k = c
        return (
            int(round(255 * (1 - cc) * (1 - k))),
            int(round(255 * (1 - m) * (1 - k))),
            int(round(255 * (1 - y) * (1 - k))),
        )
    return tuple(max(0, min(255, int(round(v * 255)))) for v in c[:3])  # type: ignore[return-value]


def _area(b: BBox) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _union(boxes: List[BBox]) -> Optional[BBox]:
    boxes = [b for b in boxes if b and b[2] > b[0] and b[3] > b[1]]
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _inside(inner: BBox, outer: BBox, tol: float = 1.0) -> bool:
    return (inner[0] >= outer[0] - tol and inner[1] >= outer[1] - tol
            and inner[2] <= outer[2] + tol and inner[3] <= outer[3] + tol)


def _center_inside(b: BBox, outer: BBox) -> bool:
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

def _invisible_text_keys(page: "pymupdf.Page") -> set:
    """Keys (rounded first-char origin) of spans drawn invisibly (render mode 3) or fully transparent."""
    keys = set()
    try:
        for tr in page.get_texttrace():
            if tr.get("type") == 3 or (tr.get("opacity") is not None and tr.get("opacity") <= 0.01):
                chars = tr.get("chars") or []
                if chars:
                    ox, oy = chars[0][2]
                    keys.add((round(ox, 1), round(oy, 1)))
    except Exception:
        pass
    return keys


def _extract_lines(page: "pymupdf.Page", outline_bold: Optional[set] = None) -> List[Line]:
    from .fontmap import descriptor_bold_fonts, synthetic_bold_origins

    flags = pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP
    raw = page.get_text("dict", flags=flags)
    invisible = _invisible_text_keys(page)
    desc_bold = descriptor_bold_fonts(page.parent, page)
    fake_bold = synthetic_bold_origins(page) | (outline_bold or set())
    lines: List[Line] = []
    for b_idx, block in enumerate(raw.get("blocks", [])):
        if block.get("type", 0) != 0:
            continue
        for ln in block.get("lines", []):
            spans: List[Span] = []
            all_invisible = True
            for sp in ln.get("spans", []):
                text = sp.get("text", "")
                if not text:
                    continue
                origin = tuple(sp.get("origin", (sp["bbox"][0], sp["bbox"][3])))
                hidden = (round(origin[0], 1), round(origin[1], 1)) in invisible or sp.get("alpha", 255) == 0
                if not hidden:
                    all_invisible = False
                font = sp.get("font", "")
                spans.append(Span(
                    text=text,
                    font=font,
                    size=float(sp.get("size", 10.0)),
                    color=_rgb_from_int(int(sp.get("color", 0))),
                    flags=int(sp.get("flags", 0)),
                    bbox=tuple(sp["bbox"]),
                    origin=(float(origin[0]), float(origin[1])),
                    force_bold=(re.sub(r"^[A-Z]{6}\+", "", font) in desc_bold
                                or (round(origin[0]), round(origin[1])) in fake_bold),
                ))
            if spans and any(s.text.strip() for s in spans):
                lines.append(Line(spans=spans, bbox=tuple(ln["bbox"]), block=b_idx, invisible=all_invisible))
    return order_lines(collapse_overprint(lines))


def _overprint_tolerance(size: float) -> Tuple[float, float]:
    """How far apart (dx, dy) two copies of a run may be and still be one overprinted run."""
    return max(1.0, 0.12 * size), max(0.6, 0.06 * size)


def collapse_overprint(lines: List[Line]) -> List[Line]:
    """
    Removes the extra copies of text a producer drew more than once at (almost)
    the same spot, and marks the surviving run bold.

    Many PDF producers fake bold by drawing a run twice — fill then stroke, or
    two fills a fraction of a point apart. PyMuPDF reports every copy as its own
    line, so each bold label used to reach the facts (and the word-coverage gate,
    which counts words as a multiset) twice: the converter then had to typeset it
    twice, and the two copies — set in a real bold of slightly different width —
    showed up as "double-layered" text.
    """
    kept: List[Span] = []
    out: List[Line] = []
    for ln in lines:
        survivors: List[Span] = []
        for sp in ln.spans:
            text = sp.text.strip()
            if not text:
                survivors.append(sp)
                continue
            dx_tol, dy_tol = _overprint_tolerance(sp.size)
            twin = next((k for k in kept if k.text.strip() == text
                         and abs(k.origin[0] - sp.origin[0]) <= dx_tol
                         and abs(k.origin[1] - sp.origin[1]) <= dy_tol
                         and abs(k.size - sp.size) <= 0.5), None)
            if twin is not None:
                twin.force_bold = True
                continue
            kept.append(sp)
            survivors.append(sp)
        if any(s.text.strip() for s in survivors):
            if len(survivors) != len(ln.spans):
                xs = [s.bbox for s in survivors if s.text.strip()]
                ln = Line(spans=survivors, bbox=(min(b[0] for b in xs), min(b[1] for b in xs),
                                                 max(b[2] for b in xs), max(b[3] for b in xs)),
                          block=ln.block, invisible=ln.invisible, column=ln.column)
            out.append(ln)
    return out


# --- reading order ---------------------------------------------------------

GUTTER_MIN = 8.0   # pt of empty width/height that separates two independent regions
_CUT_LIMIT = 6     # recursion depth; deeper than this a page is not a column layout


def _bbox_of(lines: List[Line]) -> BBox:
    return (min(l.bbox[0] for l in lines), min(l.bbox[1] for l in lines),
            max(l.bbox[2] for l in lines), max(l.bbox[3] for l in lines))


def _widest_gap(spans: List[Tuple[float, float]], lo: float, hi: float) -> Optional[float]:
    """Largest empty band in [lo, hi] not touching either end; returns its midpoint."""
    best, best_w = None, GUTTER_MIN
    edge = lo
    for a, b in sorted(spans):
        if a - edge > best_w and edge > lo:
            best, best_w = (edge + a) / 2.0, a - edge
        edge = max(edge, b)
    return best


def _xy_cut(groups: List[List[Line]], depth: int = 0) -> List[List[Line]]:
    """
    Classic XY-cut: split on an empty horizontal band (top before bottom), else on an empty
    vertical gutter (left before right), else fall back to top-to-bottom, left-to-right.

    Without this the lines keep PyMuPDF's block order, which follows the PDF content stream.
    A page whose margin notes were drawn after the body therefore handed the model the whole
    body, then jumped back to the top of the page for the notes — so the notes were woven into
    the running text and the vertical gap across the jump came out at -352pt.
    """
    if len(groups) <= 1 or depth >= _CUT_LIMIT:
        return groups
    boxes = [(_bbox_of(g), g) for g in groups]
    x0 = min(b[0] for b, _ in boxes); x1 = max(b[2] for b, _ in boxes)
    y0 = min(b[1] for b, _ in boxes); y1 = max(b[3] for b, _ in boxes)
    for horizontal in (True, False):
        spans = [((b[1], b[3]) if horizontal else (b[0], b[2])) for b, _ in boxes]
        cut = _widest_gap(spans, y0 if horizontal else x0, y1 if horizontal else x1)
        if cut is None:
            continue
        i = 1 if horizontal else 0
        first = [g for b, g in boxes if b[i + 2] <= cut]
        second = [g for b, g in boxes if b[i + 2] > cut]
        if first and second:
            return _xy_cut(first, depth + 1) + _xy_cut(second, depth + 1)
    return sorted(groups, key=lambda g: (_bbox_of(g)[1], _bbox_of(g)[0]))


def _overlap_ratio(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Horizontal overlap of two x-ranges, as a fraction of the narrower one."""
    inner = min(a[1], b[1]) - max(a[0], b[0])
    narrow = min(a[1] - a[0], b[1] - b[0])
    return inner / narrow if narrow > 0 else 0.0


def _group_lines(lines: List[Line]) -> List[List[Line]]:
    """
    Lines clustered into text blocks by horizontal overlap and vertical adjacency.

    PyMuPDF's own blocks cannot be trusted for this: a producer that writes each line with its
    own text operator yields one block per line, and the column structure is then invisible.
    """
    groups: List[List[Line]] = []
    spans: List[Tuple[float, float]] = []  # x-range of each open group
    for ln in sorted(lines, key=lambda l: (round(l.bbox[1], 1), l.bbox[0])):
        height = max(1.0, ln.bbox[3] - ln.bbox[1])
        best, best_ov = None, 0.5  # require a majority overlap to join a block
        for i, g in enumerate(groups):
            last = g[-1]
            if ln.bbox[1] - last.bbox[3] > 2.5 * height:
                continue  # too far below the block to belong to it
            ov = _overlap_ratio((ln.bbox[0], ln.bbox[2]), spans[i])
            if ov > best_ov:
                best, best_ov = i, ov
        if best is None:
            groups.append([ln])
            spans.append((ln.bbox[0], ln.bbox[2]))
        else:
            groups[best].append(ln)
            spans[best] = (min(spans[best][0], ln.bbox[0]), max(spans[best][1], ln.bbox[2]))
    return groups


def order_lines(lines: List[Line]) -> List[Line]:
    """Lines in human reading order, as blocks laid out on the page rather than drawing order."""
    if len(lines) < 2:
        return lines
    ordered: List[Line] = []
    for col, group in enumerate(_xy_cut(_group_lines(lines))):
        for ln in group:
            ln.column = col
            ordered.append(ln)
    return ordered


# ---------------------------------------------------------------------------
# Vector drawings
# ---------------------------------------------------------------------------

def _pt(p) -> Tuple[float, float]:
    return (float(p.x), float(p.y)) if hasattr(p, "x") else (float(p[0]), float(p[1]))


def _split_drawing(p: Dict, page_area: float) -> List[Drawing]:
    """Normalizes one PyMuPDF path into rules / rectangles, or a single complex path."""
    ptype = p.get("type") or ""
    stroke = _rgb_from_floats(p.get("color")) if "s" in ptype else None
    fill = _rgb_from_floats(p.get("fill")) if "f" in ptype else None
    if stroke is None and fill is None:
        return []
    width = float(p.get("width") or 0.0) if stroke else 0.0
    items = list(p.get("items") or [])
    r = p.get("rect")
    rect = (r.x0, r.y0, r.x1, r.y1) if r is not None else (0.0, 0.0, 0.0, 0.0)

    if fill == (255, 255, 255) and stroke is None and _area(rect) >= 0.9 * page_area:
        return []  # page-sized white background

    if fill is not None and items and all(it[0] == "l" for it in items):
        segs = [(_pt(it[1]), _pt(it[2])) for it in items]
        if all(abs(a[1] - b[1]) <= AXIS_TOL or abs(a[0] - b[0]) <= AXIS_TOL for a, b in segs):
            return [_rect_or_rule(rect, stroke, fill, width)]  # filled box drawn as line segments

    out: List[Drawing] = []
    simple = True
    for it in items:
        kind = it[0]
        if kind == "l":
            (x0, y0), (x1, y1) = _pt(it[1]), _pt(it[2])
            if abs(y0 - y1) <= AXIS_TOL:
                hw = max(width, 0.4) / 2
                out.append(Drawing(rect=(min(x0, x1), y0 - hw, max(x0, x1), y0 + hw), kind="hrule",
                                   stroke=stroke or fill, width=max(width, 0.4)))
            elif abs(x0 - x1) <= AXIS_TOL:
                hw = max(width, 0.4) / 2
                out.append(Drawing(rect=(x0 - hw, min(y0, y1), x0 + hw, max(y0, y1)), kind="vrule",
                                   stroke=stroke or fill, width=max(width, 0.4)))
            else:
                simple = False
        elif kind == "re":
            rr = it[1]
            rb = (rr.x0, rr.y0, rr.x1, rr.y1)
            out.append(_rect_or_rule(rb, stroke, fill, width))
        elif kind == "qu":
            q = it[1]
            pts = [_pt(q.ul), _pt(q.ur), _pt(q.ll), _pt(q.lr)]
            xs, ys = sorted({round(x, 1) for x, _ in pts}), sorted({round(y, 1) for _, y in pts})
            if len(xs) <= 2 and len(ys) <= 2:
                out.append(_rect_or_rule((xs[0], ys[0], xs[-1], ys[-1]), stroke, fill, width))
            else:
                simple = False
        else:  # "c" (Bezier) and anything else
            simple = False

    if simple and out:
        return out
    return [Drawing(rect=rect, kind="path", stroke=stroke, fill=fill, width=width,
                    n_items=len(items), complex=True)]


def _rect_or_rule(b: BBox, stroke, fill, width: float) -> Drawing:
    w, h = b[2] - b[0], b[3] - b[1]
    if fill is not None and stroke is None:
        if h <= 2.5 and w > 3 * h:
            return Drawing(rect=b, kind="hrule", stroke=fill, width=max(h, 0.4))
        if w <= 2.5 and h > 3 * w:
            return Drawing(rect=b, kind="vrule", stroke=fill, width=max(w, 0.4))
    return Drawing(rect=b, kind="rect", stroke=stroke, fill=fill, width=width)


def _page_paths(page: "pymupdf.Page") -> List[Dict]:
    try:
        return page.get_drawings()
    except Exception as e:
        logger.warning(f"get_drawings failed on page {page.number + 1}: {e}")
        return []


def _extract_drawings(page: "pymupdf.Page", paths: Optional[List[Dict]] = None,
                      skip: Optional[set] = None) -> List[Drawing]:
    """Drawings of the page; ``skip`` = indices of paths that belong to text (glyph outlines)."""
    paths = _page_paths(page) if paths is None else paths
    page_area = page.rect.width * page.rect.height
    out: List[Drawing] = []
    for i, p in enumerate(paths):
        if skip and i in skip:
            continue
        out.extend(_split_drawing(p, page_area))
    return out


def _shading_rects(page: "pymupdf.Page") -> List[BBox]:
    out = []
    try:
        for kind, box in page.get_bboxlog():
            if kind == "fill-shade":
                out.append(tuple(box))
    except Exception:
        pass
    return out


def _cluster(boxes: List[BBox], pad: float = CLUSTER_PAD) -> List[BBox]:
    """Merges boxes that touch (within pad) into connected regions."""
    regions: List[BBox] = []
    for b in boxes:
        cur = (b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad)
        changed = True
        while changed:
            changed = False
            keep = []
            for r in regions:
                if r[0] <= cur[2] and cur[0] <= r[2] and r[1] <= cur[3] and cur[1] <= r[3]:
                    cur = (min(r[0], cur[0]), min(r[1], cur[1]), max(r[2], cur[2]), max(r[3], cur[3]))
                    changed = True
                else:
                    keep.append(r)
            regions = keep
        regions.append(cur)
    return [(r[0] + pad, r[1] + pad, r[2] - pad, r[3] - pad) for r in regions]


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def _save_image(doc: "pymupdf.Document", xref: int, target_base: Path) -> Tuple[Optional[Path], int, int]:
    """Saves image xref at original resolution as PNG/JPEG (pdfLaTeX-compatible). Returns (path, w, h)."""
    try:
        info = doc.extract_image(xref)
    except Exception:
        info = None
    smask = (info or {}).get("smask") or 0
    if info and not smask and info.get("ext") in ("png", "jpeg", "jpg") and info.get("colorspace") in (1, 3):
        ext = "jpg" if info["ext"] in ("jpeg", "jpg") else "png"
        path = target_base.with_suffix(f".{ext}")
        path.write_bytes(info["image"])
        return path, int(info.get("width", 0)), int(info.get("height", 0))
    try:
        pix = pymupdf.Pixmap(doc, xref)
        if smask:
            try:
                mask = pymupdf.Pixmap(doc, smask)
                if pix.alpha:
                    pix = pymupdf.Pixmap(pix, 0)
                pix = pymupdf.Pixmap(pix, mask)
            except Exception as e:
                logger.debug(f"Soft mask merge failed for xref {xref}: {e}")
        if pix.colorspace and pix.colorspace.n not in (1, 3):
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        path = target_base.with_suffix(".png")
        pix.save(str(path))
        return path, pix.width, pix.height
    except Exception as e:
        logger.warning(f"Could not extract image xref {xref}: {e}")
        return None, 0, 0


def _extract_images(doc: "pymupdf.Document", page: "pymupdf.Page", assets_root: Path, asset_prefix: str,
                    saved: Dict[int, Tuple[str, int, int]]) -> List[ImageRef]:
    images: List[ImageRef] = []
    try:
        infos = page.get_image_info(xrefs=True)
    except Exception as e:
        logger.warning(f"get_image_info failed on page {page.number + 1}: {e}")
        return images
    n = page.number + 1
    k = 0
    for info in infos:
        clipped = pymupdf.Rect(info["bbox"]) & page.rect
        if clipped.is_empty or clipped.width < 1 or clipped.height < 1:
            continue
        k += 1
        xref = int(info.get("xref") or 0)
        bbox = (clipped.x0, clipped.y0, clipped.x1, clipped.y1)
        if xref and xref in saved:
            rel, w, h = saved[xref]
        elif xref:
            path, w, h = _save_image(doc, xref, assets_root / f"page{n}_img{k}")
            if path is None:
                continue
            rel = f"{asset_prefix}/{path.name}"
            saved[xref] = (rel, w, h)
        else:
            pix = page.get_pixmap(clip=clipped, dpi=FIGURE_DPI)
            path = assets_root / f"page{n}_img{k}.png"
            pix.save(str(path))
            rel, w, h = f"{asset_prefix}/{path.name}", pix.width, pix.height
        images.append(ImageRef(file=rel, bbox=bbox, width_px=w, height_px=h))
    return images


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------

def _is_scanned(page_w: float, page_h: float, visible: List[Line], images: List[ImageRef]) -> bool:
    if sum(len(l.text.strip()) for l in visible) >= SCANNED_MAX_CHARS:
        return False
    area = page_w * page_h
    img_area = max((_area(i.bbox) for i in images), default=0.0)
    return area > 0 and img_area / area >= SCANNED_MIN_IMAGE_COVERAGE


def _margins(page_w: float, page_h: float, boxes: List[BBox]) -> BBox:
    content = _union(boxes)
    if not content:
        return (72.0, 72.0, 72.0, 72.0)
    return (max(0.0, content[0]), max(0.0, content[1]),
            max(0.0, page_w - content[2]), max(0.0, page_h - content[3]))


def _rasterize_vector_art(doc: "pymupdf.Document", page: "pymupdf.Page", pe: PageExtract,
                          assets_root: Path, asset_prefix: str, shading: List[BBox],
                          text_paths: Optional[List[BBox]] = None) -> None:
    """Replaces vector art LaTeX rules cannot express with figure rasters or a page background."""
    n = pe.number
    page_area = pe.width * pe.height
    if len(pe.drawings) > DENSE_DRAWINGS:
        seeds = [d.rect for d in pe.drawings]
    else:
        seeds = [d.rect for d in pe.drawings if d.complex] + shading
    regions = [r for r in _cluster(seeds) if _area(r) >= FIGURE_MIN_AREA]
    if not regions:
        return

    if any(_area(r) >= BACKGROUND_MIN_COVERAGE * page_area for r in regions):
        png = render_page_png(doc, n, dpi=BACKGROUND_DPI, without_text=True, erase=text_paths)
        name = f"page{n}_bg.png"
        (assets_root / name).write_bytes(png)
        pe.background = f"{asset_prefix}/{name}"
        pe.drawings = []
        pe.images = []
        pe.warnings.append("Vector artwork covering most of the page is placed as a background image; "
                           "the text stays real text.")
        return

    for k, region in enumerate(regions, start=1):
        clip = pymupdf.Rect(region) & page.rect
        if clip.is_empty:
            continue
        box = (clip.x0, clip.y0, clip.x1, clip.y1)
        name = f"page{n}_fig{k}.png"
        page.get_pixmap(clip=clip, dpi=FIGURE_DPI, alpha=False).save(str(assets_root / name))
        pe.lines = [l for l in pe.lines if not _center_inside(l.bbox, box)]
        pe.drawings = [d for d in pe.drawings if not _inside(d.rect, box)]
        pe.images = [i for i in pe.images if not _inside(i.bbox, box)]
        pe.images.append(ImageRef(file=f"{asset_prefix}/{name}", bbox=box,
                                  width_px=int(clip.width * FIGURE_DPI / 72), height_px=int(clip.height * FIGURE_DPI / 72),
                                  kind="figure"))
    pe.warnings.append(f"{len(regions)} vector graphic region(s) (curves, gradients or charts) were rasterized as images.")


def extract_document(pdf_bytes: bytes, out_root: Path, asset_prefix: str,
                     max_pages: Optional[int] = None) -> Tuple[DocExtract, "pymupdf.Document"]:
    """
    Extracts every page. Images and rasters are written under out_root / asset_prefix.
    Returns the extract and the (rotation-normalized) open document, used for page renders.
    """
    doc = open_pdf(pdf_bytes)
    if max_pages and doc.page_count > max_pages:
        n = doc.page_count
        doc.close()
        raise PdfValidationError(f"PDF has {n} pages; the limit is {max_pages}.")
    normalize_rotation(doc)

    assets_root = out_root / asset_prefix
    assets_root.mkdir(parents=True, exist_ok=True)
    saved_images: Dict[int, Tuple[str, int, int]] = {}
    pages: List[PageExtract] = []
    for page in doc:
        w, h = page.rect.width, page.rect.height
        paths = _page_paths(page)
        # Bold faked by stroking each glyph's outline as a separate vector path:
        # the strokes are text, not artwork (see fontmap.outline_stroke_bold).
        outline_bold, glyph_paths = outline_stroke_bold(page, paths)
        all_lines = _extract_lines(page, outline_bold)
        visible = [l for l in all_lines if not l.invisible]
        images = _extract_images(doc, page, assets_root, asset_prefix, saved_images)
        pe = PageExtract(number=page.number + 1, width=w, height=h, margins=(72.0, 72.0, 72.0, 72.0),
                         lines=visible, drawings=_extract_drawings(page, paths, glyph_paths), images=images)

        if _is_scanned(w, h, visible, images):
            pe.is_scanned = True
            biggest = max(images, key=lambda i: _area(i.bbox))
            biggest.kind = "scan"
            ocr = [l for l in all_lines if l.invisible]
            if ocr:
                pe.lines = ocr
                pe.ocr_text = True
                pe.warnings.append("Scanned page: the scan is placed as-is with its OCR text as an invisible, "
                                   "searchable layer.")
            else:
                pe.warnings.append("Scanned page without a text layer: the scan is placed as an image.")
        else:
            glyph_rects = [tuple(paths[i]["rect"]) for i in glyph_paths]
            _rasterize_vector_art(doc, page, pe, assets_root, asset_prefix, _shading_rects(page), glyph_rects)

        pe.margins = _margins(w, h, [l.bbox for l in pe.lines] + [d.rect for d in pe.drawings]
                              + [i.bbox for i in pe.images])
        pages.append(pe)

    meta = {k: v for k, v in (doc.metadata or {}).items() if v}
    return DocExtract(pages=pages, asset_prefix=asset_prefix, metadata=meta), doc


def _erase_paths(page: "pymupdf.Page", rects: List[BBox]) -> None:
    """
    Removes the vector paths with these bounding boxes (glyph-outline strokes)
    from a scratch copy of a page. MuPDF only removes line art a redaction
    *touches*, which also catches anything underneath — a page fill, a coloured
    box behind a bold label — so those collateral paths are drawn back,
    beneath the page content, afterwards.
    """
    if not rects:
        return
    want = {tuple(round(v, 1) for v in r) for r in rects}
    before = page.get_drawings()
    for x0, y0, x1, y1 in rects:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        page.add_redact_annot(pymupdf.Rect(cx - 0.2, cy - 0.2, cx + 0.2, cy + 0.2), fill=False)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                          graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                          text=pymupdf.PDF_REDACT_TEXT_NONE)
    after = {(tuple(round(v, 1) for v in d["rect"]), d.get("type")) for d in page.get_drawings()}
    collateral = [d for d in before
                  if tuple(round(v, 1) for v in d["rect"]) not in want
                  and (tuple(round(v, 1) for v in d["rect"]), d.get("type")) not in after]
    if not collateral:
        return
    shape = page.new_shape()
    for d in collateral:
        for it in d.get("items", []):
            if it[0] == "l":
                shape.draw_line(it[1], it[2])
            elif it[0] == "re":
                shape.draw_rect(it[1])
            elif it[0] == "qu":
                shape.draw_quad(it[1])
            elif it[0] == "c":
                shape.draw_bezier(it[1], it[2], it[3], it[4])
        shape.finish(fill=d.get("fill"), color=d.get("color"), width=d.get("width") or 0,
                     even_odd=bool(d.get("even_odd")), closePath=bool(d.get("closePath")),
                     fill_opacity=d.get("fill_opacity") or 1, stroke_opacity=d.get("stroke_opacity") or 1)
    shape.commit(overlay=False)


def render_page_png(doc: "pymupdf.Document", page_no: int, dpi: int = 150,
                    clip: Optional[BBox] = None, without_text: bool = False,
                    erase: Optional[List[BBox]] = None) -> bytes:
    """
    Renders a 1-based page (optionally a clip region, optionally with text removed) to PNG bytes.
    ``erase``: bounding boxes of vector paths that belong to the text (glyph-outline strokes),
    removed together with the text.
    """
    if without_text:
        tmp = pymupdf.open()
        tmp.insert_pdf(doc, from_page=page_no - 1, to_page=page_no - 1)
        page = tmp[0]
        try:
            _erase_paths(page, list(erase or []))
        except Exception as e:  # noqa: BLE001 — a failed erase only leaves the strokes in the image
            logger.warning(f"Could not remove glyph-outline strokes from the background: {e}")
        page.add_redact_annot(page.rect)
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_NONE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
            text=pymupdf.PDF_REDACT_TEXT_REMOVE,
        )
        pix = page.get_pixmap(dpi=dpi, clip=pymupdf.Rect(clip) if clip else None, alpha=False)
        tmp.close()
        return pix.tobytes("png")
    page = doc[page_no - 1]
    pix = page.get_pixmap(dpi=dpi, clip=pymupdf.Rect(clip) if clip else None, alpha=False)
    return pix.tobytes("png")
