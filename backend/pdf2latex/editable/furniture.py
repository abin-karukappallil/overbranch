"""
furniture.py — Running headers/footers, page numbers and numbering segments.

These must come out of the flowing text (a page number in the middle of a paragraph is the classic
reflow bug, and a footer counted as body text hides where each page really ends) and be reproduced
as a fancyhdr page style instead: the header's text and logo, the footer's text, the page number
where and how the PDF prints it. Pure over the extracted lines and images.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Set, Tuple

from ..models import Line, PageExtract
from .model import Furniture

_PAGENUM = re.compile(r"^\s*(?:page\s*)?(\d{1,4}|[ivxlcdm]{1,7})\s*(?:(?:of|/)\s*\d{1,4})?\s*$",
                      re.IGNORECASE)
_ROMAN_ONLY = re.compile(r"^[ivxlcdm]{1,7}$", re.IGNORECASE)


def _norm(text: str) -> str:
    t = text.strip().lower()
    t = re.sub(r"\b[ivxlcdm]+\b", "#", t)
    t = re.sub(r"\d+", "#", t)
    return re.sub(r"\s+", " ", t).strip()


def _roman_to_int(s: str) -> int:
    vals = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    total, prev = 0, 0
    for ch in reversed(s.lower()):
        v = vals.get(ch, 0)
        total += -v if v < prev else v
        prev = max(prev, v)
    return total


_EDGES: Dict[str, float] = {}


def _align(x0: float, x1: float, page_w: float) -> str:
    """L/C/R for a header or footer item: flush with the body text's left or right edge first
    (a two-line footer title starting at the margin is left-aligned even if it is long), then
    centred on the page."""
    left, right = _EDGES.get("left"), _EDGES.get("right")
    if left is not None and abs(x0 - left) <= 6 and not (right is not None and abs(x1 - right) <= 6
                                                         and x1 - x0 < 0.5 * page_w):
        return "L"
    if right is not None and abs(x1 - right) <= 6:
        return "R"
    cx = (x0 + x1) / 2
    if abs(cx - page_w / 2) <= 0.05 * page_w:
        return "C"
    return "L" if cx < page_w / 2 else "R"


def _body_edges(pages: List[PageExtract]) -> None:
    xs0: Counter = Counter()
    xs1: Counter = Counter()
    for p in pages:
        for ln in p.lines:
            if ln.text.strip() and 0.15 * p.height < ln.bbox[1] < 0.85 * p.height:
                xs0[round(ln.bbox[0])] += 1
                xs1[round(ln.bbox[2])] += 1
    _EDGES.clear()
    if xs0:
        _EDGES["left"] = float(xs0.most_common(1)[0][0])
    if xs1:
        _EDGES["right"] = float(xs1.most_common(1)[0][0])


def _style(ln: Line) -> Dict:
    from ..fontmap import editable_font
    sp = max(ln.spans, key=lambda s: len(s.text.strip()))
    _cls, family = editable_font(sp.font, sp.flags)
    return {"size": round(sp.size * 2) / 2, "color": sp.color, "bold": sp.bold, "italic": sp.italic,
            "family": family}


def detect(pages: List[PageExtract]) -> Furniture:
    n = len(pages)
    if n == 0:
        return Furniture()
    _body_edges(pages)
    # 1. band-limited candidate lines per page
    top_lines: Dict[int, List[Tuple[int, Line]]] = {}
    bot_lines: Dict[int, List[Tuple[int, Line]]] = {}
    for p in pages:
        tops = [ln.bbox[1] for ln in p.lines if ln.text.strip()]
        bots = [ln.bbox[3] for ln in p.lines if ln.text.strip()]
        if not tops:
            continue
        top_band = max(0.10 * p.height, min(tops) + 4)
        bot_band = min(0.90 * p.height, max(bots) - 4)
        tl, bl = [], []
        for i, ln in enumerate(p.lines):
            if not ln.text.strip():
                continue
            if ln.bbox[3] <= top_band:
                tl.append((i, ln))
            elif ln.bbox[1] >= bot_band:
                bl.append((i, ln))
        top_lines[p.number] = tl
        bot_lines[p.number] = bl

    thresh = max(2, int(round(0.4 * n)))
    furniture_ids: Set[Tuple[int, int]] = set()
    items: List[Dict] = []
    header_pages: Set[int] = set()
    footer_pages: Set[int] = set()

    # 2. repeated running header/footer text (same normalised text on ≥max(2, 40%) of pages)
    def repeated(sel: Dict[int, List[Tuple[int, Line]]], band: str) -> Optional[str]:
        sig_pages: Dict[str, Set[int]] = defaultdict(set)
        sig_items: Dict[str, List[Tuple[int, int, Line]]] = defaultdict(list)
        for pno, its in sel.items():
            for i, ln in its:
                norm = _norm(ln.text)
                if len(norm) >= 2 and not _PAGENUM.match(ln.text):
                    sig_pages[norm].add(pno)
                    sig_items[norm].append((pno, i, ln))
        chosen = None
        for sig, ps in sig_pages.items():
            if len(ps) < thresh:
                continue
            chosen = chosen or sig
            for pno, i, _ln in sig_items[sig]:
                furniture_ids.add((pno, i))
            (header_pages if band == "top" else footer_pages).update(ps)
            # the representative instance: the one on the first page carrying it
            pno, i, ln = min(sig_items[sig], key=lambda t: t[0])
            page_w = next(p.width for p in pages if p.number == pno)
            items.append({"band": band, "align": _align(ln.bbox[0], ln.bbox[2], page_w),
                          "text": ln.text.strip(), "y": ln.bbox[1], "bottom": ln.bbox[3],
                          "baseline": ln.baseline, **_style(ln)})
        return chosen

    header_sig = repeated(top_lines, "top")
    footer_sig = repeated(bot_lines, "bottom")

    # 3. page numbers: a number standing alone in its line inside a band. Other furniture lines
    # may share the band (a footer title beside the number), so the test is the sequence: the
    # values must count up from page to page, which a year or a stray figure does not.
    # every number-only line in a band is a candidate; a page's page number is the one whose value
    # keeps the document's usual offset from the page index (a "2024" in a short last page's top
    # band is a date, not page 2024)
    all_cand: Dict[int, List[Tuple[str, int, int, Line, str]]] = defaultdict(list)
    for p in pages:
        for band, sel in (("top", top_lines), ("bottom", bot_lines)):
            for i, ln in sel.get(p.number, []):
                if (p.number, i) in furniture_ids:
                    continue
                m = _PAGENUM.match(ln.text)
                if not m:
                    continue
                val = m.group(1)
                style = "roman" if _ROMAN_ONLY.match(val) else "arabic"
                num = _roman_to_int(val) if style == "roman" else int(val)
                all_cand[p.number].append((style, num, i, ln, band))
    offsets = Counter((c[0], c[1] - pno) for pno, cs in all_cand.items() for c in cs)
    cand: Dict[int, Tuple[str, int, int, Line, str]] = {}
    for pno, cs in all_cand.items():
        cand[pno] = max(cs, key=lambda c: (offsets[(c[0], c[1] - pno)], c[4] == "bottom"))
    nums = sorted(cand.items())
    pairs = [(a, b) for a, b in zip(nums, nums[1:]) if b[0] == a[0] + 1]
    rising = sum(1 for a, b in pairs if b[1][0] == a[1][0] and b[1][1] == a[1][1] + 1)
    valid = len(nums) >= 2 and (not pairs or rising >= 0.6 * len(pairs))
    page_num: Dict[int, Tuple[str, int]] = {}
    num_band, num_align, num_size = None, "C", 0.0
    if valid:
        bands, aligns, sizes = Counter(), Counter(), Counter()
        for pno, (style, num, i, ln, band) in nums:
            page_num[pno] = (style, num)
            furniture_ids.add((pno, i))
            page_w = next(p.width for p in pages if p.number == pno)
            bands[band] += 1
            aligns[_align(ln.bbox[0], ln.bbox[2], page_w)] += 1
            sizes[round(ln.spans[0].size * 2) / 2 if ln.spans else 0.0] += 1
        num_band = bands.most_common(1)[0][0]
        num_align = aligns.most_common(1)[0][0]
        num_size = sizes.most_common(1)[0][0]
        pno, (style, num, i, ln, band) = nums[0]
        # the words around the number ("Page 1 of 3" → "Page", "of 3") are printed with it
        text = ln.text.strip()
        ms = _PAGENUM.match(text)
        prefix, suffix = (text[:ms.start(1)], text[ms.end(1):]) if ms else ("", "")
        items.append({"band": band, "align": num_align, "page_number": True, "text": "",
                      "prefix": prefix, "suffix": suffix,
                      "y": ln.bbox[1], "bottom": ln.bbox[3], "baseline": ln.baseline, **_style(ln)})

    # 4. pictures repeated at the same place (a logo in the header)
    pic_pages: Dict[Tuple[int, int, int, int], Set[int]] = defaultdict(set)
    pic_files: Dict[Tuple[int, int, int, int], List[Tuple[int, str]]] = defaultdict(list)
    for p in pages:
        for img in p.images:
            key = tuple(int(round(v / 3)) for v in img.bbox)
            pic_pages[key].add(p.number)
            pic_files[key].append((p.number, img.file))
    image_keys: Set[Tuple[int, str]] = set()
    for key, ps in pic_pages.items():
        if len(ps) < thresh:
            continue
        image_keys.update(pic_files[key])
        pno, f = min(pic_files[key])
        img = next(i for p in pages if p.number == pno for i in p.images if i.file == f)
        page = next(p for p in pages if p.number == pno)
        band = "top" if img.bbox[1] < page.height / 2 else "bottom"
        (header_pages if band == "top" else footer_pages).update(ps)
        items.append({"band": band, "align": _align(img.bbox[0], img.bbox[2], page.width),
                      "image": f, "height": round(img.bbox[3] - img.bbox[1], 1),
                      "y": img.bbox[1], "bottom": img.bbox[3], "baseline": img.bbox[3]})

    # 5. rules repeated at the same place in the header or footer band (a header underline)
    rule_pages: Dict[Tuple[int, int, int], Set[int]] = defaultdict(set)
    rule_ex: Dict[Tuple[int, int, int], Tuple] = {}
    for p in pages:
        for d in p.drawings:
            if d.kind != "hrule":
                continue
            y = (d.rect[1] + d.rect[3]) / 2
            if 0.12 * p.height < y < 0.88 * p.height:
                continue
            key = (int(round(y / 2)), int(round(d.rect[0] / 3)), int(round(d.rect[2] / 3)))
            rule_pages[key].add(p.number)
            rule_ex.setdefault(key, (p, d))
    rule_keys: Set[Tuple[int, int]] = set()
    for key, ps in rule_pages.items():
        if len(ps) < thresh:
            continue
        p, d = rule_ex[key]
        y = (d.rect[1] + d.rect[3]) / 2
        band = "top" if y < p.height / 2 else "bottom"
        for pno in ps:
            rule_keys.add((pno, key[0]))
        items.append({"band": band, "rule": round(max(0.2, d.width or (d.rect[3] - d.rect[1])), 2),
                      "color": d.stroke or d.fill or (0, 0, 0), "y": y, "bottom": y, "baseline": y})

    # 6. numbering segments: a new segment at a style change or a non-consecutive value
    segments: List[Dict] = []
    prev_style = None
    prev_val = None
    for p in pages:
        style, val = page_num.get(p.number, ("none", None))
        reset = (style != prev_style) or (val is not None and prev_val is not None and val != prev_val + 1)
        if not segments or reset:
            segments.append({"first_page": p.number, "style": style, "start": val})
        prev_style, prev_val = style, val

    heads = [it for it in items if it["band"] == "top" and not it.get("rule")]
    foots = [it for it in items if it["band"] == "bottom" and not it.get("rule")]
    return Furniture(header_sig=header_sig, footer_sig=footer_sig, page_number_band=num_band,
                     page_number_align=num_align, page_number_size=num_size,
                     numbering_segments=segments, furniture_line_ids=furniture_ids,
                     items=items, header_pages=header_pages, footer_pages=footer_pages,
                     image_keys=image_keys, rule_keys=rule_keys, page_numbers=page_num,
                     header_bottom=max((it["bottom"] for it in heads), default=0.0),
                     footer_top=min((it["y"] for it in foots), default=0.0),
                     footer_baseline=min((it["baseline"] for it in foots), default=0.0))
