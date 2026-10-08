"""
The write gate and the healers: new structural errors are not hidden behind old
ones, and the deterministic repairs never corrupt what they touch.
"""

from document_index import ensure_document_environment
from edit_validator import validate_edit
from latex_error_fixer import auto_heal_latex_code, balance_latex_environments, fix_tikz_semicolons
from opencode.shadow_workspace import ShadowWorkspace

B = "\\"


def _doc(*body_lines, preamble=()):
    return "\n".join([B + "documentclass{article}", *preamble, B + "begin{document}", *body_lines,
                      B + "end{document}", ""])


# --- validate_edit: magnitudes, not presence ---------------------------------------------

def test_new_unclosed_brace_is_not_hidden_by_an_old_one():
    before = _doc("Old " + B + "textbf{unclosed text", "Plain line.")
    after = before.replace("Plain line.", "New " + B + "emph{text and " + B + "textit{more")
    ok, errors = validate_edit(before, after)
    assert not ok and any("Unclosed '{'" in e for e in errors)


def test_closing_an_old_brace_is_an_improvement():
    before = _doc("Old " + B + "textbf{unclosed text", "Plain line.")
    after = before.replace("unclosed text", "unclosed text}")
    assert validate_edit(before, after) == (True, [])


def test_balanced_edit_next_to_an_old_imbalance_passes():
    before = _doc("Old " + B + "textbf{unclosed text", "Plain line.")
    after = before.replace("Plain line.", "Plain " + B + "emph{line}.")
    assert validate_edit(before, after) == (True, [])


def test_edit_that_shifts_an_imbalance_inside_itself_is_caught():
    # Two separate hunks: one loses a `{`, the other gains one — the document-wide depth
    # is unchanged, but each hunk is unbalanced on its own.
    before = _doc("Old " + B + "textbf{unclosed text", "A {group} here.", "Unchanged.", "Plain line.")
    after = before.replace("A {group} here.", "A group} here.").replace("Plain line.", "Plain {line.")
    ok, errors = validate_edit(before, after)
    assert not ok


# --- TikZ semicolons ---------------------------------------------------------------------

def test_escaped_percent_is_not_a_comment():
    code = _doc(B + "begin{tikzpicture}", B + "node at (0,0) {Accuracy 97" + B + "%};",
                B + "node at (2,0) {B}", B + "end{tikzpicture}")
    out, _ = fix_tikz_semicolons(code)
    assert "{Accuracy 97" + B + "%};\n" in out
    assert B + "node at (2,0) {B};" in out


def test_semicolon_before_a_comment_keeps_the_newline():
    code = _doc(B + "begin{tikzpicture}", B + "draw (0,0) -- (1,1) % diagonal", B + "end{tikzpicture}")
    out, fixes = fix_tikz_semicolons(code)
    assert B + "draw (0,0) -- (1,1); % diagonal\n" + B + "end{tikzpicture}" in out
    assert fixes


def test_matrix_cells_do_not_get_a_semicolon_after_the_open_brace():
    code = _doc(B + "begin{tikzpicture}", B + "matrix (m) [matrix of nodes] {",
                B + "node {a}; " + B + B, B + "node {b}; " + B + B, "};", B + "end{tikzpicture}")
    out, _ = fix_tikz_semicolons(code)
    assert "{;" not in out
    assert out == code


# --- TikZ package injection ----------------------------------------------------------------

def test_injected_tikz_goes_after_the_documents_xcolor():
    code = _doc(B + "begin{tikzpicture}", B + "draw (0,0) -- (1,1);", B + "end{tikzpicture}",
                preamble=(B + "usepackage[table]{xcolor}",))
    out, _ = auto_heal_latex_code(code)
    assert out.index(B + "usepackage{tikz}") > out.index(B + "usepackage[table]{xcolor}")
    assert out.index(B + "usepackage{tikz}") < out.index(B + "begin{document}")


def test_tikz_mentioned_in_a_comment_is_not_injected():
    code = _doc("% a tikzpicture would go here", "Text.")
    out, _ = auto_heal_latex_code(code)
    assert B + "usepackage{tikz}" not in out


def test_tikz_loaded_in_a_package_list_is_recognised():
    code = _doc(B + "begin{tikzpicture}", B + "draw (0,0) -- (1,1);", B + "end{tikzpicture}",
                preamble=(B + "usepackage{tikz,pgfplots}", B + "usetikzlibrary{calc}"))
    out, _ = auto_heal_latex_code(code)
    assert B + "usepackage{tikz}\n" not in out


# --- \begin/\end{document} and environment balancing ------------------------------------

def test_end_document_mentioned_in_a_trailing_comment_keeps_the_real_one():
    code = _doc("Body.") + "% notes: anything after " + B + "end{document} is ignored\n"
    out = ensure_document_environment(code)
    assert B + "end{document}\n% notes" in out


def test_document_tags_inside_a_listing_are_left_alone():
    code = _doc(B + "begin{lstlisting}", B + "begin{document}", "Hi", B + "end{document}",
                B + "end{lstlisting}", preamble=(B + "usepackage{listings}",))
    assert ensure_document_environment(code) == code


def test_end_of_an_environment_opened_by_a_macro_is_kept():
    code = _doc(B + "twocol", "Left " + B + "column{.5" + B + "textwidth} Right", B + "end{columns}",
                preamble=(B + "newcommand{" + B + "twocol}{" + B + "begin{columns}}",))
    out, _ = balance_latex_environments(code)
    assert B + "end{columns}" in out


# --- locator fuzzy guard & edit hygiene -------------------------------------------------------

def test_fuzzy_match_never_swallows_a_closing_brace():
    # The unclosed \textbf elsewhere is what used to let the swallowed `}` through the
    # (then presence-based) validator; the fuzzy guard must refuse the match regardless.
    code = _doc("Old " + B + "textbf{unclosed text", B + "textcolor{gray}{",
                "  Our approach improves accuracy by 40" + B + "% overall.}", "Next.")
    ws = ShadowWorkspace(code)
    res = ws.str_replace("Our approach improves accuracy by 40% overall.",
                         "Our approach improves accuracy by 45% overall.")
    assert res["success"] is False
    assert ws.get_buffer() == code


def test_line_number_prefixes_copied_from_read_file_range_are_stripped():
    code = _doc("Intro text here.", "Second line.")
    ws = ShadowWorkspace(code)
    res = ws.str_replace("3: Intro text here.\n4: Second line.", "3: Intro words.\n4: Second words.")
    assert res["success"]
    assert "Intro words.\nSecond words." in ws.get_buffer()
    assert "3: " not in ws.get_buffer()


def test_trailing_newline_of_the_replaced_text_is_kept():
    code = _doc("Closing words.", "Next line.")
    ws = ShadowWorkspace(code)
    assert ws.str_replace("Closing words.\n", "Closing remarks. % note")["success"]
    assert "Closing remarks. % note\nNext line." in ws.get_buffer()


def test_server_never_places_a_whole_document_item_over_a_changed_document():
    from opencode.apply_edits import resolve_and_apply
    original = _doc("Hello.")
    item = {"original_chunk": original, "proposed_chunk": original.replace("Hello.", "Hi."),
            "is_full_document": True}
    typed = original.replace("Hello.", "Hello. Typed meanwhile.")
    out = resolve_and_apply(typed, [item], original_code=None)
    assert out["success"] is False and out["document_unchanged"] is True
    assert out["code"] == typed
    ok = resolve_and_apply(original, [item], original_code=None)
    assert ok.get("success") and "Hi." in ok["code"]


def test_heal_repairs_are_reported_to_the_model():
    code = _doc("Intro text here.", preamble=(B + "usepackage{tikz}", B + "usetikzlibrary{calc}"))
    ws = ShadowWorkspace(code)
    res = ws.str_replace("Intro text here.", B + "begin{tikzpicture}\n" + B + "draw (0,0) -- (2,2)\n"
                         + B + "end{tikzpicture}")
    assert res["success"]
    assert res.get("auto_repairs")
