"""
Agent-run outcomes around the compile gate: nothing ships uncompiled, a fix
request is judged on whether the document compiles, partial fixes are kept and
reported honestly, and simple TeX errors are repaired without an LLM round.
"""

import pytest

from conftest import final_buffer, result_event, run_agent

BODY = "\n".join(f"Filler line {i} about the topic." for i in range(30))
DOC = (
    "\\documentclass{article}\n\\begin{document}\n"
    "\\section{Intro}\nIntro text here.\n" + BODY + "\n"
    "\\section{End}\nClosing words.\n\\end{document}\n"
)
FIX_PROMPT = ("Please fix this LaTeX compilation error:\n\n```\n./main.tex:5: Undefined control sequence.\n```\n\n"
              "Please locate the error in the document, inspect the surrounding code, and apply the necessary "
              "in-place fix.")


@pytest.fixture
def rule_compiler(monkeypatch):
    """
    Shadow compile whose errors follow rules: every line containing ``needle``
    reports ``message`` at that line (like TeX would).
    """
    from opencode import shadow_compiler
    state = {"rules": [], "calls": 0}

    def fake_run(workspace, code, engine, timeout_seconds):
        state["calls"] += 1
        errors = []
        for i, line in enumerate(code.splitlines(), start=1):
            for needle, message in state["rules"]:
                if needle in line:
                    errors.append({"error": message, "line": i, "context": "", "type": "LATEX_ERROR",
                                   "suggested_action": "", "file": None})
        return {"result": {"success": not errors, "compile_time_ms": 1}, "log": "", "errors": errors,
                "summary": "\n".join(e["error"] for e in errors), "pdf": None, "overfull": [], "infra": False}

    monkeypatch.setattr(shadow_compiler, "_run_compile", fake_run)
    return state


def _edit(old, new, done=False):
    reply = {"thought": "edit", "tool_call": {"name": "replace_text", "arguments": {"old_str": old, "new_str": new}}}
    if done:
        reply["done"] = True
    return reply


# --- nothing ships uncompiled ---------------------------------------------------------

def test_budget_exhausted_without_done_is_compiled_and_rolled_back(scripted_llm, rule_compiler):
    rule_compiler["rules"] = [("\\badmacro", "Undefined control sequence.")]
    scripted_llm([_edit("Closing words.", "Closing \\badmacro words.")])
    events = run_agent("In the End section, change the closing words", DOC, max_steps=1)
    assert final_buffer(events, DOC) == DOC
    assert result_event(events)["failure"]["document_unchanged"] is True


def test_budget_exhausted_without_done_ships_a_clean_edit_compiled(scripted_llm, rule_compiler):
    scripted_llm([_edit("Closing words.", "Closing remarks.")])
    events = run_agent("In the End section, change the closing words", DOC, max_steps=1)
    assert "Closing remarks." in final_buffer(events, DOC)
    data = result_event(events)
    assert data["trace"]["compile_result"] == "passed"
    assert data["compile_verified"] is True


def test_error_found_on_the_last_step_still_gets_a_repair_turn(scripted_llm, rule_compiler):
    rule_compiler["rules"] = [("\\badmacro", "Undefined control sequence.")]
    scripted_llm([
        _edit("Closing words.", "Closing \\badmacro words.", done=True),
        _edit("Closing \\badmacro words.", "Closing kind words.", done=True),
    ])
    events = run_agent("In the End section, change the closing words", DOC, max_steps=1)
    assert "Closing kind words." in final_buffer(events, DOC)
    assert result_event(events)["trace"]["compile_result"] == "passed"


# --- fix requests ---------------------------------------------------------------------

BROKEN = DOC.replace("Intro text here.", "Intro \\legacybroken text.")


def test_fix_request_that_leaves_the_error_is_not_success(scripted_llm, rule_compiler):
    rule_compiler["rules"] = [("\\legacybroken", "Undefined control sequence.")]
    unrelated = _edit("Closing words.", "Closing remarks.", done=True)
    scripted_llm([unrelated, unrelated, unrelated, unrelated])
    events = run_agent(FIX_PROMPT, BROKEN)
    assert final_buffer(events, BROKEN) == BROKEN
    data = result_event(events)
    assert data["failure"]["document_unchanged"] is True
    assert data["trace"]["compile_result"] == "failed"


def test_fix_request_that_fixes_the_error_passes(scripted_llm, rule_compiler):
    rule_compiler["rules"] = [("\\legacybroken", "Undefined control sequence.")]
    scripted_llm([_edit("Intro \\legacybroken text.", "Intro text.", done=True)])
    events = run_agent(FIX_PROMPT, BROKEN)
    data = result_event(events)
    assert "Intro text." in final_buffer(events, BROKEN)
    assert data["trace"]["compile_result"] == "passed"
    assert "Compiles without errors" in data["explanation"]


def test_partial_fix_is_kept_and_says_what_still_fails(scripted_llm, rule_compiler):
    rule_compiler["rules"] = [("\\legacybroken", "Undefined control sequence.")]
    two = BROKEN.replace("Closing words.", "Closing \\legacybroken words.")
    fix_one = _edit("Intro \\legacybroken text.", "Intro text.", done=True)
    cannot = _edit("Filler line 3 about the topic.", "Filler line three about the topic.", done=True)
    scripted_llm([fix_one, cannot, cannot, cannot])
    events = run_agent(FIX_PROMPT, two)
    buf = final_buffer(events, two)
    assert "Intro text." in buf and "Closing \\legacybroken words." in buf
    data = result_event(events)
    assert data["partial"]["partial"] is True
    assert data["partial"]["document_unchanged"] is False
    assert "Fixed 1 of 2" in data["explanation"]
    assert data["trace"]["compile_result"] == "partial"


# --- deterministic repairs / honest explanation -----------------------------------------

def test_missing_dollar_is_repaired_without_an_llm_round(scripted_llm, rule_compiler):
    rule_compiler["rules"] = [("file_name", "Missing $ inserted.")]
    llm = scripted_llm([_edit("Closing words.", "Closing words about file_name handling.", done=True)])
    # (phrased like the other tests so the scope classifier does not consume a scripted reply)
    events = run_agent("In the End section, change the closing words", DOC)
    buf = final_buffer(events, DOC)
    assert "file\\_name" in buf
    assert result_event(events)["trace"]["compile_result"] == "passed"
    assert len(llm.calls) == 1


def test_explanation_reports_pre_existing_errors_honestly(scripted_llm, rule_compiler):
    rule_compiler["rules"] = [("\\legacybroken", "Undefined control sequence.")]
    scripted_llm([_edit("Closing words.", "Closing remarks.", done=True)])
    events = run_agent("In the End section, change the closing words to closing remarks", BROKEN)
    data = result_event(events)
    assert "Closing remarks." in final_buffer(events, BROKEN)
    assert "1 error(s) that were already in the document remain" in data["explanation"]
    assert data["has_changes"] is True and data["proposed_code"].endswith("\\end{document}\n")
