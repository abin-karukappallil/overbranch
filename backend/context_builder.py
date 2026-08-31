import logging
import hashlib
from typing import List, Dict, Any, Optional

logger = logging.getLogger("context_builder")

# Token budgets — edits need far less context than generation
MAX_CONTEXT_CHARS_EDIT = 2500       # Targeted edit: just the slide window
MAX_CONTEXT_CHARS_GENERATE = 3500   # Generation/conversion: broader context
MAX_CONTEXT_CHARS = MAX_CONTEXT_CHARS_GENERATE  # Default (backward compat)


def _group_by_file(chunks: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group chunks by their source file path."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for chunk in chunks:
        fp = chunk.get("file_path", "unknown")
        if fp not in groups:
            groups[fp] = []
        groups[fp].append(chunk)
    return groups


def _sort_by_index(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort chunks within a file group by chunk_index (document order)."""
    return sorted(chunks, key=lambda c: c.get("chunk_index", 0))


def _merge_adjacent(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge chunks with adjacent chunk_index into single blocks."""
    if len(chunks) <= 1:
        return chunks

    merged = [chunks[0].copy()]
    for chunk in chunks[1:]:
        last = merged[-1]
        # Adjacent if chunk_index difference <= 1
        if abs(chunk.get("chunk_index", 0) - last.get("chunk_index", 0)) <= 1:
            # Merge: combine content, extend line range, keep higher score
            last["content"] = last["content"].rstrip() + "\n\n" + chunk["content"].lstrip()
            last["end_line"] = max(last.get("end_line", 0), chunk.get("end_line", 0))
            last["composite_score"] = max(
                last.get("composite_score", 0),
                chunk.get("composite_score", 0),
            )
            # Update summary to cover both
            if chunk.get("summary"):
                last["summary"] = (last.get("summary", "") + " | " + chunk["summary"])[:120]
        else:
            merged.append(chunk.copy())

    return merged


def _remove_content_duplicates(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove chunks whose content is fully contained in another chunk."""
    result = []
    for i, chunk in enumerate(chunks):
        content = chunk.get("content", "").strip()
        is_contained = False
        for j, other in enumerate(chunks):
            if i != j:
                other_content = other.get("content", "").strip()
                if content and other_content and content in other_content:
                    is_contained = True
                    break
        if not is_contained:
            result.append(chunk)
    return result


def _deduplicate_by_content_hash(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Fast deduplication using content fingerprints.
    Keeps the chunk with the highest composite_score when duplicates are found.
    """
    seen: Dict[str, Dict[str, Any]] = {}
    for chunk in chunks:
        content = chunk.get("content", "").strip()
        if not content:
            continue
        # Use a hash of the first 200 chars + length as a fast fingerprint
        fingerprint = hashlib.md5(
            f"{content[:200]}:{len(content)}".encode("utf-8")
        ).hexdigest()

        if fingerprint in seen:
            # Keep the one with higher score
            existing = seen[fingerprint]
            if chunk.get("composite_score", 0) > existing.get("composite_score", 0):
                seen[fingerprint] = chunk
        else:
            seen[fingerprint] = chunk

    return list(seen.values())


def _format_chunk_header(chunk: Dict[str, Any], file_path: str) -> str:
    """Format a metadata header for a chunk."""
    chunk_type = chunk.get("chunk_type", "paragraph")
    start = chunk.get("start_line", "?")
    end = chunk.get("end_line", "?")
    score = chunk.get("composite_score", chunk.get("similarity", 0))
    summary = chunk.get("summary", "")

    header = f"[{chunk_type}] Lines {start}-{end}"
    if summary:
        header += f" — {summary[:60]}"
    return header


def build_context(
    chunks: List[Dict[str, Any]],
    max_chars: int = MAX_CONTEXT_CHARS,
) -> str:
    """
    Build a structured context string from retrieved chunks.

    Groups by file, sorts by document order, merges adjacent chunks,
    removes duplicates, and trims to context budget.
    """
    if not chunks:
        return "No existing LaTeX chunks found for this file. Generate proposed snippet based on user request."

    # Step 1: Fast hash-based dedup first, then content-containment dedup
    chunks = _deduplicate_by_content_hash(chunks)
    chunks = _remove_content_duplicates(chunks)

    # Step 2: Group by file
    file_groups = _group_by_file(chunks)

    # Step 3: For each file group, sort and merge
    processed_groups: Dict[str, List[Dict[str, Any]]] = {}
    for fp, group in file_groups.items():
        sorted_group = _sort_by_index(group)
        merged_group = _merge_adjacent(sorted_group)
        processed_groups[fp] = merged_group

    # Step 4: Build formatted context string
    # Sort files by max composite_score of their chunks (most relevant file first)
    sorted_files = sorted(
        processed_groups.keys(),
        key=lambda fp: max(c.get("composite_score", 0) for c in processed_groups[fp]),
        reverse=True,
    )

    context_parts = []
    total_chars = 0

    for fp in sorted_files:
        group = processed_groups[fp]
        file_header = f"=== FILE: {fp} ==="

        # Sort chunks within file by composite score (highest first)
        group.sort(key=lambda c: c.get("composite_score", 0), reverse=True)

        file_parts = [file_header]
        for idx, chunk in enumerate(group[:8], 1):
            chunk_type = chunk.get("chunk_type", "paragraph")
            start = chunk.get("start_line", "?")
            end = chunk.get("end_line", "?")
            summary = chunk.get("summary", "")
            chunk_content = chunk.get("content", "").strip()

            block = (
                f"--- RETRIEVED CHUNK {idx} (File: {fp}, Type: {chunk_type}, Lines: {start}-{end}) ---\n"
                f"{chunk_content}"
            )

            # Check budget
            if total_chars + len(block) > max_chars:
                remaining = max_chars - total_chars
                if remaining > 200:
                    # Truncate this chunk to fit
                    block = block[:remaining] + "\n... [truncated for context budget]"
                    file_parts.append(block)
                    total_chars += len(block)
                break

            file_parts.append(block)
            total_chars += len(block)

        context_parts.append("\n".join(file_parts))

        if total_chars >= max_chars:
            break

    result = "\n\n".join(context_parts)
    logger.info(f"Context builder: {len(chunks)} chunks → {len(result)} chars "
                f"across {len(sorted_files)} files")
    return result


# ---------------------------------------------------------------------------
# Targeted context building (for edit operations)
# ---------------------------------------------------------------------------

def build_targeted_context(
    retrieved_chunks: List[Dict[str, Any]],
    current_code: Optional[str],
    target_page_index: Optional[int],
    max_chars: int = MAX_CONTEXT_CHARS_EDIT,
) -> str:
    """
    Build a focused context string for edit operations.

    Instead of dumping all retrieved chunks, this:
    1. Parses the document into a page/slide index
    2. Extracts only the target page ± 1 neighbor
    3. Deduplicates retrieved chunks against the page window
    4. Keeps total context size minimal for free-tier LLM APIs

    Falls back to standard build_context() when targeting isn't possible.

    Args:
        retrieved_chunks: Chunks from the vector retrieval pipeline
        current_code: The user's full LaTeX document
        target_page_index: Index of the target page (from find_target_page)
        max_chars: Context budget in characters
    """
    # If no current code or no target, fall back to standard context
    if not current_code or target_page_index is None:
        return build_context(retrieved_chunks, max_chars=max_chars)

    try:
        from document_index import parse_document_structure, get_page_window

        doc_index = parse_document_structure(current_code)

        if not doc_index.pages:
            return build_context(retrieved_chunks, max_chars=max_chars)

        # Get the target page window (target ± 1 neighbor)
        window_pages = get_page_window(doc_index, target_page_index, window=1)

        if not window_pages:
            return build_context(retrieved_chunks, max_chars=max_chars)

        # Build the targeted context from the page window
        parts = []
        total_chars = 0

        for page in window_pages:
            is_target = page.page_index == target_page_index
            marker = "TARGET" if is_target else "NEIGHBOR"
            header = (
                f"--- [{marker}] {page.page_type.upper()} "
                f"(id: {page.page_id}, title: {page.title}) ---"
            )

            content = page.content.strip()

            # Budget check — truncate if needed but always include the target
            entry = f"{header}\n{content}"
            if total_chars + len(entry) > max_chars and not is_target:
                # Skip neighbor pages that would exceed budget
                continue

            if total_chars + len(entry) > max_chars and is_target:
                # Truncate target content to fit
                remaining = max_chars - total_chars - len(header) - 50
                if remaining > 200:
                    content = content[:remaining] + "\n... [truncated for budget]"
                    entry = f"{header}\n{content}"

            parts.append(entry)
            total_chars += len(entry)

        # Add a few high-scoring retrieved chunks that aren't already in the window
        # (for cross-reference context), but cap tightly
        window_hashes = {p.content_hash for p in window_pages}
        extra_budget = max_chars - total_chars

        if extra_budget > 300 and retrieved_chunks:
            deduped = _deduplicate_by_content_hash(retrieved_chunks)
            for chunk in sorted(deduped, key=lambda c: c.get("composite_score", 0), reverse=True)[:3]:
                chunk_content = chunk.get("content", "").strip()
                # Skip if this chunk overlaps with window content
                chunk_hash = hashlib.md5(
                    f"{chunk_content[:200]}:{len(chunk_content)}".encode("utf-8")
                ).hexdigest()[:16]
                if chunk_hash in window_hashes:
                    continue

                entry = f"--- RETRIEVED (score: {chunk.get('composite_score', 0):.2f}) ---\n{chunk_content[:500]}"
                if total_chars + len(entry) > max_chars:
                    break
                parts.append(entry)
                total_chars += len(entry)

        result = "\n\n".join(parts)
        logger.info(
            f"Targeted context: {len(window_pages)} pages in window, "
            f"{total_chars} chars (budget: {max_chars})"
        )
        return result

    except Exception as e:
        logger.warning(f"Targeted context building failed, falling back: {e}")
        return build_context(retrieved_chunks, max_chars=max_chars)

