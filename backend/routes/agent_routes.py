"""
routes/agent_routes.py — OpenCode Agentic Pipeline SSE Endpoint
================================================================
New FastAPI router for the OpenCode pipeline. Provides:
  POST /api/agent/opencode — SSE streaming endpoint

Coexists alongside the legacy /api/agent/chat endpoint.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from cancellation import cancellation_manager, CancellationToken, LLMOperationCancelled
from auth import get_current_user, get_current_user_or_guest, verify_project_ownership_or_member
from models import User
from rate_limiter import RateLimiter
from project_storage import get_supabase_client

logger = logging.getLogger("routes.agent_opencode")

router = APIRouter()


# ============================================================================
# Request / Response Models
# ============================================================================

class OpenCodeRequest(BaseModel):
    project_id: str = Field(..., description="Project ID or UUID")
    file_path: str = Field("main.tex", description="Path of the TeX file")
    user_prompt: str = Field(..., description="User's editing request or question")
    current_code: Optional[str] = Field(None, description="Current editor LaTeX content")
    model: Optional[str] = Field(None, description="LLM model name")
    mode: Optional[str] = Field("edit", description="Chat mode: 'edit' (default) or 'ask'")
    attached_file: Optional[Dict[str, Any]] = Field(None, description="Attached PDF/text document reference")
    attached_files: Optional[List[Dict[str, Any]]] = Field(None, description="List of attached documents")
    api_keys: Optional[Dict[str, str]] = Field(None, description="User-provided API keys")
    request_id: Optional[str] = Field(None, description="Unique client request ID for cancellation")
    session_id: Optional[str] = Field(None, description="Client session ID for cross-turn context persistence")
    max_steps: Optional[int] = Field(None, description="Max agent reasoning steps (default: 12)")


OpenCodeRequest.model_rebuild()


class AgentStopRequest(BaseModel):
    project_id: Optional[str] = Field(None, description="Project ID")
    request_id: Optional[str] = Field(None, description="Request ID to stop")


@router.post(
    "/api/agent/stop",
    dependencies=[Depends(RateLimiter(times=30, seconds=60, key_prefix="rl_agent_stop"))],
)
async def agent_stop(
    req: AgentStopRequest,
    request: Request,
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    """
    Immediately halts active OpenCode reasoning, LLM API calls,
    and background operations for the specified request_id and/or project_id.
    Requires authenticated Better Auth session or verified guest identity.
    """
    user_id = auth_info["user_id"]
    is_guest = bool(auth_info.get("is_guest"))
    if req.project_id:
        try:
            sb = get_supabase_client()
            verify_project_ownership_or_member(sb, req.project_id, user_id, is_guest=is_guest)
        except Exception as auth_err:
            logger.warning(f"Stop request project authorization check: {auth_err}")
            if req.project_id not in ("proj-default", "default", "scratchpad") and not req.project_id.startswith("proj-"):
                raise

    cancelled = cancellation_manager.cancel(
        request_id=req.request_id,
        project_id=req.project_id,
        reason=f"Stopped by user {user_id} from editor UI",
    )
    logger.info(
        f"Agent stop requested by user {user_id}: "
        f"request_id={req.request_id}, project_id={req.project_id}, stopped={cancelled}"
    )
    return {"success": True, "stopped": cancelled}


class ValidateLatexRequest(BaseModel):
    latex_code: str = Field(..., description="Full LaTeX document to validate")
    project_id: Optional[str] = Field(None, description="Project ID, for access control")
    file_path: str = Field("main.tex", description="Path of the TeX file being validated")
    heal: bool = Field(
        False,
        description=(
            "Also return an auto-healed version. Off by default: healing hoists "
            "\\usepackage, injects \\usetikzlibrary and theme colours and rewrites "
            "\\[len] spacing, so it must never be applied without showing the user "
            "what changed (see fixes_applied)."
        ),
    )


MAX_VALIDATE_BYTES = 2_000_000


@router.post(
    "/api/agent/validate-latex",
    dependencies=[Depends(RateLimiter(times=60, seconds=60, key_prefix="rl_latex_validate"))],
)
async def validate_latex_endpoint(
    req: ValidateLatexRequest,
    request: Request,
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    """
    Heals and/or validates a LaTeX document without writing anything.

    The editor calls this after applying a *subset* of the agent's proposed edits:
    the full-document path is already backend-validated, but a partial selection
    can leave an orphaned \\end{...} that nothing else would catch.
    """
    user_id = auth_info["user_id"]
    is_guest = bool(auth_info.get("is_guest"))

    if req.project_id:
        try:
            sb = get_supabase_client()
            verify_project_ownership_or_member(sb, req.project_id, user_id, is_guest=is_guest)
        except Exception as auth_err:
            logger.warning(f"validate-latex project authorization check: {auth_err}")
            if req.project_id not in ("proj-default", "default", "scratchpad") and not req.project_id.startswith("proj-"):
                raise

    if len(req.latex_code.encode("utf-8")) > MAX_VALIDATE_BYTES:
        return JSONResponse(
            status_code=413,
            content={
                "detail": f"Document exceeds the {MAX_VALIDATE_BYTES // 1_000_000} MB validation limit."
            },
        )

    from latex_error_fixer import auto_heal_latex_code
    from edit_validator import validate_latex_pre_commit

    code = req.latex_code
    fixes: List[str] = []
    healed: Optional[str] = None

    if req.heal:
        try:
            healed, fixes = auto_heal_latex_code(code)
        except Exception as e:
            logger.warning(f"validate-latex heal failed, validating as-is: {e}")
            healed = code

    target = healed if healed is not None else code
    valid, errors = validate_latex_pre_commit(target)

    return {
        "valid": valid,
        "errors": errors,
        "fixes_applied": fixes,
        "healed_code": healed,
        "changed": healed is not None and healed != code,
        "file_path": req.file_path,
    }


class ResolveEditsRequest(BaseModel):
    current_code: str
    items: List[Dict[str, Any]]
    original_code: Optional[str] = None
    project_id: Optional[str] = None
    file_path: Optional[str] = None


@router.post(
    "/api/agent/resolve-edits",
    dependencies=[Depends(RateLimiter(times=60, seconds=60, key_prefix="rl_resolve_edits"))],
)
async def resolve_edits_endpoint(
    req: ResolveEditsRequest,
    request: Request,
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    """
    Places accepted agent edits that the editor could not locate by exact text
    (the document changed under them), using the agent's target locator. Writes
    nothing; returns the new code or, if any edit cannot be placed confidently,
    the unchanged code and what was tried for each edit.
    """
    user_id = auth_info["user_id"]
    is_guest = bool(auth_info.get("is_guest"))
    if req.project_id:
        try:
            sb = get_supabase_client()
            verify_project_ownership_or_member(sb, req.project_id, user_id, is_guest=is_guest)
        except Exception as auth_err:
            logger.warning(f"resolve-edits project authorization check: {auth_err}")
            if req.project_id not in ("proj-default", "default", "scratchpad") and not req.project_id.startswith("proj-"):
                raise

    size = len(req.current_code.encode("utf-8")) + len((req.original_code or "").encode("utf-8"))
    if size > 2 * MAX_VALIDATE_BYTES or len(req.items) > 200:
        return JSONResponse(status_code=413, content={"detail": "Document or edit list too large."})

    from opencode.apply_edits import resolve_and_apply

    result = await asyncio.to_thread(resolve_and_apply, req.current_code, req.items, req.original_code)
    logger.info(
        "resolve-edits project=%s file=%s items=%d applied=%d failed=%d methods=%s",
        req.project_id, req.file_path, len(req.items), len(result["applied"]), len(result["failed"]),
        sorted({a["method"] for a in result["applied"]}),
    )
    result["file_path"] = req.file_path
    return result


# ============================================================================
# SSE Endpoint
# ============================================================================

@router.post(
    "/api/agent/opencode",
    dependencies=[Depends(RateLimiter(times=20, seconds=60, key_prefix="rl_agent_opencode"))],
)
async def agent_opencode(
    request: Request,
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    """
    OpenCode Agentic Pipeline with SSE streaming.
    Requires an authenticated Better Auth user session or verified guest identity.

    Sends real-time reasoning events (thought, tool_call, tool_result,
    compile_error) and a final_diff payload for the InlineDiffEditor.
    """
    # Parse request body manually to bypass body size limits
    try:
        body = await request.body()
        if len(body) > 10 * 1024 * 1024:  # 10MB hard cap
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large. Maximum size is 10MB."},
            )
        raw_data = json.loads(body)
        req = OpenCodeRequest(**raw_data)
    except json.JSONDecodeError as e:
        return JSONResponse(status_code=400, content={"detail": f"Invalid JSON: {e}"})
    except Exception as e:
        return JSONResponse(status_code=422, content={"detail": f"Validation error: {e}"})

    # Verify project access for caller
    user_id = auth_info["user_id"]
    is_guest = bool(auth_info.get("is_guest"))
    if req.project_id:
        try:
            sb = get_supabase_client()
            verify_project_ownership_or_member(sb, req.project_id, user_id, is_guest=is_guest)
        except Exception as auth_err:
            logger.warning(f"Project access verification warning for user {user_id}: {auth_err}")
            if req.project_id not in ("proj-default", "default", "scratchpad") and not req.project_id.startswith("proj-"):
                raise

    # Create cancellation token
    request_id = req.request_id or f"OverBranch-{uuid.uuid4().hex[:12]}"
    token = cancellation_manager.create_token(request_id=request_id, project_id=req.project_id)

    # Disconnect monitor task
    async def disconnect_monitor():
        try:
            while not token.is_cancelled():
                await asyncio.sleep(1.5)
                try:
                    if await request.is_disconnected():
                        logger.info(f"Client disconnected for OverBranch request {request_id}")
                        token.cancel("Client disconnected")
                        break
                except Exception:
                    pass
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Disconnect monitor error: {e}")

    disconnect_task = asyncio.create_task(disconnect_monitor())

    def sse_event(event_type: str, data: dict) -> str:
        """Format a single SSE event."""
        return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def pipeline_generator():
        try:
            from opencode.agent_loop import stream_opencode_agent

            # Resolve assets directory
            assets_dir = _resolve_assets_dir(req.project_id)

            model = req.model or "gemini-3.7-flash"
            max_steps = req.max_steps  # None enables adaptive step budgeting based on prompt scope

            yield sse_event("progress", {
                "step": "init",
                "message": "Starting OverBranch agent pipeline...",
                "icon": "zap",
            })

            # Stream events in real time from worker thread via asyncio.Queue
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue = asyncio.Queue()
            sentinel = object()

            def producer():
                try:
                    for event in stream_opencode_agent(
                        user_instruction=req.user_prompt,
                        project_id=req.project_id,
                        current_code=req.current_code or "",
                        file_path=req.file_path,
                        model=model,
                        mode=req.mode or "edit",
                        attached_file=req.attached_file,
                        attached_files=req.attached_files,
                        api_keys=req.api_keys,
                        max_steps=max_steps,
                        cancel_token=token,
                        assets_dir=assets_dir,
                        session_id=req.session_id or req.project_id,
                        user_context={"user_id": user_id, "is_guest": is_guest},
                    ):
                        if token.is_cancelled():
                            break
                        loop.call_soon_threadsafe(queue.put_nowait, event)
                except Exception as exc:
                    loop.call_soon_threadsafe(queue.put_nowait, exc)
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, sentinel)

            # Lets tools running in the worker thread (convert_attached_pdf) schedule async jobs
            from pdf2latex.runner import bind_loop
            bind_loop(loop)

            producer_task = loop.run_in_executor(None, producer)

            while True:
                item = await queue.get()
                if item is sentinel:
                    break
                if isinstance(item, Exception):
                    raise item

                event = item
                event_type = event.get("type", "status")

                if event_type == "thought":
                    yield sse_event("progress", {
                        "step": "thought",
                        "message": f" {event.get('content', '')}",
                        "icon": "brain",
                    })

                elif event_type == "tool_call":
                    tool_name = event.get("tool", "")
                    yield sse_event("progress", {
                        "step": "tool_call",
                        "message": f"Tool Calling `{tool_name}`...",
                        "icon": "wrench",
                        "tool": tool_name,
                        "args": event.get("args", {}),
                    })

                elif event_type == "tool_result":
                    tool_name = event.get("tool", "")
                    result = event.get("result", {})
                    # Summarize tool result for the progress feed
                    summary = _summarize_tool_result(tool_name, result)
                    yield sse_event("progress", {
                        "step": "tool_result",
                        "message": summary,
                        "icon": "check",
                    })
                    if tool_name == "convert_attached_pdf" and result.get("job_id") and result.get("success"):
                        yield sse_event("pdf_conversion", {
                            "job_id": result["job_id"],
                            "page_count": result.get("page_count"),
                            "filename": result.get("filename"),
                        })

                elif event_type == "coverage_check":
                    yield sse_event("coverage_check", event)
                    passed = event.get("passed", False)
                    msg = event.get("message", "Coverage check executed")
                    yield sse_event("progress", {
                        "step": "coverage_check",
                        "message": msg,
                        "icon": "check" if passed else "alert",
                    })

                elif event_type == "compile_error":
                    yield sse_event("progress", {
                        "step": "compile_error",
                        "message": f" {event.get('message', 'Compilation error')}",
                        "icon": "alert",
                    })
                    yield sse_event("compile_error", event)

                elif event_type == "error":
                    yield sse_event("error", event)

                elif event_type == "phase":
                    phase = event.get("phase", "")
                    yield sse_event("progress", {
                        "step": "phase",
                        "phase": phase,
                        "message": event.get("message", ""),
                        "icon": _PHASE_ICONS.get(phase, "zap"),
                        "details": event.get("details"),
                    })

                elif event_type == "status":
                    yield sse_event("progress", {
                        "step": event.get("step", ""),
                        "message": event.get("message", ""),
                        "icon": "zap",
                    })

                elif event_type == "final_diff":
                    # The key event for the frontend InlineDiffEditor
                    yield sse_event("final_diff", event)

                elif event_type == "result":
                    # Backward-compatible result event
                    yield sse_event("result", event.get("data", event))

            yield sse_event("progress", {
                "step": "done",
                "message": "Complete",
                "icon": "check",
            })

        except LLMOperationCancelled:
            logger.info(f"OverBranch pipeline cleanly stopped: {request_id}")
            yield sse_event("cancelled", {"message": "AI response generation stopped by user."})

        except Exception as e:
            logger.error(f"OverBranch pipeline error: {e}", exc_info=True)
            payload = {"message": "The AI agent hit an unexpected error. The document was not modified."}
            if os.getenv("ENVIRONMENT", os.getenv("NODE_ENV", "")).lower() in ("development", "dev", "local"):
                payload["detail"] = f"{type(e).__name__}: {str(e)[:300]}"
            yield sse_event("error", payload)

        finally:
            if disconnect_task and not disconnect_task.done():
                disconnect_task.cancel()
            cancellation_manager.cleanup(request_id)

    return StreamingResponse(
        pipeline_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================================
# Helpers
# ============================================================================

def _resolve_assets_dir(project_id: str) -> Optional[str]:
    """Resolves the assets directory path for a project."""
    try:
        from project_storage import UPLOADS_BASE_DIR
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", project_id or "default")
        assets_path = UPLOADS_BASE_DIR / safe_id / "assets"
        if assets_path.exists():
            return str(assets_path)
    except Exception:
        pass
    return None


_PHASE_ICONS = {
    "finding_target": "search", "applying": "wrench", "compiling": "zap", "checking_layout": "search",
    "repairing": "wrench", "done": "check", "failed": "alert",
}


def _summarize_tool_result(tool_name: str, result: Dict[str, Any]) -> str:
    """
    A concise, user-facing summary of a tool result for the progress feed.
    Internal failure detail (locator attempts, anchors) stays in the agent's own
    context and the trace; the feed says what happened in plain words.
    """
    from opencode.tools import canonical_tool_name

    tool_name = canonical_tool_name(tool_name)
    edit_tools = {"replace_text", "replace_block", "insert_block", "delete_block", "rewrite_chunk",
                  "insert_into_chunk", "justify_content"}

    if tool_name in edit_tools:
        if result.get("success"):
            lines = result.get("lines_affected") or []
            where = f" at lines {lines[0]}–{lines[1]}" if len(lines) == 2 else ""
            method = result.get("method")
            how = {"normalized": " (matched despite whitespace differences)",
                   "fuzzy": " (located by similarity)",
                   "exact+hint": "", "node": ""}.get(method or "", "")
            if tool_name == "justify_content":
                strategy = (result.get("justify") or {}).get("strategy", "")
                return f"Adjusted layout ({strategy}){where}" if result.get("lines_affected") else \
                    (result.get("message") or "Layout already fits")
            return f"Edit applied{where}{how}"
        if result.get("reason") == "ambiguous":
            return "Target appears more than once — asking the agent to be more specific (document unchanged)"
        if "validation_errors" in result:
            return "Edit would break the LaTeX structure — not applied (document unchanged)"
        return "Couldn't locate the edit target — re-reading that region (document unchanged)"

    if result.get("error"):
        return f"`{tool_name}`: {str(result['error'])[:120]}"

    if tool_name == "read_file_range":
        lines_read = result.get("lines_read", "?")
        total = result.get("total_lines", "?")
        return f" Read lines {lines_read} (file has {total} lines)"

    elif tool_name == "search_document":
        count = result.get("match_count", 0)
        query = result.get("query", "")
        return f" Found {count} match{'es' if count != 1 else ''} for \"{query[:50]}\""

    elif tool_name in ("get_block", "inspect_document"):
        return f" Read {result.get('node_id') or 'document outline'}"

    elif tool_name == "list_assets":
        count = result.get("count", 0)
        return f" Found {count} asset file{'s' if count != 1 else ''}"

    elif tool_name == "compile_latex":
        if result.get("infra_skip"):
            return "Compilation skipped (compiler unavailable)"
        elif result.get("success"):
            ms = result.get("compile_time_ms", 0)
            pre = result.get("preexisting_errors") or 0
            return f"Compilation passed ({ms}ms)" + (f" — {pre} pre-existing issue(s) left untouched" if pre else "")
        else:
            err_count = len(result.get("new_errors") or result.get("errors", []))
            return f"Compilation failed with {err_count} new error{'s' if err_count != 1 else ''}"

    elif tool_name == "detect_overflow":
        if result.get("skipped"):
            return "Layout check skipped (no PDF)"
        n = len(result.get("beyond_text_area", [])) + len(result.get("beyond_page", [])) + \
            len([o for o in result.get("overfull", []) if o.get("severe")])
        return f"Layout check: {n} overflowing line{'s' if n != 1 else ''}" if n else "Layout check: nothing overflows"

    elif tool_name == "convert_attached_pdf":
        pages = result.get("page_count", "?")
        return f"Started {result.get('mode', 'exact')} PDF → LaTeX conversion ({pages} page{'s' if pages != 1 else ''})"

    return f"✓ `{tool_name}` completed"
