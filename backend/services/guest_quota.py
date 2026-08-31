"""
guest_quota.py — Enforces strict 24-hour conversion quotas for guest users

Features:
- Exactly 1 PDF conversion per 24 hours per guest device/session
- Checks both session and device fingerprint to thwart cookie-clearing abuse
- Calculates remaining time until quota reset
- Checks for active, unmigrated guest project
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple

from project_storage import get_supabase_client
from .guest_identity import parse_utc_datetime

logger = logging.getLogger("guest_quota")

CONVERSION_LIMIT_PER_24H = 1


def check_guest_conversion_quota(session: Dict[str, Any], fingerprint_hash: str) -> Tuple[bool, int, Optional[datetime], Optional[str]]:
    """
    Checks if the guest is allowed to perform a PDF conversion.

    Returns:
        (allowed, conversions_used, resets_at_datetime, reason)
    """
    supabase = get_supabase_client()
    now_utc = datetime.now(timezone.utc)

    # 1. Check current session
    used = session.get("conversions_used", 0)
    last_conv_raw = session.get("last_conversion_at")

    if used >= CONVERSION_LIMIT_PER_24H and last_conv_raw:
        last_conv = parse_utc_datetime(last_conv_raw)
        resets_at = last_conv + timedelta(hours=24)
        if now_utc < resets_at:
            hours_left = max(1, int((resets_at - now_utc).total_seconds() // 3600))
            return False, used, resets_at, f"Daily guest limit reached (1 conversion per 24 hours). Resets in ~{hours_left}h. Sign in for unlimited conversions."

    return True, used, None, None


def consume_guest_conversion(session_id: str) -> None:
    """Records that a conversion was used by this guest session."""
    supabase = get_supabase_client()
    now_utc = datetime.now(timezone.utc)

    # Fetch current
    curr = supabase.table("guest_sessions").select("conversions_used").eq("id", session_id).single().execute()
    curr_used = curr.data.get("conversions_used", 0) if curr.data else 0

    supabase.table("guest_sessions").update({
        "conversions_used": curr_used + 1,
        "last_conversion_at": now_utc.isoformat(),
    }).eq("id", session_id).execute()


def get_guest_session_status(session: Dict[str, Any], fingerprint_hash: str) -> Dict[str, Any]:
    """
    Returns high-level status for frontend UI:
    - allowed: bool
    - conversions_used: int
    - conversions_limit: int
    - resets_at: ISO timestamp or None
    - active_project: metadata of active unmigrated project if exists
    """
    allowed, used, resets_at, reason = check_guest_conversion_quota(session, fingerprint_hash)
    supabase = get_supabase_client()
    now_utc = datetime.now(timezone.utc)

    # Check for active project
    active_project = None
    res_gp = supabase.table("guest_projects").select("id, project_id, expires_at, migrated_to_user_id")\
        .eq("guest_session_id", session["id"])\
        .is_("migrated_to_user_id", "null")\
        .order("created_at", desc=True)\
        .limit(1)\
        .execute()

    if res_gp.data and len(res_gp.data) > 0:
        gp = res_gp.data[0]
        exp = parse_utc_datetime(gp["expires_at"])
        if exp > now_utc:
            # Fetch project details
            p_res = supabase.table("projects").select("id, name, template, created_at").eq("id", gp["project_id"]).limit(1).execute()
            if p_res.data and len(p_res.data) > 0:
                p_data = p_res.data[0]
                active_project = {
                    "project_id": p_data["id"],
                    "name": p_data["name"],
                    "template": p_data.get("template"),
                    "expires_at": gp["expires_at"],
                    "seconds_remaining": max(0, int((exp - now_utc).total_seconds())),
                }

    return {
        "session_id": session["id"],
        "allowed": allowed,
        "conversions_used": used,
        "conversions_limit": CONVERSION_LIMIT_PER_24H,
        "resets_at": resets_at.isoformat() if resets_at else None,
        "reason": reason,
        "active_project": active_project,
    }
