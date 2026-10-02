"""
document_analyzer.py — Local LaTeX Document Analysis (No LLM Required)
======================================================================
Performs fast, local analysis of LaTeX documents to understand their structure,
content, and metadata without any LLM calls. Used by the context strategy
engine to decide how to present documents to the LLM efficiently.

Provides:
  - DocumentAnalysis: Structured representation of a document's content
  - analyze_document(): Produces a full analysis from raw LaTeX code
  - generate_compact_summary(): Creates a token-efficient summary for LLM context
  - identify_preservation_map(): Determines what should be preserved vs. changed
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("document_analyzer")


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class SectionInfo:
    """Metadata about a single structural section in the document."""
    section_type: str          # "chapter", "section", "subsection", "frame"
    title: str
    start_line: int
    end_line: int
    line_count: int
    char_count: int
    has_figures: bool = False
    has_tables: bool = False
    has_equations: bool = False
    has_code_listings: bool = False
    figure_count: int = 0
    table_count: int = 0
    equation_count: int = 0
    subsection_count: int = 0


@dataclass
class DocumentAnalysis:
    """Complete structural analysis of a LaTeX document."""
    # Document metadata
    document_class: str = ""
    document_class_options: str = ""
    title: str = ""
    author: str = ""
    date: str = ""
    is_beamer: bool = False

    # Scale metrics
    total_lines: int = 0
    total_chars: int = 0
    estimated_tokens: int = 0
    preamble_lines: int = 0
    body_lines: int = 0

    # Structural counts
    chapter_count: int = 0
    section_count: int = 0
    subsection_count: int = 0
    subsubsection_count: int = 0
    frame_count: int = 0

    # Content element counts
    figure_count: int = 0
    table_count: int = 0
    equation_count: int = 0
    citation_count: int = 0
    reference_count: int = 0
    bibitem_count: int = 0
    code_listing_count: int = 0
    algorithm_count: int = 0

    # Package analysis
    packages: List[str] = field(default_factory=list)
    has_bibliography: bool = False
    bibliography_type: str = ""  # "thebibliography", "biblatex", "bibtex"

    # Per-section breakdown
    sections: List[SectionInfo] = field(default_factory=list)

    # Input file references (\input{...}, \include{...})
    input_files: List[str] = field(default_factory=list)

    @property
    def is_large(self) -> bool:
        """Whether the document exceeds typical 'small document' thresholds."""
        return self.total_lines > 500 or self.total_chars > 30000

    @property
    def is_very_large(self) -> bool:
        """Whether the document is very large (potentially exceeds model context)."""
        return self.total_lines > 3000 or self.total_chars > 200000

    @property
    def is_multi_file(self) -> bool:
        """Whether the document references external .tex files."""
        return len(self.input_files) > 0

    @property
    def primary_structure_type(self) -> str:
        """The dominant structural unit: 'chapter', 'section', 'frame', or 'flat'."""
        if self.is_beamer or self.frame_count > 0:
            return "frame"
        if self.chapter_count > 0:
            return "chapter"
        if self.section_count > 0:
            return "section"
        return "flat"

    @property
    def structural_unit_count(self) -> int:
        """Number of top-level structural units."""
        if self.is_beamer or self.frame_count > 0:
            return self.frame_count
        if self.chapter_count > 0:
            return self.chapter_count
        if self.section_count > 0:
            return self.section_count
        return 1

    @property
    def has_math(self) -> bool:
        return self.equation_count > 0

    @property
    def has_tables(self) -> bool:
        return self.table_count > 0

    @property
    def has_figures(self) -> bool:
        return self.figure_count > 0


# ============================================================================
# Core Analysis Functions
# ============================================================================

def analyze_document(latex_code: str) -> DocumentAnalysis:
    """
    Performs comprehensive local analysis of a LaTeX document.

    This is a fast, pure-Python operation — no LLM calls. It extracts:
    - Document class and metadata
    - Structural hierarchy (chapters, sections, frames)
    - Content element counts (figures, tables, equations, citations)
    - Per-section statistics
    - Package list and bibliography type
    - Input/include file references

    Args:
        latex_code: Raw LaTeX source code.

    Returns:
        DocumentAnalysis with all extracted metadata.
    """
    if not latex_code or not latex_code.strip():
        return DocumentAnalysis()

    analysis = DocumentAnalysis()
    lines = latex_code.splitlines(keepends=False)
    analysis.total_lines = len(lines)
    analysis.total_chars = len(latex_code)
    analysis.estimated_tokens = len(latex_code) // 4  # rough approximation

    # --- Document class ---
    dc_match = re.search(r"\\documentclass(?:\[([^\]]*)\])?\{([^}]+)\}", latex_code)
    if dc_match:
        analysis.document_class_options = dc_match.group(1) or ""
        analysis.document_class = dc_match.group(2)
        analysis.is_beamer = analysis.document_class.lower() == "beamer"

    # --- Preamble boundary ---
    begin_doc = re.search(r"\\begin\{document\}", latex_code)
    if begin_doc:
        preamble_text = latex_code[:begin_doc.end()]
        analysis.preamble_lines = preamble_text.count("\n") + 1
        analysis.body_lines = analysis.total_lines - analysis.preamble_lines
    else:
        analysis.preamble_lines = 0
        analysis.body_lines = analysis.total_lines

    # --- Title, Author, Date ---
    title_match = re.search(r"\\title(?:\[[^\]]*\])?\{([^}]+)\}", latex_code)
    if title_match:
        analysis.title = _clean_latex_text(title_match.group(1))

    author_match = re.search(r"\\author\{([^}]+)\}", latex_code)
    if author_match:
        analysis.author = _clean_latex_text(author_match.group(1))

    date_match = re.search(r"\\date\{([^}]+)\}", latex_code)
    if date_match:
        analysis.date = _clean_latex_text(date_match.group(1))

    # --- Packages ---
    analysis.packages = re.findall(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}", latex_code)

    # --- Structural elements ---
    chapter_matches = list(re.finditer(r"\\chapter\*?\{([^}]+)\}", latex_code))
    section_matches = list(re.finditer(r"\\section\*?\{([^}]+)\}", latex_code))
    subsection_matches = list(re.finditer(r"\\subsection\*?\{([^}]+)\}", latex_code))
    subsubsection_matches = list(re.finditer(r"\\subsubsection\*?\{([^}]+)\}", latex_code))
    frame_matches = list(re.finditer(r"\\begin\{frame\}(?:\[[^\]]*\])?(?:\{([^}]*)\})?", latex_code))

    analysis.chapter_count = len(chapter_matches)
    analysis.section_count = len(section_matches)
    analysis.subsection_count = len(subsection_matches)
    analysis.subsubsection_count = len(subsubsection_matches)
    analysis.frame_count = len(frame_matches)

    # --- Content elements ---
    analysis.figure_count = len(re.findall(r"\\begin\{figure\}", latex_code))
    analysis.table_count = len(re.findall(r"\\begin\{(?:table|tabular|tabularx|longtable)\}", latex_code))
    analysis.equation_count = len(re.findall(
        r"\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}", latex_code
    )) + len(re.findall(r"\\\[", latex_code))
    analysis.citation_count = len(re.findall(r"\\cite(?:t|p|author|year|title)?\{", latex_code))
    analysis.bibitem_count = len(re.findall(r"\\bibitem", latex_code))
    analysis.reference_count = max(analysis.citation_count, analysis.bibitem_count)
    analysis.code_listing_count = len(re.findall(r"\\begin\{(?:lstlisting|minted|verbatim)\}", latex_code))
    analysis.algorithm_count = len(re.findall(r"\\begin\{(?:algorithm|algorithmic)\}", latex_code))

    # --- Bibliography type ---
    if re.search(r"\\begin\{thebibliography\}", latex_code):
        analysis.has_bibliography = True
        analysis.bibliography_type = "thebibliography"
    elif re.search(r"\\addbibresource", latex_code) or "biblatex" in str(analysis.packages):
        analysis.has_bibliography = True
        analysis.bibliography_type = "biblatex"
    elif re.search(r"\\bibliography\{", latex_code):
        analysis.has_bibliography = True
        analysis.bibliography_type = "bibtex"

    # --- Input/Include files ---
    analysis.input_files = re.findall(r"\\(?:input|include)\{([^}]+)\}", latex_code)

    # --- Per-section breakdown ---
    if analysis.is_beamer and frame_matches:
        analysis.sections = _build_section_info(latex_code, lines, frame_matches, "frame")
    elif chapter_matches:
        analysis.sections = _build_section_info(latex_code, lines, chapter_matches, "chapter")
    elif section_matches:
        analysis.sections = _build_section_info(latex_code, lines, section_matches, "section")

    return analysis


def _build_section_info(
    latex_code: str,
    lines: List[str],
    matches: List[re.Match],
    section_type: str,
) -> List[SectionInfo]:
    """Builds per-section metadata from regex matches."""
    total_len = len(latex_code)
    sections: List[SectionInfo] = []

    for idx, m in enumerate(matches):
        start_offset = m.start()
        if idx + 1 < len(matches):
            end_offset = matches[idx + 1].start()
        else:
            # Extend to \end{document} or end of file
            end_doc = re.search(r"\\end\{document\}", latex_code[start_offset:])
            end_offset = (start_offset + end_doc.start()) if end_doc else total_len

        section_text = latex_code[start_offset:end_offset]
        start_line = latex_code[:start_offset].count("\n") + 1
        line_count = section_text.count("\n") + 1
        end_line = start_line + line_count - 1

        title = _clean_latex_text(m.group(1) if m.lastindex and m.group(1) else f"{section_type.title()} {idx + 1}")

        sections.append(SectionInfo(
            section_type=section_type,
            title=title,
            start_line=start_line,
            end_line=end_line,
            line_count=line_count,
            char_count=len(section_text),
            has_figures=bool(re.search(r"\\begin\{figure\}", section_text)),
            has_tables=bool(re.search(r"\\begin\{(?:table|tabular|tabularx)\}", section_text)),
            has_equations=bool(re.search(r"\\begin\{(?:equation|align)\}", section_text) or re.search(r"\\\[", section_text)),
            has_code_listings=bool(re.search(r"\\begin\{(?:lstlisting|minted|verbatim)\}", section_text)),
            figure_count=len(re.findall(r"\\begin\{figure\}", section_text)),
            table_count=len(re.findall(r"\\begin\{(?:table|tabular|tabularx)\}", section_text)),
            equation_count=len(re.findall(r"\\begin\{(?:equation|align)\}", section_text)),
            subsection_count=len(re.findall(r"\\subsection\*?\{", section_text)),
        ))

    return sections


def _clean_latex_text(text: str) -> str:
    """Strips LaTeX commands from text to get a clean readable string."""
    cleaned = re.sub(r"\\[a-zA-Z]+(?:\{[^}]*\})?", "", text)
    cleaned = re.sub(r"[{}\\]", "", cleaned)
    return cleaned.strip()


# ============================================================================
# Summary Generation
# ============================================================================

def generate_compact_summary(analysis: DocumentAnalysis) -> str:
    """
    Generates a compact, token-efficient document summary suitable for LLM context.

    This replaces the need to send the full document when the agent only needs
    to understand the document's structure and content at a high level.

    Returns:
        A compact multi-line string summarizing the document.
    """
    parts: List[str] = []

    # Header
    parts.append("DOCUMENT ANALYSIS SUMMARY")
    parts.append("=" * 40)

    # Metadata
    if analysis.title:
        parts.append(f"Title: {analysis.title}")
    if analysis.author:
        parts.append(f"Author: {analysis.author}")
    parts.append(f"Class: \\documentclass[{analysis.document_class_options}]{{{analysis.document_class}}}")

    # Scale
    parts.append(f"Scale: {analysis.total_lines} lines, ~{analysis.estimated_tokens} tokens")
    parts.append(f"Preamble: {analysis.preamble_lines} lines | Body: {analysis.body_lines} lines")

    # Structure type
    parts.append(f"Structure: {analysis.primary_structure_type} ({analysis.structural_unit_count} units)")

    # Content elements
    elements = []
    if analysis.figure_count:
        elements.append(f"{analysis.figure_count} figures")
    if analysis.table_count:
        elements.append(f"{analysis.table_count} tables")
    if analysis.equation_count:
        elements.append(f"{analysis.equation_count} equations")
    if analysis.reference_count:
        elements.append(f"{analysis.reference_count} references")
    if analysis.code_listing_count:
        elements.append(f"{analysis.code_listing_count} code listings")
    if analysis.algorithm_count:
        elements.append(f"{analysis.algorithm_count} algorithms")
    if elements:
        parts.append(f"Content: {', '.join(elements)}")

    if analysis.has_bibliography:
        parts.append(f"Bibliography: {analysis.bibliography_type}")

    if analysis.input_files:
        parts.append(f"External files: {', '.join(analysis.input_files)}")

    # Per-section breakdown
    if analysis.sections:
        parts.append("")
        parts.append("SECTION BREAKDOWN:")
        for idx, sec in enumerate(analysis.sections, 1):
            label = f"  {idx}. [{sec.section_type.upper()}] {sec.title}"
            details = f"(Lines {sec.start_line}–{sec.end_line}, {sec.line_count} lines, {sec.char_count} chars)"
            content_markers = []
            if sec.figure_count:
                content_markers.append(f"{sec.figure_count}fig")
            if sec.table_count:
                content_markers.append(f"{sec.table_count}tab")
            if sec.equation_count:
                content_markers.append(f"{sec.equation_count}eq")
            if sec.subsection_count:
                content_markers.append(f"{sec.subsection_count}subsec")
            markers_str = f" [{', '.join(content_markers)}]" if content_markers else ""
            parts.append(f"{label} {details}{markers_str}")

    return "\n".join(parts)


def generate_preservation_map(
    analysis: DocumentAnalysis,
    user_instruction: str,
) -> Dict[str, Any]:
    """
    Determines what should be preserved vs. changed based on the user's request.

    Returns a structured map:
    {
        "preserve": ["formatting", "document_class", "packages", ...],
        "change": ["topic", "title", "content", ...],
        "expand": ["section_1", "section_3", ...] or "all",
        "add": ["new_section_X", ...],
        "affected_sections": ["section_1", "section_2", ...] or "all"
    }
    """
    user_lower = user_instruction.lower()
    result: Dict[str, Any] = {
        "preserve": [],
        "change": [],
        "expand": [],
        "add": [],
        "affected_sections": [],
    }

    # --- Preservation heuristics ---
    # By default, preserve structural elements
    result["preserve"].append("document_class")
    result["preserve"].append("packages")
    result["preserve"].append("preamble_layout")

    # Check if user wants to keep formatting
    if any(kw in user_lower for kw in ["keep format", "keep the format", "same format",
                                        "preserve format", "keep layout", "same layout",
                                        "keep style", "same style", "keep template",
                                        "use this template", "same template"]):
        result["preserve"].append("formatting")
        result["preserve"].append("template_style")

    # Check if user wants to keep structure
    if any(kw in user_lower for kw in ["keep structure", "same structure",
                                        "preserve structure", "keep hierarchy",
                                        "keep sections", "same sections"]):
        result["preserve"].append("section_hierarchy")

    # Check if user explicitly wants to preserve preamble / bibliography
    if any(kw in user_lower for kw in ["preamble", "keep preamble", "preserve preamble"]):
        result["preserve"].append("preamble")
    if any(kw in user_lower for kw in ["bibliography", "keep bibliography", "preserve bibliography"]):
        result["preserve"].append("bibliography")

    # --- Change heuristics ---
    if any(kw in user_lower for kw in ["change topic", "new topic", "switch topic",
                                        "about ", "make it about", "change to",
                                        "transform to", "convert to"]):
        result["change"].extend(["topic", "title", "content", "examples"])
        if analysis.has_bibliography:
            result["change"].append("references")

    if any(kw in user_lower for kw in ["change title", "new title", "rename"]):
        result["change"].append("title")

    if any(kw in user_lower for kw in ["rewrite", "redo", "overhaul", "replace all"]):
        result["change"].append("content")
        result["affected_sections"] = "all"

    # --- Expansion heuristics ---
    if any(kw in user_lower for kw in ["expand", "elaborate", "more content",
                                        "more detail", "longer", "add depth",
                                        "flesh out", "fill out"]):
        # Check if specific section or all
        section_specific = _find_mentioned_sections(user_lower, analysis)
        if section_specific:
            result["expand"] = section_specific
            result["affected_sections"] = section_specific
        else:
            result["expand"] = "all"
            result["affected_sections"] = "all"

    # --- Addition heuristics ---
    if any(kw in user_lower for kw in ["add a section", "add chapter", "new section",
                                        "new chapter", "insert section", "add a new"]):
        result["add"].append("new_section")

    if any(kw in user_lower for kw in ["add references", "add bibliography",
                                        "add citations"]):
        result["add"].append("references")

    # If no specific sections affected, try to detect from instruction
    if not result["affected_sections"]:
        section_specific = _find_mentioned_sections(user_lower, analysis)
        if section_specific:
            result["affected_sections"] = section_specific
        elif any(result["change"]) or any(result["expand"]):
            result["affected_sections"] = "all"

    return result


def _find_mentioned_sections(
    user_lower: str,
    analysis: DocumentAnalysis,
) -> List[str]:
    """
    Identifies specific sections mentioned in the user instruction.
    Returns a list of section identifiers that match.
    """
    mentioned = []
    for sec in analysis.sections:
        title_lower = sec.title.lower()
        # Check if the section title appears in the user instruction
        if len(title_lower) > 3 and title_lower in user_lower:
            mentioned.append(sec.title)
        # Check for numbered references like "section 3", "chapter 2"
        type_patterns = [
            rf"{sec.section_type}\s+{analysis.sections.index(sec) + 1}\b",
            rf"{sec.section_type}\s+{sec.start_line}\b",
        ]
        for pat in type_patterns:
            if re.search(pat, user_lower):
                mentioned.append(sec.title)
                break

    # Also check for generic section type references
    generic_patterns = {
        "introduction": ["introduction", "intro"],
        "methodology": ["methodology", "methods", "method"],
        "results": ["results", "result", "findings"],
        "conclusion": ["conclusion", "conclusions", "summary"],
        "abstract": ["abstract"],
        "literature": ["literature review", "related work", "background"],
        "discussion": ["discussion"],
    }
    for key, patterns in generic_patterns.items():
        for pat in patterns:
            if pat in user_lower:
                # Find matching section
                for sec in analysis.sections:
                    if pat in sec.title.lower():
                        if sec.title not in mentioned:
                            mentioned.append(sec.title)

    return mentioned


# ============================================================================
# Task State Builder
# ============================================================================

def build_task_state(
    user_instruction: str,
    analysis: DocumentAnalysis,
    preservation_map: Dict[str, Any],
    scope: str,
    attached_documents: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Builds a compact task state string that can be reused across agent iterations.

    This replaces growing conversation history with a focused summary of:
    - What the task is
    - What should be preserved/changed
    - Document structure
    - Attached reference materials
    - Current progress (updated externally)

    Returns:
        A compact multi-line string suitable for LLM system/user context.
    """
    parts: List[str] = []

    parts.append("TASK STATE")
    parts.append("-" * 30)
    parts.append(f"Request: {user_instruction[:200]}")
    parts.append(f"Scope: {scope}")

    if attached_documents:
        att_entries = []
        for att in attached_documents:
            fname = att.get("filename", "reference_document")
            pc = att.get("page_count")
            pc_str = f", {pc} pages" if pc else ""
            att_entries.append(f"{fname} ({att.get('size', 0)} chars{pc_str})")
        parts.append(f"Attached Reference(s): {'; '.join(att_entries)}")

    if analysis.title:
        parts.append(f"Document: {analysis.title}")
    parts.append(f"Scale: {analysis.total_lines} lines, {analysis.structural_unit_count} {analysis.primary_structure_type}s")

    # Preservation map
    if preservation_map.get("preserve"):
        parts.append(f"Preserve: {', '.join(preservation_map['preserve'])}")
    if preservation_map.get("change"):
        parts.append(f"Change: {', '.join(preservation_map['change'])}")
    if preservation_map.get("expand"):
        expand = preservation_map["expand"]
        parts.append(f"Expand: {'all sections' if expand == 'all' else ', '.join(expand)}")
    if preservation_map.get("add"):
        parts.append(f"Add: {', '.join(preservation_map['add'])}")

    affected = preservation_map.get("affected_sections", [])
    if affected == "all":
        parts.append("Affected: all sections")
    elif affected:
        parts.append(f"Affected: {', '.join(affected)}")

    # Content inventory (compact)
    inventory = []
    if analysis.section_count:
        inventory.append(f"{analysis.section_count} sections")
    if analysis.chapter_count:
        inventory.append(f"{analysis.chapter_count} chapters")
    if analysis.frame_count:
        inventory.append(f"{analysis.frame_count} frames")
    if analysis.figure_count:
        inventory.append(f"{analysis.figure_count} figures")
    if analysis.table_count:
        inventory.append(f"{analysis.table_count} tables")
    if analysis.reference_count:
        inventory.append(f"{analysis.reference_count} references")
    if inventory:
        parts.append(f"Content: {', '.join(inventory)}")

    return "\n".join(parts)
