"""
assets.py — Stage 5 of the AI-rebuild pipeline: the pictures, figure crops, tables and equation
crops a page body may reference.

Input is the extractor's output (`extract.extract_document`), which has already saved every embedded
image and rasterised curved/shaded vector art. This stage turns that into an `AssetManifest`:

  embedded images   copied to `p{n}_img{k}.{png|jpg}`, cropped to their ink (the bbox follows the
                    crop, so it stays where the picture sits on the page); specks and pictures
                    repeated as page furniture are kept but flagged `meta.decorative`
  vector figures    the regions the extractor rasterised, plus clusters of filled shapes and the
                    axes/labels around them (a bar chart the extractor leaves as rectangles), cropped
                    to one-page PDFs `p{n}_fig{k}.pdf` that keep vectors AND text; the extractor's
                    PNG of such a region is removed
  backgrounds       full-page art (>= 40% of the page) and scans as `p{n}_bg.{png|jpg}`
  tables            `TableData` from `editable.tables.detect_tables` (ruled and booktabs), with the
                    column/row edges and a style read from the page's own rules
  math              `editable.mathcrop.detect_math` regions as `p{n}_math{k}.png`

Filenames are relative to `out_dir`, under `asset_prefix`, spelled exactly as `\\includegraphics`
must use them. Every file is rewritten deterministically on each run (resume-friendly). One bad
region is logged and skipped; the stage never raises for it. Captions are not detected here.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pymupdf

from ..extract import BACKGROUND_DPI, CLUSTER_PAD, FIGURE_MIN_AREA, _cluster, render_page_png
from ..models import DocExtract, ImageRef, PageExtract
from .model import Asset, AssetManifest, Inspection, Rect, TableData

logger = logging.getLogger("pdf2latex.rebuild.assets")

BACKGROUND_MIN_COVERAGE = 0.4   # share of the page a figure must cover to become the page background
SPECK_MAX_PT = 12.0             # an image this small on both sides is decoration (a bullet, a rule cap)
SPECK_MAX_AREA = 150.0          # pt²
LABEL_GAP = 10.0                # pt: a short text line this close to a figure's art is one of its labels
LABEL_MAX_WORDS = 5
RULE_BAND = 0.08               # top/bottom share of the page whose rules are page furniture
FIGURE_MIN_SIDE = 12.0          # pt: a figure narrower/shorter than this is a rule, not a figure
_CAPTION_RE = re.compile(r"^\s*(fig(ure)?\.?|table|tab\.)\s*\d", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _area(b: Rect) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _overlap(a: Rect, b: Rect, pad: float = 0.0) -> bool:
    return a[0] - pad < b[2] and b[0] - pad < a[2] and a[1] - pad < b[3] and b[1] - pad < a[3]


def _inside(inner: Rect, outer: Rect, tol: float = 1.0) -> bool:
    return (inner[0] >= outer[0] - tol and inner[1] >= outer[1] - tol
            and inner[2] <= outer[2] + tol and inner[3] <= outer[3] + tol)


def _center_in(b: Rect, outer: Rect) -> bool:
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]


def _union(a: Rect, b: Rect) -> Rect:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _round(b: Rect) -> Rect:
    return tuple(round(float(v), 2) for v in b)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build_assets(extract: DocExtract, doc: "pymupdf.Document", out_dir: Path, inspection: Inspection,
                 asset_prefix: str) -> AssetManifest:
    """
    Builds the asset manifest of the whole document (see the module docstring). Text lines that
    fall inside a vector-figure crop are removed from `extract.pages[i].lines`, the way the extractor
    already does for the regions it rasterises: that text now lives in the crop.
    """
    out_dir = Path(out_dir)
    (out_dir / asset_prefix).mkdir(parents=True, exist_ok=True)
    scanned = set(inspection.scanned_pages) if inspection else set()
    decorative_keys = _furniture_images(extract)
    furn_ids = _furniture_lines(extract)

    manifest = AssetManifest()
    for pe in extract.pages:
        try:
            pg = doc[pe.number - 1]
        except Exception as e:  # noqa: BLE001
            logger.warning(f"assets: page {pe.number} not in the document: {e}")
            continue
        try:
            _page_assets(doc, pg, pe, out_dir, asset_prefix, pe.number in scanned, decorative_keys,
                         furn_ids, manifest)
        except Exception as e:  # noqa: BLE001 — one bad page never fails the stage
            logger.warning(f"assets: page {pe.number} failed, continuing: {e}")

    manifest.assets.sort(key=lambda a: (a.page, round(a.bbox[1], 2), round(a.bbox[0], 2), a.filename))
    manifest.tables.sort(key=lambda t: (t.page, round(t.bbox[1], 2), round(t.bbox[0], 2)))
    return manifest


def _furniture_images(extract: DocExtract) -> Set[Tuple[int, str]]:
    """(page, file) of pictures repeated at the same place on many pages (a header logo). Scans are
    left out: a scanned document repeats a page-sized picture on every page and it is content."""
    try:
        from ..editable import furniture
        pages = [p for p in extract.pages if not p.is_scanned]
        return set(furniture.detect(pages).image_keys) if len(pages) >= 2 else set()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"assets: furniture detection failed: {e}")
        return set()


def _furniture_lines(extract: DocExtract) -> Set[Tuple[int, int]]:
    try:
        from ..editable import furniture
        return set(furniture.detect(extract.pages).furniture_line_ids)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"assets: furniture line detection failed: {e}")
        return set()


def _page_assets(doc, pg, pe: PageExtract, out_dir: Path, prefix: str, scanned: bool,
                 decorative_keys: Set[Tuple[int, str]], furn_ids, manifest: AssetManifest) -> None:
    n = pe.number
    page_rect: Rect = (0.0, 0.0, pe.width, pe.height)

    # Scanned page: the scan is the page; nothing else on it is an asset of its own.
    scan = next((i for i in pe.images if i.kind == "scan"), None)
    if pe.is_scanned or (scanned and scan is not None):
        if scan is None and pe.images:
            scan = max(pe.images, key=lambda i: _area(i.bbox))
        if scan is not None:
            a = _copy_as(out_dir, prefix, scan.file, f"p{n}_bg", n, page_rect, "background",
                         {"scan": True, "source": scan.file, "ocr_text": pe.ocr_text})
            if a:
                manifest.assets.append(a)
        return

    # Page background the extractor rendered (vector art covering most of the page).
    if pe.background:
        a = _copy_as(out_dir, prefix, pe.background, f"p{n}_bg", n, page_rect, "background",
                     {"source": pe.background})
        if a:
            manifest.assets.append(a)

    # Tables first: their grids are not figures.
    tables = _tables(pg, pe)
    manifest.tables.extend(tables)
    table_boxes = [t.bbox for t in tables]

    # Vector figures: the extractor's rasterised regions plus clusters of filled shapes.
    figs = _figure_regions(pe, table_boxes)
    big = [r for r in figs if _area(r) >= BACKGROUND_MIN_COVERAGE * pe.width * pe.height]
    if big and not pe.background:
        try:
            png = render_page_png(doc, n, dpi=BACKGROUND_DPI, without_text=True)
            rel = f"{prefix}/p{n}_bg.png"
            (out_dir / rel).write_bytes(png)
            manifest.assets.append(Asset(filename=rel, kind="background", page=n, bbox=page_rect, fmt="png",
                                         meta={"rendered": True}))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"assets: background render failed p{n}: {e}")
    figs = [r for r in figs if r not in big]
    raster_figs = [i for i in pe.images if i.kind == "figure"]
    for k, region in enumerate(sorted(figs, key=lambda r: (round(r[1], 2), round(r[0], 2))), start=1):
        rel = f"{prefix}/p{n}_fig{k}.pdf"
        try:
            crop_text = _crop_pdf(doc, n - 1, region, out_dir / rel)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"assets: figure crop failed p{n} {region}: {e}")
            continue
        # the crop's own text (the extractor already dropped the lines of the regions it rasterised)
        labels = [t.strip() for t in (crop_text or "").splitlines() if t.strip()]
        meta: Dict = {"vector": True}
        if labels:
            meta["text"] = labels
        # the extractor's PNG of this region is superseded by the PDF crop
        for img in raster_figs:
            if _overlap(img.bbox, region) and _inside(img.bbox, region, tol=2.0):
                meta.setdefault("replaces", []).append(img.file)
                try:
                    (out_dir / img.file).unlink(missing_ok=True)
                except Exception:  # noqa: BLE001
                    pass
        manifest.assets.append(Asset(filename=rel, kind="vector", page=n, bbox=_round(region), fmt="pdf",
                                     meta=meta))
        # the text of the figure lives in the crop now, as the extractor does for its own regions
        pe.lines = [ln for ln in pe.lines if not _center_in(ln.bbox, region)]

    # Embedded raster images (not those inside a figure crop or under a rendered background).
    covered = figs + (big if big else [])
    images = [i for i in pe.images if i.kind == "image" and not any(_inside(i.bbox, r, tol=2.0) for r in covered)]
    images.sort(key=lambda i: (round(i.bbox[1], 2), round(i.bbox[0], 2)))
    for k, img in enumerate(images, start=1):
        a = _image_asset(out_dir, prefix, img, n, k, trim=not (pe.background or big),
                         decorative=(n, img.file) in decorative_keys)
        if a:
            manifest.assets.append(a)

    # Math regions (never inside a table or a figure).
    manifest.assets.extend(_math_assets(pg, pe, out_dir, prefix, furn_ids, table_boxes + figs))


# ---------------------------------------------------------------------------
# Raster images and backgrounds
# ---------------------------------------------------------------------------

def _copy_as(out_dir: Path, prefix: str, src_rel: str, stem: str, page: int, bbox: Rect, kind: str,
             meta: Dict) -> Optional[Asset]:
    src = out_dir / src_rel
    ext = src.suffix.lower().lstrip(".") or "png"
    ext = "jpg" if ext in ("jpg", "jpeg") else ext
    rel = f"{prefix}/{stem}.{ext}"
    try:
        if src.resolve() != (out_dir / rel).resolve():
            shutil.copyfile(src, out_dir / rel)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"assets: could not copy {src_rel}: {e}")
        return None
    return Asset(filename=rel, kind=kind, page=page, bbox=_round(bbox), fmt=ext, meta=meta)


def _image_asset(out_dir: Path, prefix: str, img: ImageRef, page: int, k: int, trim: bool,
                 decorative: bool) -> Optional[Asset]:
    from ..editable.figures import PAD, ink_box

    w_pt, h_pt = img.bbox[2] - img.bbox[0], img.bbox[3] - img.bbox[1]
    speck = (w_pt <= SPECK_MAX_PT and h_pt <= SPECK_MAX_PT) or _area(img.bbox) < SPECK_MAX_AREA
    meta: Dict = {"source": img.file}
    if decorative or speck:
        meta["decorative"] = True
        meta["reason"] = "furniture" if decorative else "speck"
    src = out_dir / img.file
    got = ink_box(src) if (trim and not meta.get("decorative")) else None
    if got is not None:
        (x0, y0, x1, y1), (w, h) = got
        if (x1 - x0 < w - 2 * PAD - 1 or y1 - y0 < h - 2 * PAD - 1) and x1 - x0 >= 4 and y1 - y0 >= 4:
            sx, sy = w_pt / w, h_pt / h
            box = (img.bbox[0] + x0 * sx, img.bbox[1] + y0 * sy, img.bbox[0] + x1 * sx, img.bbox[1] + y1 * sy)
            rel = f"{prefix}/p{page}_img{k}.png"
            try:
                from PIL import Image
                with Image.open(src) as im:
                    im.crop((x0, y0, x1, y1)).save(out_dir / rel)
                meta["trimmed"] = True
                return Asset(filename=rel, kind="image", page=page, bbox=_round(box), fmt="png", meta=meta)
            except Exception as e:  # noqa: BLE001
                logger.debug(f"assets: trim failed {img.file}: {e}")
    return _copy_as(out_dir, prefix, img.file, f"p{page}_img{k}", page, img.bbox, "image", meta)


# ---------------------------------------------------------------------------
# Vector figures
# ---------------------------------------------------------------------------

def _figure_regions(pe: PageExtract, table_boxes: List[Rect]) -> List[Rect]:
    """
    Figure regions of the page in PDF points: the vector regions the extractor rasterised, and
    clusters of filled non-white shapes (bars, markers, swatches) grown by the rules that touch them
    (axes, ticks) and the short text lines next to them (tick and bar labels). Table grids, rules on
    their own, page-sized fills and shaded boxes holding body text are not figures.
    """
    page_area = pe.width * pe.height
    regions: List[Rect] = [i.bbox for i in pe.images if i.kind == "figure"]

    lines = [ln for ln in pe.lines if ln.text.strip()]
    seeds: List[Rect] = []
    for d in pe.drawings:
        if any(_overlap(d.rect, t, pad=2.0) for t in table_boxes):
            continue
        if d.complex:
            seeds.append(d.rect)
            continue
        if d.kind != "rect" or d.fill is None or min(d.fill) >= 245:
            continue
        if _area(d.rect) >= 0.9 * page_area:
            continue
        # a shaded box around prose is a call-out, not a figure
        if any(_center_in(ln.bbox, d.rect) and len(ln.text.split()) > LABEL_MAX_WORDS for ln in lines):
            continue
        seeds.append(d.rect)
    # Axes, ticks and grid lines join the shapes they touch (bars standing on one axis become one
    # chart); a rule that touches no shape stays a rule. Header/footer-band rules never join.
    rules = [d.rect for d in pe.drawings if d.kind in ("hrule", "vrule")
             and not any(_overlap(d.rect, t, pad=2.0) for t in table_boxes)
             and RULE_BAND * pe.height < (d.rect[1] + d.rect[3]) / 2 < (1 - RULE_BAND) * pe.height]
    clusters = [r for r in _cluster(seeds + rules) if any(_inside(s, r) for s in seeds)]
    clusters = [r for r in clusters if _area(r) >= FIGURE_MIN_AREA
                and min(r[2] - r[0], r[3] - r[1]) >= FIGURE_MIN_SIDE]
    clusters = [r for r in clusters if not any(_overlap(r, q, pad=1.0) for q in regions)]
    grown = [_grow(r, rules, lines) for r in clusters]
    # growth can make two regions meet
    regions.extend(_cluster(grown, pad=0.5) if grown else [])
    page_rect = (0.0, 0.0, pe.width, pe.height)
    out = []
    for r in regions:
        r = (max(r[0], page_rect[0]), max(r[1], page_rect[1]), min(r[2], page_rect[2]), min(r[3], page_rect[3]))
        if r[2] - r[0] >= 1 and r[3] - r[1] >= 1 and r not in out:
            out.append(r)
    return out


def _grow(region: Rect, rules: List[Rect], lines) -> Rect:
    """Adds the axis rules touching a figure, then its labels (repeat until stable)."""
    used_rules: Set[int] = set()
    used_lines: Set[int] = set()
    changed = True
    while changed:
        changed = False
        for i, rr in enumerate(rules):
            if i in used_rules:
                continue
            # a rule touching the art, no longer than the art's span plus a margin (not a page rule)
            span = max(rr[2] - rr[0], rr[3] - rr[1])
            if _overlap(rr, region, pad=CLUSTER_PAD) and span <= 1.5 * max(region[2] - region[0],
                                                                           region[3] - region[1]):
                region = _union(region, rr)
                used_rules.add(i)
                changed = True
        for i, ln in enumerate(lines):
            if i in used_lines:
                continue
            t = ln.text.strip()
            if _center_in(ln.bbox, region):
                region = _union(region, ln.bbox)
                used_lines.add(i)
                changed = True
                continue
            if len(t.split()) > LABEL_MAX_WORDS or _CAPTION_RE.match(t):
                continue
            if _overlap(ln.bbox, region, pad=LABEL_GAP):
                region = _union(region, ln.bbox)
                used_lines.add(i)
                changed = True
    return region


def _crop_pdf(doc, pno: int, bbox: Rect, path: Path) -> str:
    """Writes a one-page PDF of exactly `bbox` of page `pno` (0-based), vectors, text and images
    kept; returns the crop's text."""
    clip = pymupdf.Rect(*bbox)
    out = pymupdf.open()
    try:
        page = out.new_page(width=clip.width, height=clip.height)
        page.show_pdf_page(page.rect, doc, pno, clip=clip)
        out.set_metadata({})
        path.parent.mkdir(parents=True, exist_ok=True)
        data = out.tobytes(garbage=3, deflate=True, no_new_id=True)
    finally:
        out.close()
    path.write_bytes(data)
    with pymupdf.open(path) as check:
        if check.page_count != 1:
            raise ValueError(f"crop has {check.page_count} pages")
        return check[0].get_text("text")


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def _tables(pg, pe: PageExtract) -> List[TableData]:
    try:
        from ..editable import tables as T
        blocks = T.detect_tables(pg, pe)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"assets: table detection failed p{pe.number}: {e}")
        return []
    out: List[TableData] = []
    for k, tb in enumerate(sorted(blocks, key=lambda b: (b.bbox[1], b.bbox[0])), start=1):
        try:
            out.append(_table_data(pg, pe, tb, f"p{pe.number}t{k}"))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"assets: table {k} on p{pe.number} skipped: {e}")
    return out


def _table_data(pg, pe: PageExtract, tb, tid: str) -> TableData:
    rows = [[" ".join(c.text.split()) for c in r] for r in tb.rows]
    ncol = max((len(r) for r in rows), default=0)
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    bbox: Rect = tuple(float(v) for v in tb.bbox)  # type: ignore[assignment]
    style = _table_style(pe, bbox)
    col_edges, row_edges = _table_edges(pg, bbox, style, ncol, len(rows))
    header = 0
    if rows and tb.rows and (all(c.bold for c in tb.rows[0] if c.text.strip())
                             and any(c.text.strip() for c in tb.rows[0])):
        header = 1
    elif style == "booktabs" and len(row_edges) == len(rows) + 1 and _rule_between(pe, bbox, row_edges[1]):
        header = 1
    return TableData(id=tid, page=pe.number, bbox=_round(bbox), rows=rows, col_edges=col_edges,
                     row_edges=row_edges, style=style, header_rows=header)


def _table_style(pe: PageExtract, bbox: Rect) -> str:
    """ruled: vertical rules or boxed cells; booktabs: horizontal rules only; borderless: none."""
    inside = [d for d in pe.drawings if _inside(d.rect, bbox, tol=3.0)]
    if any(d.kind == "vrule" for d in inside) or \
            any(d.kind == "rect" and d.stroke is not None and d.fill is None for d in inside):
        return "ruled"
    if any(d.kind == "hrule" for d in inside):
        return "booktabs"
    return "borderless"


def _rule_between(pe: PageExtract, bbox: Rect, y: float) -> bool:
    return any(d.kind == "hrule" and abs((d.rect[1] + d.rect[3]) / 2 - y) <= 4
               and d.rect[0] <= bbox[0] + 6 and d.rect[2] >= bbox[2] - 6 for d in pe.drawings)


def _table_edges(pg, bbox: Rect, style: str, ncol: int, nrow: int) -> Tuple[List[float], List[float]]:
    """Column and row boundaries in pt, read back from find_tables' cell boxes for this table."""
    clip = pymupdf.Rect(*bbox)
    tb = None
    try:
        strategy = "lines" if style == "ruled" else "text"
        found = pg.find_tables(strategy=strategy, clip=clip) if strategy == "text" \
            else pg.find_tables(strategy="lines")
        cands = [t for t in getattr(found, "tables", []) if _overlap(tuple(t.bbox), bbox)]
        if cands:
            tb = max(cands, key=lambda t: t.col_count * t.row_count)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"assets: find_tables for edges failed: {e}")
    cols: List[float] = []
    rows: List[float] = []
    if tb is not None:
        cells = [c for r in tb.rows for c in (r.cells or []) if c]
        xs = sorted({round(c[0], 1) for c in cells})
        if len(xs) == ncol:
            # a ruled grid's outer edges are its frame; a booktabs/text table spans the rules' box
            outer = (xs[0], round(tb.bbox[2], 1)) if style == "ruled" else (round(bbox[0], 1), round(bbox[2], 1))
            cols = [outer[0]] + xs[1:] + [outer[1]]
        ys = []
        for r in tb.rows:
            got = [c[1] for c in (r.cells or []) if c]
            if got:
                ys.append(round(min(got), 1))
        if len(ys) == nrow:
            rows = ys + [round(tb.bbox[3], 1)]
            if style != "ruled":
                rows[0] = round(bbox[1], 1)
                rows[-1] = round(bbox[3], 1)
    if not cols and ncol:
        step = (bbox[2] - bbox[0]) / ncol
        cols = [round(bbox[0] + i * step, 1) for i in range(ncol + 1)]
    if not rows and nrow:
        step = (bbox[3] - bbox[1]) / nrow
        rows = [round(bbox[1] + i * step, 1) for i in range(nrow + 1)]
    return cols, rows


# ---------------------------------------------------------------------------
# Math
# ---------------------------------------------------------------------------

def _math_assets(pg, pe: PageExtract, out_dir: Path, prefix: str, furn_ids, exclude: List[Rect]) -> List[Asset]:
    try:
        from ..editable import mathcrop
        blocks = mathcrop.detect_math(pg, pe, prefix, out_dir, furn_ids)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"assets: math detection failed p{pe.number}: {e}")
        return []
    blocks = [b for b in blocks if not any(_overlap(b.bbox, r) for r in exclude)]
    blocks.sort(key=lambda b: (round(b.bbox[1], 2), round(b.bbox[0], 2)))
    out: List[Asset] = []
    for k, mb in enumerate(blocks, start=1):
        rel = f"{prefix}/p{pe.number}_math{k}.png"
        src = out_dir / mb.image
        try:
            src.replace(out_dir / rel)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"assets: math crop {mb.image} not moved: {e}")
            continue
        text = ""
        if getattr(mb, "polish", None) == "math" and mb.glyphs:
            text = " ".join(g["t"].strip() for g in mb.glyphs if g["t"].strip())
        meta: Dict = {"text": text}
        if mb.number:
            meta["number"] = mb.number
        out.append(Asset(filename=rel, kind="math", page=pe.number, bbox=_round(mb.bbox), fmt="png", meta=meta))
    # crops of regions dropped above are scratch
    for b in _math_leftovers(out_dir, prefix, pe.number):
        b.unlink(missing_ok=True)
    return out


def _math_leftovers(out_dir: Path, prefix: str, page: int) -> List[Path]:
    """`detect_math` scratch crops (`page{n}_eq*.png`) not moved into the manifest."""
    root = out_dir / prefix
    return sorted(list(root.glob(f"page{page}_eq[0-9]*.png")) + list(root.glob(f"page{page}_eqbrace[0-9]*.png")))
