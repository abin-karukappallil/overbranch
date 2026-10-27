"""
jobs.py — File-backed conversion job state.

State lives in PDF2LATEX_JOB_DIR/<job_id>/status.json (atomic writes) so that any
uvicorn worker can answer progress polls, while the job itself runs as an asyncio
task in the worker that accepted the upload.
"""

import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import get_settings

logger = logging.getLogger("pdf2latex.jobs")

TERMINAL = {"done", "error", "needs_confirmation", "cancelled"}
# A running job whose runner has not heartbeated (or written any status) for this long is
# considered lost. The runner heartbeats every HEARTBEAT_INTERVAL_S while its task is alive, even
# during a long LLM call that writes no stage update, so this can be short.
STALE_AFTER_S = 3 * 60
HEARTBEAT_INTERVAL_S = 30
JOB_TTL_S = 24 * 3600
_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_write_lock = threading.Lock()  # serializes read-modify-write within this process


def job_root() -> Path:
    root = get_settings().job_dir
    root.mkdir(parents=True, exist_ok=True)
    return root


def job_dir(job_id: str) -> Path:
    if not _JOB_ID_RE.match(job_id or ""):
        raise ValueError("Invalid job id")
    return job_root() / job_id


def _write_atomic(path: Path, data: Dict[str, Any]) -> None:
    tmp = path.with_suffix(f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)


# "exact" is the original coordinate-faithful pipeline; "editable" reflows the PDF into ordinary
# semantic LaTeX (sections, lists, tabular, \textcolor). New jobs default to "editable".
DEFAULT_MODE = "editable"
MODES = ("exact", "editable")
# What a status.json with no "mode" key means. Job directories written before the editable mode
# existed have no key and must keep running as the coordinate pipeline, so this stays "exact"
# even though new jobs default to "editable".
LEGACY_MODE = "exact"


def job_mode(state: Optional[Dict[str, Any]]) -> str:
    """The conversion mode stored in a job state; a missing or unknown key reads as LEGACY_MODE."""
    mode = (state or {}).get("mode")
    return mode if mode in MODES else LEGACY_MODE


def create_job(owner: str, project_id: str, filename: str, page_count: int,
               is_guest: bool = False, mode: str = DEFAULT_MODE) -> Dict[str, Any]:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}, not {mode!r}.")
    job_id = uuid.uuid4().hex
    d = job_root() / job_id
    d.mkdir(parents=True)
    now = time.time()
    state = {
        "job_id": job_id,
        "owner": owner,
        "is_guest": is_guest,
        "project_id": project_id,
        "filename": filename,
        "status": "queued",
        "stage": "queued",
        "message": "Waiting to start…",
        "progress": 0.0,
        "page_count": page_count,
        "pages": [{"number": i + 1, "status": "pending", "similarity": None, "text_coverage": None,
                   "attempts": 0, "fallback": None} for i in range(page_count)],
        "report": None,
        "result": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    # The key is written whenever the mode differs from what a missing key means (LEGACY_MODE =
    # "exact"). So an exact-mode job's status.json has no "mode" key and is byte-identical to what
    # it was before this mode existed, while an editable job always carries the key.
    if mode != LEGACY_MODE:
        state["mode"] = mode
    _write_atomic(d / "status.json", state)
    return state


def _read_raw(job_id: str) -> Optional[Dict[str, Any]]:
    """status.json exactly as stored on disk, with no stale rewrite."""
    try:
        path = job_dir(job_id) / "status.json"
    except ValueError:
        return None
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return state if isinstance(state, dict) else None


def _exists(job_id: str) -> bool:
    try:
        return (job_dir(job_id) / "status.json").exists()
    except ValueError:
        return False


READ_RETRIES = 5
READ_RETRY_DELAY_S = 0.05


def _read_raw_retrying(job_id: str, tries: int = READ_RETRIES) -> Optional[Dict[str, Any]]:
    """
    _read_raw, retried while status.json exists but could not be read (EMFILE, a transient I/O
    error). A job that does not exist returns None immediately. Never call with _write_lock held:
    it sleeps between attempts.
    """
    for attempt in range(max(1, tries)):
        state = _read_raw(job_id)
        if state is not None:
            return state
        if not _exists(job_id):
            return None
        if attempt + 1 < tries:
            time.sleep(READ_RETRY_DELAY_S * (attempt + 1))
    return None


def last_alive_at(state: Dict[str, Any]) -> float:
    """The latest sign of life: the runner's heartbeat or the last status write, whichever is newer."""
    def _num(v: Any) -> float:
        return float(v) if isinstance(v, (int, float)) else 0.0
    return max(_num(state.get("heartbeat_at")), _num(state.get("updated_at")))


def is_stale(state: Dict[str, Any], now: Optional[float] = None) -> bool:
    """An unfinished job whose runner has shown no sign of life for STALE_AFTER_S."""
    if state.get("status") in TERMINAL:
        return False
    return (now if now is not None else time.time()) - last_alive_at(state) > STALE_AFTER_S


def load_job(job_id: str) -> Optional[Dict[str, Any]]:
    # A transient read failure must not look like "no such job": the client treats 404 as final.
    state = _read_raw_retrying(job_id, 3)
    if state is None:
        return None
    if is_stale(state):
        # Deliberately applied to the RETURNED dict only and never persisted: a worker that died
        # mid-conversion leaves a job that can still be resumed from its finished pages, so it
        # must not be written off on disk. Every caller recomputes this on each read.
        # The synthesised "error" is therefore NOT terminal: `stale` marks it so is_resumable()
        # can tell it apart from a job the pipeline itself failed (which is persisted as "error").
        state["status"] = "error"
        state["error"] = "The conversion worker stopped responding. Please retry."
        state["stale"] = True
    return state


def is_resumable(state: Dict[str, Any]) -> bool:
    """Whether a job may be relaunched: unfinished on disk, whether or not it has since gone stale."""
    return state.get("status") not in TERMINAL or bool(state.get("stale"))


def update_job(job_id: str, **fields: Any) -> Dict[str, Any]:
    # Read-modify-write on the raw state: going through load_job would persist the
    # synthesised stale "error" the moment anything touched the job.
    #
    # When the read fails but the job exists (EMFILE, a transient I/O error) the old code started
    # from {} and wrote back ONLY the new fields, wiping `owner` and everything else, after which
    # every poll answered 403. So a failed read is retried, and if it still fails nothing is
    # written: losing one update is recoverable, losing the owner is not.
    for attempt in range(READ_RETRIES):
        with _write_lock:
            state = _read_raw(job_id)
            if state is not None:
                state.update(fields)
                state["updated_at"] = time.time()
                _write_atomic(job_dir(job_id) / "status.json", state)
                return state
            exists = _exists(job_id)
        if not exists:
            break
        time.sleep(READ_RETRY_DELAY_S * (attempt + 1))
    if exists:
        logger.error(f"Could not read the state of conversion job {job_id}; update {sorted(fields)} not written")
    # Nothing was written: report the fields so callers that use the return value keep working.
    return dict(fields, job_id=job_id)


def touch_heartbeat(job_id: str, now: Optional[float] = None) -> bool:
    """
    Records that the runner is alive, without touching updated_at, so updated_at keeps meaning
    "last real progress". Never creates a state and never writes when the read fails.
    """
    with _write_lock:
        state = _read_raw(job_id)
        if state is None:
            return False
        state["heartbeat_at"] = now if now is not None else time.time()
        _write_atomic(job_dir(job_id) / "status.json", state)
        return True


def reassign_owner(old_owner: str, new_owner: str, is_guest: bool = False) -> List[str]:
    """
    Re-owns every job (running or finished) of `old_owner` to `new_owner`, e.g. when a guest signs
    in and their projects migrate. Each job is rewritten atomically under the write lock and a
    job whose state cannot be read is skipped, never rewritten. Returns the job ids changed.
    """
    changed: List[str] = []
    if not old_owner or not new_owner or old_owner == new_owner:
        return changed
    try:
        entries = list(job_root().iterdir())
    except OSError:
        return changed
    for d in entries:
        if not d.is_dir() or not _JOB_ID_RE.match(d.name):
            continue
        with _write_lock:
            state = _read_raw(d.name)
            if not state or state.get("owner") != old_owner:
                continue
            state["owner"] = new_owner
            state["is_guest"] = is_guest
            try:
                _write_atomic(d / "status.json", state)
            except OSError as e:
                logger.error(f"Could not re-own conversion job {d.name}: {e}")
                continue
        changed.append(d.name)
    return changed


def update_page(job_id: str, number: int, **fields: Any) -> None:
    with _write_lock:
        state = _read_raw(job_id)
        if not state:
            return
        for p in state.get("pages", []):
            if p.get("number") == number:
                p.update(fields)
        state["updated_at"] = time.time()
        _write_atomic(job_dir(job_id) / "status.json", state)


def active_job_for(owner: str) -> Optional[Dict[str, Any]]:
    root = job_root()
    for d in root.iterdir():
        if not d.is_dir() or not _JOB_ID_RE.match(d.name):
            continue
        st = load_job(d.name)
        if st and st.get("owner") == owner and st.get("status") not in TERMINAL:
            return st
    return None


def public_view(state: Dict[str, Any]) -> Dict[str, Any]:
    """Job state as returned to clients (internal fields removed)."""
    view = {k: v for k, v in state.items() if k not in ("owner",)}
    view["mode"] = job_mode(state)   # always present, so older job directories read as "exact"
    return view


def purge_old_jobs(max_age_s: int = JOB_TTL_S) -> int:
    """Deletes job directories older than max_age_s. Returns the number removed."""
    root = job_root()
    removed = 0
    cutoff = time.time() - max_age_s
    for d in root.iterdir():
        if not d.is_dir():
            continue
        try:
            if d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed
