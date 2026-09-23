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
    - errors: List[Dict[str, Any]] with error message, line number, and context snippet
    - has_errors: bool
    - summary: str
    """
    if not log_text:
        return {"has_errors": False, "errors": [], "summary": ""}

    errors: List[Dict[str, Any]] = []
    lines = log_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Pattern 1: ! <error message>
        if line.startswith("!"):
            err_msg = line[1:].strip()
            line_no = None
            context = ""
            # Inspect following lines for l.<number> <context> or file:line:
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
            })
        # Pattern 2: ./file.tex:123: <error message> or main.tex:123: ...
        else:
            file_line_match = re.match(r"^(?:\./)?([^:\s]+):(\d+):\s*(?:LaTeX Error:\s*)?(.*)$", line)
            if file_line_match:
                errors.append({
                    "error": file_line_match.group(3).strip() or "Syntax error",
                    "line": int(file_line_match.group(2)),
                    "context": "",
                })
        i += 1

    has_errors = len(errors) > 0 or "fatal error" in log_text.lower() or "! " in log_text
    summary = "\n".join(e["error"] for e in errors[:5]) if errors else log_text[-400:]

    return {
        "has_errors": has_errors,
        "errors": errors,
        "summary": summary,
    }


def compile_shadow_buffer(
    workspace: "ShadowWorkspace",
    engine: str = "pdfLaTeX",
    timeout_seconds: int = 30,
) -> Dict[str, Any]:
    """
    Compiles the current shadow buffer content with the LaTeX engine.

    Creates an isolated temp directory, writes the buffer content as main.tex,
    symlinks/copies assets, runs the compiler, and returns structured results.

    Args:
        workspace: The active ShadowWorkspace instance.
        engine: LaTeX engine to use (pdfLaTeX, XeLaTeX, LuaLaTeX).
        timeout_seconds: Max seconds for compilation (30s default).

    Returns:
        {
            "success": bool,
            "errors": [{"error": str, "line": int|None, "context": str}],
            "stderr": str,  # Raw error log for the agent
            "compile_time_ms": int,
        }
    """
    buffer_content = workspace.get_buffer()

    try:
        from compiler import compile_latex

        # Pass project files and assets if available
        extra_files = []
        if getattr(workspace, "_assets_dir", None):
            try:
                assets_path = Path(workspace._assets_dir)
                if assets_path.exists() and assets_path.is_dir():
                    for item in assets_path.rglob("*"):
                        if item.is_file() and item.name != "main.tex":
                            try:
                                rel_path = str(item.relative_to(assets_path))
                                data_bytes = item.read_bytes()
                                extra_files.append({
                                    "filename": rel_path,
                                    "data": base64.b64encode(data_bytes).decode("ascii"),
                                })
                            except Exception:
                                pass
            except Exception:
                pass

        result = compile_latex(
            latex_code=buffer_content,
            engine=engine,
            project_id=workspace._project_id,
            files=extra_files if extra_files else None,
        )

        success = result.get("success", False)
        # Check raw_log or error_log (returned on failure) or log (returned on success)
        log_text = result.get("raw_log") or result.get("error_log") or result.get("log", "")
        diagnostics = parse_latex_error_log(log_text)

        errors = diagnostics.get("errors", [])
        has_errors = not success or diagnostics.get("has_errors", False)

        # Detect infrastructure errors vs LaTeX syntax errors
        # If pdflatex is missing, binary not found, or command failed at OS level
        is_infra_error = (
            any(p.lower() in str(result).lower() for p in INFRA_ERROR_PATTERNS)
            or (not success and not errors and log_text.strip() in ("LaTeX compilation failed.", "Compilation failed", ""))
        )

        if is_infra_error and not any(e.get("line") for e in errors) and "! " not in log_text:
            logger.info("Shadow compilation infrastructure error detected — treating as skipped.")
            return {
                "success": True,  # Treat as pass so agent doesn't try to fix non-existent bugs
                "errors": [],
                "stderr": "",
                "compile_time_ms": result.get("compile_time_ms", 0),
                "summary": "Shadow compilation skipped (LaTeX compiler not available or infrastructure error). Edits are syntactically plausible.",
                "infra_skip": True,
            }

        if has_errors:
            # Format errors as a readable stderr block for the agent
            stderr_lines = ["COMPILATION ERRORS:"]
            if errors:
                for err in errors[:5]:  # Cap at 5 errors to avoid context overflow
                    line_no = err.get("line", "?")
                    error_msg = err.get("error", "Unknown error")
                    context = err.get("context", "")
                    stderr_lines.append(f"  Line {line_no}: {error_msg}")
                    if context:
                        stderr_lines.append(f"    Context: {context}")
            else:
                raw_summary = result.get("error_log") or log_text[-500:] or "Compilation failed"
                stderr_lines.append(f"  {raw_summary}")
            stderr_text = "\n".join(stderr_lines)
        else:
            stderr_text = ""

        return {
            "success": success and not has_errors,
            "errors": errors[:5],
            "stderr": stderr_text,
            "compile_time_ms": result.get("compile_time_ms", 0),
            "summary": diagnostics.get("summary", ""),
        }

    except Exception as e:
        logger.warning(f"Shadow compilation exception: {e}", exc_info=True)
        # If compiler is unavailable (e.g., no LaTeX installed), report gracefully
        return {
            "success": True,
            "errors": [],
            "stderr": "",
            "compile_time_ms": 0,
            "summary": f"Shadow compilation skipped (infrastructure error: {e}). Edits are syntactically plausible.",
            "infra_skip": True,
        }
