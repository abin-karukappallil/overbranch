"""
Live compile-pipeline tests for the fontspec-strip and beamer-promotion recoveries.

Both use the real pdflatex/xelatex binaries (per the project's "verify fixes against
real TeX" rule): a prompt-only patch is not enough — we need to see a real PDF come
out of the compile with the expected notice attached. The three fidelity-guarding
tests (test_exact_mode_frozen, test_pdf2latex_fidelity, test_pdf2latex_mode_wiring)
are the companion check that the exact-mode output has not shifted.
"""

import base64
import shutil

import pytest

import compiler


pytestmark = pytest.mark.skipif(
    shutil.which("pdflatex") is None,
    reason="pdflatex not installed on this host",
)


_BUG1_FONTSPEC = r"""\documentclass{article}
\usepackage{fontspec}
\setmainfont{DoesNotExistOnThisServerAtAll}
\begin{document}
This body text should still be visible via Computer Modern fallback. Hello world.
Line two. Line three. Line four. Line five. Line six. Seven eight nine ten.
The quick brown fox jumps over the lazy dog. Pack my box with five dozen liquor jugs.
All work and no play makes Jack a dull boy. We hold these truths to be self evident,
that all men are created equal and endowed with certain unalienable rights.
\end{document}
"""


_BUG2_BEAMER_IN_ARTICLE = r"""\documentclass{article}
\begin{document}
\begin{frame}{Slide One}
\begin{columns}
\column{.49\textwidth}
Hello left side of the slide.
\column{.49\textwidth}
Hello right side of the slide.
\end{columns}
\end{frame}
\end{document}
"""


_CONTROL_PLAIN_ARTICLE = r"""\documentclass{article}
\begin{document}
Just a plain article with ordinary content. No slides, no fontspec.
Nothing should trigger either recovery path.
\end{document}
"""


def _compile(code: str) -> dict:
    return compiler.compile_latex(code, engine="pdfLaTeX", persist_synctex=False)


def test_fontspec_strip_recovery_renders_in_cm():
    """
    A document whose \\setmainfont points at a font that is not installed on the
    server must still compile: step 5 strips the fontspec setup and reruns under
    pdflatex, so the body renders in Computer Modern. The result log carries a
    [FONT NOTICE] so the UI can surface the fallback.
    """
    res = _compile(_BUG1_FONTSPEC)
    assert res.get("success") is True, (res.get("error_log") or "")[:400]

    pdf = base64.b64decode(res["pdf_base64"])
    # Computer Modern body text is a few KB per page; a blank PDF is < ~1 KB after
    # the pagination overhead, so a non-trivial size is proof the body rendered.
    assert len(pdf) > 2000, f"recovery PDF is suspiciously small ({len(pdf)} bytes)"

    # The font preflight swaps a missing family for an installed one (here: by class,
    # serif -> TeX Gyre Termes) before TeX runs; the strip-to-CM recovery is the last
    # resort when no substitute is installed. Either way the user is told.
    log = res.get("log") or ""
    assert ("fontspec strip" in log.lower() or "[FONT NOTICE]" in log
            or "Font substitution: DoesNotExistOnThisServerAtAll" in log), log[:300]


def test_beamer_promotion_recovery_renders_slides():
    """
    A document that uses \\begin{frame}, \\column, etc. inside \\documentclass{article}
    hits "Environment columns undefined" / "\\end{frame} undefined". Step 6 promotes
    the class to beamer and re-runs; the result carries a [CLASS NOTICE] naming the
    prior class so the user knows to patch the source permanently.
    """
    res = _compile(_BUG2_BEAMER_IN_ARTICLE)
    assert res.get("success") is True, (res.get("error_log") or "")[:400]

    pdf = base64.b64decode(res["pdf_base64"])
    assert len(pdf) > 2000, f"recovery PDF is suspiciously small ({len(pdf)} bytes)"

    log = res.get("log") or ""
    assert "beamer class promotion" in log.lower() or "[CLASS NOTICE]" in log, log[:300]
    assert "article" in log, "log should name the prior class"


def test_plain_article_takes_the_normal_path():
    """A clean document must not trigger either recovery and must compile normally."""
    res = _compile(_CONTROL_PLAIN_ARTICLE)
    assert res.get("success") is True

    log = res.get("log") or ""
    assert "fontspec strip" not in log.lower()
    assert "beamer class promotion" not in log.lower()


# --- unit tests for the pure helpers ----------------------------------------


def test_strip_fontspec_setup_removes_package_and_commands():
    code = r"""\documentclass{article}
\usepackage{fontspec}
\usepackage[main=english]{polyglossia}
\setmainfont{Nope}
\setsansfont[Scale=1]{AlsoNope}
\begin{document}X\end{document}"""
    out = compiler._strip_fontspec_setup(code)
    # Each stripped line turns into a comment that preserves the line count:
    # line numbers in a later log stay faithful.
    assert out.count("\n") == code.count("\n")
    assert "AUTO-DISABLED" in out
    assert r"\usepackage{fontspec}" not in out or "% [AUTO-DISABLED" in out.splitlines()[1]
    # setmainfont and setsansfont both removed:
    for marker in (r"\setmainfont{Nope}", r"\setsansfont[Scale=1]{AlsoNope}"):
        # Still appears, but only inside a comment line:
        for line in out.splitlines():
            if marker in line:
                assert line.lstrip().startswith("%"), f"not commented: {line!r}"


def test_strip_fontspec_setup_leaves_regular_code_alone():
    code = r"""\documentclass{article}
\usepackage{amsmath}
\begin{document}Hello.\end{document}"""
    assert compiler._strip_fontspec_setup(code) == code


def test_promote_to_beamer_swaps_class_and_keeps_options():
    code = r"\documentclass[11pt,a4paper]{article}" + "\n" + r"\begin{document}X\end{document}"
    new, prior = compiler._promote_to_beamer(code)
    assert prior == "article"
    assert r"\documentclass[11pt,a4paper]{beamer}" in new
    # Idempotent: a second promotion on the already-beamer code is a no-op.
    assert compiler._promote_to_beamer(new)[1] is None


def test_promote_to_beamer_is_noop_for_beamer_class():
    code = r"\documentclass{beamer}" + "\n" + r"\begin{document}\begin{frame}X\end{frame}\end{document}"
    new, prior = compiler._promote_to_beamer(code)
    assert prior is None
    assert new == code


def test_looks_like_beamer_body_catches_the_usual_suspects():
    for body in (
        r"\begin{frame}{t}X\end{frame}",
        r"\column{.5\textwidth}",
        r"\frametitle{t}",
        r"\begin{columns}\end{columns}",
    ):
        src = r"\documentclass{article}\begin{document}" + body + r"\end{document}"
        assert compiler._looks_like_beamer_body(src), body


def test_looks_like_beamer_body_ignores_commented_markers():
    src = r"""\documentclass{article}
\begin{document}
% \begin{frame}{t}X\end{frame}
Just prose.
\end{document}"""
    assert not compiler._looks_like_beamer_body(src)
