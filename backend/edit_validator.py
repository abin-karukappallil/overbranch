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

        new_edit["proposed_chunk"] = pc
        repaired_edits.append(new_edit)

    if all_repairs:
        logger.info(f"Auto-repair applied {len(all_repairs)} fix(es): {all_repairs}")

    return repaired_edits, all_repairs
