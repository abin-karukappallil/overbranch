"""
opencode/shadow_workspace.py — Thread-Safe In-Memory Shadow Buffer
===================================================================
Provides a ShadowWorkspace that holds an exact copy of the user's main.tex
in memory. All agent edits operate on this buffer — never on disk.

Thread-safe via threading.Lock so multiple concurrent agent runs are isolated.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from document_index import DocumentChunk, DocumentIndex, ensure_document_environment

logger = logging.getLogger("shadow_workspace")


class ShadowWorkspaceError(Exception):
    """Raised when a shadow workspace operation fails (e.g. str_replace mismatch)."""
    pass


_RE_LINE_NO_PREFIX = re.compile(r"^\s*(\d+): ?")


def _strip_line_number_prefixes(text: str) -> Optional[str]:
    """
    ``text`` without the ``N: `` prefixes that read_file_range / get_block put on
    every line, when every non-empty line carries one and the numbers are
    consecutive (models copy them into old_str/new_str); otherwise None.
    """
    if not text:
        return None
    lines = text.split("\n")
    numbers = []
    for ln in lines:
        if not ln.strip():
            continue
        m = _RE_LINE_NO_PREFIX.match(ln)
        if not m:
            return None
        numbers.append(int(m.group(1)))
    if not numbers or any(b != a + 1 for a, b in zip(numbers, numbers[1:])):
        return None
    return "\n".join(_RE_LINE_NO_PREFIX.sub("", ln, count=1) if ln.strip() else ln for ln in lines)


def _match_trailing_newline(new_str: str, matched: str, following: str) -> str:
    """
    Gives ``new_str`` the trailing newline the replaced text had. A replacement
    of ``line\\n`` by ``line`` merged it with the next line — and a trailing
    ``% comment`` in new_str then commented that line out; the reverse inserted a
    blank line, which ends a paragraph and breaks a tabular.
    """
    if not new_str:
        return new_str
    if matched.endswith("\n") and not new_str.endswith("\n"):
        return new_str + "\n"
    if not matched.endswith("\n") and new_str.endswith("\n") and following.startswith("\n"):
        return new_str[:-1]
    return new_str


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
        base_version: Optional[int] = None,
        base_sha256: Optional[str] = None,
    ):
        self._original: str = original_code
        self._buffer: str = ensure_document_environment(original_code)
        self._snapshots: List[str] = []
        self._project_id: str = project_id
        self._file_path: str = file_path
        self._assets_dir: Optional[str] = assets_dir
        self._session_id: str = session_id or project_id or "default"
        self._base_version: Optional[int] = base_version
        self._base_sha256: Optional[str] = base_sha256
        self._lock = threading.RLock()
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

        # Stable node IDs that changed because an op edited the node's own title:
        # old_id -> new_id, so an ID the model already holds keeps working.
        self._node_aliases: Dict[str, str] = {}
        self._lines = self._buffer.splitlines(keepends=True)

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def file_path(self) -> str:
        return self._file_path

    @property
    def base_version(self) -> Optional[int]:
        return self._base_version

    @property
    def base_sha256(self) -> Optional[str]:
        return self._base_sha256

    # ------------------------------------------------------------------
    # Snapshot & Undo operations
    # ------------------------------------------------------------------

    def push_snapshot(self) -> None:
        """Saves a snapshot of the current buffer before an edit."""
        self._snapshots.append(self._buffer)
        if len(self._snapshots) > 50:
            self._snapshots.pop(0)

    def undo(self) -> bool:
        """Restores the shadow buffer to the previous snapshot."""
        with self._lock:
            if self._snapshots:
                self._buffer = self._snapshots.pop()
                self._lines = self._buffer.splitlines(keepends=True)
                try:
                    self._doc_index = DocumentIndex.from_latex_text(self._buffer)
                except Exception:
                    pass
                return True
            return False

    def get_snapshot_count(self) -> int:
        return len(self._snapshots)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_original(self) -> str:
        """Returns the frozen original code (never mutated)."""
        return self._original

    def get_buffer(self) -> str:
        """
        Returns the current state of the shadow buffer.

        Pure by design: reads must never mutate. The buffer is normalised once in
        __init__ and again after every write, so re-normalising here only cost
        CPU on every read (reads are frequent: coverage, compile, diff, grep) and
        mutated structure outside any validated path.
        """
        with self._lock:
            return self._buffer

    def _refresh_indexes(self) -> None:
        """
        Re-derives the cached line list and chunk index from the buffer.

        This is the post-commit half of ensure_document_structure, without the
        heal. Writes already heal *before* validating, so healing again after the
        commit both doubled the cost of every edit and mutated the buffer after
        it had been validated — balance_latex_environments can delete orphan
        \\end{env} lines and inject closers, and nothing re-checked the result.
        """
        with self._lock:
            self._lines = self._buffer.splitlines(keepends=True)
            try:
                self._doc_index = DocumentIndex.from_latex_text(self._buffer)
            except Exception:
                pass

    def _heal_and_validate(
        self,
        candidate: str,
        baseline: Optional[str] = None,
    ) -> Tuple[bool, str, List[str], List[str]]:
        """
        Runs the shared write gate: *scoped* deterministic heal, then
        *differential* pre-commit validation against ``baseline`` (the buffer
        before the edit), then the duplicate-block guard.

        Validation is differential on purpose. Every write validates the whole
        buffer, so an absolute check lets a single defect the validator cannot
        model -- a list environment defined in a .cls, an \\end{...} its grammar
        cannot pair -- reject every edit for the rest of the run. Only defects
        the edit *adds* are the edit's fault, so only those block it.

        Healing is scoped for the same reason: repairs are kept only on the lines
        the edit changed (see edit_guard.scoped_heal), so a defect the user
        already had elsewhere is never "fixed" as a side effect of this edit.
        A heal that makes validation worse is dropped.

        Returns ``(ok, committed_candidate, new_errors, fixes_applied)``.
        """
        from edit_validator import validate_edit
        from .edit_guard import introduced_duplicates, scoped_heal

        before = self._original if baseline is None else baseline

        def check(code: str) -> Tuple[bool, List[str]]:
            try:
                return validate_edit(before, code)
            except Exception as e:
                logger.warning(f"validate_edit failed, falling back to absolute check: {e}")
                from edit_validator import validate_latex_pre_commit
                return validate_latex_pre_commit(code)

        ok, errors = check(candidate)
        fixes: List[str] = []
        try:
            healed, heal_fixes, _trimmed = scoped_heal(before, candidate)
        except Exception as e:
            logger.warning(f"scoped heal during write: {e}")
            healed, heal_fixes = candidate, []
        if healed != candidate:
            ok_h, errors_h = check(healed)
            if ok_h:
                candidate, ok, errors, fixes = healed, True, [], heal_fixes
            elif not ok and len(errors_h) < len(errors):
                errors = errors_h

        if ok:
            try:
                dups = introduced_duplicates(before, candidate)
            except Exception as e:
                logger.warning(f"duplicate check failed: {e}")
                dups = []
            if dups:
                ok = False
                errors = [f"Duplicate block: the edit makes `{d}` appear twice. Edit the existing block instead "
                          f"of inserting a copy." for d in dups]

        return ok, candidate, errors, fixes

    def ensure_document_structure(self) -> None:
        """Verifies and auto-repairs missing \\begin{document}, \\end{document}, unclosed frames, and syntax errors."""
        with self._lock:
            try:
                from latex_error_fixer import auto_heal_latex_code
                self._buffer, _ = auto_heal_latex_code(self._buffer)
            except Exception as e:
                logger.warning(f"auto_heal_latex_code in ensure_document_structure: {e}")
                self._buffer = ensure_document_environment(self._buffer)
            self._lines = self._buffer.splitlines(keepends=True)
            try:
                self._doc_index = DocumentIndex.from_latex_text(self._buffer)
            except Exception:
                pass

    def heal_touched(self) -> List[str]:
        """
        Applies deterministic repairs to the lines the agent changed (relative to
        the original) and nowhere else, through the normal write gate. Used
        before compiling, in place of healing the whole buffer.
        """
        from .edit_guard import scoped_heal
        with self._lock:
            healed, fixes, _ = scoped_heal(self._original, self._buffer)
            if healed == self._buffer:
                return []
            ok, healed, _errors, _ = self._heal_and_validate(healed, baseline=self._buffer)
            if not ok:
                return []
            self.push_snapshot()
            self._buffer = healed
            self._refresh_indexes()
            return fixes

    def replace_all(self, new_content: str) -> Dict[str, Any]:
        """Replaces the entire shadow buffer with new content after pre-commit validation."""
        from latex_error_fixer import sanitize_edit_latex
        new_content = sanitize_edit_latex(new_content)
        with self._lock:
            passed, healed, errors, _ = self._heal_and_validate(new_content)
            if not passed:
                return {
                    "success": False,
                    "error": (
                        f"PRE-COMMIT VALIDATION FAILED: The proposed document has structural LaTeX errors:\n"
                        + "\n".join(f"  - {e}" for e in errors[:5])
                        + "\nThe buffer was NOT modified. Please fix these errors and retry."
                    ),
                    "validation_errors": errors,
                }
            self.push_snapshot()
            self._buffer = healed
            self._refresh_indexes()
            self._edit_history.append({
                "action": "replace_all",
                "length": len(self._buffer),
            })
            return {"success": True, "length": len(self._buffer)}

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

    def str_replace(
        self,
        old_str: str,
        new_str: str,
        line_hint: Optional[int] = None,
        node_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Replaces the text ``old_str`` refers to.

        Exact matching comes first, so behaviour is unchanged whenever the model
        copied the text faithfully. When it did not (re-indented, normalised
        quotes, a neighbouring edit changed a word), the locator falls back to
        context / line-hint disambiguation, normalised matching and finally a
        strict fuzzy match (see opencode/locator.py). Text that cannot be found
        confidently is never guessed at: the failure says what was tried and
        shows the region, so the model can correct the patch in one turn.

        Args:
            old_str: The exact string to find in the buffer.
            new_str: The replacement string.

        Returns:
            ``{success: bool, occurrences_found: int, lines_affected: [int, int]}``

        Raises:
            ShadowWorkspaceError: If ``old_str`` is not found in the buffer.
        """
        with self._lock:
            from latex_error_fixer import sanitize_edit_latex
            new_str = sanitize_edit_latex(new_str)
            # Handle empty buffer initialization (e.g. creating brand new document
            # from scratch). This is the single largest write in the system, so it
            # gets the same heal + validate + snapshot treatment as every other
            # write path — without the snapshot, the final rollback loop in
            # agent_loop has an empty stack and discards the whole new document.
            if not self._buffer.strip() and (not old_str or old_str == self._buffer):
                # A brand new document has no baseline to be fair to, so it is
                # held to the absolute standard.
                is_valid, candidate, validation_errors, _ = self._heal_and_validate(
                    new_str, baseline=""
                )
                if not is_valid:
                    return {
                        "success": False,
                        "error": (
                            "PRE-COMMIT VALIDATION FAILED: The new document has structural "
                            "LaTeX errors:\n"
                            + "\n".join(f"  - {e}" for e in validation_errors[:5])
                            + "\nThe buffer was NOT modified. Please fix these errors and retry."
                        ),
                        "validation_errors": validation_errors,
                    }

                self.push_snapshot()
                self._buffer = candidate
                self._edit_history.append({
                    "old_str": old_str,
                    "new_str": candidate,
                    "line_range": [1, 1],
                })
                return {
                    "success": True,
                    "occurrences_found": 1,
                    "lines_affected": [1, candidate.count("\n") + 1],
                    "new_line_count": self._buffer.count("\n") + 1,
                }

            if not old_str:
                return {
                    "success": False,
                    "error": "old_str cannot be empty. Use read_file_range to get the exact text to replace.",
                    "occurrences_found": 0,
                }

            from .locator import Target, resolve

            # Line numbers copied from read_file_range output ("12: \item ...").
            unprefixed_old = _strip_line_number_prefixes(old_str)
            if unprefixed_old is not None and old_str not in self._buffer and unprefixed_old in self._buffer:
                old_str = unprefixed_old
                unprefixed_new = _strip_line_number_prefixes(new_str)
                if unprefixed_new is not None:
                    new_str = unprefixed_new

            res = resolve(self._buffer, Target(node_id=node_id, text=old_str, line_hint=line_hint),
                          aliases=self._node_aliases)
            if not res.ok:
                return self._failure("replace_text", {"text": old_str[:120], "node_id": node_id,
                                                      "line_hint": line_hint}, res)
            pos, span_end = res.start, res.end
            matched = self._buffer[pos:span_end]
            line_start = self._buffer[:pos].count("\n") + 1
            line_end = line_start + matched.count("\n")
            new_str = _match_trailing_newline(new_str, matched, self._buffer[span_end:])

            candidate = self._buffer[:pos] + new_str + self._buffer[span_end:]

            is_valid, candidate, validation_errors, heal_fixes = self._heal_and_validate(
                candidate, baseline=self._buffer
            )
            if not is_valid:
                error_lines = "\n".join(f"  - {e}" for e in validation_errors[:5])
                return {
                    "success": False,
                    "error": (
                        f"PRE-COMMIT VALIDATION FAILED: The proposed edit introduces structural LaTeX errors:\n"
                        f"{error_lines}\n"
                        f"The buffer was NOT modified. Please fix these environment/delimiter mismatches and retry."
                    ),
                    "validation_errors": validation_errors,
                    "occurrences_found": 1,
                }

            # Track affected chunk IDs
            chunks = self._doc_index.get_chunks(self._buffer)
            for c in chunks:
                if (span_end > c.start_offset) and (pos < c.end_offset):
                    self._touched_chunks.add(c.chunk_id)

            self.push_snapshot()
            self._buffer = candidate
            self._refresh_indexes()

            self._edit_history.append({
                "old_str": matched,
                "new_str": new_str,
                "line_range": [line_start, line_end],
                "op": "replace_text",
                "method": res.method,
                "node_id": res.node_id,
            })

            result = {
                "success": True,
                "occurrences_found": 1,
                "method": res.method,
                "node_id": res.node_id,
                "lines_affected": [line_start, line_end],
                "new_line_count": self._buffer.count("\n") + 1,
            }
            if heal_fixes:
                # The buffer now differs from what the model wrote; say how, so its
                # next old_str is copied from what is really there.
                result["auto_repairs"] = heal_fixes
            return result

    def rewrite_chunk(self, chunk_id: str, new_content: str) -> Dict[str, Any]:
        """
        Replaces a chunk's full content using DocumentIndex byte/character offsets.
        This is the preferred tool when operating in full document rewrite mode.
        """
        from latex_error_fixer import sanitize_edit_latex
        new_content = sanitize_edit_latex(new_content)
        with self._lock:
            chunks = self._doc_index.get_chunks(self._buffer)
            target = next((c for c in chunks if c.chunk_id == chunk_id), None)
            if not target:
                # A stable node ID (sec:results, frame:overview) works here too.
                if self.resolve_node(chunk_id) is not None:
                    return self.replace_block(chunk_id, new_content)
                available_ids = [c.chunk_id for c in chunks]
                return {
                    "success": False,
                    "error": f"Chunk '{chunk_id}' not found in document. Available chunk IDs: {available_ids}",
                    "available_chunks": available_ids,
                    "document_unchanged": True,
                }

            updated_code, updated_chunk, delta = self._doc_index.replace_chunk(
                latex_code=self._buffer,
                chunk_id=chunk_id,
                new_content=new_content,
            )

            is_valid, updated_code, validation_errors, heal_fixes = self._heal_and_validate(
                updated_code, baseline=self._buffer
            )
            if not is_valid:
                error_lines = "\n".join(f"  - {e}" for e in validation_errors[:5])
                return {
                    "success": False,
                    "error": (
                        f"PRE-COMMIT VALIDATION FAILED on chunk '{chunk_id}':\n"
                        f"{error_lines}\n"
                        f"The buffer was NOT modified. Please ensure all environments and delimiters are closed within the chunk."
                    ),
                    "validation_errors": validation_errors,
                }

            self.push_snapshot()
            self._buffer = updated_code
            self._refresh_indexes()
            self._touched_chunks.add(chunk_id)

            line_start = target.start_line
            line_end = line_start + new_content.count("\n")

            self._edit_history.append({
                "chunk_id": chunk_id,
                "old_str": target.content,
                "new_str": new_content,
                "line_range": [line_start, line_end],
            })

            result = {
                "success": True,
                "chunk_id": chunk_id,
                "lines_affected": [line_start, line_end],
                "old_length": len(target.content),
                "new_length": len(new_content),
                "new_line_count": self._buffer.count("\n") + 1,
            }
            if heal_fixes:
                result["auto_repairs"] = heal_fixes
            return result

    def insert_into_chunk(
        self,
        chunk_id: str,
        content: str,
        position: str = "end",
    ) -> Dict[str, Any]:
        """
        Inserts content into a specific document chunk.
        """
        from latex_error_fixer import sanitize_edit_latex
        content = sanitize_edit_latex(content)
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
                node = self.resolve_node(chunk_id)
                if node is not None:
                    return self.insert_block(chunk_id, content, "start" if position == "begin" else "end")
                available_ids = [c.chunk_id for c in chunks]
                return {
                    "success": False,
                    "error": f"Chunk '{chunk_id}' not found in document. Available chunk IDs: {available_ids}",
                    "available_chunks": available_ids,
                    "document_unchanged": True,
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
            candidate = self._buffer[:abs_pos] + to_insert + self._buffer[abs_pos:]

            is_valid, candidate, validation_errors, heal_fixes = self._heal_and_validate(
                candidate, baseline=self._buffer
            )
            if not is_valid:
                error_lines = "\n".join(f"  - {e}" for e in validation_errors[:5])
                return {
                    "success": False,
                    "error": (
                        f"PRE-COMMIT VALIDATION FAILED on insert into '{target.chunk_id}':\n"
                        f"{error_lines}\n"
                        f"The buffer was NOT modified. Please ensure the inserted LaTeX is structurally balanced."
                    ),
                    "validation_errors": validation_errors,
                }

            self.push_snapshot()
            self._buffer = candidate
            self._refresh_indexes()
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

            result = {
                "success": True,
                "chunk_id": target.chunk_id,
                "position": position,
                "lines_affected": [line_start, line_end],
                "inserted_length": len(to_insert),
                "new_line_count": self._buffer.count("\n") + 1,
            }
            if heal_fixes:
                result["auto_repairs"] = heal_fixes
            return result

    # ------------------------------------------------------------------
    # Structural (node-addressed) operations
    # ------------------------------------------------------------------

    def get_nodes(self) -> List[Any]:
        """Structural nodes of the current buffer (stable IDs, see document_index)."""
        from document_index import index_nodes
        with self._lock:
            return index_nodes(self._buffer)

    def resolve_node(self, ref: str) -> Optional[Any]:
        from .locator import resolve_node
        with self._lock:
            return resolve_node(self._buffer, ref, self._node_aliases)

    def get_block(self, ref: str, include_parent: bool = False, include_style: bool = False) -> Dict[str, Any]:
        """Content of one node, optionally with its parent's header and the preamble lines styling it."""
        with self._lock:
            node = self.resolve_node(ref)
            if node is None:
                return self._node_not_found("get_block", ref)
            text = self._buffer[node.start:node.end]
            out: Dict[str, Any] = {
                "node_id": node.node_id, "kind": node.kind, "title": node.title,
                "lines": [node.start_line, node.end_line],
                "content": self.read_lines(node.start_line, node.end_line),
                "chars": len(text),
            }
            if include_parent and node.parent_id:
                parent = self.resolve_node(node.parent_id)
                if parent:
                    out["parent"] = {"node_id": parent.node_id, "kind": parent.kind, "title": parent.title,
                                     "lines": [parent.start_line, parent.end_line],
                                     "header": self.read_lines(parent.start_line, parent.start_line)}
            if include_style:
                from .context_builder import style_lines_for
                out["style"] = style_lines_for(self._buffer, text)
            return out

    def replace_block(self, ref: str, new_content: str) -> Dict[str, Any]:
        """Replaces a whole node (heading + body, or \\begin..\\end) by stable ID."""
        with self._lock:
            node = self.resolve_node(ref)
            if node is None:
                return self._node_not_found("replace_block", ref)
            return self._splice(node.start, node.end, new_content, op="replace_block", node=node)

    def insert_block(self, ref: str, content: str, position: str = "after") -> Dict[str, Any]:
        """
        Inserts ``content`` relative to a node: ``before`` / ``after`` the node,
        or at the ``start`` / ``end`` of its body (inside \\begin..\\end, after a
        heading line).
        """
        with self._lock:
            node = self.resolve_node(ref)
            if node is None:
                return self._node_not_found("insert_block", ref)
            pos = {"before": node.start, "after": node.end, "start": node.body_start,
                   "end": node.body_end}.get(position)
            if pos is None:
                return {"success": False, "error": f"Invalid position '{position}'. Use before, after, start or end."}
            text = content.strip("\r\n")
            prefix = "" if pos == 0 or self._buffer[pos - 1] == "\n" else "\n"
            suffix = "" if self._buffer[pos:pos + 1] == "\n" else "\n"
            return self._splice(pos, pos, prefix + text + suffix, op=f"insert_block:{position}", node=node)

    def delete_block(self, ref: str) -> Dict[str, Any]:
        with self._lock:
            node = self.resolve_node(ref)
            if node is None:
                return self._node_not_found("delete_block", ref)
            if node.kind in ("preamble",):
                return {"success": False, "error": "The preamble cannot be deleted."}
            end = node.end
            if self._buffer[end:end + 1] == "\n":
                end += 1
            return self._splice(node.start, end, "", op="delete_block", node=node)

    def _splice(self, start: int, end: int, new_text: str, op: str, node: Any = None,
                method: str = "node") -> Dict[str, Any]:
        """Applies one span replacement through the shared write gate."""
        from latex_error_fixer import sanitize_edit_latex
        new_text = sanitize_edit_latex(new_text)
        baseline = self._buffer
        candidate = baseline[:start] + new_text + baseline[end:]
        ok, candidate, errors, fixes = self._heal_and_validate(candidate, baseline=baseline)
        if not ok:
            line = baseline[:start].count("\n") + 1
            return {
                "success": False,
                "failed_op": op,
                "target": getattr(node, "node_id", None),
                "error": "PRE-COMMIT VALIDATION FAILED: the edit introduces structural LaTeX errors:\n"
                         + "\n".join(f"  - {e}" for e in errors[:5])
                         + "\nThe buffer was NOT modified.",
                "validation_errors": errors,
                "document_unchanged": True,
                "region_excerpt": self._excerpt(line),
            }

        line_start = baseline[:start].count("\n") + 1
        old_text = baseline[start:end]
        for c in self._doc_index.get_chunks(baseline):
            if end >= c.start_offset and start < c.end_offset:
                self._touched_chunks.add(c.chunk_id)

        self.push_snapshot()
        self._buffer = candidate
        self._refresh_indexes()
        new_id = None
        if node is not None and op == "replace_block":
            new_id = self._carry_node_id(node, start)
        self._edit_history.append({
            "op": op, "method": method, "node_id": getattr(node, "node_id", None),
            "old_str": old_text, "new_str": new_text,
            "line_range": [line_start, line_start + new_text.count("\n")],
        })
        result: Dict[str, Any] = {
            "success": True,
            "op": op,
            "method": method,
            "node_id": new_id or getattr(node, "node_id", None),
            "lines_affected": [line_start, line_start + new_text.count("\n")],
            "new_line_count": self._buffer.count("\n") + 1,
        }
        if fixes:
            result["auto_repairs"] = fixes
        return result

    def _carry_node_id(self, old_node: Any, start: int) -> Optional[str]:
        """After a node was replaced, keeps its old ID pointing at the new node."""
        from document_index import index_nodes
        for n in index_nodes(self._buffer):
            if n.start == start and n.kind == old_node.kind:
                if n.node_id != old_node.node_id:
                    self._node_aliases[old_node.node_id] = n.node_id
                return n.node_id
        return None

    def _excerpt(self, line: Optional[int], radius: int = 20) -> str:
        from .edit_guard import region_excerpt
        return region_excerpt(self._buffer, line, radius)

    def _node_not_found(self, op: str, ref: str) -> Dict[str, Any]:
        from document_index import index_nodes
        ids = [n.node_id for n in index_nodes(self._buffer) if n.kind != "env"][:40]
        return {
            "success": False,
            "failed_op": op,
            "target": ref,
            "error": f"Node '{ref}' not found. Use one of the node IDs from inspect_document: {ids}",
            "available_nodes": ids,
            "document_unchanged": True,
        }

    def _failure(self, op: str, target: Dict[str, Any], res: Any) -> Dict[str, Any]:
        """Structured failure for a text target the locator could not resolve."""
        line = target.get("line_hint")
        if not line and res.node_id:
            node = self.resolve_node(res.node_id)
            line = node.start_line if node else None
        reason = res.reason or "target_not_found"
        if reason == "ambiguous":
            msg = ("AMBIGUOUS MATCH: the text occurs more than once and the location could not be decided. "
                   "Pass node_id or line_hint, or include more surrounding text.")
        else:
            msg = ("TARGET NOT FOUND: the text was not found exactly, after normalising whitespace/quotes, or by "
                   "similarity. Re-read the region below (or use get_block/search_document) and retry with "
                   "the current text, or address the block by node_id.")
        return {
            "success": False,
            "failed_op": op,
            "target": target,
            "error": msg,
            "reason": reason,
            "attempts": res.attempts,
            "occurrences_found": 0 if reason != "ambiguous" else 2,
            "document_unchanged": True,
            "region_excerpt": self._excerpt(line) if line else "",
        }

    # ------------------------------------------------------------------
    # Transactions
    # ------------------------------------------------------------------

    def begin_transaction(self) -> Dict[str, Any]:
        """Captures everything an edit batch can change, for an all-or-nothing rollback."""
        with self._lock:
            return {
                "buffer": self._buffer,
                "aux": dict(self._aux_files),
                "touched": set(self._touched_chunks),
                "history": len(self._edit_history),
                "snapshots": len(self._snapshots),
                "aliases": dict(self._node_aliases),
            }

    def rollback_transaction(self, tx: Dict[str, Any]) -> None:
        with self._lock:
            self._buffer = tx["buffer"]
            self._aux_files = dict(tx["aux"])
            self._touched_chunks = set(tx["touched"])
            del self._edit_history[tx["history"]:]
            del self._snapshots[tx["snapshots"]:]
            self._node_aliases = dict(tx["aliases"])
            self._refresh_indexes()

    def rollback_last(self) -> Dict[str, Any]:
        """Undoes the most recent successful edit (the agent's rollback_edit tool)."""
        with self._lock:
            if not self._snapshots:
                return {"success": False, "error": "Nothing to roll back."}
            last = self._edit_history.pop() if self._edit_history else {}
            self.undo()
            return {"success": True, "rolled_back": {k: last.get(k) for k in ("op", "node_id", "line_range")}}

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
            from .locator import Target, resolve
            res = resolve(buf, Target(text=old_str))
            if not res.ok:
                return {
                    "success": False,
                    "failed_op": "replace_text",
                    "target": {"file": file_path, "text": old_str[:120]},
                    "error": ("AMBIGUOUS MATCH in auxiliary file" if res.reason == "ambiguous"
                              else "TARGET NOT FOUND in auxiliary file"),
                    "reason": res.reason,
                    "attempts": res.attempts,
                    "document_unchanged": True,
                    "occurrences_found": 0,
                }

            pos, span_end = res.start, res.end
            line_start = buf[:pos].count("\n") + 1
            line_end = line_start + buf[pos:span_end].count("\n")

            # Auxiliary files get the same heal + validate gate as the main buffer.
            # Without it, a broken \input fragment reaches the user unchecked: the
            # final validation pass in agent_loop only covers the main buffer.
            candidate = buf[:pos] + new_str + buf[span_end:]
            is_valid, candidate, validation_errors, fixes = self._heal_and_validate(
                candidate, baseline=buf
            )
            if not is_valid:
                return {
                    "success": False,
                    "error": (
                        f"PRE-COMMIT VALIDATION FAILED for '{file_path}': the edit introduces "
                        f"structural LaTeX errors:\n"
                        + "\n".join(f"  - {e}" for e in validation_errors[:5])
                        + f"\n'{file_path}' was NOT modified. Please fix these errors and retry."
                    ),
                    "validation_errors": validation_errors,
                }

            self._aux_files[file_path] = candidate
            self._aux_edit_history.setdefault(file_path, []).append({
                "old_str": old_str, "new_str": new_str, "line_range": [line_start, line_end],
            })
            result = {"success": True, "file": file_path, "method": res.method,
                      "lines_affected": [line_start, line_end]}
            if fixes:
                result["auto_repairs"] = fixes
            return result

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
