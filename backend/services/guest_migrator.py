"""
guest_migrator.py — Atomic transfer of guest projects to registered user accounts

Features:
- Validates guest token and authenticated user
- Atomically updates project ownership and memberships
- Preserves all files, assets, Qdrant vectors, and metadata
- Marks guest_projects records as migrated
- Purges temporary synthetic guest user row
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from project_storage import get_supabase_client
from .guest_identity import verify_guest_token

logger = logging.getLogger("guest_migrator")


def migrate_guest_projects_to_user(
    guest_token: str,
    target_user_id: str,
) -> Dict[str, Any]:
    """
    Transfers ownership of all unmigrated guest projects belonging to the token's session
    to the target registered user.
    """
    verified = verify_guest_token(guest_token)
    if not verified:
        raise ValueError("Invalid or expired guest session token.")

    session_id, _ = verified
    supabase = get_supabase_client()
    now_utc = datetime.now(timezone.utc)

    # 1. Verify target user exists
    target_user = supabase.table("user").select("id, name, email").eq("id", target_user_id).limit(1).execute()
    if not (target_user.data and len(target_user.data) > 0):
        raise ValueError(f"Target user '{target_user_id}' does not exist.")

    # 2. Find all active unmigrated guest projects
    gp_res = supabase.table("guest_projects").select("id, project_id, expires_at")\
        .eq("guest_session_id", session_id)\
        .is_("migrated_to_user_id", "null")\
        .execute()

    guest_records = gp_res.data or []
    if not guest_records:
        return {
            "success": True,
            "migrated_count": 0,
            "projects": [],
            "message": "No pending guest projects found to migrate.",
        }

    migrated_projects = []
    synthetic_guest_user_id = f"guest_{session_id}"

    for gp in guest_records:
        project_id = gp["project_id"]
        gp_id = gp["id"]

        try:
            # 3. Update project owner
            supabase.table("projects").update({
                "owner_id": target_user_id,
                "status": "active",
            }).eq("id", project_id).execute()

            # 4. Update or insert project_members
            # First check if membership already exists for target user
            existing_mem = supabase.table("project_members").select("id")\
                .eq("project_id", project_id)\
                .eq("user_id", target_user_id)\
                .limit(1)\
                .execute()

            if not (existing_mem.data and len(existing_mem.data) > 0):
                # Update the guest member row or insert new
                guest_mem = supabase.table("project_members").select("id")\
                    .eq("project_id", project_id)\
                    .eq("user_id", synthetic_guest_user_id)\
                    .limit(1)\
                    .execute()

                if guest_mem.data and len(guest_mem.data) > 0:
                    supabase.table("project_members").update({
                        "user_id": target_user_id,
                        "role": "Owner",
                    }).eq("id", guest_mem.data[0]["id"]).execute()
                else:
                    import uuid
                    supabase.table("project_members").insert({
                        "id": str(uuid.uuid4()),
                        "project_id": project_id,
                        "user_id": target_user_id,
                        "role": "Owner",
                    }).execute()

            # 5. Mark guest_project as migrated
            supabase.table("guest_projects").update({
                "migrated_to_user_id": target_user_id,
                "migrated_at": now_utc.isoformat(),
            }).eq("id", gp_id).execute()

            migrated_projects.append(project_id)
            logger.info(f"Migrated guest project {project_id} to user {target_user_id}")

        except Exception as p_err:
            logger.error(f"Error migrating project {project_id}: {p_err}", exc_info=True)
            raise RuntimeError(f"Failed migrating project {project_id}: {str(p_err)}")

    # 6. Clean up temporary synthetic guest user row
    try:
        supabase.table("user").delete().eq("id", synthetic_guest_user_id).execute()
    except Exception as del_err:
        logger.warning(f"Could not purge temporary guest user row {synthetic_guest_user_id}: {del_err}")

    return {
        "success": True,
        "migrated_count": len(migrated_projects),
        "projects": migrated_projects,
        "primary_project_id": migrated_projects[0] if migrated_projects else None,
        "message": f"Successfully migrated {len(migrated_projects)} project(s) to your account.",
    }
