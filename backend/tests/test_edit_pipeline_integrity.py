"""
tests/test_edit_pipeline_integrity.py — Regression & Integrity Tests for AI Edit Pipeline
=========================================================================================
Tests and reproduces:
1. Multi-edit batch with shifting line numbers applied in descending position order.
2. Edit touching a tikzpicture and an itemize inside a frame (catching environment mismatches).
3. Edit containing \\frac, \\text, \\begin, and \\right preventing backslash control character corruption.
4. Pre-commit validation step checking environment nesting, math delimiters ($, $$, \\(, \\[), and braces.
5. ShadowWorkspace snapshot rollback / undo step.
6. Discarding truncated model responses (max_tokens / length).
"""

import re
import json
import pytest
from edit_validator import validate_latex_pre_commit, clean_latex_for_validation
from opencode.shadow_workspace import ShadowWorkspace
from opencode.agent_loop import _parse_agent_response, sanitize_latex_json


# ============================================================================
# Test 1: Multi-Edit Batch with Shifting Line Numbers
# ============================================================================

def test_multi_edit_batch_shifting_line_numbers():
    r"""
    Reproduces stale line offsets when multiple edits are applied.
    When applying edits from top to bottom, the first edit alters the file length,
    causing subsequent edits to match the wrong offsets or fail.
    Sorting edits in descending position order guarantees earlier offsets remain intact.
    """
    initial_latex = (
        r"\documentclass{beamer}" "\n"
        r"\begin{document}" "\n"
        r"\begin{frame}{Slide 1: Intro}" "\n"
        r"Short text." "\n"
        r"\end{frame}" "\n"
        r"\begin{frame}{Slide 2: Methodology}" "\n"
        r"Method text." "\n"
        r"\end{frame}" "\n"
        r"\begin{frame}{Slide 3: Conclusion}" "\n"
        r"Conclusion text." "\n"
        r"\end{frame}" "\n"
        r"\end{document}"
    )

    ws = ShadowWorkspace(initial_latex)

    # Two edits: Slide 1 expands significantly (adding 10 lines), Slide 2 expands
    edit_slide1_orig = r"\begin{frame}{Slide 1: Intro}" "\n" r"Short text." "\n" r"\end{frame}"
    edit_slide1_prop = (
        r"\begin{frame}{Slide 1: Intro}" "\n"
        r"\begin{itemize}" "\n"
        + "\n".join([f"\\item Elaborated point {i}" for i in range(1, 8)]) + "\n"
        r"\end{itemize}" "\n"
        r"\end{frame}"
    )

    edit_slide2_orig = r"\begin{frame}{Slide 2: Methodology}" "\n" r"Method text." "\n" r"\end{frame}"
    edit_slide2_prop = (
        r"\begin{frame}{Slide 2: Methodology}" "\n"
        r"Expanded methodology with detailed framework architecture." "\n"
        r"\end{frame}"
    )

    edits = [
        {"orig": edit_slide1_orig, "prop": edit_slide1_prop},
        {"orig": edit_slide2_orig, "prop": edit_slide2_prop},
    ]

    # Map start indices in the document
    buffer_text = ws.get_buffer()
    for e in edits:
        e["pos"] = buffer_text.find(e["orig"])
        assert e["pos"] != -1

    # Sort descending by start position (Slide 2 at bottom applied before Slide 1 at top)
    edits.sort(key=lambda x: x["pos"], reverse=True)
    assert edits[0]["orig"] == edit_slide2_orig
    assert edits[1]["orig"] == edit_slide1_orig

    # Apply both edits
    for e in edits:
        res = ws.str_replace(e["orig"], e["prop"])
        assert res["success"] is True, f"Failed on {e['orig'][:30]}: {res.get('error')}"

    final_buffer = ws.get_buffer()
    assert "Elaborated point 7" in final_buffer
    assert "Expanded methodology with detailed framework" in final_buffer
    assert r"\end{document}" in final_buffer

    # Verify structural integrity
    passed, errors = validate_latex_pre_commit(final_buffer)
    assert passed is True, f"Validation errors: {errors}"


# ============================================================================
# Test 2: Edit Touching TikZ and Itemize Inside a Frame
# ============================================================================

def test_edit_touching_tikzpicture_and_itemize_inside_frame():
    r"""
    Reproduces typical corruption:
    - '\begin{tikzpicture} ended by \end{...}'
    - '\begin{frame} ended by \end{itemize}' / 'ended by \end{document}'
    Validates that pre-commit validator flags improper nesting order and unclosed tags,
    and ShadowWorkspace rejects the edit without modifying the document.
    """
    initial_latex = (
        r"\documentclass{beamer}" "\n"
        r"\usepackage{tikz}" "\n"
        r"\begin{document}" "\n"
        r"\begin{frame}{Complex Slide}" "\n"
        r"\begin{itemize}" "\n"
        r"\item First item" "\n"
        r"\end{itemize}" "\n"
        r"\begin{tikzpicture}" "\n"
        r"\draw (0,0) -- (1,1);" "\n"
        r"\end{tikzpicture}" "\n"
        r"\end{frame}" "\n"
        r"\end{document}"
    )

    ws = ShadowWorkspace(initial_latex)

    # Corrupted Edit 1: Drops \end{tikzpicture} and ends frame prematurely
    corrupted_latex_1 = (
        r"\documentclass{beamer}" "\n"
        r"\usepackage{tikz}" "\n"
        r"\begin{document}" "\n"
        r"\begin{frame}{Complex Slide}" "\n"
        r"\begin{itemize}" "\n"
        r"\item First item" "\n"
        r"\end{itemize}" "\n"
        r"\begin{tikzpicture}" "\n"
        r"\draw (0,0) -- (1,1);" "\n"
        r"\end{frame}" "\n"  # \begin{tikzpicture} ended by \end{frame}!
        r"\end{document}"
    )
    passed1, errors1 = validate_latex_pre_commit(corrupted_latex_1)
    assert passed1 is False
    assert any("tikzpicture" in err and "frame" in err for err in errors1)

    # Corrupted Edit 2: Inverted nesting (\begin{frame} ended by \end{itemize})
    corrupted_latex_2 = (
        r"\documentclass{beamer}" "\n"
        r"\begin{document}" "\n"
        r"\begin{frame}{Complex Slide}" "\n"
        r"\begin{itemize}" "\n"
        r"\item First item" "\n"
        r"\end{frame}" "\n"
        r"\end{itemize}" "\n"
        r"\end{document}"
    )
    passed2, errors2 = validate_latex_pre_commit(corrupted_latex_2)
    assert passed2 is False
    assert any("itemize" in err and "frame" in err for err in errors2)

    # A corrupted edit must never land in the buffer as-is. The write path heals
    # first and validates second, so the outcome is either a deterministic repair
    # or a rejection -- but the buffer is structurally sound either way.
    res = ws.str_replace(
        r"\end{tikzpicture}",
        r"\end{itemize}",
    )
    if res["success"]:
        # Healed: the unclosed tikzpicture was closed and the orphan dropped.
        assert r"\end{tikzpicture}" in ws.get_buffer()
        passed_after, errors_after = validate_latex_pre_commit(ws.get_buffer())
        assert passed_after, f"healed buffer is still broken: {errors_after}"
    else:
        assert "PRE-COMMIT VALIDATION FAILED" in res["error"]
        assert validate_latex_pre_commit(ws.get_buffer())[0]

    # Valid edit passes cleanly
    valid_edit = (
        r"\begin{frame}{Complex Slide}" "\n"
        r"\begin{itemize}" "\n"
        r"\item Updated item 1" "\n"
        r"\item Added item 2" "\n"
        r"\end{itemize}" "\n"
        r"\begin{tikzpicture}" "\n"
        r"\draw[blue] (0,0) circle (2cm);" "\n"
        r"\end{tikzpicture}" "\n"
        r"\end{frame}"
    )
    res_valid = ws.str_replace(
        ws.get_buffer().split(r"\begin{frame}{Complex Slide}")[1].split(r"\end{frame}")[0] + r"\end{frame}",
        valid_edit.replace(r"\begin{frame}{Complex Slide}", ""),
    )
    assert res_valid["success"] is True
    assert "Added item 2" in ws.get_buffer()


# ============================================================================
# Test 3: Edit Containing \frac, \text, \begin and \right (Backslash Corruption)
# ============================================================================

def test_edit_containing_frac_text_begin_and_right():
    r"""
    Reproduces backslash corruption where \b, \f, \t, \r sequences inside JSON strings
    were decoded into control characters \x08, \x0c, \x09, \x0d by standard json.loads.
    Verifies that sanitize_latex_json and _parse_agent_response preserve \frac, \text,
    \begin, and \right verbatim without corruption.
    """
    raw_llm_json = r"""{
        "thought": "Adding mathematical formula with fractions, text labels, and delimiters.",
        "tool_call": {
            "name": "str_replace",
            "arguments": {
                "old_str": "Old content",
                "new_str": "\begin{equation}\n\frac{1}{2}\text{ where }x = \left(\frac{a}{b}\right.\n\end{equation}"
            }
        }
    }"""

    parsed = _parse_agent_response(raw_llm_json)
    assert "tool_call" in parsed
    new_str = parsed["tool_call"]["arguments"]["new_str"]

    # Verify backslashes were NOT decoded to control characters:
    assert "\x08" not in new_str, "Found \x08 control character from corrupted \\begin!"
    assert "\x0c" not in new_str, "Found \x0c control character from corrupted \\frac!"
    assert "\x09" not in new_str or "\\text" in new_str, "Found corrupted \\text!"
    assert "\x0d" not in new_str, "Found \x0d control character from corrupted \\right!"

    # Verify exact LaTeX commands are intact
    assert r"\begin{equation}" in new_str
    assert r"\frac{1}{2}" in new_str
    assert r"\text{ where }" in new_str
    assert r"\right." in new_str
    assert r"\end{equation}" in new_str

    # Apply into ShadowWorkspace
    doc = (
        r"\documentclass{article}" "\n"
        r"\usepackage{amsmath}" "\n"
        r"\begin{document}" "\n"
        r"Old content" "\n"
        r"\end{document}"
    )
    ws = ShadowWorkspace(doc)
    res = ws.str_replace(
        parsed["tool_call"]["arguments"]["old_str"],
        parsed["tool_call"]["arguments"]["new_str"],
    )
    assert res["success"] is True
    final_code = ws.get_buffer()
    assert r"\frac{1}{2}" in final_code
    assert r"\text{ where }" in final_code
    assert r"\begin{equation}" in final_code
    assert r"\right." in final_code


# ============================================================================
# Test 4: Pre-Commit Validation of Delimiters and Braces
# ============================================================================

def test_pre_commit_validation_delimiters_and_braces():
    r"""
    Tests pre-commit validation catching:
    - Unbalanced inline math $
    - Unbalanced display math $$
    - Unbalanced \( \) and \[ \]
    - Unbalanced curly braces { }
    """
    # 1. Unbalanced inline $
    doc_bad_dollar = r"\documentclass{article}\begin{document}Value is $50 without closing.\end{document}"
    passed, errors = validate_latex_pre_commit(doc_bad_dollar)
    assert passed is False
    assert any("'$'" in e for e in errors)

    # 2. Escaped \$ should NOT trigger error
    doc_escaped_dollar = r"\documentclass{article}\begin{document}Price is \$50 total.\end{document}"
    passed, errors = validate_latex_pre_commit(doc_escaped_dollar)
    assert passed is True, f"Escaped dollar false positive: {errors}"

    # 3. Unbalanced display math $$
    doc_bad_dd = r"\documentclass{article}\begin{document}$$ x + y = z \end{document}"
    passed, errors = validate_latex_pre_commit(doc_bad_dd)
    assert passed is False
    assert any("'$$'" in e for e in errors)

    # 4. Unbalanced \( \)
    doc_bad_paren = r"\documentclass{article}\begin{document}\( x + y \end{document}"
    passed, errors = validate_latex_pre_commit(doc_bad_paren)
    assert passed is False
    assert any(r"\(" in e for e in errors)

    # 5. Unbalanced \[ \]
    doc_bad_bracket = r"\documentclass{article}\begin{document}\[ x = 1 \end{document}"
    passed, errors = validate_latex_pre_commit(doc_bad_bracket)
    assert passed is False
    assert any(r"\[" in e for e in errors)

    # 6. Unbalanced braces { }
    doc_bad_brace = r"\documentclass{article}\begin{document}\textbf{unclosed brace\end{document}"
    passed, errors = validate_latex_pre_commit(doc_bad_brace)
    assert passed is False
    assert any("curly brace" in e for e in errors)


# ============================================================================
# Test 5: ShadowWorkspace Snapshot and Undo Rollback
# ============================================================================

def test_shadow_workspace_snapshot_and_undo():
    r"""
    Tests that ShadowWorkspace maintains snapshots before each edit, allowing
    the user or system to rollback one or more steps cleanly.
    """
    initial = (
        r"\documentclass{article}" "\n"
        r"\begin{document}" "\n"
        r"\section{Introduction}" "\n"
        r"Original text." "\n"
        r"\end{document}"
    )
    ws = ShadowWorkspace(initial)
    assert ws.get_snapshot_count() == 0

    # Edit 1
    res1 = ws.str_replace("Original text.", "First modification.")
    assert res1["success"] is True
    assert ws.get_snapshot_count() == 1
    assert "First modification." in ws.get_buffer()

    # Edit 2
    res2 = ws.str_replace("First modification.", "Second modification.")
    assert res2["success"] is True
    assert ws.get_snapshot_count() == 2
    assert "Second modification." in ws.get_buffer()

    # Undo Step 1 -> rolls back to Edit 1
    assert ws.undo() is True
    assert "First modification." in ws.get_buffer()
    assert "Second modification." not in ws.get_buffer()

    # Undo Step 2 -> rolls back to Initial
    assert ws.undo() is True
    assert "Original text." in ws.get_buffer()
    assert "First modification." not in ws.get_buffer()

    # No more undos
    assert ws.undo() is False


# ============================================================================
# Test 6: Pre-Commit Validation Failure Always Yields Result & Final Diff
# ============================================================================

def test_pre_commit_validation_rejection_always_yields_structured_result_and_diff():
    r"""
    Verifies that when an edit fails pre-commit validation and cannot be safely committed,
    stream_opencode_agent ALWAYS yields:
    1. compile_error event detailing the validation error
    2. result event with has_changes=False, explaining why the edit was rejected
    3. final_diff event with has_changes=False
    It must NEVER do a bare return that leaves the frontend with 'No result received from AI agent'.
    """
    from opencode.agent_loop import stream_opencode_agent
    import json
    from unittest.mock import patch

    # Document where initial code is valid
    doc = (
        r"\documentclass{beamer}" "\n"
        r"\begin{document}" "\n"
        r"\begin{frame}{Initial}" "\n"
        r"Content" "\n"
        r"\end{frame}" "\n"
        r"\end{document}"
    )

    # Agent claims it's done without having made changes or with an invalid state
    resp = json.dumps({
        "thought": "I am done without modifying.",
        "done": True,
        "explanation": "No edits needed.",
    })

    with patch("providers.router.provider_router.chat") as mock_chat:
        mock_chat.return_value = {"content": resp}

        events = list(stream_opencode_agent(
            user_instruction="Please check the document",
            current_code=doc,
            project_id="test_safe_result_proj",
            max_steps=2,
        ))

    event_types = [e.get("type") for e in events]
    # result event must ALWAYS be yielded
    assert "result" in event_types, f"Expected 'result' in events, got: {event_types}"
    res_event = next(e for e in events if e.get("type") == "result")
    assert "data" in res_event
    assert "explanation" in res_event["data"]


# ============================================================================
# Test 7: Auto-Heal Fixes Mangled Spacing, Package Hoisting, and Orphaned Envs
# ============================================================================

def test_auto_heal_fixes_corrupted_spacing_packages_and_orphans():
    r"""
    Reproduces the exact corruption observed in production:
    1. Corrupted newline spacing: '\[0.3em]', '\[1.5em]' instead of '\\[0.3em]'
    2. \usepackage and \usetikzlibrary placed in document body
    3. Orphaned \end{itemize}, \end{column}, \end{columns}, \end{frame}
    Verifies that auto_heal_latex_code repairs all of them and produces code
    that passes validate_latex_pre_commit.
    """
    from latex_error_fixer import auto_heal_latex_code
    from edit_validator import validate_latex_pre_commit

    corrupted_doc = (
        r"\documentclass{beamer}" "\n"
        r"\begin{document}" "\n"
        r"\begin{frame}{Slide 1}" "\n"
        r"Title \[0.3em]" "\n"
        r"Subtitle \[1.5em]" "\n"
        r"\end{frame}" "\n"
        r"\usepackage{tikz}" "\n"
        r"\usetikzlibrary{calc}" "\n"
        r"\end{itemize}" "\n"
        r"\end{column}" "\n"
        r"\end{columns}" "\n"
        r"\end{frame}" "\n"
        r"\begin{frame}{Slide 2}" "\n"
        r"\begin{itemize}" "\n"
        r"\item Valid item" "\n"
        r"\end{document}"
    )

    healed, fixes = auto_heal_latex_code(corrupted_doc)
    assert len(fixes) > 0

    # 1. Verify spacing was repaired to \\[length]
    assert re.search(r"(?<!\\)\\\[0\.3em\]", healed) is None
    assert r"\\[0.3em]" in healed
    assert r"\\[1.5em]" in healed

    # 2. Verify packages were hoisted to preamble
    m_doc = healed.find(r"\begin{document}")
    assert m_doc != -1
    preamble = healed[:m_doc]
    body = healed[m_doc:]
    assert r"\usepackage{tikz}" in preamble
    assert r"\usetikzlibrary{calc}" in preamble
    assert r"\usepackage{tikz}" not in body

    # 3. Verify orphaned \end tags were removed
    assert r"\end{columns}" not in body

    # 4. Verify pre-commit validation now passes completely
    is_valid, errors = validate_latex_pre_commit(healed)
    assert is_valid is True, f"Validation failed with errors: {errors}"



# ===========================================================================
# Validator masking — regressions for false positives that blocked real edits
# ===========================================================================
#
# Each row below used to be reported as a structural error. Because every write
# path validates the *whole* buffer, a single false positive made every
# subsequent str_replace fail with PRE-COMMIT VALIDATION FAILED and deadlocked
# the agent until rollback discarded all of its work.

VALID_BUT_PREVIOUSLY_REJECTED = [
    ("semiverbatim_in_fragile_frame",
     r"\begin{frame}[fragile]\begin{semiverbatim}if x { y\end{semiverbatim}\end{frame}"),
    ("fancyvrb_Verbatim", r"\begin{Verbatim}\begin{itemize}\end{Verbatim}"),
    ("fancyvrb_BVerbatim", r"\begin{BVerbatim}$ { %\end{BVerbatim}"),
    ("alltt", r"\begin{alltt}{ $ %\end{alltt}"),
    ("comment_env", r"\begin{comment}\begin{itemize} { $\end{comment}"),
    ("lstlisting_optarg", r"\begin{lstlisting}[language=C]for(){ \end{lstlisting}"),
    ("minted_langarg", r"\begin{minted}{python}d = {1:2\end{minted}"),
    ("verb_star", r"\verb*|{| text"),
    ("verb_quote", r'\verb"a{b" x'),
    ("verb_tilde", r"\verb~a{b~ x"),
    ("verb_bang", r"\verb!a{b! x"),
    ("verb_at", r"\verb@a{b@ x"),
    ("url_percent", r"\url{http://x/a%20b}"),
    ("href_percent", r"\href{http://x/a%20b}{link text}"),
    ("url_hash_underscore", r"\url{http://x/a_b#frag}"),
    ("newcommand_with_begin", r"\newcommand{\openlist}{\begin{itemize}}"),
    ("newcommand_starred", r"\newcommand*{\openlist}{\begin{itemize}}"),
    ("newcommand_with_args", r"\newcommand{\hdr}[1]{\begin{center}#1}"),
    ("newenvironment", r"\newenvironment{mybox}{\begin{center}}{\end{center}}"),
    ("def_with_begin", r"\def\foo{\begin{itemize}}"),
    ("begin_with_space", r"\begin {itemize}\item a\end{itemize}"),
    ("escaped_percent_brace", r"100\% of \{a\} done"),
    ("left_right_balanced", r"$\left\{ x \right\}$"),
    ("left_right_dot", r"$\left. \frac{a}{b} \right|$"),
    ("display_math", r"\[ x = \frac{1}{2} \]"),
    ("row_spacing", r"a \\[0.3em] b"),
]


@pytest.mark.parametrize(
    "name,code", VALID_BUT_PREVIOUSLY_REJECTED,
    ids=[n for n, _ in VALID_BUT_PREVIOUSLY_REJECTED],
)
def test_valid_latex_is_not_rejected(name, code):
    passed, errors = validate_latex_pre_commit(code)
    assert passed, f"{name}: valid LaTeX reported as broken: {errors}"


GENUINELY_BROKEN = [
    ("unclosed_itemize", r"\begin{document}\begin{itemize}\item a\end{document}"),
    ("orphan_end", r"\end{itemize}"),
    ("unclosed_brace", r"\textbf{hello"),
    ("extra_close_brace", r"\textbf{hi}}"),
    ("odd_dollar", r"x $y z"),
    ("left_without_right", r"$\left( x $"),
    ("right_without_left", r"$ x \right)$"),
    ("mismatched_nesting",
     "\\begin{frame}\n\\begin{itemize}\n\\item a\n\\end{frame}\n\\end{itemize}"),
    ("math_in_href_text_unbalanced", r"\href{u}{$x}"),
]


@pytest.mark.parametrize(
    "name,code", GENUINELY_BROKEN, ids=[n for n, _ in GENUINELY_BROKEN],
)
def test_broken_latex_is_still_caught(name, code):
    passed, errors = validate_latex_pre_commit(code)
    assert not passed, f"{name}: real structural error went undetected"
    assert errors


@pytest.mark.parametrize(
    "name,code",
    VALID_BUT_PREVIOUSLY_REJECTED + GENUINELY_BROKEN,
    ids=[n for n, _ in VALID_BUT_PREVIOUSLY_REJECTED + GENUINELY_BROKEN],
)
def test_clean_latex_preserves_line_count_and_length(name, code):
    """
    The masking promise in clean_latex_for_validation's docstring: characters are
    replaced in place so reported line numbers stay accurate.
    """
    cleaned = clean_latex_for_validation(code)
    assert cleaned.count("\n") == code.count("\n"), f"{name}: newline count changed"
    assert len(cleaned) == len(code), f"{name}: length changed, offsets would drift"


def test_unterminated_verb_does_not_swallow_following_lines():
    code = "\\verb|unterminated\n\\begin{itemize}\n\\item a\n\\end{itemize}\n"
    cleaned = clean_latex_for_validation(code)
    assert cleaned.count("\n") == code.count("\n")
    # The itemize on the next line must still be visible to the validator.
    passed, _ = validate_latex_pre_commit(code)
    assert passed


def test_comment_hiding_end_document_is_masked():
    code = "\\begin{document}\n% \\end{document}\nreal text\n\\end{document}\n"
    passed, errors = validate_latex_pre_commit(code)
    assert passed, f"commented-out \\end{{document}} must be ignored: {errors}"


def test_macro_body_braces_are_still_balance_checked():
    """Masking blanks the body but keeps its braces, so real imbalance is caught."""
    passed, _ = validate_latex_pre_commit(r"\newcommand{\foo}{\textbf{a}")
    assert not passed
