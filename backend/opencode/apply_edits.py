"""
opencode/apply_edits.py — Server-side recovery for edits the editor could not place.

The editor applies an accepted edit by exact substring (lib/latex-edit-apply.ts).
When the document moved under the edit — the user typed while the agent ran,
an earlier edit was accepted, Monaco normalised whitespace — that lookup fails.
Instead of dropping the edit, the editor sends the live document and the
unplaced items here, where the same locator the agent uses (node ID → exact →
normalized → fuzzy) finds where each one now belongs.

All-or-nothing: either every item is placed and the result validates, or the
document is returned unchanged with a per-item account of what was tried.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from latex_error_fixer import sanitize_edit_latex
from .locator import Target, resolve


def resolve_and_apply(
    current_code: str,
    items: List[Dict[str, Any]],
    original_code: Optional[str] = None,
    base_version: Optional[int] = None,
    live_version: Optional[int] = None,
) -> Dict[str, Any]:
    current = current_code.replace("\r\n", "\n")
    placed: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    is_stale = (
        base_version is not None
        and live_version is not None
        and live_version != base_version
    )

    for idx, item in enumerate(items):
        item_id = item.get("id") or f"edit-{idx + 1}"
        anchor = (item.get("original_chunk") or "").replace("\r\n", "\n")
        proposal = sanitize_edit_latex((item.get("proposed_chunk") or "").replace("\r\n", "\n"))
        op = item.get("op") or "replace"

        if item.get("is_full_document"):
            # Only over the document the backend diffed. Without original_code the item's own
            # original_chunk (the whole original) is the reference — placing it unconditionally
            # overwrote text typed during the run, or a different file.
            norm_orig = (original_code if original_code is not None else anchor).replace("\r\n", "\n")
            if (current == norm_orig or current.strip() == norm_orig.strip()) and not is_stale:
                placed.append({"id": item_id, "start": 0, "end": len(current), "text": proposal,
                               "method": "full_document"})
            else:
                failed.append({"id": item_id, "op": op, "target": "whole document",
                               "reason": "stale_document_conflict" if is_stale else "document_changed",
                               "attempts": [{"method": "full_document", "outcome": "stale_conflict" if is_stale else "document_changed"}]})
            continue
        if not anchor:
            failed.append({"id": item_id, "op": op, "target": None, "reason": "no_target", "attempts": []})
            continue

        res = resolve(current, Target(node_id=item.get("node_id"), text=anchor,
                                      line_hint=item.get("orig_start_line")))
        if not res.ok:
            failed.append({"id": item_id, "op": op, "target": item.get("node_id") or anchor[:80],
                           "reason": res.reason, "attempts": res.attempts})
            continue

        if is_stale and res.confidence < 0.85:
            failed.append({
                "id": item_id, "op": op, "target": item.get("node_id") or anchor[:80],
                "reason": "stale_anchor_drift",
                "attempts": [{"method": res.method, "outcome": f"stale version drift, confidence {round(res.confidence, 3)} < 0.85"}]
            })
            continue

        placed.append({"id": item_id, "start": res.start, "end": res.end, "text": proposal,
                       "method": res.method, "confidence": round(res.confidence, 3)})

    # Overlapping placements mean two edits claim the same text: refuse both.
    placed.sort(key=lambda p: p["start"])
    for a, b in zip(placed, placed[1:]):
        if b["start"] < a["end"]:
            for p in (a, b):
                failed.append({"id": p["id"], "op": "replace", "target": None, "reason": "overlap",
                               "attempts": [{"method": p["method"], "outcome": "overlaps another edit"}]})

    if failed:
        return {"success": False, "code": current_code, "applied": [], "failed": failed,
                "document_unchanged": True}

    code = current
    for p in sorted(placed, key=lambda p: p["start"], reverse=True):
        code = code[:p["start"]] + p["text"] + code[p["end"]:]

    from edit_validator import validate_edit
    ok, errors = validate_edit(current, code)
    if not ok:
        return {"success": False, "code": current_code, "applied": [],
                "failed": [{"id": None, "op": "validate", "target": None, "reason": "invalid_result",
                            "attempts": [{"method": "validate_edit", "outcome": e} for e in errors[:3]]}],
                "document_unchanged": True}
    return {
        "success": True,
        "code": code,
        "applied": [{"id": p["id"], "method": p["method"], "confidence": p.get("confidence", 1.0)} for p in placed],
        "failed": [],
        "document_unchanged": code == current,
    }
