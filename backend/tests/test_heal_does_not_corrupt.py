"""
Regressions for the healer writing syntax errors into the user's document.

``auto_heal_latex_code`` runs on the whole buffer on **every** agent write. It
used to scan raw text while ``validate_latex_pre_commit`` scanned a masked view,
so the two disagreed about what the document contains. The healer then
"repaired" structure that was never there, and the damage compounded:

* the user got broken LaTeX, and
* the corrupted buffer failed validation on the *next* write, so every
  subsequent edit was rejected and the agent burned its whole step budget
  before the final rollback discarded the run.

Each case below is taken from a real document in ``backend/templates/``.
"""

from __future__ import annotations

import glob
import os

import pytest

from edit_validator import (
    clean_latex_for_validation,
    validate_edit,
    validate_latex_pre_commit,
)
from latex_error_fixer import auto_heal_latex_code

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")


# ---------------------------------------------------------------------------
# The healer must not invent structure out of non-structure
# ---------------------------------------------------------------------------

MUST_NOT_CHANGE = [
    (
        "begin_in_trailing_comment",
        # A \begin mentioned in a comment is not an open environment. The healer
        # used to append \end{itemize} before \end{document}, which then made
        # every later write fail validation against the corrupted buffer.
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "Hello.  % use \\begin{itemize} here later\n"
        "World.\n"
        "\\end{document}\n",
    ),
    (
        "begin_and_end_inside_one_brace_group",
        # letters/letter3: \date{...\begin{flushleft}\today\end{flushleft}}.
        # Ends were processed before begins, so the \end looked orphaned, was
        # deleted, and a replacement was emitted before \end{document} --
        # silently wrapping the rest of the document in a flushleft group.
        "\\documentclass{letter}\n"
        "\\date{\\vspace{1.5cm}\\begin{flushleft}\\today\\end{flushleft}}\n"
        "\\begin{document}\n"
        "Body text.\n"
        "\\end{document}\n",
    ),
    (
        "item_in_class_defined_list_env",
        # resume/63abeea...: moderncv-style rSubsection takes \item directly.
        # Wrapping those items in \begin{itemize} re-renders the whole section.
        "\\documentclass{resume}\n"
        "\\begin{document}\n"
        "\\begin{rSection}{Experience}\n"
        "\\begin{rSubsection}{ACME}{2010}{Dev}{Palo Alto}\n"
        "\\item Built things\n"
        "\\item Shipped things\n"
        "\\end{rSubsection}\n"
        "\\end{rSection}\n"
        "\\end{document}\n",
    ),
    (
        "env_tags_inside_newenvironment_body",
        # resume/63b8103a.../structure.tex: \newenvironment{x}{\begin{list}...}{\end{list}}
        # is balanced template text, not live structure.
        "\\documentclass{article}\n"
        "\\newenvironment{indentsection}\n"
        "{\\begin{list}{}{\\setlength{\\leftmargin}{1em}}}{\\end{list}}\n"
        "\\begin{document}\n"
        "\\begin{indentsection}\\item[] text\\end{indentsection}\n"
        "\\end{document}\n",
    ),
    (
        "item_and_begin_inside_verbatim",
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "\\begin{verbatim}\n"
        "\\begin{itemize}\n"
        "\\item not a real item\n"
        "\\end{verbatim}\n"
        "\\end{document}\n",
    ),
    (
        "begin_inside_lstlisting",
        "\\documentclass{article}\n"
        "\\usepackage{listings}\n"
        "\\begin{document}\n"
        "\\begin{lstlisting}[language=TeX]\n"
        "\\begin{itemize}\n"
        "\\item one\n"
        "\\end{lstlisting}\n"
        "Done.\n"
        "\\end{document}\n",
    ),
    (
        "palette_word_used_only_as_prose",
        # "the gold standard" is not a colour reference. Injecting a Regalia
        # palette for it rewrote preambles that never asked for one.
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "This remains the gold standard for ink-based navy research.\n"
        "\\end{document}\n",
    ),
]


@pytest.mark.parametrize("name,code", MUST_NOT_CHANGE, ids=[n for n, _ in MUST_NOT_CHANGE])
def test_healer_leaves_valid_document_untouched(name, code):
    assert validate_latex_pre_commit(code)[0], "fixture itself must be valid"
    healed, fixes = auto_heal_latex_code(code)
    assert healed == code, f"{name}: healer rewrote valid LaTeX: {fixes}"
    assert fixes == []


# ---------------------------------------------------------------------------
# The healer must still repair what it is there to repair
# ---------------------------------------------------------------------------

MUST_REPAIR = [
    (
        "unclosed_frame",
        "\\documentclass{beamer}\n\\begin{document}\n"
        "\\begin{frame}{One}\nText\n"
        "\\begin{frame}{Two}\nMore\n\\end{frame}\n\\end{document}\n",
    ),
    (
        "lonely_item_in_frame",
        "\\documentclass{beamer}\n\\begin{document}\n"
        "\\begin{frame}{Key Points}\n\\item First\n\\item Second\n"
        "\\end{frame}\n\\end{document}\n",
    ),
    (
        "unclosed_itemize_before_end_document",
        "\\documentclass{article}\n\\begin{document}\n"
        "\\begin{itemize}\n\\item a\n\\end{document}\n",
    ),
]


@pytest.mark.parametrize("name,code", MUST_REPAIR, ids=[n for n, _ in MUST_REPAIR])
def test_healer_still_repairs_real_breakage(name, code):
    healed, fixes = auto_heal_latex_code(code)
    assert fixes, f"{name}: healer did nothing"
    ok, errors = validate_latex_pre_commit(healed)
    assert ok, f"{name}: still broken after healing: {errors}"


def test_healer_never_increases_the_error_count():
    r"""
    The outermost guarantee: healing is applied speculatively and discarded if
    it makes the document worse. Without it, one bad repair corrupts the buffer
    and every later write fails validation against the corruption.
    """
    # A pre-existing defect the healer's grammar cannot safely repair.
    code = (
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "\\textbf{unclosed\n"
        "\\end{document}\n"
    )
    _, before = validate_latex_pre_commit(code)
    healed, _ = auto_heal_latex_code(code)
    _, after = validate_latex_pre_commit(healed)
    assert len(after) <= len(before)


# ---------------------------------------------------------------------------
# Every bundled template survives a heal
# ---------------------------------------------------------------------------

TEMPLATE_FILES = sorted(glob.glob(os.path.join(TEMPLATE_DIR, "**", "*.tex"), recursive=True))


@pytest.mark.parametrize(
    "path", TEMPLATE_FILES,
    ids=[os.path.relpath(p, TEMPLATE_DIR) for p in TEMPLATE_FILES],
)
def test_bundled_template_is_valid_and_survives_healing(path):
    """
    Every shipped template must pass validation *and* come out of the healer no
    worse. These are the documents users start from, so a false positive here
    blocks every edit to a brand new project.
    """
    code = open(path, encoding="utf-8", errors="replace").read()

    ok_before, errors_before = validate_latex_pre_commit(code)
    assert ok_before, f"shipped template reported as broken: {errors_before[:3]}"

    healed, _ = auto_heal_latex_code(code)
    ok_after, errors_after = validate_latex_pre_commit(healed)
    assert ok_after, f"healer broke a valid template: {errors_after[:3]}"


# ---------------------------------------------------------------------------
# Masking: comments and verbatim decide what each other mean
# ---------------------------------------------------------------------------

def test_commented_out_listing_does_not_leave_a_live_end_tag():
    r"""
    assignments/Modern Lab Report Assignment ships a commented-out usage
    example. Masking verbatim before comments let the body it "opened" swallow
    the % that disabled its own \end{lstlisting}, leaving a live orphan tag --
    so the whole template validated as broken and every edit to it failed.
    """
    code = (
        "\\documentclass{article}\n"
        "\\usepackage{listings}\n"
        "% Usage:\n"
        "%   \\begin{lstlisting}[language=Python]\n"
        "%   print('hi')\n"
        "%   \\end{lstlisting}\n"
        "\\begin{document}\n"
        "\\begin{lstlisting}[language=Python]\n"
        "print('real')\n"
        "\\end{lstlisting}\n"
        "\\end{document}\n"
    )
    ok, errors = validate_latex_pre_commit(code)
    assert ok, errors


def test_percent_inside_verbatim_is_not_a_comment():
    """The converse: a % inside a verbatim body is literal text."""
    code = "\\begin{verbatim}$ { %\\end{verbatim}"
    ok, errors = validate_latex_pre_commit(code)
    assert ok, errors


def test_percent_inside_url_is_not_a_comment():
    ok, errors = validate_latex_pre_commit(r"\href{http://x/a%20b}{link text}")
    assert ok, errors


@pytest.mark.parametrize(
    "code",
    [
        "\\begin{verbatim}$ { %\\end{verbatim}",
        r"\href{http://x/a%20b}{link}",
        "% \\begin{itemize}\n\\textbf{x}\n",
        "\\begin{minted}{python}\nx = '%'\n\\end{minted}\n",
        r"\verb|$ { %|",
    ],
)
def test_masking_preserves_length_and_line_count(code):
    """
    Offsets in the masked view are mapped straight back onto the original by
    both the validator (line numbers) and the healer (structure decisions), so
    the view must be character-for-character aligned with its input.
    """
    view = clean_latex_for_validation(code)
    assert len(view) == len(code)
    assert view.count("\n") == code.count("\n")


# ---------------------------------------------------------------------------
# Differential validation
# ---------------------------------------------------------------------------

def test_pre_existing_defect_does_not_block_an_unrelated_edit():
    r"""
    Every write validates the whole buffer. Holding each edit to an absolute
    standard let one defect the validator cannot model reject *every* edit for
    the rest of the run -- the agent retried until its step budget ran out and
    the final rollback discarded everything.
    """
    before = (
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "\\begin{customlist}\n"   # closed by a macro the validator cannot see
        "Intro paragraph.\n"
        "\\end{document}\n"
    )
    assert not validate_latex_pre_commit(before)[0], "fixture must be 'invalid'"

    after = before.replace("Intro paragraph.", "Rewritten intro paragraph.")
    ok, new_errors = validate_edit(before, after)
    assert ok, f"unrelated edit blocked by a pre-existing defect: {new_errors}"


def test_newly_introduced_defect_is_still_blocked():
    before = "\\documentclass{article}\n\\begin{document}\nText.\n\\end{document}\n"
    after = before.replace("Text.", "\\begin{itemize}\n\\item a\n")
    ok, new_errors = validate_edit(before, after)
    assert not ok
    assert any("itemize" in e for e in new_errors), new_errors


def test_defect_moving_to_another_line_is_not_counted_as_new():
    before = "\\documentclass{article}\n\\begin{document}\n\\begin{itemize}\n\\item a\n\\end{document}\n"
    after = before.replace("\\begin{document}\n", "\\begin{document}\n\nPadding.\n\n")
    ok, _ = validate_edit(before, after)
    assert ok
