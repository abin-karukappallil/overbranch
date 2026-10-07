"""
facts.py — Compact per-page facts for the LLM, and the deterministic layout fallback.

Coordinates are pt relative to the top-left of the LaTeX text area (the preamble's
geometry margins) so gaps translate directly into \\vspace / \\hspace. Text is
pre-escaped for pdfLaTeX, and colors use the preamble's color names.
"""

from typing import Any, Dict, List, Optional, Set, Tuple

from .models import Line, PageExtract, Span
from .preamble import FontPlan, Geometry, color_name, family_of, font_class
from .texutil import fmt, latex_text

MAX_LINES = 700
MAX_SHAPES = 150
MAX_MARKS = 60
ASCENT = 0.8      # fraction of the font size from a line's top to its baseline, for most text fonts
NATURAL_LEAD = 1.2  # the leading the prompt asks for: \fontsize{sz}{1.2 sz}
MIN_GAP = 1.5     # extra space below this is ordinary leading jitter, not a deliberate gap
SIDE_OVERLAP = 0.25  # a side block may be overlapped this much by the body before it counts as inline
SIDE_EDGE_TOL = 6.0  # pt: blocks starting this close to a side block share its margin column


def _r(v: float) -> float:
    return round(v * 2) / 2


def _style(sp: Span) -> Tuple:
    return (_r(sp.size), color_name(sp.color), sp.bold, sp.italic, family_of(font_class(sp.font, sp.flags)), sp.superscript)


def _runs(ln: Line) -> List[Tuple[Tuple, str, float]]:
    """Adjacent spans with the same style merged: (style, raw text, x of first glyph)."""
    runs: List[Tuple[Tuple, str, float]] = []
    for sp in ln.spans:
        if runs and (not sp.text.strip() or _style(sp) == runs[-1][0]):
            style, text, x = runs[-1]
            runs[-1] = (style, text + sp.text, x)
        else:
            runs.append((_style(sp), sp.text, sp.origin[0]))
    return [(s, t, x) for s, t, x in runs if t.strip()]


def _alignment(x0: float, x1: float, text_w: float) -> Optional[str]:
    if abs((x0 + x1) / 2 - text_w / 2) <= max(3.0, 0.02 * text_w) and x0 > 0.05 * text_w:
        return "c"
    if abs(x1 - text_w) <= max(3.0, 0.015 * text_w) and x0 > 0.25 * text_w:
        return "r"
    return None


def _two_columns(entries: List[Dict[str, Any]], text_w: float) -> bool:
    left = [e for e in entries if e["x"] + e["w"] <= 0.55 * text_w]
    right = [e for e in entries if e["x"] >= 0.45 * text_w]
    n = max(1, len(entries))
    return len(left) >= 5 and len(right) >= 5 and len(left) / n >= 0.3 and len(right) / n >= 0.3


def _blocks(lines: List[Line]) -> Dict[int, Dict[str, float]]:
    """Per reading-order region: its box and whether it sits beside another region."""
    boxes: Dict[int, Dict[str, float]] = {}
    for ln in lines:
        b = boxes.setdefault(ln.column, {"x0": ln.bbox[0], "y0": ln.bbox[1], "x1": ln.bbox[2], "y1": ln.bbox[3]})
        b["x0"], b["y0"] = min(b["x0"], ln.bbox[0]), min(b["y0"], ln.bbox[1])
        b["x1"], b["y1"] = max(b["x1"], ln.bbox[2]), max(b["y1"], ln.bbox[3])
    for b in boxes.values():
        h = max(1.0, b["y1"] - b["y0"])
        w = max(1.0, b["x1"] - b["x0"])
        b["side"] = 1.0 if any(
            other is not b
            and (min(b["y1"], other["y1"]) - max(b["y0"], other["y0"])) > 0.5 * h   # shares vertical space
            # ...but barely any horizontal space. A margin column usually clears the body by a
            # visible gutter, though a stray wide line can poke into it, so allow a little overlap.
            and (min(b["x1"], other["x1"]) - max(b["x0"], other["x0"])) < SIDE_OVERLAP * w
            and (other["x1"] - other["x0"]) > w                                     # and is the wider one
            for other in boxes.values()) else 0.0

    # A margin column is usually several blocks stacked down one edge, and the lowest of them may
    # hang below the body and so share vertical space with nothing. Blocks that start at the same
    # x as a known side block belong to the same column.
    edges = [b["x0"] for b in boxes.values() if b["side"]]
    for b in boxes.values():
        if not b["side"] and any(abs(b["x0"] - e) <= SIDE_EDGE_TOL for e in edges):
            b["side"] = 1.0
    return boxes


FIT_TOLERANCE = 1.02  # a line measuring wider than its source by more than this gets a fit width


def _metrics_family(family: str, fonts: FontPlan) -> str:
    """The font class that will actually set text of ``family`` under this preamble."""
    if family == fonts.main_family:
        return fonts.main
    return {"sans": fonts.sans, "mono": "courier"}.get(family, "times")


def _fit_width(ln: Line, fonts: FontPlan, src_w: float) -> Optional[float]:
    """
    The source width when this line, set in the substitute font, would come out
    wider than it is in the PDF (so it would run past its right edge). Measured
    with the TeX font files themselves (latex_layout.metrics).
    """
    if src_w <= 0:
        return None
    try:
        from latex_layout.metrics import text_width
        width = 0.0
        for (size, _c, bold, italic, family, _sup), text, _x in _runs(ln):
            width += text_width(text, _metrics_family(family, fonts), size, bold, italic)
    except Exception:
        return None
    if width > src_w * FIT_TOLERANCE + 0.5:
        return _r(src_w + 0.5)
    return None


def page_facts(page: PageExtract, geom: Geometry, fonts: FontPlan, n_pages: int,
               default_color: str) -> Tuple[Dict[str, Any], Set[str]]:
    """Returns (facts dict, characters that could not be represented in pdfLaTeX)."""
    ox, oy = geom.left, geom.top
    unknown: Set[str] = set()
    entries: List[Dict[str, Any]] = []
    prev_baseline: Optional[float] = None
    prev_column: Optional[int] = None
    boxes = _blocks(page.lines[:MAX_LINES])
    side_blocks = 0
    for ln in page.lines[:MAX_LINES]:
        runs = []
        for (size, color, bold, italic, family, sup), text, _x in _runs(ln):
            run: Dict[str, Any] = {"t": latex_text(text, unknown), "sz": size}
            if color != default_color:
                run["c"] = color
            if bold:
                run["b"] = 1
            if italic:
                run["i"] = 1
            if family != fonts.main_family:
                run["f"] = family
            if sup:
                run["sup"] = 1
            runs.append(run)
        if not runs:
            continue
        x0, x1 = ln.bbox[0] - ox, ln.bbox[2] - ox
        baseline = ln.baseline - oy
        entry: Dict[str, Any] = {"x": _r(x0), "y": _r(baseline), "w": _r(x1 - x0)}
        # The vertical space to put BEFORE this line, already worked out. y is a baseline, and a
        # baseline is not where \vspace takes effect: deriving one from the other needs the font's
        # ascent and the leading, so asking the model to do it made every page drift downwards.
        size = max(runs[0]["sz"], 1.0)
        if ln.column != prev_column:
            # A new region: the previous line is somewhere else on the page, so the distance
            # between the two baselines is not a gap to typeset. Emitting one anyway is what
            # put a \vspace{-222pt} in front of a margin note and dropped it over the title.
            box = boxes.get(ln.column, {})
            entry["nb"] = 1
            entry["top"] = _r(baseline - ASCENT * size)
            if box.get("side"):
                entry["side"] = 1
                entry["bw"] = _r(box["x1"] - box["x0"])
                side_blocks += 1
        elif prev_baseline is not None:
            gap = baseline - prev_baseline - NATURAL_LEAD * size
            if abs(gap) >= MIN_GAP:
                entry["gap"] = _r(gap)
        prev_baseline, prev_column = baseline, ln.column
        if len(runs) == 1:
            entry.update(runs[0])
        else:
            entry["runs"] = runs
        al = _alignment(x0, x1, geom.text_w)
        if al:
            entry["al"] = al
        fit = _fit_width(ln, fonts, x1 - x0)
        if fit:
            entry["fit"] = fit
        entries.append(entry)

    images = []
    for im in page.images:
        item = {"file": im.file, "x": _r(im.bbox[0] - ox), "y": _r(im.bbox[1] - oy),
                "w": _r(im.bbox[2] - im.bbox[0]), "h": _r(im.bbox[3] - im.bbox[1])}
        if im.kind != "image":
            item["kind"] = im.kind
        images.append(item)

    shapes, marks = [], []
    for d in sorted(page.drawings, key=lambda d: -(d.rect[2] - d.rect[0]) * max(1.0, d.rect[3] - d.rect[1])):
        box = {"x": _r(d.rect[0] - ox), "y": _r(d.rect[1] - oy),
               "w": _r(d.rect[2] - d.rect[0]), "h": _r(d.rect[3] - d.rect[1])}
        if d.complex:
            if len(marks) < MAX_MARKS:
                marks.append({"k": "mark", **box, "c": color_name(d.fill or d.stroke)})
            continue
        if len(shapes) >= MAX_SHAPES:
            continue
        shape: Dict[str, Any] = {"k": d.kind, **box}
        if d.kind in ("hrule", "vrule"):
            shape["lw"] = _r(d.width) or 0.5
            shape["c"] = color_name(d.stroke)
        else:
            if d.fill is not None:
                shape["fill"] = color_name(d.fill)
            if d.stroke is not None:
                shape["stroke"] = color_name(d.stroke)
                shape["lw"] = _r(d.width) or 0.5
        shapes.append(shape)

    facts: Dict[str, Any] = {
        "page": page.number,
        "of": n_pages,
        "text_area_pt": {"w": _r(geom.text_w), "h": _r(geom.text_h)},
        "main_family": fonts.main_family,
        "body_size": fonts.body_size,
        "default_color": default_color,
        "lines": entries,
    }
    if images:
        facts["images"] = images
    if shapes:
        facts["shapes"] = shapes
    if marks:
        facts["marks"] = marks
    if page.background:
        facts["background"] = "Vector artwork is already placed behind this page automatically; do not reproduce it."
    if side_blocks:
        facts["layout_hint"] = "side_blocks"
    elif _two_columns(entries, geom.text_w):
        facts["layout_hint"] = "two_column"
    dropped = len(page.lines) - MAX_LINES
    if dropped > 0:
        facts["truncated_lines"] = dropped
    return facts, unknown


# ---------------------------------------------------------------------------
# Deterministic fallback: every word, image and rule at its measured position
# ---------------------------------------------------------------------------

_FAMILY_CMD = {"serif": "\\rmfamily", "sans": "\\sffamily", "mono": "\\ttfamily"}


def fallback_body(page: PageExtract, geom: Geometry, fonts: FontPlan) -> str:
    """Positioned TikZ layout of the page facts. Compiles reliably; used when the LLM path fails."""
    ox, oy = geom.left, geom.top
    out = [
        "\\noindent\\begin{tikzpicture}[x=1bp,y=-1bp,inner sep=0pt,outer sep=0pt]",
        f"\\useasboundingbox (0,0) rectangle ({fmt(geom.text_w)},{fmt(max(1.0, geom.text_h - 1))});",
    ]
    for d in page.drawings:
        if d.complex:
            continue
        x0, y0, x1, y1 = (fmt(d.rect[0] - ox), fmt(d.rect[1] - oy), fmt(d.rect[2] - ox), fmt(d.rect[3] - oy))
        if d.kind in ("hrule", "vrule") or (d.fill is not None and d.stroke is None):
            out.append(f"\\fill[{color_name(d.fill or d.stroke)}] ({x0},{y0}) rectangle ({x1},{y1});")
        else:
            opts = [f"draw={color_name(d.stroke)}", f"line width={fmt(max(d.width, 0.3))}bp"]
            if d.fill is not None:
                opts.insert(0, f"fill={color_name(d.fill)}")
            out.append(f"\\path[{','.join(opts)}] ({x0},{y0}) rectangle ({x1},{y1});")
    for im in page.images:
        out.append(f"\\node[anchor=north west] at ({fmt(im.bbox[0] - ox)},{fmt(im.bbox[1] - oy)}) "
                   f"{{\\includegraphics[width={fmt(im.bbox[2] - im.bbox[0])}bp,"
                   f"height={fmt(im.bbox[3] - im.bbox[1])}bp]{{{im.file}}}}};")
    hidden = ",text opacity=0" if page.is_scanned else ""
    for ln in page.lines:
        y = fmt(ln.baseline - oy)
        for (size, color, bold, italic, family, sup), text, x in _runs(ln):
            font = f"\\fontsize{{{fmt(size)}bp}}{{{fmt(size * 1.2)}bp}}\\selectfont{_FAMILY_CMD[family]}"
            font += ("\\bfseries" if bold else "") + ("\\itshape" if italic else "")
            out.append(f"\\node[anchor=base west,text={color},font={{{font}}}{hidden}] "
                       f"at ({fmt(x - ox)},{y}) {{{latex_text(text.strip())}}};")
    out.append("\\end{tikzpicture}")
    return "\n".join(out)
