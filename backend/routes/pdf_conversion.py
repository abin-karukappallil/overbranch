"""
pdf_conversion.py — FastAPI Router for PDF to Editable LaTeX Conversion

Provides two primary entry points:
1. POST /api/pdf/convert — Dashboard import: parses PDF, synthesizes LaTeX, creates new project, streams progress SSE
2. POST /api/pdf/convert-in-project — In-editor conversion: updates current project, saves into assets/, streams progress SSE
"""

import json
import logging
import asyncio
from typing import Set, Dict, Any, Optional
from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from services.pdf_parser import parse_pdf, MAX_ALLOWED_PAGES
from services.pdf_to_latex import convert_pdf_to_latex
from services.project_file_writer import (
    write_project_files_and_assets,
    create_new_project_from_conversion,
)
from project_storage import get_supabase_client
from auth import get_current_user, get_current_user_or_guest, verify_project_ownership_or_member
from models import User
from rate_limiter import RateLimiter

logger = logging.getLogger("pdf_conversion")
router = APIRouter(prefix="/api/pdf", tags=["pdf_conversion"])

# Concurrency lock: prevent multiple simultaneous conversions per user
_active_user_conversions: Set[str] = set()
_lock = asyncio.Lock()


class ConvertPDFRequest(BaseModel):
    pdf_data: str = Field(..., description="Base64-encoded PDF or data URL")
    project_name: Optional[str] = Field(None, description="Optional custom name for new project")
    user_id: Optional[str] = Field(None, description="Requesting User ID")
    document_type_hint: Optional[str] = Field(None, description="Optional document type override (beamer, article, report)")
    model: Optional[str] = Field(None, description="Optional target LLM model")


class ConvertInProjectRequest(BaseModel):
    pdf_data: str = Field(..., description="Base64-encoded PDF or data URL")
    project_id: str = Field(..., description="Target project UUID")
    user_id: Optional[str] = Field(None, description="Requesting User ID")
    document_type_hint: Optional[str] = Field(None, description="Optional document type override (beamer, article, report)")
    model: Optional[str] = Field(None, description="Optional target LLM model")


def format_sse(event_type: str, data: Dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


@router.post(
    "/convert",
    dependencies=[Depends(RateLimiter(times=10, seconds=60, key_prefix="rl_pdf_convert"))],
)
async def convert_pdf_to_new_project(
    request: Request,
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    """
    Dashboard Entry Point:
    Uploads a PDF, converts it into an editable LaTeX project, creates the project in Supabase,
    and streams SSE progress events.
    Supports authenticated Better Auth user sessions and verified guest sessions.
    """
    try:
        body = await request.body()
        if len(body) > 100 * 1024 * 1024:
            return JSONResponse(status_code=413, content={"detail": "PDF file too large. Maximum size is 100MB."})
        data = json.loads(body)
        req = ConvertPDFRequest(**data)
    except json.JSONDecodeError as e:
        return JSONResponse(status_code=400, content={"detail": f"Invalid JSON payload: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=422, content={"detail": f"Validation error: {str(e)}"})

    # Extract user ID and guest status from auth dependency
    user_id = auth_info["user_id"]
    is_guest = bool(auth_info.get("is_guest"))

    # Enforce single concurrent conversion per user
    async with _lock:
        if user_id in _active_user_conversions:
            return JSONResponse(
                status_code=429,
                content={"detail": "A PDF conversion is already running for your account. Please wait for it to finish."},
            )
        _active_user_conversions.add(user_id)

    async def sse_stream():
        try:
            yield format_sse("progress", {"step": "uploading", "message": "Reading and validating PDF document...", "pct": 10})

            # 1. Parse PDF with PyMuPDF
            yield format_sse("progress", {"step": "analyzing", "message": "Analyzing pages, fonts, layout, and equations...", "pct": 25})
            loop = asyncio.get_running_loop()

            try:
                parse_result = await loop.run_in_executor(
                    None,
                    lambda: parse_pdf(
                        req.pdf_data,
                        render_300dpi=True,
                        render_150dpi=True,
                        max_pages=MAX_ALLOWED_PAGES,
                        doc_type_override=req.document_type_hint,
                    )
                )
            except ValueError as ve:
                yield format_sse("error", {"message": str(ve)})
                return
            except Exception as pe:
                logger.error(f"Error parsing PDF: {pe}", exc_info=True)
                yield format_sse("error", {"message": f"Failed to parse PDF: {str(pe)}"})
                return

            # 2. Extract assets notice
            img_count = len(parse_result.embedded_images)
            asset_msg = f"Extracted {img_count} image figures into assets/ directory" if img_count > 0 else "No embedded raster images detected"
            yield format_sse("progress", {"step": "extracting_assets", "message": asset_msg, "pct": 40, "asset_count": img_count})

            # 3. Generate LaTeX with LLM + compilation auto-repair
            progress_queue = asyncio.Queue()

            def sync_progress_cb(step: str, message: str):
                progress_queue.put_nowait((step, message))

            conversion_task = loop.run_in_executor(
                None,
                lambda: convert_pdf_to_latex(
                    parse_result=parse_result,
                    model=req.model,
                    progress_callback=sync_progress_cb,
                    auto_repair=True,
                )
            )

            # Stream intermediate LLM progress while conversion runs
            while not conversion_task.done():
                try:
                    step, msg = await asyncio.wait_for(progress_queue.get(), timeout=1.5)
                    yield format_sse("progress", {"step": step, "message": msg, "pct": 65})
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"

            conversion_result = await conversion_task

            # 4. Create new project and save files
            yield format_sse("progress", {"step": "creating_project", "message": "Creating project workspace and writing files...", "pct": 90})

            created = await loop.run_in_executor(
                None,
                lambda: create_new_project_from_conversion(
                    conversion=conversion_result,
                    user_id=user_id,
                    project_name=req.project_name,
                )
            )

            new_project_id = created.get("project_id")

            # If guest, record in guest_projects table
            guest_token = None
            if is_guest:
                from datetime import datetime, timedelta, timezone
                import uuid
                from services.guest_identity import sign_guest_token
                session_id = auth_info.get("session_id") or user_id.replace("guest_", "")
                guest_token = sign_guest_token(session_id)
                now_utc = datetime.now(timezone.utc)
                expires_at_dt = now_utc + timedelta(hours=24)
                try:
                    sb = get_supabase_client()
                    guest_proj_record = {
                        "id": str(uuid.uuid4()),
                        "guest_session_id": session_id,
                        "project_id": new_project_id,
                        "migrated_to_user_id": None,
                        "migrated_at": None,
                        "expires_at": expires_at_dt.isoformat(),
                        "created_at": now_utc.isoformat(),
                    }
                    sb.table("guest_projects").insert(guest_proj_record).execute()
                except Exception as gp_err:
                    logger.warning(f"Error recording guest project in database: {gp_err}")

            # Surface visual fidelity report event
            yield format_sse("fidelity_score", {
                "fidelity_score": getattr(conversion_result, "fidelity_score", 1.0),
                "defects": getattr(conversion_result, "fidelity_defects", []),
                "flagged_pages": getattr(conversion_result, "flagged_pages", []),
                "page_fidelity_scores": getattr(conversion_result, "page_fidelity_scores", {}),
            })

            progress_done_payload = {
                "step": "done",
                "message": "Project created successfully! Opening editor...",
                "pct": 100,
                "project_id": new_project_id,
            }
            if guest_token:
                progress_done_payload["guest_token"] = guest_token
            yield format_sse("progress", progress_done_payload)

            # Final payload with project info
            result_payload = {
                "success": True,
                "project_id": new_project_id,
                "name": created.get("name"),
                "document_class": created.get("document_class"),
                "files": created.get("files", []),
                "assets": created.get("assets", []),
                "compiled_successfully": getattr(conversion_result, "compiled_successfully", False),
                "compile_log": conversion_result.compile_log[:500] if getattr(conversion_result, "compile_log", None) else "",
                "fidelity_score": getattr(conversion_result, "fidelity_score", 1.0),
                "flagged_pages": getattr(conversion_result, "flagged_pages", []),
                "page_fidelity_scores": getattr(conversion_result, "page_fidelity_scores", {}),
                "is_guest": is_guest,
            }
            if guest_token:
                result_payload["guest_token"] = guest_token
            yield format_sse("result", result_payload)

        except Exception as e:
            logger.error(f"Error in PDF conversion pipeline: {e}", exc_info=True)
            yield format_sse("error", {"message": f"Conversion failed: {str(e)}"})
        finally:
            async with _lock:
                _active_user_conversions.discard(user_id)

    return StreamingResponse(
        sse_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/convert-in-project",
    dependencies=[Depends(RateLimiter(times=10, seconds=60, key_prefix="rl_pdf_convert_in_proj"))],
)
async def convert_in_project(
    request: Request,
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    """
    In-Editor Entry Point:
    Uploads a PDF from within an existing open project, converts it into LaTeX,
    overwrites or merges main.tex, saves any extracted figures into the project's assets/ directory,
    and streams SSE progress events.
    Requires an active Better Auth session or verified guest identity.
    """
    try:
        body = await request.body()
        if len(body) > 100 * 1024 * 1024:
            return JSONResponse(status_code=413, content={"detail": "PDF file too large. Maximum size is 100MB."})
        data = json.loads(body)
        req = ConvertInProjectRequest(**data)
    except json.JSONDecodeError as e:
        return JSONResponse(status_code=400, content={"detail": f"Invalid JSON payload: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=422, content={"detail": f"Validation error: {str(e)}"})

    user_id = auth_info.get("user_id")
    is_guest = bool(auth_info.get("is_guest"))

    try:
        sb = get_supabase_client()
        verify_project_ownership_or_member(sb, req.project_id, user_id, is_guest=is_guest)
    except HTTPException as he:
        return JSONResponse(status_code=he.status_code, content={"detail": he.detail})
    except Exception as e:
        logger.warning(f"Project access check error in convert_in_project: {e}")

    async with _lock:
        if user_id in _active_user_conversions:
            return JSONResponse(
                status_code=429,
                content={"detail": "A conversion is already running for your account. Please wait for it to finish."},
            )
        _active_user_conversions.add(user_id)

    async def sse_stream():
        try:
            yield format_sse("progress", {"step": "uploading", "message": "Reading attached PDF...", "pct": 10})

            loop = asyncio.get_running_loop()

            # 1. Parse PDF
            yield format_sse("progress", {"step": "analyzing", "message": "Analyzing document structure and layout...", "pct": 25})
            try:
                parse_result = await loop.run_in_executor(
                    None,
                    lambda: parse_pdf(req.pdf_data, render_300dpi=True, render_150dpi=True, max_pages=MAX_ALLOWED_PAGES)
                )
            except ValueError as ve:
                yield format_sse("error", {"message": str(ve)})
                return
            except Exception as pe:
                yield format_sse("error", {"message": f"Failed to parse PDF: {str(pe)}"})
                return

            img_count = len(parse_result.embedded_images)
            yield format_sse("progress", {"step": "extracting_assets", "message": f"Extracted {img_count} figures for assets/ directory", "pct": 40})

            # 2. Convert to LaTeX
            progress_queue = asyncio.Queue()

            def sync_progress_cb(step: str, message: str):
                progress_queue.put_nowait((step, message))

            conversion_task = loop.run_in_executor(
                None,
                lambda: convert_pdf_to_latex(
                    parse_result=parse_result,
                    model=req.model,
                    progress_callback=sync_progress_cb,
                    auto_repair=True,
                )
            )

            while not conversion_task.done():
                try:
                    step, msg = await asyncio.wait_for(progress_queue.get(), timeout=1.5)
                    yield format_sse("progress", {"step": step, "message": msg, "pct": 65})
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"

            conversion_result = await conversion_task

            # 3. Write files directly to current project
            yield format_sse("progress", {"step": "writing_files", "message": "Writing files and assets to project workspace...", "pct": 90})

            written = await loop.run_in_executor(
                None,
                lambda: write_project_files_and_assets(
                    project_id=req.project_id,
                    conversion=conversion_result,
                    user_id=user_id,
                )
            )

            # Surface visual fidelity report event
            yield format_sse("fidelity_score", {
                "fidelity_score": getattr(conversion_result, "fidelity_score", 1.0),
                "defects": getattr(conversion_result, "fidelity_defects", []),
                "flagged_pages": getattr(conversion_result, "flagged_pages", []),
                "page_fidelity_scores": getattr(conversion_result, "page_fidelity_scores", {}),
            })

            yield format_sse("progress", {"step": "done", "message": "Project files and assets updated successfully!", "pct": 100})

            yield format_sse("result", {
                "success": True,
                "project_id": req.project_id,
                "main_tex_content": main_content,
                "document_class": getattr(conversion_result, "document_class", "article"),
                "files": written.get("files", []),
                "assets": written.get("assets", []),
                "compiled_successfully": getattr(conversion_result, "compiled_successfully", False),
                "compile_log": conversion_result.compile_log[:500] if getattr(conversion_result, "compile_log", None) else "",
                "fidelity_score": getattr(conversion_result, "fidelity_score", 1.0),
                "flagged_pages": getattr(conversion_result, "flagged_pages", []),
                "page_fidelity_scores": getattr(conversion_result, "page_fidelity_scores", {}),
            })

        except Exception as e:
            logger.error(f"Error updating project from PDF: {e}", exc_info=True)
            yield format_sse("error", {"message": f"Conversion failed: {str(e)}"})
        finally:
            async with _lock:
                _active_user_conversions.discard(user_id)

    return StreamingResponse(
        sse_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
