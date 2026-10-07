"""
overflow.py — Text that runs past where it should stop.

Three independent signals, because each misses cases the others catch:

* the log's ``Overfull \\hbox (Xpt too wide) … at lines a--b`` — exact, maps to
  source lines, but only covers boxes TeX itself built and knows the width of;
* glyphs past the page edge — always a defect, whatever the cause;
* lines past the page's text-area right edge, inferred from where most lines
  stop — catches \\makebox / \\hspace / tabular content TeX never warns about.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from .blocks import TextBlock, text_blocks_from_pdf

_RE_OVERFULL = re.compile(
    r"Overfull \\([hv])box \(([0-9.]+)pt too (?:wide|high)\)(?: in (paragraph|alignment) at lines (\d+)--(\d+)"
    r"| detected at line (\d+))?")

SEVERE_OVERFULL_PT = 2.0     # smaller overfull boxes are invisible in print
EDGE_TOL = 1.5


def parse_overfull(log: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for m in _RE_OVERFULL.finditer(log or ""):
        a = m.group(4) or m.group(6)
        b = m.group(5) or m.group(6)
        out.append({
            "box": f"{m.group(1)}box",
            "amount_pt": float(m.group(2)),
            "where": m.group(3) or ("line" if m.group(6) else None),
            "lines": [int(a), int(b)] if a else None,
            "severe": float(m.group(2)) >= SEVERE_OVERFULL_PT,
        })
    return out[:50]


def text_right_edge(blocks: List[TextBlock]) -> Optional[float]:
    """The x where most full-width lines stop (the text area's right edge), if there is one."""
    ends = Counter(round(b.x1) for b in blocks if b.width > 60)
    if not ends:
        return None
    edge, count = ends.most_common(1)[0]
    # Several lines must agree, otherwise there is no common right edge to hold to.
    if count < 3:
        return None
    # Include lines within 1pt of the mode (justified lines jitter by rounding).
    return float(max(e for e in ends if abs(e - edge) <= 1))


def detect_overflow(pdf_bytes: Optional[bytes], log: str = "",
                    text_box: Optional[Tuple[float, float]] = None, max_pages: int = 20) -> Dict[str, Any]:
    """
    Returns {overfull: [...], beyond_text_area: [...], beyond_page: [...], has_overflow}.
    ``text_box`` = (left, right) of the text area in pt, when known; otherwise
    the right edge is inferred per page from the lines themselves.
    """
    overfull = parse_overfull(log)
    beyond_area: List[Dict[str, Any]] = []
    beyond_page: List[Dict[str, Any]] = []
    if pdf_bytes:
        import pymupdf
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            n = min(doc.page_count, max_pages)
        for i in range(n):
            blocks, (pw, _ph) = text_blocks_from_pdf(pdf_bytes, i)
            right = text_box[1] if text_box else text_right_edge(blocks)
            for b in blocks:
                if b.x1 > pw - 0.5 or b.x < 0.5:
                    beyond_page.append({"page": i + 1, "text": b.text[:100], "x0": round(b.x, 1),
                                        "x1": round(b.x1, 1), "page_width": round(pw, 1)})
                elif right is not None and b.x1 > right + EDGE_TOL:
                    beyond_area.append({"page": i + 1, "text": b.text[:100], "x1": round(b.x1, 1),
                                        "right_edge": round(right, 1), "by_pt": round(b.x1 - right, 1)})
    severe = [o for o in overfull if o["severe"]]
    return {
        "overfull": overfull,
        "beyond_text_area": beyond_area[:40],
        "beyond_page": beyond_page[:40],
        "has_overflow": bool(severe or beyond_area or beyond_page),
    }
