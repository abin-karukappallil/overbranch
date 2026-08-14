"""
file_analyzer.py — AI File Analysis Module for OverBranch

Supports direct FILE + USER PROMPT -> LLM multimodal analysis.
Primary model: GPT-120B OSS (Groq / NVIDIA endpoint) with built-in file content extraction.
Fallback model: Gemini Files API upload model (gemini-2.5-flash / gemini-1.5-pro).
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


# ─── Gemini Provider Implementation (File Upload Fallback Model) ─────────────

class GeminiFileAnalysisProvider(BaseFileAnalysisProvider):
    def get_provider_name(self) -> str:
        return "gemini"

    def _get_client(self):
        try:
            from google import genai
        except ImportError:
            raise RuntimeError("The 'google-genai' package is not installed on the server.")

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key or not api_key.strip():
            raise ValueError("No GEMINI_API_KEY or GOOGLE_API_KEY configured in backend environment (.env).")

        return genai.Client(api_key=api_key.strip())

    def _upload_and_wait(self, client, file_path: str, filename: str, mime_type: str):
        from google.genai import types

        logger.info(f"[Fallback Provider] Uploading file '{filename}' ({mime_type}) to Gemini Files API...")
        try:
            gemini_file = client.files.upload(
                file=file_path,
                config=types.UploadFileConfig(
                    mime_type=mime_type,
                    display_name=filename
                )
            )
        except Exception as upload_err:
            err_str = str(upload_err)
            logger.error(f"Gemini file upload failed for '{filename}': {err_str}")
            if "429" in err_str or "quota" in err_str.lower() or "resource" in err_str.lower():
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Gemini API rate limit exceeded during file upload fallback."
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload file to Gemini Files API: {err_str}"
            )

        poll_count = 0
        max_polls = 60
        while hasattr(gemini_file, "state") and str(gemini_file.state).upper() in ("PROCESSING", "STATE_PROCESSING"):
            if poll_count >= max_polls:
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail=f"Timed out waiting for file '{filename}' processing on Gemini servers."
                )
            time.sleep(2)
            gemini_file = client.files.get(name=gemini_file.name)
            poll_count += 1

        if hasattr(gemini_file, "state") and str(gemini_file.state).upper() in ("FAILED", "STATE_FAILED"):
            error_msg = getattr(gemini_file, "error", "File processing failed on Gemini servers.")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Gemini file processing failed: {error_msg}"
            )

        return gemini_file

    def _cleanup_gemini_file(self, client, gemini_file):
        if not gemini_file or not hasattr(gemini_file, "name"):
            return
        try:
            client.files.delete(name=gemini_file.name)
        except Exception:
            pass

    def _select_model(self, model_name: Optional[str]) -> str:
        if model_name and "gemini" in model_name.lower():
            return model_name.strip()
        env_model = os.getenv("GEMINI_MODEL")
        if env_model and env_model.strip():
            return env_model.strip()
        return "gemini-2.5-flash"

    def analyze_file(
        self,
        file_path: str,
        filename: str,
        mime_type: str,
        prompt: str,
        model_name: Optional[str] = None
    ) -> AnalysisResult:
        client = self._get_client()
        target_model = self._select_model(model_name)
        gemini_file = None

        try:
            gemini_file = self._upload_and_wait(client, file_path, filename, mime_type)
            contents = [gemini_file, prompt]

            response = client.models.generate_content(
                model=target_model,
                contents=contents
            )

            usage_data = {}
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                um = response.usage_metadata
                usage_data = {
                    "promptTokens": getattr(um, "prompt_token_count", 0),
                    "candidatesTokens": getattr(um, "candidates_token_count", 0),
                    "totalTokens": getattr(um, "total_token_count", 0),
                }

            analysis_text = response.text if hasattr(response, "text") and response.text else "No analysis output returned."

            return AnalysisResult(
                success=True,
                filename=filename,
                mimeType=mime_type,
                analysis=analysis_text,
                usage=usage_data,
                provider="gemini-files-fallback"
            )
        finally:
            if gemini_file:
                self._cleanup_gemini_file(client, gemini_file)

    def analyze_file_stream(
        self,
        file_path: str,
        filename: str,
        mime_type: str,
        prompt: str,
        model_name: Optional[str] = None
    ) -> Generator[str, None, None]:
        client = self._get_client()
        target_model = self._select_model(model_name)
        gemini_file = None

        try:
            gemini_file = self._upload_and_wait(client, file_path, filename, mime_type)
            contents = [gemini_file, prompt]

            response_stream = client.models.generate_content_stream(
                model=target_model,
                contents=contents
            )

            prompt_tokens = 0
            candidates_tokens = 0
            total_tokens = 0

            for chunk in response_stream:
                chunk_text = getattr(chunk, "text", "") or ""
                if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                    um = chunk.usage_metadata
                    prompt_tokens = getattr(um, "prompt_token_count", prompt_tokens)
                    candidates_tokens = getattr(um, "candidates_token_count", candidates_tokens)
                    total_tokens = getattr(um, "total_token_count", total_tokens)

                if chunk_text:
                    payload = f"data: {JSONResponse({'chunk': chunk_text}).body.decode('utf-8')}\n\n"
                    yield payload

            final_meta = {
                "done": True,
                "filename": filename,
                "mimeType": mime_type,
                "usage": {
                    "promptTokens": prompt_tokens,
                    "candidatesTokens": candidates_tokens,
                    "totalTokens": total_tokens
                }
            }
            yield f"data: {JSONResponse(final_meta).body.decode('utf-8')}\n\n"
        finally:
            if gemini_file:
                self._cleanup_gemini_file(client, gemini_file)


# ─── GPT-120B OSS Provider Implementation (Primary Model) ────────────────────

class GPT120BFileAnalysisProvider(BaseFileAnalysisProvider):
    def __init__(self, fallback_provider: Optional[BaseFileAnalysisProvider] = None):
        self.fallback_provider = fallback_provider or GeminiFileAnalysisProvider()

    def get_provider_name(self) -> str:
        return "gpt-120b"

    def _get_api_credentials(self, model_override: Optional[str] = None):
        model = model_override or os.getenv("NVIDIA_LLM_MODEL") or os.getenv("GROQ_LLM_MODEL") or "openai/gpt-oss-120b"

        # Check Groq Key first if set
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key and groq_key.strip():
            groq_model = os.getenv("GROQ_LLM_MODEL", "qwen/qwen3.6-27b")
            return {
                "key": groq_key.strip(),
                "url": "https://api.groq.com/openai/v1/chat/completions",
                "model": groq_model
            }

        # Check NVIDIA Key (NVIDIA_LLM_MODEL="openai/gpt-oss-120b")
        nvidia_key = os.getenv("NVIDIA_API_KEY")
        if nvidia_key and nvidia_key.strip():
            return {
                "key": nvidia_key.strip(),
                "url": "https://integrate.api.nvidia.com/v1/chat/completions",
                "model": "openai/gpt-oss-120b"
            }

        raise ValueError("No GROQ_API_KEY or NVIDIA_API_KEY configured for GPT-120B OSS model.")

    def _extract_file_content(self, file_path: str, filename: str, mime_type: str) -> str:
        """Inbuilt text and document content extractor for GPT-120B OSS file analysis."""
        ext = os.path.splitext(filename)[1].lower()

        # PDF Extraction
        if mime_type == "application/pdf" or ext == ".pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(file_path)
                pages = []
                for i in range(min(len(reader.pages), 50)):
                    txt = reader.pages[i].extract_text() or ""
                    if txt.strip():
                        pages.append(f"[Page {i+1}]\n{txt.strip()}")
                if pages:
                    return "\n\n".join(pages)
            except Exception as e:
                logger.warning(f"pypdf extraction failed for {filename}: {e}")

        # Text, Code, CSV, JSON, LOG, TeX, HTML
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(120000)
                return content
        except Exception as e:
            logger.warning(f"Text reading failed for {filename}: {e}")
            return f"[Binary file content '{filename}' ({mime_type})]"

    def analyze_file(
        self,
        file_path: str,
        filename: str,
        mime_type: str,
        prompt: str,
        model_name: Optional[str] = None
    ) -> AnalysisResult:
        try:
            creds = self._get_api_credentials(model_name)
            file_text = self._extract_file_content(file_path, filename, mime_type)

            full_system_prompt = (
                f"You are OverBranch's GPT-120B OSS AI File Analyzer. Analyze the attached file carefully according to user instructions."
            )
            user_content = f"📎 Attached File: '{filename}' ({mime_type})\n\n--- FILE CONTENT START ---\n{file_text}\n--- FILE CONTENT END ---\n\nUser Prompt: {prompt}"

            logger.info(f"Sending file analysis request for '{filename}' to GPT-120B OSS model ({creds['model']})...")
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
                "max_tokens": 4096
            }

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
                    provider="gpt-120b"
                )
            else:
                logger.warning(f"GPT-120B API returned status {resp.status_code}: {resp.text[:200]}. Falling back to Gemini Files API...")

        except Exception as err:
            logger.warning(f"GPT-120B OSS analysis failed ({err}). Executing automatic fallback to Gemini Files API upload model...")

        # Fallback to Gemini Files API upload model
        return self.fallback_provider.analyze_file(
            file_path=file_path,
            filename=filename,
            mime_type=mime_type,
            prompt=prompt,
            model_name=model_name
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
            creds = self._get_api_credentials(model_name)
            file_text = self._extract_file_content(file_path, filename, mime_type)

            full_system_prompt = (
                f"You are OverBranch's GPT-120B OSS AI File Analyzer. Analyze the attached file carefully according to user instructions."
            )
            user_content = f"📎 Attached File: '{filename}' ({mime_type})\n\n--- FILE CONTENT START ---\n{file_text}\n--- FILE CONTENT END ---\n\nUser Prompt: {prompt}"

            logger.info(f"Streaming file analysis for '{filename}' with GPT-120B OSS ({creds['model']})...")
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
                "max_tokens": 4096,
                "stream": True
            }

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
                logger.warning(f"GPT-120B stream API returned status {resp.status_code}. Executing fallback stream to Gemini Files API...")

        except Exception as err:
            logger.warning(f"GPT-120B stream failed ({err}). Executing fallback stream to Gemini Files API...")

        # Delegate streaming execution to Fallback Gemini Files API provider
        yield from self.fallback_provider.analyze_file_stream(
            file_path=file_path,
            filename=filename,
            mime_type=mime_type,
            prompt=prompt,
            model_name=model_name
        )


# ─── Provider Registry ────────────────────────────────────────────────────────

class FileAnalysisRegistry:
    def __init__(self):
        self._providers: Dict[str, BaseFileAnalysisProvider] = {}
        gemini_provider = GeminiFileAnalysisProvider()
        gpt120b_provider = GPT120BFileAnalysisProvider(fallback_provider=gemini_provider)

        self.register_provider("gpt-120b", gpt120b_provider)
        self.register_provider("openai/gpt-oss-120b", gpt120b_provider)
        self.register_provider("groq", gpt120b_provider)
        self.register_provider("gemini", gemini_provider)

    def register_provider(self, name: str, provider: BaseFileAnalysisProvider):
        self._providers[name.lower()] = provider

    def get_provider(self, name: str = "gpt-120b") -> BaseFileAnalysisProvider:
        if not name or name.lower() in ("default", "gpt-120b", "openai/gpt-oss-120b", "groq"):
            return self._providers.get("gpt-120b")
        provider = self._providers.get(name.lower())
        if not provider:
            return self._providers.get("gpt-120b")
        return provider

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
    Processes file via GPT-120B OSS with automatic fallback to Gemini Files API.
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
