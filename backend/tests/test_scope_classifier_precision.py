"""
test_scope_classifier_precision.py — scope inflation guards.

Misclassifying a targeted request as a document-wide one is the single most
expensive mistake in the agent loop, and the most destructive. On a 15-chunk
deck, FULL_DOCUMENT_EXPANSION raises the step budget from 8 to 34 — 34 sequential
LLM round trips at ~14-16K input tokens each — *and* makes coverage validation
demand that every chunk be rewritten. So "expand the conclusion paragraph" used
to rewrite the user's entire presentation.

The trigger was EXPANSION_PATTERNS matching
``(?:expand|elaborate|explain)\\s+(?:this|the|...)``, checked before
TARGETED_PATTERNS and returning immediately (the LLM classifier is only a
fallback for ambiguous cases, so it never saw these).
"""

from __future__ import annotations

import pytest

from opencode.agent_loop import determine_adaptive_step_budget
from scope_classifier import ScopeType, classify_scope


def _deck(n: int = 15) -> str:
    frames = "\n".join(
        "\\begin{frame}{Topic %d}\n\\item point\n\\end{frame}" % i for i in range(n)
    )
    return (
        "\\documentclass{beamer}\n\\begin{document}\n" + frames + "\n\\end{document}"
    )


DECK = _deck()


def _scope(prompt: str, code: str = DECK) -> str:
    result = classify_scope(prompt, code)
    scope = getattr(result, "scope", result)
    return scope.value if hasattr(scope, "value") else str(scope)


# A specific, singular target — must never buy a document-wide budget.
TARGETED_PROMPTS = [
    "expand the conclusion paragraph",
    "explain this better",
    "elaborate this",
    "explain the method more",
    "expand this slide",
    "expand the introduction",
    "elaborate on this equation",
    "explain the abstract more clearly",
    "fix the typo on slide 3",
    "expand section 2",
    "make this sentence clearer",
    "elaborate the figure caption",
]


@pytest.mark.parametrize("prompt", TARGETED_PROMPTS)
def test_single_target_requests_stay_targeted(prompt):
    assert _scope(prompt) == ScopeType.TARGETED_EDIT.value, (
        f"{prompt!r} would inflate to a whole-document rewrite"
    )


# Genuinely document-wide language — must keep the full budget and coverage.
DOCUMENT_WIDE_PROMPTS = [
    ("expand every section", ScopeType.FULL_DOCUMENT_EXPANSION.value),
    ("expand all slides with more detail", ScopeType.FULL_DOCUMENT_EXPANSION.value),
    ("expand the entire document", ScopeType.FULL_DOCUMENT_EXPANSION.value),
    ("add more content to each section", ScopeType.FULL_DOCUMENT_EXPANSION.value),
    ("make the presentation longer", ScopeType.FULL_DOCUMENT_EXPANSION.value),
    ("elaborate each chapter", ScopeType.FULL_DOCUMENT_EXPANSION.value),
    ("rewrite everything about quantum computing", ScopeType.FULL_DOCUMENT_REWRITE.value),
    ("change the topic to machine learning", ScopeType.FULL_DOCUMENT_REWRITE.value),
]


@pytest.mark.parametrize("prompt,expected", DOCUMENT_WIDE_PROMPTS)
def test_document_wide_requests_keep_full_scope(prompt, expected):
    assert _scope(prompt) == expected, (
        f"{prompt!r} must remain document-wide — narrowing it would leave "
        f"most of the document untouched"
    )


def test_all_document_language_overrides_single_target_guard():
    """'every section' wins even though 'the introduction' looks singular."""
    assert _scope("expand the introduction and every section") == (
        ScopeType.FULL_DOCUMENT_EXPANSION.value
    )


# ---------------------------------------------------------------------------
# Step budget
# ---------------------------------------------------------------------------

def test_targeted_scope_gets_a_small_budget():
    lines = DECK.count("\n") + 1
    budget = determine_adaptive_step_budget(
        "expand the conclusion paragraph",
        lines,
        0,
        15,
        num_chunks=15,
        scope=ScopeType.TARGETED_EDIT.value,
        mode="edit",
        requested_steps=8,
    )
    assert budget == 8


def test_full_rewrite_keeps_enough_steps_to_cover_every_chunk():
    """
    Coverage validation requires every content chunk to be touched, so a genuine
    full rewrite must not be capped below that — otherwise the loop burns its
    budget and then fails coverage.
    """
    lines = DECK.count("\n") + 1
    budget = determine_adaptive_step_budget(
        "rewrite everything",
        lines,
        0,
        15,
        num_chunks=15,
        scope=ScopeType.FULL_DOCUMENT_REWRITE.value,
        mode="edit",
        requested_steps=8,
    )
    assert budget >= 15, "not enough steps to touch all 15 chunks"


def test_ask_mode_stays_cheap():
    budget = determine_adaptive_step_budget(
        "what does this document cover?",
        200,
        0,
        15,
        num_chunks=15,
        scope=ScopeType.TARGETED_EDIT.value,
        mode="ask",
    )
    assert budget <= 4
