"""
columns.py — Reading order, column zones, rows and segments.

This is the fix for the split-row problem: the extractor's own reading order (``Line.column`` from
the XY-cut) tears a visual row apart — a list marker from its text, a label from its definition, a
contents entry from its page number. Editable mode ignores ``Line.column`` entirely and rebuilds
the page: detect column zones geometrically, drop furniture, then group source lines into rows by
baseline and runs into segments by horizontal gap.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Optional, Set, Tuple

from ..fontmap import editable_font
from ..models import Line, PageExtract, Span
from .model import RGB, Run, Segment, TLine, Zone

# A span is math if its font name matches one of these, or it holds a private-use glyph.
_MATH_FONT_RE = re.compile(r"(cmmi|cmsy|cmex|cmbsy|msam|msbm|symbol|mathjax|stix|esint|rsfs|eufm|"
                           r"math|wasy)", re.IGNORECASE)


def _is_pua(text: str) -> bool:
    return any(0xE000 <= ord(c) <= 0xF8FF for c in text)


TAB_GAP = 1.5   # in ems: a wider horizontal gap between spans starts a new segment (field)


def is_math_span(sp: Span) -> bool:
    if _MATH_FONT_RE.search(sp.font or ""):
        return True
    if not _is_pua(sp.text):
        return False
    # private-use glyphs inside words are ligatures ("di\ue04ferent"), not maths
    letters = sum(c.isalpha() for c in sp.text if not (0xE000 <= ord(c) <= 0xF8FF))
    return letters < 0.5 * max(1, len(sp.text.strip()))


def rsz(v: float) -> float:
    """Round a size to the nearest 0.5 pt."""
    return round(v * 2) / 2.0


def to_run(sp: Span, color_override: Optional[RGB] = None, script: int = 0) -> Run:
    cls, family = editable_font(sp.font, sp.flags)
    return Run(text=sp.text, size=rsz(sp.size), family=family, font_cls=cls,
               bold=sp.bold, italic=sp.italic, color=color_override or sp.color,
               script=script, math=is_math_span(sp))


# ---------------------------------------------------------------------------
# Body column (document level)
# ---------------------------------------------------------------------------

def _char_weight(line: Line) -> int:
    return sum(len(s.text.strip()) for s in line.spans)


def dominant_size(lines: List[Line]) -> float:
    """Char-weighted modal size (rounded 0.5) across the given lines."""
    c: Counter = Counter()
    for ln in lines:
        for sp in ln.spans:
            n = len(sp.text.strip())
            if n:
                c[rsz(sp.size)] += n
    return c.most_common(1)[0][0] if c else 10.0


def body_size(pages: List[PageExtract]) -> float:
    return dominant_size([ln for p in pages for ln in p.lines])


def _mode_bin(values: List[float], weights: List[int], bin_pt: float = 1.0) -> float:
    """The weighted modal value, binned to ``bin_pt``; returns the mean of the winning bin."""
    if not values:
        return 0.0
    bins: Dict[int, float] = {}
    counts: Dict[int, int] = {}
    for v, w in zip(values, weights):
        b = int(round(v / bin_pt))
        bins[b] = bins.get(b, 0.0) + v * w
        counts[b] = counts.get(b, 0) + w
    best = max(counts, key=lambda k: counts[k])
    return bins[best] / counts[best]


def body_column(pages: List[PageExtract], furniture: Optional[Set[Tuple[int, int]]] = None,
                bsize: Optional[float] = None) -> Tuple[float, float]:
    """
    (left, right) x of the body text column. Left = modal x0 of body-size lines; right = modal x1
    of the lines that cluster near the widest right edge. Callouts and margin notes, which reach
    far past the body, do not move these because they are a minority of lines.
    """
    furniture = furniture or set()
    bsize = bsize if bsize is not None else body_size(pages)
    widths = [ln.bbox[2] - ln.bbox[0] for p in pages for ln in p.lines]
    widest = max(widths) if widths else 1.0
    lefts, lw, rights, rw = [], [], [], []
    for p in pages:
        for i, ln in enumerate(p.lines):
            if (p.number, i) in furniture or not ln.text.strip():
                continue
            w = ln.bbox[2] - ln.bbox[0]
            n = _char_weight(ln)
            if abs(dominant_size([ln]) - bsize) <= 0.6 and w >= 0.5 * widest:
                lefts.append(ln.bbox[0]); lw.append(n)
            if w >= 0.3 * widest:
                rights.append(ln.bbox[2]); rw.append(n)
    if not lefts:
        lefts, lw = [ln.bbox[0] for p in pages for ln in p.lines], [1] * sum(len(p.lines) for p in pages)
    col_left = _mode_bin(lefts, lw, 1.0) if lefts else 0.0
    # Right edge: the modal full-line x1 if a real cluster exists, else the 95th percentile.
    if rights:
        col_right = _mode_bin(rights, rw, 1.0)
        srt = sorted(rights)
        p95 = srt[min(len(srt) - 1, int(0.95 * len(srt)))]
        if col_right < p95 - 20:
            # the modal edge is an inner column's (two-column text): the page's right text edge
            # is the modal one among the lines reaching the far right
            near = [(r, w) for r, w in zip(rights, rw) if p95 - 20 <= r <= p95 + 1]
            col_right = _mode_bin([r for r, _ in near], [w for _, w in near], 1.0) if near else p95
    else:
        col_right = max((ln.bbox[2] for p in pages for ln in p.lines), default=0.0)
    return col_left, col_right


# ---------------------------------------------------------------------------
# Per-page column zones
# ---------------------------------------------------------------------------

def detect_zones(page: PageExtract, body_lines: List[Tuple[int, Line]], col_left: float,
                 col_right: float) -> List[Zone]:
    """
    Split the page into reading-order zones. A two-column band needs a gutter with ≥6 lines fully
    left and ≥6 fully right and ≤2 crossing it; a crossing row ends the band. Returns zones top to
    bottom; a two-column band yields its left zone then its right zone.
    """
    if not body_lines:
        return [Zone(page=page.number, bbox=(col_left, 0, col_right, page.height), of_columns=1)]
    W = col_right - col_left
    mid = (col_left + col_right) / 2.0
    # Candidate gutters near the page centre. A gutter needs ≥6 column-width lines entirely on each
    # side. Lines that cross it (a full-width title, abstract or footer) are allowed: the sweep
    # below turns them into full-width bands. A single-column page has no column-width lines
    # entirely in its right half, so it never qualifies.
    best = None
    for k in range(-6, 7):
        g = mid + k * 0.01 * W
        left = [ln for _, ln in body_lines if ln.bbox[2] <= g - 4 and (ln.bbox[2] - ln.bbox[0]) >= 0.3 * W]
        right = [ln for _, ln in body_lines if ln.bbox[0] >= g + 4 and (ln.bbox[2] - ln.bbox[0]) >= 0.3 * W]
        crossing = [ln for _, ln in body_lines if ln.bbox[0] < g - 4 and ln.bbox[2] > g + 4]
        if len(left) >= 6 and len(right) >= 6 and len(crossing) < 0.6 * (len(left) + len(right)):
            score = len(left) + len(right) - 2 * len(crossing)
            if best is None or score > best[0]:
                best = (score, g)
    if best is None:
        return [Zone(page=page.number, bbox=(col_left, 0, col_right, page.height), of_columns=1)]
    g = best[1]
    # Sweep rows top to bottom; a wide crossing row toggles back to a full-width band.
    ordered = sorted(body_lines, key=lambda t: t[1].baseline)
    zones: List[Zone] = []
    i = 0
    n = len(ordered)
    while i < n:
        ln = ordered[i][1]
        # column text never crosses the gutter, so anything straddling it is full width
        crosses = ln.bbox[0] < g - 4 and ln.bbox[2] > g + 4
        if crosses:
            zones.append(Zone(page=page.number, bbox=(col_left, ln.bbox[1], col_right, ln.bbox[3]),
                              of_columns=1))
            i += 1
            continue
        # gather a run of non-crossing rows as one two-column band
        j = i
        band = []
        while j < n:
            l2 = ordered[j][1]
            if l2.bbox[0] < g - 4 and l2.bbox[2] > g + 4:
                break
            band.append(ordered[j]); j += 1
        y0 = min(l[1].bbox[1] for l in band)
        y1 = max(l[1].bbox[3] for l in band)
        left_n = sum(1 for _, l in band if l.bbox[2] <= g)
        right_n = sum(1 for _, l in band if l.bbox[0] >= g)
        if left_n >= 3 and right_n >= 3:
            zones.append(Zone(page=page.number, bbox=(col_left, y0, g, y1), column=0, of_columns=2))
            zones.append(Zone(page=page.number, bbox=(g, y0, col_right, y1), column=1, of_columns=2))
        else:
            zones.append(Zone(page=page.number, bbox=(col_left, y0, col_right, y1), of_columns=1))
        i = j
    return zones


# ---------------------------------------------------------------------------
# Rows and segments
# ---------------------------------------------------------------------------

def zone_captures_x(z: Zone, cx: float) -> bool:
    """
    Horizontal membership. A zone's bbox x is its *text column* (alignment is judged against it),
    but it captures everything level with it: a single-column zone takes the whole width (row
    labels left of the column, marks or dates right of it stay in their row), and the two halves
    of a two-column band split at the gutter.
    """
    if z.of_columns == 1:
        return True
    return cx < z.bbox[2] if z.column == 0 else cx >= z.bbox[0]


def _line_in_zone(ln: Line, z: Zone) -> bool:
    cx = (ln.bbox[0] + ln.bbox[2]) / 2
    return z.bbox[1] - 1 <= ln.baseline <= z.bbox[3] + 1 and zone_captures_x(z, cx)


def split_side_notes(page: PageExtract, furniture: Set[Tuple[int, int]], col_left: float,
                     col_right: float, exclude_boxes=()) -> List[List[Tuple[int, Line]]]:
    """
    Side callouts that sit beside the text and cannot flow (a template's margin instructions):
    multi-word lines reaching past the right edge of the body column (or lying wholly left of it),
    stacked vertically. Returned as stacks; their lines are removed from the main flow.
    """
    W = max(1.0, col_right - col_left)
    cand = []
    for i, ln in enumerate(page.lines):
        if (page.number, i) in furniture or len(ln.text.split()) < 2:
            continue
        cx, cy = (ln.bbox[0] + ln.bbox[2]) / 2, (ln.bbox[1] + ln.bbox[3]) / 2
        if any(bx0 - 2 <= cx <= bx1 + 2 and by0 - 2 <= cy <= by1 + 2 for bx0, by0, bx1, by1 in exclude_boxes):
            continue   # part of a table or an equation, not a callout
        x0, _y0, x1, _y1 = ln.bbox
        right_side = x1 > col_right + 6 and x0 >= col_left + 0.35 * W
        left_side = x1 <= col_left - 4
        if right_side or left_side:
            cand.append((i, ln))
    cand.sort(key=lambda t: t[1].bbox[1])
    stacks: List[List[Tuple[int, Line]]] = []
    for i, ln in cand:
        sz = dominant_size([ln])
        if stacks:
            pi, pl = stacks[-1][-1]
            if ln.bbox[1] - pl.bbox[3] <= 1.2 * sz and abs(ln.bbox[0] - stacks[-1][0][1].bbox[0]) <= 25:
                stacks[-1].append((i, ln))
                continue
        stacks.append([(i, ln)])
    return _grow_stacks(page, stacks, furniture, exclude_boxes)


def _style(ln: Line) -> Tuple[float, Tuple[int, int, int]]:
    c: Counter = Counter()
    for sp in ln.spans:
        c[sp.color] += len(sp.text.strip())
    return dominant_size([ln]), (c.most_common(1)[0][0] if c else (0, 0, 0))


def _grow_stacks(page: PageExtract, stacks, furniture, exclude_boxes):
    """
    A callout's short last lines ("as such.", "no") don't reach past the column edge, so they are
    not candidates on their own. Absorb lines that continue a stack: same size and colour, aligned
    with or indented from the stack's left edge, and directly above/below or between its lines.
    Then merge stacks that touch.
    """
    taken = {i for st in stacks for i, _ in st}
    grew = True
    while grew:
        grew = False
        for st in stacks:
            sz, col = _style(st[0][1])
            x0 = min(l.bbox[0] for _, l in st)
            x1 = max(l.bbox[2] for _, l in st)
            top = min(l.bbox[1] for _, l in st)
            bot = max(l.bbox[3] for _, l in st)
            for i, ln in enumerate(page.lines):
                if i in taken or (page.number, i) in furniture or not ln.text.strip():
                    continue
                lsz, lcol = _style(ln)
                if abs(lsz - sz) > 0.6 or max(abs(a - b) for a, b in zip(lcol, col)) > 10:
                    continue
                if not (x0 - 3 <= ln.bbox[0] <= x1 - 4):
                    continue
                if not (top - 1.3 * sz <= ln.bbox[1] <= bot + 1.3 * sz):
                    continue
                st.append((i, ln))
                taken.add(i)
                grew = True
            st.sort(key=lambda t: t[1].bbox[1])
    stacks.sort(key=lambda st: st[0][1].bbox[1])
    merged: List[List[Tuple[int, Line]]] = []
    for st in stacks:
        if merged:
            prev = merged[-1]
            sz = dominant_size([st[0][1]])
            pbot = max(l.bbox[3] for _, l in prev)
            if st[0][1].bbox[1] - pbot <= 1.3 * sz and abs(st[0][1].bbox[0] - prev[0][1].bbox[0]) <= 25 \
                    and _style(st[0][1])[1] == _style(prev[0][1])[1]:
                prev.extend(st)
                continue
        merged.append(st)
    return merged


def _attach_drop_caps(lines: List[Tuple[int, Line]]) -> List[Tuple[int, Line]]:
    """
    A drop cap (one big initial spanning two or three lines) has the baseline of a lower line, so
    grouping by baseline would put "C" on the second line ("C tack tactics") and leave "YBER" on the
    first. Prefix the initial to the line whose top it shares, in that line's style ("CYBER").
    """
    if len(lines) < 2:
        return lines
    out = list(lines)
    for idx, ln in list(lines):
        t = ln.text.strip()
        if len(t) != 1 or not t.isalpha() or not t.isupper():
            continue
        size = max(sp.size for sp in ln.spans)
        # the lines beside the initial (its box includes the font's ascent, so test the line's
        # middle against the initial's span); the initial belongs to the topmost of them
        beside = []
        for j, other in out:
            if other is ln or not other.text.strip():
                continue
            osz = dominant_size([other])
            mid = (other.bbox[1] + other.bbox[3]) / 2
            if size >= 1.8 * osz and ln.bbox[1] <= mid <= ln.bbox[3] \
                    and 0 <= other.bbox[0] - ln.bbox[2] <= 1.5 * osz:
                beside.append((j, other))
        if not beside:
            continue
        target = min(beside, key=lambda t: t[1].bbox[1])
        j, other = target
        first = other.spans[0]
        cap = Span(text=t, font=first.font, size=first.size, color=first.color, flags=first.flags,
                   bbox=(ln.bbox[0], other.bbox[1], other.bbox[0], other.bbox[3]),
                   origin=(ln.bbox[0], other.baseline), force_bold=first.force_bold)
        merged = Line(spans=[cap] + list(other.spans), bbox=(ln.bbox[0], other.bbox[1], other.bbox[2],
                      other.bbox[3]), block=other.block, invisible=other.invisible, column=other.column)
        out = [(k, merged if l is other else l) for k, l in out if l is not ln]
    return out


def rows_in_zone(lines: List[Tuple[int, Line]]) -> List[TLine]:
    """Group source lines into visual rows by baseline, then build segments within each row."""
    if not lines:
        return []
    lines = _attach_drop_caps(lines)
    items = sorted(lines, key=lambda t: (t[1].baseline, t[1].bbox[0]))
    rows: List[List[Tuple[int, Line]]] = []
    for idx, ln in items:
        placed = False
        sz = dominant_size([ln])
        for row in rows:
            r_base = row[0][1].baseline
            r_sz = dominant_size([row[0][1]])
            small = min(sz, r_sz)
            if abs(ln.baseline - r_base) <= 0.35 * small:
                row.append((idx, ln)); placed = True; break
            # super/subscript: much smaller glyph overlapping the row vertically
            ov = min(ln.bbox[3], row[0][1].bbox[3]) - max(ln.bbox[1], row[0][1].bbox[1])
            if sz <= 0.8 * r_sz and ov >= 0.5 * (ln.bbox[3] - ln.bbox[1]):
                row.append((idx, ln)); placed = True; break
        if not placed:
            rows.append([(idx, ln)])
    out: List[TLine] = []
    for row in rows:
        out.append(_build_row(row))
    out.sort(key=lambda t: t.baseline)
    return out


def _build_row(row: List[Tuple[int, Line]]) -> TLine:
    base_sz = dominant_size([ln for _, ln in row])
    # The row's baseline is its main text's, not the lowest line's: a subscript ("δ" + "ij") sits
    # lower, and taking the maximum would turn the main text into a "superscript".
    main = [ln for _, ln in row if abs(dominant_size([ln]) - base_sz) <= 0.6] or [ln for _, ln in row]
    base = max(main, key=_char_weight).baseline
    # collect (span, baseline) sorted by x
    pieces: List[Tuple[Span, float]] = []
    for _, ln in row:
        for sp in ln.spans:
            if sp.text:
                for piece in _explode(sp):
                    pieces.append((piece, ln.baseline))
    pieces.sort(key=lambda t: t[0].origin[0])
    segments = _segments(pieces, base_sz, base)
    xs0 = min(ln.bbox[0] for _, ln in row)
    xs1 = max(ln.bbox[2] for _, ln in row)
    top = min(ln.bbox[1] for _, ln in row)
    bot = max(ln.bbox[3] for _, ln in row)
    return TLine(segments=segments, x0=xs0, x1=xs1, top=top, bottom=bot, baseline=base,
                 page=0, size=base_sz, src=[idx for idx, _ in row])


_SPACE_RUN = re.compile(r"\t+| {3,}")


def _explode(sp: Span) -> List[Span]:
    """
    A span as positioned pieces. Word documents indent and tabulate with spaces inside one span
    ("            (include tabular form)", "2.2       Comparison"): the bbox then starts at the
    spaces, not at the text. Leading/trailing spaces move the piece's edges in, and a run of ≥3
    spaces or a tab splits the span into separate fields. Positions inside a span are estimated
    in proportion to the characters (spaces counted at a quarter em).
    """
    text = sp.text
    if not text.strip():
        return [sp]
    w = sp.bbox[2] - sp.bbox[0]
    space = 0.25 * sp.size
    n_sp = text.count(" ") + text.count("\t")
    n_ch = max(1, len(text) - n_sp)
    ch_w = max(0.1, (w - n_sp * space) / n_ch)

    def width(t: str) -> float:
        k = t.count(" ") + t.count("\t")
        return k * space + (len(t) - k) * ch_w

    parts = []
    pos = 0
    for m in _SPACE_RUN.finditer(text):
        if m.start() > pos:
            parts.append((pos, text[pos:m.start()]))
        pos = m.end()
    if pos < len(text):
        parts.append((pos, text[pos:]))
    out: List[Span] = []
    for start, piece in parts:
        lead = len(piece) - len(piece.lstrip())
        core = piece.strip()
        if not core:
            continue
        x0 = sp.bbox[0] + width(text[:start]) + lead * space
        x1 = min(sp.bbox[2], x0 + width(core))
        out.append(Span(text=core + (" " if piece.endswith(" ") else ""), font=sp.font, size=sp.size,
                        color=sp.color, flags=sp.flags, bbox=(x0, sp.bbox[1], x1, sp.bbox[3]),
                        origin=(x0, sp.origin[1]), force_bold=sp.force_bold))
    return out or [sp]


def _segments(pieces: List[Tuple[Span, float]], base_sz: float, base: float) -> List[Segment]:
    """
    Split a row's spans into segments at tab-size gaps (≥TAB_GAP·size), inserting a space where the
    PDF left a word gap (≥0.15·size) that neither side already carries. PyMuPDF splits spans only at
    style changes, so gaps between spans inside justified text stay well under one em; a gap of
    1.5 em is a column boundary (a symbols list, a label/value table, a date pushed right). A super/subscript is tagged by
    its baseline offset from the row baseline.
    """
    segs: List[Segment] = []
    cur: List[Run] = []
    cur_x0 = cur_x1 = 0.0
    prev_end: Optional[float] = None
    for sp, sp_base in pieces:
        script = 0
        if sp_base < base - 0.2 * base_sz:
            script = 1
        elif sp_base > base + 0.1 * base_sz:
            script = -1
        x0, x1 = sp.bbox[0], sp.bbox[2]
        gap = (x0 - prev_end) if prev_end is not None else 0.0
        if prev_end is not None and gap > TAB_GAP * base_sz and cur:
            segs.append(Segment(runs=_merge_runs(cur), x0=cur_x0, x1=cur_x1))
            cur = []
        text = sp.text
        if cur and prev_end is not None and 0.15 * base_sz <= gap <= TAB_GAP * base_sz \
                and not cur[-1].text.endswith((" ", " ")) and not text.startswith((" ", " ")):
            text = " " + text
        run = to_run(sp, script=script)
        run.text = text
        if not cur:
            cur_x0 = x0
        cur.append(run)
        cur_x1 = x1
        prev_end = x1
    if cur:
        segs.append(Segment(runs=_merge_runs(cur), x0=cur_x0, x1=cur_x1))
    return segs


def _same_style(a: Run, b: Run) -> bool:
    return a.style_key() == b.style_key() and a.font_cls == b.font_cls


def _merge_runs(runs: List[Run]) -> List[Run]:
    """Merge adjacent runs that share a style."""
    out: List[Run] = []
    for r in runs:
        if out and _same_style(out[-1], r):
            out[-1] = Run(**{**out[-1].__dict__, "text": out[-1].text + r.text})
        else:
            out.append(r)
    return out


def page_zones_and_rows(page: PageExtract, furniture: Set[Tuple[int, int]], col_left: float,
                        col_right: float) -> List[Tuple[Zone, List[TLine]]]:
    """Full per-page pipeline: zones in reading order, each with its rebuilt rows."""
    body = [(i, ln) for i, ln in enumerate(page.lines)
            if (page.number, i) not in furniture and ln.text.strip()]
    zones = detect_zones(page, body, col_left, col_right)
    assigned: Set[int] = set()
    result: List[Tuple[Zone, List[TLine]]] = []
    for z in zones:
        in_zone = [(i, ln) for i, ln in body if i not in assigned and _line_in_zone(ln, z)]
        for i, _ in in_zone:
            assigned.add(i)
        rows = rows_in_zone(in_zone)
        for r in rows:
            r.page = page.number
        result.append((z, rows))
    # any unassigned lines (odd positions) go into a trailing zone
    leftover = [(i, ln) for i, ln in body if i not in assigned]
    if leftover:
        z = Zone(page=page.number, bbox=(col_left, 0, col_right, page.height), of_columns=1)
        rows = rows_in_zone(leftover)
        for r in rows:
            r.page = page.number
        result.append((z, rows))
    return result
