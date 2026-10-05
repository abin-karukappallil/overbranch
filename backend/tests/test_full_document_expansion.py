"""
tests/test_full_document_expansion.py — Regression & Unit Tests for Bug 1 (Full Document Expansion)
==================================================================================================
Tests:
1. Scope classifier classifies expansion requests ("add more content", "expand document",
   "make longer", "flesh out all chapters") as FULL_DOCUMENT_EXPANSION.
2. Step budget dynamically scales for FULL_DOCUMENT_EXPANSION based on chunk count.
3. Coverage validator enforces that all content chunks are expanded in FULL_DOCUMENT_EXPANSION mode.
4. Agent loop emits coverage_check events and prompts agent to complete untouched chunks.
"""

import json
from unittest.mock import MagicMock, patch
import pytest

from scope_classifier import classify_scope, ScopeType
from document_index import DocumentIndex
from edit_validator import validate_coverage, CoverageValidationResult
from opencode.shadow_workspace import ShadowWorkspace
from opencode.agent_loop import determine_adaptive_step_budget, stream_opencode_agent


MULTI_CHAPTER_DOC = r"""\documentclass{report}
\usepackage{amsmath,amssymb}
\begin{document}

\chapter{Introduction}
This is the introduction chapter.

\chapter{Literature Review}
This is the literature review chapter.

\chapter{Methodology}
This is the methodology chapter.

\chapter{Experimental Results}
This is the results chapter.

\chapter{Conclusion}
This is the conclusion chapter.

\end{document}
"""

SECTION_DOC = r"""\documentclass{article}
\begin{document}

\section{Introduction}
Introductory remarks.

\section{System Architecture}
Architecture details.

\section{Evaluation}
Performance metrics.

\section{Conclusion}
Final remarks.

\end{document}
"""


def test_scope_classifier_detects_expansion_heuristics():
    """Verify that expansion prompts are classified as FULL_DOCUMENT_EXPANSION."""
    expansion_prompts = [
        "Please add more content to the document",
        "Expand the entire document with more details and equations",
        "Expand all chapters with detailed explanations",
        "Make the document longer and elaborate on each section",
        "Make document 10 pages with extensive theory",
        "Flesh out the report across all chapters",
        "Add more details throughout the document",
        "Elaborate on all sections with benchmark results",
        "Write more content in all topics",
        "Expand every chapter with comprehensive subchapters",
    ]

    for prompt in expansion_prompts:
        result = classify_scope(prompt)
        assert result.scope == ScopeType.FULL_DOCUMENT_EXPANSION.value, f"Failed for: '{prompt}' (got {result.scope})"
        assert result.is_expansion is True
        assert result.is_full_rewrite is False


def test_scope_classifier_preserves_targeted_and_rewrite():
    """Verify that targeted edits and full rewrites are NOT misclassified as expansion."""
    rewrite_prompt = "Rewrite the entire document from scratch based on this new topic"
    res_rewrite = classify_scope(rewrite_prompt)
    assert res_rewrite.scope == ScopeType.FULL_DOCUMENT_REWRITE.value
    assert res_rewrite.is_full_rewrite is True
    assert res_rewrite.is_expansion is False

    targeted_prompt = "Fix the typo in section 2 and change author name to John Doe"
    res_targeted = classify_scope(targeted_prompt)
    assert res_targeted.scope == ScopeType.TARGETED_EDIT.value
    assert res_targeted.is_expansion is False
    assert res_targeted.is_full_rewrite is False


def test_adaptive_step_budget_scales_for_expansion():
    """
    FULL_DOCUMENT_EXPANSION gets more steps than a targeted edit, scaling with
    chunk count but never past the documented cap.
    """
    from opencode.agent_loop import MAX_STEP_BUDGET

    budget_5_chunks = determine_adaptive_step_budget(
        user_instruction="Add more content to all chapters",
        total_lines=100,
        num_chapters=5,
        num_sections=0,
        num_chunks=5,
        scope=ScopeType.FULL_DOCUMENT_EXPANSION.value,
        mode="edit",
    )
    budget_10_chunks = determine_adaptive_step_budget(
        user_instruction="Expand all sections with deep technical explanations",
        total_lines=200,
        num_chapters=0,
        num_sections=10,
        num_chunks=10,
        scope=ScopeType.FULL_DOCUMENT_EXPANSION.value,
        mode="edit",
    )
    budget_huge = determine_adaptive_step_budget(
        user_instruction="Expand every section",
        total_lines=4000,
        num_chapters=0,
        num_sections=150,
        num_chunks=150,
        scope=ScopeType.FULL_DOCUMENT_EXPANSION.value,
        mode="edit",
    )

    assert budget_5_chunks >= 10
    assert budget_10_chunks > budget_5_chunks
    assert budget_huge == MAX_STEP_BUDGET
    assert all(b <= MAX_STEP_BUDGET for b in (budget_5_chunks, budget_10_chunks))


def test_coverage_validation_blocks_incomplete_expansion():
    """Verify that validate_coverage fails if only a subset of chunks are expanded."""
    ws = ShadowWorkspace(MULTI_CHAPTER_DOC, project_id="test-exp")
    
    # Only edit chapter 1
    ws.str_replace("This is the introduction chapter.", "This is the expanded introduction with 3 subsections.")
    
    res = validate_coverage(
        workspace=ws,
        user_instruction="Add more content to the document",
        scope=ScopeType.FULL_DOCUMENT_EXPANSION.value,
    )

    assert res.passed is False
    assert res.total_chunks == 5
    assert res.edited_chunks == 1
    assert len(res.missing_chunk_ids) == 4
    assert "chapter_2" in res.missing_chunk_ids
    assert "chapter_3" in res.missing_chunk_ids
    assert "chapter_4" in res.missing_chunk_ids
    assert "chapter_5" in res.missing_chunk_ids
    assert "COVERAGE CHECK FAILED" in res.feedback_message
    assert "FULL_DOCUMENT_EXPANSION" in res.feedback_message


def test_coverage_validation_passes_when_all_chunks_expanded():
    """Verify that validate_coverage passes when all content chunks are touched."""
    ws = ShadowWorkspace(SECTION_DOC, project_id="test-sec")
    
    # Touch all 4 section chunks
    ws.insert_into_chunk("section_1", "Added detailed intro background.")
    ws.insert_into_chunk("section_2", "Added architecture diagram details.")
    ws.insert_into_chunk("section_3", "Added evaluation metrics table.")
    ws.insert_into_chunk("section_4", "Added future work directions.")

    res = validate_coverage(
        workspace=ws,
        user_instruction="Expand all sections with extensive details",
        scope=ScopeType.FULL_DOCUMENT_EXPANSION.value,
    )

    assert res.passed is True
    assert res.total_chunks == 4
    assert res.edited_chunks == 4
    assert len(res.missing_chunk_ids) == 0


def test_agent_loop_rejection_and_recovery_on_expansion():
    """Verify agent loop enforces coverage and prompts agent when prematurely stopping on expansion."""
    mock_router = MagicMock()
    mock_router.chat.side_effect = [
        # Step 1: Agent edits only chunk 1
        {
            "content": json.dumps({
                "thought": "Expanding chapter 1",
                "tool_call": {
                    "name": "insert_into_chunk",
                    "arguments": {"chunk_id": "chapter_1", "content": "Deep expanded text for Ch 1"}
                }
            }),
            "finish_reason": "stop",
        },
        # Step 2: Agent attempts premature done=true
        {
            "content": json.dumps({"thought": "I'm done", "done": True}),
            "finish_reason": "stop",
        },
        # Step 3: Agent receives coverage rejection feedback and expands remaining chunks
        {
            "content": json.dumps({
                "thought": "Expanding remaining chapters",
                "tool_call": {
                    "name": "insert_into_chunk",
                    "arguments": {"chunk_id": "chapter_2", "content": "Deep expanded text for Ch 2"}
                }
            }),
            "finish_reason": "stop",
        },
        # Step 4: Final done
        {
            "content": json.dumps({"thought": "Completed all", "done": True}),
            "finish_reason": "stop",
        },
    ]

    doc_2_chapters = r"""\documentclass{report}
\begin{document}
\chapter{First}
Content 1.
\chapter{Second}
Content 2.
\end{document}"""

    with patch("opencode.agent_loop.provider_router", mock_router):
        events = list(stream_opencode_agent(
            user_instruction="Add more content across all chapters",
            project_id="test-p",
            current_code=doc_2_chapters,
            mode="edit",
            max_steps=6,
        ))

        # Check coverage check events were emitted
        cov_events = [e for e in events if e.get("type") == "coverage_check"]
        assert len(cov_events) >= 1
        # First coverage check should have failed because chapter_2 was missing
        assert cov_events[0]["passed"] is False
        assert "chapter_2" in cov_events[0]["missing_chunk_ids"]
