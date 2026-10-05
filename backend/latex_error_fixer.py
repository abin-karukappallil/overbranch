"""
backend/latex_error_fixer.py — Automated LaTeX Compilation Error Diagnostics & Repair
======================================================================================
Provides:
1. parse_compilation_errors: Parses LaTeX compilation error logs into structured diagnostics
   with exact line numbers, error categories, and contextual advice.
2. auto_heal_latex_code: Deterministically repairs common LaTeX syntax errors:
   - Unclosed environments (\\begin{frame}, \\begin{tikzpicture}, \\begin{itemize}, etc.)
   - Missing \\usetikzlibrary{calc} when coordinate calculations $(...)$ are present
   - Missing semicolons in TikZ path statements (\\fill, \\draw, \\node, \\path)
   - Missing \\begin{document} / \\end{document}
   - Undefined standard colors in Beamer / Regalia
3. format_compilation_fix_prompt: Generates surgical, line-targeted instructions for the
   LLM agent when interactive error repair is required.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("latex_error_fixer")

# Pre-compiled hot-path patterns. auto_heal_latex_code runs on the whole buffer
# on every single agent write, so per-line re module dispatch showed up as a
# measurable share of edit latency.
_RE_LINE_COMMENT = re.compile(r"%.*$")
_RE_TRAILING_COMMENT = re.compile(r"(\s*%.*)$")
_RE_BEGIN_FRAME = re.compile(r"\\begin\s*\{frame\}")
_RE_END_FRAME = re.compile(r"\\end\s*\{frame\}")
_RE_END_DOCUMENT = re.compile(r"\\end\s*\{document\}")
_RE_BEGIN_DOCUMENT = re.compile(r"\\begin\s*\{document\}")



@dataclass
class ParsedLatexError:
    line_number: Optional[int]
    error_type: str
    message: str
    snippet: str = ""
    suggested_action: str = ""


# Standard Regalia / Beamer color definitions to inject if undefined
REGALIA_COLOR_DEFS = (
    "\\definecolor{navy}{HTML}{0B2545}\n"
    "\\definecolor{navylight}{HTML}{13315C}\n"
    "\\definecolor{gold}{HTML}{C9A24B}\n"
    "\\definecolor{cream}{HTML}{F7F4EC}\n"
    "\\definecolor{ink}{HTML}{1D1D1D}\n"
    "\\definecolor{muted}{HTML}{5C6270}\n"
)


def parse_compilation_errors(error_text: str) -> List[ParsedLatexError]:
    """
    Parses a raw LaTeX compilation error log or user-submitted error report into
    structured ParsedLatexError objects with line numbers and targeted advice.
    """
    if not error_text or not error_text.strip():
        return []

    errors: List[ParsedLatexError] = []
    lines = error_text.splitlines()

    # Pattern: ./file.tex:<line>: <error message>
    re_file_line = re.compile(r"(?:\./)?[\w\-_./]+\.tex:(\d+):\s*(.*)", re.IGNORECASE)
    # Pattern: l.<line> <code snippet>
    re_l_num = re.compile(r"^l\.(\d+)\s*(.*)")
    # Pattern: \begin{env} on input line <line> ended by \end{env}
    re_unclosed_env = re.compile(r"\\begin\{([^}]+)\}\s+on\s+input\s+line\s+(\d+)\s+ended\s+by\s+\\end\{([^}]+)\}", re.IGNORECASE)

    for idx, line in enumerate(lines):
        line_str = line.strip()
        if not line_str:
            continue

        # 1. Check for unclosed environment mismatch (e.g. \begin{frame} on line 160 ended by \end{document})
        m_unclosed = re_unclosed_env.search(line_str)
        if m_unclosed:
            opened_env = m_unclosed.group(1)
            line_no = int(m_unclosed.group(2))
            closed_env = m_unclosed.group(3)
            errors.append(ParsedLatexError(
                line_number=line_no,
                error_type="UNCLOSED_ENVIRONMENT",
                message=f"\\begin{{{opened_env}}} starting on line {line_no} was ended by \\end{{{closed_env}}} without being closed.",
                snippet=line_str,
                suggested_action=f"Insert \\end{{{opened_env}}} before \\end{{{closed_env}}}.",
            ))
            continue

        # 2. Check for standard ./main.tex:66: <error message>
        m_file_line = re_file_line.match(line_str)
        if m_file_line:
            line_no = int(m_file_line.group(1))
            msg = m_file_line.group(2).strip()

            err_type = "GENERAL_LATEX_ERROR"
            action = ""

            if "bad math environment delimiter" in msg.lower():
                err_type = "BAD_MATH_DELIMITER"
                action = (
                    "TikZ coordinate arithmetic $(...)$ requires \\usetikzlibrary{calc} in the preamble. "
                    "Ensure math mode delimiters ($, $$, \\(, \\)) are balanced."
                )
            elif "giving up on this path" in msg.lower() or "did you forget a sem" in msg.lower():
                err_type = "TIKZ_SYNTAX_ERROR"
                action = "Ensure all TikZ path commands (\\fill, \\draw, \\node, \\path) inside \\begin{tikzpicture} end with a semicolon (;)."
            elif "undefined control sequence" in msg.lower():
                err_type = "UNDEFINED_MACRO"
                action = "Check for misspelled macro name or missing package in preamble."
            elif "undefined color" in msg.lower():
                err_type = "UNDEFINED_COLOR"
                action = "Define the color in preamble using \\definecolor{<name>}{HTML}{<hex>} or \\definecolor{<name>}{RGB}{...}."
            elif "emergency stop" in msg.lower():
                continue

            errors.append(ParsedLatexError(
                line_number=line_no,
                error_type=err_type,
                message=msg,
                snippet=line_str,
                suggested_action=action,
            ))
            continue

        # 3. Check for standalone ! Package tikz Error: ...
        if "package tikz error" in line_str.lower():
            errors.append(ParsedLatexError(
                line_number=None,
                error_type="TIKZ_SYNTAX_ERROR",
                message=line_str,
                snippet=line_str,
                suggested_action="Verify TikZ path statements end with a semicolon (;) and \\usetikzlibrary{calc} is loaded.",
            ))

    # Deduplicate errors by (line_number, error_type)
    seen = set()
    deduped: List[ParsedLatexError] = []
    for err in errors:
        key = (err.line_number, err.error_type, err.message[:40])
        if key not in seen:
            seen.add(key)
            deduped.append(err)

    return deduped


def heal_lonely_items(code: str) -> Tuple[str, List[str]]:
    """
    Detects \\item statements that exist outside of any list environment
    (\\begin{itemize}, \\begin{enumerate}, \\begin{description}) and wraps
    them in \\begin{itemize} ... \\end{itemize}.
    Prevents 'LaTeX Error: Lonely \\item--perhaps a missing list environment'.
    """
    if not code or r"\item" not in code:
        return code, []

    repairs: List[str] = []
    lines = code.splitlines(keepends=True)
    out_lines: List[str] = []

    list_depth = 0
    in_lonely_block = False

    re_list_begin = re.compile(r"\\begin\s*\{(?:itemize|enumerate|description)\}")
    re_list_end = re.compile(r"\\end\s*\{(?:itemize|enumerate|description)\}")
    re_item = re.compile(r"^\s*\\item\b")
    re_block_break = re.compile(r"^\s*\\(?:begin|end|section\*?|chapter\*?|part\*?|subsection\*?|subsubsection\*?)\b")

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Update list_depth from line content
        for _ in re_list_begin.finditer(line):
            list_depth += 1
        for _ in re_list_end.finditer(line):
            list_depth = max(0, list_depth - 1)

        is_item_line = bool(re_item.search(line))

        if is_item_line:
            if list_depth == 0 and not in_lonely_block:
                out_lines.append("\\begin{itemize}\n")
                in_lonely_block = True
                repairs.append(f"Auto-wrapped lonely \\item starting at line {idx} in \\begin{{itemize}}.")
            out_lines.append(line)
        else:
            if in_lonely_block:
                # Close the lonely block if blank line, environment start/end, or inside real list
                if stripped == "" or re_block_break.search(line) or list_depth > 0:
                    out_lines.append("\\end{itemize}\n")
                    in_lonely_block = False
                    repairs.append(f"Auto-closed lonely \\item block with \\end{{itemize}} before line {idx}.")
            out_lines.append(line)

    if in_lonely_block:
        out_lines.append("\\end{itemize}\n")
        repairs.append("Auto-closed trailing lonely \\item block with \\end{itemize} at document end.")

    return "".join(out_lines), repairs


def fix_tikz_semicolons(code: str) -> Tuple[str, List[str]]:
    """
    Ensures that TikZ path commands (\\draw, \\node, \\fill, \\path, \\coordinate, etc.)
    are properly terminated with a semicolon (;) without corrupting multi-line paths.
    """
    if "\\begin{tikzpicture}" not in code:
        return code, []

    fixes: List[str] = []
    stmt_start = re.compile(r"^\s*\\(?:draw|fill|filldraw|node|coordinate|path|clip|shade|shadedraw|matrix|graph)\b")
    end_env = re.compile(r"\\end\{(?:tikzpicture|scope|frame)\}")

    def _fix_block(match: re.Match) -> str:
        block = match.group(0)
        lines = block.splitlines(keepends=True)
        new_lines: List[str] = []
        in_stmt = False

        for idx, line in enumerate(lines):
            stripped = line.strip()
            clean = _RE_LINE_COMMENT.sub("", stripped).rstrip()

            if not clean:
                new_lines.append(line)
                continue

            is_new = bool(stmt_start.match(clean))
            is_close = bool(end_env.search(clean))

            if in_stmt and (is_new or is_close):
                for j in range(len(new_lines) - 1, -1, -1):
                    prev = new_lines[j]
                    prev_clean = _RE_LINE_COMMENT.sub("", prev.strip()).rstrip()
                    if prev_clean:
                        if not prev_clean.endswith(";"):
                            m_comm = _RE_TRAILING_COMMENT.search(prev)
                            if m_comm:
                                new_lines[j] = prev[:m_comm.start()].rstrip() + ";" + m_comm.group(1)
                            else:
                                new_lines[j] = prev.rstrip("\r\n") + ";\n"
                            fixes.append("Added missing semicolon (;) to TikZ path statement.")
                        break
                in_stmt = False

            if is_new:
                in_stmt = True

            if in_stmt and clean.endswith(";"):
                in_stmt = False

            new_lines.append(line)

        return "".join(new_lines)

    healed_code = re.sub(
        r"\\begin\{tikzpicture\}(?:\[[^\]]*\])?.*?(?:\\end\{tikzpicture\}|\\end\{frame\}|\\end\{document\})",
        _fix_block,
        code,
        flags=re.DOTALL,
    )
    return healed_code, fixes


def balance_latex_environments(latex_code: str) -> Tuple[str, List[str]]:
    """
    Accurately balances LaTeX environments (\\begin{env} ... \\end{env}),
    ensuring that:
    1. Frames are closed before the next \\begin{frame} or \\end{document}.
    2. Inner environments inside frames (itemize, tikzpicture, columns, etc.) are closed before \\end{frame}.
    3. All remaining open environments are closed before \\end{document}.
    """
    if not latex_code or not latex_code.strip():
        return latex_code, []

    repairs: List[str] = []
    lines = latex_code.splitlines(keepends=True)
    out_lines: List[str] = []

    # Stack holds tuples of (env_name, line_number)
    env_stack: List[Tuple[str, int]] = []

    re_begin = re.compile(r"\\begin\s*\{([a-zA-Z*]+)\}")
    re_end = re.compile(r"\\end\s*\{([a-zA-Z*]+)\}")

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Ignore comments
        if stripped.startswith("%"):
            out_lines.append(line)
            continue

        # Check if line starts a new frame while a previous frame is still open
        if _RE_BEGIN_FRAME.search(line) and any(e[0] == "frame" for e in env_stack):
            # Close all environments up to and including 'frame'
            while env_stack:
                env_name, open_line = env_stack.pop()
                out_lines.append(f"\\end{{{env_name}}}\n")
                repairs.append(f"Auto-closed unclosed \\begin{{{env_name}}} from line {open_line} before starting new frame at line {idx}.")
                if env_name == "frame":
                    break

        # Check if line closes a frame (\end{frame}) while inner environments are still open
        if _RE_END_FRAME.search(line) and any(e[0] == "frame" for e in env_stack):
            while env_stack and env_stack[-1][0] != "frame":
                inner_env, inner_line = env_stack.pop()
                out_lines.append(f"\\end{{{inner_env}}}\n")
                repairs.append(f"Auto-closed inner environment \\begin{{{inner_env}}} from line {inner_line} before \\end{{frame}} at line {idx}.")

        # Check if line is \end{document} while other environments are still open
        if _RE_END_DOCUMENT.search(line) and env_stack:
            while env_stack:
                env_name, open_line = env_stack.pop()
                if env_name != "document":
                    out_lines.append(f"\\end{{{env_name}}}\n")
                    repairs.append(f"Auto-closed unclosed \\begin{{{env_name}}} from line {open_line} before \\end{{document}} at line {idx}.")
                else:
                    break

        end_matches = list(re_end.finditer(line))
        begin_matches = list(re_begin.finditer(line))

        # Check for end environments on this line
        is_orphan_scope = all(e[0] == "document" for e in env_stack)
        if end_matches and not begin_matches:
            line_to_keep = line
            for m in end_matches:
                env_name = m.group(1)
                stack_names = [e[0] for e in env_stack]
                if env_name not in stack_names and env_name != "document":
                    if is_orphan_scope:
                        # Discard orphaned \end{env} with no matching open environment
                        line_to_keep = line_to_keep.replace(m.group(0), "")
                        repairs.append(f"Removed orphaned \\end{{{env_name}}} at line {idx} (no matching open environment).")
                elif env_name in stack_names:
                    # Close inner environments if this \end closes an outer one
                    while env_stack and env_stack[-1][0] != env_name:
                        inner_env, inner_line = env_stack.pop()
                        out_lines.append(f"\\end{{{inner_env}}}\n")
                        repairs.append(f"Auto-closed inner environment \\begin{{{inner_env}}} from line {inner_line} before \\end{{{env_name}}} at line {idx}.")
                    if env_stack and env_stack[-1][0] == env_name:
                        env_stack.pop()

            if line_to_keep.strip() or line_to_keep.endswith("\n"):
                if line_to_keep.strip():
                    out_lines.append(line_to_keep)
        else:
            for m in end_matches:
                env_name = m.group(1)
                stack_names = [e[0] for e in env_stack]
                if env_name in stack_names:
                    while env_stack and env_stack[-1][0] != env_name:
                        inner_env, inner_line = env_stack.pop()
                        out_lines.append(f"\\end{{{inner_env}}}\n")
                        repairs.append(f"Auto-closed inner environment \\begin{{{inner_env}}} from line {inner_line} before \\end{{{env_name}}} at line {idx}.")
                    if env_stack and env_stack[-1][0] == env_name:
                        env_stack.pop()
                elif env_name != "document" and is_orphan_scope:
                    line = line.replace(m.group(0), "")
                    repairs.append(f"Removed orphaned \\end{{{env_name}}} at line {idx}.")

            # Push begin environments
            for m in begin_matches:
                env_name = m.group(1)
                env_stack.append((env_name, idx))

            if line.strip() or line.endswith("\n"):
                out_lines.append(line)

    # If document ended without closing environments (e.g. unclosed frame before document end)
    if env_stack:
        for env_name, open_line in reversed(env_stack):
            if env_name != "document":
                # Insert \end{env_name} before \end{document} if present in out_lines
                inserted = False
                for j in range(len(out_lines) - 1, -1, -1):
                    if r"\end{document}" in out_lines[j]:
                        out_lines.insert(j, f"\\end{{{env_name}}}\n")
                        repairs.append(f"Auto-closed trailing unclosed \\begin{{{env_name}}} from line {open_line} before \\end{{document}}.")
                        inserted = True
                        break
                if not inserted:
                    out_lines.append(f"\\end{{{env_name}}}\n")
                    repairs.append(f"Auto-closed trailing unclosed \\begin{{{env_name}}} from line {open_line} at document end.")

    result = "".join(out_lines)
    return result, repairs


def auto_heal_latex_code(code: str, error_log: str = "") -> Tuple[str, List[str]]:
    """
    Applies deterministic automatic fixes to LaTeX code for common syntax and compilation issues:
    1. Ensures \\begin{document} and \\end{document} structural integrity.
    2. Repairs mangled newline spacing (e.g. \\[0.3em] written as \\[0.3em]).
    3. Hoists any \\usepackage or \\usetikzlibrary out of document body into preamble.
    4. Balances all unclosed environments (frames, itemize, tikzpicture, columns) and removes orphaned \\end{...}.
    5. Auto-wraps lonely \\item statements in \\begin{itemize} ... \\end{itemize}.
    6. Injects \\usepackage{tikz} and \\usetikzlibrary{calc,positioning,arrows.meta} whenever TikZ is used.
    7. Fixes missing semicolons on TikZ path commands without breaking multi-line statements.
    8. Injects missing Regalia / Beamer color definitions.
    """
    if not code or not code.strip():
        return code, []

    fixes_applied: List[str] = []

    # 1. Structural begin/end document integrity first
    try:
        from document_index import ensure_document_environment
        code = ensure_document_environment(code)
    except Exception as e:
        logger.warning(f"ensure_document_environment pre-pass note: {e}")

    # 2. Repair mangled newline spacing: \[length] -> \\[length]
    # (e.g. \[0.3em] or \[1.5em] mistakenly opening display math instead of newline with spacing)
    re_mangled_spacing = re.compile(r"(?<!\\)\\(\[\s*-?\d+(?:\.\d+)?\s*(?:pt|mm|cm|in|ex|em|bp|dd|pc|sp)\s*\])")
    if re_mangled_spacing.search(code):
        code = re_mangled_spacing.sub(r"\\\\\1", code)
        fixes_applied.append("Repaired corrupted newline spacing (converted stray '\\[<len>]' to '\\\\[<len>]').")

    # 3. Hoist any packages / libraries found inside document body into the preamble
    m_doc_env = _RE_BEGIN_DOCUMENT.search(code)
    if m_doc_env:
        doc_pos = m_doc_env.start()
        preamble = code[:doc_pos]
        body = code[doc_pos:]

        pkg_pattern = re.compile(
            r"^[ \t]*(\\(?:usepackage|usetikzlibrary|RequirePackage)(?:\[[^\]]*\])?\{[^}]+\}[ \t]*\n?)",
            re.MULTILINE,
        )
        found_in_body = list(pkg_pattern.finditer(body))
        if found_in_body:
            extracted_pkgs = []
            for pm in reversed(found_in_body):
                pkg_cmd = pm.group(1).strip()
                extracted_pkgs.insert(0, pkg_cmd)
                body = body[:pm.start()] + body[pm.end():]
                fixes_applied.append(f"Moved `{pkg_cmd}` from document body into preamble.")

            for pkg in extracted_pkgs:
                if pkg not in preamble:
                    preamble = preamble.rstrip() + "\n" + pkg + "\n"

            code = preamble + body

    # 4. Lonely item healing (wraps stray \item in \begin{itemize})
    code, item_repairs = heal_lonely_items(code)
    fixes_applied.extend(item_repairs)

    # 5. Structural environment balancing (closes unclosed frames and environments, removes orphans)
    code, balance_repairs = balance_latex_environments(code)
    fixes_applied.extend(balance_repairs)

    # 6. TikZ Calc & Core Libraries Fix
    # If tikzpicture or \usepackage{tikz} is present, ALWAYS ensure calc, positioning, arrows.meta are loaded
    has_tikz = "\\begin{tikzpicture}" in code or "\\usepackage{tikz}" in code or "tikzpicture" in code
    if has_tikz:
        if not re.search(r"\\usepackage(?:\[[^\]]*\])?\{tikz\}", code):
            m_doc = re.search(r"(\\documentclass(?:\[[^\]]*\])?\{[^}]+\}\n)", code)
            if m_doc:
                code = code[:m_doc.end()] + "\\usepackage{tikz}\n\\usetikzlibrary{calc}\n\\usetikzlibrary{positioning,arrows.meta}\n" + code[m_doc.end():]
                fixes_applied.append("Injected missing \\usepackage{tikz} and \\usetikzlibrary{calc} into preamble.")
        else:
            has_calc_lib = bool(re.search(r"\\usetikzlibrary\{[^}]*calc[^}]*\}", code))
            if not has_calc_lib:
                m_tikz = re.search(r"\\usepackage(?:\[[^\]]*\])?\{tikz\}", code)
                if m_tikz:
                    code = code[:m_tikz.end()] + "\n\\usetikzlibrary{calc}\n\\usetikzlibrary{positioning,arrows.meta}" + code[m_tikz.end():]
                    fixes_applied.append("Injected \\usetikzlibrary{calc} into preamble.")

    # 7. TikZ Semicolon Fix
    code, tikz_fixes = fix_tikz_semicolons(code)
    fixes_applied.extend(tikz_fixes)

    # 8. Injected Undefined Colors (Regalia / Beamer)
    needed_colors = []
    for c_name in ("navy", "gold", "cream", "ink", "muted"):
        if re.search(rf"\b{c_name}\b", code) and not re.search(rf"\\definecolor\{{{c_name}\}}", code):
            needed_colors.append(c_name)

    if needed_colors:
        m_begin = _RE_BEGIN_DOCUMENT.search(code)
        if m_begin:
            pos = m_begin.start()
            code = code[:pos] + f"\n% ---------- Palette ----------\n{REGALIA_COLOR_DEFS}\n" + code[pos:]
            fixes_applied.append(f"Injected missing color definitions ({', '.join(needed_colors)}) into preamble.")

    # 9. Final pass on document environment integrity
    try:
        from document_index import ensure_document_environment
        code = ensure_document_environment(code)
    except Exception as e:
        logger.warning(f"ensure_document_environment post-pass note: {e}")

    return code, fixes_applied


def format_compilation_fix_prompt(
    raw_error: str,
    parsed_errors: List[ParsedLatexError],
    workspace: Any,
    fixes_applied: List[str],
) -> str:
    """
    Builds a surgical compilation fix prompt that equips the LLM agent with
    exact line snippets, diagnostics, and step-by-step instructions.
    """
    diagnostic_blocks: List[str] = []

    for err in parsed_errors[:6]:
        line_info = f"Line {err.line_number}" if err.line_number else "Global / Preamble"
        snippet = ""
        if err.line_number and hasattr(workspace, "read_lines"):
            start_l = max(1, err.line_number - 3)
            end_l = min(workspace.get_line_count(), err.line_number + 3)
            snippet = f"\nCode Context:\n```latex\n{workspace.read_lines(start_l, end_l)}\n```"

        diagnostic_blocks.append(
            f"ERROR AT {line_info} [{err.error_type}]:\n"
            f"Message: {err.message}\n"
            f"Required Fix: {err.suggested_action}"
            f"{snippet}"
        )

    diag_text = "\n\n".join(diagnostic_blocks) if diagnostic_blocks else raw_error[:600]

    auto_fix_summary = ""
    if fixes_applied:
        auto_fix_summary = "AUTOMATIC REPAIRS ALREADY APPLIED TO WORKSPACE BUFFER:\n" + "\n".join(f"- {f}" for f in fixes_applied) + "\n\n"

    return (
        "=========================================================\n"
        "COMPILATION ERROR SURGICAL REPAIR MANDATE (ASK AI TO FIX):\n"
        "The document failed compilation. Fix the exact lines below to restore zero errors.\n\n"
        f"{auto_fix_summary}"
        f"PARSED COMPILATION DIAGNOSTICS:\n{diag_text}\n\n"
        "SURGICAL FIX INSTRUCTIONS:\n"
        "1. Focus ONLY on the flagged lines. Do not alter unrelated sections of the document.\n"
        "2. If an environment is unclosed (e.g. \\begin{frame} ended by \\end{document}), close it with \\end{frame} before the next frame or \\end{document}.\n"
        "3. If TikZ gives 'Bad math environment delimiter', ensure \\usetikzlibrary{calc} is loaded and TikZ path statements end with a semicolon (;).\n"
        "4. Use `str_replace` to apply your targeted in-place fix.\n"
        "5. MANDATORY VERIFICATION: You MUST run `verify_compile` after applying your fix to verify compilation passes with 0 errors before concluding.\n"
        "6. If compilation passes, signal done=true with a concise explanation of what you repaired.\n"
        "========================================================="
    )
