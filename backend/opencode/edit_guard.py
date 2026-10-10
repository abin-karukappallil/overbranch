"""
opencode/edit_guard.py — Keeping an edit to the place it was meant for.

Two guards sit between "the agent asked for this change" and "the buffer now
holds it":

* ``scoped_heal`` runs the deterministic healer but keeps only the repairs that
  land on lines the edit itself changed (plus package / colour insertions in the
  preamble that those lines need). The healer used to run over the whole buffer
  on every write, so a defect the user already had — an unclosed environment far
  away, a missing TikZ semicolon — was "fixed" as a side effect of an unrelated
  edit and showed up in the diff as a change nobody asked for.

* ``introduced_duplicates`` refuses an edit that makes a frame or section appear
  twice — the classic result of a model inserting a block it had already written.
"""

from __future__ import annotations

import difflib
import re
from typing import List, Optional, Set, Tuple

_RE_BEGIN_DOC = re.compile(r"\\begin\s*\{document\}")
_DUP_KINDS = ("frame", "section", "chapter", "subsection")
_DUP_MIN_CHARS = 80


def changed_lines(before: str, after: str) -> Set[int]:
    """0-based indices of lines in ``after`` that differ from ``before``, plus
    the line at each pure deletion point."""
    a = before.splitlines(keepends=True)
    b = after.splitlines(keepends=True)
    out: Set[int] = set()
    for tag, _i1, _i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if j1 == j2:
            out.add(min(j1, max(0, len(b) - 1)))
        out.update(range(j1, j2))
    return out


def _preamble_end_line(lines: List[str]) -> int:
    for i, ln in enumerate(lines):
        if _RE_BEGIN_DOC.search(ln):
            return i
    return -1


def scoped_heal(baseline: str, candidate: str) -> Tuple[str, List[str], bool]:
    """
    Heals ``candidate`` but only where the edit (baseline → candidate) touched it.

    Returns (code, fixes, trimmed). ``trimmed`` is True when some healer changes
    were dropped because they fell outside the edited region.
    """
    from latex_error_fixer import auto_heal_latex_code

    try:
        healed, fixes = auto_heal_latex_code(candidate)
    except Exception:
        return candidate, [], False
    if healed == candidate or not fixes:
        return candidate, [], False

    if not baseline.strip():
        return healed, fixes, False  # a brand-new document: everything is the edit
    touched = changed_lines(baseline, candidate)
    if not touched:
        return candidate, [], True  # nothing was edited, so nothing may be "repaired"

    allowed: Set[int] = set()
    for i in touched:
        allowed.update((i - 1, i, i + 1))

    cand = candidate.splitlines(keepends=True)
    heal = healed.splitlines(keepends=True)
    pre_end = _preamble_end_line(cand)

    # Preamble lines the healer would add to the document *before* the edit are
    # needs the user's document already had (a TikZ library for an old figure);
    # only insertions the edit itself creates belong to this edit.
    try:
        base_healed, _ = auto_heal_latex_code(baseline)
        pre_existing = {ln.strip() for ln in base_healed.splitlines()} - {ln.strip() for ln in baseline.splitlines()}
    except Exception:
        pre_existing = set()

    out: List[str] = []
    trimmed = False
    kept_any = False
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, cand, heal, autojunk=False).get_opcodes():
        if tag == "equal":
            out.extend(cand[i1:i2])
            continue
        in_edit = any(i in allowed for i in range(i1, max(i2, i1 + 1)))
        is_pkg_insert = any(ln.strip().startswith(r"\usepackage") for ln in heal[j1:j2]) and not all(ln.strip() in pre_existing for ln in heal[j1:j2])
        preamble_insert = ((tag == "insert" and pre_end != -1 and i1 <= pre_end) or is_pkg_insert) and not all(ln.strip() in pre_existing for ln in heal[j1:j2])
        doc_end_insert = tag == "insert" and i1 >= len(cand) - 1
        if in_edit or preamble_insert or doc_end_insert:
            out.extend(heal[j1:j2])
            kept_any = True
        else:
            out.extend(cand[i1:i2])
            trimmed = True
    if not kept_any:
        return candidate, [], trimmed
    return "".join(out), fixes, trimmed


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def introduced_duplicates(baseline: str, candidate: str) -> List[str]:
    """
    Frames / sections whose full text now occurs more often than it did before
    the edit, among those the edit touched. Returns their node IDs.
    """
    from document_index import index_nodes

    touched = changed_lines(baseline, candidate)
    if not touched:
        return []
    cand_nodes = [n for n in index_nodes(candidate) if n.kind in _DUP_KINDS]
    base_counts: dict = {}
    for n in index_nodes(baseline):
        if n.kind in _DUP_KINDS:
            key = _norm(baseline[n.start:n.end])
            base_counts[key] = base_counts.get(key, 0) + 1
    cand_counts: dict = {}
    for n in cand_nodes:
        key = _norm(candidate[n.start:n.end])
        cand_counts[key] = cand_counts.get(key, 0) + 1

    dups: List[str] = []
    for n in cand_nodes:
        if not any(n.start_line - 1 <= i <= n.end_line - 1 for i in touched):
            continue
        key = _norm(candidate[n.start:n.end])
        if len(key) < _DUP_MIN_CHARS:
            continue
        if cand_counts.get(key, 0) > 1 and cand_counts[key] > base_counts.get(key, 0):
            dups.append(n.node_id)
    return list(dict.fromkeys(dups))


def region_excerpt(code: str, line: Optional[int], radius: int = 20) -> str:
    """Line-numbered excerpt around ``line`` (1-based), for a failed edit's feedback."""
    if not line:
        return ""
    lines = code.splitlines()
    lo = max(1, line - radius)
    hi = min(len(lines), line + radius)
    return "\n".join(f"{i}: {lines[i - 1]}" for i in range(lo, hi + 1))
