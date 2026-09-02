import logging
import math
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set

from chunker import CHUNK_TYPE_WEIGHTS

logger = logging.getLogger("retriever")

# Retrieval configuration
BROAD_SEARCH_LIMIT = 15       # Stage 1: fetch this many from Qdrant
DIVERSITY_SELECT_COUNT = 10   # Stage 3: MMR selects this many
FINAL_RESULT_COUNT = 5       # Stage 5: return top 5 embedding chunks (reduced for token budget)
OVERLAP_THRESHOLD = 0.70      # Stage 4: dedup if >70% content overlap
MMR_LAMBDA = 0.6              # MMR trade-off: relevance vs diversity

# Score weights for composite ranking
W_SEMANTIC = 0.55
W_RECENCY = 0.20
W_QUALITY = 0.15
W_FILE_RELEVANCE = 0.10


def _recency_score(last_modified: str) -> float:
    """Score 0..1 based on how recent the chunk is. More recent = higher."""
    try:
        mod_time = datetime.fromisoformat(last_modified.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age_hours = (now - mod_time).total_seconds() / 3600.0
        # Decay: score = 1.0 for <1h, 0.5 for ~24h, approaches 0 for very old
        return max(0.0, 1.0 / (1.0 + age_hours / 24.0))
    except Exception:
        return 0.5  # Default if parsing fails


def _chunk_quality_score(chunk_type: str) -> float:
    """Score based on chunk type — structural chunks are higher quality."""
    return CHUNK_TYPE_WEIGHTS.get(chunk_type, 0.5)


def _file_relevance_score(chunk_file: str, active_file: str) -> float:
    """Score 1.0 if chunk is from the currently edited file, 0.5 otherwise."""
    if not active_file:
        return 0.7
    return 1.0 if chunk_file == active_file else 0.5


def _compute_composite_score(
    semantic_score: float,
    chunk_type: str,
    last_modified: str,
    chunk_file: str,
    active_file: str,
    chunk_section: str = "",
    target_section: str = "",
    is_nearby: bool = False,
) -> float:
    """Compute weighted composite score for a retrieved chunk."""
    score = (
        W_SEMANTIC * semantic_score
        + W_RECENCY * _recency_score(last_modified)
        + W_QUALITY * _chunk_quality_score(chunk_type)
        + W_FILE_RELEVANCE * _file_relevance_score(chunk_file, active_file)
    )

    # Prioritize same section
    if target_section and chunk_section and target_section.lower() in chunk_section.lower():
        score += 0.15

    # Prioritize nearby chunks to top-scoring anchors
    if is_nearby:
        score += 0.10

    return score


def _jaccard_similarity(text_a: str, text_b: str) -> float:
    """Compute Jaccard token similarity between two texts."""
    tokens_a = set(text_a.lower().split())
    tokens_b = set(text_b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _content_overlap_ratio(text_a: str, text_b: str) -> float:
    """Check how much of text_a appears in text_b (substring containment)."""
    if not text_a or not text_b:
        return 0.0
    shorter = text_a if len(text_a) <= len(text_b) else text_b
    longer = text_b if len(text_a) <= len(text_b) else text_a
    # Check substring containment of words
    short_words = set(shorter.lower().split())
    long_words = set(longer.lower().split())
    if not short_words:
        return 0.0
    contained = short_words & long_words
    return len(contained) / len(short_words)


def stage1_broad_search(
    qdrant_client,
    collection_name: str,
    query_embedding: List[float],
    project_id: str,
    file_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Stage 1: Broad semantic search from Qdrant with metadata filtering."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    # Always filter by project_id
    must_conditions = [
        FieldCondition(key="project_id", match=MatchValue(value=project_id)),
    ]

    # Prefer chunks from the active file when provided (use 'should' so
    # cross-file results are still returned but scored lower by Qdrant)
    should_conditions = []
    if file_path:
        should_conditions.append(
            FieldCondition(key="file_path", match=MatchValue(value=file_path))
        )

    filter_cond = Filter(must=must_conditions, should=should_conditions if should_conditions else None)

    hits = []
    try:
        if hasattr(qdrant_client, "query_points"):
            res = qdrant_client.query_points(
                collection_name=collection_name,
                query=query_embedding,
                query_filter=filter_cond,
                limit=BROAD_SEARCH_LIMIT,
            )
            hits = getattr(res, "points", [])
        elif hasattr(qdrant_client, "search"):
            hits = qdrant_client.search(
                collection_name=collection_name,
                query_vector=query_embedding,
                query_filter=filter_cond,
                limit=BROAD_SEARCH_LIMIT,
            )
    except Exception as e:
        logger.warning(f"Stage 1 broad search failed: {e}")

    # Convert hits to dicts
    results = []
    for hit in hits:
        payload = hit.payload if hasattr(hit, "payload") and hit.payload else {}
        results.append({
            "content": payload.get("content", ""),
            "similarity": getattr(hit, "score", 0.0),
            "chunk_index": payload.get("chunk_index", 0),
            "chunk_type": payload.get("chunk_type", "paragraph"),
            "section": payload.get("section", ""),
            "approx_position": payload.get("approx_position", 0.0),
            "start_line": payload.get("start_line", 0),
            "end_line": payload.get("end_line", 0),
            "file_path": payload.get("file_path", ""),
            "summary": payload.get("summary", ""),
            "file_hash": payload.get("file_hash", ""),
            "last_modified": payload.get("last_modified", ""),
            "project_id": payload.get("project_id", ""),
        })

    logger.info(f"Stage 1: Retrieved {len(results)} raw hits from Qdrant")
    return results


def stage2_metadata_scoring(
    chunks: List[Dict[str, Any]],
    active_file: str,
    target_section: str = "",
) -> List[Dict[str, Any]]:
    """Stage 2: Re-score chunks using composite scoring (semantic + metadata + section/proximity)."""
    # Identify anchor chunk indices from top semantic matches
    anchor_indices = {c.get("chunk_index", 0) for c in chunks[:3]}
    nearby_indices = {i + offset for i in anchor_indices for offset in (-1, 1)}

    for chunk in chunks:
        c_idx = chunk.get("chunk_index", 0)
        chunk["composite_score"] = _compute_composite_score(
            semantic_score=chunk.get("similarity", 0.0),
            chunk_type=chunk.get("chunk_type", "paragraph"),
            last_modified=chunk.get("last_modified", ""),
            chunk_file=chunk.get("file_path", ""),
            active_file=active_file,
            chunk_section=chunk.get("section", ""),
            target_section=target_section,
            is_nearby=(c_idx in nearby_indices),
        )

    # Sort by composite score descending
    chunks.sort(key=lambda c: c["composite_score"], reverse=True)
    logger.info(f"Stage 2: Re-scored {len(chunks)} chunks by composite score")
    return chunks


def stage3_mmr_diversity(
    chunks: List[Dict[str, Any]],
    select_count: int = DIVERSITY_SELECT_COUNT,
) -> List[Dict[str, Any]]:
    """Stage 3: Maximal Marginal Relevance diversity selection."""
    if len(chunks) <= select_count:
        return chunks

    selected: List[Dict[str, Any]] = [chunks[0]]  # Always pick the top hit
    remaining = list(chunks[1:])

    while len(selected) < select_count and remaining:
        best_candidate = None
        best_mmr_score = -float("inf")

        for candidate in remaining:
            relevance = candidate["composite_score"]

            # Max similarity to any already-selected chunk
            max_sim = max(
                _jaccard_similarity(candidate["content"], sel["content"])
                for sel in selected
            )

            # MMR score: balance relevance vs redundancy
            mmr = MMR_LAMBDA * relevance - (1.0 - MMR_LAMBDA) * max_sim

            if mmr > best_mmr_score:
                best_mmr_score = mmr
                best_candidate = candidate

        if best_candidate:
            selected.append(best_candidate)
            remaining.remove(best_candidate)
        else:
            break

    logger.info(f"Stage 3: MMR selected {len(selected)} diverse chunks from {len(chunks)}")
    return selected


def stage4_dedup(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Stage 4: Remove chunks with >70% content overlap."""
    if len(chunks) <= 1:
        return chunks

    deduped = [chunks[0]]
    for candidate in chunks[1:]:
        is_dup = False
        for existing in deduped:
            if _content_overlap_ratio(candidate["content"], existing["content"]) > OVERLAP_THRESHOLD:
                is_dup = True
                break
        if not is_dup:
            deduped.append(candidate)

    removed = len(chunks) - len(deduped)
    if removed > 0:
        logger.info(f"Stage 4: Removed {removed} overlapping chunks")
    return deduped


def stage5_final_selection(
    chunks: List[Dict[str, Any]],
    max_results: int = FINAL_RESULT_COUNT,
) -> List[Dict[str, Any]]:
    """Stage 5: Return top N results sorted by composite score."""
    final = chunks[:max_results]
    logger.info(f"Stage 5: Final selection → {len(final)} chunks")
    return final


def retrieve(
    qdrant_client,
    collection_name: str,
    query_embedding: List[float],
    project_id: str,
    file_path: str = "",
    top_k: int = FINAL_RESULT_COUNT,
    target_section: str = "",
) -> List[Dict[str, Any]]:
    """
    Full multi-stage retrieval pipeline.

    Returns up to top_k diverse, high-quality, deduplicated chunks.
    """
    print(f"\n🔎 [QDRANT RETRIEVAL] Starting vector retrieval for project='{project_id}', file='{file_path}', top_k={top_k}")
    # Stage 1: Broad search
    raw_hits = stage1_broad_search(qdrant_client, collection_name, query_embedding, project_id, file_path)

    if not raw_hits:
        print("  ⚠️  [QDRANT RETRIEVAL] Stage 1 returned 0 hits.")
        return []

    print(f"  ► Stage 1 (Broad Search): Retrieved {len(raw_hits)} raw vector hits")

    # Stage 2: Metadata-boosted scoring
    scored = stage2_metadata_scoring(raw_hits, active_file=file_path, target_section=target_section)
    print(f"  ► Stage 2 (Composite Scoring): Scored {len(scored)} candidates")

    # Stage 3: MMR diversity selection
    diverse = stage3_mmr_diversity(scored, select_count=max(top_k * 2, DIVERSITY_SELECT_COUNT))
    print(f"  ► Stage 3 (MMR Diversity): Selected {len(diverse)} diverse candidates")

    # Stage 4: Overlap deduplication
    deduped = stage4_dedup(diverse)
    print(f"  ► Stage 4 (Overlap Dedup): Retained {len(deduped)} deduplicated candidates")

    # Stage 5: Final selection
    final = stage5_final_selection(deduped, max_results=top_k)
    print(f"  ✅ [QDRANT RETRIEVAL COMPLETE] Returning top {len(final)} chunks for context builder\n")

    return final
