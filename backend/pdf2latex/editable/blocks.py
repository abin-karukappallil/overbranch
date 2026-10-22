"""
blocks.py — Structural analysis: rows → semantic blocks.

Takes the rebuilt rows (one zone at a time, in reading order) plus the page's figures and rules,
and produces a flat list of ``Block``s: figures, lists, headings, paragraphs, rules and notes.
Tables and math are detected upstream (enrich/tables) and passed in as pre-built blocks to splice
in by position. Nothing here positions by coordinate.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

from ..models import Drawing, ImageRef, PageExtract
from .columns import zone_captures_x
from .model import (HFILL, Block, Box, Cell, Figure, Heading, Item, ListBlock, Math, Note, Para, Rule,
                    Run, Segment, Table, TLine, Zone)
from .profile import (EditProfile, heading_candidate, is_upper, key_align, match_level, row_align, row_bold,
                      row_color, row_family, row_italic, row_mostly_bold)

# Marker patterns for list items.
_BULLET = re.compile(r"^\s*([•●○◦▪■□▶►➢➤✦✧✓✔❖◆◇*·‣⁃\-–—])\s+")
_ORDERED = re.compile(r"^\s*(\(?)(\d{1,3}|[a-zA-Z]|[ivxlcdmIVXLCDM]{1,6})([.)\]])\s+")
_COMPOUND = re.compile(r"^\s*(\d{1,3})\s+([a-z])\)\s+")   # "11 a) ..." question-paper style
_REF = re.compile(r"^\s*\[(\d{1,3})\]\s+")                # "[3] ..." bibliography
_NUM_PREFIX = re.compile(r"^\s*((?:chapter|section|part)\s+)?"
                         r"((?:\d+|[IVXLC]+|[A-Z])(?:\.\d+)*)[.)]?\s+", re.IGNORECASE)


# ---------------------------------------------------------------------------
# A positioned item in a zone's stream: a row, a figure or a rule.
# ---------------------------------------------------------------------------

class _FigItem:
    def __init__(self, img: ImageRef):
        self.img = img
        self.top = img.bbox[1]
        self.kind = "fig"


class _RuleItem:
    def __init__(self, d: Drawing):
        self.d = d
        self.top = d.rect[1]
        self.kind = "rule"


class _RowItem:
    def __init__(self, row: TLine):
        self.row = row
        self.top = row.top
        self.kind = "row"


# ---------------------------------------------------------------------------
# Marker detection
# ---------------------------------------------------------------------------

def _marker(text: str) -> Optional[Tuple[str, str, str]]:
    """(label_text, kind, value) for a list marker at the row start, else None."""
    m = _REF.match(text)
    if m:
        return f"[{m.group(1)}]", "ref", m.group(1)
    m = _COMPOUND.match(text)
    if m:
        return f"{m.group(1)} {m.group(2)})", "compound", m.group(2)
    m = _BULLET.match(text)
    if m:
        return m.group(1), "bullet", m.group(1)
    m = _ORDERED.match(text)
    if m:
        lead, val, close = m.group(1), m.group(2), m.group(3)
        kind = "roman" if re.fullmatch(r"[ivxlcdmIVXLCDM]+", val) and val.lower() != "i" else (
            "alpha" if val.isalpha() else "decimal")
        # "i" alone is ambiguous (roman one vs letter i); treat as alpha unless in a roman run
        if val.lower() == "i":
            kind = "alpha"
        return f"{lead}{val}{close}", kind, val
    return None


_SEG_LABEL = re.compile(r"^\(?(\d{1,3}|[a-zA-Z]|[ivxlcdmIVXLCDM]{1,6})[.)\]]?$")


def _kind_of(val: str) -> str:
    if val.isdigit():
        return "decimal"
    if re.fullmatch(r"[ivxlcdmIVXLCDM]+", val) and val.lower() != "i":
        return "roman"
    return "alpha"


def _row_marker(row: TLine) -> Optional[Tuple[str, str, str]]:
    """
    The row's list marker: a textual one ("1.", "(a)", "•", "[3]") at the start of the text, or a
    short label standing alone in its own first segment before a tab gap ("1", "a", "iv") — the
    numbered-question shape, where the number sits in its own column.
    """
    m = _marker(row.text)
    if m:
        return m
    if len(row.segments) >= 2:
        lab = row.segments[0].text.strip()
        mm = _SEG_LABEL.match(lab)
        if mm and len(lab) <= 5:
            return lab, _kind_of(mm.group(1)), mm.group(1)
    return None


def _strip_marker(row: TLine, marker_text: str) -> None:
    """Remove the marker (and following space) from the row, in place."""
    if len(row.segments) >= 2 and row.segments[0].text.strip() == marker_text.strip():
        row.segments = row.segments[1:]          # the label had its own segment
        row.x0 = row.segments[0].x0
        return
    for seg in row.segments:
        for r in seg.runs:
            if r.text.strip():
                stripped = r.text.lstrip()
                # drop the literal marker glyph(s) and following whitespace
                mt = marker_text.strip()
                if stripped.startswith(mt):
                    r.text = stripped[len(mt):].lstrip()
                else:
                    # marker may be split; fall back to regex removal on the combined text
                    r.text = re.sub(r"^\s*\S+\s+", "", r.text, count=1)
                return


# ---------------------------------------------------------------------------
# Block building
# ---------------------------------------------------------------------------

class _Builder:
    def __init__(self, profile: EditProfile, col_left: float, col_right: float):
        self.p = profile
        self.col_left = col_left
        self.col_right = col_right
        self._id = 0

    def nid(self) -> int:
        self._id += 1
        return self._id

    def build_zone(self, page: int, items: List, col_left: float, col_right: float) -> List[Block]:
        items = sorted(items, key=lambda it: it.top)
        out: List[Block] = []
        i = 0
        n = len(items)
        while i < n:
            it = items[i]
            if it.kind == "pre":   # a pre-built table or math block, spliced in by position
                out.append(it.block)
                i += 1
                continue
            if it.kind == "fig":
                out.append(self._figure(page, it.img, col_left, col_right))
                i += 1
                continue
            if it.kind == "rule":
                r = self._rule(page, it.d, col_left, col_right)
                if r:
                    out.append(r)
                i += 1
                continue
            row = it.row
            if not row.text.strip():
                i += 1
                continue
            # heading?
            lv = match_level(self.p, row, col_left, col_right)
            if lv is not None:
                h = self._heading(page, row, lv, col_left, col_right)
                i += 1
                # a heading broken over several lines (a long title): same style, line spacing
                while i < n and items[i].kind == "row" and items[i].row.text.strip():
                    nxt = items[i].row
                    prev_base = h.bbox[3]
                    # the next line in the same size and weight, at line spacing (its alignment may
                    # differ: a second title line centred under the title text, not the column)
                    if not heading_candidate(nxt, self.p.body_size) or abs(nxt.size - row.size) > 0.6 \
                            or row_mostly_bold(nxt) != row_mostly_bold(row) \
                            or nxt.top - prev_base > 0.9 * nxt.size:
                        break
                    from .model import LINEBREAK, Run as _Run
                    if h.runs:
                        h.runs[-1] = _Run(**{**h.runs[-1].__dict__, "text": h.runs[-1].text.rstrip()})
                        # the PDF's own line break in a heading set over several lines
                        h.runs.append(_Run(**{**h.runs[-1].__dict__, "text": LINEBREAK}))
                    h.runs.extend(_runs_spaced(nxt, col_left, col_right))
                    h.bbox = (min(h.bbox[0], nxt.x0), h.bbox[1], max(h.bbox[2], nxt.x1), nxt.bottom)
                    h.baselines.append(nxt.baseline)
                    i += 1
                out.append(h)
                continue
            # list?
            if _row_marker(row):
                lst, consumed = self._list(page, items, i, col_left, col_right)
                if lst is not None and not lst.ordered and _marker(row.text) is None \
                        and len(row.segments) >= 2:
                    # A short label in its own column that doesn't count up (n, q, t, A …) is a
                    # table's label column, not a list: prefer the table when it covers as much.
                    tbl, t_consumed = self._borderless(page, items, i, col_left, col_right)
                    if tbl is not None and t_consumed >= consumed:
                        out.append(tbl)
                        i = t_consumed
                        continue
                if lst is not None:
                    out.append(lst)
                    i = consumed
                    continue
            # borderless table (fields aligned on the same column anchors over ≥3 rows)?
            if len(row.segments) >= 2:
                tbl, consumed = self._borderless(page, items, i, col_left, col_right)
                if tbl is None:
                    # side-by-side centred blocks (signatures: name / role / department)
                    tbl, consumed = self._column_block(page, items, i, col_left, col_right)
                if tbl is not None:
                    out.append(tbl)
                    i = consumed
                    continue
            # paragraph (gather continuation rows)
            para, consumed = self._paragraph(page, items, i, col_left, col_right)
            out.append(para)
            i = consumed
        return out

    # -- figures -----------------------------------------------------------
    def _figure(self, page: int, img: ImageRef, col_left: float, col_right: float) -> Figure:
        # width relative to the zone it sits in (a column of a two-column band, or the full body)
        W = col_right - col_left
        frac = min(1.0, round((img.bbox[2] - img.bbox[0]) / W, 2)) if W > 0 else 0.5
        cx = (img.bbox[0] + img.bbox[2]) / 2
        mid = (col_left + col_right) / 2
        align = "center" if abs(cx - mid) <= 0.15 * W else ("left" if cx < mid else "right")
        return Figure(page=page, bbox=img.bbox, id=self.nid(), images=[img.file],
                      width_frac=[max(0.05, frac)], align=align)

    # -- rules -------------------------------------------------------------
    def _rule(self, page: int, d: Drawing, col_left: float, col_right: float) -> Optional[Rule]:
        if d.kind != "hrule":
            return None
        W = col_right - col_left
        w = d.rect[2] - d.rect[0]
        if W <= 0 or w < 0.25 * W:
            return None
        cx = (d.rect[0] + d.rect[2]) / 2
        align = "center" if abs(cx - (col_left + col_right) / 2) <= 0.1 * W else (
            "left" if cx < (col_left + col_right) / 2 else "right")
        return Rule(page=page, bbox=d.rect, id=self.nid(), width_frac=min(1.0, round(w / W, 2)),
                    thickness=max(0.2, round(d.width or 0.4, 1)), color=d.stroke or d.fill or (0, 0, 0),
                    align=align)

    # -- headings ----------------------------------------------------------
    def _heading(self, page: int, row: TLine, lv: Dict, col_left: float = 0.0,
                 col_right: float = 0.0) -> Heading:
        number = None
        runs = _runs_spaced(row, col_left, col_right)
        m = _NUM_PREFIX.match(row.text)
        if m and m.group(2):
            number = m.group(2)
        return Heading(page=page, bbox=(row.x0, row.top, row.x1, row.bottom), id=self.nid(),
                       level=lv["level"], number=number, runs=[r for r in runs if r.text.strip() or r.text == " "],
                       style_key=(lv["size"], lv["bold"], lv["italic"], lv["family"], lv["align"]),
                       starts_page=False,
                       # a full-width title line is as much centred as flush left: its level's way
                       align=(key_align(row, col_left, col_right, self._page_w()) or lv["align"]),
                       baselines=[row.baseline])

    # -- lists -------------------------------------------------------------
    def _list(self, page: int, items: List, start: int, col_left: float, col_right: float
              ) -> Tuple[Optional[ListBlock], int]:
        first = items[start].row
        mk = _row_marker(first)
        marker_x = first.x0
        text_x = self._marker_text_x(first, mk[0])
        collected: List[Tuple[TLine, Tuple[str, str, str]]] = [(first, mk)]
        # continuation + further items
        i = start + 1
        n = len(items)
        leading = self._leading_for(first.size)
        text_x_seen = len(first.segments) >= 2 and first.segments[0].text.strip() == mk[0].strip()
        item_rows: List[List[TLine]] = [[first]]
        values: List[str] = [mk[2]]
        kinds: List[str] = [mk[1]]
        while i < n:
            it = items[i]
            if it.kind != "row" or not it.row.text.strip():
                break
            row = it.row
            rm = _row_marker(row)
            if rm and abs(row.x0 - marker_x) <= 3:
                item_rows.append([row])
                values.append(rm[2])
                kinds.append(rm[1])
                collected.append((row, rm))
                i += 1
                continue
            # continuation of the current item: indented under the item's text, at line spacing.
            # The text's start is only estimated from the marker row, so the first continuation
            # line (anywhere within three ems right of the marker) fixes it for the rest.
            prev_bottom = item_rows[-1][-1].baseline
            under_text = abs(row.x0 - text_x) <= 6 or (
                not text_x_seen and marker_x + 2 < row.x0 <= marker_x + 3 * first.size)
            if not rm and under_text and 0 < (row.baseline - prev_bottom) <= 1.6 * leading \
                    and match_level(self.p, row, col_left, col_right) is None:
                if not text_x_seen:
                    text_x, text_x_seen = row.x0, True
                item_rows[-1].append(row)
                i += 1
                continue
            break
        if len(item_rows) < 2 and not (mk[1] == "bullet"):
            return None, start
        ordered = kinds[0] in ("decimal", "alpha", "roman", "ref", "compound")
        label_kind = kinds[0]
        # strip markers and build items
        items_out: List[Item] = []
        for rows, (label, _) in zip(item_rows, [(_row_marker(r[0])[0], None) for r in item_rows]):
            body_row0 = rows[0]
            mrun = next((r for r in body_row0.runs if r.text.strip()), None)
            label_color = mrun.color if mrun is not None else None
            bm = _row_marker(body_row0)
            _strip_marker(body_row0, bm[0] if bm else "")
            para = Para(page=page, bbox=body_row0.bbox, id=self.nid(), lines=rows,
                        align="left", leading=leading, left=col_left, right=col_right)
            items_out.append(Item(label=label, body=[para], label_color=label_color))
        consecutive = ordered and _is_consecutive(values, label_kind)
        lb = ListBlock(page=page, bbox=first.bbox, id=self.nid(), ordered=consecutive,
                       label_kind=label_kind, start=_start_value(values[0], label_kind),
                       items=items_out, marker_x=marker_x, text_x=text_x,
                       itemsep=self._itemsep(item_rows), left=col_left)
        return lb, i

    def _itemsep(self, item_rows: List[List[TLine]]) -> float:
        """Extra space between items: first-line pitch minus the line pitch at that size."""
        firsts = [rows[0].baseline for rows in item_rows]
        pitches = []
        for k in range(len(item_rows) - 1):
            nlines = len(item_rows[k])
            lead = self._leading_for(item_rows[k][0].size)
            pitches.append(firsts[k + 1] - firsts[k] - (nlines - 1) * lead - lead)
        if not pitches:
            return 0.0
        pitches.sort()
        return round(max(0.0, pitches[len(pitches) // 2]), 1)

    def _marker_text_x(self, row: TLine, marker_text: str) -> float:
        # where the item text begins: start of the first run after the marker
        mt = marker_text.strip()
        if len(row.segments) >= 2 and row.segments[0].text.strip() == mt:
            return row.segments[1].x0
        # approximate: marker width proportional to its char share of the first segment
        if row.segments:
            seg = row.segments[0]
            frac = min(1.0, (len(mt) + 1) / max(1, len(seg.text)))
            return seg.x0 + frac * (seg.x1 - seg.x0)
        return row.x0 + 12

    # -- borderless tables -------------------------------------------------
    def _borderless(self, page: int, items: List, start: int, col_left: float, col_right: float
                    ) -> Tuple[Optional[Table], int]:
        """
        Rows whose fields start on shared column anchors — an abbreviations or symbols list, a
        contents page — as a tabular. The anchors are clustered over all the rows, so a contents
        page whose chapter rows (number, title, page) and section rows (indented number, title,
        page) use different starting points still lines up; a field that skips an anchor spans the
        skipped columns. A one-field row that starts on a later anchor continues the cell above (a
        wrapped title). Needs ≥3 rows; stops at a heading, a textual list item, a big gap, or a
        field that sits on no anchor.
        """
        leading = self._leading_for(items[start].row.size)
        cand: List[TLine] = []
        last_base = None
        i = start
        while i < len(items):
            it = items[i]
            if it.kind != "row" or not it.row.text.strip():
                break
            r = it.row
            if i > start and (match_level(self.p, r, col_left, col_right) is not None
                              or _marker(r.text) is not None):
                break   # a heading or a textual list item ends it; a bare label column does not
            if last_base is not None:
                gap = r.baseline - last_base
                if gap <= 0 or gap > 3.2 * leading:
                    break
            if len(r.segments) < 2:
                # a one-field row continues the cell above only when it is a wrapped line of it:
                # starting right of the first column, same size, at line spacing
                if (not cand or r.segments[0].x0 <= cand[0].segments[0].x0 + 4
                        or abs(r.size - cand[-1].size) > 0.6
                        or (last_base is not None and r.baseline - last_base > 1.6 * self._leading_for(r.size))):
                    break
            cand.append(r)
            last_base = r.baseline
            i += 1
        multi = [r for r in cand if len(r.segments) >= 2]
        if len(multi) < 3:
            return None, start
        # cluster all field starts into anchors
        xs = sorted(seg.x0 for r in cand for seg in r.segments)
        anchors: List[float] = []
        for x in xs:
            if anchors and x - anchors[-1] <= 8:
                continue
            anchors.append(x)
        if len(anchors) > 6:
            return None, start
        def anchor_of(x: float) -> int:
            return min(range(len(anchors)), key=lambda k: abs(anchors[k] - x))
        # every multi-field row must use ≥2 anchors that other rows share
        rows: List[List[List[Segment]]] = []
        bases: List[float] = []
        spans_x1: Dict[int, List[float]] = {}
        number_cols = {anchor_of(r.segments[0].x0) for r in cand if len(r.segments) >= 2
                       and _SECNUM.fullmatch(r.segments[0].text.strip())}
        for r in cand:
            if len(r.segments) == 1 and anchor_of(r.segments[0].x0) in number_cols:
                split = _split_number(r.segments[0])
                k = anchor_of(r.segments[0].x0)
                if split and k + 1 < len(anchors):
                    cells = [[] for _ in anchors]
                    cells[k].append(split[0])
                    cells[k + 1].append(split[1])
                    spans_x1.setdefault(k, []).append(split[0].x1)
                    rows.append(cells)
                    bases.append(r.baseline)
                    continue
            idx = [anchor_of(seg.x0) for seg in r.segments]
            if len(r.segments) >= 2 or not rows:
                cells: List[List[Segment]] = [[] for _ in anchors]
                for seg, k in zip(r.segments, idx):
                    cells[k].append(seg)
                    spans_x1.setdefault(k, []).append(seg.x1)
                rows.append(cells)
                bases.append(r.baseline)
            else:
                rows[-1][idx[0]].extend(r.segments)
        W = max(1.0, col_right - col_left)
        widths = [anchors[k + 1] - anchors[k] for k in range(len(anchors) - 1)] + [col_right - anchors[-1]]
        tabcolsep = 6.0
        fracs = [round(max(0.03, (w - 2 * tabcolsep) / W), 3) for w in widths[:-1]]
        fracs.append(round(max(0.05, (widths[-1] - tabcolsep) / W), 3))
        # a column whose fields end on a common right edge (page numbers) is right-aligned
        aligns = []
        for k in range(len(anchors)):
            ends = spans_x1.get(k, [])
            starts = [seg.x0 for cells in rows for seg in cells[k]]
            right = (len(ends) >= 3 and max(ends) - min(ends) <= 3 and max(starts) - min(starts) > 2
                     and k == len(anchors) - 1)
            aligns.append("r" if right else "p")
        if aligns[-1] == "r":
            fracs[-1] = round(max(0.03, (max(spans_x1[len(anchors) - 1]) - anchors[-1] + 2) / W), 3)
        grid: List[List[Cell]] = []
        for cells in rows:
            row_cells: List[Cell] = []
            k = 0
            while k < len(cells):
                segs = cells[k]
                if not segs:
                    row_cells.append(Cell())
                    k += 1
                    continue
                # span the empty columns up to the next filled one (never into the last column
                # when that holds the right-aligned page numbers)
                nxt = k + 1
                limit = len(cells) - (1 if aligns[-1] == "r" else 0)
                while nxt < limit and not cells[nxt]:
                    nxt += 1
                span = max(1, (nxt - k) if nxt < len(cells) and cells[nxt] else 1)
                lines = [TLine(segments=[sg], x0=sg.x0, x1=sg.x1, top=0, bottom=0, baseline=0,
                               page=page, size=0) for sg in segs]
                row_cells.append(Cell(paras=[Para(page=page, lines=lines)], colspan=span))
                k += span
            grid.append(row_cells)
        pitches = [b - a for a, b in zip(bases, bases[1:]) if b > a]
        pitch = sorted(pitches)[len(pitches) // 2] if pitches else leading
        stretch = round(pitch / leading, 2) if leading else 1.0
        bbox = (anchors[0], cand[0].top, col_right, cand[-1].bottom)
        consumed = start + len(cand)
        return Table(page=page, bbox=bbox, id=self.nid(), rows=grid, col_align=aligns,
                     col_frac=fracs, ruled=False, indent=round(anchors[0] - col_left, 1),
                     stretch=stretch if stretch > 1.15 else 1.0, width_pt=W), consumed

    def _page_w(self) -> float:
        return self.p.paper_pt[0] if self.p.paper_pt else 0.0

    def _column_block(self, page: int, items: List, start: int, col_left: float, col_right: float
                      ) -> Tuple[Optional[Table], int]:
        """
        Rows whose fields are centred on the same 2–4 column centres (three signatures side by
        side, each a name over a role over a department) as one row of centred, stacked cells.
        """
        W = max(1.0, col_right - col_left)
        cand: List[TLine] = []
        last = None
        i = start
        while i < len(items) and len(cand) < 14:
            it = items[i]
            if it.kind != "row" or not it.row.text.strip():
                break
            r = it.row
            if last is not None and not (0 < r.baseline - last <= 2.6 * self._leading_for(r.size)):
                break
            if any(seg.x1 - seg.x0 > 0.45 * W for seg in r.segments):
                break
            cand.append(r)
            last = r.baseline
            i += 1
        centres = sorted((seg.x0 + seg.x1) / 2 for r in cand for seg in r.segments)
        clusters: List[List[float]] = []
        for c in centres:
            if clusters and c - clusters[-1][-1] <= 0.06 * W:
                clusters[-1].append(c)
            else:
                clusters.append([c])
        cols = [sum(c) / len(c) for c in clusters]
        if not (2 <= len(cols) <= 4) or any(b - a < 0.2 * W for a, b in zip(cols, cols[1:])):
            return None, start

        def col_of(seg):
            c = (seg.x0 + seg.x1) / 2
            k = min(range(len(cols)), key=lambda j: abs(cols[j] - c))
            return k if abs(cols[k] - c) <= 0.06 * W else None
        rows: List[TLine] = []
        for r in cand:
            if any(col_of(seg) is None for seg in r.segments):
                break
            rows.append(r)
        if sum(1 for r in rows if len(r.segments) >= 2) < 2:
            return None, start
        stacks: List[List[Segment]] = [[] for _ in cols]
        for r in rows:
            for seg in r.segments:
                stacks[col_of(seg)].append(seg)
        cells = []
        for segs in stacks:
            paras = [Para(page=page, lines=[TLine(segments=[sg], x0=sg.x0, x1=sg.x1, top=0, bottom=0,
                                                  baseline=0, page=page, size=0)]) for sg in segs]
            cells.append(Cell(paras=paras, stack=True))
        sep = 12.0 / W
        widths = [max((sg.x1 - sg.x0 for sg in segs), default=0.0) + 14.0 for segs in stacks]
        scale = min(1.0, (1.0 - sep * len(cols)) / max(1e-6, sum(widths) / W))
        fracs = [round(scale * w / W, 3) for w in widths]
        bbox = (col_left, rows[0].top, col_right, rows[-1].bottom)
        x0 = min(sg.x0 for segs in stacks for sg in segs)
        x1 = max(sg.x1 for segs in stacks for sg in segs)
        spread = (x0 - col_left) <= 0.05 * W and (col_right - x1) <= 0.05 * W
        return Table(page=page, bbox=bbox, id=self.nid(), rows=[cells], col_align=["c"] * len(cols),
                     col_frac=fracs, ruled=False, width_pt=W, centered=True, spread=spread), start + len(rows)

    def _leading_for(self, size: float) -> float:
        """The measured line pitch for text of this size (the body's for body-size text)."""
        lbs = getattr(self.p, "leading_by_size", {}) or {}
        if size in lbs:
            return lbs[size]
        near = [k for k in lbs if abs(k - size) <= 0.6]
        if near:
            return lbs[min(near, key=lambda k: abs(k - size))]
        if abs(size - self.p.body_size) <= 0.6:
            return self.p.leading or 1.2 * size
        return 1.2 * size

    # -- paragraphs --------------------------------------------------------
    def _paragraph(self, page: int, items: List, start: int, col_left: float, col_right: float
                   ) -> Tuple[Para, int]:
        row0 = items[start].row
        lines = [row0]
        body_left = row0.x0
        leading = self._leading_for(row0.size)
        i = start + 1
        n = len(items)
        while i < n:
            it = items[i]
            if it.kind != "row" or not it.row.text.strip():
                break
            r = it.row
            prev = lines[-1]
            gap = r.baseline - prev.baseline
            scope_ok = abs(r.size - prev.size) <= 0.6 and row_family(r) == row_family(prev)
            not_marker = _row_marker(r) is None
            indent_doc = (self.p.parindent or 0) > 0
            # the second line of a paragraph whose first line carries the first-line indent
            mid = (col_left + col_right) / 2
            if len(lines) == 1 and 4 <= row0.x0 - r.x0 <= 48 and abs(r.x0 - col_left) <= 4:
                near_left = True
                body_left = r.x0
            elif abs((r.x0 + r.x1) / 2 - mid) <= 3 and abs((prev.x0 + prev.x1) / 2 - mid) <= 3 \
                    and r.x0 > col_left + 6 and prev.x0 > col_left + 6:
                near_left = True          # the next line of a centred block (a wrapped title)
            elif r.x0 > body_left + 4:
                # an indented line starts the next paragraph where paragraphs are marked by an
                # indent; elsewhere it may be a hanging continuation
                near_left = not indent_doc
            else:
                near_left = abs(r.x0 - body_left) <= 3
            # a short line ends a justified paragraph (ragged text, where every line is short,
            # is told apart by having no full line yet)
            full = [l for l in lines if l.x1 >= col_right - 2.0 * l.size]
            ended = bool(full) and prev.x1 < col_right - 2.0 * prev.size
            # A tight baseline gap means a soft line break inside the paragraph (true for ragged
            # text too, where lines never reach the right margin); a wider gap starts a new
            # paragraph. This keeps short-line documents (résumés, question papers) from turning
            # every line into its own paragraph.
            if scope_ok and 0 < gap <= 1.35 * leading and near_left and not_marker and not ended \
                    and match_level(self.p, r, col_left, col_right) is None:
                lines.append(r)
                i += 1
                continue
            break
        align = _para_align(lines, col_left, col_right, self._page_w())
        body_x = min(l.x0 for l in lines[1:]) if len(lines) > 1 else (
            col_left if 4 <= row0.x0 - col_left <= 48 else row0.x0)
        indent_l = max(0.0, round(body_x - col_left)) if align in ("left", "justify") else 0.0
        first_indent = max(0.0, round(row0.x0 - min(l.x0 for l in lines[1:]), 1)) if len(lines) > 1 \
            else max(0.0, round(row0.x0 - col_left, 1))
        para = Para(page=page, bbox=(row0.x0, row0.top, row0.x1, lines[-1].bottom), id=self.nid(),
                    lines=lines, align=align, indent_l=indent_l if indent_l > 6 else 0.0,
                    first_indent=first_indent if first_indent > 4 else 0.0, leading=leading,
                    left=col_left, right=col_right)
        return para, i


def _para_align(lines: List[TLine], col_left: float, col_right: float, page_w: float = 0.0) -> str:
    col_center = (col_left + col_right) / 2
    if page_w and all(abs((l.x0 + l.x1) / 2 - page_w / 2) <= 4 for l in lines) \
            and not all(abs((l.x0 + l.x1) / 2 - col_center) <= 3 for l in lines) \
            and max(l.x1 - l.x0 for l in lines) < 0.9 * page_w:
        return "center"
    W = col_right - col_left
    # Justified: the lines (but the last) share one left and one right edge across (nearly) the
    # column's width; the first may carry an indent. The edges are the text's own: a column zone
    # of a two-column page also takes in half the gutter, so its bounds are not where text ends.
    if len(lines) >= 2:
        non_last = lines[:-1]
        right_edge = max(l.x1 for l in non_last)
        left_edge = min(l.x0 for l in lines[1:])
        flush = sum(1 for k, l in enumerate(non_last)
                    if l.x1 >= right_edge - 2 and l.x0 <= left_edge + (48 if k == 0 else 3))
        # its last line starts at the left edge too (a centred block's last line sits inward), or
        # runs full (the paragraph goes on, on the next page)
        last = lines[-1]
        last_ok = last.x0 <= left_edge + 3 or last.x1 >= right_edge - 2
        # and the text meets the column's edge on one side at least (a zone of a two-column page
        # may take in half the gutter on the other)
        on_edge = left_edge <= col_left + 3 or right_edge >= col_right - 0.03 * W
        if flush >= 0.8 * len(non_last) and right_edge - left_edge >= 0.85 * W \
                and left_edge <= col_left + 0.15 * W and last_ok and on_edge:
            return "justify"
    elif lines and lines[0].x1 - lines[0].x0 >= 0.9 * W:
        return "left"             # one line across the column: plain text, not a centred line
    if all(abs((l.x0 + l.x1) / 2 - col_center) <= 3 for l in lines):
        return "center"
    # right-aligned: ragged left edges; an indented first line over full-width lines is a
    # justified paragraph that runs on to the next page, not right-aligned text
    rest = lines[1:] or lines
    if all(l.x1 >= col_right - 3 for l in lines) and any(l.x0 > col_left + 6 for l in rest):
        return "right"
    if all(l.x0 > col_left + 0.3 * W for l in lines):
        return "offset"
    return "left"


def _is_consecutive(values: List[str], kind: str) -> bool:
    if len(values) < 2:
        return True
    try:
        if kind == "decimal" or kind == "ref" or kind == "compound":
            nums = [int(re.sub(r"[^0-9]", "", v)) for v in values]
        elif kind == "alpha":
            nums = [ord(v.lower()) for v in values]
        elif kind == "roman":
            nums = [_roman(v) for v in values]
        else:
            return False
    except (ValueError, KeyError):
        return False
    return all(b - a == 1 for a, b in zip(nums, nums[1:]))


def _start_value(v: str, kind: str) -> int:
    try:
        if kind in ("decimal", "ref", "compound"):
            return int(re.sub(r"[^0-9]", "", v) or 1)
        if kind == "alpha":
            return ord(v.lower()) - ord("a") + 1
        if kind == "roman":
            return _roman(v)
    except (ValueError, KeyError):
        pass
    return 1


_ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def _roman(s: str) -> int:
    s = s.lower()
    total = 0
    prev = 0
    for ch in reversed(s):
        val = _ROMAN[ch]
        total += -val if val < prev else val
        prev = max(prev, val)
    return total


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------

def build_blocks(pages: List[PageExtract], page_layout: Dict[int, List[Tuple[Zone, List[TLine]]]],
                 profile: EditProfile, col_left: float, col_right: float,
                 table_blocks: Optional[Dict[int, List[Block]]] = None,
                 math_blocks: Optional[Dict[int, List[Block]]] = None,
                 note_stacks: Optional[Dict[int, List[List[TLine]]]] = None,
                 boxes: Optional[Dict[int, List[dict]]] = None,
                 furniture=None) -> List[Block]:
    """Build the ordered block list across all pages. Returns blocks only (no PageMarks;
    pages.py inserts those)."""
    table_blocks = table_blocks or {}
    math_blocks = math_blocks or {}
    note_stacks = note_stacks or {}
    boxes = boxes or {}
    furn_imgs = getattr(furniture, "image_keys", set()) or set()
    furn_rules = getattr(furniture, "rule_keys", set()) or set()
    b = _Builder(profile, col_left, col_right)
    out: List[Block] = []
    for p in pages:
        page_blocks: List[Block] = []
        # splice pre-built tables/math as positioned items
        extra_items: List = []
        suppress: List[Tuple[float, float, float, float]] = []   # bboxes whose rows are replaced
        used_imgs: Set[int] = {id(img) for img in p.images if (p.number, img.file) in furn_imgs}
        used_rules: Set[int] = {id(d) for d in p.drawings if d.kind == "hrule"
                                and (p.number, int(round((d.rect[1] + d.rect[3]) / 4))) in furn_rules}
        for tb in table_blocks.get(p.number, []):
            tb.id = b.nid()
            extra_items.append(_PreItem(tb))
            suppress.append(tb.bbox)
        for mb in math_blocks.get(p.number, []):
            mb.id = b.nid()
            extra_items.append(_PreItem(mb))
            suppress.append(mb.bbox)
        all_rows = [r for _z, rows in page_layout.get(p.number, []) for r in rows]
        for spec in boxes.get(p.number, []):
            bx = _build_box(b, p.number, spec, all_rows, col_left, col_right)
            if bx is not None:
                extra_items.append(_PreItem(bx))
                suppress.append(spec["bbox"])
        for z, rows in page_layout.get(p.number, []):
            # drop rows whose content is already carried by a table/math block
            kept = [r for r in rows if not _covered(r, suppress)]
            items: List = [_RowItem(r) for r in kept]
            # figures whose centre-x falls in this zone
            for img in p.images:
                cx = (img.bbox[0] + img.bbox[2]) / 2
                if id(img) in used_imgs:
                    continue
                if zone_captures_x(z, cx) and z.bbox[1] - 2 <= img.bbox[1] <= z.bbox[3] + 40:
                    used_imgs.add(id(img))
                    items.append(_FigItem(img))
            for d in p.drawings:
                if d.kind == "hrule" and not _rect_covered(d.rect, suppress) and id(d) not in used_rules:
                    cx = (d.rect[0] + d.rect[2]) / 2
                    if zone_captures_x(z, cx) and z.bbox[1] - 2 <= d.rect[1] <= z.bbox[3] + 2:
                        used_rules.add(id(d))
                        items.append(_RuleItem(d))
            # splice table/math items that fall in this zone's vertical span
            for pi in list(extra_items):
                if z.bbox[1] - 2 <= pi.top <= z.bbox[3] + 2:
                    items.append(pi)
                    extra_items.remove(pi)
            zone_blocks = b.build_zone(p.number, items, z.bbox[0], z.bbox[2])
            for zb in zone_blocks:
                zb.cols = z.of_columns
            page_blocks.extend(zone_blocks)
        # any leftover tables/math (no matching zone) appended at the end
        for pi in extra_items:
            page_blocks.append(pi.block)
        # images no zone captured (e.g. in a margin) still belong to the page
        for img in p.images:
            if id(img) not in used_imgs:
                page_blocks.append(b._figure(p.number, img, col_left, col_right))
        page_blocks = _insert_notes(b, p.number, page_blocks, note_stacks.get(p.number, []),
                                    col_left, col_right)
        out.extend(page_blocks)
    _measured_spacing(out, b)
    return _join_across_pages(out)


class _PreItem:
    def __init__(self, block: Block):
        self.block = block
        self.top = block.bbox[1]
        self.kind = "pre"


def is_right_field(seg, n_segs: int, si: int, col_left: float, col_right: float) -> bool:
    """A short last field standing in the right part of the column (a date, marks, a page number)."""
    if si != n_segs - 1 or si == 0 or col_right <= col_left:
        return False
    W = col_right - col_left
    return len(seg.text.strip()) <= 24 and seg.x0 >= col_left + 0.6 * W


def hfill_run(like: Run) -> Run:
    return Run(**{**like.__dict__, "text": HFILL})


def _runs_spaced(row: TLine, col_left: float = 0.0, col_right: float = 0.0) -> List:
    """Row runs with a space at each segment (tab-gap) boundary, or \\hfill before a short field
    pushed to the right (so a CV entry keeps its date on the right)."""
    out: List[Run] = []
    n = len(row.segments)
    for si, seg in enumerate(row.segments):
        if si > 0 and seg.runs:
            if is_right_field(seg, n, si, col_left, col_right):
                out.append(hfill_run(seg.runs[0]))
            elif out and out[-1].text and not out[-1].text.endswith((" ", "\u00a0")):
                out[-1] = Run(**{**out[-1].__dict__, "text": out[-1].text + " "})
        out.extend(seg.runs)
    return out


_SECNUM = re.compile(r"(?:\d+\.)*\d+\.?|[A-Z]\.?|[IVX]+\.?")


def _split_number(seg: Segment) -> Optional[Tuple[Segment, Segment]]:
    """"2.2 Comparison of …" in one field → ("2.2", "Comparison of …"), splitting the runs."""
    text = seg.text
    m = re.match(r"^\s*((?:\d+\.)*\d+\.?|[A-Z]\.|[IVX]+\.)\s+\S", text)
    if not m:
        return None
    cut = m.end(1)
    head: List[Run] = []
    tail: List[Run] = []
    pos = 0
    for r in seg.runs:
        end = pos + len(r.text)
        if end <= cut:
            head.append(r)
        elif pos >= cut:
            tail.append(r)
        else:
            head.append(Run(**{**r.__dict__, "text": r.text[:cut - pos]}))
            tail.append(Run(**{**r.__dict__, "text": r.text[cut - pos:]}))
        pos = end
    if tail:
        tail[0] = Run(**{**tail[0].__dict__, "text": tail[0].text.lstrip()})
    if not head or not tail:
        return None
    frac = cut / max(1, len(text))
    xm = seg.x0 + frac * (seg.x1 - seg.x0)
    return Segment(runs=head, x0=seg.x0, x1=xm), Segment(runs=tail, x0=xm, x1=seg.x1)


def _rect_covered(r, boxes) -> bool:
    """A drawing (e.g. a table border) lying inside a table/math region belongs to it."""
    return any(x0 - 3 <= r[0] and r[2] <= x1 + 3 and y0 - 3 <= r[1] and r[3] <= y1 + 3
               for x0, y0, x1, y1 in boxes)


def _covered(row: TLine, boxes: List[Tuple[float, float, float, float]]) -> bool:
    cx = (row.x0 + row.x1) / 2
    cy = (row.top + row.bottom) / 2
    return any(x0 - 2 <= cx <= x1 + 2 and y0 - 2 <= cy <= y1 + 2 for x0, y0, x1, y1 in boxes)


# ---------------------------------------------------------------------------
# Side notes
# ---------------------------------------------------------------------------

def _note_paras(page: int, rows: List[TLine], left: float, right: float) -> List[Para]:
    """A callout's rows as paragraphs: a new paragraph starts at each "- " / "•" item."""
    groups: List[List[TLine]] = []
    for r in rows:
        if not groups or _marker(r.text) is not None:
            groups.append([r])
        else:
            groups[-1].append(r)
    return [Para(page=page, bbox=g[0].bbox, lines=g, align="left", left=left, right=right)
            for g in groups]


def _insert_notes(b: "_Builder", page: int, blocks: List[Block], stacks: List[List[TLine]],
                  col_left: float, col_right: float) -> List[Block]:
    """
    Anchor each side-note stack to the main-flow block it sits beside (the block whose span
    contains the note's top, else the next block below, else the last one) and insert the Note
    just before it. With no main-flow block on the page the note becomes ordinary paragraphs.
    """
    if not stacks:
        return blocks
    out = list(blocks)
    for rows in stacks:
        rows = sorted(rows, key=lambda r: r.baseline)
        top = min(r.top for r in rows)
        x0 = min(r.x0 for r in rows)
        x1 = max(r.x1 for r in rows)
        main = [blk for blk in out if blk.kind not in ("note", "pagemark")]
        paras = _note_paras(page, rows, x0, x1)
        if not main:
            out.extend(paras)
            continue
        anchor = next((m for m in main if m.bbox[1] - 1 <= top <= m.bbox[3] + 1), None) \
            or next((m for m in main if m.bbox[1] >= top), None) or main[-1]
        # The note's zero-height line sits above the anchor by TeX's interline glue (about a
        # quarter of the anchor's size), so the offset is measured from there.
        a_size = _block_text_size(anchor) or b.p.body_size
        note = Note(page=page, bbox=(x0, top, x1, max(r.bottom for r in rows)), id=b.nid(),
                    anchor=anchor.id, dx=round(x0 - col_left, 1),
                    dy=round(rows[0].baseline - anchor.bbox[1] + 0.26 * a_size, 1),
                    width=round(x1 - x0 + 4, 1), content=paras, anchor_top=anchor.bbox[1])
        out.insert(out.index(anchor), note)
    return out


def _block_text_size(blk) -> float:
    runs = []
    if isinstance(blk, Heading):
        runs = blk.runs
    elif isinstance(blk, Para):
        runs = [r for ln in blk.lines for r in ln.runs]
    w: Dict[float, int] = {}
    for r in runs:
        w[r.size] = w.get(r.size, 0) + len(r.text.strip())
    return max(w, key=w.get) if w else 0.0


def _build_box(b: "_Builder", page: int, spec: dict, rows: List[TLine], col_left: float,
               col_right: float) -> Optional[Box]:
    """A shaded box: its title bar's text as the title, the rows inside it as ordinary blocks."""
    bb = spec["bbox"]
    inside = [r for r in rows if _covered(r, [bb])]
    if not inside:
        return None
    tb = spec.get("title_bbox")
    title_rows = [r for r in inside if tb and _covered(r, [tb])]
    body_rows = [r for r in inside if r not in title_rows]
    content = b.build_zone(page, [_RowItem(r) for r in body_rows], bb[0] + 4, bb[2] - 4)
    title_runs: List[Run] = []
    for r in title_rows:
        title_runs.extend(_runs_spaced(r))
    W = max(1.0, col_right - col_left)
    return Box(page=page, bbox=bb, id=b.nid(), fill=spec["fill"], content=content,
               title_runs=title_runs, title_fill=spec.get("title_fill"),
               width_frac=round(min(1.0, (bb[2] - bb[0]) / W), 2))


# ---------------------------------------------------------------------------
# Flow across pages and measured spacing
# ---------------------------------------------------------------------------

def _last_para(b: Block) -> Optional[Para]:
    """The paragraph a following line would continue: the block itself, or a list's last item."""
    if isinstance(b, Para):
        return b
    if isinstance(b, ListBlock) and b.items and b.items[-1].body and isinstance(b.items[-1].body[-1], Para):
        return b.items[-1].body[-1]
    return None


def _join_across_pages(blocks: List[Block]) -> List[Block]:
    """
    A paragraph or list item broken by the page turn ("…modifications en-" / "gineered by …")
    is one paragraph: the next page's opening paragraph is folded back into it when it plainly
    continues — the previous line runs to the right edge or ends in a hyphen, and the next line
    starts in lower case or after that hyphen, without a first-line indent.
    """
    out: List[Block] = []
    for b in blocks:
        prev = next((x for x in reversed(out) if x.kind not in ("note", "pagemark")), None)
        if isinstance(b, Para) and prev is not None and prev.page != b.page and b.lines:
            tail = _last_para(prev)
            if tail is not None and tail.lines:
                last = tail.lines[-1]
                first = b.lines[0]
                text = first.text.lstrip()
                hyphen = last.text.rstrip().endswith("-")
                full = tail.right and last.x1 >= tail.right - 2.0 * last.size
                lower = bool(text) and text[0].islower()
                body_x = min((ln.x0 for ln in tail.lines[1:]), default=tail.lines[0].x0)
                no_indent = first.x0 <= body_x + 4
                same_size = abs(first.size - last.size) <= 0.6
                if same_size and no_indent and (hyphen or (full and lower)):
                    tail.lines.extend(b.lines)
                    continue
        out.append(b)
    return out


def _last_size(b: Block) -> float:
    p = _last_para(b)
    return p.lines[-1].size if p is not None and p.lines else 10.0


def _first_baseline(b: Block) -> Optional[float]:
    if isinstance(b, Para) and b.lines:
        return b.lines[0].baseline
    if isinstance(b, ListBlock) and b.items and b.items[0].body and getattr(b.items[0].body[0], "lines", None):
        return b.items[0].body[0].lines[0].baseline
    return None


def _last_baseline(b: Block) -> Optional[float]:
    p = _last_para(b)
    if p is not None and p.lines:
        return p.lines[-1].baseline
    return None


def _measured_spacing(blocks: List[Block], builder: "_Builder") -> None:
    """
    Space the PDF leaves between two blocks beyond what LaTeX puts there on its own (a gap before
    a signature block, around a centred title) becomes the block's space_before, which the emitter
    writes as a quantised \\vspace. Ordinary paragraph spacing (leading + parskip) and heading
    spacing (titlesec) add nothing.
    """
    prof = builder.p

    def stacked(a: Block, b: Block) -> bool:
        """b sits below a in the same column (not at the top of the next column)."""
        overlap = min(a.bbox[2], b.bbox[2]) - max(a.bbox[0], b.bbox[0])
        return b.bbox[1] >= a.bbox[3] - 2 and overlap > 0

    def gaps():
        for a, b in zip(blocks, blocks[1:]):
            if a.page != b.page or a.kind in ("note", "pagemark", "heading") or b.kind in ("note", "heading"):
                continue
            if not stacked(a, b):
                continue
            lead = builder._leading_for(getattr(b, "lines", [None])[0].size if isinstance(b, Para) and b.lines
                                        else prof.body_size)
            fb, lb = _first_baseline(b), _last_baseline(a)
            ps = prof.parskip or 0.0
            if fb is not None and lb is not None:
                yield a, b, (fb - lb) - (lead + ps), True
            elif fb is None and lb is not None and isinstance(b, Rule):
                # a rule under a line of text: a thin line of its own, one \baselineskip lower
                yield a, b, b.bbox[3] - (lb + lead + ps), False
            elif fb is None and lb is not None:
                # a picture under a line of text: LaTeX puts it \lineskip (1pt) below the line's
                # descenders
                yield a, b, b.bbox[1] - (lb + 0.22 * _last_size(a) + ps + 1.0), False
            elif fb is not None:
                # a line of text under a picture: one \baselineskip below the picture's bottom
                yield a, b, (fb - a.bbox[3]) - (lead + ps), False
            else:
                yield a, b, (b.bbox[1] - a.bbox[3]) - (ps + 1.0), False

    # A list's space above it is its topsep (LaTeX puts the same below it); a list whose space
    # isn't measurable here (it follows a heading or opens a page) takes the document's usual one.
    for _a, b, extra, exact in gaps():
        if isinstance(b, ListBlock) and exact:
            b.topsep = round(max(0.0, extra), 1)
    measured = sorted(x.topsep for x in blocks if isinstance(x, ListBlock) and x.topsep is not None)
    usual = measured[len(measured) // 2] if measured else 0.0
    for x in blocks:
        if isinstance(x, ListBlock) and x.topsep is None:
            x.topsep = usual
    for a, b, extra, _exact in gaps():
        if isinstance(b, ListBlock):
            continue
        if isinstance(a, ListBlock):
            extra -= a.topsep or 0.0
        pictures = (Figure, Math, Table, Rule)
        if isinstance(a, pictures) or isinstance(b, pictures):
            # the space around a picture is written exactly (as a float's \intextsep would be)
            if abs(extra) >= 2.0:
                b.space_before = round(extra, 1)
                b.space_exact = True
        elif extra >= max(6.0, 0.5 * builder._leading_for(prof.body_size)):
            b.space_before = round(extra, 1)
