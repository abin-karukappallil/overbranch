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
from typing import Any, Dict, Optional

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
    api_keys: Optional[Dict[str, str]] = Field(None, description="User-provided API keys")
    request_id: Optional[str] = Field(None, description="Unique client request ID for cancellation")
    max_steps: Optional[int] = Field(None, description="Max agent reasoning steps (default: 12)")


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
                        api_keys=req.api_keys,
                        max_steps=max_steps,
                        cancel_token=token,
                        assets_dir=assets_dir,
                    ):
                        if token.is_cancelled():
                            break
                        loop.call_soon_threadsafe(queue.put_nowait, event)
                except Exception as exc:
                    loop.call_soon_threadsafe(queue.put_nowait, exc)
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, sentinel)

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
            yield sse_event("error", {"message": f"OverBranch agent failed: {str(e)}"})

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


def _summarize_tool_result(tool_name: str, result: Dict[str, Any]) -> str:
    """Generates a concise summary of a tool result for the progress feed."""
    if result.get("error"):
        return f"`{tool_name}` error: {result['error'][:120]}"

    if tool_name == "read_file_range":
        lines_read = result.get("lines_read", "?")
        total = result.get("total_lines", "?")
        return f" Read lines {lines_read} (file has {total} lines)"

    elif tool_name == "grep_search":
        count = result.get("match_count", 0)
        query = result.get("query", "")
        return f" Found {count} match{'es' if count != 1 else ''} for \"{query[:50]}\""

    elif tool_name == "str_replace":
        if result.get("success"):
            lines = result.get("lines_affected", [])
            return f"Replaced text at lines {lines[0]}–{lines[1]}" if lines else "✅ Text replaced"
        else:
            return f"Replace failed: {result.get('error', 'unknown')[:100]}"

    elif tool_name == "rewrite_chunk":
        if result.get("success"):
            chunk_id = result.get("chunk_id", "chunk")
            lines = result.get("lines_affected", [])
            return f"Rewrote chunk `{chunk_id}` (lines {lines[0]}–{lines[1]})" if lines else f"Rewrote chunk `{chunk_id}`"
        else:
            return f"Rewrite chunk failed: {result.get('error', 'unknown')[:100]}"

    elif tool_name == "list_assets":
        count = result.get("count", 0)
        return f" Found {count} asset file{'s' if count != 1 else ''}"

    elif tool_name == "verify_compile":
        if result.get("infra_skip"):
            return "Compilation skipped (compiler unavailable)"
        elif result.get("success"):
            ms = result.get("compile_time_ms", 0)
            return f"Compilation passed ({ms}ms)"
        else:
            err_count = len(result.get("errors", []))
            return f"Compilation failed with {err_count} error{'s' if err_count != 1 else ''}"

    return f"✓ `{tool_name}` completed"
