"""
backend/collab/events.py — Structured collaboration logging
===========================================================
One function, one event vocabulary, so collaboration can be traced in
development and stay quiet in production.

Cursor/awareness traffic is the highest-volume thing in the system and is
deliberately *not* logged at INFO: `COLLAB_AWARENESS` only appears when
`COLLAB_DEBUG=1`. Everything that changes state (connect, join, sync, persist,
auth failure) is logged at INFO so a production incident is reconstructible.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from .config import config

logger = logging.getLogger("collab")

# Events that are emitted per message / per cursor move and would flood logs.
_HIGH_VOLUME = frozenset({"COLLAB_AWARENESS", "COLLAB_UPDATE", "COLLAB_SEND"})

EVENTS = (
    "COLLAB_CONNECT",
    "COLLAB_DISCONNECT",
    "COLLAB_JOIN",
    "COLLAB_LEAVE",
    "COLLAB_SYNC",
    "COLLAB_PERSIST",
    "COLLAB_RECONNECT",
    "COLLAB_AUTH_FAILURE",
    "COLLAB_CONFLICT",
    "COLLAB_ROOM_OPEN",
    "COLLAB_ROOM_CLOSE",
    "COLLAB_FILE_LOAD",
    "COLLAB_EXTERNAL_CHANGE",
    "COLLAB_AWARENESS",
    "COLLAB_UPDATE",
    "COLLAB_ERROR",
)


def log_event(event: str, **fields: Any) -> None:
    """
    Emits one structured line: `COLLAB_SYNC {"project_id": "...", ...}`.

    Never include document text or session tokens in `fields` — user ids,
    project ids, file paths, counts and byte sizes only.
    """
    payload = {k: v for k, v in fields.items() if v is not None}
    payload["ts"] = round(time.time(), 3)
    try:
        rendered = json.dumps(payload, default=str, separators=(",", ":"))
    except Exception:  # pragma: no cover - defensive
        rendered = str(payload)

    if event in _HIGH_VOLUME and not config.debug:
        logger.debug("%s %s", event, rendered)
    else:
        logger.info("%s %s", event, rendered)


def log_error(event: str, exc: BaseException, **fields: Any) -> None:
    payload = {k: v for k, v in fields.items() if v is not None}
    logger.warning(
        "%s %s error=%s: %s",
        event,
        json.dumps(payload, default=str, separators=(",", ":")),
        type(exc).__name__,
        exc,
    )
