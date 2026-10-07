"""
pipeline.py — Per-page PDF → LaTeX conversion job.

  extract facts (PyMuPDF, no LLM) → one deterministic preamble → for every page, in parallel:
      LLM body (page image + facts) → compile the page on its own → fix compile errors
      (deterministic heal, then ≤ PDF2LATEX_MAX_COMPILE_REPAIRS LLM fixes) → render and compare
      with the original (SSIM) → one quality re-run when below the threshold → best version kept
  → merge into main.tex → final compile and page-count check → write into the project.

A page the LLM cannot produce, or that never compiles, falls back to a deterministic
positioned layout of its facts, then to the page image; the report says which.
"""

import asyncio
import base64
import logging
import re
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from compile_queue import CompileQueueFullError, compile_queue
from compiler import compile_latex

from . import jobs
from .config import Pdf2LatexSettings, get_settings
from .extract import extract_document, render_page_png
from .facts import fallback_body, page_facts
from .geometry import (describe_unresolved, drop_condensed_sizes, fitted_texts, page_mismatches,
                       repair_body, source_blocks)
from .llm import LLMCallFailed, complete, llm_available, model_name
from .models import RGB, ConversionReport, DocExtract, PageExtract, PageReport
from .preamble import (
    FontPlan,
    Geometry,
    assemble_document,
    background_command,
    body_of,
    build_preamble,
    clean_body,
    collect_colors,
    color_name,
    page_for_line,
    page_geometry,
    plan_fonts,
    referenced_files,
    standalone_page,
)
from .prompts import (
    COMPILE_FIX_SYSTEM,
    COMPILE_FIX_USER,
    PAGE_SYSTEM_PROMPT,
    QUALITY_NOTE,
    SHORT_RETRY_NOTE,
    fill,
    page_user_prompt,
)
from .storage import FileConflictError, write_output_to_project
from .texutil import sanitize_unicode
from .verify import (Region, WordBox, compare_pages, compare_words, describe_regions, displacement,
                     extract_words_from_pdf, render_pdf_pages, tokenize, words_with_boxes)

logger = logging.getLogger("pdf2latex.pipeline")

LLM_IMAGE_DPI = 150
MIN_TEXT_COVERAGE = 0.6  # a generated body with fewer source words than this is retried once
PAGE_COMPILE_TIMEOUT = 90
OVERFLOW_PENALTY = 0.9
FALLBACK_MARGIN = 0.03  # the positioned layout rescues an unacceptable page only when clearly closer
EXTRA_TOLERANCE = 0.05  # invented words tolerated, as a share of the page's source words
QUEUE_RETRIES = 6       # compile_queue already waits COMPILE_QUEUE_TIMEOUT for a slot on each try
QUEUE_BACKOFF_MAX_S = 8.0


class ConversionError(RuntimeError):
    pass


@dataclass
class Score:
    value: float
    ssim: float
    pixel_diff: float
    coverage: float
    missing: List[str]
    overflow: bool
    regions: List[Region]
    extra: List[str] = field(default_factory=list)
    extra_ratio: float = 0.0
    shift_pt: float = 0.0
    displacement: Optional[float] = None  # median pt a word moved from its place in the PDF
    clipped: bool = False  # text runs off the page edge

    @property
    def rank(self) -> float:
        """
        Ranking used to pick between two candidate versions of the same page. The words are
        the content, so a missing or invented word outweighs a visual difference: the visual
        number is partly a measure of how closely the type was re-set, which a faithful
        reflow legitimately loses on.
        """
        moved = (self.displacement or 0.0) / 100.0
        return self.value - 2.0 * (1.0 - self.coverage) - 1.0 * self.extra_ratio - moved


@dataclass
class Ctx:
    job_id: str
    settings: Pdf2LatexSettings
    jd: Path
    out_dir: Path
    doc: object  # pymupdf.Document (not thread-safe: guard with doc_lock)
    extract: DocExtract
    geom: Geometry
    fonts: FontPlan
    colors: Dict[str, RGB]
    preamble: str
    has_tex: bool
    use_llm: bool
    report: ConversionReport
    originals: List[np.ndarray] = field(default_factory=list)
    bodies: Dict[int, str] = field(default_factory=dict)
    b64: Dict[str, str] = field(default_factory=dict)
    src_words: Dict[int, List[WordBox]] = field(default_factory=dict)
    src_blocks: Dict[int, Tuple[list, Tuple[float, float]]] = field(default_factory=dict)
    doc_lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def threshold(self) -> float:
        return self.settings.sim_threshold

    def acceptable(self, sc: Optional["Score"]) -> bool:
        """
        Is this page good enough to ship? It must compile to exactly ONE page carrying every
        word of the source and nothing invented.

        Visual similarity only has to clear a floor. It deliberately does not decide the
        question: full-page SSIM is dominated by the white background, so it scores a blank
        page around 0.73 and a page missing half its text around 0.86, while a pixel-perfect
        page nudged down by a single point scores about 0.83. Gating on it meant every page of
        a normal document missed the target, bought a re-run that could not help, and was then
        replaced by the positioned-layout fallback. Text coverage is the signal that actually
        separates a faithful page from a broken one.
        """
        return (sc is not None and not sc.overflow and not sc.clipped
                and sc.coverage >= self.settings.coverage_target
                and sc.extra_ratio <= EXTRA_TOLERANCE
                and sc.value >= self.settings.visual_floor
                and (sc.displacement is None or sc.displacement <= self.settings.max_displacement))

    @property
    def default_color(self) -> str:
        return color_name((0, 0, 0)) if not self.colors else next(iter(self.colors))

    def page_report(self, n: int) -> PageReport:
        return self.report.pages[n - 1]


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------

def _progress(ctx: Ctx, stage: str, message: str, progress: float) -> None:
    jobs.update_job(ctx.job_id, status="running", stage=stage, message=message, progress=round(progress, 3))


def _page_status(ctx: Ctx, pr: PageReport, status: Optional[str] = None) -> None:
    if status:
        pr.status = status
    jobs.update_page(ctx.job_id, pr.number, status=pr.status, similarity=pr.similarity, attempts=pr.attempts,
                     fallback=pr.fallback, warnings=pr.warnings, text_coverage=pr.text_coverage,
                     style_mismatches=pr.style_mismatches, overflow_lines=pr.overflow_lines,
                     geometry_repairs=pr.geometry_repairs)
    done = sum(1 for p in ctx.report.pages if p.status in ("done", "below_threshold", "failed"))
    total = max(1, len(ctx.report.pages))
    jobs.update_job(ctx.job_id, progress=round(0.15 + 0.75 * done / total, 3),
                    message=f"Converting pages… {done}/{total} done")


# ---------------------------------------------------------------------------
# Compile & render
# ---------------------------------------------------------------------------

def _with_background(page: PageExtract, body: str) -> str:
    return (background_command(page.background) + "\n" + body) if page.background else body


def _files_for(ctx: Ctx, tex: str) -> List[Dict[str, str]]:
    files = []
    for rel in referenced_files(tex):
        path = ctx.out_dir / rel
        if not path.is_file():
            continue
        if rel not in ctx.b64:
            ctx.b64[rel] = base64.b64encode(path.read_bytes()).decode("ascii")
        files.append({"filename": rel, "data": ctx.b64[rel]})
    return files


async def compile_tex(ctx: Ctx, tex: str, timeout_s: int) -> Tuple[Optional[bytes], str]:
    """
    Compiles with pdfLaTeX through the shared compile queue. Returns (pdf bytes or None, log).
    Strict: a PDF produced despite TeX errors, or a reference to a missing image, counts as a failure.
    """
    missing = [rel for rel in referenced_files(tex) if not (ctx.out_dir / rel).is_file()]
    if missing:
        return None, "\n".join(f"! LaTeX Error: File `{rel}' not found (use the exact file paths from the facts)."
                               for rel in missing)
    files = _files_for(ctx, tex)
    res = None
    for attempt in range(QUEUE_RETRIES):
        try:
            res = await compile_queue.submit(
                compile_latex, latex_code=tex, engine="pdflatex", files=files,
                project_id=None, timeout_seconds=timeout_s, persist_synctex=False,
                allow_recovery=False,  # the model fixes the errors; patch-and-retry is wasted here
            )
            break
        except CompileQueueFullError:
            await asyncio.sleep(min(QUEUE_BACKOFF_MAX_S, 1.5 * (attempt + 1)))
    if res is None:
        return None, "Compile queue is saturated."
    log = res.get("raw_log") or res.get("error_log") or res.get("log") or ""
    errors = res.get("errors")
    if res.get("success") and res.get("pdf_base64") and errors == []:
        return base64.b64decode(res["pdf_base64"]), log
    if errors:
        return None, "\n".join(errors) + "\n" + log
    # No error list: the compile service only got a PDF by patching the code (e.g. disabling packages)
    return None, log or "Compilation failed."


def _render_bytes(pdf: bytes, dpi: int) -> List[np.ndarray]:
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tf:
        tf.write(pdf)
        tf.flush()
        return render_pdf_pages(Path(tf.name), dpi)


def _error_lines(log: str) -> List[int]:
    nums = [int(m) for m in re.findall(r"\.tex:(\d+):", log or "")]
    nums += [int(m) for m in re.findall(r"^l\.(\d+)", log or "", flags=re.MULTILINE)]
    return nums


def _log_errors(log: str, limit: int = 2500) -> str:
    lines = (log or "").splitlines()
    keep: List[str] = []
    for i, line in enumerate(lines):
        if line.startswith("!") or ".tex:" in line or re.match(r"^l\.\d+", line):
            keep.extend(lines[i:i + 3] if line.startswith("!") else [line])
    text = "\n".join(dict.fromkeys(keep)) or (log or "")[-limit:]
    return text[-limit:]


def _tex_available() -> bool:
    return bool(shutil.which("latexmk") or shutil.which("pdflatex"))


def _page_count(pdf: bytes) -> int:
    import pymupdf
    with pymupdf.open(stream=pdf, filetype="pdf") as d:
        return d.page_count


# ---------------------------------------------------------------------------
# Per-page steps
# ---------------------------------------------------------------------------

def _prepare(body: str, pr: PageReport) -> str:
    body, dropped = sanitize_unicode(body)
    if dropped:
        pr.warnings.append(f"Dropped {len(dropped)} character(s) pdfLaTeX cannot typeset: {''.join(dropped)[:40]}")
    return body


async def _llm(ctx: Ctx, system: str, user: str, image: Optional[bytes], label: str) -> str:
    s = ctx.settings
    return await complete(system, user, image, timeout=s.page_timeout, retries=s.page_retries,
                          concurrency=s.concurrency, label=f"{ctx.job_id[:8]}:{label}")


async def _generate(ctx: Ctx, page: PageExtract, facts: Dict, png: bytes, pr: PageReport,
                    note: str = "", allow_short_retry: bool = True) -> Optional[str]:
    """LLM body for a page; retried once when it comes back empty or misses most of the text."""
    colors = list(ctx.colors)
    source = tokenize(page.text)
    extra = note
    for attempt in range(2 if allow_short_retry else 1):
        pr.attempts += 1
        try:
            raw = await _llm(ctx, PAGE_SYSTEM_PROMPT, page_user_prompt(facts, colors, extra), png, f"p{page.number}")
        except LLMCallFailed as e:
            pr.warnings.append(f"LLM generation failed: {e}")
            return None
        body = clean_body(raw)
        cov = compare_words(source, tokenize(body))
        if body and (not source or cov.coverage >= MIN_TEXT_COVERAGE):
            return _prepare(body, pr)
        extra = (note + "\n" if note else "") + fill(
            SHORT_RETRY_NOTE, COVERAGE=f"{cov.coverage:.0%}", MISSING=", ".join(w for w, _ in cov.missing[:30]))
    pr.warnings.append("The model's answer was empty or left out most of the page text.")
    return None


def _auto_heal(ctx: Ctx, page: PageExtract, tex: str, log: str) -> Optional[str]:
    from latex_error_fixer import auto_heal_latex_code
    healed, fixes = auto_heal_latex_code(tex, log)
    if not fixes:
        return None
    body = body_of(healed, page.number)
    if body is None:
        return None
    if page.background:
        body = body.replace(background_command(page.background) + "\n", "", 1)
    return body


async def _compile_page(ctx: Ctx, page: PageExtract, body: str, pr: PageReport,
                        allow_llm: bool = True) -> Tuple[str, Optional[bytes], str]:
    """Compiles one page on its own; deterministic heal first, then up to N LLM fixes."""
    healed = False
    repairs = 0
    while True:
        tex = standalone_page(ctx.preamble, _with_background(page, body), page.number)
        pdf, log = await compile_tex(ctx, tex, PAGE_COMPILE_TIMEOUT)
        if pdf is not None:
            return body, pdf, log
        if not healed:
            healed = True
            fixed = _auto_heal(ctx, page, tex, log)
            if fixed and fixed != body:
                body = fixed
                continue
        if not (allow_llm and ctx.use_llm) or repairs >= ctx.settings.max_compile_repairs:
            return body, None, log
        repairs += 1
        pr.compile_repairs += 1
        _page_status(ctx, pr, "repairing")
        try:
            raw = await _llm(ctx, COMPILE_FIX_SYSTEM, fill(COMPILE_FIX_USER, ERRORS=_log_errors(log), BODY=body),
                             None, f"p{page.number}-fix{repairs}")
        except LLMCallFailed as e:
            pr.warnings.append(f"Compile repair failed: {e}")
            return body, None, log
        fixed = _prepare(clean_body(raw), pr)
        if not fixed or fixed == body:
            return body, None, log
        body = fixed


async def _fallbacks(ctx: Ctx, page: PageExtract, pr: PageReport) -> Tuple[str, Optional[bytes]]:
    """Positioned layout of the facts; if even that fails to compile, the page image."""
    body = fallback_body(page, ctx.geom, ctx.fonts)
    body, pdf, _log = await _compile_page(ctx, page, body, pr, allow_llm=False)
    if pdf is not None:
        pr.fallback = "layout"
        return body, pdf
    rel = f"{ctx.extract.asset_prefix}/page{page.number}_render.png"
    with ctx.doc_lock:
        png = render_page_png(ctx.doc, page.number, LLM_IMAGE_DPI)
    (ctx.out_dir / rel).write_bytes(png)
    page.background = None
    body = background_command(rel) + "\n\\null"
    pr.fallback = "image"
    pr.warnings.append("The page could not be compiled as text; it is embedded as an image.")
    body, pdf, _log = await _compile_page(ctx, page, body, pr, allow_llm=False)
    return body, pdf


async def _score(ctx: Ctx, page: PageExtract, pdf: bytes) -> Optional[Score]:
    rendered = await asyncio.to_thread(_render_bytes, pdf, ctx.settings.render_dpi)
    if not rendered:
        return None
    cmp = await asyncio.to_thread(compare_pages, ctx.originals[page.number - 1], rendered[0], ctx.settings.render_dpi)
    overflow = len(rendered) > 1
    words_by_page = await asyncio.to_thread(extract_words_from_pdf, pdf)
    cov = compare_words(tokenize(page.text), [w for i in sorted(words_by_page) for w in words_by_page[i]])
    moved = await asyncio.to_thread(displacement, ctx.src_words.get(page.number, []), words_with_boxes(pdf, 0))
    return Score(value=cmp.score * (OVERFLOW_PENALTY if overflow else 1.0), ssim=cmp.ssim, pixel_diff=cmp.pixel_diff,
                 coverage=cov.coverage, missing=[w for w, _ in cov.missing], overflow=overflow, regions=cmp.regions,
                 extra=[w for w, _ in cov.extra], extra_ratio=cov.extra_ratio, shift_pt=cmp.shift_pt,
                 displacement=moved)


GEOMETRY_ROUNDS = 2
GEOMETRY_RANK_TOLERANCE = 0.02  # a style repair may cost this much visual rank (bold is wider)
_FIXABLE = ("weight", "italic", "overflow_right")


def _src_blocks(ctx: Ctx, n: int):
    if n not in ctx.src_blocks:
        with ctx.doc_lock:
            ctx.src_blocks[n] = source_blocks(ctx.doc, n)
    return ctx.src_blocks[n]


async def _polish(ctx: Ctx, page: PageExtract, body: str, pdf: bytes, sc: Score,
                  pr: PageReport) -> Tuple[str, bytes, Score, list]:
    """
    Compares the compiled page with the PDF line by line and fixes, in place and
    without the LLM, what can be fixed locally: lost bold/italic and lines that
    run past their right edge. A repair is kept only if it does not cost text
    coverage or more than a sliver of visual rank. Returns the (possibly
    repaired) page and the mismatches still left.
    """
    try:
        src, size = await asyncio.to_thread(_src_blocks, ctx, page.number)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"source blocks unavailable for page {page.number}: {e}")
        return body, pdf, sc, []
    mism = await asyncio.to_thread(page_mismatches, src, size, pdf)
    for _ in range(GEOMETRY_ROUNDS):
        fixable = [m for m in mism if m.kind in _FIXABLE]
        if not fixable:
            break
        ordered = [(ln.text.strip(), ln.bbox[0], ln.baseline) for ln in page.lines]
        new_body, repairs, _left = repair_body(body, fixable, ordered)
        if not repairs:
            break
        nb, npdf, _log = await _compile_page(ctx, page, new_body, pr, allow_llm=False)
        if npdf is None:
            break
        nsc = await _score(ctx, page, npdf)
        if (nsc is None or nsc.coverage + 1e-9 < sc.coverage or (nsc.overflow and not sc.overflow)
                or nsc.rank < sc.rank - GEOMETRY_RANK_TOLERANCE):
            break
        body, pdf, sc = nb, npdf, nsc
        pr.geometry_repairs.extend(repairs)
        mism = await asyncio.to_thread(page_mismatches, src, size, pdf)
    mism = drop_condensed_sizes(mism, fitted_texts(pr.geometry_repairs))
    sc.clipped = any(m.kind == "clipped" for m in mism)
    pr.style_mismatches = sum(1 for m in mism if m.kind in ("weight", "italic", "size"))
    pr.overflow_lines = sum(1 for m in mism if m.kind in ("overflow_right", "clipped"))
    return body, pdf, sc, mism


def _differences(sc: Score) -> str:
    """The note for a re-run: the concrete, fixable defects first."""
    parts = []
    if sc.overflow:
        parts.append("- The page overflowed onto a second page: tighten spacing so everything fits on one page.")
    if sc.missing:
        parts.append(f"- Missing words ({sc.coverage:.0%} of the source text present) — add these back verbatim: "
                     + ", ".join(sc.missing[:30]))
    if sc.extra and sc.extra_ratio > EXTRA_TOLERANCE:
        parts.append("- Words in your output that are NOT in the source — remove them: " + ", ".join(sc.extra[:20]))
    if sc.displacement is not None and sc.displacement > 20.0:
        parts.append(f"- The text is in the WRONG PLACES: the typical word is {sc.displacement:.0f}pt away from "
                     f"where it sits in the original. Follow the block structure and each line's gap/top; keep "
                     f"blocks in the order given and do not weave a side block into the running text.")
    if abs(sc.shift_pt) >= 3.0:
        where = "lower" if sc.shift_pt > 0 else "higher"
        parts.append(f"- The whole page sits about {abs(sc.shift_pt):.0f}pt {where} than the original: "
                     f"adjust the leading \\vspace before the first line.")
    parts.append("- Regions that look different (pt from the page top-left; compare positions, sizes, spacing):\n"
                 + describe_regions(sc.regions))
    return "\n".join(parts)


async def _process_page(ctx: Ctx, page: PageExtract, sem: asyncio.Semaphore) -> None:
    n = page.number
    pr = ctx.page_report(n)
    async with sem:
        _page_status(ctx, pr, "generating")
        facts, unknown = page_facts(page, ctx.geom, ctx.fonts, len(ctx.extract.pages), ctx.default_color)
        if unknown:
            pr.warnings.append(f"{len(unknown)} character(s) have no pdfLaTeX equivalent and were dropped: "
                               f"{''.join(sorted(unknown))[:40]}")
        png = b""
        body: Optional[str] = None
        if ctx.use_llm and not page.is_scanned:
            def _render() -> bytes:
                with ctx.doc_lock:
                    return render_page_png(ctx.doc, n, LLM_IMAGE_DPI)
            png = await asyncio.to_thread(_render)
            body = await _generate(ctx, page, facts, png, pr)
        if body is None:
            body = fallback_body(page, ctx.geom, ctx.fonts)
            pr.fallback = "layout"

        if not ctx.has_tex:
            ctx.bodies[n] = body
            _page_status(ctx, pr, "done")
            return

        _page_status(ctx, pr, "compiling")
        body, pdf, log = await _compile_page(ctx, page, body, pr, allow_llm=pr.fallback is None)
        if pdf is None:
            if pr.fallback is None:
                first_error = next(iter(_log_errors(log, 300).splitlines()), "")[:200]
                pr.warnings.append("Did not compile after repairs; using the positioned-layout fallback."
                                   + (f" Last error: {first_error}" if first_error else ""))
            body, pdf = await _fallbacks(ctx, page, pr)

        sc: Optional[Score] = None
        if pdf is not None:
            _page_status(ctx, pr, "verifying")
            sc = await _score(ctx, page, pdf)
            unresolved: list = []
            if sc is not None and not page.is_scanned:
                body, pdf, sc, unresolved = await _polish(ctx, page, body, pdf, sc, pr)

            # 1. Re-run only for a defect the model can act on: missing or invented words,
            #    an overflow, or a page that looks nothing like the original. A page that is
            #    merely re-set differently is already right, and asking again cannot improve
            #    it — that request used to be made for every page of every document.
            if (ctx.settings.quality_rerun and ctx.use_llm and pr.fallback is None
                    and sc is not None and not ctx.acceptable(sc)):
                _page_status(ctx, pr, "rerunning")
                details = _differences(sc)
                style = describe_unresolved(unresolved)
                if style:
                    details += "\n- Text style / right-edge differences (fix each):\n" + style
                note = fill(QUALITY_NOTE, SCORE=f"{sc.value:.2f}", TARGET=f"{ctx.threshold:.2f}",
                            DETAILS=details, BODY=body)
                body2 = await _generate(ctx, page, facts, png, pr, note=note, allow_short_retry=False)
                if body2:
                    body2, pdf2, _ = await _compile_page(ctx, page, body2, pr)
                    sc2 = await _score(ctx, page, pdf2) if pdf2 is not None else None
                    if sc2 is not None and pdf2 is not None:
                        body2, pdf2, sc2, _unres2 = await _polish(ctx, page, body2, pdf2, sc2, pr)
                    if sc2 is not None and sc2.rank > sc.rank:
                        body, pdf, sc = body2, pdf2, sc2
                    else:
                        pr.warnings.append("Quality re-run did not improve the page; kept the first version.")

            # 2. Scale an overflowing page to fit before judging it, so a page that is merely
            #    a few points too tall is not handed to the fallback.
            if sc is not None and sc.overflow:
                fitted, pdf3, _ = await _compile_page(ctx, page, "\\obfit{%\n" + body + "\n}", pr, allow_llm=False)
                sc3 = await _score(ctx, page, pdf3) if pdf3 is not None else None
                if sc3 is not None and not sc3.overflow:
                    body, pdf, sc = fitted, pdf3, sc3
                    pr.warnings.append("The page content was scaled down slightly to fit on one page.")
                else:
                    pr.warnings.append("The page content overflows onto an extra page.")

            # 3. The positioned layout RESCUES a page, it does not compete with one. It is a
            #    grid of absolutely-placed TikZ nodes: pixel-close but not editable LaTeX, which
            #    is the point of the import. So it only takes over a page that is still not
            #    acceptable — never one that just reflowed differently, as it used to whenever
            #    the visual score missed the target (i.e. nearly always).
            if sc is not None and pr.fallback is None and not ctx.acceptable(sc):
                fb_body, fb_pdf, _ = await _compile_page(ctx, page, fallback_body(page, ctx.geom, ctx.fonts), pr,
                                                         allow_llm=False)
                fb = await _score(ctx, page, fb_pdf) if fb_pdf is not None else None
                if fb is not None and not fb.overflow and fb.rank > sc.rank + FALLBACK_MARGIN:
                    pr.warnings.append(f"The positioned layout reproduced this page more faithfully "
                                       f"({fb.value:.2f} vs {sc.value:.2f}, text {fb.coverage:.0%} vs "
                                       f"{sc.coverage:.0%}), so it is used instead of the model's version.")
                    body, pdf, sc = fb_body, fb_pdf, fb
                    pr.fallback = "layout"

        if sc is not None:
            pr.similarity, pr.ssim, pr.pixel_diff = round(sc.value, 4), round(sc.ssim, 4), round(sc.pixel_diff, 4)
            pr.text_coverage, pr.overflow = round(sc.coverage, 4), sc.overflow
            pr.extra_ratio, pr.shift_pt = round(sc.extra_ratio, 4), sc.shift_pt
            pr.displacement = round(sc.displacement, 2) if sc.displacement is not None else None
            if sc.displacement is not None and sc.displacement > ctx.settings.max_displacement:
                pr.warnings.append(f"The text is placed differently from the PDF: the typical word is "
                                   f"{sc.displacement:.0f}pt away from its position in the original.")
            if sc.missing:
                pr.warnings.append(f"Words from the PDF missing in the output ({sc.coverage:.1%} present): "
                                   + ", ".join(sc.missing[:12]))
            if sc.extra and sc.extra_ratio > EXTRA_TOLERANCE:
                pr.warnings.append(f"Words in the output that are not in the PDF ({sc.extra_ratio:.0%} extra): "
                                   + ", ".join(sc.extra[:12]))
            status = "done" if ctx.acceptable(sc) else "below_threshold"
        else:
            status = "failed" if pdf is None else "done"
        ctx.bodies[n] = body
        _page_status(ctx, pr, status)


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def _document(ctx: Ctx) -> str:
    pages = {p.number: p for p in ctx.extract.pages}
    return assemble_document(ctx.preamble, {n: _with_background(pages[n], b) for n, b in ctx.bodies.items()})


async def _merge_and_compile(ctx: Ctx) -> Tuple[str, Optional[bytes]]:
    tex = _document(ctx)
    if not ctx.has_tex:
        return tex, None
    n_pages = len(ctx.extract.pages)
    pages = {p.number: p for p in ctx.extract.pages}
    log = ""
    for _round in range(3):
        pdf, log = await compile_tex(ctx, tex, int(60 + 6 * n_pages))
        if pdf is not None:
            return tex, pdf
        failing: Set[int] = {p for p in (page_for_line(tex, ln) for ln in _error_lines(log)) if p}
        if not failing:
            break
        for n in sorted(failing):
            pr = ctx.page_report(n)
            ctx.bodies[n] = fallback_body(pages[n], ctx.geom, ctx.fonts)
            pr.fallback = "layout"
            pr.warnings.append("Broke the merged document; replaced by the positioned-layout fallback.")
            _page_status(ctx, pr)
        tex = _document(ctx)
    ctx.report.warnings.append("The merged document did not compile: " + _log_errors(log, 600))
    return tex, None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run_conversion(job_id: str, pdf_bytes: bytes, project_id: str,
                         overwrite: bool = False, target_path: str = "main.tex") -> None:
    settings = get_settings()
    jd = jobs.job_dir(job_id)
    out_dir = jd / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    doc = None
    report = ConversionReport(page_count=0, threshold=settings.sim_threshold, model=model_name(),
                              coverage_target=settings.coverage_target,
                              max_displacement=settings.max_displacement)
    try:
        _set = lambda **kw: jobs.update_job(job_id, status="running", **kw)  # noqa: E731
        _set(stage="extracting", message="Extracting text, colors, images and vectors…", progress=0.02)
        extract, doc = await asyncio.to_thread(extract_document, pdf_bytes, out_dir, f"assets/pdf_{job_id[:8]}",
                                               settings.max_pages)
        report.page_count = len(extract.pages)
        report.pages = [PageReport(number=p.number, warnings=list(p.warnings)) for p in extract.pages]
        (jd / "source.pdf").write_bytes(doc.tobytes())

        has_tex = _tex_available()
        use_llm = llm_available()
        report.llm_used = use_llm
        if not use_llm:
            report.warnings.append("No LLM is configured for the AI copilot (GEMINI_WEB2API_*): every page uses the "
                                   "deterministic positioned layout.")
        if not has_tex:
            report.warnings.append("No pdfLaTeX on the server: the LaTeX is generated but not compiled or verified.")

        geom = page_geometry(extract)
        colors = collect_colors(extract)
        fonts = plan_fonts(extract)
        if len({(round(p.width), round(p.height)) for p in extract.pages}) > 1:
            report.warnings.append("Pages have different sizes; all pages use the most common size.")
        ctx = Ctx(job_id=job_id, settings=settings, jd=jd, out_dir=out_dir, doc=doc, extract=extract, geom=geom,
                  fonts=fonts, colors=colors, preamble=build_preamble(geom, colors, fonts), has_tex=has_tex,
                  use_llm=use_llm, report=report)

        _set(stage="rendering", message="Rendering reference pages…", progress=0.08)
        ctx.originals = await asyncio.to_thread(render_pdf_pages, jd / "source.pdf", settings.render_dpi)
        src_bytes = (jd / "source.pdf").read_bytes()
        ctx.src_words = {pg.number: await asyncio.to_thread(words_with_boxes, src_bytes, pg.number - 1)
                         for pg in extract.pages}

        _set(stage="converting", message=f"Converting {len(extract.pages)} page(s)…", progress=0.15)
        sem = asyncio.Semaphore(settings.concurrency)
        await asyncio.gather(*(_process_page(ctx, p, sem) for p in extract.pages))

        _set(stage="merging", message="Merging pages and compiling the document…", progress=0.92)
        tex, pdf = await _merge_and_compile(ctx)
        if pdf is not None:
            report.compiled = True
            report.compiled_page_count = await asyncio.to_thread(_page_count, pdf)
            if report.compiled_page_count != report.page_count:
                report.warnings.append(f"The compiled document has {report.compiled_page_count} pages; "
                                       f"the PDF has {report.page_count}.")
            (jd / "output.pdf").write_bytes(pdf)
        (out_dir / "main.tex").write_text(tex, encoding="utf-8")

        jobs.update_job(job_id, stage="writing", message="Writing files into the project…", progress=0.96,
                        report=report.to_dict())
        try:
            written = await asyncio.to_thread(write_output_to_project, project_id, out_dir, "main.tex",
                                              target_path, overwrite)
            jobs.update_job(job_id, status="done", stage="done", progress=1.0, message="Conversion complete.",
                            result=written, report=report.to_dict())
        except FileConflictError as fc:
            jobs.update_job(job_id, status="needs_confirmation", stage="needs_confirmation", progress=1.0,
                            message=str(fc), conflict_path=fc.path, report=report.to_dict())
    except Exception as e:  # noqa: BLE001 — the job must always reach a terminal state
        logger.error(f"PDF conversion job {job_id} failed: {e}", exc_info=True)
        jobs.update_job(job_id, status="error", stage="error", error=str(e), message=f"Conversion failed: {e}",
                        report=report.to_dict() if report.page_count else None)
    finally:
        if doc is not None:
            doc.close()
        _emit_trace(job_id, project_id, report, time.time() - started)


def _emit_trace(job_id: str, project_id: str, report: ConversionReport, elapsed: float) -> None:
    try:
        from trace import ConversionTrace, trace_manager
        trace_manager.emit_conversion_trace(ConversionTrace(
            job_id=job_id, project_id=project_id, model=report.model, num_pages=report.page_count,
            page_scores=[p.similarity for p in report.pages], mean_similarity=report.mean_similarity,
            fallback_pages=sum(1 for p in report.pages if p.fallback), warnings=len(report.warnings),
            compile_success=report.compiled, total_latency_ms=elapsed * 1000,
            style_mismatches=sum(p.style_mismatches or 0 for p in report.pages),
            overflow_lines=sum(p.overflow_lines or 0 for p in report.pages),
            geometry_repairs=sum(len(p.geometry_repairs) for p in report.pages),
        ))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"Conversion trace emission failed: {e}")


async def commit_pending_output(job_id: str, overwrite: bool, target_path: str) -> Dict:
    """Finishes a needs_confirmation job by writing its output with the user's choice."""
    state = jobs.load_job(job_id)
    if not state or state.get("status") != "needs_confirmation":
        raise ConversionError("This conversion is not waiting for confirmation.")
    out_dir = jobs.job_dir(job_id) / "output"
    written = await asyncio.to_thread(write_output_to_project, state["project_id"], out_dir, "main.tex",
                                      target_path, overwrite)
    jobs.update_job(job_id, status="done", stage="done", message="Conversion complete.", result=written,
                    conflict_path=None)
    return written
