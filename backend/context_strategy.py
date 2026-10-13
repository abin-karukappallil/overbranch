"""
context_strategy.py — Smart Context Strategy Engine
====================================================
Decides how to present document context to the LLM based on:
  - Document size vs. model context window
  - Scope classification (targeted edit, full rewrite, expansion)
  - User request specificity

Strategies:
  TARGETED       — Send only the relevant section + surrounding context
  WHOLE_FILE     — Send entire document (fits comfortably in context window)
  SUMMARY_FIRST  — Send structural summary + targeted sections
  PLAN_EXECUTE   — First create transformation plan, then execute section-by-section

Also provides:
  - Model context window lookup
  - Token budget allocation per step
  - Targeted error context extraction for compile failures
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from document_analyzer import DocumentAnalysis

logger = logging.getLogger("context_strategy")


# ============================================================================
# Model Context Window Registry
# ============================================================================

# Maps model ID patterns to their context window sizes (in tokens).
# Conservative estimates to leave room for output generation.
MODEL_CONTEXT_WINDOWS: Dict[str, int] = {
    # Gemini models
    "gemini-3.7-flash": 900_000,
    "gemini-3.5-flash": 900_000,
    "gemini-3.5-flash-thinking": 900_000,
    "gemini-3.5-flash-thinking-lite": 900_000,
    "gemini-2.5-flash": 900_000,
    "gemini-2.5-pro": 900_000,
    "gemini-2.0-flash": 900_000,
    "gemini-1.5-flash": 900_000,
    "gemini-1.5-pro": 1_800_000,
    # Groq models
    "llama-3.1-8b-instant": 120_000,
    "llama-3.3-70b-versatile": 120_000,
    "llama-3.1-70b-versatile": 120_000,
    "llama-3.1-405b": 120_000,
    "mixtral-8x7b-32768": 30_000,
    "gemma2-9b-it": 7_500,
    # OpenRouter models
    "minimax/minimax-01": 900_000,
    "deepseek/deepseek-chat": 60_000,
    "deepseek/deepseek-coder": 60_000,
    "anthropic/claude-3.5-sonnet": 180_000,
    "openai/gpt-4o": 120_000,
    "openai/gpt-4o-mini": 120_000,
}

# Default context window when model is unknown
DEFAULT_CONTEXT_WINDOW = 120_000

# Reserve this fraction of the context window for output generation
OUTPUT_RESERVE_FRACTION = 0.25

# Threshold: if document tokens < this fraction of available context, use WHOLE_FILE
WHOLE_FILE_THRESHOLD_FRACTION = 0.6


def get_model_context_window(model: str) -> int:
    """
    Returns the context window size (in tokens) for a given model.
    Uses pattern matching to handle model ID variations.
    """
    if not model:
        return DEFAULT_CONTEXT_WINDOW

    clean = model.strip().lower()

    # Direct match
    if clean in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[clean]

    # Pattern matching for model families
    for pattern, window in MODEL_CONTEXT_WINDOWS.items():
        if pattern in clean or clean.startswith(pattern.split("/")[-1]):
            return window

    # Gemini family fallback
    if "gemini" in clean:
        return 900_000

    # Llama family fallback
    if "llama" in clean:
        return 120_000

    return DEFAULT_CONTEXT_WINDOW


def get_available_input_tokens(model: str) -> int:
    """Returns the number of input tokens available after reserving space for output."""
    total = get_model_context_window(model)
    return int(total * (1 - OUTPUT_RESERVE_FRACTION))


# ============================================================================
# Context Strategy Types
# ============================================================================

class ContextStrategy(str, Enum):
    """How the agent should present document context to the LLM."""
    TARGETED = "TARGETED"               # Only relevant region(s)
    WHOLE_FILE = "WHOLE_FILE"           # Entire document in context
    SUMMARY_FIRST = "SUMMARY_FIRST"     # Summary + targeted sections
    PLAN_EXECUTE = "PLAN_EXECUTE"       # Plan first, then execute per-section


@dataclass
class ContextDecision:
    """The resolved context strategy with metadata."""
    strategy: ContextStrategy
    reason: str
    model: str = ""
    available_tokens: int = 0
    document_tokens: int = 0
    fits_in_context: bool = True

    # For TARGETED strategy
    target_sections: List[str] = field(default_factory=list)
    context_lines_before: int = 20
    context_lines_after: int = 20

    # For PLAN_EXECUTE strategy
    plan_sections: List[str] = field(default_factory=list)

    # Token allocation
    step_max_tokens: int = 4096     # Max output tokens per LLM step
    initial_context_budget: int = 0  # Max input tokens for initial context


# ============================================================================
# Strategy Resolver
# ============================================================================

def resolve_context_strategy(
    analysis: DocumentAnalysis,
    scope: str,
    model: str,
    user_instruction: str,
    is_creation: bool = False,
) -> ContextDecision:
    """
    Determines the optimal context strategy for a given document + request.

    Decision logic (priority order):
    1. Empty/tiny documents → WHOLE_FILE (always)
    2. Creation requests → WHOLE_FILE (need full template awareness)
    3. Targeted edits on small docs → WHOLE_FILE
    4. Targeted edits on large docs → TARGETED (send only relevant section)
    5. Full rewrites where doc fits in context → WHOLE_FILE
    6. Full rewrites where doc exceeds context → PLAN_EXECUTE
    7. Expansions where doc fits → WHOLE_FILE
    8. Expansions where doc exceeds → SUMMARY_FIRST

    Args:
        analysis: DocumentAnalysis from document_analyzer.
        scope: Scope classification string.
        model: LLM model identifier.
        user_instruction: Raw user prompt.
        is_creation: Whether this is a document creation request.

    Returns:
        ContextDecision with the resolved strategy and parameters.
    """
    available = get_available_input_tokens(model)
    doc_tokens = analysis.estimated_tokens
    fits = doc_tokens < int(available * WHOLE_FILE_THRESHOLD_FRACTION)
    is_targeted = scope in ("TARGETED_EDIT", "targeted_edit")
    is_rewrite = scope in ("FULL_DOCUMENT_REWRITE", "full_document_rewrite")
    is_expansion = scope in ("FULL_DOCUMENT_EXPANSION", "full_document_expansion")

    base = ContextDecision(
        strategy=ContextStrategy.WHOLE_FILE,
        reason="",
        model=model,
        available_tokens=available,
        document_tokens=doc_tokens,
        fits_in_context=fits,
    )

    # 1. Empty or tiny documents → always WHOLE_FILE
    if analysis.total_lines <= 50 or not analysis.total_chars:
        base.strategy = ContextStrategy.WHOLE_FILE
        base.reason = "Document is small enough to send entirely"
        base.step_max_tokens = 8192 if is_creation else 4096
        base.initial_context_budget = available
        return base

    # 2. Creation requests → WHOLE_FILE (need to see existing template)
    if is_creation:
        base.strategy = ContextStrategy.WHOLE_FILE
        base.reason = "Creation request — full template context needed"
        base.step_max_tokens = 8192
        base.initial_context_budget = available
        return base

    # 3. Targeted edits
    if is_targeted:
        if fits or analysis.total_lines <= 800:
            base.strategy = ContextStrategy.WHOLE_FILE
            base.reason = "Targeted edit on document that fits in context"
            base.step_max_tokens = 2048
            base.initial_context_budget = available
        elif analysis.total_lines <= 3000:
            # Medium doc, targeted edit → still WHOLE_FILE if fits, else TARGETED
            if fits:
                base.strategy = ContextStrategy.WHOLE_FILE
                base.reason = "Targeted edit — document fits in model context"
                base.step_max_tokens = 2048
                base.initial_context_budget = available
            else:
                base.strategy = ContextStrategy.TARGETED
                base.reason = "Targeted edit on large document — sending only relevant sections"
                base.step_max_tokens = 2048
                base.target_sections = _identify_target_sections(user_instruction, analysis)
                base.initial_context_budget = min(available, doc_tokens // 3)
        else:
            # Very large doc, targeted edit → always TARGETED
            base.strategy = ContextStrategy.TARGETED
            base.reason = "Targeted edit on very large document — focused context only"
            base.step_max_tokens = 2048
            base.target_sections = _identify_target_sections(user_instruction, analysis)
            base.initial_context_budget = min(available, 30000)
        return base

    # 4. Full rewrites
    if is_rewrite:
        if fits:
            base.strategy = ContextStrategy.WHOLE_FILE
            base.reason = "Full rewrite — document fits in model context window"
            base.step_max_tokens = 4096
            base.initial_context_budget = available
        else:
            base.strategy = ContextStrategy.PLAN_EXECUTE
            base.reason = "Full rewrite on document exceeding context window — plan first, then execute"
            base.step_max_tokens = 4096
            base.plan_sections = [s.title for s in analysis.sections]
            base.initial_context_budget = min(available, 50000)
        return base

    # 5. Expansions
    if is_expansion:
        if fits:
            base.strategy = ContextStrategy.WHOLE_FILE
            base.reason = "Full expansion — document fits in model context"
            base.step_max_tokens = 4096
            base.initial_context_budget = available
        else:
            base.strategy = ContextStrategy.SUMMARY_FIRST
            base.reason = "Full expansion on large document — summary + section-by-section"
            base.step_max_tokens = 4096
            base.initial_context_budget = min(available, 40000)
        return base

    # Default fallback
    if fits:
        base.strategy = ContextStrategy.WHOLE_FILE
        base.reason = "Document fits in context window"
        base.step_max_tokens = 4096
        base.initial_context_budget = available
    else:
        base.strategy = ContextStrategy.SUMMARY_FIRST
        base.reason = "Large document — using summary + targeted context"
        base.step_max_tokens = 4096
        base.initial_context_budget = min(available, 40000)

    return base


def _identify_target_sections(
    user_instruction: str,
    analysis: DocumentAnalysis,
) -> List[str]:
    """
    Identifies which sections are referenced in the user instruction.
    Falls back to empty list if no specific sections are detected.
    """
    from document_analyzer import _find_mentioned_sections
    mentioned = _find_mentioned_sections(user_instruction.lower(), analysis)
    return mentioned


# ============================================================================
# Dynamic Max-Token Allocation
# ============================================================================

# Output budget for a batched multi-chunk rewrite turn. Must stay comfortably
# above the largest batch the prompt asks for; every mainstream model used here
# (Gemini, Claude, GPT-4o, Llama 3.3 70B) supports at least 16K output tokens.
FULL_REWRITE_STEP_MAX_TOKENS = 16384

def compute_step_max_tokens(
    strategy: ContextStrategy,
    scope: str,
    step_number: int,
    is_creation: bool = False,
    total_steps: int = 12,
) -> int:
    """
    Computes the max output tokens for a specific agent step.

    Allocates more tokens for:
    - Creation requests (first 2 steps)
    - Full rewrites / expansions
    - Plan generation steps

    Allocates fewer tokens for:
    - Simple tool calls (read, grep)
    - Targeted edits
    - Late-stage fix-up steps
    """
    if is_creation and step_number <= 2:
        return 8192

    if strategy == ContextStrategy.PLAN_EXECUTE and step_number == 1:
        return 4096  # Planning step

    if scope in ("FULL_DOCUMENT_REWRITE", "FULL_DOCUMENT_EXPANSION"):
        # The system prompt instructs the model to batch several rewrite_chunk
        # calls into one turn. At 4096 output tokens (~16 KB of LaTeX) that was
        # physically impossible for a multi-chunk deck, so the model either
        # serialised to one chunk per turn or overran and fell into the
        # truncation-recovery path — which costs a second full LLM call with the
        # entire payload and then discards the response. Give batching enough
        # room to actually happen.
        return FULL_REWRITE_STEP_MAX_TOKENS

    if scope == "TARGETED_EDIT":
        # 2048 was below the size of a single Beamer frame or a short section
        # once JSON escaping is paid for, so ordinary targeted edits tripped the
        # truncation path: a second full LLM call to continue the JSON, and a
        # discarded step plus a third call when that continuation also ran long.
        # Recovering from truncation costs far more than the headroom does.
        return 4096

    return 4096


# ============================================================================
# Targeted Error Context Extraction
# ============================================================================

def extract_error_context(
    latex_code: str,
    errors: List[Dict[str, Any]],
    context_radius: int = 10,
) -> str:
    """
    Extracts focused context around compilation errors instead of sending
    the full error log + full document.

    For each error with a known line number, extracts ±context_radius lines
    from the document. This minimizes the context needed for the LLM to fix
    compilation errors.

    Args:
        latex_code: The current LaTeX buffer.
        errors: List of error dicts with optional 'line' key.
        context_radius: Number of lines above/below the error to include.

    Returns:
        A formatted string with error context blocks.
    """
    if not errors:
        return ""

    lines = latex_code.splitlines(keepends=False)
    total = len(lines)
    parts: List[str] = ["COMPILATION ERRORS WITH CONTEXT:"]

    seen_regions: List[Tuple[int, int]] = []

    for err in errors[:5]:  # Cap at 5 errors
        err_msg = err.get("error", "Unknown error")
        err_line = err.get("line")
        err_context = err.get("context", "")

        if err_line and isinstance(err_line, int) and 1 <= err_line <= total:
            start = max(1, err_line - context_radius)
            end = min(total, err_line + context_radius)

            # Skip if this region overlaps with a previously extracted one
            overlaps = False
            for s, e in seen_regions:
                if start <= e and end >= s:
                    overlaps = True
                    break

            if not overlaps:
                seen_regions.append((start, end))
                parts.append(f"\n--- Error: {err_msg} (Line {err_line}) ---")
                for i in range(start - 1, end):
                    marker = " >>> " if (i + 1) == err_line else "     "
                    parts.append(f"{marker}{i + 1}: {lines[i]}")
        else:
            # No line number available — just include the error message
            parts.append(f"\n--- Error: {err_msg} ---")
            if err_context:
                parts.append(f"  Context: {err_context}")

    return "\n".join(parts)


# ============================================================================
# Initial Context Builder
# ============================================================================

def build_initial_context(
    decision: ContextDecision,
    analysis: DocumentAnalysis,
    workspace: Any,
    user_instruction: str,
    doc_outline: str,
) -> str:
    """
    Builds the initial document context to include in the first LLM message,
    based on the resolved context strategy.

    Args:
        decision: The ContextDecision from resolve_context_strategy.
        analysis: DocumentAnalysis from document_analyzer.
        workspace: The ShadowWorkspace instance.
        user_instruction: The raw user prompt.
        doc_outline: The document outline from _build_document_outline.

    Returns:
        A string to use as the document context portion of the initial user message.
    """
    from document_analyzer import generate_compact_summary

    total_lines = workspace.get_line_count()

    if decision.strategy == ContextStrategy.WHOLE_FILE:
        # Send the full document — it fits comfortably
        full_content = workspace.read_lines(1, total_lines)
        return (
            f"FULL DOCUMENT CONTENT ({total_lines} lines, ~{analysis.estimated_tokens} tokens):\n"
            f"{doc_outline}\n\n"
            f"{full_content}"
        )

    elif decision.strategy == ContextStrategy.TARGETED:
        # Send only outline + targeted sections
        parts = [
            f"DOCUMENT OVERVIEW ({total_lines} lines total — showing targeted context only):\n",
            doc_outline,
            "",
        ]

        # If we identified target sections, read those regions
        if decision.target_sections and analysis.sections:
            for sec in analysis.sections:
                if sec.title in decision.target_sections:
                    ctx_start = max(1, sec.start_line - decision.context_lines_before)
                    ctx_end = min(total_lines, sec.end_line + decision.context_lines_after)
                    region = workspace.read_lines(ctx_start, ctx_end)
                    parts.append(f"\n--- TARGETED SECTION: {sec.title} (Lines {ctx_start}–{ctx_end}) ---")
                    parts.append(region)
        else:
            # Fallback: show first 100 lines + outline
            preview = workspace.read_lines(1, min(100, total_lines))
            parts.append(f"\nFILE PREVIEW (first 100 lines):\n{preview}")
            parts.append("\nUse `read_file_range` and `grep_search` to inspect specific sections before editing.")

        return "\n".join(parts)

    elif decision.strategy == ContextStrategy.SUMMARY_FIRST:
        # Send compact summary + outline
        summary = generate_compact_summary(analysis)
        return (
            f"DOCUMENT SUMMARY (file is {total_lines} lines — too large to send fully):\n\n"
            f"{summary}\n\n"
            f"{doc_outline}\n\n"
            "Use `read_file_range` to inspect specific sections as needed.\n"
            "Do NOT request the entire file — work section-by-section using chunk IDs."
        )

    elif decision.strategy == ContextStrategy.PLAN_EXECUTE:
        # Send compact summary for planning phase
        summary = generate_compact_summary(analysis)
        return (
            f"DOCUMENT SUMMARY (file is {total_lines} lines — plan-then-execute mode):\n\n"
            f"{summary}\n\n"
            f"{doc_outline}\n\n"
            "PLANNING MODE: Before making edits, first analyze the document structure and create\n"
            "a transformation plan. Use `read_file_range` to inspect key sections as needed.\n"
            "Then execute the plan section-by-section using `rewrite_chunk` or `str_replace`."
        )

    # Fallback
    return doc_outline
