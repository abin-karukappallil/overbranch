"""
pdf_convert.py — FastAPI router for the per-page PDF → LaTeX importer (pdf2latex).

Endpoints:
- GET  /api/convert/pdf/config                  — limits, similarity target, LLM availability and model
- POST /api/convert/pdf                         — multipart upload (file, project_id?, project_name?, overwrite?) → job id
- GET  /api/convert/pdf/{job_id}                — job progress, per-page status/similarity, report, result
- POST /api/convert/pdf/{job_id}/commit         — finish a job waiting for overwrite confirmation
- GET  /api/convert/pdf/{job_id}/preview/{page} — PNG render of original / converted / diff page
- GET  /api/guest/session                       — guest quota status + signed guest token
- POST /api/guest/migrate                       — transfers guest projects to the signed-in user
"""

import asyncio
import io
import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from auth import extract_guest_token, get_current_user, get_current_user_or_guest, verify_project_ownership_or_member
from models import User
from rate_limiter import RateLimiter

from pdf2latex import jobs
from pdf2latex.config import get_settings
from pdf2latex.extract import PdfValidationError, open_pdf
from pdf2latex.llm import llm_available, model_name
from pdf2latex.pipeline import ConversionError, commit_pending_output
from pdf2latex.runner import start_job
from pdf2latex.storage import FileConflictError, create_project_for_conversion, sanitize_target_path

logger = logging.getLogger("pdf_convert")

router = APIRouter(tags=["pdf_convert"])

CONVERSIONS_PER_HOUR = int(os.getenv("PDF2LATEX_RATE_PER_HOUR", "10"))


class CommitRequest(BaseModel):
    overwrite: bool = Field(False, description="Overwrite the target file if it has content")
    target_path: str = Field("main.tex", description="Project-relative .tex path to write")


class GuestMigrateRequest(BaseModel):
    user_id: str = Field(..., description="Target authenticated User ID")
    guest_token: Optional[str] = Field(None, description="Optional explicit guest token (falls back to cookie)")


def _supabase_or_503():
    from project_storage import get_supabase_client
    try:
        return get_supabase_client()
    except HTTPException:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Project storage database is not configured.")


def _owned_job(job_id: str, auth: Dict[str, Any]) -> Dict[str, Any]:
    state = jobs.load_job(job_id)
    if not state or state.get("owner") != auth["user_id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversion job not found.")
    return state


async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    buf = io.BytesIO()
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        buf.write(chunk)
        if buf.tell() > limit:
            raise HTTPException(status_code=413,
                                detail=f"PDF exceeds the {limit // (1024 * 1024)} MB limit.")
    return buf.getvalue()


def _guest_session(session_id: str, request: Request) -> Dict[str, Any]:
    from services.guest_identity import get_or_create_guest_session
    sb = _supabase_or_503()
    res = sb.table("guest_sessions").select("*").eq("id", session_id).limit(1).execute()
    if res.data:
        return res.data[0]
    session, _token, _new = get_or_create_guest_session(request)
    return session


@router.get("/api/convert/pdf/config")
async def conversion_config():
    s = get_settings()
    return {
        "llm_available": llm_available(),
        "model": model_name(),
        "max_file_mb": s.max_file_mb,
        "max_pages": s.max_pages,
        "threshold": s.sim_threshold,
    }


@router.post(
    "/api/convert/pdf",
    dependencies=[Depends(RateLimiter(times=CONVERSIONS_PER_HOUR, seconds=3600, key_prefix="rl_pdf2latex"))],
)
async def start_conversion(
    request: Request,
    file: UploadFile = File(...),
    project_id: Optional[str] = Form(None),
    project_name: Optional[str] = Form(None),
    overwrite: bool = Form(False),
    cancel_previous: bool = Form(False),
    auth: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    settings = get_settings()
    data = await _read_limited(file, settings.max_file_bytes)
    try:
        doc = await asyncio.to_thread(open_pdf, data)
        page_count = doc.page_count
        doc.close()
    except PdfValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if page_count > settings.max_pages:
        raise HTTPException(status_code=422, detail=f"PDF has {page_count} pages; the limit is {settings.max_pages}.")

    user_id: str = auth["user_id"]
    is_guest: bool = bool(auth.get("is_guest"))
    guest_session = None
    if is_guest and auth.get("session_id"):
        from services.guest_identity import compute_device_fingerprint
        from services.guest_quota import check_guest_conversion_quota
        guest_session = await asyncio.to_thread(_guest_session, auth["session_id"], request)
        allowed, used, resets_at, reason = await asyncio.to_thread(
            check_guest_conversion_quota, guest_session, compute_device_fingerprint(request))
        if not allowed:
            return JSONResponse(status_code=429, content={
                "detail": reason or "Guest conversion limit reached.",
                "resets_at": resets_at.isoformat() if resets_at else None,
                "conversions_used": used,
            })

    existing = await asyncio.to_thread(jobs.active_job_for, user_id)
    if existing:
        prev_job_id = existing.get("job_id", "")
        from pdf2latex.runner import cancel_job
        if cancel_previous:
            logger.info(f"Cancelling active conversion job {prev_job_id} as requested")
            cancel_job(prev_job_id)
            await asyncio.to_thread(jobs.update_job, prev_job_id, status="error", error="Cancelled by user.")
        else:
            return JSONResponse(status_code=409, content={
                "detail": "A conversion is already running for your account.", "job_id": prev_job_id})

    if project_id:
        sb = _supabase_or_503()
        await asyncio.to_thread(verify_project_ownership_or_member, sb, project_id, user_id, is_guest)
        project = {"project_id": project_id, "name": None, "created": False}
    else:
        created = await asyncio.to_thread(
            create_project_for_conversion, user_id, project_name, file.filename or "document.pdf",
            guest_session["id"] if guest_session else None)
        project = {**created, "created": True}

    if guest_session:
        from services.guest_quota import consume_guest_conversion
        try:
            await asyncio.to_thread(consume_guest_conversion, guest_session["id"])
        except Exception as e:
            logger.warning(f"Could not record guest conversion: {e}")

    state = start_job(user_id, is_guest, project["project_id"], file.filename or "document.pdf",
                      data, page_count, overwrite)

    body = {"job_id": state["job_id"], "project_id": project["project_id"], "project_name": project.get("name"),
            "project_created": project["created"], "page_count": page_count}
    token = extract_guest_token(request) if is_guest else None
    if token:
        body["guest_token"] = token
    response = JSONResponse(status_code=202, content=body)
    if token:
        from services.guest_identity import set_guest_cookie
        set_guest_cookie(response, token, request)
    return response


@router.get("/api/convert/pdf/{job_id}")
async def get_conversion(job_id: str, auth: Dict[str, Any] = Depends(get_current_user_or_guest)):
    return jobs.public_view(_owned_job(job_id, auth))


@router.post("/api/convert/pdf/{job_id}/commit")
async def commit_conversion(job_id: str, payload: CommitRequest,
                            auth: Dict[str, Any] = Depends(get_current_user_or_guest)):
    _owned_job(job_id, auth)
    try:
        target = sanitize_target_path(payload.target_path)
        result = await commit_pending_output(job_id, payload.overwrite, target)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except FileConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ConversionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"success": True, "result": result}


@router.get("/api/convert/pdf/{job_id}/preview/{page}")
async def preview_page(job_id: str, page: int, which: str = "original",
                       auth: Dict[str, Any] = Depends(get_current_user_or_guest)):
    _owned_job(job_id, auth)
    if which not in ("original", "converted", "diff"):
        raise HTTPException(status_code=422, detail="which must be original, converted or diff")
    jd = jobs.job_dir(job_id)
    cache = jd / "previews" / f"{which}_{page}.png"
    if not cache.exists():
        png = await asyncio.to_thread(_render_preview, jd, page, which)
        if png is None:
            raise HTTPException(status_code=404, detail="Preview not available for this page.")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(png)
    return Response(content=cache.read_bytes(), media_type="image/png",
                    headers={"Cache-Control": "private, max-age=600"})


def _render_preview(jd, page: int, which: str) -> Optional[bytes]:
    import pymupdf
    from pdf2latex.verify import diff_heatmap_png, render_pdf_pages

    src, out = jd / "source.pdf", jd / "output.pdf"
    dpi = get_settings().render_dpi
    target = src if which == "original" else out
    if not target.exists():
        return None
    with pymupdf.open(str(target)) as d:
        if page < 1 or page > d.page_count:
            return None
        if which != "diff":
            return d[page - 1].get_pixmap(dpi=dpi, alpha=False).tobytes("png")
    if not src.exists():
        return None
    a = render_pdf_pages(src, dpi, first=page, last=page)
    b = render_pdf_pages(out, dpi, first=page, last=page)
    if not a or not b:
        return None
    return diff_heatmap_png(a[0], b[0])


# ---------------------------------------------------------------------------
# Guest session & migration (moved from the former guest_pdf router)
# ---------------------------------------------------------------------------

@router.get(
    "/api/guest/session",
    dependencies=[Depends(RateLimiter(times=30, seconds=60, key_prefix="rl_guest_sess"))],
)
async def get_guest_session_info(request: Request):
    """Returns guest quota, active project, and countdown timer for the current device."""
    from services.guest_identity import compute_device_fingerprint, get_or_create_guest_session, set_guest_cookie
    from services.guest_quota import get_guest_session_status
    try:
        session, token, is_new = await asyncio.to_thread(get_or_create_guest_session, request)
        info = await asyncio.to_thread(get_guest_session_status, session, compute_device_fingerprint(request))
        info["token"] = token
        info["is_new"] = is_new
        response = JSONResponse(content=info)
        set_guest_cookie(response, token, request)
        return response
    except Exception as e:
        logger.error(f"Error fetching guest session: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "Failed to retrieve guest session."})


@router.post(
    "/api/guest/migrate",
    dependencies=[Depends(RateLimiter(times=10, seconds=60, key_prefix="rl_guest_migrate"))],
)
async def migrate_guest_session(request: Request, payload: GuestMigrateRequest,
                                current_user: User = Depends(get_current_user)):
    """Called after sign-up / sign-in: transfers all guest projects to the authenticated user."""
    from services.guest_identity import GUEST_TOKEN_COOKIE_NAME, compute_device_fingerprint, sign_guest_token
    from services.guest_migrator import migrate_guest_projects_to_user

    token = payload.guest_token or request.cookies.get(GUEST_TOKEN_COOKIE_NAME)
    if not token:
        # Fallback: most recent sessions on this device that still own unmigrated projects
        sb = _supabase_or_503()
        fp = compute_device_fingerprint(request)
        res_fp = sb.table("guest_sessions").select("id").eq("fingerprint_hash", fp) \
            .order("created_at", desc=True).limit(3).execute()
        for past in (res_fp.data or []):
            check = sb.table("guest_projects").select("id").eq("guest_session_id", past["id"]) \
                .is_("migrated_to_user_id", "null").limit(1).execute()
            if check.data:
                token = sign_guest_token(past["id"])
                break
    if not token:
        return JSONResponse(content={"success": True, "migrated_count": 0, "message": "No pending guest session found."})
    try:
        result = await asyncio.to_thread(migrate_guest_projects_to_user, guest_token=token, target_user_id=current_user.id)
        return JSONResponse(content=result)
    except ValueError as ve:
        return JSONResponse(status_code=400, content={"detail": str(ve)})
    except Exception as e:
        logger.error(f"Migration error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "Project migration failed."})


@router.post("/api/convert/pdf/{job_id}/cancel")
async def cancel_conversion_job(
    job_id: str,
    auth: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    """Cancels an active or stuck conversion job for the owner."""
    state = _owned_job(job_id, auth)
    from pdf2latex.runner import cancel_job
    cancelled = cancel_job(job_id)
    if not cancelled:
        await asyncio.to_thread(jobs.update_job, job_id, status="cancelled", message="Conversion cancelled by user.")
    return {"job_id": job_id, "status": "cancelled"}
