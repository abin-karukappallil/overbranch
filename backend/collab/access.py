"""
backend/collab/access.py — Project authorization for realtime rooms
===================================================================
The collaboration layer adds **no** new notion of identity or permission. It
resolves the caller's role from the same two tables the rest of OverBranch uses
(`projects.owner_id`, `project_members.role`) and returns None for anything
else — including a project that no longer exists.

This is called on every socket open *and* every `COLLAB_REAUTH_INTERVAL`
seconds while the socket is open, which is what makes revocation take effect
mid-session instead of at the next page load.
"""

from __future__ import annotations

from typing import Literal, Optional

from .events import log_error

Role = Literal["Owner", "Editor", "Viewer"]


def resolve_project_role(project_id: str, user_id: str) -> Optional[Role]:
    """
    Returns the caller's role in the project, or None when access is denied.

    Denies, deliberately:
      - a project id that does not exist (deleted project)
      - a user who is neither the owner nor in `project_members`
      - any lookup that errors (fail closed — a database hiccup must not open
        a private document to an unauthenticated socket)
    """
    if not project_id or not user_id:
        return None

    try:
        from project_storage import get_supabase_client

        supabase = get_supabase_client()
        proj = (
            supabase.table("projects")
            .select("id, owner_id")
            .eq("id", project_id)
            .limit(1)
            .execute()
        )
        rows = proj.data or []
        if not rows:
            return None

        if rows[0].get("owner_id") == user_id:
            return "Owner"

        member = (
            supabase.table("project_members")
            .select("role")
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        member_rows = member.data or []
        if not member_rows:
            return None

        role = (member_rows[0].get("role") or "Editor").strip()
        if role not in ("Owner", "Editor", "Viewer"):
            role = "Viewer"
        return role  # type: ignore[return-value]
    except Exception as e:
        log_error("COLLAB_AUTH_FAILURE", e, project_id=project_id, user_id=user_id)
        return None


def can_edit(role: Optional[str]) -> bool:
    return role in ("Owner", "Editor")
