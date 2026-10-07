"""
opencode/diff_generator.py — Line-Level Diff Computation
==========================================================
Pure-Python diff generator using difflib. Produces the ``final_diff``
payload that maps directly to the frontend's EditItem interface.

Apply contract (version 2)
--------------------------
``compute_edit_items`` guarantees, for every emitted item:

1. **Non-empty anchor.** ``original_chunk`` is never ``""`` (except for the single
   degenerate item emitted when the original document is empty, which is flagged
   ``is_full_document``). Raw ``difflib`` insert opcodes have ``i1 == i2`` and so
   produce empty anchors; those are expanded with surrounding context instead.
2. **Unique anchor.** ``original_chunk`` occurs exactly once in the original
   document, so a client may locate it by substring search.
3. **Structurally closed.** The chunk changes no net LaTeX environment nesting,
   brace depth or ``$`` parity. A ``\\begin{...}`` and its matching ``\\end{...}``
   therefore always live in the *same* item and can never be applied or rejected
   independently. This is what makes *any subset* of items individually
   applicable without corrupting the document.
4. **Non-overlapping.** Item line ranges are disjoint, so a client can resolve
   all positions up front and splice in descending order.
5. **Line-addressed.** ``orig_start_line`` / ``orig_end_line`` (1-based,
   inclusive) allow positional application when the document is unchanged.

6. **Node-addressed (v3, additive).** ``node_id`` / ``node_path`` name the
   innermost structural node (document_index.index_nodes) enclosing the anchor
   in the original. A client that cannot find the anchor by text — because the
   document changed under it — can send the item to ``/api/agent/resolve-edits``,
   which re-locates it by node, then normalised text, then similarity.

``compute_final_diff`` additionally carries ``proposed_code`` plus
``original_sha256``: that pair is *authoritative*. A client holding it should
write ``proposed_code`` directly when the live document still matches
``original_code``, and fall back to replaying ``edits`` otherwise.

The client-side implementation of this contract lives in
``lib/latex-edit-apply.ts``; ``backend/tests/test_diff_generator_anchors.py``
holds a Python mirror of it that asserts a full replay reproduces
``proposed_code`` byte-for-byte.
"""

from __future__ import annotations

import difflib
import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple

from edit_validator import clean_latex_for_validation

APPLY_CONTRACT_VERSION = 3

_RE_ENV_TAG = re.compile(r"\\(begin|end)\s*\{\s*([A-Za-z@*][A-Za-z0-9@*]*)\s*\}")
_RE_ESCAPED_BRACE = re.compile(r"(?<!\\)(?:\\\\)*\\[{}]")
_RE_DOUBLE_DOLLAR = re.compile(r"(?<!\\)(?:\\\\)*\$\$")
_RE_SINGLE_DOLLAR = re.compile(r"(?<!\\)(?:\\\\)*\$")

# (unmatched_begin_envs, orphan_end_count, brace_delta, dollar_parity)
StructuralDelta = Tuple[Tuple[str, ...], int, int, int]


def _structural_delta(text: str) -> StructuralDelta:
    """
    Summarises how a fragment changes LaTeX structure.

    Two fragments with equal deltas are interchangeable as far as environment
    nesting, brace depth and inline-math parity are concerned. Verbatim bodies,
    comments, URL arguments and macro definition bodies are neutralised first.
    """
    if not text:
        return ((), 0, 0, 0)

    cleaned = clean_latex_for_validation(text)

    stack: List[str] = []
    orphan_ends = 0
    for m in _RE_ENV_TAG.finditer(cleaned):
        if m.group(1) == "begin":
            stack.append(m.group(2))
        else:
            if stack and stack[-1] == m.group(2):
                stack.pop()
            else:
                orphan_ends += 1

    no_escaped = _RE_ESCAPED_BRACE.sub("", cleaned)
    brace_delta = no_escaped.count("{") - no_escaped.count("}")

    no_dd = _RE_DOUBLE_DOLLAR.sub("", cleaned)
    dollar_parity = len(_RE_SINGLE_DOLLAR.findall(no_dd)) % 2

    return (tuple(stack), orphan_ends, brace_delta, dollar_parity)


def _strip_one_trailing_newline(s: str) -> str:
    return s[:-1] if s.endswith("\n") else s


def _full_document_item(
    original: str,
    modified: str,
    explanation: str,
    total_orig_lines: int,
    total_mod_lines: int,
) -> Dict[str, Any]:
    """The whole-document fallback. Chunks are exact (never newline-stripped)."""
    return {
        "original_chunk": original,
        "proposed_chunk": modified,
        "explanation": explanation,
        "orig_start_line": 1,
        "orig_end_line": total_orig_lines,
        "new_start_line": 1,
        "new_end_line": total_mod_lines,
        "context_before": 0,
        "context_after": 0,
        "op": "replace" if original else "insert",
        "anchor_unique": bool(original) and total_orig_lines > 0,
        "is_full_document": True,
    }


def compute_edit_items(
    original: str,
    modified: str,
    explanation: str = "",
    min_context: int = 1,
    max_context: int = 200,
) -> List[Dict[str, Any]]:
    """
    Computes a list of EditItem dicts satisfying the apply contract above.

    Each item represents a contiguous changed region together with enough
    surrounding context to be uniquely locatable and structurally self-contained.
    """
    if original == modified:
        return []

    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)
    n_orig = len(orig_lines)
    n_mod = len(mod_lines)

    # No original text means there is no anchor to find.
    if not orig_lines:
        return [_full_document_item(original, modified, explanation, 0, n_mod)]

    sm = difflib.SequenceMatcher(None, orig_lines, mod_lines)
    hunks: List[List[int]] = [
        [i1, i2, j1, j2] for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"
    ]
    if not hunks:
        return []

    def orig_body(h: List[int]) -> str:
        return "".join(orig_lines[h[0]:h[1]])

    def prop_body(h: List[int]) -> str:
        return "".join(mod_lines[h[2]:h[3]])

    def is_closed(h: List[int]) -> bool:
        return _structural_delta(orig_body(h)) == _structural_delta(prop_body(h))

    def merged(a: List[int], b: List[int]) -> List[int]:
        return [a[0], b[1], a[2], b[3]]

    def merge_at(hs: List[List[int]], k: int) -> bool:
        """Merges hunk k with a neighbour. Returns False if it cannot."""
        if k + 1 < len(hs):
            hs[k:k + 2] = [merged(hs[k], hs[k + 1])]
            return True
        if k > 0:
            hs[k - 1:k + 1] = [merged(hs[k - 1], hs[k])]
            return True
        return False

    # Pass 2 — structural merge. Keep merging until every hunk is structurally
    # closed and no two anchors could overlap.
    progressed = True
    while progressed and len(hunks) > 1:
        progressed = False
        for k, h in enumerate(hunks):
            too_close = (
                k + 1 < len(hunks)
                and (hunks[k + 1][0] - h[1]) < 2 * min_context
            )
            if is_closed(h) and not too_close:
                continue
            if merge_at(hunks, k):
                progressed = True
            break

    # Passes 3 & 4 — context expansion for uniqueness, then emit. If a hunk's
    # anchor cannot be made unique within its bounds, merge it and start over.
    while True:
        items: List[Dict[str, Any]] = []
        failed_at: Optional[int] = None

        for k, h in enumerate(hunks):
            i1, i2, j1, j2 = h
            left_limit = hunks[k - 1][1] if k > 0 else 0
            right_limit = hunks[k + 1][0] if k + 1 < len(hunks) else n_orig

            a = max(left_limit, i1 - min_context)
            b = min(right_limit, i2 + min_context)

            while True:
                anchor = "".join(orig_lines[a:b])
                if anchor and original.count(anchor) == 1:
                    break
                if (b - a) > max_context:
                    break
                if b < right_limit:
                    b += 1
                elif a > left_limit:
                    a -= 1
                else:
                    break

            anchor = "".join(orig_lines[a:b])
            if not anchor or original.count(anchor) != 1:
                failed_at = k
                break

            ja = j1 - (i1 - a)
            jb = j2 + (b - i2)
            proposal = "".join(mod_lines[ja:jb])

            if i1 == i2:
                op = "insert"
            elif j1 == j2:
                op = "delete"
            else:
                op = "replace"

            is_full = a == 0 and b == n_orig

            items.append({
                "original_chunk": anchor if is_full else _strip_one_trailing_newline(anchor),
                "proposed_chunk": proposal if is_full else _strip_one_trailing_newline(proposal),
                "explanation": explanation,
                "orig_start_line": a + 1,
                "orig_end_line": b,
                "new_start_line": ja + 1,
                "new_end_line": jb,
                "context_before": i1 - a,
                "context_after": b - i2,
                "op": op,
                "anchor_unique": True,
                "is_full_document": is_full,
            })

        if failed_at is None:
            return _annotate_nodes(original, items)

        if len(hunks) == 1 or not merge_at(hunks, failed_at):
            return [_full_document_item(original, modified, explanation, n_orig, n_mod)]


def _annotate_nodes(original: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Adds node_id / node_path of the innermost node enclosing each item's lines."""
    try:
        from document_index import index_nodes
        nodes = index_nodes(original)
    except Exception:
        return items
    by_id = {n.node_id: n for n in nodes}
    for item in items:
        # The changed lines, without the context added to make the anchor unique.
        a = item.get("orig_start_line", 0) + item.get("context_before", 0)
        b = item.get("orig_end_line", 0) - item.get("context_after", 0)
        if b < a:  # pure insertion: it sits between two lines
            a = b = max(1, a - 1)
        inner = None
        for n in nodes:
            if n.kind != "preamble" and n.start_line <= a and b <= n.end_line:
                if inner is None or (n.end - n.start) <= (inner.end - inner.start):
                    inner = n
        if inner is None:
            pre = by_id.get("preamble")
            inner = pre if pre and b <= pre.end_line else None
        if inner is None:
            continue
        path = [inner.node_id]
        parent = inner.parent_id
        while parent and parent in by_id and len(path) < 6:
            path.append(parent)
            parent = by_id[parent].parent_id
        item["node_id"] = inner.node_id
        item["node_path"] = list(reversed(path))
    return items


def compute_final_diff(
    original: str,
    modified: str,
    file_path: str = "main.tex",
    explanation: str = "",
) -> Dict[str, Any]:
    """
    Computes a structured diff between original and modified LaTeX code.

    ``proposed_code`` together with ``original_sha256`` is the authoritative
    result; ``edits`` is a replayable decomposition of it (see the module
    docstring's apply contract).
    """
    orig_sha = hashlib.sha256(original.encode("utf-8")).hexdigest()
    prop_sha = hashlib.sha256(modified.encode("utf-8")).hexdigest()

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
            "original_sha256": orig_sha,
            "proposed_sha256": prop_sha,
            "apply_contract_version": APPLY_CONTRACT_VERSION,
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

    # When the decomposition is nearly as large as the document itself, shipping
    # both doubles the SSE payload for no benefit — send one whole-document item.
    edits_chars = sum(len(e["proposed_chunk"]) for e in edits)
    if modified and edits_chars > 0.6 * len(modified) and not (
        len(edits) == 1 and edits[0].get("is_full_document")
    ):
        edits = [_full_document_item(
            original, modified, explanation, len(orig_lines), len(mod_lines)
        )]

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
        "original_sha256": orig_sha,
        "proposed_sha256": prop_sha,
        "apply_contract_version": APPLY_CONTRACT_VERSION,
    }


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
