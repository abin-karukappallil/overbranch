"""
vision_layout.py — Vision-based correction of figure/table size, alignment and placement.

The deterministic build detects figures and tables geometrically. In practice this misbehaves at
page boundaries: a figure sized too wide pushes the following paragraph onto a new page, a wide
borderless table overflows ``\\linewidth``, alignment sometimes disagrees with the PDF, and nothing
promotes an overflowing block to a float. The output grows longer than the source.

This pass renders each PDF page carrying at least one figure or table as a PNG, asks Gemini (via
the project's web2api gateway, same wrapper as ``polish.py``) for a strict JSON correction of each
block's ``width_frac``, ``align``, ``float_spec`` and reading-order ``anchor``, and applies the
result only when a fresh compile verifies it: no new compile error, the compiled page count does
not grow, and the coverage/style gates do not regress. Otherwise every mutation is reverted.

Verdicts are cached in the job directory keyed by (prompt version, page PNG hash, request JSON) so
a resumed job never re-queries.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .model import EditDoc, Figure, Table
from .prompts import PROMPT_VERSION, VISION_BLOAT_HINT, VISION_LAYOUT_SYSTEM, VISION_LAYOUT_USER

logger = logging.getLogger("pdf2latex.editable.vision_layout")

PAGE_DPI = 150
STD_FLOAT_SPECS = {"htbp", "ht", "H", "!htbp", "hbp", "tbp"}
STD_ALIGNS = {"left", "center", "right"}
MIN_WIDTH = 0.10
MAX_WIDTH = 1.0


# ---------------------------------------------------------------------------
# Verdict shape (what Gemini returns, per block)
# ---------------------------------------------------------------------------

@dataclass
class _Verdict:
    block_id: int
    width_frac: Optional[float] = None
    align: Optional[str] = None
    float_spec: Optional[str] = None     # "" means "clear the current spec"; None means "no change"
    anchor: Optional[str] = None         # "before" | "after" | "unchanged"
    anchor_block_id: Optional[int] = None


@dataclass
class _Snapshot:
    """What we need to revert a block to its pre-vision state."""
    block_id: int
    is_figure: bool
    width_frac_list: Optional[List[float]] = None
    width_pt: Optional[float] = None
    col_frac: Optional[List[float]] = None
    align: Optional[str] = None
    centered: Optional[bool] = None
    float_spec: Optional[str] = None
    original_index: int = -1


@dataclass
class _PageJob:
    page: int
    text_w: float
    text_h: float
    page_w: float
    page_h: float
    figures: List[Dict] = field(default_factory=list)
    tables: List[Dict] = field(default_factory=list)
    png: bytes = b""


# ---------------------------------------------------------------------------
# Prompt filling
# ---------------------------------------------------------------------------

def _fill(t: str, **kw) -> str:
    for k, v in kw.items():
        t = t.replace("{{" + k + "}}", str(v))
    return t


# ---------------------------------------------------------------------------
# JSON extraction and clamping
# ---------------------------------------------------------------------------

_FENCE = re.compile(r"^```[a-zA-Z0-9_-]*\s*|\s*```$", re.MULTILINE)


def _extract_json(text: str) -> Optional[Dict]:
    s = _FENCE.sub("", text).strip()
    # tolerate a leading preamble: find the first "{" and the matching close.
    i = s.find("{")
    if i < 0:
        return None
    depth = 0
    end = -1
    for k in range(i, len(s)):
        if s[k] == "{":
            depth += 1
        elif s[k] == "}":
            depth -= 1
            if depth == 0:
                end = k
                break
    if end < 0:
        return None
    try:
        return json.loads(s[i:end + 1])
    except (json.JSONDecodeError, ValueError):
        return None


def _clamp_width(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return max(MIN_WIDTH, min(MAX_WIDTH, f))


def _clean_float_spec(v) -> Optional[str]:
    """Return "" to mean "clear the spec", a valid spec, or None to mean "no change"."""
    if v is None:
        return ""     # explicit null => clear
    if not isinstance(v, str):
        return None
    s = v.strip()
    if not s or s.lower() in ("null", "none"):
        return ""
    if s in STD_FLOAT_SPECS:
        return s
    return None


def _parse_verdicts(obj: Dict, known_ids: Dict[int, Tuple[bool, Dict]]) -> List[_Verdict]:
    """Pull verdicts out of the JSON for ids in ``known_ids`` (id → (is_figure, meta))."""
    out: List[_Verdict] = []
    for key in ("figures", "tables"):
        items = obj.get(key)
        if not isinstance(items, list):
            continue
        want_figure = (key == "figures")
        for it in items:
            if not isinstance(it, dict):
                continue
            raw_id = it.get("id")
            try:
                bid = int(raw_id)
            except (TypeError, ValueError):
                continue
            if bid not in known_ids:
                continue
            is_figure, meta = known_ids[bid]
            if is_figure != want_figure:
                continue
            v = _Verdict(block_id=bid)
            if "width_frac" in it:
                w = _clamp_width(it["width_frac"])
                if w is not None:
                    v.width_frac = w
            align = it.get("align")
            if isinstance(align, str) and align.lower() in STD_ALIGNS:
                v.align = align.lower()
            fs = _clean_float_spec(it.get("float_spec", None))
            # distinguish "field present → clear/set" vs "field absent → leave alone"
            if "float_spec" in it:
                v.float_spec = fs
            anc = it.get("anchor")
            if isinstance(anc, str) and anc.lower() in ("before", "after", "unchanged"):
                v.anchor = anc.lower()
            aid = it.get("anchor_block_id")
            if aid is not None:
                try:
                    v.anchor_block_id = int(aid)
                except (TypeError, ValueError):
                    v.anchor_block_id = None
            # anchor only accepted when a known neighbour id is given
            if v.anchor in ("before", "after"):
                allowed = set(meta.get("neighbour_ids", []))
                if v.anchor_block_id not in allowed:
                    v.anchor = None
                    v.anchor_block_id = None
            out.append(v)
    return out


# ---------------------------------------------------------------------------
# Page rendering (PyMuPDF)
# ---------------------------------------------------------------------------

def _render_page(pdf_doc, page_number: int, dpi: int = PAGE_DPI) -> bytes:
    """``page_number`` is 1-based (PageExtract convention)."""
    import pymupdf
    pg = pdf_doc[page_number - 1]
    pix = pg.get_pixmap(matrix=pymupdf.Matrix(dpi / 72.0, dpi / 72.0), alpha=False)
    return pix.tobytes("png")


# ---------------------------------------------------------------------------
# Target collection
# ---------------------------------------------------------------------------

def _para_text(p) -> str:
    if p is None:
        return ""
    return " ".join(l.text for l in getattr(p, "lines", []))[:160]


def _neighbour_ids(blocks: List, idx: int) -> List[int]:
    """The two blocks either side of ``blocks[idx]`` on the same page, as id ints.
    Pagemarks and notes are skipped so the anchor is a block Gemini actually sees."""
    page = blocks[idx].page
    before: List[int] = []
    i = idx - 1
    while i >= 0 and len(before) < 2:
        b = blocks[i]
        if b.page != page:
            break
        if b.kind not in ("pagemark", "note") and b.id:
            before.insert(0, b.id)
        i -= 1
    after: List[int] = []
    j = idx + 1
    while j < len(blocks) and len(after) < 2:
        b = blocks[j]
        if b.page != page:
            break
        if b.kind not in ("pagemark", "note") and b.id:
            after.append(b.id)
        j += 1
    return before + after


def _collect_jobs(doc: EditDoc) -> Dict[int, _PageJob]:
    """One ``_PageJob`` per page carrying at least one Figure or Table."""
    jobs: Dict[int, _PageJob] = {}
    blocks = doc.blocks
    text_w = max(72.0, doc.profile.paper_pt[0] - doc.profile.margins.get("left", 72.0)
                       - doc.profile.margins.get("right", 72.0))
    text_h = max(72.0, doc.profile.paper_pt[1] - doc.profile.margins.get("top", 72.0)
                       - doc.profile.margins.get("bottom", 72.0))
    page_w, page_h = doc.profile.paper_pt
    for i, b in enumerate(blocks):
        if not isinstance(b, (Figure, Table)):
            continue
        if not b.id:
            continue
        job = jobs.get(b.page)
        if job is None:
            job = _PageJob(page=b.page, text_w=round(text_w, 1), text_h=round(text_h, 1),
                           page_w=round(page_w, 1), page_h=round(page_h, 1))
            jobs[b.page] = job
        bbox = tuple(round(x, 1) for x in b.bbox)
        neigh = _neighbour_ids(blocks, i)
        if isinstance(b, Figure):
            # Report the sum of per-image widths: for a one-image figure this is just the width,
            # and for two side-by-side images it is the total line coverage, which is what the
            # LLM reasons about from the rendered page.
            total_frac = round(min(1.0, sum(b.width_frac)), 3) if b.width_frac else 1.0
            job.figures.append({
                "id": b.id,
                "bbox": bbox,
                "width_frac": total_frac,
                "align": b.align or "center",
                "float_spec": b.float_spec,
                "caption": _para_text(b.caption),
                "before_ids": neigh[:2],
                "after_ids": neigh[2:],
            })
        else:
            # Table: width is width_pt (pt). Report as a fraction so the LLM reasons in the same
            # units as a figure. Fall back to the col_frac sum (p-column tables) when width_pt is
            # unset, and to a full-line default when neither is known.
            if b.width_pt:
                width_pt = b.width_pt
            elif b.col_frac:
                width_pt = sum(b.col_frac) * text_w
            else:
                width_pt = text_w
            frac = max(MIN_WIDTH, min(MAX_WIDTH, round(width_pt / max(1.0, text_w), 3)))
            job.tables.append({
                "id": b.id,
                "bbox": bbox,
                "width_frac": frac,
                "align": "center" if b.centered else "left",
                "float_spec": b.float_spec,
                "caption": _para_text(b.caption),
                "cols": len(b.col_x),
                "rows": len(b.rows),
                "before_ids": neigh[:2],
                "after_ids": neigh[2:],
            })
    return jobs


# ---------------------------------------------------------------------------
# Apply / snapshot / revert
# ---------------------------------------------------------------------------

def _snapshot_blocks(doc: EditDoc, verdicts_by_id: Dict[int, _Verdict]) -> List[_Snapshot]:
    snaps: List[_Snapshot] = []
    for idx, b in enumerate(doc.blocks):
        if b.id not in verdicts_by_id:
            continue
        if isinstance(b, Figure):
            snaps.append(_Snapshot(block_id=b.id, is_figure=True,
                                   width_frac_list=list(b.width_frac),
                                   align=b.align, float_spec=b.float_spec,
                                   original_index=idx))
        elif isinstance(b, Table):
            snaps.append(_Snapshot(block_id=b.id, is_figure=False,
                                   width_pt=b.width_pt, col_frac=list(b.col_frac),
                                   centered=b.centered, float_spec=b.float_spec,
                                   original_index=idx))
    return snaps


def _apply_verdicts(doc: EditDoc, verdicts: List[_Verdict], text_w_by_page: Dict[int, float]) -> int:
    """Mutate ``doc.blocks`` in place. Returns the count of blocks changed."""
    by_id = {v.block_id: v for v in verdicts}
    changed = 0
    # width/align/float_spec first (per block)
    for b in doc.blocks:
        v = by_id.get(getattr(b, "id", 0))
        if v is None:
            continue
        touched = False
        if isinstance(b, Figure):
            if v.width_frac is not None and b.width_frac:
                # Scale per-image widths so their sum (total line coverage) matches the verdict.
                old_sum = sum(b.width_frac) or 1.0
                scale = v.width_frac / old_sum
                b.width_frac = [max(MIN_WIDTH, min(MAX_WIDTH, w * scale)) for w in b.width_frac]
                touched = True
            elif v.width_frac is not None and not b.width_frac:
                # defensive: split the total evenly across the images this Figure has
                n = max(1, len(b.images))
                b.width_frac = [max(MIN_WIDTH, v.width_frac / n)] * n
                touched = True
            if v.align is not None and v.align != b.align:
                b.align = v.align
                touched = True
            if v.float_spec is not None:
                new_fs = v.float_spec or None
                if new_fs != b.float_spec:
                    b.float_spec = new_fs
                    touched = True
        elif isinstance(b, Table):
            if v.width_frac is not None:
                text_w = text_w_by_page.get(b.page, 468.0)
                new_width_pt = max(72.0, v.width_frac * text_w)
                if b.col_frac:
                    old_sum = sum(b.col_frac) or 1.0
                    scale = v.width_frac / old_sum
                    b.col_frac = [max(0.03, c * scale) for c in b.col_frac]
                if b.width_pt and abs(b.width_pt - new_width_pt) > 1.0:
                    b.width_pt = new_width_pt
                    touched = True
                elif not b.width_pt:
                    b.width_pt = new_width_pt
                    touched = True
            if v.align is not None:
                want_centered = (v.align == "center")
                if want_centered != b.centered:
                    b.centered = want_centered
                    touched = True
            if v.float_spec is not None:
                new_fs = v.float_spec or None
                if new_fs != b.float_spec:
                    b.float_spec = new_fs
                    touched = True
        if touched:
            changed += 1
    # anchor moves (reorder) after the per-block mutations so neighbour-id lookups still work
    for v in verdicts:
        if v.anchor not in ("before", "after") or v.anchor_block_id is None:
            continue
        src = next((i for i, b in enumerate(doc.blocks) if b.id == v.block_id), -1)
        dst = next((i for i, b in enumerate(doc.blocks) if b.id == v.anchor_block_id), -1)
        if src < 0 or dst < 0 or doc.blocks[src].page != doc.blocks[dst].page:
            continue
        blk = doc.blocks.pop(src)
        # the pop may shift dst left by one when src < dst
        if src < dst:
            dst -= 1
        insert_at = dst if v.anchor == "before" else dst + 1
        doc.blocks.insert(insert_at, blk)
        changed += 1
    return changed


def _revert(doc: EditDoc, snaps: List[_Snapshot]) -> None:
    by_id = {s.block_id: s for s in snaps}
    # revert fields
    for b in doc.blocks:
        s = by_id.get(getattr(b, "id", 0))
        if s is None:
            continue
        if s.is_figure and isinstance(b, Figure):
            b.width_frac = list(s.width_frac_list) if s.width_frac_list is not None else []
            b.align = s.align or "center"
            b.float_spec = s.float_spec
        elif not s.is_figure and isinstance(b, Table):
            b.width_pt = s.width_pt or 0.0
            b.col_frac = list(s.col_frac) if s.col_frac is not None else []
            b.centered = bool(s.centered)
            b.float_spec = s.float_spec
    # revert order (only move blocks we captured, so untouched order is preserved)
    want_order = sorted(snaps, key=lambda s: s.original_index)
    for s in want_order:
        src = next((i for i, b in enumerate(doc.blocks) if b.id == s.block_id), -1)
        if src < 0 or src == s.original_index:
            continue
        blk = doc.blocks.pop(src)
        dst = min(s.original_index, len(doc.blocks))
        doc.blocks.insert(dst, blk)


# ---------------------------------------------------------------------------
# One LLM call per page
# ---------------------------------------------------------------------------

async def _query_page(job: _PageJob, cache_dir: Optional[Path], settings,
                      page_count: int, bloated: bool) -> List[Dict]:
    """Return the raw LLM verdict list for this page (figures + tables merged), from cache or a
    fresh ``complete()`` call."""
    from ..llm import complete
    payload = {
        "figures": job.figures,
        "tables": job.tables,
        "page": job.page,
        "text_w": job.text_w,
        "text_h": job.text_h,
        "page_w": job.page_w,
        "page_h": job.page_h,
        "bloated": bloated,
    }
    png_hash = hashlib.sha256(job.png).hexdigest()[:32]
    cache_key = hashlib.sha256(
        (PROMPT_VERSION + "|" + png_hash + "|" + json.dumps(payload, sort_keys=True)).encode()
    ).hexdigest()[:40]
    if cache_dir is not None:
        hit = cache_dir / f"{cache_key}.json"
        if hit.exists():
            try:
                return json.loads(hit.read_text(encoding="utf-8")).get("entries", [])
            except (json.JSONDecodeError, OSError):
                pass
    figures_json = json.dumps(job.figures, ensure_ascii=False)
    tables_json = json.dumps(job.tables, ensure_ascii=False)
    user = _fill(VISION_LAYOUT_USER,
                 PAGE=job.page, TOTAL=page_count,
                 TEXT_W=job.text_w, TEXT_H=job.text_h,
                 PAGE_W=job.page_w, PAGE_H=job.page_h,
                 FIGURES_JSON=figures_json, TABLES_JSON=tables_json,
                 BLOAT_HINT=(VISION_BLOAT_HINT if bloated else ""))
    try:
        answer = await complete(VISION_LAYOUT_SYSTEM, user, job.png,
                                timeout=settings.page_timeout,
                                retries=settings.page_retries,
                                concurrency=settings.concurrency,
                                max_tokens=2000, label=f"vision-p{job.page}")
    except Exception as e:  # noqa: BLE001 — LLM failure leaves the block in place
        logger.info(f"vision p{job.page}: LLM call failed: {e}")
        return []
    obj = _extract_json(answer)
    if not obj:
        logger.info(f"vision p{job.page}: no JSON in response ({len(answer)} chars)")
        return []
    # the parsed object is kept raw in the cache; parsing/clamping happens on load too
    entries: List[Dict] = []
    for key in ("figures", "tables"):
        items = obj.get(key)
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict):
                    entries.append({"_kind": key, **it})
    if cache_dir is not None:
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / f"{cache_key}.json").write_text(
                json.dumps({"entries": entries}), encoding="utf-8")
        except OSError:
            pass
    return entries


def _verdicts_from_entries(entries_by_page: Dict[int, List[Dict]],
                           jobs: Dict[int, _PageJob]) -> List[_Verdict]:
    """Flatten the per-page cache entries back into clamped _Verdict objects."""
    all_verdicts: List[_Verdict] = []
    for page, entries in entries_by_page.items():
        job = jobs[page]
        fig_meta = {f["id"]: (True, f) for f in job.figures}
        tbl_meta = {t["id"]: (False, t) for t in job.tables}
        known_ids = {**fig_meta, **tbl_meta}
        obj = {"figures": [e for e in entries if e.get("_kind") == "figures"],
               "tables":  [e for e in entries if e.get("_kind") == "tables"]}
        all_verdicts.extend(_parse_verdicts(obj, known_ids))
    return all_verdicts


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def vision_layout(ctx, extract, doc: EditDoc, tex: str, pdf: Optional[bytes], lm,
                        gate_result: Dict, settings, job_id: str, pdf_doc,
                        compile_tex=None) -> Tuple[str, Optional[bytes], Dict]:
    """Return (tex, pdf, gate_result): corrected only when a fresh compile verifies it, else the
    inputs unchanged. ``pdf_doc`` is the open PyMuPDF document from the extract phase."""
    from ..pipeline import compile_tex as _compile_tex
    from . import gates as G
    from .emit import emit_document
    compile_tex = compile_tex or _compile_tex
    gate_result = dict(gate_result)
    stats: Dict = {"pages": 0, "requested": 0, "applied": 0, "accepted": False, "reverted": False,
                   "page_delta": None}
    jobs = _collect_jobs(doc)
    if not jobs:
        gate_result["vision"] = stats
        return tex, pdf, gate_result
    # render page images
    page_count = max(1, doc.page_count)
    bloated = pdf is not None and gate_result.get("compiled_page_count") is not None and \
              gate_result["compiled_page_count"] > page_count
    # pdf is not None by the time this is called from run_editable, but the compiled page count
    # may not be in gate_result; recompute conservatively from the compiled PDF.
    if pdf is not None and not bloated:
        try:
            from ..pipeline import _page_count as _pcount
            compiled_n = _pcount(pdf)
            bloated = compiled_n > page_count
        except Exception:  # noqa: BLE001
            compiled_n = None
    for page, job in jobs.items():
        try:
            job.png = await asyncio.to_thread(_render_page, pdf_doc, page, PAGE_DPI)
        except Exception as e:  # noqa: BLE001 — a page we cannot render drops out of the pass
            logger.info(f"vision p{page}: render failed: {e}")
    jobs = {p: j for p, j in jobs.items() if j.png}
    stats["pages"] = len(jobs)
    if not jobs:
        gate_result["vision"] = stats
        return tex, pdf, gate_result
    # cache dir
    cache_dir: Optional[Path] = None
    try:
        from .. import jobs as _jmod
        cache_dir = _jmod.job_dir(job_id) / "editable" / "vision_cache"
    except Exception:  # noqa: BLE001
        cache_dir = None
    # concurrent queries, bounded by the shared slot pool inside llm.complete
    entries_by_page: Dict[int, List[Dict]] = {}
    tasks = {p: asyncio.create_task(_query_page(j, cache_dir, settings, page_count, bloated))
             for p, j in jobs.items()}
    for page, task in tasks.items():
        try:
            entries_by_page[page] = await task
        except Exception as e:  # noqa: BLE001
            logger.info(f"vision p{page}: query failed: {e}")
            entries_by_page[page] = []
    verdicts = _verdicts_from_entries(entries_by_page, jobs)
    stats["requested"] = len(verdicts)
    if not verdicts:
        gate_result["vision"] = stats
        return tex, pdf, gate_result
    # snapshot before mutation so a revert is exact
    by_id = {v.block_id: v for v in verdicts}
    snaps = _snapshot_blocks(doc, by_id)
    text_w_by_page = {p: j.text_w for p, j in jobs.items()}
    applied = _apply_verdicts(doc, verdicts, text_w_by_page)
    stats["applied"] = applied
    if not applied:
        gate_result["vision"] = stats
        return tex, pdf, gate_result
    # re-emit and recompile
    try:
        new_tex, new_lm = emit_document(doc)
    except Exception as e:  # noqa: BLE001 — a malformed mutation reverts the whole pass
        logger.info(f"vision: re-emit failed: {e}")
        _revert(doc, snaps)
        stats["reverted"] = True
        gate_result["vision"] = stats
        return tex, pdf, gate_result
    timeout = G.MERGE_TIMEOUT_BASE + 6 * max(1, doc.page_count)
    new_pdf, _log = await compile_tex(ctx, new_tex, timeout)
    if new_pdf is None:
        _revert(doc, snaps)
        stats["reverted"] = True
        gate_result["vision"] = stats
        return tex, pdf, gate_result
    # measurement gate: do not grow the page count, do not regress coverage/style/lint
    try:
        from ..pipeline import _page_count as _pcount
        new_n = _pcount(new_pdf)
        old_n = _pcount(pdf) if pdf is not None else new_n
    except Exception:  # noqa: BLE001
        new_n, old_n = page_count, page_count
    page_delta = new_n - old_n
    new_gates = G.run_gates(extract, doc, new_tex, new_pdf, settings)
    old = gate_result.get("gates", {}) if isinstance(gate_result.get("gates"), dict) else {}
    worse_pages = new_n > old_n
    worse_cov = new_gates["gates"].get("coverage", 0.0) < old.get("coverage", 0.0) - 1e-4
    worse_style = new_gates["gates"].get("style", 0.0) < old.get("style", 0.0) - 0.005
    worse_lint = len(new_gates.get("failed", [])) > len(gate_result.get("failed", []))
    if worse_pages or worse_cov or worse_style or worse_lint:
        _revert(doc, snaps)
        stats["reverted"] = True
        stats["page_delta"] = page_delta
        gate_result["vision"] = stats
        return tex, pdf, gate_result
    stats["accepted"] = True
    stats["page_delta"] = page_delta
    new_gates["vision"] = stats
    return new_tex, new_pdf, new_gates
