"""
retriever.py — Structural & Vector Retriever with Full-Rewrite Bypass
=====================================================================
Retrieves relevant document chunks from DocumentIndex based on query and scope:
- TARGETED_EDIT: Returns top-k similarity-ranked subset of chunks matching the query.
- FULL_DOCUMENT_REWRITE: Completely bypasses top-k retrieval and returns the complete
  ordered list of all chunks (every chapter/section/frame in the document).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from document_index import DocumentChunk, DocumentIndex
from scope_classifier import ScopeType

logger = logging.getLogger("retriever")


def _score_chunk(chunk: DocumentChunk, query_terms: List[str]) -> float:
    """Computes a simple lexical relevance score between chunk and query terms."""
    if not query_terms:
        return 1.0

    score = 0.0
    content_lower = chunk.content.lower()
    title_lower = chunk.title.lower()

    for term in query_terms:
        t = term.lower().strip()
        if not t:
            continue
        # Title match has high weight
        if t in title_lower:
            score += 5.0
        # Content match
        count = content_lower.count(t)
        score += min(count * 0.5, 3.0)

    # Chunk type quality weights
    type_weights = {
        "chapter": 1.5,
        "section": 1.2,
        "frame": 1.2,
        "content": 1.0,
        "frontmatter": 0.5,
        "preamble": 0.3,
    }
    score *= type_weights.get(chunk.chunk_type, 1.0)
    return score


def retrieve_chunks(
    document_code: str,
    query: str,
    scope: str = ScopeType.TARGETED_EDIT.value,
    top_k: int = 5,
    include_preamble: bool = False,
) -> List[DocumentChunk]:
    """
    Retrieves document chunks according to scope.

    When scope is FULL_DOCUMENT_REWRITE:
      Bypasses semantic top-k filtering and returns the complete ordered list of all
      chunks in the document.

    When scope is TARGETED_EDIT:
      Returns the top-k highest scoring chunks matching the query.
    """
    doc_index = DocumentIndex()
    all_chunks = doc_index.get_chunks(document_code)

    if not all_chunks:
        return []

    # 1. FULL_DOCUMENT_REWRITE: Return all chunks in sequential order
    if scope == ScopeType.FULL_DOCUMENT_REWRITE.value or scope == "FULL_DOCUMENT_REWRITE":
        logger.info(f"Retriever: FULL_DOCUMENT_REWRITE mode active. Returning all {len(all_chunks)} chunks without top-k filtering.")
        if include_preamble:
            return all_chunks
        return [c for c in all_chunks if c.chunk_type != "preamble"]

    # 2. TARGETED_EDIT: Rank chunks and return top-k
    query_terms = [w for w in re.split(r"\s+", query) if len(w) > 2]
    candidate_chunks = [c for c in all_chunks if include_preamble or c.chunk_type != "preamble"]

    scored = [(c, _score_chunk(c, query_terms)) for c in candidate_chunks]
    scored.sort(key=lambda x: x[1], reverse=True)

    top_chunks = [c for c, s in scored[:top_k] if s > 0]
    if not top_chunks and candidate_chunks:
        # Fallback to first chunk if no query match
        top_chunks = candidate_chunks[:1]

    return top_chunks
