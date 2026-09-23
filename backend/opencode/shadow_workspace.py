"""
opencode/shadow_workspace.py — Thread-Safe In-Memory Shadow Buffer
===================================================================
Provides a ShadowWorkspace that holds an exact copy of the user's main.tex
in memory. All agent edits operate on this buffer — never on disk.

Thread-safe via threading.Lock so multiple concurrent agent runs are isolated.
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from document_index import DocumentChunk, DocumentIndex


class ShadowWorkspaceError(Exception):
    """Raised when a shadow workspace operation fails (e.g. str_replace mismatch)."""
    pass


class ShadowWorkspace:
    """
    In-memory shadow copy of a LaTeX project for safe agentic editing.

    The original code is frozen at construction time. All mutations happen
    on the internal ``_buffer``. After the agent finishes, call
    ``compute_diff()`` to get a structured diff payload for the frontend.
    """

    def __init__(
        self,
        original_code: str,
        project_id: str = "default",
        file_path: str = "main.tex",
        assets_dir: Optional[str] = None,
    ):
        self._original: str = original_code
        self._buffer: str = original_code
        self._project_id: str = project_id
        self._file_path: str = file_path
        self._assets_dir: Optional[str] = assets_dir
        self._lock = threading.Lock()
        self._edit_history: List[Dict[str, Any]] = []
        self._doc_index = DocumentIndex()
        self._touched_chunks: Set[str] = set()

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_original(self) -> str:
        """Returns the frozen original code (never mutated)."""
        return self._original

    def get_buffer(self) -> str:
        """Returns the current state of the shadow buffer."""
        with self._lock:
            return self._buffer

    def get_line_count(self) -> int:
        """Returns the number of lines in the current buffer."""
        with self._lock:
            return len(self._buffer.splitlines(keepends=False)) or 1

    def read_lines(self, start_line: int, end_line: int) -> str:
        """
        Returns exact line-numbered content from the shadow buffer.

        Args:
            start_line: 1-indexed inclusive start line.
            end_line: 1-indexed inclusive end line.

        Returns:
            String with ``<line_no>: <content>`` per line.
        """
        with self._lock:
            lines = self._buffer.splitlines(keepends=False)

        total = len(lines)
        start = max(1, start_line)
        end = min(total, end_line)

        if start > total:
            return f"(No content — file has {total} lines, requested start={start_line})"

        result_parts: list[str] = []
        for i in range(start - 1, end):
            result_parts.append(f"{i + 1}: {lines[i]}")

        return "\n".join(result_parts)

    def grep(self, pattern: str, is_regex: bool = False) -> List[Dict[str, Any]]:
        """
        Searches the shadow buffer for a pattern.

        Args:
            pattern: Literal string or regex pattern.
            is_regex: If True, treat pattern as regex.

        Returns:
            List of ``{line_no: int, content: str, match: str}`` dicts.
        """
        with self._lock:
            lines = self._buffer.splitlines(keepends=False)

        results: List[Dict[str, Any]] = []
        try:
            compiled = re.compile(pattern if is_regex else re.escape(pattern))
        except re.error as e:
            return [{"error": f"Invalid regex: {e}"}]

        for idx, line in enumerate(lines, start=1):
            m = compiled.search(line)
            if m:
                results.append({
                    "line_no": idx,
                    "content": line,
                    "match": m.group(0),
                })
                # Cap results to prevent flooding the LLM context
                if len(results) >= 50:
                    results.append({"truncated": True, "total_lines_searched": len(lines)})
                    break

        return results

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def str_replace(self, old_str: str, new_str: str) -> Dict[str, Any]:
        """
        Exact character-for-character replacement in the shadow buffer.

        Enforces that ``old_str`` exists verbatim in the buffer. This prevents
        hallucinated edits where the LLM invents text that doesn't exist.

        Args:
            old_str: The exact string to find in the buffer.
            new_str: The replacement string.

        Returns:
            ``{success: bool, occurrences_found: int, lines_affected: [int, int]}``

        Raises:
            ShadowWorkspaceError: If ``old_str`` is not found in the buffer.
        """
        with self._lock:
            # Handle empty buffer initialization (e.g. creating brand new document from scratch)
            if not self._buffer.strip() and (not old_str or old_str == self._buffer):
                self._buffer = new_str
                self._edit_history.append({
                    "old_str": old_str,
                    "new_str": new_str,
                    "line_range": [1, 1],
                })
                return {
                    "success": True,
                    "occurrences_found": 1,
                    "lines_affected": [1, new_str.count("\n") + 1],
                    "new_line_count": self._buffer.count("\n") + 1,
                }

            if not old_str:
                return {
                    "success": False,
                    "error": "old_str cannot be empty. Use read_file_range to get the exact text to replace.",
                    "occurrences_found": 0,
                }

            count = self._buffer.count(old_str)

            if count == 0:
                # Provide diagnostic info to help the LLM self-correct
                # Try to find a close match
                snippet = old_str[:80].replace("\n", "\\n")
                return {
                    "success": False,
                    "error": (
                        f"EXACT MATCH FAILED: The string was not found character-for-character "
                        f"in the buffer. Searched for: \"{snippet}...\"\n"
                        f"Use read_file_range to re-read the exact current content, then retry "
                        f"with the precise text."
                    ),
                    "occurrences_found": 0,
                }

            if count > 1:
                return {
                    "success": False,
                    "error": (
                        f"AMBIGUOUS MATCH: Found {count} occurrences of the target string. "
                        f"Include more surrounding context in old_str to uniquely identify "
                        f"the target location."
                    ),
                    "occurrences_found": count,
                }

            # Exactly one occurrence — safe to replace
            pos = self._buffer.find(old_str)
            line_start = self._buffer[:pos].count("\n") + 1
            line_end = line_start + old_str.count("\n")

            # Track affected chunk IDs
            chunks = self._doc_index.get_chunks(self._buffer)
            for c in chunks:
                if (pos + len(old_str) > c.start_offset) and (pos < c.end_offset):
                    self._touched_chunks.add(c.chunk_id)

            self._buffer = self._buffer.replace(old_str, new_str, 1)

            self._edit_history.append({
                "old_str": old_str,
                "new_str": new_str,
                "line_range": [line_start, line_end],
            })

            return {
                "success": True,
                "occurrences_found": 1,
                "lines_affected": [line_start, line_end],
                "new_line_count": self._buffer.count("\n") + 1,
            }

    def rewrite_chunk(self, chunk_id: str, new_content: str) -> Dict[str, Any]:
        """
        Replaces a chunk's full content using DocumentIndex byte/character offsets.
        This is the preferred tool when operating in full document rewrite mode.
        """
        with self._lock:
            chunks = self._doc_index.get_chunks(self._buffer)
            target = next((c for c in chunks if c.chunk_id == chunk_id), None)
            if not target:
                available_ids = [c.chunk_id for c in chunks]
                return {
                    "success": False,
                    "error": f"Chunk '{chunk_id}' not found in document. Available chunk IDs: {available_ids}",
                    "available_chunks": available_ids,
                }

            updated_code, updated_chunk, delta = self._doc_index.replace_chunk(
                latex_code=self._buffer,
                chunk_id=chunk_id,
                new_content=new_content,
            )
            self._buffer = updated_code
            self._touched_chunks.add(chunk_id)

            line_start = target.start_line
            line_end = line_start + new_content.count("\n")

            self._edit_history.append({
                "chunk_id": chunk_id,
                "old_str": target.content,
                "new_str": new_content,
                "line_range": [line_start, line_end],
            })

            return {
                "success": True,
                "chunk_id": chunk_id,
                "lines_affected": [line_start, line_end],
                "old_length": len(target.content),
                "new_length": len(new_content),
                "new_line_count": self._buffer.count("\n") + 1,
            }

    # ------------------------------------------------------------------
    # Asset operations
    # ------------------------------------------------------------------

    def list_assets(self) -> List[str]:
        """
        Lists files in the project's assets/ directory.

        Returns:
            List of relative file paths (e.g. ``["assets/fig1.png", "assets/data.csv"]``).
        """
        if not self._assets_dir:
            return ["(No assets directory configured for this project)"]

        assets_path = Path(self._assets_dir)
        if not assets_path.exists():
            return [f"(Assets directory not found: {self._assets_dir})"]

        result: List[str] = []
        try:
            for item in sorted(assets_path.rglob("*")):
                if item.is_file():
                    rel = item.relative_to(assets_path.parent)
                    result.append(str(rel))
        except Exception as e:
            result.append(f"(Error listing assets: {e})")

        return result if result else ["(Assets directory is empty)"]

    # ------------------------------------------------------------------
    # State inspection
    # ------------------------------------------------------------------

    def has_changed(self) -> bool:
        """Returns True if the buffer has been modified from the original."""
        with self._lock:
            return self._buffer != self._original

    def get_edit_count(self) -> int:
        """Returns the number of str_replace operations performed."""
        return len(self._edit_history)

    def get_edit_history(self) -> List[Dict[str, Any]]:
        """Returns the full edit history for debugging."""
        return list(self._edit_history)

    def get_touched_chunks(self) -> Set[str]:
        """Returns the set of chunk IDs modified during this session."""
        with self._lock:
            return set(self._touched_chunks)

    def get_document_index(self) -> DocumentIndex:
        """Returns the DocumentIndex instance."""
        return self._doc_index

    def get_all_chunks(self) -> List[DocumentChunk]:
        """Returns all chunks in the current buffer."""
        with self._lock:
            return self._doc_index.get_chunks(self._buffer)

    def get_content_chunks(self) -> List[DocumentChunk]:
        """Returns all content chunks (chapters/sections/frames) in the current buffer."""
        with self._lock:
            return self._doc_index.get_content_chunks(self._buffer)
