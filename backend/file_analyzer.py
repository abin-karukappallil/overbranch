"""
file_analyzer.py — AI File Analysis Module for OverBranch

Supports direct FILE + USER PROMPT -> LLM multimodal analysis using Gemini Files API.
Architecture is provider-independent (BaseFileAnalysisProvider) so future engines
(OpenAI, Claude, etc.) can be seamlessly registered.
"""

import os
import re
import time
import uuid
import shutil
import tempfile
import logging
import mimetypes
from abc import ABC, abstractmethod
from typing import Dict, Any, Generator, Optional, List, AsyncGenerator
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Query
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

# Common extensions to MIME mapping fallback
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
    # Remove directory separators and null bytes
    clean = os.path.basename(filename)
    clean = re.sub(r'[\r\n\t\0]', '', clean)
    # Replace non-alphanumeric (except dot, dash, underscore) with underscore
    clean = re.sub(r'[^\w\.\-]', '_', clean)
    return clean[:255] or "unnamed_file"

def detect_mime_type(filename: str, header_mime: str, file_path: str) -> str:
    """
    Determines MIME type safely without trusting client-provided header alone.
    Uses magic bytes inspection + file extension mapping fallback.
    """
    ext = os.path.splitext(filename)[1].lower()
    
    # 1. Read first 2048 bytes for magic signature checks
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

    # 2. Check extension mapping table
    if ext in EXTENSION_MIME_MAP:
        return EXTENSION_MIME_MAP[ext]

    # 3. Use standard mimetypes guess
    guessed_type, _ = mimetypes.guess_type(filename)
    if guessed_type:
        return guessed_type

    # 4. Check client header if reasonable
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
    provider: str = "gemini"


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


# ─── Gemini Provider Implementation ──────────────────────────────────────────

class GeminiFileAnalysisProvider(BaseFileAnalysisProvider):
    def __init__(self):
        self._client = None

    def get_provider_name(self) -> str:
        return "gemini"

    def _get_client(self):
        """Initializes and returns google-genai Client securely."""
        try:
            from google import genai
        except ImportError:
            raise RuntimeError("The 'google-genai' package is not installed on the server.")

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key or not api_key.strip():
            raise ValueError("No GEMINI_API_KEY or GOOGLE_API_KEY configured in backend environment (.env).")

        return genai.Client(api_key=api_key.strip())

    def _upload_and_wait(self, client, file_path: str, filename: str, mime_type: str):
        """
        Uploads file to Gemini Files API and waits until file state is ACTIVE.
        Returns the Gemini File reference object.
        """
        from google.genai import types

        logger.info(f"Uploading file '{filename}' ({mime_type}) to Gemini Files API...")
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
                    detail="Gemini API rate limit exceeded during file upload. Please wait a moment and try again."
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload file to Gemini Files API: {err_str}"
            )

        # Wait if file is processing (e.g. video/large file)
        poll_count = 0
        max_polls = 60  # max 2 minutes wait
        while hasattr(gemini_file, "state") and str(gemini_file.state).upper() in ("PROCESSING", "STATE_PROCESSING"):
            if poll_count >= max_polls:
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail=f"Timed out waiting for file '{filename}' processing on Gemini servers."
                )
            logger.info(f"Waiting for Gemini file '{filename}' processing... (poll {poll_count + 1})")
            time.sleep(2)
            gemini_file = client.files.get(name=gemini_file.name)
            poll_count += 1

        if hasattr(gemini_file, "state") and str(gemini_file.state).upper() in ("FAILED", "STATE_FAILED"):
            error_msg = getattr(gemini_file, "error", "File processing failed on Gemini servers.")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Gemini file processing failed: {error_msg}"
            )

        logger.info(f"Gemini file uploaded successfully: name={gemini_file.name}, uri={getattr(gemini_file, 'uri', 'N/A')}")
        return gemini_file

    def _cleanup_gemini_file(self, client, gemini_file):
        """Cleanly deletes file from Gemini cloud storage after request completion."""
        if not gemini_file or not hasattr(gemini_file, "name"):
            return
        try:
            client.files.delete(name=gemini_file.name)
            logger.info(f"Cleaned up Gemini file remote reference: {gemini_file.name}")
        except Exception as e:
            logger.warning(f"Failed to delete remote Gemini file {gemini_file.name}: {e}")

    def _select_model(self, model_name: Optional[str]) -> str:
        if model_name and model_name.strip():
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
            # 1. Upload original file directly to Gemini Files API
            gemini_file = self._upload_and_wait(client, file_path, filename, mime_type)

            # 2. Send uploaded file reference + user prompt in same request
            contents = [gemini_file, prompt]

            logger.info(f"Sending file '{filename}' and prompt to Gemini model '{target_model}'...")
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
                provider="gemini"
            )

        except HTTPException:
            raise
        except Exception as err:
            err_str = str(err)
            logger.error(f"Error during Gemini file analysis for '{filename}': {err_str}", exc_info=True)
            if "429" in err_str or "quota" in err_str.lower() or "resource" in err_str.lower():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Gemini API quota/rate limit exceeded. Please try again in a few moments."
                )
            elif "context" in err_str.lower() or "token" in err_str.lower() or "too large" in err_str.lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File or prompt exceeds model context limits."
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gemini analysis error: {err_str}"
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

            logger.info(f"Streaming file analysis for '{filename}' using model '{target_model}'...")
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

        except Exception as err:
            err_str = str(err)
            logger.error(f"Error during streaming Gemini file analysis for '{filename}': {err_str}", exc_info=True)
            err_event = {
                "error": True,
                "detail": err_str
            }
            yield f"data: {JSONResponse(err_event).body.decode('utf-8')}\n\n"
        finally:
            if gemini_file:
                self._cleanup_gemini_file(client, gemini_file)


# ─── Provider Registry ────────────────────────────────────────────────────────

class FileAnalysisRegistry:
    def __init__(self):
        self._providers: Dict[str, BaseFileAnalysisProvider] = {}
        self.register_provider("gemini", GeminiFileAnalysisProvider())

    def register_provider(self, name: str, provider: BaseFileAnalysisProvider):
        self._providers[name.lower()] = provider

    def get_provider(self, name: str = "gemini") -> BaseFileAnalysisProvider:
        provider = self._providers.get(name.lower())
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported LLM provider '{name}'. Available providers: {list(self._providers.keys())}"
            )
        return provider

registry = FileAnalysisRegistry()


# ─── Fallback Helper for Unsupported Files ───────────────────────────────────

def process_unsupported_file_fallback(file_path: str, filename: str, mime_type: str) -> str:
    """
    Fallback parser for text/code/custom binary files if direct native API upload
    needs plain text extraction.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(100000)  # Read up to 100k chars
            return f"[Extracted content from '{filename}']\n{text}"
    except Exception as e:
        logger.warning(f"Fallback reading failed for {filename}: {e}")
        return f"[Binary file '{filename}' of type '{mime_type}']"


# ─── Fast API Route Handler ───────────────────────────────────────────────────

@router.post("/ai/analyze-file")
async def analyze_file_endpoint(
    file: UploadFile = File(..., description="Uploaded original file"),
    prompt: str = Form(..., description="User prompt describing analysis instructions"),
    provider: Optional[str] = Form("gemini", description="LLM provider (default: gemini)"),
    model: Optional[str] = Form(None, description="Specific model override"),
    stream: Optional[bool] = Form(False, description="Stream output via SSE")
):
    """
    POST /api/ai/analyze-file
    Accepts multipart/form-data with original file and user prompt.
    Uploads file to Gemini Files API and sends [uploaded_file, prompt] to Gemini.
    """
    if not prompt or not prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prompt is required. Please provide instructions for analyzing the file."
        )

    # 1. Isolated temporary directory creation
    temp_dir = tempfile.mkdtemp(prefix="overbranch_ai_")
    safe_name = sanitize_filename(file.filename or "uploaded_file")
    temp_file_path = os.path.join(temp_dir, safe_name)

    try:
        # 2. Save uploaded stream safely to disk
        file_size = 0
        with open(temp_file_path, "wb") as out_file:
            while chunk := await file.read(1024 * 1024):  # 1MB chunk reading
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

        # 3. Detect true MIME type
        detected_mime = detect_mime_type(safe_name, file.content_type or "", temp_file_path)
        logger.info(f"Processing uploaded file: '{safe_name}' ({detected_mime}, {file_size} bytes)")

        # 4. Fetch analysis provider
        analysis_provider = registry.get_provider(provider or "gemini")

        # 5. Handle Streaming vs Non-streaming
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
