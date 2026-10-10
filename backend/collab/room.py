"""
backend/collab/room.py — One collaboration room per project
===========================================================
A room owns an authoritative `pycrdt.Doc` for one project and relays the
standard **y-websocket** wire protocol, so the browser can use the stock
`y-websocket` provider (with its reconnect/backoff and awareness) unchanged.

Document shape (identical names on both sides, so the roots line up):

    Y.Text  "file:<path>"   one per open text file
    Y.Map   "meta"          "loaded:<path>" -> True   (seeded, safe to bind)
                            "saved:<path>"  -> {hash, at}  (last persisted)

Why the server holds a real CRDT and not a dumb relay:

  * **Late joiners.** A client that connects an hour in sends sync step 1 and
    needs step 2 from *somebody*. A relay has to ask a peer, which fails when
    everyone has left and the document only exists in Postgres.
  * **Restart safety.** Rebuilding a room by inserting the DB text into a fresh
    doc gives the text a new CRDT identity. A client reconnecting with its old
    doc merges both insertions and the user gets the document twice. Applying
    the stored update preserves identity, so the merge is a no-op.
  * **Write authority.** A Viewer's updates can be dropped server-side rather
    than trusting the client to behave.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, Iterable, List, Optional, Set

from pycrdt import (
    Awareness,
    Doc,
    Map,
    Text,
    YMessageType,
    YSyncMessageType,
    create_awareness_message,
    create_update_message,
    read_message,
)
# Only the two step helpers are not re-exported from the package root.
from pycrdt._sync import create_sync_step1_message, create_sync_step2_message

from .config import config
from .events import log_error, log_event
from .persistence import (
    content_hash,
    load_crdt_state,
    load_document_text,
    save_crdt_state,
    save_document_text,
)

FILE_PREFIX = "file:"
META_ROOT = "meta"
MESSAGE_QUERY_AWARENESS = 3  # y-websocket's messageQueryAwareness

# Close codes the client must NOT retry on (see lib/collab/useCollaboration.ts).
CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_NOT_FOUND = 4404
CLOSE_ROOM_FULL = 4429
CLOSE_PROTOCOL = 4400


class Connection:
    """One websocket in a room, with its own send queue and writer task."""

    __slots__ = (
        "id",
        "ws",
        "user_id",
        "user_name",
        "role",
        "queue",
        "awareness_client_ids",
        "connected_at",
        "_writer",
        "_closed",
        "close_code",
    )

    _next_id = 0

    def __init__(self, ws: Any, user_id: str, user_name: str, role: str) -> None:
        Connection._next_id += 1
        self.id = Connection._next_id
        self.ws = ws
        self.user_id = user_id
        self.user_name = user_name
        self.role = role
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=config.send_queue_size)
        self.awareness_client_ids: Set[int] = set()
        self.connected_at = time.time()
        self._writer: Optional[asyncio.Task] = None
        self._closed = False
        self.close_code: Optional[int] = None

    @property
    def can_edit(self) -> bool:
        return self.role in ("Owner", "Editor")

    def enqueue(self, message: bytes) -> bool:
        """
        Non-blocking send. A client that cannot keep up is disconnected rather
        than allowed to grow an unbounded buffer in the server; y-websocket
        reconnects and re-syncs from scratch, which is cheaper than the memory.
        """
        if self._closed:
            return False
        try:
            self.queue.put_nowait(message)
            return True
        except asyncio.QueueFull:
            self._closed = True
            self.close_code = CLOSE_PROTOCOL
            return False

    async def start_writer(self) -> None:
        async def pump() -> None:
            try:
                while True:
                    message = await self.queue.get()
                    await self.ws.send_bytes(message)
            except asyncio.CancelledError:
                raise
            except Exception:
                # The read loop owns teardown; a send failure only ends the pump.
                self._closed = True

        self._writer = asyncio.create_task(pump())

    async def stop_writer(self) -> None:
        if self._writer and not self._writer.done():
            self._writer.cancel()
            try:
                await self._writer
            except (asyncio.CancelledError, Exception):
                pass
        self._writer = None


class CollabRoom:
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self.doc = Doc()
        self.awareness = Awareness(self.doc)
        self.connections: Dict[int, Connection] = {}

        self._meta: Map = self.doc.get(META_ROOT, type=Map)
        self._texts: Dict[str, Text] = {}
        self._text_subs: Dict[str, Any] = {}
        self._dirty: Set[str] = set()
        self._first_dirty_at: Optional[float] = None
        self._last_change_at: float = 0.0
        self._state_dirty = False
        self._loading: Set[str] = set()

        self._persist_task: Optional[asyncio.Task] = None
        # Strong references to fire-and-forget seeding tasks. asyncio only keeps
        # a weak reference to a running task, so without this a seed could be
        # garbage collected mid-flight and the file would never load.
        self._pending_tasks: Set[asyncio.Task] = set()
        self._lock = asyncio.Lock()
        self._started = False
        self.empty_since: Optional[float] = time.time()
        self._awareness_sub: Optional[str] = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._started:
            return
        self._started = True

        state = await asyncio.to_thread(load_crdt_state, self.project_id)
        restored = False
        if state:
            try:
                self.doc.apply_update(state)
                restored = True
            except Exception as e:
                # A corrupt blob must not make the project unopenable: fall
                # back to seeding from the document text.
                log_error("COLLAB_ERROR", e, project_id=self.project_id, stage="apply_snapshot")

        # Re-attach text observers for whatever the snapshot restored, and
        # adopt any edit made outside the room while it was closed (AI agent
        # writes, a PDF import, a template clone).
        for key in self._known_file_keys():
            path = key[len(FILE_PREFIX):]
            self._attach_text(path)
        if restored:
            await self._reconcile_external_changes()

        self._awareness_sub = self.awareness.observe(self._on_awareness_change)
        self._persist_task = asyncio.create_task(self._persist_loop())
        log_event(
            "COLLAB_ROOM_OPEN",
            project_id=self.project_id,
            restored_from_snapshot=restored,
            files=len(self._texts),
        )

    async def stop(self) -> None:
        if self._persist_task and not self._persist_task.done():
            self._persist_task.cancel()
            try:
                await self._persist_task
            except (asyncio.CancelledError, Exception):
                pass
        self._persist_task = None
        for task in list(self._pending_tasks):
            if not task.done():
                task.cancel()
        self._pending_tasks.clear()
        if self._awareness_sub is not None:
            try:
                self.awareness.unobserve(self._awareness_sub)
            except Exception:
                pass
            self._awareness_sub = None
        await self.flush(force=True)
        log_event("COLLAB_ROOM_CLOSE", project_id=self.project_id)

    # ── Document helpers ─────────────────────────────────────────────────────

    def _known_file_keys(self) -> List[str]:
        try:
            return [k for k in self.doc.keys() if k.startswith(FILE_PREFIX)]
        except Exception:
            return []

    def _attach_text(self, path: str) -> Text:
        """Materializes the Y.Text for a path and starts marking it dirty."""
        existing = self._texts.get(path)
        if existing is not None:
            return existing
        text = self.doc.get(FILE_PREFIX + path, type=Text)
        self._texts[path] = text

        # Exactly one parameter: pycrdt inspects the callback's arity and
        # passes the transaction as a second argument when it accepts one, so a
        # `_path: str = path` default would be overwritten by a ReadTransaction
        # and the dirty set would fill with transactions instead of paths.
        def on_change(_event: Any) -> None:
            self._dirty.add(path)
            self._state_dirty = True
            now = time.time()
            self._last_change_at = now
            if self._first_dirty_at is None:
                self._first_dirty_at = now

        try:
            self._text_subs[path] = text.observe(on_change)
        except Exception as e:  # pragma: no cover - defensive
            log_error("COLLAB_ERROR", e, project_id=self.project_id, stage="observe_text")
        return text

    def _apply_server_change(self, mutate) -> Optional[bytes]:
        """
        Runs a server-originated mutation and returns the resulting update so it
        can be broadcast. No `await` may happen inside `mutate`: the state
        vector is captured immediately before it and diffed immediately after.
        """
        before = self.doc.get_state()
        mutate()
        update = self.doc.get_update(before)
        if not update or update == b"\x00\x00":
            return None
        return update

    def is_text_file(self, path: str) -> bool:
        lowered = path.lower()
        return any(lowered.endswith(ext) for ext in config.collaborative_files)

    def _validate_path(self, path: str) -> bool:
        if not path or len(path) > 512:
            return False
        if ".." in path or path.startswith("/") or "\\" in path:
            return False
        return self.is_text_file(path)

    async def ensure_file_loaded(self, path: str) -> None:
        """
        Seeds `file:<path>` from durable storage exactly once, then flips
        `meta["loaded:<path>"]`. Clients wait for that flag before binding
        Monaco — binding to a not-yet-seeded (empty) text and typing into it
        would merge the user's keystrokes into position 0 of a document that is
        about to arrive, which garbles it.
        """
        if path in self._texts and self._meta.get(f"loaded:{path}") is True:
            return
        if not self._validate_path(path):
            return
        if path in self._loading:
            return
        if len(self._texts) >= config.max_files_per_room and path not in self._texts:
            log_event("COLLAB_ERROR", project_id=self.project_id, reason="max_files_per_room")
            return

        self._loading.add(path)
        try:
            async with self._lock:
                if self._meta.get(f"loaded:{path}") is True:
                    self._attach_text(path)
                    return

                stored = await asyncio.to_thread(load_document_text, self.project_id, path)
                text = self._attach_text(path)

                def mutate() -> None:
                    if len(text) == 0 and stored:
                        text.insert(0, stored)
                    self._meta[f"loaded:{path}"] = True
                    # Record what storage held at seed time. Without this
                    # marker a cold room cannot tell "someone edited the file
                    # outside the room" from "the room has edits it never
                    # flushed", and `_reconcile_external_changes` would have to
                    # guess — guessing wrong either resurrects deleted text or
                    # discards an AI/import rewrite.
                    if f"saved:{path}" not in self._meta:
                        self._meta[f"saved:{path}"] = {
                            "hash": content_hash(str(text)),
                            "at": int(time.time() * 1000),
                        }

                update = self._apply_server_change(mutate)
                if update:
                    self.broadcast(create_update_message(update))

                log_event(
                    "COLLAB_FILE_LOAD",
                    project_id=self.project_id,
                    file_path=path,
                    chars=len(stored or ""),
                    found=stored is not None,
                )
        except Exception as e:
            log_error("COLLAB_ERROR", e, project_id=self.project_id, file_path=path, stage="ensure_file_loaded")
        finally:
            self._loading.discard(path)

    async def _reconcile_external_changes(self) -> None:
        """
        A cold room's snapshot can be older than the document text: the AI
        agent's `save-file`, a PDF import or a template clone all write
        `latex_documents` directly. When the stored text no longer matches the
        hash recorded at the last flush, the external version wins and is
        applied as a CRDT operation (so a reconnecting client merges it rather
        than fighting it).
        """
        for path in list(self._texts.keys()):
            try:
                saved = self._meta.get(f"saved:{path}")
                recorded = saved.get("hash") if isinstance(saved, dict) else None
                stored = await asyncio.to_thread(load_document_text, self.project_id, path)
                if stored is None:
                    continue
                text = self._texts[path]
                current = str(text)
                if current == stored:
                    continue
                if recorded is None or content_hash(current) != recorded:
                    # Either we have no record of what storage held when we
                    # last agreed with it, or the room's text has moved on
                    # since then: these are the room's own unflushed edits and
                    # they are newer than whatever is in storage. Keep them.
                    continue

                def mutate(_text: Text = text, _stored: str = stored) -> None:
                    if len(_text) > 0:
                        del _text[0 : len(_text)]
                    if _stored:
                        _text.insert(0, _stored)

                self._apply_server_change(mutate)
                self._dirty.discard(path)
                log_event(
                    "COLLAB_EXTERNAL_CHANGE",
                    project_id=self.project_id,
                    file_path=path,
                    chars=len(stored),
                )
            except Exception as e:
                log_error("COLLAB_ERROR", e, project_id=self.project_id, file_path=path, stage="reconcile")

    # ── Connections ──────────────────────────────────────────────────────────

    async def add_connection(self, conn: Connection, initial_file: Optional[str] = None) -> None:
        self.connections[conn.id] = conn
        self.empty_since = None
        await conn.start_writer()

        if initial_file:
            await self.ensure_file_loaded(initial_file)

        # y-websocket handshake: our step 1 (so we learn what they have), then
        # the awareness states we already know (so a late joiner sees existing
        # cursors immediately instead of waiting for the next 15s heartbeat).
        conn.enqueue(create_sync_step1_message(self.doc.get_state()))
        known = [cid for cid, state in self.awareness.states.items() if state]
        if known:
            conn.enqueue(create_awareness_message(self.awareness.encode_awareness_update(known)))

        log_event(
            "COLLAB_JOIN",
            project_id=self.project_id,
            user_id=conn.user_id,
            role=conn.role,
            conn_id=conn.id,
            peers=len(self.connections),
            file_path=initial_file,
        )

    async def remove_connection(self, conn: Connection) -> None:
        self.connections.pop(conn.id, None)
        await conn.stop_writer()

        # Drop this client's cursor so other users do not see a ghost, and tell
        # them about it. Awareness is memory-only; nothing to clean up in SQL.
        stale = [cid for cid in conn.awareness_client_ids if cid in self.awareness.states]
        if stale:
            try:
                self.awareness.remove_awareness_states(stale, "disconnect")
                self.broadcast(
                    create_awareness_message(self.awareness.encode_awareness_update(stale))
                )
            except Exception as e:
                log_error("COLLAB_ERROR", e, project_id=self.project_id, stage="remove_awareness")

        if not self.connections:
            self.empty_since = time.time()
            await self.flush(force=True)

        log_event(
            "COLLAB_LEAVE",
            project_id=self.project_id,
            user_id=conn.user_id,
            conn_id=conn.id,
            peers=len(self.connections),
            seconds=round(time.time() - conn.connected_at, 1),
        )

    def broadcast(self, message: bytes, exclude: Optional[Connection] = None) -> None:
        dropped: List[Connection] = []
        for conn in list(self.connections.values()):
            if exclude is not None and conn.id == exclude.id:
                continue
            if not conn.enqueue(message):
                dropped.append(conn)
        for conn in dropped:
            log_event(
                "COLLAB_ERROR",
                project_id=self.project_id,
                conn_id=conn.id,
                reason="send_queue_full",
            )

    def _on_awareness_change(self, topic: str, payload) -> None:
        """Remembers which awareness client ids arrived on which connection."""
        if topic != "update":
            return
        changes, origin = payload
        if not isinstance(origin, Connection):
            return
        for cid in list(changes.get("added", [])) + list(changes.get("updated", [])):
            origin.awareness_client_ids.add(cid)

    # ── Protocol ─────────────────────────────────────────────────────────────

    async def handle_message(self, conn: Connection, data: bytes) -> None:
        if not data:
            return
        if len(data) > config.max_message_bytes:
            log_event(
                "COLLAB_ERROR",
                project_id=self.project_id,
                conn_id=conn.id,
                reason="message_too_large",
                bytes=len(data),
            )
            conn.close_code = CLOSE_PROTOCOL
            return

        message_type = data[0]

        if message_type == YMessageType.SYNC:
            await self._handle_sync(conn, data)
        elif message_type == YMessageType.AWARENESS:
            self._handle_awareness(conn, data)
        elif message_type == MESSAGE_QUERY_AWARENESS:
            known = [cid for cid, state in self.awareness.states.items() if state]
            if known:
                conn.enqueue(
                    create_awareness_message(self.awareness.encode_awareness_update(known))
                )
        # messageAuth (2) is server -> client only; anything else is ignored.

    async def _handle_sync(self, conn: Connection, data: bytes) -> None:
        if len(data) < 2:
            return
        sub_type = data[1]

        if sub_type == YSyncMessageType.SYNC_STEP1:
            state = read_message(data[2:])
            update = self.doc.get_update(state)
            conn.enqueue(create_sync_step2_message(update))
            log_event(
                "COLLAB_SYNC",
                project_id=self.project_id,
                conn_id=conn.id,
                user_id=conn.user_id,
                direction="step2_sent",
                bytes=len(update),
            )
            return

        if sub_type not in (YSyncMessageType.SYNC_STEP2, YSyncMessageType.SYNC_UPDATE):
            return

        if not conn.can_edit:
            # Defense in depth: the UI already locks a Viewer's editor, but the
            # room must not take a document update on their word.
            log_event(
                "COLLAB_AUTH_FAILURE",
                project_id=self.project_id,
                user_id=conn.user_id,
                conn_id=conn.id,
                reason="write_denied_for_role",
                role=conn.role,
            )
            return

        update = read_message(data[2:])
        if not update or update == b"\x00\x00":
            return

        try:
            self.doc.apply_update(update)
        except Exception as e:
            log_error(
                "COLLAB_CONFLICT",
                e,
                project_id=self.project_id,
                conn_id=conn.id,
                user_id=conn.user_id,
                bytes=len(update),
            )
            return

        # Relay verbatim to the other peers. The originator already has it, so
        # echoing it back would only double the traffic.
        self.broadcast(data, exclude=conn)

        # An update can introduce a file this room had not materialized yet
        # (the peer opened it first); start watching it so it gets persisted.
        for key in self._known_file_keys():
            path = key[len(FILE_PREFIX):]
            if path not in self._texts:
                self._attach_text(path)
                self._dirty.add(path)

        self._state_dirty = True
        now = time.time()
        self._last_change_at = now
        if self._first_dirty_at is None:
            self._first_dirty_at = now

        log_event(
            "COLLAB_UPDATE",
            project_id=self.project_id,
            conn_id=conn.id,
            user_id=conn.user_id,
            bytes=len(update),
            peers=len(self.connections),
        )

    def _handle_awareness(self, conn: Connection, data: bytes) -> None:
        try:
            update = read_message(data[1:])
        except Exception:
            return
        try:
            self.awareness.apply_awareness_update(update, origin=conn)
        except Exception as e:
            log_error("COLLAB_ERROR", e, project_id=self.project_id, stage="awareness")
            return

        self.broadcast(data, exclude=conn)

        # Presence doubles as the file-open signal: a client announces the file
        # it is about to edit, and the room seeds it. No extra protocol.
        for cid in conn.awareness_client_ids:
            state = self.awareness.states.get(cid) or {}
            path = state.get("filePath")
            if isinstance(path, str) and path and path not in self._texts:
                task = asyncio.create_task(self.ensure_file_loaded(path))
                self._pending_tasks.add(task)
                task.add_done_callback(self._pending_tasks.discard)

        log_event(
            "COLLAB_AWARENESS",
            project_id=self.project_id,
            conn_id=conn.id,
            clients=len(conn.awareness_client_ids),
        )

    # ── Persistence ──────────────────────────────────────────────────────────

    async def _persist_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(config.persist_tick)
                if not self._dirty and not self._state_dirty:
                    continue
                now = time.time()
                idle_enough = (now - self._last_change_at) >= config.persist_debounce
                waited_too_long = (
                    self._first_dirty_at is not None
                    and (now - self._first_dirty_at) >= config.persist_max_interval
                )
                if idle_enough or waited_too_long:
                    await self.flush()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # pragma: no cover - defensive
            log_error("COLLAB_ERROR", e, project_id=self.project_id, stage="persist_loop")

    async def flush(self, force: bool = False) -> int:
        """
        Writes dirty files to disk + Supabase and the CRDT blob to its store.
        Returns the number of files written.
        """
        async with self._lock:
            paths = sorted(self._dirty)
            self._dirty.clear()
            written = 0

            for path in paths:
                text = self._texts.get(path)
                if text is None:
                    continue
                content = str(text)
                if len(content.encode("utf-8")) > config.max_file_bytes:
                    log_event(
                        "COLLAB_ERROR",
                        project_id=self.project_id,
                        file_path=path,
                        reason="file_too_large_to_persist",
                        bytes=len(content.encode("utf-8")),
                    )
                    continue

                digest = content_hash(content)
                saved = self._meta.get(f"saved:{path}")
                previous = saved.get("hash") if isinstance(saved, dict) else None
                if previous == digest and not force:
                    continue

                try:
                    await asyncio.to_thread(save_document_text, self.project_id, path, content)
                except Exception as e:
                    # Keep it dirty so the next tick retries instead of
                    # silently dropping the user's work.
                    self._dirty.add(path)
                    log_error("COLLAB_ERROR", e, project_id=self.project_id, file_path=path, stage="persist_text")
                    continue

                written += 1
                update = self._apply_server_change(
                    lambda _p=path, _d=digest: self._meta.__setitem__(
                        f"saved:{_p}", {"hash": _d, "at": int(time.time() * 1000)}
                    )
                )
                if update:
                    self.broadcast(create_update_message(update))

                log_event(
                    "COLLAB_PERSIST",
                    project_id=self.project_id,
                    file_path=path,
                    chars=len(content),
                    peers=len(self.connections),
                )

            if self._state_dirty or force:
                try:
                    blob = self.doc.get_update()
                    await asyncio.to_thread(save_crdt_state, self.project_id, blob)
                    self._state_dirty = False
                except Exception as e:
                    log_error("COLLAB_ERROR", e, project_id=self.project_id, stage="persist_crdt")

            if not self._dirty:
                self._first_dirty_at = None
            return written

    # ── External writes (AI agent commits, PDF import, plain save-file) ──────

    async def replace_file_text(self, path: str, text: str) -> bool:
        """
        Brings an externally-produced version of a file into the live document.

        Called when something outside the room writes a project file while
        people are editing it: the PDF importer committing `main.tex`, or a
        client that fell back to the REST save path. Writing storage alone
        would be invisible to everyone currently in the room until the room
        next cold-started, and the room's own next flush would then overwrite
        it — the external edit would simply vanish.

        The change is applied as the *difference* (common prefix and suffix are
        left alone) rather than as delete-all + insert-all, so collaborators'
        cursors stay where they are and concurrent edits outside the changed
        span survive.
        """
        if not self._validate_path(path):
            return False
        await self.ensure_file_loaded(path)
        async with self._lock:
            target = self._texts.get(path)
            if target is None:
                return False
            current = str(target)
            if current == text:
                return True

            start = 0
            limit = min(len(current), len(text))
            while start < limit and current[start] == text[start]:
                start += 1
            end = 0
            while (
                end < limit - start
                and current[len(current) - 1 - end] == text[len(text) - 1 - end]
            ):
                end += 1

            removed = len(current) - start - end
            inserted = text[start : len(text) - end]

            def mutate() -> None:
                if removed > 0:
                    del target[start : start + removed]
                if inserted:
                    target.insert(start, inserted)

            update = self._apply_server_change(mutate)
            if update:
                self.broadcast(create_update_message(update))
            self._dirty.add(path)
            self._state_dirty = True
            self._last_change_at = time.time()
            if self._first_dirty_at is None:
                self._first_dirty_at = self._last_change_at

            log_event(
                "COLLAB_EXTERNAL_CHANGE",
                project_id=self.project_id,
                file_path=path,
                removed=removed,
                inserted=len(inserted),
                peers=len(self.connections),
                origin="external_write",
            )
            return True

    # ── Introspection (used by /api/collab/rooms and tests) ──────────────────

    def describe(self) -> Dict[str, Any]:
        peers = []
        for conn in self.connections.values():
            peers.append(
                {
                    "conn_id": conn.id,
                    "user_id": conn.user_id,
                    "role": conn.role,
                    "connected_seconds": round(time.time() - conn.connected_at, 1),
                    "awareness_clients": len(conn.awareness_client_ids),
                }
            )
        return {
            "project_id": self.project_id,
            "peers": peers,
            "files": sorted(self._texts.keys()),
            "dirty": sorted(self._dirty),
            "awareness_states": len([s for s in self.awareness.states.values() if s]),
        }

    def get_file_text(self, path: str) -> Optional[str]:
        text = self._texts.get(path)
        return None if text is None else str(text)
