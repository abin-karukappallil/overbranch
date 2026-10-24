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

from project_storage import create_empty_project, get_project_disk_path, get_supabase_client, upsert_latex_document

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
    base = name or Path(filename or "Imported PDF").stem or "Imported PDF"
    return create_empty_project(owner_id, base, guest_session_id, template_tag="PDF Import")
