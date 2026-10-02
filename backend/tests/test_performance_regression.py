"""
tests/test_performance_regression.py — Performance & Regression Benchmark Suite
================================================================================
Profiles and tests the OpenCode agent loop for:
1. Step count and step budget adherence
2. verify_compile invocation frequency and compile latency
3. Context compaction efficiency and token size growth
4. Per-tool breakdown and AST validation latency
5. 100% chunk coverage across multi-chapter documents
"""

import json
import logging
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch
import pytest

from scope_classifier import classify_scope, ScopeType
from document_index import DocumentIndex
from edit_validator import validate_coverage
from opencode.shadow_workspace import ShadowWorkspace
from opencode.agent_loop import stream_opencode_agent, run_opencode_agent, determine_adaptive_step_budget
from trace import AgentTrace

logger = logging.getLogger("performance_benchmark")

# 5-Chapter Realistic Academic Document (~500 lines scale)
BENCHMARK_MULTI_CHAPTER_DOC = r"""\documentclass[11pt,a4paper,oneside]{report}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{hyperref}

\title{Next-Generation Agentic Systems: Distributed Reasoning in Autonomous LaTeX IDEs}
\author{OverBranch Systems Research Group}
\date{\today}

\begin{document}
\maketitle

\begin{abstract}
This research report investigates asynchronous ReAct agent execution models in collaborative LaTeX environments.
\end{abstract}

\chapter{Introduction}
\label{ch:intro}
Distributed agent architectures present complex state management and latency challenges in real-time document editing.
Traditional monolithic LLM pipelines suffer from linear step scaling, quadratic token growth, and blocking validation passes.

\chapter{Related Work and Theoretical Foundations}
\label{ch:related}
Prior research in program synthesis and automated document refactoring has relied on sequential tool execution loops.
Recent work in OpenCode-style environments demonstrates that shadow sandboxing enables non-destructive document mutations.

\chapter{System Architecture and Shadow Buffer Mechanics}
\label{ch:arch}
The OverBranch architecture decouples user-facing disk persistence from in-memory shadow AST buffers.
Every edit operates on structural chunk boundaries delineated by AST byte offsets.

\chapter{Experimental Evaluation and Latency Benchmarks}
\label{ch:eval}
We evaluate step efficiency, compilation frequency, and token footprint across varied document scales.
Preliminary experiments reveal significant speedups when multi-chunk mutations are dispatched in batched agent turns.

\chapter{Conclusion and Future Research Directions}
\label{ch:concl}
In this report, we have presented an optimized, concurrency-safe agent loop for agentic LaTeX IDEs.
Future investigations will explore speculative parallel compilation and automated theorem verification.

\begin{thebibliography}{99}
\bibitem{vaswani17} A. Vaswani et al., "Attention is all you need," NeurIPS 2017.
\bibitem{knuth84} D. Knuth, "The TeXbook," Addison-Wesley, 1984.
\end{thebibliography}

\end{document}
"""


def simulate_sequential_agent_turn(messages: List[Dict[str, Any]], step: int) -> Dict[str, Any]:
    """
    Simulates the unoptimized/prior sequential agent behavior where the agent
    processes one chunk per LLM round-trip:
    Step 1: Read Ch 1
    Step 2: Rewrite Ch 1
    Step 3: verify_compile
    Step 4: Read Ch 2
    Step 5: Rewrite Ch 2
    Step 6: verify_compile
    Step 7: Read Ch 3
    Step 8: Rewrite Ch 3
    Step 9: verify_compile
    Step 10: Read Ch 4
    Step 11: Rewrite Ch 4
    Step 12: verify_compile
    Step 13: Read Ch 5
    Step 14: Rewrite Ch 5
    Step 15: verify_compile
    Step 16: done
    """
    chunk_map = {
        1: ("read_file_range", {"start_line": 15, "end_line": 25}),
        2: ("rewrite_chunk", {"chunk_id": "chapter_1", "new_content": "\\chapter{Introduction}\nExpanded Introduction with 3 detailed subsections, background context, and motivation."}),
        3: ("verify_compile", {}),
        4: ("read_file_range", {"start_line": 26, "end_line": 35}),
        5: ("rewrite_chunk", {"chunk_id": "chapter_2", "new_content": "\\chapter{Related Work and Theoretical Foundations}\nExpanded Literature Review covering 15 foundational papers and comparative taxonomy."}),
        6: ("verify_compile", {}),
        7: ("read_file_range", {"start_line": 36, "end_line": 45}),
        8: ("rewrite_chunk", {"chunk_id": "chapter_3", "new_content": "\\chapter{System Architecture and Shadow Buffer Mechanics}\nExpanded Architecture with detailed AST differential offset equations and memory diagrams."}),
        9: ("verify_compile", {}),
        10: ("read_file_range", {"start_line": 46, "end_line": 55}),
        11: ("rewrite_chunk", {"chunk_id": "chapter_4", "new_content": "\\chapter{Experimental Evaluation and Latency Benchmarks}\nExpanded Evaluation with benchmark tables comparing before vs after step counts and latency."}),
        12: ("verify_compile", {}),
        13: ("read_file_range", {"start_line": 56, "end_line": 65}),
        14: ("rewrite_chunk", {"chunk_id": "chapter_5", "new_content": "\\chapter{Conclusion and Future Research Directions}\nExpanded Conclusion with summary of theoretical contributions and roadmap."}),
        15: ("verify_compile", {}),
    }

    if step in chunk_map:
        tool_name, tool_args = chunk_map[step]
        return {
            "content": json.dumps({
                "thought": f"Sequential step {step}: executing {tool_name}",
                "tool_call": {
                    "name": tool_name,
                    "arguments": tool_args,
                }
            }),
            "finish_reason": "stop",
        }
    else:
        return {
            "content": json.dumps({
                "thought": "All 5 chapters expanded sequentially.",
                "done": True,
                "explanation": "Expanded all chapters sequentially.",
            }),
            "finish_reason": "stop",
        }


def simulate_batched_agent_turn(messages: List[Dict[str, Any]], step: int) -> Dict[str, Any]:
    """
    Simulates the optimized batched agent behavior:
    Step 1: Emits batched tool_calls rewriting all 5 chapters in a single turn.
    Step 2: verify_compile once + done=true.
    """
    if step == 1:
        return {
            "content": json.dumps({
                "thought": "Expanding all 5 chapters in a single high-efficiency batched turn.",
                "tool_calls": [
                    {"name": "rewrite_chunk", "arguments": {"chunk_id": "chapter_1", "new_content": "\\chapter{Introduction}\nExpanded Introduction with detailed subsections and motivation."}},
                    {"name": "rewrite_chunk", "arguments": {"chunk_id": "chapter_2", "new_content": "\\chapter{Related Work and Theoretical Foundations}\nExpanded Literature Review covering taxonomy."}},
                    {"name": "rewrite_chunk", "arguments": {"chunk_id": "chapter_3", "new_content": "\\chapter{System Architecture and Shadow Buffer Mechanics}\nExpanded Architecture with detailed AST differential offset equations."}},
                    {"name": "rewrite_chunk", "arguments": {"chunk_id": "chapter_4", "new_content": "\\chapter{Experimental Evaluation and Latency Benchmarks}\nExpanded Evaluation with comprehensive benchmark metrics."}},
                    {"name": "rewrite_chunk", "arguments": {"chunk_id": "chapter_5", "new_content": "\\chapter{Conclusion and Future Research Directions}\nExpanded Conclusion with theoretical summary."}},
                ]
            }),
            "finish_reason": "stop",
        }
    elif step == 2:
        return {
            "content": json.dumps({
                "thought": "Verifying LaTeX compilation once across the full document batch.",
                "tool_call": {"name": "verify_compile", "arguments": {}},
            }),
            "finish_reason": "stop",
        }
    else:
        return {
            "content": json.dumps({
                "thought": "All chapters expanded and verified cleanly.",
                "done": True,
                "explanation": "Expanded all 5 chapters with 100% coverage in batched mode.",
            }),
            "finish_reason": "stop",
        }


def run_benchmark_simulation(simulation_fn, name: str) -> Dict[str, Any]:
    """Runs a complete agent run against the benchmark document and captures telemetry."""
    call_step = 0

    def mock_chat(*args, **kwargs):
        nonlocal call_step
        call_step += 1
        messages = kwargs.get("messages", [])
        return simulation_fn(messages, call_step)

    with patch("opencode.agent_loop.provider_router.chat", side_effect=mock_chat):
        t0 = time.time()
        result = run_opencode_agent(
            user_instruction="Please add more content across all chapters with detailed theoretical explanations, equations, and benchmark metrics.",
            project_id=f"bench-{name.lower()}",
            current_code=BENCHMARK_MULTI_CHAPTER_DOC,
            mode="edit",
            max_steps=20,
        )
        total_time_ms = (time.time() - t0) * 1000

    trace = result.get("trace", {})
    return {
        "name": name,
        "total_wall_clock_ms": total_time_ms,
        "steps_used": result.get("steps_taken", 0),
        "step_budget_allocated": trace.get("step_budget_allocated", 0),
        "tool_breakdown": trace.get("tool_breakdown", {}),
        "compile_invocations": trace.get("compile_invocations", 0),
        "compile_total_latency_ms": trace.get("compile_total_latency_ms", 0),
        "edit_validator_invocations": trace.get("edit_validator_invocations", 0),
        "edit_validator_latency_ms": trace.get("edit_validator_latency_ms", 0),
        "coverage_pct": trace.get("coverage_pct", 0),
        "edit_count": result.get("edit_count", 0),
        "trace": trace,
    }


def test_baseline_vs_batched_benchmark():
    """Runs and asserts baseline vs optimized benchmark comparison."""
    baseline = run_benchmark_simulation(simulate_sequential_agent_turn, "Baseline (Sequential 1-by-1)")
    optimized = run_benchmark_simulation(simulate_batched_agent_turn, "Optimized (Batched)")

    print("\n" + "=" * 80)
    print("STEP 0 BENCHMARK METRICS COMPARISON TABLE (5-Chapter Document, Broad Expansion)")
    print("=" * 80)
    print(f"{'Metric':<35} | {'Baseline (Sequential)':<20} | {'Optimized (Batched)':<20}")
    print("-" * 80)
    print(f"{'Total Agent Steps':<35} | {baseline['steps_used']:<20} | {optimized['steps_used']:<20}")
    print(f"{'Step Budget Allocated':<35} | {baseline['step_budget_allocated']:<20} | {optimized['step_budget_allocated']:<20}")
    print(f"{'verify_compile Calls':<35} | {baseline['compile_invocations']:<20} | {optimized['compile_invocations']:<20}")
    print(f"{'Coverage %':<35} | {baseline['coverage_pct']}%{'':<16} | {optimized['coverage_pct']}%{'':<16}")
    print(f"{'Total Edits Applied':<35} | {baseline['edit_count']:<20} | {optimized['edit_count']:<20}")
    print(f"{'Edit Validator Invocations':<35} | {baseline['edit_validator_invocations']:<20} | {optimized['edit_validator_invocations']:<20}")
    print("-" * 80)
    print("Tool Calls Breakdown:")
    all_tools = set(baseline["tool_breakdown"].keys()) | set(optimized["tool_breakdown"].keys())
    for t in sorted(all_tools):
        b_count = baseline["tool_breakdown"].get(t, {}).get("count", 0)
        o_count = optimized["tool_breakdown"].get(t, {}).get("count", 0)
        print(f"  - {t:<31} | count: {b_count:<13} | count: {o_count:<13}")
    print("=" * 80)

    # Assertions for performance budgets
    assert optimized["steps_used"] <= 3, f"Optimized run took {optimized['steps_used']} steps, expected <= 3"
    assert optimized["compile_invocations"] <= 1, f"Optimized run had {optimized['compile_invocations']} compile calls, expected <= 1"
    assert optimized["coverage_pct"] == 100.0, f"Coverage was {optimized['coverage_pct']}%, expected 100.0%"
    assert baseline["coverage_pct"] == 100.0


def test_performance_budget_upper_bounds():
    """CI Regression Test: Asserts upper bounds on steps and compile calls for broad expansion."""
    bench = run_benchmark_simulation(simulate_batched_agent_turn, "CI Budget Check")
    assert bench["steps_used"] <= 4, "Performance Regression: Steps exceeded budget of 4"
    assert bench["compile_invocations"] <= 1, "Performance Regression: verify_compile exceeded budget of 1"
    assert bench["coverage_pct"] == 100.0, "Correctness Regression: Coverage dropped below 100%"


if __name__ == "__main__":
    test_baseline_vs_batched_benchmark()
