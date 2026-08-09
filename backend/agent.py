"""
agent.py — Thin Agent Router

Orchestrates the full AI pipeline:
Embed → Retrieve → Build Context → Memory → Build Prompt → LLM → Parse → Return
"""
import os
import json
import re
import logging
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
    from langchain_groq import ChatGroq
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False


class AgentChatRequest(BaseModel):
    project_id: str = Field(..., description="Project ID or UUID")
    file_path: str = Field(..., description="Path of the TeX file")
    user_prompt: str = Field(..., description="User's editing request or question")
    current_code: Optional[str] = Field(None, description="Current editor LaTeX content in plain text")
    groq_api_key: Optional[str] = Field(None, description="Optional Groq API key from user")
    groq_model: Optional[str] = Field(None, description="Optional Groq model name selected by user")


def get_nvidia_embeddings() -> NVIDIAEmbeddings:
    nvidia_api_key = os.getenv("NVIDIA_API_KEY")
    return NVIDIAEmbeddings(
        model="nvidia/nemotron-3-embed-1b",
        nvidia_api_key=nvidia_api_key
    )


def get_chat_llm(
    model_override: Optional[str] = None,
    user_groq_key: Optional[str] = None,
    user_groq_model: Optional[str] = None,
    use_server_groq_first: bool = True
):
    """
    Main Agent LLM Engine selection:
    1. If user provided a Groq API key in UI: Use ChatGroq with user_groq_key and selected model.
    2. If user did not provide Groq API key: Use Groq with server GROQ_API_KEY and model 'openai/gpt-oss-120b' instead of NVIDIA.
    3. Fallback to ChatNVIDIA if server GROQ_API_KEY is not set.
    """
    has_user_groq = bool(user_groq_key and user_groq_key.strip())
    server_groq_key = os.getenv("GROQ_API_KEY")

    if HAS_GROQ and has_user_groq:
        selected_model = model_override or user_groq_model or os.getenv("GROQ_LLM_MODEL", "openai/gpt-oss-120b")
        logger.info(f"MAIN AGENT GROQ ENGINE (User Key): Executing Groq Model '{selected_model}'")
        return ChatGroq(
            model_name=selected_model,
            groq_api_key=user_groq_key.strip(),
            temperature=0.2,
            max_tokens=3072,
            request_timeout=30.0
        )

    # If user didn't provide a Groq API key: Use server GROQ_API_KEY with 'openai/gpt-oss-120b' instead of NVIDIA
    if HAS_GROQ and server_groq_key and server_groq_key.strip():
        selected_model = model_override or os.getenv("GROQ_DEFAULT_MODEL", "openai/gpt-oss-120b")
        logger.info(f"MAIN AGENT GROQ ENGINE (Server Key - gpt-oss-120b): Executing Groq Model '{selected_model}'")
        return ChatGroq(
            model_name=selected_model,
            groq_api_key=server_groq_key.strip(),
            temperature=0.2,
            max_tokens=3072,
            request_timeout=30.0
        )

    nvidia_api_key = os.getenv("NVIDIA_API_KEY")
    if nvidia_api_key and nvidia_api_key.strip():
        env_model = os.getenv("NVIDIA_LLM_MODEL")
        nvidia_model = "openai/gpt-oss-120b" if (not env_model or env_model in ["meta/llama-3.3-70b-instruct", "z-ai/glm-5.2"]) else env_model
        logger.info(f"MAIN AGENT NVIDIA ENGINE: Groq key absent and server Groq key missing, using ChatNVIDIA model '{nvidia_model}'")
        try:
            return ChatNVIDIA(
                model=nvidia_model,
                nvidia_api_key=nvidia_api_key.strip(),
                temperature=0.2,
                max_tokens=3072,
                timeout=30.0
            )
        except Exception as n_err:
            logger.warning(f"NVIDIA NIM initialization failed with {nvidia_model}: {n_err}")

    # Fallback to server GROQ_API_KEY if not used earlier
    if HAS_GROQ and server_groq_key and server_groq_key.strip():
        selected_model = model_override or "openai/gpt-oss-120b"
        return ChatGroq(
            model_name=selected_model,
            groq_api_key=server_groq_key.strip(),
            temperature=0.2,
            max_tokens=3072,
            request_timeout=30.0
        )

    raise ValueError("No valid AI API Key configured. Please configure your Groq API Key in the AI settings panel (🔑 Key icon).")


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
    """Extracts code block from ```latex ... ``` response format or raw LaTeX document/frame."""
    pattern = r"```(?:latex)?\s*\n([\s\S]*?)```"
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()

    raw_doc_match = re.search(r'(\\documentclass[\s\S]*?\\end\{document\}|\\begin\{frame\}[\s\S]*?\\end\{frame\}|\\begin\{[a-zA-Z*]+\}[\s\S]*?\\end\{[a-zA-Z*]+\})', text)
    if raw_doc_match:
        return raw_doc_match.group(1).strip()

    return None


def extract_chunk_latex(text: str) -> Optional[str]:
    """Extracts LaTeX chunk after UPDATED_LATEX: marker if present."""
    marker = text.find("UPDATED_LATEX:")
    if marker == -1:
        return extract_latex_from_response(text)
    after_marker = text[marker:]
    return extract_latex_from_response(after_marker)


def clean_json_response(text: str) -> Dict[str, Any]:
    """Multi-strategy response parser: fenced LaTeX, JSON, auto-repair, regex fallback."""
    cleaned = text.strip()

    # Attempt 1: Fenced LaTeX block or UPDATED_LATEX format
    fenced_code = extract_chunk_latex(cleaned)
    if fenced_code and not cleaned.startswith("{"):
        return {
            "original_chunk": "",
            "proposed_chunk": fenced_code,
            "explanation": "Updated LaTeX document code block."
        }

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)

    # Attempt 2: Direct JSON parse
    try:
        return json.loads(cleaned, strict=False)
    except Exception:
        pass

    # Attempt 3: Auto-repair truncated JSON
    try:
        repaired = auto_repair_truncated_json(cleaned)
        return json.loads(repaired, strict=False)
    except Exception:
        pass

    # Attempt 4: Escape unescaped LaTeX backslashes
    try:
        fixed_slashes = re.sub(r'(?<!\\)\\([a-zA-Z%&$#_{}\[\]])', r'\\\\\1', cleaned)
        repaired_slashes = auto_repair_truncated_json(fixed_slashes)
        return json.loads(repaired_slashes, strict=False)
    except Exception:
        pass

    # Attempt 5: Extract JSON object via regex
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

    # Attempt 6: Regex extraction of proposed_chunk
    try:
        return extract_fallback_chunks(cleaned)
    except Exception:
        pass

    # Attempt 7: Fallback fenced code or raw LaTeX extraction
    if fenced_code:
        return {
            "original_chunk": "",
            "proposed_chunk": fenced_code,
            "explanation": "Extracted LaTeX code from response."
        }

    raise ValueError(f"LLM output could not be parsed as valid JSON: {text}")


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
    Full RAG Agent Pipeline with 3 Interaction Modes:
    1. GENERAL_CHAT: Vector search = False, Edits = False
    2. INSPECT_DOCUMENT: Vector search = True, Edits = False
    3. EDIT_DOCUMENT: Vector search = True, Edits = True
    """
    try:
        mode, is_search_needed = categorize_user_intent(req.user_prompt)
        print(f"\n🚀 [AGENT CHAT REQUEST RECEIVED]\n  ► Prompt: '{req.user_prompt}'\n  ► Project ID: {req.project_id}\n  ► Mode: {mode} (Vector Search = {is_search_needed})")

        retrieved_chunks = []
        if is_search_needed:
            try:
                print("  ► Generating Nemotron query embedding (2048 dims)...")
                embeddings_model = get_nvidia_embeddings()
                prompt_embedding = embeddings_model.embed_query(req.user_prompt)

                qdrant = get_qdrant_client()
                ensure_qdrant_collection(qdrant)

                print("  ► Executing multi-stage vector search against Qdrant DB...")
                retrieved_chunks = retriever.retrieve(
                    qdrant_client=qdrant,
                    collection_name=COLLECTION_NAME,
                    query_embedding=prompt_embedding,
                    project_id=req.project_id,
                    file_path=req.file_path,
                )
                print(f"  ► Qdrant returned {len(retrieved_chunks)} text chunk(s)")
            except Exception as qdrant_err:
                print(f"  ⚠️  Vector retrieval error: {qdrant_err}. Continuing with 0 chunks.")
        else:
            print(f"  💬 Mode {mode}: Skipping Qdrant vector search.")

        # Fast-path for simple greetings
        text_clean = req.user_prompt.lower().strip()
        greetings_set = {"hi", "hello", "hey", "good morning", "good evening", "greetings"}
        if text_clean in greetings_set or (len(text_clean.split()) <= 2 and any(g in text_clean for g in greetings_set)):
            print("  👋 Simple greeting detected. Returning instant conversational response.")
            return {
                "plan": "",
                "edits": [],
                "original_chunk": "",
                "proposed_chunk": "",
                "explanation": "Hello! How can I help you with your LaTeX document or Beamer slides today?",
                "retrieved_chunks_count": 0,
            }

        # Step 3: Build structured context from top retrieved embedding chunks
        context_str = context_builder.build_context(retrieved_chunks)

        # Step 4: Load memory
        conv_ctx = conversation_memory.get_conversation_context(req.project_id)
        proj_ctx = project_memory.get_project_context(req.project_id)

        # Lazy project memory scan if not yet scanned
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
            except Exception as scan_err:
                logger.debug(f"Project memory scan note: {scan_err}")

        # Step 5: Build prompt (Plain text user prompt + Plain text LaTeX context)
        print("  ► Assembling structured system & user prompt messages...")
        messages = prompt_builder.build_prompt(
            user_request=req.user_prompt,
            retrieved_context=context_str,
            conversation_context=conv_ctx,
            project_context=proj_ctx,
        )

        # Step 6: Invoke LLM (Only bind tools for EDIT_DOCUMENT mode to prevent Groq API 'json' tool errors)
        print(f"  ► Invoking LLM Engine (Selected Model: '{req.groq_model or 'openai/gpt-oss-120b'}'), Mode={mode}...")
        try:
            llm = get_chat_llm(user_groq_key=req.groq_api_key, user_groq_model=req.groq_model)
            if mode == "EDIT_DOCUMENT":
                try:
                    llm_with_tools = llm.bind_tools(AI_TOOLS)
                    llm_response = llm_with_tools.invoke(messages)
                except Exception as bind_err:
                    print(f"  ⚠️  Tool binding note: {bind_err}. Invoking base LLM...")
                    llm_response = llm.invoke(messages)
            else:
                # Base LLM invocation for chat / inspection (no tool binding)
                llm_response = llm.invoke(messages)
        except Exception as llm_err:
            print(f"  ⚠️  Primary LLM failed / timed out: {llm_err}.")
            server_groq = os.getenv("GROQ_API_KEY")
            has_groq_option = bool((req.groq_api_key and req.groq_api_key.strip()) or (server_groq and server_groq.strip()))
            
            if not has_groq_option:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="LLM outage / timeout detected on default model. Please configure your own API key using Groq provider in the AI settings panel (🔑 Key icon)."
                )

            print("  Retrying with fallback Groq engine...")
            try:
                llm = get_chat_llm(
                    model_override="openai/gpt-oss-120b",
                    user_groq_key=req.groq_api_key,
                    use_server_groq_first=True
                )
                if mode == "EDIT_DOCUMENT":
                    try:
                        llm_with_tools = llm.bind_tools(AI_TOOLS)
                        llm_response = llm_with_tools.invoke(messages)
                    except Exception:
                        llm_response = llm.invoke(messages)
                else:
                    llm_response = llm.invoke(messages)
            except Exception as fallback_err:
                print(f"  ❌ Fallback LLM failed: {fallback_err}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="LLM outage / timeout detected on default model. Please configure your own API key using Groq provider in the AI settings panel (🔑 Key icon)."
                )

        # Step 7: Process Tool Calls or Raw JSON Response
        tool_calls = getattr(llm_response, "tool_calls", [])
        if tool_calls:
            print(f"  ✨ LLM executed {len(tool_calls)} native Tool Call(s): {[tc.get('name') for tc in tool_calls]}")
            parsed_result = process_tool_calls(tool_calls, retrieved_chunks)
        else:
            print("  📝 LLM returned raw JSON response string. Parsing response...")
            response_text = llm_response.content if hasattr(llm_response, "content") else str(llm_response)
            parsed_result = clean_json_response(response_text)

        edits = parsed_result.get("edits", [])
        if not isinstance(edits, list):
            edits = []

        # If edits array is empty but single original_chunk/proposed_chunk present, normalize into edits list
        if not edits:
            orig = parsed_result.get("original_chunk", "")
            prop = parsed_result.get("proposed_chunk", "")
            exp = parsed_result.get("explanation", "")
            if orig or prop:
                edits = [{
                    "original_chunk": orig,
                    "proposed_chunk": prop,
                    "explanation": exp
                }]

        # Step 7b: Self-verification check
        action_keywords = ["add", "change", "replace", "delete", "remove", "generate", "create", "make", "insert", "update", "slide", "ppt"]
        user_prompt_lower = req.user_prompt.lower()
        if not edits and any(kw in user_prompt_lower for kw in action_keywords):
            logger.info("Self-verification: User requested action but no edits returned. Running self-correction turn...")
            try:
                verify_messages = messages + [
                    HumanMessage(content=f"Self-Verification Check: The user prompt was '{req.user_prompt}'. Your output produced 0 edits. Please re-check the 8 retrieved chunks and provide the required edit(s) in JSON schema matching {{\"plan\": \"...\", \"edits\": [...]}}.")
                ]
                verify_response = llm.invoke(verify_messages)
                verify_text = verify_response.content if hasattr(verify_response, "content") else str(verify_response)
                repaired_result = clean_json_response(verify_text)
                repaired_edits = repaired_result.get("edits", [])
                if repaired_edits and isinstance(repaired_edits, list):
                    edits = repaired_edits
                    parsed_result = repaired_result
                elif repaired_result.get("proposed_chunk") or repaired_result.get("original_chunk"):
                    edits = [{
                        "original_chunk": repaired_result.get("original_chunk", ""),
                        "proposed_chunk": repaired_result.get("proposed_chunk", ""),
                        "explanation": repaired_result.get("explanation", "")
                    }]
                    parsed_result = repaired_result
            except Exception as verify_err:
                logger.warning(f"Self-verification retry note: {verify_err}")

        # If mode is GENERAL_CHAT or INSPECT_DOCUMENT, enforce zero edits
        if mode != "EDIT_DOCUMENT":
            print(f"  ℹ️  Mode '{mode}': Clearing edits array to prevent unwanted diff popups.")
            edits = []
            first_orig = ""
            first_prop = ""
        else:
            first_orig = edits[0].get("original_chunk", "") if edits else parsed_result.get("original_chunk", "")
            first_prop = edits[0].get("proposed_chunk", "") if edits else parsed_result.get("proposed_chunk", "")

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

        # Step 8: Store in conversation memory
        chunk_summaries = [c.get("summary", "") for c in retrieved_chunks if c.get("summary")]
        conversation_memory.add_turn(
            project_id=req.project_id,
            user_prompt=req.user_prompt,
            assistant_response=parsed_result,
            file_path=req.file_path,
            chunk_summaries=chunk_summaries,
        )

        return {
            "plan": clean_plan,
            "edits": clean_edits,
            "original_chunk": first_orig,
            "proposed_chunk": first_prop,
            "explanation": overall_exp,
            "retrieved_chunks_count": len(retrieved_chunks),
        }

    except Exception as e:
        logger.error(f"Error in AI agent endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI Agent execution failed: {str(e)}"
        )
