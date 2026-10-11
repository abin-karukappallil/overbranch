"""
attachment_figures.py — Figures of an attached PDF, for the agent to place in a document
=========================================================================================
"Make a seminar from this paper" needs the paper's figures, not just its text:
the system-architecture diagram belongs on the architecture slide. This module
finds the figures of an attached PDF and renders them as images the project
can ``\\includegraphics``.

Two decisions shape it:

* **A figure is found by its caption.** A page's graphics are embedded images
  plus vector paths, and neither says "I am Figure 2": a diagram is often
  several images and dozens of paths, a logo or a table rule is none. The
  caption line (``Fig. 2. System architecture``) is what the authors used to
  mark one, so each caption is paired with the graphic region directly above
  it (below, for the styles that put captions on top) in the same column.
  Large uncaptioned graphics are still listed; rules, logos and table frames
  are not.
* **A table is not a figure, but it is listed.** Publishers often typeset
  table bodies as vector outlines (in the paper this was tested on, every
  table was — its text cannot be extracted at all), so the region under a
  ``TABLE 2.`` caption looks exactly like a diagram. It is paired with *its*
  caption and labelled ``table``: an image of a results table is useful on a
  slide, but only when the model knows that is what it is.
* **The region is rendered, not extracted.** Pulling the embedded image out by
  xref loses everything drawn over it — the labels of a block diagram are text,
  the arrows are paths. Rendering the clip of the page gives the figure as the
  reader saw it.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("attachment_figures")

BBox = Tuple[float, float, float, float]

MAX_FIGURE_PAGES = int(os.getenv("AGENT_ATTACH_FIGURE_PAGES", "60") or 60)
MAX_FIGURES = 40
RENDER_DPI = 200
MAX_RENDER_PX = 2400          # longest side of an imported figure
PNG_SOFT_LIMIT = 1_500_000    # larger renders (photographs) are stored as JPEG instead

MIN_SIDE = 36.0               # pt: smaller regions are icons, bullets, rules
MAX_CAPTION_GAP = 48.0        # pt between a graphic and its caption
CLUSTER_PAD = 6.0
LABEL_REACH = 30.0            # pt: axis/tick labels this close to the graphic belong to it
BAND_SLACK = 8.0              # pt a label may sit outside the span of graphic + caption
LABEL_BLOCK_CHARS = 48        # a text block longer than this is prose, not a label
UNCAPTIONED_MIN_SHARE = 0.04  # of the page area, for a graphic nobody captioned
MAX_PATHS = 4000              # beyond this a page's vector art is clustered from a sample

# A caption is the label, its number and a separator ("Fig. 2." / "Figure 2:" / "TABLE II." /
# "Fig. 2 |"), or the label and number alone on a line. "Fig. 2 shows …" and "Table 1
# summarizes …" open paragraphs that *refer* to one: no separator, so no caption.
_RE_CAPTION = re.compile(
    r"^\s*(?P<label>Fig(?:ure)?\.?|FIG(?:URE)?\.?|Table|TABLE|Tab\.)\s*"
    r"(?P<number>\d+[a-z]?|[IVXLC]+)\s*(?:[.:|\-–—]\s*(?P<rest>.*)|$)")


def _fitz():
    try:
        import pymupdf as fitz
    except ImportError:  # pragma: no cover — older installs
        import fitz
    return fitz


def _area(b: BBox) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _union(a: BBox, b: BBox) -> BBox:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _h_overlap(a: BBox, b: BBox) -> float:
    """Horizontal overlap as a share of the narrower box."""
    inter = min(a[2], b[2]) - max(a[0], b[0])
    narrow = min(a[2] - a[0], b[2] - b[0])
    return inter / narrow if narrow > 0 else 0.0


def _text_lines(page: Any) -> List[Dict[str, Any]]:
    """Text lines of a page: text, bbox, and whether the line starts its block."""
    out: List[Dict[str, Any]] = []
    try:
        blocks = page.get_text("dict").get("blocks", [])
    except Exception as e:  # noqa: BLE001
        logger.debug(f"get_text failed on page {page.number + 1}: {e}")
        return out
    for bi, block in enumerate(blocks):
        if block.get("type") != 0:
            continue
        for li, line in enumerate(block.get("lines", [])):
            text = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
            if text:
                out.append({"text": text, "bbox": tuple(line["bbox"]), "block": bi, "first": li == 0})
    chars: Dict[int, int] = {}
    count: Dict[int, int] = {}
    for ln in out:
        chars[ln["block"]] = chars.get(ln["block"], 0) + len(ln["text"])
        count[ln["block"]] = count.get(ln["block"], 0) + 1
    for ln in out:
        ln["label_like"] = chars[ln["block"]] <= LABEL_BLOCK_CHARS and count[ln["block"]] <= 3
    return out


def _captions(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    captions: List[Dict[str, Any]] = []
    for i, ln in enumerate(lines):
        m = _RE_CAPTION.match(ln["text"])
        if not m:
            continue
        # The caption is the rest of its text block, from this line on.
        parts, box = [ln["text"]], ln["bbox"]
        for nxt in lines[i + 1:]:
            if nxt["block"] != ln["block"]:
                break
            parts.append(nxt["text"])
            box = _union(box, nxt["bbox"])
        text = re.sub(r"\s+", " ", " ".join(parts)).strip()
        captions.append({
            "number": m.group("number"), "text": text[:320], "bbox": box, "block": ln["block"],
            "type": "table" if m.group("label").lower().startswith("tab") else "figure",
        })
    return captions


def _graphic_regions(page: Any, fitz: Any) -> List[Dict[str, Any]]:
    """Connected graphic regions of a page (embedded images + vector art), with what they are made of."""
    from pdf2latex.extract import _cluster, _extract_drawings, _page_paths

    pw, ph = page.rect.width, page.rect.height
    page_area = pw * ph
    seeds: List[Tuple[BBox, str, bool]] = []  # (box, kind, complex)

    try:
        infos = page.get_image_info()
    except Exception:  # noqa: BLE001
        infos = []
    for info in infos:
        r = fitz.Rect(info["bbox"]) & page.rect
        if r.is_empty or r.width < 4 or r.height < 4:
            continue
        box = (r.x0, r.y0, r.x1, r.y1)
        if _area(box) >= 0.85 * page_area:
            continue  # a scanned page or a full-page background, not a figure
        seeds.append((box, "image", True))

    paths = _page_paths(page)
    if len(paths) > MAX_PATHS:
        paths = paths[:: max(1, len(paths) // MAX_PATHS)]
    for d in _extract_drawings(page, paths):
        w, h = d.rect[2] - d.rect[0], d.rect[3] - d.rect[1]
        if d.kind == "hrule" and w > 0.7 * pw:
            continue  # header / footer / full-width separator rules
        if d.kind == "vrule" and h > 0.7 * ph:
            continue
        if _area(d.rect) >= 0.85 * page_area:
            continue  # page frame or background fill
        seeds.append((d.rect, "vector", bool(d.complex)))

    regions = []
    for box in _cluster([s[0] for s in seeds], pad=CLUSTER_PAD):
        if box[2] - box[0] < MIN_SIDE or box[3] - box[1] < MIN_SIDE:
            continue
        members = [s for s in seeds if s[0][0] >= box[0] - 1 and s[0][1] >= box[1] - 1
                   and s[0][2] <= box[2] + 1 and s[0][3] <= box[3] + 1]
        kinds = {m[1] for m in members}
        regions.append({
            "bbox": box,
            "kind": "mixed" if len(kinds) > 1 else (next(iter(kinds)) if kinds else "vector"),
            "has_image": "image" in kinds,
            "complex": any(m[2] for m in members),
            "paths": sum(1 for m in members if m[1] == "vector"),
        })
    return regions


def _with_labels(region: BBox, caption: Optional[BBox], lines: List[Dict[str, Any]],
                 caption_blocks: set, page_rect: BBox) -> BBox:
    """
    Grows a graphic region over the text that belongs to it: tick labels, axis
    titles, sub-figure tags. They are text, so no drawing path covers them, and a
    chart cut at its axes loses its numbers.

    What stops it swallowing the neighbouring column: a label sits in a short
    text block of its own (a paragraph's last line is short too, but its block
    is not), inside the band the graphic and its caption span.
    """
    band = _union(region, caption) if caption else region
    x_lo, x_hi = band[0] - BAND_SLACK, band[2] + BAND_SLACK
    lo = region[1] - 8.0
    hi = caption[1] if caption and caption[1] >= region[3] - 4 else region[3] + LABEL_REACH
    box = region
    for _ in range(3):
        grown = box
        for ln in lines:
            if ln["block"] in caption_blocks or not ln["label_like"]:
                continue
            b = ln["bbox"]
            cy = (b[1] + b[3]) / 2
            if not (lo <= cy <= hi) or b[0] < x_lo or b[2] > x_hi:
                continue
            near_h = b[0] <= box[2] + LABEL_REACH and b[2] >= box[0] - LABEL_REACH
            near_v = b[1] <= box[3] + LABEL_REACH and b[3] >= box[1] - LABEL_REACH
            if near_h and near_v:
                grown = _union(grown, b)
        if grown == box:
            break
        box = grown
    return (max(page_rect[0], box[0] - 3), max(page_rect[1], box[1] - 3),
            min(page_rect[2], box[2] + 3), min(page_rect[3], box[3] + 3))


def _page_figures(page: Any, fitz: Any) -> List[Dict[str, Any]]:
    pw, ph = page.rect.width, page.rect.height
    page_rect = (0.0, 0.0, pw, ph)
    lines = _text_lines(page)
    regions = _graphic_regions(page, fitz)
    captions = _captions(lines)
    caption_blocks = {c["block"] for c in captions}
    used: set = set()
    found: List[Dict[str, Any]] = []

    for cap in captions:
        c = cap["bbox"]
        best, best_gap = None, None
        for idx, r in enumerate(regions):
            if idx in used:
                continue
            rb = r["bbox"]
            # A caption is centred under (or over) a figure that may be far narrower or wider.
            if _h_overlap(rb, c) < 0.3:
                continue
            gap_above = c[1] - rb[3]      # graphic above the caption (usual for figures)
            gap_below = rb[1] - c[3]      # caption above the graphic (usual for tables)
            usual, other = (gap_below, gap_above) if cap["type"] == "table" else (gap_above, gap_below)
            if -6 <= usual <= MAX_CAPTION_GAP:
                gap = max(usual, 0.0)
            elif -6 <= other <= MAX_CAPTION_GAP:
                gap = max(other, 0.0) + 12.0  # the unusual side only when the usual one is empty
            else:
                continue
            if best_gap is None or gap < best_gap:
                best, best_gap = idx, gap
        if best is None:
            continue
        used.add(best)
        r = regions[best]
        if cap["type"] == "table":
            # A table is its rules and cells; there are no outside labels to gather, and
            # growing towards a caption that sits *above* it would take the caption in.
            b = r["bbox"]
            box = (max(0.0, b[0] - 3), max(0.0, b[1] - 3), min(pw, b[2] + 3), min(ph, b[3] + 3))
        else:
            box = _with_labels(r["bbox"], c, lines, caption_blocks, page_rect)
        found.append({"bbox": box, "caption": cap["text"], "number": cap["number"],
                      "kind": "table" if cap["type"] == "table" else r["kind"]})

    for idx, r in enumerate(regions):
        if idx in used:
            continue
        # Nobody captioned it: keep it only if it is clearly content, not furniture.
        if _area(r["bbox"]) < UNCAPTIONED_MIN_SHARE * pw * ph:
            continue
        if not (r["has_image"] or (r["complex"] and r["paths"] >= 4)):
            continue  # frames and table rules
        found.append({"bbox": _with_labels(r["bbox"], None, lines, caption_blocks, page_rect),
                      "caption": "", "number": None, "kind": r["kind"]})

    found.sort(key=lambda f: (f["bbox"][1], f["bbox"][0]))
    return found


def extract_figures(pdf_bytes: bytes, max_pages: int = MAX_FIGURE_PAGES) -> List[Dict[str, Any]]:
    """
    Figures and tables of a PDF: ``{id, page, bbox (pt), caption, number, kind, width_px,
    height_px}``, in reading order. ``kind`` is ``image`` / ``vector`` / ``mixed`` for a
    figure and ``table`` for a table; ``id`` is ``p<page>-f<k>`` or ``p<page>-t<k>``.
    """
    fitz = _fitz()
    figures: List[Dict[str, Any]] = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not open PDF for figure extraction: {e}")
        return figures
    try:
        for page in doc:
            if page.number >= max_pages or len(figures) >= MAX_FIGURES:
                break
            try:
                on_page = _page_figures(page, fitz)
            except Exception as e:  # noqa: BLE001 — one odd page must not hide the rest
                logger.warning(f"Figure extraction failed on page {page.number + 1}: {e}")
                continue
            counters = {"f": 0, "t": 0}
            for f in on_page:
                b = f["bbox"]
                scale = _render_scale(b)
                letter = "t" if f["kind"] == "table" else "f"
                counters[letter] += 1
                figures.append({
                    "id": f"p{page.number + 1}-{letter}{counters[letter]}",
                    "page": page.number + 1,
                    "bbox": tuple(round(v, 2) for v in b),
                    "caption": f["caption"] or f"Figure on page {page.number + 1}",
                    "captioned": bool(f["caption"]),
                    "number": f["number"],
                    "kind": f["kind"],
                    "width_px": int((b[2] - b[0]) * scale),
                    "height_px": int((b[3] - b[1]) * scale),
                })
    finally:
        doc.close()
    return figures[:MAX_FIGURES]


def _render_scale(b: BBox) -> float:
    scale = RENDER_DPI / 72.0
    longest = max(b[2] - b[0], b[3] - b[1]) * scale
    return scale * (MAX_RENDER_PX / longest) if longest > MAX_RENDER_PX else scale


def render_figure(pdf_bytes: bytes, figure: Dict[str, Any]) -> Tuple[bytes, str]:
    """Renders one figure's region of its page. Returns (bytes, 'png' | 'jpg')."""
    fitz = _fitz()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc[int(figure["page"]) - 1]
        clip = fitz.Rect(figure["bbox"]) & page.rect
        s = _render_scale(tuple(figure["bbox"]))
        pix = page.get_pixmap(matrix=fitz.Matrix(s, s), clip=clip, alpha=False)
        png = pix.tobytes("png")
        if len(png) > PNG_SOFT_LIMIT:
            try:
                return pix.tobytes("jpeg", jpg_quality=90), "jpg"
            except Exception:  # noqa: BLE001 — a build without JPEG output keeps the PNG
                pass
        return png, "png"
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Attachment records
# ---------------------------------------------------------------------------

def figures_for(record: Dict[str, Any], store: Any) -> List[Dict[str, Any]]:
    """Figures of one attachment (cached on the record). An attached image is one figure."""
    cached = record.get("figures")
    if isinstance(cached, list):
        return cached
    att = record.get("id") or "att"
    figures: List[Dict[str, Any]] = []
    if record.get("kind") == "image":
        figures = [{
            "id": f"{att}-img", "page": 1, "bbox": None, "caption": f"Attached image {record.get('filename')}",
            "captioned": False, "number": None, "kind": "image",
            "width_px": record.get("width_px", 0), "height_px": record.get("height_px", 0),
        }]
    elif record.get("kind") == "pdf":
        data = store.read_bytes(record)
        if data:
            figures = extract_figures(data)
            for f in figures:
                f["id"] = f"{att}-{f['id']}"
    for f in figures:
        f["filename"] = record.get("filename")
    record["figures"] = figures
    return figures


def find_figure(session_id: str, figure_id: str, store: Any) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """(attachment record, figure) for a figure id, tolerant of a missing attachment prefix."""
    wanted = (figure_id or "").strip().strip("[]`'\"").lower()
    if not wanted:
        return None
    loose: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for record in store.get_attachments(session_id):
        for f in figures_for(record, store):
            fid = f["id"].lower()
            if fid == wanted:
                return record, f
            if fid.endswith("-" + wanted) or fid.split("-", 1)[-1] == wanted:
                loose.append((record, f))
    return loose[0] if len(loose) == 1 else None


def figure_bytes(record: Dict[str, Any], figure: Dict[str, Any], store: Any) -> Optional[Tuple[bytes, str]]:
    """The image of a figure as pdfLaTeX can include it: (bytes, 'png' | 'jpg')."""
    data = store.read_bytes(record)
    if not data:
        return None
    if record.get("kind") == "image":
        if data.startswith(b"\x89PNG"):
            return data, "png"
        if data.startswith(b"\xff\xd8\xff"):
            return data, "jpg"
        try:  # WebP and anything else PyMuPDF can read: pdfLaTeX needs PNG or JPEG
            pix = _fitz().Pixmap(data)
            if pix.alpha:
                pix = _fitz().Pixmap(pix, 0)
            return pix.tobytes("png"), "png"
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Could not convert attached image '{record.get('filename')}': {e}")
            return None
    return render_figure(data, figure)


def figure_inventory(session_id: str, store: Any, per_file: int = 12) -> str:
    """The figures of every attachment, as the lines the agent's first message carries."""
    blocks: List[str] = []
    for record in store.get_attachments(session_id):
        figs = figures_for(record, store)
        if not figs:
            continue
        rows = [f"  [{f['id']}] page {f['page']} — {f['caption'][:150]} "
                f"({'image of the typeset table, ' if f['kind'] == 'table' else ''}{f['width_px']}×{f['height_px']} px)"
                for f in figs[:per_file]]
        if len(figs) > per_file:
            rows.append(f"  … {len(figs) - per_file} more: call list_attachment_figures(filename='{record.get('filename')}')")
        blocks.append(f"FIGURES IN {record.get('filename')}:\n" + "\n".join(rows))
    return "\n\n".join(blocks)
