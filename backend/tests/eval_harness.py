"""
tests/eval_harness.py — Automated Evaluation Suite (18 Benchmark Prompts)
========================================================================
Runs an end-to-end evaluation suite of 18 realistic LaTeX editing prompts across:
  - Category A (Bug 1): Full Document Expansion prompts
  - Category B (Bug 2): Bibliography & List insertion prompts
  - Category C (Bug 3): Multi-turn Attached Reference File persistence
  - Category D (Regressions): Targeted edits, Topic rewrites, Beamer presentations, Document creation

Can be run via pytest (`pytest backend/tests/eval_harness.py`) or standalone (`python backend/tests/eval_harness.py`).
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch
import pytest

from scope_classifier import classify_scope, ScopeType
from document_index import DocumentIndex
from edit_validator import validate_coverage
from opencode.shadow_workspace import ShadowWorkspace
from opencode.tools import execute_tool
from attached_context import attached_context_store, AttachedContextStore

logger = logging.getLogger("eval_harness")


@dataclass
class EvalCase:
    case_id: str
    category: str
    prompt: str
    input_latex: str
    expected_scope: str
    attached_file: Optional[Dict[str, Any]] = None
    validation_type: str = "scope"  # "scope", "insert_bib", "insert_list", "coverage", "attachment"
    expected_contains: Optional[List[str]] = None


TEST_DOC_MULTI_CHAPTER = r"""\documentclass{report}
\begin{document}
\chapter{Introduction}
Introduction text.
\chapter{Architecture}
Architecture text.
\chapter{Results}
Results text.
\end{document}
"""

TEST_DOC_BIB = r"""\documentclass{article}
\begin{document}
\section{Introduction}
Some text referencing literature.
\section{References}
\begin{thebibliography}{99}
\bibitem{knuth84} D. Knuth, The TeXbook, 1984.
\end{thebibliography}
\end{document}
"""

TEST_DOC_LIST = r"""\documentclass{article}
\begin{document}
\section{Highlights}
Key points:
\begin{itemize}
\item Point one.
\end{itemize}
\end{document}
"""


EVAL_PROMPTS: List[EvalCase] = [
    # --- Category A: Full Document Expansion (Bug 1) ---
    EvalCase(
        case_id="EXP-01",
        category="Bug 1 (Expansion)",
        prompt="Please add more content to the document across all chapters.",
        input_latex=TEST_DOC_MULTI_CHAPTER,
        expected_scope=ScopeType.FULL_DOCUMENT_EXPANSION.value,
        validation_type="coverage",
    ),
    EvalCase(
        case_id="EXP-02",
        category="Bug 1 (Expansion)",
        prompt="Expand the entire document with detailed theoretical proofs and equations.",
        input_latex=TEST_DOC_MULTI_CHAPTER,
        expected_scope=ScopeType.FULL_DOCUMENT_EXPANSION.value,
        validation_type="scope",
    ),
    EvalCase(
        case_id="EXP-03",
        category="Bug 1 (Expansion)",
        prompt="Make the document longer and elaborate on each section thoroughly.",
        input_latex=TEST_DOC_MULTI_CHAPTER,
        expected_scope=ScopeType.FULL_DOCUMENT_EXPANSION.value,
        validation_type="scope",
    ),
    EvalCase(
        case_id="EXP-04",
        category="Bug 1 (Expansion)",
        prompt="Flesh out the report and add depth to all chapters.",
        input_latex=TEST_DOC_MULTI_CHAPTER,
        expected_scope=ScopeType.FULL_DOCUMENT_EXPANSION.value,
        validation_type="scope",
    ),
    EvalCase(
        case_id="EXP-05",
        category="Bug 1 (Expansion)",
        prompt="Make document 10 pages by expanding every chapter.",
        input_latex=TEST_DOC_MULTI_CHAPTER,
        expected_scope=ScopeType.FULL_DOCUMENT_EXPANSION.value,
        validation_type="scope",
    ),

    # --- Category B: Bibliography & List Insertions (Bug 2) ---
    EvalCase(
        case_id="BIB-01",
        category="Bug 2 (Insert Into Chunk)",
        prompt="Add a reference to Smith 2024 in the bibliography section.",
        input_latex=TEST_DOC_BIB,
        expected_scope=ScopeType.TARGETED_EDIT.value,
        validation_type="insert_bib",
        expected_contains=[r"\bibitem{smith2024}"],
    ),
    EvalCase(
        case_id="BIB-02",
        category="Bug 2 (Insert Into Chunk)",
        prompt="Add Vaswani et al. Attention is all you need to references.",
        input_latex=TEST_DOC_BIB,
        expected_scope=ScopeType.TARGETED_EDIT.value,
        validation_type="insert_bib",
        expected_contains=[r"\bibitem{vaswani17}"],
    ),
    EvalCase(
        case_id="BIB-03",
        category="Bug 2 (Insert Into Chunk)",
        prompt="Add a new bullet point to the highlights list.",
        input_latex=TEST_DOC_LIST,
        expected_scope=ScopeType.TARGETED_EDIT.value,
        validation_type="insert_list",
        expected_contains=[r"\item Point two."],
    ),
    EvalCase(
        case_id="BIB-04",
        category="Bug 2 (Insert Into Chunk)",
        prompt="Append Lamport 1994 LaTeX manual to bibliography.",
        input_latex=TEST_DOC_BIB,
        expected_scope=ScopeType.TARGETED_EDIT.value,
        validation_type="insert_bib",
        expected_contains=[r"\bibitem{lamport94}"],
    ),

    # --- Category C: Attached Reference File Persistence (Bug 3) ---
    EvalCase(
        case_id="ATT-01",
        category="Bug 3 (Attached Context)",
        prompt="Extract the database benchmark table from the attached paper.",
        input_latex=TEST_DOC_MULTI_CHAPTER,
        expected_scope=ScopeType.TARGETED_EDIT.value,
        attached_file={
            "filename": "benchmarks.pdf",
            "file_type": "pdf",
            "content": "Benchmark: Postgres latency 12ms, MySQL latency 18ms.",
        },
        validation_type="attachment",
    ),
    EvalCase(
        case_id="ATT-02",
        category="Bug 3 (Attached Context - Follow-up)",
        prompt="Now also include the MySQL throughput numbers from the previously attached paper.",
        input_latex=TEST_DOC_MULTI_CHAPTER,
        expected_scope=ScopeType.TARGETED_EDIT.value,
        attached_file=None,  # Follow up turn without resending file
        validation_type="attachment",
    ),
    EvalCase(
        case_id="ATT-03",
        category="Bug 3 (Attached Context)",
        prompt="Search the attached reference file for neural network hyperparameters.",
        input_latex=TEST_DOC_MULTI_CHAPTER,
        expected_scope=ScopeType.TARGETED_EDIT.value,
        attached_file={
            "filename": "hyperparams.pdf",
            "file_type": "pdf",
            "content": "Learning rate: 0.001, Batch size: 64, Optimizer: AdamW.",
        },
        validation_type="attachment",
    ),

    # --- Category D: Regression Tests (Targeted / Rewrite / Creation) ---
    EvalCase(
        case_id="REG-01",
        category="Regression (Targeted)",
        prompt="Fix the typo in section 1: change 'teh' to 'the'.",
        input_latex=TEST_DOC_MULTI_CHAPTER,
        expected_scope=ScopeType.TARGETED_EDIT.value,
        validation_type="scope",
    ),
    EvalCase(
        case_id="REG-02",
        category="Regression (Targeted)",
        prompt="Change the author name on the title page to Jane Doe.",
        input_latex=TEST_DOC_MULTI_CHAPTER,
        expected_scope=ScopeType.TARGETED_EDIT.value,
        validation_type="scope",
    ),
    EvalCase(
        case_id="REG-03",
        category="Regression (Full Rewrite)",
        prompt="Rewrite the entire document from scratch to be about Quantum Computing instead of Machine Learning.",
        input_latex=TEST_DOC_MULTI_CHAPTER,
        expected_scope=ScopeType.FULL_DOCUMENT_REWRITE.value,
        validation_type="scope",
    ),
    EvalCase(
        case_id="REG-04",
        category="Regression (Full Rewrite)",
        prompt="Replace all content and chapters with this new source material.",
        input_latex=TEST_DOC_MULTI_CHAPTER,
        expected_scope=ScopeType.FULL_DOCUMENT_REWRITE.value,
        validation_type="scope",
    ),
    EvalCase(
        case_id="REG-05",
        category="Regression (Creation)",
        prompt="Create a 10-slide Beamer presentation on Transformer architectures from scratch.",
        input_latex="",
        expected_scope=ScopeType.TARGETED_EDIT.value,
        validation_type="scope",
    ),
    EvalCase(
        case_id="REG-06",
        category="Regression (Creation)",
        prompt="Draft a research paper for IEEE conference about edge AI.",
        input_latex="",
        expected_scope=ScopeType.TARGETED_EDIT.value,
        validation_type="scope",
    ),
]


@pytest.mark.parametrize("eval_case", EVAL_PROMPTS, ids=[c.case_id for c in EVAL_PROMPTS])
def test_eval_case_execution(eval_case: EvalCase):
    """Executes a single evaluation prompt fixture and validates assertions."""
    # 1. Scope classification check
    result = classify_scope(eval_case.prompt, current_code=eval_case.input_latex)
    assert result.scope == eval_case.expected_scope, (
        f"[{eval_case.case_id}] Expected scope {eval_case.expected_scope}, got {result.scope} for prompt: '{eval_case.prompt}'"
    )

    # 2. Category-specific functional validations
    if eval_case.validation_type == "insert_bib":
        ws = ShadowWorkspace(eval_case.input_latex, project_id=eval_case.case_id)
        citation = eval_case.expected_contains[0] if eval_case.expected_contains else r"\bibitem{ref1} Author, 2024."
        res = ws.insert_into_chunk("section_2", citation, position="end")
        assert res["success"] is True
        buf = ws.get_buffer()
        assert citation in buf
        assert buf.find(citation) < buf.find(r"\end{thebibliography}"), "Citation must be before \\end{thebibliography}"

    elif eval_case.validation_type == "insert_list":
        ws = ShadowWorkspace(eval_case.input_latex, project_id=eval_case.case_id)
        item = eval_case.expected_contains[0] if eval_case.expected_contains else r"\item New point."
        res = ws.insert_into_chunk("section_1", item, position="end")
        assert res["success"] is True
        buf = ws.get_buffer()
        assert item in buf
        assert buf.find(item) < buf.find(r"\end{itemize}"), "Item must be before \\end{itemize}"

    elif eval_case.validation_type == "coverage":
        ws = ShadowWorkspace(eval_case.input_latex, project_id=eval_case.case_id)
        # Verify incomplete coverage fails
        ws.insert_into_chunk("chapter_1", "Expanded intro.")
        cov_res = validate_coverage(ws, eval_case.prompt, scope=result.scope)
        assert cov_res.passed is False
        assert len(cov_res.missing_chunk_ids) > 0

        # Verify full coverage passes
        ws.insert_into_chunk("chapter_2", "Expanded arch.")
        ws.insert_into_chunk("chapter_3", "Expanded results.")
        cov_full = validate_coverage(ws, eval_case.prompt, scope=result.scope)
        assert cov_full.passed is True

    elif eval_case.validation_type == "attachment":
        session_id = f"eval-sess-{eval_case.case_id}"
        if eval_case.attached_file:
            attached_context_store.store_attachment(session_id, eval_case.attached_file)
            attachments = attached_context_store.get_attachments(session_id)
            assert len(attachments) >= 1
            assert eval_case.attached_file["filename"] in [a["filename"] for a in attachments]
        elif eval_case.case_id == "ATT-02":
            # Test retrieval from earlier stored file in ATT-01
            prior_session = "eval-sess-ATT-01"
            attachments = attached_context_store.get_attachments(prior_session)
            assert len(attachments) >= 1
            assert "Postgres latency" in attachments[0]["content"]


def run_standalone_eval():
    """Runs all 18 eval cases and prints a structured summary table."""
    print("=" * 70)
    print("OverBranch Evaluation Suite — 18 Benchmark Cases")
    print("=" * 70)

    passed = 0
    failed = 0
    start_time = time.time()

    for case in EVAL_PROMPTS:
        t0 = time.time()
        try:
            test_eval_case_execution(case)
            elapsed = (time.time() - t0) * 1000
            print(f"  [PASS] {case.case_id} ({case.category:<25}) in {elapsed:.1f}ms: \"{case.prompt[:45]}...\"")
            passed += 1
        except AssertionError as e:
            elapsed = (time.time() - t0) * 1000
            print(f"  [FAIL] {case.case_id} ({case.category:<25}) in {elapsed:.1f}ms: {e}")
            failed += 1

    total_time = time.time() - start_time
    print("=" * 70)
    print(f"Results: {passed}/{len(EVAL_PROMPTS)} passed, {failed} failed in {total_time:.2f}s (Success rate: {(passed/len(EVAL_PROMPTS))*100:.1f}%)")
    print("=" * 70)
    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_standalone_eval()
    sys.exit(0 if success else 1)
