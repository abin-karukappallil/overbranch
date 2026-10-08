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


def ensure_document_environment(code: str) -> str:
    """
    Ensures that a LaTeX document with \\documentclass contains both
    \\begin{document} and \\end{document} in their proper structural positions,
    and deduplicates multiple occurrences.
    Guarantees that rewrite-like agentic edits never produce code with missing
    \\begin{document}.
    """
    if not code or not code.strip():
        return code

    # Only process documents that define a \\documentclass
    if not re.search(r"\\documentclass\b", code):
        return code

    def doc_tags(src: str) -> Tuple[List["re.Match"], List["re.Match"]]:
        # Real \begin/\end{document} only: found on the masked view, so one mentioned in a
        # comment ("% notes after \end{document}") or shown in a verbatim / lstlisting
        # example is not a duplicate. Deduplicating raw text deleted the real
        # \end{document} when a comment after it mentioned one, and stripped the lines
        # out of listings. (Masking is length-preserving, so offsets apply to ``src``.)
        try:
            from edit_validator import clean_latex_for_validation
            view = clean_latex_for_validation(src)
            if len(view) != len(src):
                view = src
        except Exception:
            view = src
        return (list(re.finditer(r"\\begin\s*\{document\}", view)),
                list(re.finditer(r"\\end\s*\{document\}", view)))

    # Deduplicate multiple \\begin{document} if present
    begin_matches, _ = doc_tags(code)
    if len(begin_matches) > 1:
        # Keep the first, remove the subsequent duplicates
        for m in reversed(begin_matches[1:]):
            code = code[:m.start()] + code[m.end():]

    # Deduplicate multiple \\end{document} if present
    begin_matches, end_matches = doc_tags(code)
    if len(end_matches) > 1:
        # Keep the last, remove earlier duplicates
        for m in reversed(end_matches[:-1]):
            code = code[:m.start()] + code[m.end():]
        begin_matches, end_matches = doc_tags(code)

    has_begin_doc = len(begin_matches) > 0
    has_end_doc = len(end_matches) > 0

    if has_begin_doc and has_end_doc:
        return code

    lines = code.splitlines(keepends=True)

    if not has_begin_doc:
        # Find the optimal boundary line to insert \\begin{document}
        # Pre-scan for body triggers: \\chapter, \\section, \\begin{frame}, \\maketitle, \\begin{abstract}, etc.
        body_trigger_pattern = re.compile(
            r"^\s*\\(?:chapter\*?|section\*?|subsection\*?|subsubsection\*?|part\*?|"
            r"maketitle|tableofcontents|titlepage)\b|"
            r"^\s*\\begin\s*\{(?:frame|titlepage|abstract)\}"
        )
        insert_line_idx = -1
        for idx, line in enumerate(lines):
            if body_trigger_pattern.search(line):
                insert_line_idx = idx
                break

        # If no explicit structural trigger was found, find the end of preamble declarations
        if insert_line_idx == -1:
            preamble_macros = re.compile(
                r"^\s*\\(?:documentclass|usepackage|RequirePackage|definecolor|colorlet|usetheme|usecolortheme|"
                r"usefonttheme|useinnertheme|useoutertheme|setbeamer[a-zA-Z*]+|setbeamertemplate|setbeamercolor|"
                r"setbeamerfont|title|author|date|institute|titlegraphic|newcommand|renewcommand|DeclareMathOperator|"
                r"DeclarePairedDelimiter|geometry|hypersetup|pagestyle|thispagestyle|setlength|tikzset|usetikzlibrary|"
                r"bibliographystyle)\b"
            )
            last_preamble_line = -1
            in_multiline_macro = False
            for idx, line in enumerate(lines):
                stripped = line.strip()
                if not stripped or stripped.startswith("%"):
                    continue
                if preamble_macros.search(line):
                    last_preamble_line = idx
                    open_braces = line.count("{")
                    close_braces = line.count("}")
                    if open_braces > close_braces:
                        in_multiline_macro = True
                    continue
                if in_multiline_macro:
                    open_braces = line.count("{")
                    close_braces = line.count("}")
                    if close_braces >= open_braces:
                        in_multiline_macro = False
                    last_preamble_line = idx
                    continue

                if last_preamble_line != -1 and not in_multiline_macro:
                    insert_line_idx = idx
                    break

            if insert_line_idx == -1:
                insert_line_idx = (last_preamble_line + 1) if last_preamble_line != -1 else len(lines)

        lines.insert(insert_line_idx, "\\begin{document}\n\n")
        code = "".join(lines)

    # Now verify \\end{document}
    if not re.search(r"\\end\s*\{document\}", code):
        code = code.rstrip() + "\n\\end{document}\n"

    return code


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

        # Auto-repair document environment if a standalone LaTeX document is missing \begin{document}
        if re.search(r"\\documentclass\b", latex_code) and not re.search(r"\\begin\s*\{document\}", latex_code):
            latex_code = ensure_document_environment(latex_code)

        chunks: List[DocumentChunk] = []
        doc_len = len(latex_code)

        # 1. Preamble Detection
        doc_begin_match = re.search(r"\\begin\s*\{document\}", latex_code)
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

        # Preserve \begin{document} if target is preamble and new_content omits it
        if target.chunk_id == "preamble":
            if r"\begin{document}" in target.content and not re.search(r"\\begin\s*\{document\}", new_content):
                new_content = new_content.rstrip() + "\n\\begin{document}\n"

        before = latex_code[:target.start_offset]
        after = latex_code[target.end_offset:]
        updated_code = before + new_content + after

        # Ensure document structure integrity (\begin{document} and \end{document})
        updated_code = ensure_document_environment(updated_code)
        length_delta = len(updated_code) - len(target.content)

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


# ============================================================================
# Structural nodes with stable IDs
# ============================================================================
#
# Chunk IDs above are positional (``section_3``): inserting a section renumbers
# every later one, so an ID handed to the model at step 1 can name a different
# section by step 3. Node IDs are derived from what a node *is* — its kind and
# its title or label — so they survive edits elsewhere in the document. They
# live only in memory; nothing is written into the user's LaTeX.

HEADING_LEVELS = {
    "part": 0, "chapter": 1, "section": 2, "subsection": 3, "subsubsection": 4, "paragraph": 5,
}
_HEADING_PREFIX = {
    "part": "part", "chapter": "chapter", "section": "sec", "subsection": "subsec",
    "subsubsection": "subsubsec", "paragraph": "para",
}
META_COMMANDS = ("title", "subtitle", "author", "date", "institute", "titlegraphic")

_RE_HEADING = re.compile(r"\\(part|chapter|section|subsection|subsubsection|paragraph)\*?\s*(?:\[[^\]]*\])?\s*\{")
_RE_ENV = re.compile(r"\\(begin|end)\s*\{\s*([A-Za-z@*][A-Za-z0-9@*]*)\s*\}")
_RE_META = re.compile(r"\\(" + "|".join(META_COMMANDS) + r")\s*(?:\[[^\]]*\])?\s*\{")
_RE_LABEL = re.compile(r"\\label\s*\{([^}]+)\}")
_RE_FRAMETITLE = re.compile(r"\\frametitle\s*(?:\[[^\]]*\])?\s*\{")
_RE_CMD_STRIP = re.compile(r"\\[A-Za-z@]+\*?")


@dataclass
class DocumentNode:
    node_id: str
    kind: str            # preamble | meta | maketitle | heading kind | frame | env
    name: str            # env name / heading kind / meta command
    title: str
    start: int           # offsets into the document (end exclusive)
    end: int
    start_line: int
    end_line: int
    parent_id: Optional[str] = None
    body_start: int = 0  # first offset after the opening line / \begin{...}[..]{..}
    body_end: int = 0    # offset of the closing \end{...} (== end for headings)
    labels: Tuple[str, ...] = ()
    ordinal: int = 0     # 1-based position among nodes of the same kind

    def summary(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id, "kind": self.kind, "title": self.title,
            "lines": [self.start_line, self.end_line], "parent": self.parent_id,
        }


def slugify(text: str, limit: int = 40) -> str:
    """Stable, readable slug of a LaTeX title: commands dropped, arguments kept."""
    text = _RE_CMD_STRIP.sub(" ", text or "")
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text[:limit].strip("-")


def _match_brace_at(s: str, i: int) -> int:
    """Index just past the brace group that opens at s[i] == '{' (or len(s) if unbalanced)."""
    depth = 0
    j = i
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return len(s)


def _skip_args(masked: str, j: int) -> int:
    """Skips the optional [...] and {...} groups that follow an environment opener."""
    n = len(masked)
    while j < n:
        k = j
        while k < n and masked[k] in " \t":
            k += 1
        if k < n and masked[k] == "[":
            close = masked.find("]", k)
            if close == -1:
                return j
            j = close + 1
            continue
        if k < n and masked[k] == "{" and "\n" not in masked[j:k]:
            j = _match_brace_at(masked, k)
            continue
        return j
    return j


def _line_of(starts: List[int], offset: int) -> int:
    import bisect
    return bisect.bisect_right(starts, offset)


def index_nodes(code: str) -> List[DocumentNode]:
    """
    Parses ``code`` into structural nodes, outermost first, in document order.

    Structure is read from the validator's masked view (comments, verbatim
    bodies and macro-definition bodies neutralised, length preserved), so a
    ``\\section`` inside a listing or a comment is never mistaken for one.
    """
    if not code:
        return []
    try:
        from edit_validator import clean_latex_for_validation
        masked = clean_latex_for_validation(code)
        if len(masked) != len(code):
            masked = code
    except Exception:
        masked = code

    line_starts = [0] + [m.end() for m in re.finditer(r"\n", code)]
    doc_end = len(code)
    begin_doc = re.search(r"\\begin\s*\{document\}", masked)
    end_doc = None
    for m in re.finditer(r"\\end\s*\{document\}", masked):
        end_doc = m
    body_lo = begin_doc.end() if begin_doc else 0
    body_hi = end_doc.start() if end_doc else doc_end

    raw: List[Dict[str, Any]] = []

    if begin_doc:
        raw.append(dict(kind="preamble", name="preamble", title="Preamble", start=0, end=begin_doc.end(),
                        body_start=0, body_end=begin_doc.start(), base="preamble"))

    for m in _RE_META.finditer(masked):
        brace = m.end() - 1
        end = _match_brace_at(masked, brace)
        title = code[brace + 1:end - 1].strip()
        raw.append(dict(kind="meta", name=m.group(1), title=title, start=m.start(), end=end,
                        body_start=brace + 1, body_end=end - 1, base=f"meta:{m.group(1)}"))

    # Pages of an imported PDF (pdf2latex writes a marker comment before each).
    # Read from the raw text: the markers are comments, which the masked view blanks.
    marks = list(re.finditer(r"^%% ==== OB-PAGE (\d+) ====$", code, re.MULTILINE))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else body_hi
        if end > m.start():
            raw.append(dict(kind="page", name="page", title=f"Page {m.group(1)}", start=m.start(), end=end,
                            body_start=m.end() + 1, body_end=end, base=f"page:{m.group(1)}"))

    for m in re.finditer(r"\\maketitle\b|\\titlepage\b", masked):
        raw.append(dict(kind="maketitle", name=m.group(0)[1:], title="Title page", start=m.start(), end=m.end(),
                        body_start=m.end(), body_end=m.end(), base="maketitle"))

    # Environments (matched with a stack; unmatched begins are left out).
    stack: List[Tuple[str, re.Match]] = []
    for m in _RE_ENV.finditer(masked):
        kind, name = m.group(1), m.group(2)
        if name == "document":
            continue
        if kind == "begin":
            stack.append((name, m))
            continue
        for depth in range(len(stack) - 1, -1, -1):
            if stack[depth][0] == name:
                _, bm = stack[depth]
                del stack[depth:]
                header_end = _skip_args(masked, bm.end())
                inner = code[header_end:m.start()]
                title = ""
                if name == "frame":
                    after = masked[bm.end():header_end]
                    tm = re.search(r"\{", after)
                    if tm:
                        b = bm.end() + tm.start()
                        title = code[b + 1:_match_brace_at(masked, b) - 1]
                    if not title:
                        ft = _RE_FRAMETITLE.search(masked, header_end, m.start())
                        if ft:
                            title = code[ft.end():_match_brace_at(masked, ft.end() - 1) - 1]
                labels = tuple(_RE_LABEL.findall(inner))
                raw.append(dict(kind="frame" if name == "frame" else "env", name=name, title=title.strip(),
                                start=bm.start(), end=m.end(), body_start=header_end, body_end=m.start(),
                                labels=labels))
                break

    # Headings: a heading's node runs to the next heading of the same or a
    # higher level, or the end of the enclosing body.
    heads = list(_RE_HEADING.finditer(masked))
    for idx, m in enumerate(heads):
        if not (body_lo <= m.start() < body_hi):
            continue
        hk = m.group(1)
        level = HEADING_LEVELS[hk]
        brace = m.end() - 1
        title_end = _match_brace_at(masked, brace)
        end = body_hi
        for nxt in heads[idx + 1:]:
            if HEADING_LEVELS[nxt.group(1)] <= level and nxt.start() < body_hi:
                end = nxt.start()
                break
        # A heading inside a frame/minipage ends with that environment.
        for r in raw:
            if r["kind"] in ("frame", "env") and r["start"] < m.start() < r["end"]:
                end = min(end, r["body_end"])
        line_end = code.find("\n", title_end)
        body_start = line_end + 1 if line_end != -1 and line_end < end else title_end
        own = re.match(r"\s*\\label\s*\{([^}]+)\}", code[title_end:end])
        labels = (own.group(1),) if own else ()
        raw.append(dict(kind=hk, name=hk, title=code[brace + 1:title_end - 1].strip(), start=m.start(), end=end,
                        body_start=body_start, body_end=end, labels=labels[:1]))

    raw.sort(key=lambda r: (r["start"], -(r["end"] - r["start"])))

    nodes: List[DocumentNode] = []
    seen_ids: Dict[str, int] = {}
    ordinals: Dict[str, int] = {}
    open_nodes: List[DocumentNode] = []
    for r in raw:
        while open_nodes and not (open_nodes[-1].start <= r["start"] and r["end"] <= open_nodes[-1].end):
            open_nodes.pop()
        parent = open_nodes[-1] if open_nodes else None
        kind = r["kind"]
        ordinals[kind] = ordinals.get(kind, 0) + 1
        if "base" in r:
            base = r["base"]
        elif kind == "frame":
            slug = slugify(r["title"])
            base = f"frame:{slug}" if slug else f"frame#{ordinals[kind]}"
        elif kind in HEADING_LEVELS:
            slug = slugify(r["title"]) or str(ordinals[kind])
            base = f"{_HEADING_PREFIX[kind]}:{slug}"
        else:
            label = r.get("labels") or ()
            if label:
                base = f"env:{r['name']}:{slugify(label[0])}"
            else:
                scope = parent.node_id if parent and parent.kind != "preamble" else "doc"
                base = f"env:{r['name']}@{scope}"
        count = seen_ids.get(base, 0) + 1
        seen_ids[base] = count
        node_id = base if count == 1 and not (kind == "env" and "@" in base) else f"{base}#{count}"
        node = DocumentNode(
            node_id=node_id, kind=kind, name=r["name"], title=r["title"],
            start=r["start"], end=r["end"],
            start_line=_line_of(line_starts, r["start"]),
            end_line=_line_of(line_starts, max(r["start"], r["end"] - 1)),
            parent_id=parent.node_id if parent else None,
            body_start=r["body_start"], body_end=r["body_end"],
            labels=tuple(r.get("labels") or ()), ordinal=ordinals[kind],
        )
        nodes.append(node)
        open_nodes.append(node)
    return nodes


def find_node(nodes: List[DocumentNode], ref: str) -> Optional[DocumentNode]:
    """
    Looks a node up by stable ID, label, or ordinal shorthand:
    ``sec:introduction``, ``label:fig:arch``, ``frame#3`` / ``slide 3``,
    ``section 2``, ``title`` (the \\title command, else the title page).
    """
    if not ref:
        return None
    ref = ref.strip()
    by_id = {n.node_id: n for n in nodes}
    if ref in by_id:
        return by_id[ref]
    low = ref.lower()
    if low.startswith("label:"):
        want = ref[6:]
        return next((n for n in nodes if want in n.labels), None)
    m = re.fullmatch(r"(frame|slide|section|sec|chapter|subsection|subsec|page)\s*[#_ :]\s*(\d+)", low)
    if m:
        kind = {"slide": "frame", "sec": "section", "subsec": "subsection"}.get(m.group(1), m.group(1))
        n_want = int(m.group(2))
        return next((n for n in nodes if n.kind == kind and n.ordinal == n_want), None)
    if low in ("title", "meta:title"):
        return by_id.get("meta:title") or next((n for n in nodes if n.kind == "maketitle"), None)
    # A bare slug or title: unique match on the slug part of the ID or the title.
    slug = slugify(ref)
    if slug:
        hits = [n for n in nodes if n.node_id.split(":", 1)[-1].split("#")[0] == slug or slugify(n.title) == slug]
        if len(hits) == 1:
            return hits[0]
    return None
