"""
Deterministic repairs for the most common compile errors in generated LaTeX:
a macro/environment whose package is not loaded, `_` / `&` in text.
"""

import types
from pathlib import Path

import compiler
from latex_error_fixer import ensure_required_packages, repair_from_compile_errors
from opencode.shadow_workspace import ShadowWorkspace

B = "\\"


def _doc(*body, preamble=(), cls="article"):
    return "\n".join([B + "documentclass{" + cls + "}", *preamble, B + "begin{document}", *body,
                      B + "end{document}", ""])


TABLE = [B + "begin{tabular}{ll}", B + "toprule", "a & b " + B + B, B + "bottomrule", B + "end{tabular}"]


# --- ensure_required_packages ---------------------------------------------------------------

def test_booktabs_is_added_before_begin_document():
    out, fixes = ensure_required_packages(_doc(*TABLE))
    assert B + "usepackage{booktabs}\n" + B + "begin{document}" in out
    assert fixes and "booktabs" in fixes[0]


def test_align_needs_amsmath():
    out, _ = ensure_required_packages(_doc(B + "begin{align}", "a &= b", B + "end{align}"))
    assert B + "usepackage{amsmath}" in out


def test_beamer_already_provides_xcolor():
    code = _doc(B + "begin{frame}", B + "textcolor{red}{x}", B + "end{frame}", cls="beamer")
    assert ensure_required_packages(code) == (code, [])


def test_tikz_provides_xcolor():
    code = _doc(B + "textcolor{red}{x}", preamble=(B + "usepackage{tikz}",))
    assert ensure_required_packages(code) == (code, [])


def test_macro_defined_by_the_document_needs_no_package():
    code = _doc(*TABLE, preamble=(B + "newcommand{" + B + "toprule}{" + B + "hline}",
                                  B + "newcommand{" + B + "bottomrule}{" + B + "hline}"))
    assert ensure_required_packages(code) == (code, [])


def test_commented_use_is_not_a_use():
    code = _doc("% " + B + "toprule would go here", "Text.")
    assert ensure_required_packages(code) == (code, [])


def test_preamble_use_gets_the_package_before_it():
    code = _doc("Text.", preamble=(B + "definecolor{navy}{HTML}{0B2545}",))
    out, _ = ensure_required_packages(code)
    assert out.index(B + "usepackage{xcolor}") < out.index(B + "definecolor")


def test_ulem_gets_normalem():
    out, _ = ensure_required_packages(_doc(B + "sout{old}"))
    assert B + "usepackage[normalem]{ulem}" in out


def test_xcolor_table_option_provides_rowcolor():
    code = _doc(B + "begin{tabular}{l}", B + "rowcolor{gray}a " + B + B, B + "end{tabular}",
                preamble=(B + "usepackage[table]{xcolor}",))
    assert ensure_required_packages(code) == (code, [])


def test_agent_edit_that_uses_toprule_gets_booktabs():
    code = _doc("Intro text here.")
    ws = ShadowWorkspace(code)
    res = ws.str_replace("Intro text here.", "\n".join(TABLE))
    assert res["success"]
    assert B + "usepackage{booktabs}" in ws.get_buffer()


def test_editor_compile_adds_the_package_and_reports_source_lines(monkeypatch):
    seen = {}

    def run(cmd, cwd=None, **kw):
        src = (Path(cwd) / "main.tex").read_text(encoding="utf-8").splitlines()
        seen["src"] = src
        n = next(i + 1 for i, l in enumerate(src) if "undefinedmacro" in l)
        return types.SimpleNamespace(stdout=f"./main.tex:{n}: Undefined control sequence.\n", stderr="",
                                     returncode=1)

    monkeypatch.setattr(compiler.subprocess, "run", run)
    doc = _doc(*TABLE, B + "undefinedmacro")
    r = compiler.compile_latex(doc, engine="pdflatex", persist_synctex=False)
    assert B + "usepackage{booktabs}" in seen["src"]
    source_line = doc.splitlines().index(B + "undefinedmacro") + 1
    assert f"main.tex:{source_line}:" in r["error_log"]


# --- repair_from_compile_errors ---------------------------------------------------------------

def _err(line, msg):
    return {"error": msg, "line": line}


def test_missing_dollar_escapes_underscore_in_text_only():
    code = _doc("See file_name and " + B + "label{fig_a} and $x_1$ here.")
    line = code.splitlines().index("See file_name and " + B + "label{fig_a} and $x_1$ here.") + 1
    out, fixes = repair_from_compile_errors(code, [_err(line, "Missing $ inserted.")])
    assert "See file" + B + "_name and " + B + "label{fig_a} and $x_1$ here." in out
    assert fixes


def test_missing_dollar_inside_a_math_environment_is_left_alone():
    code = _doc(B + "begin{align}", "a_b &= c", B + "end{align}")
    line = code.splitlines().index("a_b &= c") + 1
    assert repair_from_compile_errors(code, [_err(line, "Missing $ inserted.")]) == (code, [])


def test_ampersand_in_text_is_escaped_but_not_in_a_tabular():
    code = _doc("Tom & Jerry", *TABLE)
    text_line = code.splitlines().index("Tom & Jerry") + 1
    row_line = code.splitlines().index("a & b " + B + B) + 1
    out, _ = repair_from_compile_errors(code, [_err(text_line, "Misplaced alignment tab character &."),
                                              _err(row_line, "Misplaced alignment tab character &.")])
    assert "Tom " + B + "& Jerry" in out
    assert "a & b " + B + B in out


def test_only_allowed_lines_are_repaired():
    code = _doc("See file_name here.")
    line = code.splitlines().index("See file_name here.") + 1
    assert repair_from_compile_errors(code, [_err(line, "Missing $ inserted.")], allowed_lines={1}) == (code, [])
