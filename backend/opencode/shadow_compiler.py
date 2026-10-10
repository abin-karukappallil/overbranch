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

# Markers the compiler itself writes when it could not run TeX at all (see
# compiler._compile_latex_impl). Generic phrases ("not found", "timed out",
# "winerror") used to be matched against the whole result, which turned real TeX
# failures — `File 'logo.png' not found`, a slow compile — into "compiler
# unavailable": the gate was skipped and compilation was switched off for the
# rest of the run, so broken edits shipped. Only a production host with TeX ever
# hits that path, which is why it never showed in development.
INFRA_MARKERS = ("[infrastructure error]", "compilation infrastructure error")
_FAILURE_PLACEHOLDERS = ("", "latex compilation failed.", "compilation failed")


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
                "file": p.file,
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


def _norm_file(path: Any) -> Optional[str]:
    if not path:
        return None
    p = str(path).replace("\\", "/")
    return p[2:] if p.startswith("./") else p


def _error_signature(err: Dict[str, Any]) -> str:
    """
    Position-independent identity of a compile error, for before/after comparison.

    The message alone is not an identity: TeX's messages are generic
    ("Undefined control sequence.", "Missing $ inserted."), so keyed by message a
    document that already had one undefined macro hid every new one the agent
    added. The text of the source line the error points at (``source``, attached
    by compile_workspace) tells them apart; an error the edit leaves on a line it
    changed gets a new signature, i.e. counts as the edit's.
    """
    msg = str(err.get("error", "")).lower()
    msg = re.sub(r"l\.\d+|line \d+|\d+", "#", msg)
    msg = re.sub(r"\s+", " ", msg).strip()[:160]
    src = re.sub(r"\s+", " ", str(err.get("source") or "")).strip()[:240]
    return f"{_norm_file(err.get('file')) or ''}|{msg}|{src}"


def _attach_sources(errors: List[Dict[str, Any]], code: str, file_path: str) -> None:
    """Records the text of the source line each error points at (errors in ``code`` only)."""
    lines = code.splitlines()
    own = _norm_file(file_path) or "main.tex"
    for err in errors:
        ln = err.get("line")
        f = _norm_file(err.get("file"))
        if isinstance(ln, int) and 1 <= ln <= len(lines) and (f is None or f == own):
            err["source"] = lines[ln - 1].strip()


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

    project_id = getattr(workspace, "_project_id", None)
    if project_id in ("default", "", "proj-default", "scratchpad"):
        project_id = None

    file_path = getattr(workspace, "_file_path", "main.tex")
    files = _project_files(workspace)
    main_code = code

    # If the user is editing an auxiliary file (not main.tex), ensure the edited buffer
    # is passed as that file, and the real main.tex is used as latex_code. Without
    # the real main.tex the fragment itself was compiled as the document, so the
    # check said nothing about the project the user builds.
    if file_path != "main.tex":
        files.append({
            "filename": file_path,
            "data": base64.b64encode(code.encode("utf-8")).decode("ascii"),
        })
        aux_main = getattr(workspace, "_aux_files", {}).get("main.tex")
        if not aux_main:
            from compiler import load_project_text_file
            aux_main = load_project_text_file(project_id, "main.tex")
            if aux_main:
                workspace.__dict__.setdefault("_aux_files", {})["main.tex"] = aux_main
        if aux_main:
            main_code = aux_main

    def compile_once(timeout: int) -> Dict[str, Any]:
        return compile_latex(
            latex_code=main_code,
            engine=engine,
            project_id=project_id,
            files=files or None,
            timeout_seconds=timeout,
            persist_synctex=False,
            allow_recovery=True,
            # The errors reported here are mapped onto the agent's buffer by line
            # number; a whole-document pre-heal that inserts a preamble line shifts
            # every one of them, so the agent "fixes" the wrong lines. The edited
            # lines are already healed by workspace.heal_touched().
            pre_heal=False,
        )

    result = compile_once(timeout_seconds)
    log_text = result.get("raw_log") or result.get("error_log") or result.get("log", "")
    if not result.get("success") and "[TIMEOUT]" in (log_text or ""):
        # Agent compiles do not go through compile_queue, so under load a healthy
        # document can time out; one retry with twice the budget before calling it an error.
        result = compile_once(timeout_seconds * 2)
        log_text = result.get("raw_log") or result.get("error_log") or result.get("log", "")

    # TeX's own error lines (`./main.tex:12: …`, `! …`) are taken from the FULL log by
    # the compiler; the log text here is only its tail (1000 chars on success).
    tex_errs = [e for e in (result.get("errors") or []) if e]
    if tex_errs:
        diagnostics = parse_latex_error_log("\n".join(tex_errs))
        errors = diagnostics.get("errors", [])
        if not errors and not result.get("success"):
            diagnostics = parse_latex_error_log(log_text)
            errors = diagnostics.get("errors", [])
        if not errors:
            errors = [{"error": e, "line": None, "context": "", "type": "LATEX_ERROR",
                       "suggested_action": "", "file": None} for e in tex_errs]
    elif result.get("success"):
        diagnostics, errors = {"summary": ""}, []  # warnings in the tail of a clean log are not errors
    else:
        diagnostics = parse_latex_error_log(log_text)
        errors = diagnostics.get("errors", [])

    pdf_bytes = None
    if result.get("pdf_base64"):
        try:
            pdf_bytes = base64.b64decode(result["pdf_base64"])
        except Exception:
            pdf_bytes = None

    low_log = (log_text or "").lower()
    is_infra_error = bool(str(result.get("log", "")).startswith("Rendered via Fast TeX Engine")) or (
        not result.get("success") and not errors
        and (any(m in low_log for m in INFRA_MARKERS) or low_log.strip() in _FAILURE_PLACEHOLDERS)
    )
    if not result.get("success") and not errors and not is_infra_error:
        # TeX ran and failed but nothing parseable came out (timeout, unparsed fatal
        # error). That is a failure, never "no errors": it used to pass the gate.
        tail = [ln.strip() for ln in (log_text or "").splitlines() if ln.strip()]
        reason = next((ln for ln in reversed(tail) if ln.startswith("[TIMEOUT]")), tail[-1] if tail else "")
        errors = [{"error": f"Compilation failed: {reason[:200]}", "line": None, "context": "",
                   "type": "COMPILE_FAILED", "suggested_action": "", "file": None}]
        diagnostics = {"summary": errors[0]["error"]}
    return {
        "result": result,
        "log": log_text,
        "errors": errors,
        "summary": diagnostics.get("summary", "") or "\n".join(e["error"] for e in errors[:5]),
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
    # The key must cover every file the compile reads, not just the main
    # buffer. A document that \input{}s its chapters has a main file that
    # never changes, so an edit to a chapter hit this cache and was handed the
    # verdict from *before* it — reporting a fixed document as still broken,
    # and a broken one as fine.
    digest = hashlib.sha256(code.encode("utf-8"))
    for name, content in sorted((getattr(workspace, "_aux_files", {}) or {}).items()):
        digest.update(b"\x00")
        digest.update(name.encode("utf-8", "replace"))
        digest.update(b"\x00")
        digest.update((content or "").encode("utf-8", "replace"))
    key = digest.hexdigest()
    cache = workspace.__dict__.setdefault("_compile_cache", {})
    if key in cache:
        return cache[key]

    from collections import Counter

    file_path = getattr(workspace, "_file_path", "main.tex")
    run = _run_compile(workspace, code, engine, timeout_seconds)
    _attach_sources(run["errors"], code, file_path)
    run["errors_before"] = None
    if not run["infra"] and run["errors"]:
        base = workspace.__dict__.get("_original_compile")
        if base is None:
            original = workspace.get_original()
            base = run if original == code else _run_compile(workspace, original, engine, timeout_seconds)
            if base is not run:
                _attach_sources(base["errors"], original, file_path)
            workspace.__dict__["_original_compile"] = base
        # Counted, not a set: two new undefined macros next to one old one are two new errors.
        remaining = Counter(_error_signature(e) for e in base["errors"])
        new_errors = []
        for e in run["errors"]:
            sig = _error_signature(e)
            if remaining[sig] > 0:
                remaining[sig] -= 1
            else:
                new_errors.append(e)
        run["new_errors"] = new_errors
        run["preexisting_errors"] = len(run["errors"]) - len(new_errors)
        run["errors_before"] = 0 if base.get("infra") else len(base["errors"])
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

    By default ``success`` means the edits introduced no compile error: errors
    the user's document already had are reported (``preexisting_errors``) but do
    not fail the check, so the agent never burns its budget on problems it did
    not cause and was not asked to fix. With ``workspace.compile_strict`` set (a
    "fix the compile errors" request) ``success`` needs zero errors — otherwise
    a fix run "passed" with the original errors untouched, because they were
    pre-existing. Before compiling, deterministic repairs are applied to the
    lines the agent edited (and only those, see edit_guard.scoped_heal).

    ``errors`` are the errors the agent must fix (all of them in strict mode,
    the new ones otherwise). Returns {success, errors, new_errors,
    new_error_count, preexisting_errors, errors_before, errors_after,
    remaining_errors, strict, overfull_boxes, stderr, compile_time_ms,
    summary[, infra_skip]}.
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

    strict = bool(getattr(workspace, "compile_strict", False))
    all_errors = run["errors"]
    new_errors = run["new_errors"]
    failing = all_errors if strict else new_errors
    stderr_text = ""
    if failing:
        try:
            from context_strategy import extract_error_context
            stderr_text = extract_error_context(latex_code=workspace.get_buffer(), errors=failing[:5],
                                                context_radius=10)
        except Exception:
            stderr_text = "COMPILATION ERRORS:\n" + "\n".join(
                f"  Line {e.get('line', '?')}: {e.get('error', 'Unknown error')}" for e in failing[:5])

    if not all_errors:
        summary = "Compiled without errors."
    elif not failing:
        summary = (f"No new errors; {len(all_errors)} error(s) that were already in the original document "
                   f"remain (not caused by these edits).")
    elif strict:
        before = run.get("errors_before")
        summary = (f"{len(all_errors)} compile error(s) remain"
                   + (f" ({before} before the edits)" if before is not None else "") + ":\n"
                   + "\n".join(str(e.get("error", "")) for e in all_errors[:5]))
    else:
        summary = run["summary"]

    severe = [o for o in run["overfull"] if o.get("severe")]
    return {
        "success": not failing,
        "errors": failing[:5],
        "new_errors": new_errors[:5],
        "new_error_count": len(new_errors),
        "preexisting_errors": run["preexisting_errors"],
        "errors_before": run.get("errors_before"),
        "errors_after": len(all_errors),
        "remaining_errors": len(all_errors),
        "strict": strict,
        "overfull_boxes": severe[:10],
        "stderr": stderr_text,
        "compile_time_ms": result.get("compile_time_ms", 0),
        "summary": summary,
    }
