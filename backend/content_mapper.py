"""
content_mapper.py — Many-to-Many Semantic Chunk Mapping for Content Insertion

Handles broad-relevance source documents (e.g. multi-topic PDFs or reference text).
Chunks the source content along structural boundaries, computes batched embeddings,
and independently matches each source chunk against destination sections via Qdrant.
Dispatches all discovered destination section edits in parallel through governed
concurrency pools, and routes unmatched chunks to new section proposals.
"""

import re
import uuid
import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Union

logger = logging.getLogger("content_mapper")


@dataclass
class SourceChunk:
    """A semantically coherent unit extracted from the incoming source content."""
    id: str
    text: str
    approx_topic_heading: Optional[str] = None
    page_number: Optional[int] = None


@dataclass
class MatchedInsertion:
    """A mapping from a source chunk to a destination section with similarity score."""
    source_chunk: SourceChunk
    similarity: float


def chunk_source_content(
    extracted_pdf_text: str,
    layout_blocks: Optional[List[Any]] = None,
) -> List[SourceChunk]:
    """
    Split the incoming PDF/source content into semantically coherent units using
    boundary-aware logic — headings, paragraph breaks, detected section markers,
    and layout blocks — NOT a fixed character count.
    """
    if not extracted_pdf_text or not extracted_pdf_text.strip():
        return []

    chunks: List[SourceChunk] = []

    # If explicit layout_blocks are provided, group by detected block headers/paragraphs
    if layout_blocks and isinstance(layout_blocks, list) and len(layout_blocks) > 0:
        current_heading: Optional[str] = None
        current_texts: List[str] = []
        current_page: Optional[int] = None

        for block in layout_blocks:
            b_text = ""
            b_page = None
            if isinstance(block, dict):
                b_text = block.get("text", "").strip()
                b_page = block.get("page") or block.get("page_number")
            elif hasattr(block, "text"):
                b_text = getattr(block, "text", "").strip()
                b_page = getattr(block, "page", None) or getattr(block, "page_number", None)

            if not b_text:
                continue

            # Check if this block looks like a section/topic heading
            is_heading = bool(
                re.match(r"^(?:\\(?:sub)*section\{|#+\s+|[0-9]+(?:\.[0-9]+)*\s+[A-Z]|[A-Z\s]{4,40}$)", b_text)
                or (len(b_text) < 80 and b_text.endswith(":") and "\n" not in b_text)
            )

            if is_heading:
                if current_texts:
                    chunk_text = "\n\n".join(current_texts).strip()
                    if chunk_text:
                        c_id = f"src_chunk_{len(chunks)+1}_{uuid.uuid4().hex[:6]}"
                        chunks.append(SourceChunk(
                            id=c_id,
                            text=chunk_text,
                            approx_topic_heading=current_heading or "Source Content",
                            page_number=current_page,
                        ))
                    current_texts = []
                current_heading = re.sub(r"^(?:\\(?:sub)*section\{|#+\s+|[0-9]+(?:\.[0-9]+)*\s+)", "", b_text).rstrip("}")
                current_texts.append(b_text)
                current_page = b_page
            else:
                current_texts.append(b_text)
                if current_page is None:
                    current_page = b_page

        if current_texts:
            chunk_text = "\n\n".join(current_texts).strip()
            if chunk_text:
                c_id = f"src_chunk_{len(chunks)+1}_{uuid.uuid4().hex[:6]}"
                chunks.append(SourceChunk(
                    id=c_id,
                    text=chunk_text,
                    approx_topic_heading=current_heading or "Source Content",
                    page_number=current_page,
                ))

        if chunks:
            return chunks

    # Fallback to boundary parsing on extracted_pdf_text
    # Check for page markers like '--- PAGE N ---' or '[Page N]'
    page_marker_re = re.compile(r"(?:--- PAGE (\d+) ---|\[Page (\d+)\])", re.IGNORECASE)

    # Split on structural heading patterns or page markers
    # Patterns: \section, \subsection, # Heading, 1. Title, Page markers
    lines = extracted_pdf_text.splitlines()
    buffer_lines: List[str] = []
    current_heading = None
    current_page = 1

    def flush_buffer():
        nonlocal buffer_lines, current_heading, current_page
        joined = "\n".join(buffer_lines).strip()
        if joined and len(joined) >= 40:
            c_id = f"src_chunk_{len(chunks)+1}_{uuid.uuid4().hex[:6]}"
            chunks.append(SourceChunk(
                id=c_id,
                text=joined,
                approx_topic_heading=current_heading or "Overview",
                page_number=current_page,
            ))
        buffer_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if buffer_lines and len("\n".join(buffer_lines)) > 1200:
                flush_buffer()
            continue

        page_m = page_marker_re.search(stripped)
        if page_m:
            flush_buffer()
            pg_val = page_m.group(1) or page_m.group(2)
            current_page = int(pg_val) if pg_val and pg_val.isdigit() else current_page + 1
            continue

        # Check for structural heading
        heading_match = (
            re.match(r"^\\(?:sub)*section\*?\{([^}]+)\}", stripped)
            or re.match(r"^#{1,4}\s+(.+)$", stripped)
            or re.match(r"^([0-9]+(?:\.[0-9]+)*\s+[A-Z][A-Za-z0-9\s,\-]{2,60})$", stripped)
            or (stripped.isupper() and 4 <= len(stripped) <= 45 and not stripped.startswith("%"))
        )

        if heading_match:
            flush_buffer()
            if hasattr(heading_match, "group"):
                current_heading = heading_match.group(1).strip()
            else:
                current_heading = stripped
            buffer_lines.append(stripped)
        else:
            buffer_lines.append(line)

    flush_buffer()

    # If no structural chunks emerged (e.g. plain unformatted paragraph text), split on paragraphs
    if not chunks:
        paragraphs = re.split(r"\n\s*\n", extracted_pdf_text)
        for idx, p in enumerate(paragraphs):
            p_clean = p.strip()
            if p_clean:
                chunks.append(SourceChunk(
                    id=f"src_chunk_{idx+1}_{uuid.uuid4().hex[:6]}",
                    text=p_clean,
                    approx_topic_heading=f"Section {idx+1}",
                    page_number=None,
                ))

    return chunks


async def embed_batch(
    texts: List[str],
    embeddings_model: Any = None,
) -> List[List[float]]:
    """
    Generate vector embeddings for multiple texts in a single batched network round-trip.
    """
    if not texts:
        return []

    if embeddings_model is None:
        from vector_sync import get_nvidia_embeddings
        embeddings_model = get_nvidia_embeddings()

    # If the embeddings model provides async batch embedding
    if hasattr(embeddings_model, "aembed_documents"):
        return await embeddings_model.aembed_documents(texts)

    # Run synchronous embedding in an executor to avoid blocking the event loop
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, embeddings_model.embed_documents, texts)


def _extract_score(hit: Any) -> float:
    """Extract similarity score from a Qdrant search result or dictionary."""
    if hasattr(hit, "score"):
        return float(hit.score)
    if isinstance(hit, dict):
        return float(hit.get("score", 0.0))
    return 0.0


def _extract_payload(hit: Any) -> Dict[str, Any]:
    """Extract payload dictionary from a Qdrant search result."""
    if hasattr(hit, "payload") and isinstance(hit.payload, dict):
        return hit.payload
    if isinstance(hit, dict):
        return hit.get("payload", {})
    return {}


async def map_source_chunks_to_destinations(
    source_chunks: List[SourceChunk],
    qdrant_client: Any,
    project_id: str,
    min_similarity: float = 0.55,
    max_targets_per_chunk: int = 2,
    embeddings_model: Any = None,
    doc_idx: Any = None,
) -> Tuple[Dict[str, List[MatchedInsertion]], List[SourceChunk]]:
    """
    Many-to-many semantic matching: each source chunk finds its own destination(s).
    Uses a single batch embedding call to handle all source chunks at once.

    Returns:
        (destination_map, unmatched_chunks)
        where destination_map is { destination_page_id: [MatchedInsertion(source_chunk, similarity), ...] }
    """
    if not source_chunks:
        return {}, []

    source_embeddings = await embed_batch([c.text for c in source_chunks], embeddings_model=embeddings_model)

    destination_map: Dict[str, List[MatchedInsertion]] = defaultdict(list)
    unmatched_chunks: List[SourceChunk] = []

    for chunk, embedding in zip(source_chunks, source_embeddings):
        hits = []
        if qdrant_client is not None:
            try:
                # Support standard Qdrant search
                if hasattr(qdrant_client, "search"):
                    hits = qdrant_client.search(
                        collection_name="overbranch_latex_chunks",
                        query_vector=embedding,
                        query_filter={"must": [{"key": "project_id", "match": {"value": project_id}}]},
                        limit=max_targets_per_chunk,
                    )
                elif hasattr(qdrant_client, "query_points"):
                    res = qdrant_client.query_points(
                        collection_name="overbranch_latex_chunks",
                        query=embedding,
                        limit=max_targets_per_chunk,
                    )
                    hits = res.points if hasattr(res, "points") else []
            except Exception as search_err:
                logger.warning(f"Qdrant search error for source chunk '{chunk.id}': {search_err}")
                hits = []

        confident_hits = [h for h in hits if _extract_score(h) >= min_similarity]

        if not confident_hits:
            unmatched_chunks.append(chunk)
            continue

        for hit in confident_hits:
            payload = _extract_payload(hit)
            score = _extract_score(hit)
            page_id = payload.get("page_id")

            # Fallback resolution of page_id if not stored explicitly on payload
            if not page_id and doc_idx:
                if "start_line" in payload:
                    p = doc_idx.page_for_line(payload["start_line"])
                    if p:
                        page_id = p.page_id
                if not page_id and "section" in payload:
                    p = doc_idx.resolve_target(payload["section"])
                    if p:
                        page_id = p.page_id

            if not page_id:
                page_id = payload.get("section") or payload.get("file_path") or "unknown_target"

            destination_map[page_id].append(
                MatchedInsertion(source_chunk=chunk, similarity=score)
            )

    return dict(destination_map), unmatched_chunks


async def propose_new_section_placement(
    unmatched_chunks: List[SourceChunk],
    doc_idx: Any,
    current_code: str,
) -> Dict[str, Any]:
    """
    Handle chunks that don't match anywhere. Formulates a proposed placement
    for new sections rather than silently stuffing material into a low-confidence match.
    """
    if not unmatched_chunks:
        return {}

    first_heading = unmatched_chunks[0].approx_topic_heading or "Supplementary Material"

    # Identify reasonable insertion location: after the main body sections, before appendix / bibliography
    placement_description = "at the end of the main document"
    if doc_idx and getattr(doc_idx, "pages", None):
        non_preamble = [p for p in doc_idx.pages if p.page_id != "preamble" and getattr(p, "page_type", "") != "preamble"]
        if non_preamble:
            last_page = non_preamble[-1]
            placement_description = f"after '{last_page.title}'"

    return {
        "proposal_type": "create_new_section",
        "num_unmatched": len(unmatched_chunks),
        "unmatched_chunk_ids": [c.id for c in unmatched_chunks],
        "suggested_title": first_heading,
        "suggested_placement": placement_description,
        "proposed_sections": [
            {
                "title": c.approx_topic_heading or f"Section {idx+1}",
                "content": c.text,
            }
            for idx, c in enumerate(unmatched_chunks)
        ],
        "message": (
            f"{len(unmatched_chunks)} part{'s' if len(unmatched_chunks) != 1 else ''} of this content "
            f"don't match any existing section — should I create a new section for them, or would you like to place them manually?"
        ),
    }


async def execute_mapped_insertions(
    destination_map: Dict[str, List[MatchedInsertion]],
    req: Any,
    doc_state: Any,
    doc_idx: Any,
    ledger: Any,
    provider_name: Optional[str] = None,
    model: str = "",
    api_keys: Optional[Dict[str, str]] = None,
    preferred_provider_fn: Optional[Any] = None,
    call_provider_fn: Optional[Any] = None,
    self_heal_fn: Optional[Any] = None,
) -> List[Any]:
    """
    Aggregate per destination, dispatch in parallel regardless of count.
    Multiple source chunks landing on the same destination get merged into ONE
    edit prompt for that section — never one LLM call per source chunk.
    Dispatched concurrently via asyncio.gather through the governed provider pool.
    """
    if not destination_map:
        return []

    # Setup helper functions
    from provider_governor import call_provider_governed

    effective_call_provider = call_provider_fn or call_provider_governed

    effective_current_code = getattr(req, "current_code", "") or getattr(doc_state, "current_code", "")

    async def insert_into_one_destination(page_id: str, matches: List[MatchedInsertion]) -> Any:
        # Multiple source chunks landing on the same destination get merged into
        # ONE edit prompt for that section
        combined_source_text = "\n\n---\n\n".join(m.source_chunk.text for m in matches)

        target_page = None
        if hasattr(doc_idx, "get_page"):
            target_page = doc_idx.get_page(page_id)
        elif hasattr(doc_idx, "get_page_by_id"):
            target_page = doc_idx.get_page_by_id(page_id)
        if not target_page and hasattr(doc_idx, "resolve_target"):
            target_page = doc_idx.resolve_target(page_id)

        ledger_context = ledger.spans_touching_page(page_id) if ledger and hasattr(ledger, "spans_touching_page") else []

        import prompt_builder
        prompt_messages = prompt_builder.build_insertion_prompt(
            source_content=combined_source_text,
            target_page=target_page,
            full_document=effective_current_code,
            ledger_context=ledger_context,
            original_instruction=getattr(req, "user_prompt", ""),
        )

        active_provider = provider_name
        if not active_provider:
            if preferred_provider_fn:
                active_provider = preferred_provider_fn(model)
            else:
                active_provider = "gemini_web2api"

        proposed_edit = await effective_call_provider(
            active_provider,
            prompt_messages,
            model=model,
            api_keys=api_keys,
        )

        if self_heal_fn:
            return await self_heal_fn(proposed_edit, doc_state, doc_idx, ledger)

        # Fallback to importing apply_edit_with_self_healing
        from agent import apply_edit_with_self_healing, clean_json_response, extract_chunk_latex

        # Format proposed_edit into list of edits if it is a ChatMessage / string / dict
        formatted_edits = []
        if isinstance(proposed_edit, dict):
            if "edits" in proposed_edit:
                formatted_edits = proposed_edit["edits"]
            else:
                formatted_edits = [proposed_edit]
        elif hasattr(proposed_edit, "content"):
            parsed = clean_json_response(proposed_edit.content)
            if parsed and parsed.get("edits"):
                formatted_edits = parsed["edits"]
            elif parsed and (parsed.get("proposed_chunk") or parsed.get("original_chunk")):
                formatted_edits = [parsed]
            else:
                extracted = extract_chunk_latex(proposed_edit.content)
                if extracted and target_page:
                    formatted_edits = [{
                        "original_chunk": target_page.content,
                        "proposed_chunk": extracted,
                        "explanation": f"Integrated content into {target_page.title}",
                    }]

        curr_code_str = getattr(doc_state, "current_code", effective_current_code) if not isinstance(doc_state, str) else doc_state

        return await apply_edit_with_self_healing(
            proposed_edits=formatted_edits,
            current_code=curr_code_str,
            doc_idx=doc_idx,
            ledger=ledger,
            user_instruction=getattr(req, "user_prompt", ""),
            preferred_provider_name=active_provider,
            model=model,
            api_keys=api_keys,
            project_id=getattr(req, "project_id", None),
        )

    # Dispatched in parallel via asyncio.gather across all destination sections
    results = await asyncio.gather(*[
        insert_into_one_destination(page_id, matches)
        for page_id, matches in destination_map.items()
    ])
    return list(results)
