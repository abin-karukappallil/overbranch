"""
storage.py — Writes conversion output into a project using the existing project
file mechanism (disk under UPLOADS_BASE_DIR + latex_documents rows), and creates
projects for dashboard / guest imports.

Existing files are never overwritten silently: writing the .tex file over a
non-empty file requires an explicit overwrite=True (the UI asks the user first).
Assets go into a per-job folder (assets/pdf_<id>/) so they cannot collide.
"""

import logging
import re
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from project_storage import get_project_disk_path, get_supabase_client, upsert_latex_document

logger = logging.getLogger("pdf2latex.storage")

TEXT_SUFFIXES = {".tex", ".sty", ".cls", ".bib", ".txt", ".md"}


class FileConflictError(Exception):
    def __init__(self, path: str):
        super().__init__(f"'{path}' already exists in the project and is not empty.")
        self.path = path


def _supabase():
    try:
        return get_supabase_client()
    except Exception as e:  # HTTPException when Supabase is not configured (local/tests)
        logger.warning(f"Supabase unavailable; writing project files to disk only: {e}")
        return None


def sanitize_target_path(path: str) -> str:
    p = (path or "main.tex").strip().lstrip("/\\")
    if not p.endswith(".tex") or ".." in Path(p).parts or not re.fullmatch(r"[\w\-./ ]+", p):
        raise ValueError("Target path must be a relative .tex path inside the project.")
    return p


def project_file_has_content(project_id: str, file_path: str) -> bool:
    """True if the project file exists with non-whitespace content (disk first, then DB)."""
    disk = get_project_disk_path(project_id, file_path)
    if disk.exists():
        try:
            return bool(disk.read_text(encoding="utf-8", errors="ignore").strip())
        except OSError:
            return True
    sb = _supabase()
    if sb is None:
        return False
    try:
        res = sb.table("latex_documents").select("raw_code").eq("project_id", project_id).eq("file_path", file_path).limit(1).execute()
        return bool(res.data and (res.data[0].get("raw_code") or "").strip())
    except Exception as e:
        logger.warning(f"Could not check existing project file: {e}")
        return False


def write_output_to_project(project_id: str, out_dir: Path, tex_name: str = "main.tex",
                            target_path: str = "main.tex", overwrite: bool = False) -> Dict[str, Any]:
    """
    Copies out_dir/<tex_name> to <target_path> and every other file under out_dir (assets)
    to the same relative path in the project. Raises FileConflictError when the target
    .tex has content and overwrite is False.
    """
    target_path = sanitize_target_path(target_path)
    if not overwrite and project_file_has_content(project_id, target_path):
        raise FileConflictError(target_path)

    sb = _supabase()
    written: List[str] = []
    assets: List[str] = []
    tex_src = out_dir / tex_name
    for src in sorted(p for p in out_dir.rglob("*") if p.is_file()):
        rel = src.relative_to(out_dir).as_posix()
        if src == tex_src:
            rel = target_path
        dest = get_project_disk_path(project_id, rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        if sb is not None:
            try:
                if src.suffix.lower() in TEXT_SUFFIXES:
                    upsert_latex_document(sb, project_id, rel, src.read_text(encoding="utf-8", errors="ignore"))
                else:
                    upsert_latex_document(sb, project_id, rel,
                                          f"[Binary Asset: {src.name}, Size: {src.stat().st_size} bytes]")
            except Exception as e:
                logger.warning(f"DB record for {rel} failed: {e}")
        (written if rel == target_path else assets).append(rel)
    return {"project_id": project_id, "tex_path": target_path, "files": written, "assets": assets}


def create_project_for_conversion(owner_id: str, name: Optional[str], filename: str,
                                  guest_session_id: Optional[str] = None) -> Dict[str, Any]:
    """Creates a project (and, for guests, the 24h guest_projects record) to import into."""
    project_id = str(uuid.uuid4())
    base = name or Path(filename or "Imported PDF").stem or "Imported PDF"
    clean_name = re.sub(r"[^\w\s\-().]", "", base).strip()[:80] or "Imported PDF"
    slug = re.sub(r"[^a-z0-9]+", "-", clean_name.lower()).strip("-") or "imported-pdf"

    # Seed an empty main.tex on disk, mirroring trpc projects.createProject
    main = get_project_disk_path(project_id, "main.tex")
    main.parent.mkdir(parents=True, exist_ok=True)
    main.write_text("", encoding="utf-8")

    sb = _supabase()
    if sb is None:
        return {"project_id": project_id, "name": clean_name}

    if owner_id.startswith("guest_"):
        try:
            from services.guest_identity import ensure_guest_user_row
            ensure_guest_user_row(sb, owner_id)
        except Exception as e:
            logger.warning(f"Could not ensure guest user row for {owner_id}: {e}")
    try:
        sb.table("projects").insert({
            "id": project_id,
            "owner_id": owner_id,
            "name": clean_name,
            "description": "Imported from PDF",
            "repository": f"prostack/{slug}",
            "default_branch": "main.tex",
            "language": "latex",
            "status": "active",
            "is_public": False,
            "is_favorite": False,
            "template": "PDF Import",
            "stars_count": 0,
        }).execute()
        sb.table("project_members").insert({
            "id": str(uuid.uuid4()), "project_id": project_id, "user_id": owner_id, "role": "Owner",
        }).execute()
    except Exception as e:
        logger.warning(f"Project row creation failed: {e}")

    if guest_session_id:
        now = datetime.now(timezone.utc)
        try:
            sb.table("guest_projects").insert({
                "id": str(uuid.uuid4()),
                "guest_session_id": guest_session_id,
                "project_id": project_id,
                "migrated_to_user_id": None,
                "migrated_at": None,
                "expires_at": (now + timedelta(hours=24)).isoformat(),
                "created_at": now.isoformat(),
            }).execute()
        except Exception as e:
            logger.warning(f"guest_projects record failed: {e}")
    return {"project_id": project_id, "name": clean_name}
