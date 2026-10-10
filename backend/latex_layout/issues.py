"""
issues.py — Layout defects of a rendered document, found by measurement.

What a reader calls "badly formatted" is not one thing, and none of it is
visible in the LaTeX source: it only exists once TeX has set the page. This
module compiles nothing and edits nothing — it reads a rendered PDF (plus the
compiler's log, when there is one) and names what is wrong, where it is on the
page, and which text is responsible, so that repair.py can choose a fix and
the tool can map it back to the source.

Three independent signals, because each one misses what the others catch:

* the log's ``Overfull \\hbox … at lines a--b`` — exact and already mapped to
  source lines, but only covers boxes TeX itself built and warned about;
* word boxes against the text area — catches \\makebox, tabular content and
  anything TeX never complained about, and is the only signal that sees a
  table running off the page or into the footer;
* adjacent line pairs — a technical token split across a line break is a
  defect no width measurement can see, because every line *does* fit.

The text area is taken from TeX's own \\textwidth when the caller can supply it
(layout_tools probes for it); inferring it from the page is a fallback, because
on a real page with tables too few lines share a right edge for the mode to
mean anything.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .blocks import TextBlock, text_blocks
from .overflow import SEVERE_OVERFULL_PT, parse_overfull, text_right_edge

logger = logging.getLogger("latex_layout.issues")

# Defect taxonomy. The string values are what the agent and the tests see.
OVERFLOW = "OVERFLOW"
MARGIN_VIOLATION = "MARGIN_VIOLATION"
AWKWARD_LINE_BREAK = "AWKWARD_LINE_BREAK"
LONG_PATH = "LONG_PATH"
LONG_URL = "LONG_URL"
LONG_IDENTIFIER = "LONG_IDENTIFIER"
CODE_WRAP = "CODE_WRAP"
TABLE_WIDTH = "TABLE_WIDTH"
TABLE_CELL_OVERFLOW = "TABLE_CELL_OVERFLOW"
COLUMN_IMBALANCE = "COLUMN_IMBALANCE"
VERTICAL_OVERFLOW = "VERTICAL_OVERFLOW"
ORPHAN_LINE = "ORPHAN_LINE"
VISUAL_INCONSISTENCY = "VISUAL_INCONSISTENCY"

# Severity is a property of the defect kind, so prioritisation (fix the worst
# first, then re-measure) is table-driven rather than decided case by case.
SEVERITY: Dict[str, str] = {
    MARGIN_VIOLATION: "high",
    VERTICAL_OVERFLOW: "high",
    TABLE_WIDTH: "high",
    TABLE_CELL_OVERFLOW: "high",
    OVERFLOW: "medium",
    AWKWARD_LINE_BREAK: "medium",
    LONG_PATH: "medium",
    LONG_URL: "medium",
    LONG_IDENTIFIER: "medium",
    CODE_WRAP: "medium",
    COLUMN_IMBALANCE: "low",
    ORPHAN_LINE: "low",
    VISUAL_INCONSISTENCY: "low",
}
_RANK = {"high": 0, "medium": 1, "low": 2}

# Weights for the layout score: a repair is kept only if the score does not
# rise. Text outside the page costs more than a loose-looking column.
WEIGHT: Dict[str, float] = {
    MARGIN_VIOLATION: 10.0, VERTICAL_OVERFLOW: 10.0, TABLE_WIDTH: 8.0, TABLE_CELL_OVERFLOW: 8.0,
    OVERFLOW: 4.0, AWKWARD_LINE_BREAK: 2.0, LONG_PATH: 2.0, LONG_URL: 2.0,
    LONG_IDENTIFIER: 2.0, CODE_WRAP: 2.0, COLUMN_IMBALANCE: 1.0, ORPHAN_LINE: 1.0,
    VISUAL_INCONSISTENCY: 0.5,
}

EDGE_TOL = 1.5          # pt a line may pass the text edge before it counts
RULE_MIN_LEN = 20.0     # pt: shorter stroked segments are not table rules
RULE_TOL = 0.8          # pt: thickness below which a stroke is a rule, not a box


# ---------------------------------------------------------------------------
# Content typing
# ---------------------------------------------------------------------------

_RE_URL = re.compile(r"^(?:https?|ftp)://|^www\.", re.I)
_RE_EXT = re.compile(r"\.[A-Za-z][A-Za-z0-9]{0,5}$")
_RE_CAMEL = re.compile(r"[a-z][A-Z]")
_RE_WORDY = re.compile(r"^[A-Za-z]+$")
# "CAPE-bound", "well-known": ordinary hyphenated English, which TeX
# already breaks at the hyphen. Not an identifier to be re-punctuated.
_RE_COMPOUND = re.compile(r"^[A-Za-z]+(?:-[A-Za-z]+)+$")


def classify_token(token: str) -> Optional[str]:
    """
    The defect type a broken-up ``token`` should be repaired as, or None when
    it is ordinary prose and breaking it was legitimate.

    Ordinary words are the common case and must not be touched: TeX's own
    hyphenation is correct and wrapping it in a break-anywhere command would
    make the paragraph worse, not better.
    """
    t = (token or "").strip()
    if len(t) < 4 or " " in t:
        return None
    if _RE_URL.search(t):
        return LONG_URL
    if "/" in t or "\\" in t:
        return LONG_PATH
    if _RE_EXT.search(t) and not _RE_WORDY.match(t):
        return LONG_PATH
    if "_" in t or "::" in t or _RE_CAMEL.search(t):
        return LONG_IDENTIFIER
    if _RE_WORDY.match(t):
        return None          # a plain word: TeX hyphenated it, which is fine
    if _RE_COMPOUND.match(t):
        return None          # "CAPE-bound": a compound word, not an identifier
    if re.search(r"[A-Za-z]", t) and re.search(r"[-.:#@]", t) and len(t) >= 8:
        return LONG_IDENTIFIER
    return None


# ---------------------------------------------------------------------------
# The issue record
# ---------------------------------------------------------------------------

@dataclass
class LayoutIssue:
    page: int                                   # 1-based
    type: str
    description: str
    text: str = ""                              # the offending run, as rendered
    severity: str = "medium"
    region: Optional[Tuple[float, float, float, float]] = None   # x, y, w, h in pt
    source: Optional[Tuple[int, int]] = None                     # source lines, filled by mapping
    evidence: Dict[str, Any] = field(default_factory=dict)

    @property
    def weight(self) -> float:
        """
        How bad this issue is, magnitude included.

        Presence alone is not enough to rank two versions of a page. A repair
        that takes an overflow from 57pt to 32pt is real progress, but if the
        score only counted issues it would tie with the original and be rolled
        back — and the next repair in the ladder, which would have finished
        the job, never gets tried. (The document write gate compares
        structural errors by magnitude for the same reason.)
        """
        base = WEIGHT.get(self.type, 1.0)
        ev = self.evidence or {}
        over = ev.get("by_pt")
        if over is None and ev.get("x1") is not None and ev.get("page_width") is not None:
            over = float(ev["x1"]) - float(ev["page_width"])
        if over is None:
            m = re.search(r"\(([0-9.]+)pt too wide\)", " ".join(ev.get("compiler_warnings") or []))
            over = float(m.group(1)) if m else None
        if over is None and ev.get("table_width") and ev.get("text_width"):
            over = float(ev["table_width"]) - float(ev["text_width"])
        if over is None and ev.get("table_bottom") and ev.get("text_bottom"):
            over = float(ev["table_bottom"]) - float(ev["text_bottom"])
        if over is None:
            return base
        # Saturating, so one catastrophic overflow cannot outweigh everything.
        return round(base * (1.0 + min(max(over, 0.0), 120.0) / 120.0), 4)

    def key(self) -> Tuple[Any, ...]:
        """Identity for de-duplication across detection passes."""
        return (self.page, self.type, re.sub(r"\s+", " ", self.text).strip()[:80])

    def as_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "page": self.page, "type": self.type, "severity": self.severity,
            "description": self.description,
        }
        if self.text:
            d["text"] = self.text[:200]
        if self.region:
            d["region"] = [round(v, 1) for v in self.region]
        if self.source:
            d["source_lines"] = list(self.source)
        if self.evidence:
            d["evidence"] = self.evidence
        return d


def sort_issues(issues: Sequence[LayoutIssue]) -> List[LayoutIssue]:
    """Worst first, then by page — the order repairs are attempted in."""
    return sorted(issues, key=lambda i: (_RANK.get(i.severity, 1), -i.weight, i.page))


def layout_score(issues: Sequence[LayoutIssue], pages: Optional[Sequence[int]] = None) -> float:
    """Weighted badness of a set of issues, optionally restricted to ``pages``."""
    sel = [i for i in issues if pages is None or i.page in set(pages)]
    return round(sum(i.weight for i in sel), 3)


def issue_counts(issues: Sequence[LayoutIssue]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for i in issues:
        out[i.type] = out.get(i.type, 0) + 1
    return out


# ---------------------------------------------------------------------------
# Page geometry
# ---------------------------------------------------------------------------

@dataclass
class TextArea:
    left: float
    right: float
    top: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    def as_dict(self) -> Dict[str, float]:
        return {"left": round(self.left, 1), "right": round(self.right, 1),
                "top": round(self.top, 1), "bottom": round(self.bottom, 1)}


def _body_band(blocks: List[TextBlock], page_h: float) -> Tuple[float, float]:
    """
    Top of the running text and the lowest y the body may occupy, with the
    running header and footer excluded.

    A running header or footer is one isolated line separated from the body by
    a gap much larger than the body's own leading. The *bottom* returned is the
    top of the footer (not the last line of text): a page whose text simply
    ends early has acres of legitimate empty space below it, and clamping the
    limit to the last line would report every short page as overflowing.
    """
    if not blocks:
        return 0.0, page_h
    ys = sorted({round(b.y, 1) for b in blocks})
    if len(ys) < 3:
        return ys[0], page_h
    gaps = sorted(ys[i + 1] - ys[i] for i in range(len(ys) - 1))
    typical = gaps[len(gaps) // 2] or 12.0
    cut = max(2.5 * typical, 24.0)
    top, bottom = ys[0], page_h
    # Peel one isolated line off each end (a header/footer is a single line).
    if ys[1] - ys[0] > cut:
        top = ys[1]
    if ys[-1] - ys[-2] > cut:
        # The footer's baseline; the body must stop above its ascent.
        bottom = ys[-1] - max(typical, 12.0)
    return top, bottom


def page_text_area(blocks: List[TextBlock], page_size: Tuple[float, float],
                   textwidth: Optional[float] = None,
                   geometry: Optional[Dict[str, float]] = None) -> TextArea:
    """
    The rectangle the body text is supposed to stay inside.

    ``geometry`` is the exact answer from ``justify.probe_page_geometry`` (TeX's
    own \\textwidth / \\textheight and margins, in big points) and is used
    whenever it is available. Inference is only a fallback, because it is
    least reliable on exactly the pages that need checking: a page dominated
    by a wide table has no three lines sharing a right edge, so
    ``text_right_edge`` finds no mode and returns None.
    """
    pw, ph = page_size
    if geometry:
        return TextArea(geometry["left"], geometry["right"], geometry["top"], geometry["bottom"])
    body = [b for b in blocks if b.width > 1]
    if not body:
        return TextArea(0.0, pw, 0.0, ph)
    # Left edge: the leftmost x that more than one line starts at. The *modal*
    # start is wrong on a page with a table — padded cells in a two-column
    # table outnumber the body's own lines and move the margin inwards, which
    # then hides every line that really does overrun it.
    from collections import Counter
    starts = Counter(round(b.x) for b in body)
    repeated = [x for x, n in starts.items() if n >= 2]
    left = float(min(repeated)) if repeated else float(min(starts))
    if textwidth and textwidth > 0:
        right = left + textwidth
    else:
        inferred = text_right_edge(body)
        right = float(inferred) if inferred else pw
    top, bottom = _body_band(body, ph)
    return TextArea(left, right, top, bottom)


# ---------------------------------------------------------------------------
# Tables, from the rules TeX actually drew
# ---------------------------------------------------------------------------

@dataclass
class TableRegion:
    bbox: Tuple[float, float, float, float]     # x0, y0, x1, y1
    columns: List[float]                        # x of every vertical rule
    rows: List[float]                           # y of every horizontal rule

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]


def _rules(page: Any) -> Tuple[List[Tuple[float, float, float]], List[Tuple[float, float, float]]]:
    """(horizontal, vertical) rules as (fixed coord, from, to), from the page's strokes."""
    hor: List[Tuple[float, float, float]] = []
    ver: List[Tuple[float, float, float]] = []
    try:
        drawings = page.get_drawings()
    except Exception as e:
        logger.debug(f"get_drawings failed: {e}")
        return hor, ver
    for g in drawings:
        r = g.get("rect")
        if r is None:
            continue
        w, h = float(r.width), float(r.height)
        if h <= RULE_TOL and w >= RULE_MIN_LEN:
            hor.append((float(r.y0), float(r.x0), float(r.x1)))
        elif w <= RULE_TOL and h >= 2.0:
            ver.append((float(r.x0), float(r.y0), float(r.y1)))
    return hor, ver


def table_regions(page: Any) -> List[TableRegion]:
    """
    Tables found from the rules TeX drew, not from PyMuPDF's find_tables().

    find_tables() is built for tables whose borders are real strokes forming a
    closed grid; it returns nothing for a LaTeX table whose rules run off the
    page, and nothing at all for booktabs, which has no vertical rules. The
    horizontal rules are the reliable invariant: every LaTeX table has at least
    two, and their extent is the table's width — including the part that has
    left the page, which is the whole point of measuring.
    """
    hor, ver = _rules(page)
    if len(hor) < 2:
        return []
    hor.sort()
    groups: List[List[Tuple[float, float, float]]] = []
    for rule in hor:
        y, x0, x1 = rule
        placed = False
        for g in groups:
            gy = g[-1][0]
            gx0 = min(r[1] for r in g)
            gx1 = max(r[2] for r in g)
            # Same table: vertically close and horizontally overlapping.
            if y - gy <= 220.0 and min(x1, gx1) - max(x0, gx0) > 0.4 * min(x1 - x0, gx1 - gx0):
                g.append(rule)
                placed = True
                break
        if not placed:
            groups.append([rule])
    out: List[TableRegion] = []
    for g in groups:
        if len(g) < 2:
            continue
        x0 = min(r[1] for r in g)
        x1 = max(r[2] for r in g)
        y0 = min(r[0] for r in g)
        y1 = max(r[0] for r in g)
        cols = sorted({round(v[0], 1) for v in ver if y0 - 2 <= v[1] <= y1 + 2 and x0 - 2 <= v[0] <= x1 + 2})
        out.append(TableRegion((x0, y0, x1, y1), cols, sorted({round(r[0], 1) for r in g})))
    return out


def _cell_columns(region: TableRegion, blocks: List[TextBlock]) -> List[Tuple[float, float]]:
    """Column spans of a table: between its vertical rules, else from text starts."""
    if len(region.columns) >= 2:
        return [(region.columns[i], region.columns[i + 1]) for i in range(len(region.columns) - 1)]
    inside = [b for b in blocks if region.bbox[1] - 4 <= b.y <= region.bbox[3] + 4]
    if not inside:
        return []
    from collections import Counter
    starts = sorted({round(b.x, 1) for b in inside})
    merged: List[float] = []
    for s in starts:
        if not merged or s - merged[-1] > 6.0:
            merged.append(s)
    bounds = merged + [region.bbox[2]]
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def _line_pairs(blocks: List[TextBlock]) -> List[Tuple[TextBlock, TextBlock]]:
    """Vertically adjacent line pairs that belong to the same running text."""
    ordered = sorted(blocks, key=lambda b: (round(b.y, 1), b.x))
    pairs: List[Tuple[TextBlock, TextBlock]] = []
    for a, b in zip(ordered, ordered[1:]):
        gap = b.y - a.y
        lead = max(a.height, b.height, 1.0)
        # Next line of the same paragraph, and starting at or left of where a began.
        if 0 < gap <= 2.2 * lead and b.x <= a.x + 6.0:
            pairs.append((a, b))
    return pairs


def _plain_source(code: str) -> str:
    """
    The source's visible text on one line per source line, for confirming that
    two PDF line fragments really were one token before TeX broke them.
    """
    from .metrics import latex_to_plain
    return "\n".join(latex_to_plain(ln) for ln in (code or "").splitlines())


def _is_one_token_in_source(joined: str, source_plain: Optional[str]) -> Optional[bool]:
    """
    True when ``joined`` occurs in the source as one unbroken run, False when
    it does not, None when there is no source to check against.

    This is what separates a real mid-token break from the ordinary case of
    one token ending a line and the next word starting the following one.
    Geometry alone cannot tell them apart — in the PDF both are simply "line
    ends here, line starts there" — and without the check every paragraph
    whose last word happens to be a file path is reported as broken.
    """
    if not source_plain:
        return None
    needle = joined.strip("()[]{}.,;:!?\u2019\"'")
    if len(needle) < 4:
        return False
    return needle in source_plain


def _below_text_area(blocks: List[TextBlock], area: TextArea, page_h: float) -> List[TextBlock]:
    """
    Lines printing below where the body text may go — content running over the
    footer or off the page — with the running footer itself excluded.

    The two are told apart by continuity, not position. Overflowing content
    keeps coming at the body's own line pitch, because it is the body; a
    running footer sits alone after a wide gap. Using position alone would
    report every page in the document, since a page number is below the text
    block by design.
    """
    ordered = sorted(blocks, key=lambda b: b.y)
    if not ordered:
        return []
    # The line pitch of the BODY, not of the page: a page holding two lines and
    # a page number has one enormous "gap", and taking that as typical makes
    # the page number look like a continuation of the text.
    inside = [b.y for b in ordered if b.y <= area.bottom + EDGE_TOL]
    gaps = sorted(inside[i + 1] - inside[i] for i in range(len(inside) - 1))
    typical = gaps[len(gaps) // 2] if len(gaps) >= 2 else 14.0
    typical = typical if 4.0 <= typical <= 40.0 else 14.0
    out: List[TextBlock] = []
    for prev, b in zip([None] + ordered[:-1], ordered):
        if b.y <= area.bottom + EDGE_TOL:
            continue
        if b.y > page_h:                       # off the paper entirely: never a footer
            out.append(b)
            continue
        gap = (b.y - prev.y) if prev is not None else float("inf")
        if gap > 2.2 * typical:
            continue                            # isolated below the body: a running footer
        out.append(b)
    return out


def _broken_tokens(blocks: List[TextBlock], page: int, area: TextArea,
                   source_plain: Optional[str] = None) -> List[LayoutIssue]:
    """Technical tokens split across a line break with no hyphen to show for it."""
    found: List[LayoutIssue] = []
    for a, b in _line_pairs(blocks):
        at, bt = a.text.rstrip(), b.text.lstrip()
        if not at or not bt:
            continue
        # TeX's own hyphenation leaves a hyphen; that break is legitimate.
        if at.endswith(("-", "‐", "–", "—")):
            continue
        # A break *at* a separator is the good kind, and is exactly what a
        # repair installs: "scanners/" + "downloads/..." reads correctly. Only
        # a break inside an alphanumeric run invents a word boundary that is
        # not there, so without this every successful repair re-reports itself.
        if at.endswith(tuple("/_.:,=?@+")):
            continue
        if at.endswith((".", ",", ";", ":", "!", "?", ")", "]", "}")):
            continue
        tail = at.split()[-1]
        head = bt.split()[0]
        joined = tail + head
        kind = classify_token(joined)
        if kind is None:
            continue
        # Both halves must be substantial enough that this is a real split, and
        # the tail must reach the right edge (otherwise the break was chosen,
        # not forced, and rewriting it would be meddling).
        if len(tail) < 2 or len(head) < 2:
            continue
        if a.x1 < area.right - 24.0:
            continue
        # Confirm against the source: the two halves must be one token there.
        if _is_one_token_in_source(joined, source_plain) is False:
            continue
        found.append(LayoutIssue(
            page=page, type=kind, severity=SEVERITY[kind],
            description=(f"{_human(kind)} '{joined}' is split across a line break "
                         f"after '{tail}' with no hyphen, which reads as two separate items."),
            text=joined,
            region=(a.x, a.y - a.height, a.x1 - a.x, a.height),
            evidence={"visual_observation": f"line ends '{at[-40:]}', next line starts '{bt[:40]}'"},
        ))
    return found


def _human(kind: str) -> str:
    return {LONG_PATH: "File path", LONG_URL: "URL", LONG_IDENTIFIER: "Identifier",
            CODE_WRAP: "Code"}.get(kind, "Technical token")


def detect_page(pdf_bytes: bytes, page_index: int, textwidth: Optional[float] = None,
                overfull: Optional[List[Dict[str, Any]]] = None,
                geometry: Optional[Dict[str, float]] = None,
                source_plain: Optional[str] = None) -> Tuple[List[LayoutIssue], TextArea]:
    """Every geometric defect of one page, plus the text area they were judged against."""
    import pymupdf

    page_no = page_index + 1
    issues: List[LayoutIssue] = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        if page_index >= doc.page_count:
            return [], TextArea(0, 0, 0, 0)
        page = doc[page_index]
        pw, ph = page.rect.width, page.rect.height
        blocks = text_blocks(page)
        area = page_text_area(blocks, (pw, ph), textwidth, geometry)
        tables = table_regions(page)

    body = [b for b in blocks if b.width > 1]

    # 1. Text outside the page, or past the text area's right edge.
    for b in body:
        if b.x1 > pw - 0.5 or b.x < 0.5:
            issues.append(LayoutIssue(
                page=page_no, type=MARGIN_VIOLATION, severity=SEVERITY[MARGIN_VIOLATION],
                description=f"Text runs off the page edge (ends at {b.x1:.0f}pt, page is {pw:.0f}pt wide).",
                text=b.text, region=(b.x, b.y - b.height, b.width, b.height),
                evidence={"x1": round(b.x1, 1), "page_width": round(pw, 1)}))
        elif b.x1 > area.right + EDGE_TOL:
            issues.append(LayoutIssue(
                page=page_no, type=MARGIN_VIOLATION, severity=SEVERITY[MARGIN_VIOLATION],
                description=(f"Text runs {b.x1 - area.right:.0f}pt past the right margin "
                             f"(ends at {b.x1:.0f}pt, text area ends at {area.right:.0f}pt)."),
                text=b.text, region=(b.x, b.y - b.height, b.width, b.height),
                evidence={"x1": round(b.x1, 1), "right_edge": round(area.right, 1),
                          "by_pt": round(b.x1 - area.right, 1)}))

    # 2. Technical tokens broken across lines.
    issues.extend(_broken_tokens(body, page_no, area, source_plain))

    # 3. Tables.
    for t in tables:
        x0, y0, x1, y1 = t.bbox
        # A table issue has no offending *line*, so carry some of the table's
        # own text as its identity: without it the repair step has no anchor
        # and cannot tell which of the document's tables this is. The LONGEST
        # line, not the first — a header cell is often one short word
        # ("Table", "Purpose") which is far too generic to locate a span by,
        # and the issue was simply reported unlocatable.
        inside = [b.text.strip() for b in body
                  if y0 - 2 <= b.y <= y1 + 2 and len(b.text.strip()) > 2]
        head = max(inside, key=len) if inside else ""
        if x1 > area.right + EDGE_TOL or x0 < area.left - EDGE_TOL:
            issues.append(LayoutIssue(
                page=page_no, type=TABLE_WIDTH, severity=SEVERITY[TABLE_WIDTH],
                description=(f"Table is {x1 - x0:.0f}pt wide but the text area is {area.width:.0f}pt; "
                             f"it extends {max(0.0, x1 - area.right):.0f}pt past the right margin."),
                text=head, region=(x0, y0, x1 - x0, y1 - y0),
                evidence={"table_width": round(x1 - x0, 1), "text_width": round(area.width, 1)}))
        if y1 > area.bottom + EDGE_TOL:
            issues.append(LayoutIssue(
                page=page_no, type=VERTICAL_OVERFLOW, severity=SEVERITY[VERTICAL_OVERFLOW],
                description=(f"Table runs {y1 - area.bottom:.0f}pt below the bottom of the text area, "
                             f"overlapping the footer or running off the page."),
                text=head, region=(x0, y0, x1 - x0, y1 - y0),
                evidence={"table_bottom": round(y1, 1), "text_bottom": round(area.bottom, 1)}))
        # Cell content crossing its own column border.
        cols = _cell_columns(t, body)
        for lo, hi in cols:
            for b in body:
                if not (y0 - 4 <= b.y <= y1 + 4):
                    continue
                if b.x < lo - 1 or b.x > hi + 1:
                    continue
                if b.x1 > hi + EDGE_TOL:
                    issues.append(LayoutIssue(
                        page=page_no, type=TABLE_CELL_OVERFLOW, severity=SEVERITY[TABLE_CELL_OVERFLOW],
                        description=(f"Table cell content runs {b.x1 - hi:.0f}pt past its column border "
                                     f"(column ends at {hi:.0f}pt)."),
                        text=b.text, region=(b.x, b.y - b.height, b.width, b.height),
                        evidence={"column": [round(lo, 1), round(hi, 1)], "x1": round(b.x1, 1)}))

    # 4. Content printing below the text block: over the footer, or off the page.
    #    Measured from the text, not from table rules: PyMuPDF reports a path's
    #    bounding box, so a run of \hline rules can come back merged into one
    #    shape whose geometry says nothing about where the rows ended up.
    spill = _below_text_area(body, area, ph)
    if spill:
        lowest = max(b.y for b in spill)
        issues.append(LayoutIssue(
            page=page_no, type=VERTICAL_OVERFLOW, severity=SEVERITY[VERTICAL_OVERFLOW],
            description=(f"{len(spill)} line(s) print below the bottom of the text area "
                         f"(lowest at {lowest:.0f}pt, text area ends at {area.bottom:.0f}pt), "
                         f"running over the footer or off the page."),
            text=spill[0].text,
            region=(min(b.x for b in spill), spill[0].y,
                    max(b.x1 for b in spill) - min(b.x for b in spill), lowest - spill[0].y),
            evidence={"lines_below": len(spill), "lowest_pt": round(lowest, 1),
                      "text_bottom": round(area.bottom, 1),
                      "table_bottom": round(lowest, 1)}))

    # 5. Overfull boxes TeX warned about, already carrying their source lines.
    for o in (overfull or []):
        if not o.get("severe"):
            continue
        lines = o.get("lines")
        issues.append(LayoutIssue(
            page=page_no, type=OVERFLOW, severity=SEVERITY[OVERFLOW],
            description=f"TeX reported an overfull {o.get('box', 'hbox')} ({o.get('amount_pt', 0):.0f}pt too wide).",
            source=(lines[0], lines[1]) if lines else None,
            evidence={"compiler_warnings": [f"Overfull {o.get('box')} ({o.get('amount_pt', 0):.1f}pt too wide)"]}))
    return issues, area


def detect_layout_issues(pdf_bytes: Optional[bytes], log: str = "",
                         textwidth: Optional[float] = None,
                         pages: Optional[Sequence[int]] = None,
                         max_pages: int = 40,
                         geometry: Optional[Dict[str, float]] = None,
                         source: Optional[str] = None) -> List[LayoutIssue]:
    """
    Every geometric layout defect of a rendered document, worst first.

    ``pages`` (1-based) restricts the scan; ``log`` supplies TeX's overfull
    warnings, which are the only signal that already knows its source lines;
    ``geometry`` is ``justify.probe_page_geometry``'s exact text area; and
    ``source`` is the LaTeX itself, used to confirm that a token which *looks*
    broken across a line really is one token in the source.
    """
    if not pdf_bytes:
        return []
    import pymupdf

    overfull = parse_overfull(log)
    source_plain = _plain_source(source) if source else None
    # An overfull box is reported by TeX without a page number; it is attached
    # to the first page scanned so it is reported once, not once per page.
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        count = doc.page_count
    wanted = [p - 1 for p in pages] if pages else list(range(count))
    wanted = [i for i in wanted if 0 <= i < count][:max_pages]

    found: List[LayoutIssue] = []
    seen = set()
    for n, idx in enumerate(wanted):
        try:
            page_issues, _area = detect_page(pdf_bytes, idx, textwidth,
                                             overfull if n == 0 else None, geometry, source_plain)
        except Exception as e:                      # one bad page must not lose the rest
            logger.warning(f"Layout detection failed on page {idx + 1}: {e}")
            continue
        for i in page_issues:
            if i.key() in seen:
                continue
            seen.add(i.key())
            found.append(i)
    return sort_issues(found)
