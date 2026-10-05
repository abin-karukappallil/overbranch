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
STALE_AFTER_S = 15 * 60  # a running job not updated for this long is considered lost
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


def create_job(owner: str, project_id: str, filename: str, page_count: int,
               is_guest: bool = False) -> Dict[str, Any]:
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
    _write_atomic(d / "status.json", state)
    return state


def load_job(job_id: str) -> Optional[Dict[str, Any]]:
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
    if state.get("status") not in TERMINAL and time.time() - state.get("updated_at", 0) > STALE_AFTER_S:
        state["status"] = "error"
        state["error"] = "The conversion worker stopped responding. Please retry."
    return state


def update_job(job_id: str, **fields: Any) -> Dict[str, Any]:
    with _write_lock:
        state = load_job(job_id) or {}
        state.update(fields)
        state["updated_at"] = time.time()
        _write_atomic(job_dir(job_id) / "status.json", state)
        return state


def update_page(job_id: str, number: int, **fields: Any) -> None:
    with _write_lock:
        state = load_job(job_id)
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
    return {k: v for k, v in state.items() if k not in ("owner",)}


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


def list_files(directory: Path) -> List[Path]:
    return sorted(p for p in directory.rglob("*") if p.is_file())
