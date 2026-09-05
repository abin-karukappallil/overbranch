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
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from services.pdf_parser import parse_pdf, MAX_ALLOWED_PAGES
from services.pdf_to_latex import convert_pdf_to_latex
from services.project_file_writer import (
    write_project_files_and_assets,
    create_new_project_from_conversion,
)
from project_storage import get_supabase_client

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


@router.post("/convert")
async def convert_pdf_to_new_project(request: Request):
    """
    Dashboard Entry Point:
    Uploads a PDF, converts it into an editable LaTeX project, creates the project in Supabase,
    and streams SSE progress events.
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

    # Determine user_id securely: Never steal or default to another user's ID!
    user_id = req.user_id or request.headers.get("x-user-id") or request.headers.get("X-User-Id")
    if not user_id:
        # Try resolving from better-auth session cookie
        auth_cookie = (
            request.cookies.get("__Secure-better-auth.session_token")
            or request.cookies.get("better-auth.session_token")
            or request.cookies.get("session_token")
        )
        if auth_cookie:
            try:
                sb = get_supabase_client()
                token = auth_cookie.split(".")[0]
                session_res = sb.table("session").select("user_id").eq("token", token).limit(1).execute()
                if session_res.data and session_res.data[0].get("user_id"):
                    user_id = session_res.data[0]["user_id"]
                    logger.info(f"Resolved user_id '{user_id}' from Better-Auth session cookie")
            except Exception as sess_err:
                logger.warning(f"Could not resolve user from session cookie: {sess_err}")

    # Fallback to guest identity or default-user
    if not user_id:
        guest_tok = request.cookies.get("ob_guest_token")
        if guest_tok:
            user_id = f"guest-{guest_tok[:16]}"
        else:
            user_id = "default-user"

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

            yield format_sse("progress", {"step": "done", "message": "Project created successfully! Opening editor...", "pct": 100})

            # Final payload with project info
            yield format_sse("result", {
                "success": True,
                "project_id": created["project_id"],
                "name": created["name"],
                "document_class": created["document_class"],
                "files": created["files"],
                "assets": created["assets"],
                "compiled_successfully": conversion_result.compiled_successfully,
                "compile_log": conversion_result.compile_log[:500] if conversion_result.compile_log else "",
            })

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


@router.post("/convert-in-project")
async def convert_pdf_in_existing_project(request: Request):
    """
    In-Editor Entry Point:
    Converts PDF and writes files directly into an existing project, updating main.tex,
    creating sections/, saving extracted images to assets/, and streaming progress events.
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

    user_id = req.user_id or "default-user"

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

            # Find main.tex content to send back to editor
            main_content = next((f.content for f in conversion_result.files if f.path == "main.tex"), "")

            yield format_sse("progress", {"step": "done", "message": "Project files and assets updated successfully!", "pct": 100})

            yield format_sse("result", {
                "success": True,
                "project_id": req.project_id,
                "main_tex_content": main_content,
                "document_class": conversion_result.document_class,
                "files": written["files"],
                "assets": written["assets"],
                "compiled_successfully": conversion_result.compiled_successfully,
                "compile_log": conversion_result.compile_log[:500] if conversion_result.compile_log else "",
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
