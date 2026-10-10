"""
backend/collab/inject.py — Routing backend document writes into a live room
===========================================================================
Everything in OverBranch that writes a project file goes through
`project_storage.write_document_text`. When a collaboration room for that
project is open, writing storage *only* would be wrong twice over: the people
currently editing would not see the change, and the room's next debounced
flush would write its own (older) text straight back over it.

So the write is first offered to the room, which applies it as a CRDT
difference and takes responsibility for persisting it. The storage write then
happens as usual, so non-realtime readers (the compiler, the agent, the PDF
importer) are immediately correct either way.

The room lives on the server's event loop while these callers are on worker
threads, hence `run_coroutine_threadsafe`. The room's own flush must *not* come
back through here — it passes `from_room=True` — or it would deadlock on the
room lock it already holds.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from .config import config
from .events import log_error
from .manager import room_manager

# A room write is a handful of in-memory CRDT operations plus a broadcast; if it
# has not completed in this long, something is wrong and the caller should fall
# through to the plain storage write rather than hang an HTTP request.
INJECT_TIMEOUT = 5.0


def inject_document_text(project_id: str, file_path: str, text: str) -> bool:
    """
    Applies `text` to the live room for this project, if there is one.

    Returns True when a room absorbed the change (and will persist it), False
    when there is no room, the loop is not running, or the attempt failed — in
    which case the caller's own storage write is the whole story.
    """
    if not config.enabled or not project_id or not file_path:
        return False

    room = room_manager.get(project_id)
    loop: Optional[asyncio.AbstractEventLoop] = room_manager.loop
    if room is None or loop is None or loop.is_closed():
        return False

    try:
        future = asyncio.run_coroutine_threadsafe(
            room.replace_file_text(file_path, text), loop
        )
        return bool(future.result(timeout=INJECT_TIMEOUT))
    except Exception as e:
        log_error("COLLAB_ERROR", e, project_id=project_id, file_path=file_path, stage="inject")
        return False
