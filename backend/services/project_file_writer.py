"""
project_file_writer.py — Project File and Asset Writer

Persists converted LaTeX project files and extracted assets:
1. Writes files to disk under uploads/projects/<project_id>/
2. Creates assets/ folder and saves extracted images
3. Upserts file records into Supabase latex_documents table
4. For new projects: inserts projects and project_members records
5. Syncs .tex files with Qdrant vector database
"""

import os
import re
import uuid
import shutil
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from .pdf_to_latex import ConversionResult, ProjectFile, AssetFile
from project_storage import (
    UPLOADS_BASE_DIR,
    get_project_disk_path,
    get_supabase_client,
    upsert_latex_document,
)
from vector_sync import sync_file, SyncFileRequest

logger = logging.getLogger("project_file_writer")


def sanitize_project_name(name: str) -> str:
    """Cleans project name to a friendly format."""
    clean = re.sub(r'[\r\n\t]+', ' ', name).strip()
    return clean if clean else "PDF_Converted_Project"


def slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')


def write_project_files_and_assets(
    project_id: str,
    conversion: ConversionResult,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Writes all files from ConversionResult to disk and database for a given project_id.
    Creates assets/ folder for embedded images.
    Returns list of written file paths and asset paths.
    """
    safe_project = re.sub(r'[^a-zA-Z0-9_-]', '_', project_id)
    project_dir = UPLOADS_BASE_DIR / safe_project
    project_dir.mkdir(parents=True, exist_ok=True)

    assets_dir = project_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    supabase = get_supabase_client()
    written_files = []
    written_assets = []

    # 1. Write text / LaTeX files
    for pfile in conversion.files:
        clean_path = pfile.path.lstrip("/\\")
        target_path = get_project_disk_path(project_id, clean_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        target_path.write_text(pfile.content, encoding="utf-8")
        written_files.append(clean_path)

        # Upsert in database
        try:
            upsert_latex_document(supabase, project_id, clean_path, pfile.content)
        except Exception as db_err:
            logger.warning(f"Database upsert error for {clean_path}: {db_err}")

        # Vector sync for .tex files
        if clean_path.endswith(".tex"):
            try:
                sync_file(SyncFileRequest(
                    project_id=project_id,
                    file_path=clean_path,
                    new_code=pfile.content,
                ))
            except Exception as v_err:
                logger.warning(f"Vector sync error for {clean_path}: {v_err}")

    # 2. Write binary image assets
    for asset in conversion.assets:
        clean_fn = asset.filename.lstrip("/\\")
        # Ensure it sits in assets/
        if clean_fn.startswith("assets/"):
            rel_asset_path = clean_fn
        else:
            rel_asset_path = f"assets/{clean_fn}"

        target_asset_path = get_project_disk_path(project_id, rel_asset_path)
        target_asset_path.parent.mkdir(parents=True, exist_ok=True)
        target_asset_path.write_bytes(asset.data_bytes)
        written_assets.append(rel_asset_path)

        # Also write directly to root project dir if references use bare filename
        bare_name = Path(clean_fn).name
        if bare_name != rel_asset_path:
            try:
                shutil.copy2(target_asset_path, project_dir / bare_name)
            except Exception:
                pass

        # Record asset metadata in DB
        try:
            asset_meta = f"[Binary Asset: {clean_fn}, Size: {len(asset.data_bytes)} bytes]"
            upsert_latex_document(supabase, project_id, rel_asset_path, asset_meta)
        except Exception as db_err:
            logger.warning(f"Database asset record error for {rel_asset_path}: {db_err}")

    logger.info(
        f"Project '{project_id}' updated: {len(written_files)} files written, "
        f"{len(written_assets)} assets saved in assets/."
    )

    return {
        "project_id": project_id,
        "files": written_files,
        "assets": written_assets,
    }


def create_new_project_from_conversion(
    conversion: ConversionResult,
    user_id: str,
    project_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates a new project in Supabase and writes all converted files and assets.
    Used by the Dashboard PDF Import flow.
    """
    supabase = get_supabase_client()
    project_id = str(uuid.uuid4())
    member_id = str(uuid.uuid4())

    name = sanitize_project_name(project_name or f"PDF_{conversion.document_class.title()}_{project_id[:6]}")
    repo_slug = f"prostack/{slugify(name)}"

    # 1. Insert into Supabase projects table
    proj_record = {
        "id": project_id,
        "owner_id": user_id,
        "name": name,
        "description": f"Editable LaTeX generated from PDF ({conversion.document_class})",
        "repository": repo_slug,
        "default_branch": "main.tex",
        "language": "latex",
        "status": "active",
        "is_public": False,
        "is_favorite": False,
        "template": conversion.document_class.title(),
        "stars_count": 0,
    }

    try:
        supabase.table("projects").insert(proj_record).execute()
        # 2. Insert into project_members table
        member_record = {
            "id": member_id,
            "project_id": project_id,
            "user_id": user_id,
            "role": "Owner",
        }
        supabase.table("project_members").insert(member_record).execute()
    except Exception as db_err:
        logger.error(f"Failed to create project in database: {db_err}", exc_info=True)
        raise RuntimeError(f"Database project creation failed: {str(db_err)}")

    # 3. Write files and assets
    write_result = write_project_files_and_assets(
        project_id=project_id,
        conversion=conversion,
        user_id=user_id,
    )

    return {
        "success": True,
        "project_id": project_id,
        "name": name,
        "document_class": conversion.document_class,
        "files": write_result["files"],
        "assets": write_result["assets"],
    }
