from dotenv import load_dotenv
load_dotenv(override=True)

from fastapi import FastAPI
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

app.include_router(vector_sync.router)
app.include_router(agent.router)
app.include_router(project_storage.router)
app.include_router(template_service.router)
app.include_router(file_analyzer.router, prefix="/api")

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
