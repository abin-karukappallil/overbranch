"""
document_index.py — Structural LaTeX Document Indexer & Chunk Manager
=====================================================================
Constructs an AST-aware structural representation of a LaTeX document, mapping every
chapter, section, slide/frame, and frontmatter component to stable chunk IDs, line numbers,
byte/character offsets (start_offset, end_offset), and SHA-256 fingerprints.

Provides offset-based chunk replacements (rewrite_chunk) that bypass fragile exact-string
matches, and enumerates the complete ordered list of chunks for full document rewrites.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("document_index")


@dataclass
class DocumentChunk:
    chunk_id: str
    title: str
    chunk_type: str  # "preamble", "frontmatter", "chapter", "section", "subsection", "frame", "content"
    start_offset: int
    end_offset: int
    start_line: int
    end_line: int
    content: str
    is_content_chunk: bool = True
    sha256: str = ""

    def __post_init__(self):
        if not self.sha256 and self.content:
            self.sha256 = hashlib.sha256(self.content.encode("utf-8")).hexdigest()


class DocumentIndex:
    """
    Parses and indexes LaTeX documents into sequential, ordered chunks.
    """

    def __init__(self):
        pass

    def index_document(self, latex_code: str) -> List[DocumentChunk]:
        r"""
        Parses latex_code into an ordered list of DocumentChunks.
        Detects Document structure:
        - Multi-chapter reports/theses (\chapter{...})
        - Multi-section articles/papers (\section{...})
        - Beamer slide decks (\begin{frame} ... \end{frame})
        """
        if not latex_code:
            return []

        chunks: List[DocumentChunk] = []
        doc_len = len(latex_code)

        # 1. Preamble Detection
        doc_begin_match = re.search(r"\\begin\{document\}", latex_code)
        if doc_begin_match:
            preamble_end = doc_begin_match.end()
            preamble_content = latex_code[:preamble_end]
            chunks.append(DocumentChunk(
                chunk_id="preamble",
                title="Preamble & Setup",
                chunk_type="preamble",
                start_offset=0,
                end_offset=preamble_end,
                start_line=1,
                end_line=preamble_content.count("\n") + 1,
                content=preamble_content,
                is_content_chunk=False,
            ))
            body_start_offset = preamble_end
        else:
            body_start_offset = 0

        body_text = latex_code[body_start_offset:]

        # Find end{document} position
        doc_end_match = re.search(r"\\end\{document\}", body_text)
        content_end_offset = (body_start_offset + doc_end_match.start()) if doc_end_match else doc_len

        # Check for Beamer frames vs Chapters vs Sections
        frame_matches = list(re.finditer(r"\\begin\{frame\}(?:\[[^\]]*\])?(?:\{([^}]*)\})?", body_text))
        chapter_matches = list(re.finditer(r"\\chapter\*?\{([^}]+)\}", body_text))
        section_matches = list(re.finditer(r"\\section\*?\{([^}]+)\}", body_text))

        if frame_matches:
            # --- Beamer Presentation Parsing ---
            # Frontmatter before first frame (e.g. \titlepage, \tableofcontents)
            first_frame_pos = body_start_offset + frame_matches[0].start()
            if first_frame_pos > body_start_offset:
                fm_content = latex_code[body_start_offset:first_frame_pos]
                if fm_content.strip():
                    start_l = latex_code[:body_start_offset].count("\n") + 1
                    end_l = start_l + fm_content.count("\n")
                    chunks.append(DocumentChunk(
                        chunk_id="frontmatter",
                        title="Title & Outline Setup",
                        chunk_type="frontmatter",
                        start_offset=body_start_offset,
                        end_offset=first_frame_pos,
                        start_line=start_l,
                        end_line=end_l,
                        content=fm_content,
                        is_content_chunk=False,
                    ))

            # Parse each frame
            for idx, fm in enumerate(frame_matches, start=1):
                f_start = body_start_offset + fm.start()
                # Find matching \end{frame}
                end_frame_match = re.search(r"\\end\{frame\}", latex_code[f_start:])
                if end_frame_match:
                    f_end = f_start + end_frame_match.end()
                else:
                    # Fallback to next frame start or content end
                    next_start = (body_start_offset + frame_matches[idx].start()) if idx < len(frame_matches) else content_end_offset
                    f_end = next_start

                f_content = latex_code[f_start:f_end]
                title_group = fm.group(1) if fm.lastindex and fm.group(1) else f"Slide {idx}"
                clean_title = re.sub(r"\\[a-zA-Z]+(?:\{[^}]*\})?", "", title_group).strip() or f"Slide {idx}"
                start_l = latex_code[:f_start].count("\n") + 1
                end_l = start_l + f_content.count("\n")

                chunks.append(DocumentChunk(
                    chunk_id=f"frame_{idx}",
                    title=f"Frame {idx}: {clean_title}",
                    chunk_type="frame",
                    start_offset=f_start,
                    end_offset=f_end,
                    start_line=start_l,
                    end_line=end_l,
                    content=f_content,
                    is_content_chunk=True,
                ))

        elif chapter_matches:
            # --- Multi-Chapter Report / Thesis Parsing ---
            first_ch_pos = body_start_offset + chapter_matches[0].start()
            if first_ch_pos > body_start_offset:
                fm_content = latex_code[body_start_offset:first_ch_pos]
                if fm_content.strip():
                    start_l = latex_code[:body_start_offset].count("\n") + 1
                    end_l = start_l + fm_content.count("\n")
                    chunks.append(DocumentChunk(
                        chunk_id="frontmatter",
                        title="Frontmatter (Title Page, Abstract, TOC)",
                        chunk_type="frontmatter",
                        start_offset=body_start_offset,
                        end_offset=first_ch_pos,
                        start_line=start_l,
                        end_line=end_l,
                        content=fm_content,
                        is_content_chunk=False,
                    ))

            for idx, cm in enumerate(chapter_matches, start=1):
                c_start = body_start_offset + cm.start()
                if idx < len(chapter_matches):
                    c_end = body_start_offset + chapter_matches[idx].start()
                else:
                    c_end = content_end_offset

                c_content = latex_code[c_start:c_end]
                raw_title = cm.group(1).strip()
                clean_title = re.sub(r"\\[a-zA-Z]+(?:\{[^}]*\})?", "", raw_title).strip()
                start_l = latex_code[:c_start].count("\n") + 1
                end_l = start_l + c_content.count("\n")

                chunks.append(DocumentChunk(
                    chunk_id=f"chapter_{idx}",
                    title=f"Chapter {idx}: {clean_title}",
                    chunk_type="chapter",
                    start_offset=c_start,
                    end_offset=c_end,
                    start_line=start_l,
                    end_line=end_l,
                    content=c_content,
                    is_content_chunk=True,
                ))

        elif section_matches:
            # --- Section-Based Article / Paper Parsing ---
            first_sec_pos = body_start_offset + section_matches[0].start()
            if first_sec_pos > body_start_offset:
                fm_content = latex_code[body_start_offset:first_sec_pos]
                if fm_content.strip():
                    start_l = latex_code[:body_start_offset].count("\n") + 1
                    end_l = start_l + fm_content.count("\n")
                    chunks.append(DocumentChunk(
                        chunk_id="frontmatter",
                        title="Frontmatter (Title, Authors, Abstract)",
                        chunk_type="frontmatter",
                        start_offset=body_start_offset,
                        end_offset=first_sec_pos,
                        start_line=start_l,
                        end_line=end_l,
                        content=fm_content,
                        is_content_chunk=False,
                    ))

            for idx, sm in enumerate(section_matches, start=1):
                s_start = body_start_offset + sm.start()
                if idx < len(section_matches):
                    s_end = body_start_offset + section_matches[idx].start()
                else:
                    s_end = content_end_offset

                s_content = latex_code[s_start:s_end]
                raw_title = sm.group(1).strip()
                clean_title = re.sub(r"\\[a-zA-Z]+(?:\{[^}]*\})?", "", raw_title).strip()
                start_l = latex_code[:s_start].count("\n") + 1
                end_l = start_l + s_content.count("\n")

                chunks.append(DocumentChunk(
                    chunk_id=f"section_{idx}",
                    title=f"Section {idx}: {clean_title}",
                    chunk_type="section",
                    start_offset=s_start,
                    end_offset=s_end,
                    start_line=start_l,
                    end_line=end_l,
                    content=s_content,
                    is_content_chunk=True,
                ))

        else:
            # Fallback: Single whole body chunk
            if content_end_offset > body_start_offset:
                content = latex_code[body_start_offset:content_end_offset]
                start_l = latex_code[:body_start_offset].count("\n") + 1
                end_l = start_l + content.count("\n")
                chunks.append(DocumentChunk(
                    chunk_id="content_body",
                    title="Document Body",
                    chunk_type="content",
                    start_offset=body_start_offset,
                    end_offset=content_end_offset,
                    start_line=start_l,
                    end_line=end_l,
                    content=content,
                    is_content_chunk=True,
                ))

        return chunks

    def get_chunks(self, latex_code: str) -> List[DocumentChunk]:
        """Returns all chunks in the document in order."""
        return self.index_document(latex_code)

    def get_content_chunks(self, latex_code: str) -> List[DocumentChunk]:
        """Returns all content chunks (excluding preamble and frontmatter)."""
        return [c for c in self.index_document(latex_code) if c.is_content_chunk]

    def get_chunk_by_id(self, latex_code: str, chunk_id: str) -> Optional[DocumentChunk]:
        """Finds a chunk by chunk_id."""
        for c in self.index_document(latex_code):
            if c.chunk_id == chunk_id:
                return c
        return None

    def replace_chunk(
        self,
        latex_code: str,
        chunk_id: str,
        new_content: str,
    ) -> Tuple[str, Optional[DocumentChunk], int]:
        """
        Replaces the specified chunk's full content using character offsets.
        Returns: (updated_latex_code, updated_chunk, length_delta)
        """
        chunks = self.index_document(latex_code)
        target = next((c for c in chunks if c.chunk_id == chunk_id), None)
        if not target:
            return latex_code, None, 0

        before = latex_code[:target.start_offset]
        after = latex_code[target.end_offset:]
        updated_code = before + new_content + after
        length_delta = len(new_content) - len(target.content)

        # Re-index to get the updated chunk object
        new_chunks = self.index_document(updated_code)
        updated_target = next((c for c in new_chunks if c.chunk_id == chunk_id), None)

        return updated_code, updated_target, length_delta

    def extract_key_terms(self, latex_code: str) -> List[str]:
        """
        Extracts distinctive topic terms, chapter titles, and metadata from the document.
        """
        terms: List[str] = []
        chunks = self.index_document(latex_code)
        for c in chunks:
            # Extract title components
            title_text = re.sub(r"^(?:Chapter|Section|Frame)\s+\d+:\s*", "", c.title).strip()
            if len(title_text) > 3 and not title_text.startswith("Slide"):
                terms.append(title_text)

        # Extract \title{...}
        t_match = re.search(r"\\title(?:\[[^\]]*\])?\{([^}]+)\}", latex_code)
        if t_match:
            clean = re.sub(r"\\[a-zA-Z]+(?:\{[^}]*\})?", "", t_match.group(1)).strip()
            if len(clean) > 3:
                terms.append(clean)

        return list(dict.fromkeys(terms))
