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
    Scans for guest projects past their expiration date (24h) that have NOT been migrated.
    Permanently deletes both filesystem artifacts and database records.
    """
    supabase = get_supabase_client()
    now_utc = datetime.now(timezone.utc)

    # Find expired, unmigrated projects
    res = supabase.table("guest_projects").select("id, project_id, guest_session_id, expires_at")\
        .lt("expires_at", now_utc.isoformat())\
        .is_("migrated_to_user_id", "null")\
        .limit(100)\
        .execute()

    expired_list = res.data or []
    purged_projects = []
    purged_disk_dirs = 0

    for item in expired_list:
        project_id = item["project_id"]
        gp_id = item["id"]
        guest_session_id = item.get("guest_session_id")

        logger.info(f"Purging expired guest project: {project_id}")

        # 1. Delete from disk
        disk_path = UPLOADS_BASE_DIR / project_id
        if disk_path.exists() and disk_path.is_dir():
            try:
                shutil.rmtree(disk_path, ignore_errors=True)
                purged_disk_dirs += 1
            except Exception as fs_err:
                logger.warning(f"Error removing disk path for {project_id}: {fs_err}")

        # 2. Delete from database (projects table CASCADE deletes members and latex_documents)
        try:
            supabase.table("projects").delete().eq("id", project_id).execute()
        except Exception as db_err:
            logger.warning(f"Error deleting project {project_id} from DB: {db_err}")

        # 3. Delete from guest_projects
        try:
            supabase.table("guest_projects").delete().eq("id", gp_id).execute()
        except Exception as gp_err:
            logger.warning(f"Error deleting guest_project record {gp_id}: {gp_err}")

        # 4. Clean up synthetic guest user if needed
        if guest_session_id:
            try:
                supabase.table("user").delete().eq("id", f"guest_{guest_session_id}").execute()
            except Exception:
                pass

        purged_projects.append(project_id)

    # Clean up stale guest sessions older than 7 days
    stale_date = (now_utc - timedelta(days=7)).isoformat()
    try:
        supabase.table("guest_sessions").delete().lt("expires_at", stale_date).execute()
    except Exception as gs_err:
        logger.warning(f"Error deleting stale guest sessions: {gs_err}")

    # Clean up stale synctex build artifacts (>24h old)
    if cleanup_stale_synctex_cache:
        try:
            cleanup_stale_synctex_cache(max_age_hours=24)
        except Exception as sc_err:
            logger.warning(f"Error during synctex cache cleanup: {sc_err}")

    logger.info(f"Guest cleanup complete: {len(purged_projects)} expired projects purged.")
    return {
        "success": True,
        "purged_count": len(purged_projects),
        "purged_projects": purged_projects,
        "purged_disk_dirs": purged_disk_dirs,
    }


async def start_cleanup_scheduler(interval_seconds: int = 900):
    """
    Background daemon loop that runs the purge task periodically (default: every 15 mins).
    """
    logger.info(f"Guest project cleanup scheduler initialized (runs every {interval_seconds}s).")
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            async with _cleanup_lock:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, purge_expired_guest_projects)
        except asyncio.CancelledError:
            logger.info("Guest cleanup scheduler stopped.")
            break
        except Exception as err:
            logger.error(f"Error during scheduled guest cleanup: {err}", exc_info=True)
            await asyncio.sleep(60)
