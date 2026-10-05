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


@dataclass
class ToolCallRecord:
    name: str
    args: Dict[str, Any]
    result_summary: str
    latency_ms: float
    success: bool = True
    node_id: Optional[str] = None


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

    def record_tool_call(
        self,
        name: str,
        args: Dict[str, Any],
        result_summary: str,
        latency_ms: float,
        success: bool = True,
        node_id: Optional[str] = None,
    ):
        """Records an individual tool call and aggregates tool-level breakdown."""
        record = ToolCallRecord(
            name=name,
            args=args,
            result_summary=result_summary,
            latency_ms=latency_ms,
            success=success,
            node_id=node_id,
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
        """Emits an AgentTrace to stdout and project log file."""
        trace_dict = asdict(trace)
        json_line = json.dumps({"trace_type": "agent", **trace_dict})

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
