"""
inspect.py — Stage 1 of the AI rebuild: look at the source PDF before doing any work on it.

Reports page count, per-page size in points (as displayed, i.e. after /Rotate), how much text each
page really shows, which pages are scans (no text, page-sized picture), and a coarse `doc_type`
(paper / slides / form / report) from deterministic signals only. No LLM, no network.

Nothing here modifies the source: pages with /Rotate are normalised on an in-memory copy so the
text geometry used for the signals is in the displayed orientation, exactly as the later stages see it.
"""

from __future__ import annotations

import re
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Tuple, Union

import pymupdf

from ..extract import PdfValidationError, normalize_rotation
from .model import Inspection, PageInfo

# --- scanned-page rule: the same numbers as extract._is_scanned ------------------------------
SCANNED_MAX_CHARS = 20
SCANNED_MIN_IMAGE_COVERAGE = 0.5

HUGE_PAGE_PT = 2000.0           # either side (A0 is 2384 x 3370; ordinary pages are < 1200)
TINY_PAGE_PT = 72.0
SAMPLE_PAGES = 20               # pages that feed the doc_type signals (char counts cover all pages)

# slides: every page landscape, text big relative to the page, few words per page
PAPER_MAX_PAGES = 30          # abstract + references beyond this many pages is a report
SLIDE_LANDSCAPE = 1.15          # width / height (same ratio as editable.run's deck check)
SLIDE_MIN_FONT_RATIO = 0.028    # median font size / page height (Beamer 4:3 ~0.040, A4 landscape 12pt ~0.020)
SLIDE_MAX_WORDS = 150           # median words per page

# forms
FORM_MIN_WIDGETS = 3
FORM_MIN_LABELS = 8             # "Name:" style lines
FORM_MIN_FIELD_BOXES = 6        # empty stroked boxes / underscore leaders next to those labels

# two-column body
COLUMN_MIN_LINES = 6            # lines needed in each column on a page
COLUMN_MAX_SPANNING = 0.25      # share of lines allowed to straddle the gutter (title, abstract, figure captions)

_LABEL_RE = re.compile(r"^[A-Za-z][\w /().,'&-]{0,40}:\s*(?:_{2,}|\.{3,}|\s)*$")
_FIELD_LEADER_RE = re.compile(r"_{4,}|\.{6,}")
_ABSTRACT_RE = re.compile(r"^(?:\d+\.?\s*|[IVX]+\.?\s*)?abstract\s*(?:[-—–.:]|$)", re.I)
_REFERENCES_RE = re.compile(
    r"^(?:\d+\.?\s*|[IVX]+\.?\s*)?(?:references|bibliography|literature cited|works cited)\s*:?$", re.I)


class PdfInspectError(PdfValidationError):
    """The source cannot be processed at all; the route maps it to HTTP 400."""


class EncryptedPdfError(PdfInspectError):
    """The PDF needs a password."""


# ---------------------------------------------------------------------------
# Per-page measurements
# ---------------------------------------------------------------------------

def _area(b) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _largest_image_coverage(page: "pymupdf.Page") -> float:
    """Share of the page covered by its largest picture (clipped to the page)."""
    area = page.rect.width * page.rect.height
    if area <= 0:
        return 0.0
    best = 0.0
    try:
        infos = page.get_image_info()
    except Exception:
        return 0.0
    for info in infos:
        r = pymupdf.Rect(info["bbox"]) & page.rect
        if not r.is_empty:
            best = max(best, _area(r))
    return best / area


def _invisible_origins(page: "pymupdf.Page") -> set:
    """Rounded origins of the first glyph of spans drawn invisibly (render mode 3 or fully transparent)."""
    keys = set()
    try:
        for tr in page.get_texttrace():
            if tr.get("type") == 3 or (tr.get("opacity") is not None and tr.get("opacity") <= 0.01):
                chars = tr.get("chars") or []
                if chars:
                    ox, oy = chars[0][2]
                    keys.add((round(ox, 1), round(oy, 1)))
    except Exception:
        pass
    return keys


class _PageText:
    """The visible text lines of one page: (text, bbox, font size) plus the hidden character count."""

    def __init__(self) -> None:
        self.lines: List[Tuple[str, Tuple[float, float, float, float]]] = []
        self.chars = 0
        self.hidden_chars = 0
        self.sizes: List[Tuple[float, int]] = []    # (font size, characters)


def _read_text(page: "pymupdf.Page", check_hidden: bool) -> _PageText:
    out = _PageText()
    flags = pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP
    try:
        raw = page.get_text("dict", flags=flags)
    except Exception:
        return out
    hidden_keys = _invisible_origins(page) if check_hidden else set()
    for block in raw.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for ln in block.get("lines", []):
            parts: List[str] = []
            for sp in ln.get("spans", []):
                text = sp.get("text", "")
                n = len(text.strip())
                if not n:
                    continue
                origin = sp.get("origin") or (sp["bbox"][0], sp["bbox"][3])
                hidden = ((round(origin[0], 1), round(origin[1], 1)) in hidden_keys
                          or sp.get("alpha", 255) == 0)
                if hidden:
                    out.hidden_chars += n
                    continue
                out.chars += n
                out.sizes.append((float(sp.get("size", 10.0)), n))
                parts.append(text)
            text = "".join(parts).strip()
            if text:
                out.lines.append((text, tuple(ln["bbox"])))
    return out


def _is_scanned(width: float, height: float, visible_chars: int, image_coverage: float) -> bool:
    """extract._is_scanned, restated on plain numbers: little visible text under a page-sized picture."""
    return width * height > 0 and visible_chars < SCANNED_MAX_CHARS \
        and image_coverage >= SCANNED_MIN_IMAGE_COVERAGE


# ---------------------------------------------------------------------------
# Document type
# ---------------------------------------------------------------------------

def _weighted_median(pairs: List[Tuple[float, int]]) -> float:
    pairs = sorted(pairs)
    total = sum(n for _s, n in pairs)
    if total <= 0:
        return 0.0
    acc = 0
    for size, n in pairs:
        acc += n
        if acc * 2 >= total:
            return size
    return pairs[-1][0]


def _two_column(page: "pymupdf.Page", text: _PageText) -> bool:
    """A body of lines that sit wholly in a left or a right half, with few lines across the gutter."""
    mid = page.rect.width / 2
    left = right = span = 0
    for t, (x0, _y0, x1, _y1) in text.lines:
        if len(t) < 20:
            continue
        if x0 < mid - 8 and x1 > mid + 8:
            span += 1
        elif x1 <= mid + 8:
            left += 1
        elif x0 >= mid - 8:
            right += 1
    total = left + right + span
    return left >= COLUMN_MIN_LINES and right >= COLUMN_MIN_LINES and span <= COLUMN_MAX_SPANNING * total


def _field_boxes(page: "pymupdf.Page") -> int:
    """Empty stroked rectangles shaped like a fill-in field (wide, one text line tall)."""
    n = 0
    try:
        drawings = page.get_drawings()
    except Exception:
        return 0
    for d in drawings:
        r = d.get("rect")
        if r is None or d.get("fill") not in (None, (1.0, 1.0, 1.0)):
            continue
        if d.get("color") is None:
            continue
        if 40 <= r.width <= 400 and 8 <= r.height <= 40:
            n += 1
    return n


def _classify(doc: "pymupdf.Document", pages: List[PageInfo], texts: Dict[int, _PageText]
              ) -> Tuple[str, Dict[str, Any]]:
    sample = [p.number for p in pages[:SAMPLE_PAGES]]
    sizes: List[Tuple[float, int]] = []
    words_per_page: List[int] = []
    labels = leaders = abstract = references = 0
    col_pages = text_pages = 0
    for n in sample:
        t = texts[n]
        sizes.extend(t.sizes)
        if t.chars:
            text_pages += 1
        words_per_page.append(sum(len(s.split()) for s, _b in t.lines))
        for s, _b in t.lines:
            if _LABEL_RE.match(s):
                labels += 1
            if _FIELD_LEADER_RE.search(s):
                leaders += 1
            if _ABSTRACT_RE.match(s):
                abstract += 1
            if _REFERENCES_RE.match(s):
                references += 1
        if t.chars >= 400 and _two_column(doc[n - 1], t):
            col_pages += 1
    # references usually sit past the sample on a long paper; look at the tail pages as well
    for p in pages[SAMPLE_PAGES:][-5:]:
        t = texts[p.number]
        references += sum(1 for s, _b in t.lines if _REFERENCES_RE.match(s))

    widgets = 0
    for n in sample:
        try:
            widgets += sum(1 for _w in doc[n - 1].widgets())
        except Exception:
            break
    boxes = 0
    if labels >= FORM_MIN_LABELS:
        boxes = sum(_field_boxes(doc[n - 1]) for n in sample[:5])

    font_ratio = 0.0
    if sizes:
        heights = median(p.height_pt for p in pages) or 1.0
        font_ratio = _weighted_median(sizes) / heights
    median_words = int(median(words_per_page)) if words_per_page else 0
    landscape = all(p.width_pt > p.height_pt * SLIDE_LANDSCAPE for p in pages)

    signals: Dict[str, Any] = {
        "landscape": landscape, "font_ratio": round(font_ratio, 4), "median_words": median_words,
        "widgets": widgets, "labels": labels, "field_boxes": boxes + leaders,
        "two_column_pages": col_pages, "text_pages": text_pages,
        "abstract": abstract > 0, "references": references > 0,
    }

    if len(pages) >= 2 and landscape and font_ratio >= SLIDE_MIN_FONT_RATIO and 0 < median_words <= SLIDE_MAX_WORDS:
        return "slides", signals
    if widgets >= FORM_MIN_WIDGETS or (labels >= FORM_MIN_LABELS and boxes + leaders >= FORM_MIN_FIELD_BOXES):
        return "form", signals
    two_col = text_pages > 0 and col_pages * 2 >= text_pages
    # A book-length document with an abstract and references is a (project/thesis) report, not a paper:
    # it takes \chapter-style structure, which steers the model's document class.
    if two_col or (abstract and references and len(pages) <= PAPER_MAX_PAGES):
        return "paper", signals
    return "report", signals


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _open(source: Union[Path, str, bytes]) -> "pymupdf.Document":
    if isinstance(source, (bytes, bytearray)):
        if not source or not bytes(source).lstrip()[:5].startswith(b"%PDF-"):
            raise PdfInspectError("File is not a PDF (missing %PDF- header).")
        opener = lambda: pymupdf.open(stream=bytes(source), filetype="pdf")  # noqa: E731
    else:
        path = Path(source)
        if not path.is_file():
            raise PdfInspectError(f"PDF not found: {path.name}")
        with open(path, "rb") as fh:
            if not fh.read(1024).lstrip()[:5].startswith(b"%PDF-"):
                raise PdfInspectError("File is not a PDF (missing %PDF- header).")
        opener = lambda: pymupdf.open(str(path), filetype="pdf")  # noqa: E731
    try:
        doc = opener()
    except Exception as e:
        raise PdfInspectError(f"PDF could not be parsed: {e}") from e
    if doc.needs_pass:
        doc.close()
        raise EncryptedPdfError("PDF is password-protected.")
    if doc.page_count == 0:
        doc.close()
        raise PdfInspectError("PDF has no pages.")
    return doc


def inspect_pdf(source: Union[Path, str, bytes]) -> Inspection:
    """
    Inspects a PDF given as a path or as bytes.

    Raises `PdfInspectError` (a `PdfValidationError`) for non-PDF, unparseable or empty input and
    `EncryptedPdfError` for password-protected input; both are client errors (HTTP 400). Everything
    else that is merely odd (huge or tiny pages, no text at all) comes back in `Inspection.warnings`.
    """
    doc = _open(source)
    try:
        normalize_rotation(doc)
        pages: List[PageInfo] = []
        texts: Dict[int, _PageText] = {}
        for i, page in enumerate(doc):
            n = i + 1
            w, h = float(page.rect.width), float(page.rect.height)
            coverage = _largest_image_coverage(page)
            # invisible text only matters on pages that could be scans (text drawn over a big picture)
            t = _read_text(page, check_hidden=coverage >= SCANNED_MIN_IMAGE_COVERAGE)
            texts[n] = t
            scanned = _is_scanned(w, h, t.chars, coverage)
            pages.append(PageInfo(
                number=n, width_pt=round(w, 2), height_pt=round(h, 2), chars=t.chars, scanned=scanned,
                # a scan that already carries an invisible text layer needs no OCR of ours
                ocr=scanned and t.hidden_chars >= SCANNED_MAX_CHARS, hidden_chars=t.hidden_chars))

        doc_type, signals = _classify(doc, pages, texts)
        warnings: List[str] = []
        huge = [p.number for p in pages if max(p.width_pt, p.height_pt) > HUGE_PAGE_PT]
        if huge:
            warnings.append(f"Very large page size on page(s) {_fmt_pages(huge)} "
                            f"(up to {max(max(p.width_pt, p.height_pt) for p in pages):.0f} pt); "
                            "rendering and the model's view of them will be coarse.")
        tiny = [p.number for p in pages if min(p.width_pt, p.height_pt) < TINY_PAGE_PT]
        if tiny:
            warnings.append(f"Very small page size on page(s) {_fmt_pages(tiny)}.")
        if sum(p.chars + p.hidden_chars for p in pages) == 0 and not any(p.scanned for p in pages):
            warnings.append("The PDF has no extractable text and no scanned pages (vector outlines or pictures only).")
        return Inspection(page_count=len(pages), pages=pages, doc_type=doc_type, warnings=warnings,
                          signals=signals)
    finally:
        doc.close()


def _fmt_pages(nums: List[int], limit: int = 8) -> str:
    shown = ", ".join(str(n) for n in nums[:limit])
    return shown + (f" and {len(nums) - limit} more" if len(nums) > limit else "")
