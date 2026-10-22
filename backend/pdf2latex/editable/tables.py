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
    return out


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
    body_w = page.width * 0.8
    table_frac = min(0.98, tb_w / body_w) if body_w else 0.9
    widths = _col_widths(tb, ncol)
    total = sum(widths) or 1.0
    col_frac = [round(max(0.05, table_frac * w / total), 2) for w in widths]
    col_align = ["p"] * ncol
    return Table(page=page.number, bbox=tuple(tb.bbox), rows=cells_grid, col_align=col_align,
                 col_frac=col_frac, header_rows=header_rows, ruled=True, booktabs=False,
                 vrules=set(range(ncol - 1)))


def _col_widths(tb, ncol: int) -> List[float]:
    try:
        edges = sorted({round(c[0], 1) for r in tb.rows for c in (r.cells or []) if c} |
                       {round(tb.bbox[2], 1)})
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
