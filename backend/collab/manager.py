"""
backend/collab/manager.py — Room registry & lifecycle
=====================================================
One room per project, created on the first connection and torn down
`COLLAB_ROOM_IDLE_TTL` seconds after the last one leaves (so a page refresh or
a brief network drop rejoins the *same* in-memory document instead of paying a
cold load, while an abandoned project does not sit in memory forever).

Scaling note (also in COLLABORATION.md): rooms live in the worker process.
With more than one uvicorn worker, two users could land on different workers
and get two independent rooms for one project — so collaboration requires
`WORKERS=1`, or a load balancer that pins `/ws/collab/<project_id>` to one
worker. `warn_if_multi_worker()` makes that loud at startup rather than
mysterious in production.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Dict, List, Optional

from .config import config
from .events import log_error, log_event
from .room import CollabRoom


class RoomManager:
    def __init__(self) -> None:
        self._rooms: Dict[str, CollabRoom] = {}
        self._lock = asyncio.Lock()
        self._reaper: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """
        The loop the rooms run on, so synchronous backend writers on worker
        threads can hand work to a room (see collab/inject.py).
        """
        return self._loop

    async def get_or_create(self, project_id: str) -> CollabRoom:
        self._loop = asyncio.get_running_loop()
        async with self._lock:
            room = self._rooms.get(project_id)
            if room is not None:
                return room
            if len(self._rooms) >= config.max_rooms:
                # Evict the longest-idle empty room before refusing service.
                await self._reap_locked(force_one=True)
            room = CollabRoom(project_id)
            self._rooms[project_id] = room
        await room.start()
        return room

    def get(self, project_id: str) -> Optional[CollabRoom]:
        return self._rooms.get(project_id)

    @property
    def rooms(self) -> Dict[str, CollabRoom]:
        return dict(self._rooms)

    async def _reap_locked(self, force_one: bool = False) -> None:
        now = time.time()
        candidates: List[CollabRoom] = [
            room
            for room in self._rooms.values()
            if not room.connections and room.empty_since is not None
        ]
        if force_one:
            candidates.sort(key=lambda r: r.empty_since or 0.0)
            candidates = candidates[:1]
        else:
            candidates = [
                room
                for room in candidates
                if (now - (room.empty_since or now)) >= config.room_idle_ttl
            ]

        for room in candidates:
            self._rooms.pop(room.project_id, None)
            try:
                await room.stop()
            except Exception as e:
                log_error("COLLAB_ERROR", e, project_id=room.project_id, stage="reap")

    async def start_reaper(self) -> None:
        self._loop = asyncio.get_running_loop()
        if self._reaper and not self._reaper.done():
            return

        async def loop() -> None:
            try:
                while True:
                    await asyncio.sleep(max(5.0, config.room_idle_ttl / 2))
                    async with self._lock:
                        await self._reap_locked()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # pragma: no cover - defensive
                log_error("COLLAB_ERROR", e, stage="reaper")

        self._reaper = asyncio.create_task(loop())

    async def shutdown(self) -> None:
        """Flushes every open room — a deploy must not lose unsaved keystrokes."""
        if self._reaper and not self._reaper.done():
            self._reaper.cancel()
            try:
                await self._reaper
            except (asyncio.CancelledError, Exception):
                pass
        self._reaper = None

        async with self._lock:
            rooms = list(self._rooms.values())
            self._rooms.clear()
        for room in rooms:
            try:
                await room.stop()
            except Exception as e:
                log_error("COLLAB_ERROR", e, project_id=room.project_id, stage="shutdown")
        log_event("COLLAB_ROOM_CLOSE", rooms=len(rooms), reason="shutdown")

    async def drop(self, project_id: str) -> None:
        async with self._lock:
            room = self._rooms.pop(project_id, None)
        if room is not None:
            await room.stop()


room_manager = RoomManager()


def warn_if_multi_worker() -> None:
    """
    Loud startup warning for the one configuration that silently breaks
    collaboration. `COLLAB_MULTI_WORKER=1` says "my proxy pins rooms by
    project, I know what I am doing" and suppresses it.
    """
    if (os.getenv("COLLAB_MULTI_WORKER") or "").strip() in ("1", "true", "yes"):
        return
    try:
        workers = int((os.getenv("WORKERS") or "1").strip().strip('"').strip("'") or 1)
    except ValueError:
        workers = 1
    if workers > 1 and config.enabled:
        log_event(
            "COLLAB_ERROR",
            reason="multiple_uvicorn_workers",
            workers=workers,
            detail=(
                "Collaboration rooms are per-process. Run WORKERS=1 or pin "
                "/ws/collab/<project_id> to a single worker, otherwise two "
                "users may edit two independent copies of the same document."
            ),
        )
