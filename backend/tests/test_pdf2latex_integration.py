"""
End-to-end: convert fixture PDFs, compile with pdfLaTeX through the real compile service,
render both PDFs and check page count and measured similarity.

The LLM is stubbed with a simple flow-layout writer so the test is deterministic and
offline. Set PDF2LATEX_LIVE_LLM=1 to run one conversion against the real copilot model.
Skipped when pdflatex/latexmk or pdftoppm are missing.
"""

import asyncio
import json
import os
import shutil

import pymupdf
import pytest

import pdf2latex.llm as llm
import project_storage
from compile_queue import compile_queue
from pdf2latex import jobs, pipeline, storage
from tests import pdf2latex_fixtures as fx

pytestmark = pytest.mark.skipif(
    not (shutil.which("pdflatex") or shutil.which("latexmk")) or not shutil.which("pdftoppm"),
    reason="needs pdfLaTeX and poppler's pdftoppm",
)


@pytest.fixture
def env(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(project_storage, "UPLOADS_BASE_DIR", uploads.resolve())
    monkeypatch.setattr(storage, "_supabase", lambda: None)
    monkeypatch.setenv("PDF2LATEX_JOB_DIR", str(tmp_path / "jobs"))
    monkeypatch.setattr(compile_queue, "_semaphore", None)
    return uploads


def _stub_llm(monkeypatch):
    def chat(messages, model, temperature=0.1, max_tokens=4096, api_keys=None, cancel_token=None):
        user = messages[-1]["content"]
        text = user if isinstance(user, str) else user[0]["text"]
        facts = json.loads(text.split("Page facts (JSON):\n", 1)[1].split("\n\nReturn only")[0])
        out, y = [], 0.0
        for ln in facts["lines"]:
            t = ln.get("t") or " ".join(r["t"] for r in ln["runs"])
            gap = max(0.0, ln["y"] - y - ln["sz"] * 1.2)
            out.append(f"\\vspace{{{gap:.1f}pt}}\\noindent\\hspace*{{{ln['x']}pt}}"
                       f"{{\\fontsize{{{ln['sz']}}}{{{ln['sz'] * 1.2:.1f}}}\\selectfont {t}\\par}}")
            y = ln["y"]
        for im in facts.get("images", []):
            out.append(f"\\noindent\\includegraphics[width={im['w']}bp,height={im['h']}bp]{{{im['file']}}}\\par")
        return {"content": "\n".join(out) + ("" if facts["page"] == facts["of"] else "\n\\newpage")}

    monkeypatch.setattr(pipeline, "llm_available", lambda: True)
    monkeypatch.setattr(llm.provider_router, "chat", chat)


def _convert(data, project):
    with pymupdf.open(stream=data, filetype="pdf") as src:
        n = src.page_count
    job = jobs.create_job("user-int", project, f"{project}.pdf", n)
    asyncio.run(pipeline.run_conversion(job["job_id"], data, project))
    return jobs.load_job(job["job_id"]), n


@pytest.mark.parametrize("use_llm", [True, False], ids=["llm", "no-llm"])
def test_multi_page_conversion_compiles_with_same_page_count(env, monkeypatch, use_llm):
    if use_llm:
        _stub_llm(monkeypatch)
    else:
        monkeypatch.setattr(pipeline, "llm_available", lambda: False)
    data = fx.multi_page_pdf()
    state, n = _convert(data, "proj-multi")
    assert state["status"] == "done", state.get("error")
    report = state["report"]
    assert report["compiled"] is True, report["warnings"]
    assert report["compiled_page_count"] == n == 3

    out_pdf = jobs.job_dir(state["job_id"]) / "output.pdf"
    with pymupdf.open(str(out_pdf)) as out, pymupdf.open(stream=data, filetype="pdf") as src:
        assert out.page_count == src.page_count
        assert tuple(out[0].rect) == pytest.approx(tuple(src[0].rect), abs=0.5)
        text = out[0].get_text()
        assert "Quarterly Report" in text and "monospace:" in text  # real, selectable text
        assert "Revenue" in out[2].get_text()

    scores = [p["similarity"] for p in report["pages"]]
    assert all(s is not None and s > 0.8 for s in scores), scores
    main_tex = (env / "proj-multi" / "main.tex").read_text()
    assert "\\definecolor{c0D2673}{RGB}{13,38,115}" in main_tex
    assert (env / "proj-multi" / state["result"]["assets"][0]).exists()


@pytest.mark.parametrize("name", ["image", "table", "vector", "two_column", "scanned"])
def test_fixture_pages_compile(env, monkeypatch, name):
    _stub_llm(monkeypatch)
    data = getattr(fx, f"{name}_pdf")()
    state, n = _convert(data, f"proj-{name}")
    assert state["status"] == "done", state.get("error")
    assert state["report"]["compiled_page_count"] == n


@pytest.mark.skipif(os.getenv("PDF2LATEX_LIVE_LLM") != "1", reason="set PDF2LATEX_LIVE_LLM=1 to call the real model")
def test_live_llm_conversion(env):
    if not llm.llm_available():
        pytest.skip("GEMINI_WEB2API_* is not configured")
    state, n = _convert(fx.multi_page_pdf(), "proj-live")
    assert state["status"] == "done", state.get("error")
    assert state["report"]["compiled_page_count"] == n
    print(json.dumps([(p["number"], p["similarity"], p["fallback"]) for p in state["report"]["pages"]]))
