"""
Transactional edits (E, Q): an edit set that does not compile is rolled back as
a whole; repairs never touch lines the edit did not change; duplicate blocks
and structurally broken edits are refused; provider failure leaves the
document unchanged.
"""

from conftest import final_buffer, result_event, run_agent

from opencode.shadow_workspace import ShadowWorkspace
from providers.base_provider import LLMProviderError

BODY = "\n".join(f"Filler line {i} about the topic." for i in range(30))
DOC = (
    "\\documentclass{article}\n\\usepackage{tikz}\n\\begin{document}\n"
    "\\section{Intro}\nIntro text here.\n" + BODY + "\n"
    "\\section{Figure}\n\\begin{tikzpicture}\n\\draw (0,0) -- (1,1)\n\\end{tikzpicture}\n"
    "\\section{End}\nClosing words.\n\\end{document}\n"
)


# --- Q. no unrelated changes ------------------------------------------------------

def test_edit_does_not_repair_untouched_defects_elsewhere():
    ws = ShadowWorkspace(DOC)
    res = ws.str_replace("Closing words.", "Final closing words.")
    assert res["success"]
    buf = ws.get_buffer()
    # The pre-existing missing TikZ semicolon is not "fixed" as a side effect.
    assert "\\draw (0,0) -- (1,1)\n" in buf
    changed = [(a, b) for a, b in zip(DOC.splitlines(), buf.splitlines()) if a != b]
    assert changed == [("Closing words.", "Final closing words.")]


def test_heal_still_repairs_the_edited_lines():
    ws = ShadowWorkspace(DOC)
    res = ws.str_replace("Intro text here.", "\\begin{tikzpicture}\n\\draw (0,0) -- (2,2)\n\\end{tikzpicture}")
    assert res["success"]
    buf = ws.get_buffer()
    assert "\\draw (0,0) -- (2,2);" in buf          # the new code was healed
    assert "\\draw (0,0) -- (1,1)\n" in buf          # the old code was not


def test_structurally_broken_edit_is_refused():
    ws = ShadowWorkspace(DOC)
    before = ws.get_buffer()
    res = ws.replace_block("sec:end", "\\section{End}\nAn {unbalanced group and $x = 1\n")
    assert res["success"] is False and res["document_unchanged"]
    assert ws.get_buffer() == before


def test_duplicate_block_is_refused():
    frame = ("\\begin{frame}{Results}\nAccuracy improved by four points across all benchmarks we ran, "
             "including the two largest ones.\n\\end{frame}")
    doc = "\\documentclass{beamer}\n\\begin{document}\n" + frame + "\n\\end{document}\n"
    ws = ShadowWorkspace(doc)
    res = ws.insert_block("frame:results", frame, "after")
    assert res["success"] is False
    assert "Duplicate block" in res["validation_errors"][0]


def test_transaction_rollback_restores_everything():
    ws = ShadowWorkspace(DOC)
    tx = ws.begin_transaction()
    assert ws.str_replace("Intro text here.", "Changed.")["success"]
    assert ws.insert_block("sec:end", "\\section{Extra}\nMore.", "after")["success"]
    ws.rollback_transaction(tx)
    assert ws.get_buffer() == DOC
    assert not ws.get_touched_chunks()


def test_rollback_edit_tool_undoes_last_edit():
    from opencode.tools import execute_tool
    ws = ShadowWorkspace(DOC)
    ws.str_replace("Intro text here.", "One.")
    ws.str_replace("Closing words.", "Two.")
    out = execute_tool("rollback_edit", {}, ws)
    assert out["success"]
    assert "One." in ws.get_buffer() and "Closing words." in ws.get_buffer()


# --- E. rollback after failed compile ----------------------------------------------

def test_agent_rolls_back_when_edit_never_compiles(scripted_llm, stub_compiler):
    stub_compiler["fail_if"] = lambda code: "\\badmacro" in code
    bad_edit = {"thought": "edit", "tool_call": {"name": "replace_text", "arguments": {
        "old_str": "Closing words.", "new_str": "Closing \\badmacro words."}}, "done": True}
    still_bad = {"thought": "fix", "tool_call": {"name": "replace_text", "arguments": {
        "old_str": "Closing \\badmacro words.", "new_str": "Closing \\badmacro{} words."}}, "done": True}
    llm = scripted_llm([bad_edit, still_bad, still_bad, still_bad])
    events = run_agent("In the End section, change the closing words", DOC)

    assert final_buffer(events, DOC) == DOC
    data = result_event(events)
    assert data["failure"]["document_unchanged"] is True
    assert data["failure"]["message"].startswith("Couldn't safely apply this change")
    assert data["trace"]["compile_result"] == "failed"
    assert data["trace"]["retry_count"] == 2          # bounded: SHADOW_COMPILE_MAX_RETRIES
    assert any(e.get("type") == "phase" and e["phase"] == "failed" for e in events)
    assert len(llm.calls) <= 4


def test_agent_repairs_compile_error_then_commits(scripted_llm, stub_compiler):
    stub_compiler["fail_if"] = lambda code: "\\badmacro" in code
    scripted_llm([
        {"thought": "edit", "tool_call": {"name": "replace_text", "arguments": {
            "old_str": "Closing words.", "new_str": "Closing \\badmacro words."}}, "done": True},
        {"thought": "fix", "tool_call": {"name": "replace_text", "arguments": {
            "old_str": "Closing \\badmacro words.", "new_str": "Closing kind words."}}, "done": True},
    ])
    events = run_agent("In the End section, change the closing words", DOC)
    buf = final_buffer(events, DOC)
    assert "Closing kind words." in buf
    assert result_event(events)["trace"]["compile_result"] == "passed"


def test_compile_errors_already_in_the_original_do_not_block(scripted_llm, stub_compiler):
    stub_compiler["fail_if"] = lambda code: "\\legacybroken" in code
    doc = DOC.replace("Intro text here.", "Intro \\legacybroken text.")
    scripted_llm([{"thought": "edit", "tool_call": {"name": "replace_text", "arguments": {
        "old_str": "Closing words.", "new_str": "Closing remarks."}}, "done": True}])
    events = run_agent("In the End section, change the closing words to closing remarks", doc)
    assert "Closing remarks." in final_buffer(events, doc)


# --- provider failure ----------------------------------------------------------------

def test_provider_failure_leaves_document_unchanged(scripted_llm, stub_compiler):
    scripted_llm([
        {"thought": "edit", "tool_call": {"name": "replace_text", "arguments": {
            "old_str": "Intro text here.", "new_str": "Partial."}}},
        LLMProviderError("HTTP 429: rate limited", status_code=429, provider="Gemini"),
    ])
    events = run_agent("Rewrite the intro sentence and then the closing sentence", DOC)
    assert final_buffer(events, DOC) == DOC
    failure = result_event(events)["failure"]
    assert failure["document_unchanged"] and "rate-limited" in failure["message"]
