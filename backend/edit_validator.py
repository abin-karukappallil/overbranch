"""
edit_validator.py — Coverage, AST Integrity & Leftover-Content Validation
========================================================================
Runs pre-output validation passes after the agent loop finishes:
1. AST Coverage Check: Verifies that every content chunk (chapter, section, slide/frame)
   was explicitly rewritten during a FULL_DOCUMENT_REWRITE session. Blocks finalization
   if any content chunk was missed, feeding the missed IDs back to the agent loop.
2. Leftover Content Sweep: Scans the buffer for forbidden keywords and old topic terms
   if a topic change was requested.
3. Environment Balance & LIFO Auto-Repair: Verifies balanced \\begin / \\end tags.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from document_index import DocumentChunk, DocumentIndex

logger = logging.getLogger("edit_validator")


@dataclass
class CoverageValidationResult:
    passed: bool
    total_chunks: int
    edited_chunks: int
    missing_chunk_ids: List[str] = field(default_factory=list)
    missing_chunk_titles: List[str] = field(default_factory=list)
    leftover_terms_found: List[Dict[str, Any]] = field(default_factory=list)
    feedback_message: str = ""


def check_environment_balance(latex_code: str) -> Tuple[bool, List[str]]:
    """Checks that all LaTeX environments \\begin{env} have matching \\end{env}."""
    stack: List[Tuple[str, int]] = []
    errors: List[str] = []

    pattern = re.compile(r"\\(begin|end)\{([a-zA-Z*]+)\}")
    for idx, line in enumerate(latex_code.splitlines(), start=1):
        for m in pattern.finditer(line):
            tag_type = m.group(1)
            env_name = m.group(2)
            if tag_type == "begin":
                stack.append((env_name, idx))
            elif tag_type == "end":
                if not stack:
                    errors.append(f"Line {idx}: Unmatched \\end{{{env_name}}}")
                else:
                    top_env, top_line = stack.pop()
                    if top_env != env_name:
                        errors.append(f"Line {idx}: Mismatched \\end{{{env_name}}}, expected \\end{{{top_env}}} from line {top_line}")

    for env_name, line_no in stack:
        errors.append(f"Line {line_no}: Unclosed \\begin{{{env_name}}}")

    return len(errors) == 0, errors


def auto_repair_truncated_latex(latex_code: str) -> str:
    """Closes unclosed LaTeX environments in LIFO order if response was cut off."""
    code = latex_code.rstrip()
    pattern = re.compile(r"\\(begin|end)\{([a-zA-Z*]+)\}")
    stack: List[str] = []

    for m in pattern.finditer(code):
        tag_type = m.group(1)
        env_name = m.group(2)
        if tag_type == "begin":
            stack.append(env_name)
        elif tag_type == "end" and stack:
            if stack[-1] == env_name:
                stack.pop()

    if stack:
        logger.info(f"Auto-repairing {len(stack)} unclosed LaTeX environments: {stack}")
        for env in reversed(stack):
            code += f"\n\\end{{{env}}}"

    if "\\begin{document}" in code and "\\end{document}" not in code:
        code += "\n\\end{document}"

    return code


def validate_coverage(
    workspace: Any,
    user_instruction: str,
    scope: str = "FULL_DOCUMENT_REWRITE",
    forbidden_terms: Optional[List[str]] = None,
) -> CoverageValidationResult:
    """
    Validates that:
    1. Every content chunk in the original document was touched/rewritten in full-rewrite mode.
    2. No forbidden or obsolete topic terms remain in the updated shadow buffer.
    """
    doc_index = DocumentIndex()
    orig_code = workspace.get_original() if hasattr(workspace, "get_original") else ""
    current_code = workspace.get_buffer() if hasattr(workspace, "get_buffer") else ""

    content_chunks = doc_index.get_content_chunks(orig_code)
    total_content_chunks = len(content_chunks)
    touched_ids: Set[str] = workspace.get_touched_chunks() if hasattr(workspace, "get_touched_chunks") else set()

    # If document has no structural content chunks (e.g. single small document or empty), coverage is trivially satisfied
    if total_content_chunks == 0:
        return CoverageValidationResult(
            passed=True,
            total_chunks=0,
            edited_chunks=0,
            feedback_message="Document has no distinct content chunks to validate.",
        )

    # 1. Chunk Coverage Check
    missing_chunks: List[DocumentChunk] = [c for c in content_chunks if c.chunk_id not in touched_ids]
    edited_count = total_content_chunks - len(missing_chunks)

    if missing_chunks and (scope == "FULL_DOCUMENT_REWRITE" or "FULL_DOCUMENT_REWRITE" in scope):
        missing_ids = [c.chunk_id for c in missing_chunks]
        missing_titles = [c.title for c in missing_chunks]
        chunks_bullet_list = "\n".join([f"  - `{c.chunk_id}`: {c.title}" for c in missing_chunks])

        feedback = (
            f"COVERAGE CHECK FAILED: In FULL_DOCUMENT_REWRITE mode, you must replace all content chunks.\n"
            f"You have edited {edited_count}/{total_content_chunks} content chunks.\n"
            f"The following {len(missing_chunks)} chunk(s) have NOT been rewritten:\n"
            f"{chunks_bullet_list}\n\n"
            f"ACTION REQUIRED: Call `rewrite_chunk(chunk_id, new_content)` for each unedited chunk before setting done=true."
        )

        logger.warning(f"Coverage check failed: {len(missing_chunks)} chunks untouched: {missing_ids}")
        return CoverageValidationResult(
            passed=False,
            total_chunks=total_content_chunks,
            edited_chunks=edited_count,
            missing_chunk_ids=missing_ids,
            missing_chunk_titles=missing_titles,
            feedback_message=feedback,
        )

    # 2. Leftover Content & Forbidden Terms Sweep
    leftover_matches: List[Dict[str, Any]] = []
    if forbidden_terms:
        for term in forbidden_terms:
            t = term.strip()
            if not t or len(t) < 3:
                continue
            # Search current buffer
            grep_results = workspace.grep(t) if hasattr(workspace, "grep") else []
            valid_hits = [g for g in grep_results if "line_no" in g]
            if valid_hits:
                leftover_matches.append({
                    "term": t,
                    "count": len(valid_hits),
                    "lines": [h["line_no"] for h in valid_hits[:5]],
                })

    if leftover_matches and (scope == "FULL_DOCUMENT_REWRITE" or "FULL_DOCUMENT_REWRITE" in scope):
        summary_items = [f"'{m['term']}' (found on lines {m['lines']})" for m in leftover_matches]
        summary_str = ", ".join(summary_items)
        feedback = (
            f"LEFTOVER CONTENT CHECK FAILED: The following terms from the old document/topic were found remaining:\n"
            f"  {summary_str}\n\n"
            f"ACTION REQUIRED: Replace or remove these obsolete topic terms using `rewrite_chunk` or `str_replace` before finishing."
        )
        logger.warning(f"Leftover terms check failed: {summary_str}")
        return CoverageValidationResult(
            passed=False,
            total_chunks=total_content_chunks,
            edited_chunks=edited_count,
            leftover_terms_found=leftover_matches,
            feedback_message=feedback,
        )

    # All checks passed
    logger.info(f"Coverage check PASSED: all {total_content_chunks} chunks edited, 0 leftover forbidden terms.")
    return CoverageValidationResult(
        passed=True,
        total_chunks=total_content_chunks,
        edited_chunks=total_content_chunks,
        missing_chunk_ids=[],
        missing_chunk_titles=[],
        feedback_message=f"Coverage verified: all {total_content_chunks} chunks rewritten and verified.",
    )
