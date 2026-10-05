"""
attached_context.py — In-Memory Multi-Turn Session Store for Attached Reference Files
====================================================================================
Provides a thread-safe, TTL-cached in-memory store for attached documents (PDFs, papers,
source texts) uploaded in chat sessions.

Persists uploaded reference files across follow-up messages in the same session/project,
allowing the agent to recall domain data, benchmark results, and citations without
requiring the user to re-attach the file on every prompt.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("attached_context")

DEFAULT_TTL_SECONDS = 7200  # 2 hours
MAX_ATTACHED_FILE_CHARS = 60000  # Initial prompt injection cap (~15,000 tokens)


def _decode_base64_payload(content: Any) -> Optional[bytes]:
    """Decodes data URL, raw base64 string, or raw bytes into bytes."""
    if not content:
        return None
    if isinstance(content, (bytes, bytearray)):
        return bytes(content)
    clean = content.strip()
    try:
        if clean.startswith("data:"):
            if "," in clean:
                b64_part = clean.split(",", 1)[1].strip()
                # Remove any URL-encoding or whitespace in base64 string
                b64_part = re.sub(r"\s+", "", b64_part)
                # Fix missing padding if needed
                pad = len(b64_part) % 4
                if pad:
                    b64_part += "=" * (4 - pad)
                return base64.b64decode(b64_part)
        elif clean.startswith("%PDF-"):
            return clean.encode("latin-1")
        elif clean.startswith("JVBERi0"):  # Standard PDF header in base64 (%PDF-)
            b64_clean = re.sub(r"\s+", "", clean)
            pad = len(b64_clean) % 4
            if pad:
                b64_clean += "=" * (4 - pad)
            return base64.b64decode(b64_clean)
    except Exception as e:
        logger.warning(f"Base64 decoding failed: {e}")
    return None


def extract_text_and_pages_from_pdf(pdf_bytes: bytes, filename: str) -> Tuple[str, Dict[int, str], int, bool]:
    """
    Extracts text and per-page mappings from PDF bytes using PyMuPDF (fitz)
    with a graceful fallback to pypdf.

    Returns:
        (full_text, pages_dict, page_count, is_scanned_or_empty)
    """
    pages_dict: Dict[int, str] = {}
    page_count = 0

    # 1. Try PyMuPDF (fitz) — fast and accurate
    try:
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_count = len(doc)
        for idx, page in enumerate(doc, start=1):
            txt = page.get_text().strip()
            if txt:
                pages_dict[idx] = txt

        if pages_dict:
            full_text = "\n\n".join([f"--- Page {p} ---\n{t}" for p, t in pages_dict.items()])
            logger.info(f"PyMuPDF extracted {len(full_text)} chars across {len(pages_dict)}/{page_count} pages from '{filename}'")
            return full_text, pages_dict, page_count, False
    except Exception as e:
        logger.warning(f"PyMuPDF extraction failed on '{filename}': {e}. Attempting pypdf fallback...")

    # 2. Try pypdf fallback
    try:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        page_count = len(reader.pages)
        for idx, page in enumerate(reader.pages, start=1):
            txt = (page.extract_text() or "").strip()
            if txt:
                pages_dict[idx] = txt

        if pages_dict:
            full_text = "\n\n".join([f"--- Page {p} ---\n{t}" for p, t in pages_dict.items()])
            logger.info(f"pypdf fallback extracted {len(full_text)} chars across {len(pages_dict)}/{page_count} pages from '{filename}'")
            return full_text, pages_dict, page_count, False
    except Exception as e:
        logger.warning(f"pypdf fallback extraction failed on '{filename}': {e}")

    # 3. PDF has no extractable text (likely image-based / scanned)
    if page_count > 0:
        diagnostic = (
            f"[Attached document '{filename}' has {page_count} page(s), but contains no extractable digital text. "
            f"It may be a scanned or image-only PDF. Please copy and paste key text, tables, or equations directly into the chat prompt.]"
        )
        return diagnostic, {1: diagnostic}, page_count, True

    return "", {}, 0, True


def extract_document_payload(
    filename: str,
    file_type: str,
    content: str,
) -> Tuple[str, Dict[int, str], int, bool]:
    """
    Extracts readable text, per-page dictionary, and metadata from an uploaded file payload.
    Supports PDF (data URLs / base64), plain text, LaTeX, Markdown, CSV, and JSON.

    Returns:
        (full_text, pages_dict, page_count, is_scanned_or_empty)
    """
    if not content:
        return "", {}, 0, True

    clean_content = content.strip()
    is_pdf = (
        filename.lower().endswith(".pdf")
        or "application/pdf" in (file_type or "").lower()
        or clean_content.startswith("data:application/pdf")
        or clean_content.startswith("data:application/x-pdf")
        or (clean_content.startswith("JVBERi0") and len(clean_content) > 100)
    )

    if is_pdf:
        # Check if the content is already plain text (e.g. pre-extracted or in mock unit tests)
        if not clean_content.startswith("data:") and not clean_content.startswith("JVBERi0"):
            if clean_content.startswith("%PDF-"):
                try:
                    return extract_text_and_pages_from_pdf(clean_content.encode("latin-1"), filename)
                except Exception:
                    pass
            elif all(c.isprintable() or c.isspace() for c in clean_content[:500]):
                return clean_content, {1: clean_content}, 1, False

        pdf_bytes = _decode_base64_payload(clean_content)
        if pdf_bytes:
            return extract_text_and_pages_from_pdf(pdf_bytes, filename)
        else:
            if all(c.isprintable() or c.isspace() for c in clean_content[:500]):
                return clean_content, {1: clean_content}, 1, False
            err_msg = f"[Attached PDF '{filename}' could not be decoded from base64 payload.]"
            return err_msg, {1: err_msg}, 1, True

    # Non-PDF text files (text/plain, text/markdown, text/csv, application/json, etc.)
    if clean_content.startswith("data:") and ";base64," in clean_content:
        try:
            b64_part = clean_content.split(";base64,", 1)[1]
            decoded_bytes = base64.b64decode(b64_part)
            text = decoded_bytes.decode("utf-8", errors="replace")
            return text, {1: text}, 1, False
        except Exception as e:
            logger.warning(f"Failed to decode text file data URL for '{filename}': {e}")
            return clean_content, {1: clean_content}, 1, False

    # Plain text string
    return clean_content, {1: clean_content}, 1, False


def extract_text_from_attachment(filename: str, file_type: str, content: str) -> str:
    """
    Extracts clean readable plain text from an attached file payload.
    Backward-compatible wrapper returning the full extracted text string.
    """
    full_text, _, _, _ = extract_document_payload(filename, file_type, content)
    return full_text


class AttachedContextStore:
    """
    Thread-safe in-memory session cache for attached reference documents.
    Supports full multi-page document inspection, page-by-page reads,
    line-by-line reads, and contextual keyword search.
    """

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self._lock = threading.Lock()
        self._store: Dict[str, List[Dict[str, Any]]] = {}
        self._last_accessed: Dict[str, float] = {}
        self._ttl_seconds = ttl_seconds

    def store_attachment(self, session_id: str, file_data: Dict[str, Any]) -> None:
        """
        Stores or updates an attached reference document for a session.
        Automatically extracts text, page mappings, and metadata.
        """
        if not session_id or not file_data:
            return

        filename = file_data.get("filename", "Uploaded File")
        file_type = file_data.get("file_type", "document")
        raw_content = file_data.get("content", "")

        full_text, pages_dict, page_count, is_scanned = extract_document_payload(
            filename=filename,
            file_type=file_type,
            content=raw_content,
        )

        # Build initial prompt preview (capped at MAX_ATTACHED_FILE_CHARS)
        prompt_content = full_text
        if len(prompt_content) > MAX_ATTACHED_FILE_CHARS:
            prompt_content = prompt_content[:MAX_ATTACHED_FILE_CHARS] + f"\n\n... [Remaining content available via `read_attached_document` ({page_count} pages total)]"

        # Keep the original PDF bytes so the PDF → LaTeX converter can import the attachment
        raw_pdf: Optional[bytes] = None
        if isinstance(raw_content, str) and raw_content.strip()[:30].startswith(("data:application/pdf", "data:application/x-pdf", "JVBERi0")):
            decoded = _decode_base64_payload(raw_content.strip())
            max_bytes = int(os.getenv("PDF2LATEX_MAX_FILE_MB", "50")) * 1024 * 1024
            if decoded and decoded[:5] == b"%PDF-" and len(decoded) <= max_bytes:
                raw_pdf = decoded

        record = {
            "filename": filename,
            "file_type": file_type,
            "is_pdf": raw_pdf is not None,
            "raw_bytes": raw_pdf,
            "content": prompt_content,           # Capped preview for prompt context
            "full_content": full_text,            # Full un-truncated text for tool reading
            "pages": pages_dict,                  # Dict[page_number: text]
            "page_count": max(1, page_count),
            "size": len(full_text),
            "is_scanned": is_scanned,
            "uploaded_at": time.time(),
        }

        with self._lock:
            self._cleanup_expired_locked()
            if session_id not in self._store:
                self._store[session_id] = []

            # Replace if same filename exists, else append
            existing_idx = next(
                (i for i, f in enumerate(self._store[session_id]) if f.get("filename") == filename),
                None
            )
            if existing_idx is not None:
                self._store[session_id][existing_idx] = record
            else:
                self._store[session_id].append(record)

            self._last_accessed[session_id] = time.time()
            logger.info(f"Stored attached file '{filename}' for session '{session_id}' ({page_count} pages, {len(full_text)} chars)")

    def get_attachments(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieves all active attached reference documents for a session."""
        if not session_id:
            return []

        with self._lock:
            self._cleanup_expired_locked()
            if session_id in self._store:
                self._last_accessed[session_id] = time.time()
                return list(self._store[session_id])
            return []

    def get_attachment(self, session_id: str, filename: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieves a specific attachment by filename, or the first/latest attachment if filename is None."""
        attachments = self.get_attachments(session_id)
        if not attachments:
            return None
        if not filename:
            return attachments[-1]  # Return most recent

        # Case-insensitive filename match or basename match
        fn_lower = filename.lower()
        for att in attachments:
            att_name = att.get("filename", "").lower()
            if att_name == fn_lower or att_name.endswith("/" + fn_lower) or fn_lower.endswith("/" + att_name):
                return att
        return attachments[-1]

    def read_attachment_pages(
        self,
        session_id: str,
        filename: Optional[str] = None,
        start_page: int = 1,
        end_page: int = 5,
    ) -> str:
        """
        Reads a specific range of pages from an attached reference document.
        """
        att = self.get_attachment(session_id, filename)
        if not att:
            return f"(No attached document found for session '{session_id}')"

        pages = att.get("pages", {})
        if not pages:
            # Fall back to full_content
            return att.get("full_content", "(Document content is empty)")

        total_pages = att.get("page_count", len(pages))
        sp = max(1, start_page)
        ep = min(total_pages, end_page)

        if sp > total_pages:
            return f"(Document '{att.get('filename')}' only has {total_pages} pages; requested start_page={sp})"

        parts: List[str] = [f"ATTACHED DOCUMENT: {att.get('filename')} (Reading Pages {sp}–{ep} of {total_pages}):\n"]
        for p in range(sp, ep + 1):
            p_text = pages.get(p, "(Empty page or unparsed)")
            parts.append(f"--- Page {p} ---\n{p_text}")

        return "\n\n".join(parts)

    def read_attachment_lines(
        self,
        session_id: str,
        filename: Optional[str] = None,
        start_line: int = 1,
        end_line: int = 100,
    ) -> str:
        """
        Reads line-numbered content from the full extracted text of an attached document.
        """
        att = self.get_attachment(session_id, filename)
        if not att:
            return f"(No attached document found for session '{session_id}')"

        full_text = att.get("full_content") or att.get("content", "")
        lines = full_text.splitlines(keepends=False)
        total = len(lines)
        if total == 0:
            return f"(Document '{att.get('filename')}' contains no lines)"

        sl = max(1, start_line)
        el = min(total, end_line)

        if sl > total:
            return f"(Document '{att.get('filename')}' has {total} lines; requested start_line={sl})"

        parts: List[str] = [f"ATTACHED DOCUMENT: {att.get('filename')} (Lines {sl}–{el} of {total}):"]
        for i in range(sl - 1, el):
            parts.append(f"{i + 1}: {lines[i]}")

        return "\n".join(parts)

    def search_attachments(self, session_id: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Performs keyword and phrase search across all attachments for a session.
        Returns matching paragraphs with line numbers and page markers.
        """
        if not session_id or not query:
            return []

        attachments = self.get_attachments(session_id)
        if not attachments:
            return []

        q_clean = query.strip().lower()
        query_terms = [q for q in q_clean.split() if len(q) > 2]
        if not query_terms:
            query_terms = [q_clean]

        results: List[Dict[str, Any]] = []

        for att in attachments:
            fname = att.get("filename", "Uploaded File")
            content = att.get("full_content") or att.get("content", "")
            lines = content.splitlines()

            current_page = 1
            for idx, line in enumerate(lines, start=1):
                # Track page headers: "--- Page X ---"
                page_match = re.match(r"^---\s*Page\s*(\d+)\s*---", line, re.IGNORECASE)
                if page_match:
                    current_page = int(page_match.group(1))

                line_lower = line.lower()

                # Score exact phrase match higher
                score = 0
                if q_clean in line_lower:
                    score += 5

                # Score individual term matches
                term_matches = sum(1 for term in query_terms if term in line_lower)
                score += term_matches

                if score > 0:
                    start_ctx = max(0, idx - 4)
                    end_ctx = min(len(lines), idx + 5)
                    context_snippet = "\n".join(lines[start_ctx:end_ctx])
                    results.append({
                        "filename": fname,
                        "page": current_page,
                        "line_no": idx,
                        "score": score,
                        "snippet": context_snippet,
                        "match_line": line,
                    })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def clear_session(self, session_id: str) -> None:
        """Clears all attachments for a specific session."""
        with self._lock:
            self._store.pop(session_id, None)
            self._last_accessed.pop(session_id, None)

    def cleanup_expired(self) -> None:
        """Public method to clean up expired sessions."""
        with self._lock:
            self._cleanup_expired_locked()

    def _cleanup_expired_locked(self) -> None:
        now = time.time()
        expired = [
            sid for sid, last_time in self._last_accessed.items()
            if (now - last_time) > self._ttl_seconds
        ]
        for sid in expired:
            self._store.pop(sid, None)
            self._last_accessed.pop(sid, None)
            logger.debug(f"Expired attached context for session '{sid}'")


# Global singleton instance
attached_context_store = AttachedContextStore()
