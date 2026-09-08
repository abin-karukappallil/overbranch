"""
environment_ledger.py — Global LaTeX Environment Ledger

Computes global environment structure across the entire document once, cheaply,
with regex/AST parsing (no LLM call). Handed to edit prompts and validation as ground truth.
Prevents premature \\end{document} bugs, unclosed environments, and cross-section boundary errors.
"""

import re
import hashlib
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Set, Any

try:
    from document_index import DocumentIndex, PageEntry, parse_document_structure
except ImportError:
    from backend.document_index import DocumentIndex, PageEntry, parse_document_structure

logger = logging.getLogger("environment_ledger")

# Cache ledgers by document hash
_LEDGER_CACHE: Dict[str, "EnvironmentLedger"] = {}
_MAX_CACHE_SIZE = 100


@dataclass
class OpenEnvironmentSpan:
    """Represents a LaTeX environment span from \\begin{env} to \\end{env}."""
    env_name: str                  # "document", "frame", "itemize", "table", "tabular", etc.
    opens_in_page_id: str          # page_id where \begin{env} is located
    opens_at_offset: int           # character offset of \begin{env}
    closes_in_page_id: Optional[str] = None  # None if unterminated (syntax/compile error)
    closes_at_offset: Optional[int] = None
    spans_multiple_sections: bool = False   # True if opens_in_page_id != closes_in_page_id

    def is_unterminated(self) -> bool:
        return self.closes_at_offset is None


class EnvironmentLedger:
    """
    Built once per document version, cached by document content hash.
    Rebuilt only when the document actually changes, not per LLM call.
    """

    def __init__(self, full_document: str, doc_idx: DocumentIndex):
        self.doc_hash = hashlib.sha256(full_document.encode("utf-8")).hexdigest()
        self.full_document = full_document
        self.doc_idx = doc_idx
        self.spans: List[OpenEnvironmentSpan] = self._build(full_document, doc_idx)

    def _build(self, doc: str, doc_idx: DocumentIndex) -> List[OpenEnvironmentSpan]:
        """
        Stack-based scan across the WHOLE document (single linear pass, O(n), no LLM):
        push on \\begin{env}, pop on matching \\end{env}, record which page_id
        (via doc_idx.page_for_offset()) each open/close landed in.
        """
        spans: List[OpenEnvironmentSpan] = []
        if not doc:
            return spans

        # Pattern matching \begin{name} or \end{name}
        env_pattern = re.compile(r"\\(begin|end)\{([a-zA-Z0-9*_-]+)\}")

        stack: List[Tuple[str, int, str]] = []  # (env_name, open_offset, open_page_id)

        for match in env_pattern.finditer(doc):
            token_type = match.group(1)  # "begin" or "end"
            env_name = match.group(2)
            offset = match.start()

            page = doc_idx.page_for_offset(offset)
            page_id = page.page_id if page else "unknown"

            if token_type == "begin":
                stack.append((env_name, offset, page_id))
            elif token_type == "end":
                # Find matching \begin on stack from top down
                match_idx = -1
                for idx in range(len(stack) - 1, -1, -1):
                    if stack[idx][0] == env_name:
                        match_idx = idx
                        break

                if match_idx != -1:
                    # Found matching open tag
                    open_env, open_off, open_pid = stack.pop(match_idx)
                    spans.append(OpenEnvironmentSpan(
                        env_name=open_env,
                        opens_in_page_id=open_pid,
                        opens_at_offset=open_off,
                        closes_in_page_id=page_id,
                        closes_at_offset=offset,
                        spans_multiple_sections=(open_pid != page_id),
                    ))
                else:
                    # Stray \end{env} with no matching open tag
                    spans.append(OpenEnvironmentSpan(
                        env_name=env_name,
                        opens_in_page_id="missing_open",
                        opens_at_offset=-1,
                        closes_in_page_id=page_id,
                        closes_at_offset=offset,
                        spans_multiple_sections=True,
                    ))

        # Any unclosed environments remaining on stack
        while stack:
            open_env, open_off, open_pid = stack.pop()
            spans.append(OpenEnvironmentSpan(
                env_name=open_env,
                opens_in_page_id=open_pid,
                opens_at_offset=open_off,
                closes_in_page_id=None,
                closes_at_offset=None,
                spans_multiple_sections=True,
            ))

        return spans

    def _page_index_for_id(self, page_id: str) -> Optional[int]:
        if not self.doc_idx or not self.doc_idx.pages:
            return None
        for i, p in enumerate(self.doc_idx.pages):
            if p.page_id == page_id:
                return i
        return None

    def spans_touching_page(self, page_id: str) -> List[OpenEnvironmentSpan]:
        """
        Every environment that is open going INTO this page, or that opens/closes
        WITHIN this page. This is what gets attached to that section's edit prompt.
        """
        touching: List[OpenEnvironmentSpan] = []
        target_idx = self._page_index_for_id(page_id)
        target_page = self.doc_idx.get_page_by_id(page_id)

        for span in self.spans:
            # Case 1: opens or closes directly in this page
            if span.opens_in_page_id == page_id or span.closes_in_page_id == page_id:
                touching.append(span)
                continue

            # Case 2: spans across this page (opened before, closed after or unclosed)
            open_idx = self._page_index_for_id(span.opens_in_page_id)
            close_idx = self._page_index_for_id(span.closes_in_page_id) if span.closes_in_page_id else None

            if open_idx is not None and target_idx is not None:
                if open_idx < target_idx:
                    if close_idx is None or close_idx > target_idx:
                        touching.append(span)
            elif target_page and span.opens_at_offset < target_page.start_offset:
                if span.closes_at_offset is None or span.closes_at_offset > target_page.end_offset:
                    touching.append(span)

        return touching

    def is_page_safe_for_isolated_edit(self, page_id: str) -> Tuple[bool, Optional[str]]:
        """
        False if any environment spanning this page also spans other pages
        (e.g. \\begin{document} opened in preamble, not closed until the final page).
        Returns (False, reason) so the caller can decide to widen scope or reject edit.
        """
        for span in self.spans_touching_page(page_id):
            if span.spans_multiple_sections:
                open_loc = span.opens_in_page_id
                close_loc = span.closes_in_page_id if span.closes_in_page_id else "NEVER CLOSED (EOF)"
                return False, (
                    f"Environment '{span.env_name}' opens in '{open_loc}' and "
                    f"closes in '{close_loc}' — this page cannot be edited in "
                    f"isolation without risking that boundary."
                )
        return True, None

    def get_document_span(self) -> Optional[OpenEnvironmentSpan]:
        """Find the \\begin{document} ... \\end{document} span."""
        for s in self.spans:
            if s.env_name == "document":
                return s
        return None

    def summarize(self) -> str:
        """Produce a diagnostic string summary of all open / cross-section environments."""
        lines = []
        for s in self.spans:
            if s.spans_multiple_sections or s.is_unterminated():
                close_str = s.closes_in_page_id or "UNTERMINATED"
                lines.append(f"- \\begin{{{s.env_name}}} in '{s.opens_in_page_id}' → \\end{{{s.env_name}}} in '{close_str}'")
        return "\n".join(lines) if lines else "All environments are cleanly self-contained within single sections."

    def generate_prompt_facts_block(self, page_id: str) -> str:
        """
        Generates the ground-truth facts block to attach to edit prompts.
        Directly and structurally prevents premature closure bugs.
        """
        target_page = self.doc_idx.get_page_by_id(page_id)
        page_title = target_page.title if target_page else page_id

        doc_span = self.get_document_span()
        last_page = self.doc_idx.pages[-1] if self.doc_idx.pages else None
        first_page = self.doc_idx.pages[0] if self.doc_idx.pages else None

        closing_page_id = doc_span.closes_in_page_id if doc_span and doc_span.closes_in_page_id else (last_page.page_id if last_page else "final page")
        closing_page_obj = self.doc_idx.get_page_by_id(closing_page_id) if closing_page_id else last_page
        closing_page_title = closing_page_obj.title if closing_page_obj else closing_page_id

        opening_page_id = doc_span.opens_in_page_id if doc_span else (first_page.page_id if first_page else "preamble")
        opening_page_obj = self.doc_idx.get_page_by_id(opening_page_id) if opening_page_id else first_page
        opening_page_title = opening_page_obj.title if opening_page_obj else opening_page_id

        is_last_page = (last_page is not None and last_page.page_id == page_id)
        is_closing_page = (page_id == closing_page_id)
        is_opening_page = (page_id == opening_page_id)

        facts = [
            "[DOCUMENT STRUCTURE FACTS — do not deviate from these, they are computed, not inferred]"
        ]

        if doc_span:
            facts.append(
                f"- \\begin{{document}} opens in section \"{opening_page_title}\" and closes in section \"{closing_page_title}\" (the LAST section of this document)."
            )
        else:
            facts.append(
                f"- This document is structured across {len(self.doc_idx.pages)} sections/frames."
            )

        if not is_last_page and not is_closing_page:
            facts.append(
                f"- This section (\"{page_title}\") is NOT the final section. Do NOT emit \\end{{document}} anywhere in your output for this section."
            )
            facts.append(
                f"- The only section where \\end{{document}} may legally appear is \"{closing_page_title}\"."
            )
        else:
            facts.append(
                f"- This section (\"{page_title}\") IS the final section of the document. Ensure \\end{{document}} is properly preserved at the end if completing the document."
            )

        if not is_opening_page:
            facts.append(
                f"- \\documentclass and \\begin{{document}} are declared in \"{opening_page_title}\". Do NOT repeat \\documentclass or \\begin{{document}} in this section."
            )

        # Add notes for any other cross-page environments touching this page
        touching_spanning = [
            s for s in self.spans_touching_page(page_id)
            if s.spans_multiple_sections and s.env_name != "document"
        ]
        for s in touching_spanning:
            if s.opens_in_page_id == page_id:
                facts.append(
                    f"- Environment \\begin{{{s.env_name}}} opens here and closes in section \"{s.closes_in_page_id or 'later'}\". Do NOT close \\end{{{s.env_name}}} inside this snippet unless deliberately restructuring."
                )
            elif s.closes_in_page_id == page_id:
                facts.append(
                    f"- Environment \\begin{{{s.env_name}}} opened earlier in section \"{s.opens_in_page_id}\" and closes here with \\end{{{s.env_name}}}."
                )
            else:
                facts.append(
                    f"- Environment \\begin{{{s.env_name}}} is open across this section (opened in \"{s.opens_in_page_id}\", closes in \"{s.closes_in_page_id or 'later'}\")."
                )

        return "\n".join(facts)


def get_environment_ledger(full_document: str, doc_idx: Optional[DocumentIndex] = None) -> EnvironmentLedger:
    """
    Returns a cached or freshly built EnvironmentLedger for the given document.
    """
    if not full_document:
        if doc_idx is None:
            doc_idx = DocumentIndex()
        return EnvironmentLedger("", doc_idx)

    doc_hash = hashlib.sha256(full_document.encode("utf-8")).hexdigest()
    if doc_hash in _LEDGER_CACHE:
        return _LEDGER_CACHE[doc_hash]

    if doc_idx is None:
        doc_idx = parse_document_structure(full_document)

    ledger = EnvironmentLedger(full_document, doc_idx)

    # Manage cache size
    if len(_LEDGER_CACHE) >= _MAX_CACHE_SIZE:
        # Evict oldest entry
        oldest_key = next(iter(_LEDGER_CACHE))
        _LEDGER_CACHE.pop(oldest_key, None)

    _LEDGER_CACHE[doc_hash] = ledger
    return ledger
