"""
Agent-run outcomes around the compile gate: nothing ships uncompiled, a fix
request is judged on whether the document compiles, partial fixes are kept and
reported honestly, and simple TeX errors are repaired without an LLM round.
"""

import re

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
    # "pdf": TeX carries on past most errors and still writes a PDF; set it to get that.
    state = {"rules": [], "calls": 0, "pdf": False}

    def fake_run(workspace, code, engine, timeout_seconds):
        state["calls"] += 1
        errors = []
        for i, line in enumerate(code.splitlines(), start=1):
            for needle, message in state["rules"]:
                if needle in line:
                    errors.append({"error": message, "line": i, "context": "", "type": "LATEX_ERROR",
                                   "suggested_action": "", "file": None})
        return {"result": {"success": state["pdf"] or not errors, "compile_time_ms": 1}, "log": "", "errors": errors,
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


def test_compile_failure_returns_errored_code_and_detailed_diagnostics(scripted_llm, rule_compiler):
    rule_compiler["rules"] = [("\\badmacro", "Undefined control sequence.")]
    scripted_llm([
        _edit("Closing words.", "Closing \\badmacro words.", done=True),
        _edit("Closing \\badmacro words.", "Still \\badmacro words.", done=True),
    ])
    events = run_agent("In the End section, change the closing words", DOC, max_steps=2)

    # 1. Document was safely rolled back
    assert final_buffer(events, DOC) == DOC

    # 2. Compile error event contains errored_code and detailed_errors
    compile_err_ev = [ev for ev in events if ev.get("type") == "compile_error"][-1]
    assert compile_err_ev is not None
    assert "errored_code" in compile_err_ev
    assert "\\badmacro" in compile_err_ev["errored_code"]
    assert "detailed_errors" in compile_err_ev
    assert len(compile_err_ev["detailed_errors"]) > 0
    de = compile_err_ev["detailed_errors"][0]
    assert de["error"] == "Undefined control sequence."
    assert de["line"] is not None
    assert "\\badmacro" in de["source"]

    # 3. Result event data contains errored_code, detailed_errors, and failure payload
    res = result_event(events)
    assert res["failure"]["document_unchanged"] is True
    assert res["errored_code"] == compile_err_ev["errored_code"]
    assert "\\badmacro" in res["errored_code"]
    assert res["detailed_errors"] == compile_err_ev["detailed_errors"]
    assert res["failure"]["errored_code"] == compile_err_ev["errored_code"]
    assert res["failure"]["detailed_errors"] == compile_err_ev["detailed_errors"]

    # 4. Agent explanation details how it errored and includes the candidate code
    explanation = res["explanation"]
    assert "### How It Errored (Diagnostics):" in explanation
    assert f"Line {de['line']}" in explanation
    assert "Undefined control sequence." in explanation
    assert "\\badmacro" in explanation
    assert "### Candidate LaTeX Code That Failed Compilation:" in explanation
    assert "```latex" in explanation



# --- misplaced & : prevented, located, repaired — never left to guesswork -------------------

DECK = "\n".join([
    "\\documentclass{beamer}", "\\usepackage{tikz,booktabs}", "\\usetikzlibrary{calc}",
    "\\usetikzlibrary{positioning,arrows.meta}", "\\begin{document}",
    "\\begin{frame}[plain]", "  \\begin{tikzpicture}",
    "    \\node[anchor=west] at (0,0) {Architecture & Efficiency};", "  \\end{tikzpicture}", "\\end{frame}",
    "\\begin{frame}{Outline}{Scope & Plan}", "  \\begin{itemize}", "    \\item Background & Motivation",
    "    \\item Methods & Materials", "    \\item Results & Discussion", "    \\item Q&A", "  \\end{itemize}",
    "\\end{frame}",
    "\\begin{frame}{Numbers}", "  \\begin{tabular}{ll}", "    \\toprule", "    Model & Score \\\\",
    "    \\bottomrule", "  \\end{tabular}", "\\end{frame}", "\\end{document}", "",
])
CREATE = "Create a beamer presentation about efficient transformers"


@pytest.fixture
def beamer_compiler(monkeypatch):
    """
    Shadow compile that reports like TeX does on a Beamer deck: one error per bare
    `&` outside a tabular, every one of them at the closing line of its frame —
    never on the line the `&` is on. A PDF is still produced.
    """
    from opencode import shadow_compiler
    state = {"calls": 0, "seen": []}

    def fake_run(workspace, code, engine, timeout_seconds):
        state["calls"] += 1
        lines = code.splitlines()
        frame_end, opened = {}, None
        for i, line in enumerate(lines, start=1):
            if "\\begin{frame}" in line:
                opened = i
            if "\\end{frame}" in line and opened:
                frame_end.update({k: i for k in range(opened, i + 1)})
                opened = None
        errors, in_table = [], False
        for i, line in enumerate(lines, start=1):
            in_table = (in_table or "\\begin{tabular}" in line) and "\\end{tabular}" not in line
            if in_table:
                continue
            for _ in re.findall(r"(?<!\\)&", line):
                at = frame_end.get(i, i)
                errors.append({"error": "Misplaced alignment tab character &.", "line": at, "reported_line": at,
                               "context": "", "type": "ALIGNMENT_TAB_ERROR", "suggested_action": "", "file": None})
        state["seen"].append(len(errors))
        return {"result": {"success": True, "compile_time_ms": 1}, "log": "", "errors": errors,
                "summary": "\n".join(e["error"] for e in errors), "pdf": None, "overfull": [], "infra": False}

    monkeypatch.setattr(shadow_compiler, "_run_compile", fake_run)
    return state


def _agent(scripted_llm, replies):
    """Scripted agent replies; the scope classifier's own LLM call does not consume one."""
    queue = list(replies)

    def respond(messages):
        if "scope classifier" in str(messages[0].get("content", "")):
            return {"scope": "TARGETED_EDIT", "confidence": 0.9, "reason": "test"}
        return queue.pop(0) if queue else {"thought": "done", "done": True, "explanation": "Finished."}

    llm = scripted_llm([respond] * 16)
    llm.agent_calls = lambda: [c for c in llm.calls if "scope classifier" not in str(c[0].get("content", ""))]
    return llm


def test_new_deck_with_bare_ampersands_is_delivered_without_a_repair_round(scripted_llm, beamer_compiler):
    llm = _agent(scripted_llm, [_edit("", DECK, done=True)])
    events = run_agent(CREATE, "")
    buf = final_buffer(events, "")
    data = result_event(events)
    assert data["trace"]["compile_result"] == "passed" and data["trace"]["retry_count"] == 0
    assert "Background \\& Motivation" in buf and "Q\\&A" in buf and "{Scope \\& Plan}" in buf
    assert "{Architecture \\& Efficiency}" in buf and "Model & Score \\\\" in buf
    assert len(llm.agent_calls()) == 1 and beamer_compiler["seen"][-1] == 0
    assert "Compiles without errors" in data["explanation"]


def test_gate_repairs_ampersands_tex_reported_at_end_frame(scripted_llm, beamer_compiler, monkeypatch):
    """With the write-time pass out of the way, the compile gate must still get there on its own."""
    import latex_specials
    monkeypatch.setattr(latex_specials, "escape_misplaced_ampersands", lambda code, *a, **k: (code, []))
    llm = _agent(scripted_llm, [_edit("", DECK, done=True)])
    events = run_agent(CREATE, "")
    buf = final_buffer(events, "")
    data = result_event(events)
    assert beamer_compiler["seen"][0] == 6            # every & reported, all at \end{frame} lines
    assert data["trace"]["compile_result"] == "passed" and data["trace"]["retry_count"] == 0
    assert "Background \\& Motivation" in buf and "Q\\&A" in buf and "Model & Score \\\\" in buf
    assert len(llm.agent_calls()) == 1                # no LLM repair round was needed


def test_an_explicit_compile_call_gets_the_same_repairs(scripted_llm, beamer_compiler, monkeypatch):
    import latex_specials
    monkeypatch.setattr(latex_specials, "escape_misplaced_ampersands", lambda code, *a, **k: (code, []))
    compile_call = {"thought": "check", "tool_call": {"name": "compile_latex", "arguments": {}}}
    llm = _agent(scripted_llm, [_edit("", DECK), compile_call])
    events = run_agent(CREATE, "")
    results = [ev["result"] for ev in events if ev.get("type") == "tool_result" and ev.get("tool") == "compile_latex"]
    assert results and results[0]["success"] is True and results[0]["auto_repairs"]
    assert "failing_errors" not in results[0]
    assert result_event(events)["trace"]["compile_result"] == "passed"
    assert not any("COMPILATION FAILED" in str(m.get("content", "")) for call in llm.agent_calls() for m in call)


def test_an_edit_leaves_a_pre_existing_bare_ampersand_alone(scripted_llm, beamer_compiler):
    doc = DOC.replace("Intro text here.", "Tom & Jerry text here.")
    _agent(scripted_llm, [_edit("Closing words.", "Closing remarks.", done=True)])
    events = run_agent("In the End section, change the closing words", doc)
    buf = final_buffer(events, doc)
    assert "Tom & Jerry text here." in buf and "Closing remarks." in buf
    assert "1 error(s) that were already in the document remain" in result_event(events)["explanation"]


def test_fix_request_for_an_ampersand_needs_no_llm_round(scripted_llm, beamer_compiler):
    doc = DOC.replace("Intro text here.", "Tom & Jerry text here.")
    line = doc.splitlines().index("Tom & Jerry text here.") + 1
    llm = _agent(scripted_llm, [])
    events = run_agent(f"Please fix this LaTeX compilation error:\n\n```\n./main.tex:{line}: Misplaced alignment "
                       f"tab character &.\n```", doc)
    data = result_event(events)
    assert "Tom \\& Jerry text here." in final_buffer(events, doc)
    assert data["trace"]["compile_result"] == "passed" and llm.agent_calls() == []
    assert "Fixed the compile error(s) automatically" in data["explanation"]
    assert "Compiles without errors" in data["explanation"]


def test_feedback_to_the_model_names_the_true_line(scripted_llm, beamer_compiler, monkeypatch):
    """When an LLM round is needed after all, it is told where the & is — not where the frame ends."""
    import latex_error_fixer
    import latex_specials
    monkeypatch.setattr(latex_specials, "escape_misplaced_ampersands", lambda code, *a, **k: (code, []))
    monkeypatch.setattr(latex_error_fixer, "_repair_alignment_errors", lambda code, errors, allowed: (code, []))
    fix = {"thought": "fix", "done": True, "tool_calls": [
        {"name": "replace_text", "arguments": {"old_str": old, "new_str": old.replace("&", "\\&")}}
        for old in ("{Architecture & Efficiency}", "{Scope & Plan}", "Background & Motivation",
                    "Methods & Materials", "Results & Discussion", "\\item Q&A")]}
    llm = _agent(scripted_llm, [_edit("", DECK, done=True), fix])
    events = run_agent(CREATE, "")
    assert result_event(events)["trace"]["compile_result"] == "passed"
    feedback = next(str(m["content"]) for call in llm.agent_calls() for m in call
                    if "COMPILATION FAILED" in str(m.get("content", "")))
    assert "Background & Motivation" in feedback and "{Architecture & Efficiency}" in feedback
    assert "Lines 11-18" in feedback and "offending token is somewhere inside it" in feedback


# --- a new document that still builds is kept as a draft ----------------------------------------

NEW_DOC = ("\\documentclass{article}\n\\begin{document}\n\\section{Intro}\nSome \\badmacro text.\n"
           "\\end{document}\n")


def test_new_document_with_a_surviving_error_is_kept_as_a_draft(scripted_llm, rule_compiler):
    rule_compiler["rules"] = [("\\badmacro", "Undefined control sequence.")]
    rule_compiler["pdf"] = True
    _agent(scripted_llm, [_edit("", NEW_DOC, done=True)])
    events = run_agent("Create a short article about testing", "")
    data = result_event(events)
    assert final_buffer(events, "") == NEW_DOC
    assert not data.get("failure")
    assert data["partial"]["draft"] is True and data["partial"]["document_unchanged"] is False
    assert data["has_changes"] is True
    assert "Created the document, but 1 LaTeX error remains" in data["explanation"]
    assert "Undefined control sequence." in data["explanation"]
    assert data["trace"]["compile_result"] == "draft"


def test_new_document_that_produces_no_pdf_is_still_rolled_back(scripted_llm, rule_compiler):
    rule_compiler["rules"] = [("\\badmacro", "Undefined control sequence.")]
    _agent(scripted_llm, [_edit("", NEW_DOC, done=True)])
    events = run_agent("Create a short article about testing", "")
    data = result_event(events)
    assert final_buffer(events, "") == ""
    assert data["failure"]["document_unchanged"] is True and data["trace"]["compile_result"] == "failed"


def test_an_edit_to_a_document_with_content_is_never_kept_as_a_draft(scripted_llm, rule_compiler):
    rule_compiler["rules"] = [("\\badmacro", "Undefined control sequence.")]
    rule_compiler["pdf"] = True
    _agent(scripted_llm, [_edit("Closing words.", "Closing \\badmacro words.", done=True)])
    events = run_agent("In the End section, change the closing words", DOC, max_steps=1)
    assert final_buffer(events, DOC) == DOC
    assert result_event(events)["failure"]["document_unchanged"] is True
