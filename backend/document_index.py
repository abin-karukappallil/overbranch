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


@dataclass
class CollectionEntry:
    """An ordered/enumerated collection of structural sibling items."""
    collection_id: str           # stable hash of the shared heading pattern
    collection_type: str         # "beamer_frame_group" | "bibitem" | "itemize" | "enumerate" | "table_rows"
    member_page_ids: list        # ordered list of member page_ids (or item identifiers)
    member_offsets: list         # list of (start_offset, end_offset) for each member
    last_member_end_offset: int  # char offset right after the last member
    numbering_style: str         # e.g. "Paper {n}", "\\bibitem{{key}}", ordinal, or "none"
    current_count: int           # number of existing members
    parent_title: str            # e.g. "Literature Survey" or section name
    sample_members: list         # 1-2 existing member content strings for style reference


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
    text = re.sub(r"\bbetwen\b|\bbetweeen\b", "between", text)
    text = re.sub(r"\binsertin\b|\badditionedits\b|\badditonal\b", "add", text)

    content_pages = [p for p in doc_index.pages if p.page_type not in ("preamble", "postamble")]
    if not content_pages:
        return None

    # 1b. Relative positioning: "between slide X and Y", "after slide X", "before slide Y", "after literature survey"
    between_match = re.search(r"between\s+(?:slide|frame|page|section)?\s*#?\s*(\d+)\s+(?:and|&)\s+(?:slide|frame|page|section)?\s*#?\s*(\d+)", text)
    if between_match:
        first_num = int(between_match.group(1))
        # Anchor on the first slide (insertion will happen directly after it)
        if 1 <= first_num <= len(content_pages):
            return content_pages[first_num - 1].page_index

    after_num_match = re.search(r"(?:after|following|behind|post)\s+(?:slide|frame|page|section)?\s*#?\s*(\d+)", text)
    if after_num_match:
        num = int(after_num_match.group(1))
        if 1 <= num <= len(content_pages):
            return content_pages[num - 1].page_index

    before_num_match = re.search(r"(?:before|prior\s+to|preceding|ahead\s+of)\s+(?:slide|frame|page|section)?\s*#?\s*(\d+)", text)
    if before_num_match:
        num = int(before_num_match.group(1))
        # Insertion before slide N means anchoring on slide N (or slide N-1)
        if 1 <= num <= len(content_pages):
            return content_pages[num - 1].page_index

    # 2. Match fractional numbers like "7/7", "(7/7)", "1/7"
    fraction_match = re.search(r"\(?(\d+)\s*/\s*(\d+)\)?", text)
    if fraction_match:
        target_num = fraction_match.group(1)
        for page in content_pages:
            if f"({target_num}/" in page.title or f" {target_num}/" in page.title or f"({target_num}/" in page.content:
                return page.page_index

    # 3. Match survey / paper / item / topic numbering: "literature survey 7", "survey 7", "paper 3"
    survey_match = re.search(
        r"(?:literature\s+survey|survey|paper|item|part|topic)\s*#?\s*(\d+)", text
    )
    if survey_match:
        num = survey_match.group(1)
        # Check if any slide has this specific survey/paper number in its title or content
        for page in content_pages:
            title_lower = page.title.lower()
            if (f"({num}/" in title_lower or f" {num}/" in title_lower or
                f"survey ({num}" in title_lower or f"paper {num}" in title_lower or
                f"survey {num}" in title_lower or f"({num})" in title_lower):
                return page.page_index

    # 4. Explicit slide/page/frame number references: "slide 7", "slide #7", "slide-7", "frame 3", "page 12", "7th slide"
    slide_num_match = re.search(
        r"(?:slide|frame|page|section)\s*[:#\-]?\s*(\d+)", text
    )
    if slide_num_match:
        num = int(slide_num_match.group(1))
        if 1 <= num <= len(content_pages):
            return content_pages[num - 1].page_index

    # Ordinal numbers: "7th slide", "3rd frame", "1st page", "seventh slide"
    ordinal_map = {
        "1st": 1, "first": 1,
        "2nd": 2, "second": 2,
        "3rd": 3, "third": 3,
        "4th": 4, "fourth": 4,
        "5th": 5, "fifth": 5,
        "6th": 6, "sixth": 6,
        "7th": 7, "seventh": 7,
        "8th": 8, "eighth": 8,
        "9th": 9, "ninth": 9,
        "10th": 10, "tenth": 10,
    }
    ord_match = re.search(
        r"\b(1st|2nd|3rd|[4-9]th|10th|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+(?:slide|frame|page|section)\b",
        text
    )
    if ord_match:
        ord_word = ord_match.group(1)
        num = ordinal_map.get(ord_word)
        if num and 1 <= num <= len(content_pages):
            return content_pages[num - 1].page_index

    # 5. Position references: "penultimate slide", "2nd last slide", "last slide", "final slide", "first slide"
    if any(w in text for w in ["penultimate slide", "second to last slide", "2nd to last slide", "2nd last slide", "penultimate frame"]):
        if len(content_pages) >= 2:
            return content_pages[-2].page_index
    if any(w in text for w in ["last slide", "final slide", "end slide", "closing slide", "last frame", "final frame"]):
        return content_pages[-1].page_index
    if any(w in text for w in ["title page", "title slide", "first slide", "cover slide", "first frame", "cover page"]):
        return content_pages[0].page_index
    if any(w in text for w in ["outline", "agenda", "table of contents"]):
        if len(content_pages) >= 2:
            return content_pages[1].page_index

    # 6. Content matching: "slide with this content", "slide containing", "slide about", or unique content query
    # Check if user instruction mentions text inside page.content
    content_query = ""
    content_phrase_m = re.search(
        r"(?:with\s+this\s+content|with\s+content|having\s+content|slide\s+with|containing|titled|having|about|content|text)\s*[:\-]?\s*[\"']?([^\"'\n\r]+)[\"']?",
        text,
        re.IGNORECASE
    )
    if content_phrase_m:
        extracted = content_phrase_m.group(1).strip()
        content_query = re.sub(
            r"^(?:this\s+content|content|text|words|the|that|a|an)\s*[:\-]?\s*",
            "",
            extracted,
            flags=re.IGNORECASE
        ).strip().lower()

    best_match_idx = None
    best_match_score = 0.0

    # Generic words that should not count as title/content matches
    _GENERIC_WORDS = {"slide", "frame", "page", "section", "the", "this", "that", "edit", "change", "modify", "update", "issue", "overflow", "fix", "delete", "remove", "drop", "erase", "content", "with"}

    # Extract any numbers in the prompt
    prompt_numbers = set(re.findall(r"\b\d+\b", text))

    for page in content_pages:
        title_lower = page.title.lower()
        content_lower = page.content.lower()

        # If user gave an explicit content query substring
        if content_query and len(content_query) >= 3 and content_query in content_lower:
            score = 10.0 + len(content_query)
            if score > best_match_score:
                best_match_score = score
                best_match_idx = page.page_index
                continue

        page_numbers = set(re.findall(r"\b\d+\b", title_lower))

        # If user specified a number and the slide has numbers, they MUST overlap
        if prompt_numbers and page_numbers and not (prompt_numbers & page_numbers):
            continue

        # Exact title substring in instruction — high priority
        if title_lower and title_lower in text:
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

        # Content keyword overlap (if title did not match)
        if best_match_score < 1.0 and text_words:
            content_words = set(re.findall(r"[a-z]{4,}", content_lower)) - _GENERIC_WORDS
            content_overlap = text_words & content_words
            if len(content_overlap) >= 1:
                c_score = len(content_overlap) * 0.8
                if c_score > best_match_score:
                    best_match_score = c_score
                    best_match_idx = page.page_index

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


# ---------------------------------------------------------------------------
# Broad / plural instruction detection
# ---------------------------------------------------------------------------

# Patterns that indicate the user wants to audit, fix, or clean up issues across the code
_FIX_ALL_PATTERNS = [
    re.compile(r"\b(?:fix|repair|clean\s*up|resolve|debug|check)\s+all\s+(?:the\s+)?(?:issues|errors|bugs|problems|warnings|broken\s*code)\b", re.IGNORECASE),
    re.compile(r"\bfix\s+all\s+(?:issues|errors|bugs|problems|warnings|broken\s*code)\s+(?:in|throughout|across)\s+(?:this|the)?\s*(?:latex|code|document|paper|report|presentation|project|file)?\b", re.IGNORECASE),
    re.compile(r"\b(?:check|make\s*sure|ensure)\s+(?:no\s+)?(?:broken\s*code|errors|issues|comment\s*overlap)\b", re.IGNORECASE),
    re.compile(r"\bfix\s+(?:all\s+)?(?:broken\s*code|broken\s*latex|syntax\s*errors)\b", re.IGNORECASE),
    re.compile(r"\b(?:fix|correct)\s+(?:all\s+)?(?:comment\s*overlap|comment\s*issues|escaped\s*characters)\b", re.IGNORECASE),
    re.compile(r"\b(?:all\s+ok\s+if\s+any\s+changes\s+fix|if\s+any\s+issues\s+fix)\b", re.IGNORECASE),
    re.compile(r"\bfix\s+(?:all\s+)?(?:compile|compilation)\s+(?:errors|issues)\b", re.IGNORECASE),
]

# Patterns that indicate the user wants to edit ALL sections/chapters/slides,
# not just a single specific one.
_BROAD_PATTERNS = [
    re.compile(r"\b(?:all|every|each)\s+(?:chapter|section|slide|frame|page|part)s?\b", re.IGNORECASE),
    re.compile(r"\b(?:all|every|each)\s+(?:of\s+)?(?:the\s+)?(?:chapter|section|slide|frame|page|part)s?\b", re.IGNORECASE),
    re.compile(r"\bthroughout\s+(?:the\s+)?(?:document|presentation|paper|report)\b", re.IGNORECASE),
    re.compile(r"\b(?:entire|whole|full)\s+(?:document|presentation|paper|report)\b", re.IGNORECASE),
    re.compile(r"\bevery\s+(?:single\s+)?(?:chapter|section|slide|frame|page|part)\b", re.IGNORECASE),
    re.compile(r"\b(?:across|in)\s+all\s+(?:chapter|section|slide|frame|page|part)s?\b", re.IGNORECASE),
    re.compile(r"\ball\s+(?:the\s+)?(?:existing\s+)?(?:chapter|section|slide|frame|page|part)s?\b", re.IGNORECASE),
] + _FIX_ALL_PATTERNS


def is_fix_all_instruction(user_instruction: str) -> bool:
    """
    Detect whether user wants to audit/repair errors, broken code,
    or comment overlaps throughout the entire document.
    """
    if not user_instruction:
        return False

    text = user_instruction.strip()
    for pattern in _FIX_ALL_PATTERNS:
        if pattern.search(text):
            logger.info(f"Fix-all instruction detected: '{text[:80]}' matched {pattern.pattern}")
            return True

    return False


def is_broad_instruction(user_instruction: str) -> bool:
    """
    Detect whether a user instruction targets multiple / all sections
    rather than a single specific one.

    Returns True for instructions like:
      - "elaborate the content in all chapters"
      - "add more detail to every section"
      - "improve content throughout the document"
      - "expand each slide"
      - "fix all issues in this latex code"
      - "make sure no broken code or comment overlap is there"

    Returns False for single-target instructions like:
      - "expand the methodology section"
      - "edit slide 3"
      - "fix the introduction"
    """
    if not user_instruction:
        return False

    text = user_instruction.strip()
    for pattern in _BROAD_PATTERNS:
        if pattern.search(text):
            logger.info(f"Broad instruction detected: '{text[:80]}' matched {pattern.pattern}")
            return True

    return False


def resolve_all_targets(
    doc_index: DocumentIndex,
    target_type: Optional[str] = None,
    include_preamble: bool = False,
) -> List[PageEntry]:
    """
    Return all content PageEntry objects of the requested type.

    For broad/plural instructions, this returns every chapter/section/frame
    in the document (excluding postamble, and preamble unless include_preamble=True)
    so the caller can iterate over them individually.

    Args:
        doc_index: Parsed document index.
        target_type: Optional filter — "frame", "section", or None for all
                     content pages.
        include_preamble: When True, also includes the preamble page so
                          packages and document-level setup are audited.

    Returns:
        List of PageEntry objects matching the filter, in document order.
    """
    if not doc_index.pages:
        return []

    excluded = ("postamble",) if include_preamble else ("preamble", "postamble")
    content_pages = [
        p for p in doc_index.pages
        if p.page_type not in excluded
    ]

    if target_type:
        content_pages = [p for p in content_pages if p.page_type == target_type]

    logger.info(
        f"resolve_all_targets: {len(content_pages)} targets "
        f"(type={target_type or 'all'}, include_preamble={include_preamble}, total_pages={len(doc_index.pages)})"
    )
    return content_pages


# ---------------------------------------------------------------------------
# Ordered Collection Detection & Resolution
# ---------------------------------------------------------------------------

_APPEND_COLLECTION_PATTERNS = [
    # "add [a new/another/...] [xai ieee] paper/slide/reference/item/row"
    re.compile(r"\b(?:add|append|insert|include)\s+(?:a\s+|an\s+|one\s+)?(?:new|another|extra|more|additional|next)?\s*(?:[\w\-]+\s+)*(?:paper|slide|frame|reference|citation|bibitem|item|bullet|point|row|entry|work|study|survey)\b", re.IGNORECASE),
    # "add another ...", "add one more ...", "insert a new ..."
    re.compile(r"\b(?:add|append|insert)\s+(?:another|one\s+more|a\s+new|an\s+additional|the\s+next)\b", re.IGNORECASE),
    # "add xai ieee paper", "insert survey paper"
    re.compile(r"\b(?:add|append|insert)\s+(?:[\w\-]+\s+)*(?:paper|reference|citation|slide|item|row)\b", re.IGNORECASE),
    # "add paper 8", "insert slide 8"
    re.compile(r"\b(?:add|append|insert)\s+(?:paper|slide|frame|item|ref|row)\s*#?\s*\d+\b", re.IGNORECASE),
    # "add ... to (the) survey/collection/list/references/table"
    re.compile(r"\b(?:add|append|insert)\s+.*?\bto\s+(?:the\s+)?(?:collection|survey|literature\s+survey|list|references|bibliography|table)\b", re.IGNORECASE),
]


def is_append_to_collection_instruction(user_prompt: str) -> bool:
    """
    Detect whether user wants to append a new item to an existing
    ordered collection (slide, paper, reference, item, row, etc.).
    """
    if not user_prompt:
        return False

    text = user_prompt.strip()

    # Exclude broad-edit and fix-all instructions
    if is_broad_instruction(text) or is_fix_all_instruction(text):
        return False

    # Exclude explicit edit, delete, or new-from-scratch instructions
    if re.search(r"^\s*(?:edit|modify|update|change|rewrite|improve|fix|repair|debug|delete|remove|drop)\b", text, re.IGNORECASE):
        if not re.search(r"\b(?:add|append|insert|include)\b", text, re.IGNORECASE):
            return False

    # Exclude brand new document creation from scratch
    if re.search(r"^\s*(?:create|generate|make|build|write)\s+(?:a\s+|an\s+)?(?:new\s+)?(?:presentation|paper|report|document|deck|slides|cv|resume)\b", text, re.IGNORECASE):
        return False

    # Positive match patterns
    for pattern in _APPEND_COLLECTION_PATTERNS:
        if pattern.search(text):
            logger.info(f"Append-to-collection instruction detected: '{text[:80]}' matched {pattern.pattern}")
            return True

    return False


def compute_next_ordinal(collection: CollectionEntry) -> Tuple[int, str]:
    """
    Deterministically compute the next ordinal number and formatted label
    for appending to an existing collection.

    Returns:
        (next_ordinal, next_label)
        e.g. (8, "Paper 8") or (8, "Literature Survey (8/8)") or (5, "\\bibitem{ref5}")
    """
    next_ord = collection.current_count + 1
    style = collection.numbering_style or ""

    if "{n}" in style:
        if "{total}" in style:
            label = style.format(n=next_ord, total=next_ord)
        else:
            label = style.format(n=next_ord)
    elif collection.collection_type == "bibitem":
        label = f"\\bibitem{{ref{next_ord}}}"
    elif collection.collection_type in ("enumerate", "itemize"):
        label = "\\item"
    elif collection.collection_type == "beamer_frame_group":
        if "paper" in collection.parent_title.lower():
            label = f"Paper {next_ord}"
        else:
            label = f"{collection.parent_title} {next_ord}"
    else:
        label = f"{collection.parent_title} {next_ord}" if collection.parent_title else f"Item {next_ord}"

    return next_ord, label


def detect_collections(
    doc_index: DocumentIndex,
    latex_code: str,
) -> List[CollectionEntry]:
    """
    Detect ordered/enumerated collections of structural sibling items in the document.

    Identifies:
      1. Beamer frame groups (consecutive frames sharing a title prefix, fraction, or numbering template)
      2. \\bibitem bibliography entries inside or outside \\begin{thebibliography}
      3. \\item entries inside enumerate and itemize environments
      4. Table rows inside tabular environments

    Returns:
        List of CollectionEntry objects.
    """
    if not latex_code:
        return []

    collections: List[CollectionEntry] = []

    # ── 1. Beamer frame groups ───────────────────────────────────────────
    frame_pages = [p for p in doc_index.pages if p.page_type == "frame"]
    if frame_pages:
        def extract_frame_info(p: PageEntry):
            title = p.title.strip()
            # Fraction pattern: e.g. "Literature Survey (1/7)" or "Survey (1/7): Paper A"
            m_frac = re.search(r"(.*?)\s*\((\d+)\s*/\s*(\d+)\)(.*)", title)
            if m_frac:
                prefix = m_frac.group(1).strip() or "Literature Survey"
                cur_n = int(m_frac.group(2))
                return prefix, f"{prefix} ({{n}}/{{total}})", cur_n

            # "Paper 1", "Paper 2", etc.
            m_paper = re.search(r"^(.*?)(?:\b(Paper|Slide|Survey|Work|Ref|Study|Model)\s*#?\s*)(\d+)(.*)$", title, re.IGNORECASE)
            if m_paper:
                prefix = (m_paper.group(1).strip() + " " + m_paper.group(2).strip()).strip()
                cur_n = int(m_paper.group(3))
                return prefix, f"{prefix} {{n}}", cur_n

            # Prefix before colon or dash, e.g. "Literature Survey - Paper A"
            m_colon = re.search(r"^(.*?)\s*[:\-\u2013\u2014]\s*(.*)$", title)
            if m_colon and len(m_colon.group(1).strip()) >= 3:
                prefix = m_colon.group(1).strip()
                return prefix, f"{prefix} {{n}}", None

            # Generic fallback: if title contains "Literature Survey" or "Survey"
            if re.search(r"\b(?:literature\s+survey|survey\s+paper|paper)\b", title, re.IGNORECASE):
                prefix = "Literature Survey" if "survey" in title.lower() else "Paper"
                return prefix, f"{prefix} {{n}}", None

            return None, None, None

        # Group consecutive frames with compatible prefix / pattern
        current_group: List[PageEntry] = []
        current_prefix = None
        current_style = None

        for p in frame_pages:
            prefix, style, _ = extract_frame_info(p)
            if prefix:
                norm_prefix = prefix.lower()
                norm_cur = current_prefix.lower() if current_prefix else None

                if norm_cur and (norm_prefix in norm_cur or norm_cur in norm_prefix):
                    current_group.append(p)
                else:
                    if current_group:
                        if len(current_group) >= 2 or (len(current_group) == 1 and current_style and "{n}" in current_style):
                            collections.append(_build_frame_collection(current_group, current_prefix, current_style))
                    current_group = [p]
                    current_prefix = prefix
                    current_style = style
            else:
                if current_group:
                    if len(current_group) >= 2 or (len(current_group) == 1 and current_style and "{n}" in current_style):
                        collections.append(_build_frame_collection(current_group, current_prefix, current_style))
                    current_group = []
                    current_prefix = None
                    current_style = None

        if current_group and (len(current_group) >= 2 or (len(current_group) == 1 and current_style and "{n}" in current_style)):
            collections.append(_build_frame_collection(current_group, current_prefix, current_style))

    # ── 2. \bibitem entries ──────────────────────────────────────────────
    bib_matches = list(re.finditer(r"\\bibitem(?:\s*\[([^\]]*)\])?\s*\{([^}]+)\}", latex_code))
    if bib_matches:
        member_ids = []
        member_offsets = []
        sample_members = []
        for i, m in enumerate(bib_matches):
            key = m.group(2)
            member_ids.append(key)
            start_off = m.start()
            if i + 1 < len(bib_matches):
                end_off = bib_matches[i + 1].start()
            else:
                end_env = re.search(r"\\end\{thebibliography\}", latex_code[start_off:])
                if end_env:
                    end_off = start_off + end_env.start()
                else:
                    end_off = m.end()
            member_offsets.append((start_off, end_off))

        for s, e in member_offsets[-2:]:
            sample_members.append(latex_code[s:e].strip())

        last_offset = member_offsets[-1][1] if member_offsets else 0
        collections.append(CollectionEntry(
            collection_id="collection-bibitem-references",
            collection_type="bibitem",
            member_page_ids=member_ids,
            member_offsets=member_offsets,
            last_member_end_offset=last_offset,
            numbering_style="\\bibitem{{{key}}}",
            current_count=len(member_ids),
            parent_title="References",
            sample_members=sample_members,
        ))

    # ── 3. enumerate and itemize lists ───────────────────────────────────
    for env_m in re.finditer(r"\\begin\{(enumerate|itemize)\}([\s\S]*?)\\end\{\1\}", latex_code):
        env_type = env_m.group(1)
        env_body = env_m.group(2)
        body_start = env_m.start(2)

        item_matches = list(re.finditer(r"\\item(?:\s*\[[^\]]*\])?", env_body))
        if len(item_matches) >= 2:
            item_offsets = []
            item_ids = []
            for i, itm in enumerate(item_matches):
                item_start = body_start + itm.start()
                if i + 1 < len(item_matches):
                    item_end = body_start + item_matches[i + 1].start()
                else:
                    item_end = body_start + len(env_body)
                item_offsets.append((item_start, item_end))
                item_ids.append(f"{env_type}-item-{i+1}")

            sample_items = [latex_code[s:e].strip() for s, e in item_offsets[-2:]]
            collections.append(CollectionEntry(
                collection_id=f"collection-{env_type}-{env_m.start()}",
                collection_type=env_type,
                member_page_ids=item_ids,
                member_offsets=item_offsets,
                last_member_end_offset=item_offsets[-1][1],
                numbering_style="\\item",
                current_count=len(item_ids),
                parent_title=f"{env_type.title()} List",
                sample_members=sample_items,
            ))

    # ── 4. Table rows inside tabular ─────────────────────────────────────
    for tab_m in re.finditer(r"\\begin\{(?:tabular|tabularx)\}(?:\{[^}]*\})*([\s\S]*?)\\end\{(?:tabular|tabularx)\}", latex_code):
        tab_body = tab_m.group(1)
        tab_start = tab_m.start(1)

        raw_rows = tab_body.split("\\\\")
        valid_rows = []
        curr_offset = tab_start
        for r in raw_rows:
            clean_r = re.sub(r"\\(?:hline|toprule|midrule|bottomrule)", "", r).strip()
            if clean_r and "&" in clean_r:
                valid_rows.append((curr_offset, curr_offset + len(r) + 2, r.strip()))
            curr_offset += len(r) + 2

        if len(valid_rows) >= 2:
            collections.append(CollectionEntry(
                collection_id=f"collection-table-rows-{tab_m.start()}",
                collection_type="table_rows",
                member_page_ids=[f"row-{i+1}" for i in range(len(valid_rows))],
                member_offsets=[(r[0], r[1]) for r in valid_rows],
                last_member_end_offset=valid_rows[-1][1],
                numbering_style="row",
                current_count=len(valid_rows),
                parent_title="Table Rows",
                sample_members=[r[2] for r in valid_rows[-2:]],
            ))

    return collections


def _build_frame_collection(group: List[PageEntry], prefix: str, style: Optional[str]) -> CollectionEntry:
    """Helper to build a CollectionEntry for a group of frames."""
    parent_title = prefix or "Literature Survey"
    numbering_style = style or (f"{parent_title} {{n}}" if "paper" not in parent_title.lower() else "Paper {n}")

    sample_members = []
    if group:
        sample_members.append(group[0].content)
        if len(group) > 1:
            sample_members.append(group[-1].content)

    return CollectionEntry(
        collection_id=f"collection-beamer-{_slug(parent_title)}",
        collection_type="beamer_frame_group",
        member_page_ids=[p.page_id for p in group],
        member_offsets=[(p.start_offset, p.end_offset) for p in group],
        last_member_end_offset=group[-1].end_offset,
        numbering_style=numbering_style,
        current_count=len(group),
        parent_title=parent_title,
        sample_members=sample_members,
    )


def resolve_collection(
    doc_index: DocumentIndex,
    latex_code: str,
    instruction: str,
) -> Optional[CollectionEntry]:
    """
    Resolve the best-matching CollectionEntry for a given user instruction.
    """
    if not instruction or not instruction.strip():
        return None

    collections = detect_collections(doc_index, latex_code)
    if not collections:
        return None

    inst_lower = instruction.lower()

    if len(collections) == 1:
        c = collections[0]
        if c.collection_type == "bibitem" and any(w in inst_lower for w in ["slide", "frame"]):
            return None
        if c.collection_type == "beamer_frame_group" and any(w in inst_lower for w in ["reference", "bibitem", "cite"]):
            return None
        return c

    best_score = -1.0
    best_coll = None
    inst_words = set(re.findall(r"\b[a-z0-9_\-]+\b", inst_lower))
    stopwords = {"add", "append", "insert", "include", "put", "new", "another", "one", "more", "the", "a", "an", "to", "in", "for", "of", "and", "please", "can", "you", "my"}
    keywords = inst_words - stopwords

    for c in collections:
        score = 0.0
        parent_lower = c.parent_title.lower()
        style_lower = c.numbering_style.lower()

        for kw in keywords:
            if kw in parent_lower:
                score += 4.0
            if kw in style_lower:
                score += 3.0
            if any(kw in s.lower() for s in c.sample_members):
                score += 1.5

        if c.collection_type == "beamer_frame_group":
            if any(w in inst_lower for w in ["paper", "survey", "slide", "frame", "literature"]):
                score += 4.0
            if "literature" in parent_lower and any(w in inst_lower for w in ["paper", "survey", "xai", "ieee"]):
                score += 5.0
        elif c.collection_type == "bibitem":
            if any(w in inst_lower for w in ["reference", "citation", "bib", "bibitem", "source"]):
                score += 6.0
        elif c.collection_type in ("enumerate", "itemize"):
            if any(w in inst_lower for w in ["item", "bullet", "point", "list", "numbered"]):
                score += 5.0
        elif c.collection_type == "table_rows":
            if any(w in inst_lower for w in ["table", "row", "entry", "column", "comparison"]):
                score += 5.0

        if score > best_score:
            best_score = score
            best_coll = c

    if best_score >= 2.0:
        return best_coll

    return None

