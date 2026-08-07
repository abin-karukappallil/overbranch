import logging
from typing import List, Dict, Any

logger = logging.getLogger("context_builder")

MAX_CONTEXT_CHARS = 3500


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

    # Step 1: Remove content duplicates
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
