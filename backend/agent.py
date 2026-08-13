"""
agent.py — Thin Agent Router

Orchestrates the full AI pipeline:
Embed → Retrieve → Build Context → Memory → Build Prompt → LLM → Parse → Return
"""
import os
import json
import re
import logging
import base64
import io
try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings, ChatNVIDIA
from langchain_core.messages import SystemMessage, HumanMessage

from vector_sync import get_qdrant_client, ensure_qdrant_collection, COLLECTION_NAME
import retriever
import context_builder
import prompt_builder
from memory import conversation_memory, project_memory
from tools import AI_TOOLS, process_tool_calls

load_dotenv(override=True)

logger = logging.getLogger("agent")
logging.basicConfig(level=logging.INFO)

router = APIRouter()


try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False



class AttachedFile(BaseModel):
    filename: str = Field(..., description="Uploaded file name")
    content: str = Field(..., description="File content in text or base64")
    file_type: Optional[str] = Field("text/plain", description="MIME type or file extension")


class AgentChatRequest(BaseModel):
    project_id: str = Field(..., description="Project ID or UUID")
    file_path: str = Field(..., description="Path of the TeX file")
    user_prompt: str = Field(..., description="User's editing request or question")
    current_code: Optional[str] = Field(None, description="Current editor LaTeX content in plain text")
    attached_file: Optional[AttachedFile] = Field(None, description="Optional attached file from user chat")
    model: Optional[str] = Field(None, description="Primary LLM model name")
    fallback_model: Optional[str] = Field(None, description="Fallback LLM model name")



def process_attached_file_content(filename: str, content: str, file_type: str) -> str:
    """
    Safely extracts text content from uploaded files (PDFs, text files, Data URLs).
    Prevents corrupt binary streams from causing errors in prompt building or LLM.
    """
    if not content:
        return ""

    is_pdf = (
        (file_type and "pdf" in file_type.lower()) or
        filename.lower().endswith(".pdf") or
        content.startswith("data:application/pdf")
    )

    if is_pdf:
        if not HAS_PYPDF:
            logger.warning(f"pypdf package not installed, skipping text extraction for '{filename}'")
            return f"[Uploaded PDF file: '{filename}']"
        try:
            b64_data = content
            if "," in b64_data:
                b64_data = b64_data.split(",", 1)[1]

            raw_bytes = base64.b64decode(b64_data)
            reader = pypdf.PdfReader(io.BytesIO(raw_bytes))

            extracted_pages = []
            max_pages = min(len(reader.pages), 12)  # Cap at top 12 pages for ultra-fast parsing
            for i in range(max_pages):
                txt = reader.pages[i].extract_text() or ""
                if txt.strip():
                    extracted_pages.append(f"[Page {i+1}]\n{txt.strip()}")

            if extracted_pages:
                full_text = "\n\n".join(extracted_pages)
                if len(full_text) > 6000:
                    full_text = full_text[:6000] + "\n...[TRUNCATED FOR FAST PARSING]"
                logger.info(f"Fast-extracted {len(extracted_pages)} text pages from PDF '{filename}'")
                return full_text
            else:
                return f"[PDF Document '{filename}' uploaded — contains {len(reader.pages)} page(s)]"
        except Exception as pdf_err:
            logger.warning(f"Failed to extract text from PDF '{filename}': {pdf_err}")
            return f"[Uploaded PDF file: '{filename}']"

    if content.startswith("data:") and ";base64," in content:
        try:
            b64_data = content.split(";base64,", 1)[1]
            txt = base64.b64decode(b64_data).decode("utf-8", errors="replace")
            return txt[:6000] if len(txt) > 6000 else txt
        except Exception:
            return content

    return content[:6000] if len(content) > 6000 else content


def get_nvidia_embeddings() -> NVIDIAEmbeddings:
    nvidia_api_key = os.getenv("NVIDIA_API_KEY")
    return NVIDIAEmbeddings(
        model="nvidia/nemotron-3-embed-1b",
        nvidia_api_key=nvidia_api_key
    )


def get_genai_client() -> genai.Client:
    """
    Main Agent LLM Engine selection using native Google GenAI SDK:
    Reads GEMINI_API_KEY or GOOGLE_API_KEY from environment.
    """
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not gemini_key or not gemini_key.strip():
        raise ValueError("No valid GEMINI_API_KEY configured in backend environment (.env).")
    return genai.Client(api_key=gemini_key.strip())




# ─── Response Parsing Utilities ───────────────────────────────────────────────

def sanitize_explanation_text(text: str) -> str:
    """Removes internal chunk references (e.g. CHUNK 1, in CHUNK 2, from CHUNK 3) from user-facing text."""
    if not text or not isinstance(text, str):
        return text or ""
    # Strip phrases like "in CHUNK 1", "from CHUNK 2", "CHUNK 3:", "[CHUNK 4]", "CHUNK 5"
    cleaned = re.sub(r'(?i)\b(?:in|from|for|of)?\s*\[?CHUNK\s*\d+\]?:?\s*', '', text)
    # Remove leading colons, hyphens, or extra whitespace left over
    cleaned = re.sub(r'^\s*[:\-]\s*', '', cleaned)
    # Clean up spaces before punctuation
    cleaned = re.sub(r'\s+([.,!?;])', r'\1', cleaned)
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned.strip()


def auto_repair_truncated_json(text: str) -> str:
    """Attempts to auto-close unclosed strings and JSON object braces if LLM output was truncated."""
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.MULTILINE)
        s = re.sub(r"\s*```$", "", s, flags=re.MULTILINE)

    if not s.endswith("}"):
        if not s.endswith('"'):
            s += '"'
        open_b = s.count('{')
        close_b = s.count('}')
        if open_b > close_b:
            s += '}' * (open_b - close_b)
    return s


def extract_fallback_chunks(text: str) -> Dict[str, Any]:
    """Fallback regex extractor for proposed_chunk when JSON parsing fails."""
    prop_match = re.search(r'"proposed_chunk"\s*:\s*"((?:[^"\\]|\\.)*)', text, re.DOTALL)
    orig_match = re.search(r'"original_chunk"\s*:\s*"((?:[^"\\]|\\.)*)', text, re.DOTALL)
    exp_match = re.search(r'"explanation"\s*:\s*"((?:[^"\\]|\\.)*)', text, re.DOTALL)

    if prop_match:
        prop = prop_match.group(1).replace('\\\\', '\\').replace('\\"', '"').replace('\\n', '\n')
        orig = orig_match.group(1).replace('\\\\', '\\').replace('\\"', '"').replace('\\n', '\n') if orig_match else ""
        exp = exp_match.group(1).replace('\\\\', '\\').replace('\\"', '"').replace('\\n', '\n') if exp_match else "Extracted LaTeX content."
        return {
            "original_chunk": orig,
            "proposed_chunk": prop,
            "explanation": exp
        }
    raise ValueError(f"LLM output could not be parsed as valid JSON: {text}")


def extract_latex_from_response(text: str) -> Optional[str]:
    """Extracts code block from ```latex ... ``` response format (closed or unclosed) or raw LaTeX document/frame."""
    if not text or not isinstance(text, str):
        return None

    # Strategy 1: Fenced code block (closed or unclosed)
    fenced_match = re.search(r"```(?:latex|tex)?\s*\n([\s\S]*?)(?:```|$)", text, re.IGNORECASE)
    if fenced_match:
        candidate = fenced_match.group(1).strip()
        if candidate:
            return candidate

    # Strategy 2: Raw LaTeX document from \documentclass to \end{document} (or end of string if unclosed)
    raw_doc_match = re.search(r"(\\documentclass[\s\S]*?(?:\\end\{document\}|$))", text, re.IGNORECASE)
    if raw_doc_match:
        candidate = raw_doc_match.group(1).strip()
        if candidate:
            return candidate

    # Strategy 3: Any LaTeX environment from \begin{...} to \end{...} (or end of string)
    env_match = re.search(r"(\\begin\{[a-zA-Z*]+\}[\s\S]*?(?:\\end\{[a-zA-Z*]+\}|$))", text, re.IGNORECASE)
    if env_match:
        candidate = env_match.group(1).strip()
        if candidate:
            return candidate

    # Strategy 4: Any LaTeX command block starting with \section, \title, \frame, \usepackage, etc.
    cmd_match = re.search(r"(\\(?:section|title|frame|usepackage|item|maketitle|tableofcontents)[\s\S]*)", text, re.IGNORECASE)
    if cmd_match:
        candidate = cmd_match.group(1).strip()
        if candidate:
            return candidate

    return None


def extract_chunk_latex(text: str) -> Optional[str]:
    """Extracts LaTeX chunk after UPDATED_LATEX: marker if present."""
    marker = text.find("UPDATED_LATEX:")
    if marker == -1:
        return extract_latex_from_response(text)
    after_marker = text[marker:]
    return extract_latex_from_response(after_marker)


def stringify_content(content: Any) -> str:
    """Normalizes string, list of strings, or list of content block dicts into a single plain text string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            elif hasattr(item, "text"):
                parts.append(str(getattr(item, "text")))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content) if content is not None else ""


def clean_json_response(text: Any) -> Dict[str, Any]:
    """Multi-strategy response parser: fenced LaTeX, JSON, auto-repair, regex fallback."""
    raw_text = stringify_content(text)
    cleaned = raw_text.strip()

    if cleaned.startswith("```"):
        stripped_json_block = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
        stripped_json_block = re.sub(r"\s*```$", "", stripped_json_block, flags=re.MULTILINE)
    else:
        stripped_json_block = cleaned

    # Attempt 1: Direct JSON parse
    try:
        return json.loads(stripped_json_block, strict=False)
    except Exception:
        pass

    # Attempt 2: Auto-repair truncated JSON
    try:
        repaired = auto_repair_truncated_json(stripped_json_block)
        return json.loads(repaired, strict=False)
    except Exception:
        pass

    # Attempt 3: Escape unescaped LaTeX backslashes
    try:
        fixed_slashes = re.sub(r'(?<!\\)\\([a-zA-Z%&$#_{}\[\]])', r'\\\\\1', stripped_json_block)
        repaired_slashes = auto_repair_truncated_json(fixed_slashes)
        return json.loads(repaired_slashes, strict=False)
    except Exception:
        pass

    # Attempt 4: Extract JSON object via regex
    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        raw_match = json_match.group(0)
        try:
            return json.loads(raw_match, strict=False)
        except Exception:
            try:
                fixed_raw = re.sub(r'(?<!\\)\\([a-zA-Z%&$#_{}\[\]])', r'\\\\\1', raw_match)
                repaired_raw = auto_repair_truncated_json(fixed_raw)
                return json.loads(repaired_raw, strict=False)
            except Exception:
                pass

    # Attempt 5: Regex extraction of proposed_chunk
    try:
        return extract_fallback_chunks(cleaned)
    except Exception:
        pass

    # Attempt 6: Extract any LaTeX code block or LaTeX environment (even if unclosed or surrounded by prose)
    extracted_latex = extract_chunk_latex(cleaned)
    if extracted_latex:
        prose_parts = cleaned.split("```")[0].strip()
        explanation = prose_parts if prose_parts and len(prose_parts) < 300 else "Generated LaTeX document proposal."
        return {
            "plan": "Generated LaTeX code snippet.",
            "edits": [{
                "original_chunk": "",
                "proposed_chunk": extracted_latex,
                "explanation": explanation
            }],
            "original_chunk": "",
            "proposed_chunk": extracted_latex,
            "explanation": explanation
        }

    # Attempt 7: Safe fallback returning raw response text as explanation without crashing
    return {
        "plan": "",
        "edits": [],
        "original_chunk": "",
        "proposed_chunk": "",
        "explanation": cleaned if cleaned else "AI response received."
    }


# ─── Main Agent Endpoint ──────────────────────────────────────────────────────

from typing import List, Optional, Dict, Any, Tuple


def categorize_user_intent(user_prompt: str) -> Tuple[str, bool]:
    """
    Categorizes user intent into 3 modes:
    1. ("GENERAL_CHAT", False) — Pure greetings & syntax questions ("hi", "how to center text in LaTeX?"). Vector search: False, Edits: False.
    2. ("INSPECT_DOCUMENT", True) — Document inquiries ("where is abstract?", "what packages are used in my document?"). Vector search: True, Edits: False.
    3. ("EDIT_DOCUMENT", True) — Edit/generation instructions ("add section", "generate ppt for..."). Vector search: True, Edits: True.
    """
    text = user_prompt.lower().strip()

    # Pure greetings
    greetings = {"hi", "hello", "hey", "good morning", "good evening", "who are you", "what can you do", "help", "thanks", "thank you"}
    if text in greetings or (len(text.split()) <= 2 and any(g == text for g in greetings)):
        return ("GENERAL_CHAT", False)

    how_to_syntax_keywords = ["how do i", "how to", "how can i", "what is", "explain", "how does", "syntax for", "example of"]
    my_doc_references = ["my code", "my document", "my title", "my file", "my paper", "this paper", "this document", "this code", "my project"]

    # Pure syntax explanation request without asking to modify/create
    if any(h in text for h in how_to_syntax_keywords) and not any(r in text for r in my_doc_references):
        gen_triggers = ["generate", "create", "make", "build", "draw", "write", "ppt", "slide", "beamer", "presentation", "table", "figure", "section", "add", "insert"]
        if not any(g in text for g in gen_triggers):
            return ("GENERAL_CHAT", False)

    # Document Inspection / Inquiry Triggers
    doc_inquiry_keywords = ["where is", "find in my", "what packages", "check my", "show my", "list sections", "is my"]
    if any(inq in text for inq in doc_inquiry_keywords):
        return ("INSPECT_DOCUMENT", True)

    # All other prompts default to EDIT_DOCUMENT so tool binding & JSON edit proposals are active
    return ("EDIT_DOCUMENT", True)


@router.post("/api/agent/chat")
def agent_chat(req: AgentChatRequest):
    """
    Full RAG Agent Pipeline with SSE streaming progress events.
    Sends real-time progress updates then the final JSON result.
    """
    from fastapi.responses import StreamingResponse
    import time

    def sse_event(event_type: str, data: dict) -> str:
        """Format a single SSE event."""
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    def pipeline_generator():
        try:
            # Step 1: Categorize intent
            yield sse_event("progress", {"step": "analyze", "message": "Analyzing prompt...", "icon": "zap"})
            mode, is_search_needed = categorize_user_intent(req.user_prompt)
            print(f"\n [AGENT CHAT REQUEST RECEIVED]\n  ► Prompt: '{req.user_prompt}'\n  ► Project ID: {req.project_id}\n  ► Mode: {mode} (Vector Search = {is_search_needed})")

            # Fast-path: Bypass vector search for attached files & new presentation generation to save 2-3s
            is_new_doc_request = any(kw in req.user_prompt.lower() for kw in ["ppt", "presentation", "beamer", "slide", "create ppt", "make ppt", "generate ppt"])
            if req.attached_file or is_new_doc_request:
                is_search_needed = False

            yield sse_event("progress", {"step": "intent", "message": f"Mode: {mode.replace('_', ' ').title()}", "icon": "brain"})

            # Fast-path for simple greetings
            text_clean = req.user_prompt.lower().strip()
            greetings_set = {"hi", "hello", "hey", "good morning", "good evening", "greetings"}
            if text_clean in greetings_set or (len(text_clean.split()) <= 2 and any(g in text_clean for g in greetings_set)):
                yield sse_event("result", {
                    "plan": "", "edits": [], "original_chunk": "", "proposed_chunk": "",
                    "explanation": "Hello! How can I help you with your LaTeX document or Beamer slides today?",
                    "retrieved_chunks_count": 0,
                })
                return

            # Step 2: Vector search
            retrieved_chunks = []
            if is_search_needed:
                try:
                    yield sse_event("progress", {"step": "embed", "message": "Generating query embedding...", "icon": "search"})
                    embeddings_model = get_nvidia_embeddings()
                    prompt_embedding = embeddings_model.embed_query(req.user_prompt)

                    qdrant = get_qdrant_client()
                    ensure_qdrant_collection(qdrant)

                    yield sse_event("progress", {"step": "search", "message": "Searching document vectors...", "icon": "database"})
                    retrieved_chunks = retriever.retrieve(
                        qdrant_client=qdrant,
                        collection_name=COLLECTION_NAME,
                        query_embedding=prompt_embedding,
                        project_id=req.project_id,
                        file_path=req.file_path,
                    )
                    yield sse_event("progress", {"step": "retrieved", "message": f"Retrieved {len(retrieved_chunks)} chunks", "icon": "file-text"})
                except Exception as qdrant_err:
                    yield sse_event("progress", {"step": "search_warn", "message": "Vector search unavailable, continuing...", "icon": "alert-triangle"})
            else:
                yield sse_event("progress", {"step": "skip_search", "message": "Direct response mode", "icon": "message-circle"})

            # Step 3: Build context
            yield sse_event("progress", {"step": "context", "message": "Building document context...", "icon": "layers"})
            context_str = context_builder.build_context(retrieved_chunks)

            # Step 4: Load memory
            conv_ctx = conversation_memory.get_conversation_context(req.project_id)
            proj_ctx = project_memory.get_project_context(req.project_id)

            if not project_memory.is_scanned(req.project_id):
                try:
                    from pathlib import Path
                    uploads_base = Path(os.path.dirname(__file__)).parent / "uploads" / "projects"
                    import re as _re
                    safe_project = _re.sub(r'[^a-zA-Z0-9_-]', '_', req.project_id)
                    tex_path = uploads_base / safe_project / req.file_path
                    if tex_path.exists():
                        tex_content = tex_path.read_text(encoding="utf-8")
                        project_memory.scan_and_store(req.project_id, tex_content)
                        proj_ctx = project_memory.get_project_context(req.project_id)
                except Exception:
                    pass

            # Step 5: Build prompt
            yield sse_event("progress", {"step": "prompt", "message": "Assembling prompt...", "icon": "edit-3"})
            attached_info = None
            if req.attached_file:
                yield sse_event("progress", {"step": "file", "message": f"Extracting content from {req.attached_file.filename}...", "icon": "paperclip"})
                processed_content = process_attached_file_content(
                    filename=req.attached_file.filename,
                    content=req.attached_file.content,
                    file_type=req.attached_file.file_type or "text/plain",
                )
                attached_info = {
                    "filename": req.attached_file.filename,
                    "file_type": req.attached_file.file_type or "text/plain",
                    "content": processed_content,
                }
                yield sse_event("progress", {"step": "file_done", "message": f"Attached: {req.attached_file.filename}", "icon": "check-square"})

            messages = prompt_builder.build_prompt(
                user_request=req.user_prompt,
                retrieved_context=context_str,
                conversation_context=conv_ctx,
                project_context=proj_ctx,
                attached_file_info=attached_info,
                current_code=req.current_code,
            )

            # Step 6: Invoke LLM
            system_content = messages[0].content if (isinstance(messages, list) and len(messages) > 0) else ""
            user_content = messages[1].content if (isinstance(messages, list) and len(messages) > 1) else req.user_prompt

            # Build Gemini API contents payload (supports native PDF and Image parts + text prompt)
            contents_payload = []

            if req.attached_file:
                fn = req.attached_file.filename
                ft = (req.attached_file.file_type or "text/plain").lower()
                raw_content = req.attached_file.content or ""
                lower_fn = fn.lower()

                if "pdf" in ft or lower_fn.endswith(".pdf") or raw_content.startswith("data:application/pdf"):
                    try:
                        b64_data = raw_content
                        if "," in b64_data:
                            b64_data = b64_data.split(",", 1)[1]
                        pdf_bytes = base64.b64decode(b64_data)
                        pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
                        contents_payload.append(pdf_part)
                        yield sse_event("progress", {"step": "native_pdf", "message": f"Sending native PDF '{fn}' ({len(pdf_bytes)} bytes) to Gemini...", "icon": "file-text"})
                        logger.info(f"Attached native Gemini PDF Part ({len(pdf_bytes)} bytes)")
                    except Exception as pdf_part_err:
                        logger.warning(f"Native PDF Part construction note: {pdf_part_err}")

                elif ft.startswith("image/") or raw_content.startswith("data:image/"):
                    try:
                        mime = ft if ft.startswith("image/") else "image/png"
                        b64_data = raw_content
                        if "," in b64_data:
                            hdr, b64_data = b64_data.split(",", 1)
                            if "data:" in hdr and ";base64" in hdr:
                                mime = hdr.split("data:", 1)[1].split(";base64", 1)[0]
                        img_bytes = base64.b64decode(b64_data)
                        img_part = types.Part.from_bytes(data=img_bytes, mime_type=mime)
                        contents_payload.append(img_part)
                        yield sse_event("progress", {"step": "native_img", "message": f"Sending native Image '{fn}' to Gemini...", "icon": "image"})
                    except Exception as img_part_err:
                        logger.warning(f"Native Image Part construction note: {img_part_err}")

            contents_payload.append(user_content)

            client = get_genai_client()
            primary_model = req.model or os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
            env_fallback = os.getenv("GEMINI_FALLBACK_MODEL") or os.getenv("FALLBACK_MODEL")
            req_fallback = req.fallback_model or env_fallback

            config = types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=6144,
                system_instruction=system_content if system_content else None,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            )

            default_fallbacks = [
                "gemini-2.5-flash",
                "gemini-3.1-flash-lite",
                "gemini-3.5-flash-lite",
                "gemini-2.5-flash-lite",
                "gemini-3.6-flash",
                "gemini-2.5-pro",
                "gemini-1.5-flash",
            ]

            models_to_try = [primary_model]
            if req_fallback and req_fallback not in models_to_try:
                models_to_try.append(req_fallback)
            for m in default_fallbacks:
                if m not in models_to_try:
                    models_to_try.append(m)

            yield sse_event("progress", {"step": "llm", "message": f"Generating with {primary_model}...", "icon": "sparkles"})

            response_text = None
            model_used = None
            is_fallback = False
            last_error = None

            for idx, current_model in enumerate(models_to_try):
                try:
                    if idx > 0:
                        yield sse_event("progress", {"step": "fallback", "message": f"Trying fallback model: {current_model}...", "icon": "refresh-cw"})
                    response = client.models.generate_content(
                        model=current_model,
                        contents=contents_payload,
                        config=config,
                    )
                    response_text = stringify_content(getattr(response, "text", response))
                    model_used = current_model
                    is_fallback = (idx > 0)
                    break
                except Exception as genai_err:
                    last_error = genai_err
                    print(f"  Model '{current_model}' failed: {genai_err}")

            # Cross-provider fallback to NVIDIA NIM if all Gemini models fail and NVIDIA_API_KEY is available
            if response_text is None and os.getenv("NVIDIA_API_KEY"):
                nvidia_model = os.getenv("NVIDIA_LLM_MODEL", "openai/gpt-oss-120b")
                yield sse_event("progress", {"step": "fallback_nvidia", "message": f"Trying NVIDIA NIM fallback ({nvidia_model})...", "icon": "refresh-cw"})
                try:
                    nvidia_llm = ChatNVIDIA(
                        model=nvidia_model,
                        nvidia_api_key=os.getenv("NVIDIA_API_KEY"),
                        temperature=0.1,
                    )
                    prompt_msgs = []
                    if system_content:
                        prompt_msgs.append(SystemMessage(content=system_content))
                    prompt_msgs.append(HumanMessage(content=user_content))
                    nv_res = nvidia_llm.invoke(prompt_msgs)
                    response_text = stringify_content(getattr(nv_res, "content", nv_res))
                    model_used = f"NVIDIA NIM ({nvidia_model})"
                    is_fallback = True
                except Exception as nv_err:
                    print(f"  NVIDIA NIM fallback failed: {nv_err}")
                    last_error = nv_err

            if response_text is None:
                yield sse_event("error", {"message": f"All primary and fallback models failed. Last error: {str(last_error)}"})
                return

            # Step 7: Parse response
            yield sse_event("progress", {"step": "parse", "message": "Parsing AI response...", "icon": "code"})
            parsed_result = clean_json_response(response_text)

            edits = parsed_result.get("edits", [])
            if not isinstance(edits, list):
                edits = []

            if not edits:
                orig = parsed_result.get("original_chunk", "")
                prop = parsed_result.get("proposed_chunk", "")
                exp = parsed_result.get("explanation", "")
                if orig or prop:
                    edits = [{"original_chunk": orig, "proposed_chunk": prop, "explanation": exp}]

            # Fast local extraction if no edits parsed from JSON schema
            if not edits:
                extracted_latex = extract_chunk_latex(response_text)
                if extracted_latex:
                    edits = [{
                        "original_chunk": "",
                        "proposed_chunk": extracted_latex,
                        "explanation": "Extracted LaTeX document proposal."
                    }]

            # Step 8: Compute edit line ranges for progress display
            if mode != "EDIT_DOCUMENT":
                edits = []
                first_orig = ""
                first_prop = ""
            else:
                first_orig = edits[0].get("original_chunk", "") if edits else parsed_result.get("original_chunk", "")
                first_prop = edits[0].get("proposed_chunk", "") if edits else parsed_result.get("proposed_chunk", "")

            if edits and req.current_code:
                for e in edits:
                    oc = e.get("original_chunk", "")
                    pc = e.get("proposed_chunk", "")
                    if oc and req.current_code and oc in req.current_code:
                        start_idx = req.current_code.index(oc)
                        start_line = req.current_code[:start_idx].count("\n") + 1
                        end_line = start_line + oc.count("\n")
                        yield sse_event("progress", {"step": "editing", "message": f"Editing lines {start_line}–{end_line}", "icon": "file-code"})
                    elif pc:
                        pc_lines = pc.count("\n") + 1
                        yield sse_event("progress", {"step": "inserting", "message": f"Inserting {pc_lines} new lines", "icon": "plus-circle"})

            overall_exp = sanitize_explanation_text(
                parsed_result.get("explanation", "") or (edits[0].get("explanation", "") if edits else "")
            )
            clean_plan = sanitize_explanation_text(parsed_result.get("plan", ""))

            clean_edits = []
            for e in edits:
                item = dict(e)
                if item.get("explanation"):
                    item["explanation"] = sanitize_explanation_text(item["explanation"])
                clean_edits.append(item)

            # Step 9: Store in conversation memory
            chunk_summaries = [c.get("summary", "") for c in retrieved_chunks if c.get("summary")]
            conversation_memory.add_turn(
                project_id=req.project_id,
                user_prompt=req.user_prompt,
                assistant_response=parsed_result,
                file_path=req.file_path,
                chunk_summaries=chunk_summaries,
            )

            fallback_notice = (
                f"Note: Primary model ({primary_model}) was unavailable. Used fallback model ({model_used})."
                if is_fallback
                else None
            )

            yield sse_event("progress", {"step": "done", "message": "Complete", "icon": "check"})

            # Final result
            yield sse_event("result", {
                "plan": clean_plan,
                "edits": clean_edits,
                "original_chunk": first_orig,
                "proposed_chunk": first_prop,
                "explanation": overall_exp,
                "retrieved_chunks_count": len(retrieved_chunks),
                "model_used": model_used,
                "is_fallback": is_fallback,
                "fallback_notice": fallback_notice,
            })

        except Exception as e:
            logger.error(f"Error in AI agent endpoint: {str(e)}", exc_info=True)
            yield sse_event("error", {"message": f"AI Agent execution failed: {str(e)}"})

    return StreamingResponse(
        pipeline_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
