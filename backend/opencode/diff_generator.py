"""
opencode/diff_generator.py — Line-Level Diff Computation
==========================================================
Pure-Python diff generator using difflib. Produces the ``final_diff``
payload that maps directly to the frontend InlineDiffEditor's EditItem
interface.
"""

from __future__ import annotations

import difflib
from typing import Any, Dict, List


def compute_final_diff(
    original: str,
    modified: str,
    file_path: str = "main.tex",
    explanation: str = "",
) -> Dict[str, Any]:
    """
    Computes a structured diff between original and modified LaTeX code.

    Returns the ``final_diff`` payload formatted for the frontend:

    .. code-block:: json

        {
            "type": "final_diff",
            "file": "main.tex",
            "original_code": "...",
            "proposed_code": "...",
            "explanation": "...",
            "stats": {"additions": 5, "deletions": 2, "modifications": 3}
        }
    """
    if original == modified:
        return {
            "type": "final_diff",
            "file": file_path,
            "has_changes": False,
            "original_code": original,
            "proposed_code": modified,
            "explanation": explanation or "No changes were made.",
            "unified_diff": "",
            "edits": [],
            "stats": {"additions": 0, "deletions": 0, "modifications": 0},
        }

    # Compute line-level stats
    orig_lines = original.splitlines(keepends=False)
    mod_lines = modified.splitlines(keepends=False)

    sm = difflib.SequenceMatcher(None, orig_lines, mod_lines)
    additions = 0
    deletions = 0
    modifications = 0

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "insert":
            additions += j2 - j1
        elif tag == "delete":
            deletions += i2 - i1
        elif tag == "replace":
            # Lines that changed — count the larger side as the base
            old_count = i2 - i1
            new_count = j2 - j1
            modifications += min(old_count, new_count)
            if new_count > old_count:
                additions += new_count - old_count
            elif old_count > new_count:
                deletions += old_count - new_count

    udiff = "\n".join(difflib.unified_diff(
        orig_lines,
        mod_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        lineterm="",
    ))

    edits = compute_edit_items(original, modified, explanation)

    return {
        "type": "final_diff",
        "file": file_path,
        "has_changes": True,
        "original_code": original,
        "proposed_code": modified,
        "explanation": explanation,
        "unified_diff": udiff,
        "edits": edits,
        "stats": {
            "additions": additions,
            "deletions": deletions,
            "modifications": modifications,
        },
    }


def compute_edit_items(
    original: str,
    modified: str,
    explanation: str = "",
) -> List[Dict[str, str]]:
    """
    Computes a list of EditItem dicts compatible with InlineDiffEditor.

    Each item represents a contiguous changed region:
    ``{original_chunk, proposed_chunk, explanation}``
    """
    if original == modified:
        return []

    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)

    sm = difflib.SequenceMatcher(None, orig_lines, mod_lines)
    edit_items: List[Dict[str, str]] = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue

        orig_chunk = "".join(orig_lines[i1:i2])
        prop_chunk = "".join(mod_lines[j1:j2])

        # Strip trailing newline for cleaner display
        orig_chunk = orig_chunk.rstrip("\n")
        prop_chunk = prop_chunk.rstrip("\n")

        edit_items.append({
            "original_chunk": orig_chunk,
            "proposed_chunk": prop_chunk,
            "explanation": explanation,
        })

    return edit_items


def generate_unified_diff(
    original: str,
    modified: str,
    file_path: str = "main.tex",
    context_lines: int = 3,
) -> str:
    """
    Generates a standard unified diff string (for debugging / copy-patch).
    """
    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)

    diff = difflib.unified_diff(
        orig_lines,
        mod_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        n=context_lines,
    )
    return "".join(diff)
