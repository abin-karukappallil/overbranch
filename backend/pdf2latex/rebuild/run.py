"""
run.py — The AI-rebuild job: every stage in order, job progress, the queue and the failure policy.

  run_rebuild       the job as `pipeline.run_conversion` starts it: waits for a slot, runs
                    `rebuild_document`, writes the result into the project.
  rebuild_document  inspect → OCR → extract → rasterize → assets → preamble → pages (parallel) → package.
                    Touches the job's own directory and state only, so the CLI can run it too.

Failure policy:
  whole job    The gateway does not answer the text probe, the preamble cannot be produced, more than
               `max_failed_page_share` of the pages fail, the merged document does not build, or a
               stage hits a bug: the job goes to `editable.run.run_editable` from a clean output
               directory. Its `engine` flips to "deterministic" and `report.rebuild.fallback_reason`
               says why (added by `jobs.public_view`, because that engine writes its own report).
  one page     The model cannot write it or it never compiles: it becomes an image of the source page,
               `fallback` true and flagged low confidence.
  vision       Never a failure. The pipeline works from the measured text report alone and the report
               says whether the model really saw any image.

Resume: every stage up to assets is deterministic and runs again (OCR excepted, its result is kept); a
saved preamble that still compiles is reused without an LLM call, and a page whose best attempt was
saved under that same preamble is not redone.

The queue covers rebuild jobs only, per process (PDF2LATEX_MAX_ACTIVE_JOBS). Exact-mode and deterministic
jobs do not pass through this module.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import shutil
import time
import weakref
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

from .. import jobs
from ..config import get_settings
from ..extract import PdfValidationError, extract_document, normalize_rotation, open_pdf
from ..llm import model_name
from ..models import ConversionReport, PageReport
from ..storage import PACKAGE_EXTRAS, FileConflictError, write_output_to_project
from . import generate, package, refine
from .assets import build_assets
from .inspect import inspect_pdf
from .layout import build_layouts
from .model import AssetManifest, Inspection, PageResult, RebuildCtx
from .ocr import OcrResult, ensure_text_layer
from .probe import Probe, probe_gateway
from .raster import rasterize_pages
from .settings import get_rebuild_settings

logger = logging.getLogger("pdf2latex.rebuild.run")

ENGINE = "rebuild"
FALLBACK_ENGINE = "deterministic"
FINISHED = ("done", "fallback", "failed")
DISCLAIMER = ("Closest match, not pixel-exact: the document is typeset again from the PDF's text and layout, so "
              "spacing and line breaks can differ from the source. Each page's match score and the pages that "
              "need a look are listed in the report.")
# What a page's low-confidence reasons (refine._reasons) mean to the person reading the report.
REASON_TEXT = {
    "ocr": "text comes from OCR and may contain errors",
    "table": "contains a table, check its cells",
    "math": "contains math rebuilt without seeing the page",
    "score": "match score is below the threshold",
    "coverage": "text coverage is below the target",
    "overflow": "runs past one page",
    "image fallback": "kept as an image of the source page, not editable text",
    "repairs exhausted": "did not compile after every repair",
}


class WholeJobFallback(Exception):
    """The rebuild gives up on this job; the message is the reason the user sees."""


class GatewayDown(WholeJobFallback):
    """The model gateway did not answer the text probe."""


class _TooManyFailed(Exception):
    pass


# ---------------------------------------------------------------------------
# The queue
# ---------------------------------------------------------------------------

def _mark_queued(job_id: str, position: int) -> None:
    jobs.update_job(job_id, status="queued", stage="queued", queue_position=position,
                    message=f"Waiting for a free conversion slot (position {position})…")


class _JobGate:
    """First come, first served, at most `max_active_jobs` at once; waiters see their position in the job state."""

    def __init__(self) -> None:
        self.active: Set[str] = set()
        self.waiting: Deque[Tuple[str, "asyncio.Future[None]"]] = deque()

    def _publish(self) -> None:
        for position, (job_id, _fut) in enumerate(self.waiting, start=1):
            _mark_queued(job_id, position)

    def _advance(self) -> None:
        limit = get_rebuild_settings().max_active_jobs
        while self.waiting and len(self.active) < limit:
            job_id, fut = self.waiting.popleft()
            if not fut.done():
                self.active.add(job_id)
                fut.set_result(None)
        self._publish()

    async def acquire(self, job_id: str) -> None:
        if not self.waiting and len(self.active) < get_rebuild_settings().max_active_jobs:
            self.active.add(job_id)
            return
        fut: "asyncio.Future[None]" = asyncio.get_running_loop().create_future()
        self.waiting.append((job_id, fut))
        self._publish()
        try:
            await fut
        except asyncio.CancelledError:
            self.waiting = deque(w for w in self.waiting if w[1] is not fut)
            if job_id in self.active:   # the slot came through as the cancel did
                self.release(job_id)
            else:
                self._publish()
            raise

    def release(self, job_id: str) -> None:
        self.active.discard(job_id)
        self._advance()


_gates: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, _JobGate]" = weakref.WeakKeyDictionary()


def _gate() -> _JobGate:
    loop = asyncio.get_running_loop()
    gate = _gates.get(loop)
    if gate is None:
        gate = _gates[loop] = _JobGate()
    return gate


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------

class _Tracker:
    """The job state while pages run in parallel: per-page rows, `stage_counts`, overall stage and progress."""

    def __init__(self, job_id: str, numbers: List[int]) -> None:
        self.job_id = job_id
        self.statuses: Dict[int, str] = {n: "pending" for n in numbers}

    def _flush(self) -> None:
        counts = Counter(self.statuses.values())
        total = max(1, len(self.statuses))
        finished = sum(counts[s] for s in FINISHED)
        # The earliest step with pages in it: the UI ticks off every step before the job's stage.
        if counts["pending"] or counts["generating"]:
            stage = "generating"
        elif counts["compiling"]:
            stage = "compiling"
        else:
            stage = "verifying"
        jobs.update_job(self.job_id, status="running", stage=stage, stage_counts=dict(counts),
                        progress=round(0.15 + 0.75 * finished / total, 3),
                        message=f"Rebuilding pages… {finished}/{total} done")

    def status(self, n: int, status: str) -> None:
        self.statuses[n] = status
        jobs.update_page(self.job_id, n, status=status)
        self._flush()

    def finish(self, pr: PageResult) -> None:
        self.statuses[pr.number] = pr.status
        jobs.update_page(self.job_id, pr.number, **_page_row(pr))
        self._flush()

    def start(self) -> None:
        self._flush()


def _reason_texts(reasons: List[str]) -> List[str]:
    return [REASON_TEXT.get(r, r) for r in reasons]


def _page_row(pr: PageResult) -> Dict[str, Any]:
    """The job's `pages[]` row. `fallback` is true for a page kept as an image."""
    row = pr.public()
    row["fallback"] = True if pr.fallback == "image" else None
    row["low_confidence"] = _reason_texts(pr.low_confidence)
    return row


def _failed(pr: PageResult) -> bool:
    return pr.status == "failed" or pr.fallback == "image"


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------

def _best_dir(ctx: RebuildCtx) -> Path:
    return ctx.rebuild_dir / "best"


def _preamble_id(preamble: str) -> str:
    return hashlib.sha256(preamble.encode("utf-8")).hexdigest()[:16]


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _save_best(ctx: RebuildCtx, pr: PageResult) -> None:
    """`best/pN.{tex,pdf,json}`; the .json goes last because a resume trusts a page only when it is there."""
    best = _best_dir(ctx)
    best.mkdir(parents=True, exist_ok=True)
    n = pr.number
    _write_atomic(best / f"p{n}.tex", pr.body)
    if pr.pdf_path is not None and Path(pr.pdf_path).is_file():
        shutil.copyfile(pr.pdf_path, best / f"p{n}.pdf")
    meta = {"preamble": _preamble_id(ctx.preamble), "status": pr.status, "score": pr.score, "ssim": pr.ssim,
            "coverage": pr.coverage, "displacement_pt": pr.displacement_pt, "overflow": pr.overflow,
            "rounds": pr.rounds, "repairs": pr.repairs, "fallback": pr.fallback, "vision_used": pr.vision_used,
            "low_confidence": pr.low_confidence, "warnings": pr.warnings}
    _write_atomic(best / f"p{n}.json", json.dumps(meta, ensure_ascii=False))


def _load_best(ctx: RebuildCtx, n: int) -> Optional[PageResult]:
    best = _best_dir(ctx)
    try:
        meta = json.loads((best / f"p{n}.json").read_text(encoding="utf-8"))
        body = (best / f"p{n}.tex").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict) or meta.get("preamble") != _preamble_id(ctx.preamble) or not body.strip():
        return None
    pdf = best / f"p{n}.pdf"
    return PageResult(number=n, status=str(meta.get("status") or "done"), body=body,
                      pdf_path=pdf if pdf.is_file() else None, score=meta.get("score"), ssim=meta.get("ssim"),
                      coverage=meta.get("coverage"), displacement_pt=meta.get("displacement_pt"),
                      overflow=bool(meta.get("overflow")), rounds=int(meta.get("rounds") or 0),
                      repairs=int(meta.get("repairs") or 0), fallback=str(meta.get("fallback") or ""),
                      vision_used=bool(meta.get("vision_used")), low_confidence=list(meta.get("low_confidence") or []),
                      warnings=list(meta.get("warnings") or []))


def _ocr_record(jd: Path) -> Path:
    return jd / "rebuild" / "ocr.json"


def _load_ocr(jd: Path, inspection: Inspection) -> Optional[OcrResult]:
    """A finished OCR of an interrupted run: `ocr.pdf` plus its record, which is written after it."""
    try:
        rec = json.loads(_ocr_record(jd).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not (jd / "ocr.pdf").is_file() or not isinstance(rec, dict):
        return None
    pages = [int(p) for p in rec.get("pages") or []]
    for p in inspection.pages:
        if p.number in pages:
            p.ocr = True
    inspection.ocr_applied = True
    return OcrResult(applied=True, engine=str(rec.get("engine") or ""), pages=pages, warnings=list(rec.get("warnings") or []))


# ---------------------------------------------------------------------------
# Stages before the model
# ---------------------------------------------------------------------------

@dataclass
class _RunInfo:
    """What the job knows so far: a whole-job fallback can happen at any stage and reports it."""
    probe: Optional[Probe] = None
    doc_type: Optional[str] = None
    ocr: Optional[Dict[str, Any]] = None
    rounds: int = 0
    warnings: List[str] = field(default_factory=list)


def _write_source(data: bytes, dest: Path) -> None:
    doc = open_pdf(data)
    try:
        normalize_rotation(doc)
        tmp = dest.with_name(dest.name + ".tmp")
        tmp.write_bytes(doc.tobytes())
        tmp.replace(dest)
    finally:
        doc.close()


def _drop_scans_under_ocr_text(ctx: RebuildCtx) -> None:
    """
    A scan stays the page only while it has no text. A page rebuilt from OCR text is typeset, so the scan
    behind it would print every word twice, out of register. This is enforced here because a prompt rule
    cannot be relied on: the model is told to use the background assets it is given.
    """
    for layout in ctx.layouts:
        if not any(str(b.get("text") or "").strip() for b in layout.blocks):
            continue
        scans = {a.filename for a in ctx.manifest.for_page(layout.number)
                 if a.kind == "background" and a.meta.get("scan")}
        if scans:
            ctx.manifest.assets = [a for a in ctx.manifest.assets if a.filename not in scans]
            layout.assets = [a for a in layout.assets if a.get("file") not in scans]


def _write_extract_json(ctx: RebuildCtx) -> None:
    folder = ctx.job_dir / "extract"
    folder.mkdir(parents=True, exist_ok=True)
    for layout in ctx.layouts:
        _write_atomic(folder / f"page_{layout.number}.json",
                      json.dumps(layout.to_prompt_dict(), ensure_ascii=False))
    ctx.rebuild_dir.mkdir(parents=True, exist_ok=True)
    _write_atomic(ctx.rebuild_dir / "manifest.json", json.dumps(ctx.manifest.to_dict(), ensure_ascii=False, default=str))


async def _analyse(job_id: str, pdf_bytes: bytes, info: _RunInfo, probe: Probe, resume: bool) -> RebuildCtx:
    """inspecting → ocr → extracting → rasterizing → assets. Off the event loop, one thread at a time."""
    settings, s = get_settings(), get_rebuild_settings()
    jd = jobs.job_dir(job_id)
    out_dir = jd / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    (jd / "rebuild").mkdir(parents=True, exist_ok=True)

    def stage(name: str, message: str, progress: float) -> None:
        jobs.update_job(job_id, status="running", stage=name, message=message, progress=progress, queue_position=None)

    stage("inspecting", "Inspecting the PDF…", 0.02)
    source = jd / "source.pdf"
    await asyncio.to_thread(_write_source, pdf_bytes, source)
    inspection = await asyncio.to_thread(inspect_pdf, source)
    info.doc_type = inspection.doc_type
    info.warnings.extend(inspection.warnings)

    extract_from = source
    ocr = OcrResult()
    if inspection.scanned_pages:
        stage("ocr", f"Reading {len(inspection.scanned_pages)} scanned page(s) with OCR…", 0.04)
        saved = _load_ocr(jd, inspection) if resume else None
        if saved is not None:
            ocr = saved
        else:
            ocr = await asyncio.to_thread(ensure_text_layer, source, jd / "ocr.pdf", inspection,
                                          language=s.ocr_language, timeout_s=s.ocr_timeout_s)
            if ocr.applied:
                _write_atomic(_ocr_record(jd), json.dumps({"engine": ocr.engine, "pages": ocr.pages,
                                                           "warnings": ocr.warnings}))
        if ocr.applied:
            extract_from = jd / "ocr.pdf"
        info.warnings.extend(ocr.warnings)
    info.ocr = {"applied": ocr.applied, "engine": ocr.engine or None, "pages": list(ocr.pages)}

    stage("extracting", "Extracting text, fonts and layout…", 0.06)
    data = await asyncio.to_thread(extract_from.read_bytes)
    prefix = f"assets/pdf_{job_id[:8]}"
    extract, doc = await asyncio.to_thread(extract_document, data, out_dir, prefix, settings.max_pages)
    try:
        if len({(round(p.width), round(p.height)) for p in extract.pages}) > 1:
            info.warnings.append("Pages have different sizes; all pages use the most common size.")
        stage("rasterizing", "Rendering reference images of the pages…", 0.09)
        pngs = await asyncio.to_thread(rasterize_pages, extract_from, jd / "pages", s.raster_dpi)

        stage("assets", "Cropping figures, reading tables and classifying blocks…", 0.11)
        manifest: AssetManifest = await asyncio.to_thread(build_assets, extract, doc, out_dir, inspection, prefix)
        layouts = await asyncio.to_thread(build_layouts, extract, doc, manifest, inspection)
    finally:
        doc.close()
    ctx = RebuildCtx(job_id=job_id, job_dir=jd, out_dir=out_dir, source_pdf=extract_from, inspection=inspection,
                     layouts=layouts, manifest=manifest, page_pngs=pngs, vision=probe.vision_ok)
    _drop_scans_under_ocr_text(ctx)
    await asyncio.to_thread(_write_extract_json, ctx)
    return ctx


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

async def _build_page(ctx: RebuildCtx, n: int, tracker: _Tracker) -> PageResult:
    """Draft → compile, repair, measure, correct. Whatever goes wrong ends in the page's image or "failed"."""
    tracker.status(n, "generating")
    try:
        draft = await generate.write_page(ctx, n)
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 — PageGenerationFailed, or any fault in this one page
        logger.warning(f"{ctx.job_id[:8]} p{n}: no draft: {e}")
        return await refine.image_fallback_page(ctx, n, f"The model did not produce this page: {e}")
    pr = await refine.refine_page(ctx, n, draft.body, on_status=tracker.status)
    pr.vision_used = pr.vision_used or draft.vision_used
    pr.warnings = list(draft.warnings) + pr.warnings
    if pr.status == "failed":
        pr = await refine.image_fallback_page(ctx, n, "The page never compiled.", warnings=pr.warnings)
    return pr


async def _build_pages(ctx: RebuildCtx, tracker: _Tracker, info: _RunInfo, resume: bool) -> None:
    """All pages in parallel, under PDF2LATEX_CONCURRENCY. A job past the failure limit stops at once."""
    s = get_rebuild_settings()
    numbers = [p.number for p in ctx.inspection.pages]
    limit = s.max_failed_page_share * len(numbers)
    sem = asyncio.Semaphore(get_settings().concurrency)

    def account(pr: PageResult) -> None:
        ctx.results[pr.number] = pr
        tracker.finish(pr)
        info.rounds = sum(r.rounds for r in ctx.results.values())
        if sum(1 for r in ctx.results.values() if _failed(r)) > limit:
            raise _TooManyFailed()

    async def one(n: int) -> None:
        async with sem:
            pr = await _build_page(ctx, n, tracker)
            if pr.status != "failed":
                await asyncio.to_thread(_save_best, ctx, pr)
            account(pr)

    todo = []
    for n in numbers:
        saved = _load_best(ctx, n) if resume else None
        if saved is None:
            todo.append(n)
        else:
            ctx.results[n] = saved
            tracker.finish(saved)
    tasks = [asyncio.ensure_future(one(n)) for n in todo]
    failed_now = sum(1 for r in ctx.results.values() if _failed(r))
    try:
        if failed_now > limit:
            raise _TooManyFailed()
        await asyncio.gather(*tasks)
    except _TooManyFailed:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        failed = sum(1 for r in ctx.results.values() if _failed(r))
        raise WholeJobFallback(f"{failed} of {len(numbers)} pages could not be rebuilt by the model.") from None


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _mean(values: List[Optional[float]]) -> Optional[float]:
    vals = [float(v) for v in values if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def _low_confidence(ctx: RebuildCtx, build: package.MergedBuild) -> List[Dict[str, Any]]:
    target = get_settings().coverage_target
    rows = []
    for n, pr in sorted(ctx.results.items()):
        reasons = list(pr.low_confidence)
        cov = build.coverage.get(n)
        if cov is not None and cov < target and "coverage" not in reasons:
            reasons.append("coverage")
        if len(build.page_map.get(str(n)) or [n]) > 1 and "overflow" not in reasons:
            reasons.append("overflow")
        pr.low_confidence = reasons
        if reasons:
            rows.append({"page": n, "reasons": _reason_texts(reasons)})
    return rows


def _vision_detail(ctx: RebuildCtx, probe: Probe) -> Tuple[bool, str]:
    saw = sum(1 for pr in ctx.results.values() if pr.vision_used)
    if saw:
        return True, f"the model saw the page image on {saw} of {len(ctx.results)} pages"
    if probe.vision_ok:
        return False, "the gateway passed the image probe, but no page call kept its image"
    return False, probe.detail


def _report(ctx: RebuildCtx, build: package.MergedBuild, info: _RunInfo, probe: Probe,
            started: float) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(the job's `report`, with `report.rebuild` inside; the same `rebuild` dict)."""
    settings = get_settings()
    low = _low_confidence(ctx, build)
    pages = []
    for n, pr in sorted(ctx.results.items()):
        pages.append(PageReport(
            number=n, status=pr.status, similarity=None if pr.score is None else round(pr.score, 4),
            ssim=None if pr.ssim is None else round(pr.ssim, 4),
            text_coverage=round(build.coverage.get(n, pr.coverage or 0.0), 4),
            displacement=None if pr.displacement_pt is None else round(pr.displacement_pt, 2),
            attempts=pr.rounds + 1, compile_repairs=pr.repairs, fallback="image" if pr.fallback == "image" else None,
            overflow=pr.overflow or len(build.page_map.get(str(n)) or [n]) > 1, warnings=pr.warnings[:8]))
    source_pages = ctx.inspection.page_count
    warnings = list(info.warnings)
    drift = package.drifted_pages(build.page_map)
    if build.output_pages != source_pages or drift:
        warnings.append(f"The output has {build.output_pages} pages for {source_pages} source pages; pages "
                        f"{', '.join(map(str, drift[:12]))}{'…' if len(drift) > 12 else ''} did not land on their "
                        "own page number.")
    vision, detail = _vision_detail(ctx, probe)
    rebuild = {
        "engine": ENGINE, "vision": vision, "vision_detail": detail, "doc_type": ctx.inspection.doc_type,
        "ocr": info.ocr, "score_mean": _mean([p.similarity for p in pages]),
        "coverage_mean": _mean([p.text_coverage for p in pages]),
        "page_count_match": build.output_pages == source_pages, "output_pages": build.output_pages,
        "low_confidence": low, "rounds_used": sum(pr.rounds for pr in ctx.results.values()), "fallback_reason": None,
        "seconds": round(time.time() - started, 1),
    }
    report = ConversionReport(page_count=source_pages, pages=pages, warnings=warnings,
                              threshold=settings.sim_threshold, coverage_target=settings.coverage_target,
                              max_displacement=settings.max_displacement, compiled=True,
                              compiled_page_count=build.output_pages, model=model_name(), llm_used=True,
                              mode="editable", disclaimer=DISCLAIMER)
    data = report.to_dict()
    data["rebuild"] = rebuild
    return data, rebuild


# ---------------------------------------------------------------------------
# One document
# ---------------------------------------------------------------------------

@dataclass
class Rebuilt:
    ctx: RebuildCtx
    build: package.MergedBuild
    report: Dict[str, Any]
    rebuild: Dict[str, Any]
    zip_path: Path


async def rebuild_document(job_id: str, pdf_bytes: bytes, *, resume: bool = False, info: Optional[_RunInfo] = None,
                           started: Optional[float] = None) -> Rebuilt:
    """Every stage, for a job that already has a state. Raises WholeJobFallback when the rebuild gives up."""
    info = info if info is not None else _RunInfo()
    started = started if started is not None else time.time()
    jobs.update_job(job_id, status="running", stage="inspecting", queue_position=None, stage_counts=None,
                    message="Checking the model gateway…", progress=0.01)
    probe = await probe_gateway()
    info.probe = probe
    if not probe.text_ok:
        raise GatewayDown(f"The model gateway is unreachable ({probe.detail}).")

    ctx = await _analyse(job_id, pdf_bytes, info, probe, resume)

    jobs.update_job(job_id, status="running", stage="generating", progress=0.14, message="Writing the preamble…",
                    stage_counts={"pending": ctx.inspection.page_count})
    try:
        made = await generate.make_preamble(ctx)
    except generate.PreambleFailed as e:
        raise WholeJobFallback(f"The preamble could not be generated: {e}") from e
    info.warnings.extend(made.warnings)

    tracker = _Tracker(job_id, [p.number for p in ctx.inspection.pages])
    tracker.start()
    await _build_pages(ctx, tracker, info, resume)

    jobs.update_job(job_id, status="running", stage="packaging", progress=0.92,
                    message="Merging the pages and compiling the document…")

    def replaced(n: int) -> None:
        tracker.finish(ctx.results[n])

    build = await package.compile_merged(ctx, on_replace=replaced)
    if not build.compiled:
        reason = "; ".join(build.errors[:3])[:package.ERROR_TEXT_CHARS] or "no PDF was produced"
        raise WholeJobFallback(f"The merged document did not compile: {reason}")
    failed = sum(1 for r in ctx.results.values() if _failed(r))
    if failed > get_rebuild_settings().max_failed_page_share * len(ctx.results):
        raise WholeJobFallback(f"{failed} of {len(ctx.results)} pages could not be rebuilt by the model.")

    report, rebuild = _report(ctx, build, info, probe, started)
    state = jobs.load_job(job_id) or {}
    md = package.report_markdown(str(state.get("filename") or ""), rebuild, report["pages"], build.page_map,
                                 report["warnings"], report["model"])
    zip_path = await asyncio.to_thread(package.write_package, ctx, build, md)
    await asyncio.to_thread(shutil.rmtree, ctx.work_dir, True)
    return Rebuilt(ctx=ctx, build=build, report=report, rebuild=rebuild, zip_path=zip_path)


# ---------------------------------------------------------------------------
# Whole-job fallback
# ---------------------------------------------------------------------------

def _clear_rebuild_output(jd: Path) -> None:
    """Everything the rebuild left that the deterministic engine would pick up (it ships all of output/)."""
    for name in ("output", "build", "previews"):
        shutil.rmtree(jd / name, ignore_errors=True)
    for name in ("output.pdf", "package.zip"):
        (jd / name).unlink(missing_ok=True)
    (jd / "output").mkdir(parents=True, exist_ok=True)


async def _hand_to_deterministic(job_id: str, pdf_bytes: bytes, project_id: str, overwrite: bool, target_path: str,
                                 resume: bool, saved_state: Optional[Dict[str, Any]], reason: str, info: _RunInfo,
                                 started: float) -> None:
    from ..editable.run import run_editable

    logger.warning(f"Rebuild job {job_id} falls back to the deterministic engine: {reason}")
    jd = jobs.job_dir(job_id)
    await asyncio.to_thread(_clear_rebuild_output, jd)
    summary: Dict[str, Any] = {
        "engine": FALLBACK_ENGINE, "vision": False,
        "vision_detail": info.probe.detail if info.probe else "the gateway was not reached",
        "doc_type": info.doc_type, "ocr": info.ocr, "score_mean": None, "coverage_mean": None,
        "page_count_match": None, "output_pages": None, "low_confidence": [], "rounds_used": info.rounds,
        "fallback_reason": reason, "seconds": None,
    }
    state = jobs.load_job(job_id) or {}
    pages = [{"number": p.get("number"), "status": "pending", "similarity": None, "text_coverage": None,
              "attempts": 0, "fallback": None} for p in state.get("pages", [])]
    jobs.update_job(job_id, engine=FALLBACK_ENGINE, rebuild_fallback=summary, status="running", stage="extracting",
                    queue_position=None, stage_counts=None, report=None, pages=pages, progress=0.02,
                    message="Using the deterministic engine…")
    await run_editable(job_id, pdf_bytes, project_id, overwrite=overwrite, target_path=target_path, resume=resume,
                       saved_state=saved_state)
    final = jobs.load_job(job_id) or {}
    report = final.get("report") if isinstance(final.get("report"), dict) else {}
    gates = (report.get("editable") or {}).get("gates") or {}
    out_pages = report.get("compiled_page_count")
    summary.update(coverage_mean=gates.get("coverage"), output_pages=out_pages,
                   page_count_match=None if out_pages is None else out_pages == report.get("page_count"),
                   seconds=round(time.time() - started, 1))
    jobs.update_job(job_id, rebuild_fallback=summary)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def _run_admitted(job_id: str, pdf_bytes: bytes, project_id: str, overwrite: bool, target_path: str,
                        resume: bool, saved_state: Optional[Dict[str, Any]]) -> None:
    started = time.time()
    info = _RunInfo()
    try:
        done = await rebuild_document(job_id, pdf_bytes, resume=resume, info=info, started=started)
    except PdfValidationError as e:     # not the engine's fault: the other engine would refuse it as well
        jobs.update_job(job_id, status="error", stage="error", error=str(e), message=f"Conversion failed: {e}",
                        queue_position=None)
        return
    except WholeJobFallback as e:
        reason = str(e)
    except Exception as e:  # noqa: BLE001 — a fault in the rebuild must not cost the user their result
        logger.error(f"Rebuild job {job_id} hit an internal error: {e}", exc_info=True)
        reason = f"The rebuild hit an internal error: {str(e)[:300] or type(e).__name__}"
    else:
        await _deliver(job_id, project_id, overwrite, target_path, done, started)
        return
    await _hand_to_deterministic(job_id, pdf_bytes, project_id, overwrite, target_path, resume, saved_state, reason,
                                 info, started)


async def _deliver(job_id: str, project_id: str, overwrite: bool, target_path: str, done: Rebuilt,
                   started: float) -> None:
    from ..pipeline import _emit_trace

    extra = {"has_package": True, "page_map": done.build.page_map}
    jobs.update_job(job_id, status="running", stage="packaging", message="Writing files into the project…",
                    progress=0.96, report=done.report, result_extra=extra)
    try:
        written = await asyncio.to_thread(write_output_to_project, project_id, done.ctx.out_dir, "main.tex",
                                          target_path, overwrite, keep_existing=PACKAGE_EXTRAS)
        jobs.update_job(job_id, status="done", stage="done", progress=1.0, message="Conversion complete.",
                        result={**written, **extra}, report=done.report)
    except FileConflictError as fc:
        jobs.update_job(job_id, status="needs_confirmation", stage="needs_confirmation", progress=1.0,
                        message=str(fc), conflict_path=fc.path, report=done.report)
    except Exception as e:  # noqa: BLE001 — the job must always reach a terminal state
        logger.error(f"Rebuild job {job_id} could not write into the project: {e}", exc_info=True)
        jobs.update_job(job_id, status="error", stage="error", error=str(e), message=f"Conversion failed: {e}",
                        report=done.report)
    finally:
        trace = ConversionReport(page_count=done.report["page_count"], model=done.report["model"],
                                 compiled=True, pages=[PageReport(number=p["number"], similarity=p["similarity"],
                                                                  fallback=p["fallback"])
                                                       for p in done.report["pages"]])
        _emit_trace(job_id, project_id, trace, time.time() - started)


async def run_rebuild(job_id: str, pdf_bytes: bytes, project_id: str, overwrite: bool = False,
                      target_path: str = "main.tex", resume: bool = False,
                      saved_state: Optional[Dict[str, Any]] = None) -> None:
    """One editable job on the AI-rebuild engine. Reaches a terminal state on every path but cancellation."""
    jobs.update_job(job_id, engine=ENGINE)
    gate = _gate()
    await gate.acquire(job_id)
    try:
        await _run_admitted(job_id, pdf_bytes, project_id, overwrite, target_path, resume, saved_state)
    finally:
        gate.release(job_id)
