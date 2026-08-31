"""
document_index.py — Document Structure Parser

Parses LaTeX documents into a structured page/slide index keyed by stable IDs.
Used by context_builder (targeted retrieval) and edit_validator (scope checking).

Supports:
  - Beamer presentations (\\begin{frame}...\\end{frame})
  - Articles / reports (\\section / \\subsection)
"""
import re
import hashlib
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger("document_index")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PageEntry:
    """One logical page/slide in the document."""
    page_id: str              # Stable identifier: label, title slug, or "page-N"
    page_index: int           # 0-based sequential index
    page_type: str            # "preamble", "frame", "section", "postamble"
    title: str                # Human-readable title (frame title or section name)
    start_offset: int         # Character offset in source (inclusive)
    end_offset: int           # Character offset in source (exclusive)
    content: str              # Raw LaTeX source for this page
    content_hash: str = ""    # SHA-256 fingerprint for dedup / change detection

    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = hashlib.sha256(
                self.content.strip().encode("utf-8")
            ).hexdigest()[:16]


@dataclass
class DocumentIndex:
    """Full structural index of a LaTeX document."""
    pages: List[PageEntry] = field(default_factory=list)
    doc_type: str = "unknown"       # "beamer", "article", "report", "letter"
    has_preamble: bool = False
    total_frames: int = 0
    total_sections: int = 0

    def get_page_by_id(self, page_id: str) -> Optional[PageEntry]:
        for p in self.pages:
            if p.page_id == page_id:
                return p
        return None

    def get_page_by_index(self, idx: int) -> Optional[PageEntry]:
        if 0 <= idx < len(self.pages):
            return self.pages[idx]
        return None


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_DOCCLASS_RE = re.compile(r"\\documentclass(?:\[[^\]]*\])?\{([^}]+)\}")
_BEGIN_DOC_RE = re.compile(r"\\begin\{document\}")
_END_DOC_RE = re.compile(r"\\end\{document\}")

# Frame detection — handles \begin{frame}{Title}, \begin{frame}[opts]{Title},
# \begin{frame}[plain], \begin{frame} with \frametitle{}, etc.
_FRAME_BEGIN_RE = re.compile(
    r"\\begin\{frame\}"
    r"(?:\s*\[[^\]]*\])?"          # optional [plain] or [fragile]
    r"(?:\s*\{([^}]*)\})?"         # optional {Title}
)
_FRAME_END_RE = re.compile(r"\\end\{frame\}")
_FRAMETITLE_RE = re.compile(r"\\frametitle\{([^}]*)\}")
_FRAME_LABEL_RE = re.compile(r"\\label\{([^}]*)\}")

_SECTION_RE = re.compile(r"\\section\{([^}]*)\}")
_SUBSECTION_RE = re.compile(r"\\subsection\{([^}]*)\}")


# ---------------------------------------------------------------------------
# Slug helper
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    """Convert a title to a stable, lowercase slug."""
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:40] or "untitled"


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

def parse_document_structure(latex_code: str) -> DocumentIndex:
    """
    Parse a LaTeX document into a structured page/slide index.

    For Beamer documents, each \\begin{frame}...\\end{frame} is a page.
    For articles/reports, each \\section{...} block is a page.
    The preamble (before \\begin{document}) is always page 0.
    """
    if not latex_code or not latex_code.strip():
        return DocumentIndex()

    # Detect document class
    dc_match = _DOCCLASS_RE.search(latex_code)
    doc_class = dc_match.group(1).lower() if dc_match else "article"
    is_beamer = doc_class == "beamer"
    doc_type = "beamer" if is_beamer else doc_class

    # Find document body boundaries
    begin_doc = _BEGIN_DOC_RE.search(latex_code)
    end_doc = _END_DOC_RE.search(latex_code)

    pages: List[PageEntry] = []
    page_idx = 0

    # --- Preamble ---
    if begin_doc:
        preamble_end = begin_doc.start()
        if preamble_end > 0:
            preamble_text = latex_code[:preamble_end].strip()
            if preamble_text:
                pages.append(PageEntry(
                    page_id="preamble",
                    page_index=page_idx,
                    page_type="preamble",
                    title="Preamble",
                    start_offset=0,
                    end_offset=preamble_end,
                    content=preamble_text,
                ))
                page_idx += 1

    body_start = begin_doc.end() if begin_doc else 0
    body_end = end_doc.start() if end_doc else len(latex_code)
    body = latex_code[body_start:body_end]

    if is_beamer:
        pages, page_idx = _parse_beamer_frames(body, body_start, pages, page_idx)
    else:
        pages, page_idx = _parse_sections(body, body_start, pages, page_idx)

    # --- Postamble (after last frame/section, before \end{document}) ---
    if pages and pages[-1].page_type not in ("preamble",):
        last_content_end = pages[-1].end_offset
        if last_content_end < body_start + len(body):
            post_text = latex_code[last_content_end:body_start + len(body)].strip()
            if post_text and len(post_text) > 10:
                pages.append(PageEntry(
                    page_id="postamble",
                    page_index=page_idx,
                    page_type="postamble",
                    title="Postamble",
                    start_offset=last_content_end,
                    end_offset=body_start + len(body),
                    content=post_text,
                ))
                page_idx += 1

    total_frames = sum(1 for p in pages if p.page_type == "frame")
    total_sections = sum(1 for p in pages if p.page_type == "section")

    idx = DocumentIndex(
        pages=pages,
        doc_type=doc_type,
        has_preamble=any(p.page_type == "preamble" for p in pages),
        total_frames=total_frames,
        total_sections=total_sections,
    )

    logger.info(
        f"Document index: type={doc_type}, pages={len(pages)}, "
        f"frames={total_frames}, sections={total_sections}"
    )
    return idx


def _parse_beamer_frames(
    body: str,
    body_offset: int,
    pages: List[PageEntry],
    page_idx: int,
) -> Tuple[List[PageEntry], int]:
    """Parse Beamer frames from the document body."""
    seen_ids: set = set()

    for match in _FRAME_BEGIN_RE.finditer(body):
        frame_start = match.start()

        # Find matching \end{frame}
        end_match = _FRAME_END_RE.search(body, match.end())
        if not end_match:
            continue
        frame_end = end_match.end()

        frame_content = body[frame_start:frame_end]

        # Extract title: inline {Title} or \frametitle{Title}
        title = match.group(1) or ""
        if not title:
            ft_match = _FRAMETITLE_RE.search(frame_content)
            if ft_match:
                title = ft_match.group(1)
        title = title.strip()

        # Build stable page_id: prefer \label{}, then title slug, then index
        label_match = _FRAME_LABEL_RE.search(frame_content)
        if label_match:
            page_id = f"frame-{label_match.group(1)}"
        elif title:
            page_id = f"frame-{_slug(title)}"
        else:
            page_id = f"frame-{page_idx}"

        # Deduplicate IDs
        base_id = page_id
        counter = 2
        while page_id in seen_ids:
            page_id = f"{base_id}-{counter}"
            counter += 1
        seen_ids.add(page_id)

        pages.append(PageEntry(
            page_id=page_id,
            page_index=page_idx,
            page_type="frame",
            title=title or f"Slide {page_idx}",
            start_offset=body_offset + frame_start,
            end_offset=body_offset + frame_end,
            content=frame_content,
        ))
        page_idx += 1

    return pages, page_idx


def _parse_sections(
    body: str,
    body_offset: int,
    pages: List[PageEntry],
    page_idx: int,
) -> Tuple[List[PageEntry], int]:
    """Parse section-based structure for articles/reports."""
    section_starts: List[Tuple[int, str]] = []
    seen_ids: set = set()

    for m in _SECTION_RE.finditer(body):
        section_starts.append((m.start(), m.group(1).strip()))

    if not section_starts:
        # No sections found — treat entire body as one page
        if body.strip():
            pages.append(PageEntry(
                page_id="body",
                page_index=page_idx,
                page_type="section",
                title="Document Body",
                start_offset=body_offset,
                end_offset=body_offset + len(body),
                content=body.strip(),
            ))
            page_idx += 1
        return pages, page_idx

    # Content before first section
    if section_starts[0][0] > 0:
        pre_content = body[:section_starts[0][0]].strip()
        if pre_content and len(pre_content) > 10:
            pages.append(PageEntry(
                page_id="pre-sections",
                page_index=page_idx,
                page_type="section",
                title="Pre-Section Content",
                start_offset=body_offset,
                end_offset=body_offset + section_starts[0][0],
                content=pre_content,
            ))
            page_idx += 1

    for i, (start, title) in enumerate(section_starts):
        end = section_starts[i + 1][0] if i + 1 < len(section_starts) else len(body)
        content = body[start:end].strip()

        page_id = f"sec-{_slug(title)}"
        base_id = page_id
        counter = 2
        while page_id in seen_ids:
            page_id = f"{base_id}-{counter}"
            counter += 1
        seen_ids.add(page_id)

        pages.append(PageEntry(
            page_id=page_id,
            page_index=page_idx,
            page_type="section",
            title=title,
            start_offset=body_offset + start,
            end_offset=body_offset + end,
            content=content,
        ))
        page_idx += 1

    return pages, page_idx


# ---------------------------------------------------------------------------
# Target identification
# ---------------------------------------------------------------------------

def find_target_page(
    doc_index: DocumentIndex,
    user_instruction: str,
) -> Optional[int]:
    """
    Identify which page/slide the user's instruction targets.

    Returns the page_index of the best match, or None if the instruction
    targets the whole document or cannot be localized.
    """
    if not doc_index.pages or not user_instruction:
        return None

    # 1. Normalize common typos in instruction
    text = user_instruction.lower().strip()
    text = re.sub(r"\blitertaure\b", "literature", text)
    text = re.sub(r"\bsldies\b|\bslidee\b|\bslid\b", "slide", text)
    text = re.sub(r"\bconetnts\b|\bcontetns\b", "contents", text)

    content_pages = [p for p in doc_index.pages if p.page_type not in ("preamble", "postamble")]

    # 2. Match fractional numbers like "7/7", "(7/7)", "1/7"
    fraction_match = re.search(r"\(?(\d+)\s*/\s*(\d+)\)?", text)
    if fraction_match:
        target_num = fraction_match.group(1)
        for page in content_pages:
            if f"({target_num}/" in page.title or f" {target_num}/" in page.title:
                return page.page_index

    # 3. Match survey / paper / item / topic numbering: "literature survey 7", "survey 7", "paper 3"
    survey_match = re.search(
        r"(?:literature\s+survey|survey|paper|item|part|topic)\s*#?\s*(\d+)", text
    )
    if survey_match:
        num = survey_match.group(1)
        # Check if any slide has this specific survey/paper number in its title
        for page in content_pages:
            title_lower = page.title.lower()
            if (f"({num}/" in title_lower or f" {num}/" in title_lower or
                f"survey ({num}" in title_lower or f"paper {num}" in title_lower or
                f"survey {num}" in title_lower or f"({num})" in title_lower):
                return page.page_index

    # 4. Explicit slide/page/frame number references: "slide 7", "frame 3", "page 12"
    slide_num_match = re.search(
        r"(?:slide|frame|page)\s*#?\s*(\d+)", text
    )
    if slide_num_match:
        num = int(slide_num_match.group(1))
        if 1 <= num <= len(content_pages):
            return content_pages[num - 1].page_index
        return None

    # 5. Explicit title references: "the introduction slide", "conclusion section"
    best_match_idx = None
    best_match_score = 0.0

    # Generic words that should not count as title matches
    _GENERIC_WORDS = {"slide", "frame", "page", "section", "the", "this", "that", "edit", "change", "modify", "update", "issue", "overflow", "fix"}

    # Extract any numbers in the prompt
    prompt_numbers = set(re.findall(r"\b\d+\b", text))

    for page in content_pages:
        title_lower = page.title.lower()
        if not title_lower:
            continue

        page_numbers = set(re.findall(r"\b\d+\b", title_lower))

        # If user specified a number and the slide has numbers, they MUST overlap
        # (prevents "survey 7" from matching "Literature Survey (1/7)")
        if prompt_numbers and page_numbers and not (prompt_numbers & page_numbers):
            continue

        # Exact title substring in instruction — high priority
        if title_lower in text:
            score = 2.0 + len(title_lower) / max(len(text), 1)
            if prompt_numbers and (prompt_numbers & page_numbers):
                score += 3.0  # Big boost when numbers align
            if score > best_match_score:
                best_match_score = score
                best_match_idx = page.page_index

        # Check individual significant words from title (excluding generics)
        title_words = set(re.findall(r"[a-z]{3,}", title_lower)) - _GENERIC_WORDS
        text_words = set(re.findall(r"[a-z]{3,}", text)) - _GENERIC_WORDS
        if title_words and text_words:
            overlap = title_words & text_words
            if overlap:
                score = len(overlap) / len(title_words)
                if prompt_numbers and (prompt_numbers & page_numbers):
                    score += 2.0  # Boost if numbers match
                if score > best_match_score and score >= 0.5:
                    best_match_score = score
                    best_match_idx = page.page_index

    # 6. Keyword heuristics for common slide positions
    if best_match_idx is None and content_pages:
        if any(w in text for w in ["title page", "title slide", "first slide", "cover"]):
            best_match_idx = content_pages[0].page_index
        elif any(w in text for w in ["last slide", "final slide", "thank you", "closing"]):
            best_match_idx = content_pages[-1].page_index
        elif any(w in text for w in ["outline", "agenda", "table of contents"]):
            if len(content_pages) >= 2:
                best_match_idx = content_pages[1].page_index

    if best_match_idx is not None:
        target = doc_index.get_page_by_index(best_match_idx)
        logger.info(f"Target page identified: idx={best_match_idx}, "
                     f"id='{target.page_id}', title='{target.title}'")
    else:
        logger.info("No specific target page identified — instruction targets full document")

    return best_match_idx


# ---------------------------------------------------------------------------
# Window retrieval
# ---------------------------------------------------------------------------

def get_page_window(
    doc_index: DocumentIndex,
    target_idx: int,
    window: int = 1,
) -> List[PageEntry]:
    """
    Return the target page plus up to `window` pages before and after it.

    Always includes the preamble if present (for context about packages/theme).
    """
    if not doc_index.pages:
        return []

    pages = doc_index.pages
    total = len(pages)

    # Clamp target
    target_idx = max(0, min(target_idx, total - 1))

    start = max(0, target_idx - window)
    end = min(total, target_idx + window + 1)

    window_pages = pages[start:end]

    # Always include preamble for context (theme, packages, colors)
    if doc_index.has_preamble and pages[0].page_type == "preamble":
        if pages[0] not in window_pages:
            window_pages = [pages[0]] + window_pages

    return window_pages
