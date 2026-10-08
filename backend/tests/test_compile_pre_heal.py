"""
compile_latex pre-heal: who heals before TeX, and which line numbers come back.

The healer can insert lines (\\usetikzlibrary{calc} after \\usepackage{tikz}),
so TeX's line numbers refer to the healed text. The editor gets them translated
back to the user's source; the agent's shadow compiler skips the pre-heal so its
error lines match its buffer. No TeX needed: subprocess.run is faked.
"""

import types
from pathlib import Path

import pytest

import compiler

B = "\\"
DOC = "\n".join([B + "documentclass{article}", B + "usepackage{tikz}", B + "begin{document}", "Hello",
                 B + "undefinedmacro", "Some wide text", B + "end{document}", ""])
SRC_ERR, SRC_WIDE = 5, 6


@pytest.fixture
def fake_tex(monkeypatch):
    seen = {}

    def install(make_pdf: bool):
        def run(cmd, cwd=None, **kw):
            src = (Path(cwd) / "main.tex").read_text(encoding="utf-8").splitlines()
            seen["src"] = src
            n = next(i + 1 for i, l in enumerate(src) if "undefinedmacro" in l)
            w = next(i + 1 for i, l in enumerate(src) if "wide text" in l)
            if make_pdf:
                (Path(cwd) / "main.pdf").write_bytes(b"%PDF-1.4")
            out = (f"./main.tex:{n}: Undefined control sequence.\nl.{n} {B}undefinedmacro\n"
                   f"Overfull {B}hbox (12.0pt too wide) in paragraph at lines {w}--{w}\n")
            return types.SimpleNamespace(stdout=out, stderr="", returncode=1)
        monkeypatch.setattr(compiler.subprocess, "run", run)
        return seen

    return install


def _healed(seen) -> bool:
    return any("usetikzlibrary" in line for line in seen["src"])


@pytest.mark.parametrize("make_pdf", [False, True])
def test_editor_compile_heals_and_reports_source_lines(fake_tex, make_pdf):
    seen = fake_tex(make_pdf)
    r = compiler.compile_latex(DOC, engine="pdflatex", persist_synctex=False)
    assert _healed(seen)
    text = (r.get("error_log") or "") + "\n".join(r.get("errors") or []) + (r.get("log") or "")
    assert f"main.tex:{SRC_ERR}:" in text
    assert f"main.tex:{SRC_ERR + 2}:" not in text
    if make_pdf:
        assert f"l.{SRC_ERR} " in r["log"]
        assert [b["lines"] for b in r["overfull"]] == [[SRC_WIDE, SRC_WIDE]]


@pytest.mark.parametrize("kwargs", [
    {"allow_recovery": True, "pre_heal": False},   # agent shadow compiler
    {"allow_recovery": False},                     # PDF importer
])
def test_exact_code_callers_are_not_healed(fake_tex, kwargs):
    seen = fake_tex(False)
    r = compiler.compile_latex(DOC, engine="pdflatex", persist_synctex=False, **kwargs)
    assert not _healed(seen)
    assert f"main.tex:{SRC_ERR}:" in r["error_log"]


def test_shadow_compiler_disables_pre_heal(monkeypatch):
    from opencode import shadow_compiler
    from opencode.shadow_workspace import ShadowWorkspace

    captured = {}

    def fake_compile(**kwargs):
        captured.update(kwargs)
        return {"success": True, "pdf_base64": "", "log": "ok", "errors": []}

    monkeypatch.setattr(compiler, "compile_latex", fake_compile)
    shadow_compiler._run_compile(ShadowWorkspace(DOC), DOC, "pdfLaTeX", 30)
    assert captured["pre_heal"] is False
