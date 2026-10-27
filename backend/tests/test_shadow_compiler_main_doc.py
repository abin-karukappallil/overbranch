"""The agent's shadow compile builds the project's MAIN document, not the file being edited."""
import base64
import shutil

import pytest

import compiler
import project_storage
from agent import shadow_compiler
from agent.shadow_workspace import ShadowWorkspace

needs_tex = pytest.mark.skipif(shutil.which("latexmk") is None or shutil.which("pdflatex") is None,
                               reason="needs latexmk + pdflatex")
B = "\\"
MAIN = (B + "documentclass{article}\n" + B + "begin{document}\nTHESISMAIN\n"
        + B + "input{ch}\n" + B + "end{document}\n")


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    base = (tmp_path / "projects").resolve()
    base.mkdir()
    monkeypatch.setattr(project_storage, "UPLOADS_BASE_DIR", base)
    monkeypatch.setenv("UPLOADS_BASE_DIR", str(base))

    def no_supabase():
        raise RuntimeError("no supabase in tests")
    monkeypatch.setattr(project_storage, "get_supabase_client", no_supabase)
    return base


def make(base, pid, files):
    for rel, text in files.items():
        p = base / pid / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


@pytest.fixture
def captured(monkeypatch):
    seen = {}

    def fake_compile(**kwargs):
        seen.update(kwargs)
        return {"success": True, "pdf_base64": "", "log": "ok", "errors": []}

    monkeypatch.setattr(compiler, "compile_latex", fake_compile)
    return seen


def decoded(files):
    return {f["filename"]: base64.b64decode(f["data"]).decode() for f in files or []}


def test_subfolder_main_is_compiled_when_editing_a_chapter(uploads, captured):
    make(uploads, "p1", {"thesis/thesis.tex": MAIN, "thesis/ch.tex": "disk chapter\n"})
    project_storage.set_main_document("p1", "thesis/thesis.tex")
    ws = ShadowWorkspace("buffer chapter\n", project_id="p1", file_path="thesis/ch.tex")
    shadow_compiler._run_compile(ws, "EDITED chapter\n", "pdfLaTeX", 30)
    assert captured["active_file"] == "thesis/thesis.tex"
    assert captured["active_text"] == MAIN and captured["latex_code"] == MAIN
    assert decoded(captured["files"])["thesis/ch.tex"] == "EDITED chapter\n"
    assert captured["pre_heal"] is False


def test_editing_the_main_document_itself(uploads, captured):
    make(uploads, "p2", {"thesis/thesis.tex": MAIN})
    project_storage.set_main_document("p2", "thesis/thesis.tex")
    ws = ShadowWorkspace(MAIN, project_id="p2", file_path="thesis/thesis.tex")
    shadow_compiler._run_compile(ws, MAIN + "% edit\n", "pdfLaTeX", 30)
    assert captured["active_file"] == "thesis/thesis.tex" and captured["active_text"].endswith("% edit\n")
    assert "thesis/thesis.tex" not in decoded(captured["files"])


def test_main_tex_project_is_unchanged_in_shape(uploads, captured):
    make(uploads, "p3", {"main.tex": MAIN, "ch.tex": "c\n"})
    ws = ShadowWorkspace("c\n", project_id="p3", file_path="ch.tex")
    shadow_compiler._run_compile(ws, "c2\n", "pdfLaTeX", 30)
    assert captured["active_file"] == "main.tex" and captured["latex_code"] == MAIN
    assert decoded(captured["files"]) == {"ch.tex": "c2\n"}


def test_aux_edited_main_is_used(uploads, captured):
    make(uploads, "p4", {"main.tex": MAIN, "ch.tex": "c\n"})
    ws = ShadowWorkspace("c\n", project_id="p4", file_path="ch.tex")
    ws.__dict__["_aux_files"] = {"main.tex": MAIN + "% aux edit\n"}
    shadow_compiler._run_compile(ws, "c\n", "pdfLaTeX", 30)
    assert captured["active_text"].endswith("% aux edit\n")
    assert "main.tex" not in decoded(captured["files"])


def test_scratch_document_keeps_the_legacy_path(uploads, captured):
    ws = ShadowWorkspace(MAIN)  # project_id "default"
    shadow_compiler._run_compile(ws, MAIN, "pdfLaTeX", 30)
    assert captured["active_file"] is None and captured["latex_code"] == MAIN


@needs_tex
def test_real_tex_builds_the_subfolder_main_and_reports_errors_in_the_edited_chapter(uploads):
    make(uploads, "p5", {
        "thesis/thesis.tex": MAIN,
        "thesis/ch.tex": "ok chapter\n",
        "main.tex": B + "documentclass{article}\n" + B + "begin{document}\nWRONGDOC\n" + B + "end{document}\n",
    })
    project_storage.set_main_document("p5", "thesis/thesis.tex")
    ws = ShadowWorkspace("ok chapter\n", project_id="p5", file_path="thesis/ch.tex")
    ok = shadow_compiler._run_compile(ws, "fine edited chapter\n", "pdfLaTeX", 60)
    assert ok["result"]["success"] and not ok["errors"], ok["log"]
    assert ok["result"]["main_file"] == "thesis/thesis.tex"
    import fitz
    doc = fitz.open(stream=ok["pdf"], filetype="pdf")
    text = "\n".join(p.get_text() for p in doc)
    assert "THESISMAIN" in text and "fine edited chapter" in text and "WRONGDOC" not in text

    bad = shadow_compiler._run_compile(ws, B + "undefinedmacroxyz\n", "pdfLaTeX", 60)
    assert bad["errors"], bad["log"]
    print("error file field:", [e.get("file") for e in bad["errors"]])
