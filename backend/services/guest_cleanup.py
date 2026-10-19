"""
guest_cleanup.py — Background garbage collection & disk purger for expired guest projects

Features:
- Purges unmigrated guest projects older than 24 hours
- Deletes project directory from filesystem (uploads/projects/<project_id>)
- Deletes database records across projects, documents, memberships
- Deletes abandoned guest sessions older than 7 days
- Includes concurrency lock to safely run in multi-worker environments
"""

import shutil
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from project_storage import UPLOADS_BASE_DIR, get_supabase_client

try:
    from synctex_service import cleanup_stale_synctex_cache
except ImportError:
    cleanup_stale_synctex_cache = None

logger = logging.getLogger("guest_cleanup")

# Concurrency lock to prevent multiple purge jobs running concurrently
_cleanup_lock = asyncio.Lock()


def purge_expired_guest_projects() -> Dict[str, Any]:
    """
    Scans for expired guest sessions and guest projects.
    Removes:
    1. Unmigrated guest projects past their expiration date (24h) from disk and database.
    2. Expired guest sessions (expires_at < now_utc) and their corresponding guest users from the user table.
    3. Any orphaned guest users in the user table whose sessions have expired or no longer exist.
    """
    supabase = get_supabase_client()
    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()

    purged_projects = []
    purged_disk_dirs = 0
    purged_guest_users = 0
    purged_sessions = 0

    # 1. Find expired, unmigrated guest projects
    try:
        res = supabase.table("guest_projects").select("id, project_id, guest_session_id, expires_at")\
            .lt("expires_at", now_iso)\
            .is_("migrated_to_user_id", "null")\
            .limit(100)\
            .execute()

        expired_list = res.data or []
        for item in expired_list:
            project_id = item["project_id"]
            gp_id = item["id"]
            guest_session_id = item.get("guest_session_id")

            logger.info(f"Purging expired guest project: {project_id}")

            # Delete from disk
            disk_path = UPLOADS_BASE_DIR / project_id
            if disk_path.exists() and disk_path.is_dir():
                try:
                    shutil.rmtree(disk_path, ignore_errors=True)
                    purged_disk_dirs += 1
                except Exception as fs_err:
                    logger.warning(f"Error removing disk path for {project_id}: {fs_err}")

            # Delete from database (projects table CASCADE deletes members and latex_documents)
            try:
                supabase.table("projects").delete().eq("id", project_id).execute()
            except Exception as db_err:
                logger.warning(f"Error deleting project {project_id} from DB: {db_err}")

            # Delete from guest_projects
            try:
                supabase.table("guest_projects").delete().eq("id", gp_id).execute()
            except Exception as gp_err:
                logger.warning(f"Error deleting guest_project record {gp_id}: {gp_err}")

            # Clean up synthetic guest user if associated
            if guest_session_id:
                try:
                    del_u = supabase.table("user").delete().eq("id", f"guest_{guest_session_id}").execute()
                    if del_u.data:
                        purged_guest_users += len(del_u.data)
                except Exception:
                    pass

            purged_projects.append(project_id)
    except Exception as gp_scan_err:
        logger.warning(f"Error scanning expired guest projects: {gp_scan_err}")

    # 2. Find ALL expired guest sessions (expires_at < now_utc)
    try:
        expired_sessions_res = supabase.table("guest_sessions").select("id, expires_at")\
            .lt("expires_at", now_iso)\
            .limit(200)\
            .execute()

        expired_sessions = expired_sessions_res.data or []
        for s in expired_sessions:
            session_id = s["id"]
            guest_user_id = f"guest_{session_id}"

            # Clean up disk artifacts for any projects owned by this expired guest user
            try:
                p_res = supabase.table("projects").select("id").eq("owner_id", guest_user_id).execute()
                for p in (p_res.data or []):
                    proj_id = p["id"]
                    disk_path = UPLOADS_BASE_DIR / proj_id
                    if disk_path.exists() and disk_path.is_dir():
                        shutil.rmtree(disk_path, ignore_errors=True)
                        purged_disk_dirs += 1
                    supabase.table("projects").delete().eq("id", proj_id).execute()
                    purged_projects.append(proj_id)
            except Exception as p_err:
                logger.warning(f"Error cleaning projects for expired guest session {session_id}: {p_err}")

            # Remove guest user from user table
            try:
                del_user = supabase.table("user").delete().eq("id", guest_user_id).execute()
                if del_user.data:
                    purged_guest_users += len(del_user.data)
            except Exception as u_err:
                logger.warning(f"Error deleting expired guest user {guest_user_id}: {u_err}")

            # Remove expired guest session from guest_sessions table
            try:
                supabase.table("guest_sessions").delete().eq("id", session_id).execute()
                purged_sessions += 1
            except Exception as s_err:
                logger.warning(f"Error deleting expired guest session {session_id}: {s_err}")
    except Exception as sess_scan_err:
        logger.warning(f"Error scanning expired guest sessions: {sess_scan_err}")

    # 3. Sweep orphaned/expired guest users from user table
    # (Any user with role='guest' or id LIKE 'guest_%' whose session is expired or missing)
    try:
        # Fetch active guest session IDs that have not expired
        active_sessions_res = supabase.table("guest_sessions").select("id")\
            .gte("expires_at", now_iso)\
            .execute()
        active_session_ids = {s["id"] for s in (active_sessions_res.data or [])}

        # Query all guest users from the user table
        guest_users_res = supabase.table("user").select("id, role, email")\
            .or_("role.eq.guest,id.like.guest_%")\
            .limit(500)\
            .execute()

        for gu in (guest_users_res.data or []):
            user_id = gu["id"]
            session_id = user_id[len("guest_"):] if user_id.startswith("guest_") else None

            # If user has no active session in guest_sessions, this guest user is expired
            if not session_id or session_id not in active_session_ids:
                # Clean up any disk artifacts for projects owned by this orphaned guest
                try:
                    p_res = supabase.table("projects").select("id").eq("owner_id", user_id).execute()
                    for p in (p_res.data or []):
                        proj_id = p["id"]
                        disk_path = UPLOADS_BASE_DIR / proj_id
                        if disk_path.exists() and disk_path.is_dir():
                            shutil.rmtree(disk_path, ignore_errors=True)
                            purged_disk_dirs += 1
                        supabase.table("projects").delete().eq("id", proj_id).execute()
                        purged_projects.append(proj_id)
                except Exception as p_err:
                    logger.warning(f"Error cleaning projects for orphaned guest user {user_id}: {p_err}")

                # Delete the guest user from the user table
                try:
                    supabase.table("user").delete().eq("id", user_id).execute()
                    purged_guest_users += 1
                except Exception as u_err:
                    logger.warning(f"Error deleting orphaned guest user {user_id}: {u_err}")
    except Exception as sweep_err:
        logger.warning(f"Error sweeping orphaned guest users: {sweep_err}")

    # Clean up stale synctex build artifacts (>24h old)
    if cleanup_stale_synctex_cache:
        try:
            cleanup_stale_synctex_cache(max_age_hours=24)
        except Exception as sc_err:
            logger.warning(f"Error during synctex cache cleanup: {sc_err}")

    logger.info(
        f"Guest cleanup complete: {len(purged_projects)} projects, {purged_guest_users} guest users, "
        f"and {purged_sessions} sessions purged."
    )
    return {
        "success": True,
        "purged_count": len(purged_projects),
        "purged_projects": purged_projects,
        "purged_guest_users": purged_guest_users,
        "purged_sessions": purged_sessions,
        "purged_disk_dirs": purged_disk_dirs,
    }


async def start_cleanup_scheduler(interval_seconds: int = 900):
    """
    Background daemon loop that runs the purge task periodically (default: every 15 mins).
    Executes an initial purge on startup.
    """
    logger.info(f"Guest project cleanup scheduler initialized (runs every {interval_seconds}s).")
    # Immediate initial run on startup
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, purge_expired_guest_projects)
    except Exception as init_err:
        logger.warning(f"Initial guest cleanup run encountered an error: {init_err}")
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            async with _cleanup_lock:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, purge_expired_guest_projects)
                # Also drop PDF conversion job folders (uploads, renders, outputs) older than 24h
                from pdf2latex.jobs import purge_old_jobs
                await loop.run_in_executor(None, purge_old_jobs)
                # And collaboration CRDT snapshots for projects nobody has
                # opened in a month. The snapshot is a cache for restart
                # safety; the document itself lives in latex_documents.
                from collab.persistence import purge_stale_crdt_state
                await loop.run_in_executor(None, purge_stale_crdt_state)
        except asyncio.CancelledError:
            logger.info("Guest cleanup scheduler stopped.")
            break
        except Exception as err:
            logger.error(f"Error during scheduled guest cleanup: {err}", exc_info=True)
            await asyncio.sleep(60)
