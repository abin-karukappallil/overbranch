"""
test_multi_target_insertion_mapping.py — Comprehensive tests for Many-to-Many Content Insertion

Tests:
1. Narrow case: 4 source chunks all matching 1 section -> 1 destination key, 1 merged provider call.
2. Broad case: 12 source chunks across 8 distinct sections -> 8 destination keys, parallel dispatch with overlapping timestamps.
3. Full-breadth case: Content relevant to all 17 mock sections -> all 17 discovered and dispatched in parallel in governed batch time, not 17x.
4. Unmatched content: Low-confidence / unmatched chunks routed to propose_new_section_placement.
5. Merge correctness: 3 source chunks for the same destination page merged into 1 LLM call with combined text.
"""

import time
import asyncio
import pytest
from dataclasses import dataclass
from typing import List, Dict, Any

from content_mapper import (
    SourceChunk,
    MatchedInsertion,
    chunk_source_content,
    map_source_chunks_to_destinations,
    execute_mapped_insertions,
    propose_new_section_placement,
)
from document_index import DocumentIndex, PageEntry
from environment_ledger import EnvironmentLedger


# ---------------------------------------------------------------------------
# Test Fixtures & Helpers
# ---------------------------------------------------------------------------

class MockHit:
    def __init__(self, page_id: str, score: float):
        self.payload = {"page_id": page_id}
        self.score = score


class MockEmbeddingsModel:
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # Returns simple 2D dummy vector for each text
        return [[float(i), float(len(t))] for i, t in enumerate(texts)]


def build_mock_doc_index(num_pages: int = 17) -> DocumentIndex:
    pages = []
    # Preamble
    pages.append(PageEntry(
        page_id="preamble",
        page_index=0,
        page_type="preamble",
        title="Preamble",
        start_offset=0,
        end_offset=50,
        content="\\documentclass{article}\n\\begin{document}\n",
    ))
    # Body sections
    offset = 50
    for i in range(1, num_pages + 1):
        content = f"\\section{{Section {i}}}\nContent for section {i}.\n\n"
        end_offset = offset + len(content)
        pages.append(PageEntry(
            page_id=f"page_{i}",
            page_index=i,
            page_type="section",
            title=f"Section {i}",
            start_offset=offset,
            end_offset=end_offset,
            content=content,
        ))
        offset = end_offset

    doc = DocumentIndex(
        pages=pages,
        doc_type="article",
        has_preamble=True,
        total_sections=num_pages,
    )
    return doc


# ---------------------------------------------------------------------------
# 1. Narrow Case Test
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_narrow_case_single_destination_merged():
    """
    Narrow case: single-topic source PDF chunked into 4 pieces, all matching
    one existing section -> destination_map has exactly 1 key, and exactly 1
    provider call is made (chunks merged, not called separately).
    """
    # 4 chunks on the same topic (e.g. Introduction details)
    source_chunks = [
        SourceChunk(id=f"chunk_{i}", text=f"Introduction paragraph {i} details...", approx_topic_heading="Introduction")
        for i in range(1, 5)
    ]

    # Mock Qdrant that routes all 4 chunks to "page_1" (e.g. Introduction section)
    class SingleDestQdrant:
        def search(self, collection_name, query_vector, query_filter, limit):
            return [MockHit(page_id="page_1", score=0.92)]

    doc_idx = build_mock_doc_index(num_pages=5)

    dest_map, unmatched = await map_source_chunks_to_destinations(
        source_chunks=source_chunks,
        qdrant_client=SingleDestQdrant(),
        project_id="test_proj",
        min_similarity=0.55,
        embeddings_model=MockEmbeddingsModel(),
        doc_idx=doc_idx,
    )

    # Assert destination_map has exactly 1 key
    assert len(dest_map) == 1
    assert "page_1" in dest_map
    # All 4 chunks mapped to this key
    assert len(dest_map["page_1"]) == 4
    assert len(unmatched) == 0

    # Execute mapped insertions and assert exactly 1 provider call was made
    provider_calls = []

    async def mock_call_provider(prov, prompt_msgs, model="", api_keys=None):
        provider_calls.append(prompt_msgs)
        # Return valid JSON edit
        return {
            "original_chunk": "Content for section 1.",
            "proposed_chunk": "Content for section 1 with 4 paragraphs merged.",
            "explanation": "Integrated 4 paragraphs into section 1",
        }

    async def mock_self_heal(edit, doc_state, doc_index, ledger):
        return {"success": True, "edits": [edit]}

    @dataclass
    class MockReq:
        current_code: str = "\\documentclass{article}\n\\begin{document}\n\\section{Section 1}\nContent for section 1.\n\\end{document}"
        user_prompt: str = "Add these contents from the PDF"
        project_id: str = "test_proj"

    results = await execute_mapped_insertions(
        destination_map=dest_map,
        req=MockReq(),
        doc_state=MockReq(),
        doc_idx=doc_idx,
        ledger=None,
        call_provider_fn=mock_call_provider,
        self_heal_fn=mock_self_heal,
    )

    # Exactly 1 provider call made despite 4 source chunks
    assert len(provider_calls) == 1
    assert len(results) == 1

    # Verify that all 4 chunk texts were merged into the single prompt
    prompt_text = "\n".join(str(m.content) for m in provider_calls[0])
    for i in range(1, 5):
        assert f"Introduction paragraph {i} details..." in prompt_text


# ---------------------------------------------------------------------------
# 2. Broad Case Test (Parallel Overlap)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_broad_case_parallel_overlap():
    """
    Broad case: multi-topic source PDF chunked into 12 pieces spread across
    8 distinct existing sections by design -> destination_map has exactly 8 keys,
    and all 8 edit calls are dispatched via asyncio.gather (asserting on call
    timestamps that they overlap, proving parallelism, not sequential execution).
    """
    # 12 chunks: chunks 0-7 map to pages 1-8 (1 each), chunks 8-11 map to pages 1-4
    source_chunks = [
        SourceChunk(id=f"c_{i}", text=f"Topic content {i}", approx_topic_heading=f"Topic {i}")
        for i in range(12)
    ]

    class BroadQdrant:
        def __init__(self):
            self.call_idx = 0

        def search(self, collection_name, query_vector, query_filter, limit):
            # Map index % 8 to page_{1..8}
            dest_page = f"page_{(self.call_idx % 8) + 1}"
            self.call_idx += 1
            return [MockHit(page_id=dest_page, score=0.88)]

    doc_idx = build_mock_doc_index(num_pages=10)

    dest_map, unmatched = await map_source_chunks_to_destinations(
        source_chunks=source_chunks,
        qdrant_client=BroadQdrant(),
        project_id="test_proj",
        min_similarity=0.55,
        embeddings_model=MockEmbeddingsModel(),
        doc_idx=doc_idx,
    )

    # Exactly 8 distinct sections discovered
    assert len(dest_map) == 8
    assert len(unmatched) == 0

    # Track timing of each call to verify concurrent execution
    call_intervals = []

    async def mock_timed_provider(prov, prompt_msgs, model="", api_keys=None):
        start = time.time()
        await asyncio.sleep(0.08)  # simulate network/LLM latency
        end = time.time()
        call_intervals.append((start, end))
        return {"edits": [{"proposed_chunk": "updated", "original_chunk": "orig"}]}

    async def mock_self_heal(edit, doc_state, doc_index, ledger):
        return {"success": True, "edits": edit.get("edits", [])}

    @dataclass
    class MockReq:
        current_code: str = "doc code"
        user_prompt: str = "Add content from PDF"
        project_id: str = "test_proj"

    t0 = time.time()
    results = await execute_mapped_insertions(
        destination_map=dest_map,
        req=MockReq(),
        doc_state=MockReq(),
        doc_idx=doc_idx,
        ledger=None,
        call_provider_fn=mock_timed_provider,
        self_heal_fn=mock_self_heal,
    )
    total_elapsed = time.time() - t0

    # 8 calls made
    assert len(results) == 8
    assert len(call_intervals) == 8

    # Check timestamp overlap: if sequential, 8 * 0.08 = 0.64s.
    # In parallel, all 8 execute concurrently, so total time is < 0.3s.
    assert total_elapsed < 0.35, f"Expected parallel execution (< 0.35s), took {total_elapsed:.3f}s"

    # Verify that first start is before last start and calls overlapped
    first_start = min(s for s, e in call_intervals)
    last_start = max(s for s, e in call_intervals)
    first_end = min(e for s, e in call_intervals)
    assert last_start < first_end + 0.05, "Calls did not execute concurrently in parallel!"


# ---------------------------------------------------------------------------
# 3. Full-Breadth Case Test (17 Mock Sections)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_full_breadth_17_sections_governed_parallel():
    """
    Full-breadth case: source content deliberately relevant to all 17 mock sections ->
    assert all 17 are discovered and dispatched in parallel, and that wall-clock time
    in the test is close to one governed batch's latency, not 17x it.
    """
    num_sections = 17
    source_chunks = [
        SourceChunk(id=f"c_{i}", text=f"Update for section {i+1}", approx_topic_heading=f"Topic {i+1}")
        for i in range(num_sections)
    ]

    class FullBreadthQdrant:
        def __init__(self):
            self.call_count = 0

        def search(self, collection_name, query_vector, query_filter, limit):
            p_id = f"page_{self.call_count + 1}"
            self.call_count += 1
            return [MockHit(page_id=p_id, score=0.85)]

    doc_idx = build_mock_doc_index(num_pages=num_sections)

    dest_map, unmatched = await map_source_chunks_to_destinations(
        source_chunks=source_chunks,
        qdrant_client=FullBreadthQdrant(),
        project_id="test_proj",
        min_similarity=0.55,
        embeddings_model=MockEmbeddingsModel(),
        doc_idx=doc_idx,
    )

    # All 17 sections discovered
    assert len(dest_map) == 17
    assert len(unmatched) == 0

    call_count = 0

    async def mock_concurrency_call(prov, prompt_msgs, model="", api_keys=None):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.06)  # 60ms simulated latency
        return {"edits": [{"proposed_chunk": "new", "original_chunk": "old"}]}

    async def mock_self_heal(edit, doc_state, doc_index, ledger):
        return {"success": True, "edits": edit.get("edits", [])}

    @dataclass
    class MockReq:
        current_code: str = "doc code"
        user_prompt: str = "Update all sections from broad PDF"
        project_id: str = "test_proj"

    t0 = time.time()
    results = await execute_mapped_insertions(
        destination_map=dest_map,
        req=MockReq(),
        doc_state=MockReq(),
        doc_idx=doc_idx,
        ledger=None,
        call_provider_fn=mock_concurrency_call,
        self_heal_fn=mock_self_heal,
    )
    elapsed = time.time() - t0

    assert len(results) == 17
    assert call_count == 17

    # If sequential, 17 * 0.06 = 1.02s.
    # In parallel, it should complete well under 0.35s (close to single-batch latency).
    assert elapsed < 0.40, f"Expected full-breadth parallel completion (< 0.40s), took {elapsed:.3f}s"


# ---------------------------------------------------------------------------
# 4. Unmatched Content Routing Test
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_unmatched_content_proposes_new_section():
    """
    Unmatched content: a source chunk with no confident match to any section
    (similarity below threshold) -> assert it is routed to propose_new_section_placement,
    not silently attached to the nearest low-confidence match.
    """
    source_chunks = [
        SourceChunk(
            id="unmatched_1",
            text="Brand new quantum computing methodology never discussed in the document.",
            approx_topic_heading="Quantum Methodology",
        ),
        SourceChunk(
            id="matched_1",
            text="Detailed breakdown of dataset sizes for Section 2.",
            approx_topic_heading="Dataset Breakdown",
        ),
    ]

    class SelectiveQdrant:
        def search(self, collection_name, query_vector, query_filter, limit):
            # First chunk has low similarity 0.32 (below 0.55 threshold)
            if query_vector[0] == 0.0:
                return [MockHit(page_id="page_1", score=0.32)]
            # Second chunk has high similarity 0.91
            return [MockHit(page_id="page_2", score=0.91)]

    doc_idx = build_mock_doc_index(num_pages=5)

    dest_map, unmatched = await map_source_chunks_to_destinations(
        source_chunks=source_chunks,
        qdrant_client=SelectiveQdrant(),
        project_id="test_proj",
        min_similarity=0.55,
        embeddings_model=MockEmbeddingsModel(),
        doc_idx=doc_idx,
    )

    # Assert only matched_1 is in destination_map
    assert len(dest_map) == 1
    assert "page_2" in dest_map
    assert "page_1" not in dest_map

    # Assert unmatched_1 is properly recorded as unmatched
    assert len(unmatched) == 1
    assert unmatched[0].id == "unmatched_1"

    # Propose new section placement for unmatched
    proposal = await propose_new_section_placement(
        unmatched_chunks=unmatched,
        doc_idx=doc_idx,
        current_code="\\documentclass{article}\n\\begin{document}\n\\section{Section 1}...\n\\end{document}",
    )

    assert proposal["proposal_type"] == "create_new_section"
    assert proposal["num_unmatched"] == 1
    assert "Quantum Methodology" in proposal["suggested_title"]
    assert "don't match any existing section" in proposal["message"]
    assert len(proposal["proposed_sections"]) == 1
    assert "quantum computing methodology" in proposal["proposed_sections"][0]["content"]


# ---------------------------------------------------------------------------
# 5. Merge Correctness Test
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_merge_correctness_multiple_chunks_one_destination():
    """
    Merge correctness: 3 source chunks all matching the same destination page ->
    assert exactly 1 LLM call is made for that page with all 3 chunks' text combined,
    not 3 separate calls.
    """
    source_chunks = [
        SourceChunk(id="c1", text="Point A: Architecture layers", approx_topic_heading="Architecture"),
        SourceChunk(id="c2", text="Point B: Network latency metrics", approx_topic_heading="Metrics"),
        SourceChunk(id="c3", text="Point C: Hardware specifications", approx_topic_heading="Hardware"),
    ]

    class SameDestQdrant:
        def search(self, collection_name, query_vector, query_filter, limit):
            return [MockHit(page_id="page_3", score=0.82)]

    doc_idx = build_mock_doc_index(num_pages=5)

    dest_map, unmatched = await map_source_chunks_to_destinations(
        source_chunks=source_chunks,
        qdrant_client=SameDestQdrant(),
        project_id="test_proj",
        min_similarity=0.55,
        embeddings_model=MockEmbeddingsModel(),
        doc_idx=doc_idx,
    )

    assert len(dest_map) == 1
    assert "page_3" in dest_map
    assert len(dest_map["page_3"]) == 3

    received_prompts = []

    async def mock_call(prov, prompt_msgs, model="", api_keys=None):
        received_prompts.append(prompt_msgs)
        return {"edits": [{"proposed_chunk": "merged content", "original_chunk": "old content"}]}

    async def mock_heal(edit, doc_state, doc_index, ledger):
        return {"success": True, "edits": edit.get("edits", [])}

    @dataclass
    class MockReq:
        current_code: str = "code"
        user_prompt: str = "Insert architecture details"
        project_id: str = "test_proj"

    results = await execute_mapped_insertions(
        destination_map=dest_map,
        req=MockReq(),
        doc_state=MockReq(),
        doc_idx=doc_idx,
        ledger=None,
        call_provider_fn=mock_call,
        self_heal_fn=mock_heal,
    )

    # Exactly 1 call made
    assert len(received_prompts) == 1
    assert len(results) == 1

    combined_prompt_content = "\n".join(str(m.content) for m in received_prompts[0])
    # Assert all 3 points are present in the single prompt
    assert "Point A: Architecture layers" in combined_prompt_content
    assert "Point B: Network latency metrics" in combined_prompt_content
    assert "Point C: Hardware specifications" in combined_prompt_content
    # Assert separator is used
    assert "\n\n---\n\n" in combined_prompt_content or "---" in combined_prompt_content


# ---------------------------------------------------------------------------
# 6. Source Chunking Test
# ---------------------------------------------------------------------------

def test_chunk_source_content_headings_and_paragraphs():
    """
    Test that chunk_source_content correctly splits text along structural headings,
    page markers, and paragraph boundaries without arbitrary character slicing.
    """
    text = (
        "--- PAGE 1 ---\n"
        "\\section{Executive Summary}\n"
        "This is the executive summary of the system architecture and key results.\n\n"
        "\\section{Methodology & Pipeline}\n"
        "We implemented a multi-stage evaluation pipeline using PyMuPDF.\n\n"
        "--- PAGE 2 ---\n"
        "\\section{Experimental Results}\n"
        "The experiments show a 4x reduction in latency under sustained concurrency.\n"
    )

    chunks = chunk_source_content(text)
    assert len(chunks) == 3

    assert chunks[0].approx_topic_heading == "Executive Summary"
    assert chunks[0].page_number == 1
    assert "executive summary" in chunks[0].text

    assert chunks[1].approx_topic_heading == "Methodology & Pipeline"
    assert "evaluation pipeline" in chunks[1].text

    assert chunks[2].approx_topic_heading == "Experimental Results"
    assert chunks[2].page_number == 2
    assert "reduction in latency" in chunks[2].text
