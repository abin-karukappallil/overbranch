"""
pages.py — Page breaks and title pages.

Page-locked: every source page boundary is a hard break (\\sourcepage), so each source page's
content is set on the output page of the same number; the text flows freely inside its page.
The numbering plan (roman then arabic, restarts) rides on those breaks.
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

from ..models import PageExtract
from .model import (Block, EditProfile, Figure, Heading, PageMark, Para, TitlePage, TLine)
from .profile import row_align


def detect_title_page(page: PageExtract, rows: List[TLine], col_left: float, col_right: float,
                      profile: EditProfile) -> bool:
    text_rows = [r for r in rows if r.text.strip()]
    if not text_rows or len(text_rows) > 40:
        return False
    centered = sum(1 for r in text_rows if row_align(r, col_left, col_right, page.width) == "center")
    if centered < 0.55 * len(text_rows):
        return False
    # a page carrying a justified prose paragraph (a certificate's text) is not a title page
    full = [r for r in text_rows if r.x0 <= col_left + 4 and r.x1 >= col_right - 4]
    if len(full) > 2:
        return False
    sizes = [r.size for r in text_rows]
    big = sum(1 for s in sizes if s >= profile.body_size + 2)
    has_large = max(sizes) >= profile.body_size + 2 or big >= 2
    return has_large and len(text_rows) >= 3


def wrap_title_page(blocks: List[Block], page: int) -> List[Block]:
    """Replace the page's blocks with one TitlePage, keeping measured gaps between items."""
    page_blocks = [b for b in blocks if b.page == page]
    rest = [b for b in blocks if b.page != page]
    if not page_blocks:
        return blocks
    # vertical gap from each item to the next flowing item; side notes take no space of their own
    gaps = []
    for i, a in enumerate(page_blocks):
        if a.kind == "note":
            gaps.append(0.0)
            continue
        nxt = next((b for b in page_blocks[i + 1:] if b.kind != "note"), None)
        gaps.append(max(0.0, nxt.bbox[1] - a.bbox[3]) if nxt is not None else 0.0)
    tp = TitlePage(page=page, bbox=page_blocks[0].bbox, id=page_blocks[0].id,
                   content=page_blocks, gaps=gaps)
    at = next(i for i, b in enumerate(blocks) if b.page == page)
    return [b for b in blocks[:at] if b.page != page] + [tp] + [b for b in blocks[at:] if b.page != page]


def insert_page_marks(blocks: List[Block], pages: List[PageExtract],
                      page_rows: Dict[int, List[TLine]], profile: EditProfile,
                      pinned: Set[int], furniture) -> List[Block]:
    """Insert PageMark blocks at page boundaries, hard where the source clearly broke the page."""
    leading = profile.leading or 1.2 * profile.body_size
    # precompute per-page last content bottom and whether it ended early
    last_bottom: Dict[int, float] = {}
    for p in pages:
        rows = page_rows.get(p.number, [])
        last_bottom[p.number] = max((r.bottom for r in rows), default=0.0)
    seg_starts = {s["first_page"]: s for s in furniture.numbering_segments}

    out: List[Block] = []
    nid = max((b.id for b in blocks), default=0)
    # levels whose headings mostly open a page
    first_on_page: Dict[int, List[bool]] = {}
    seen: Set[int] = set()
    for b in blocks:
        if isinstance(b, Heading):
            first_on_page.setdefault(b.level, []).append(b.page not in seen)
        seen.add(b.page)
    page_levels = {lv for lv, firsts in first_on_page.items()
                   if len(firsts) >= 2 and sum(firsts) >= 0.6 * len(firsts)}
    # Page-locked: every source page boundary is a hard mark (\\sourcepage), so each source page's
    # content is set on the output page of the same number. The reasons the reflow mode used to
    # tell a forced break from a soft one are kept for the report.
    by_page: Dict[int, List[Block]] = {}
    order: List[int] = []
    for b in blocks:
        if b.page not in by_page:
            order.append(b.page)
        by_page.setdefault(b.page, []).append(b)
    numbers = [p.number for p in pages]
    for pno in sorted(set(order) - set(numbers)):
        numbers.append(pno)          # blocks of a page the extraction did not list (defensive)
    numbers = sorted(set(numbers))
    prev = None
    for pno in numbers:
        page_blocks = by_page.get(pno, [])
        if prev is not None:
            nid += 1
            reasons = ["source_page"]
            b = page_blocks[0] if page_blocks else None
            if isinstance(b, Heading) and (b.level == 0 or b.level in page_levels):
                reasons.append("chapter")
            elif isinstance(b, Para) and b.align == "center" and 1 <= len(b.lines) <= 2 \
                    and max(ln.size for ln in b.lines) >= profile.body_size + 2:
                reasons.append("display_title")
            p_prev = next((p for p in pages if p.number == prev), None)
            if p_prev is not None:
                text_bottom = p_prev.height - profile.margins["bottom"]
                text_h = p_prev.height - profile.margins["top"] - profile.margins["bottom"]
                if (text_bottom - last_bottom.get(prev, text_bottom)) >= max(0.2 * text_h, 4 * leading):
                    reasons.append("page_ended_early")
            if prev in pinned or pno in pinned:
                reasons.append("pinned")
            out.append(PageMark(page=pno, bbox=(b.bbox if b is not None else (0.0, 0.0, 0.0, 0.0)), id=nid,
                                hard=True, reasons=reasons, empty=not page_blocks))
        elif not page_blocks:
            # the document opens with an empty page: hold it with an empty box
            nid += 1
            out.append(PageMark(page=pno, id=nid, hard=False, reasons=["empty_first"], empty=True))
        out.extend(page_blocks)
        prev = pno
    return out


def apply_numbering(blocks: List[Block], pages: List[PageExtract], furniture) -> Dict:
    """
    Page numbers and running header/footer as the PDF has them, from the numbers it actually prints.

    Numbered pages are grouped into runs that count consistently (same style, value - page constant),
    so a document numbered i–vi then 1, 2, 3 … has two runs and a restart is a third. Unnumbered
    pages inside a run that open a chapter are left to the 'plain' page style (empty when those pages
    print nothing, as \\chapter pages use 'plain'); a run starts at the chapter that opens it, with the
    counter set so the first printed number comes out right. Each run start (and the start of an
    unnumbered stretch after a run) gets a hard break carrying the switch.

    Returns {"initial": (style, value, chrome) | None, "plain_empty": bool}.
    """
    nums = getattr(furniture, "page_numbers", {}) or {}
    chrome_pages = set(getattr(furniture, "header_pages", set())) | set(getattr(furniture, "footer_pages", set()))
    # chapter-opening pages: the page's first block is a top-level heading
    first: Dict[int, Block] = {}
    for b in blocks:
        if b.kind != "pagemark" and b.page not in first:
            first[b.page] = b
    chapter_open = {pg for pg, b in first.items() if isinstance(b, Heading) and b.level == 0}
    order = [p.number for p in pages]
    runs: List[Dict] = []
    for pg in order:
        if pg not in nums:
            continue
        style, val = nums[pg]
        off = val - pg
        if runs and runs[-1]["style"] == style and runs[-1]["off"] == off and \
                all(q in chapter_open or q in nums for q in range(runs[-1]["end"] + 1, pg)):
            runs[-1]["end"] = pg
            runs[-1]["pages"].append(pg)
        else:
            runs.append({"style": style, "off": off, "start": pg, "end": pg, "pages": [pg]})
    prev_end = 0
    for r in runs:
        s = r["start"]
        while s - 1 > prev_end and (s - 1) in chapter_open and (s - 1) not in nums:
            s -= 1
        r["start"] = s
        r["value"] = max(1, s + r["off"]) if r["style"] == "arabic" else max(1, s + r["off"])
        r["chrome"] = sum(1 for q in r["pages"] if q in chrome_pages) >= 0.5 * len(r["pages"])
        prev_end = r["end"]
    switches: Dict[int, Tuple] = {}
    for k, r in enumerate(runs):
        switches[r["start"]] = (r["style"], r["value"], r["chrome"])
        nxt = runs[k + 1]["start"] if k + 1 < len(runs) else None
        after = r["end"] + 1
        while after in chapter_open and after not in nums and (nxt is None or after < nxt):
            after += 1
        if after in order and (nxt is None or after < nxt) and after not in switches:
            switches[after] = ("none", 0, False)
    initial = None
    if order and order[0] in switches:
        initial = switches.pop(order[0])
    for b in blocks:
        if b.kind == "pagemark" and b.page in switches:
            b.numbering = switches[b.page][:2]
            b.chrome = switches[b.page][2]
            if not b.hard:
                b.hard = True
                b.reasons.append("numbering")
    inside = [pg for r in runs for pg in range(r["start"], r["end"] + 1) if pg in chapter_open]
    plain_empty = bool(inside) and sum(1 for pg in inside if pg not in nums) >= 0.5 * len(inside)
    return {"initial": initial, "plain_empty": plain_empty}
