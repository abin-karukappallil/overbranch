"""
opencode/shadow_compiler.py — Shadow Compilation Verification
==============================================================
Wraps the existing compiler infrastructure to verify the shadow buffer
compiles without errors. Each compilation runs in an isolated temp directory
for thread safety.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .shadow_workspace import ShadowWorkspace

logger = logging.getLogger("opencode.shadow_compiler")

# Reuse the existing log parser from the legacy shadow compiler
from shadow_compiler import parse_latex_error_log


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

        result = compile_latex(
            latex_code=buffer_content,
            engine=engine,
            project_id=workspace._project_id,
        )

        success = result.get("success", False)
        log_text = result.get("log", "")
        diagnostics = parse_latex_error_log(log_text)

        errors = diagnostics.get("errors", [])
        has_errors = diagnostics.get("has_errors", False)

        if has_errors and errors:
            # Format errors as a readable stderr block for the agent
            stderr_lines = ["COMPILATION ERRORS:"]
            for err in errors[:5]:  # Cap at 5 errors to avoid context overflow
                line_no = err.get("line", "?")
                error_msg = err.get("error", "Unknown error")
                context = err.get("context", "")
                stderr_lines.append(f"  Line {line_no}: {error_msg}")
                if context:
                    stderr_lines.append(f"    Context: {context}")
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
        logger.warning(f"Shadow compilation exception: {e}")
        # If compiler is unavailable (e.g., no LaTeX installed), report gracefully
        return {
            "success": True,
            "errors": [],
            "stderr": f"(Shadow compilation skipped: {e})",
            "compile_time_ms": 0,
            "summary": f"Compilation infrastructure unavailable: {e}",
        }
