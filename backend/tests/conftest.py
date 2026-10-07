"""
Shared fixtures: a scripted LLM in place of provider_router.chat, and a stub
compiler for the agent's shadow compile (so tests need neither network nor TeX
unless they ask for it).
"""

import json
import os
import sys
from typing import Any, Callable, Dict, List, Optional, Union

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


class ScriptedLLM:
    """
    Replies from a list, in order. Each reply is a dict (sent as JSON), a
    string, or a callable(messages) -> dict|str. Records every request.
    """

    def __init__(self, replies: List[Union[Dict[str, Any], str, Callable]]):
        self.replies = list(replies)
        self.calls: List[List[Dict[str, Any]]] = []

    def __call__(self, messages, model=None, temperature=0.1, max_tokens=4096, api_keys=None,
                 cancel_token=None, observer=None, **_):
        self.calls.append([dict(m) for m in messages])
        if not self.replies:
            reply: Any = {"thought": "done", "done": True, "explanation": "Finished."}
        else:
            reply = self.replies.pop(0)
        if callable(reply):
            reply = reply(messages)
        if isinstance(reply, Exception):
            raise reply
        content = reply if isinstance(reply, str) else json.dumps(reply)
        resp = {"content": content, "model_used": "stub", "finish_reason": "stop",
                "usage": {"prompt_tokens": sum(len(str(m.get("content", ""))) for m in messages) // 4,
                          "completion_tokens": len(content) // 4},
                "provider": "stub", "key_id": None, "is_fallback": False}
        if observer:
            observer({"provider": "stub", "model": "stub", "ok": True, "latency_ms": 1.0})
        return resp

    @property
    def prompt_chars(self) -> List[int]:
        return [sum(len(str(m.get("content", ""))) for m in call) for call in self.calls]


@pytest.fixture
def scripted_llm(monkeypatch):
    def make(replies):
        llm = ScriptedLLM(replies)
        from providers.router import provider_router
        monkeypatch.setattr(provider_router, "chat", llm)
        return llm
    return make


@pytest.fixture
def stub_compiler(monkeypatch):
    """
    Replaces the shadow compile. ``state["fail_if"]`` is a predicate on the
    buffer: when it returns True the compile reports a new error.
    """
    from opencode import shadow_compiler

    state: Dict[str, Any] = {"fail_if": None, "calls": 0, "infra": False}

    def fake_run(workspace, code, engine, timeout_seconds):
        state["calls"] += 1
        failing = bool(state["fail_if"] and state["fail_if"](code))
        errors = ([{"error": "Undefined control sequence \\badmacro", "line": 3, "context": "",
                    "type": "LATEX_ERROR", "suggested_action": ""}] if failing else [])
        return {"result": {"success": not failing, "compile_time_ms": 1}, "log": "", "errors": errors,
                "summary": "", "pdf": None, "overfull": [], "infra": state["infra"]}

    monkeypatch.setattr(shadow_compiler, "_run_compile", fake_run)
    return state


def run_agent(instruction: str, code: str, **kw) -> List[Dict[str, Any]]:
    from opencode.agent_loop import stream_opencode_agent
    return list(stream_opencode_agent(user_instruction=instruction, project_id="test-project",
                                      current_code=code, **kw))


def final_buffer(events: List[Dict[str, Any]], original: str) -> str:
    for ev in reversed(events):
        if ev.get("type") == "final_diff" and ev.get("file", "main.tex") == "main.tex":
            return ev["proposed_code"]
    return original


def result_event(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    return next(ev["data"] for ev in reversed(events) if ev.get("type") == "result")
