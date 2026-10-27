"""Bibliography handling in compiler.py (no TeX needed: the engine is faked)."""

import base64
import subprocess
from pathlib import Path

import pytest

import compiler


class FakeRun:
    """Stands in for compiler._run_tex; records commands and the files the engine would see."""

    def __init__(self):
        self.commands = []
        self.main_tex = None
        self.files = {}

    def __call__(self, cmd, *, cwd, timeout, env, capture_output=True):
        cwd = Path(cwd)
        self.commands.append(list(cmd))
        if cmd[0] in ("pdflatex", "xelatex", "lualatex"):
            self.main_tex = (cwd / "main.tex").read_text()
            self.files = {p.name: p.read_text() for p in cwd.glob("*.bib")}
            (cwd / "main.pdf").write_bytes(b"%PDF-1.4 fake")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


@pytest.fixture
def fake(monkeypatch):
    run = FakeRun()
    monkeypatch.setattr(compiler, "_run_tex", run)
    return run


def test_detection_sees_addbibresource_in_input_file(tmp_path):
    (tmp_path / "ch1.tex").write_text("\\addbibresource{refs.bib}\n")
    text = compiler._project_tex_text("\\input{ch1}\n", tmp_path)
    assert compiler._bibliography_backend(text) == "biber"
    assert compiler._bibliography_backend("\\input{ch1}") is None  # main alone misses it


def test_commented_out_bibliography_is_ignored():
    assert compiler._bib_targets("% \\bibliography{old}\n\\bibliography{new}") == ["new.bib"]


def test_biber_missing_falls_back_to_bibtex_with_one_diagnostic(fake, monkeypatch):
    monkeypatch.setattr(compiler.shutil, "which", lambda name: None if name == "biber" else "/usr/bin/" + name)
    src = ("\\documentclass{article}\\usepackage{biblatex}\\addbibresource{refs.bib}\n"
           "\\begin{document}\\cite{a}\\printbibliography\\end{document}\n")
    res = compiler._compile_latex_impl(src, persist_synctex=False)
    assert res["success"]
    assert ["bibtex", "main"] in fake.commands
    assert not any(c[0] == "biber" for c in fake.commands)
    msgs = [d["message"] for d in res["diagnostics"]]
    assert msgs.count("biblatex detected but biber is not installed; fell back to bibtex.") == 1
    assert res["errors"] == []  # a bibliography note never becomes a compile error


def test_missing_bib_gets_stub_with_one_entry_per_key(fake):
    src = ("\\documentclass{article}\\begin{document}\n"
           "\\cite{a,b} \\citep[p.~3]{c} \\textcite{a} \\autocite{d}\n"
           "\\bibliographystyle{plain}\\bibliography{refs}\\end{document}\n")
    res = compiler._compile_latex_impl(src, persist_synctex=False)
    assert res["success"]
    bib = fake.files["refs.bib"]
    for key in "abcd":
        assert f"@misc{{{key}," in bib
    assert bib.count("@misc{") == 4
    assert any("refs.bib" in d["message"] for d in res["diagnostics"])


def test_existing_bib_is_not_overwritten(tmp_path):
    (tmp_path / "refs.bib").write_text("@book{a, title={Real}}")
    assert compiler._generate_stub_bibs(tmp_path, "\\cite{a}\\bibliography{refs}") == []
    assert "Real" in (tmp_path / "refs.bib").read_text()


def test_inline_thebibliography_generates_no_bib(fake):
    src = ("\\documentclass{article}\\begin{document}\\cite{x}\n"
           "\\begin{thebibliography}{9}\\bibitem{x} Someone.\\end{thebibliography}\\end{document}\n")
    res = compiler._compile_latex_impl(src, persist_synctex=False)
    assert res["success"]
    assert fake.files == {}
    assert not any(c[0] in ("bibtex", "biber") for c in fake.commands)
    assert len([c for c in fake.commands if c[0] == "pdflatex"]) == 2  # the extra pass still runs
    assert "hyperref" in fake.main_tex  # citations are made clickable here too


def test_hyperref_injected_once_into_compile_copy_only(tmp_path):
    src = "\\documentclass{article}\n\\begin{document}\\cite{a}\\end{document}\n"
    out = compiler._inject_hyperref(src, src, tmp_path)
    assert out.count(r"\usepackage[hidelinks]{hyperref}") == 1
    assert r"\@ifpackageloaded{hyperref}" in out  # a no-op if a class already loaded it
    assert out.count("\n") == src.count("\n")  # no line shift
    assert out.index("hyperref") < out.index("\\begin{document}")
    assert compiler._inject_hyperref(out, out, tmp_path) == out  # idempotent


def test_hyperref_not_injected_when_loaded_elsewhere(tmp_path):
    src = "\\documentclass{article}\\usepackage[colorlinks]{hyperref}\\begin{document}\\cite{a}\\end{document}"
    assert compiler._inject_hyperref(src, src, tmp_path) == src
    (tmp_path / "ch.tex").write_text("\\usepackage{hyperref}")
    main = "\\documentclass{article}\\begin{document}\\cite{a}\\end{document}"
    assert compiler._inject_hyperref(main, compiler._project_tex_text(main, tmp_path), tmp_path) == main


@pytest.mark.parametrize("cls", ["\\documentclass{beamer}", "\\documentclass[10pt]{beamer}"])
def test_hyperref_skipped_for_beamer(cls, tmp_path):
    src = cls + "\\begin{document}\\cite{a}\\end{document}"
    assert compiler._inject_hyperref(src, src, tmp_path) == src


def test_hyperref_skipped_without_citations_or_with_cleveref(tmp_path):
    plain = "\\documentclass{article}\\begin{document}hi\\end{document}"
    assert compiler._inject_hyperref(plain, plain, tmp_path) == plain
    clev = "\\documentclass{article}\\usepackage{cleveref}\\begin{document}\\cite{a}\\end{document}"
    assert compiler._inject_hyperref(clev, clev, tmp_path) == clev


def test_user_source_is_not_modified_in_result(fake):
    src = "\\documentclass{article}\\begin{document}\\cite{a}\\end{document}\n"
    res = compiler._compile_latex_impl(src, persist_synctex=False)
    assert "hyperref" in fake.main_tex
    assert "hyperref" not in src
    assert "hyperref" not in str(res.get("code", ""))
