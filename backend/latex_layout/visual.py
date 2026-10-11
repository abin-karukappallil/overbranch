"""
latex_layout/visual.py — Defects a reader sees and a width measurement does not
================================================================================
``issues.py`` measures whether content fits: margins, tables, the page bottom.
The requests this module serves are about how a page *looks* — "the title is
on top of the picture", "I can't read the text on this slide" — and those are
different measurements over the same rendered page:

* ``TEXT_OVERLAP``    — two words printed over each other.
* ``ELEMENT_OVERLAP`` — text straddling the edge of an image, or two images
  intersecting. Text lying *entirely* on an image is a caption on a background,
  which is a design; text crossing its edge is almost never one.
* ``OFF_PAGE``        — an image extending past the page.
* ``LOW_CONTRAST``    — text whose colour is too close to what is behind it,
  measured from the rendered pixels (WCAG contrast ratio).

These are reported, never repaired automatically: there is no closed set of
safe fixes for "these overlap" the way there is for an overfull line — moving
the title, shrinking the image and changing the colour are all plausible, and
which one is right is a decision about the content.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from .issues import LayoutIssue

logger = logging.getLogger("latex_layout.visual")

TEXT_OVERLAP = "TEXT_OVERLAP"
ELEMENT_OVERLAP = "ELEMENT_OVERLAP"
OFF_PAGE = "OFF_PAGE"
LOW_CONTRAST = "LOW_CONTRAST"

WORD_OVERLAP_SHARE = 0.35     # of the smaller word's area, before two words count as overprinted
IMAGE_STRADDLE_MIN = 0.15     # share of a text line that must be inside the image…
IMAGE_STRADDLE_MAX = 0.85     # …and outside it, to count as crossing its edge
IMAGE_OVERLAP_SHARE = 0.10
CONTRAST_UNREADABLE = 1.6     # WCAG ratio below which text is effectively invisible
CONTRAST_POOR = 2.5           # …and below which it is hard to read (WCAG AA asks for 4.5)
CONTRAST_DPI = 72
MAX_PER_KIND = 8

BBox = Tuple[float, float, float, float]
_RE_WORDY = re.compile(r"[A-Za-z0-9]{2,}")


def _area(b: BBox) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _inter(a: BBox, b: BBox) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _region(b: BBox) -> Tuple[float, float, float, float]:
    return (b[0], b[1], b[2] - b[0], b[3] - b[1])


def _lines(page: Any) -> List[Dict[str, Any]]:
    """Text lines with their bbox and dominant colour."""
    out: List[Dict[str, Any]] = []
    try:
        blocks = page.get_text("dict").get("blocks", [])
    except Exception as e:  # noqa: BLE001
        logger.debug(f"get_text failed: {e}")
        return out
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            main = max(spans, key=lambda s: len(s.get("text", "")))
            out.append({
                "text": " ".join(s["text"].strip() for s in spans),
                "bbox": tuple(line["bbox"]),
                "color": int(main.get("color") or 0),
                "size": float(main.get("size") or 0.0),
            })
    return out


def _word_overlaps(page: Any, page_no: int) -> List[LayoutIssue]:
    try:
        words = [w for w in page.get_text("words") if _RE_WORDY.search(w[4] or "")]
    except Exception:  # noqa: BLE001
        return []
    words.sort(key=lambda w: w[1])
    # The whole line each word sits in: that is what the source has, and what a reader would quote.
    line_text: Dict[Tuple[int, int], str] = {}
    for w in sorted(words, key=lambda w: (w[5], w[6], w[7])):
        line_text[(w[5], w[6])] = (line_text.get((w[5], w[6]), "") + " " + w[4]).strip()
    issues: List[LayoutIssue] = []
    seen: set = set()
    for i, a in enumerate(words):
        abox = (a[0], a[1], a[2], a[3])
        for b in words[i + 1:]:
            if b[1] >= a[3]:
                break  # sorted by top: nothing further down can intersect
            bbox = (b[0], b[1], b[2], b[3])
            inter = _inter(abox, bbox)
            if inter <= 0:
                continue
            smaller = min(_area(abox), _area(bbox))
            if smaller <= 0 or inter / smaller < WORD_OVERLAP_SHARE:
                continue
            # The same word drawn twice at the same place is faked bold, not a collision.
            if a[4] == b[4] and abs(a[0] - b[0]) < 1.5 and abs(a[1] - b[1]) < 1.5:
                continue
            # Same line of the same block: kerning / ligature boxes, not a collision.
            if a[5] == b[5] and a[6] == b[6]:
                continue
            key = (a[5], a[6], b[5], b[6])
            if key in seen:
                continue
            seen.add(key)
            union = (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))
            first, second = line_text[(a[5], a[6])], line_text[(b[5], b[6])]
            issues.append(LayoutIssue(
                page=page_no, type=TEXT_OVERLAP, severity="high",
                description=f"Text is printed over other text: “{first[:60]}” overlaps “{second[:60]}”.",
                text=first, region=_region(union),
                evidence={"other_text": second, "overlap_share": round(inter / smaller, 2)}))
            if len(issues) >= MAX_PER_KIND:
                return issues
    return issues


def _image_boxes(page: Any) -> List[BBox]:
    boxes: List[BBox] = []
    try:
        for info in page.get_image_info():
            b = tuple(info["bbox"])
            if (b[2] - b[0]) >= 12 and (b[3] - b[1]) >= 12:
                boxes.append(b)
    except Exception:  # noqa: BLE001
        pass
    return boxes


def _element_overlaps(page: Any, page_no: int, lines: List[Dict[str, Any]]) -> List[LayoutIssue]:
    pw, ph = page.rect.width, page.rect.height
    images = _image_boxes(page)
    issues: List[LayoutIssue] = []

    for img in images:
        over = max(0.0 - img[0], img[2] - pw, 0.0 - img[1], img[3] - ph)
        if over > 2.0:
            issues.append(LayoutIssue(
                page=page_no, type=OFF_PAGE, severity="high",
                description=f"An image extends {over:.0f}pt past the page edge and is cut off.",
                region=_region(img), evidence={"by_pt": round(over, 1)}))

    # An image covering nearly the whole page is a background; text on it is by design.
    content_images = [i for i in images if _area(i) < 0.7 * pw * ph]
    for ln in lines:
        lb = ln["bbox"]
        la = _area(lb)
        if la <= 0 or not _RE_WORDY.search(ln["text"]):
            continue
        for img in content_images:
            share = _inter(lb, img) / la
            if IMAGE_STRADDLE_MIN <= share <= IMAGE_STRADDLE_MAX:
                issues.append(LayoutIssue(
                    page=page_no, type=ELEMENT_OVERLAP, severity="high",
                    description=f"Text crosses the edge of an image ({share:.0%} of the line is on top of it).",
                    text=ln["text"], region=_region(lb),
                    evidence={"share_on_image": round(share, 2), "image_region": [round(v, 1) for v in _region(img)]}))
                break
        if len(issues) >= MAX_PER_KIND:
            break

    for i, a in enumerate(content_images):
        for b in content_images[i + 1:]:
            inter = _inter(a, b)
            smaller = min(_area(a), _area(b))
            if smaller > 0 and IMAGE_OVERLAP_SHARE <= inter / smaller <= 0.95:
                issues.append(LayoutIssue(
                    page=page_no, type=ELEMENT_OVERLAP, severity="medium",
                    description=f"Two images overlap ({inter / smaller:.0%} of the smaller one is covered).",
                    region=_region((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))),
                    evidence={"overlap_share": round(inter / smaller, 2)}))
    return issues


def _luminance(rgb: Tuple[float, float, float]) -> float:
    def channel(v: float) -> float:
        v = v / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    """WCAG contrast ratio of two sRGB colours (1 = identical, 21 = black on white)."""
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _hex(rgb: Tuple[float, float, float]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(int(round(c)) for c in rgb))


def _low_contrast(page: Any, page_no: int, lines: List[Dict[str, Any]]) -> List[LayoutIssue]:
    """Text against the pixels actually behind it."""
    try:
        import numpy as np
        import pymupdf
        pix = page.get_pixmap(dpi=CONTRAST_DPI, colorspace=pymupdf.csRGB, alpha=False)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    except Exception as e:  # noqa: BLE001 — contrast is a bonus measurement
        logger.debug(f"Contrast check skipped: {e}")
        return []
    scale = CONTRAST_DPI / 72.0
    issues: List[LayoutIssue] = []
    for ln in lines:
        text = ln["text"]
        if len(text.strip()) < 3 or not _RE_WORDY.search(text):
            continue
        x0, y0, x1, y1 = (int(v * scale) for v in ln["bbox"])
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(pix.width, x1 + 1), min(pix.height, y1 + 1)
        if x1 - x0 < 3 or y1 - y0 < 3:
            continue
        patch = img[y0:y1, x0:x1].reshape(-1, 3).astype(float)
        c = ln["color"]
        fg = (float((c >> 16) & 255), float((c >> 8) & 255), float(c & 255))
        # Ink is the minority of a line's box, so the pixels far from the text colour
        # are the background; their median is robust to anti-aliasing.
        dist = np.abs(patch - np.array(fg)).sum(axis=1)
        far = patch[dist > 48]
        if len(far) < 0.25 * len(patch):
            bg = tuple(np.median(patch, axis=0))   # the box is nearly one colour: the text's own
        else:
            bg = tuple(np.median(far, axis=0))
        ratio = contrast_ratio(fg, bg)
        if ratio >= CONTRAST_POOR:
            continue
        issues.append(LayoutIssue(
            page=page_no, type=LOW_CONTRAST,
            severity="high" if ratio < CONTRAST_UNREADABLE else "medium",
            description=(f"Text is {'nearly invisible' if ratio < CONTRAST_UNREADABLE else 'hard to read'}: "
                         f"{_hex(fg)} on {_hex(bg)} (contrast {ratio:.1f}:1; readable text needs at least 4.5:1)."),
            text=text, region=_region(ln["bbox"]),
            evidence={"text_color": _hex(fg), "background": _hex(bg), "contrast": round(ratio, 2)}))
        if len(issues) >= MAX_PER_KIND:
            break
    return issues


RUNNING_BAND = 0.12       # top / bottom share of the page where a theme's own lines live
RUNNING_SHARE = 0.3       # of the pages a line must recur on
RUNNING_SCAN_PAGES = 40


def _running_key(line: Dict[str, Any]) -> Tuple[int, str]:
    text = re.sub(r"#+", "#", re.sub(r"\d+", "#", line["text"].strip()))[:40]
    return (round(line["bbox"][3] / 3.0), text)


def _running_lines(doc: Any) -> set:
    """
    Lines a theme prints on page after page — a navigation bar's section names, a
    footline, a page number. Their colours are the theme's choice (a navigation bar
    dims the sections you are not in on purpose), so they are not judged for contrast.
    """
    n = min(doc.page_count, RUNNING_SCAN_PAGES)
    if n < 2:
        return set()
    counts: Dict[Tuple[int, str], int] = {}
    for i in range(n):
        page = doc[i]
        ph = page.rect.height
        keys = set()
        for ln in _lines(page):
            b = ln["bbox"]
            if len(ln["text"]) <= 40 and (b[3] >= ph * (1 - RUNNING_BAND) or b[1] <= ph * RUNNING_BAND):
                keys.add(_running_key(ln))
        for k in keys:
            counts[k] = counts.get(k, 0) + 1
    need = max(2, int(n * RUNNING_SHARE + 0.999))
    return {k for k, c in counts.items() if c >= need}


def detect_visual_issues(pdf_bytes: Optional[bytes], pages: List[int]) -> List[LayoutIssue]:
    """Overlap, off-page and contrast defects of the given 1-based pages."""
    if not pdf_bytes:
        return []
    import pymupdf

    issues: List[LayoutIssue] = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        try:
            running = _running_lines(doc)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"Could not determine running lines: {e}")
            running = set()
        for n in pages:
            if not (1 <= n <= doc.page_count):
                continue
            page = doc[n - 1]
            try:
                lines = _lines(page)
                issues.extend(_word_overlaps(page, n))
                issues.extend(_element_overlaps(page, n, lines))
                issues.extend(_low_contrast(page, n, [ln for ln in lines if _running_key(ln) not in running]))
            except Exception as e:  # noqa: BLE001 — one odd page must not fail the tool
                logger.warning(f"Visual check failed on page {n}: {e}")
    return issues
