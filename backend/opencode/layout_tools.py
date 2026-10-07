"""
opencode/layout_tools.py — Agent tools over latex_layout: detect_overflow,
inspect_pdf_geometry and justify_content.

All three are deterministic. The model decides *that* a block needs horizontal
correction; justify_content decides *how*, from measurements, and applies the
change through the workspace's normal write gate (validated, revertible).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, Optional

from latex_layout.justify import FontSpec, justify_content, split_preamble, tex_probe
from latex_layout.overflow import detect_overflow, text_right_edge
from latex_layout.blocks import text_blocks_from_pdf

if TYPE_CHECKING:
    from .shadow_workspace import ShadowWorkspace

_FAMILY_BY_PACKAGE = (
    ("carlito", "carlito"), ("arimo", "arimo"), ("tinos", "tinos"), ("caladea", "caladea"),
    ("helvet", "helvetica"), ("mathptmx", "times"), ("times", "times"), ("newtxtext", "times"),
    ("mathpazo", "palatino"), ("palatino", "palatino"), ("courier", "courier"),
)


def document_font(code: str) -> FontSpec:
    """Best-effort main font of a document, for metric-based measurement."""
    pre = split_preamble(code)
    family = "lmodern"
    for pkg, fam in _FAMILY_BY_PACKAGE:
        if re.search(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\b" + pkg + r"\b", pre):
            family = fam
            break
    if family in ("helvetica",) or "\\sfdefault" in pre or re.search(r"\\documentclass(?:\[[^\]]*\])?\{beamer\}", pre):
        family = family if family != "lmodern" else "lmsans"
    m = re.search(r"\\documentclass\[([^\]]*)\]", pre)
    size = 10.0
    if m:
        sm = re.search(r"(\d+(?:\.\d+)?)pt", m.group(1))
        if sm:
            size = float(sm.group(1))
    elif re.search(r"\\documentclass\{beamer\}", pre):
        size = 11.0
    return FontSpec(family=family, size=size)


def _compile(ws: "ShadowWorkspace") -> Dict[str, Any]:
    from .shadow_compiler import compile_workspace
    return compile_workspace(ws)


def detect_overflow_tool(ws: "ShadowWorkspace") -> Dict[str, Any]:
    run = _compile(ws)
    if run["infra"] or not run["pdf"]:
        return {"success": False, "skipped": True,
                "error": "No PDF to inspect (compiler unavailable or the document does not compile).",
                "new_errors": run.get("new_errors", [])[:3]}
    report = detect_overflow(run["pdf"], "")
    lines = ws.get_buffer().splitlines()
    overfull = []
    for o in run["overfull"]:
        item = dict(o)
        if o.get("lines"):
            a, b = o["lines"]
            item["source"] = "\n".join(f"{i}: {lines[i - 1]}" for i in range(a, min(b, a + 3) + 1)
                                       if 0 < i <= len(lines))
        overfull.append(item)
    report["overfull"] = overfull
    report["has_overflow"] = bool([o for o in overfull if o.get("severe")]
                                  or report["beyond_text_area"] or report["beyond_page"])
    report["success"] = True
    if report["has_overflow"]:
        report["hint"] = "Fix with justify_content on the affected block or line (node_id or text)."
    return report


def inspect_pdf_geometry_tool(ws: "ShadowWorkspace", page: int = 1) -> Dict[str, Any]:
    run = _compile(ws)
    if run["infra"] or not run["pdf"]:
        return {"success": False, "skipped": True, "error": "No PDF to inspect."}
    blocks, (pw, ph) = text_blocks_from_pdf(run["pdf"], max(0, page - 1))
    return {
        "success": True,
        "page": page,
        "page_size_pt": [round(pw, 1), round(ph, 1)],
        "text_right_edge_pt": text_right_edge(blocks),
        "lines": [b.as_dict() for b in blocks[:80]],
        "truncated": max(0, len(blocks) - 80),
    }


_LR_BOX_RE = re.compile(r"\\(?:makebox|mbox|hbox|fbox|framebox|raisebox|resizebox\*?|scalebox|obhfit)"
                        r"\s*(?:\[[^\]]*\]|\{[^{}]*\})*\s*$")


def in_lr_box(code: str, start: int) -> bool:
    """
    True when ``start`` lies inside the argument of a box command that cannot
    break lines (\\makebox, \\mbox, …) or a tabular cell: content there is one
    line whatever its length, so it must be fitted, not wrapped.
    """
    depth = 0
    i = start - 1
    lo = max(0, start - 2000)
    while i >= lo:
        c = code[i]
        if c == "}" and code[i - 1:i] != "\\":
            depth += 1
        elif c == "{" and code[i - 1:i] != "\\":
            if depth == 0:
                if _LR_BOX_RE.search(code[max(0, i - 120):i]):
                    return True
            else:
                depth -= 1
        i -= 1
    # Inside a tabular row: the line holds an unescaped & before the target.
    line_start = code.rfind("\n", 0, start) + 1
    return bool(re.search(r"(?<!\\)&", code[line_start:start]))


def justify_content_tool(ws: "ShadowWorkspace", args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolves the target (node or text), measures it, applies the smallest fix
    and — when a compiler is available — verifies that the overflow is gone.
    The edit and any package it needs are one transaction.
    """
    from .locator import Target, resolve

    code = ws.get_buffer()
    node_ref = (args.get("node_id") or "").strip() or None
    text = args.get("text") or None
    alignment = (args.get("alignment") or "").strip().lower() or None
    try:
        width = float(args.get("width_pt") or 0)
    except (TypeError, ValueError):
        width = 0.0

    start = end = None
    if node_ref and not text:
        node = ws.resolve_node(node_ref)
        if node is None:
            return ws._node_not_found("justify_content", node_ref)
        # The content of a node, not its \begin/\end or heading command.
        start, end = node.body_start, node.body_end
        if node.kind in ("section", "subsection", "subsubsection", "chapter", "part", "paragraph"):
            start, end = node.start, node.body_start
    else:
        res = resolve(code, Target(node_id=node_ref, text=text), aliases=ws._node_aliases)
        if not res.ok:
            return ws._failure("justify_content", {"text": (text or "")[:120], "node_id": node_ref}, res)
        start, end = res.start, res.end

    fragment = code[start:end]
    lead = fragment[:len(fragment) - len(fragment.lstrip())]
    trail = fragment[len(fragment.rstrip()):]
    core = fragment.strip()
    if not core:
        return {"success": False, "error": "The target is empty.", "document_unchanged": True}

    preamble = split_preamble(code)
    aux = dict(getattr(ws, "_aux_files", {}))
    if width <= 0:
        probe = tex_probe(preamble, [], aux)
        width = (probe or {}).get("LW") or (probe or {}).get("TW") or 0.0
    if width <= 0:
        return {"success": False, "error": "Could not determine the available width; pass width_pt.",
                "document_unchanged": True}

    single_line = True if in_lr_box(code, start + len(lead)) else None
    result = justify_content(core, width, document_font(code), alignment=alignment, single_line=single_line,
                             preamble=preamble, extra_files=aux)
    out: Dict[str, Any] = {"success": True, "justify": result.as_dict()}
    if not result.changed:
        out["message"] = "No change needed: the content fits the available width."
        return out

    tx = ws.begin_transaction()
    applied = ws._splice(start, end, lead + result.latex + trail, op="justify_content", method="node" if node_ref else "text")
    if not applied.get("success"):
        ws.rollback_transaction(tx)
        return applied
    is_beamer = bool(re.search(r"\\documentclass(?:\[[^\]]*\])?\{beamer\}", preamble))
    for pkg in result.needs_packages:
        if pkg == "graphicx" and is_beamer:
            continue
        if re.search(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\b" + re.escape(pkg) + r"\b", ws.get_buffer()):
            continue
        buf = ws.get_buffer()
        m = re.search(r"\\begin\s*\{document\}", buf)
        if not m:
            break
        added = ws._splice(m.start(), m.start(), f"\\usepackage{{{pkg}}}\n", op="add_package", method="structural")
        if not added.get("success"):
            ws.rollback_transaction(tx)
            return added
    out["lines_affected"] = applied.get("lines_affected")

    # Verify with the compiler when there is one: the fix must not add errors.
    try:
        from .shadow_compiler import compile_workspace
        run = compile_workspace(ws)
        if not run["infra"]:
            if run["new_errors"]:
                ws.rollback_transaction(tx)
                return {"success": False, "failed_op": "justify_content", "document_unchanged": True,
                        "error": "The fix did not compile; it was rolled back.",
                        "new_errors": run["new_errors"][:3], "justify": result.as_dict()}
            lo, hi = applied["lines_affected"]
            still = [o for o in run["overfull"] if o.get("severe") and o.get("lines")
                     and o["lines"][0] <= hi and o["lines"][1] >= lo]
            out["verified"] = not still
            if still:
                out["remaining_overfull"] = still
    except Exception as e:  # verification is best-effort
        out["verify_error"] = str(e)[:200]
    return out
