"""
geometry.py — Targeted, deterministic repair of a compiled page against the PDF.

"It compiles and every word is there" says nothing about whether a bold label
stayed bold or a line still stops at the right edge it stopped at in the PDF.
After a page compiles, its TextBlocks are compared with the source page's
(latex_layout.blocks.compare_blocks) and each mismatch the LaTeX can be
corrected for locally is fixed in place — no LLM call, no regeneration:

    weight lost      → the run is wrapped in \\textbf{…}
    italic lost      → the run is wrapped in \\textit{…}
    right overflow   → the line is wrapped in \\obhfit{<width>}{…}
                       (condensed to the source width, only if still wider)

A run is only touched where it occurs exactly once in the body, so a repair
can never land on the wrong words. What cannot be fixed this way (size
differences, wrapping) is returned for the re-run note instead.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

from latex_layout.blocks import Mismatch, TextBlock, compare_blocks, text_blocks, text_blocks_from_pdf
from latex_layout.justify import hfit_line

from .texutil import latex_text

MAX_REPAIRS_PER_ROUND = 40


def source_blocks(doc: Any, page_number: int) -> Tuple[List[TextBlock], Tuple[float, float]]:
    """TextBlocks of the original page, with descriptor/synthetic bold applied."""
    from .fontmap import descriptor_bold_fonts, synthetic_bold_origins

    from .fontmap import outline_stroke_bold

    page = doc[page_number - 1]
    desc = descriptor_bold_fonts(doc, page)
    fake = synthetic_bold_origins(page) | outline_stroke_bold(page)[0]
    override = {}
    if desc or fake:
        for b in page.get_text("dict").get("blocks", []):
            for ln in b.get("lines", []):
                for sp in ln.get("spans", []):
                    o = sp.get("origin")
                    if not o:
                        continue
                    key = (round(o[0]), round(o[1]))
                    font = re.sub(r"^[A-Z]{6}\+", "", sp.get("font", ""))
                    if font in desc or key in fake:
                        override[key] = True
    return text_blocks(page, override or None), (page.rect.width, page.rect.height)


def _pattern(words: List[str]) -> Optional[re.Pattern]:
    """Matches the words as they appear in a LaTeX body: escaped, separated by blanks/~."""
    parts = [re.escape(latex_text(w)) for w in words if w.strip()]
    if not parts:
        return None
    sep = r"(?:\s|~|\\ )+"
    return re.compile(r"(?<![\w\\])" + sep.join(parts) + r"(?!\w)")


def _occurrence(words: List[str], where: dict, ordered: Optional[List[Tuple[str, float, float]]]) -> Optional[Tuple[int, int]]:
    """
    (index, total) of this phrase's occurrence among the source lines in reading
    order — the order the body was written in — located by the mismatch's position.
    """
    if not ordered or "y" not in where:
        return None
    pat = _pattern(words)
    phrase = " ".join(words)
    holders = [(i, x0, y) for i, (text, x0, y) in enumerate(ordered) if phrase in text]
    if not holders or pat is None:
        return None
    best = min(holders, key=lambda h: abs(h[2] - where["y"]) + 0.1 * abs(h[1] - where.get("x0", h[1])))
    if abs(best[2] - where["y"]) > 3.0:
        return None
    return [h[0] for h in holders].index(best[0]), len(holders)


def _unique_span(body: str, words: List[str], where: Optional[dict] = None,
                 ordered: Optional[List[Tuple[str, float, float]]] = None) -> Optional[Tuple[int, int]]:
    pat = _pattern(words)
    if pat is None:
        return None
    hits = list(pat.finditer(body))
    if len(hits) != 1:
        # Repeated phrase: the k-th source occurrence (reading order) is the k-th
        # in the body, but only when the counts agree.
        occ = _occurrence(words, where or {}, ordered) if len(hits) > 1 else None
        if occ is None or occ[1] != len(hits):
            return None
        hits = [hits[occ[0]]]
    m = hits[0]
    # Never wrap text that sits in a command's option list or a \definecolor etc.
    line_start = body.rfind("\n", 0, m.start()) + 1
    prefix = body[line_start:m.start()]
    if prefix.count("[") > prefix.count("]"):
        return None
    return m.start(), m.end()


def _is_wrapped(body: str, start: int, end: int, command: str) -> bool:
    return body[max(0, start - len(command) - 1):start] == command + "{" and body[end:end + 1] == "}"


def repair_body(body: str, mismatches: List[Mismatch],
                ordered: Optional[List[Tuple[str, float, float]]] = None) -> Tuple[str, List[str], List[Mismatch]]:
    """
    Applies the local repairs. ``ordered`` = the source lines in reading order as
    (text, x0, baseline), used to tell repeated phrases apart.
    Returns (new body, repair descriptions, unresolved mismatches).
    """
    edits: List[Tuple[int, int, str, str]] = []  # (start, end, replacement, description)
    unresolved: List[Mismatch] = []
    taken: List[Tuple[int, int]] = []

    def free(a: int, b: int) -> bool:
        return all(b <= s or a >= e for s, e in taken)

    for mm in mismatches:
        if len(edits) >= MAX_REPAIRS_PER_ROUND:
            unresolved.append(mm)
            continue
        words = mm.text.split()
        span = _unique_span(body, words, mm.src, ordered)
        x0_override = None
        if span is None and mm.kind == "overflow_right":
            # The whole line may be split by formatting commands in the body; the
            # part that overflows is its right end, so try the longest unique tail.
            placed = mm.out.get("words") or []
            for k in range(len(placed) - 1, 0, -1):
                tail = placed[-k:]
                span = _unique_span(body, [w for w, _x in tail], mm.src, ordered)
                if span is not None:
                    x0_override = tail[0][1]
                    break
        if span is None or not free(*span):
            unresolved.append(mm)
            continue
        a, b = span
        text = body[a:b]
        if mm.kind == "weight" and not _is_wrapped(body, a, b, "\\textbf"):
            edits.append((a, b, f"\\textbf{{{text}}}", f"bold restored: '{mm.text[:40]}'"))
        elif mm.kind == "italic" and not _is_wrapped(body, a, b, "\\textit"):
            edits.append((a, b, f"\\textit{{{text}}}", f"italic restored: '{mm.text[:40]}'"))
        elif mm.kind == "overflow_right":
            start_x = x0_override if x0_override is not None else mm.out.get("x0", mm.src.get("x0", 0))
            target = float(mm.src.get("x1", 0)) - float(start_x)
            if target <= 4:
                unresolved.append(mm)
                continue
            if "\\obhfit" in body[max(0, a - 40):a]:
                unresolved.append(mm)  # already condensed once; condensing again would compound
                continue
            edits.append((a, b, hfit_line(text, target), f"fitted to the right edge ({target:.0f}pt): '{mm.text[:40]}'"))
        else:
            unresolved.append(mm)
            continue
        taken.append((a, b))

    for a, b, repl, _desc in sorted(edits, key=lambda e: e[0], reverse=True):
        body = body[:a] + repl + body[b:]
    return body, [e[3] for e in edits], unresolved


def page_mismatches(src: List[TextBlock], page_size: Tuple[float, float], pdf: bytes) -> List[Mismatch]:
    out, _ = text_blocks_from_pdf(pdf, 0)
    return compare_blocks(src, out, page_size)


def fitted_texts(repairs: List[str]) -> List[str]:
    """Texts the repair condensed with \\obhfit (their reported font size shrinks with the condensing)."""
    out = []
    for r in repairs:
        m = re.match(r"fitted to the right edge \(\d+pt\): '(.*)'$", r)
        if m:
            out.append(m.group(1))
    return out


def drop_condensed_sizes(mismatches: List[Mismatch], fitted: List[str]) -> List[Mismatch]:
    """
    A horizontally condensed word reports a smaller font size (PyMuPDF derives the
    size from the text matrix), so a size "mismatch" on a line the repair fitted is
    the repair itself, not a defect.
    """
    if not fitted:
        return mismatches
    words = {w for t in fitted for w in t.split()}
    return [m for m in mismatches if not (m.kind == "size" and set(m.text.split()) <= words)]


def describe_unresolved(mismatches: List[Mismatch], limit: int = 12) -> str:
    """Concrete items for the LLM re-run note."""
    lines = []
    for mm in mismatches[:limit]:
        if mm.kind == "size":
            lines.append(f"- '{mm.text[:50]}' must be {mm.src.get('size')}pt (is {mm.out.get('size')}pt)")
        elif mm.kind == "weight":
            lines.append(f"- '{mm.text[:50]}' must be bold")
        elif mm.kind == "italic":
            lines.append(f"- '{mm.text[:50]}' must be italic")
        elif mm.kind in ("overflow_right", "clipped"):
            lines.append(f"- '{mm.text[:50]}' runs past its right edge ({mm.detail}); keep it within "
                         f"{mm.src.get('width', '?')}pt (use \\obhfit)")
    return "\n".join(lines)
