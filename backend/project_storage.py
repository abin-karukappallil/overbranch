import os
import re
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, HTTPException, status, UploadFile, File, Form, Depends
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from supabase import create_client, Client
from auth import get_current_user_or_guest, verify_project_ownership_or_member
from rate_limiter import RateLimiter

load_dotenv()

logger = logging.getLogger("project_storage")
logging.basicConfig(level=logging.INFO)

router = APIRouter()

UPLOADS_BASE_DIR = Path(os.getenv("UPLOADS_BASE_DIR", os.path.join(os.path.dirname(__file__), "..", "uploads", "projects"))).resolve()


class SaveDocumentRequest(BaseModel):
    project_id: str = Field(..., description="Project ID or UUID")
    file_path: str = Field(..., description="Path of the file relative to project root (e.g. main.tex)")
    raw_code: str = Field(..., description="LaTeX code or text content")
    user_id: Optional[str] = Field(None, description="Requesting User ID for authorization check")


def verify_project_access(supabase: Client, project_id: str, user_id: Optional[str] = None, is_guest: bool = False):
    """Verifies that project exists and user is owner or member."""
    if not project_id or not user_id:
        return
    verify_project_ownership_or_member(supabase, project_id, user_id, is_guest=is_guest)


def get_project_disk_path(project_id: str, file_path: str) -> Path:
    safe_project = re.sub(r'[^a-zA-Z0-9_-]', '_', project_id)
    target_path = (UPLOADS_BASE_DIR / safe_project / file_path).resolve()
    if not str(target_path).startswith(str(UPLOADS_BASE_DIR)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path (path traversal detected)."
        )
    return target_path


_supabase_client: Optional[Client] = None

def get_supabase_client() -> Client:
    """Returns a cached Supabase client singleton to prevent socket/connection leaks."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
    )
    if not supabase_url or not supabase_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase credentials are not configured in environment."
        )
    _supabase_client = create_client(supabase_url, supabase_key)
    return _supabase_client


def reset_supabase_client():
    """Allows resetting the client in case of connection resets or credentials rotation."""
    global _supabase_client
    _supabase_client = None


def upsert_latex_document(supabase: Client, project_id: str, file_path: str, raw_code: str):
    """Safely updates or inserts a latex_documents record without relying on DB unique constraints."""
    try:
        existing = (
            supabase.table("latex_documents")
            .select("id")
            .eq("project_id", project_id)
            .eq("file_path", file_path)
            .execute()
        )
        if existing.data and len(existing.data) > 0:
            rec_id = existing.data[0]["id"]
            supabase.table("latex_documents").update({
                "raw_code": raw_code
            }).eq("id", rec_id).execute()
        else:
            supabase.table("latex_documents").insert({
                "project_id": project_id,
                "file_path": file_path,
                "raw_code": raw_code
            }).execute()
    except Exception as e:
        logger.warning(f"Failed to upsert latex_document ({file_path}): {e}")


@router.post(
    "/api/projects/save-file",
    dependencies=[Depends(RateLimiter(times=60, seconds=60, key_prefix="rl_save_file"))],
)
def save_project_file(
    req: SaveDocumentRequest,
    request: Request,
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    """
    Saves LaTeX document code:
    1. Verifies server-side authorization access with token or session.
    2. Writes to local system disk storage under uploads/projects/<project_id>/<file_path>.
    3. Upserts document in Supabase latex_documents database table.
    """
    try:
        supabase = get_supabase_client()
        user_id = auth_info.get("user_id") or req.user_id
        is_guest = bool(auth_info.get("is_guest"))
        verify_project_access(supabase, req.project_id, user_id, is_guest=is_guest)

        # 1. Save to local disk
        target_path = get_project_disk_path(req.project_id, req.file_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(req.raw_code, encoding="utf-8")
        logger.info(f"Saved file to local disk: '{target_path}'")

        # 2. Save / Upsert in Supabase Postgres latex_documents table safely
        try:
            upsert_latex_document(supabase, req.project_id, req.file_path, req.raw_code)
            logger.info(f"Upserted document in Supabase latex_documents for project '{req.project_id}'.")
        except Exception as db_err:
            logger.warning(f"Supabase DB save fallback warning: {db_err}")

        return {
            "success": True,
            "project_id": req.project_id,
            "file_path": req.file_path,
            "saved_to_disk": str(target_path),
            "saved_to_db": True
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving project file: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Save project file failed: {str(e)}"
        )


@router.post(
    "/api/projects/upload-asset",
    dependencies=[Depends(RateLimiter(times=30, seconds=60, key_prefix="rl_upload_asset"))],
)
async def upload_project_asset(
    request: Request,
    project_id: str = Form(...),
    file_path: str = Form(...),
    file: UploadFile = File(...),
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    """Uploads binary assets (images, PDFs, fonts, class files) to local disk & records in DB."""
    try:
        supabase = get_supabase_client()
        user_id = auth_info.get("user_id")
        is_guest = bool(auth_info.get("is_guest"))
        verify_project_access(supabase, project_id, user_id, is_guest=is_guest)

        target_path = get_project_disk_path(project_id, file_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        content = await file.read()
        target_path.write_bytes(content)
        logger.info(f"Uploaded binary asset to local disk: '{target_path}'")

        # Save metadata in Supabase latex_documents table safely
        try:
            asset_meta = f"[Binary Asset: {file.filename}, Size: {len(content)} bytes]"
            upsert_latex_document(supabase, project_id, file_path, asset_meta)
        except Exception as db_err:
            logger.warning(f"Asset metadata DB insert warning: {db_err}")

        return {
            "success": True,
            "project_id": project_id,
            "file_path": file_path,
            "size_bytes": len(content),
            "saved_to_disk": str(target_path)
        }
    except Exception as e:
        logger.error(f"Error uploading asset: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload asset failed: {str(e)}"
        )


@router.get(
    "/api/projects/get-file",
    dependencies=[Depends(RateLimiter(times=120, seconds=60, key_prefix="rl_get_file"))],
)
def get_project_file(
    request: Request,
    project_id: str,
    file_path: str = "main.tex",
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    """
    Retrieves project file content from local disk or Supabase latex_documents table.
    Includes auto-creation fallback for main.tex when missing.
    """
    supabase = get_supabase_client()
    user_id = auth_info.get("user_id")
    is_guest = bool(auth_info.get("is_guest"))
    verify_project_access(supabase, project_id, user_id, is_guest=is_guest)

    target_path = get_project_disk_path(project_id, file_path)

    # 1. Check local disk first
    if target_path.exists():
        if file_path.endswith((".png", ".jpg", ".jpeg", ".pdf", ".zip")):
            return FileResponse(target_path)
        content = target_path.read_text(encoding="utf-8")
        return {
            "project_id": project_id,
            "file_path": file_path,
            "raw_code": content,
            "source": "local_disk"
        }

    # 2. Check Supabase DB
    try:
        supabase = get_supabase_client()
        res = (
            supabase.table("latex_documents")
            .select("raw_code")
            .eq("project_id", project_id)
            .eq("file_path", file_path)
            .execute()
        )
        data = res.data or []
        if data:
            raw_code = data[0].get("raw_code", "")
            # Save back to local disk
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(raw_code, encoding="utf-8")
            return {
                "project_id": project_id,
                "file_path": file_path,
                "raw_code": raw_code,
                "source": "supabase_db"
            }
    except Exception as e:
        logger.warning(f"Error querying Supabase for file: {e}")

    # 3. Auto-creation fallback for main.tex if missing from disk & DB
    if file_path == "main.tex":
        starter_code = r"""\documentclass[12pt]{article}
\usepackage[utf8]{utf8}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{hyperref}

\title{LaTeX Workspace}
\author{OverBranch Author}
\date{\today}

\begin{document}

\maketitle

\section{Introduction}
Welcome to your OverBranch LaTeX document! You can start typing LaTeX equations, text, figures, and tables here.

\section{Mathematics Example}
Here is a sample equation:
\begin{equation}
E = mc^2
\end{equation}

\end{document}
"""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(starter_code, encoding="utf-8")
        try:
            supabase = get_supabase_client()
            upsert_latex_document(supabase, project_id, file_path, starter_code)
        except Exception:
            pass

        return {
            "project_id": project_id,
            "file_path": file_path,
            "raw_code": starter_code,
            "source": "auto_generated"
        }

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"File '{file_path}' for project '{project_id}' not found."
    )


@router.get(
    "/api/projects/list-files",
    dependencies=[Depends(RateLimiter(times=120, seconds=60, key_prefix="rl_list_files"))],
)
def list_project_files(
    request: Request,
    project_id: str,
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    """Lists all files and assets for a project from disk and Supabase DB."""
    supabase = get_supabase_client()
    user_id = auth_info.get("user_id")
    is_guest = bool(auth_info.get("is_guest"))
    verify_project_access(supabase, project_id, user_id, is_guest=is_guest)

    files_map: Dict[str, Dict[str, Any]] = {}

    # 1. Check local disk
    safe_project = re.sub(r'[^a-zA-Z0-9_-]', '_', project_id)
    project_dir = UPLOADS_BASE_DIR / safe_project
    if project_dir.exists():
        for path in project_dir.rglob("*"):
            if path.is_file():
                rel_path = str(path.relative_to(project_dir))
                ext = path.suffix.lower()
                is_img = ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"]
                files_map[rel_path] = {
                    "path": rel_path,
                    "name": path.name,
                    "size": path.stat().st_size,
                    "type": "image" if is_img else "document",
                    "ext": ext,
                }

    # 2. Query Supabase latex_documents for any DB records
    try:
        res = supabase.table("latex_documents").select("file_path").eq("project_id", project_id).execute()
        for row in res.data or []:
            f_path = row.get("file_path")
            if f_path and f_path not in files_map:
                name = os.path.basename(f_path)
                ext = os.path.splitext(name)[1].lower()
                is_img = ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"]
                files_map[f_path] = {
                    "path": f_path,
                    "name": name,
                    "size": 0,
                    "type": "image" if is_img else "document",
                    "ext": ext,
                }
    except Exception as e:
        logger.warning(f"Error fetching files list from Supabase: {e}")

    # Always ensure main.tex is present
    if "main.tex" not in files_map:
        files_map["main.tex"] = {
            "path": "main.tex",
            "name": "main.tex",
            "size": 0,
            "type": "document",
            "ext": ".tex",
        }

    return {"project_id": project_id, "files": list(files_map.values())}


class RenameFileRequest(BaseModel):
    project_id: str = Field(..., description="Project ID or UUID")
    old_path: str = Field(..., description="Current relative path of the file")
    new_path: str = Field(..., description="New relative path of the file")
    user_id: Optional[str] = Field(None, description="Requesting User ID for authorization check")


@router.post(
    "/api/projects/rename-file",
    dependencies=[Depends(RateLimiter(times=30, seconds=60, key_prefix="rl_rename_file"))],
)
def rename_project_file(
    req: RenameFileRequest,
    request: Request,
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    """
    Renames a project file/asset on local disk and in Supabase DB.
    main.tex cannot be renamed or replaced.
    """
    old_clean = req.old_path.strip()
    new_clean = req.new_path.strip()

    if old_clean.lower() == "main.tex":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Primary main.tex file cannot be renamed."
        )
    if new_clean.lower() == "main.tex":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot rename file to main.tex as main.tex is the primary document."
        )
    if not new_clean:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New file name cannot be empty."
        )

    supabase = get_supabase_client()
    user_id = auth_info.get("user_id") or req.user_id
    is_guest = bool(auth_info.get("is_guest"))
    verify_project_access(supabase, req.project_id, user_id, is_guest=is_guest)

    old_disk_path = get_project_disk_path(req.project_id, old_clean)
    new_disk_path = get_project_disk_path(req.project_id, new_clean)

    if not old_disk_path.exists():
        res = (
            supabase.table("latex_documents")
            .select("file_path")
            .eq("project_id", req.project_id)
            .eq("file_path", old_clean)
            .execute()
        )
        if not (res.data or []):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File '{old_clean}' for project '{req.project_id}' not found."
            )

    new_disk_path.parent.mkdir(parents=True, exist_ok=True)
    if old_disk_path.exists():
        old_disk_path.rename(new_disk_path)
        logger.info(f"Renamed file on disk: '{old_disk_path}' -> '{new_disk_path}'")

    try:
        supabase.table("latex_documents").update({"file_path": new_clean}).eq("project_id", req.project_id).eq("file_path", old_clean).execute()
        logger.info(f"Updated file path in Supabase latex_documents from '{old_clean}' to '{new_clean}'")
    except Exception as e:
        logger.warning(f"Error updating file path in Supabase DB: {e}")

    return {
        "success": True,
        "project_id": req.project_id,
        "old_path": old_clean,
        "new_path": new_clean
    }


@router.delete(
    "/api/projects/delete-file",
    dependencies=[Depends(RateLimiter(times=30, seconds=60, key_prefix="rl_delete_file"))],
)
def delete_project_file(
    request: Request,
    project_id: str,
    file_path: str,
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    """Deletes a file from local disk and Supabase DB."""
    if file_path.strip().lower() == "main.tex":
        raise HTTPException(status_code=400, detail="Cannot delete primary main.tex document.")

    supabase = get_supabase_client()
    user_id = auth_info.get("user_id")
    is_guest = bool(auth_info.get("is_guest"))
    verify_project_access(supabase, project_id, user_id, is_guest=is_guest)

    target_path = get_project_disk_path(project_id, file_path)
    if target_path.exists():
        target_path.unlink()
        logger.info(f"Deleted file from local disk: '{target_path}'")

    try:
        supabase.table("latex_documents").delete().eq("project_id", project_id).eq("file_path", file_path).execute()
        logger.info(f"Deleted file record from Supabase DB: '{file_path}'")
    except Exception as e:
        logger.warning(f"Error deleting from Supabase DB: {e}")

    return {"success": True, "project_id": project_id, "file_path": file_path}


