from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from compiler import compile_latex

app = FastAPI(title="OverBranch TeX Engine API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CompileRequest(BaseModel):
    latex_code: str
    project_id: str = ""
    engine: str = "pdflatex"


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "OverBranch Python Engine", "version": "1.0.0"}


@app.post("/api/compile")
def compile_endpoint(req: CompileRequest):
    result = compile_latex(req.latex_code, engine=req.engine)
    return result
