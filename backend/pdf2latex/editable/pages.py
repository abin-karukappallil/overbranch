"""
pages.py — Page breaks and title pages.

Reflowed text flows freely; this module decides where to force a page break so the output keeps the
source's page structure (chapters, pages that ended early, numbering resets, pinned pages) without
locking every page 1:1.
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
    seen_pages: Set[int] = set()
    cur_page = None
    for b in blocks:
        if isinstance(b, TitlePage):
            out.append(b)
            cur_page = b.page
            seen_pages.add(b.page)
            continue
        if b.page != cur_page:
            if cur_page is not None:
                nid += 1
                reasons = []
                hard = False
                # 1. new page starts with a chapter-level heading, or one in a style that opens
                # pages (ABSTRACT, CONTENTS, REFERENCES … each on a page of its own)
                if isinstance(b, Heading) and (b.level == 0 or b.level in page_levels):
                    hard = True; reasons.append("chapter")
                # … or with a centred display line in no heading style (a one-off "CERTIFICATE")
                elif isinstance(b, Para) and b.align == "center" and 1 <= len(b.lines) <= 2 \
                        and max(ln.size for ln in b.lines) >= profile.body_size + 2:
                    hard = True; reasons.append("display_title")
                # 2. previous page ended early
                p_prev = next((p for p in pages if p.number == cur_page), None)
                if p_prev is not None:
                    text_bottom = p_prev.height - profile.margins["bottom"]
                    text_h = p_prev.height - profile.margins["top"] - profile.margins["bottom"]
                    early = (text_bottom - last_bottom.get(cur_page, text_bottom)) >= max(0.2 * text_h, 4 * leading)
                    if early and not getattr(b, "joins_prev", False):
                        hard = True; reasons.append("page_ended_early")
                # 3. pinned pages
                if cur_page in pinned or b.page in pinned:
                    hard = True; reasons.append("pinned")
                numbering = None     # set by apply_numbering()
                pm = PageMark(page=b.page, bbox=b.bbox, id=nid, hard=hard, reasons=reasons,
                              numbering=numbering)
                out.append(pm)
            cur_page = b.page
            seen_pages.add(b.page)
        out.append(b)
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
