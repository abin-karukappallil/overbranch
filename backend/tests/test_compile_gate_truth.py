"""
The agent's compile gate must not report success when TeX failed.

Each of these used to return success=True. None of them showed on a machine
without TeX (every compile is "infrastructure-skipped" there), which is why
broken AI edits only shipped in production. No TeX needed: compile_latex /
subprocess.run are faked.
"""

import types
from pathlib import Path

import pytest

import compiler
from latex_error_fixer import parse_compilation_errors
from opencode.shadow_compiler import compile_shadow_buffer
from opencode.shadow_workspace import ShadowWorkspace

B = "\\"
ORIG = "\n".join([B + "documentclass{article}", B + "begin{document}", "A " + B + "bottom", "B",
                  B + "end{document}", ""])
WITH_NEW_MACRO = ORIG.replace("B\n", B + "foo\n")


def _pdf(errors, log=""):
    return {"success": True, "pdf_base64": "", "log": log, "errors": errors}


def _fail(log):
    return {"success": False, "error_log": log, "raw_log": log}


def _gate(monkeypatch, buffer, results, strict=False):
    it = iter(results)
    calls = []

    def fake_compile_latex(**kw):
        calls.append(kw)
        return next(it)

    monkeypatch.setattr(compiler, "compile_latex", fake_compile_latex)
    ws = ShadowWorkspace(ORIG)
    ws._buffer = buffer
    ws.compile_strict = strict
    return compile_shadow_buffer(ws), calls


def test_not_found_in_log_is_not_compiler_unavailable(monkeypatch):
    res, _ = _gate(monkeypatch, WITH_NEW_MACRO, [
        _pdf(["./main.tex:4: Undefined control sequence.",
              "./main.tex:9: LaTeX Error: File `logo.png' not found."]),
        _pdf([]),
    ])
    assert not res.get("infra_skip")
    assert res["success"] is False
    assert res["new_error_count"] == 2


def test_new_error_is_not_masked_by_an_old_one_of_the_same_kind(monkeypatch):
    res, _ = _gate(monkeypatch, WITH_NEW_MACRO, [
        _pdf(["./main.tex:3: Undefined control sequence.", "./main.tex:4: Undefined control sequence."]),
        _pdf(["./main.tex:3: Undefined control sequence."]),
    ])
    assert res["success"] is False
    assert res["new_error_count"] == 1
    assert res["preexisting_errors"] == 1
    assert res["errors"][0]["line"] == 4


def test_pre_existing_error_moved_by_an_insert_is_still_pre_existing(monkeypatch):
    moved = ORIG.replace(B + "begin{document}\n", B + "begin{document}\nNew paragraph.\n")
    res, _ = _gate(monkeypatch, moved, [
        _pdf(["./main.tex:4: Undefined control sequence."]),   # \bottom, now one line lower
        _pdf(["./main.tex:3: Undefined control sequence."]),
    ])
    assert res["success"] is True
    assert res["preexisting_errors"] == 1
    assert "cleanly" not in res["summary"]


def test_timeout_is_a_failure_after_one_retry(monkeypatch):
    res, calls = _gate(monkeypatch, WITH_NEW_MACRO, [
        _fail("\n[TIMEOUT] pdflatex exceeded 30s"),
        _fail("\n[TIMEOUT] pdflatex exceeded 60s"),
        _pdf([]),  # the original compiles
    ])
    assert res["success"] is False
    assert not res.get("infra_skip")
    assert calls[1]["timeout_seconds"] == 2 * calls[0]["timeout_seconds"]
    assert "TIMEOUT" in res["errors"][0]["error"]


def test_timeout_then_success_on_retry_passes(monkeypatch):
    res, _ = _gate(monkeypatch, WITH_NEW_MACRO, [_fail("\n[TIMEOUT] pdflatex exceeded 30s"), _pdf([])])
    assert res["success"] is True


def test_missing_tex_engine_is_still_infra(monkeypatch):
    res, _ = _gate(monkeypatch, WITH_NEW_MACRO, [
        _fail("\n[INFRASTRUCTURE ERROR] Executable 'pdflatex' not found: [WinError 2]")])
    assert res.get("infra_skip") is True


def test_strict_mode_fails_while_the_original_error_remains(monkeypatch):
    unchanged_error = ORIG.replace("B\n", "C\n")
    res, _ = _gate(monkeypatch, unchanged_error, [
        _pdf(["./main.tex:3: Undefined control sequence."]),
        _pdf(["./main.tex:3: Undefined control sequence."]),
    ], strict=True)
    assert res["success"] is False
    assert res["new_error_count"] == 0
    assert res["errors_before"] == 1 and res["errors_after"] == 1
    assert "remain" in res["summary"]


def test_strict_mode_passes_when_fixed(monkeypatch):
    fixed = ORIG.replace(B + "bottom", B + "textbf{x}")
    res, _ = _gate(monkeypatch, fixed, [_pdf([])], strict=True)
    assert res["success"] is True
    assert res["summary"] == "Compiled without errors."


def test_editing_a_non_main_file_compiles_the_projects_real_main(monkeypatch):
    main = "\n".join([B + "documentclass{article}", B + "begin{document}", B + "input{chapters/intro}",
                      B + "end{document}", ""])
    chapter = B + "section{Intro}\nText.\n"
    calls = []

    def fake_compile_latex(**kw):
        calls.append(kw)
        return _pdf([])

    monkeypatch.setattr(compiler, "compile_latex", fake_compile_latex)
    monkeypatch.setattr(compiler, "load_project_text_file",
                        lambda pid, rel="main.tex": main if (pid, rel) == ("p1", "main.tex") else None)
    ws = ShadowWorkspace(chapter, project_id="p1", file_path="chapters/intro.tex")
    assert compile_shadow_buffer(ws)["success"] is True
    assert calls[0]["latex_code"] == main
    assert "chapters/intro.tex" in [f["filename"] for f in calls[0]["files"]]


# --- compiler.py ---------------------------------------------------------------------

def _capture_engine(monkeypatch):
    seen = []

    def run(cmd, cwd=None, **kw):
        seen.append(cmd[0])
        (Path(cwd) / "main.pdf").write_bytes(b"%PDF-1.4")
        return types.SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(compiler.subprocess, "run", run)
    return seen


def test_explicit_pdflatex_switches_to_xelatex_for_fontspec(monkeypatch):
    seen = _capture_engine(monkeypatch)
    doc = "\n".join([B + "documentclass{article}", B + "usepackage{fontspec}", B + "setmainfont{Arial}",
                     B + "begin{document}", "x", B + "end{document}", ""])
    compiler.compile_latex(doc, engine="pdfLaTeX", persist_synctex=False, allow_recovery=False)
    assert seen[0] == "xelatex"


def test_explicit_pdflatex_stays_pdflatex_for_plain_documents(monkeypatch):
    seen = _capture_engine(monkeypatch)
    compiler.compile_latex(ORIG, engine="pdfLaTeX", persist_synctex=False, allow_recovery=False)
    assert seen[0] == "pdflatex"


def test_compile_failure_keeps_file_line_errors_and_context():
    log = ("This is pdfTeX\n(./main.tex\n./main.tex:42: Undefined control sequence.\n"
           "l.42 Some text " + B + "foo\n\n./main.tex:50: Missing $ inserted.\n<inserted text>\n$\n"
           "l.50 a_b\n!  ==> Fatal error occurred, no output PDF file produced!\n")
    r = compiler._compile_failure(log)
    assert "./main.tex:42: Undefined control sequence." in r["error_log"]
    assert "l.42 Some text " + B + "foo" in r["error_log"]
    assert "./main.tex:50: Missing $ inserted." in r["error_log"]
    assert "./main.tex:42: Undefined control sequence." in r["errors"]


def test_recovery_success_still_reports_errors(monkeypatch):
    state = {"n": 0}

    def run(cmd, cwd=None, **kw):
        state["n"] += 1
        if state["n"] == 1:  # first run: a package is missing, TeX stops
            out = "./main.tex:2: LaTeX Error: File `fancypkg.sty' not found.\n"
            return types.SimpleNamespace(stdout=out, stderr="", returncode=1)
        assert "-file-line-error" in cmd
        (Path(cwd) / "main.pdf").write_bytes(b"%PDF-1.4")
        out = "./main.tex:4: Undefined control sequence.\nl.4 " + B + "foo\n"
        return types.SimpleNamespace(stdout=out, stderr="", returncode=1)

    monkeypatch.setattr(compiler.subprocess, "run", run)
    doc = "\n".join([B + "documentclass{article}", B + "usepackage{fancypkg}", B + "begin{document}",
                     B + "foo", B + "end{document}", ""])
    r = compiler.compile_latex(doc, engine="pdflatex", persist_synctex=False, pre_heal=False)
    assert r["success"] is True
    assert r["errors"] == ["./main.tex:4: Undefined control sequence."]


# --- latex_error_fixer.parse_compilation_errors ----------------------------------------

def test_parse_classic_bang_format_with_l_number():
    log = "! Undefined control sequence.\nl.17 Some text " + B + "foo\n"
    [e] = parse_compilation_errors(log)
    assert e.line_number == 17
    assert e.error_type == "UNDEFINED_MACRO"
    assert e.snippet.endswith(B + "foo")


def test_parse_keeps_file_and_drops_lines_of_packages():
    log = ("./chapters/intro.tex:5: Undefined control sequence.\n"
           "/usr/share/texlive/texmf-dist/tex/latex/foo/foo.sty:120: Package foo Error: bad option.\n"
           "./main.tex:9: Emergency stop.\n")
    errs = parse_compilation_errors(log)
    assert [(e.file, e.line_number) for e in errs] == [
        ("chapters/intro.tex", 5),
        ("/usr/share/texlive/texmf-dist/tex/latex/foo/foo.sty", None),
    ]


def test_pdflatex_non_utf8_output_byte_0xed_does_not_raise_infra_error(monkeypatch):
    """
    pdflatex can emit non-UTF-8 bytes (e.g. byte 0xed) in font banners, metrics, or error logs.
    This must NOT crash with UnicodeDecodeError or be classified as [INFRASTRUCTURE ERROR].
    """
    raw_non_utf8 = b"This is pdfTeX\n" + b"x" * 13840 + b"\xed" + b"invalid continuation\nOutput written on main.pdf (1 page).\n"

    def run(cmd, cwd=None, **kw):
        (Path(cwd) / "main.pdf").write_bytes(b"%PDF-1.4 simulated pdf")
        return types.SimpleNamespace(stdout=raw_non_utf8, stderr=b"", returncode=0)

    monkeypatch.setattr(compiler.subprocess, "run", run)
    doc = "\n".join([B + "documentclass{article}", B + "begin{document}", "Hello", B + "end{document}", ""])
    res = compiler.compile_latex(doc, engine="pdflatex", persist_synctex=False)

    assert res["success"] is True
    assert "pdf_base64" in res
    assert "[INFRASTRUCTURE ERROR]" not in res.get("log", "")
    assert "[INFRASTRUCTURE ERROR]" not in res.get("error_log", "")



# ── Timeouts are a missing answer, not a verdict on the edit ────────────────

def test_the_budget_comes_from_the_whole_project_not_just_main(monkeypatch):
    """
    A thesis has a main.tex of thirty lines that only \\input{}s its chapters.
    Sized on that file alone it looked like the lightest document in the
    project, got the short budget, and timed out — then the gate called the
    timeout a compile failure and the whole run was rolled back.
    """
    from opencode.shadow_compiler import project_compile_timeout, SHADOW_COMPILE_TIMEOUT

    ws = ShadowWorkspace(ORIG)
    assert project_compile_timeout(ws) == SHADOW_COMPILE_TIMEOUT

    thesis = ShadowWorkspace(
        B + "documentclass{report}\n" + B + "begin{document}\n"
        + B + "input{ch1}\n" + B + "end{document}\n")
    thesis.add_auxiliary_file("ch1.tex", "x" * 250_000)
    assert project_compile_timeout(thesis) > project_compile_timeout(ws)

    tikz = ShadowWorkspace(ORIG)
    tikz.add_auxiliary_file("ch1.tex", (B + "begin{tikzpicture}") * 6)
    assert project_compile_timeout(tikz) > SHADOW_COMPILE_TIMEOUT


def test_the_retry_does_not_double_past_the_ceiling(monkeypatch):
    from opencode import shadow_compiler

    monkeypatch.setattr(shadow_compiler, "SHADOW_COMPILE_TIMEOUT_MAX", 100)
    res, calls = _gate(monkeypatch, WITH_NEW_MACRO, [
        _fail("\n[TIMEOUT] pdflatex exceeded 90s"),
        _fail("\n[TIMEOUT] pdflatex exceeded 100s"),
        _pdf([]),
    ])
    assert calls[1]["timeout_seconds"] <= 100


def test_a_timeout_the_original_also_has_does_not_fail_a_fix_request(monkeypatch):
    """
    Strict mode fails on every remaining error, which is right for errors. A
    timeout is not an error, it is the absence of an answer — counting it as
    one told a user whose document is merely slow that their edit had broken
    it, and discarded the edit.
    """
    res, _ = _gate(monkeypatch, WITH_NEW_MACRO, [
        _fail("\n[TIMEOUT] pdflatex exceeded 90s"),
        _fail("\n[TIMEOUT] pdflatex exceeded 180s"),
        _fail("\n[TIMEOUT] pdflatex exceeded 90s"),
        _fail("\n[TIMEOUT] pdflatex exceeded 180s"),
    ], strict=True)
    assert res["success"] is True
    assert res["unverified"] is True and res["timed_out"] is True
    assert "could not be verified" in res["summary"]
    assert "did not compile" not in res["summary"]


def test_a_timeout_only_the_edit_has_still_fails(monkeypatch):
    """The original builds and the edit does not: that is evidence, and it stands."""
    res, _ = _gate(monkeypatch, WITH_NEW_MACRO, [
        _fail("\n[TIMEOUT] pdflatex exceeded 90s"),
        _fail("\n[TIMEOUT] pdflatex exceeded 180s"),
        _pdf([]),
    ], strict=True)
    assert res["success"] is False
    assert res["unverified"] is False


def test_a_real_error_in_strict_mode_still_fails(monkeypatch):
    """The timeout exemption must not become a hole for genuine errors."""
    res, _ = _gate(monkeypatch, WITH_NEW_MACRO, [
        _pdf(["./main.tex:3: Undefined control sequence."]),
        _pdf(["./main.tex:3: Undefined control sequence."]),
    ], strict=True)
    assert res["success"] is False
    assert res["unverified"] is False
