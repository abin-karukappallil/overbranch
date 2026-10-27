"""
PDF import liveness: update_job never wipes `owner`, migrated guests keep job access, a heartbeating
job is never faked into an error, and heartbeat staleness uses a 3 minute window.
"""

import asyncio
import time

import pytest
from fastapi import HTTPException

from pdf2latex import jobs, runner
from routes import pdf_convert
from services import guest_migrator

ME = {"user_id": "user-1"}


@pytest.fixture
def job_root(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF2LATEX_JOB_DIR", str(tmp_path))
    monkeypatch.setattr(jobs, "READ_RETRY_DELAY_S", 0)
    return tmp_path


def _make(owner="user-1"):
    return jobs.create_job(owner, "proj-1", "doc.pdf", 2)["job_id"]


def _set(job_id, **fields):
    state = jobs._read_raw(job_id)
    state.update(fields)
    jobs._write_atomic(jobs.job_dir(job_id) / "status.json", state)


# (a) update_job with a failing read keeps the owner --------------------------------------

def test_update_job_read_failure_never_wipes_owner(job_root, monkeypatch):
    jid = _make()
    real = jobs._read_raw
    monkeypatch.setattr(jobs, "_read_raw", lambda _id: None)  # status.json exists but is unreadable
    jobs.update_job(jid, status="running", message="x")
    monkeypatch.setattr(jobs, "_read_raw", real)
    state = jobs._read_raw(jid)
    assert state["owner"] == "user-1" and state["status"] == "queued"
    assert pdf_convert._owned_job(jid, ME)["job_id"] == jid


def test_update_job_retries_a_transient_read_failure(job_root, monkeypatch):
    jid = _make()
    real = jobs._read_raw
    calls = {"n": 0}

    def flaky(job_id):
        calls["n"] += 1
        return None if calls["n"] <= 2 else real(job_id)

    monkeypatch.setattr(jobs, "_read_raw", flaky)
    jobs.update_job(jid, status="running")
    monkeypatch.setattr(jobs, "_read_raw", real)
    state = jobs._read_raw(jid)
    assert state["status"] == "running" and state["owner"] == "user-1"


# (b) migrated guest keeps access ------------------------------------------------------------

def test_reassign_owner_moves_running_and_finished_jobs(job_root):
    running, done, other = _make("guest_s1"), _make("guest_s1"), _make("guest_s2")
    jobs.update_job(running, status="running")
    jobs.update_job(done, status="done")
    moved = jobs.reassign_owner("guest_s1", "user-1")
    assert sorted(moved) == sorted([running, done])
    assert pdf_convert._owned_job(running, ME)["status"] == "running"
    assert pdf_convert._owned_job(done, ME)["status"] == "done"
    assert jobs._read_raw(other)["owner"] == "guest_s2"
    assert jobs._read_raw(running)["is_guest"] is False


def test_owned_job_grants_a_migrated_guest_and_reowns(job_root, monkeypatch):
    jid = _make("guest_s1")
    monkeypatch.setattr(guest_migrator, "project_migrated_to",
                        lambda owner, project, user: (owner, project, user) == ("guest_s1", "proj-1", "user-1"))
    assert pdf_convert._owned_job(jid, ME)["job_id"] == jid
    assert jobs._read_raw(jid)["owner"] == "user-1"


def test_owned_job_still_forbids_an_unmigrated_guest_job(job_root, monkeypatch):
    jid = _make("guest_s1")
    monkeypatch.setattr(guest_migrator, "project_migrated_to", lambda *a: False)
    with pytest.raises(HTTPException) as e:
        pdf_convert._owned_job(jid, ME)
    assert e.value.status_code == 403 and e.value.detail["code"] == "job_forbidden"


def test_a_lookup_failure_is_forbidden_not_500(job_root, monkeypatch):
    jid = _make("guest_s1")

    def boom(*a):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(guest_migrator, "project_migrated_to", boom)
    with pytest.raises(HTTPException) as e:
        pdf_convert._owned_job(jid, ME)
    assert e.value.status_code == 403


def test_a_guest_caller_never_qualifies_via_migration(job_root, monkeypatch):
    jid = _make("guest_s1")
    monkeypatch.setattr(guest_migrator, "project_migrated_to", lambda *a: True)
    with pytest.raises(HTTPException):
        pdf_convert._owned_job(jid, {"user_id": "guest_s2", "is_guest": True})


def test_other_users_job_stays_forbidden(job_root, monkeypatch):
    jid = _make("someone-else")
    monkeypatch.setattr(guest_migrator, "project_migrated_to", lambda *a: True)
    with pytest.raises(HTTPException) as e:
        pdf_convert._owned_job(jid, ME)
    assert e.value.status_code == 403


# (c) a live heartbeating job is not faked into an error --------------------------------------

def test_live_job_on_this_worker_is_never_reported_as_stopped(job_root, monkeypatch):
    jid = _make()
    jobs.update_job(jid, status="running", message="Calling the model…")
    _set(jid, updated_at=time.time() - 3600, heartbeat_at=time.time() - 3600)  # even a late beat
    monkeypatch.setattr(pdf_convert, "is_job_running", lambda _id: True)
    launched = []
    monkeypatch.setattr(pdf_convert, "start_job", lambda *a, **kw: launched.append(1))

    view = asyncio.run(pdf_convert.get_conversion(jid, ME))

    assert view["status"] == "running" and view["error"] is None and "stale" not in view
    assert launched == []


def test_heartbeating_job_is_not_stale_despite_old_status_write(job_root):
    jid = _make()
    jobs.update_job(jid, status="running")
    _set(jid, updated_at=time.time() - 3600)
    assert jobs.touch_heartbeat(jid)
    seen = jobs.load_job(jid)
    assert seen["status"] == "running" and not seen.get("stale")
    assert jobs._read_raw(jid)["owner"] == "user-1"


def test_runner_heartbeat_task_writes_while_the_job_task_lives(job_root, monkeypatch):
    monkeypatch.setattr(jobs, "HEARTBEAT_INTERVAL_S", 0.05)
    jid = _make()

    async def go():
        job = asyncio.get_running_loop().create_task(asyncio.sleep(0.3))
        beat = asyncio.get_running_loop().create_task(runner._heartbeat(jid, job))
        await asyncio.sleep(0.15)
        first = jobs._read_raw(jid).get("heartbeat_at")
        await asyncio.sleep(0.1)
        second = jobs._read_raw(jid).get("heartbeat_at")
        await job
        await asyncio.wait_for(beat, 1)  # ends when the job task is done
        return first, second

    first, second = asyncio.run(go())
    assert first and second and second > first


# (d) 3 minute heartbeat window ------------------------------------------------------------------

def test_stale_window_is_three_minutes():
    assert jobs.STALE_AFTER_S == 180


def test_old_heartbeat_is_stale_young_heartbeat_is_alive(job_root):
    jid = _make()
    jobs.update_job(jid, status="running")
    now = time.time()

    _set(jid, updated_at=now - 3600, heartbeat_at=now - 181)
    old = jobs.load_job(jid)
    assert old["status"] == "error" and old["stale"] is True and jobs.is_resumable(old)

    _set(jid, updated_at=now - 3600, heartbeat_at=now - 170)
    young = jobs.load_job(jid)
    assert young["status"] == "running" and not young.get("stale")
