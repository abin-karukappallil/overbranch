"""
opencode/shadow_compiler.py — Shadow Compilation Verification
==============================================================
Wraps the existing compiler infrastructure to verify the shadow buffer
compiles without errors. Each compilation runs in an isolated temp directory
for thread safety.
"""

from __future__ import annotations

import base64
import logging
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .shadow_workspace import ShadowWorkspace

logger = logging.getLogger("opencode.shadow_compiler")

INFRA_ERROR_PATTERNS = [
    "no such file or directory",
    "not found",
    "permission denied",
    "compilation infrastructure error",
    "command not found",
    "cannot execute",
    "executable not found",
]


def parse_latex_error_log(log_text: str) -> Dict[str, Any]:
    """
    Parses a raw LaTeX compilation log or error summary into structured diagnostics:
    - errors: List[Dict[str, Any]] with error message, line number, context snippet, error type, and suggested action
    - has_errors: bool
    - summary: str
    """
    if not log_text:
        return {"has_errors": False, "errors": [], "summary": ""}

    errors: List[Dict[str, Any]] = []

    # Use comprehensive diagnostic parser
    try:
        from latex_error_fixer import parse_compilation_errors
        parsed = parse_compilation_errors(log_text)
        for p in parsed:
            errors.append({
                "error": p.message,
                "line": p.line_number,
                "context": p.snippet,
                "type": p.error_type,
                "suggested_action": p.suggested_action,
            })
    except Exception as e:
        logger.warning(f"parse_compilation_errors note: {e}")

    # Fallback to regex line scanning if parser didn't catch errors
    if not errors:
        lines = log_text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # Pattern 1: ! <error message>
            if line.startswith("!"):
                err_msg = line[1:].strip()
                line_no = None
                context = ""
                j = i + 1
                while j < min(i + 6, len(lines)):
                    nxt = lines[j].strip()
                    l_match = re.match(r"^l\.(\d+)\s*(.*)$", nxt)
                    if l_match:
                        line_no = int(l_match.group(1))
                        context = l_match.group(2).strip()
                        break
                    j += 1
                errors.append({
                    "error": err_msg,
                    "line": line_no,
                    "context": context,
                    "type": "LATEX_ERROR",
                    "suggested_action": "",
                })
            # Pattern 2: ./file.tex:123: <error message> or main.tex:123: ...
            else:
                file_line_match = re.match(r"^(?:\./)?([^:\s]+):(\d+):\s*(?:LaTeX Error:\s*)?(.*)$", line)
                if file_line_match:
                    errors.append({
                        "error": file_line_match.group(3).strip() or "Syntax error",
                        "line": int(file_line_match.group(2)),
                        "context": "",
                        "type": "SYNTAX_ERROR",
                        "suggested_action": "",
                    })
            i += 1

    has_errors = len(errors) > 0 or "fatal error" in log_text.lower() or "! " in log_text
    summary = "\n".join(e["error"] for e in errors[:5]) if errors else log_text[-400:]

    return {
        "has_errors": has_errors,
        "errors": errors,
        "summary": summary,
    }


def _error_signature(err: Dict[str, Any]) -> str:
    """Position-independent identity of a compile error, for before/after comparison."""
    msg = str(err.get("error", "")).lower()
    msg = re.sub(r"l\.\d+|line \d+|\d+", "#", msg)
    return re.sub(r"\s+", " ", msg).strip()[:160]


def _project_files(workspace: "ShadowWorkspace") -> List[Dict[str, str]]:
    files: List[Dict[str, str]] = []
    assets_dir = getattr(workspace, "_assets_dir", None)
    if assets_dir:
        try:
            assets_path = Path(assets_dir)
            if assets_path.is_dir():
                for item in assets_path.rglob("*"):
                    if item.is_file() and item.name != "main.tex":
                        try:
                            files.append({
                                # Relative to the project root: documents reference
                                # assets/<file>, so a path relative to assets/ itself
                                # left every image missing from the compile.
                                "filename": str(item.relative_to(assets_path.parent)),
                                "data": base64.b64encode(item.read_bytes()).decode("ascii"),
                            })
                        except Exception:
                            pass
        except Exception:
            pass
    for fpath, content in getattr(workspace, "_aux_files", {}).items():
        files.append({"filename": fpath, "data": base64.b64encode(content.encode("utf-8")).decode("ascii")})
    return files


def _run_compile(workspace: "ShadowWorkspace", code: str, engine: str, timeout_seconds: int) -> Dict[str, Any]:
    """One compile of ``code`` with the project's files. Raw result + parsed errors + PDF bytes."""
    from compiler import compile_latex

    result = compile_latex(
        latex_code=code,
        engine=engine,
        project_id=None,
        files=_project_files(workspace) or None,
        timeout_seconds=timeout_seconds,
        persist_synctex=False,
        # The agent must see the real errors: auto-recovery silently disables
        # packages and reports success for a document the user would not get.
        allow_recovery=False,
    )
    log_text = result.get("raw_log") or result.get("error_log") or result.get("log", "")
    diagnostics = parse_latex_error_log(log_text)
    errors = diagnostics.get("errors", [])
    tex_errs = result.get("errors") or []
    if result.get("success") and not tex_errs:
        errors = []  # warnings in the tail of a clean log are not errors
    elif not errors and tex_errs:
        errors = [{"error": e, "line": None, "context": "", "type": "LATEX_ERROR", "suggested_action": ""}
                  for e in tex_errs]
    pdf_bytes = None
    if result.get("pdf_base64"):
        try:
            pdf_bytes = base64.b64decode(result["pdf_base64"])
        except Exception:
            pdf_bytes = None
    is_infra_error = (
        any(p in str(result).lower() for p in INFRA_ERROR_PATTERNS)
        and not any(e.get("line") for e in errors) and "! " not in log_text
    ) or (not result.get("success") and not errors
          and log_text.strip() in ("LaTeX compilation failed.", "Compilation failed", ""))
    if result.get("log", "").startswith("Rendered via Fast TeX Engine"):
        is_infra_error = True  # ReportLab preview: no TeX engine on this host
    return {
        "result": result,
        "log": log_text,
        "errors": errors,
        "summary": diagnostics.get("summary", ""),
        "pdf": pdf_bytes,
        "overfull": result.get("overfull") or [],
        "infra": bool(is_infra_error),
    }


def compile_workspace(workspace: "ShadowWorkspace", engine: str = "pdfLaTeX",
                      timeout_seconds: int = 30) -> Dict[str, Any]:
    """
    Compiles the buffer (cached by content) and classifies its errors against
    the ORIGINAL document's: only errors the edits introduced are ``new_errors``.
    The original is compiled at most once per run, and only when a compile is
    actually requested.
    """
    import hashlib

    code = workspace.get_buffer()
    key = hashlib.sha256(code.encode("utf-8")).hexdigest()
    cache = workspace.__dict__.setdefault("_compile_cache", {})
    if key in cache:
        return cache[key]

    run = _run_compile(workspace, code, engine, timeout_seconds)
    if not run["infra"] and run["errors"]:
        base = workspace.__dict__.get("_original_compile")
        if base is None:
            original = workspace.get_original()
            base = run if original == code else _run_compile(workspace, original, engine, timeout_seconds)
            workspace.__dict__["_original_compile"] = base
        before = {_error_signature(e) for e in base["errors"]}
        run["new_errors"] = [e for e in run["errors"] if _error_signature(e) not in before]
        run["preexisting_errors"] = len(run["errors"]) - len(run["new_errors"])
    else:
        run["new_errors"] = list(run["errors"])
        run["preexisting_errors"] = 0
    cache.clear()  # only the latest buffer is worth keeping
    cache[key] = run
    return run


def compile_shadow_buffer(
    workspace: "ShadowWorkspace",
    engine: str = "pdfLaTeX",
    timeout_seconds: int = 30,
) -> Dict[str, Any]:
    """
    The agent's compile check.

    ``success`` means the edits introduced no compile error: errors the user's
    document already had are reported (``preexisting_errors``) but do not fail
    the check, so the agent never burns its budget on problems it did not cause
    and was not asked to fix. Before compiling, deterministic repairs are applied
    to the lines the agent edited (and only those, see edit_guard.scoped_heal).

    Returns {success, errors, new_errors, preexisting_errors, overfull_boxes,
    stderr, compile_time_ms, summary[, infra_skip]}.
    """
    try:
        workspace.heal_touched()
    except Exception as e:
        logger.warning(f"heal_touched before compile: {e}")

    try:
        run = compile_workspace(workspace, engine, timeout_seconds)
    except Exception as e:
        logger.warning(f"Shadow compilation exception: {e}", exc_info=True)
        return {
            "success": True, "errors": [], "new_errors": [], "stderr": "", "compile_time_ms": 0,
            "summary": f"Shadow compilation skipped (infrastructure error: {e}).", "infra_skip": True,
        }

    result = run["result"]
    if run["infra"]:
        logger.info("Shadow compilation infrastructure error detected — treating as skipped.")
        return {
            "success": True, "errors": [], "new_errors": [], "stderr": "",
            "compile_time_ms": result.get("compile_time_ms", 0),
            "summary": "Shadow compilation skipped (LaTeX compiler not available). Edits are syntactically plausible.",
            "infra_skip": True,
        }

    new_errors = run["new_errors"]
    stderr_text = ""
    if new_errors:
        try:
            from context_strategy import extract_error_context
            stderr_text = extract_error_context(latex_code=workspace.get_buffer(), errors=new_errors[:5],
                                                context_radius=10)
        except Exception:
            stderr_text = "COMPILATION ERRORS:\n" + "\n".join(
                f"  Line {e.get('line', '?')}: {e.get('error', 'Unknown error')}" for e in new_errors[:5])

    severe = [o for o in run["overfull"] if o.get("severe")]
    return {
        "success": not new_errors,
        "errors": new_errors[:5],
        "new_errors": new_errors[:5],
        "preexisting_errors": run["preexisting_errors"],
        "overfull_boxes": severe[:10],
        "stderr": stderr_text,
        "compile_time_ms": result.get("compile_time_ms", 0),
        "summary": run["summary"] if new_errors else (
            "Compiled without new errors" + (f" ({run['preexisting_errors']} error(s) were already in the "
                                              f"original document)" if run["preexisting_errors"] else "") + "."),
    }
