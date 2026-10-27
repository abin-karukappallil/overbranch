"""
run.py — Editable-mode conversion job orchestration.

Page-locked: extract → analyse (furniture, columns, profile, blocks, one hard mark per source
page) → compose LaTeX → pagefit.finish (compile with a per-block degradation repair loop →
heading calibration → the measured page-fit loop) → measure gates → optional text-only LLM polish
(refused if it moves a page, a page start or a picture) → write into the project.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..extract import extract_document
from ..models import ConversionReport, DocExtract, PageReport
from ..storage import FileConflictError, write_output_to_project
from . import blocks as B
from . import columns as C
from . import furniture as F
from . import pages as PG
from . import profile as PRof
from .emit import Emitter
from .model import LINEBREAK, Block, EditDoc, Heading, LineMap, Para, TitlePage

logger = logging.getLogger("pdf2latex.editable")


@dataclass
class EditCtx:
    """Minimal context for reusing pipeline.compile_tex (it only needs out_dir and b64)."""
    out_dir: Path
    b64: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Deterministic assembly (sync, testable on its own)
# ---------------------------------------------------------------------------

def assemble(extract: DocExtract, doc, source_name: str = "") -> Tuple[str, EditDoc, LineMap]:
    """Build the editable LaTeX document from an extraction. Pure of I/O beyond reading ``doc``."""
    pages = extract.pages
    furn = F.detect(pages)
    col_left, col_right = C.body_column(pages, furn.furniture_line_ids)
    page_layout: Dict[int, List] = {}
    page_rows: Dict[int, List] = {}
    note_stacks: Dict[int, List] = {}
    for p in pages:
        # side callouts come out of the flow first, so they never merge into a row they only
        # happen to share a baseline with
        boxes = [b.bbox for b in extract.metadata.get("_editable_tables", {}).get(p.number, [])] + \
                [b.bbox for b in extract.metadata.get("_editable_math", {}).get(p.number, [])]
        stacks = C.split_side_notes(p, furn.furniture_line_ids, col_left, col_right, boxes)
        exclude = set(furn.furniture_line_ids)
        rows_of_stacks = []
        for st in stacks:
            exclude.update((p.number, i) for i, _ln in st)
            nrows = C.rows_in_zone(st)
            for r in nrows:
                r.page = p.number
            rows_of_stacks.append(nrows)
        if rows_of_stacks:
            note_stacks[p.number] = rows_of_stacks
        furn_imgs = getattr(furn, "image_keys", set()) or set()
        wide = [b.bbox for b in extract.metadata.get("_editable_tables", {}).get(p.number, [])] + \
               [img.bbox for img in p.images if (p.number, img.file) not in furn_imgs]
        layout = C.page_zones_and_rows(p, exclude, col_left, col_right, wide)
        page_layout[p.number] = layout
        page_rows[p.number] = [r for _z, rows in layout for r in rows]

    profile = PRof.build_profile(pages, page_rows, col_left, col_right)
    PRof.two_column_layout(profile, page_layout)
    from .hyphen import vocabulary
    profile.words, profile.compounds = vocabulary(ln.text for p in pages for ln in p.lines)

    # pinned pages: scanned, background art, or a title page
    pinned = set()
    scanned = set()
    for p in pages:
        if p.is_scanned or p.background:
            pinned.add(p.number)
            if p.is_scanned:
                scanned.add(p.number)
    # A slide deck (every page landscape) keeps one output page per slide: each page is pinned so
    # every boundary is a hard break, while the content of each slide is still ordinary LaTeX.
    deck = len(pages) >= 2 and all(p.width > p.height * 1.15 for p in pages)
    if deck:
        pinned.update(p.number for p in pages)
        # each slide is its own page already: slide titles are sections, never \\chapter (which
        # would clear the page and add a chapter's spacing inside the slide)
        if profile.has_chapters:
            for lv in profile.heading_levels:
                lv["level"] += 1
            profile.heading_levels = [lv for lv in profile.heading_levels if lv["level"] <= 3]
            profile.has_chapters = False

    table_blocks = extract.metadata.get("_editable_tables", {})
    math_blocks = extract.metadata.get("_editable_math", {})
    blocks = B.build_blocks(pages, page_layout, profile, col_left, col_right,
                            table_blocks=table_blocks, math_blocks=math_blocks,
                            note_stacks=note_stacks,
                            boxes=extract.metadata.get("_editable_boxes", {}),
                            furniture=furn,
                            trims=extract.metadata.get("_editable_trims", {}))
    # shaded boxes bring fill colours the text never used; give them names too
    box_rgbs = [c for specs in extract.metadata.get("_editable_boxes", {}).values() for spec in specs
                for c in (spec.get("fill"), spec.get("title_fill")) if c]
    known = [rgb for _n, rgb in profile.colors]
    new = [c for c in dict.fromkeys(box_rgbs) if c not in known]
    if new:
        profile.colors = PRof.name_colors(known + new)
    reading_rows = _with_note_rows(page_rows, blocks)

    # title page: wrap page 1 if it looks like one
    # title pages (a cover, an inner title page, a part divider): centred display lines set apart,
    # each on its own page, with their measured spacing
    for p in pages:
        if not deck and PG.detect_title_page(p, page_rows.get(p.number, []), col_left, col_right, profile):
            blocks = PG.wrap_title_page(blocks, p.number)
            pinned.add(p.number)

    blocks = PG.insert_page_marks(blocks, pages, page_rows, profile, pinned, furn)
    seen_pages = set()
    for b in blocks:
        if b.kind == "pagemark" or b.page in seen_pages:
            continue
        seen_pages.add(b.page)
        if isinstance(b, Heading):
            b.starts_page = True
    blocks = _fold_heading_rules(blocks, profile)
    _measure_heading_spacing(blocks, profile)
    # after the heading measurement: the gap it gives a page's first block must not be read as a
    # heading's own space above (it drove the chapter before-space to a wild negative)
    _space_at_page_top(blocks, profile)
    plan = PG.apply_numbering(blocks, pages, furn)
    furn.initial_numbering = plan["initial"]
    furn.plain_empty = plan["plain_empty"]
    if not deck:
        _lock_geometry(blocks, profile, furn, page_rows)

    for pno in extract.metadata.get("_editable_backgrounds", {}):
        pinned.add(pno)   # a decorated page keeps its own page
    if deck and extract.metadata.get("_editable_backgrounds"):
        # the slide numbers and footer are part of each slide's background picture
        furn.page_number_band = None
        furn.numbering_segments = [{"first_page": pages[0].number, "style": "none", "start": None}]
    doc_model = EditDoc(blocks=blocks, profile=profile, furniture=furn, pinned=pinned,
                        scanned=scanned, page_count=len(pages), rows_by_page=reading_rows,
                        backgrounds=extract.metadata.get("_editable_backgrounds", {}),
                        deck=deck,
                        zone_rows={pno: [((z.column, z.of_columns), rows) for z, rows in lay]
                                   for pno, lay in page_layout.items()},
                        title=(source_name or "").rsplit("/", 1)[-1])
    has_notes = any(b.kind == "note" for b in blocks)
    em = Emitter(profile, source_name=source_name, furniture=furn,
                 backgrounds=extract.metadata.get("_editable_backgrounds", {}), deck=deck)
    tex, lm = em.document(blocks, has_notes)
    return tex, doc_model, lm


def _lock_geometry(blocks: List[Block], profile, furn, page_rows: Dict[int, List]) -> None:
    """
    Page-locked geometry. A block the PDF sets at the foot of its page (its last baseline on the
    text area's foot, a wide gap above it) is anchored there (``anchor_bottom``). Then the text area
    is let down as far as the lowest content of any page (by one more line), never into the footer:
    a source page whose text sets a little taller than the PDF's then still fits its page, which
    \\raggedbottom leaves unstretched.
    """
    from .blocks import _last_baseline
    ph = profile.paper_pt[1] if profile.paper_pt else 842.0
    m = profile.margins
    src_bottom = ph - m["bottom"]
    profile.text_bottom_src = src_bottom
    lead = profile.leading or 1.2 * profile.body_size
    by_page: Dict[int, List[Block]] = {}
    for b in blocks:
        if b.kind in ("note", "pagemark"):
            continue
        by_page.setdefault(b.page, []).append(b)
    lowest = src_bottom
    for pno, bl in by_page.items():
        for b in bl:
            if not isinstance(b, TitlePage):
                lowest = max(lowest, b.bbox[3])
        flow = [b for b in bl if not isinstance(b, TitlePage)]
        if len(flow) < 2 or len(flow) != len(bl):
            continue
        last, prev = flow[-1], flow[-2]
        lb = _last_baseline(last)
        lb = lb if lb is not None else last.bbox[3]
        if abs(src_bottom - lb) <= 0.6 * lead and last.bbox[1] - prev.bbox[3] >= 2 * lead \
                and not getattr(last, "joins_prev", False):
            last.anchor_bottom = round(lb, 2)
    for rows in page_rows.values():
        for r in rows:
            lowest = max(lowest, r.bottom)
    if furn is not None and furn.footer_top:
        cap = furn.footer_top - 2
        if furn.footer_baseline:
            cap = min(cap, furn.footer_baseline - 12.0)
    else:
        cap = ph - 18.0
    new_bottom = max(src_bottom, min(cap, lowest + lead))
    m["bottom"] = round(ph - new_bottom, 2)


def _with_note_rows(page_rows: Dict[int, List], blocks: List[Block]) -> Dict[int, List]:
    """The measured reading order: each note's rows go where the note is emitted (just before its
    anchor), so the order gate reads the document the way the output PDF does."""
    out = {k: list(v) for k, v in page_rows.items()}
    for b in blocks:
        if b.kind != "note":
            continue
        rows = [ln for c in b.content for ln in getattr(c, "lines", [])]
        main = out.setdefault(b.page, [])
        idx = next((i for i, r in enumerate(main) if r.top >= b.anchor_top - 0.5), len(main))
        out[b.page] = main[:idx] + rows + main[idx:]
    return out


def structure_summary(doc: EditDoc) -> Dict:
    """Counts for the report / CLI --json."""
    from collections import Counter
    kinds = Counter(b.kind for b in doc.blocks)
    headings = [b for b in doc.blocks if isinstance(b, Heading)]
    lists = [b for b in doc.blocks if b.kind == "list"]
    return {
        "blocks": len(doc.blocks),
        "kinds": dict(kinds),
        "headings": len(headings),
        "heading_levels": sorted({h.level for h in headings}),
        "lists": len(lists),
        "list_items": sum(len(getattr(b, "items", [])) for b in lists),
        "tables": kinds.get("table", 0),
        "figures": kinds.get("figure", 0),
        "math": kinds.get("math", 0),
        "notes": kinds.get("note", 0),
        "hard_breaks": sum(1 for b in doc.blocks if b.kind == "pagemark" and getattr(b, "hard", False)),
        "pages_source": doc.page_count,
        "profile": {
            "body_size": doc.profile.body_size, "body_cls": doc.profile.body_cls,
            "has_chapters": doc.profile.has_chapters,
            "colors": [n for n, _ in doc.profile.colors],
            "margins": {k: round(v, 1) for k, v in doc.profile.margins.items()},
        },
    }


# ---------------------------------------------------------------------------
# Async job entry point (called from pipeline.run_conversion)
# ---------------------------------------------------------------------------

async def run_editable(job_id: str, pdf_bytes: bytes, project_id: str, overwrite: bool = False,
                       target_path: str = "main.tex", resume: bool = False,
                       saved_state: Optional[Dict] = None) -> None:
    from .. import jobs
    from ..config import get_settings
    from ..llm import llm_available, model_name
    from ..pipeline import _page_count, _tex_available, compile_tex, _emit_trace
    from . import gates as G
    from . import polish as POL

    settings = get_settings()
    jd = jobs.job_dir(job_id)
    out_dir = jd / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    (jd / "editable").mkdir(parents=True, exist_ok=True)
    started = time.time()
    doc = None
    report = ConversionReport(page_count=0, model=model_name(), mode="editable",
                              coverage_target=settings.coverage_target)
    try:
        _set = lambda **kw: jobs.update_job(job_id, status="running", **kw)  # noqa: E731
        _set(stage="extracting", message="Extracting text, colours, images and vectors…", progress=0.02)
        source_name = (saved_state or {}).get("filename", "") or ""
        extract, doc = await asyncio.to_thread(extract_document, pdf_bytes, out_dir,
                                               f"assets/pdf_{job_id[:8]}", settings.max_pages)
        report.page_count = len(extract.pages)
        report.pages = [PageReport(number=p.number, warnings=list(p.warnings)) for p in extract.pages]
        (jd / "source.pdf").write_bytes(doc.tobytes())

        _set(stage="analysing", message="Rebuilding the document structure…", progress=0.12)
        tex, doc_model, lm = await asyncio.to_thread(_assemble_enriched, extract, doc, out_dir, source_name)
        report.warnings.extend(doc_model.warnings)
        (jd / "editable" / "deterministic.tex").write_text(tex, encoding="utf-8")

        has_tex = _tex_available()
        report.llm_used = llm_available() and settings.editable_polish
        if not has_tex:
            report.warnings.append("No pdfLaTeX on the server: the LaTeX is generated but not compiled or verified.")

        ctx = EditCtx(out_dir=out_dir)
        pdf = None
        fit_info: Dict = {}
        if has_tex:
            # compile (repairing) → calibrate the measured spacing → fit every source page to its
            # page: the same passes the CLI runs (pagefit.finish)
            from . import pagefit as PF
            _set(stage="compiling", message="Compiling and fitting the pages…", progress=0.35)
            tex, lm, pdf, fit_info = await PF.finish(ctx, extract, doc_model, tex, lm, compile_tex)

        _set(stage="verifying", message="Checking coverage, style and structure…", progress=0.50)
        gate_result = {}
        if pdf is not None:
            (jd / "output.pdf").write_bytes(pdf)
            report.compiled = True
            report.compiled_page_count = await asyncio.to_thread(_page_count, pdf)
            gate_result = await asyncio.to_thread(G.run_gates, extract, doc_model, tex, pdf, settings,
                                                  out_dir)
            gate_result["compiled_page_count"] = report.compiled_page_count
            gate_result["compiles"] = fit_info.get("compiles")
            gate_result["fit"] = fit_info.get("fit")

        # No LLM decides where anything goes: placement is the page lock's and the measured fit's
        # (settings.editable_vision is accepted and ignored).

        # Polish pass (text-only LLM per flagged block), gated
        if pdf is not None and report.llm_used:
            _set(stage="polishing", message="Polishing tables, maths and lists…", progress=0.6)
            tex, pdf, gate_result = await POL.polish_document(ctx, extract, doc_model, tex, pdf, lm,
                                                              gate_result, settings, job_id)
            if pdf is not None:
                (jd / "output.pdf").write_bytes(pdf)

        report.editable = _build_editable_report(doc_model, gate_result)
        report.compiled = pdf is not None
        _apply_page_reports(report, doc_model, gate_result)

        (out_dir / "main.tex").write_text(tex, encoding="utf-8")
        jobs.update_job(job_id, stage="writing", message="Writing files into the project…", progress=0.96,
                        report=report.to_dict())
        try:
            written = await asyncio.to_thread(write_output_to_project, project_id, out_dir, "main.tex",
                                              target_path, overwrite)
            status = "done"
            msg = "Conversion complete." if not gate_result.get("failed") else \
                "Conversion complete (some quality checks did not pass; see the report)."
            updated_pages = [
                {"number": pr.number, "status": "done", "similarity": None,
                 "text_coverage": pr.text_coverage, "attempts": 1, "fallback": None}
                for pr in report.pages
            ]
            jobs.update_job(job_id, status=status, stage="done", progress=1.0, message=msg,
                            result=written, report=report.to_dict(), pages=updated_pages)
        except FileConflictError as fc:
            updated_pages = [
                {"number": pr.number, "status": "done", "similarity": None,
                 "text_coverage": pr.text_coverage, "attempts": 1, "fallback": None}
                for pr in report.pages
            ]
            jobs.update_job(job_id, status="needs_confirmation", stage="needs_confirmation", progress=1.0,
                            message=str(fc), conflict_path=fc.path, report=report.to_dict(), pages=updated_pages)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Editable PDF conversion job {job_id} failed: {e}", exc_info=True)
        jobs.update_job(job_id, status="error", stage="error", error=str(e),
                        message=f"Conversion failed: {e}",
                        report=report.to_dict() if report.page_count else None)
    finally:
        if doc is not None:
            doc.close()
        _emit_trace(job_id, project_id, report, time.time() - started)


def _assemble_enriched(extract: DocExtract, doc, out_dir, source_name: str):
    """assemble() plus the enrich pass (tables, math, notes) that needs the open doc."""
    from . import enrich as EN
    return EN.assemble_with_enrichment(extract, doc, out_dir, source_name, assemble)


def _build_editable_report(doc_model: EditDoc, gate_result: Dict) -> Dict:
    return {"structure": structure_summary(doc_model), "gates": gate_result.get("gates", {}),
            "style": gate_result.get("style", {}), "lint": gate_result.get("lint", {}),
            "assets": gate_result.get("assets", {}), "failed": gate_result.get("failed", []),
            "polish": gate_result.get("polish", {}),
            "vision": gate_result.get("vision", {})}


def _apply_page_reports(report: ConversionReport, doc_model: EditDoc, gate_result: Dict):
    cov = gate_result.get("page_coverage", {})
    for pr in report.pages:
        pr.text_coverage = cov.get(pr.number)
        pr.status = "done"


def _measure_heading_spacing(blocks: List[Block], profile) -> None:
    """
    The vertical space around each heading level, as titlesec's before/after separations (median
    over that level's headings). Before is measured from the previous block's last baseline (or,
    for a heading that opens a page, from the top of the text area); after, to the next block's
    first baseline. LaTeX's own baseline distance is taken off, so the numbers are what titlesec
    adds. A heading that opens a page in a chapter-style level keeps its space from the page top,
    which is how a chapter title sits low on its page.
    """
    from .blocks import _first_baseline, _last_baseline
    from .model import Heading as _H
    stats: Dict[int, Dict[str, List[float]]] = {}
    followers: List[Tuple[Heading, Block, float]] = []
    parskip = profile.parskip or 0.0          # LaTeX adds it above the title and above the text
    for i, b in enumerate(blocks):
        if not isinstance(b, _H) or not b.runs:
            continue
        size = max((r.size for r in b.runs if r.text.strip()), default=profile.body_size)
        top_base = b.baselines[0] if b.baselines else b.bbox[1] + 0.8 * size     # first title baseline
        bot_base = b.baselines[-1] if b.baselines else b.bbox[3] - 0.22 * size   # last title baseline
        st = stats.setdefault(b.level, {"before": [], "after": []})
        prev = next((x for x in reversed(blocks[:i]) if x.kind not in ("note",)), None)
        if b.starts_page or prev is None or prev.kind == "pagemark" or prev.page != b.page:
            st["before"].append(max(0.0, b.bbox[1] - profile.margins["top"]))
        else:
            lb = _last_baseline(prev)
            base = lb if lb is not None else prev.bbox[3]
            v = top_base - base - 1.2 * size - parskip
            st["before"].append(max(0.0, v))
            if lb is None and prev.kind in ("rule", "figure", "table", "math"):
                # under a rule or a picture the level's usual space (measured under text) doesn't
                # hold; the emitter corrects this heading by the difference
                b.before_measured = v
        nxt = next((x for x in blocks[i + 1:] if x.kind not in ("note",)), None)
        if nxt is not None and nxt.kind != "pagemark" and nxt.page == b.page:
            fb = _first_baseline(nxt)
            lv_rule = next((lv.get("rule") for lv in profile.heading_levels
                            if lv["level"] == b.level and lv.get("rule")), None)
            lead = profile.leading or 1.2 * profile.body_size
            v = None
            if fb is not None and lv_rule:
                # under a rule there is no baselineskip: the text's first line just follows
                rule_bottom = bot_base + lv_rule["gap"] + lv_rule["thickness"] / 2
                v = fb - rule_bottom - 0.7 * profile.body_size - parskip
            elif fb is not None:
                v = fb - bot_base - lead - parskip
            elif nxt.kind == "rule":
                # a rule of its own under the title (not every heading of the level has one): its
                # line sits one baselineskip below the space
                v = nxt.bbox[3] - bot_base - lead - parskip
            if v is not None:
                st["after"].append(max(0.0, v))
                followers.append((b, nxt, v))
    for lv in profile.heading_levels:
        st = stats.get(lv["level"])
        if not st or not st["before"]:
            continue
        def med(xs):
            xs = sorted(xs)
            return xs[len(xs) // 2] if xs else 0.0
        lv["space_before"] = round(min(med(st["before"]), 200.0), 1)
        lv["space_before_measured"] = lv["space_before"]      # before calibration
        lv["space_after"] = round(min(med(st["after"]), 80.0), 1) if st["after"] else 6.0
    # a heading whose own space below differs from its level's (the text under a slide title
    # without the usual underline) passes the difference to the block below, in points
    after_of = {lv["level"]: lv.get("space_after") for lv in profile.heading_levels}
    for h, nxt, v in followers:
        base = after_of.get(h.level)
        if base is not None and abs(v - base) >= 4 and nxt.kind != "heading":
            nxt.space_before = round(v - base, 1)
            nxt.space_exact = True


def _space_at_page_top(blocks: List[Block], profile) -> None:
    """Give the first block of each hard-broken page the gap the PDF leaves above it.

    Spacing is otherwise measured from the previous block, which for a page's first block sits on
    the page before — so the gap is recorded as zero and the block rides up to the top margin. A
    centred "CONTENTS" title that the source sets ~52pt down the page landed hard against it.
    Headings are left alone: their place comes from their level's titlesec spacing, corrected by
    ``calibrate_heading_spacing``.
    """
    top = (profile.margins or {}).get("top")
    if not top:
        return
    lead = profile.leading or 12.0
    hard = False
    for b in blocks:
        if b.kind == "pagemark":
            hard = bool(getattr(b, "hard", False))
            continue
        if hard and not isinstance(b, (Heading, TitlePage)) and not b.space_before \
                and not getattr(b, "joins_prev", False):
            gap = b.bbox[1] - top
            if 0.4 * lead <= gap <= 400.0:
                b.space_before = round(gap, 1)
                b.space_exact = True
        hard = False


MAX_HEADING_LIFT = 36.0   # pt a page-opening heading may be pulled up toward the page top


def calibrate_heading_spacing(doc: EditDoc, pdf: bytes) -> bool:
    """
    Measured correction of the space around headings. TeX adds \\topskip, \\parskip, interline
    glue and the title's own leading to titlesec's before/after spaces, so the first compile sets
    headings a little off. Find each heading in the output and compare, with the source:
      - a heading that opens its page (a chapter title): where it sits on the page;
      - any other heading: the distance from the line above it and to the line below it.
    Each level's before/after space is corrected by the median error. Returns whether anything
    changed (the caller recompiles once).
    """
    import statistics
    from .blocks import _first_baseline, _last_baseline
    if doc.deck:
        return False          # slides are scaled to fit their page: their positions don't compare
    rows = _output_rows(pdf, doc.profile)
    opening: Dict[int, List[float]] = {}
    opening_top: Dict[int, List[float]] = {}
    opening_h: List[Tuple[Heading, float]] = []
    before: Dict[int, List[float]] = {}
    after: Dict[int, List[float]] = {}
    flow = [b for b in doc.blocks if b.kind not in ("note",)]
    stacked: List[Tuple[Heading, Heading, float, float]] = []   # (heading, heading above, out, src)
    old = {lv["level"]: (lv.get("space_before") or 0.0, lv.get("space_after") or 0.0)
           for lv in doc.profile.heading_levels}
    cursor = 0
    for i, b in enumerate(flow):
        if not isinstance(b, Heading) or not b.runs:
            continue
        key = _norm_key("".join(r.text if r.text != LINEBREAK else " " for r in b.runs))
        if len(key) < 3:
            continue
        j = next((k for k in range(cursor, len(rows)) if rows[k][2].startswith(key)), None)
        if j is None:
            continue
        cursor = j + 1
        page, base, _t, top = rows[j]
        nlines = max(1, len(b.baselines))
        last_j = j + nlines - 1
        if last_j >= len(rows) or rows[last_j][0] != page:
            continue
        src_first = b.baselines[0] if b.baselines else None
        src_last = b.baselines[-1] if b.baselines else None
        if b.starts_page:
            # baselines: the two fonts' bounding boxes differ, their baselines are the text's place
            off = (base - src_first) if src_first is not None else (top - b.bbox[1])
            opening.setdefault(b.level, []).append(off)
            opening_top.setdefault(b.level, []).append(top)
            opening_h.append((b, off))
        else:
            prev = flow[i - 1] if i > 0 else None
            src_prev = _last_baseline(prev) if prev is not None and prev.page == b.page else None
            if src_prev is not None and src_first is not None and j > 0 and rows[j - 1][0] == page:
                before.setdefault(b.level, []).append((base - rows[j - 1][1]) - (src_first - src_prev))
            elif isinstance(prev, Heading) and prev.page == b.page and prev.baselines \
                    and src_first is not None and j > 0 and rows[j - 1][0] == page:
                # right under another heading LaTeX keeps the larger of the two spaces, not their
                # sum: measured, and corrected on this heading alone below
                stacked.append((b, prev, base - rows[j - 1][1], src_first - prev.baselines[-1]))
        nxt = flow[i + 1] if i + 1 < len(flow) else None
        src_next = _first_baseline(nxt) if nxt is not None and nxt.page == b.page else None
        if src_next is not None and src_last is not None and last_j + 1 < len(rows) \
                and rows[last_j + 1][0] == page:
            after.setdefault(b.level, []).append((rows[last_j + 1][1] - rows[last_j][1]) - (src_next - src_last))
    changed = False
    for lv in doc.profile.heading_levels:
        if lv.get("space_before") is None:
            continue
        level = lv["level"]
        # a level whose headings open their pages (chapters) is placed from the page top; the
        # space above any other heading at a page top is dropped by TeX, as in the source
        n_open, n_mid = len(opening.get(level, [])), len(before.get(level, []))
        offs = opening.get(level) if n_open > n_mid else before.get(level)
        if offs:
            delta = statistics.median(offs)
            floor = 0.0
            if n_open > n_mid:
                # A page-opening heading usually has to come UP: \chapter* carries its own space
                # above the title that titlesec's before-space has to cancel, so the correction has
                # to be allowed to go negative (titlesec accepts a negative before-space). Clamped at
                # zero, every chapter page started ~34pt below the source's.
                floor = -80.0
                # …but only by a moderate amount. A large lift means the PDF sets its chapter titles
                # up in the page's top margin; following them there puts the title outside the text
                # block, in the running header's band, where it neither reads nor counts as covered.
                tops = opening_top.get(level) or []
                margin_top = (doc.profile.margins or {}).get("top") or 0.0
                room = max(0.0, statistics.median(tops) - margin_top) if tops else 0.0
                if delta > 0:
                    delta = min(delta, MAX_HEADING_LIFT, room) if tops else min(delta, MAX_HEADING_LIFT)
            if abs(delta) > 1.0:
                lv["space_before"] = round(max(floor, lv["space_before"] - delta), 1)
                changed = True
        offs = after.get(level)
        if offs and lv.get("space_after") is not None:
            delta = statistics.median(offs)
            if abs(delta) > 1.0:
                lv["space_after"] = round(max(0.0, lv["space_after"] - delta), 1)
                changed = True
    # A block that opens a page carries a \vspace* set from the source geometry, but a space at a
    # page top does not start from zero — TeX lands the first box by \topskip, which shifts once a
    # rigid space is there — so the first compile overshoots. Correct each by its measured error;
    # from a non-zero space the response is linear, so one correction lands it.
    # Only a row that opens an output page can be such a block: matching anywhere would hit the
    # same words in the contents list ("LIST OF FIGURES … viii") instead of the page itself.
    page_first: Dict[int, int] = {}
    for k, row in enumerate(rows):
        page_first.setdefault(row[0], k)
    openers = sorted(page_first.values())
    hard, cursor2 = False, 0
    for b in doc.blocks:
        if b.kind == "pagemark":
            hard = bool(getattr(b, "hard", False))
            continue
        opens, hard = hard, False
        if not opens or not isinstance(b, Para) or not b.space_exact or not b.lines:
            continue
        key = _norm_key("".join(r.text if r.text != LINEBREAK else " " for r in b.lines[0].runs))
        if len(key) < 3:
            continue
        j = next((k for k in openers if k >= cursor2 and rows[k][2].startswith(key)), None)
        if j is None:
            continue
        cursor2 = j + 1
        delta = rows[j][3] - b.bbox[1]
        if abs(delta) > 2.0:
            b.space_before = round(max(0.0, b.space_before - delta), 1)
            changed = True

    # A heading right under another: LaTeX adds only the upper one's after-space (a heading's
    # before-space is skipped right after a heading, \\if@nobreak). Where that, with the levels as
    # now corrected, still misses the PDF by 4pt or more, this heading gets a \\kern.
    new = {lv["level"]: (lv.get("space_before") or 0.0, lv.get("space_after") or 0.0)
           for lv in doc.profile.heading_levels}
    for h, up, out_dist, src_dist in stacked:
        if h.level not in old or up.level not in old:
            continue
        rest_dist = out_dist - old[up.level][1] - h.kern
        predicted = rest_dist + new[up.level][1]
        if abs(predicted - src_dist) >= 4.0:
            h.kern = round(src_dist - predicted, 1)
            h.stacked = True
            changed = True
    return changed


def _norm_key(text: str) -> str:
    import re as _re
    return _re.sub(r"[^0-9a-z]", "", text.lower())[:16]


def _output_rows(pdf: bytes, profile) -> List[Tuple[int, float, str, float]]:
    from .measure import output_rows
    return output_rows(pdf, profile)


def _fold_heading_rules(blocks: List[Block], profile) -> List[Block]:
    """
    A heading level whose headings are (nearly) all underlined by a full-width rule just below the
    title (a CV's or a report's section titles) carries that rule in its style — titlesec's
    \\titlerule after the title — instead of a separate rule after each heading, so a heading the
    user adds gets its rule too. Records the rule (thickness, colour, distance below the title's
    baseline) on the level and drops the rule blocks.
    """
    from .model import Rule
    found: Dict[int, List[Tuple[Heading, Optional[Rule]]]] = {}
    for i, b in enumerate(blocks):
        if not isinstance(b, Heading) or not b.runs:
            continue
        size = max((r.size for r in b.runs if r.text.strip()), default=profile.body_size)
        nxt = blocks[i + 1] if i + 1 < len(blocks) else None
        base = b.baselines[-1] if b.baselines else b.bbox[3]
        ok = (isinstance(nxt, Rule) and nxt.page == b.page and nxt.width_frac >= 0.9
              and 0 < (nxt.bbox[1] + nxt.bbox[3]) / 2 - base <= 1.5 * size)
        found.setdefault(b.level, []).append((b, nxt if ok else None))
    drop = set()
    for lv in profile.heading_levels:
        pairs = found.get(lv["level"], [])
        ruled = [(h, r) for h, r in pairs if r is not None]
        if len(pairs) < 2 or len(ruled) < 0.8 * len(pairs):
            continue
        gaps = sorted((r.bbox[1] + r.bbox[3]) / 2 - (h.baselines[-1] if h.baselines else h.bbox[3])
                      for h, r in ruled)
        thick = sorted(r.thickness for _h, r in ruled)
        colors: Dict = {}
        for _h, r in ruled:
            colors[r.color] = colors.get(r.color, 0) + 1
        lv["rule"] = {"gap": round(gaps[len(gaps) // 2], 1), "thickness": thick[len(thick) // 2],
                      "color": max(colors, key=colors.get)}
        for _h, r in ruled:
            drop.add(id(r))
    return [b for b in blocks if id(b) not in drop] if drop else blocks

