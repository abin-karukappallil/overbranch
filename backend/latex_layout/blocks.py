"""
blocks.py — Text lines of a PDF page as TextBlocks, and source/output comparison.

A TextBlock is one visual line: its text, box, font size, weight and slant.
Comparing the blocks of an original PDF page with those of the page LaTeX
produced finds the differences that a word count or a pixel score cannot name:
a label that lost its bold, a line set larger than the original, a line that
now runs past the right edge it used to stop at.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

BOLD_NAME_RE = re.compile(r"(bold|black|heavy|semibold|demibold|demi|extrabold|ultrabold|[-,]bd\b|[-,]b\b)", re.I)
ITALIC_NAME_RE = re.compile(r"(italic|oblique|[-,]it\b|[-,]i\b)", re.I)

OVERFLOW_TOL = 1.5      # pt past the source right edge before a line counts as overflowing
SIZE_TOL = 0.6          # pt difference before a size counts as different


@dataclass
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    bold: bool
    italic: bool
    line: int  # index of the TextBlock (line) it belongs to


@dataclass
class TextBlock:
    text: str
    x: float
    y: float          # baseline
    width: float
    height: float
    font_size: float
    font_weight: str  # "bold" | "normal" | "mixed"
    italic: bool
    alignment: Optional[str] = None
    words: List[Word] = field(default_factory=list, repr=False)

    @property
    def x1(self) -> float:
        return self.x + self.width

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("words", None)
        d = {k: (round(v, 1) if isinstance(v, float) else v) for k, v in d.items()}
        return d


def span_is_bold(font: str, flags: int) -> bool:
    return bool(flags & 16) or bool(BOLD_NAME_RE.search(font.split("+")[-1]))


def span_is_italic(font: str, flags: int) -> bool:
    return bool(flags & 2) or bool(ITALIC_NAME_RE.search(font.split("+")[-1]))


def _norm_word(w: str) -> str:
    return re.sub(r"[^\w]", "", w.lower())


def text_blocks(page: Any, bold_override: Optional[Dict[Tuple[int, int], bool]] = None) -> List[TextBlock]:
    """
    TextBlocks of a PyMuPDF page, one per visual line, with per-word style.
    ``bold_override`` maps rounded span origins to a bold flag decided elsewhere
    (e.g. synthetic bold detected from the text render mode).
    """
    import pymupdf
    # Without the mediabox clip: text that runs off the page is exactly what an
    # overflow check must see, and the default extraction silently drops it.
    flags = pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_MEDIABOX_CLIP
    raw = page.get_text("rawdict", flags=flags)
    blocks: List[TextBlock] = []
    seen: List[Word] = []  # every word kept so far, to drop overprinted copies
    for b in raw.get("blocks", []):
        if b.get("type", 0) != 0:
            continue
        for ln in b.get("lines", []):
            words: List[Word] = []
            sizes: List[float] = []
            line_idx = len(blocks)
            for sp in ln.get("spans", []):
                font = sp.get("font", "")
                flags = int(sp.get("flags", 0))
                bold = span_is_bold(font, flags)
                origin = sp.get("origin")
                if bold_override and origin:
                    key = (round(origin[0]), round(origin[1]))
                    bold = bold_override.get(key, bold)
                italic = span_is_italic(font, flags)
                size = float(sp.get("size", 0.0))
                cur: List[Dict[str, Any]] = []
                for ch in sp.get("chars", []) + [None]:
                    if ch is None or not ch["c"].strip():
                        if cur:
                            text = "".join(c["c"] for c in cur)
                            words.append(Word(text, cur[0]["bbox"][0], cur[0]["bbox"][1], cur[-1]["bbox"][2],
                                              cur[-1]["bbox"][3], size, bold, italic, line_idx))
                            sizes.append(size)
                            cur = []
                        continue
                    cur.append(ch)
            # A word drawn again at (almost) the same spot is the same word —
            # producers fake bold this way — so keep one copy and call it bold.
            unique: List[Word] = []
            for w in words:
                tol = max(1.0, 0.12 * w.size)
                twin = next((k for k in seen if k.text == w.text and abs(k.x0 - w.x0) <= tol
                             and abs(k.y1 - w.y1) <= max(0.6, 0.06 * w.size)), None)
                if twin is not None:
                    twin.bold = True
                    continue
                seen.append(w)
                unique.append(w)
            words = unique
            if not words:
                continue
            x0 = min(w.x0 for w in words)
            x1 = max(w.x1 for w in words)
            y0 = min(w.y0 for w in words)
            y1 = max(w.y1 for w in words)
            n_bold = sum(1 for w in words if w.bold)
            weight = "bold" if n_bold == len(words) else ("normal" if n_bold == 0 else "mixed")
            spans = ln.get("spans") or [{}]
            baseline = max(float(s.get("origin", (0, y1))[1]) for s in spans)
            blocks.append(TextBlock(
                text=" ".join(w.text for w in words), x=x0, y=baseline, width=x1 - x0, height=y1 - y0,
                font_size=max(set(sizes), key=sizes.count) if sizes else 0.0,
                font_weight=weight, italic=all(w.italic for w in words), words=words,
            ))
    # An overprinted copy found later may have made an earlier line's words bold.
    for b in blocks:
        n_bold = sum(1 for w in b.words if w.bold)
        b.font_weight = "bold" if n_bold == len(b.words) else ("normal" if n_bold == 0 else "mixed")
    return blocks


def text_blocks_from_pdf(pdf_bytes: bytes, page_index: int = 0) -> Tuple[List[TextBlock], Tuple[float, float]]:
    """(blocks, (page_width, page_height)) for one page of a PDF given as bytes."""
    import pymupdf

    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        if page_index >= doc.page_count:
            return [], (0.0, 0.0)
        page = doc[page_index]
        return text_blocks(page), (page.rect.width, page.rect.height)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

@dataclass
class Mismatch:
    kind: str           # weight | italic | size | overflow_right | clipped
    text: str           # the source words concerned (a run, not a whole page)
    src: Dict[str, Any]
    out: Dict[str, Any]
    detail: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


MATCH_RADIUS = 160.0  # pt: a word further than this from its source position is a different word


def _match_words(src: List[Word], out: List[Word]) -> List[Tuple[Word, Word]]:
    """
    Pairs each source word with the nearest unused output word of the same text.

    Source and output share page coordinates (the import keeps paper size and
    margins), so position disambiguates repeated words ("Status" in two column
    headers) that in-order matching pairs with the wrong occurrence — and the
    output's reading order may differ from the source's anyway. Pairs are
    assigned closest-first, so one bad guess cannot steal a better match.
    """
    by_key: Dict[str, List[int]] = {}
    for j, w in enumerate(out):
        key = _norm_word(w.text)
        if key:
            by_key.setdefault(key, []).append(j)
    cands: List[Tuple[float, int, int]] = []
    for i, w in enumerate(src):
        for j in by_key.get(_norm_word(w.text), []):
            o = out[j]
            d = ((w.x0 - o.x0) ** 2 + (w.y1 - o.y1) ** 2) ** 0.5
            if d <= MATCH_RADIUS:
                cands.append((d, i, j))
    cands.sort()
    used_s, used_o = set(), set()
    pairs: List[Tuple[Word, Word]] = []
    for _d, i, j in cands:
        if i in used_s or j in used_o:
            continue
        used_s.add(i)
        used_o.add(j)
        pairs.append((src[i], out[j]))
    pairs.sort(key=lambda p: src.index(p[0]))
    return pairs


def _runs(pairs: List[Tuple[Word, Word]], pred) -> List[List[Tuple[Word, Word]]]:
    """Consecutive pairs (same source line) for which pred holds."""
    runs: List[List[Tuple[Word, Word]]] = []
    cur: List[Tuple[Word, Word]] = []
    for p in pairs:
        if not pred(p):
            if cur:
                runs.append(cur)
                cur = []
            continue
        if cur and cur[-1][0].line != p[0].line:
            runs.append(cur)
            cur = []
        cur.append(p)
    if cur:
        runs.append(cur)
    return runs


def compare_blocks(src: List[TextBlock], out: List[TextBlock],
                   page_size: Optional[Tuple[float, float]] = None) -> List[Mismatch]:
    """
    Differences between a source page and its re-typeset version that a
    targeted repair can act on. Weight / slant / size are compared per word and
    reported as runs of consecutive words on one source line; overflow is
    reported per output line that extends past the right edge of the source
    line its words came from.
    """
    src_words = [w for b in src for w in b.words]
    out_words = [w for b in out for w in b.words]
    pairs = _match_words(src_words, out_words)
    found: List[Mismatch] = []

    def run_text(run: List[Tuple[Word, Word]]) -> str:
        return " ".join(p[0].text for p in run)

    def where(run: List[Tuple[Word, Word]]) -> Dict[str, Any]:
        first = run[0][0]
        return {"line": src[first.line].text[:80], "x0": round(first.x0, 1), "y": round(src[first.line].y, 1)}

    for run in _runs(pairs, lambda p: p[0].bold and not p[1].bold):
        found.append(Mismatch("weight", run_text(run), {"bold": True, **where(run)},
                              {"bold": False}, "bold in the original, regular in the output"))
    for run in _runs(pairs, lambda p: p[0].italic and not p[1].italic):
        found.append(Mismatch("italic", run_text(run), {"italic": True, **where(run)}, {"italic": False},
                              "italic in the original, upright in the output"))
    def size_differs(p: Tuple[Word, Word]) -> bool:
        # The reported size of a horizontally condensed word shrinks with the
        # condensing; its height does not. Only a change in both is a real size change.
        hs, ho = p[0].y1 - p[0].y0, p[1].y1 - p[1].y0
        return abs(p[0].size - p[1].size) > SIZE_TOL and hs > 0 and abs(ho / hs - 1.0) > 0.12

    for run in _runs(pairs, size_differs):
        s, o = run[0][0].size, run[0][1].size
        found.append(Mismatch("size", run_text(run), {"size": round(s, 1), **where(run)}, {"size": round(o, 1)},
                              f"set at {o:.1f}pt instead of {s:.1f}pt"))

    # Overflow: per output line, the furthest right its words reach compared
    # with where those same words ended in the source.
    by_out_line: Dict[int, List[Tuple[Word, Word]]] = {}
    for p in pairs:
        by_out_line.setdefault(p[1].line, []).append(p)
    for out_line, ps in by_out_line.items():
        src_lines = {p[0].line for p in ps}
        src_right = max(src[i].x1 for i in src_lines)
        out_right = max(p[1].x1 for p in ps)
        # Relative slack too: TeX's interword spacing and kerning legitimately
        # differ from the PDF producer's by a point or two on a long line.
        tol = max(OVERFLOW_TOL, 0.01 * (src_right - min(src[i].x for i in src_lines)))
        if out_right > src_right + tol:
            sl = src[min(src_lines)]
            found.append(Mismatch(
                "overflow_right", " ".join(p[0].text for p in ps),
                {"x1": round(src_right, 1), "x0": round(sl.x, 1), "width": round(src_right - sl.x, 1),
                 "line": sl.text[:120], "y": round(sl.y, 1)},
                {"x1": round(out_right, 1), "x0": round(min(p[1].x0 for p in ps), 1),
                 "words": [[p[0].text, round(p[1].x0, 1)] for p in ps]},
                f"runs {out_right - src_right:.1f}pt past the original right edge"))
        if page_size and out_right > page_size[0] - 0.5:
            found.append(Mismatch("clipped", " ".join(p[0].text for p in ps), {}, {"x1": round(out_right, 1)},
                                  "text runs off the page"))
    return found
