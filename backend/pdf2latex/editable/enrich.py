"""
enrich.py — Read-only pass over the open PyMuPDF document for things the extractor doesn't give us:
ruled tables (find_tables, "lines" strategy only), links, math regions and side-note rows. The
results are passed to the block builder so tables/math/notes are spliced into the flow by position.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Tuple

from ..models import DocExtract
from .model import Block, EditDoc, LineMap

logger = logging.getLogger("pdf2latex.editable.enrich")


def assemble_with_enrichment(extract: DocExtract, doc, out_dir, source_name: str,
                             assemble_fn: Callable) -> Tuple[str, EditDoc, LineMap]:
    """Recover private-use glyphs, enrich (tables/math), stash the results, then assemble."""
    try:
        from . import glyphs
        glyphs.recover(doc, extract)
    except Exception as e:  # noqa: BLE001 — recovery is an improvement, never a failure
        logger.warning(f"Glyph recovery failed, continuing without it: {e}")
    try:
        from . import markers
        extract.metadata["_editable_markers"] = markers.convert_image_bullets(doc, extract)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Picture-bullet conversion failed, continuing without it: {e}")
        extract.metadata["_editable_markers"] = {}
    try:
        tables, maths = _detect(extract, doc, out_dir)
    except Exception as e:  # noqa: BLE001 — enrichment must never fail the whole conversion
        logger.warning(f"Editable enrichment failed, continuing without tables/math: {e}")
        tables, maths = {}, {}
    extract.metadata["_editable_tables"] = tables
    extract.metadata["_editable_math"] = maths
    try:
        extract.metadata["_editable_boxes"] = detect_boxes(doc, extract)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Box detection failed, continuing without boxes: {e}")
        extract.metadata["_editable_boxes"] = {}
    try:
        from . import backgrounds, furniture
        pages = extract.pages
        deck = len(pages) >= 2 and all(p.width > p.height * 1.15 for p in pages)
        furn_ids = furniture.detect(pages).furniture_line_ids
        extract.metadata["_editable_backgrounds"] = backgrounds.page_backgrounds(
            doc, extract, furn_ids, out_dir, deck, extract.metadata["_editable_boxes"],
            extract.metadata.get("_editable_markers", {}))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Page backgrounds failed, continuing without them: {e}")
        extract.metadata["_editable_backgrounds"] = {}
    try:
        from . import figures
        extract.metadata["_editable_trims"] = figures.trim_images(extract, out_dir)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Figure trimming failed, continuing with the full pictures: {e}")
        extract.metadata["_editable_trims"] = {}
    return assemble_fn(extract, doc, source_name)


def _detect(extract: DocExtract, doc, out_dir) -> Tuple[Dict[int, List[Block]], Dict[int, List[Block]]]:
    from . import tables as T
    from . import mathcrop as M
    from . import furniture as F
    table_blocks: Dict[int, List[Block]] = {}
    math_blocks: Dict[int, List[Block]] = {}
    try:
        furn_ids = F.detect(extract.pages).furniture_line_ids
    except Exception:  # noqa: BLE001
        furn_ids = set()
    try:
        from . import hyphen as HY
        vocab = HY.vocabulary(ln.text for p in extract.pages for ln in p.lines)
    except Exception:  # noqa: BLE001
        vocab = None
    for page in extract.pages:
        pno = page.number
        try:
            pg = doc[pno - 1]
        except Exception:
            continue
        tbs = T.detect_tables(pg, page, vocab)
        if tbs:
            table_blocks[pno] = tbs
        mbs = M.detect_math(pg, page, extract.asset_prefix, out_dir, furn_ids)
        if mbs:
            math_blocks[pno] = mbs
    return table_blocks, math_blocks


def detect_boxes(doc, extract: DocExtract) -> Dict[int, List[dict]]:
    """
    Shaded content boxes (a Beamer block, a coloured call-out): a filled, non-white shape that is
    not page decoration and holds body text. A narrow differently-coloured bar sitting on a box's
    top edge with one line of text in it is that box's title. Returned per page as plain dicts:
    {bbox, fill, title_bbox, title_fill}.
    """
    out: Dict[int, List[dict]] = {}
    for page in extract.pages:
        try:
            paths = doc[page.number - 1].get_drawings()
        except Exception:  # noqa: BLE001
            continue
        W, H = page.width, page.height
        cands = []
        for d in paths:
            fill = d.get("fill")
            if not fill or d.get("type") not in ("f", "fs"):
                continue
            rgb = tuple(int(round(c * 255)) for c in fill[:3])
            if min(rgb) >= 245:
                continue                                  # white: a text-box knock-out, not a box
            r = d["rect"]
            w, h = r.x1 - r.x0, r.y1 - r.y0
            if w < 0.3 * W or h < 8 or h > 0.85 * H:
                continue                                  # thin rules, page tint, side bars
            lines = [ln for ln in page.lines if ln.text.strip()
                     and r.x0 - 1 <= (ln.bbox[0] + ln.bbox[2]) / 2 <= r.x1 + 1
                     and r.y0 - 1 <= (ln.bbox[1] + ln.bbox[3]) / 2 <= r.y1 + 1]
            if lines:
                cands.append({"bbox": (r.x0, r.y0, r.x1, r.y1), "fill": rgb, "n": len(lines)})
        cands.sort(key=lambda c: c["bbox"][1])
        boxes: List[dict] = []
        used = set()
        for i, c in enumerate(cands):
            if i in used:
                continue
            x0, y0, x1, y1 = c["bbox"]
            below = None
            if c["n"] == 1:   # a title bar: one line, directly above a same-width box of another colour
                for j, d in enumerate(cands):
                    if j != i and j not in used and abs(d["bbox"][0] - x0) <= 3 \
                            and abs(d["bbox"][2] - x1) <= 3 and 0 <= d["bbox"][1] - y1 <= 4 \
                            and d["fill"] != c["fill"]:
                        below = j
                        break
            if below is not None:
                d = cands[below]
                used.update({i, below})
                boxes.append({"bbox": (x0, y0, x1, d["bbox"][3]), "fill": d["fill"],
                              "title_bbox": c["bbox"], "title_fill": c["fill"]})
            else:
                used.add(i)
                boxes.append({"bbox": c["bbox"], "fill": c["fill"], "title_bbox": None,
                              "title_fill": None})
        if boxes:
            out[page.number] = boxes
    return out
