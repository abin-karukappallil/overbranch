"""
chunker.py — Semantic LaTeX Chunker

Splits LaTeX documents along structural boundaries (sections, subsections,
frames, environments, paragraphs) instead of fixed character counts.
Produces rich metadata for every chunk.
"""
import re
import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger("chunker")

# Chunk size limits (600–900 tokens target, ~4 chars per token)
MAX_CHUNK_CHARS = 3200
MIN_CHUNK_CHARS = 100
FALLBACK_CHUNK_SIZE = 2800
FALLBACK_OVERLAP = 480   # ~120 tokens overlap

# Chunk type quality weights (used by retriever for scoring)
CHUNK_TYPE_WEIGHTS: Dict[str, float] = {
    "section": 1.0,
    "frame": 0.95,
    "subsection": 0.9,
    "table": 0.88,
    "figure": 0.88,
    "bibliography": 0.85,
    "environment": 0.8,
    "paragraph": 0.6,
    "preamble": 0.3,
}

# Regex patterns for structural boundaries
_SECTION_RE = re.compile(r"^\\section\{", re.MULTILINE)
_SUBSECTION_RE = re.compile(r"^\\subsection\{", re.MULTILINE)
_FRAME_RE = re.compile(r"\\begin\{frame\}", re.DOTALL)
_ENV_BEGIN_RE = re.compile(r"\\begin\{(figure|table|itemize|enumerate|equation|align|abstract|thebibliography)\}")
_ENV_END_RE_TMPL = r"\\end\{%s\}"
_PARAGRAPH_RE = re.compile(r"\n\s*\n")
_BEGIN_DOC_RE = re.compile(r"\\begin\{document\}")
_END_DOC_RE = re.compile(r"\\end\{document\}")
_TEX_CMD_RE = re.compile(r"\\[a-zA-Z]+\{?[^}]*\}?")


def _compute_file_hash(content: str) -> str:
    """Fast hash of file content for dedup detection."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _strip_tex_for_summary(text: str) -> str:
    """Strip TeX commands to produce a plain-text summary."""
    s = text.strip()
    s = re.sub(r"\\begin\{[^}]*\}", "", s)
    s = re.sub(r"\\end\{[^}]*\}", "", s)
    s = re.sub(r"\\[a-zA-Z]+\*?\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\[a-zA-Z]+\*?", "", s)
    s = re.sub(r"[{}]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:120]


def _line_number_at(text: str, char_pos: int) -> int:
    """Return 1-based line number for a character position."""
    return text[:char_pos].count("\n") + 1


def _extract_section_title(text: str) -> str:
    """Extract the title from a \\section{...} or \\subsection{...} line."""
    m = re.match(r"\\(?:sub)?section\{([^}]*)\}", text.strip())
    return m.group(1) if m else ""


def _classify_chunk(text: str) -> str:
    """Classify a chunk by its dominant structural element."""
    stripped = text.strip()
    if re.match(r"\\documentclass", stripped) or re.match(r"\\usepackage", stripped):
        return "preamble"
    if re.match(r"\\section\{", stripped):
        return "section"
    if re.match(r"\\subsection\{", stripped):
        return "subsection"
    if re.match(r"\\begin\{frame\}", stripped):
        return "frame"
    if "\\begin{table}" in stripped or "\\begin{tabular}" in stripped:
        return "table"
    if "\\begin{figure}" in stripped:
        return "figure"
    if "\\begin{thebibliography}" in stripped or "\\bibliography{" in stripped or "\\bibliographystyle{" in stripped:
        return "bibliography"
    if _ENV_BEGIN_RE.match(stripped):
        return "environment"
    return "paragraph"


def _split_keeping_environments(text: str) -> List[str]:
    """Split text at structural boundaries while keeping environments intact."""
    # Find all section/subsection boundaries
    boundaries = []

    for m in _SECTION_RE.finditer(text):
        boundaries.append(m.start())
    for m in _SUBSECTION_RE.finditer(text):
        boundaries.append(m.start())
    for m in re.finditer(r"\\begin\{(table|figure|thebibliography)\}", text):
        boundaries.append(m.start())

    # If we have structural boundaries, split on them
    if boundaries:
        boundaries = sorted(set(boundaries))
        chunks = []
        for i, start in enumerate(boundaries):
            end = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

        # If there's text before the first boundary, include it
        if boundaries[0] > 0:
            pre = text[:boundaries[0]].strip()
            if pre:
                chunks.insert(0, pre)

        return chunks

    # Try splitting on frames
    frame_chunks = _split_on_frames(text)
    if len(frame_chunks) > 1:
        return frame_chunks

    # Try splitting on paragraph boundaries
    para_chunks = _split_on_paragraphs(text)
    if len(para_chunks) > 1:
        return para_chunks

    return [text]


def _split_on_frames(text: str) -> List[str]:
    """Split on \\begin{frame}...\\end{frame} boundaries."""
    parts = []
    last_end = 0

    for m in re.finditer(r"\\begin\{frame\}.*?\\end\{frame\}", text, re.DOTALL):
        pre = text[last_end:m.start()].strip()
        if pre:
            parts.append(pre)
        parts.append(m.group(0))
        last_end = m.end()

    post = text[last_end:].strip()
    if post:
        parts.append(post)

    return parts if len(parts) > 1 else [text]


def _split_on_paragraphs(text: str) -> List[str]:
    """Split on double-newline paragraph boundaries."""
    raw_parts = _PARAGRAPH_RE.split(text)
    parts = [p.strip() for p in raw_parts if p.strip()]
    return parts if len(parts) > 1 else [text]


def _fallback_split(text: str) -> List[str]:
    """Fixed-size split with overlap as last resort."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + FALLBACK_CHUNK_SIZE, len(text))
        chunks.append(text[start:end])
        start = end - FALLBACK_OVERLAP
        if start >= len(text):
            break
    return chunks


def _enforce_size_limits(chunks: List[str]) -> List[str]:
    """Split oversized chunks and merge undersized ones."""
    result = []

    for chunk in chunks:
        if len(chunk) > MAX_CHUNK_CHARS:
            # Try to split further on sub-boundaries
            sub_chunks = _split_on_paragraphs(chunk)
            if len(sub_chunks) == 1 and len(sub_chunks[0]) > MAX_CHUNK_CHARS:
                sub_chunks = _fallback_split(chunk)
            result.extend(sub_chunks)
        else:
            result.append(chunk)

    # Merge undersized chunks with neighbors — but NEVER merge structural chunks
    # (sections, subsections, frames) across boundaries
    merged = []
    buffer = ""
    for chunk in result:
        chunk_is_structural = bool(
            re.match(r"\\(section|subsection|begin\{frame\}|begin\{table\}|begin\{figure\}|begin\{thebibliography\})", chunk.strip())
        )
        # If this chunk starts a new structural element, flush the buffer
        if chunk_is_structural:
            if buffer:
                merged.append(buffer)
                buffer = ""
            merged.append(chunk)
        elif len(buffer) + len(chunk) < MIN_CHUNK_CHARS * 3 and not bool(
            re.match(r"\\(section|subsection|begin\{frame\})", buffer.strip())
        ):
            buffer = (buffer + "\n\n" + chunk).strip() if buffer else chunk
        else:
            if buffer:
                merged.append(buffer)
            buffer = chunk

    if buffer:
        merged.append(buffer)

    return merged


def semantic_chunk_latex(
    content: str,
    project_id: str,
    file_path: str,
) -> List[Dict[str, Any]]:
    """
    Split LaTeX content into semantically meaningful chunks with rich metadata.

    Returns a list of chunk dicts ready for embedding and Qdrant upsert.
    """
    if not content or not content.strip():
        return []

    file_hash = _compute_file_hash(content)
    now_iso = datetime.now(timezone.utc).isoformat()

    # Separate preamble from body
    preamble_text = ""
    body_text = content

    begin_doc = _BEGIN_DOC_RE.search(content)
    if begin_doc:
        preamble_text = content[:begin_doc.start()].strip()
        end_doc = _END_DOC_RE.search(content)
        if end_doc:
            body_text = content[begin_doc.end():end_doc.start()].strip()
        else:
            body_text = content[begin_doc.end():].strip()

    # Build raw chunk list
    raw_chunks = []

    # Preamble as one chunk
    if preamble_text:
        raw_chunks.append(preamble_text)

    # Split body on structural boundaries
    if body_text:
        body_parts = _split_keeping_environments(body_text)
        raw_chunks.extend(body_parts)

    # Enforce size limits
    raw_chunks = _enforce_size_limits(raw_chunks)

    # Build metadata for each chunk
    result = []
    current_section = ""

    for idx, chunk_text in enumerate(raw_chunks):
        chunk_type = _classify_chunk(chunk_text)

        # Track current section context
        sec_title = _extract_section_title(chunk_text)
        if sec_title:
            current_section = sec_title

        # Add section context prefix for non-section chunks
        display_content = chunk_text
        if chunk_type not in ("section", "preamble") and current_section:
            display_content = f"% Context: \\section{{{current_section}}}\n{chunk_text}"

        start_line = _line_number_at(content, content.find(chunk_text[:80])) if chunk_text[:80] in content else 0
        end_line = start_line + chunk_text.count("\n")

        summary = _strip_tex_for_summary(chunk_text)
        approx_pos = round((idx + 1) / max(len(raw_chunks), 1), 2)

        result.append({
            "project_id": project_id,
            "file_path": file_path,
            "chunk_index": idx,
            "chunk_type": chunk_type,
            "section": current_section,
            "approx_position": approx_pos,
            "start_line": start_line,
            "end_line": end_line,
            "content": display_content,
            "raw_text": chunk_text,
            "summary": summary,
            "file_hash": file_hash,
            "last_modified": now_iso,
        })

    logger.info(f"Semantic chunker: split '{file_path}' into {len(result)} chunks "
                f"(types: {[c['chunk_type'] for c in result]})")
    return result
