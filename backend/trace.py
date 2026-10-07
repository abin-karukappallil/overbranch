"""
trace.py — Structured Observability & Tracing for Agent Runs & PDF Conversion

Provides:
- AgentTrace: structured record of task classification, touched nodes, tool calls,
  shadow compile results, latencies, tokens, and model provenance.
- ConversionTrace: structured record of PDF conversion, fidelity scores, and defects.
- Emits formatted JSON to stdout and persists to rotating log files per project.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("trace")
TRACE_DIR = Path("/tmp/overbranch_traces")


def redact_args(args: Dict[str, Any], limit: int = 80) -> Dict[str, Any]:
    """
    Tool arguments as they may be logged: identifiers and numbers kept, any
    long text (document content, replacement LaTeX) reduced to its length.
    """
    out: Dict[str, Any] = {}
    for k, v in (args or {}).items():
        if isinstance(v, str):
            out[k] = v if len(v) <= limit and "\n" not in v and k not in (
                "new_content", "content", "new_str", "old_str", "text") else f"<{len(v)} chars>"
        elif isinstance(v, (int, float, bool)) or v is None:
            out[k] = v
        else:
            out[k] = f"<{type(v).__name__}>"
    return out


@dataclass
class ToolCallRecord:
    name: str
    args: Dict[str, Any]
    result_summary: str
    latency_ms: float
    success: bool = True
    node_id: Optional[str] = None
    edit_type: Optional[str] = None
    target_resolution_method: Optional[str] = None
    failure_reason: Optional[str] = None


@dataclass
class AgentTrace:
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    task_classification: Dict[str, Any] = field(default_factory=dict)
    nodes_touched: List[str] = field(default_factory=list)
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    validation_result: Dict[str, Any] = field(default_factory=dict)
    shadow_compile_result: Dict[str, Any] = field(default_factory=dict)
    fidelity_score: Optional[float] = None
    total_latency_ms: float = 0.0
    model_used: str = ""
    tokens_in: int = 0
    tokens_out: int = 0

    # Extended performance & latency profiling telemetry
    step_budget_allocated: int = 0
    steps_used: int = 0
    tool_breakdown: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    compile_invocations: int = 0
    compile_latencies_ms: List[float] = field(default_factory=list)
    compile_total_latency_ms: float = 0.0
    step_token_sizes: List[Dict[str, Any]] = field(default_factory=list)
    edit_validator_invocations: int = 0
    edit_validator_latency_ms: float = 0.0
    coverage_pct: float = 100.0
    llm_invocations: int = 0
    llm_latencies_ms: List[float] = field(default_factory=list)
    llm_total_latency_ms: float = 0.0

    # Request / provider provenance (key IDs only — never keys)
    request_id: str = ""
    document_id: str = ""
    provider: str = ""
    key_ids: List[str] = field(default_factory=list)
    llm_attempts: List[Dict[str, Any]] = field(default_factory=list)
    fallback_used: bool = False
    # Edit outcome
    context_info: Dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
    compile_result: str = ""          # passed | failed | skipped | not_run
    failure_reason: str = ""

    @property
    def agent_run_id(self) -> str:
        return self.trace_id

    def record_llm_attempt(self, attempt: Dict[str, Any]) -> None:
        """One provider attempt as reported by ProviderRouter.chat's observer."""
        clean = {k: attempt.get(k) for k in ("provider", "model", "ok", "failure", "status_code", "key_id", "latency_ms")}
        self.llm_attempts.append(clean)
        if attempt.get("ok"):
            self.provider = attempt.get("provider") or self.provider
            if attempt.get("model"):
                self.model_used = attempt["model"]
            if attempt.get("key_id") and attempt["key_id"] not in self.key_ids:
                self.key_ids.append(attempt["key_id"])
        if len(self.llm_attempts) > 1 and any(not a.get("ok") for a in self.llm_attempts):
            self.fallback_used = any(a.get("ok") for a in self.llm_attempts[1:])

    def record_tool_call(
        self,
        name: str,
        args: Dict[str, Any],
        result_summary: str,
        latency_ms: float,
        success: bool = True,
        node_id: Optional[str] = None,
        edit_type: Optional[str] = None,
        target_resolution_method: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ):
        """Records an individual tool call and aggregates tool-level breakdown."""
        record = ToolCallRecord(
            name=name,
            args=redact_args(args),
            result_summary=result_summary[:160],
            latency_ms=latency_ms,
            success=success,
            node_id=node_id,
            edit_type=edit_type,
            target_resolution_method=target_resolution_method,
            failure_reason=failure_reason,
        )
        self.tool_calls.append(record)

        if name not in self.tool_breakdown:
            self.tool_breakdown[name] = {
                "count": 0,
                "success_count": 0,
                "failure_count": 0,
                "total_latency_ms": 0.0,
                "avg_latency_ms": 0.0,
            }

        entry = self.tool_breakdown[name]
        entry["count"] += 1
        if success:
            entry["success_count"] += 1
        else:
            entry["failure_count"] += 1
        entry["total_latency_ms"] += latency_ms
        entry["avg_latency_ms"] = entry["total_latency_ms"] / entry["count"]

    def record_llm_call(
        self,
        latency_ms: float,
        usage: Optional[Dict[str, Any]] = None,
    ):
        """
        Records one provider_router.chat round trip.

        Without this the trace showed total latency and payload size but not the
        LLM-vs-local split, which had to be inferred by subtracting tool and
        validator latencies from the total. Token counts come straight from the
        provider response's `usage`, which was already on hand and discarded.
        """
        self.llm_invocations += 1
        self.llm_latencies_ms.append(round(latency_ms, 2))
        self.llm_total_latency_ms += latency_ms
        if usage:
            self.tokens_in += int(
                usage.get("prompt_tokens") or usage.get("input_tokens") or 0
            )
            self.tokens_out += int(
                usage.get("completion_tokens") or usage.get("output_tokens") or 0
            )

    def record_compile(self, latency_ms: float, success: bool = True):
        """Records a shadow compilation event."""
        self.compile_invocations += 1
        self.compile_latencies_ms.append(latency_ms)
        self.compile_total_latency_ms += latency_ms

    def record_validator(self, latency_ms: float):
        """Records an AST coverage / edit validation pass."""
        self.edit_validator_invocations += 1
        self.edit_validator_latency_ms += latency_ms

    def record_step_tokens(
        self,
        step: int,
        raw_chars: int,
        compacted_chars: int,
        estimated_tokens: int,
    ):
        """Records context token and character growth per step."""
        self.step_token_sizes.append({
            "step": step,
            "raw_chars": raw_chars,
            "compacted_chars": compacted_chars,
            "estimated_tokens": estimated_tokens,
        })

    def summary(self) -> Dict[str, Any]:
        """Returns a concise telemetry summary dict."""
        return {
            "trace_id": self.trace_id,
            "project_id": self.project_id,
            "total_latency_ms": self.total_latency_ms,
            "step_budget_allocated": self.step_budget_allocated,
            "steps_used": self.steps_used,
            "nodes_touched": len(self.nodes_touched),
            "tool_calls_count": len(self.tool_calls),
            "tool_breakdown": self.tool_breakdown,
            "compile_invocations": self.compile_invocations,
            "compile_total_latency_ms": self.compile_total_latency_ms,
            "edit_validator_invocations": self.edit_validator_invocations,
            "edit_validator_latency_ms": self.edit_validator_latency_ms,
            "coverage_pct": self.coverage_pct,
            # LLM round trips dominate wall-clock time; surfacing them directly
            # makes the LLM-vs-local split measurable instead of inferred.
            "llm_invocations": self.llm_invocations,
            "llm_total_latency_ms": round(self.llm_total_latency_ms, 2),
            "llm_share_pct": (
                round(100.0 * self.llm_total_latency_ms / self.total_latency_ms, 1)
                if self.total_latency_ms > 0
                else 0.0
            ),
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "agent_run_id": self.trace_id,
            "request_id": self.request_id,
            "document_id": self.document_id,
            "provider": self.provider,
            "model": self.model_used,
            "key_ids": self.key_ids,
            "fallback_used": self.fallback_used,
            "llm_attempts": len(self.llm_attempts),
            "context": self.context_info,
            "edits": [
                {"tool": t.name, "edit_type": t.edit_type, "method": t.target_resolution_method,
                 "node_id": t.node_id, "success": t.success, "failure_reason": t.failure_reason}
                for t in self.tool_calls if t.edit_type
            ],
            "retry_count": self.retry_count,
            "compile_result": self.compile_result,
            "validation_result": self.validation_result,
            "failure_reason": self.failure_reason,
        }


@dataclass
class ConversionTrace:
    """Telemetry for one PDF → LaTeX conversion job (pdf2latex pipeline)."""
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    project_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    model: str = ""
    num_pages: int = 0
    page_scores: List[Optional[float]] = field(default_factory=list)
    mean_similarity: Optional[float] = None
    fallback_pages: int = 0
    warnings: int = 0
    compile_success: bool = False
    total_latency_ms: float = 0.0
    style_mismatches: int = 0
    overflow_lines: int = 0
    geometry_repairs: int = 0


class TraceManager:
    """Manages trace emission to stdout and disk logging."""

    def __init__(self, trace_dir: Path = TRACE_DIR):
        self.trace_dir = trace_dir
        self._ensure_trace_dir()

    def _ensure_trace_dir(self):
        try:
            self.trace_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.debug(f"Trace dir init note: {e}")

    def emit_agent_trace(self, trace: AgentTrace):
        """Emits an AgentTrace to stdout and project log file (metadata only)."""
        trace_dict = asdict(trace)
        trace_dict["agent_run_id"] = trace.trace_id
        json_line = json.dumps({"trace_type": "agent", **trace_dict}, default=str)

        # Structured log to stdout
        logger.info(f"[TRACE:AGENT] {json_line}")

        # Persist to project log file if project_id exists
        if trace.project_id:
            try:
                proj_file = self.trace_dir / f"project_{trace.project_id}.jsonl"
                with open(proj_file, "a", encoding="utf-8") as f:
                    f.write(json_line + "\n")
            except Exception as e:
                logger.debug(f"Failed to persist agent trace: {e}")

    def emit_conversion_trace(self, trace: ConversionTrace):
        """Emits a ConversionTrace to stdout and log file."""
        trace_dict = asdict(trace)
        json_line = json.dumps({"trace_type": "conversion", **trace_dict})

        logger.info(f"[TRACE:CONVERSION] {json_line}")

        if trace.project_id:
            try:
                proj_file = self.trace_dir / f"project_{trace.project_id}.jsonl"
                with open(proj_file, "a", encoding="utf-8") as f:
                    f.write(json_line + "\n")
            except Exception as e:
                logger.debug(f"Failed to persist conversion trace: {e}")


trace_manager = TraceManager()
