"""
tests/test_latex_error_fixer.py
================================
Unit tests for LaTeX error parsing, deterministic auto-healing, and surgical repair guidance.
"""

import pytest
from latex_error_fixer import (
    parse_compilation_errors,
    auto_heal_latex_code,
    balance_latex_environments,
    format_compilation_fix_prompt,
    ParsedLatexError,
)
from opencode.shadow_workspace import ShadowWorkspace


def test_parse_compilation_errors():
    """Verify error parser extracts lines and types accurately from LaTeX logs."""
    sample_log = """./main.tex:66: LaTeX Error: Bad math environment delimiter.
./main.tex:66: LaTeX Error: Bad math environment delimiter.
./main.tex:66: Package tikz Error: Giving up on this path. Did you forget a sem
./main.tex:66: LaTeX Error: \\begin{tikzpicture} on input line 66 ended by \\end{frame}.
./main.tex:241: LaTeX Error: \\begin{frame} on input line 160 ended by \\end{document}.
! Emergency stop.
!  ==> Fatal error occurred, no output PDF file produced!"""

    errors = parse_compilation_errors(sample_log)
    assert len(errors) >= 3

    lines = [e.line_number for e in errors if e.line_number is not None]
    assert 66 in lines
    assert 160 in lines

    # Verify unclosed environment detection
    unclosed_lines = [e.line_number for e in errors if e.error_type == "UNCLOSED_ENVIRONMENT"]
    assert 66 in unclosed_lines
    assert 160 in unclosed_lines

    # Verify bad math delimiter detection
    bad_math = next((e for e in errors if e.error_type == "BAD_MATH_DELIMITER"), None)
    assert bad_math is not None
    assert bad_math.line_number == 66
    assert "calc" in bad_math.suggested_action


def test_balance_latex_environments_unclosed_frame():
    """Verify unclosed \\begin{frame} is closed before \\end{document} or next frame."""
    code = r"""\documentclass{beamer}
\begin{document}
\begin{frame}{Slide 1}
Hello slide 1
\end{frame}
\begin{frame}{Slide 2}
Unclosed slide 2
\end{document}"""

    healed, repairs = balance_latex_environments(code)
    assert len(repairs) >= 1
    assert r"\end{frame}" in healed
    assert healed.count(r"\begin{frame}") == healed.count(r"\end{frame}")
    # \end{frame} must precede \end{document}
    assert healed.find(r"\end{frame}") < healed.rfind(r"\end{document}")


def test_balance_latex_environments_inner_unclosed_env():
    """Verify unclosed inner environments (itemize, tikzpicture) inside a frame are closed properly."""
    code = r"""\documentclass{beamer}
\begin{document}
\begin{frame}{Slide 1}
\begin{itemize}
\item Item 1
\end{frame}
\end{document}"""

    healed, repairs = balance_latex_environments(code)
    assert r"\end{itemize}" in healed
    assert healed.find(r"\end{itemize}") < healed.find(r"\end{frame}")


def test_auto_heal_injects_tikz_calc_library():
    """Verify \\usetikzlibrary{calc} is injected when TikZ coordinate arithmetic is used."""
    code = r"""\documentclass{beamer}
\usepackage{tikz}
\begin{document}
\begin{frame}{Slide 1}
\begin{tikzpicture}
\fill[navy] (current page.north west) rectangle ($(current page.north west)+(2,2)$);
\end{tikzpicture}
\end{frame}
\end{document}"""

    healed, fixes = auto_heal_latex_code(code)
    assert r"\usetikzlibrary{calc}" in healed
    assert any("calc" in f for f in fixes)


def test_auto_heal_injects_missing_semicolon_in_tikz():
    """Verify missing semicolon on TikZ path statement is auto-fixed."""
    code = r"""\documentclass{beamer}
\usepackage{tikz}
\usetikzlibrary{calc}
\begin{document}
\begin{frame}{Slide 1}
\begin{tikzpicture}
\fill[navy] (0,0) rectangle (2,2)
\end{tikzpicture}
\end{frame}
\end{document}"""

    healed, fixes = auto_heal_latex_code(code)
    assert r"\fill[navy] (0,0) rectangle (2,2);" in healed
    assert any("semicolon" in f for f in fixes)


def test_auto_heal_injects_missing_color_definitions():
    """Verify missing standard colors (navy, gold, cream) are injected into preamble."""
    code = r"""\documentclass{beamer}
\setbeamercolor{background canvas}{bg=cream}
\setbeamercolor{frametitle}{fg=navy}
\begin{document}
\begin{frame}{Slide 1}
Hello
\end{frame}
\end{document}"""

    healed, fixes = auto_heal_latex_code(code)
    assert r"\definecolor{navy}" in healed
    assert r"\definecolor{cream}" in healed
    assert any("color" in f for f in fixes)


def test_format_compilation_fix_prompt():
    """Verify prompt formatting generates clear, line-targeted surgical mandate."""
    ws = ShadowWorkspace(original_code=r"""\documentclass{beamer}
\begin{document}
\begin{frame}{Title}
Hello
\end{frame}
\end{document}""")

    errors = [
        ParsedLatexError(
            line_number=3,
            error_type="UNCLOSED_ENVIRONMENT",
            message=r"\begin{frame} ended by \end{document}",
            suggested_action=r"Insert \end{frame} before \end{document}.",
        )
    ]

    prompt = format_compilation_fix_prompt("Raw error log", errors, ws, ["Fixed unclosed frame"])
    assert "COMPILATION ERROR SURGICAL REPAIR MANDATE (ASK AI TO FIX)" in prompt
    assert "Line 3" in prompt
    assert "MANDATORY VERIFICATION" in prompt
    assert "verify_compile" in prompt


def test_heal_lonely_items_wraps_in_itemize():
    """Verify lonely \\item outside a list environment is safely wrapped in \\begin{itemize}."""
    code = r"""\documentclass{beamer}
\begin{document}
\begin{frame}{Key Points}
\item First point
\item Second point with details
\end{frame}
\end{document}"""

    healed, fixes = auto_heal_latex_code(code)
    assert r"\begin{itemize}" in healed
    assert r"\item First point" in healed
    assert r"\item Second point with details" in healed
    assert r"\end{itemize}" in healed
    assert any("lonely" in f.lower() for f in fixes)


def test_fix_tikz_semicolons_preserves_multiline_paths():
    """Verify that multi-line TikZ path statements are not broken with premature semicolons."""
    code = r"""\documentclass{beamer}
\usepackage{tikz}
\begin{document}
\begin{frame}{Architecture}
\begin{tikzpicture}
\draw[thick, fill=blue!10] (0,0)
    -- (2,2)
    node[midway] {Label};
\node (A) at (1,1) {$x+y$};
\node (B) at (3,3) {Missing semicolon}
\end{tikzpicture}
\end{frame}
\end{document}"""

    healed, fixes = auto_heal_latex_code(code)
    # Ensure line 1 was NOT broken with premature semicolon
    assert r"\draw[thick, fill=blue!10] (0,0);" not in healed
    # Ensure line 2 ends cleanly with semicolon
    assert r"node[midway] {Label};" in healed
    # Ensure missing semicolon on node B was added
    assert r"\node (B) at (3,3) {Missing semicolon};" in healed


def test_workspace_str_replace_auto_heals_buffer():
    """Verify ShadowWorkspace.str_replace automatically runs auto_heal on the modified buffer."""
    ws = ShadowWorkspace(
        original_code=r"""\documentclass{beamer}
\begin{document}
\begin{frame}{Initial Slide}
Content
\end{frame}
\end{document}""",
        file_path="main.tex",
    )

    # Insert a lonely item and an unclosed frame via str_replace
    bad_edit = r"""\begin{frame}{Initial Slide}
Content
\item New lonely item
\end{frame}
\begin{frame}{Unclosed Slide}
Unclosed content"""

    ws.str_replace(r"\begin{frame}{Initial Slide}" + "\nContent\n" + r"\end{frame}", bad_edit)
    buf = ws.get_buffer()

    # Verify lonely item was wrapped in itemize
    assert r"\begin{itemize}" in buf
    assert r"\item New lonely item" in buf
    assert r"\end{itemize}" in buf

    # Verify unclosed frame was closed before end document
    assert buf.count(r"\begin{frame}") == buf.count(r"\end{frame}")
    assert buf.rfind(r"\end{frame}") < buf.rfind(r"\end{document}")

