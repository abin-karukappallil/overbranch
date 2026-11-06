"""
package.py — Stage 9 of the AI rebuild ("packaging"): one document out of the best page bodies.

`compile_merged` merges the preamble and the bodies and compiles the whole document in the sandbox. A
page that compiled alone can still break the merged document (a macro it left defined, an unclosed
group); the page an error points at is replaced by an image of the source page and the build runs
again, for as long as that finds a new page to replace. It then reads `page_map` (source page → output
pages) from `main.aux`: `\\obpagestart` writes `ob-out-n` holding the physical page, because the
`ob-src-n` label's page field is `\\thepage`, which the same macro has just set to the source page.
It measures each source page's words on the output pages it became: this is the coverage of the
deliverable, where a page's own compile only says what that page did alone.

`write_package` writes `output/` (main.tex, assets/, output.pdf, report.md), `<job>/output.pdf` for the
preview route, and `<job>/package.zip`. The zip stays outside `output/` because everything in there
is copied into the user's project.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set

from ..verify import compare_words, extract_words_from_pdf
from . import refine
from .document import ASSET_ROOT, merged_document
from .model import PageResult, RebuildCtx
from .settings import get_rebuild_settings

logger = logging.getLogger("pdf2latex.rebuild.package")

MERGED_BASE_S = 60          # wall clock of the merged compile: this, plus MERGED_PER_PAGE_S per page
MERGED_PER_PAGE_S = 6
ERROR_TEXT_CHARS = 600
MAIN_TEX = "main.tex"
OUTPUT_PDF = "output.pdf"
REPORT_MD = "report.md"

_ERR_LINE = re.compile(r"^(?:\./)?main\.tex:(\d+):")
_PAGE_MARK = re.compile(r"^\\obpagestart\{(\d+)\}\s*$")
_LABEL = re.compile(r"^\\newlabel\{ob-(src|out)-(\d+)\}\{\{[^{}]*\}\{(\d+)\}")
_FILE_REF = re.compile(r"\\(?:includegraphics|obbackground)\*?\s*(?:\[[^\]]*\])?\s*\{([^{}]+)\}")


@dataclass
class MergedBuild:
    compiled: bool
    tex: str
    pdf_path: Optional[Path] = None
    output_pages: int = 0
    page_map: Dict[str, List[int]] = field(default_factory=dict)  # "3" -> [3] (source page -> output pages)
    coverage: Dict[int, float] = field(default_factory=dict)      # measured on the merged PDF
    replaced: List[int] = field(default_factory=list)             # pages swapped for their image here
    errors: List[str] = field(default_factory=list)
    log: str = ""


# ---------------------------------------------------------------------------
# Reading the build back
# ---------------------------------------------------------------------------

def read_page_map(aux: Path, pages: Sequence[int], total: int) -> Dict[str, List[int]]:
    """
    Source page → the output pages it occupies, from the labels in `aux`. A page runs from its own
    start to the page before the next source page starts. Without `ob-out-n` (a preamble that did not
    come through the guard) the `ob-src-n` page field is the best there is, and it hides drift.
    """
    found: Dict[str, Dict[int, int]] = {"src": {}, "out": {}}
    try:
        lines = aux.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    for line in lines:
        m = _LABEL.match(line)
        if m:
            found[m.group(1)][int(m.group(2))] = int(m.group(3))
    starts = {n: found["out"].get(n, found["src"].get(n)) for n in pages}
    ordered = sorted(pages)
    out: Dict[str, List[int]] = {}
    for i, n in enumerate(ordered):
        start = starts.get(n)
        if start is None:
            out[str(n)] = []
            continue
        later = [starts[m] for m in ordered[i + 1:] if starts.get(m) is not None]
        end = later[0] - 1 if later else total
        out[str(n)] = list(range(start, max(start, end) + 1))
    return out


def _pages_of_errors(tex: str, errors: Iterable[str]) -> Set[int]:
    """The source pages whose lines of the merged `tex` the errors point at."""
    marks = [(i, int(m.group(1))) for i, line in enumerate(tex.split("\n"), 1)
             for m in [_PAGE_MARK.match(line)] if m]
    pages: Set[int] = set()
    for e in errors:
        hit = _ERR_LINE.match(e.strip())
        if not hit:
            continue
        line = int(hit.group(1))
        at = [n for start, n in marks if start <= line]
        if at:
            pages.add(at[-1])
    return pages


def _measure_output(ctx: RebuildCtx, pdf: Path, page_map: Dict[str, List[int]]) -> Dict[int, float]:
    by_page = extract_words_from_pdf(pdf.read_bytes())     # 0-based page index -> words
    coverage: Dict[int, float] = {}
    for key, outs in page_map.items():
        n = int(key)
        words = [w for o in outs for w in by_page.get(o - 1, [])]
        coverage[n] = compare_words(refine.source_tokens(ctx, n), words).coverage
    return coverage


def _page_count(pdf: Path) -> int:
    import pymupdf
    with pymupdf.open(str(pdf)) as doc:
        return doc.page_count


def _use_page_image(ctx: RebuildCtx, pr: PageResult, why: str) -> None:
    pr.body = refine.page_image_body(ctx, pr.number)
    pr.fallback = "image"
    pr.status = "fallback"
    pr.warnings.append(why)
    if "image fallback" not in pr.low_confidence:
        pr.low_confidence.append("image fallback")


# ---------------------------------------------------------------------------
# The merged build
# ---------------------------------------------------------------------------

async def compile_merged(ctx: RebuildCtx, *, on_replace: Optional[Callable[[int], None]] = None) -> MergedBuild:
    """Merges `ctx.results` and compiles them (see the module docstring). `compiled` False if it never built."""
    import asyncio

    pages = sorted(ctx.results)
    wd = ctx.work_dir / "final"
    timeout = max(get_rebuild_settings().compile_timeout_s, MERGED_BASE_S + MERGED_PER_PAGE_S * len(pages))
    build = MergedBuild(compiled=False, tex="")
    for n in pages:     # a page with no usable body starts as its image; nothing else could stand in for it
        pr = ctx.results[n]
        if not pr.body.strip() or pr.status == "failed":
            await asyncio.to_thread(_use_page_image, ctx, pr, "The page could not be rebuilt; it is an image of "
                                                              "the source page.")
            build.replaced.append(n)
            if on_replace is not None:
                on_replace(n)
    while True:
        build.tex = merged_document(ctx.preamble, [(n, ctx.results[n].body) for n in pages])
        shutil.rmtree(wd, ignore_errors=True)   # a stale .aux must not decide this build's labels
        wd.mkdir(parents=True, exist_ok=True)
        (wd / MAIN_TEX).write_text(build.tex, encoding="utf-8")
        refine._link_assets(ctx, wd)
        res = await refine._run_sandbox(wd, timeout_s=timeout)
        build.errors, build.log = list(res.errors), res.log
        if res.ok and res.pdf_path is not None and res.pdf_path.is_file():
            break
        fresh = _pages_of_errors(build.tex, res.errors) - set(build.replaced)
        if not fresh:
            if not build.errors and res.detail:
                build.errors = [res.detail]
            return build
        for n in sorted(fresh):
            msg = next((e for e in res.errors if e), "")[:200]
            await asyncio.to_thread(_use_page_image, ctx, ctx.results[n],
                                    f"The page broke the merged document ({msg}); it is an image of the source page.")
            build.replaced.append(n)
            if on_replace is not None:
                on_replace(n)
    build.compiled = True
    build.pdf_path = res.pdf_path
    build.output_pages = await asyncio.to_thread(_page_count, res.pdf_path)
    build.page_map = read_page_map(wd / "main.aux", pages, build.output_pages)
    build.coverage = await asyncio.to_thread(_measure_output, ctx, res.pdf_path, build.page_map)
    return build


def drifted_pages(page_map: Dict[str, List[int]]) -> List[int]:
    """Source pages that did not land on exactly their own output page."""
    return sorted(int(k) for k, v in page_map.items() if v != [int(k)])


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _pct(v: Any, digits: int = 1) -> str:
    return "n/a" if v is None else f"{float(v) * 100:.{digits}f}%"


def _cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def report_markdown(filename: str, summary: Dict[str, Any], rows: Sequence[Dict[str, Any]],
                    page_map: Dict[str, List[int]], warnings: Sequence[str], model: str) -> str:
    """`report.md`. `summary` is the job's `report.rebuild`; `rows` are the per-page reports."""
    ocr = summary.get("ocr") or {}
    lines = [
        f"# PDF to LaTeX report: {filename or 'document'}",
        "",
        "Closest match, not pixel-exact: the page is typeset again, so it can differ from the source in "
        "spacing and line breaks. Pages listed under \"Pages to check\" need a look.",
        "",
        f"- Engine: AI rebuild ({model})",
        f"- Document type: {summary.get('doc_type') or 'n/a'}",
        f"- Pages: {summary.get('output_pages')} output / {len(rows)} source",
        f"- Mean match: {_pct(summary.get('score_mean'))}",
        f"- Mean text coverage: {_pct(summary.get('coverage_mean'))}",
        f"- Visual review: {'on' if summary.get('vision') else 'off'} ({summary.get('vision_detail') or 'n/a'})",
        f"- OCR: {'applied on pages ' + ', '.join(map(str, ocr.get('pages') or [])) + ' (' + str(ocr.get('engine')) + ')' if ocr.get('applied') else 'not applied'}",
        f"- Correction rounds, all pages: {summary.get('rounds_used', 0)}",
        f"- Time: {summary.get('seconds', 0):.0f}s" if summary.get("seconds") is not None else "- Time: n/a",
        "",
        "## Pages",
        "",
        "| Page | Output page | Match | Text coverage | Word shift (pt) | Rounds | Kind |",
        "|---:|---:|---:|---:|---:|---:|:---|",
    ]
    for r in rows:
        n = r["number"]
        kind = "image of the source page" if r.get("fallback") else "LaTeX"
        shift = "n/a" if r.get("displacement") is None else f"{r['displacement']:.1f}"
        out = ", ".join(map(str, page_map.get(str(n)) or [])) or "n/a"
        lines.append(f"| {n} | {out} | {_pct(r.get('similarity'))} | {_pct(r.get('text_coverage'))} | {shift} | "
                     f"{max(0, int(r.get('attempts') or 1) - 1)} | {kind} |")
    low = summary.get("low_confidence") or []
    lines += ["", "## Pages to check", ""]
    if low:
        lines += [f"- Page {e['page']}: {_cell('; '.join(e['reasons']))}" for e in low]
    else:
        lines.append("None.")
    if warnings:
        lines += ["", "## Warnings", ""] + [f"- {_cell(w)}" for w in warnings]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _prune_assets(ctx: RebuildCtx, tex: str) -> None:
    """
    Drops what extraction wrote and nothing uses (images a crop replaced, renders no page needs). Files
    of the manifest stay even when unreferenced: math crops are fallback assets for the user.
    """
    keep = {m.group(1).strip().removeprefix("./") for m in _FILE_REF.finditer(tex)} | set(ctx.manifest.filenames())
    root = ctx.out_dir / ASSET_ROOT
    if not root.is_dir():
        return
    for path in sorted(p for p in root.rglob("*") if p.is_file() or p.is_symlink()):
        rel = path.relative_to(ctx.out_dir).as_posix()
        if rel not in keep and os.path.splitext(rel)[0] not in keep:
            path.unlink(missing_ok=True)
    for path in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
        if not any(path.iterdir()):
            path.rmdir()


def _zip(ctx: RebuildCtx, dest: Path) -> None:
    out = ctx.out_dir
    assets = sorted(p for p in (out / ASSET_ROOT).rglob("*") if p.is_file()) if (out / ASSET_ROOT).is_dir() else []
    fd, tmp = tempfile.mkstemp(prefix=".package-", suffix=".tmp", dir=str(dest.parent))
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for path in [out / MAIN_TEX, out / OUTPUT_PDF, out / REPORT_MD, *assets]:
                z.write(path, path.relative_to(out).as_posix())
        os.chmod(tmp, 0o644)
        os.replace(tmp, dest)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_package(ctx: RebuildCtx, build: MergedBuild, report_md: str) -> Path:
    """Writes `output/` and `<job>/output.pdf` from a compiled build; returns the path of `package.zip`."""
    if not build.compiled or build.pdf_path is None:
        raise ValueError("write_package needs a compiled build")
    out = ctx.out_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / MAIN_TEX).write_text(build.tex, encoding="utf-8")
    shutil.copyfile(build.pdf_path, out / OUTPUT_PDF)
    shutil.copyfile(build.pdf_path, ctx.job_dir / OUTPUT_PDF)
    _prune_assets(ctx, build.tex)
    (out / REPORT_MD).write_text(report_md, encoding="utf-8")
    dest = ctx.job_dir / "package.zip"
    _zip(ctx, dest)
    return dest
