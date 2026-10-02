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
        session_id: Optional[str] = None,
    ):
        self._original: str = original_code
        self._buffer: str = original_code
        self._project_id: str = project_id
        self._file_path: str = file_path
        self._assets_dir: Optional[str] = assets_dir
        self._session_id: str = session_id or project_id or "default"
        self._lock = threading.Lock()
        self._edit_history: List[Dict[str, Any]] = []
        self._doc_index = DocumentIndex()
        self._touched_chunks: Set[str] = set()

        # Multi-file support: auxiliary .tex files in the same project
        # Keys are relative file paths (e.g. "chapters/intro.tex")
        self._aux_files: Dict[str, str] = {}           # current state
        self._aux_originals: Dict[str, str] = {}       # frozen originals
        self._aux_edit_history: Dict[str, List[Dict[str, Any]]] = {}

        # Attached reference files (PDFs, papers, source documents) — read-only
        self._reference_files: Dict[str, str] = {}

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def file_path(self) -> str:
        return self._file_path

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

    def insert_into_chunk(
        self,
        chunk_id: str,
        content: str,
        position: str = "end",
    ) -> Dict[str, Any]:
        """
        Inserts content into a specific document chunk.

        When position="end" (default):
          - If the chunk contains \\end{thebibliography}, inserts BEFORE \\end{thebibliography}.
          - If content contains \\item or \\bibitem and the chunk contains a list environment,
            inserts BEFORE the closing list tag.
          - If the chunk contains \\end{frame}, inserts BEFORE \\end{frame}.
          - Otherwise, inserts at the end of the chunk content.

        When position="begin":
          - Inserts after the opening section/chapter/frame/environment declaration line.
          - Otherwise, inserts at the start of the chunk.
        """
        with self._lock:
            chunks = self._doc_index.get_chunks(self._buffer)
            target = next((c for c in chunks if c.chunk_id == chunk_id), None)

            # Fallback alias search for bibliography / references
            if not target and chunk_id.lower() in ("bibliography", "references", "bib", "refs", "biblio"):
                target = next(
                    (c for c in chunks if r"\begin{thebibliography}" in c.content or r"\end{thebibliography}" in c.content),
                    None
                )

            if not target:
                available_ids = [c.chunk_id for c in chunks]
                return {
                    "success": False,
                    "error": f"Chunk '{chunk_id}' not found in document. Available chunk IDs: {available_ids}",
                    "available_chunks": available_ids,
                }

            chunk_text = self._buffer[target.start_offset:target.end_offset]
            pos_in_chunk = None
            cleaned_content = content.strip("\r\n")

            if position == "end":
                # 1. Check for thebibliography environment
                bib_end_match = re.search(r"\\end\{thebibliography\}", chunk_text)
                if bib_end_match:
                    pos_in_chunk = bib_end_match.start()
                # 2. Check for itemize / enumerate / description if inserting an item
                elif (cleaned_content.startswith(r"\item") or cleaned_content.startswith(r"\bibitem")) and re.search(r"\\end\{(?:itemize|enumerate|description)\}", chunk_text):
                    list_end_matches = list(re.finditer(r"\\end\{(?:itemize|enumerate|description)\}", chunk_text))
                    if list_end_matches:
                        pos_in_chunk = list_end_matches[-1].start()
                # 3. Check for beamer frame
                elif re.search(r"\\end\{frame\}", chunk_text):
                    frame_end_match = re.search(r"\\end\{frame\}", chunk_text)
                    if frame_end_match:
                        pos_in_chunk = frame_end_match.start()
                else:
                    # Insert at end of chunk (before trailing whitespace/newline)
                    rstrip_len = len(chunk_text) - len(chunk_text.rstrip())
                    pos_in_chunk = len(chunk_text) - rstrip_len

            elif position == "begin":
                # Find the header/opening line of the chunk
                header_match = re.search(
                    r"^(?:\\(?:chapter|section|subsection|subsubsection)\*?\{[^}]*\}|\\begin\{(?:frame|thebibliography)\}(?:\[[^\]]*\])?(?:\{[^}]*\})?)",
                    chunk_text,
                    re.MULTILINE
                )
                if header_match:
                    line_end = chunk_text.find("\n", header_match.end())
                    pos_in_chunk = (line_end + 1) if line_end != -1 else header_match.end()
                else:
                    pos_in_chunk = 0
            else:
                return {
                    "success": False,
                    "error": f"Invalid position '{position}'. Must be 'end' or 'begin'.",
                }

            if pos_in_chunk is None:
                pos_in_chunk = len(chunk_text)

            abs_pos = target.start_offset + pos_in_chunk

            # Prepare text with appropriate newlines
            prefix = ""
            suffix = ""

            if abs_pos > 0 and self._buffer[abs_pos - 1] != "\n":
                prefix = "\n"
            if abs_pos < len(self._buffer) and not self._buffer[abs_pos:].startswith("\n"):
                suffix = "\n"

            to_insert = prefix + cleaned_content + suffix

            self._buffer = self._buffer[:abs_pos] + to_insert + self._buffer[abs_pos:]
            self._touched_chunks.add(target.chunk_id)

            line_start = self._buffer[:abs_pos].count("\n") + 1
            line_end = line_start + to_insert.count("\n")

            self._edit_history.append({
                "chunk_id": target.chunk_id,
                "operation": "insert_into_chunk",
                "position": position,
                "inserted": to_insert,
                "line_range": [line_start, line_end],
            })

            return {
                "success": True,
                "chunk_id": target.chunk_id,
                "position": position,
                "lines_affected": [line_start, line_end],
                "inserted_length": len(to_insert),
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
        """Returns True if any buffer (main or auxiliary) has been modified."""
        with self._lock:
            if self._buffer != self._original:
                return True
            for fpath, content in self._aux_files.items():
                if content != self._aux_originals.get(fpath, ""):
                    return True
            return False

    def get_edit_count(self) -> int:
        """Returns the total number of edit operations across all files."""
        total = len(self._edit_history)
        for hist in self._aux_edit_history.values():
            total += len(hist)
        return total

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

    # ------------------------------------------------------------------
    # Multi-file operations
    # ------------------------------------------------------------------

    def add_auxiliary_file(self, file_path: str, content: str) -> None:
        """Registers an auxiliary .tex file in the workspace."""
        with self._lock:
            self._aux_files[file_path] = content
            if file_path not in self._aux_originals:
                self._aux_originals[file_path] = content
            if file_path not in self._aux_edit_history:
                self._aux_edit_history[file_path] = []

    def get_auxiliary_file(self, file_path: str) -> Optional[str]:
        """Returns the current content of an auxiliary file, or None."""
        with self._lock:
            return self._aux_files.get(file_path)

    def get_file_list(self) -> List[Dict[str, Any]]:
        """Returns a list of all files in the workspace with metadata."""
        with self._lock:
            files = [{
                "path": self._file_path,
                "lines": len(self._buffer.splitlines()),
                "chars": len(self._buffer),
                "is_main": True,
                "modified": self._buffer != self._original,
            }]
            for fpath, content in self._aux_files.items():
                orig = self._aux_originals.get(fpath, "")
                files.append({
                    "path": fpath,
                    "lines": len(content.splitlines()),
                    "chars": len(content),
                    "is_main": False,
                    "modified": content != orig,
                })
            for rpath, content in self._reference_files.items():
                files.append({
                    "path": rpath,
                    "lines": len(content.splitlines()),
                    "chars": len(content),
                    "is_main": False,
                    "is_reference": True,
                    "read_only": True,
                    "modified": False,
                })
            return files

    def add_reference_file(self, file_path: str, content: str) -> None:
        """Registers a read-only attached reference file (PDF, paper, etc.) in the workspace."""
        with self._lock:
            self._reference_files[file_path] = content

    def get_reference_file(self, file_path: str) -> Optional[str]:
        """Returns the content of an attached reference file, or None."""
        with self._lock:
            return self._reference_files.get(file_path)

    def get_reference_files(self) -> Dict[str, str]:
        """Returns all attached reference files."""
        with self._lock:
            return dict(self._reference_files)

    def read_file_lines(self, file_path: str, start_line: int, end_line: int) -> str:
        """Read lines from a specific file (main or auxiliary)."""
        content = self._resolve_file_content(file_path)
        if content is None:
            return f"(File '{file_path}' not found in workspace)"

        lines = content.splitlines(keepends=False)
        total = len(lines)
        start = max(1, start_line)
        end = min(total, end_line)
        if start > total:
            return f"(No content — file has {total} lines, requested start={start_line})"

        result_parts: list[str] = []
        for i in range(start - 1, end):
            result_parts.append(f"{i + 1}: {lines[i]}")
        return "\n".join(result_parts)

    def grep_file(self, file_path: str, pattern: str, is_regex: bool = False) -> List[Dict[str, Any]]:
        """Search a specific file for a pattern."""
        content = self._resolve_file_content(file_path)
        if content is None:
            return [{"error": f"File '{file_path}' not found in workspace"}]

        lines = content.splitlines(keepends=False)
        results: List[Dict[str, Any]] = []
        try:
            compiled = re.compile(pattern if is_regex else re.escape(pattern))
        except re.error as e:
            return [{"error": f"Invalid regex: {e}"}]

        for idx, line in enumerate(lines, start=1):
            m = compiled.search(line)
            if m:
                results.append({"file": file_path, "line_no": idx, "content": line, "match": m.group(0)})
                if len(results) >= 50:
                    results.append({"truncated": True})
                    break
        return results

    def str_replace_file(self, file_path: str, old_str: str, new_str: str) -> Dict[str, Any]:
        """Exact string replacement in a specific auxiliary file."""
        with self._lock:
            if file_path in self._reference_files:
                return {
                    "success": False,
                    "error": (
                        f"Cannot modify '{file_path}': attached reference documents are read-only sources. "
                        f"Apply your edits to LaTeX document files (e.g. {self._file_path}) using str_replace."
                    ),
                }

            if file_path == self._file_path or file_path == "main.tex":
                # Delegate to the main buffer's str_replace (unlocked internally)
                pass  # Fall through — caller should use str_replace() instead
            if file_path not in self._aux_files:
                return {"success": False, "error": f"File '{file_path}' not found in workspace"}

            buf = self._aux_files[file_path]
            count = buf.count(old_str)
            if count == 0:
                return {"success": False, "error": "EXACT MATCH FAILED in auxiliary file", "occurrences_found": 0}
            if count > 1:
                return {"success": False, "error": f"AMBIGUOUS MATCH: {count} occurrences", "occurrences_found": count}

            pos = buf.find(old_str)
            line_start = buf[:pos].count("\n") + 1
            line_end = line_start + old_str.count("\n")
            self._aux_files[file_path] = buf.replace(old_str, new_str, 1)
            self._aux_edit_history.setdefault(file_path, []).append({
                "old_str": old_str, "new_str": new_str, "line_range": [line_start, line_end],
            })
            return {"success": True, "file": file_path, "lines_affected": [line_start, line_end]}

    def get_all_modified_files(self) -> Dict[str, Tuple[str, str]]:
        """Returns {file_path: (original, modified)} for all changed files."""
        result: Dict[str, Tuple[str, str]] = {}
        with self._lock:
            if self._buffer != self._original:
                result[self._file_path] = (self._original, self._buffer)
            for fpath, content in self._aux_files.items():
                orig = self._aux_originals.get(fpath, "")
                if content != orig:
                    result[fpath] = (orig, content)
        return result

    def _resolve_file_content(self, file_path: str) -> Optional[str]:
        """Resolves file content from main buffer, aux files, or reference files."""
        with self._lock:
            if file_path == self._file_path or file_path == "main.tex":
                return self._buffer
            if file_path in self._aux_files:
                return self._aux_files[file_path]
            if file_path in self._reference_files:
                return self._reference_files[file_path]
            # Match by basename or case-insensitive for attached documents
            fp_lower = file_path.lower()
            for rpath, content in self._reference_files.items():
                rp_lower = rpath.lower()
                if (
                    rp_lower == fp_lower
                    or rp_lower.endswith("/" + fp_lower)
                    or fp_lower.endswith("/" + rp_lower)
                ):
                    return content
            return None
