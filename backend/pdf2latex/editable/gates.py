"""
gates.py — Compile-repair loop and the editable quality gates (G1–G8 + lint).

Measured, not prompt-based: every gate is computed from the extraction and the compiled output PDF.
The output is always written; the gates say whether the job is "done" or "below_threshold".
"""

from __future__ import annotations

import logging
import re
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from ..models import DocExtract
from .model import EditDoc, LineMap

logger = logging.getLogger("pdf2latex.editable.gates")

MERGE_TIMEOUT_BASE = 90

# Body constructs that must never appear (editability lint).
_FORBIDDEN = [r"\\begin\{tikzpicture\}", r"\\node", r"\\put\b", r"\\begin\{picture\}",
              r"\\textblock", r"\\obfit\b", r"\\obhfit\b"]


async def compile_with_repair(ctx, tex: str, doc: EditDoc, lm: LineMap,
                              compile_tex: Callable[..., Awaitable]) -> Tuple[str, Optional[bytes]]:
    """
    Compile; on failure, degrade the blocks the error points at (table→paras, list→paras,
    math→image only, note→inline) and recompile. Never falls back to coordinates. Continues while
    the error count strictly decreases.
    """
    timeout = MERGE_TIMEOUT_BASE + 6 * max(1, doc.page_count)
    pdf, log = await compile_tex(ctx, tex, timeout)
    if pdf is not None:
        return tex, pdf
    from ..pipeline import _error_lines, _log_errors
    prev_errors = None
    for _ in range(4):
        lines = _error_lines(log)
        bad_ids = {lm.block_for_line(n) for n in lines if lm.block_for_line(n)}
        logger.info(f"editable compile failed; degrading blocks {bad_ids}")
        if not bad_ids:
            # last resort: strip the offending raw lines is unsafe; give up with no PDF
            break
        changed = _degrade(doc, bad_ids)
        if not changed:
            break
        from .emit import emit_document
        tex, lm = emit_document(doc)
        pdf, log = await compile_tex(ctx, tex, timeout)
        if pdf is not None:
            return tex, pdf
        n_err = len(_error_lines(log))
        if prev_errors is not None and n_err >= prev_errors:
            break
        prev_errors = n_err
    return tex, None


def _degrade(doc: EditDoc, bad_ids: set) -> bool:
    """Drop one structural rung on the flagged blocks. Returns whether anything changed."""
    changed = False
    new_blocks = []
    for b in doc.blocks:
        if b.id in bad_ids:
            rung = _degraded_level(b)
            if rung is not None:
                new_blocks.extend(rung)
                changed = True
                continue
        new_blocks.append(b)
    doc.blocks = new_blocks
    return changed


def _degraded_level(b):
    from .model import Para, TLine, Segment, Run
    kind = b.kind
    if kind == "table":
        # one paragraph per row, cells joined
        out = []
        for row in getattr(b, "rows", []):
            txt = "  ".join(c.text for c in row if c.text)
            if txt.strip():
                out.append(_plain_para(b.page, txt))
        return out or [_plain_para(b.page, " ")]
    if kind == "list":
        out = []
        for it in getattr(b, "items", []):
            txt = (it.label + " " + " ".join(p.lines[0].text for p in it.body if hasattr(p, "lines") and p.lines))
            out.append(_plain_para(b.page, txt))
        return out
    if kind == "note":
        return [_plain_para(b.page, " ".join(c.lines[0].text for c in b.content
                                             if hasattr(c, "lines") and c.lines))]
    if kind == "math":
        b.number = None       # keep the crop image only
        return [b]
    if kind == "heading":
        return [_plain_para(b.page, b.text)]
    return None


def _plain_para(page: int, text: str):
    from .model import Para, TLine, Segment, Run
    run = Run(text=text, size=10.0, family="serif", font_cls="times", bold=False, italic=False,
              color=(0, 0, 0))
    tl = TLine(segments=[Segment(runs=[run], x0=0, x1=0)], x0=0, x1=0, top=0, bottom=0,
               baseline=0, page=page, size=10.0)
    return Para(page=page, bbox=(0, 0, 0, 0), lines=[tl])


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

def run_gates(extract: DocExtract, doc: EditDoc, tex: str, pdf: bytes, settings) -> Dict:
    from . import measure as MEAS
    result: Dict = {"gates": {}, "failed": []}
    # G2/G3 coverage + order
    cov = MEAS.coverage_and_order(extract, doc, pdf)
    result["gates"]["coverage"] = cov["coverage"]
    result["gates"]["extra_ratio"] = cov["extra_ratio"]
    result["gates"]["order"] = cov["order"]
    result["page_coverage"] = cov.get("page_coverage", {})
    # G4 style
    style = MEAS.style_fidelity(extract, doc, pdf)
    result["style"] = style
    result["gates"]["style"] = style.get("overall", 0.0)
    # G5 pages
    from ..pipeline import _page_count
    out_pages = _page_count(pdf)
    result["gates"]["pages_out"] = out_pages
    result["gates"]["pages_source"] = doc.page_count
    # G6 assets
    result["assets"] = _asset_gate(extract, doc, tex)
    # G8 lint
    result["lint"] = _lint(tex, doc)

    # decide failures
    # Editable targets: coverage/extra/style stay strict (they measure text & style fidelity);
    # order and page count are naturally looser under reflow.
    if cov["coverage"] < settings.coverage_target:
        result["failed"].append("coverage")
    if cov["extra_ratio"] > 0.01:
        result["failed"].append("extra")
    if cov["order"] < 0.95:
        result["failed"].append("order")
    tgt = getattr(settings, "style_target", 0.97)
    if style.get("overall", 1.0) < tgt:
        result["failed"].append("style")
    allow = max(1, round(0.25 * doc.page_count))
    if abs(out_pages - doc.page_count) > allow:
        result["failed"].append("pages")
    if not result["assets"].get("ok", True):
        result["failed"].append("assets")
    if result["lint"].get("forbidden", 0) > 0:
        result["failed"].append("lint")
    return result


def _asset_gate(extract: DocExtract, doc: EditDoc, tex: str) -> Dict:
    from pathlib import Path
    refs = set(re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", tex))
    extracted = set()
    for p in extract.pages:
        for img in p.images:
            extracted.add(img.file)
    # equation crops (page{n}_eq{k}.png) are generated by editable mode, not extracted images,
    # so they are expected references, not "extra".
    extra = {r for r in refs - extracted
             if not any(t in r.rsplit("/", 1)[-1] for t in ("_eq", "_bg"))}
    return {"ok": True, "referenced": sorted(refs), "extracted": sorted(extracted),
            "extra": sorted(extra)}


def _lint(tex: str, doc: EditDoc) -> Dict:
    # strip comments and the preamble
    body = tex.split("\\begin{document}", 1)[-1]
    body = "\n".join(l for l in body.splitlines() if not l.lstrip().startswith("%"))
    forbidden = sum(len(re.findall(p, body)) for p in _FORBIDDEN)
    fontsize = len(re.findall(r"\\fontsize", body))
    nodes = len(re.findall(r"\\node", body))
    npages = max(1, doc.page_count)
    vspace = len(re.findall(r"\\vspace", body))
    hspace = len(re.findall(r"\\hspace\{[-0-9.]+\s*(?:pt|bp|cm|mm|in)", body))
    notes = len(re.findall(r"\\obnote", body))
    sections = len(re.findall(r"\\(?:chapter|section|subsection|subsubsection)\*?\{", body))
    return {"forbidden": forbidden, "fontsize": fontsize, "nodes": nodes,
            "vspace_per_page": round(vspace / npages, 2), "hspace_per_page": round(hspace / npages, 2),
            "notes": notes, "sections": sections}
