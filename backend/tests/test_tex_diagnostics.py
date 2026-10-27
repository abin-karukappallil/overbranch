"""
TeX's errors on the lines they are really on (latex_diagnostics), and the
compiler carrying that through: Beamer reports every error of a frame at its
\\end{frame}, and the context TeX prints underneath is the only place that says
where the offending token is.
"""

import shutil
import types
from pathlib import Path

import pytest

import compiler
from latex_diagnostics import diagnose, enclosing_span, error_lines, locate, parse_tex_errors

HAS_TEX = shutil.which("pdflatex") is not None
needs_tex = pytest.mark.skipif(not HAS_TEX, reason="pdflatex not installed")

DECK = r"""\documentclass{beamer}
\usepackage{tikz,booktabs}
\begin{document}
\begin{frame}{Outline}
  \begin{itemize}
    \item Background & Motivation
    \item Methods & Materials
    \item file_name is snake_case
    \item Uses \undefinedmacro here
    \item Q&A
  \end{itemize}
\end{frame}
\begin{frame}{Numbers}
  \begin{tabular}{ll}
    A & B \\
  \end{tabular}
\end{frame}
\end{document}
"""
END_FRAME = DECK.split("\n").index(r"\end{frame}") + 1  # 12


def _line_of(text: str) -> int:
    return next(i for i, line in enumerate(DECK.split("\n"), start=1) if text in line)


def _pair(first: str, second: str) -> str:
    """A context pair as TeX prints it: the continuation is indented to the width of the first line."""
    return first + "\n" + " " * len(first) + second + "\n"


def _beamer_error(message: str, read: str, upcoming: str, deeper: str = "") -> str:
    return (f"./main.tex:{END_FRAME}: {message}\n" + deeper
            + _pair(r"\beamer@doifinframe ..." + read, upcoming)
            + _pair(f"l.{END_FRAME} " + r"\end{frame}", ""))


LOG = (
    "This is pdfTeX\n(./main.tex\n"
    + _beamer_error("Misplaced alignment tab character &.", r"itemize} \item Background &", r"Motivation \item Methods ...")
    + _beamer_error("Misplaced alignment tab character &.", r" Motivation \item Methods &", r"Materials \item file_...")
    + _beamer_error("Missing $ inserted.", r"Methods & Materials \item file_", "name is snake...",
                    deeper=_pair("<inserted text> ", "$") + _pair("<to be read again> ", "_"))
    + _beamer_error("Undefined control sequence.", r"snake_case \item Uses \undefinedmacro ", r"here \item Q&A ...")
    + _beamer_error("Misplaced alignment tab character &.", r"\undefinedmacro here \item Q&", r"A \end {itemize} ...")
    + "Output written on main.pdf (2 pages).\n"
)


def _located(log: str = LOG, source: str = DECK):
    return diagnose(log, lambda name: source if name == "main.tex" else None)


# --- parsing --------------------------------------------------------------------------

def test_every_occurrence_is_its_own_error():
    errors = parse_tex_errors(LOG)
    assert [e.message for e in errors].count("Misplaced alignment tab character &.") == 3
    assert {e.reported_line for e in errors} == {END_FRAME}
    assert all(e.l_before == r"\end{frame}" for e in errors)


def test_consequences_are_not_errors():
    log = ("./main.tex:3: Undefined control sequence.\nl.3 \\foo\n\n"
           "! Emergency stop.\n!  ==> Fatal error occurred, no output PDF file produced!\n"
           "(That makes 100 errors; please try again.)\n")
    assert [e.message for e in parse_tex_errors(log)] == ["Undefined control sequence."]


def test_classic_log_without_file_line_error_is_understood():
    log = "! Misplaced alignment tab character &.\nl.6     \\item Background &\n                             Motivation\n"
    [err] = parse_tex_errors(log)
    assert (err.file, err.reported_line, err.l_before) == (None, 6, r"    \item Background &")


# --- location -------------------------------------------------------------------------

def test_frame_errors_are_placed_on_their_own_lines():
    found = _located()
    amps = [d for d in found if "alignment tab" in d["message"]]
    assert [d["line"] for d in amps] == [_line_of("Background"), _line_of("Methods"), _line_of("Q&A")]
    assert all(d["token"] == "&" and d["located_by"] == "tex-context" and d["reported_line"] == END_FRAME
               for d in amps)
    # the column is the & itself
    for d in amps:
        assert DECK.split("\n")[d["line"] - 1][d["col"] - 1] == "&"


def test_missing_dollar_is_placed_by_the_deeper_context():
    [d] = [d for d in _located() if d["message"] == "Missing $ inserted."]
    assert (d["line"], d["token"]) == (_line_of("file_name"), "_")


def test_undefined_control_sequence_points_at_the_macro():
    [d] = [d for d in _located() if d["message"] == "Undefined control sequence."]
    line = DECK.split("\n")[d["line"] - 1]
    assert d["token"] == r"\undefinedmacro" and line[d["col"] - 1:].startswith(r"\undefinedmacro")


def test_error_reported_on_its_own_line_stays_there():
    source = "\\documentclass{article}\n\\begin{document}\nPlain R&D text here.\n\\end{document}\n"
    log = "./main.tex:3: Misplaced alignment tab character &.\n" + _pair("l.3 Plain R&", "D text here.")
    [d] = diagnose(log, lambda name: source)
    assert (d["line"], d["col"], d["token"], d["located_by"]) == (3, 8, "&", "tex-line")


def test_an_error_that_cannot_be_placed_keeps_tex_line_and_names_the_block():
    log = (f"./main.tex:{END_FRAME}: Missing $ inserted.\n" + _pair("<inserted text> ", "$")
           + _pair(f"l.{END_FRAME} " + r"\end{frame}", ""))
    [d] = _located(log)
    assert d["located_by"] is None and d["line"] == END_FRAME
    assert d["span"] == [_line_of(r"\begin{frame}{Outline}"), END_FRAME]


def test_a_location_whose_token_cannot_be_the_cause_is_refused():
    # "Extra alignment tab" in a body-grabbing table: TeX's l.N text ends at `}` of \end{tabularx}.
    source = ("\\documentclass{article}\n\\begin{document}\n\\begin{tabularx}{\\textwidth}{lX}\n"
              "A & B & C \\\\\n\\end{tabularx}\n\\end{document}\n")
    log = ("./main.tex:5: Extra alignment tab has been changed to \\cr.\n"
           + _pair("<recently read> \\endtemplate ", "") + _pair("l.5 \\end{tabularx}", ""))
    [d] = diagnose(log, lambda name: source)
    assert d["located_by"] is None and d["span"] == [3, 5]


def test_fragile_frame_error_is_mapped_out_of_the_vrb_file():
    source = ("\\documentclass{beamer}\n\\begin{document}\n\\begin{frame}[fragile]{Code}\n"
              "R&D in a fragile frame\n\\end{frame}\n\\end{document}\n")
    log = "./main.vrb:1: Misplaced alignment tab character &.\n" + _pair("l.1 R&", "D in a fragile frame")
    [d] = diagnose(log, lambda name: source if name == "main.tex" else None)
    assert (d["file"], d["line"], d["token"]) == ("main.tex", 4, "&")


def test_error_lines_keep_distinct_occurrences_and_the_string_shape():
    lines = error_lines(_located())
    assert f"./main.tex:{_line_of('Background')}: Misplaced alignment tab character &." in lines
    assert f"./main.tex:{_line_of('Q&A')}: Misplaced alignment tab character &." in lines
    assert not any(f"main.tex:{END_FRAME}:" in line for line in lines)
    assert len(lines) == len(set(lines)) == 5


@pytest.mark.parametrize("line,expected", [
    (END_FRAME, (4, END_FRAME)),   # \end{frame} -> the frame
    (6, (6, 6)),                   # an ordinary line stands alone
])
def test_enclosing_span(line, expected):
    assert enclosing_span(DECK.split("\n"), line) == expected


def test_enclosing_span_of_a_multi_line_argument():
    lines = ["\\caption{Cost", "and benefit", "of it}"]
    assert enclosing_span(lines, 3) == (1, 3)


def test_missing_source_leaves_the_error_as_tex_reported_it():
    [err] = locate(parse_tex_errors("./chapters/a.tex:9: Undefined control sequence.\nl.9 \\foo\n"),
                   lambda name: None)
    assert err.line is None and err.as_dict()["line"] == 9


# --- compiler.py ------------------------------------------------------------------------

def test_compile_result_carries_located_errors(monkeypatch):
    def run(cmd, cwd=None, **kw):
        if cmd[0] == "latexmk":  # the latexmk candidate gets the same \errorcontextlines
            assert any(a.startswith("-usepretex=") and "errorcontextlines=20" in a for a in cmd)
            raise FileNotFoundError("latexmk")  # exercise the direct-engine path below
        assert cmd[-1] == compiler._TEX_ENTRY and "-jobname=main" in cmd
        assert kw["env"]["error_line"] == "254"
        (Path(cwd) / "main.pdf").write_bytes(b"%PDF-1.4")
        return types.SimpleNamespace(stdout=LOG, stderr="", returncode=1)

    monkeypatch.setattr(compiler, "_run_tex", run)
    r = compiler.compile_latex(DECK, engine="pdflatex", persist_synctex=False, pre_heal=False)
    assert r["success"] is True
    assert f"./main.tex:{_line_of('Background')}: Misplaced alignment tab character &." in r["errors"]
    assert not any(f":{END_FRAME}:" in e for e in r["errors"])
    assert [d["line"] for d in r["diagnostics"] if d["token"] == "&"] == [
        _line_of("Background"), _line_of("Methods"), _line_of("Q&A")]


def test_recovery_does_not_turn_table_row_breaks_into_paragraph_breaks(monkeypatch):
    doc = ("\\documentclass{article}\n\\begin{document}\n\\begin{center}\nTitle\\\\[1cm]\nAuthor\n\\end{center}\n"
           "\\begin{tabular}{ll}\na & b \\\\[2pt]\nc & d \\\\\n\\end{tabular}\n\\end{document}\n")
    seen = []

    def run(cmd, cwd=None, **kw):
        if cmd[0] == "latexmk":
            raise FileNotFoundError("latexmk")  # direct-engine path only
        seen.append((Path(cwd) / "main.tex").read_text(encoding="utf-8"))
        if len(seen) == 1:  # no PDF, and the log line that triggers the title/spacing recovery
            return types.SimpleNamespace(stdout="./main.tex:8: Argument of \\x has an extra }.\n", stderr="", returncode=1)
        (Path(cwd) / "main.pdf").write_bytes(b"%PDF-1.4")
        return types.SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(compiler, "_run_tex", run)
    compiler.compile_latex(doc, engine="pdflatex", persist_synctex=False, pre_heal=False)
    patched = seen[-1]
    assert "a & b \\\\[2pt]" in patched                      # the table keeps its row break
    assert "Title\\par\\vspace{1cm}" in patched               # the title page is what the patch is for


@needs_tex
def test_real_tex_reports_frame_errors_on_their_true_lines():
    r = compiler.compile_latex(DECK, engine="pdfLaTeX", persist_synctex=False, pre_heal=False)
    by_line = {d["line"]: d for d in r["diagnostics"] if "alignment tab" in d["message"]}
    assert set(by_line) == {_line_of("Background"), _line_of("Methods"), _line_of("Q&A")}
    assert all(d["reported_line"] == END_FRAME for d in by_line.values())
    assert any(d["line"] == _line_of("file_name") and d["token"] == "_" for d in r["diagnostics"])
    assert any(e.startswith(f"./main.tex:{_line_of('Background')}:") for e in r["errors"])


@needs_tex
def test_real_tex_wide_invocation_still_builds_a_clean_document():
    clean = (DECK.replace("& M", r"\& M").replace("Q&A", r"Q\&A")
             .replace("file_name is snake_case", r"file\_name is snake\_case")
             .replace(r"Uses \undefinedmacro here", "Uses nothing here"))
    r = compiler.compile_latex(clean, engine="pdfLaTeX", persist_synctex=False, pre_heal=False)
    assert r["success"] is True and r["errors"] == [] and "diagnostics" not in r
