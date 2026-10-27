from pathlib import Path
from dotenv import load_dotenv

# Load workspace root .env first, then backend .env if present
_root_env = Path(__file__).resolve().parent.parent / ".env"
_backend_env = Path(__file__).resolve().parent / ".env"
if _root_env.exists():
    load_dotenv(dotenv_path=_root_env, override=True)
if _backend_env.exists():
    load_dotenv(dotenv_path=_backend_env, override=True)
load_dotenv(override=True)

import os
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from compiler import compile_latex
from compile_queue import compile_queue, CompileQueueFullError
import project_storage
import file_analyzer
import template_service

logger = logging.getLogger("main")

_cleanup_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _cleanup_task
    logger.info("Starting OverBranch TeX Engine API...")
    # Start guest project + PDF conversion job cleanup scheduler (runs every 15 mins)
    from services.guest_cleanup import start_cleanup_scheduler
    _cleanup_task = asyncio.create_task(start_cleanup_scheduler(900))

    # Realtime collaboration: start the idle-room reaper. Rooms themselves are
    # created lazily by the first websocket for a project.
    from collab import config as collab_config, room_manager, warn_if_multi_worker
    if collab_config.enabled:
        warn_if_multi_worker()
        await room_manager.start_reaper()

    # Prime TeX's font/format caches off the request path (first xelatex/lualatex run in a
    # fresh container can take minutes) and log whether each engine works here at all.
    import tex_health
    asyncio.get_running_loop().run_in_executor(None, tex_health.warm_up)

    yield

    logger.info("OverBranch TeX Engine API shutting down gracefully...")
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()

    # Flush every live collaboration room before the process exits, so a
    # deploy cannot drop keystrokes that were still inside the debounce window.
    try:
        await room_manager.shutdown()
    except Exception as e:
        logger.warning(f"Error shutting down collaboration rooms: {e}")

    from database import close_db
    try:
        await close_db()
    except Exception as e:
        logger.warning(f"Error closing database pool: {e}")

    try:
        from compile_queue import compile_queue
        if getattr(compile_queue, "_executor", None) is not None:
            compile_queue._executor.shutdown(wait=False, cancel_futures=True)
    except Exception as e:
        logger.warning(f"Error shutting down compile executor: {e}")

    try:
        import pdf2latex.llm as pdf_llm
        if getattr(pdf_llm, "_pool", None) is not None:
            pdf_llm._pool.shutdown(wait=False, cancel_futures=True)
            pdf_llm._pool = None
    except Exception as e:
        logger.warning(f"Error shutting down pdf2latex llm pool: {e}")

    logger.info("OverBranch shutdown complete.")


app = FastAPI(title="OverBranch TeX Engine API", version="1.0.0", lifespan=lifespan)

allowed_origins_env = os.getenv("ALLOWED_ORIGINS")
origins = [o.strip() for o in allowed_origins_env.split(",")] if allowed_origins_env else [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://overbranch.app",
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

# Trust reverse proxy headers (Cloudflare -> Nginx -> Docker) so request.client.host
# and logs resolve the real visitor IP instead of 127.0.0.1
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])

from routes.pdf_convert import router as pdf_convert_router
from routes.agent_routes import router as agent_router
from routes.collab_routes import router as collab_router
from routes import project_import
from routes import project_export

app.include_router(project_storage.router)
app.include_router(template_service.router)
app.include_router(file_analyzer.router, prefix="/api")
app.include_router(pdf_convert_router)
app.include_router(agent_router)
app.include_router(collab_router)
app.include_router(project_import.router, prefix='/api/projects')
app.include_router(project_export.router, prefix='/api/projects')


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
    # Project compile from the editor: the path of the file open in the editor and
    # its live text. When set (with project_id), the open buffer is overlaid at its
    # own path in the project copy and the project's MAIN DOCUMENT is compiled —
    # never the open file itself. Absent: latex_code is the document (legacy).
    active_file: Optional[str] = None
    active_text: Optional[str] = None


@app.get("/api/models")
def list_models():
    """
    The models the editor may offer and which one is selected by default.

    The frontend has always fetched this path (``trpc/routers/ai.ts``); until it
    existed the call 404'd and the browser fell back to its own hardcoded list,
    so the default model was really defined in TypeScript. The backend's
    ``provider_router`` is the single source of truth, and this is how it reaches
    the client.
    """
    from providers.router import provider_router

    return provider_router.get_available_models()


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "OverBranch Python Engine",
        "version": "1.0.0",
        "active_compiles": compile_queue.active_count,
        "waiting_compiles": compile_queue.waiting_count,
    }


@app.get("/api/health/tex")
async def tex_health_check(refresh: bool = False):
    """Builds a one-line document with each engine and reports timings (cached for 60s)."""
    import tex_health
    return await asyncio.to_thread(tex_health.check, 120.0, refresh)


from fastapi import Depends
from auth import get_current_user_or_guest, verify_project_ownership_or_member
from rate_limiter import RateLimiter
from project_storage import get_supabase_client


# How long a compile waits for the project's collab room to persist. The flush
# is normally milliseconds (a few disk writes); the cap only stops a wedged room
# from hanging the request.
COLLAB_FLUSH_TIMEOUT_SECONDS = 2.0


async def _flush_collab_room_before_compile(project_id: str) -> None:
    """
    Best-effort: persist the project's live collab room before compiling.

    Only ``main.tex`` travels in the compile request; every sibling (``\\input``
    chapters, ``.bib``) is copied from ``uploads/projects/<id>/``, which the room
    writes on a 2s-idle / 15s-max debounce. Without this, a chapter edited just
    before clicking Compile is built from its previous version.

    Never raises: a missing room, collab being disabled, a failing or slow flush
    are logged and the compile goes ahead with whatever is on disk.
    """
    pid = (project_id or "").strip()
    if not pid:
        return
    try:
        from collab import config as collab_config, room_manager

        if not collab_config.enabled:
            logger.warning(f"[COMPILE] collab disabled; no room flush before compiling project {pid}")
            return
        room = room_manager.get(pid)
        if room is None:
            logger.warning(f"[COMPILE] no live collab room for project {pid}; compiling from stored files")
            return
        # shield: on timeout stop *waiting*, but let the flush finish. Cancelling it
        # mid-write would drop the paths it had already taken off the dirty set.
        await asyncio.wait_for(asyncio.shield(room.flush()), timeout=COLLAB_FLUSH_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning(
            f"[COMPILE] collab flush for project {pid} exceeded {COLLAB_FLUSH_TIMEOUT_SECONDS}s; compiling anyway"
        )
    except Exception as e:
        logger.warning(f"[COMPILE] collab flush for project {pid} failed ({e!r}); compiling anyway")


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
            # Blocking Supabase round-trip: off the event loop, or every request (including
            # the polls of compiles already running) stalls behind it.
            await asyncio.to_thread(
                lambda: verify_project_ownership_or_member(
                    get_supabase_client(), req.project_id, user_id, is_guest=is_guest
                )
            )
        except Exception as e:
            logger.warning(f"Project compile verification warning: {e}")
            raise

    code = req.latex_code if req.latex_code.strip() else req.latex
    active_file = (req.active_file or "").strip() or None
    active_text = req.active_text if active_file else None
    if active_file and active_text is None:
        active_text = code  # an editor that only sent latex_code: that IS the open buffer
    if active_file and not (req.project_id or "").strip():
        # No project to build: the open buffer is the whole document.
        code = active_text if active_text is not None else code
        active_file = active_text = None
    images_dict = [{"filename": img.filename, "data": img.data} for img in (req.images or [])]
    files_dict = [{"filename": f.filename, "data": f.data} for f in (req.files or [])]

    await _flush_collab_room_before_compile(req.project_id)

    try:
        result = await compile_queue.submit(
            compile_latex,
            latex_code=code,
            engine=req.engine,
            images=images_dict,
            files=files_dict,
            project_id=req.project_id,
            active_file=active_file,
            active_text=active_text,
        )
        if isinstance(result, dict) and result.get("success") is not True and not (result.get("error_log") or "").strip():
            result["error_log"] = (
                "Compilation failed without a TeX log (the engine produced no output or was cut off by the "
                "compile timeout). Check GET /api/health/tex on the server for the toolchain status."
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
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, proxy_headers=True, forwarded_allow_ips="*")

