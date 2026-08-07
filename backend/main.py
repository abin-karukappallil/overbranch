from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from compiler import compile_latex
import vector_sync
import agent
import project_storage
from typing import List, Optional, Dict, Any

app = FastAPI(title="OverBranch TeX Engine API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(vector_sync.router)
app.include_router(agent.router)
app.include_router(project_storage.router)

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
        files=files_dict
    )
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
