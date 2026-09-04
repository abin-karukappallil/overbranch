from dotenv import load_dotenv
load_dotenv(override=True)

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from compiler import compile_latex
import vector_sync
import agent
import project_storage
import file_analyzer
import template_service
from typing import List, Optional, Dict, Any

# Allow up to 100MB request bodies (large PDFs base64-encoded can be 10-50MB)
app = FastAPI(title="OverBranch TeX Engine API", version="1.0.0")

import os

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
from services.guest_cleanup import start_cleanup_scheduler
import asyncio

app.include_router(vector_sync.router)
app.include_router(agent.router)
app.include_router(project_storage.router)
app.include_router(template_service.router)
app.include_router(file_analyzer.router, prefix="/api")
app.include_router(pdf_conversion_router)
app.include_router(guest_pdf_router)

_cleanup_task: Optional[asyncio.Task] = None

@app.on_event("startup")
async def startup_event():
    global _cleanup_task
    # Start guest project cleanup scheduler (runs every 15 mins)
    _cleanup_task = asyncio.create_task(start_cleanup_scheduler(900))

@app.on_event("shutdown")
async def shutdown_event():
    import logging
    logger = logging.getLogger("main")
    logger.info("OverBranch TeX Engine API shutting down gracefully...")
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
    # Clean up Qdrant client connection if open
    try:
        from vector_sync import close_qdrant_client
        close_qdrant_client()
    except Exception:
        pass
    logger.info("OverBranch shutdown complete.")


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
    return {"status": "ok", "service": "OverBranch Python Engine", "version": "1.0.0"}

@app.post("/api/compile")
def compile_endpoint(req: CompileRequest):
    code = req.latex_code if req.latex_code.strip() else req.latex
    images_dict = [{"filename": img.filename, "data": img.data} for img in (req.images or [])]
    files_dict = [{"filename": f.filename, "data": f.data} for f in (req.files or [])]
    
    result = compile_latex(
        latex_code=code,
        engine=req.engine,
        images=images_dict,
        files=files_dict,
        project_id=req.project_id
    )
    return result


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


@app.post("/api/synctex/backward")
def synctex_backward_endpoint(req: SyncTeXBackwardRequest):
    from synctex_service import backward_lookup
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


@app.post("/api/synctex/forward")
def synctex_forward_endpoint(req: SyncTeXForwardRequest):
    from synctex_service import forward_lookup
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
