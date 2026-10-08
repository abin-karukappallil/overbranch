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
   - Truncated booktabs rule (\\bottom -> \\bottomrule)
   - Bare '&' in frame titles (escaped to \\&)
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


def _structure_view(code: str) -> str:
    r"""
    Returns a same-length, same-line-count copy of ``code`` in which everything
    that must NOT be read as structure is blanked out: verbatim/lstlisting
    bodies, inline \verb, URL arguments, \newcommand / \newenvironment bodies,
    and % comments.

    The healer used to scan raw text while the validator scanned a masked view,
    so the two disagreed about what the document contains. The healer then
    "repaired" things that were never broken — a \begin{itemize} mentioned in a
    trailing comment, an \item inside a lstlisting, a \begin{list} inside a
    \newenvironment body — and emitted real syntax errors into the user's file.
    Because every write validates the whole buffer, that corruption also made
    every subsequent edit fail, which is what burned the step budget.

    Offsets, lines and columns are identical to the input, so a decision taken
    on the view can be applied to the original text directly.
    """
    try:
        from edit_validator import clean_latex_for_validation
        view = clean_latex_for_validation(code)
    except Exception as e:  # never let masking failure disable healing
        logger.warning(f"structure view unavailable, healing on raw text: {e}")
        return code
    # Defensive: the masking contract is length- and line-preserving. If that
    # ever breaks, fall back to the raw text rather than mis-mapping offsets.
    if len(view) != len(code) or view.count("\n") != code.count("\n"):
        logger.warning("structure view changed length; healing on raw text")
        return code
    return view


# Environments in which a bare \item is unambiguously illegal. A lonely \item is
# only wrapped when the innermost open environment is one of these (or nothing
# is open). Any *unknown* environment is assumed to be a list defined by a class
# or package — moderncv's rSubsection, res.cls's basedescript, custom cvitemize
# — where wrapping the items in \begin{itemize} silently re-renders the section.
ITEM_ILLEGAL_HOSTS = frozenset({
    "document", "frame", "frame*", "block", "alertblock", "exampleblock",
    "column", "columns", "center", "flushleft", "flushright", "minipage",
    "quote", "quotation", "verse", "abstract", "titlepage", "slide",
})

_RE_ITEM = re.compile(r"^\s*\\item\b")
_RE_BLOCK_BREAK = re.compile(
    r"^\s*\\(?:begin|end|section\*?|chapter\*?|part\*?|subsection\*?|subsubsection\*?)\b"
)
_RE_ENV_TAG_HEAL = re.compile(r"\\(begin|end)\s*\{\s*([A-Za-z@*][A-Za-z0-9@*]*)\s*\}")


def heal_lonely_items(code: str) -> Tuple[str, List[str]]:
    r"""
    Wraps \item statements that sit outside any list environment in
    \begin{itemize} ... \end{itemize}, preventing
    'LaTeX Error: Lonely \item--perhaps a missing list environment'.

    Only acts when the enclosing environment is one in which \item is certainly
    illegal (see ITEM_ILLEGAL_HOSTS) and only on structure that survives
    masking, so items inside listings, verbatim blocks, macro bodies or
    class-defined list environments are left alone.
    """
    if not code or r"\item" not in code:
        return code, []

    view = _structure_view(code)
    repairs: List[str] = []
    lines = code.splitlines(keepends=True)
    view_lines = view.splitlines(keepends=True)
    if len(view_lines) != len(lines):
        view_lines = lines
    out_lines: List[str] = []

    env_stack: List[str] = []
    list_depth = 0
    in_lonely_block = False

    for idx, (line, vline) in enumerate(zip(lines, view_lines), start=1):
        stripped = vline.strip()

        is_item_line = bool(_RE_ITEM.search(vline))
        innermost = env_stack[-1] if env_stack else None

        if is_item_line:
            if (
                list_depth == 0
                and not in_lonely_block
                and (innermost is None or innermost in ITEM_ILLEGAL_HOSTS)
            ):
                out_lines.append("\\begin{itemize}\n")
                in_lonely_block = True
                repairs.append(
                    f"Auto-wrapped lonely \\item starting at line {idx} in \\begin{{itemize}}."
                )
            out_lines.append(line)
        else:
            if in_lonely_block and (
                stripped == "" or _RE_BLOCK_BREAK.search(vline) or list_depth > 0
            ):
                out_lines.append("\\end{itemize}\n")
                in_lonely_block = False
                repairs.append(
                    f"Auto-closed lonely \\item block with \\end{{itemize}} before line {idx}."
                )
            out_lines.append(line)

        # Update environment state *after* the line is emitted, so an \item on
        # the same line as its \begin{itemize} is still seen as inside the list.
        for m in _RE_ENV_TAG_HEAL.finditer(vline):
            env = m.group(2)
            if m.group(1) == "begin":
                env_stack.append(env)
            elif env_stack and env in env_stack:
                while env_stack and env_stack.pop() != env:
                    pass
        list_depth = sum(
            1 for e in env_stack if e.rstrip("*") in ("itemize", "enumerate", "description")
        )

    if in_lonely_block:
        out_lines.append("\\end{itemize}\n")
        repairs.append(
            "Auto-closed trailing lonely \\item block with \\end{itemize} at document end."
        )

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

    block_re = re.compile(
        r"\\begin\{tikzpicture\}(?:\[[^\]]*\])?.*?(?:\\end\{tikzpicture\}|\\end\{frame\}|\\end\{document\})",
        re.DOTALL,
    )
    # A tikzpicture shown inside a listing or verbatim block is example text, not
    # code to repair; appending semicolons there changes what the user is showing.
    view = _structure_view(code)
    if len(view) != len(code):
        view = code

    out: List[str] = []
    cursor = 0
    for m in block_re.finditer(code):
        if view[m.start():m.start() + len("\\begin{tikzpicture}")] != "\\begin{tikzpicture}":
            continue
        out.append(code[cursor:m.start()])
        out.append(_fix_block(m))
        cursor = m.end()
    out.append(code[cursor:])
    return "".join(out), fixes


def balance_latex_environments(latex_code: str) -> Tuple[str, List[str]]:
    r"""
    Balances LaTeX environments (\begin{env} ... \end{env}) positionally:

    1. A still-open frame is closed before the next \begin{frame}.
    2. Inner environments are closed before the \end that closes an outer one.
    3. Everything still open is closed before \end{document} (or at end of file).
    4. An \end{env} with no matching \begin anywhere in scope is dropped.

    Tags are processed in the order they appear **within** a line, not ends
    before begins. Without that ordering,
    ``\date{\begin{flushleft}\today\end{flushleft}}`` had its \end{flushleft}
    deleted as an "orphan" (the \begin on the same line had not been pushed yet)
    and a replacement emitted before \end{document} — silently moving the rest
    of the document inside a flushleft group.

    Structure is read from the masked view (see ``_structure_view``), so
    environments mentioned in comments, listings, verbatim blocks or
    \newenvironment bodies are not treated as live.
    """
    if not latex_code or not latex_code.strip():
        return latex_code, []

    view = _structure_view(latex_code)
    repairs: List[str] = []
    lines = latex_code.splitlines(keepends=True)
    view_lines = view.splitlines(keepends=True)
    if len(view_lines) != len(lines):
        view_lines = lines

    out_lines: List[str] = []
    env_stack: List[Tuple[str, int]] = []

    def close_down_to(env: str, idx: int, reason: str) -> bool:
        """Pops inner environments above ``env`` (emitting closers), then ``env``."""
        if not any(e[0] == env for e in env_stack):
            return False
        while env_stack and env_stack[-1][0] != env:
            inner, inner_line = env_stack.pop()
            out_lines.append(f"\\end{{{inner}}}\n")
            repairs.append(
                f"Auto-closed inner environment \\begin{{{inner}}} from line {inner_line} {reason} at line {idx}."
            )
        if env_stack and env_stack[-1][0] == env:
            env_stack.pop()
        return True

    for idx, (line, vline) in enumerate(zip(lines, view_lines), start=1):
        tags = [
            (m.start(), m.end(), m.group(1), m.group(2), m.group(0))
            for m in _RE_ENV_TAG_HEAL.finditer(vline)
        ]
        if not tags:
            out_lines.append(line)
            continue

        drop_spans: List[Tuple[int, int]] = []
        pending_before: List[str] = []

        for start, end, kind, env, _raw in tags:
            if kind == "begin":
                if env == "frame" and any(e[0] == "frame" for e in env_stack):
                    # A new frame starts while the previous one is still open.
                    while env_stack:
                        prev, prev_line = env_stack.pop()
                        pending_before.append(f"\\end{{{prev}}}\n")
                        repairs.append(
                            f"Auto-closed unclosed \\begin{{{prev}}} from line {prev_line} before starting new frame at line {idx}."
                        )
                        if prev == "frame":
                            break
                env_stack.append((env, idx))
                continue

            # kind == "end"
            if env == "document":
                # Close everything still open above \end{document}.
                while env_stack and env_stack[-1][0] != "document":
                    inner, inner_line = env_stack.pop()
                    pending_before.append(f"\\end{{{inner}}}\n")
                    repairs.append(
                        f"Auto-closed unclosed \\begin{{{inner}}} from line {inner_line} before \\end{{document}} at line {idx}."
                    )
                if env_stack and env_stack[-1][0] == "document":
                    env_stack.pop()
                continue

            if any(e[0] == env for e in env_stack):
                # Inner closers belong on their own lines *before* this one.
                emitted_before = len(out_lines)
                close_down_to(env, idx, f"before \\end{{{env}}}")
                if len(out_lines) > emitted_before:
                    pending_before.extend(out_lines[emitted_before:])
                    del out_lines[emitted_before:]
            else:
                # Genuinely orphaned: nothing it could be closing.
                drop_spans.append((start, end))
                repairs.append(
                    f"Removed orphaned \\end{{{env}}} at line {idx} (no matching open environment)."
                )

        out_lines.extend(pending_before)

        if drop_spans:
            kept = []
            cursor = 0
            for a, b in drop_spans:
                kept.append(line[cursor:a])
                cursor = b
            kept.append(line[cursor:])
            line = "".join(kept)
            if not line.strip():
                continue

        out_lines.append(line)

    # Anything still open at end of file.
    if env_stack:
        for env_name, open_line in reversed(env_stack):
            if env_name == "document":
                continue
            inserted = False
            for j in range(len(out_lines) - 1, -1, -1):
                if _RE_END_DOCUMENT.search(out_lines[j]):
                    out_lines.insert(j, f"\\end{{{env_name}}}\n")
                    repairs.append(
                        f"Auto-closed trailing unclosed \\begin{{{env_name}}} from line {open_line} before \\end{{document}}."
                    )
                    inserted = True
                    break
            if not inserted:
                out_lines.append(f"\\end{{{env_name}}}\n")
                repairs.append(
                    f"Auto-closed trailing unclosed \\begin{{{env_name}}} from line {open_line} at document end."
                )

    return "".join(out_lines), repairs


_RE_BOTTOM_TRUNC = re.compile(r"\\bottom\b")
_RE_BOOKTABS_INUSE = re.compile(r"\\(?:top|mid|bottom)rule\b|\\usepackage(?:\[[^\]]*\])?\{booktabs\}")


def fix_booktabs_truncations(code: str) -> Tuple[str, List[str]]:
    r"""
    Repairs a truncated booktabs rule — a bare ``\bottom`` that should be
    ``\bottomrule`` (a recurring LLM output glitch, e.g. ``... \\ \bottom%``).

    ``\bottom`` has no standard meaning, so mapping it is safe; ``\top`` and
    ``\mid`` are deliberately **not** touched because they are valid math
    commands (``\top`` = ⊤, ``\mid`` = the ``∣`` relation). The fix only runs
    when booktabs rules are actually in use, and skips any ``\bottom`` that the
    masked view shows is inside a listing / verbatim block / comment.
    """
    if r"\bottom" not in code or not _RE_BOOKTABS_INUSE.search(code):
        return code, []

    view = _structure_view(code)
    if len(view) != len(code):
        view = code

    out: List[str] = []
    cursor = 0
    count = 0
    for m in _RE_BOTTOM_TRUNC.finditer(code):
        # Only rewrite real code, not an example \bottom inside a listing/comment.
        if view[m.start():m.end()] != code[m.start():m.end()]:
            continue
        out.append(code[cursor:m.start()])
        out.append(r"\bottomrule")
        cursor = m.end()
        count += 1

    if not count:
        return code, []
    out.append(code[cursor:])
    return "".join(out), [f"Corrected {count} truncated \\bottom -> \\bottomrule (booktabs)."]


_RE_FRAME_TITLE_OPEN = re.compile(r"\\begin\s*\{frame\}\s*(?:<[^>]*>)?\s*(?:\[[^\]]*\]\s*)*\{")
_RE_FRAMETITLE_CMD_OPEN = re.compile(r"\\frametitle\s*(?:<[^>]*>)?\s*\{")
_RE_BARE_AMP = re.compile(r"(?<!\\)&")


def _match_brace(text: str, open_pos: int) -> Optional[int]:
    """Index of the ``}`` that closes the ``{`` at ``open_pos`` (``\\{`` escapes skipped)."""
    depth = 0
    i = open_pos
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def fix_ampersand_in_frame_titles(code: str) -> Tuple[str, List[str]]:
    r"""
    Escapes a bare ``&`` inside a ``\begin{frame}{...}`` / ``\frametitle{...}``
    title to ``\&``. A bare ``&`` there is an alignment-tab character and raises
    'Misplaced alignment tab character &', which — in a custom frametitle
    template that typesets the title inside a TikZ node — can take down the
    whole title. ``&`` inside the frame *body* (real tabulars) is untouched.
    """
    if "&" not in code or (r"\begin{frame}" not in code and r"\frametitle" not in code):
        return code, []

    view = _structure_view(code)
    if len(view) != len(code):
        view = code

    openers: List[int] = []
    for rx in (_RE_FRAME_TITLE_OPEN, _RE_FRAMETITLE_CMD_OPEN):
        for m in rx.finditer(code):
            # Ignore a \begin{frame} shown as example text in a listing/verbatim.
            if view[m.start():m.end()] != code[m.start():m.end()]:
                continue
            openers.append(m.end() - 1)  # the title's opening brace

    if not openers:
        return code, []

    # Rightmost-first so edits never shift the offsets still to be processed.
    new_code = code
    count = 0
    for open_pos in sorted(set(openers), reverse=True):
        close = _match_brace(new_code, open_pos)
        if close is None:
            continue
        inner = new_code[open_pos + 1:close]
        if "&" not in inner:
            continue
        fixed_inner, n_sub = _RE_BARE_AMP.subn(r"\\&", inner)
        if n_sub:
            new_code = new_code[:open_pos + 1] + fixed_inner + new_code[close:]
            count += n_sub

    if not count:
        return code, []
    return new_code, [f"Escaped {count} bare '&' in frame title(s) to '\\&'."]


def _apply_heal_passes(code: str, error_log: str = "") -> Tuple[str, List[str]]:
    r"""
    Applies deterministic automatic fixes to LaTeX code for common syntax and compilation issues:
    1. Ensures \\begin{document} and \\end{document} structural integrity.
    2. Repairs mangled newline spacing (e.g. \\[0.3em] written as \\[0.3em]).
    3. Hoists any \\usepackage or \\usetikzlibrary out of document body into preamble.
    4. Balances all unclosed environments (frames, itemize, tikzpicture, columns) and removes orphaned \\end{...}.
    5. Auto-wraps lonely \\item statements in \\begin{itemize} ... \\end{itemize}.
    6. Injects \\usepackage{tikz} and \\usetikzlibrary{calc,positioning,arrows.meta} whenever TikZ is used.
    7. Fixes missing semicolons on TikZ path commands without breaking multi-line statements.
    7b. Corrects a truncated booktabs rule (\\bottom -> \\bottomrule) when booktabs is in use.
    7c. Escapes a bare '&' inside a frame title (\\begin{frame}{...} / \\frametitle{...}).
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
        # Match against the masked view so a \usepackage shown inside a
        # lstlisting / verbatim block (documentation, tutorials) is not torn out
        # of the example and pasted into the preamble.
        body_view = _structure_view(code)[doc_pos:]
        if len(body_view) != len(body):
            body_view = body
        found_in_body = [
            pm for pm in pkg_pattern.finditer(body)
            if body_view[pm.start(1):pm.end(1)] == pm.group(1)
        ]
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

    # 7b. Truncated booktabs rule (\bottom -> \bottomrule)
    code, bottom_fixes = fix_booktabs_truncations(code)
    fixes_applied.extend(bottom_fixes)

    # 7c. Bare '&' in frame titles (\begin{frame}{a & b} -> a \& b)
    code, amp_fixes = fix_ampersand_in_frame_titles(code)
    fixes_applied.extend(amp_fixes)

    # 8. Injected Undefined Colors (Regalia / Beamer)
    needed_colors = []
    color_view = _structure_view(code)
    for c_name in ("navy", "gold", "cream", "ink", "muted"):
        # The bare word must appear as a *colour argument*, not as prose. "The
        # gold standard" and "think in ink" are not colour references, and
        # injecting a palette for them rewrote preambles that never asked for one.
        used_as_color = re.search(
            rf"(?:\\(?:color|textcolor|colorbox|fcolorbox|pagecolor|rowcolor|cellcolor|columncolor|arrayrulecolor)"
            rf"\s*\{{\s*{c_name}\s*[}}!]"
            rf"|(?:fg|bg|fill|draw|text|color)\s*=\s*{c_name}\b"
            rf"|\[\s*{c_name}\s*[\]!,]"
            rf"|\\colorlet\s*\{{[^}}]*\}}\s*\{{\s*{c_name}\b)",
            color_view,
        )
        if used_as_color and not re.search(rf"\\definecolor\s*\*?\s*\{{\s*{c_name}\s*\}}", color_view):
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


def auto_heal_latex_code(code: str, error_log: str = "") -> Tuple[str, List[str]]:
    r"""
    Deterministically repairs common LaTeX syntax faults — and never makes the
    document worse than it found it.

    This runs on the whole buffer on **every** agent write, so a healing pass
    that introduces a defect does not just corrupt one edit: the next write
    fails pre-commit validation against the already-corrupted buffer, the agent
    retries, and the run burns its entire step budget before discarding
    everything. The repairs are therefore applied speculatively and kept only if
    the structural error count does not rise.

    Returns ``(healed_code, fixes_applied)``; on a regression the original code
    is returned with an empty fix list.
    """
    if not code or not code.strip():
        return code, []

    try:
        healed, fixes = _apply_heal_passes(code, error_log)
    except Exception as e:
        logger.warning(f"auto_heal_latex_code failed, returning input unchanged: {e}")
        return code, []

    if healed == code:
        return code, fixes

    try:
        from edit_validator import validate_latex_pre_commit
        ok_after, errors_after = validate_latex_pre_commit(healed)
        if not ok_after:
            _, errors_before = validate_latex_pre_commit(code)
            if len(errors_after) > len(errors_before):
                logger.warning(
                    "auto_heal_latex_code regressed the document "
                    f"({len(errors_before)} -> {len(errors_after)} structural errors); "
                    f"discarding repairs: {fixes[:3]}"
                )
                return code, []
    except Exception as e:
        logger.warning(f"post-heal validation unavailable: {e}")

    return healed, fixes


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
