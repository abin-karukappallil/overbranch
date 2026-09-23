from pathlib import Path
from dotenv import load_dotenv

# Load workspace root .env first, then backend .env if present
_root_env = Path(__file__).resolve().parent.parent / ".env"
_backend_env = Path(__file__).resolve().parent / ".env"
if _root_env.exists():
    load_dotenv(dotenv_path=_root_env, override=False)
if _backend_env.exists():
    load_dotenv(dotenv_path=_backend_env, override=True)
load_dotenv(override=False)

import os
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from compiler import compile_latex
from compile_queue import compile_queue, CompileQueueFullError
from trace import trace_manager
import project_storage
import file_analyzer
import template_service

logger = logging.getLogger("main")

_cleanup_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _cleanup_task
    logger.info("Starting OverBranch TeX Engine API...")
    # Start guest project cleanup scheduler (runs every 15 mins)
    from services.guest_cleanup import start_cleanup_scheduler
    _cleanup_task = asyncio.create_task(start_cleanup_scheduler(900))

    yield

    logger.info("OverBranch TeX Engine API shutting down gracefully...")
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()

    from database import close_db
    try:
        await close_db()
    except Exception as e:
        logger.warning(f"Error closing database pool: {e}")

    logger.info("OverBranch shutdown complete.")


app = FastAPI(title="OverBranch TeX Engine API", version="1.0.0", lifespan=lifespan)

allowed_origins_env = os.getenv("ALLOWED_ORIGINS")
origins = [o.strip() for o in allowed_origins_env.split(",")] if allowed_origins_env else [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://overbranch.abinthomas.dev"
]
if os.getenv("NEXT_PUBLIC_APP_URL"):
    origins.append(os.getenv("NEXT_PUBLIC_APP_URL").rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from routes.pdf_conversion import router as pdf_conversion_router
from routes.guest_pdf import router as guest_pdf_router
from routes.agent_routes import router as agent_opencode_router

app.include_router(project_storage.router)
app.include_router(template_service.router)
app.include_router(file_analyzer.router, prefix="/api")
app.include_router(pdf_conversion_router)
app.include_router(guest_pdf_router)
app.include_router(agent_opencode_router)


class FileAsset(BaseModel):
    filename: str
    data: str


class CompileRequest(BaseModel):
    latex_code: str = ""
    latex: str = ""
    project_id: str = ""
    engine: str = "latexmk"
    images: Optional[List[FileAsset]] = []
    files: Optional[List[FileAsset]] = []


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "OverBranch Python Engine",
        "version": "1.0.0",
        "active_compiles": compile_queue.active_count,
        "waiting_compiles": compile_queue.waiting_count,
    }


from fastapi import Depends
from auth import get_current_user_or_guest, verify_project_ownership_or_member
from rate_limiter import RateLimiter
from project_storage import get_supabase_client


@app.post(
    "/api/compile",
    dependencies=[Depends(RateLimiter(times=60, seconds=60, key_prefix="rl_compile"))],
)
async def compile_endpoint(
    req: CompileRequest,
    request: Request,
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    """
    Protected TeX compilation endpoint.
    Requires an active Better Auth session or verified guest identity.
    """
    user_id = auth_info.get("user_id")
    is_guest = bool(auth_info.get("is_guest"))
    if user_id and req.project_id:
        try:
            sb = get_supabase_client()
            verify_project_ownership_or_member(sb, req.project_id, user_id, is_guest=is_guest)
        except Exception as e:
            logger.warning(f"Project compile verification warning: {e}")
            raise

    code = req.latex_code if req.latex_code.strip() else req.latex
    images_dict = [{"filename": img.filename, "data": img.data} for img in (req.images or [])]
    files_dict = [{"filename": f.filename, "data": f.data} for f in (req.files or [])]

    try:
        result = await compile_queue.submit(
            compile_latex,
            latex_code=code,
            engine=req.engine,
            images=images_dict,
            files=files_dict,
            project_id=req.project_id,
        )
        return result
    except CompileQueueFullError as qfe:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": str(qfe),
                "retry_after_seconds": qfe.estimated_wait_s,
            },
            headers={"Retry-After": str(int(qfe.estimated_wait_s))},
        )


class SyncTeXBackwardRequest(BaseModel):
    page: int
    x: float
    y: float
    project_id: Optional[str] = None


class SyncTeXForwardRequest(BaseModel):
    file: str
    line: int
    column: Optional[int] = 1
    project_id: Optional[str] = None


@app.post(
    "/api/synctex/backward",
    dependencies=[Depends(RateLimiter(times=120, seconds=60, key_prefix="rl_synctex"))],
)
async def synctex_backward_endpoint(
    req: SyncTeXBackwardRequest,
    request: Request,
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    from synctex_service import backward_lookup
    user_id = auth_info.get("user_id")
    is_guest = bool(auth_info.get("is_guest"))
    if user_id and req.project_id:
        try:
            sb = get_supabase_client()
            verify_project_ownership_or_member(sb, req.project_id, user_id, is_guest=is_guest)
        except Exception as e:
            logger.warning(f"SyncTeX backward auth check warning: {e}")
            raise

    res = backward_lookup(
        project_id=req.project_id,
        page=req.page,
        x=req.x,
        y=req.y,
    )
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No SyncTeX mapping found for this position"
        )
    return res


@app.post(
    "/api/synctex/forward",
    dependencies=[Depends(RateLimiter(times=120, seconds=60, key_prefix="rl_synctex"))],
)
async def synctex_forward_endpoint(
    req: SyncTeXForwardRequest,
    request: Request,
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    from synctex_service import forward_lookup
    user_id = auth_info.get("user_id")
    is_guest = bool(auth_info.get("is_guest"))
    if user_id and req.project_id:
        try:
            sb = get_supabase_client()
            verify_project_ownership_or_member(sb, req.project_id, user_id, is_guest=is_guest)
        except Exception as e:
            logger.warning(f"SyncTeX forward auth check warning: {e}")
            raise

    res = forward_lookup(
        project_id=req.project_id,
        file_path=req.file,
        line=req.line,
        column=req.column or 1,
    )
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No SyncTeX mapping found for this source line"
        )
    return res


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

