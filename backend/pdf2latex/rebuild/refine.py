"""
refine.py — Stages 7 and 8 of the AI-rebuild pipeline: compile a generated page body, repair it,
then measure it against the source page and correct it, keeping the best version.

  compiling   `compile_body` builds `build/p{n}_{tag}/main.tex` (preamble + `\\obpagestart{n}` + body)
              next to a relative `assets` symlink and compiles it in the sandbox. A compile counts
              only with a PDF, zero TeX errors and no missing file. A failed compile gets the
              deterministic heal (`latex_error_fixer.auto_heal_latex_code`) once, then up to
              `max_compile_repairs` LLM fix calls that see the errors mapped back to BODY lines. An
              error located in the preamble cannot be fixed here: the page fails with "preamble error".
  verifying   `measure` scores the compiled page against the source page: visual comparison
              (`verify.compare_pages`), word coverage against the extracted text, word displacement,
              overflow (estimated in lines from the ink of the extra pages), and the placed size and
              position of every figure versus the asset manifest. The mismatch report built from that
              goes into a correction call (plus both page images when the gateway takes images); the
              answer is recompiled, re-measured and kept only if it ranks higher. The loop stops when
              the page passes, when a round gains less than `min_gain`, or after `refine_rounds`.
  fallback    a page that never compiles, or ends below the visual floor without the text, is embedded
              as a render of the source page (`fallback="image"`).

Never raises for a per-page failure (cancellation excepted): the result's status, warnings and
low-confidence reasons carry it. The match `value` (0..1) mirrors `pipeline._score` but weights
text coverage and word placement above the visual number, which full-page SSIM inflates on a
mostly white page (see `config.py`).
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import re
import shutil
import signal
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence, Set, Tuple

import numpy as np

from ..config import get_settings
from ..llm import LLMCallFailed, complete_ex
from ..verify import (Region, WordBox, compare_pages, compare_words, describe_regions, displacement,
                      extract_words_from_pdf, render_pdf_pages, tokenize, words_with_boxes)
from . import sandbox
from .document import ASSET_ROOT, standalone_page
from .model import Asset, PageLayout, PageResult, RebuildCtx
from .refine_prompts import (COMPILE_FIX_SYSTEM, COMPILE_FIX_USER, CORRECT_SYSTEM, CORRECT_USER,
                             IMAGES_NOTE, fill)
from .settings import get_rebuild_settings

try:  # the generation stage's body guard, when that module is present
    from .generate import guard_body as _generate_guard
except ImportError:
    _generate_guard = None

logger = logging.getLogger("pdf2latex.rebuild.refine")

OVERFLOW_PENALTY = 0.9      # as pipeline._score: an overflowing page cannot pass
W_VISUAL, W_COVERAGE, W_PLACE = 0.30, 0.45, 0.25   # weights of the match value
SETTLE_PT = 4.0             # median word displacement a faithful re-setting has anyway
EXTRA_TOLERANCE = 0.05      # invented words tolerated, as a share of the source's (pipeline.EXTRA_TOLERANCE)
FIGURE_SIZE_TOL = 0.10      # a placed figure this much larger/smaller than the source is reported
FIGURE_POS_TOL_PT = 12.0
BLOCK_DRIFT_PT = 6.0
INK_LEVEL = 160             # grey level below which a pixel is ink (overflow estimate)
DEFAULT_LINE_PT = 13.2
MAX_REPORT_ERRORS = 8
KILL_WAIT_S = 15.0          # how long a cancelled compile may take to die
_CACHE_MAX = 128

StatusFn = Optional[Callable[[int, str], None]]


class CompileOutcome(NamedTuple):
    ok: bool                    # a PDF, zero TeX errors, no missing file
    pdf_path: Optional[Path]
    errors: List[str]           # "file:line: message" (+ "missing file: x", "sandbox: why")
    log: str
    pages: int


@dataclass
class Measure:
    """One compiled attempt measured against the source page."""
    value: float                # 0..1 match value (see _value)
    visual: float               # verify.compare_pages score
    ssim: float
    pixel_diff: float
    coverage: float
    missing: List[str]
    extra: List[str]
    extra_ratio: float
    displacement: Optional[float]
    overflow: bool
    overflow_lines: int
    pages: int
    shift_pt: float
    regions: List[Region] = field(default_factory=list)
    figures: List[str] = field(default_factory=list)    # figure size/position mismatch messages
    blocks: List[str] = field(default_factory=list)     # blocks out of place
    breaks: List[str] = field(default_factory=list)     # source line ends the output does not share

    @property
    def rank(self) -> float:
        """Best-of ordering, as pipeline.Score.rank: a missing or invented word outweighs any visual gain."""
        moved = (self.displacement or 0.0) / 100.0
        return self.value - 2.0 * (1.0 - self.coverage) - 1.0 * self.extra_ratio - moved


@dataclass
class _Attempt:
    body: str
    outcome: Optional[CompileOutcome]
    preamble_error: str = ""
    exhausted: bool = False     # still failing after the deterministic heal and every LLM repair
    measure: Optional[Measure] = None

    @property
    def ok(self) -> bool:
        return bool(self.outcome and self.outcome.ok)


# ---------------------------------------------------------------------------
# Compile
# ---------------------------------------------------------------------------

def _link_assets(ctx: RebuildCtx, wd: Path) -> None:
    """
    `wd/assets` → `ctx.out_dir/assets` as a RELATIVE link (`../../output/assets`): the build and
    output directories are siblings inside the job directory, so the same link resolves in this
    process and in the runner sidecar, which mounts the job volume at another absolute path.
    """
    target = ctx.out_dir / ASSET_ROOT
    target.mkdir(parents=True, exist_ok=True)
    rel = os.path.relpath(target, wd)
    link = wd / ASSET_ROOT
    if link.is_symlink():
        if os.readlink(link) == rel:
            return
        link.unlink()
    elif link.exists():
        shutil.rmtree(link) if link.is_dir() else link.unlink()
    link.symlink_to(rel, target_is_directory=True)


def _kill_procs_in(wd: Path) -> int:
    """SIGKILLs the process group of every process whose cwd is inside `wd` (Linux /proc)."""
    target = os.path.realpath(wd)
    own = os.getpgrp()
    killed = 0
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return 0
    for pid in pids:
        try:
            cwd = os.readlink(f"/proc/{pid}/cwd")
        except OSError:
            continue
        if cwd != target and not cwd.startswith(target + os.sep):
            continue
        try:
            pgid = os.getpgid(int(pid))
            if pgid != own:
                os.killpg(pgid, signal.SIGKILL)
            else:
                os.kill(int(pid), signal.SIGKILL)
            killed += 1
        except (ProcessLookupError, PermissionError, OSError):
            continue
    return killed


async def _run_sandbox(wd: Path, timeout_s: Optional[int] = None):
    """
    `sandbox.compile_dir`, cancellation-safe: a local compile runs in a worker thread that task
    cancellation cannot stop, so on cancel the TeX processes in `wd` are killed and the thread is
    waited for (bounded) before the cancellation propagates — no orphaned engine keeps burning CPU.
    In runner mode the HTTP request is dropped; the sidecar's own timeout bounds its compile.
    """
    task = asyncio.ensure_future(sandbox.compile_dir(wd) if timeout_s is None
                                 else sandbox.compile_dir(wd, timeout_s=timeout_s))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        if get_rebuild_settings().sandbox_mode == "runner":
            task.cancel()
            raise
        deadline = time.monotonic() + KILL_WAIT_S
        while not task.done() and time.monotonic() < deadline:
            _kill_procs_in(wd)
            await asyncio.sleep(0.1)
        _kill_procs_in(wd)
        if not task.done():
            task.cancel()
        raise


_MISSING_RES = (
    re.compile(r"LaTeX Error: File `([^']+)' not found"),
    re.compile(r"Unable to load picture or PDF file '([^']+)'"),
    re.compile(r"! I can't find file `([^']+)'"),
    re.compile(r"File `([^']+\.(?:png|jpe?g|pdf|eps))' not found", re.IGNORECASE),
)


def _missing_files(log: str) -> List[str]:
    found: List[str] = []
    for rx in _MISSING_RES:
        found += [m.group(1) for m in rx.finditer(log or "")]
    return list(dict.fromkeys(found))


async def compile_body(ctx: RebuildCtx, n: int, body: str, attempt_tag: str) -> CompileOutcome:
    """Compiles source page `n`'s body on its own in `ctx.work_dir/p{n}_{attempt_tag}`."""
    wd = ctx.work_dir / f"p{n}_{attempt_tag}"
    wd.mkdir(parents=True, exist_ok=True)
    (wd / "main.tex").write_text(standalone_page(ctx.preamble, body, n), encoding="utf-8")
    _link_assets(ctx, wd)
    res = await _run_sandbox(wd)
    errors = list(res.errors)
    for name in _missing_files(res.log):
        if not any(name in e for e in errors):
            errors.append(f"missing file: {name}")
    if res.timed_out:
        errors.append(f"sandbox: {res.detail or 'compile timed out'}")
    elif res.detail and not errors:
        errors.append(f"sandbox: {res.detail}")
    pdf = res.pdf_path if res.pdf_path is not None and res.pdf_path.is_file() else None
    return CompileOutcome(ok=bool(res.ok and pdf is not None and not errors), pdf_path=pdf, errors=errors,
                          log=res.log, pages=res.pages)


# ---------------------------------------------------------------------------
# Errors → body lines
# ---------------------------------------------------------------------------

_ERR_RE = re.compile(r"^(?P<file>[^\s:]+\.[A-Za-z]+):(?P<line>\d+|None): (?P<msg>.+)$")


def _body_start(preamble: str) -> int:
    """1-based line of main.tex where the body starts (see document.standalone_page)."""
    return len(preamble.rstrip().splitlines()) + 3


def _located(ctx: RebuildCtx, errors: Sequence[str]) -> List[Tuple[Optional[int], str, bool]]:
    """(body line or None, message, in_preamble) per error, in log order."""
    start = _body_start(ctx.preamble)
    out: List[Tuple[Optional[int], str, bool]] = []
    for e in errors:
        m = _ERR_RE.match(e.strip())
        if not m or m.group("line") == "None":
            out.append((None, e.strip().lstrip("! ").strip(), False))
            continue
        fname = m.group("file")
        fname = fname[2:] if fname.startswith("./") else fname
        line = int(m.group("line"))
        if fname != "main.tex":
            out.append((None, f"{fname}:{line}: {m.group('msg')}", False))
        elif line < start:
            out.append((None, m.group("msg"), True))
        else:
            out.append((line - start + 1, m.group("msg"), False))
    return out


def _preamble_error(ctx: RebuildCtx, outcome: CompileOutcome) -> str:
    """The first error, when TeX hit it before reaching the body (only the preamble stage can fix it)."""
    located = _located(ctx, outcome.errors)
    if located and located[0][2]:
        return located[0][1]
    return ""


def _error_report(ctx: RebuildCtx, body: str, outcome: CompileOutcome) -> str:
    lines = body.splitlines()
    parts: List[str] = []
    for bl, msg, _pre in _located(ctx, outcome.errors)[:MAX_REPORT_ERRORS]:
        if bl is None:
            parts.append(f"- {msg}")
            continue
        bl = min(max(1, bl), max(1, len(lines)))
        ctx_lines = []
        for i in range(max(1, bl - 2), min(len(lines), bl + 2) + 1):
            mark = ">>" if i == bl else "  "
            ctx_lines.append(f"  {mark} {i:4d} | {lines[i - 1]}")
        parts.append(f"- body line {bl}: {msg}\n" + "\n".join(ctx_lines))
    if not parts:
        tail = [ln for ln in (outcome.log or "").splitlines() if ln.startswith("!") or re.match(r"^l\.\d+", ln)]
        parts.append("\n".join(tail[-12:]) or (outcome.log or "")[-1500:] or "no PDF was produced")
    return "\n".join(parts)


def _packages(preamble: str) -> str:
    names: List[str] = []
    for m in re.finditer(r"\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", preamble):
        names += [p.strip() for p in m.group(1).split(",") if p.strip()]
    return ", ".join(dict.fromkeys(names)) or "(none)"


def _body_of(tex: str, n: int) -> Optional[str]:
    """Page n's body back out of a (healed) standalone document; the heal may move our \\clearpage."""
    marker = f"\\obpagestart{{{n}}}\n"
    i = tex.find(marker)
    j = tex.rfind("\\end{document}")
    if i < 0 or j < i:
        return None
    lines = tex[i + len(marker):j].splitlines()
    for k in range(len(lines) - 1, -1, -1):
        if lines[k].strip() == "\\clearpage":
            del lines[k]
            break
    return "\n".join(lines).strip()


def _heal(ctx: RebuildCtx, n: int, body: str, log: str) -> Optional[str]:
    from latex_error_fixer import auto_heal_latex_code
    healed, fixes = auto_heal_latex_code(standalone_page(ctx.preamble, body, n), log)
    if not fixes:
        return None
    fixed = _body_of(healed, n)
    return fixed if fixed and fixed != body.strip() else None


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```[a-zA-Z]*\s*\n(.*?)```", re.DOTALL)
_PREAMBLE_LINE_RE = re.compile(r"^\s*\\(documentclass|usepackage|RequirePackage)\b.*$\n?", re.MULTILINE)
_EDGE_RE = re.compile(r"^(?:\s*\\obpagestart\{\d+\}\s*)|(?:\s*\\(?:clearpage|newpage)\s*)+$")
_INCLUDE_RE = re.compile(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")


def _allowed_files(ctx: RebuildCtx, draft: str) -> Set[str]:
    allowed = set(ctx.manifest.filenames())
    allowed |= {m.group(1).strip() for m in _INCLUDE_RE.finditer(draft)}
    return allowed


def _file_ok(name: str, allowed: Set[str]) -> bool:
    name = name.strip()
    name = name[2:] if name.startswith("./") else name
    if name in allowed:
        return True
    return any(os.path.splitext(a)[0] == name for a in allowed)


def _minimal_guard(text: str, allowed: Set[str]) -> Tuple[str, List[str]]:
    """Fences, document/preamble commands and \\includegraphics of unknown files out; returns (body, notes)."""
    notes: List[str] = []
    b = (text or "").strip()
    fenced = _FENCE_RE.search(b)
    if fenced:
        b = fenced.group(1)
    if "\\begin{document}" in b:
        b = b.split("\\begin{document}", 1)[1]
    if "\\end{document}" in b:
        b = b.split("\\end{document}", 1)[0]
    b = _PREAMBLE_LINE_RE.sub("", b).strip()
    b = _EDGE_RE.sub("", b).strip()

    def _drop(m: "re.Match[str]") -> str:
        if _file_ok(m.group(1), allowed):
            return m.group(0)
        notes.append(f"dropped \\includegraphics of a file not in the asset manifest: {m.group(1).strip()}")
        return ""

    b = _INCLUDE_RE.sub(_drop, b)
    return b.strip(), notes


def _call_generate_guard(ctx: RebuildCtx, n: int, body: str, allowed: Set[str]) -> Tuple[str, List[str]]:
    """`generate.guard_body`, its arguments bound by parameter name (that module is written separately)."""
    values = {"body": body, "text": body, "raw": body, "latex": body, "tex": body,
              "ctx": ctx, "rctx": ctx, "n": n, "page": n, "number": n, "page_no": n, "page_number": n,
              "manifest": ctx.manifest, "allowed": allowed, "files": allowed, "filenames": allowed,
              "allowed_files": allowed, "preamble": ctx.preamble}
    args: List[Any] = []
    kwargs: Dict[str, Any] = {}
    for name, p in inspect.signature(_generate_guard).parameters.items():
        if name not in values:
            if p.default is inspect.Parameter.empty and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
                raise TypeError(f"guard_body parameter {name!r} is not known to refine")
            continue
        if p.kind is p.POSITIONAL_ONLY:
            args.append(values[name])
        else:
            kwargs[name] = values[name]
    res = _generate_guard(*args, **kwargs)
    notes: List[str] = []
    if isinstance(res, str):
        return res, notes
    if isinstance(res, (tuple, list)) and res and isinstance(res[0], str):
        for extra in res[1:]:
            if isinstance(extra, (list, tuple)):
                notes += [str(x) for x in extra]
        return res[0], notes
    body_attr = getattr(res, "body", None)
    if isinstance(body_attr, str):
        notes += [str(x) for x in (getattr(res, "warnings", None) or [])]
        return body_attr, notes
    raise TypeError(f"guard_body returned {type(res).__name__}")


def _guard(ctx: RebuildCtx, n: int, text: str, allowed: Set[str], pr: PageResult) -> str:
    body = text or ""
    if _generate_guard is not None:
        try:
            body, notes = _call_generate_guard(ctx, n, body, allowed)
            pr.warnings.extend(notes)
        except Exception as e:  # noqa: BLE001 - the minimal guard below still runs
            logger.warning(f"generate.guard_body unusable here ({e}); minimal guard only")
    body, notes = _minimal_guard(body, allowed)
    pr.warnings.extend(notes)
    return body


# ---------------------------------------------------------------------------
# LLM calls
# ---------------------------------------------------------------------------

async def _ask(ctx: RebuildCtx, n: int, system: str, user: str, images: Sequence[bytes], label: str):
    s = get_settings()
    return await complete_ex(system, user, list(images), timeout=s.page_timeout, retries=s.page_retries,
                             concurrency=s.concurrency, label=f"{ctx.job_id[:8]}:p{n}-{label}")


async def _compile_repair(ctx: RebuildCtx, n: int, body: str, tag: str, pr: PageResult,
                          allowed: Set[str], allow_llm: bool = True) -> _Attempt:
    """Compile; on failure the deterministic heal once, then up to max_compile_repairs LLM fixes."""
    max_repairs = get_settings().max_compile_repairs
    healed = False
    repairs = 0
    cur, suffix = body, ""
    while True:
        out = await compile_body(ctx, n, cur, tag + suffix)
        if out.ok:
            return _Attempt(cur, out)
        pre = _preamble_error(ctx, out)
        if pre:
            return _Attempt(cur, out, preamble_error=pre)
        if out.pdf_path is None and out.errors and all(e.startswith("sandbox:") for e in out.errors) \
                and "timed out" not in out.errors[0]:
            # the sandbox itself failed (runner unreachable, path rejected): no edit of the body can help
            pr.warnings.append(out.errors[0])
            return _Attempt(cur, out)
        if not healed:
            healed = True
            fixed = await asyncio.to_thread(_heal, ctx, n, cur, out.log)
            if fixed:
                cur, suffix = fixed, "h"
                continue
        if not allow_llm or repairs >= max_repairs:
            return _Attempt(cur, out, exhausted=True)
        repairs += 1
        pr.repairs += 1
        user = fill(COMPILE_FIX_USER, ERRORS=_error_report(ctx, cur, out), PACKAGES=_packages(ctx.preamble),
                    BODY=cur)
        try:
            reply = await _ask(ctx, n, COMPILE_FIX_SYSTEM, user, (), f"{tag}-fix{repairs}")
        except LLMCallFailed as e:
            pr.warnings.append(f"compile repair call failed: {e}")
            return _Attempt(cur, out)
        fixed = _guard(ctx, n, reply.text, allowed, pr)
        if not fixed or fixed == cur:
            return _Attempt(cur, out, exhausted=True)
        cur, suffix = fixed, f"f{repairs}"


# ---------------------------------------------------------------------------
# Measure
# ---------------------------------------------------------------------------

@dataclass
class _Source:
    width: float
    height: float
    words: List[WordBox]
    tokens: List[str]                   # every word of the page
    ref_tokens: List[str]               # the reference text for coverage
    line_ends: List[str]                # last word of every non-final line of a multi-line block


_cache: "OrderedDict[tuple, Any]" = OrderedDict()
_cache_lock = threading.Lock()


def _cached(key: tuple, make: Callable[[], Any]) -> Any:
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    value = make()
    with _cache_lock:
        _cache[key] = value
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
    return value


def _src_key(ctx: RebuildCtx, *rest: Any) -> tuple:
    try:
        mtime = ctx.source_pdf.stat().st_mtime_ns
    except OSError:
        mtime = 0
    return (ctx.job_id, str(ctx.source_pdf), mtime, *rest)


def _layout(ctx: RebuildCtx, n: int) -> Optional[PageLayout]:
    return next((lay for lay in ctx.layouts if lay.number == n), None)


def _layout_text(layout: Optional[PageLayout]) -> str:
    if layout is None:
        return ""
    parts = [str(b.get("text") or "") for b in layout.blocks]
    for t in layout.tables:
        for row in t.get("rows") or []:
            parts.append(" ".join(str(c) for c in row))
    return "\n".join(p for p in parts if p.strip())


def _line_ends(page) -> List[str]:
    ends: List[str] = []
    for blk in page.get_text("dict").get("blocks", []):
        lines = [ln for ln in blk.get("lines", [])
                 if "".join(sp.get("text", "") for sp in ln.get("spans", [])).strip()]
        for ln in lines[:-1]:
            toks = tokenize("".join(sp.get("text", "") for sp in ln.get("spans", [])))
            if len(toks) >= 2 and len(toks[-1]) >= 2:
                ends.append(toks[-1])
    return ends


def _source(ctx: RebuildCtx, n: int) -> _Source:
    def make() -> _Source:
        import pymupdf
        data = ctx.source_pdf.read_bytes()
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            page = doc[n - 1]
            text = page.get_text("text") or ""
            ends = _line_ends(page)
            w, h = page.rect.width, page.rect.height
        layout_text = _layout_text(_layout(ctx, n))
        tokens = tokenize(text)
        return _Source(width=w, height=h, words=words_with_boxes(data, n - 1), tokens=tokens,
                       ref_tokens=tokenize(layout_text) if layout_text else tokens, line_ends=ends)
    return _cached(_src_key(ctx, "words", n, len(ctx.layouts)), make)


def _source_raster(ctx: RebuildCtx, n: int, dpi: int) -> np.ndarray:
    return _cached(_src_key(ctx, "raster", n, dpi),
                   lambda: render_pdf_pages(ctx.source_pdf, dpi, first=n, last=n)[0])


def _value(visual: float, coverage: float, extra_ratio: float, moved: Optional[float], has_words: bool,
           overflow: bool, max_disp: float) -> float:
    """
    One 0..1 match number. Text coverage and word placement carry 70% of it; the visual score only
    30%, because full-page SSIM scores a blank page ~0.73 (see pipeline.Ctx.acceptable).
    """
    if moved is None:
        place = 0.5 if has_words else 1.0
    else:
        place = max(0.0, 1.0 - max(0.0, moved - SETTLE_PT) / (4.0 * max_disp))
    v = W_VISUAL * visual + W_COVERAGE * coverage + W_PLACE * place
    v -= min(0.3, max(0.0, extra_ratio - EXTRA_TOLERANCE))
    if overflow:
        v *= OVERFLOW_PENALTY
    return float(min(1.0, max(0.0, v)))


def _overflow_lines(pages: List[np.ndarray], dpi: int, layout: Optional[PageLayout]) -> int:
    """Lines of ink on the pages after the first, inside the source's top/bottom margins."""
    px_per_pt = dpi / 72.0
    line_pt = DEFAULT_LINE_PT
    if layout is not None:
        sizes = [float((b.get("font") or {}).get("size") or 0) for b in layout.blocks if b.get("role") == "body"]
        sizes = [s for s in sizes if s > 0]
        if sizes:
            line_pt = float(np.median(sizes)) * 1.2
    total = 0
    for arr in pages:
        h = arr.shape[0]
        top = bottom = 0.06 * h / px_per_pt
        if layout is not None and layout.margins:
            top = float(layout.margins.get("top", top)) * 0.8
            bottom = float(layout.margins.get("bottom", bottom)) * 0.8
        y0, y1 = int(top * px_per_pt), int(h - bottom * px_per_pt)
        rows = (arr[y0:max(y0, y1)] < INK_LEVEL).any(axis=1)
        band = 0
        for ink in list(rows) + [False]:
            if ink:
                band += 1
            elif band:
                total += max(1, int(round(band / px_per_pt / line_pt)))
                band = 0
    return total


# --- figure placement --------------------------------------------------------

_WS = b" \t\r\n\x0c\x00"
_DELIM = b"()<>[]{}/%"


def _content_ops(data: bytes):
    """(operator, operands) of a content stream; strings, arrays and dicts become opaque operands."""
    i, n = 0, len(data)
    operands: List[Any] = []
    while i < n:
        c = data[i]
        if c in _WS:
            i += 1
        elif c == 0x25:  # %
            while i < n and data[i] not in b"\r\n":
                i += 1
        elif c == 0x28:  # (
            depth, i = 1, i + 1
            while i < n and depth:
                if data[i] == 0x5C:
                    i += 2
                    continue
                depth += {0x28: 1, 0x29: -1}.get(data[i], 0)
                i += 1
            operands.append(None)
        elif c == 0x3C:  # <
            if data[i + 1:i + 2] == b"<":
                depth, i = 1, i + 2
                while i < n and depth:
                    if data[i:i + 2] == b"<<":
                        depth, i = depth + 1, i + 2
                    elif data[i:i + 2] == b">>":
                        depth, i = depth - 1, i + 2
                    else:
                        i += 1
            else:
                end = data.find(b">", i)
                i = n if end < 0 else end + 1
            operands.append(None)
        elif c in b">[]{})":
            i += 1
        elif c == 0x2F:  # /
            j = i + 1
            while j < n and data[j] not in _WS and data[j] not in _DELIM:
                j += 1
            operands.append(("name", data[i + 1:j].decode("latin-1")))
            i = j
        else:
            j = i
            while j < n and data[j] not in _WS and data[j] not in _DELIM:
                j += 1
            tok = data[i:j]
            i = max(j, i + 1)
            try:
                operands.append(float(tok))
                continue
            except ValueError:
                pass
            op = tok.decode("latin-1")
            yield op, operands
            operands = []
            if op == "BI":  # inline image: skip its binary data
                m = re.compile(rb"\sEI(?=[\s]|$)").search(data, i)
                i = n if m is None else m.end()


def _placements(doc, page) -> List[Tuple[str, str, Tuple[float, float, float, float], Tuple[float, float]]]:
    """(xobject name, kind, rect in page space, intrinsic size) of every image/form the page draws itself."""
    import pymupdf
    known: Dict[str, Tuple[str, int, Tuple[float, float], Any]] = {}
    for img in page.get_images(full=True):
        if img[9] == 0:
            known[img[7]] = ("image", img[0], (float(img[2]), float(img[3])), None)
    for xref, name, invoker, bbox in page.get_xobjects():
        if invoker == 0:
            b = pymupdf.Rect(bbox)
            known[name] = ("form", xref, (round(b.width, 2), round(b.height, 2)), b)
    if not known:
        return []
    out = []
    ctm = pymupdf.Matrix(1, 0, 0, 1, 0, 0)
    stack: List[Any] = []
    to_page = page.transformation_matrix
    for op, ops in _content_ops(page.read_contents() or b""):
        if op == "q":
            stack.append(ctm)
        elif op == "Q":
            ctm = stack.pop() if stack else ctm
        elif op == "cm":
            nums = [v for v in ops if isinstance(v, float)][-6:]
            if len(nums) == 6:
                ctm = pymupdf.Matrix(*nums) * ctm
        elif op == "Do":
            names = [v[1] for v in ops if isinstance(v, tuple)]
            if not names or names[-1] not in known:
                continue
            kind, xref, size, bbox = known[names[-1]]
            if kind == "image":
                r = pymupdf.Rect(0, 0, 1, 1) * ctm
            else:
                mat = pymupdf.Matrix(1, 0, 0, 1, 0, 0)
                typ, val = doc.xref_get_key(xref, "Matrix")
                if typ == "array":
                    try:
                        mat = pymupdf.Matrix(*[float(x) for x in val.strip("[] ").split()])
                    except (TypeError, ValueError):
                        pass
                r = bbox * mat * ctm
            r = (r * to_page)
            r.normalize()
            out.append((names[-1], kind, (r.x0, r.y0, r.x1, r.y1), size))
    return out


def _intrinsic(path: Path) -> Optional[Tuple[str, Tuple[float, float]]]:
    """('image', pixel size) for a raster, ('form', page size in pt) for a PDF asset."""
    try:
        if path.suffix.lower() == ".pdf":
            import pymupdf
            with pymupdf.open(str(path)) as d:
                r = d[0].rect
                return "form", (round(r.width, 2), round(r.height, 2))
        from PIL import Image
        with Image.open(path) as im:
            return "image", (float(im.width), float(im.height))
    except Exception:  # noqa: BLE001 - an unreadable asset is simply not checked
        return None


def _same_size(kind: str, a: Tuple[float, float], b: Tuple[float, float]) -> bool:
    tol = 0.6 if kind == "form" else 0.5
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def _figure_messages(ctx: RebuildCtx, n: int, body: str, pdf_path: Path) -> List[str]:
    """Placed size/position of each of the page's figures versus where it sits on the source page."""
    import pymupdf
    referenced = [m.group(1).strip() for m in _INCLUDE_RE.finditer(body)]
    refset = {r[2:] if r.startswith("./") else r for r in referenced}
    msgs: List[str] = []
    assets = [a for a in ctx.manifest.for_page(n) if a.kind in ("image", "vector") or a.filename in refset
              or os.path.splitext(a.filename)[0] in refset]
    if not assets:
        return msgs
    with pymupdf.open(str(pdf_path)) as doc:
        placed = [(pno + 1, p) for pno in range(doc.page_count) for p in _placements(doc, doc[pno])]
    used: Set[int] = set()
    for a in assets:
        label = f"figure {os.path.basename(a.filename)}"
        src_at = f"x={a.bbox[0]:.0f}..{a.bbox[2]:.0f}pt, y={a.bbox[1]:.0f}..{a.bbox[3]:.0f}pt"
        if a.filename not in refset and os.path.splitext(a.filename)[0] not in refset:
            if not a.meta.get("decorative"):
                msgs.append(f"{label} is not included; in the source it is {a.width_pt:.0f}x{a.height_pt:.0f}pt "
                            f"at {src_at} (\\includegraphics{{{a.filename}}})")
            continue
        ident = _intrinsic(ctx.out_dir / a.filename)
        hit = None
        if ident is not None:
            for k, (pg, (_name, kind, rect, size)) in enumerate(placed):
                if k not in used and kind == ident[0] and _same_size(kind, size, ident[1]):
                    hit = k
                    break
        if hit is None:
            msgs.append(f"{label} is referenced but not drawn on the page")
            continue
        used.add(hit)
        pg, (_name, _kind, (x0, y0, x1, y1), _size) = placed[hit]
        if pg > 1:
            msgs.append(f"{label} landed on page {pg} (overflow); in the source it is at {src_at}")
            continue
        pw, ph = x1 - x0, y1 - y0
        aw, ah = max(1e-3, a.width_pt), max(1e-3, a.height_pt)
        wr, hr = pw / aw, ph / ah
        parts = []
        if abs(wr - 1.0) >= FIGURE_SIZE_TOL:
            parts.append(f"{abs(wr - 1.0):.0%} too {'wide' if wr > 1 else 'narrow'}")
        if abs(hr - 1.0) >= FIGURE_SIZE_TOL and (abs(hr - wr) >= FIGURE_SIZE_TOL or not parts):
            parts.append(f"{abs(hr - 1.0):.0%} too {'tall' if hr > 1 else 'short'}")
        if parts:
            msgs.append(f"{label} is {' and '.join(parts)} ({pw:.0f}x{ph:.0f}pt; source {aw:.0f}x{ah:.0f}pt: "
                        f"use width={aw:.0f}bp)")
        dx, dy = x0 - a.bbox[0], y0 - a.bbox[1]
        moves = []
        if abs(dy) >= FIGURE_POS_TOL_PT:
            moves.append(f"{abs(dy):.0f}pt {'lower' if dy > 0 else 'higher'}")
        if abs(dx) >= FIGURE_POS_TOL_PT:
            moves.append(f"{abs(dx):.0f}pt {'right' if dx > 0 else 'left'}")
        if moves:
            msgs.append(f"{label} sits {' and '.join(moves)} than in the source (top-left at x={x0:.0f}, "
                        f"y={y0:.0f}pt; source x={a.bbox[0]:.0f}, y={a.bbox[1]:.0f}pt)")
    return msgs


# --- blocks and line breaks -------------------------------------------------

def _match(source: List[WordBox], rendered: List[WordBox]) -> List[Tuple[WordBox, WordBox]]:
    """Greedy in-order word matching, as verify.displacement."""
    pool: Dict[str, List[WordBox]] = {}
    for wb in rendered:
        pool.setdefault(wb.text, []).append(wb)
    pairs = []
    for wb in source:
        bucket = pool.get(wb.text)
        if not bucket:
            continue
        best = min(bucket, key=lambda r: abs(r.y - wb.y) * 2 + abs(r.x - wb.x))
        bucket.remove(best)
        pairs.append((wb, best))
    return pairs


def _block_messages(layout: Optional[PageLayout], pairs: List[Tuple[WordBox, WordBox]]) -> List[str]:
    if layout is None or not pairs:
        return []
    found = []
    for b in layout.blocks:
        bb = b.get("bbox") or []
        if len(bb) != 4:
            continue
        x0, y0, x1, y1 = (float(v) for v in bb)
        moved = [(r.x - s.x, r.y - s.y) for s, r in pairs if x0 - 2 <= s.x <= x1 + 2 and y0 - 2 <= s.y <= y1 + 2]
        if len(moved) < 2:
            continue
        dx = float(np.median([m[0] for m in moved]))
        dy = float(np.median([m[1] for m in moved]))
        if abs(dy) < BLOCK_DRIFT_PT and abs(dx) < 2 * BLOCK_DRIFT_PT:
            continue
        where = []
        if abs(dy) >= BLOCK_DRIFT_PT:
            where.append(f"{abs(dy):.0f}pt {'low' if dy > 0 else 'high'}")
        if abs(dx) >= 2 * BLOCK_DRIFT_PT:
            where.append(f"{abs(dx):.0f}pt too far {'right' if dx > 0 else 'left'}")
        text = " ".join(str(b.get("text") or "").split())
        snippet = text[:40] + ("..." if len(text) > 40 else "")
        found.append((max(abs(dy), abs(dx) / 2), f"block {b.get('id', '?')} ({b.get('role', 'text')} "
                      f"\"{snippet}\", source y={y0:.0f}pt) sits {' and '.join(where)}"))
    found.sort(key=lambda t: -t[0])
    return [m for _, m in found[:6]]


def _break_messages(source_ends: List[str], pdf_path: Path) -> List[str]:
    if not source_ends:
        return []
    import pymupdf
    out_ends: List[str] = []
    with pymupdf.open(str(pdf_path)) as doc:
        for page in doc:
            for blk in page.get_text("dict").get("blocks", []):
                for ln in blk.get("lines", []):
                    toks = tokenize("".join(sp.get("text", "") for sp in ln.get("spans", [])))
                    if toks:
                        out_ends.append(toks[-1])
    pool: Dict[str, int] = {}
    for t in out_ends:
        pool[t] = pool.get(t, 0) + 1
    differ = []
    for t in source_ends:
        if pool.get(t, 0) > 0:
            pool[t] -= 1
        else:
            differ.append(t)
    return differ


def _measure_sync(ctx: RebuildCtx, n: int, body: str, pdf_path: Path) -> Optional[Measure]:
    cfg = get_settings()
    dpi = cfg.render_dpi
    rendered = render_pdf_pages(pdf_path, dpi)
    if not rendered:
        return None
    src = _source(ctx, n)
    original = _source_raster(ctx, n, dpi)
    cmp = compare_pages(original, rendered[0], dpi)
    data = pdf_path.read_bytes()
    by_page = extract_words_from_pdf(data)
    out_tokens = [w for i in sorted(by_page) for w in by_page[i]]
    cov = compare_words(src.ref_tokens, out_tokens)
    extra = compare_words(src.tokens, out_tokens)
    out_words = words_with_boxes(data, 0)
    moved = displacement(src.words, out_words)
    overflow = len(rendered) > 1
    layout = _layout(ctx, n)
    value = _value(cmp.score, cov.coverage, extra.extra_ratio, moved, bool(src.words), overflow,
                   cfg.max_displacement)
    return Measure(
        value=value, visual=cmp.score, ssim=cmp.ssim, pixel_diff=cmp.pixel_diff, coverage=cov.coverage,
        missing=[w for w, _ in cov.missing], extra=[w for w, _ in extra.extra], extra_ratio=extra.extra_ratio,
        displacement=moved, overflow=overflow,
        overflow_lines=_overflow_lines(rendered[1:], dpi, layout) if overflow else 0,
        pages=len(rendered), shift_pt=cmp.shift_pt, regions=cmp.regions,
        figures=_figure_messages(ctx, n, body, pdf_path),
        blocks=_block_messages(layout, _match(src.words, out_words)),
        breaks=_break_messages(src.line_ends, pdf_path),
    )


async def measure(ctx: RebuildCtx, n: int, body: str, pdf_path: Path) -> Optional[Measure]:
    """Scores a compiled page against source page `n` (CPU-bound work in a worker thread)."""
    return await asyncio.to_thread(_measure_sync, ctx, n, body, pdf_path)


def mismatch_report(m: Measure) -> str:
    """The measured differences as plain text for the correction call (pt from the page's top-left)."""
    parts: List[str] = []
    if m.overflow:
        parts.append(f"- OVERFLOW: the body runs onto {m.pages - 1} extra page(s); the page overflows by about "
                     f"{m.overflow_lines} line(s). It must fit on ONE page: tighten vertical spacing, reduce "
                     f"oversized figures or headings to their source size, remove manual blank space.")
    if m.missing:
        parts.append(f"- Missing words ({m.coverage:.1%} of the source text present); add back verbatim: "
                     + ", ".join(m.missing[:30]))
    if m.extra and m.extra_ratio > 0:
        parts.append("- Words in the output that are NOT on the source page; remove them: " + ", ".join(m.extra[:20]))
    if abs(m.shift_pt) >= 3.0:
        parts.append(f"- Vertical drift: the whole page sits about {abs(m.shift_pt):.0f}pt "
                     f"{'lower' if m.shift_pt > 0 else 'higher'} than the original.")
    if m.displacement is not None and m.displacement > SETTLE_PT * 2:
        parts.append(f"- The typical word is {m.displacement:.0f}pt away from where it sits in the original.")
    if m.blocks:
        parts.append("- Blocks out of place:\n" + "\n".join(f"  - {b}" for b in m.blocks))
    if m.figures:
        parts.append("- Figures:\n" + "\n".join(f"  - {f}" for f in m.figures))
    if m.breaks:
        parts.append(f"- Line breaks differ: in the source, lines end after these words but in the output they "
                     f"do not: {', '.join(m.breaks[:10])}. Match the source line width/size so lines break alike.")
    parts.append("- Regions that look different (pt from the page top-left):\n" + describe_regions(m.regions))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

def _fallback_png(ctx: RebuildCtx, n: int) -> str:
    rel = f"{ASSET_ROOT}/pdf_{ctx.job_id[:8]}/p{n}_page.png"
    dest = ctx.out_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    png = ctx.page_pngs.get(n)
    if png is not None and Path(png).is_file():
        shutil.copyfile(png, dest)
    else:
        import pymupdf
        with pymupdf.open(str(ctx.source_pdf)) as doc:
            doc[n - 1].get_pixmap(dpi=get_rebuild_settings().raster_dpi, alpha=False).save(str(dest))
    return rel


def fallback_body(rel: str) -> str:
    """The page render as a full-page background (kernel shipout hook: no extra package needed)."""
    return ("\\thispagestyle{empty}%\n"
            "\\AddToHookNext{shipout/background}{\\put(0pt,-\\paperheight){\\includegraphics"
            f"[width=\\paperwidth,height=\\paperheight]{{{rel}}}}}}}%\n"
            "\\null")


def page_image_body(ctx: RebuildCtx, n: int) -> str:
    """The body of page `n` as an image of the source page (renders the file; run off the event loop)."""
    return fallback_body(_fallback_png(ctx, n))


async def _image_fallback(ctx: RebuildCtx, n: int, pr: PageResult, allowed: Set[str]) -> Optional[_Attempt]:
    try:
        rel = await asyncio.to_thread(_fallback_png, ctx, n)
    except Exception as e:  # noqa: BLE001
        pr.warnings.append(f"page image fallback could not be rendered: {e}")
        return None
    allowed.add(rel)
    att = await _compile_repair(ctx, n, fallback_body(rel), "fb", pr, allowed, allow_llm=False)
    if not att.ok:
        pr.warnings.append("even the page image fallback did not compile: "
                           + "; ".join((att.outcome.errors if att.outcome else [])[:3]))
        return None
    try:
        att.measure = await measure(ctx, n, att.body, att.outcome.pdf_path)
    except Exception as e:  # noqa: BLE001 - the fallback stands without a score
        logger.warning(f"p{n}: measuring the image fallback failed: {e}")
    return att


async def image_fallback_page(ctx: RebuildCtx, n: int, reason: str, *,
                              warnings: Sequence[str] = ()) -> PageResult:
    """The result for a page the model could not produce at all: its image, or status "failed"."""
    pr = PageResult(number=n, warnings=[*warnings, reason])
    fb = await _image_fallback(ctx, n, pr, set())
    if fb is None:
        pr.status = "failed"
        return pr
    _apply(pr, fb)
    pr.fallback = "image"
    pr.low_confidence = _reasons(ctx, n, pr, False)
    pr.status = "fallback"
    return pr


def source_tokens(ctx: RebuildCtx, n: int) -> List[str]:
    """The words of source page `n` that coverage is measured against."""
    return _source(ctx, n).ref_tokens


# ---------------------------------------------------------------------------
# The page loop
# ---------------------------------------------------------------------------

def _passes(m: Measure) -> bool:
    return (m.value >= get_rebuild_settings().page_pass_score and m.coverage >= get_settings().coverage_target
            and not m.overflow)


async def _png_of(pdf_path: Path, dpi: int) -> bytes:
    def run() -> bytes:
        import pymupdf
        with pymupdf.open(str(pdf_path)) as doc:
            return doc[0].get_pixmap(dpi=dpi, alpha=False).tobytes("png")
    return await asyncio.to_thread(run)


async def _source_png(ctx: RebuildCtx, n: int, dpi: int) -> bytes:
    p = ctx.page_pngs.get(n)
    if p is not None and Path(p).is_file():
        return await asyncio.to_thread(Path(p).read_bytes)

    def run() -> bytes:
        import pymupdf
        with pymupdf.open(str(ctx.source_pdf)) as doc:
            return doc[n - 1].get_pixmap(dpi=dpi, alpha=False).tobytes("png")
    return await asyncio.to_thread(run)


def _reasons(ctx: RebuildCtx, n: int, pr: PageResult, exhausted: bool) -> List[str]:
    s, cfg = get_rebuild_settings(), get_settings()
    info = next((p for p in ctx.inspection.pages if p.number == n), None)
    layout = _layout(ctx, n)
    reasons: List[str] = []
    if info is not None and (info.ocr or info.scanned):
        reasons.append("ocr")
    if ctx.manifest.tables_for_page(n) or (layout is not None and layout.tables):
        reasons.append("table")
    has_math = (any(a.kind == "math" for a in ctx.manifest.for_page(n))
                or (layout is not None and any(b.get("role") == "math" for b in layout.blocks)))
    if has_math and not (ctx.vision or pr.vision_used):
        reasons.append("math")
    if pr.score is not None and pr.score < s.low_confidence_score:
        reasons.append("score")
    if pr.coverage is not None and pr.coverage < cfg.coverage_target:
        reasons.append("coverage")
    if pr.overflow:
        reasons.append("overflow")
    if pr.fallback == "image":
        reasons.append("image fallback")
    if exhausted:
        reasons.append("repairs exhausted")
    return reasons


def _apply(pr: PageResult, att: _Attempt) -> None:
    pr.body = att.body
    pr.pdf_path = att.outcome.pdf_path if att.outcome else None
    m = att.measure
    if m is not None:
        pr.score, pr.ssim, pr.coverage = m.value, m.ssim, m.coverage
        pr.displacement_pt, pr.overflow = m.displacement, m.overflow


async def refine_page(ctx: RebuildCtx, n: int, body: str, *,
                      on_status: Optional[Callable[[int, str], None]] = None) -> PageResult:
    """Compiles, repairs, measures and corrects source page `n`'s draft body; returns the best result."""
    pr = PageResult(number=n)

    def status(st: str) -> None:
        pr.status = st
        if on_status is not None:
            try:
                on_status(n, st)
            except Exception:  # noqa: BLE001 - a progress callback never breaks the page
                logger.exception("on_status callback failed")

    s = get_rebuild_settings()
    body = (body or "").strip()
    allowed = _allowed_files(ctx, body)
    exhausted = False
    best: Optional[_Attempt] = None
    try:
        status("compiling")
        first = await _compile_repair(ctx, n, body, "r0", pr, allowed)
        if first.preamble_error:
            pr.body = first.body
            pr.warnings.append(f"preamble error: {first.preamble_error}")
            status("failed")
            return pr
        if first.ok:
            status("verifying")
            first.measure = await measure(ctx, n, first.body, first.outcome.pdf_path)
            best = first if first.measure is not None else None
            if best is None:
                pr.warnings.append("the compiled page could not be rendered for measuring")
        else:
            exhausted = first.exhausted
            pr.warnings.append("the page did not compile: " + "; ".join((first.outcome.errors if first.outcome
                                                                         else [])[:3]))

        while best is not None and pr.rounds < s.refine_rounds and not _passes(best.measure):
            pr.rounds += 1
            k = pr.rounds
            images: List[bytes] = []
            if ctx.vision:
                images = [await _source_png(ctx, n, s.raster_dpi), await _png_of(best.outcome.pdf_path, s.raster_dpi)]
            lay = _layout(ctx, n)
            user = fill(CORRECT_USER, PAGE=str(n), WIDTH=f"{lay.width_pt:.0f}" if lay else "?",
                        HEIGHT=f"{lay.height_pt:.0f}" if lay else "?", REPORT=mismatch_report(best.measure),
                        PACKAGES=_packages(ctx.preamble), IMAGES_NOTE=IMAGES_NOTE if images else "", BODY=best.body)
            system = fill(CORRECT_SYSTEM, FILES=", ".join(sorted(ctx.manifest.filenames(n))) or "(none)")
            try:
                reply = await _ask(ctx, n, system, user, images, f"correct{k}")
            except LLMCallFailed as e:
                pr.warnings.append(f"round {k}: correction call failed: {e}")
                break
            if reply.images_sent and not reply.images_dropped:
                pr.vision_used = True
            cand_body = _guard(ctx, n, reply.text, allowed, pr)
            if not cand_body or cand_body == best.body:
                pr.warnings.append(f"round {k}: the correction changed nothing")
                break
            status("compiling")
            cand = await _compile_repair(ctx, n, cand_body, f"r{k}", pr, allowed)
            status("verifying")
            if not cand.ok:
                pr.warnings.append(f"round {k}: the corrected body did not compile; kept the previous version")
                break
            cand.measure = await measure(ctx, n, cand.body, cand.outcome.pdf_path)
            if cand.measure is None:
                break
            gain = cand.measure.rank - best.measure.rank
            if gain > 0:
                best = cand
            else:
                pr.warnings.append(f"round {k}: the correction scored lower ({cand.measure.value:.3f} vs "
                                   f"{best.measure.value:.3f}); kept the previous version")
            if gain < s.min_gain:
                break

        cfg = get_settings()
        if best is None or (best.measure.value < cfg.visual_floor and best.measure.coverage < cfg.coverage_target):
            fb = await _image_fallback(ctx, n, pr, allowed)
            if fb is not None:
                _apply(pr, fb)
                pr.fallback = "image"
                pr.warnings.append("the page is embedded as an image of the source page")
                pr.low_confidence = _reasons(ctx, n, pr, exhausted)
                status("fallback")
                return pr
            if best is None:
                pr.body = first.body
                pr.low_confidence = _reasons(ctx, n, pr, exhausted)
                status("failed")
                return pr
        _apply(pr, best)
        pr.low_confidence = _reasons(ctx, n, pr, exhausted)
        status("done")
        return pr
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 - one page's fault never reaches the orchestrator
        logger.exception(f"p{n}: refine failed")
        pr.warnings.append(f"refine error: {e!r}")
        if best is not None:
            _apply(pr, best)
            pr.low_confidence = _reasons(ctx, n, pr, exhausted)
            status("done")
            return pr
        try:
            fb = await _image_fallback(ctx, n, pr, allowed)
        except asyncio.CancelledError:
            raise
        except Exception as e2:  # noqa: BLE001
            pr.warnings.append(f"image fallback error: {e2!r}")
            fb = None
        if fb is not None:
            _apply(pr, fb)
            pr.fallback = "image"
            pr.low_confidence = _reasons(ctx, n, pr, exhausted)
            status("fallback")
        else:
            pr.body = body
            status("failed")
        return pr
