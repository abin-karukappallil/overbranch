"""
backend/collab/presence.py — Who is looking at a project, without a socket.

A collaboration room is not free: it holds a websocket, a uvicorn concurrency
slot, an authoritative CRDT document and a persistence timer, for as long as
the tab is open. Opening one the moment somebody views a project spends all of
that on the overwhelmingly common case — one person editing alone, who needs
none of it and is served perfectly well by the REST autosave path.

But "is anyone else here?" is exactly what a room is for, so asking it cannot
require one. This module is the cheap answer: a heartbeat the client posts
every few seconds, kept in memory with a short TTL, that says how many distinct
people currently have the project open. The websocket is opened only when that
count reaches two *and* the project is actually shared with someone.

Deliberately in-memory and deliberately approximate:

* it is a hint about whether to open a socket, never an authorization decision
  (that is still `access.resolve_project_role`, on every connect and every
  re-auth tick);
* being briefly wrong is harmless in both directions — a late second viewer
  waits one poll interval before the socket opens, and a stale entry opens a
  socket nobody needed, which the idle reaper closes;
* it is per-process, like the rooms themselves, which is the same constraint
  collaboration already has (`warn_if_multi_worker`).
"""

from __future__ import annotations

import os
import time
from threading import Lock
from typing import Dict, Optional, Set, Tuple

# A viewer is "here" for this long after their last heartbeat. Comfortably
# longer than the client's poll interval so one dropped request does not make
# somebody flicker out of existence and tear a live session down.
VIEWER_TTL = float(os.environ.get("COLLAB_PRESENCE_TTL", "30") or 30)
POLL_INTERVAL = float(os.environ.get("COLLAB_PRESENCE_POLL", "8") or 8)
# People needed before a room is worth opening.
CONNECT_THRESHOLD = int(os.environ.get("COLLAB_CONNECT_THRESHOLD", "2") or 2)


class PresenceRegistry:
    """Recent viewers per project, keyed by user so two tabs are one person."""

    def __init__(self) -> None:
        self._seen: Dict[str, Dict[str, float]] = {}
        self._lock = Lock()

    def _purge(self, project_id: str, now: float) -> Dict[str, float]:
        viewers = self._seen.get(project_id)
        if viewers is None:
            return {}
        for uid in [u for u, ts in viewers.items() if now - ts > VIEWER_TTL]:
            viewers.pop(uid, None)
        if not viewers:
            self._seen.pop(project_id, None)
            return {}
        return viewers

    def touch(self, project_id: str, user_id: str) -> Set[str]:
        """Records that ``user_id`` is viewing, and returns everyone who is."""
        now = time.time()
        with self._lock:
            viewers = self._seen.setdefault(project_id, {})
            viewers[user_id] = now
            return set(self._purge(project_id, now).keys())

    def viewers(self, project_id: str) -> Set[str]:
        with self._lock:
            return set(self._purge(project_id, time.time()).keys())

    def leave(self, project_id: str, user_id: str) -> None:
        """Explicit departure, so the last editor's socket closes promptly."""
        with self._lock:
            viewers = self._seen.get(project_id)
            if viewers:
                viewers.pop(user_id, None)
                if not viewers:
                    self._seen.pop(project_id, None)

    def clear(self) -> None:
        with self._lock:
            self._seen.clear()


presence_registry = PresenceRegistry()


def project_is_shared(project_id: str) -> bool:
    """
    Whether anyone besides the owner can open this project.

    A project with no collaborators can never have a second viewer, so it
    never needs a room — and answering that from the membership table costs
    one indexed lookup against the socket it saves.
    """
    if not project_id:
        return False
    try:
        from project_storage import get_supabase_client

        supabase = get_supabase_client()
        members = (
            supabase.table("project_members")
            .select("user_id")
            .eq("project_id", project_id)
            .limit(1)
            .execute()
        )
        return bool(members.data)
    except Exception:
        # Fail *open*: if membership cannot be read, allow the socket. A
        # needless room is a wasted connection; a refused one silently drops
        # a real collaborator back to single-user editing with no warning.
        return True


def should_open_socket(project_id: str, user_id: str) -> Tuple[bool, Dict[str, object]]:
    """
    ``(open_it, detail)`` — whether this viewer should hold a live room now.

    An already-open room keeps its occupants connected even as the count falls
    back to one: the last editor's session is flushed and closed by the room's
    own last-leave path, not by yanking the socket mid-keystroke.
    """
    from .manager import room_manager

    viewers = presence_registry.touch(project_id, user_id)
    shared = project_is_shared(project_id)
    room = room_manager.get(project_id)
    room_live = bool(room and room.connections)
    enough = len(viewers) >= CONNECT_THRESHOLD
    open_it = shared and (enough or room_live)
    return open_it, {
        "viewers": len(viewers),
        "shared": shared,
        "room_live": room_live,
        "threshold": CONNECT_THRESHOLD,
        "poll_interval": POLL_INTERVAL,
        "reason": ("not_shared" if not shared
                   else "alone" if not (enough or room_live)
                   else "room_live" if not enough
                   else "enough_viewers"),
    }
