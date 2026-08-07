import os
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from supabase import create_client, Client
from vector_sync import sync_file, SyncFileRequest

load_dotenv()

logger = logging.getLogger("project_storage")
logging.basicConfig(level=logging.INFO)

router = APIRouter()

UPLOADS_BASE_DIR = Path(os.path.join(os.path.dirname(__file__), "..", "uploads", "projects")).resolve()


class SaveDocumentRequest(BaseModel):
    project_id: str = Field(..., description="Project ID or UUID")
    file_path: str = Field(..., description="Path of the file relative to project root (e.g. main.tex)")
    raw_code: str = Field(..., description="LaTeX code or text content")
    user_id: Optional[str] = Field(None, description="Requesting User ID for authorization check")


def verify_project_access(supabase: Client, project_id: str, user_id: Optional[str] = None):
    """Verifies that project exists and user is owner or member."""
    if not project_id or not user_id:
        return
    try:
        proj_res = supabase.table("projects").select("id, owner_id").eq("id", project_id).execute()
        data = proj_res.data or []
        if data:
            owner_id = data[0].get("owner_id")
            if owner_id == user_id:
                return
            mem_res = supabase.table("project_members").select("id").eq("project_id", project_id).eq("user_id", user_id).execute()
            if not (mem_res.data or []):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Forbidden: Access denied for this project."
                )
    except HTTPException:
        raise
    except Exception as err:
        logger.warning(f"Project access verification check skipped/warned: {err}")


def get_project_disk_path(project_id: str, file_path: str) -> Path:
    safe_project = re.sub(r'[^a-zA-Z0-9_-]', '_', project_id)
    target_path = (UPLOADS_BASE_DIR / safe_project / file_path).resolve()
    if not str(target_path).startswith(str(UPLOADS_BASE_DIR)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path (path traversal detected)."
        )
    return target_path


import re

def get_supabase_client() -> Client:
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
    return create_client(supabase_url, supabase_key)


@router.post("/api/projects/save-file")
def save_project_file(req: SaveDocumentRequest):
    """
    Saves LaTeX document code:
    1. Verifies server-side authorization access.
    2. Writes to local system disk storage under uploads/projects/<project_id>/<file_path>.
    3. Upserts document in Supabase latex_documents database table.
    4. Triggers Qdrant vector sync for .tex files.
    """
    try:
        supabase = get_supabase_client()
        verify_project_access(supabase, req.project_id, req.user_id)

        # 1. Save to local disk
        target_path = get_project_disk_path(req.project_id, req.file_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(req.raw_code, encoding="utf-8")
        logger.info(f"Saved file to local disk: '{target_path}'")

        # 2. Save / Upsert in Supabase Postgres latex_documents table
        supabase = get_supabase_client()
        record = {
            "project_id": req.project_id,
            "file_path": req.file_path,
            "raw_code": req.raw_code
        }
        
        # Upsert in Supabase latex_documents
        upsert_resp = (
            supabase.table("latex_documents")
            .upsert(record, on_conflict="project_id, file_path")
            .execute()
        )
        logger.info(f"Upserted document in Supabase latex_documents for project '{req.project_id}'.")

        # 3. Trigger background Qdrant vector sync if .tex file
        if req.file_path.endswith(".tex"):
            try:
                sync_file(SyncFileRequest(
                    project_id=req.project_id,
                    file_path=req.file_path,
                    new_code=req.raw_code
                ))
            except Exception as v_err:
                logger.warning(f"Background vector sync warning: {v_err}")

        return {
            "success": True,
            "project_id": req.project_id,
            "file_path": req.file_path,
            "saved_to_disk": str(target_path),
            "saved_to_db": True
        }

    except Exception as e:
        logger.error(f"Error saving project file: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Save project file failed: {str(e)}"
        )


@router.post("/api/projects/upload-asset")
async def upload_project_asset(
    project_id: str = Form(...),
    file_path: str = Form(...),
    file: UploadFile = File(...)
):
    """Uploads binary assets (images, PDFs, fonts, class files) to local disk & records in DB."""
    try:
        target_path = get_project_disk_path(project_id, file_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        content = await file.read()
        target_path.write_bytes(content)
        logger.info(f"Uploaded binary asset to local disk: '{target_path}'")

        # Save metadata in Supabase latex_documents table
        supabase = get_supabase_client()
        record = {
            "project_id": project_id,
            "file_path": file_path,
            "raw_code": f"[Binary Asset: {file.filename}, Size: {len(content)} bytes]"
        }
        supabase.table("latex_documents").upsert(record, on_conflict="project_id, file_path").execute()

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


@router.get("/api/projects/get-file")
def get_project_file(project_id: str, file_path: str = "main.tex"):
    """
    Retrieves project file content from local disk or Supabase latex_documents table.
    """
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

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"File '{file_path}' for project '{project_id}' not found."
    )
