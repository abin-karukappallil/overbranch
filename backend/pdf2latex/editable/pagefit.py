"""
pagefit.py — The measured compile passes of an editable conversion, shared by the job and the CLI.

    compile_with_repair → calibrate_heading_spacing → page fit (overflow loop) → (gates, polish)

The job runs them through the shared compile queue (``pipeline.compile_tex``); the CLI through
``sync_compile_tex`` (pdflatex in the output directory). Both count their compiles, so a CLI run
measures exactly what production does.
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from .model import EditDoc, LineMap

logger = logging.getLogger("pdf2latex.editable.pagefit")

MAX_FIT_ROUNDS = 5


class Counter:
    """Wraps a compile_tex coroutine and counts the compiles."""

    def __init__(self, compile_tex: Callable[..., Awaitable]):
        self.inner = compile_tex
        self.n = 0

    async def __call__(self, ctx, tex: str, timeout: int):
        self.n += 1
        return await self.inner(ctx, tex, timeout)


def sync_compile_tex(ctx, tex: str, timeout: int) -> Tuple[Optional[bytes], str]:
    """pdflatex in ctx.out_dir, strict as the job's compile: a PDF made despite errors fails."""
    out = Path(ctx.out_dir)
    (out / "main.tex").write_text(tex, encoding="utf-8")
    pdf = out / "main.pdf"
    if pdf.exists():
        pdf.unlink()
    try:
        r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error",
                            "main.tex"], cwd=str(out), capture_output=True, text=True,
                           timeout=timeout, errors="replace")
        log = r.stdout
    except subprocess.TimeoutExpired:
        return None, "Compilation timed out."
    errors = [ln for ln in log.splitlines() if ln.startswith("!") or re.search(r"\.tex:\d+:", ln)]
    if r.returncode != 0 or errors or not pdf.exists():
        return None, log
    return pdf.read_bytes(), log


async def async_sync_compile(ctx, tex: str, timeout: int):
    return await asyncio.to_thread(sync_compile_tex, ctx, tex, timeout)


async def finish(ctx, extract, doc: EditDoc, tex: str, lm: LineMap,
                 compile_tex: Callable[..., Awaitable]) -> Tuple[str, LineMap, Optional[bytes], Dict]:
    """Compile (repairing), calibrate the measured spacing, fit every source page to its page.
    Returns (tex, line map, pdf or None, info) where info counts the compiles and the fit rounds."""
    from . import gates as G
    from .emit import emit_document
    from .run import calibrate_heading_spacing
    cc = compile_tex if isinstance(compile_tex, Counter) else Counter(compile_tex)
    info: Dict = {}
    timeout = G.MERGE_TIMEOUT_BASE + 6 * max(1, doc.page_count)
    tex, pdf = await G.compile_with_repair(ctx, tex, doc, lm, cc)
    if pdf is None:
        info["compiles"] = cc.n
        return tex, lm, None, info
    tex, lm = emit_document(doc)      # the line map of what compiled (repair may have re-emitted)
    if await asyncio.to_thread(calibrate_heading_spacing, doc, pdf):
        tex2, lm2 = emit_document(doc)
        pdf2, _log = await cc(ctx, tex2, timeout)
        if pdf2 is not None:
            tex, lm, pdf = tex2, lm2, pdf2
    tex, lm, pdf, fitted = await fit(ctx, doc, tex, lm, pdf, cc, timeout)
    info["fit"] = fitted
    info["compiles"] = cc.n
    return tex, lm, pdf, info


# ---------------------------------------------------------------------------
# The overflow fit loop
# ---------------------------------------------------------------------------

_SNAP_ATTRS = ("space_before", "space_exact", "kern", "looseness", "topsep", "counter")


def _walk(blocks):
    for b in blocks:
        yield b
        for attr in ("content", "beside"):
            inner = getattr(b, attr, None)
            if inner:
                yield from _walk(inner)


def _snapshot(doc: EditDoc):
    import copy
    state = []
    for b in _walk(doc.blocks):
        state.append((b, {a: getattr(b, a) for a in _SNAP_ATTRS if hasattr(b, a)}))
    return state, copy.deepcopy(doc.page_fit)


def _restore(doc: EditDoc, snap) -> None:
    state, pf = snap
    for b, attrs in state:
        for a, v in attrs.items():
            setattr(b, a, v)
    doc.page_fit = pf


def _page_blocks(doc: EditDoc) -> Dict[int, List]:
    out: Dict[int, List] = {}
    for b in doc.blocks:
        if b.kind in ("pagemark", "note"):
            continue
        out.setdefault(b.page, []).append(b)
    return out


def _text_len(p) -> int:
    return sum(len(ln.text) for ln in getattr(p, "lines", []))


def _rung_spacing(doc: EditDoc, blocks: List, undo: List) -> float:
    """Rung 1: the page's measured gaps (space above blocks, the heading spacing, list spacing)
    shrink to a third. Returns the predicted gain, pt."""
    from .model import Heading, ListBlock, TitlePage
    gain = 0.0
    levels = {lv["level"]: lv for lv in doc.profile.heading_levels}
    for i, b in enumerate(blocks):
        if isinstance(b, TitlePage):
            continue
        if isinstance(b, Heading):
            if i == 0 or b.starts_page:
                continue
            lv = levels.get(b.level) or {}
            before = (lv.get("space_before") or 0.0) + (b.kern or 0.0)
            if before > 3:
                undo.append((b, "kern", b.kern))
                b.kern = round((b.kern or 0.0) - 2 * before / 3, 1)
                gain += 2 * before / 3
            continue
        if getattr(b, "joins_prev", False) or getattr(b, "anchor_bottom", None) is not None:
            continue
        if b.space_before and b.space_before > 3:
            undo.append((b, "space_before", b.space_before))
            undo.append((b, "space_exact", b.space_exact))
            new = round(b.space_before / 3, 1)
            gain += b.space_before - new
            b.space_before = new
            b.space_exact = True
        if isinstance(b, ListBlock) and b.topsep and b.topsep > 2:
            undo.append((b, "topsep", b.topsep))
            new = round(b.topsep / 3, 1)
            gain += 2 * (b.topsep - new)
            b.topsep = new
    return gain


def _rung_looseness(doc: EditDoc, blocks: List, need: float, undo: List) -> float:
    """Rung 2: \\looseness=-1 on the page's longest paragraphs (TeX sets them a line shorter
    where it can)."""
    from .model import Para
    lead = doc.profile.leading or 12.0
    paras = sorted((b for b in blocks if isinstance(b, Para) and len(b.lines) >= 3 and not b.looseness
                    and b.align in ("justify", "left")), key=_text_len, reverse=True)
    n = min(len(paras), max(1, int(need // lead) + 2))
    for p in paras[:n]:
        undo.append((p, "looseness", p.looseness))
        p.looseness = -1
    return 0.5 * n * lead          # TeX finds a shorter setting for about half of them


def _rung_stretch(doc: EditDoc, pno: int, blocks: List, undo: List) -> float:
    """Rung 3: the page's line pitch 3% tighter (\\setstretch, never the font size)."""
    pf = doc.page_fit.setdefault(pno, {})
    if pf.get("stretch"):
        return 0.0
    undo.append(("fit", pno, "stretch", None))
    pf["stretch"] = 0.97
    m = doc.profile.margins
    height = (doc.profile.paper_pt[1] - m["top"] - m["bottom"]) if doc.profile.paper_pt else 600.0
    return 0.03 * height


def _rung_enlarge(doc: EditDoc, pno: int, undo: List) -> float:
    """Rung 4: \\enlargethispage by at most one line and never into the footer."""
    pf = doc.page_fit.setdefault(pno, {})
    if pf.get("enlarge"):
        return 0.0
    lead = doc.profile.leading or 12.0
    ph = doc.profile.paper_pt[1] if doc.profile.paper_pt else 842.0
    text_bottom = ph - doc.profile.margins["bottom"]
    furn = doc.furniture
    if furn is not None and furn.footer_top:
        room = furn.footer_top - 2 - text_bottom
        if furn.footer_baseline:
            room = min(room, furn.footer_baseline - 8.0 - text_bottom)
    else:
        room = ph - 12.0 - text_bottom
    x = min(lead, room)
    if x < 2.0:
        return 0.0
    undo.append(("fit", pno, "enlarge", None))
    pf["enlarge"] = round(x, 1)
    return x


def _undo(doc: EditDoc, undo: List) -> None:
    for rec in reversed(undo):
        if rec[0] == "fit":
            _f, pno, key, old = rec
            pf = doc.page_fit.setdefault(pno, {})
            if old is None:
                pf.pop(key, None)
            else:
                pf[key] = old
        else:
            obj, attr, old = rec
            setattr(obj, attr, old)


def _climb(doc: EditDoc, pno: int, blocks: List, need: float) -> bool:
    """Apply the next useful rung for a spilled page. Returns whether anything changed."""
    st = doc.page_fit.setdefault(pno, {})
    while st.get("rung", 0) < 4:
        rung = st.get("rung", 0)
        st["rung"] = rung + 1
        undo: List = []
        if rung == 0:
            gain = _rung_spacing(doc, blocks, undo)
        elif rung == 1:
            gain = _rung_looseness(doc, blocks, need, undo)
        elif rung == 2:
            gain = _rung_stretch(doc, pno, blocks, undo)
        else:
            gain = _rung_enlarge(doc, pno, undo)
        if not undo:
            continue
        if gain < 1.0:
            _undo(doc, undo)          # predicted to do nothing: skip the rung
            continue
        st.setdefault("undo", []).append(undo)
        return True
    st["accepted"] = True             # rung 5: the spill stays, and is reported
    return False


def _revert_last(doc: EditDoc, pno: int) -> bool:
    st = doc.page_fit.get(pno) or {}
    stack = st.get("undo") or []
    if not stack:
        return False
    _undo(doc, stack.pop())
    return True


def _figure_corrections(doc: EditDoc, fp: Dict, over: Dict[int, float], landing: Dict[int, int]) -> int:
    """Move each picture on a page that fits (and starts where it should) by its measured
    vertical error, through its exact space above."""
    from .model import Figure
    by_file: Dict[str, Figure] = {}
    for b in doc.blocks:
        if isinstance(b, Figure):
            for img in b.images:
                by_file.setdefault(img, b)
    n = 0
    done = set()
    for it in (fp or {}).get("items", []):
        if not it.get("found") or it.get("ok"):
            continue
        pno = it["page"]
        f = by_file.get(it["file"])
        if f is None or id(f) in done or pno in over or landing.get(pno) != pno:
            continue
        if it.get("out_page") != pno:
            continue
        dy = it.get("dy") or 0.0
        if abs(dy) <= 2.0:
            continue
        done.add(id(f))
        f.space_before = round((f.space_before or 0.0) - dy, 1)
        f.space_exact = True
        n += 1
    return n


def _printed_counters(doc: EditDoc, spilled) -> None:
    """After a page that spills, the next page's counter is set to the number the PDF prints
    there, so every later page keeps its printed number."""
    nums = getattr(doc.furniture, "page_numbers", {}) or {}
    for b in doc.blocks:
        if b.kind == "pagemark" and getattr(b, "hard", False) and (b.page - 1) in spilled:
            val = nums.get(b.page)
            if val is not None and (b.numbering is None or b.numbering[1] != val[1]):
                b.counter = val[1]


def _objective(m: Dict, fp: Optional[Dict]) -> Tuple[float, float]:
    fig_err = 0.0
    for it in (fp or {}).get("items", []):
        if it.get("found") and not it.get("ok"):
            fig_err += min(200.0, abs(it.get("dy") or 0.0)) + (200.0 if it.get("out_page") != it["page"] else 0)
    return (m["total"], round(fig_err, 1))


async def fit(ctx, doc: EditDoc, tex: str, lm: LineMap, pdf: bytes, cc, timeout: int):
    """
    Measured page fit: compile → measure where each source page overflows → tighten each spilled
    page one rung → recompile, at most MAX_FIT_ROUNDS rounds, while the total overflow (then the
    pictures' total vertical error) strictly drops. Pages are independent (each ends in a forced
    break), so one compile tries every page at once; a page that got worse is put back. The best
    compiled state is kept (and the document model restored to it).
    """
    from .emit import emit_document
    from . import measure as MEAS
    out_dir = getattr(ctx, "out_dir", None)

    def measure(p):
        if doc.deck:
            # a slide never spills: it is scaled down to fit; its overflow is what the scale took
            return MEAS.deck_overflow(doc, p), None
        m = MEAS.page_overflow(doc, p)
        fp = MEAS.figure_position(doc, p, out_dir) if out_dir is not None else None
        return m, fp

    m, fp = await asyncio.to_thread(measure, pdf)
    best = (_objective(m, fp), tex, lm, pdf, _snapshot(doc), m)
    history = [{"round": 0, "overflow": m["total"], "pages_out": m["pages_out"], "spilled": sorted(m["over"])}]
    prev_over = dict(m["over"])
    rounds = 0
    stalls = 0
    pages = _page_blocks(doc)
    for r in range(MAX_FIT_ROUNDS):
        changed = False
        # a page that got worse after its last rung is put back
        for pno, amount in m["over"].items():
            if amount > prev_over.get(pno, 0.0) + 0.5 and (doc.page_fit.get(pno) or {}).get("undo") \
                    and r > 0:
                changed |= _revert_last(doc, pno)
        for pno, amount in sorted(m["over"].items()):
            if amount > prev_over.get(pno, 0.0) + 0.5 and r > 0:
                continue
            changed |= _climb(doc, pno, pages.get(pno, []), amount)
        changed |= _figure_corrections(doc, fp, m["over"], m["landing"]) > 0
        _printed_counters(doc, set(m["over"]))
        if not changed:
            break
        tex2, lm2 = emit_document(doc)
        pdf2, _log = await cc(ctx, tex2, timeout)
        rounds += 1
        if pdf2 is None:
            break
        prev_over = dict(m["over"])
        m2, fp2 = await asyncio.to_thread(measure, pdf2)
        obj = _objective(m2, fp2)
        history.append({"round": r + 1, "overflow": m2["total"], "pages_out": m2["pages_out"],
                        "spilled": sorted(m2["over"])})
        improved = obj < best[0]
        worse = obj > best[0]
        if improved:
            best = (obj, tex2, lm2, pdf2, _snapshot(doc), m2)
            stalls = 0
        else:
            stalls += 1
        m, fp = m2, fp2
        # a rung can do nothing measurable (no paragraph TeX could set shorter): the next one is
        # still tried, but two rounds without progress, or a worse one, end the loop
        if stalls >= 2:
            break
    obj, tex, lm, pdf, snap, m = best
    _restore(doc, snap)
    spilled = sorted(m["over"])
    return tex, lm, pdf, {"rounds": rounds, "history": history, "spilled": spilled,
                          "overflow": m["total"],
                          "fit": {p: {k: v for k, v in st.items() if k != "undo"}
                                  for p, st in doc.page_fit.items() if st}}
