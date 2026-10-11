"""
attached_context.py — Session store for files attached to the agent chat
=========================================================================
Up to ``AGENT_ATTACH_MAX_FILES`` reference files (PDFs, images, text) per chat
session, kept across follow-up messages so the agent can read them, search them
and import their figures without the user re-attaching anything.

Text, page maps and figure lists live in memory. The uploaded **bytes** live on
disk (``AGENT_ATTACH_DIR``) and a session that is not in memory is rebuilt from
them: the server recycles its worker regularly (``--limit-max-requests``), and
an in-memory-only store lost every attachment mid-conversation when it did.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("attached_context")

DEFAULT_TTL_SECONDS = 7200  # 2 hours
MAX_ATTACHED_FILE_CHARS = 60000  # Initial prompt injection cap (~15,000 tokens)
MAX_ATTACHMENTS = int(os.getenv("AGENT_ATTACH_MAX_FILES", "5") or 5)
MAX_ATTACHMENT_BYTES = int(float(os.getenv("AGENT_ATTACH_MAX_MB", "25") or 25) * 1024 * 1024)
DISK_PURGE_INTERVAL = 600.0  # seconds between sweeps of expired session folders

IMAGE_MIME_BY_EXT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


class AttachmentLimitError(ValueError):
    """An upload the store refuses: too many files in the session, a file too large, or empty."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def attachment_dir() -> Path:
    return Path(os.getenv("AGENT_ATTACH_DIR") or os.path.join(tempfile.gettempdir(), "overbranch_attachments"))


def sniff_kind(filename: str, file_type: str, data: bytes) -> str:
    """'pdf' | 'image' | 'text', from the bytes first (a renamed file keeps its real type)."""
    head = data[:16]
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8\xff") or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"):
        return "image"
    ext = os.path.splitext(filename.lower())[1]
    if ext in IMAGE_MIME_BY_EXT or (file_type or "").lower().startswith("image/"):
        return "image"
    return "text"


def payload_to_bytes(filename: str, file_type: str, content: Any) -> Optional[bytes]:
    """
    The bytes of an attachment sent inside a JSON body (data URL, bare base64 PDF or
    plain text). ``None`` when nothing usable was sent.
    """
    if not content:
        return None
    if isinstance(content, (bytes, bytearray)):
        return bytes(content)
    clean = str(content).strip()
    if clean.startswith("data:") and "," in clean:
        header, b64 = clean.split(",", 1)
        if ";base64" in header:
            b64 = re.sub(r"\s+", "", b64)
            b64 += "=" * (-len(b64) % 4)
            try:
                return base64.b64decode(b64)
            except Exception as e:  # noqa: BLE001 — malformed uploads are reported, not raised
                logger.warning(f"Could not decode attachment '{filename}': {e}")
                return None
        return b64.encode("utf-8")
    if clean.startswith("JVBERi0") and len(clean) > 100:
        return _decode_base64_payload(clean)
    if clean.startswith("%PDF-"):
        return clean.encode("latin-1", errors="replace")
    return str(content).encode("utf-8")


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


def _image_size(data: bytes) -> Tuple[int, int]:
    try:
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        pix = fitz.Pixmap(data)
        return pix.width, pix.height
    except Exception:  # noqa: BLE001 — an unreadable image is still listed, without a size
        return 0, 0


def build_record(filename: str, file_type: str, data: bytes) -> Dict[str, Any]:
    """Everything the agent needs from one attachment, extracted from its bytes."""
    kind = sniff_kind(filename, file_type, data)
    is_scanned = False
    width = height = 0
    if kind == "pdf":
        full_text, pages, page_count, is_scanned = extract_text_and_pages_from_pdf(data, filename)
        file_type = "application/pdf"
    elif kind == "image":
        width, height = _image_size(data)
        size_note = f" ({width}×{height} px)" if width else ""
        full_text = (f"[Attached image '{filename}'{size_note}. It can be placed in the document: "
                     f"import it with import_attachment_figure.]")
        pages, page_count = {1: full_text}, 1
        file_type = file_type if (file_type or "").startswith("image/") else \
            IMAGE_MIME_BY_EXT.get(os.path.splitext(filename.lower())[1], "image/png")
    else:
        full_text = data.decode("utf-8", errors="replace")
        pages, page_count = {1: full_text}, 1

    preview = full_text
    if len(preview) > MAX_ATTACHED_FILE_CHARS:
        preview = (preview[:MAX_ATTACHED_FILE_CHARS]
                   + f"\n\n... [Remaining content available via `read_attached_document` ({page_count} pages total)]")
    return {
        "id": hashlib.sha1(filename.strip().lower().encode("utf-8")).hexdigest()[:8],
        "filename": filename,
        "file_type": file_type or "document",
        "kind": kind,
        "is_pdf": kind == "pdf",
        "content": preview,            # capped preview for the prompt
        "full_content": full_text,     # full text for the reading tools
        "pages": pages,
        "page_count": max(1, page_count),
        "size": len(full_text),
        "size_bytes": len(data),
        "width_px": width,
        "height_px": height,
        "is_scanned": is_scanned,
        "uploaded_at": time.time(),
    }


class AttachedContextStore:
    """
    Thread-safe session cache of attached reference files: page-by-page reads,
    line reads, keyword search, and the original bytes (on disk) for the PDF
    importer and for figure extraction.
    """

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS, root: Optional[Path] = None,
                 max_files: Optional[int] = None, max_bytes: Optional[int] = None):
        self._lock = threading.Lock()
        self._store: Dict[str, List[Dict[str, Any]]] = {}
        self._last_accessed: Dict[str, float] = {}
        self._ttl_seconds = ttl_seconds
        self._root = Path(root) if root else None
        self._max_files = max_files
        self._max_bytes = max_bytes
        self._last_disk_purge = 0.0

    # -- limits & disk ------------------------------------------------------

    @property
    def max_files(self) -> int:
        return self._max_files if self._max_files is not None else MAX_ATTACHMENTS

    @property
    def max_bytes(self) -> int:
        return self._max_bytes if self._max_bytes is not None else MAX_ATTACHMENT_BYTES

    def _session_dir(self, session_id: str) -> Path:
        root = self._root or attachment_dir()
        return root / hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]

    def _write_disk(self, session_id: str, record: Dict[str, Any], data: bytes) -> None:
        try:
            d = self._session_dir(session_id)
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{record['id']}.bin").write_bytes(data)
            meta = {"id": record["id"], "filename": record["filename"], "file_type": record["file_type"],
                    "uploaded_at": record["uploaded_at"]}
            (d / f"{record['id']}.json").write_text(json.dumps(meta), encoding="utf-8")
            record["raw_path"] = str(d / f"{record['id']}.bin")
        except OSError as e:
            logger.warning(f"Could not persist attachment '{record.get('filename')}': {e}")

    def read_bytes(self, record: Dict[str, Any]) -> Optional[bytes]:
        """The uploaded bytes of an attachment (``None`` if they are gone from disk)."""
        path = record.get("raw_path")
        if not path:
            return None
        try:
            return Path(path).read_bytes()
        except OSError:
            return None

    def _load_from_disk(self, session_id: str) -> List[Dict[str, Any]]:
        """Rebuilds a session's records from disk (after a worker restart)."""
        d = self._session_dir(session_id)
        if not d.is_dir():
            return []
        if time.time() - d.stat().st_mtime > self._ttl_seconds:
            shutil.rmtree(d, ignore_errors=True)
            return []
        records: List[Dict[str, Any]] = []
        for meta_path in sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                bin_path = meta_path.with_suffix(".bin")
                record = build_record(meta["filename"], meta.get("file_type") or "", bin_path.read_bytes())
                record["uploaded_at"] = meta.get("uploaded_at") or record["uploaded_at"]
                record["raw_path"] = str(bin_path)
                records.append(record)
            except Exception as e:  # noqa: BLE001 — one unreadable file must not hide the others
                logger.warning(f"Could not restore attachment from {meta_path}: {e}")
        if records:
            logger.info(f"Restored {len(records)} attachment(s) for session '{session_id}' from disk")
        return records

    def _touch(self, session_id: str) -> None:
        self._last_accessed[session_id] = time.time()
        try:
            os.utime(self._session_dir(session_id), None)
        except OSError:
            pass

    # -- writes -------------------------------------------------------------

    def store_bytes(self, session_id: str, filename: str, file_type: str, data: bytes) -> Dict[str, Any]:
        """
        Stores one uploaded file. Re-uploading a filename replaces it. Raises
        ``AttachmentLimitError`` when the file is too large or the session is full.
        """
        if not session_id:
            raise AttachmentLimitError("No chat session to attach the file to.")
        filename = os.path.basename((filename or "").replace("\\", "/")).strip() or "attachment"
        if not data:
            raise AttachmentLimitError(f"'{filename}' is empty.")
        if len(data) > self.max_bytes:
            raise AttachmentLimitError(
                f"'{filename}' is {len(data) / 1048576:.1f} MB; the limit is {self.max_bytes / 1048576:.0f} MB per file.",
                status_code=413)

        existing = self.get_attachments(session_id)
        if not any(a.get("filename") == filename for a in existing) and len(existing) >= self.max_files:
            raise AttachmentLimitError(
                f"A chat can hold at most {self.max_files} attached files. Remove one to attach '{filename}'.",
                status_code=409)

        record = build_record(filename, file_type, data)  # extraction happens outside the lock
        self._write_disk(session_id, record, data)
        with self._lock:
            files = self._store.setdefault(session_id, [])
            idx = next((i for i, f in enumerate(files) if f.get("filename") == filename), None)
            if idx is not None:
                files[idx] = record
            elif len(files) >= self.max_files:
                raise AttachmentLimitError(
                    f"A chat can hold at most {self.max_files} attached files. Remove one to attach '{filename}'.",
                status_code=409)
            else:
                files.append(record)
            self._touch(session_id)
        logger.info(f"Stored attachment '{filename}' ({record['kind']}, {record['page_count']} page(s), "
                    f"{len(data)} bytes) for session '{session_id}'")
        return record

    def store_attachment(self, session_id: str, file_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Stores an attachment sent inside a JSON body ({filename, file_type, content})."""
        if not session_id or not file_data:
            return None
        filename = file_data.get("filename", "Uploaded File")
        file_type = file_data.get("file_type", "document")
        data = payload_to_bytes(filename, file_type, file_data.get("content", ""))
        if not data:
            return None
        return self.store_bytes(session_id, filename, file_type, data)

    def remove_attachment(self, session_id: str, attachment_id: str) -> bool:
        """Removes one attachment by id (or exact filename). Returns whether anything was removed."""
        self.get_attachments(session_id)  # make sure a disk-only session is loaded
        with self._lock:
            files = self._store.get(session_id) or []
            keep = [f for f in files if f.get("id") != attachment_id and f.get("filename") != attachment_id]
            removed = [f for f in files if f not in keep]
            if not removed:
                return False
            self._store[session_id] = keep
        d = self._session_dir(session_id)
        for f in removed:
            for suffix in (".bin", ".json"):
                try:
                    (d / f"{f['id']}{suffix}").unlink()
                except OSError:
                    pass
        return True

    # -- reads --------------------------------------------------------------

    def get_attachments(self, session_id: str) -> List[Dict[str, Any]]:
        """All attachments of a session (rebuilt from disk if this process has not seen it)."""
        if not session_id:
            return []
        with self._lock:
            self._cleanup_expired_locked()
            if session_id in self._store:
                self._touch(session_id)
                return list(self._store[session_id])
        restored = self._load_from_disk(session_id)
        if not restored:
            return []
        with self._lock:
            files = self._store.setdefault(session_id, restored)
            self._touch(session_id)
            return list(files)

    def get_attachment(self, session_id: str, filename: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """An attachment by filename or id; the most recent one when ``filename`` is None or unknown."""
        attachments = self.get_attachments(session_id)
        if not attachments:
            return None
        if not filename:
            return attachments[-1]

        fn_lower = filename.lower()
        for att in attachments:
            att_name = att.get("filename", "").lower()
            if (att.get("id") == filename or att_name == fn_lower
                    or att_name.endswith("/" + fn_lower) or fn_lower.endswith("/" + att_name)):
                return att
        return attachments[-1]

    def find_attachment(self, session_id: str, name_or_id: str) -> Optional[Dict[str, Any]]:
        """Like get_attachment, but ``None`` when nothing matches (no most-recent fallback)."""
        wanted = (name_or_id or "").strip().lower()
        for att in self.get_attachments(session_id):
            if att.get("id") == wanted or att.get("filename", "").lower() == wanted:
                return att
        return None

    def summaries(self, session_id: str) -> List[Dict[str, Any]]:
        """What the client shows for each attachment — never text or bytes."""
        out = []
        for a in self.get_attachments(session_id):
            out.append({
                "id": a.get("id"),
                "filename": a.get("filename"),
                "file_type": a.get("file_type"),
                "kind": a.get("kind"),
                "page_count": a.get("page_count", 1),
                "size_bytes": a.get("size_bytes", 0),
                "chars": a.get("size", 0),
                "is_scanned": bool(a.get("is_scanned")),
                "figure_count": len(a["figures"]) if isinstance(a.get("figures"), list) else None,
            })
        return out

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

    # -- lifecycle ----------------------------------------------------------

    def clear_session(self, session_id: str) -> None:
        """Clears all attachments for a specific session, on disk too."""
        with self._lock:
            self._store.pop(session_id, None)
            self._last_accessed.pop(session_id, None)
        shutil.rmtree(self._session_dir(session_id), ignore_errors=True)

    def cleanup_expired(self) -> None:
        """Public method to clean up expired sessions."""
        with self._lock:
            self._cleanup_expired_locked(force_disk=True)

    def _cleanup_expired_locked(self, force_disk: bool = False) -> None:
        now = time.time()
        expired = [
            sid for sid, last_time in self._last_accessed.items()
            if (now - last_time) > self._ttl_seconds
        ]
        for sid in expired:
            self._store.pop(sid, None)
            self._last_accessed.pop(sid, None)
            shutil.rmtree(self._session_dir(sid), ignore_errors=True)
            logger.debug(f"Expired attached context for session '{sid}'")

        # Folders of sessions this process never loaded (left by an earlier worker).
        if force_disk or now - self._last_disk_purge > DISK_PURGE_INTERVAL:
            self._last_disk_purge = now
            root = self._root or attachment_dir()
            try:
                for d in root.iterdir():
                    if d.is_dir() and now - d.stat().st_mtime > self._ttl_seconds:
                        shutil.rmtree(d, ignore_errors=True)
            except OSError:
                pass


# Global singleton instance
attached_context_store = AttachedContextStore()
