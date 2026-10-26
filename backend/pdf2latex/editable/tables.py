"""
tables.py — Ruled tables from PyMuPDF find_tables (lines strategy only) and borderless tables from
aligned columns. Returns pre-built Table blocks for the block builder to splice in by position.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from ..models import PageExtract
from .model import Block, Cell, Para, Table, TLine
from .columns import rsz, to_run
from .model import Run, Segment

logger = logging.getLogger("pdf2latex.editable.tables")


def detect_tables(pg, page: PageExtract) -> List[Block]:
    """Ruled tables via find_tables('lines'). Conservative: ≥2×2, <80% of page, ≥2 text lines."""
    out: List[Block] = []
    try:
        found = pg.find_tables(strategy="lines")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"find_tables failed on page {page.number}: {e}")
        return out
    page_area = page.width * page.height
    for tb in getattr(found, "tables", []):
        try:
            rows = tb.extract()
        except Exception:
            continue
        if tb.row_count < 2 or tb.col_count < 2:
            continue
        x0, y0, x1, y1 = tb.bbox
        if (x1 - x0) * (y1 - y0) > 0.8 * page_area:
            continue
        text_lines = [ln for ln in page.lines if x0 - 2 <= ln.bbox[0] and ln.bbox[2] <= x1 + 2
                      and y0 - 2 <= ln.bbox[1] and ln.bbox[3] <= y1 + 2 and ln.text.strip()]
        if len(text_lines) < 2:
            continue
        out.append(_build_ruled(tb, rows, page))
    # Booktabs tables (horizontal rules only) are invisible to the lines strategy; recover them from
    # their rules. Only for regions the lines strategy did not already claim.
    covered = [b.bbox for b in out]
    try:
        out.extend(_booktabs_tables(pg, page, covered))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"booktabs detect failed p{page.number}: {e}")
    return out


def _overlaps(a, b) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _normalize_fracs(fracs: List[float], budget: float) -> List[float]:
    fracs = [max(0.04, f) for f in fracs]
    s = sum(fracs)
    if s > budget and s > 0:
        fracs = [f * budget / s for f in fracs]
    return [round(f, 3) for f in fracs]


def _booktabs_tables(pg, page: PageExtract, covered: List[tuple]) -> List[Block]:
    """Tables ruled only with horizontal (booktabs) rules — invisible to find_tables('lines'). The
    rules bound the table (minus the running header/footer rules); a text-strategy scan clipped to
    that band recovers the columns without swallowing the surrounding prose, and wrapped lines are
    merged back into their rows. Ragged results are rejected (the header must fill every column), so
    an ambiguous or over-split table keeps whatever emission it had."""
    try:
        import pymupdf
    except ImportError:  # pragma: no cover
        import fitz as pymupdf
    hr = sorted((d.rect for d in page.drawings if d.kind == "hrule"), key=lambda r: r[1])
    body = [r for r in hr if 0.12 * page.height < (r[1] + r[3]) / 2 < 0.88 * page.height]
    if len(body) < 2:
        return []
    clusters: List[List[tuple]] = [[body[0]]]
    for r in body[1:]:
        if r[1] - clusters[-1][-1][3] > 0.6 * page.height:
            clusters.append([r])
        else:
            clusters[-1].append(r)
    out: List[Block] = []
    for cl in clusters:
        if len(cl) < 2:
            continue
        x0 = min(r[0] for r in cl) - 3
        y0 = min(r[1] for r in cl) - 3
        x1 = max(r[2] for r in cl) + 3
        y1 = max(r[3] for r in cl) + 3
        if any(_overlaps((x0, y0, x1, y1), c) for c in covered):
            continue
        try:
            tbs = list(getattr(pg.find_tables(strategy="text", clip=pymupdf.Rect(x0, y0, x1, y1)),
                               "tables", []))
        except Exception:
            continue
        if not tbs:
            continue
        tb = max(tbs, key=lambda t: t.col_count * t.row_count)
        try:
            grid = tb.extract()
        except Exception:
            continue
        tbl = _build_booktabs(tb, grid, page, (x0, y0, x1, y1))
        if tbl is not None:
            out.append(tbl)
    return out


def _cell_text_from_lines(page: PageExtract, cb: tuple) -> str:
    """Text of one cell, read from the page's own spans by the cell's box (so a word the text
    strategy split across a column edge stays whole), de-hyphenating line-wrapped words."""
    x0, y0, x1, y1 = cb
    spans = [sp for ln in page.lines for sp in ln.spans if sp.text.strip()
             and x0 - 1 <= (sp.bbox[0] + sp.bbox[2]) / 2 <= x1 + 1
             and y0 - 1 <= (sp.bbox[1] + sp.bbox[3]) / 2 <= y1 + 1]
    spans.sort(key=lambda s: (round(s.bbox[1] / 3), s.bbox[0]))
    out = ""
    for sp in spans:
        t = sp.text.strip()
        if not t:
            continue
        if out.endswith("-") and t[:1].islower():
            out = out[:-1] + t
        elif out:
            out += " " + t
        else:
            out = t
    return " ".join(out.split())


def _page_body_w(page: PageExtract) -> float:
    if getattr(page, "lines", None):
        vis = [ln for ln in page.lines if ln.text.strip()]
        if vis:
            min_x0 = min((ln.bbox[0] for ln in vis if ln.bbox[0] > 20), default=72.0)
            max_x1 = max((ln.bbox[2] for ln in vis if ln.bbox[2] < page.width - 20), default=page.width - 72.0)
            if max_x1 > min_x0 + 100:
                return max_x1 - min_x0
    return max(100.0, page.width - 144.0)


def _build_booktabs(tb, grid, page: PageExtract, bbox: tuple):
    ncol = tb.col_count
    if ncol < 3 or ncol > 10:
        return None
    # read each physical cell from the page spans by cell box (keeps split words whole); fall back to
    # the text strategy's own extraction if the table has no usable cell boxes
    prows: List[List[str]] = []
    try:
        for r in tb.rows:
            cbs = r.cells
            if not cbs or len(cbs) != ncol:
                raise ValueError
            prows.append([_cell_text_from_lines(page, cb) if cb else "" for cb in cbs])
    except Exception:
        prows = [[" ".join((c or "").split()) for c in row] for row in grid]
    if len(prows) < 3:
        return None
    # merge wrapped physical rows: a row whose first cell is empty continues the row above
    logical: List[List[str]] = []
    for cells in prows:
        if not any(cells):
            continue
        if logical and not cells[0]:
            for k in range(ncol):
                if cells[k]:
                    prev = logical[-1][k]
                    logical[-1][k] = (prev[:-1] + cells[k]) if prev.endswith("-") \
                        else (prev + " " + cells[k]).strip()
        else:
            logical.append(list(cells))
    if len(logical) < 2:
        return None
    header = logical[0]
    # gate: the header must label every column (an over-split wide text column leaves an empty
    # header cell) — otherwise the reconstruction is unreliable, so decline it
    if any(not header[k] for k in range(1, ncol)):
        return None
    cells_grid: List[List[Cell]] = []
    for ri, row in enumerate(logical):
        cells_grid.append([Cell(paras=[_text_para(t, page)] if t else [], bold=(ri == 0)) for t in row])
    widths = _col_widths(tb, ncol, max_x1=bbox[2])
    tb_w = bbox[2] - bbox[0]
    body_w = _page_body_w(page)
    table_frac = 1.0 if tb_w >= body_w * 0.90 else min(1.0, max(0.5, tb_w / body_w))
    total = sum(widths) or 1.0
    pad_frac = min(0.35, (2 * max(1, ncol - 1) * 4.0) / max(1.0, body_w))
    budget = max(0.60, table_frac - pad_frac)
    raw_fracs = [budget * w / total for w in widths]
    min_col = max(0.06, min(0.12, 40.0 / body_w))
    col_frac = _normalize_fracs([max(min_col, f) for f in raw_fracs], budget)
    small = ncol >= 5 or len(logical) >= 10
    return Table(page=page.number, bbox=bbox, rows=cells_grid, col_align=["p"] * ncol,
                 col_frac=col_frac, header_rows=1, ruled=True, booktabs=True, vrules=set(), small=small)


def _build_ruled(tb, rows, page: PageExtract) -> Table:
    ncol = tb.col_count
    cells_grid: List[List[Cell]] = []
    header_rows = 0
    for ri, row in enumerate(rows):
        cells: List[Cell] = []
        bold_count = 0
        for cj, val in enumerate(row):
            text = " ".join((val or "").split())   # collapse internal newlines to spaces
            bold, size, color = _cell_style(tb, page, ri, cj)
            if bold and text:
                bold_count += 1
            para = _text_para(text, page, size, color) if text else None
            cells.append(Cell(paras=[para] if para else [], bold=bold))
        cells_grid.append(cells)
        if ri == 0 and bold_count >= max(1, ncol // 2):
            header_rows = 1
    # p-columns sized proportionally to each column's pixel width, summing to the table's share
    tb_w = tb.bbox[2] - tb.bbox[0]
    body_w = _page_body_w(page)
    table_frac = 1.0 if tb_w >= body_w * 0.90 else min(1.0, max(0.5, tb_w / body_w))
    widths = _col_widths(tb, ncol, max_x1=tb.bbox[2])
    total = sum(widths) or 1.0
    pad_frac = min(0.35, (2 * max(1, ncol - 1) * 4.0) / max(1.0, body_w))
    budget = max(0.60, table_frac - pad_frac)
    col_frac = _normalize_fracs([budget * w / total for w in widths], budget)
    col_align = ["p"] * ncol
    return Table(page=page.number, bbox=tuple(tb.bbox), rows=cells_grid, col_align=col_align,
                 col_frac=col_frac, header_rows=header_rows, ruled=True, booktabs=False,
                 vrules=set(range(ncol - 1)))


def _col_widths(tb, ncol: int, max_x1: float = 0.0) -> List[float]:
    try:
        right_edge = max(round(tb.bbox[2], 1), round(max_x1, 1)) if max_x1 > 0 else round(tb.bbox[2], 1)
        edges = sorted({round(c[0], 1) for r in tb.rows for c in (r.cells or []) if c} |
                       {right_edge})
        if len(edges) >= ncol + 1:
            return [edges[i + 1] - edges[i] for i in range(ncol)]
    except Exception:
        pass
    return [1.0] * ncol


def _cell_style(tb, page: PageExtract, ri: int, cj: int):
    """(bold, dominant_size, dominant_color) of the spans inside a cell."""
    from collections import Counter
    try:
        cell_bbox = tb.rows[ri].cells[cj]
    except Exception:
        cell_bbox = None
    if not cell_bbox:
        return False, 0.0, (0, 0, 0)
    x0, y0, x1, y1 = cell_bbox
    spans = [sp for ln in page.lines for sp in ln.spans
             if x0 - 1 <= sp.bbox[0] and sp.bbox[2] <= x1 + 1 and y0 - 1 <= sp.bbox[1] and sp.bbox[3] <= y1 + 1
             and sp.text.strip()]
    if not spans:
        return False, 0.0, (0, 0, 0)
    szc: Counter = Counter()
    cc: Counter = Counter()
    for sp in spans:
        n = len(sp.text.strip())
        szc[round(sp.size * 2) / 2] += n
        cc[sp.color] += n
    return all(sp.bold for sp in spans), szc.most_common(1)[0][0], cc.most_common(1)[0][0]


def _text_para(text: str, page: PageExtract, size: float = 0.0, color=(0, 0, 0)) -> Para:
    run = Run(text=text, size=size or 0.0, family="serif", font_cls="times", bold=False,
              italic=False, color=color)
    seg = Segment(runs=[run], x0=0, x1=0)
    tl = TLine(segments=[seg], x0=0, x1=0, top=0, bottom=0, baseline=0, page=page.number,
               size=size or 0.0)
    return Para(page=page.number, bbox=(0, 0, 0, 0), lines=[tl])
