"""
backend/tests/test_full_document_rewrite.py
===========================================
Comprehensive unit and integration test suite covering:
(a) A targeted edit request only touches the relevant chunk.
(b) A full-rewrite request touches every chunk in a multi-chapter fixture document.
(c) The coverage check correctly blocks finalization when a chunk is missed and resumes the loop.
(d) Scope classifier heuristics and LLM fallback.
(e) DocumentIndex AST chunking and byte-offset replacement (rewrite_chunk).
(f) Retriever top-k bypass for FULL_DOCUMENT_REWRITE.
(g) Leftover forbidden topic terms detection in edit_validator.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from scope_classifier import (
    classify_scope,
    extract_topic_transition_terms,
    ScopeType,
    ScopeClassificationResult,
)
from document_index import DocumentChunk, DocumentIndex
from query_rewriter import rewrite_query
from retriever import retrieve_chunks
from edit_validator import validate_coverage, check_environment_balance, auto_repair_truncated_latex
from opencode.shadow_workspace import ShadowWorkspace
from opencode.tools import execute_tool, TOOL_DEFINITIONS
from opencode.agent_loop import (
    determine_adaptive_step_budget,
    stream_opencode_agent,
    run_opencode_agent,
)


# ============================================================================
# Multi-Chapter LaTeX Fixture Document
# ============================================================================

MULTI_CHAPTER_LATEX_FIXTURE = r"""\documentclass[11pt,a4paper,oneside]{report}
\usepackage[utf8]{inputenc}
\usepackage[margin=1in]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{hyperref}

\title{Old Topic: Quantum Computing Foundations}
\author{Alice Quantum}
\date{\today}

\begin{document}
\maketitle

\begin{abstract}
This thesis explores quantum superposition and entanglement algorithms.
\end{abstract}

\tableofcontents

\chapter{Introduction to Quantum Mechanics}
Quantum mechanics deals with phenomena at microscopic scales.
Superposition allows qubits to exist in multiple states simultaneously.

\chapter{Quantum Algorithms and Circuits}
Shor's algorithm provides polynomial-time integer factorization.
Grover's algorithm accelerates unstructured database search.

\chapter{Quantum Error Correction}
Fault-tolerant quantum computing requires topological surface codes.
Decoherence remains the primary physical limitation.

\chapter{Empirical Evaluation and Future Outlook}
Simulation results on 50-qubit architectures demonstrate exponential speedups.
Future work will address noisy intermediate-scale quantum systems.

\end{document}
"""


# ============================================================================
# 1. Scope Classifier Tests
# ============================================================================

def test_scope_classifier_heuristics_full_rewrite():
    """Verify that full-rewrite keywords correctly classify as FULL_DOCUMENT_REWRITE."""
    prompts = [
        "Change the topic and replace all content based on this new source material",
        "Rewrite the entire document to be about Machine Learning in Healthcare",
        "Please overhaul all chapters and rewrite everything with new data",
        "Replace all content throughout the document based on the attached report",
        "Rewrite each chapter from scratch on Computer Vision",
    ]
    for prompt in prompts:
        res = classify_scope(user_instruction=prompt, current_code=MULTI_CHAPTER_LATEX_FIXTURE)
        assert res.is_full_rewrite, f"Failed for prompt: {prompt}"
        assert res.scope == ScopeType.FULL_DOCUMENT_REWRITE.value


def test_scope_classifier_heuristics_targeted_edit():
    """Verify that localized edit keywords correctly classify as TARGETED_EDIT."""
    prompts = [
        "Fix the typo in chapter 1",
        "Change title to Quantum Computing Essentials",
        "Update the equation on slide 3",
        "Fix spelling and grammar in section 2",
        "Rename Alice Quantum to Dr. Alice",
    ]
    for prompt in prompts:
        res = classify_scope(user_instruction=prompt, current_code=MULTI_CHAPTER_LATEX_FIXTURE)
        assert not res.is_full_rewrite, f"Failed for prompt: {prompt}"
        assert res.scope == ScopeType.TARGETED_EDIT.value


def test_scope_classifier_llm_fallback():
    """Verify that ambiguous prompts fall back to LLM classification."""
    ambiguous_prompt = "Let us transform this piece into something about robotics"
    mock_llm_response = {
        "content": json.dumps({
            "scope": "FULL_DOCUMENT_REWRITE",
            "confidence": 0.92,
            "reason": "Request asks to transform entire piece to robotics",
        })
    }
    with patch("providers.router.provider_router.chat", return_value=mock_llm_response):
        res = classify_scope(user_instruction=ambiguous_prompt)
        assert res.scope == ScopeType.FULL_DOCUMENT_REWRITE.value
        assert res.is_heuristic is False


def test_extract_topic_transition_terms():
    """Verify that old topic keywords are extracted from prompt."""
    prompt = "Change topic from Quantum Computing to Machine Learning"
    terms = extract_topic_transition_terms(prompt, MULTI_CHAPTER_LATEX_FIXTURE)
    assert any("quantum computing" in t.lower() for t in terms)


# ============================================================================
# 2. DocumentIndex & Offset-based rewrite_chunk Tests
# ============================================================================

def test_document_index_chunking_multi_chapter():
    """Verify that DocumentIndex splits the fixture into preamble, frontmatter, and 4 chapters."""
    doc_index = DocumentIndex()
    chunks = doc_index.get_chunks(MULTI_CHAPTER_LATEX_FIXTURE)
    content_chunks = doc_index.get_content_chunks(MULTI_CHAPTER_LATEX_FIXTURE)

    chunk_ids = [c.chunk_id for c in chunks]
    assert "preamble" in chunk_ids
    assert "frontmatter" in chunk_ids
    assert "chapter_1" in chunk_ids
    assert "chapter_2" in chunk_ids
    assert "chapter_3" in chunk_ids
    assert "chapter_4" in chunk_ids

    assert len(content_chunks) == 4
    assert [c.chunk_id for c in content_chunks] == ["chapter_1", "chapter_2", "chapter_3", "chapter_4"]
    assert "Introduction" in content_chunks[0].title
    assert "Algorithms" in content_chunks[1].title
    assert "Error Correction" in content_chunks[2].title
    assert "Evaluation" in content_chunks[3].title


def test_document_index_replace_chunk_offsets():
    """Verify that replace_chunk replaces exact byte offsets without breaking surrounding text."""
    doc_index = DocumentIndex()
    new_ch2_content = "\\chapter{Deep Neural Networks}\nDeep neural networks consist of layered artificial neurons.\n"
    
    updated_code, updated_chunk, delta = doc_index.replace_chunk(
        latex_code=MULTI_CHAPTER_LATEX_FIXTURE,
        chunk_id="chapter_2",
        new_content=new_ch2_content,
    )

    assert "\\chapter{Deep Neural Networks}" in updated_code
    assert "\\chapter{Quantum Algorithms and Circuits}" not in updated_code
    # Chapter 1 and Chapter 3 must remain intact
    assert "\\chapter{Introduction to Quantum Mechanics}" in updated_code
    assert "\\chapter{Quantum Error Correction}" in updated_code
    assert "\\end{document}" in updated_code


def test_shadow_workspace_rewrite_chunk_tool():
    """Verify that ShadowWorkspace.rewrite_chunk modifies the buffer and tracks touched chunks."""
    workspace = ShadowWorkspace(original_code=MULTI_CHAPTER_LATEX_FIXTURE)
    assert workspace.get_touched_chunks() == set()

    res = execute_tool(
        tool_name="rewrite_chunk",
        args={
            "chunk_id": "chapter_1",
            "new_content": "\\chapter{Introduction to AI}\nArtificial intelligence is the science of making intelligent machines.\n",
        },
        workspace=workspace,
    )
    assert res["success"] is True
    assert res["chunk_id"] == "chapter_1"
    assert "chapter_1" in workspace.get_touched_chunks()
    assert "\\chapter{Introduction to AI}" in workspace.get_buffer()


# ============================================================================
# 3. Retriever Full-Rewrite Bypass Tests
# ============================================================================

def test_retriever_full_rewrite_bypasses_top_k():
    """Verify that retriever returns all content chunks when scope is FULL_DOCUMENT_REWRITE."""
    # Targeted query with top_k=1
    targeted_chunks = retrieve_chunks(
        document_code=MULTI_CHAPTER_LATEX_FIXTURE,
        query="Shor's algorithm circuit",
        scope=ScopeType.TARGETED_EDIT.value,
        top_k=1,
    )
    assert len(targeted_chunks) == 1
    assert targeted_chunks[0].chunk_id == "chapter_2"

    # Full rewrite mode with top_k=1 (must bypass top_k and return all 4 content chunks + frontmatter)
    full_chunks = retrieve_chunks(
        document_code=MULTI_CHAPTER_LATEX_FIXTURE,
        query="Shor's algorithm circuit",
        scope=ScopeType.FULL_DOCUMENT_REWRITE.value,
        top_k=1,
    )
    assert len(full_chunks) >= 4
    chunk_ids = [c.chunk_id for c in full_chunks]
    assert "chapter_1" in chunk_ids
    assert "chapter_2" in chunk_ids
    assert "chapter_3" in chunk_ids
    assert "chapter_4" in chunk_ids


# ============================================================================
# 4. Dynamic Step Budgeting Tests
# ============================================================================

def test_dynamic_step_budget_full_rewrite():
    """Verify that step budget scales dynamically with chunk count in FULL_DOCUMENT_REWRITE."""
    # 4 chunks -> max(16, 4*2 + 4) = 16
    budget_4 = determine_adaptive_step_budget(
        user_instruction="Rewrite the entire document",
        total_lines=100,
        num_chapters=4,
        num_sections=4,
        num_chunks=4,
        scope=ScopeType.FULL_DOCUMENT_REWRITE.value,
    )
    assert budget_4 == 16

    # 10 chunks -> max(16, 10*2 + 4) = 24
    budget_10 = determine_adaptive_step_budget(
        user_instruction="Rewrite the entire document",
        total_lines=500,
        num_chapters=10,
        num_sections=10,
        num_chunks=10,
        scope=ScopeType.FULL_DOCUMENT_REWRITE.value,
    )
    assert budget_10 == 24


# ============================================================================
# 5. Requirement (a): Targeted edit request only touches relevant chunk
# ============================================================================

def test_targeted_edit_only_touches_relevant_chunk():
    """Verify that a targeted edit only touches the single target chunk."""
    workspace = ShadowWorkspace(original_code=MULTI_CHAPTER_LATEX_FIXTURE)
    
    # User asks: "Fix typo in Shor's algorithm in chapter 2"
    execute_tool(
        tool_name="str_replace",
        args={
            "old_str": "Shor's algorithm provides polynomial-time integer factorization.",
            "new_str": "Shor's algorithm provides polynomial-time prime integer factorization.",
        },
        workspace=workspace,
    )

    touched = workspace.get_touched_chunks()
    assert touched == {"chapter_2"}, f"Expected only chapter_2 to be touched, got {touched}"
    assert "chapter_1" not in touched
    assert "chapter_3" not in touched
    assert "chapter_4" not in touched


# ============================================================================
# 6. Requirement (b): Full-rewrite request touches every chunk in multi-chapter fixture
# ============================================================================

def test_full_rewrite_touches_every_chunk():
    """Verify that in full-rewrite mode, rewrite_chunk updates all chapters in the fixture."""
    workspace = ShadowWorkspace(original_code=MULTI_CHAPTER_LATEX_FIXTURE)
    
    new_chapters = {
        "chapter_1": "\\chapter{Introduction to Machine Learning}\nML algorithms learn patterns from data.\n",
        "chapter_2": "\\chapter{Deep Learning Architectures}\nTransformers and CNNs form modern vision and NLP.\n",
        "chapter_3": "\\chapter{Training and Optimization}\nStochastic gradient descent optimizes loss functions.\n",
        "chapter_4": "\\chapter{Experimental Results}\nEvaluation on ImageNet demonstrates state-of-the-art accuracy.\n",
    }

    for chunk_id, new_content in new_chapters.items():
        res = execute_tool(
            tool_name="rewrite_chunk",
            args={"chunk_id": chunk_id, "new_content": new_content},
            workspace=workspace,
        )
        assert res["success"] is True

    touched = workspace.get_touched_chunks()
    assert touched == {"chapter_1", "chapter_2", "chapter_3", "chapter_4"}

    # Coverage validation should pass
    cov_report = validate_coverage(
        workspace=workspace,
        user_instruction="Change topic to Machine Learning and rewrite all chapters",
        scope=ScopeType.FULL_DOCUMENT_REWRITE.value,
        forbidden_terms=["Quantum Algorithms", "qubits", "Shor's algorithm"],
    )
    assert cov_report.passed is True
    assert cov_report.total_chunks == 4
    assert cov_report.edited_chunks == 4
    assert cov_report.missing_chunk_ids == []


# ============================================================================
# 7. Requirement (c): Coverage check correctly blocks finalization & resumes loop
# ============================================================================

def test_coverage_check_blocks_finalization_when_chunk_missed():
    """
    Verify that if the agent only edits 3 out of 4 chapters and attempts done=true,
    coverage validation blocks finalization, returns missing chunk IDs, and allows
    completion once all 4 are rewritten.
    """
    workspace = ShadowWorkspace(original_code=MULTI_CHAPTER_LATEX_FIXTURE)

    # Agent rewrites chapters 1, 2, and 3, but forgets chapter 4
    execute_tool("rewrite_chunk", {"chunk_id": "chapter_1", "new_content": "\\chapter{Intro to ML}\nML intro.\n"}, workspace)
    execute_tool("rewrite_chunk", {"chunk_id": "chapter_2", "new_content": "\\chapter{Architectures}\nModel arch.\n"}, workspace)
    execute_tool("rewrite_chunk", {"chunk_id": "chapter_3", "new_content": "\\chapter{Training}\nTraining steps.\n"}, workspace)

    # 1. First validation check: should FAIL because chapter_4 was missed
    cov_fail = validate_coverage(
        workspace=workspace,
        user_instruction="Rewrite all content for new topic",
        scope=ScopeType.FULL_DOCUMENT_REWRITE.value,
    )
    assert cov_fail.passed is False
    assert cov_fail.total_chunks == 4
    assert cov_fail.edited_chunks == 3
    assert cov_fail.missing_chunk_ids == ["chapter_4"]
    assert "chapter_4" in cov_fail.feedback_message
    assert "COVERAGE CHECK FAILED" in cov_fail.feedback_message

    # 2. Agent resumes and rewrites chapter 4
    execute_tool("rewrite_chunk", {"chunk_id": "chapter_4", "new_content": "\\chapter{Conclusion}\nFinal thoughts.\n"}, workspace)

    # 3. Second validation check: should PASS
    cov_pass = validate_coverage(
        workspace=workspace,
        user_instruction="Rewrite all content for new topic",
        scope=ScopeType.FULL_DOCUMENT_REWRITE.value,
    )
    assert cov_pass.passed is True
    assert cov_pass.total_chunks == 4
    assert cov_pass.edited_chunks == 4
    assert cov_pass.missing_chunk_ids == []


def test_coverage_check_blocks_when_old_topic_terms_remain():
    """Verify that coverage check blocks if forbidden old topic keywords remain in document."""
    workspace = ShadowWorkspace(original_code=MULTI_CHAPTER_LATEX_FIXTURE)

    # Rewrite all 4 chapters, but leave obsolete term "Quantum Computing Foundations" in title
    execute_tool("rewrite_chunk", {"chunk_id": "chapter_1", "new_content": "\\chapter{Intro}\nIntro content.\n"}, workspace)
    execute_tool("rewrite_chunk", {"chunk_id": "chapter_2", "new_content": "\\chapter{Body}\nBody content.\n"}, workspace)
    execute_tool("rewrite_chunk", {"chunk_id": "chapter_3", "new_content": "\\chapter{Method}\nMethod content.\n"}, workspace)
    execute_tool("rewrite_chunk", {"chunk_id": "chapter_4", "new_content": "\\chapter{Results}\nResults content.\n"}, workspace)

    cov_leftover = validate_coverage(
        workspace=workspace,
        user_instruction="Change topic from Quantum Computing Foundations to AI",
        scope=ScopeType.FULL_DOCUMENT_REWRITE.value,
        forbidden_terms=["Quantum Computing Foundations"],
    )
    assert cov_leftover.passed is False
    assert "LEFTOVER CONTENT CHECK FAILED" in cov_leftover.feedback_message
    assert len(cov_leftover.leftover_terms_found) > 0

    # Fix the title using str_replace to remove the old topic term
    execute_tool(
        "str_replace",
        {"old_str": "\\title{Old Topic: Quantum Computing Foundations}", "new_str": "\\title{New Topic: AI Foundations}"},
        workspace,
    )

    cov_fixed = validate_coverage(
        workspace=workspace,
        user_instruction="Change topic from Quantum Computing Foundations to AI",
        scope=ScopeType.FULL_DOCUMENT_REWRITE.value,
        forbidden_terms=["Quantum Computing Foundations"],
    )
    assert cov_fixed.passed is True


# ============================================================================
# 8. End-to-End Agent Loop Simulation Tests
# ============================================================================

def test_stream_opencode_agent_emits_coverage_check_event():
    """
    Verify that stream_opencode_agent yields a 'coverage_check' event during
    a full document rewrite request when the agent completes all chunks.
    """
    # Simulate LLM turns:
    # Turn 1: thought + rewrite_chunk chapter_1
    # Turn 2: thought + rewrite_chunk chapter_2
    # Turn 3: thought + rewrite_chunk chapter_3
    # Turn 4: thought + rewrite_chunk chapter_4
    # Turn 5: thought + done=true
    llm_responses = [
        {"content": json.dumps({"thought": "Rewriting Ch 1", "tool_call": {"name": "rewrite_chunk", "arguments": {"chunk_id": "chapter_1", "new_content": "\\chapter{Ch 1}\nNew 1\n"}}})},
        {"content": json.dumps({"thought": "Rewriting Ch 2", "tool_call": {"name": "rewrite_chunk", "arguments": {"chunk_id": "chapter_2", "new_content": "\\chapter{Ch 2}\nNew 2\n"}}})},
        {"content": json.dumps({"thought": "Rewriting Ch 3", "tool_call": {"name": "rewrite_chunk", "arguments": {"chunk_id": "chapter_3", "new_content": "\\chapter{Ch 3}\nNew 3\n"}}})},
        {"content": json.dumps({"thought": "Rewriting Ch 4", "tool_call": {"name": "rewrite_chunk", "arguments": {"chunk_id": "chapter_4", "new_content": "\\chapter{Ch 4}\nNew 4\n"}}})},
        {"content": json.dumps({"thought": "All rewritten", "done": True, "explanation": "Rewrote all chapters on new topic."})},
    ]

    response_iter = iter(llm_responses)

    def mock_chat(*args, **kwargs):
        return next(response_iter)

    with patch("providers.router.provider_router.chat", side_effect=mock_chat):
        events = list(stream_opencode_agent(
            user_instruction="Rewrite the entire document with new content",
            project_id="test-proj",
            current_code=MULTI_CHAPTER_LATEX_FIXTURE,
            mode="edit",
        ))

    event_types = [e.get("type") for e in events]
    assert "coverage_check" in event_types
    coverage_events = [e for e in events if e.get("type") == "coverage_check"]
    assert len(coverage_events) >= 1
    assert coverage_events[-1]["passed"] is True
    assert coverage_events[-1]["total_chunks"] == 4
    assert coverage_events[-1]["edited_chunks"] == 4
    assert coverage_events[-1]["missing_chunk_ids"] == []


def test_agent_loop_rejection_and_recovery_on_premature_done():
    """
    Verify that if the LLM attempts done=true before rewriting all chapters,
    the agent loop rejects done, feeds the missing chunk IDs back, and allows
    completion once the remaining chunk is rewritten.
    """
    # Turn 1: rewrite chapter_1
    # Turn 2: rewrite chapter_2
    # Turn 3: rewrite chapter_3
    # Turn 4: premature done=true (rejected by coverage check!)
    # Turn 5: rewrite chapter_4
    # Turn 6: final done=true (accepted!)
    llm_responses = [
        {"content": json.dumps({"thought": "Rewriting Ch 1", "tool_call": {"name": "rewrite_chunk", "arguments": {"chunk_id": "chapter_1", "new_content": "\\chapter{Ch 1}\nNew 1\n"}}})},
        {"content": json.dumps({"thought": "Rewriting Ch 2", "tool_call": {"name": "rewrite_chunk", "arguments": {"chunk_id": "chapter_2", "new_content": "\\chapter{Ch 2}\nNew 2\n"}}})},
        {"content": json.dumps({"thought": "Rewriting Ch 3", "tool_call": {"name": "rewrite_chunk", "arguments": {"chunk_id": "chapter_3", "new_content": "\\chapter{Ch 3}\nNew 3\n"}}})},
        {"content": json.dumps({"thought": "Done early", "done": True, "explanation": "Attempted early completion."})},
        {"content": json.dumps({"thought": "Rewriting Ch 4 after rejection", "tool_call": {"name": "rewrite_chunk", "arguments": {"chunk_id": "chapter_4", "new_content": "\\chapter{Ch 4}\nNew 4\n"}}})},
        {"content": json.dumps({"thought": "All complete now", "done": True, "explanation": "All 4 chapters rewritten."})},
    ]

    response_iter = iter(llm_responses)

    def mock_chat(*args, **kwargs):
        return next(response_iter)

    with patch("providers.router.provider_router.chat", side_effect=mock_chat):
        events = list(stream_opencode_agent(
            user_instruction="Rewrite the entire document with new content",
            project_id="test-proj",
            current_code=MULTI_CHAPTER_LATEX_FIXTURE,
            mode="edit",
        ))

    coverage_events = [e for e in events if e.get("type") == "coverage_check"]
    # First coverage check failed, second passed
    assert len(coverage_events) >= 2
    assert coverage_events[0]["passed"] is False
    assert coverage_events[0]["missing_chunk_ids"] == ["chapter_4"]
    assert coverage_events[-1]["passed"] is True
    assert coverage_events[-1]["missing_chunk_ids"] == []

    # Final result event must be present
    result_events = [e for e in events if e.get("type") == "final_diff" or e.get("type") == "result"]
    assert len(result_events) > 0
