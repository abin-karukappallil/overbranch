"""
Pipeline tests with a stubbed LLM (the agent's provider_router.chat) and, where needed,
a stubbed compiler: job lifecycle, agent-model reuse, short-answer retry, compile repair
loop, quality re-run, fallbacks, overwrite confirmation and verification maths.
"""

import asyncio
import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

import pdf2latex.llm as llm
import project_storage
from compile_queue import compile_queue
from pdf2latex import jobs, pipeline, storage
from pdf2latex.prompts import COMPILE_FIX_SYSTEM
from pdf2latex.config import get_settings
from pdf2latex.verify import compare_pages, compare_words, tokenize
from providers.router import DEFAULT_MODEL
from tests import pdf2latex_fixtures as fx


@pytest.fixture
def env(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(project_storage, "UPLOADS_BASE_DIR", uploads.resolve())
    monkeypatch.setattr(storage, "_supabase", lambda: None)
    monkeypatch.setenv("PDF2LATEX_JOB_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("PDF2LATEX_PAGE_RETRIES", "0")
    monkeypatch.setattr(compile_queue, "_semaphore", None)
    monkeypatch.setattr(pipeline, "llm_available", lambda: True)
    monkeypatch.setattr(pipeline, "_tex_available", lambda: False)
    return uploads


def _facts(messages):
    user = messages[-1]["content"]
    text = user if isinstance(user, str) else user[0]["text"]
    return json.loads(text.split("Page facts (JSON):\n", 1)[1].split("\n\nReturn only")[0]), text


def _echo_body(facts, marker=""):
    lines = []
    for ln in facts["lines"]:
        t = ln.get("t") or " ".join(r["t"] for r in ln["runs"])
        lines.append(f"{{\\fontsize{{{ln['sz']}}}{{{ln['sz'] * 1.2}}}\\selectfont {t}\\par}}")
    for im in facts.get("images", []):
        lines.append(f"\\includegraphics[width={im['w']}bp,height={im['h']}bp]{{{im['file']}}}\\par")
    return marker + "\n".join(lines) + "\n\\newpage"


class FakeLLM:
    def __init__(self, respond):
        self.respond = respond
        self.calls = []

    def chat(self, messages, model, temperature=0.1, max_tokens=4096, api_keys=None, cancel_token=None):
        self.calls.append({"messages": messages, "model": model})
        return {"content": self.respond(messages, len(self.calls))}


def _use_llm(monkeypatch, respond) -> FakeLLM:
    fake = FakeLLM(respond)
    monkeypatch.setattr(llm.provider_router, "chat", fake.chat)
    return fake


def _run(data, project="proj-test", pages=1, overwrite=False):
    job = jobs.create_job("user-1", project, "doc.pdf", pages)
    asyncio.run(pipeline.run_conversion(job["job_id"], data, project, overwrite))
    return jobs.load_job(job["job_id"])


def _fake_compiler(monkeypatch, ok=lambda tex: True, score=lambda tex: 0.95, overflow=lambda tex: False,
                   coverage=lambda tex: 1.0):
    """compile_tex returns the tex as 'pdf bytes' so the fake scorer can inspect what was compiled."""
    compiled = []

    async def fake_compile(ctx, tex, timeout_s):
        compiled.append(tex)
        return (tex.encode(), "") if ok(tex) else (None, "! Undefined control sequence.\nl.42 \\BROKEN")

    async def fake_score(ctx, page, pdf):
        tex = pdf.decode()
        cov = coverage(tex)
        return pipeline.Score(value=score(tex), ssim=score(tex), pixel_diff=0.01, coverage=cov,
                              missing=["absent"] if cov < 1.0 else [], overflow=overflow(tex), regions=[])

    monkeypatch.setattr(pipeline, "_tex_available", lambda: True)
    monkeypatch.setattr(pipeline, "compile_tex", fake_compile)
    monkeypatch.setattr(pipeline, "_score", fake_score)
    monkeypatch.setattr(pipeline, "_page_count", lambda pdf: pdf.decode().count("%% ==== OB-PAGE"))
    return compiled


def _page_body(tex, n):
    return pipeline.body_of(tex, n)


def test_pages_use_agent_model_image_and_facts(env, monkeypatch):
    fake = _use_llm(monkeypatch, lambda m, i: "```latex\n" + _echo_body(_facts(m)[0]) + "\n```")
    state = _run(fx.multi_page_pdf(), pages=3)
    assert state["status"] == "done", state.get("error")
    assert len(fake.calls) == 3
    for call in fake.calls:
        assert call["model"] == DEFAULT_MODEL  # same model as the agentic edit feature
        user = call["messages"][-1]["content"]
        assert user[1]["type"] == "image_url" and user[1]["image_url"]["url"].startswith("data:image/png;base64,")
        assert "Predefined colors:" in user[0]["text"]
    tex = (env / "proj-test" / "main.tex").read_text()
    body = tex.split("\\begin{document}", 1)[1]
    assert body.count("\\newpage") == 2 and "```" not in tex
    assert "\\definecolor{c0D2673}{RGB}{13,38,115}" in tex
    assert "Quarterly Report" in tex and "Revenue" in tex
    assert any(a.endswith("page2_img1.png") or "page2_img1." in a for a in state["result"]["assets"])
    report = state["report"]
    assert report["compiled"] is False and report["model"] == DEFAULT_MODEL
    assert any("No pdfLaTeX" in w for w in report["warnings"])


def test_short_answer_is_retried_once(env, monkeypatch):
    fake = _use_llm(monkeypatch, lambda m, i: "" if i == 1 else _echo_body(_facts(m)[0]))
    state = _run(fx.multi_font_pdf())
    assert state["status"] == "done", state.get("error")
    assert len(fake.calls) == 2
    assert "IMPORTANT" in _facts(fake.calls[1]["messages"])[1]
    page = state["report"]["pages"][0]
    assert page["attempts"] == 2 and page["fallback"] is None


def test_answer_missing_most_text_falls_back_to_layout(env, monkeypatch):
    fake = _use_llm(monkeypatch, lambda m, i: "\\textbf{Summary of the page}")
    state = _run(fx.multi_font_pdf())
    assert len(fake.calls) == 2
    page = state["report"]["pages"][0]
    assert page["fallback"] == "layout"
    tex = (env / "proj-test" / "main.tex").read_text()
    assert "\\begin{tikzpicture}" in tex and "Italic emphasis line" in tex  # nothing omitted


def test_without_llm_every_page_uses_layout(env, monkeypatch):
    monkeypatch.setattr(pipeline, "llm_available", lambda: False)
    fake = _use_llm(monkeypatch, lambda m, i: "unused")
    state = _run(fx.multi_page_pdf(), pages=3)
    assert state["status"] == "done", state.get("error")
    assert fake.calls == []
    assert all(p["fallback"] == "layout" for p in state["report"]["pages"])
    assert state["report"]["llm_used"] is False


def test_compile_errors_are_fixed_by_the_same_llm(env, monkeypatch):
    def respond(m, i):
        if m[0]["content"] == COMPILE_FIX_SYSTEM:
            return m[-1]["content"].split("Page body:\n", 1)[1].replace("\\BROKEN", "")
        return _echo_body(_facts(m)[0], marker="\\BROKEN ")

    fake = _use_llm(monkeypatch, respond)
    _fake_compiler(monkeypatch, ok=lambda tex: "\\BROKEN" not in tex)
    state = _run(fx.multi_font_pdf())
    assert state["status"] == "done", state.get("error")
    page = state["report"]["pages"][0]
    assert page["compile_repairs"] == 1 and page["fallback"] is None
    assert all(c["model"] == DEFAULT_MODEL for c in fake.calls)
    tex = (env / "proj-test" / "main.tex").read_text()
    assert "\\BROKEN" not in tex and "Quarterly Report" in tex
    assert state["report"]["compiled"] is True and state["report"]["compiled_page_count"] == 1


def test_compile_repairs_are_capped_then_layout_fallback(env, monkeypatch):
    monkeypatch.setenv("PDF2LATEX_MAX_COMPILE_REPAIRS", "3")

    def respond(m, i):
        if m[0]["content"] == COMPILE_FIX_SYSTEM:
            return f"\\BROKEN attempt {i} " + m[-1]["content"].split("Page body:\n", 1)[1]
        return _echo_body(_facts(m)[0], marker="\\BROKEN ")

    fake = _use_llm(monkeypatch, respond)
    _fake_compiler(monkeypatch, ok=lambda tex: "\\BROKEN" not in tex)
    state = _run(fx.multi_font_pdf())
    page = state["report"]["pages"][0]
    assert page["compile_repairs"] == 3
    assert sum(1 for c in fake.calls if c["messages"][0]["content"] == COMPILE_FIX_SYSTEM) == 3
    assert page["fallback"] == "layout"
    assert "\\BROKEN" not in (env / "proj-test" / "main.tex").read_text()


def test_a_faithful_reflow_is_accepted_without_a_rerun(env, monkeypatch):
    """
    A page that compiles to one page with all of its words is done, even though its visual
    score is far below PDF2LATEX_SIM_THRESHOLD. Re-setting the same text in flowing LaTeX
    legitimately scores ~0.65 against the original (a pixel-perfect page nudged down by one
    point already scores ~0.83), so gating on that number bought every page a re-run that
    could not help and then replaced it with the positioned layout.
    """
    fake = _use_llm(monkeypatch, lambda m, i: _echo_body(_facts(m)[0], marker="% llm\n"))
    compiled = _fake_compiler(monkeypatch, score=lambda tex: 0.66)
    state = _run(fx.multi_font_pdf())
    page = state["report"]["pages"][0]
    assert len(fake.calls) == 1, "no re-run is due for a page whose text is complete"
    assert len(compiled) == 2, "page compile + merged document only"  # no rerun/layout/obfit compiles
    assert page["status"] == "done" and page["fallback"] is None
    assert page["similarity"] == pytest.approx(0.66) and page["text_coverage"] == pytest.approx(1.0)
    assert "% llm" in (env / "proj-test" / "main.tex").read_text()


def test_rerun_is_triggered_by_missing_text_and_keeps_the_better_version(env, monkeypatch):
    """Missing words are actionable, so they — not the pixel score — buy a second attempt."""
    def respond(m, i):
        facts, text = _facts(m)
        return _echo_body(facts, marker="% v2\n" if "Previous body" in text else "% v1\n")

    fake = _use_llm(monkeypatch, respond)
    _fake_compiler(monkeypatch, score=lambda tex: 0.9,
                   coverage=lambda tex: 1.0 if "% v2" in tex else 0.7)
    state = _run(fx.multi_font_pdf())
    assert len(fake.calls) == 2
    rerun_prompt = _facts(fake.calls[1]["messages"])[1]
    assert "Missing words" in rerun_prompt and "% v1" in rerun_prompt
    page = state["report"]["pages"][0]
    assert page["text_coverage"] == pytest.approx(1.0) and page["status"] == "done"
    assert "% v2" in (env / "proj-test" / "main.tex").read_text()


def test_quality_rerun_keeps_the_better_version(env, monkeypatch):
    def respond(m, i):
        facts, text = _facts(m)
        return _echo_body(facts, marker="% v2\n" if "Previous body" in text else "% v1\n")

    fake = _use_llm(monkeypatch, respond)
    # 0.50 is under PDF2LATEX_VISUAL_FLOOR: the page has its words but looks nothing like the
    # original, which is the one visual defect still worth a second attempt.
    _fake_compiler(monkeypatch, score=lambda tex: 0.95 if "% v2" in tex else (0.5 if "% v1" in tex else 0.1))
    state = _run(fx.multi_font_pdf())
    assert len(fake.calls) == 2
    rerun_prompt = _facts(fake.calls[1]["messages"])[1]
    assert "similarity 0.50" in rerun_prompt and "% v1" in rerun_prompt
    page = state["report"]["pages"][0]
    assert page["similarity"] == pytest.approx(0.95) and page["status"] == "done"
    assert "% v2" in (env / "proj-test" / "main.tex").read_text()


def test_layout_does_not_displace_a_page_whose_text_is_complete(env, monkeypatch):
    """
    The positioned layout is absolutely-placed TikZ nodes: visually close, but not the editable
    LaTeX the import exists to produce. It scores higher than any reflow by construction, so it
    must never win on the pixel score alone — it used to take over nearly every page.
    """
    _use_llm(monkeypatch, lambda m, i: _echo_body(_facts(m)[0], marker="% llm\n"))
    _fake_compiler(monkeypatch, score=lambda tex: 0.6 if "% llm" in tex else (0.97 if "tikzpicture" in tex else 0.1))
    state = _run(fx.multi_font_pdf())
    page = state["report"]["pages"][0]
    assert page["fallback"] is None and page["similarity"] == pytest.approx(0.6)
    tex = (env / "proj-test" / "main.tex").read_text()
    assert "% llm" in tex and "\\begin{tikzpicture}" not in tex


def test_layout_rescues_a_page_whose_text_is_incomplete(env, monkeypatch):
    """When the model keeps losing text, the layout is the better answer and takes the page."""
    _use_llm(monkeypatch, lambda m, i: _echo_body(_facts(m)[0], marker="% llm\n"))
    _fake_compiler(monkeypatch,
                   score=lambda tex: 0.97 if "tikzpicture" in tex else 0.6,
                   coverage=lambda tex: 1.0 if "tikzpicture" in tex else 0.5)
    state = _run(fx.multi_font_pdf())
    page = state["report"]["pages"][0]
    assert page["fallback"] == "layout" and page["similarity"] == pytest.approx(0.97)
    assert any("more faithfully" in w for w in page["warnings"])
    assert "\\begin{tikzpicture}" in (env / "proj-test" / "main.tex").read_text()


def test_overflowing_page_is_fitted(env, monkeypatch):
    _use_llm(monkeypatch, lambda m, i: _echo_body(_facts(m)[0]))
    _fake_compiler(monkeypatch, overflow=lambda tex: "\\obfit{" not in tex.split("\\begin{document}", 1)[1])
    state = _run(fx.multi_font_pdf())
    page = state["report"]["pages"][0]
    assert page["overflow"] is False
    assert "\\obfit{" in (env / "proj-test" / "main.tex").read_text().split("\\begin{document}", 1)[1]


def test_existing_main_tex_requires_confirmation(env, monkeypatch):
    _use_llm(monkeypatch, lambda m, i: _echo_body(_facts(m)[0]))
    proj = env / "proj-busy"
    proj.mkdir()
    (proj / "main.tex").write_text("\\documentclass{article}\\begin{document}Mine\\end{document}")
    job = jobs.create_job("user-1", "proj-busy", "doc.pdf", 1)
    asyncio.run(pipeline.run_conversion(job["job_id"], fx.multi_font_pdf(), "proj-busy"))
    assert jobs.load_job(job["job_id"])["status"] == "needs_confirmation"
    assert "Mine" in (proj / "main.tex").read_text()  # untouched

    with pytest.raises(storage.FileConflictError):
        asyncio.run(pipeline.commit_pending_output(job["job_id"], overwrite=False, target_path="main.tex"))
    res = asyncio.run(pipeline.commit_pending_output(job["job_id"], overwrite=False, target_path="converted.tex"))
    assert res["tex_path"] == "converted.tex"
    assert (proj / "converted.tex").read_text().startswith("% Generated by OverBranch PDF import")
    assert jobs.load_job(job["job_id"])["status"] == "done"


def test_invalid_pdf_reports_error(env):
    state = _run(b"not a pdf at all")
    assert state["status"] == "error" and "not a PDF" in state["error"]


def test_llm_timeout_retries_then_fails(monkeypatch):
    import time as _time

    def slow(messages, model, temperature=0.1, max_tokens=4096, api_keys=None, cancel_token=None):
        while not cancel_token.is_cancelled():
            _time.sleep(0.01)
        raise RuntimeError("cancelled")

    monkeypatch.setattr(llm.provider_router, "chat", slow)
    real_sleep = asyncio.sleep
    monkeypatch.setattr(llm.asyncio, "sleep", lambda s: real_sleep(0))
    with pytest.raises(llm.LLMCallFailed, match="timed out"):
        asyncio.run(llm.complete("sys", "user", b"png", timeout=0.05, retries=1, concurrency=2, label="t"))


def test_reading_order_is_spatial_not_drawing_order():
    """
    A margin column drawn after the body must not be woven into it. PyMuPDF hands back lines in
    content-stream order, which put the notes after the whole body and produced a -222pt gap in
    front of the first one — a \\vspace that dropped the notes over the title.
    """
    from pdf2latex.extract import extract_document
    from pdf2latex.facts import page_facts
    from pdf2latex.preamble import collect_colors, page_geometry, plan_fonts

    ext, doc = extract_document(fx.margin_notes_pdf(), Path(tempfile.mkdtemp()), "assets/x", 5)
    geom = page_geometry(ext)
    facts, _ = page_facts(ext.pages[0], geom, plan_fonts(ext), 1, next(iter(collect_colors(ext))))
    doc.close()

    lines = facts["lines"]
    assert facts.get("layout_hint") == "side_blocks"
    assert all(abs(l["gap"]) < 60 for l in lines if "gap" in l), "no gap may fling a line across the page"
    # the body is one contiguous run, then the notes — not alternating between the two
    is_note = [l["x"] > 0.5 * geom.text_w for l in lines]
    assert sum(1 for a, b in zip(is_note, is_note[1:]) if a != b) <= 3, f"columns interleaved: {is_note}"
    notes = [l for l, n in zip(lines, is_note) if n]
    assert notes and notes[0].get("side") == 1 and notes[0].get("top") is not None
    assert "gap" not in notes[0], "a block break carries an absolute top, never a relative gap"


def test_displacement_sees_scrambled_text_that_ssim_and_coverage_miss():
    """The gate that catches a page carrying every word in the wrong place."""
    from pdf2latex.verify import WordBox, displacement

    src = [WordBox(f"w{i}", 100.0, 100.0 + 12 * i) for i in range(20)]
    same = [WordBox(w.text, w.x, w.y) for w in src]
    nudged = [WordBox(w.text, w.x + 3, w.y + 2) for w in src]          # a re-set page
    scrambled = [WordBox(w.text, w.x, 700.0 - w.y) for w in src]       # right words, wrong places
    assert displacement(src, same) == pytest.approx(0.0)
    assert displacement(src, nudged) < 5
    assert displacement(src, scrambled) > 100
    assert displacement(src, []) is None
    assert displacement(src, [WordBox("w1", 100.0, 112.0)]) is None    # too few matches to judge


def test_compare_pages_tolerates_a_vertical_shift_and_reports_it():
    """
    A render that carries the same ink a few points lower is the same page. Scoring it against
    the original without aligning first cost ~0.17 of similarity, which is why a pixel-perfect
    page could not clear PDF2LATEX_SIM_THRESHOLD.
    """
    a = np.full((400, 300), 255, dtype=np.uint8)
    for y in range(40, 360, 16):  # text-like rows
        a[y:y + 4, 30:270] = 0
    shifted = np.full_like(a, 255)
    shifted[6:] = a[:-6]
    cmp = compare_pages(a, shifted, dpi=72)
    assert cmp.score > 0.95, f"a 6px shift should barely matter, got {cmp.score}"
    assert cmp.shift_pt == pytest.approx(-6.0, abs=1.5)
    assert compare_pages(a, a.copy(), dpi=72).shift_pt == 0.0


def test_text_coverage_counts_every_missing_and_invented_word():
    cov = compare_words(tokenize("alpha beta gamma delta epsilon zeta"), tokenize("alpha beta omega"))
    assert cov.missing_total == 4 and cov.coverage == pytest.approx(2 / 6)
    assert cov.extra_total == 1 and cov.extra_ratio == pytest.approx(1 / 6)


def test_acceptance_is_decided_by_text_not_by_pixels(env, monkeypatch):
    """The predicate the whole page flow turns on, pinned directly."""
    monkeypatch.setenv("PDF2LATEX_JOB_DIR", str(env.parent / "j"))
    settings = get_settings()
    ctx = pipeline.Ctx(job_id="x" * 32, settings=settings, jd=env, out_dir=env, doc=None, extract=None,
                       geom=None, fonts=None, colors={}, preamble="", has_tex=True, use_llm=True,
                       report=pipeline.ConversionReport(page_count=1))

    def score(**kw):
        base = dict(value=0.66, ssim=0.6, pixel_diff=0.1, coverage=1.0, missing=[], overflow=False, regions=[])
        return pipeline.Score(**{**base, **kw})

    assert ctx.acceptable(score()), "a faithful reflow scores ~0.66 and must be accepted"
    assert not ctx.acceptable(score(coverage=0.9, missing=["lost"])), "missing text is not acceptable"
    assert not ctx.acceptable(score(overflow=True)), "a page that spills over is not acceptable"
    assert not ctx.acceptable(score(value=0.2)), "a page that looks nothing like the original is not"
    assert not ctx.acceptable(score(extra_ratio=0.5, extra=["invented"])), "padding the page is not"
    assert not ctx.acceptable(score(displacement=60.0)), "every word present but in the wrong place is not"
    assert ctx.acceptable(score(displacement=12.0)), "a re-set page moves words a little; that is fine"
    assert ctx.acceptable(score(displacement=None)), "no displacement signal must not fail a page"
    assert not ctx.acceptable(None)


def test_compare_pages_scores_and_regions():
    a = np.full((200, 160), 255, dtype=np.uint8)
    a[20:60, 20:140] = 0
    same = compare_pages(a, a.copy(), dpi=72)
    assert same.score == pytest.approx(1.0)
    assert same.regions == []
    b = a.copy()
    b[120:180, 20:140] = 0
    diff = compare_pages(a, b, dpi=72)
    assert diff.score < 0.95 and diff.pixel_diff > 0.1
    assert diff.regions[0].bbox[1] >= 100


def test_job_state_is_isolated_and_purged(env):
    st = jobs.create_job("owner-a", "p", "f.pdf", 2)
    assert jobs.active_job_for("owner-a")["job_id"] == st["job_id"]
    assert jobs.active_job_for("owner-b") is None
    jobs.update_page(st["job_id"], 2, status="done", similarity=0.98)
    loaded = jobs.load_job(st["job_id"])
    assert loaded["pages"][1]["similarity"] == 0.98
    assert "owner" not in jobs.public_view(loaded)
    assert jobs.load_job("../../etc") is None
    assert jobs.purge_old_jobs(max_age_s=-1) >= 1
    assert jobs.load_job(st["job_id"]) is None


def test_compile_is_strict_about_tex_errors_and_missing_files(tmp_path, monkeypatch):
    import base64
    from types import SimpleNamespace

    from compiler import tex_errors

    log = "This is pdfTeX\n./main.tex:12: Undefined control sequence.\nl.12 \\foo\n! Emergency stop.\nOutput written"
    assert tex_errors(log) == ["./main.tex:12: Undefined control sequence.", "! Emergency stop."]

    results = []

    async def fake_submit(fn, **kw):
        return results.pop(0)

    monkeypatch.setattr(pipeline.compile_queue, "submit", fake_submit)
    ctx = SimpleNamespace(out_dir=tmp_path, b64={})
    pdf_b64 = base64.b64encode(b"%PDF-1.5").decode()

    results.append({"success": True, "pdf_base64": pdf_b64, "log": "", "errors": tex_errors(log)})
    pdf, out = asyncio.run(pipeline.compile_tex(ctx, "body", 10))
    assert pdf is None and "Undefined control sequence" in out  # a PDF produced despite errors is a failure

    results.append({"success": True, "pdf_base64": pdf_b64, "log": "patched"})  # no error list: code was patched
    assert asyncio.run(pipeline.compile_tex(ctx, "body", 10))[0] is None

    pdf, out = asyncio.run(pipeline.compile_tex(ctx, "\\includegraphics[width=1bp]{assets/nope.png}", 10))
    assert pdf is None and "assets/nope.png' not found" in out  # never compiled with a placeholder image

    results.append({"success": True, "pdf_base64": pdf_b64, "log": "", "errors": []})
    assert asyncio.run(pipeline.compile_tex(ctx, "body", 10))[0] == b"%PDF-1.5"
