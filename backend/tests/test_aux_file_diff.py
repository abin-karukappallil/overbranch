"""
test_aux_file_diff.py — auxiliary .tex files in the agent's final output.

Two regressions are guarded here:

1. ``get_all_modified_files()`` returns ``{path: (original, modified)}``, but the
   final-emission block used to pass the *tuple* straight through as
   ``modified=``, raising ``AttributeError: 'tuple' object has no attribute
   'splitlines'``. That fired after the main ``final_diff`` but before
   ``result`` — and the editor treats a missing ``result`` as "no changes", so
   the whole run was silently discarded whenever a second file was touched.

2. ``str_replace_file`` had no heal and no validation, and the final gate only
   covers the main buffer, so a structurally broken \\input fragment reached the
   user unchecked.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from opencode.agent_loop import stream_opencode_agent
from opencode.shadow_workspace import ShadowWorkspace

MAIN = (
    "\\documentclass{report}\n"
    "\\begin{document}\n"
    "\\input{chapters/ch1}\n"
    "\\end{document}\n"
)
AUX_PATH = "chapters/ch1.tex"
AUX = "\\chapter{Intro}\nOriginal body text.\n"


DONE_REPLY = {"thought": "Done.", "done": True, "explanation": "Updated chapter."}


def _agent_script(*responses):
    """
    Scripts provider_router.chat with a sequence of JSON tool-call replies,
    then keeps replying `done` so a longer-than-expected loop cannot exhaust the
    side_effect list and mask the behaviour under test.
    """
    queue = list(responses)

    def reply(*_a, **_k):
        payload = queue.pop(0) if queue else DONE_REPLY
        return {
            "content": json.dumps(payload),
            "model_used": "test",
            "finish_reason": "stop",
            "usage": {},
        }

    mock = MagicMock()
    mock.chat.side_effect = reply
    return mock


def test_result_event_still_arrives_when_an_aux_file_is_modified():
    """The tuple-unpacking crash used to suppress the result event entirely."""
    script = _agent_script(
        {
            "thought": "Update the chapter body.",
            "tool_call": {
                "name": "str_replace",
                "arguments": {
                    "file": AUX_PATH,
                    "old_str": "Original body text.",
                    "new_str": "Revised body text.",
                },
            },
        },
        {
            "thought": "Also touch the main file so the run has changes.",
            "tool_call": {
                "name": "str_replace",
                "arguments": {
                    "old_str": "\\input{chapters/ch1}",
                    "new_str": "\\input{chapters/ch1}\n% reviewed",
                },
            },
        },
        {"thought": "Done.", "done": True, "explanation": "Updated chapter."},
    )

    with patch("opencode.agent_loop.provider_router", script):
        events = list(stream_opencode_agent(
            user_instruction="Revise chapter 1 body text",
            project_id="proj-aux-diff",
            current_code=MAIN,
            mode="edit",
            max_steps=6,
            project_files={AUX_PATH: AUX},
        ))

    types = [e.get("type") for e in events]
    assert "result" in types, (
        f"result event missing — aux-file handling swallowed it. Got: {types}"
    )

    # Every final_diff must carry real strings, never a tuple.
    for e in events:
        if e.get("type") == "final_diff":
            assert isinstance(e.get("original_code"), str)
            assert isinstance(e.get("proposed_code"), str)


def test_aux_file_diff_is_emitted_for_its_own_path():
    script = _agent_script(
        {
            "thought": "Edit the chapter.",
            "tool_call": {
                "name": "str_replace",
                "arguments": {
                    "file": AUX_PATH,
                    "old_str": "Original body text.",
                    "new_str": "Revised body text.",
                },
            },
        },
        {
            "thought": "Touch main too.",
            "tool_call": {
                "name": "str_replace",
                "arguments": {
                    "old_str": "\\input{chapters/ch1}",
                    "new_str": "\\input{chapters/ch1}\n% reviewed",
                },
            },
        },
        {"thought": "Done.", "done": True, "explanation": "Updated chapter."},
    )

    with patch("opencode.agent_loop.provider_router", script):
        events = list(stream_opencode_agent(
            user_instruction="Revise chapter 1",
            project_id="proj-aux-diff-2",
            current_code=MAIN,
            mode="edit",
            max_steps=6,
            project_files={AUX_PATH: AUX},
        ))

    aux_diffs = [
        e for e in events
        if e.get("type") == "final_diff" and e.get("file") == AUX_PATH
    ]
    assert aux_diffs, "no final_diff emitted for the modified auxiliary file"
    assert "Revised body text." in aux_diffs[0]["proposed_code"]


def test_str_replace_file_heals_a_closable_environment():
    """An unclosed environment in an aux file is repaired positionally."""
    ws = ShadowWorkspace(MAIN)
    ws.add_auxiliary_file(AUX_PATH, AUX)
    res = ws.str_replace_file(
        AUX_PATH,
        "Original body text.",
        "\\begin{itemize}\n\\item dangling",
    )
    assert res["success"] is True
    assert res.get("auto_repairs"), "the repair must be reported, not applied silently"
    assert "\\end{itemize}" in ws._aux_files[AUX_PATH]


def test_str_replace_file_rejects_unhealable_edit():
    """
    Aux writes now get the same pre-commit gate as the main buffer. Brace
    imbalance is not something auto_heal repairs, so it must be refused.
    """
    ws = ShadowWorkspace(MAIN)
    ws.add_auxiliary_file(AUX_PATH, AUX)
    res = ws.str_replace_file(
        AUX_PATH, "Original body text.", "\\textbf{unclosed"
    )
    assert res["success"] is False
    assert "PRE-COMMIT VALIDATION FAILED" in res["error"]
    # The file must be untouched.
    assert ws._aux_files[AUX_PATH] == AUX


def test_str_replace_file_accepts_valid_edit():
    ws = ShadowWorkspace(MAIN)
    ws.add_auxiliary_file(AUX_PATH, AUX)
    res = ws.str_replace_file(AUX_PATH, "Original body text.", "Revised body text.")
    assert res["success"] is True
    assert "Revised body text." in ws._aux_files[AUX_PATH]
