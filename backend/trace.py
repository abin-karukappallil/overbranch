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


@dataclass
class ConversionTrace:
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    num_pages: int = 0
    doc_type: str = ""
    embedded_images_count: int = 0
    fidelity_score: float = 1.0
    defects_count: int = 0
    defects: List[Dict[str, Any]] = field(default_factory=list)
    compile_success: bool = True
    total_latency_ms: float = 0.0
    model_used: str = ""


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
