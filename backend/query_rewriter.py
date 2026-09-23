"""
query_rewriter.py — Fast Multi-Query Expansion for LaTeX Retrieval
==================================================================
Expands user instructions into targeted search queries for RAG retrieval.
Aware of edit scope: bypasses or expands to all sections in FULL_DOCUMENT_REWRITE mode.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from scope_classifier import ScopeType

logger = logging.getLogger("query_rewriter")


def _heuristic_expand(instruction: str) -> List[str]:
    """Generates 1-3 technical search terms from user instruction."""
    cleaned = re.sub(r"[^\w\s]", " ", instruction).strip()
    words = cleaned.split()
    queries = [instruction]

    # Look for LaTeX keywords
    latex_keywords = [
        "section", "chapter", "table", "figure", "equation", "align",
        "itemize", "enumerate", "abstract", "bibliography", "title", "author"
    ]
    found_kw = [w.lower() for w in words if w.lower() in latex_keywords]
    if found_kw:
        queries.append(" ".join(found_kw))

    # Add significant content words
    content_words = [w for w in words if len(w) > 3 and w.lower() not in ("please", "would", "could", "should", "change", "update", "make")]
    if content_words:
        queries.append(" ".join(content_words[:5]))

    return list(dict.fromkeys(queries))[:3]


def rewrite_query(
    user_instruction: str,
    scope: str = ScopeType.TARGETED_EDIT.value,
    model: Optional[str] = None,
    api_keys: Optional[Dict[str, str]] = None,
) -> List[str]:
    """
    Expands conversational user prompts into technical search queries.
    When scope is FULL_DOCUMENT_REWRITE, returns full-coverage queries.
    """
    if scope == ScopeType.FULL_DOCUMENT_REWRITE.value or scope == "FULL_DOCUMENT_REWRITE":
        return [user_instruction, "all chapters sections", "entire document"]

    return _heuristic_expand(user_instruction)
