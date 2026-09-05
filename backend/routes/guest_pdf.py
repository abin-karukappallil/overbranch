"""
guest_pdf.py — FastAPI Router for Guest PDF to LaTeX Conversion & Session Management

Endpoints:
- POST /api/guest/pdf/convert — Public conversion endpoint with 24-hour quota enforcement
- GET  /api/guest/session     — Returns quota status, active guest project, and time remaining
- POST /api/guest/migrate     — Migrates guest project to authenticated user upon sign-up
- POST /api/guest/purge       — Triggers purge of expired (> 24h) guest projects
"""

import os
import json
import uuid
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Set, Dict, Any, Optional

from fastapi import APIRouter, Request, Response, HTTPException, status
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from services.guest_identity import (
    get_or_create_guest_session,
    compute_device_fingerprint,
    set_guest_cookie,
    GUEST_TOKEN_COOKIE_NAME,
    verify_guest_token,
    sign_guest_token,
)
from services.guest_quota import (
    check_guest_conversion_quota,
    consume_guest_conversion,
    get_guest_session_status,
)
from services.guest_migrator import migrate_guest_projects_to_user
from services.guest_cleanup import purge_expired_guest_projects
from services.pdf_parser import parse_pdf, MAX_ALLOWED_PAGES
from services.pdf_to_latex import convert_pdf_to_latex
from services.project_file_writer import create_new_project_from_conversion
from project_storage import get_supabase_client

logger = logging.getLogger("guest_pdf")
router = APIRouter(prefix="/api/guest", tags=["guest_pdf"])

_active_guest_conversions: Set[str] = set()
_lock = asyncio.Lock()


class GuestConvertRequest(BaseModel):
    pdf_data: str = Field(..., description="Base64-encoded PDF or data URL")
    project_name: Optional[str] = Field(None, description="Optional custom name for new project")
    model: Optional[str] = Field(None, description="Optional target LLM model")
    user_id: Optional[str] = Field(None, description="Optional authenticated User ID")


class GuestMigrateRequest(BaseModel):
    user_id: str = Field(..., description="Target authenticated User ID")
    guest_token: Optional[str] = Field(None, description="Optional explicit guest token (falls back to cookie)")


def format_sse(event_type: str, data: Dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


@router.get("/session")
async def get_session_info(request: Request):
    """Returns guest quota, active project, and countdown timer for the current device."""
    try:
        session, token, is_new = get_or_create_guest_session(request)
        fingerprint = compute_device_fingerprint(request)
        status_info = get_guest_session_status(session, fingerprint)
        status_info["token"] = token
        status_info["is_new"] = is_new

        response = JSONResponse(content=status_info)
        set_guest_cookie(response, token, request)
        return response
    except Exception as e:
        logger.error(f"Error fetching guest session: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": f"Failed to retrieve guest session: {str(e)}"})


@router.post("/pdf/convert")
async def convert_guest_pdf(request: Request):
    """
    Public conversion endpoint:
    1. Authenticates/establishes guest session
    2. Enforces strict 24-hour quota (1 conversion / 24h) for anonymous guests
    3. Converts PDF to LaTeX project owned by guest synthetic user or authenticated user
    4. Records project in guest_projects with 24-hour expiration
    5. Sets HttpOnly cookie and streams SSE progress
    """
    try:
        body = await request.body()
        if len(body) > 100 * 1024 * 1024:
            return JSONResponse(status_code=413, content={"detail": "PDF file too large. Maximum size is 100MB."})
        data = json.loads(body)
        req = GuestConvertRequest(**data)
    except json.JSONDecodeError as e:
        return JSONResponse(status_code=400, content={"detail": f"Invalid JSON payload: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=422, content={"detail": f"Validation error: {str(e)}"})

    # Check if this request is from an authenticated user
    auth_user_id = req.user_id or request.headers.get("x-user-id") or request.headers.get("X-User-Id")
    if not auth_user_id:
        auth_cookie = (
            request.cookies.get("__Secure-better-auth.session_token")
            or request.cookies.get("better-auth.session_token")
            or request.cookies.get("session_token")
        )
        if auth_cookie:
            try:
                sb = get_supabase_client()
                tok = auth_cookie.split(".")[0]
                session_res = sb.table("session").select("user_id").eq("token", tok).limit(1).execute()
                if session_res.data and session_res.data[0].get("user_id"):
                    auth_user_id = session_res.data[0]["user_id"]
                    logger.info(f"guest_pdf: resolved authenticated user '{auth_user_id}'")
            except Exception as sess_err:
                logger.warning(f"Could not resolve session in guest_pdf: {sess_err}")

    # 1. Establish guest session & fingerprint
    session, token, _ = get_or_create_guest_session(request)
    fingerprint = compute_device_fingerprint(request)
    session_id = session["id"]
    guest_user_id = f"guest_{session_id}"
    effective_user_id = auth_user_id if auth_user_id else guest_user_id

    # 2. Check quota only for unauthenticated guest sessions
    if not auth_user_id:
        allowed, used, resets_at, reason = check_guest_conversion_quota(session, fingerprint)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": reason or "Guest conversion limit reached (1 conversion per 24 hours).",
                    "resets_at": resets_at.isoformat() if resets_at else None,
                    "conversions_used": used,
                    "limit": 1,
                },
            )
                "detail": reason or "Guest conversion limit reached (1 conversion per 24 hours).",
                "resets_at": resets_at.isoformat() if resets_at else None,
                "conversions_used": used,
                "limit": 1,
            },
        )

    # 3. Prevent duplicate concurrent conversions on this session
    async with _lock:
        if session_id in _active_guest_conversions:
            return JSONResponse(
                status_code=429,
                content={"detail": "A conversion is already running on this device. Please wait for it to complete."},
            )
        _active_guest_conversions.add(session_id)

    async def sse_stream():
        try:
            yield format_sse("progress", {"step": "uploading", "message": "Validating PDF & establishing secure guest session...", "pct": 10})

            # Consume quota upfront
            consume_guest_conversion(session_id)

            # 1. Parse PDF with PyMuPDF
            yield format_sse("progress", {"step": "analyzing", "message": "Extracting text, formulas, layout, and document structure...", "pct": 25})
            loop = asyncio.get_running_loop()

            try:
                parse_result = await loop.run_in_executor(
                    None,
                    lambda: parse_pdf(req.pdf_data, render_300dpi=True, render_150dpi=True, max_pages=MAX_ALLOWED_PAGES)
                )
            except ValueError as ve:
                yield format_sse("error", {"message": str(ve)})
                return
            except Exception as pe:
                logger.error(f"Error parsing PDF: {pe}", exc_info=True)
                yield format_sse("error", {"message": f"Failed to parse PDF: {str(pe)}"})
                return

            # 2. Figures notice
            img_count = len(parse_result.embedded_images)
            asset_msg = f"Extracted {img_count} figures and diagrams into project assets" if img_count > 0 else "Document layout parsed successfully"
            yield format_sse("progress", {"step": "extracting_assets", "message": asset_msg, "pct": 40, "asset_count": img_count})

            # 3. Generate LaTeX with LLM
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

            # 4. Create new project with owner
            proj_msg = f"Provisioning {'authenticated' if auth_user_id else 'temporary guest'} workspace..."
            yield format_sse("progress", {"step": "creating_project", "message": proj_msg, "pct": 90})

            created = await loop.run_in_executor(
                None,
                lambda: create_new_project_from_conversion(
                    conversion=conversion_result,
                    user_id=effective_user_id,
                    project_name=req.project_name,
                )
            )

            project_id = created["project_id"]

            # 5. Insert into guest_projects table with 24-hour expiration
            now_utc = datetime.now(timezone.utc)
            expires_at_dt = now_utc + timedelta(hours=24)
            supabase = get_supabase_client()
            guest_proj_record = {
                "id": str(uuid.uuid4()),
                "guest_session_id": session_id,
                "project_id": project_id,
                "migrated_to_user_id": auth_user_id if auth_user_id else None,
                "migrated_at": now_utc.isoformat() if auth_user_id else None,
                "expires_at": expires_at_dt.isoformat(),
                "created_at": now_utc.isoformat(),
            }
            supabase.table("guest_projects").insert(guest_proj_record).execute()

            yield format_sse("progress", {"step": "done", "message": "LaTeX project created! Opening editor...", "pct": 100})

            # Final result payload
            yield format_sse("result", {
                "success": True,
                "project_id": project_id,
                "name": created["name"],
                "document_class": created["document_class"],
                "files": created["files"],
                "assets": created["assets"],
                "compiled_successfully": conversion_result.compiled_successfully,
                "compile_log": conversion_result.compile_log[:500] if conversion_result.compile_log else "",
                "is_guest": True,
                "guest_token": token,
                "expires_at": expires_at_dt.isoformat(),
            })

        except Exception as e:
            logger.error(f"Error in guest PDF conversion pipeline: {e}", exc_info=True)
            yield format_sse("error", {"message": f"Conversion failed: {str(e)}"})
        finally:
            async with _lock:
                _active_guest_conversions.discard(session_id)

    # Attach Set-Cookie header to the StreamingResponse
    is_secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    if os.getenv("NODE_ENV") == "production" or os.getenv("ENVIRONMENT") == "production":
        is_secure = True

    cookie_directives = [
        f"{GUEST_TOKEN_COOKIE_NAME}={token}",
        f"Max-Age=86400",
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",
    ]
    if is_secure:
        cookie_directives.append("Secure")

    return StreamingResponse(
        sse_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Set-Cookie": "; ".join(cookie_directives),
        },
    )


@router.post("/migrate")
async def migrate_guest_session(request: Request, payload: GuestMigrateRequest):
    """
    Called by frontend after user registers or logs in.
    Transfers ownership of all guest projects to the authenticated user.
    """
    token = payload.guest_token or request.cookies.get(GUEST_TOKEN_COOKIE_NAME)
    if not token:
        # Fallback: check by device fingerprint for session with unmigrated projects
        fp = compute_device_fingerprint(request)
        supabase = get_supabase_client()
        res_fp = supabase.table("guest_sessions").select("id")\
            .eq("fingerprint_hash", fp)\
            .order("created_at", desc=True)\
            .limit(3)\
            .execute()
        for past_s in (res_fp.data or []):
            gp_check = supabase.table("guest_projects").select("id")\
                .eq("guest_session_id", past_s["id"])\
                .is_("migrated_to_user_id", "null")\
                .limit(1)\
                .execute()
            if gp_check.data and len(gp_check.data) > 0:
                token = sign_guest_token(past_s["id"])
                break

    if not token:
        return JSONResponse(
            status_code=200,
            content={"success": True, "migrated_count": 0, "message": "No pending guest session found."}
        )

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: migrate_guest_projects_to_user(
                guest_token=token,
                target_user_id=payload.user_id,
            )
        )
        return JSONResponse(content=result)
    except ValueError as ve:
        return JSONResponse(status_code=400, content={"detail": str(ve)})
    except Exception as e:
        logger.error(f"Migration error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": f"Project migration failed: {str(e)}"})


@router.post("/purge")
async def purge_expired_endpoint():
    """Administrative / cron trigger to purge expired guest projects."""
    try:
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, purge_expired_guest_projects)
        return JSONResponse(content=res)
    except Exception as e:
        logger.error(f"Purge error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": f"Purge operation failed: {str(e)}"})
