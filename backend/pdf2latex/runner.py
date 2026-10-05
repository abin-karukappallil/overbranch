"""
runner.py — Starts conversion jobs on the server's event loop.

Used by the HTTP endpoint (already on the loop) and by the copilot tool
`convert_attached_pdf`, which executes in a worker thread.
"""

import asyncio
import logging
from typing import Any, Dict, Optional, Set

from . import jobs
from .pipeline import run_conversion

logger = logging.getLogger("pdf2latex.runner")

_loop: Optional[asyncio.AbstractEventLoop] = None
_tasks: Set[asyncio.Task] = set()
_running_tasks: Dict[str, asyncio.Task] = {}


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Remembers the server event loop so worker threads can schedule jobs onto it."""
    global _loop
    _loop = loop


def is_job_running(job_id: str) -> bool:
    """Checks whether an asyncio task is actively executing this job in this process."""
    task = _running_tasks.get(job_id)
    return task is not None and not task.done()


def cancel_job(job_id: str) -> bool:
    """Cancels a running conversion task in memory and marks it cancelled on disk."""
    task = _running_tasks.get(job_id)
    if task and not task.done():
        task.cancel()
        _running_tasks.pop(job_id, None)
        jobs.update_job(job_id, status="cancelled", message="Conversion cancelled.")
        return True
    return False


def _spawn(job_id: str, data: bytes, project_id: str, overwrite: bool) -> None:
    task = asyncio.get_running_loop().create_task(run_conversion(job_id, data, project_id, overwrite))
    _tasks.add(task)
    _running_tasks[job_id] = task

    def _cleanup(_):
        _tasks.discard(task)
        _running_tasks.pop(job_id, None)

    task.add_done_callback(_cleanup)


def start_job(owner: str, is_guest: bool, project_id: str, filename: str, data: bytes,
              page_count: int, overwrite: bool = False) -> Dict[str, Any]:
    """
    Creates the job record, stores the upload and schedules the pipeline. Safe to call from
    the event loop thread or from a worker thread (after bind_loop).
    """
    state = jobs.create_job(owner, project_id, filename, page_count, is_guest)
    (jobs.job_dir(state["job_id"]) / "input.pdf").write_bytes(data)
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is not None:
        bind_loop(running)
        _spawn(state["job_id"], data, project_id, overwrite)
    elif _loop is not None and _loop.is_running():
        _loop.call_soon_threadsafe(_spawn, state["job_id"], data, project_id, overwrite)
    else:
        jobs.update_job(state["job_id"], status="error", error="Conversion runner is not available.")
        raise RuntimeError("No running event loop to execute the conversion job.")
    return state
