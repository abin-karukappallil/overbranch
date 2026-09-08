"""
test_adaptive_pipeline.py — Comprehensive Test Suite for Adaptive Pipeline

Tests:
1. Governor AIMD behavior, concurrency growth, multiplicative shrinkage, 502 circuit breaker, and failover.
2. Global Environment Ledger correctness, cross-section span detection, isolated-edit safety check, prompt facts block.
3. Self-healing loop: localized targeted retry on localizable compiler/validation error vs full-doc repair escalation.
4. Strict scope-lock enforcement, shared label/ref dependency detection, ScopeViolationError rejection.
5. Zero accuracy regression: triage + parallel dispatch retains full ungated context for all flagged sections.
"""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.environment_ledger import (
    EnvironmentLedger,
    OpenEnvironmentSpan,
    get_environment_ledger,
)
from backend.provider_governor import (
    AdaptiveProviderGovernor,
    call_provider_governed,
    CircuitOpenError,
    EmptyResponseError,
    GOVERNORS,
    get_governor,
)
from backend.document_index import (
    DocumentIndex,
    PageEntry,
    parse_document_structure,
    resolve_all_targets,
)
from backend.edit_validator import (
    validate_edit,
    validate_environment_ledger,
    enforce_scope_lock,
    allowed_dependency_pages,
    ScopeViolationError,
)
from backend.agent import (
    apply_diff,
    extract_line_number,
    apply_edit_with_self_healing,
    SelfHealResult,
    TRIAGE_SKIP_CONFIDENCE_THRESHOLD,
)
from backend.compiler import CompileTestResult
import backend.prompt_builder as prompt_builder


# ============================================================================
# 1. Governor AIMD & Circuit Breaker Tests
# ============================================================================

def test_governor_aimd_growth_and_shrinkage():
    """Test additive increase on 5 consecutive successes and multiplicative decrease on 502/rate-limits."""
    async def _run():
        gov = AdaptiveProviderGovernor("test_gemini", min_concurrency=1, max_concurrency=5)
        assert gov.current_limit == 1

        # 4 consecutive successes -> still 1
        for _ in range(4):
            await gov.report_result(success=True)
        assert gov.current_limit == 1

        # 5th success -> grows by 1 to 2
        await gov.report_result(success=True)
        assert gov.current_limit == 2

        # 5 more successes -> grows to 3
        for _ in range(5):
            await gov.report_result(success=True)
        assert gov.current_limit == 3

        # 502 Gateway Error -> Multiplicative decrease by 0.5 (3 * 0.5 = 1.5 -> int 1)
        await gov.report_result(success=False, error_type="gateway_502")
        assert gov.current_limit == 1
        assert gov._consecutive_successes == 0

    asyncio.run(_run())


def test_governor_circuit_breaker_trip_and_failover():
    """Test circuit breaker trips after repeated 502s and calls raise CircuitOpenError."""
    async def _run():
        gov = AdaptiveProviderGovernor("test_flaky", min_concurrency=1, max_concurrency=4)

        # Report multiple 502s
        for _ in range(4):
            await gov.report_result(success=False, error_type="gateway_502")

        assert gov._circuit_open_until is not None
        assert gov._circuit_open_until > time.time()

        # Subsequent acquire should raise CircuitOpenError immediately without waiting
        with pytest.raises(CircuitOpenError):
            await gov.acquire()

    asyncio.run(_run())


def test_call_provider_governed_automatic_fallback():
    """Test call_provider_governed automatically falls over when primary provider circuit is open."""
    async def _run():
        primary_gov = get_governor("gemini_test_trip")
        primary_gov._circuit_open_until = time.time() + 60  # Force open

        mock_chat_response = {
            "content": '{"action": "replace", "proposed_chunk": "\\section{Intro}"}',
            "model_used": "groq/llama-3",
            "is_fallback": True,
        }

        with patch("backend.provider_governor.provider_router.route") as mock_route, \
             patch("backend.provider_governor.FALLBACK_CHAIN", {"gemini_test_trip": "groq_test_fb"}), \
             patch("backend.provider_governor.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:

            mock_thread.return_value = mock_chat_response
            mock_provider = MagicMock()
            mock_provider.chat.return_value = mock_chat_response
            mock_route.return_value = mock_provider

            res = await call_provider_governed(
                provider_name="gemini_test_trip",
                messages=[{"role": "user", "content": "hello"}],
            )

            assert res["model_used"] == "groq/llama-3"

    asyncio.run(_run())


# ============================================================================
# 2. Environment Ledger Correctness Tests
# ============================================================================

SAMPLE_ARTICLE_LATEX = r"""\documentclass{article}
\usepackage{amsmath}
\begin{document}
\section{Introduction}
This is the introduction.
\section{Methodology}
\begin{equation}
E = mc^2
\end{equation}
\section{Appendix: Supplementary Material}
Final section content.
\end{document}
"""

def test_environment_ledger_detection_and_safety():
    """Test ledger tracks \begin{document} across preamble and last section and marks intermediate pages unsafe for isolated edit."""
    doc_idx = parse_document_structure(SAMPLE_ARTICLE_LATEX)
    ledger = get_environment_ledger(SAMPLE_ARTICLE_LATEX, doc_idx)

    doc_span = ledger.get_document_span()
    assert doc_span is not None
    assert doc_span.env_name == "document"
    assert doc_span.spans_multiple_sections is True

    # Preamble contains \begin{document} which closes in appendix
    preamble_page = doc_idx.pages[0]
    safe, reason = ledger.is_page_safe_for_isolated_edit(preamble_page.page_id)
    assert safe is False
    assert "document" in reason

    # Introduction is inside the spanning document
    intro_page = doc_idx.pages[1]
    safe_intro, reason_intro = ledger.is_page_safe_for_isolated_edit(intro_page.page_id)
    assert safe_intro is False

    # Check generated prompt facts block
    facts = ledger.generate_prompt_facts_block(intro_page.page_id)
    assert "DOCUMENT STRUCTURE FACTS" in facts
    assert "NOT the final section" in facts
    assert "Do NOT emit \\end{document}" in facts


def test_validator_rejects_premature_end_document_via_ledger():
    """Test edit_validator rejects an edit where a non-final section attempts to emit \\end{document}."""
    doc_idx = parse_document_structure(SAMPLE_ARTICLE_LATEX)
    ledger = get_environment_ledger(SAMPLE_ARTICLE_LATEX, doc_idx)

    intro_page = doc_idx.pages[1]

    # Edit proposing to put \end{document} in the introduction section
    illegal_edit = [{
        "action": "replace",
        "target_page_id": intro_page.page_id,
        "original_chunk": intro_page.content,
        "proposed_chunk": f"{intro_page.content}\n\\end{{document}}",
    }]

    validation = validate_edit(
        original_code=SAMPLE_ARTICLE_LATEX,
        proposed_edits=illegal_edit,
        doc_idx=doc_idx,
        ledger=ledger,
    )

    assert validation.passed is False
    err_checks = [i.check for i in validation.issues]
    assert "environment_ledger_boundary_violation" in err_checks


# ============================================================================
# 3. Self-Healing Loop Tests
# ============================================================================

def test_self_healing_localizable_error():
    """Test localized compilation failure triggers exactly 1 scoped retry and succeeds."""
    async def _run():
        broken_latex = r"""\documentclass{article}
\begin{document}
\section{Introduction}
\begin{badenvironment}
Broken content
\end{badenvironment}
\end{document}
"""
        doc_idx = parse_document_structure(broken_latex)
        ledger = get_environment_ledger(broken_latex, doc_idx)

        proposed_edits = [{
            "action": "replace",
            "original_chunk": "\\section{Introduction}\n...",
            "proposed_chunk": "\\section{Introduction}\n\\begin{badenvironment}\nBroken content\n\\end{badenvironment}",
        }]

        # Mock compiler: fails on attempt 1 (error on line 4), succeeds on attempt 2
        mock_compiler_results = [
            CompileTestResult(success=False, error_log="! LaTeX Error: Environment badenvironment undefined.\nl.4 \\begin{badenvironment}"),
            CompileTestResult(success=True, log="Compilation successful"),
        ]

        fixed_llm_resp = {
            "content": '{"action": "replace", "proposed_chunk": "\\\\section{Introduction}\\n\\\\textbf{Clean fixed content}", "explanation": "Fixed badenvironment"}',
        }

        with patch("backend.agent.test_compile", side_effect=mock_compiler_results), \
             patch("backend.agent.call_provider_governed", new_callable=AsyncMock, return_value=fixed_llm_resp) as mock_llm_call:

            result = await apply_edit_with_self_healing(
                proposed_edits=proposed_edits,
                current_code=broken_latex,
                doc_idx=doc_idx,
                ledger=ledger,
                user_instruction="Fix introduction",
                preferred_provider_name="gemini_web2api",
            )

            assert result.success is True
            assert result.attempts == 2
            assert mock_llm_call.call_count == 1

            # Verify retry prompt was targeted with self-heal system prompt
            call_args = mock_llm_call.call_args[1]["messages"]
            system_msg = call_args[0]["content"]
            assert "self-healing engine" in system_msg.lower()

    asyncio.run(_run())


def test_self_healing_non_localizable_error_escalates():
    """Test non-localizable compilation error escalates to full document repair prompt."""
    async def _run():
        doc = SAMPLE_ARTICLE_LATEX
        doc_idx = parse_document_structure(doc)
        ledger = get_environment_ledger(doc, doc_idx)

        proposed_edits = [{
            "action": "replace",
            "original_chunk": "\\section{Introduction}",
            "proposed_chunk": "\\section{Introduction}",
        }]

        # Error without line number (global cross-section error)
        mock_compiler_results = [
            CompileTestResult(success=False, error_log="! Emergency stop: Cross-document environment delimiter mismatch"),
            CompileTestResult(success=True, log="Compilation successful"),
        ]

        fixed_llm_resp = {
            "content": '{"action": "replace_all", "proposed_chunk": "\\\\documentclass{article}\\n\\\\begin{document}\\n\\\\section{Intro}\\n\\\\end{document}", "explanation": "Repaired full document"}',
        }

        with patch("backend.agent.test_compile", side_effect=mock_compiler_results), \
             patch("backend.agent.call_provider_governed", new_callable=AsyncMock, return_value=fixed_llm_resp) as mock_llm_call:

            result = await apply_edit_with_self_healing(
                proposed_edits=proposed_edits,
                current_code=doc,
                doc_idx=doc_idx,
                ledger=ledger,
                user_instruction="Global fix",
                preferred_provider_name="gemini_web2api",
            )

            assert result.success is True
            assert result.attempts == 2
            call_args = mock_llm_call.call_args[1]["messages"]
            system_msg = call_args[0]["content"]
            assert "repair engine" in system_msg.lower()

    asyncio.run(_run())


# ============================================================================
# 4. Strict Scope-Lock Tests
# ============================================================================

FOUR_SLIDE_BEAMER = r"""\documentclass{beamer}
\begin{document}
\begin{frame}{Slide 1: Intro}
\label{slide:intro}
Intro content
\end{frame}
\begin{frame}{Slide 2: Method}
\label{slide:method}
Method content with \ref{slide:intro}
\end{frame}
\begin{frame}{Slide 3: Results}
\label{slide:results}
Results content
\end{frame}
\begin{frame}{Slide 4: Conclusion}
\label{slide:conclusion}
Conclusion content
\end{frame}
\end{document}
"""

def test_scope_lock_rejects_unrelated_section_modifications():
    """Test enforce_scope_lock raises ScopeViolationError when editing slide 2 also modifies slide 4."""
    doc_idx = parse_document_structure(FOUR_SLIDE_BEAMER)
    ledger = get_environment_ledger(FOUR_SLIDE_BEAMER, doc_idx)

    # In FOUR_SLIDE_BEAMER:
    # doc_idx.pages[0] is Preamble
    # doc_idx.pages[1] is Slide 1: Intro
    # doc_idx.pages[2] is Slide 2: Method
    # doc_idx.pages[3] is Slide 3: Results
    # doc_idx.pages[4] is Slide 4: Conclusion
    slide_2 = doc_idx.pages[2]  # Slide 2: Method
    slide_4 = doc_idx.pages[4]  # Slide 4: Conclusion

    # Edit touching both Slide 2 and Slide 4
    illegal_edits = [
        {
            "target_page_id": slide_2.page_id,
            "original_chunk": slide_2.content,
            "proposed_chunk": "\\begin{frame}{Slide 2: Method}\nUpdated method\n\\end{frame}",
        },
        {
            "target_page_id": slide_4.page_id,
            "original_chunk": slide_4.content,
            "proposed_chunk": "\\begin{frame}{Slide 4: Conclusion}\nAltered conclusion\n\\end{frame}",
        },
    ]

    with pytest.raises(ScopeViolationError) as exc_info:
        enforce_scope_lock(
            proposed_edit=illegal_edits,
            resolved_target_page_ids={slide_2.page_id},
            doc_idx=doc_idx,
            ledger=ledger,
        )

    assert slide_4.page_id in str(exc_info.value)


def test_scope_lock_allows_shared_ref_dependencies():
    r"""Test allowed_dependency_pages includes sections sharing \label and \ref with the target."""
    doc_idx = parse_document_structure(FOUR_SLIDE_BEAMER)
    ledger = get_environment_ledger(FOUR_SLIDE_BEAMER, doc_idx)

    slide_2 = doc_idx.pages[2]  # Slide 2 (references slide:intro)
    slide_1 = doc_idx.pages[1]  # Slide 1 (defines slide:intro)

    deps = allowed_dependency_pages({slide_2.page_id}, doc_idx, ledger)
    assert slide_1.page_id in deps


# ============================================================================
# 5. Zero Accuracy Regression: Triage & Full Context Verification
# ============================================================================

def test_triage_confidence_threshold_and_full_context_preservation():
    """
    Asserts that triage only skips sections when confidence_no_change >= 0.85,
    and any flagged section receives the full ungated document context and computed ledger facts.
    """
    # Build a 20-frame mock document
    frames = [r"\documentclass{beamer}", r"\begin{document}"]
    for i in range(1, 21):
        frames.append(f"\\begin{{frame}}{{Slide {i}: Topic {i}}}\nContent for slide {i}\n\\end{{frame}}")
    frames.append(r"\end{document}")
    big_doc = "\n".join(frames)

    doc_idx = parse_document_structure(big_doc)
    ledger = get_environment_ledger(big_doc, doc_idx)

    all_targets = resolve_all_targets(doc_idx, include_preamble=False)
    assert len(all_targets) == 20

    # Simulate triage classification:
    # Target 2, 5, 12 need edit; Target 8 has ambiguous confidence 0.70 (< 0.85 threshold) -> included
    # Targets with confidence >= 0.85 -> skipped
    for idx, t in enumerate(all_targets):
        if idx in (1, 4, 11):  # Slide 2, 5, 12
            t.needs_edit = True
            t.confidence_no_change = 0.05
        elif idx == 7:  # Slide 8 (ambiguous)
            t.needs_edit = False
            t.confidence_no_change = 0.70
        else:
            t.needs_edit = False
            t.confidence_no_change = 0.95

    # Filter with TRIAGE_SKIP_CONFIDENCE_THRESHOLD = 0.85
    targets_to_process = [
        t for t in all_targets
        if getattr(t, "needs_edit", True) or getattr(t, "confidence_no_change", 0.0) < TRIAGE_SKIP_CONFIDENCE_THRESHOLD
    ]

    # Exactly the 3 edit targets + 1 ambiguous target should be processed
    assert len(targets_to_process) == 4
    processed_titles = [t.title for t in targets_to_process]
    assert "Slide 2: Topic 2" in processed_titles
    assert "Slide 5: Topic 5" in processed_titles
    assert "Slide 12: Topic 12" in processed_titles
    assert "Slide 8: Topic 8" in processed_titles

    # Verify that prompt building for any of these targets contains FULL ungated document context + ledger facts
    sample_target = targets_to_process[0]
    facts = ledger.generate_prompt_facts_block(sample_target.page_id)
    prompt_msgs = prompt_builder.build_broad_edit_prompt(
        user_request="Update topic 2",
        page_id=sample_target.page_id,
        page_title=sample_target.title,
        page_content=sample_target.content,
        page_index=0,
        total_targets=len(targets_to_process),
        full_document=big_doc,
        ledger_facts=facts,
    )

    user_prompt_text = prompt_msgs[1].content
    # Full document is included
    assert "COMPLETE FULL DOCUMENT" in user_prompt_text
    assert "Slide 20: Topic 20" in user_prompt_text
    # Ledger facts are included
    assert "DOCUMENT STRUCTURE FACTS" in user_prompt_text
    assert "Do NOT emit \\end{document}" in user_prompt_text
