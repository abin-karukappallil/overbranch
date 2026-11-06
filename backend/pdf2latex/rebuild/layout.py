"""
layout.py — Stage 3 of the AI rebuild ("extracting"): per-page layout and block classification.

Input is the extractor's output (`extract.extract_document`: spans with font, size, flags, colour and
bbox, lines in reading order), the open document, the asset manifest and the inspection. Output is
one `PageLayout` per page: the page's text as role-tagged blocks in reading order, plus its tables
and assets, compact enough to go straight into the page prompt.

The analysis is the deterministic engine's, called as it is (nothing in `editable/` changes):
  editable.glyphs     private-use (Symbol-font) glyphs recovered by shape, in place
  editable.furniture  running headers, footers and page numbers
  editable.columns    body column, side notes, column zones and visual rows
  editable.profile    body size, leading, heading candidates and recurring heading styles
  editable.blocks     list markers (`_row_marker`) and paragraph alignment (`_para_align`)
New here: paragraph grouping from the rows, captions (linked to the asset or table they label, whose
`caption` is set in the manifest in place), footnotes, a heading-level ladder (1..3, by size then
weight), the title, list depth, and a furniture fallback for pages the repetition test cannot see
(a one-page document still has a header and a page number).

Every source line ends up in exactly one place: a block (headers, footers and page numbers are
role-tagged blocks too), or the interior of a manifest image/vector/math asset or table (that text
travels in the asset or in `PageLayout.tables`). Captions inside an asset's box stay blocks. Block
text is the source text verbatim, whitespace collapsed, lines joined by a space; a list item's or
footnote's marker is moved to `marker`.

Block dicts follow `model.PageLayout`, with defaults omitted to keep the JSON small: `level` only on
headings (1..3) and list items (nesting depth, 1 = outermost), `column` only when not 0,
`gap_before` only when positive, `runs` only when a span differs from the block font, `font.bold`/
`font.italic` only when true, `font.color` only when not black. Extra keys: `for` on a caption (the
asset filename or table id it labels), `ref` on the `figure`/`table`/`math` placeholder blocks that
mark where an asset or table sits in the reading order (their `text` is empty), `note: "side"` on a
side callout (role `other`).

Pure CPU work over the open document: run it off the event loop (`asyncio.to_thread`).
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import pymupdf

from ..editable import columns as C
from ..editable import furniture as F
from ..editable import profile as PRof
from ..editable.blocks import _para_align, _row_marker
from ..editable.model import TLine, Zone
from ..models import DocExtract, Line, PageExtract, Span
from .model import AssetManifest, Inspection, PageLayout, Rect

logger = logging.getLogger("pdf2latex.rebuild.layout")

TOKEN_BUDGET = 5000             # target prompt size of one page's layout JSON
CHARS_PER_TOKEN = 4             # rough JSON chars per token, for the budget check
INTERIOR_SHARE = 0.6            # a line this much inside an asset/table box is that box's content
CAPTION_GAP = 30.0              # pt: a caption sits at most this far from what it labels (or 2.5 lines)
FOOTNOTE_TOP = 0.5              # footnotes sit in the lower part of the page (share of its height)
BAND_TOP, BAND_BOTTOM = 0.09, 0.91   # furniture fallback: the page's top / bottom bands
FAMILY_MAX = 40                 # chars of a font family name in the JSON

_WS = (" ", " ", "\t")
# "Figure 3:", "Fig. 2.1.", "Table 4 —", "TABLE II" (the row ends after the number), "Listing 1:"
_CAPTION = re.compile(r"^\s*(figure|fig\.?|table|algorithm|listing)\s*"
                      r"([A-Z]?\d+(?:[.\-–]\d+)*[a-z]?|[IVXLC]{1,6})\s*(?:[.:|—–-]|$)", re.IGNORECASE)
# a footnote opens with its number or symbol: "1 Figures are…", "*Corresponding author", "†Equal…"
_FN_MARK = re.compile(r"^\s*(\d{1,3}|[*†‡§¶‖]{1,3})(?=\s|[A-Z(\[“\"])")
_NUMBERED = re.compile(r"^\s*\d{1,2}(?:\.\d{1,2}){0,3}\.?\s+\S")
# dot bullets the text layer spells differently ("·" for a base-14 "•", Symbol's private-use one)
_DOT_BULLETS = {"·", "∙", "●", "\uf0b7", "\u2022"}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _area(b: Rect) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _share_inside(inner: Rect, outer: Rect, pad: float = 1.5) -> float:
    """How much of `inner` lies inside `outer` (grown by `pad`), as a share of `inner`'s area."""
    x0, y0 = max(inner[0], outer[0] - pad), max(inner[1], outer[1] - pad)
    x1, y1 = min(inner[2], outer[2] + pad), min(inner[3], outer[3] + pad)
    a = _area(inner)
    if a <= 0:
        cx, cy = (inner[0] + inner[2]) / 2, (inner[1] + inner[3]) / 2
        return 1.0 if outer[0] - pad <= cx <= outer[2] + pad and outer[1] - pad <= cy <= outer[3] + pad else 0.0
    return max(0.0, x1 - x0) * max(0.0, y1 - y0) / a


def _h_overlap(a: Rect, b: Rect) -> float:
    """Horizontal overlap of two boxes as a share of the narrower one."""
    inner = min(a[2], b[2]) - max(a[0], b[0])
    narrow = min(a[2] - a[0], b[2] - b[0])
    return inner / narrow if narrow > 0 else 0.0


def _family(font: str) -> str:
    """The family part of a PDF font name ("Times" from "ABCDEF+Times-Bold")."""
    name = re.sub(r"^[A-Z]{6}\+", "", font or "")
    return (re.split(r"[-,]", name)[0] or name)[:FAMILY_MAX]


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(v) for v in rgb[:3])


def _norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _r1(v: float) -> float:
    return round(float(v), 1)


# ---------------------------------------------------------------------------
# Rows: verbatim text and styled pieces from the source spans
# ---------------------------------------------------------------------------

@dataclass
class _Piece:
    text: str
    family: str
    size: float
    bold: bool
    italic: bool
    color: str
    script: int                 # +1 superscript, -1 subscript

    def key(self) -> Tuple:
        return (self.family, self.size, self.bold, self.italic, self.color)


def _row_pieces(page: PageExtract, row: TLine) -> List[_Piece]:
    """
    The row's spans left to right with the word gaps the PDF leaves between them made spaces. Built
    from the source spans rather than the row's segments, which drop dot leaders.
    """
    spans: List[Tuple[Span, float]] = []
    for i in row.src:
        if 0 <= i < len(page.lines):
            ln = page.lines[i]
            spans.extend((sp, ln.baseline) for sp in ln.spans if sp.text)
    spans.sort(key=lambda t: t[0].origin[0])
    size = row.size or 10.0
    out: List[_Piece] = []
    prev_end: Optional[float] = None
    for sp, base in spans:
        text = sp.text
        if out and prev_end is not None and sp.bbox[0] - prev_end >= 0.15 * size \
                and not out[-1].text.endswith(_WS) and not text.startswith(_WS):
            text = " " + text
        sp_base = sp.origin[1]
        script = 0
        if sp.superscript or sp_base < row.baseline - 0.2 * size:
            script = 1
        elif sp_base > row.baseline + 0.1 * size:
            script = -1
        out.append(_Piece(text=text, family=_family(sp.font), size=C.rsz(sp.size), bold=sp.bold,
                          italic=sp.italic, color=_hex(sp.color), script=script))
        prev_end = sp.bbox[2] if prev_end is None else max(prev_end, sp.bbox[2])
    return out


def _row_text(page: PageExtract, row: TLine) -> str:
    return _norm_ws("".join(p.text for p in _row_pieces(page, row)))


# ---------------------------------------------------------------------------
# Working blocks
# ---------------------------------------------------------------------------

@dataclass
class _Blk:
    role: str
    rows: List[TLine] = field(default_factory=list)
    zone: int = 0               # index into the page's zones (reading order)
    column: int = 0
    wide: bool = True           # in a full-width band (not one column of a two-column band)
    left: float = 0.0           # the text column it sits in (alignment is judged against it)
    right: float = 0.0
    bbox: Rect = (0.0, 0.0, 0.0, 0.0)
    marker: str = ""
    level: int = 0
    ref: str = ""               # placeholder: asset filename or table id
    target: str = ""            # caption: what it labels
    note: str = ""
    display: bool = False       # every row may be a heading (title / heading material)
    section: bool = False       # a numbered section title set like a list item ("II. RELATED WORK")
    mkind: str = ""             # list marker kind (bullet, decimal, alpha, roman, ref, compound)
    mval: str = ""              # list marker value ("3", "b", "iv")
    size: float = 0.0
    bold: bool = False
    text: str = ""

    def finish(self, page: PageExtract) -> None:
        if self.rows:
            self.bbox = (min(r.x0 for r in self.rows), min(r.top for r in self.rows),
                         max(r.x1 for r in self.rows), max(r.bottom for r in self.rows))
            c: Counter = Counter()
            for r in self.rows:
                for run in r.runs:
                    c[run.size] += len(run.text.strip())
            self.size = c.most_common(1)[0][0] if c else self.rows[0].size
            self.bold = all(PRof.row_mostly_bold(r) for r in self.rows)
            self.text = " ".join(t for t in (_row_text(page, r) for r in self.rows) if t)


@dataclass
class _Feat:
    size: float
    bold: bool
    hcand: bool
    italic: bool
    marker: Optional[Tuple[str, str, str]]
    caption: bool
    fn_mark: bool


class _Ctx:
    """Document-level measurements every page needs."""

    def __init__(self, profile, col_left: float, col_right: float):
        self.profile = profile
        self.body = profile.body_size or 10.0
        self.col_left = col_left
        self.col_right = col_right

    def lead(self, size: float) -> float:
        lead = self.profile.leading_by_size.get(C.rsz(size))
        if lead:
            return lead
        if abs(size - self.body) <= 0.6 and self.profile.leading:
            return self.profile.leading
        return 1.25 * size

    def small(self, size: float) -> bool:
        return size <= min(self.body - 1.0, 0.9 * self.body)


def _feat(row: TLine, ctx: _Ctx) -> _Feat:
    text = row.text
    return _Feat(size=PRof.row_size(row), bold=PRof.row_mostly_bold(row),
                 hcand=PRof.heading_candidate(row, ctx.body), italic=PRof.row_italic(row),
                 marker=_row_marker(row),
                 caption=bool(_CAPTION.match(text)), fn_mark=bool(_FN_MARK.match(text)))


def _centred(row: TLine, left: float, right: float) -> bool:
    return abs((row.x0 + row.x1) / 2 - (left + right) / 2) <= 4 and row.x0 > left + 6


def _group_zone(rows: List[TLine], ctx: _Ctx, left: float, right: float, page_h: float) -> List[List[TLine]]:
    """A zone's rows grouped into blocks: a paragraph, a heading, a list item, a caption..."""
    groups: List[List[TLine]] = []
    feats: Dict[int, _Feat] = {}
    width = max(1.0, right - left)

    def f(r: TLine) -> _Feat:
        if id(r) not in feats:
            feats[id(r)] = _feat(r, ctx)
        return feats[id(r)]

    def breaks(cur: List[TLine], row: TLine) -> bool:
        prev, first = cur[-1], cur[0]
        fr, fp, f0 = f(row), f(prev), f(first)
        if fr.marker or fr.caption:
            return True
        pitch = row.baseline - prev.baseline
        wrapped = prev.x1 >= right - max(40.0, 0.25 * width)
        if f0.marker and wrapped and first.x0 + 2 <= row.x0 <= first.x0 + 60 \
                and not _centred(row, left, right) and abs(fr.size - fp.size) <= 0.6 \
                and 0 < pitch <= 1.35 * ctx.lead(fr.size):
            return False              # an item's wrapped text, whatever its emphasis
        if abs(fr.size - fp.size) > 0.6 or fr.bold != fp.bold or fr.italic != fp.italic:
            return True
        if f0.hcand and (f0.bold or f0.size >= ctx.body + 1):
            # a heading only goes on with another line of itself
            return not (fr.hcand and 0 < pitch <= 1.6 * fr.size)
        exp = (cur[1].baseline - cur[0].baseline) if len(cur) >= 2 else ctx.lead(fr.size)
        if exp <= 0:
            exp = ctx.lead(fr.size)
        if pitch > max(1.35 * exp, exp + 0.3 * fr.size):
            return True
        if f0.marker:
            # a list item goes on with its wrapped text: lines indented past its marker, under a
            # line that ran to the edge (a short "A. Related work" over an indented paragraph is a
            # section title, not an item)
            return row.x0 < first.x0 + 2 or prev.x1 < right - max(40.0, 0.25 * width)
        if ctx.small(fr.size) and fr.fn_mark and row.top >= FOOTNOTE_TOP * page_h:
            return True
        if all(_centred(r, left, right) for r in cur) and not _centred(row, left, right) \
                and row.x1 - row.x0 < 0.9 * width:
            return True
        l0 = min(r.x0 for r in cur)
        if abs(prev.x0 - l0) <= 2 and 0.5 * fr.size <= row.x0 - l0 <= 48 \
                and row.x1 >= right - 0.15 * width:
            return True               # an indented first line: a new paragraph
        full = any(r.x1 >= right - 0.04 * width for r in cur)
        if full and prev.x1 < right - max(15.0, 0.12 * width) and abs(row.x0 - l0) <= 3:
            return True               # the previous line ended short: its paragraph ended
        return False

    for row in rows:
        if not groups or breaks(groups[-1], row):
            groups.append([row])
        else:
            groups[-1].append(row)
    return groups


def _classify(b: _Blk, ctx: _Ctx) -> None:
    """caption / list_item / body for a text block; headings, the title and footnotes come later."""
    first = b.rows[0]
    b.display = len(b.rows) <= 4 and all(PRof.heading_candidate(r, ctx.body) for r in b.rows)
    if _CAPTION.match(first.text):
        b.role = "caption"
        return
    m = _row_marker(first)
    # "1. Introduction" set large or bold is a heading; a bullet never is
    if m and (m[1] == "bullet" or not (b.display and (b.bold or b.size >= ctx.body + 2))):
        b.role = "list_item"
        b.marker = m[0].strip()
        b.mkind, b.mval = m[1], m[2]
        return
    b.role = "body"


_FIRST_VALUES = {"1", "a", "A", "i", "I"}


def _sections_and_lists(zb: List[_Blk], p: PageExtract, ctx: _Ctx) -> List[_Blk]:
    """
    Settle a zone's list items. A one-line numbered item with a short unpunctuated title that is set
    apart (styled, or with no item of its kind next to it) is a section title ("II. RELATED WORK",
    "A. Factual reasoning"). An ordered item that neither opens a list nor has a neighbour of its
    kind is a line that merely starts with something marker-shaped (an initial, "[6]", "200.") and
    goes back into the paragraph around it.
    """
    def same_kind(k: int, kind: str) -> bool:
        return 0 <= k < len(zb) and zb[k].role == "list_item" and zb[k].mkind == kind

    for k, b in enumerate(zb):
        if b.role != "list_item" or len(b.rows) != 1 or b.mkind in ("bullet", "ref", "compound"):
            continue
        # a section number is written "IV." / "B." / "2."; a bare label in its own column ("19",
        # "D") is a question number or a code
        if not b.marker.endswith(".") or (b.mkind == "alpha" and not b.mval.isupper()) \
                or (b.mkind == "decimal" and int(b.mval) > 30):
            continue
        _m, rest = _take_marker(b.text, b.marker)
        words = rest.split()
        if not words or len(words) > 12 or rest.endswith((".", ",", ";", ":", "?", ")")) \
                or re.search(r"[.?!:;,]\s", rest):
            continue
        row = b.rows[0]
        styled = (b.bold or PRof.row_italic(row) or PRof.is_upper(rest) or b.size >= ctx.body + 1
                  or _centred(row, b.left, b.right))
        if styled or not (same_kind(k - 1, b.mkind) or same_kind(k + 1, b.mkind)):
            b.role, b.section, b.marker = "body", True, ""
    out: List[_Blk] = []
    k = 0
    while k < len(zb):
        b = zb[k]
        # (a label standing in its own column, a question number, is an item even when alone)
        lone = (b.role == "list_item" and b.mkind != "bullet" and b.mval not in _FIRST_VALUES
                and b.rows[0].segments and b.rows[0].segments[0].text.strip() != b.marker
                and not same_kind(k - 1, b.mkind) and not same_kind(k + 1, b.mkind))
        if not lone:
            out.append(b)
            k += 1
            continue
        b.role, b.marker, b.mkind, b.mval = "body", "", "", ""
        prev = out[-1] if out else None
        if prev is not None and _joins(prev, b, ctx):
            prev.rows.extend(b.rows)
            b = prev
        else:
            out.append(b)
        nxt = zb[k + 1] if k + 1 < len(zb) else None
        if nxt is not None and _joins(b, nxt, ctx) and not _indented(b, nxt):
            b.rows.extend(nxt.rows)
            k += 1
        b.finish(p)
        k += 1
    return out


def _joins(a: _Blk, b: _Blk, ctx: _Ctx) -> bool:
    """Whether `b` reads on from paragraph `a`: same size and weight, `a` running to the column's
    edge, the next line at the usual pitch."""
    if a.role != "body" or b.role != "body" or a.section or b.section or not a.rows or not b.rows:
        return False
    if abs(a.size - b.size) > 0.6 or a.bold != b.bold:
        return False
    if a.rows[-1].x1 < a.right - max(15.0, 0.06 * (a.right - a.left)):
        return False
    pitch = b.rows[0].baseline - a.rows[-1].baseline
    return 0 < pitch <= 1.35 * ctx.lead(b.size)


def _indented(a: _Blk, b: _Blk) -> bool:
    return b.rows[0].x0 - min(r.x0 for r in a.rows) >= 0.5 * b.size


def _take_marker(text: str, marker: str) -> Tuple[str, str]:
    """(marker, text without it) — the marker spelt as the text has it."""
    if not marker:
        return "", text
    if text.startswith(marker):
        return marker, text[len(marker):].strip()
    n = len(marker.split())
    parts = text.split(" ", n)
    if len(parts) > n:
        return " ".join(parts[:n]), parts[n].strip()
    return marker, text


# ---------------------------------------------------------------------------
# Furniture
# ---------------------------------------------------------------------------

def _furniture_roles(p: PageExtract, furn, body: float) -> Dict[int, str]:
    """
    Line index → header / footer / page_number. The repetition test (`furniture.detect`) first; a
    band it found nothing in on this page falls back to the page's own shape: a line no larger than
    the body in the top or bottom band, set apart from the content by a gap or a rule (a number on
    its own is the page number).
    """
    roles: Dict[int, str] = {}
    H = p.height
    for pno, i in furn.furniture_line_ids:
        if pno != p.number or i >= len(p.lines):
            continue
        ln = p.lines[i]
        mid = (ln.bbox[1] + ln.bbox[3]) / 2
        if p.number in furn.page_numbers and F._PAGENUM.match(ln.text):
            roles[i] = "page_number"
        else:
            roles[i] = "header" if mid < H / 2 else "footer"
    has_top = any((p.lines[i].bbox[1] + p.lines[i].bbox[3]) / 2 < H / 2 for i in roles)
    has_bot = any((p.lines[i].bbox[1] + p.lines[i].bbox[3]) / 2 >= H / 2 for i in roles)
    content = [(i, ln) for i, ln in enumerate(p.lines) if i not in roles and ln.text.strip()]
    if len(content) < 2:
        return roles
    rules = [d.rect for d in p.drawings if d.kind == "hrule"]

    def rule_between(y0: float, y1: float) -> bool:
        return any(y0 - 1 <= (r[1] + r[3]) / 2 <= y1 + 1 for r in rules)

    def size_ok(ln: Line) -> bool:
        return C.dominant_size([ln]) <= body + 0.3

    if not has_top:
        band = [(i, ln) for i, ln in content if ln.bbox[3] <= BAND_TOP * H]
        rest = [ln for i, ln in content if ln.bbox[3] > BAND_TOP * H]
        if band and rest:
            below = min(ln.bbox[1] for ln in rest)
            for i, ln in band:
                gap = below - ln.bbox[3]
                h = max(1.0, ln.bbox[3] - ln.bbox[1])
                if size_ok(ln) and (gap >= 1.8 * h or rule_between(ln.bbox[3], below)):
                    roles[i] = "page_number" if F._PAGENUM.match(ln.text) else "header"
    if not has_bot:
        band = [(i, ln) for i, ln in content if ln.bbox[1] >= BAND_BOTTOM * H]
        rest = [ln for i, ln in content if ln.bbox[1] < BAND_BOTTOM * H]
        if band and rest:
            above = max(ln.bbox[3] for ln in rest)
            for i, ln in band:
                gap = ln.bbox[1] - above
                h = max(1.0, ln.bbox[3] - ln.bbox[1])
                if F._PAGENUM.match(ln.text) and gap >= 0.8 * h:
                    roles[i] = "page_number"
                elif size_ok(ln) and not _FN_MARK.match(ln.text) and not rule_between(above, ln.bbox[1]) \
                        and gap >= 1.8 * h:
                    roles[i] = "footer"     # a rule right above it would make it a footnote
    return roles


# ---------------------------------------------------------------------------
# Assets and tables on the page
# ---------------------------------------------------------------------------

@dataclass
class _Region:
    kind: str                   # image | vector | math | table
    bbox: Rect
    ref: str
    obj: Any                    # the Asset or TableData (its caption is set in place)
    decorative: bool = False


def _regions(manifest: AssetManifest, pno: int) -> List[_Region]:
    out: List[_Region] = []
    for a in manifest.for_page(pno):
        if a.kind in ("image", "vector", "math"):
            out.append(_Region(kind=a.kind, bbox=tuple(a.bbox), ref=a.filename, obj=a,
                               decorative=bool((a.meta or {}).get("decorative"))))
    for t in manifest.tables_for_page(pno):
        out.append(_Region(kind="table", bbox=tuple(t.bbox), ref=t.id, obj=t))
    return out


def _interior(p: PageExtract, regions: List[_Region], skip: Set[int]) -> Set[int]:
    """Lines that are the content of an asset or table (captions excepted)."""
    out: Set[int] = set()
    for i, ln in enumerate(p.lines):
        if i in skip or not ln.text.strip():
            continue
        for r in regions:
            # a decorative picture (a repeated logo, a speck) holds no text of its own
            if not r.decorative and _share_inside(ln.bbox, r.bbox) >= INTERIOR_SHARE:
                if r.kind != "math" and _CAPTION.match(ln.text):
                    continue
                out.add(i)
                break
    return out


def _link_captions(blocks: List[_Blk], regions: List[_Region], ctx: _Ctx) -> None:
    """Each caption to the nearest figure or table directly above or below it (one each)."""
    targets = [r for r in regions if r.kind in ("image", "vector", "table") and not r.decorative]
    caps = [b for b in blocks if b.role == "caption"]
    if not targets or not caps:
        return
    tol = max(CAPTION_GAP, 2.5 * (ctx.profile.leading or 1.2 * ctx.body))
    pairs: List[Tuple[float, int, int]] = []
    for ci, b in enumerate(caps):
        is_table = b.text.lower().startswith("table")
        for ti, r in enumerate(targets):
            if _h_overlap(b.bbox, r.bbox) < 0.3:
                continue
            if _share_inside(b.bbox, r.bbox) >= INTERIOR_SHARE:
                # set inside the crop (a figure exported with its caption)
                pairs.append((0.0 if (r.kind == "table") == is_table else 20.0, ci, ti))
                continue
            below = b.bbox[1] - r.bbox[3]         # caption under the object
            above = r.bbox[1] - b.bbox[3]         # caption over the object
            for gap, under in ((below, True), (above, False)):
                if not -3 <= gap <= tol:
                    continue
                score = max(gap, 0.0)
                if (r.kind == "table") != is_table:
                    score += 20                    # "Table 2" over a picture: possible, not first choice
                if under == (r.kind == "table"):
                    score += 6                     # figures are captioned below, tables above
                pairs.append((score, ci, ti))
    used_c: Set[int] = set()
    used_t: Set[int] = set()
    for _score, ci, ti in sorted(pairs):
        if ci in used_c or ti in used_t:
            continue
        used_c.add(ci)
        used_t.add(ti)
        caps[ci].target = targets[ti].ref
        targets[ti].obj.caption = caps[ci].text


# ---------------------------------------------------------------------------
# Footnotes, headings, title, list depth
# ---------------------------------------------------------------------------

def _footnotes(zone_blocks: List[_Blk], p: PageExtract, ctx: _Ctx) -> None:
    """
    The zone's foot: the run of small-type text blocks it ends with. When that run starts in the
    lower part of the page (or under a short separator rule), its blocks that open with a marker,
    sit under the rule or follow a footnote are footnotes. A run of small numbered entries reaching
    up the page is a list (a slide's references), not footnotes.
    """
    rules = [d.rect for d in p.drawings if d.kind == "hrule"]

    def ruled(b: _Blk) -> bool:
        # a separator: short, from the column's left edge (a table's rules run across)
        return any(r[2] - r[0] <= 0.45 * max(1.0, b.right - b.left) and abs(r[0] - b.left) <= 8
                   and 0 <= b.bbox[1] - r[3] <= max(20.0, 3 * b.size) for r in rules)

    def note_like(b: _Blk) -> bool:
        # small running text: not a table's rows (fields set apart by tab gaps)
        return b.role in ("body", "list_item") and bool(b.rows) and ctx.small(b.size) \
            and not any(len(r.segments) >= 3 for r in b.rows)

    j = len(zone_blocks)
    while j > 0 and note_like(zone_blocks[j - 1]):
        j -= 1
    run = zone_blocks[j:]
    if run and run[0].bbox[1] < FOOTNOTE_TOP * p.height:
        k = next((k for k, b in enumerate(run) if ruled(b)), None)
        run = run[k:] if k is not None else []
    prev_fn = False
    for b in run:
        pieces = _row_pieces(p, b.rows[0])
        first = next((pc for pc in pieces if pc.text.strip()), None)
        mark = ""
        if first is not None and first.script == 1 and len(first.text.strip()) <= 4:
            mark = first.text.strip()
        else:
            m = _FN_MARK.match(b.text)
            if m:
                mark = m.group(1)
        if mark or prev_fn or ruled(b):
            b.role, b.marker, b.mkind, b.mval = "footnote", mark, "", ""
            prev_fn = True


def _assign_headings(pages_blocks: Dict[int, List[_Blk]], ctx: _Ctx, page_h: Dict[int, float]) -> None:
    """
    The title (the first page's one-off largest display line), then the headings: display blocks in
    a recurring heading style (`profile.match_level`), bold ones, large numbered ones, and the
    section titles `_sections_and_lists` found. Levels 1..3 come from a ladder over the headings'
    styles: larger first, then bold, then centred, then the depth of their numbering ("3.1" under
    "3").
    """
    body = ctx.body
    flow = [(pno, b) for pno in sorted(pages_blocks) for b in pages_blocks[pno] if b.rows]
    first_page = next((pno for pno, b in flow if b.role == "body"), None)
    if first_page is not None:
        # a numbered line ("1 Introduction") is a section, however large
        cands = [b for pno, b in flow if pno == first_page and b.role == "body" and b.display
                 and b.bbox[1] <= 0.5 * page_h[pno] and b.size >= max(body + 3, 1.25 * body)
                 and not _NUMBERED.match(b.text)]
        if cands:
            top = max(cands, key=lambda b: (b.size, -b.bbox[1]))
            biggest_here = max((b.size for pno, b in flow if pno == first_page), default=0.0)
            elsewhere = [b for _pno, b in flow if b is not top and b.size >= top.size - 0.6]
            if top.size >= biggest_here - 0.01 and not elsewhere:
                top.role = "title"
    heads: List[_Blk] = []
    for _pno, b in flow:
        if b.role != "body":
            continue
        if not b.section:
            if not b.display or len(b.rows) > 3:
                continue
            lv = PRof.match_level(ctx.profile, b.rows[0], b.left, b.right)
            recurring = lv is not None and lv.get("count", 0) >= 2
            numbered = bool(_NUMBERED.match(b.text)) and b.size >= body + 1
            if not (recurring or b.bold or numbered):
                continue
        b.role = "heading"
        heads.append(b)
    if not heads:
        return

    def key(b: _Blk) -> Tuple[float, bool, bool, int]:
        m = re.match(r"^\s*(\d{1,2}(?:\.\d{1,2})*)\.?\s", b.text)
        depth = m.group(1).count(".") + 1 if m else 1
        return (round(b.size * 2) / 2, b.bold, all(_centred(r, b.left, b.right) for r in b.rows), depth)

    def rank(k) -> Tuple:
        return (-k[0], not k[1], not k[2], k[3])

    def same(a, b) -> bool:   # sizes within 0.6pt are one size
        return abs(a[0] - b[0]) <= 0.6 and a[1:] == b[1:]

    # the ladder holds the styles that recur; a one-off style (a cover line, a lone sub-heading)
    # sits under every recurring style more prominent than it, without taking a slot of its own
    counts: Counter = Counter()
    for b in heads:
        k = key(b)
        rep_k = next((c for c in counts if same(c, k)), k)
        counts[rep_k] += 1
    recurring = [k for k, n in counts.items() if n >= 2] or list(counts)
    ladder = sorted(recurring, key=rank)
    for b in heads:
        k = key(b)
        idx = next((i for i, s in enumerate(ladder) if same(s, k)), None)
        if idx is None:
            idx = sum(1 for s in ladder if rank(s) < rank(k))
        b.level = min(3, idx + 1)


def _list_depths(zone_blocks: List[_Blk]) -> None:
    """Nesting depth of each list item: the rank of its marker's indent within its run of items."""
    run: List[_Blk] = []

    def flush() -> None:
        xs: List[float] = []
        for b in sorted(run, key=lambda b: b.bbox[0]):
            if not xs or b.bbox[0] - xs[-1] > 4:
                xs.append(b.bbox[0])
        for b in run:
            b.level = 1 + max(0, sum(1 for x in xs if b.bbox[0] - x > 4))
        run.clear()

    for b in zone_blocks:
        if b.role == "list_item":
            run.append(b)
        elif run:
            flush()
    if run:
        flush()


# ---------------------------------------------------------------------------
# Block dicts
# ---------------------------------------------------------------------------

def _font_and_runs(p: PageExtract, b: _Blk) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    pieces = [pc for r in b.rows for pc in (_row_pieces(p, r) + [None])]   # None: a line break
    weight: Counter = Counter()
    for pc in pieces:
        if pc is not None and pc.text.strip():
            weight[pc.key()] += len(pc.text.strip())
    if not weight:
        return {"family": "", "size": _r1(b.size)}, []
    fam, size, bold, italic, color = weight.most_common(1)[0][0]
    font: Dict[str, Any] = {"family": fam, "size": size}
    if bold:
        font["bold"] = True
    if italic:
        font["italic"] = True
    if color != "#000000":
        font["color"] = color
    runs: List[Dict[str, Any]] = []
    last_key = None
    for pc in pieces:
        if pc is None:                              # a line break inside a run: a space
            if runs and last_key is not None:
                runs[-1]["text"] += " "
            continue
        if not pc.text.strip():
            if runs and last_key is not None:
                runs[-1]["text"] += pc.text
            continue
        diff: Dict[str, Any] = {}
        if pc.bold != bold:
            diff["bold"] = pc.bold
        if pc.italic != italic:
            diff["italic"] = pc.italic
        if pc.color != color:
            diff["color"] = pc.color
        if abs(pc.size - size) >= 0.5:
            diff["size"] = pc.size
        if pc.script:
            diff["script"] = pc.script
        key = tuple(sorted(diff.items()))
        if not diff:
            last_key = None
            continue
        if last_key == key and runs:
            runs[-1]["text"] += pc.text
        else:
            runs.append({"text": pc.text, **diff})
        last_key = key
    out = []
    for r in runs:
        r["text"] = _norm_ws(r["text"])
        if r["text"] and r["text"] != b.marker and not (b.role == "list_item" and r["text"] in _DOT_BULLETS):
            out.append(r)
    return font, out


def _block_dict(p: PageExtract, b: _Blk, page_w: float) -> Dict[str, Any]:
    d: Dict[str, Any] = {"id": "", "role": b.role, "bbox": [_r1(v) for v in b.bbox]}
    if not b.rows:                                  # a figure / table / math placeholder
        d["text"] = ""
        d["ref"] = b.ref
        if b.column:
            d["column"] = b.column
        return d
    text = b.text
    if b.role in ("list_item", "footnote") and b.marker:
        b.marker, text = _take_marker(text, b.marker)
        if b.role == "list_item" and b.marker in _DOT_BULLETS:
            b.marker = "\u2022"
    d["text"] = text
    if b.level:
        d["level"] = b.level
    font, runs = _font_and_runs(p, b)
    d["font"] = font
    if runs:
        d["runs"] = runs
    align = _para_align(b.rows, b.left, b.right, page_w)
    d["align"] = "left" if align == "offset" else align
    if b.column:
        d["column"] = b.column
    if b.marker:
        d["marker"] = b.marker
    if b.target:
        d["for"] = b.target
    if b.note:
        d["note"] = b.note
    return d


def _tokens(layout: PageLayout) -> int:
    s = json.dumps(layout.to_prompt_dict(), ensure_ascii=False, separators=(",", ":"))
    return len(s) // CHARS_PER_TOKEN


def _fit_budget(layout: PageLayout) -> None:
    """
    Keep the page JSON near the budget. Style runs go first: size-only ones, then the runs of the
    blocks that carry the most of them (a page of alternating emphasis), so sparse emphasis
    elsewhere survives. The text is never cut; a page still over budget gets a warning.
    """
    if _tokens(layout) <= TOKEN_BUDGET:
        return
    for b in layout.blocks:
        if "runs" in b:
            b["runs"] = [r for r in b["runs"] if set(r) - {"text", "size"}]
            if not b["runs"]:
                del b["runs"]
    dropped = 0
    for b in sorted((b for b in layout.blocks if "runs" in b), key=lambda b: -len(b["runs"])):
        if _tokens(layout) <= TOKEN_BUDGET:
            break
        del b["runs"]
        dropped += 1
    layout.warnings.append("Layout JSON over budget: size-only style runs were dropped"
                           + (f", and all style runs of {dropped} block(s)." if dropped else "."))
    n = _tokens(layout)
    if n > TOKEN_BUDGET:
        layout.warnings.append(f"Layout JSON is ~{n} tokens (budget {TOKEN_BUDGET}); the text is kept whole.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

@dataclass
class _PageWork:
    page: PageExtract
    roles: Dict[int, str]
    regions: List[_Region]
    stacks: List[List[Tuple[int, Line]]]
    zones: List[Tuple[Zone, List[TLine]]]
    orphans: List[TLine] = field(default_factory=list)


def _recover_glyphs(doc: pymupdf.Document, extract: DocExtract) -> None:
    try:
        from ..editable import glyphs
        glyphs.recover(doc, extract)
    except Exception as e:  # noqa: BLE001 — recovery is an improvement, never a failure
        logger.warning(f"layout: glyph recovery failed, continuing without it: {e}")


def _text_edges(z: Zone, rows: List[TLine], col_left: float, col_right: float) -> Tuple[float, float]:
    """The text edges of a zone: the body column for a full-width band; for one column of a
    two-column band, its own lines' (the zone's box takes in half the gutter)."""
    if z.of_columns == 1:
        return col_left, col_right
    long_rows = [r for r in rows if r.x1 - r.x0 >= 0.6 * (z.bbox[2] - z.bbox[0])]
    if not long_rows:
        return z.bbox[0], z.bbox[2]
    return min(r.x0 for r in long_rows), max(r.x1 for r in long_rows)


def _attach_orphans(p: PageExtract, excl: Set[Tuple[int, int]],
                    zones: List[Tuple[Zone, List[TLine]]]) -> List[TLine]:
    """
    Lines the row builder folded away: a drop cap is merged into the line beside it as a new line
    object, so its own index is in no row. It goes back to the first row level with it on its
    right; anything else left over becomes a row of its own (returned).
    """
    seen = {i for _z, rows in zones for r in rows for i in r.src}
    rest: List[TLine] = []
    for i, ln in enumerate(p.lines):
        if i in seen or (p.number, i) in excl or not ln.text.strip():
            continue
        # the row it was merged into starts where it starts; else the first row on its right
        beside = [r for _z, rows in zones for r in rows
                  if ln.bbox[1] - 2 <= r.top <= ln.bbox[3]
                  and (abs(r.x0 - ln.bbox[0]) <= 1 or r.x0 >= ln.bbox[2] - 2)]
        if beside:
            row = min(beside, key=lambda r: (r.top, r.x0))
            row.src.insert(0, i)
            # the text's own left edge: the lines under the initial line up with it, not with the cap
            own = [p.lines[j].bbox[0] for j in row.src if j != i and 0 <= j < len(p.lines)]
            if own:
                row.x0 = min(own)
            continue
        for r in C.rows_in_zone([(i, ln)]):
            r.page = p.number
            rest.append(r)
    return rest


def _zone_place(zones: List[Tuple[Zone, List[TLine]]], bbox: Rect) -> int:
    """The zone an object belongs to in reading order (its centre's), else the first zone below it."""
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    for zi, (z, _rows) in enumerate(zones):
        if z.bbox[1] - 2 <= cy <= z.bbox[3] + 2 and C.zone_captures_x(z, cx):
            return zi
    for zi, (z, _rows) in enumerate(zones):
        if z.bbox[1] >= cy and C.zone_captures_x(z, cx):
            return zi
    return len(zones)


def _page_blocks(w: _PageWork, ctx: _Ctx) -> Tuple[List[_Blk], List[_Blk]]:
    """The page's text blocks (zones, orphans, side notes) and its furniture blocks."""
    p = w.page
    blocks: List[_Blk] = []
    for zi, (z, rows) in enumerate(w.zones):
        left, right = _text_edges(z, rows, ctx.col_left, ctx.col_right)
        zb: List[_Blk] = []
        for grp in _group_zone(rows, ctx, left, right, p.height):
            b = _Blk(role="body", rows=grp, zone=zi, column=z.column if z.of_columns > 1 else 0,
                     wide=z.of_columns == 1, left=left, right=right)
            b.finish(p)
            _classify(b, ctx)
            zb.append(b)
        zb = _sections_and_lists(zb, p, ctx)
        _footnotes(zb, p, ctx)
        blocks.extend(zb)
    for row in w.orphans:
        b = _Blk(role="body", rows=[row], left=ctx.col_left, right=ctx.col_right)
        b.finish(p)
        b.zone = _zone_place(w.zones, b.bbox)
        blocks.append(b)
    for st in w.stacks:
        # a side callout reads as text of its own: grouped and classified like a zone
        rows = C.rows_in_zone(st)
        for r in rows:
            r.page = p.number
        left, right = min(r.x0 for r in rows), max(r.x1 for r in rows)
        for grp in _group_zone(rows, ctx, left, right, p.height):
            b = _Blk(role="body", rows=grp, note="side", left=left, right=right)
            b.finish(p)
            _classify(b, ctx)
            b.zone = _zone_place(w.zones, b.bbox)
            blocks.append(b)
    fb: List[_Blk] = []
    for i, role in w.roles.items():
        rows = C.rows_in_zone([(i, p.lines[i])])
        for r in rows:
            r.page = p.number
        b = _Blk(role=role, rows=rows, left=ctx.col_left, right=ctx.col_right)
        b.finish(p)
        fb.append(b)
    return blocks, fb


def _finish_page(layout: PageLayout, w: _PageWork, blocks: List[_Blk], furn: List[_Blk],
                 manifest: AssetManifest, ctx: _Ctx, scanned: bool) -> None:
    """Captions, placeholders, list depth, reading order, block dicts, margins and columns."""
    p = w.page
    pno = p.number
    _link_captions(blocks, w.regions, ctx)
    for r in w.regions:
        if r.decorative:
            continue
        role = {"image": "figure", "vector": "figure"}.get(r.kind, r.kind)
        ph = _Blk(role=role, bbox=r.bbox, ref=r.ref, zone=_zone_place(w.zones, r.bbox))
        if ph.zone < len(w.zones):
            z = w.zones[ph.zone][0]
            ph.column = z.column if z.of_columns > 1 else 0
            ph.wide = z.of_columns == 1
        blocks.append(ph)
    for zi in range(len(w.zones) + 1):
        _list_depths([b for b in blocks if b.zone == zi and b.rows])
    blocks.sort(key=lambda b: (b.zone, b.bbox[1], b.bbox[0]))
    heads = sorted((b for b in furn if b.bbox[1] < p.height / 2),
                   key=lambda b: (b.bbox[1], b.bbox[0]))
    foots = sorted((b for b in furn if b.bbox[1] >= p.height / 2),
                   key=lambda b: (b.bbox[1], b.bbox[0]))
    ordered = heads + blocks + foots

    out: List[Dict[str, Any]] = []
    prev: List[_Blk] = []
    for k, b in enumerate(ordered, start=1):
        d = _block_dict(p, b, p.width)
        d["id"] = f"p{pno}b{k}"
        # the gap to the block above it in its own column (a full-width band spans both)
        above = [o for o in prev if o.bbox[1] < b.bbox[1] - 0.1
                 and (o.wide or b.wide or o.column == b.column)]
        if above:
            gap = b.bbox[1] - max(o.bbox[3] for o in above)
            if gap > 0.05:
                d["gap_before"] = _r1(gap)
        prev.append(b)
        out.append(d)
    layout.blocks = out

    content = [b.bbox for b in blocks] + [r.bbox for r in w.regions if not r.decorative]
    if content:
        layout.margins = {"left": _r1(max(0.0, min(c[0] for c in content))),
                          "top": _r1(max(0.0, min(c[1] for c in content))),
                          "right": _r1(max(0.0, p.width - max(c[2] for c in content))),
                          "bottom": _r1(max(0.0, p.height - max(c[3] for c in content)))}
    else:
        m = p.margins
        layout.margins = {"left": _r1(m[0]), "top": _r1(m[1]), "right": _r1(m[2]), "bottom": _r1(m[3])}
    layout.columns = 2 if any(z.of_columns > 1 and rows for z, rows in w.zones) else 1
    layout.assets = [a.to_prompt() for a in manifest.for_page(pno)]
    layout.tables = [t.to_prompt() for t in manifest.tables_for_page(pno)]
    if not p.lines and (p.is_scanned or scanned):
        layout.warnings.append("Scanned page without a text layer: no text blocks.")


def build_layouts(extract: DocExtract, doc: pymupdf.Document, manifest: AssetManifest,
                  inspection: Inspection) -> List[PageLayout]:
    """
    One `PageLayout` per extracted page, blocks in reading order (see the module docstring).
    Sets `caption` on the manifest's assets and tables in place. Never raises for one bad page:
    that page gets an empty layout with a warning.
    """
    pages = extract.pages
    if not pages:
        return []
    _recover_glyphs(doc, extract)
    furn = F.detect(pages)
    col_left, col_right = C.body_column(pages, furn.furniture_line_ids)
    body_guess = C.body_size(pages)

    # pass 1: furniture, asset interiors, side notes, zones and rows
    work: Dict[int, _PageWork] = {}
    for p in pages:
        try:
            roles = _furniture_roles(p, furn, body_guess)
            regions = _regions(manifest, p.number)
            interior = _interior(p, regions, set(roles))
            excl = {(p.number, i) for i in set(roles) | interior}
            # pictures and tables are full width when they straddle the gutter (as the old engine)
            boxes = [r.bbox for r in regions] + [img.bbox for img in p.images if img.kind != "scan"
                                                 and (p.number, img.file) not in furn.image_keys]
            stacks = C.split_side_notes(p, excl, col_left, col_right, boxes)
            for st in stacks:
                excl.update((p.number, i) for i, _ln in st)
            zones = C.page_zones_and_rows(p, excl, col_left, col_right, boxes)
            orphans = _attach_orphans(p, excl, zones)
            work[p.number] = _PageWork(page=p, roles=roles, regions=regions, stacks=stacks, zones=zones,
                                       orphans=orphans)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"layout: page {p.number} analysis failed: {e}", exc_info=True)

    page_rows = {pno: [r for _z, rows in w.zones for r in rows] for pno, w in work.items()}
    profile = PRof.build_profile(pages, page_rows, col_left, col_right)
    ctx = _Ctx(profile, col_left, col_right)

    # pass 2: text blocks per zone, classified
    page_blocks: Dict[int, List[_Blk]] = {}
    furn_blocks: Dict[int, List[_Blk]] = {}
    for pno in list(work):
        try:
            page_blocks[pno], furn_blocks[pno] = _page_blocks(work[pno], ctx)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"layout: page {pno} blocks failed: {e}", exc_info=True)
            del work[pno]

    _assign_headings(page_blocks, ctx, {p.number: p.height for p in pages})

    # pass 3: captions, placeholders, reading order, dicts
    layouts: List[PageLayout] = []
    info = {pi.number: pi for pi in (inspection.pages if inspection else [])}
    for p in pages:
        pno = p.number
        layout = PageLayout(number=pno, width_pt=p.width, height_pt=p.height)
        pi = info.get(pno)
        if pi is not None and pi.ocr:
            layout.warnings.append("The text layer of this page comes from OCR: it may contain errors.")
        try:
            if pno not in work:
                raise RuntimeError("no analysis")
            _finish_page(layout, work[pno], page_blocks[pno], furn_blocks[pno], manifest, ctx,
                         bool(pi is not None and pi.scanned))
        except Exception as e:  # noqa: BLE001 — one bad page never fails the stage
            if pno in work:
                logger.warning(f"layout: page {pno} failed: {e}", exc_info=True)
            layout.blocks = []
            layout.warnings.append("Layout analysis failed for this page; no blocks were extracted.")
            layout.assets = [a.to_prompt() for a in manifest.for_page(pno)]
            layout.tables = [t.to_prompt() for t in manifest.tables_for_page(pno)]
        _fit_budget(layout)
        layouts.append(layout)
    return layouts
