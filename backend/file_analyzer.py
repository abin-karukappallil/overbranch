"""
file_analyzer.py — AI File Analysis Module for OverBranch

Supports direct FILE + USER PROMPT -> LLM multimodal analysis.
Primary model: GPT-120B OSS (Groq / NVIDIA endpoints).
Multi-key fallback: GROQ_API_KEY -> GROQ_API_KEY_2 -> GROQ_API_KEY_3 -> NVIDIA_API_KEY.
"""

import os
import re
import time
import json
import uuid
import shutil
import tempfile
import logging
import mimetypes
import requests
from abc import ABC, abstractmethod
from typing import Dict, Any, Generator, Optional, List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger("file_analyzer")
logger.setLevel(logging.INFO)

router = APIRouter()

# ─── Configuration & Security Constants ───────────────────────────────────────

MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024  # 200 MB max file size limit
ALLOWED_MIME_PREFIXES = ("image/", "video/", "audio/", "text/", "application/")

EXTENSION_MIME_MAP = {
    ".pdf": "application/pdf",
    ".csv": "text/csv",
    ".json": "application/json",
    ".txt": "text/plain",
    ".log": "text/plain",
    ".md": "text/markdown",
    ".html": "text/html",
    ".xml": "application/xml",
    ".py": "text/x-python",
    ".js": "text/javascript",
    ".ts": "text/typescript",
    ".tsx": "text/typescript-jsx",
    ".jsx": "text/javascript-jsx",
    ".css": "text/css",
    ".tex": "text/x-tex",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp3": "audio/mp3",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".m4a": "audio/m4a",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
}

def sanitize_filename(filename: str) -> str:
    """
    Sanitizes user filename to prevent path traversal and unsafe character bugs.
    """
    if not filename:
        return "unnamed_file"
    clean = os.path.basename(filename)
    clean = re.sub(r'[\r\n\t\0]', '', clean)
    clean = re.sub(r'[^\w\.\-]', '_', clean)
    return clean[:255] or "unnamed_file"

def detect_mime_type(filename: str, header_mime: str, file_path: str) -> str:
    """
    Determines MIME type safely without trusting client-provided header alone.
    Uses magic bytes inspection + file extension mapping fallback.
    """
    ext = os.path.splitext(filename)[1].lower()
    try:
        with open(file_path, "rb") as f:
            header = f.read(2048)
            
        if header.startswith(b"%PDF"):
            return "application/pdf"
        elif header.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        elif header.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        elif header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
            return "image/gif"
        elif header.startswith(b"RIFF") and header[8:12] == b"WEBP":
            return "image/webp"
        elif header.startswith(b"OggS"):
            return "audio/ogg"
        elif header.startswith(b"ID3") or header[:2] == b"\xff\xfb":
            return "audio/mp3"
        elif header.startswith(b"RIFF") and header[8:12] == b"WAVE":
            return "audio/wav"
        elif header[4:8] == b"ftyp":
            return "video/mp4"
    except Exception as e:
        logger.warning(f"Error inspecting magic bytes for {filename}: {e}")

    if ext in EXTENSION_MIME_MAP:
        return EXTENSION_MIME_MAP[ext]

    guessed_type, _ = mimetypes.guess_type(filename)
    if guessed_type:
        return guessed_type

    if header_mime and "/" in header_mime and not header_mime.endswith("octet-stream"):
        return header_mime

    return "application/octet-stream"


# ─── Provider Abstraction ───────────────────────────────────────────────────────

class AnalysisResult(BaseModel):
    success: bool = True
    filename: str
    mimeType: str
    analysis: str
    usage: Dict[str, Any] = Field(default_factory=dict)
    provider: str = "gpt-120b"


class BaseFileAnalysisProvider(ABC):
    @abstractmethod
    def get_provider_name(self) -> str:
        pass

    @abstractmethod
    def analyze_file(
        self,
        file_path: str,
        filename: str,
        mime_type: str,
        prompt: str,
        model_name: Optional[str] = None
    ) -> AnalysisResult:
        pass

    @abstractmethod
    def analyze_file_stream(
        self,
        file_path: str,
        filename: str,
        mime_type: str,
        prompt: str,
        model_name: Optional[str] = None
    ) -> Generator[str, None, None]:
        pass


# ─── GPT-120B OSS Provider Implementation (Groq Multi-Key Fallback) ─────────────

class GPT120BFileAnalysisProvider(BaseFileAnalysisProvider):
    def get_provider_name(self) -> str:
        return "gpt-120b"

    def _get_credential_candidates(self, model_override: Optional[str] = None) -> List[Dict[str, str]]:
        """
        Collects all configured FreeLLM, Groq, and NVIDIA API credentials for failover:
        1. FREELLM_API_KEY (FreeLLM Primary)
        2. GROQ_API_KEY (Groq Primary Fallback)
        3. GROQ_API_KEY_2 (Groq API 2 Fallback)
        4. GROQ_API_KEY_3 (Groq API 3 Fallback)
        5. NVIDIA_API_KEY (NVIDIA NIM API Fallback)
        """
        default_model = model_override or os.getenv("FREELLM_MODEL") or os.getenv("GROQ_LLM_MODEL") or "auto:smart"
        candidates = []

        # FreeLLM Primary Endpoint (reads exclusively from env)
        freellm_key = os.getenv("FREELLM_API_KEY")
        freellm_base = (os.getenv("FREELLM_BASE_URL") or "").rstrip("/")
        if freellm_key and freellm_key.strip() and freellm_base:
            chat_url = f"{freellm_base}/chat/completions" if freellm_base.endswith("/v1") else f"{freellm_base}/v1/chat/completions"
            candidates.append({
                "name": "FreeLLM API Router",
                "key": freellm_key.strip(),
                "url": chat_url,
                "model": default_model
            })

        # Groq API Key 1 Fallback
        key1 = os.getenv("GROQ_API_KEY")
        if key1 and key1.strip():
            candidates.append({
                "name": "Groq Primary API",
                "key": key1.strip(),
                "url": "https://api.groq.com/openai/v1/chat/completions",
                "model": os.getenv("GROQ_LLM_MODEL", "openai/gpt-oss-120b")
            })

        # Groq API Key 2 Fallback
        key2 = os.getenv("GROQ_API_KEY_2")
        if key2 and key2.strip():
            candidates.append({
                "name": "Groq API 2",
                "key": key2.strip(),
                "url": "https://api.groq.com/openai/v1/chat/completions",
                "model": os.getenv("GROQ_LLM_MODEL", "openai/gpt-oss-120b")
            })

        # Groq API Key 3 Fallback
        key3 = os.getenv("GROQ_API_KEY_3")
        if key3 and key3.strip():
            candidates.append({
                "name": "Groq API 3",
                "key": key3.strip(),
                "url": "https://api.groq.com/openai/v1/chat/completions",
                "model": os.getenv("GROQ_LLM_MODEL", "openai/gpt-oss-120b")
            })

        # NVIDIA NIM API Key Fallback
        nv_key = os.getenv("NVIDIA_API_KEY")
        if nv_key and nv_key.strip():
            candidates.append({
                "name": "NVIDIA NIM API",
                "key": nv_key.strip(),
                "url": "https://integrate.api.nvidia.com/v1/chat/completions",
                "model": os.getenv("NVIDIA_LLM_MODEL", "openai/gpt-oss-120b")
            })

        if not candidates:
            raise ValueError("No FREELLM_API_KEY, GROQ_API_KEY, or NVIDIA_API_KEY configured in environment.")

        return candidates

    def _extract_file_content(self, file_path: str, filename: str, mime_type: str) -> str:
        """Inbuilt text and document content extractor for GPT-120B OSS file analysis."""
        ext = os.path.splitext(filename)[1].lower()

        def clean_text(t: str) -> str:
            if not t:
                return ""
            return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', t)

        # Word Document DOCX Extraction
        if ext in (".docx", ".doc") or "word" in mime_type.lower() or "officedocument" in mime_type.lower():
            try:
                import docx
                doc_file = docx.Document(file_path)
                paragraphs = [p.text.strip() for p in doc_file.paragraphs if p.text.strip()]
                full_docx_text = "\n".join(paragraphs)
                if len(full_docx_text) > 16000:
                    full_docx_text = full_docx_text[:16000] + f"\n...[TRUNCATED to 16k chars]"
                return clean_text(full_docx_text)
            except Exception as e:
                logger.warning(f"Word docx extraction failed for {filename}: {e}")

        # PDF Extraction
        if mime_type == "application/pdf" or ext == ".pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(file_path, strict=False)
                pages = []
                for i in range(min(len(reader.pages), 40)):
                    txt = reader.pages[i].extract_text() or ""
                    if txt.strip():
                        pages.append(f"[Page {i+1}]\n{txt.strip()}")
                if pages:
                    full_pdf_text = "\n\n".join(pages)
                    if len(full_pdf_text) > 16000:
                        full_pdf_text = full_pdf_text[:16000] + f"\n...[TRUNCATED to 16k chars — total pages: {len(reader.pages)}]"
                    return clean_text(full_pdf_text)
            except Exception as e:
                logger.warning(f"pypdf extraction notice for {filename}: {e}. Attempting raw stream recovery...")
                try:
                    with open(file_path, "rb") as pf:
                        raw_bytes = pf.read()
                        raw_text_parts = re.findall(r'[\x20-\x7E\s]{4,}', raw_bytes.decode('latin-1', errors='ignore'))
                        clean_parts = [p.strip() for p in raw_text_parts if len(p.strip()) > 10 and not any(p.strip().startswith(k) for k in ('<<', '>>', 'obj', 'endobj', 'stream', 'endstream', '/Filter', '/Type', '/Font', 'xref', 'trailer'))]
                        if clean_parts:
                            return clean_text("\n".join(clean_parts[:200])[:16000])
                except Exception:
                    pass

        # Text, Code, CSV, JSON, LOG, TeX, HTML
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(16000)
                if len(content) >= 16000:
                    content += f"\n...[TRUNCATED to 16k chars]"
                return clean_text(content)
        except Exception as e:
            logger.warning(f"Text reading failed for {filename}: {e}")
            return f"[File '{filename}' ({mime_type}) uploaded]"

    def analyze_file(
        self,
        file_path: str,
        filename: str,
        mime_type: str,
        prompt: str,
        model_name: Optional[str] = None
    ) -> AnalysisResult:
        candidates = self._get_credential_candidates(model_name)
        file_text = self._extract_file_content(file_path, filename, mime_type)

        full_system_prompt = (
            f"You are OverBranch's GPT-120B OSS AI File Analyzer. Analyze the attached file carefully according to user instructions."
        )
        user_content = f"📎 Attached File: '{filename}' ({mime_type})\n\n--- FILE CONTENT START ---\n{file_text}\n--- FILE CONTENT END ---\n\nUser Prompt: {prompt}"
        if len(user_content) > 25000:
            user_content = user_content[:25000] + "\n...[Content capped to prevent API 413 payload limit]"

        last_error = None

        for creds in candidates:
            logger.info(f"Sending file analysis request for '{filename}' to {creds['name']} ({creds['model']})...")
            headers = {
                "Authorization": f"Bearer {creds['key']}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": creds["model"],
                "messages": [
                    {"role": "system", "content": full_system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "temperature": 0.2,
                "max_tokens": 2048
            }

            try:
                resp = requests.post(creds["url"], headers=headers, json=payload, timeout=90)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    analysis_text = choices[0]["message"]["content"] if choices else "No output generated."
                    usage = data.get("usage", {})
                    return AnalysisResult(
                        success=True,
                        filename=filename,
                        mimeType=mime_type,
                        analysis=analysis_text,
                        usage={
                            "promptTokens": usage.get("prompt_tokens", 0),
                            "candidatesTokens": usage.get("completion_tokens", 0),
                            "totalTokens": usage.get("total_tokens", 0)
                        },
                        provider=f"gpt-120b ({creds['name']})"
                    )
                else:
                    logger.warning(f"{creds['name']} returned status {resp.status_code}: {resp.text[:150]}. Trying next Groq fallback key...")
                    last_error = f"{creds['name']} HTTP {resp.status_code}: {resp.text[:150]}"
            except Exception as err:
                logger.warning(f"{creds['name']} error: {err}. Trying next Groq fallback key...")
                last_error = f"{creds['name']} error: {str(err)}"

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"All Groq and NVIDIA API keys failed for GPT-120B. Last error: {last_error}"
        )

    def analyze_file_stream(
        self,
        file_path: str,
        filename: str,
        mime_type: str,
        prompt: str,
        model_name: Optional[str] = None
    ) -> Generator[str, None, None]:
        try:
            candidates = self._get_credential_candidates(model_name)
        except Exception as e:
            err_event = {"error": True, "detail": str(e)}
            yield f"data: {JSONResponse(err_event).body.decode('utf-8')}\n\n"
            return

        file_text = self._extract_file_content(file_path, filename, mime_type)
        full_system_prompt = (
            f"You are OverBranch's GPT-120B OSS AI File Analyzer. Analyze the attached file carefully according to user instructions."
        )
        user_content = f"📎 Attached File: '{filename}' ({mime_type})\n\n--- FILE CONTENT START ---\n{file_text}\n--- FILE CONTENT END ---\n\nUser Prompt: {prompt}"
        if len(user_content) > 25000:
            user_content = user_content[:25000] + "\n...[Content capped to prevent API 413 payload limit]"

        last_error = None

        for creds in candidates:
            logger.info(f"Streaming file analysis for '{filename}' with {creds['name']} ({creds['model']})...")
            headers = {
                "Authorization": f"Bearer {creds['key']}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": creds["model"],
                "messages": [
                    {"role": "system", "content": full_system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "temperature": 0.2,
                "max_tokens": 2048,
                "stream": True
            }

            try:
                resp = requests.post(creds["url"], headers=headers, json=payload, stream=True, timeout=90)
                if resp.status_code == 200:
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        line_str = line.decode("utf-8")
                        if line_str.startswith("data: "):
                            data_content = line_str[6:].strip()
                            if data_content == "[DONE]":
                                break
                            try:
                                chunk_json = json.loads(data_content)
                                delta = chunk_json.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if delta:
                                    yield f"data: {JSONResponse({'chunk': delta}).body.decode('utf-8')}\n\n"
                            except Exception:
                                continue

                    yield f"data: {JSONResponse({'done': True, 'filename': filename, 'mimeType': mime_type}).body.decode('utf-8')}\n\n"
                    return
                else:
                    logger.warning(f"{creds['name']} stream returned status {resp.status_code}: {resp.text[:150]}. Trying next Groq fallback key...")
                    last_error = f"{creds['name']} stream HTTP {resp.status_code}"
            except Exception as err:
                logger.warning(f"{creds['name']} stream error: {err}. Trying next Groq fallback key...")
                last_error = f"{creds['name']} stream error: {str(err)}"

        err_event = {
            "error": True,
            "detail": f"All Groq and NVIDIA API keys failed for GPT-120B stream. Last error: {last_error}"
        }
        yield f"data: {JSONResponse(err_event).body.decode('utf-8')}\n\n"


# ─── Provider Registry ────────────────────────────────────────────────────────

class FileAnalysisRegistry:
    def __init__(self):
        self._providers: Dict[str, BaseFileAnalysisProvider] = {}
        gpt120b_provider = GPT120BFileAnalysisProvider()

        self.register_provider("gpt-120b", gpt120b_provider)
        self.register_provider("openai/gpt-oss-120b", gpt120b_provider)
        self.register_provider("groq", gpt120b_provider)

    def register_provider(self, name: str, provider: BaseFileAnalysisProvider):
        self._providers[name.lower()] = provider

    def get_provider(self, name: str = "gpt-120b") -> BaseFileAnalysisProvider:
        return self._providers.get("gpt-120b")

registry = FileAnalysisRegistry()


# ─── Fast API Route Handler ───────────────────────────────────────────────────

@router.post("/ai/analyze-file")
async def analyze_file_endpoint(
    file: UploadFile = File(..., description="Uploaded original file"),
    prompt: str = Form(..., description="User prompt describing analysis instructions"),
    provider: Optional[str] = Form("gpt-120b", description="LLM provider (default: gpt-120b)"),
    model: Optional[str] = Form(None, description="Specific model override"),
    stream: Optional[bool] = Form(False, description="Stream output via SSE")
):
    """
    POST /api/ai/analyze-file
    Accepts multipart/form-data with original file and user prompt.
    Processes file via GPT-120B OSS with Groq Multi-Key failover (GROQ_API_KEY -> GROQ_API_KEY_2 -> GROQ_API_KEY_3).
    """
    if not prompt or not prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prompt is required. Please provide instructions for analyzing the file."
        )

    temp_dir = tempfile.mkdtemp(prefix="overbranch_ai_")
    safe_name = sanitize_filename(file.filename or "uploaded_file")
    temp_file_path = os.path.join(temp_dir, safe_name)

    try:
        file_size = 0
        with open(temp_file_path, "wb") as out_file:
            while chunk := await file.read(1024 * 1024):
                file_size += len(chunk)
                if file_size > MAX_FILE_SIZE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB."
                    )
                out_file.write(chunk)

        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty (0 bytes)."
            )

        detected_mime = detect_mime_type(safe_name, file.content_type or "", temp_file_path)
        logger.info(f"Processing uploaded file: '{safe_name}' ({detected_mime}, {file_size} bytes)")

        analysis_provider = registry.get_provider(provider or "gpt-120b")

        if stream:
            generator = analysis_provider.analyze_file_stream(
                file_path=temp_file_path,
                filename=safe_name,
                mime_type=detected_mime,
                prompt=prompt.strip(),
                model_name=model
            )

            def safe_stream_wrapper():
                try:
                    for chunk_data in generator:
                        yield chunk_data
                finally:
                    shutil.rmtree(temp_dir, ignore_errors=True)

            return StreamingResponse(
                safe_stream_wrapper(),
                media_type="text/event-stream"
            )
        else:
            result = analysis_provider.analyze_file(
                file_path=temp_file_path,
                filename=safe_name,
                mime_type=detected_mime,
                prompt=prompt.strip(),
                model_name=model
            )
            return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected exception during analyze-file endpoint execution: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during file analysis: {str(e)}"
        )
    finally:
        if not stream:
            shutil.rmtree(temp_dir, ignore_errors=True)
