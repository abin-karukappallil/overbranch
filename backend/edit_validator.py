"""
edit_validator.py — Pre-Output Validation Layer

Validates AI-generated edits before returning to the client.
Catches duplicate slides, broken references, scope violations,
and structural integrity issues.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Tuple

logger = logging.getLogger("edit_validator")


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

@dataclass
class ValidationIssue:
    """A single validation failure."""
    check: str          # Which check failed
    severity: str       # "error" | "warning"
    message: str        # Human-readable description
    auto_fixable: bool = False  # Whether auto-repair can fix this


@dataclass
class ValidationResult:
    """Result of running all validation checks."""
    passed: bool = True
    issues: List[ValidationIssue] = field(default_factory=list)

    def add_issue(self, check: str, severity: str, message: str, auto_fixable: bool = False):
        self.issues.append(ValidationIssue(check, severity, message, auto_fixable))
        if severity == "error":
            self.passed = False


# ---------------------------------------------------------------------------
# Individual validation checks
# ---------------------------------------------------------------------------

def validate_no_duplicate_slide_ids(latex: str) -> List[ValidationIssue]:
    """Check that no two frames share the same label or title."""
    issues = []

    # Check \label{} duplicates
    labels = re.findall(r"\\label\{([^}]+)\}", latex)
    seen_labels: Dict[str, int] = {}
    for label in labels:
        seen_labels[label] = seen_labels.get(label, 0) + 1
    for label, count in seen_labels.items():
        if count > 1:
            issues.append(ValidationIssue(
                check="duplicate_label",
                severity="error",
                message=f"Duplicate \\label{{{label}}} found {count} times",
                auto_fixable=False,
            ))

    # Check for duplicate frame titles (exact same \begin{frame}{Title})
    frame_titles = re.findall(
        r"\\begin\{frame\}(?:\s*\[[^\]]*\])?\s*\{([^}]+)\}", latex
    )
    seen_titles: Dict[str, int] = {}
    for title in frame_titles:
        normalized = title.strip()
        seen_titles[normalized] = seen_titles.get(normalized, 0) + 1
    for title, count in seen_titles.items():
        if count > 2:  # Allow 2 (e.g. title + thank you could share)
            issues.append(ValidationIssue(
                check="duplicate_frame_title",
                severity="warning",
                message=f"Frame title '{title}' appears {count} times — possible duplication",
                auto_fixable=True,
            ))

    return issues


def validate_no_duplicated_content(latex: str) -> List[ValidationIssue]:
    """Check that no content block (frame) is duplicated verbatim."""
    issues = []

    # Extract all frame blocks
    frames = re.findall(
        r"(\\begin\{frame\}.*?\\end\{frame\})", latex, re.DOTALL
    )

    if len(frames) < 2:
        return issues

    # Normalize and compare
    seen_frames: Dict[str, int] = {}
    for frame in frames:
        normalized = re.sub(r"\s+", " ", frame.strip())
        if len(normalized) > 50:  # Ignore trivially short frames
            seen_frames[normalized] = seen_frames.get(normalized, 0) + 1

    for frame_text, count in seen_frames.items():
        if count > 1:
            # Extract title for readable message
            title_match = re.search(r"\\begin\{frame\}(?:\s*\[[^\]]*\])?\s*\{([^}]+)\}", frame_text)
            title = title_match.group(1) if title_match else "untitled"
            issues.append(ValidationIssue(
                check="duplicate_content",
                severity="error",
                message=f"Frame '{title}' appears {count} times verbatim — content duplicated",
                auto_fixable=True,
            ))

    return issues


def validate_document_structure(latex: str) -> List[ValidationIssue]:
    """Validate exactly one \\documentclass, \\begin{document}, \\end{document}."""
    issues = []

    dc_count = len(re.findall(r"\\documentclass", latex))
    bd_count = len(re.findall(r"\\begin\{document\}", latex))
    ed_count = len(re.findall(r"\\end\{document\}", latex))

    if dc_count > 1:
        issues.append(ValidationIssue(
            check="multiple_documentclass",
            severity="error",
            message=f"Found {dc_count} \\documentclass declarations (expected 1)",
            auto_fixable=True,
        ))
    if bd_count > 1:
        issues.append(ValidationIssue(
            check="multiple_begin_document",
            severity="error",
            message=f"Found {bd_count} \\begin{{document}} (expected 1)",
            auto_fixable=True,
        ))
    if ed_count > 1:
        issues.append(ValidationIssue(
            check="multiple_end_document",
            severity="error",
            message=f"Found {ed_count} \\end{{document}} (expected 1)",
            auto_fixable=True,
        ))
    if dc_count == 0 and (bd_count > 0 or ed_count > 0):
        issues.append(ValidationIssue(
            check="missing_documentclass",
            severity="warning",
            message="\\begin{document} or \\end{document} found without \\documentclass",
            auto_fixable=False,
        ))

    return issues


def validate_references_intact(
    original: str,
    proposed: str,
) -> List[ValidationIssue]:
    """Check that labels, refs, figures, and equations are preserved."""
    issues = []

    if not original or not proposed:
        return issues

    # Extract \label{} references from original
    orig_labels = set(re.findall(r"\\label\{([^}]+)\}", original))
    prop_labels = set(re.findall(r"\\label\{([^}]+)\}", proposed))

    # Labels that existed in original but are missing in proposed
    missing_labels = orig_labels - prop_labels
    for label in missing_labels:
        # Only flag if the label is referenced somewhere
        if re.search(r"\\(?:ref|eqref|autoref|cref|pageref)\{" + re.escape(label) + r"\}", original):
            issues.append(ValidationIssue(
                check="missing_label",
                severity="warning",
                message=f"Referenced label '{label}' was removed from the edited document",
                auto_fixable=False,
            ))

    # Check \includegraphics references are preserved
    orig_graphics = set(re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", original))
    prop_graphics = set(re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", proposed))
    missing_graphics = orig_graphics - prop_graphics
    for img in missing_graphics:
        issues.append(ValidationIssue(
            check="missing_image",
            severity="warning",
            message=f"Image reference '{img}' was removed",
            auto_fixable=False,
        ))

    return issues


def validate_scope(
    original_code: str,
    proposed_edits: List[Dict[str, Any]],
    target_page_ids: Optional[Set[str]] = None,
) -> List[ValidationIssue]:
    """
    Check that only the targeted sections changed.
    If target_page_ids is None, skip scope checking (whole-document edits).
    """
    issues = []

    if target_page_ids is None:
        return issues  # Whole-document edit, scope is unrestricted

    # For scoped edits, verify that edit original_chunks come from targeted pages
    for i, edit in enumerate(proposed_edits):
        oc = edit.get("original_chunk", "")
        pc = edit.get("proposed_chunk", "")

        if not oc and pc:
            # New content insertion — generally OK
            continue

        # Check if this is a full-document replacement (allowed for conversions)
        if "\\documentclass" in pc and "\\begin{document}" in pc:
            continue

    return issues


def validate_continuous_numbering(latex: str) -> List[ValidationIssue]:
    """Check that frame numbering is continuous (no gaps)."""
    issues = []

    # Count frames
    frame_count = len(re.findall(r"\\begin\{frame\}", latex))
    end_frame_count = len(re.findall(r"\\end\{frame\}", latex))

    if frame_count != end_frame_count:
        issues.append(ValidationIssue(
            check="unmatched_frames",
            severity="error",
            message=f"Mismatched frames: {frame_count} \\begin{{frame}} vs {end_frame_count} \\end{{frame}}",
            auto_fixable=False,
        ))

    return issues


def validate_no_duplicate_headings(
    original_code: str,
    proposed_edits: List[Dict[str, Any]],
) -> List[ValidationIssue]:
    """
    Check that create_content edits don't duplicate existing chapter/section headings.

    When the AI uses create_content (original_chunk == "") to add content that
    has the same heading as an existing chapter/section, this is almost always
    a bug — the AI should have used edit_chunk instead.

    Returns issues with auto_fixable=True so the caller can retry as edit_chunk.
    """
    issues = []

    if not original_code or not proposed_edits:
        return issues

    # Extract existing headings from the original document
    existing_headings: Dict[str, str] = {}  # normalized_title -> raw_title
    for m in re.finditer(r"\\(?:chapter|section|subsection)\{([^}]+)\}", original_code):
        raw_title = m.group(1).strip()
        normalized = re.sub(r"\s+", " ", raw_title).lower().strip()
        existing_headings[normalized] = raw_title

    if not existing_headings:
        return issues

    for i, edit in enumerate(proposed_edits):
        oc = edit.get("original_chunk", "")
        pc = edit.get("proposed_chunk", "")

        # Only check create_content edits (empty original_chunk)
        if oc or not pc:
            continue

        # Extract headings from the proposed chunk
        for m in re.finditer(r"\\(?:chapter|section|subsection)\{([^}]+)\}", pc):
            proposed_title = m.group(1).strip()
            proposed_normalized = re.sub(r"\s+", " ", proposed_title).lower().strip()

            if proposed_normalized in existing_headings:
                existing_raw = existing_headings[proposed_normalized]
                issues.append(ValidationIssue(
                    check="duplicate_heading_create",
                    severity="error",
                    message=(
                        f"create_content edit {i} duplicates existing heading "
                        f"'{existing_raw}' — should use edit_chunk instead"
                    ),
                    auto_fixable=True,
                ))

    return issues


def validate_no_comment_overlap(latex: str) -> List[ValidationIssue]:
    """
    Check for comment overlap issues in LaTeX:
    1. Unescaped % hiding code or closing braces on the same line (e.g. \\textbf{95% accuracy}).
    2. Non-LaTeX comment syntax (<!-- ... -->, // ..., /* ... */).
    3. Conversational commentary leaking into LaTeX output.
    """
    issues = []
    if not latex or not latex.strip():
        return issues

    # 1. Non-LaTeX comment syntax
    if re.search(r"<!--[\s\S]*?-->", latex):
        issues.append(ValidationIssue(
            check="comment_overlap_html",
            severity="error",
            message="HTML-style comments (<!-- ... -->) found in LaTeX code",
            auto_fixable=True,
        ))

    if re.search(r"/\*[\s\S]*?\*/", latex):
        issues.append(ValidationIssue(
            check="comment_overlap_c_style",
            severity="error",
            message="C-style block comments (/* ... */) found in LaTeX code",
            auto_fixable=True,
        ))

    lines = latex.splitlines()
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Check for C++ style comments: // at start of line
        if stripped.startswith("//"):
            issues.append(ValidationIssue(
                check="comment_overlap_slash_slash",
                severity="error",
                message=f"Line {idx}: C++ style '//' comment found in LaTeX code",
                auto_fixable=True,
            ))
            continue

        # Check for conversational leakage at start of line
        if re.match(r"^(?:Here\s+is\s+(?:the|your)?\s*(?:updated|clean|fixed)?\s*(?:code|latex|document|section)|Note:\s+|Sure,?\s+|Below\s+is\s+the|Certainly!|I\s+have\s+(?:updated|fixed|added))\b", stripped, re.IGNORECASE):
            issues.append(ValidationIssue(
                check="comment_overlap_conversational_leak",
                severity="error",
                message=f"Line {idx}: Conversational text leaked into LaTeX code: '{stripped[:50]}...'",
                auto_fixable=True,
            ))
            continue

        # Check for unescaped % that swallows closing braces on the same line
        percent_matches = list(re.finditer(r"(?<!\\)%", line))
        if percent_matches:
            first_pct = percent_matches[0].start()
            prefix = line[:first_pct]
            comment_part = line[first_pct + 1:]

            open_before = len(re.findall(r"(?<!\\)\{", prefix)) - len(re.findall(r"(?<!\\)\}", prefix))
            close_after = len(re.findall(r"(?<!\\)\}", comment_part))

            if open_before > 0 and close_after > 0:
                issues.append(ValidationIssue(
                    check="comment_overlap_swallowed_brace",
                    severity="error",
                    message=(
                        f"Line {idx}: Unescaped '%' comments out closing brace(s) on the same line: "
                        f"'{stripped[:60]}...'"
                    ),
                    auto_fixable=True,
                ))
            elif re.search(r"\b\d+(?:\.\d+)?%", prefix + "%") and not stripped.startswith("%"):
                issues.append(ValidationIssue(
                    check="comment_overlap_unescaped_percent",
                    severity="warning",
                    message=f"Line {idx}: Unescaped '%' after number — likely intended as '\\%': '{stripped[:60]}'",
                    auto_fixable=True,
                ))

    return issues


def validate_no_unmatched_braces(latex: str) -> List[ValidationIssue]:
    """
    Check that braces { and } are balanced across the LaTeX code.
    Strips out comments (lines or portions starting with unescaped %)
    and escaped braces \\{ and \\} before counting.
    """
    issues = []
    if not latex or not latex.strip():
        return issues

    open_braces = 0
    close_braces = 0

    for line in latex.splitlines():
        # Strip comments
        m = re.search(r"(?<!\\)%", line)
        code_part = line[:m.start()] if m else line

        # Strip escaped braces
        clean_code = re.sub(r"\\\{|\\\}", "", code_part)

        open_braces += clean_code.count("{")
        close_braces += clean_code.count("}")

    if open_braces != close_braces:
        issues.append(ValidationIssue(
            check="unmatched_braces",
            severity="error",
            message=f"Unmatched braces: {open_braces} open '{{' vs {close_braces} closing '}}'",
            auto_fixable=False,
        ))

    return issues


def validate_no_structural_regression(original: str, proposed: str) -> List[ValidationIssue]:
    """Check that the proposed document didn't lose major sections or environments."""
    issues = []
    
    if not original or not proposed:
        return issues
        
    orig_sections = len(re.findall(r'\\(?:chapter|section|subsection)\{', original))
    prop_sections = len(re.findall(r'\\(?:chapter|section|subsection)\{', proposed))
    
    orig_envs = len(re.findall(r'\\begin\{(?:titlepage|thebibliography|tabular|figure|table)\}', original))
    prop_envs = len(re.findall(r'\\begin\{(?:titlepage|thebibliography|tabular|figure|table)\}', proposed))
    
    if orig_sections > 3 and prop_sections < orig_sections * 0.5:
        issues.append(ValidationIssue(
            check="structural_regression_sections",
            severity="error",
            message=f"Proposed document lost >50% of sections ({orig_sections} -> {prop_sections})",
            auto_fixable=False,
        ))
        
    if orig_envs > 0 and prop_envs == 0:
        issues.append(ValidationIssue(
            check="structural_regression_environments",
            severity="warning",
            message="Proposed document lost key front-matter or back-matter environments",
            auto_fixable=False,
        ))
        
    if len(original) > 1000 and len(proposed) < len(original) * 0.4:
        issues.append(ValidationIssue(
            check="structural_regression_length",
            severity="warning",
            message=f"Proposed document is < 40% of the original length ({len(original)} -> {len(proposed)} chars)",
            auto_fixable=False,
        ))

    return issues


# ---------------------------------------------------------------------------
# Auto-repair functions
# ---------------------------------------------------------------------------

def auto_repair_duplicates(latex: str) -> Tuple[str, List[str]]:
    """
    Remove duplicate frames from the document.
    Returns (repaired_latex, list_of_repairs_made).
    """
    repairs = []

    # Find all frame blocks
    frames = list(re.finditer(
        r"(\\begin\{frame\}.*?\\end\{frame\})", latex, re.DOTALL
    ))

    if len(frames) < 2:
        return latex, repairs

    # Identify duplicates by normalized content
    seen: Dict[str, int] = {}
    indices_to_remove: List[Tuple[int, int]] = []

    for match in frames:
        normalized = re.sub(r"\s+", " ", match.group(0).strip())
        if normalized in seen:
            # Mark the later occurrence for removal
            indices_to_remove.append((match.start(), match.end()))
            title_m = re.search(r"\{([^}]+)\}", match.group(0)[:100])
            title = title_m.group(1) if title_m else "untitled"
            repairs.append(f"Removed duplicate frame '{title}'")
        else:
            seen[normalized] = match.start()

    if not indices_to_remove:
        return latex, repairs

    # Remove duplicates from end to start to preserve offsets
    result = latex
    for start, end in reversed(sorted(indices_to_remove)):
        # Also remove any leading whitespace/newlines before the frame
        actual_start = start
        while actual_start > 0 and result[actual_start - 1] in ("\n", " ", "\t"):
            actual_start -= 1
        result = result[:actual_start] + result[end:]

    return result, repairs


def auto_repair_structure(latex: str) -> Tuple[str, List[str]]:
    """
    Fix multiple \\documentclass or \\begin{document} / \\end{document}.
    Returns (repaired_latex, list_of_repairs_made).
    """
    repairs = []

    # Remove extra \documentclass (keep the first one)
    dc_matches = list(re.finditer(r"\\documentclass(?:\[[^\]]*\])?\{[^}]+\}", latex))
    if len(dc_matches) > 1:
        for m in reversed(dc_matches[1:]):
            latex = latex[:m.start()] + latex[m.end():]
            repairs.append("Removed duplicate \\documentclass")

    # Remove extra \begin{document} (keep the first one)
    bd_matches = list(re.finditer(r"\\begin\{document\}", latex))
    if len(bd_matches) > 1:
        for m in reversed(bd_matches[1:]):
            latex = latex[:m.start()] + latex[m.end():]
            repairs.append("Removed duplicate \\begin{document}")

    # Remove extra \end{document} (keep the last one)
    ed_matches = list(re.finditer(r"\\end\{document\}", latex))
    if len(ed_matches) > 1:
        for m in ed_matches[:-1]:
            latex = latex[:m.start()] + latex[m.end():]
            repairs.append("Removed duplicate \\end{document}")

    return latex, repairs


# ---------------------------------------------------------------------------
# Top-level validation
# ---------------------------------------------------------------------------

def validate_edit(
    original_code: str,
    proposed_edits: List[Dict[str, Any]],
    target_page_ids: Optional[Set[str]] = None,
) -> ValidationResult:
    """
    Run all validation checks on proposed edits.

    Args:
        original_code: The current document source
        proposed_edits: List of edit dicts with original_chunk/proposed_chunk
        target_page_ids: If set, only these pages should have been edited

    Returns:
        ValidationResult with pass/fail and issue details
    """
    result = ValidationResult()

    if not proposed_edits:
        return result

    # Build the "final" document by applying edits to see what the result looks like
    final_doc = original_code or ""
    for edit in proposed_edits:
        pc = edit.get("proposed_chunk", "")
        oc = edit.get("original_chunk", "")
        if oc and oc in final_doc:
            final_doc = final_doc.replace(oc, pc or "", 1)
        elif pc and not oc:
            # Insertion — just check the proposed chunk itself
            final_doc = pc

    # Run all checks on the final document
    result.issues.extend(validate_no_duplicate_slide_ids(final_doc))
    result.issues.extend(validate_no_duplicated_content(final_doc))
    result.issues.extend(validate_document_structure(final_doc))
    result.issues.extend(validate_continuous_numbering(final_doc))
    result.issues.extend(validate_references_intact(original_code, final_doc))
    result.issues.extend(validate_scope(original_code, proposed_edits, target_page_ids))
    result.issues.extend(validate_no_structural_regression(original_code, final_doc))
    result.issues.extend(validate_no_duplicate_headings(original_code, proposed_edits))
    result.issues.extend(validate_no_comment_overlap(final_doc))
    result.issues.extend(validate_no_unmatched_braces(final_doc))

    # Update passed flag
    result.passed = not any(i.severity == "error" for i in result.issues)

    if result.issues:
        error_count = sum(1 for i in result.issues if i.severity == "error")
        warn_count = sum(1 for i in result.issues if i.severity == "warning")
        logger.warning(
            f"Edit validation: {error_count} errors, {warn_count} warnings"
        )
        for issue in result.issues:
            logger.warning(f"  [{issue.severity.upper()}] {issue.check}: {issue.message}")
    else:
        logger.info("Edit validation: all checks passed")

    return result


def auto_repair_comment_overlap(latex: str) -> Tuple[str, List[str]]:
    """
    Auto-repair comment overlap issues:
    1. Replaces unescaped % after numbers or inside macro brackets with \\%.
    2. Strips HTML <!-- ... --> and C-style /* ... */ comments.
    3. Converts C++ // comments at line start to % comments.
    4. Removes or comments out conversational leakage lines.
    """
    repairs = []
    if not latex or not latex.strip():
        return latex, repairs

    s = latex

    # 1. Strip HTML comments
    if "<!--" in s:
        s = re.sub(r"<!--[\s\S]*?-->", "", s)
        repairs.append("Stripped HTML-style comments (<!-- ... -->)")

    # 2. Strip C-style block comments
    if "/*" in s:
        s = re.sub(r"/\*[\s\S]*?\*/", "", s)
        repairs.append("Stripped C-style comments (/* ... */)")

    cleaned_lines = []
    for line in s.splitlines():
        stripped = line.strip()

        # Convert C++ comments
        if stripped.startswith("//"):
            repairs.append(f"Converted C++ comment to LaTeX: '{stripped[:40]}'")
            cleaned_lines.append(re.sub(r"^(\s*)//", r"\1%", line))
            continue

        # Strip conversational leakage
        if re.match(r"^(?:Here\s+is\s+(?:the|your)?\s*(?:updated|clean|fixed)?\s*(?:code|latex|document|section)|Note:\s+|Sure,?\s+|Below\s+is\s+the|Certainly!)\b", stripped, re.IGNORECASE):
            repairs.append(f"Removed conversational leak: '{stripped[:40]}'")
            continue

        # Repair unescaped % inside macro where it comments out closing brace
        pct_matches = list(re.finditer(r"(?<!\\)%", line))
        if pct_matches:
            first_pct = pct_matches[0].start()
            prefix = line[:first_pct]
            comment_part = line[first_pct + 1:]

            open_before = len(re.findall(r"(?<!\\)\{", prefix)) - len(re.findall(r"(?<!\\)\}", prefix))
            close_after = len(re.findall(r"(?<!\\)\}", comment_part))

            if open_before > 0 and close_after > 0:
                fixed_line = line[:first_pct] + r"\%" + line[first_pct + 1:]
                repairs.append(f"Escaped '%' that swallowed closing brace: '{stripped[:50]}'")
                line = fixed_line

        # Repair unescaped % after numbers on non-comment lines
        if not stripped.startswith("%") and re.search(r"(?<!\\)(\d+(?:\.\d+)?)\s*%(?![a-zA-Z%])", line):
            new_line = re.sub(r"(?<!\\)(\d+(?:\.\d+)?)\s*%(?![a-zA-Z%])", r"\1\\%", line)
            if new_line != line:
                repairs.append(f"Escaped '%' in numeric percentage: '{stripped[:50]}'")
                line = new_line

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines), repairs


def auto_repair_duplicate_headings(
    proposed_edits: List[Dict[str, Any]],
    original_code: str,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Convert create_content edits that duplicate existing headings into
    edit_chunk edits by finding the matching section text in the original.

    Returns (repaired_edits, list_of_repairs_made).
    """
    repairs = []
    repaired = []

    if not original_code:
        return proposed_edits, repairs

    # Build a map of normalized heading -> full section text in original
    section_map: Dict[str, str] = {}  # normalized_title -> section_content
    section_matches = list(re.finditer(
        r"(\\(?:chapter|section|subsection)\{([^}]+)\})", original_code
    ))
    for i, m in enumerate(section_matches):
        raw_title = m.group(2).strip()
        normalized = re.sub(r"\s+", " ", raw_title).lower().strip()
        # Section extends from this heading to the next heading or end
        start = m.start()
        end = section_matches[i + 1].start() if i + 1 < len(section_matches) else len(original_code)
        # Don't go past \end{document}
        end_doc = original_code.find("\\end{document}", start)
        if end_doc != -1 and end_doc < end:
            end = end_doc
        section_text = original_code[start:end].strip()
        section_map[normalized] = section_text

    for edit in proposed_edits:
        oc = edit.get("original_chunk", "")
        pc = edit.get("proposed_chunk", "")

        if oc or not pc:
            repaired.append(edit)
            continue

        # Check if proposed heading duplicates an existing one
        heading_m = re.search(r"\\(?:chapter|section|subsection)\{([^}]+)\}", pc)
        if heading_m:
            proposed_title = heading_m.group(1).strip()
            proposed_normalized = re.sub(r"\s+", " ", proposed_title).lower().strip()

            if proposed_normalized in section_map:
                # Convert create -> edit by setting original_chunk to existing section
                new_edit = dict(edit)
                new_edit["original_chunk"] = section_map[proposed_normalized]
                repaired.append(new_edit)
                repairs.append(
                    f"Converted duplicate create '{proposed_title}' to edit_chunk"
                )
                continue

        repaired.append(edit)

    return repaired, repairs


def auto_repair_edits(
    proposed_edits: List[Dict[str, Any]],
    original_code: str,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Attempt to auto-repair common issues in proposed edits.

    Returns (repaired_edits, list_of_repairs_made).
    """
    all_repairs = []
    repaired_edits = []

    for edit in proposed_edits:
        pc = edit.get("proposed_chunk", "")
        if not pc:
            repaired_edits.append(edit)
            continue

        new_edit = dict(edit)

        # Auto-repair duplicate frames
        pc, dup_repairs = auto_repair_duplicates(pc)
        all_repairs.extend(dup_repairs)

        # Auto-repair duplicate structural elements
        pc, struct_repairs = auto_repair_structure(pc)
        all_repairs.extend(struct_repairs)

        # Auto-repair comment overlap & unescaped %
        pc, comment_repairs = auto_repair_comment_overlap(pc)
        all_repairs.extend(comment_repairs)

        new_edit["proposed_chunk"] = pc
        repaired_edits.append(new_edit)

    # Auto-repair duplicate heading creates (convert to edit_chunk)
    repaired_edits, heading_repairs = auto_repair_duplicate_headings(
        repaired_edits, original_code
    )
    all_repairs.extend(heading_repairs)

    if all_repairs:
        logger.info(f"Auto-repair applied {len(all_repairs)} fix(es): {all_repairs}")

    return repaired_edits, all_repairs
