"""
tests/test_compile_flush_and_busy.py — /api/compile: collab flush, busy vs broken
================================================================================
Plan 01, slice 06 (decision M9, and the 429 contract M8 relies on).

* Before compiling, the endpoint flushes the project's live collab room, so the
  sibling files copied from uploads/projects/<id>/ (``\\input`` chapters, .bib)
  are the ones the user just typed rather than the last debounced save. The
  flush is best-effort: missing room, disabled collab, an exception or a hang
  never stops the compile.
* A busy server answers HTTP 429 ``{detail, retry_after_seconds}`` — both when
  the queue depth cap is hit and when the slot wait expires — while a document
  that does not compile answers HTTP 200 ``{success: false, error_log}``. The
  frontend tells "busy, retry" from "broken, show the log" by exactly this.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import shutil
import sys
import time

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# main.py loads the repo's .env with override=True on import. Keep that from
# leaking into every other test in the session.
_env_before = dict(os.environ)
import main  # noqa: E402

os.environ.clear()
os.environ.update(_env_before)

import compile_queue as compile_queue_module  # noqa: E402
from auth import get_current_user_or_guest  # noqa: E402
from collab import room_manager  # noqa: E402
from compile_queue import CompileQueue  # noqa: E402
from compiler import compile_latex  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PROJECT = "proj-flush-test"


# ── Stubs ────────────────────────────────────────────────────────────────────

class StubRoom:
    def __init__(self, behaviour: str = "ok", delay: float = 0.0) -> None:
        self.behaviour = behaviour
        self.delay = delay
        self.flush_calls = 0
        self.flush_completed = False

    async def flush(self, force: bool = False) -> int:
        self.flush_calls += 1
        if self.behaviour == "raise":
            raise RuntimeError("disk on fire")
        if self.delay:
            await asyncio.sleep(self.delay)
        self.flush_completed = True
        return 1


class RecordingQueue:
    """Stands in for compile_queue: records what was submitted, compiles nothing."""

    def __init__(self, events: list | None = None) -> None:
        self.calls: list[dict] = []
        self.events = events if events is not None else []

    async def submit(self, func, *args, **kwargs):
        self.events.append("submit")
        self.calls.append(kwargs)
        return {"success": True, "pdf_base64": "", "log": "stub"}


@pytest.fixture
def collab_on(monkeypatch):
    monkeypatch.setenv("COLLAB_ENABLED", "1")


@pytest.fixture
def queue(monkeypatch):
    q = RecordingQueue()
    monkeypatch.setattr(main, "compile_queue", q)
    return q


def _install_room(monkeypatch, room) -> None:
    rooms = {PROJECT: room} if room is not None else {}
    monkeypatch.setattr(room_manager, "get", lambda pid: rooms.get(pid))


def _request(project_id: str = PROJECT) -> main.CompileRequest:
    return main.CompileRequest(
        latex_code="\\documentclass{article}\\begin{document}x\\end{document}",
        project_id=project_id,
        engine="pdflatex",
    )


async def _call(req: main.CompileRequest):
    # No user_id in auth_info: the ownership check (Supabase) is skipped.
    return await main.compile_endpoint(req, request=None, auth_info={})


@pytest.fixture
def client():
    main.app.dependency_overrides[get_current_user_or_guest] = lambda: {}
    try:
        yield TestClient(main.app)
    finally:
        main.app.dependency_overrides.pop(get_current_user_or_guest, None)


# ── Flush before compile ─────────────────────────────────────────────────────

async def test_endpoint_flushes_the_projects_room_before_submitting(monkeypatch, collab_on):
    events: list = []
    q = RecordingQueue(events)
    monkeypatch.setattr(main, "compile_queue", q)

    room = StubRoom()
    orig_flush = room.flush

    async def flush_and_note(force: bool = False):
        events.append("flush")
        return await orig_flush(force)

    room.flush = flush_and_note
    _install_room(monkeypatch, room)

    await _call(_request())

    assert room.flush_calls == 1
    assert events == ["flush", "submit"], "the room must be flushed before the compile is queued"
    assert q.calls[0]["project_id"] == PROJECT


async def test_flush_that_raises_does_not_prevent_the_compile(monkeypatch, collab_on, queue, caplog):
    room = StubRoom("raise")
    _install_room(monkeypatch, room)

    with caplog.at_level(logging.WARNING, logger="main"):
        result = await _call(_request())

    assert room.flush_calls == 1
    assert len(queue.calls) == 1
    assert result["success"] is True
    assert any("flush" in r.getMessage() and r.levelno == logging.WARNING for r in caplog.records)


async def test_flush_that_hangs_does_not_hang_the_request(monkeypatch, collab_on, queue, caplog):
    assert main.COLLAB_FLUSH_TIMEOUT_SECONDS == 2.0
    monkeypatch.setattr(main, "COLLAB_FLUSH_TIMEOUT_SECONDS", 0.1)
    room = StubRoom(delay=0.5)
    _install_room(monkeypatch, room)

    t = time.perf_counter()
    with caplog.at_level(logging.WARNING, logger="main"):
        await _call(_request())
    elapsed = time.perf_counter() - t

    assert elapsed < 0.45, f"request waited {elapsed:.2f}s on a hung flush"
    assert len(queue.calls) == 1
    assert any("exceeded" in r.getMessage() for r in caplog.records)
    # The flush is abandoned, not cancelled: cancelling it mid-write would drop
    # the files it had already taken off the room's dirty set.
    await asyncio.sleep(0.6)
    assert room.flush_completed


async def test_real_two_second_cap_bounds_a_wedged_room(monkeypatch, collab_on, queue):
    room = StubRoom(delay=30)
    _install_room(monkeypatch, room)

    t = time.perf_counter()
    await _call(_request())
    elapsed = time.perf_counter() - t

    assert 1.9 <= elapsed < 3.0
    assert len(queue.calls) == 1


async def test_no_room_still_compiles_and_logs_a_warning(monkeypatch, collab_on, queue, caplog):
    _install_room(monkeypatch, None)

    with caplog.at_level(logging.WARNING, logger="main"):
        await _call(_request())

    assert len(queue.calls) == 1
    assert any(
        r.levelno == logging.WARNING and "no live collab room" in r.getMessage() for r in caplog.records
    )


async def test_collab_disabled_skips_the_flush_and_compiles(monkeypatch, queue, caplog):
    monkeypatch.setenv("COLLAB_ENABLED", "0")
    room = StubRoom()
    _install_room(monkeypatch, room)

    with caplog.at_level(logging.WARNING, logger="main"):
        await _call(_request())

    assert room.flush_calls == 0
    assert len(queue.calls) == 1
    assert any(r.levelno == logging.WARNING and "collab disabled" in r.getMessage() for r in caplog.records)


async def test_no_project_id_compiles_without_looking_for_a_room(monkeypatch, collab_on, queue):
    def boom(pid):
        raise AssertionError("room lookup without a project id")

    monkeypatch.setattr(room_manager, "get", boom)
    await _call(_request(project_id=""))
    assert len(queue.calls) == 1


# ── Busy (429) vs broken (200, success:false) ────────────────────────────────

def _assert_busy(res) -> None:
    assert res.status_code == 429
    body = res.json()
    assert isinstance(body.get("detail"), str) and body["detail"]
    assert "retry_after_seconds" in body
    assert isinstance(body["retry_after_seconds"], (int, float))
    assert "success" not in body and "error_log" not in body
    assert "Retry-After" in res.headers


def test_queue_depth_cap_answers_429_with_retry_hint(monkeypatch, client):
    monkeypatch.setattr(main, "compile_queue", CompileQueue(max_concurrent=1, max_depth=0))
    _install_room(monkeypatch, None)
    res = client.post("/api/compile", json={"latex_code": "x", "engine": "pdflatex"})
    _assert_busy(res)


async def test_slot_wait_timeout_answers_429_with_retry_hint(monkeypatch):
    """
    Every slot held by other compiles for longer than the queue's wait: the
    request is refused as busy (429), not reported as a failed compile.
    """
    monkeypatch.setattr(compile_queue_module, "QUEUE_TIMEOUT_SECONDS", 0.1)
    q = CompileQueue(max_concurrent=1, max_depth=20)
    monkeypatch.setattr(main, "compile_queue", q)
    _install_room(monkeypatch, None)

    def must_not_run(**_kw):
        raise AssertionError("compiled without a slot")

    monkeypatch.setattr(main, "compile_latex", must_not_run)
    sem = q._get_semaphore()
    await sem.acquire()  # another compile holds the only slot
    try:
        res = await _call(_request())
    finally:
        sem.release()

    assert res.status_code == 429
    body = json.loads(res.body)
    assert isinstance(body.get("detail"), str) and body["detail"]
    assert isinstance(body.get("retry_after_seconds"), (int, float))
    assert "success" not in body and "error_log" not in body
    assert "retry-after" in res.headers
    assert q.waiting_count == 0 and q.active_count == 0


def test_compile_latex_default_timeout_comes_from_env():
    # None -> TEX_COMPILE_TIMEOUT (default 120s; heavy documents TEX_COMPILE_TIMEOUT_HEAVY, 240s)
    import compiler
    assert inspect.signature(compile_latex).parameters["timeout_seconds"].default is None
    assert compiler.TEX_COMPILE_TIMEOUT == int(os.getenv("TEX_COMPILE_TIMEOUT", "120") or 120)
    assert compiler.TEX_COMPILE_TIMEOUT_HEAVY == int(os.getenv("TEX_COMPILE_TIMEOUT_HEAVY", "240") or 240)


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="needs a TeX engine")
def test_broken_document_answers_200_with_success_false_and_error_log(monkeypatch, client):
    """Real pdflatex: a compile failure is a 200 carrying the log, never a 4xx/5xx."""
    _install_room(monkeypatch, None)
    doc = "\\documentclass{article}\\begin{document}\\input{no-such-file-xyz}\\end{document}"
    res = client.post("/api/compile", json={"latex_code": doc, "engine": "pdflatex"})
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is False
    assert "no-such-file-xyz" in body["error_log"]
