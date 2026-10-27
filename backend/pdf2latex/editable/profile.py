"""
profile.py — The document's style, measured from the rebuilt rows.

Pure and deterministic: body font/size/colour, leading, paragraph spacing, margins from the body
column (not the content extents), a size ladder mapping measured sizes to LaTeX size commands, a
readable colour palette, and the heading levels. Everything a student would edit once to restyle
the whole document.
"""

from __future__ import annotations

import colorsys
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

from ..models import PageExtract
from .columns import body_size, dominant_size
from .model import RGB, EditProfile, TLine

# Natural LaTeX \baselineskip for the standard class sizes.
_NATURAL_LEAD = {10.0: 12.0, 11.0: 13.6, 12.0: 14.5}
# Standard size commands and their pt for each base class.
_SIZE_TABLE = {
    10.0: [("\\tiny", 5), ("\\scriptsize", 7), ("\\footnotesize", 8), ("\\small", 9),
           ("\\normalsize", 10), ("\\large", 12), ("\\Large", 14.4), ("\\LARGE", 17.28),
           ("\\huge", 20.74), ("\\Huge", 24.88)],
    11.0: [("\\tiny", 6), ("\\scriptsize", 8), ("\\footnotesize", 9), ("\\small", 10),
           ("\\normalsize", 11), ("\\large", 12), ("\\Large", 14.4), ("\\LARGE", 17.28),
           ("\\huge", 20.74), ("\\Huge", 24.88)],
    12.0: [("\\tiny", 6), ("\\scriptsize", 8), ("\\footnotesize", 10), ("\\small", 11),
           ("\\normalsize", 12), ("\\large", 14.4), ("\\Large", 17.28), ("\\LARGE", 20.74),
           ("\\huge", 24.88), ("\\Huge", 24.88)],
}

# \baselineskip of each standard size command (size10/11/12.clo), pt
_BASELINESKIP = {
    10.0: {"\\tiny": 6, "\\scriptsize": 8, "\\footnotesize": 9.5, "\\small": 11, "\\normalsize": 12,
           "\\large": 14, "\\Large": 18, "\\LARGE": 22, "\\huge": 25, "\\Huge": 30},
    11.0: {"\\tiny": 7, "\\scriptsize": 9.5, "\\footnotesize": 11, "\\small": 12, "\\normalsize": 13.6,
           "\\large": 14, "\\Large": 18, "\\LARGE": 22, "\\huge": 25, "\\Huge": 30},
    12.0: {"\\tiny": 7, "\\scriptsize": 9.5, "\\footnotesize": 12, "\\small": 13.6, "\\normalsize": 14.5,
           "\\large": 18, "\\Large": 22, "\\LARGE": 25, "\\huge": 30, "\\Huge": 30},
}


def class_size(body_size: float) -> float:
    """The document class option (10/11/12pt) closest to the body size."""
    return min((10.0, 11.0, 12.0), key=lambda c: abs(c - body_size))


def tex_baselineskip(profile, size: float) -> float:
    """The \\baselineskip LaTeX gives a paragraph set at this PDF size through its size command
    (before any \\setstretch): the standard value, or 1.2× for a size redefined in the preamble."""
    cmd = profile.size_cmds.get(round(size * 2) / 2, "\\normalsize")
    redef = dict(profile.size_redefs).get(cmd)
    if redef is not None:
        return 1.2 * redef
    return float(_BASELINESKIP[class_size(profile.body_size)].get(cmd, 1.2 * size))


# ---------------------------------------------------------------------------
# Colour naming
# ---------------------------------------------------------------------------

_HUE_NAMES = [(15, "Red"), (45, "Orange"), (70, "Yellow"), (160, "Green"), (200, "Teal"),
              (255, "Blue"), (290, "Purple"), (330, "Magenta"), (360, "Red")]


def _hue_name(rgb: RGB) -> str:
    r, g, b = (v / 255.0 for v in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if s < 0.12:
        if v > 0.93:
            return "obWhite"
        if v < 0.10:
            return "obBlack"
        return "obGray%02d" % int(round(v * 100))
    deg = h * 360
    base = next(name for lim, name in _HUE_NAMES if deg <= lim)
    prefix = "Dark" if v < 0.55 else ("Light" if (v > 0.9 and s < 0.5) else "")
    return "ob" + prefix + base


def name_colors(rgbs: List[RGB]) -> List[Tuple[str, RGB]]:
    """Readable, collision-free names, keeping the input (use-ordered) order."""
    out: List[Tuple[str, RGB]] = []
    used: Dict[str, int] = {}
    for rgb in rgbs:
        base = _hue_name(rgb)
        if base not in used:
            used[base] = 1
            out.append((base, rgb))
        else:
            used[base] += 1
            out.append((base + chr(ord("A") + used[base] - 2), rgb))
    return out


# ---------------------------------------------------------------------------
# Row helpers
# ---------------------------------------------------------------------------

def row_family(row: TLine) -> str:
    c: Counter = Counter()
    for r in row.runs:
        c[r.family] += len(r.text.strip())
    return c.most_common(1)[0][0] if c else "serif"


def row_bold(row: TLine) -> bool:
    runs = [r for r in row.runs if r.text.strip()]
    return bool(runs) and all(r.bold for r in runs)


def row_mostly_bold(row: TLine) -> bool:
    """Bold by character share (≥60%): a bold entry title with a plain date is still a bold heading."""
    total = sum(len(r.text.strip()) for r in row.runs)
    bold = sum(len(r.text.strip()) for r in row.runs if r.bold)
    return total > 0 and bold / total >= 0.6


def row_size(row: TLine) -> float:
    """Character-weighted dominant run size."""
    c: Counter = Counter()
    for r in row.runs:
        c[r.size] += len(r.text.strip())
    return c.most_common(1)[0][0] if c else row.size


def row_italic(row: TLine) -> bool:
    runs = [r for r in row.runs if r.text.strip()]
    return bool(runs) and all(r.italic for r in runs)


def row_color(row: TLine) -> RGB:
    c: Counter = Counter()
    for r in row.runs:
        c[r.color] += len(r.text.strip())
    return c.most_common(1)[0][0] if c else (0, 0, 0)


def row_align(row: TLine, col_left: float, col_right: float, page_w: float = 0.0) -> str:
    """left | center | right. Centred means on the text column's centre, or — on a title page or
    title slide laid out on the whole page — on the page's centre."""
    center = (row.x0 + row.x1) / 2
    col_center = (col_left + col_right) / 2
    if abs(center - col_center) <= 4 and row.x0 > col_left + 6:
        return "center"
    if page_w and abs(center - page_w / 2) <= 4 and (row.x1 - row.x0) < 0.9 * page_w:
        return "center"
    if row.x1 >= col_right - 3 and row.x0 > col_left + 6:
        return "right"
    return "left"


def key_align(row: TLine, col_left: float, col_right: float, page_w: float = 0.0) -> Optional[str]:
    """A heading row's alignment for style matching: center | left | right, or None for a row that
    runs the column's full width (as much centred as flush left)."""
    if row.x0 <= col_left + 6 and row.x1 >= col_right - 6:
        return None
    return row_align(row, col_left, col_right, page_w)


def is_upper(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 4 and sum(c.isupper() for c in letters) / len(letters) >= 0.8


def heading_candidate(row: TLine, body: float) -> bool:
    """
    Whether a row may be a heading. A heading is genuinely larger than the body, an uppercase banner
    (bold or larger), or a short bold standalone line. Body-size "Label: value" lines and rows split
    by tab gaps into several fields (a CV's "Title | 2024", a form's "Course Code: CET362") are
    emphasis or data, not headings.
    """
    text = row.text.strip()
    words = len(text.split())
    if words == 0 or words > 20 or len(text) > 120:
        return False
    big = row.size >= body + 1
    if big:
        return True
    bold = row_bold(row)
    upper = is_upper(text)
    if upper and bold:
        return True
    labelled = re.search(r":\s*\S", text) is not None
    return (bold and words <= 8 and len(row.segments) == 1 and not labelled
            and not text.endswith((".", ",", ";")))


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

def _paper(w: float, h: float) -> Tuple[str, Tuple[float, float]]:
    if abs(w - 612) <= 2 and abs(h - 792) <= 2:
        return "letterpaper", (612.0, 792.0)
    if abs(w - 595) <= 2 and abs(h - 842) <= 2:
        return "a4paper", (595.28, 841.89)
    return f"custom:{w:.0f}x{h:.0f}", (w, h)


def _base_class(body: float) -> float:
    return min((10.0, 11.0, 12.0), key=lambda c: abs(c - body))


def _size_ladder(sizes: List[float], base: float) -> Tuple[Dict[float, str], List[Tuple[str, float]]]:
    """
    Map each used size to a LaTeX size command. The body size is \\normalsize and is never
    redefined; near-body sizes (±0.75pt rounding noise) also use it. Sizes within 0.6pt of each other
    are one size measured twice (13.9 and 14.3) and share a command. Each other size takes the
    nearest free standard command (redefined in the preamble when its standard pt is off by >0.4);
    when a document uses more sizes than LaTeX has names for, further sizes get commands of their
    own (\\obsizeA, \\obsizeB …) rather than two sizes sharing one.
    """
    table = [t for t in _SIZE_TABLE[base] if t[0] != "\\normalsize"]
    smaller = [t for t in table if t[1] < base]
    larger = [t for t in table if t[1] > base]
    cmds: Dict[float, str] = {}
    redefs: Dict[str, float] = {}
    used: Dict[str, float] = {}
    extra = iter("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    def assign(sz: float) -> str:
        if abs(sz - base) <= 0.75:
            return "\\normalsize"
        pool = smaller if sz < base else larger
        for cmd, pt in sorted(pool, key=lambda t: (abs(t[1] - sz), t[1])):
            if used.get(cmd) in (None, sz):
                used[cmd] = sz
                if abs(pt - sz) > 0.4:
                    redefs[cmd] = sz
                return cmd
        cmd = "\\obsize" + next(extra)
        used[cmd] = sz
        redefs[cmd] = sz
        return cmd

    clusters: List[List[float]] = []
    for sz in sorted(set(sizes)):
        # sizes are already rounded to 0.5pt: two of them are two sizes (a 16.8pt title is not the
        # 17.3pt one beside it; set at 17.5 it wraps where the PDF's does not)
        if clusters and sz - clusters[-1][0] <= 0.25 and \
                (abs(sz - base) <= 0.75) == (abs(clusters[-1][0] - base) <= 0.75):
            clusters[-1].append(sz)
        else:
            clusters.append([sz])
    for cl in clusters:
        rep = cl[len(cl) // 2]
        cmd = assign(rep)
        for sz in cl:
            cmds[sz] = cmd
    return cmds, list(redefs.items())


def build_profile(pages: List[PageExtract], page_rows: Dict[int, List[TLine]],
                  col_left: float, col_right: float) -> EditProfile:
    body = body_size(pages)
    base = _base_class(body)
    all_rows = [r for p in pages for r in page_rows.get(p.number, [])]

    # body font class/family/colour from body-size runs
    cls_c: Counter = Counter()
    fam_c: Counter = Counter()
    col_c: Counter = Counter()
    for r in all_rows:
        if abs(r.size - body) > 0.6:
            continue
        for run in r.runs:
            n = len(run.text.strip())
            if n:
                cls_c[run.font_cls] += n
                fam_c[run.family] += n
                col_c[run.color] += n
    body_cls = cls_c.most_common(1)[0][0] if cls_c else "times"
    body_font = _body_font_name(pages, body)
    body_family = fam_c.most_common(1)[0][0] if fam_c else "serif"
    body_color = col_c.most_common(1)[0][0] if col_c else (0, 0, 0)

    # leading: median baseline gap between consecutive body rows on a page
    # Rows arrive in reading order (zone by zone), so consecutive rows are neighbours in the same
    # column. Sorting a two-column page by baseline would interleave the columns and make every
    # gap look tiny.
    gaps = []
    for p in pages:
        rows = page_rows.get(p.number, [])
        for a, b in zip(rows, rows[1:]):
            if abs(a.size - body) <= 0.6 and abs(b.size - body) <= 0.6:
                g = b.baseline - a.baseline
                if 0 < g <= 2.2 * body:
                    gaps.append(g)
    leading = _median(gaps) if gaps else _NATURAL_LEAD.get(base, 1.2 * base)
    natural = _NATURAL_LEAD.get(base, 1.2 * base)
    stretch = leading / natural if natural else 1.0

    # leading per size class: consecutive same-size rows in reading order, tight enough to be lines
    # of one paragraph (≤ 1.6 × size)
    by_size: Dict[float, List[float]] = {}
    for p in pages:
        rows = page_rows.get(p.number, [])
        for a, b in zip(rows, rows[1:]):
            if abs(a.size - b.size) <= 0.25:
                g = b.baseline - a.baseline
                if 0.9 * a.size < g <= 1.6 * a.size or (abs(a.size - body) <= 0.6 and 0 < g <= 2.2 * body):
                    by_size.setdefault(a.size, []).append(g)
    leading_by_size = {sz: _median(gs) for sz, gs in by_size.items() if len(gs) >= 3}
    leading_by_size[body] = leading

    # parskip / parindent. The measured paragraph gap is capped at ~0.7×leading so a loosely-set
    # source (big inter-paragraph space) doesn't inflate the reflowed page count.
    starts = _paragraph_starts(pages, page_rows, body, leading, col_left, col_right)
    gaps = [g for g, _ind in starts]
    measured_parskip = _median(gaps) if gaps else 0.0
    parskip = max(0.0, round(min(measured_parskip, 0.7 * leading)))
    indents = [ind for _g, ind in starts if 4 < ind < 48]
    # paragraphs marked by a first-line indent: most paragraph starts are indented
    parindent = round(_median(indents), 1) if starts and len(indents) >= 0.5 * len(starts) else 0.0

    # margins from the body column
    w, h = pages[0].width, pages[0].height
    paper, paper_pt = _paper(w, h)
    top = _mode([min((r.top for r in page_rows.get(p.number, [])), default=72) for p in pages], 1) or 72
    bottoms = [max((r.bottom for r in page_rows.get(p.number, [])), default=h - 72) for p in pages]
    bottoms.sort(reverse=True)
    bottom_edge = _mode(bottoms[:max(1, len(bottoms) // 3)], 2) or (h - 72)
    # LaTeX places a page's first baseline \topskip below the text area's top and stops a page
    # when the next baseline would pass its bottom; measured on baselines, the text area holds
    # exactly as many lines per page as the PDF's
    area = _text_area(pages, page_rows, body, leading, col_right, _base_class(body))
    if area is not None:
        top, bottom_edge = area
    # against the paper the output is set on (a browser-printed "A4" may be 596bp wide): the text
    # column keeps the PDF's exact width, which is what decides the line breaks
    pw, ph = paper_pt if paper_pt else (w, h)
    margins = {"left": max(18.0, col_left), "right": max(18.0, pw - col_right),
               "top": max(18.0, top), "bottom": max(18.0, ph - bottom_edge)}

    # colours
    palette = name_colors(_ordered_colors(pages))

    # size ladder
    sizes_used = sorted({r.size for r in all_rows if r.size > 0})
    size_cmds, size_redefs = _size_ladder(sizes_used, base)

    # heading levels
    heading_levels, has_chapters = _heading_levels(pages, page_rows, body, col_left, col_right)

    return EditProfile(
        body_cls=body_cls, body_family=body_family, body_size=body, body_color=body_color,
        leading=leading, line_stretch=stretch, parskip=parskip, parindent=parindent,
        margins=margins, paper=paper, paper_pt=paper_pt, colors=palette,
        size_cmds=size_cmds, size_redefs=size_redefs, heading_levels=heading_levels,
        has_chapters=has_chapters, leading_by_size=leading_by_size, body_font=body_font,
    )


def _ordered_colors(pages: List[PageExtract]) -> List[RGB]:
    c: Counter = Counter()
    for p in pages:
        for ln in p.lines:
            for sp in ln.spans:
                c[sp.color] += max(1, len(sp.text.strip()))
    c[(0, 0, 0)] += 0
    return [rgb for rgb, _ in c.most_common()]


def _body_font_name(pages, body: float) -> str:
    """The family name of the font most body-size text is set in ("TeXGyreTermes" from
    "ABCDEF+TeXGyreTermes-Regular")."""
    c: Counter = Counter()
    for p in pages:
        for ln in p.lines:
            for sp in ln.spans:
                if abs(sp.size - body) <= 0.75 and sp.text.strip():
                    name = re.sub(r"^[A-Z]{6}\+", "", sp.font or "")
                    name = name.split("\u00e5\u00bc\u00ab")[-1]      # cairo's "ABC+DEF\u00e5\u00bc\u00abName"
                    c[re.split(r"[-,]", name)[0]] += len(sp.text.strip())
    return c.most_common(1)[0][0] if c else ""


def _text_area(pages, page_rows, body, leading, col_right, topskip) -> Optional[Tuple[float, float]]:
    """
    (top, bottom) of the text area, from baselines. Top: the usual first body baseline less
    \\topskip. Bottom: between the lowest last baseline on any page (it fit) and, on pages whose
    text runs on to the next page, the baseline one line lower (it did not fit). None when the
    pages carry too little body text to tell.
    """
    firsts, lasts, misses = [], [], []
    for i, p in enumerate(pages):
        rows = [r for r in page_rows.get(p.number, []) if r.text.strip()]
        if not rows:
            continue
        r0 = min(rows, key=lambda r: r.baseline)
        if abs(r0.size - body) <= 0.75:
            firsts.append(r0.baseline)
        body_rows = [r for r in rows if abs(r.size - body) <= 0.75]
        if not body_rows:
            continue
        last = max(body_rows, key=lambda r: r.baseline)
        if last.baseline < max(r.baseline for r in rows) - 0.5:
            continue                       # something else (a figure caption, a table) ends the page
        lasts.append(last.baseline)
        if i + 1 < len(pages) and last.x1 >= col_right - 2:
            misses.append(last.baseline + leading)     # a paragraph broken by the page turn
    if len(firsts) < 2 or len(lasts) < 2:
        return None
    firsts.sort()
    top_base = _median([f for f in firsts if abs(f - _median(firsts)) <= 2.0])
    lasts.sort()
    lo = lasts[-1]
    if len(lasts) >= 3 and lasts[-1] - lasts[-2] > 0.5 * leading:
        lo = lasts[-2]                     # one page running lower than all others is not the rule
    hi = min((m for m in misses if m > lo + 0.5), default=lo + 0.5 * leading)
    bottom = min((lo + hi) / 2, lo + 0.5 * leading)
    return top_base - topskip, bottom


def _paragraph_starts(pages, page_rows, body, leading, col_left, col_right) -> List[Tuple[float, float]]:
    """
    (extra gap above, first-line indent) for each paragraph start in the body text: a body-size row
    following a body-size row that ended short of the right edge (the previous paragraph's last
    line). Measured this way, a document that separates paragraphs by a first-line indent alone
    reads as parskip ≈ 0 with an indent, not as a big skip.
    """
    out = []
    for p in pages:
        rows = page_rows.get(p.number, [])   # reading order, see build_profile
        for a, b in zip(rows, rows[1:]):
            if abs(a.size - body) > 0.6 or abs(b.size - body) > 0.6:
                continue
            # a body-size bold heading line ("1.4 SCOPE") is followed by its section's space, not
            # by the space between two paragraphs
            if heading_candidate(a, body) or heading_candidate(b, body):
                continue
            g = b.baseline - a.baseline
            if not (0 < g <= 2.5 * leading):
                continue
            short = a.x1 < col_right - 2.0 * body
            if short and (b.x0 - col_left) < 60:
                out.append((max(0.0, g - leading), b.x0 - col_left))
    return out


def _heading_levels(pages, page_rows, body, col_left, col_right):
    """Cluster heading-candidate rows by style key, order by prominence, assign levels 0..3."""
    cand: List[Tuple[Tuple, bool, int]] = []   # (style_key, starts_page, page)
    for p in pages:
        rows = sorted(page_rows.get(p.number, []), key=lambda r: r.baseline)
        for idx, r in enumerate(rows):
            if not heading_candidate(r, body):
                continue
            bold = row_mostly_bold(r)
            upper = is_upper(r.text)
            key = (round(r.size), bold, row_italic(r), row_family(r),
                   key_align(r, col_left, col_right, p.width), upper)
            # a heading broken over several lines (a long title, its second line centred under
            # the title text rather than the column) counts once
            prev_key = cand[-1][0] if cand and cand[-1][2] == p.number else None
            if prev_key is not None and prev_key[:4] == key[:4] and prev_key[5] == key[5] \
                    and idx > 0 and rows[idx - 1].text.strip() \
                    and 0 < r.baseline - rows[idx - 1].baseline <= 1.6 * r.size:
                continue
            cand.append((key, idx == 0, p.number))
    if not cand:
        return [], False
    # a full-width row is as much centred as flush left: it takes the alignment of the same style
    # set elsewhere (centred first)
    known = {k for k, _s, _p in cand if k[4] is not None}
    resolved = []
    for k, sp, pg in cand:
        if k[4] is None:
            alt = [a for a in ("center", "left", "right") if (k[:4] + (a,) + k[5:]) in known]
            k = k[:4] + ((alt[0] if alt else "left"),) + k[5:]
        resolved.append((k, sp, pg))
    cand = resolved
    counts: Counter = Counter(k for k, _s, _p in cand)
    key_pages: Dict[Tuple, set] = {}
    for k, _s, pg in cand:
        key_pages.setdefault(k, set()).add(pg)
    starts: Dict[Tuple, int] = {}
    for k, sp, _pg in cand:
        starts[k] = starts.get(k, 0) + (1 if sp else 0)
    # Levels come from styles that recur. A one-off large line (a title-page line, a cover heading)
    # still becomes a heading — match_level maps it to the nearest level — but it must not take a
    # level slot and push the document's real chapter/section styles out.
    # A level recurs on two pages that carry running text: a style used only on display pages
    # (the centred lines of a title page or two) is their design, not a level of the document's
    # structure. Running text is lines across the column (a paragraph's, a contents line with its
    # leaders); documents with little of it (slides, a résumé) count every page.
    width = max(1.0, col_right - col_left)
    prose = {p.number for p in pages
             if sum(1 for r in page_rows.get(p.number, [])
                    if r.x0 <= col_left + 6 and r.x1 >= col_right - 6 and r.x1 - r.x0 >= 0.85 * width) >= 2}
    if len(prose) < 3:
        prose = {p.number for p in pages}
    recurring = [k for k in counts if counts[k] >= 2 and len(key_pages[k] & prose) >= 2]
    pool = recurring or list(counts)
    keys = sorted(pool, key=lambda k: (-k[0], not k[1], k[4] != "center", not k[5], -counts[k]))
    levels: List[Dict] = []
    start_level = 0
    top_key = keys[0]
    # A chapter-like level 0 needs a genuinely larger heading (≥ body+2), not merely a bold or
    # centred body-size line (e.g. "PART A" on a question paper), and most of its instances must
    # open a page or be centred. Otherwise the document is article-class and starts at level 1.
    # chapters recur through the document: the top style must head ≥2 different pages (a title
    # set large on page 1 only is a title, not a chapter)
    top_is_chapter = (top_key[0] >= body + 2 and counts[top_key] >= 2
                      and len(key_pages.get(top_key, ())) >= 2 and
                      (starts.get(top_key, 0) >= 0.5 * counts[top_key] or top_key[4] == "center"))
    if not top_is_chapter:
        start_level = 1
    for i, k in enumerate(keys[:4]):
        levels.append({
            "level": start_level + i, "size": k[0], "bold": k[1], "italic": k[2],
            "family": k[3], "align": k[4], "upper": k[5], "count": counts[k],
        })
    has_chapters = any(lv["level"] == 0 for lv in levels)
    return levels, has_chapters


def match_level(profile: EditProfile, row: TLine, col_left: float, col_right: float) -> Optional[Dict]:
    """
    The heading level a row is set in, or None if it is not a heading. A row matches the level whose
    style is nearest (size, then weight, alignment, capitals) — but only a level whose weight and
    alignment it shares and whose size it has (±1pt), and not a capitals level for a mixed-case
    line: a bold line in no recurring heading style (a signature under a letter, a one-off 20pt
    "CERTIFICATE", a centred college name) is a styled paragraph, which keeps its measured spacing.
    """
    if not profile.heading_levels or not heading_candidate(row, profile.body_size):
        return None
    bold = row_mostly_bold(row)
    page_w = profile.paper_pt[0] if profile.paper_pt else 0.0
    align = key_align(row, col_left, col_right, page_w)
    upper = is_upper(row.text)
    best = None
    best_d = 1e9
    for lv in profile.heading_levels:
        if lv["bold"] != bold or (align is not None and lv["align"] != align):
            continue
        if abs(lv["size"] - row.size) > max(1.0, 0.08 * lv["size"]):
            continue
        if lv.get("upper") and not upper:
            continue          # a level set in capitals: a mixed-case line is another style
        d = abs(lv["size"] - row.size) + (0 if lv.get("upper", upper) == upper else 0.5)
        if d < best_d:
            best_d = d
            best = lv
    return best


# ---------------------------------------------------------------------------
# small stats
# ---------------------------------------------------------------------------

def _median(xs: List[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _mode(xs: List[float], bin_pt: int) -> float:
    if not xs:
        return 0.0
    c: Counter = Counter(int(round(x / bin_pt)) * bin_pt for x in xs)
    return float(c.most_common(1)[0][0])


def two_column_layout(profile: EditProfile, page_layout) -> None:
    """A two-column document: two-column bands on at least 60% of the pages that carry text. The
    gap between the columns is measured (right column's left edge less left column's right edge)."""
    text_pages = 0
    two = 0
    seps: List[float] = []
    for pno, layout in page_layout.items():
        if not any(rows for _z, rows in layout):
            continue
        text_pages += 1
        lefts = [(z, rows) for z, rows in layout if z.of_columns == 2 and z.column == 0 and rows]
        rights = [(z, rows) for z, rows in layout if z.of_columns == 2 and z.column == 1 and rows]
        if lefts and rights:
            two += 1
            for (zl, rl), (zr, rr) in zip(lefts, rights):
                full_l = [r.x1 for r in rl]
                full_r = [r.x0 for r in rr]
                if len(full_l) >= 3 and len(full_r) >= 3:
                    seps.append(min(full_r) - max(full_l))
    profile.two_column = bool(text_pages) and two >= 0.6 * text_pages and two >= 1
    seps = sorted(x for x in seps if 2 <= x <= 60)
    if seps:
        profile.columnsep = round(seps[len(seps) // 2], 2)
