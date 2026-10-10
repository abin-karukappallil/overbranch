"""
backend/collab/persistence.py — Durable storage for collaborative documents
===========================================================================
Two things are persisted, and they answer two different questions.

1. **The text** goes to the existing store (local disk + Supabase
   `latex_documents`) through `project_storage.write_document_text`. This is
   what the compiler, the AI agent, the PDF importer and every non-realtime
   reader already use, so a collaborative edit must land there or the rest of
   OverBranch would not see it.

2. **The CRDT state** (one binary blob per project) goes to
   `uploads/collab-state/<project>.ybin` plus a Supabase `collab_doc_state`
   mirror. This is what makes a server restart safe: rebuilding a room from
   plain text would give the document a *new* CRDT identity, and a client that
   reconnects with its old `Y.Doc` would merge the two insertions and duplicate
   the whole file. Re-applying the stored update keeps one identity.

Both writes are debounced by the room, never per keystroke.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import time
from pathlib import Path
from typing import Optional

from .events import log_error, log_event

STATE_DIR = Path(
    os.getenv("COLLAB_STATE_DIR")
    or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "uploads", "collab-state")
).resolve()

STATE_SUFFIX = ".ybin"
_SUPABASE_TABLE = "collab_doc_state"


def content_hash(text: str) -> str:
    """Short, stable fingerprint used to detect edits made outside the room."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _safe_project(project_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", project_id)


def state_path(project_id: str) -> Path:
    return STATE_DIR / f"{_safe_project(project_id)}{STATE_SUFFIX}"


# ── Document text (reuses the existing project storage path) ──────────────────

def load_document_text(project_id: str, file_path: str) -> Optional[str]:
    from project_storage import read_document_text

    return read_document_text(project_id, file_path)


def save_document_text(project_id: str, file_path: str, text: str) -> None:
    from project_storage import write_document_text

    # from_room=True: this *is* the room's own text. Without it the write would
    # be offered straight back to the room, which is holding its flush lock.
    write_document_text(project_id, file_path, text, from_room=True)


# ── CRDT state blob ───────────────────────────────────────────────────────────

def load_crdt_state(project_id: str) -> Optional[bytes]:
    """Disk first (fast, always available), then the Supabase mirror."""
    path = state_path(project_id)
    try:
        if path.exists():
            data = path.read_bytes()
            if data:
                return data
    except OSError as e:
        log_error("COLLAB_ERROR", e, project_id=project_id, stage="load_crdt_disk")

    try:
        from project_storage import get_supabase_client

        res = (
            get_supabase_client()
            .table(_SUPABASE_TABLE)
            .select("state_b64")
            .eq("project_id", project_id)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if rows and rows[0].get("state_b64"):
            return base64.b64decode(rows[0]["state_b64"])
    except Exception as e:
        # A missing table is the normal case before the migration is applied;
        # the room then simply seeds itself from the document text.
        log_error("COLLAB_ERROR", e, project_id=project_id, stage="load_crdt_supabase")

    return None


def save_crdt_state(project_id: str, state: bytes) -> None:
    path = state_path(project_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic replace so a crash mid-write cannot leave a truncated blob
        # that would fail to apply and silently drop the document's history.
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(state)
        os.replace(tmp, path)
    except OSError as e:
        log_error("COLLAB_ERROR", e, project_id=project_id, stage="save_crdt_disk")

    try:
        from project_storage import get_supabase_client

        payload = {
            "project_id": project_id,
            "state_b64": base64.b64encode(state).decode("ascii"),
        }
        supabase = get_supabase_client()
        existing = (
            supabase.table(_SUPABASE_TABLE)
            .select("project_id")
            .eq("project_id", project_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            supabase.table(_SUPABASE_TABLE).update(
                {"state_b64": payload["state_b64"]}
            ).eq("project_id", project_id).execute()
        else:
            supabase.table(_SUPABASE_TABLE).insert(payload).execute()
    except Exception as e:
        log_error("COLLAB_ERROR", e, project_id=project_id, stage="save_crdt_supabase")


def purge_stale_crdt_state(max_age_days: int = 30) -> int:
    """
    Removes CRDT blobs for projects nobody has opened in a long time.

    The blob is a cache, not the document: the text lives in `latex_documents`
    and on disk. Dropping an old blob costs nothing (the room reseeds from the
    text) and keeps the directory from growing without bound as projects are
    deleted — a project deleted through the web app cascades its database rows
    but cannot reach this directory.
    """
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    try:
        if not STATE_DIR.exists():
            return 0
        for path in STATE_DIR.glob(f"*{STATE_SUFFIX}"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                continue
    except OSError as e:
        log_error("COLLAB_ERROR", e, stage="purge_stale_crdt_state")
        return removed

    if removed:
        log_event("COLLAB_PERSIST", action="purged_stale_crdt_state", removed=removed)
    return removed


def drop_crdt_state(project_id: str) -> None:
    """Used when a project is deleted, or when a corrupt blob must be discarded."""
    try:
        state_path(project_id).unlink(missing_ok=True)
    except OSError as e:
        log_error("COLLAB_ERROR", e, project_id=project_id, stage="drop_crdt_disk")
    try:
        from project_storage import get_supabase_client

        get_supabase_client().table(_SUPABASE_TABLE).delete().eq(
            "project_id", project_id
        ).execute()
    except Exception as e:
        log_error("COLLAB_ERROR", e, project_id=project_id, stage="drop_crdt_supabase")
    log_event("COLLAB_PERSIST", project_id=project_id, action="dropped_crdt_state")
