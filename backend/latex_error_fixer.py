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
def _comment_start(line: str) -> int:
    r"""
    Index of the first ``%`` that starts a comment (preceded by an even number of
    backslashes), or -1. ``\%`` is a literal percent sign: treating it as a comment
    turned ``{Accuracy 97\%};`` into ``{Accuracy 97\;%};`` — the closing brace and
    the next TikZ statement commented out.
    """
    i = 0
    while True:
        j = line.find("%", i)
        if j == -1:
            return -1
        k, slashes = j - 1, 0
        while k >= 0 and line[k] == "\\":
            slashes += 1
            k -= 1
        if slashes % 2 == 0:
            return j
        i = j + 1


def _strip_comment(line: str) -> str:
    k = _comment_start(line)
    return line if k < 0 else line[:k]


def _brace_delta(text: str) -> int:
    t = re.sub(r"\\[{}\\]", "", text)
    return t.count("{") - t.count("}")
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
    # File TeX reported the error in ("main.tex", "chapters/intro.tex", "beamerthemex.sty");
    # None when the log did not say. A line number only refers to the user's source
    # when this is a .tex file.
    file: Optional[str] = None


# Standard Regalia / Beamer color definitions to inject if undefined
REGALIA_COLOR_DEFS = (
    "\\definecolor{navy}{HTML}{0B2545}\n"
    "\\definecolor{navylight}{HTML}{13315C}\n"
    "\\definecolor{gold}{HTML}{C9A24B}\n"
    "\\definecolor{cream}{HTML}{F7F4EC}\n"
    "\\definecolor{ink}{HTML}{1D1D1D}\n"
    "\\definecolor{muted}{HTML}{5C6270}\n"
)


_RE_LOG_FILE_LINE = re.compile(
    r"^((?:\./)?[^\s:()]*?[\w\-]+\.(tex|sty|cls|bbl|ltx|def|cfg)):(\d+):\s*(.*)$", re.IGNORECASE)
_RE_LOG_L_NUM = re.compile(r"^l\.(\d+)\s?(.*)$")
_RE_LOG_UNCLOSED_ENV = re.compile(
    r"\\begin\{([^}]+)\}\s+on\s+input\s+line\s+(\d+)\s+ended\s+by\s+\\end\{([^}]+)\}", re.IGNORECASE)
# Consequences of an earlier error, not errors of their own.
_LOG_CONSEQUENCES = ("emergency stop", "==> fatal error occurred", "fatal error occurred, no output")


def _classify_tex_error(msg: str) -> Tuple[str, str]:
    """(error_type, suggested_action) for a TeX error message."""
    low = msg.lower()
    if "bad math environment delimiter" in low:
        return "BAD_MATH_DELIMITER", (
            "TikZ coordinate arithmetic $(...)$ requires \\usetikzlibrary{calc} in the preamble. "
            "Ensure math mode delimiters ($, $$, \\(, \\)) are balanced.")
    if "giving up on this path" in low or "did you forget a sem" in low:
        return "TIKZ_SYNTAX_ERROR", (
            "Ensure all TikZ path commands (\\fill, \\draw, \\node, \\path) inside \\begin{tikzpicture} "
            "end with a semicolon (;).")
    if "undefined control sequence" in low:
        return "UNDEFINED_MACRO", "Check for misspelled macro name or missing package in preamble."
    if "environment" in low and "undefined" in low:
        return "UNDEFINED_ENVIRONMENT", "Load the package that defines this environment, or use a standard one."
    if "undefined color" in low:
        return "UNDEFINED_COLOR", (
            "Define the color in preamble using \\definecolor{<name>}{HTML}{<hex>} or "
            "\\definecolor{<name>}{RGB}{...}.")
    if "missing $ inserted" in low:
        return "MISSING_DOLLAR", "Escape _ and ^ in text as \\_ and \\^{}, or put math in $...$."
    if "misplaced alignment tab" in low:
        return "MISPLACED_AMPERSAND", "Escape & in text as \\&; & only separates columns inside tabular/align."
    if "missing } inserted" in low or "extra }" in low or "missing \\endgroup" in low:
        return "SYNTAX_ERROR", "Check for unbalanced curly braces { } or missing closing delimiter."
    if "runaway argument" in low:
        return "RUNAWAY_ARGUMENT", "Check for unclosed curly braces { or unclosed macro argument."
    if "file" in low and "not found" in low:
        return "MISSING_FILE", "Check that the referenced graphic or input file exists in the project assets."
    if "package" in low and "error" in low:
        return "PACKAGE_ERROR", "Check package requirements, options, or conflicting definitions."
    if "something's wrong" in low or "missing \\item" in low or "lonely \\item" in low:
        return "LONELY_ITEM", "Ensure all \\item commands are enclosed inside \\begin{itemize} or \\begin{enumerate}."
    if "emergency stop" in low:
        return "COMPILER_ERROR", "Fatal compilation stop; check previous error lines."
    return "GENERAL_LATEX_ERROR", ""


def _context_after(lines: List[str], idx: int) -> Tuple[Optional[int], str]:
    """TeX's ``l.N <code>`` context line following the error at ``lines[idx]``."""
    for nxt in lines[idx + 1:idx + 9]:
        m = _RE_LOG_L_NUM.match(nxt.strip())
        if m:
            return int(m.group(1)), m.group(2).strip()
        if nxt.strip().startswith("!") or _RE_LOG_FILE_LINE.match(nxt.strip()):
            break  # the next error: this one has no context line
    return None, ""


def parse_compilation_errors(error_text: str) -> List[ParsedLatexError]:
    """
    Parses a raw LaTeX compilation error log or user-submitted error report into
    structured ParsedLatexError objects with line numbers and targeted advice.

    Understands both log shapes: ``./main.tex:66: <message>`` (-file-line-error,
    used by every compile OverBranch runs) and ``! <message>`` followed by TeX's
    ``l.66 <code>`` context (logs pasted by users, latexmk). The file is kept, so
    an error in ``chapters/intro.tex`` is not mistaken for line 66 of main.tex;
    errors reported against a ``.sty`` / ``.cls`` carry no source line.
    """
    if not error_text or not error_text.strip():
        return []

    errors: List[ParsedLatexError] = []
    lines = error_text.splitlines()

    for idx, line in enumerate(lines):
        line_str = line.strip()
        if not line_str:
            continue

        # 1. Check for unclosed environment mismatch (e.g. \begin{frame} on line 160 ended by \end{document})
        m_unclosed = _RE_LOG_UNCLOSED_ENV.search(line_str)
        if m_unclosed:
            opened_env = m_unclosed.group(1)
            line_no = int(m_unclosed.group(2))
            closed_env = m_unclosed.group(3)
            m_fl = _RE_LOG_FILE_LINE.match(line_str)
            errors.append(ParsedLatexError(
                line_number=line_no,
                error_type="UNCLOSED_ENVIRONMENT",
                message=f"\\begin{{{opened_env}}} starting on line {line_no} was ended by \\end{{{closed_env}}} without being closed.",
                snippet=line_str,
                suggested_action=f"Insert \\end{{{opened_env}}} before \\end{{{closed_env}}}.",
                file=m_fl.group(1)[2:] if m_fl and m_fl.group(1).startswith("./") else (m_fl.group(1) if m_fl else None),
            ))
            continue

        # 2. ./main.tex:66: <error message>   (-file-line-error)
        m_file_line = _RE_LOG_FILE_LINE.match(line_str)
        if m_file_line:
            fname = m_file_line.group(1)
            fname = fname[2:] if fname.startswith("./") else fname
            is_source = m_file_line.group(2).lower() in ("tex", "ltx")
            msg = m_file_line.group(4).strip()
            if any(c in msg.lower() for c in _LOG_CONSEQUENCES):
                continue
            err_type, action = _classify_tex_error(msg)
            _ctx_line, ctx = _context_after(lines, idx)
            errors.append(ParsedLatexError(
                line_number=int(m_file_line.group(3)) if is_source else None,
                error_type=err_type,
                message=msg if is_source else f"{fname}:{m_file_line.group(3)}: {msg}",
                snippet=ctx or line_str,
                suggested_action=action,
                file=fname,
            ))
            continue

        # 3. ! <error message>  +  l.<line> <context>   (classic TeX log)
        if line_str.startswith("!"):
            msg = line_str.lstrip("!").strip()
            if not msg or any(c in msg.lower() for c in _LOG_CONSEQUENCES):
                continue
            err_type, action = _classify_tex_error(msg)
            ctx_line, ctx = _context_after(lines, idx)
            errors.append(ParsedLatexError(
                line_number=ctx_line,
                error_type=err_type,
                message=msg,
                snippet=ctx or line_str,
                suggested_action=action,
            ))

    # Deduplicate errors by (file, line_number, error_type)
    seen = set()
    deduped: List[ParsedLatexError] = []
    for err in errors:
        key = (err.file, err.line_number, err.error_type, err.message[:40])
        if key not in seen:
            seen.add(key)
            deduped.append(err)

    if not deduped and error_text.strip():
        # Fallback when TeX failed but specific error patterns did not match
        clean_lines = [ln.strip() for ln in error_text.splitlines() if ln.strip()]
        if clean_lines:
            err_line = next(
                (ln for ln in clean_lines if ln.startswith("!") or "fatal error" in ln.lower() or "error:" in ln.lower()),
                clean_lines[0] if any("error" in ln.lower() for ln in clean_lines) else clean_lines[-1]
            )
            deduped.append(ParsedLatexError(
                line_number=None,
                error_type="COMPILER_ERROR",
                message=err_line[:200],
                snippet=err_line[:120],
                suggested_action="Review compiler diagnostics and LaTeX syntax",
            ))

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
        depth = 0  # brace depth inside the current statement (a \matrix body, a multi-line node text)

        for idx, line in enumerate(lines):
            stripped = line.strip()
            clean = _strip_comment(stripped).rstrip()

            if not clean:
                new_lines.append(line)
                continue

            is_new = bool(stmt_start.match(clean))
            is_close = bool(end_env.search(clean))

            if in_stmt and (is_new or is_close):
                if depth <= 0:
                    for j in range(len(new_lines) - 1, -1, -1):
                        prev = new_lines[j]
                        prev_clean = _strip_comment(prev.strip()).rstrip()
                        if prev_clean:
                            if not prev_clean.endswith(";"):
                                content = prev.rstrip("\r\n")
                                eol = prev[len(content):] or "\n"
                                k = _comment_start(content)
                                head = (content if k < 0 else content[:k]).rstrip()
                                # The comment (if any) and the line's own newline are kept.
                                new_lines[j] = head + ";" + content[len(head):] + eol
                                fixes.append("Added missing semicolon (;) to TikZ path statement.")
                            break
                    in_stmt = False
                elif is_close:
                    in_stmt = False  # an open group at \end: unclear, leave it alone
                # else: a statement inside an open group (\matrix cells) — not the end of the outer one

            if is_new and not in_stmt:
                in_stmt = True
                depth = 0

            if in_stmt:
                depth += _brace_delta(clean)
                if clean.endswith(";") and depth <= 0:
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
    # Environments opened somewhere the masked view hides — typically a macro body,
    # \newcommand{\twocol}{\begin{columns}} — whose \end{...} then looks orphaned in
    # the view. That \end is real; deleting it broke documents that compiled.
    raw_begins: Dict[str, int] = {}
    for m in _RE_ENV_TAG_HEAL.finditer(latex_code):
        if m.group(1) == "begin":
            raw_begins[m.group(2)] = raw_begins.get(m.group(2), 0) + 1
    for m in _RE_ENV_TAG_HEAL.finditer(view):
        if m.group(1) == "begin":
            raw_begins[m.group(2)] = raw_begins.get(m.group(2), 0) - 1
    hidden_begins = {env for env, n in raw_begins.items() if n > 0}

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
            elif env in hidden_begins:
                continue  # opened by a macro (or in text the view hides): not ours to remove
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


# Commands whose (first mandatory) argument is a label, key, path or URL: `_`, `^`
# and `&` there are literal and must never be escaped.
_PROTECTED_ARG_CMDS = frozenset({
    "label", "ref", "eqref", "autoref", "pageref", "cref", "Cref", "nameref", "cite", "citep",
    "citet", "citealp", "nocite", "url", "href", "hyperref", "includegraphics", "input", "include",
    "bibliography", "bibliographystyle", "usepackage", "RequirePackage", "documentclass",
    "lstinputlisting", "path", "verb", "definecolor", "colorlet", "addbibresource",
})
_MATH_ENVS = frozenset({
    "equation", "equation*", "align", "align*", "alignat", "alignat*", "gather", "gather*",
    "multline", "multline*", "eqnarray", "eqnarray*", "math", "displaymath", "flalign", "flalign*",
})
_ALIGNMENT_ENVS = _MATH_ENVS | frozenset({
    "tabular", "tabular*", "tabularx", "tabulary", "longtable", "array", "aligned", "split", "cases",
    "matrix", "pmatrix", "bmatrix", "Bmatrix", "vmatrix", "Vmatrix", "smallmatrix", "tblr",
    "NiceTabular", "supertabular", "xltabular",
})


def _enclosing_envs(view_lines: List[str], line_no: int) -> List[str]:
    """Environments open at the start of 1-based ``line_no`` (masked view)."""
    stack: List[str] = []
    for vline in view_lines[:max(0, line_no - 1)]:
        for m in _RE_ENV_TAG_HEAL.finditer(vline):
            env = m.group(2)
            if m.group(1) == "begin":
                stack.append(env)
            elif env in stack:
                while stack and stack.pop() != env:
                    pass
    return stack


def _escape_in_text(line: str, targets: str) -> Tuple[str, int]:
    """
    Escapes ``targets`` characters that sit in text on ``line``: not in $…$ / \\(…\\),
    not after an unescaped %, not inside a protected argument (\\label{a_b}).
    Returns (line, number escaped).
    """
    out: List[str] = []
    i, n, in_math, count = 0, len(line), False, 0
    while i < n:
        ch = line[i]
        if ch == "\\":
            if i + 1 < n and not line[i + 1].isalpha():
                sym = line[i + 1]
                if sym in "([":
                    in_math = True
                elif sym in ")]":
                    in_math = False
                out.append(line[i:i + 2])
                i += 2
                continue
            m = re.match(r"\\[A-Za-z]+\*?", line[i:])
            if not m:
                out.append(ch)
                i += 1
                continue
            out.append(m.group(0))
            i += len(m.group(0))
            if m.group(0)[1:].rstrip("*") in _PROTECTED_ARG_CMDS:
                j = i
                while j < n and line[j] == " ":
                    j += 1
                while j < n and line[j] == "[":
                    k = line.find("]", j)
                    if k == -1:
                        break
                    j = k + 1
                if j < n and line[j] == "{":
                    k = _match_brace(line, j)
                    if k is not None:
                        out.append(line[i:k + 1])
                        i = k + 1
            continue
        if ch == "%":
            out.append(line[i:])
            break
        if ch == "$":
            in_math = not in_math
            out.append(ch)
            i += 1
            continue
        if ch in targets and not in_math:
            out.append("\\" + ch + ("{}" if ch == "^" else ""))
            count += 1
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out), count


def sanitize_edit_latex(text: str) -> str:
    """
    Normalizes and strips accidental wrappers and fences from LLM-generated LaTeX edit content:
    - Strips markdown code blocks: ```latex ... ``` or ``` ... ```
    - Strips lines containing isolated ``` or ```latex
    - Normalizes CRLF -> LF
    """
    if not text:
        return text
    s = text.replace("\r\n", "\n")
    trimmed = s.strip()

    # If the whole content is wrapped in a markdown fence: ```latex\n...\n```
    if trimmed.startswith("```"):
        m = re.match(r"^```(?:latex|tex|text)?\s*\n?(.*?)\n?```$", trimmed, re.DOTALL)
        if m:
            s = m.group(1)
        else:
            lines = s.split("\n")
            filtered = [
                l for l in lines
                if not re.match(r"^\s*```(?:latex|tex|text)?\s*$", l)
            ]
            s = "\n".join(filtered)
    elif "```" in s:
        lines = s.split("\n")
        filtered = [
            l for l in lines
            if not re.match(r"^\s*```(?:latex|tex|text)?\s*$", l)
        ]
        s = "\n".join(filtered)

    return s


def repair_from_compile_errors(code: str, errors: List[Dict[str, Any]],
                               allowed_lines: Optional[Set[int]] = None) -> Tuple[str, List[str]]:
    r"""
    Deterministic fixes driven by TeX's own errors:
    * ``Missing $ inserted`` — bare ``_`` / ``^`` in text are escaped.
    * ``Misplaced alignment tab character &`` — bare ``&`` outside tabular/align becomes ``\&``.
    * ``Undefined control sequence`` / ``undefined environment`` — missing standard packages
      (amsmath, booktabs, graphicx, amssymb, tikz) are injected into the preamble.
    * ``did you forget a semicolon`` / TikZ error — missing semicolons added.
    * ``Missing } inserted`` / ``Extra }`` — brace imbalances repaired on affected lines.
    * ``Unclosed environment`` — inserts matching closing tag before enclosing environment.
    * ``Lonely \item`` — wrapped in itemize environment.

    The caller recompiles and keeps the result only if there are fewer errors.
    Returns ``(code, fixes)``.
    """
    if not code or not errors:
        return code, []
    lines = code.split("\n")
    view = _structure_view(code)
    view_lines = view.split("\n") if len(view) == len(code) else lines
    fixes: List[str] = []
    done: Set[Tuple[int, str]] = set()

    for err in errors:
        ln = err.get("line")
        msg = str(err.get("error", "")).lower()

        # 1. Missing $ inserted (bare _ / ^ in text) & misplaced alignment tab
        if isinstance(ln, int) and (1 <= ln <= len(lines)):
            if allowed_lines is None or ln in allowed_lines:
                if "missing $ inserted" in msg:
                    kind, targets = "dollar", "_^"
                elif "misplaced alignment tab" in msg:
                    kind, targets = "amp", "&"
                else:
                    kind, targets = None, None

                if kind is not None and (ln, kind) not in done:
                    done.add((ln, kind))
                    envs = set(_enclosing_envs(view_lines, ln))
                    if not (kind == "dollar" and envs & _MATH_ENVS) and not (kind == "amp" and envs & _ALIGNMENT_ENVS):
                        new_line, count = _escape_in_text(lines[ln - 1], targets)
                        if count:
                            lines[ln - 1] = new_line
                            what = "'_'/'^'" if kind == "dollar" else "'&'"
                            fixes.append(f"Escaped {count} bare {what} in text on line {ln}.")

                # 2. Missing brace or Extra brace on affected line
                if ("missing }" in msg or "missing \\endgroup" in msg or "runaway argument" in msg) and (ln, "brace_add") not in done:
                    done.add((ln, "brace_add"))
                    delta = _brace_delta(lines[ln - 1])
                    if delta > 0:
                        lines[ln - 1] += "}" * delta
                        fixes.append(f"Appended {delta} missing '}}' on line {ln}.")
                elif "extra }" in msg and (ln, "brace_sub") not in done:
                    done.add((ln, "brace_sub"))
                    delta = _brace_delta(lines[ln - 1])
                    if delta < 0 and "}" in lines[ln - 1]:
                        pos = lines[ln - 1].rfind("}")
                        lines[ln - 1] = lines[ln - 1][:pos] + lines[ln - 1][pos + 1:]
                        fixes.append(f"Removed extra '}}' on line {ln}.")

                # 3. Lonely \item on affected line
                if ("lonely \\item" in msg or "something's wrong" in msg or "missing \\item" in msg) and (ln, "lonely_item") not in done:
                    done.add((ln, "lonely_item"))
                    if r"\item" in lines[ln - 1]:
                        lines[ln - 1] = f"\\begin{{itemize}}\n{lines[ln - 1]}\n\\end{{itemize}}"
                        fixes.append(f"Enclosed lonely \\item on line {ln} in \\begin{{itemize}} ... \\end{{itemize}}.")

        # 4. Unclosed environment ending with mismatch
        m_unclosed = _RE_LOG_UNCLOSED_ENV.search(str(err.get("error", ""))) or _RE_LOG_UNCLOSED_ENV.search(str(err.get("snippet", "")))
        if m_unclosed and ("unclosed", m_unclosed.group(1)) not in done:
            opened_env = m_unclosed.group(1)
            closed_env = m_unclosed.group(3)
            done.add(("unclosed", opened_env))
            cur_code = "\n".join(lines)
            target = f"\\end{{{closed_env}}}"
            idx = cur_code.find(target)
            if idx != -1:
                cur_code = cur_code[:idx] + f"\\end{{{opened_env}}}\n" + cur_code[idx:]
                lines = cur_code.split("\n")
                fixes.append(f"Inserted \\end{{{opened_env}}} before \\end{{{closed_env}}}.")

    # 5. Missing package / undefined control sequence: auto-inject required packages
    has_undefined = any(
        "undefined control sequence" in str(e.get("error", "")).lower()
        or "environment" in str(e.get("error", "")).lower() and "undefined" in str(e.get("error", "")).lower()
        or e.get("type") in ("UNDEFINED_MACRO", "UNDEFINED_ENVIRONMENT")
        for e in errors
    )
    if has_undefined:
        cur_code = "\n".join(lines)
        patched_code, pkg_fixes = ensure_required_packages(cur_code)
        if pkg_fixes:
            lines = patched_code.split("\n")
            fixes.extend(pkg_fixes)

    # 6. TikZ syntax error: fix missing semicolons
    has_tikz = any(
        "did you forget a sem" in str(e.get("error", "")).lower()
        or "giving up on this path" in str(e.get("error", "")).lower()
        or e.get("type") == "TIKZ_SYNTAX_ERROR"
        for e in errors
    )
    if has_tikz:
        cur_code = "\n".join(lines)
        patched_code, tikz_fixes = fix_tikz_semicolons(cur_code)
        if tikz_fixes:
            lines = patched_code.split("\n")
            fixes.extend(tikz_fixes)

    # 7. Bad math environment delimiter in TikZ coordinate calculations
    has_calc = any(
        "bad math environment delimiter" in str(e.get("error", "")).lower()
        or e.get("type") == "BAD_MATH_DELIMITER"
        for e in errors
    )
    if has_calc:
        cur_code = "\n".join(lines)
        patched_code, heal_fixes = auto_heal_latex_code(cur_code)
        if heal_fixes:
            lines = patched_code.split("\n")
            fixes.extend(heal_fixes)

    return ("\n".join(lines), fixes) if fixes else (code, [])


_RE_PKG_LOAD = re.compile(r"\\(?:usepackage|RequirePackage)\s*(?:\[([^\]]*)\])?\s*\{([^}]*)\}")
_RE_DOCCLASS = re.compile(r"\\documentclass\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
_TIKZ_LOADERS = frozenset({"tikz", "pgfplots", "circuitikz", "tikz-cd", "smartdiagram"})


def _loaded_packages(view: str) -> Dict[str, str]:
    """package -> its options, from every \\usepackage / \\RequirePackage (lists included)."""
    out: Dict[str, str] = {}
    for m in _RE_PKG_LOAD.finditer(view):
        for name in m.group(2).split(","):
            name = name.strip()
            if name:
                out[name] = ",".join(filter(None, [out.get(name, ""), (m.group(1) or "").strip()]))
    return out


def _preamble_insertion_point(view: str, use_pos: int) -> Optional[int]:
    """
    Where a \\usepackage for something first used at ``use_pos`` goes: before the
    line of that first use when it is in the preamble (a later \\usepackage would be
    too late), otherwise at the end of the preamble, i.e. after the document's own
    packages — inserting right after \\documentclass made tikz load xcolor before the
    document's \\usepackage[table]{xcolor} ("Option clash for package xcolor").
    """
    m_begin = _RE_BEGIN_DOCUMENT.search(view)
    m_cls = _RE_DOCCLASS.search(view)
    if not m_begin or not m_cls or use_pos <= m_cls.end():
        return None
    anchor = m_begin.start() if use_pos >= m_begin.start() else use_pos
    return view.rfind("\n", 0, anchor) + 1


_RE_DEFINED_MACRO = re.compile(
    r"\\(?:newcommand|renewcommand|providecommand|DeclareRobustCommand|NewDocumentCommand|"
    r"DeclareMathOperator|def|let|gdef|edef)\*?\s*\{?\s*\\([A-Za-z]+)")
_RE_DEFINED_ENV = re.compile(r"\\(?:newenvironment|NewDocumentEnvironment|newtheorem)\*?\s*\{([A-Za-z*]+)\}")

# (package, use pattern, packages/classes that already provide it, line to insert or None)
_PACKAGE_NEEDS: Tuple[Tuple[str, "re.Pattern", Tuple[str, ...], Optional[str]], ...] = tuple(
    (pkg, re.compile(pat), alts, line) for pkg, pat, alts, line in (
        ("booktabs", r"\\(?:toprule|midrule|bottomrule|cmidrule|addlinespace)(?![A-Za-z])", (), None),
        ("amsmath", r"\\begin\s*\{(?:align|gather|multline|alignat|flalign|split|aligned|gathered|cases|"
                    r"pmatrix|bmatrix|Bmatrix|vmatrix|Vmatrix|smallmatrix)\*?\}|"
                    r"\\(?:text|dfrac|tfrac|binom|dbinom|tbinom|eqref|operatorname|boxed|intertext)(?![A-Za-z])",
         ("mathtools", "amstext"), None),
        ("amsfonts", r"\\(?:mathbb|mathfrak)(?![A-Za-z])", ("amssymb",), None),
        ("amssymb", r"\\(?:checkmark|therefore|because|leqslant|geqslant|varnothing|blacksquare|square|"
                    r"lesssim|gtrsim|nexists|complement|triangleq|lozenge|blacktriangleright|"
                    r"blacktriangleleft|boxtimes|boxplus)(?![A-Za-z])", (), None),
        ("xcolor", r"\\(?:textcolor|colorbox|fcolorbox|definecolor|colorlet|pagecolor)(?![A-Za-z])|"
                   r"\\color\s*[{\[]", ("color", "colortbl") + tuple(_TIKZ_LOADERS) + ("pgf",), None),
        ("colortbl", r"\\(?:rowcolor|cellcolor|columncolor|arrayrulecolor)(?![A-Za-z])", (), None),
        ("graphicx", r"\\(?:includegraphics|rotatebox|scalebox|resizebox|reflectbox)(?![A-Za-z])",
         ("graphics",), None),
        ("hyperref", r"\\(?:href|hypersetup|hyperlink|hypertarget|autoref)(?![A-Za-z])", (), None),
        ("url", r"\\url(?![A-Za-z])", ("hyperref", "xurl"), None),
        ("tabularx", r"\\begin\s*\{tabularx\}", ("xltabular",), None),
        ("multirow", r"\\multirow(?![A-Za-z])", (), None),
        ("listings", r"\\begin\s*\{lstlisting\}|\\(?:lstinputlisting|lstset|lstdefinestyle|lstinline)(?![A-Za-z])",
         (), None),
        ("siunitx", r"\\(?:SI|si|qty|unit|num)(?![A-Za-z])\s*[{\[]", (), None),
        ("subcaption", r"\\begin\s*\{subfigure\}|\\(?:subcaption|subcaptionbox)(?![A-Za-z])", (), None),
        ("caption", r"\\(?:captionsetup|captionof)(?![A-Za-z])", ("subcaption", "capt-of"), None),
        ("ulem", r"\\(?:sout|uline|uuline|uwave|xout)(?![A-Za-z])", (), "\\usepackage[normalem]{ulem}"),
        ("soul", r"\\hl(?![A-Za-z])\s*\{", ("soulutf8",), None),
        ("mathtools", r"\\(?:coloneqq|eqqcolon|mathclap|mathllap|mathrlap|DeclarePairedDelimiter)(?![A-Za-z])",
         (), None),
        ("bm", r"\\bm(?![A-Za-z])\s*\{", (), None),
        ("cancel", r"\\(?:cancel|bcancel|xcancel|cancelto)(?![A-Za-z])", (), None),
        ("pifont", r"\\ding(?![A-Za-z])", (), None),
        ("fancyhdr", r"\\(?:fancyhf|fancyhead|fancyfoot)(?![A-Za-z])|\\pagestyle\s*\{fancy\}", (), None),
        ("titlesec", r"\\(?:titleformat|titlespacing)(?![A-Za-z])", (), None),
        ("setspace", r"\\(?:onehalfspacing|doublespacing|singlespacing|setstretch)(?![A-Za-z])|"
                     r"\\begin\s*\{spacing\}", (), None),
        ("geometry", r"\\(?:geometry|newgeometry|restoregeometry)(?![A-Za-z])", (), None),
        ("lipsum", r"\\lipsum(?![A-Za-z])", (), None),
        ("xspace", r"\\xspace(?![A-Za-z])", (), None),
        ("enumitem", r"\\setlist(?![A-Za-z])", (), None),
    )
)
# Packages a document class already loads (only ones that are certain).
_CLASS_PROVIDES = {"beamer": ("graphicx", "hyperref", "xcolor", "url")}


def ensure_required_packages(code: str) -> Tuple[str, List[str]]:
    r"""
    Adds the ``\usepackage`` an LLM-written document forgot: ``\toprule`` without
    booktabs, ``align`` without amsmath, ``\textcolor`` without xcolor, … — the most
    common compile error in generated LaTeX ("Undefined control sequence",
    "Environment align undefined"), which otherwise costs an LLM repair round.

    Uses are found on the masked view (comments, verbatim and macro bodies do not
    count); a need is skipped when the package (or one providing the same
    commands, or the document class) is already loaded, or the document defines
    the macro / environment itself. The line is inserted before the first use if
    that is in the preamble, else at the end of the preamble. Loading an
    already-loaded package again without options is a no-op, so a class that
    loads the package itself is unaffected.
    """
    if not code or "\\documentclass" not in code:
        return code, []
    view = _structure_view(code)
    if len(view) != len(code):
        view = code
    m_cls = _RE_DOCCLASS.search(view)
    if not m_cls or not _RE_BEGIN_DOCUMENT.search(view):
        return code, []
    loaded = _loaded_packages(view)
    provided = set(loaded) | set(_CLASS_PROVIDES.get(m_cls.group(1).strip(), ()))
    if "table" in loaded.get("xcolor", ""):
        provided.add("colortbl")
    defined_macros = set(_RE_DEFINED_MACRO.findall(code))
    defined_envs = set(_RE_DEFINED_ENV.findall(code))

    inserts: List[Tuple[int, str, str]] = []
    for pkg, pattern, alternatives, line in _PACKAGE_NEEDS:
        if pkg in provided or provided.intersection(alternatives):
            continue
        first = None
        for m in pattern.finditer(view):
            used = m.group(0)
            env = re.search(r"\\begin\s*\{([^}]*)\}", used)
            if env and env.group(1) in defined_envs:
                continue
            macro = re.match(r"\\([A-Za-z]+)", used)
            if not env and macro and macro.group(1) in defined_macros:
                continue
            first = m
            break
        if first is None:
            continue
        pos = _preamble_insertion_point(view, first.start())
        if pos is None:
            continue
        inserts.append((pos, line or f"\\usepackage{{{pkg}}}", first.group(0).strip()))
        provided.add(pkg)

    if not inserts:
        return code, []
    fixes: List[str] = []
    for pos, text, used in sorted(inserts, key=lambda t: t[0], reverse=True):
        code = code[:pos] + text + "\n" + code[pos:]
        fixes.append(f"Added {text} ({used} is used but its package was not loaded).")
    return code, list(reversed(fixes))


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
    # If TikZ is used or loaded, ensure calc, positioning, arrows.meta are loaded. Detection
    # runs on the masked view (a "tikzpicture" in a comment is not a use; tikz loaded via
    # \usepackage{tikz,pgfplots} or \RequirePackage is loaded), and a missing \usepackage{tikz}
    # goes before its first preamble use / at the end of the preamble, not right after
    # \documentclass, where it loaded xcolor before the document's own xcolor options.
    tikz_view = _structure_view(code)
    if len(tikz_view) != len(code):
        tikz_view = code
    tikz_loaded = bool(_TIKZ_LOADERS.intersection(_loaded_packages(tikz_view)))
    m_tikz_use = re.search(
        r"\\begin\s*\{tikzpicture\}|\\(?:tikz|tikzset|usetikzlibrary)(?![A-Za-z])", tikz_view)
    if m_tikz_use and not tikz_loaded:
        pos = _preamble_insertion_point(tikz_view, m_tikz_use.start())
        if pos is not None:
            code = (code[:pos] + "\\usepackage{tikz}\n\\usetikzlibrary{calc}\n"
                    "\\usetikzlibrary{positioning,arrows.meta}\n" + code[pos:])
            fixes_applied.append("Injected missing \\usepackage{tikz} and \\usetikzlibrary{calc} into preamble.")
    elif tikz_loaded and not re.search(r"\\usetikzlibrary\s*\{[^}]*\bcalc\b", tikz_view):
        m_load = None
        for m in _RE_PKG_LOAD.finditer(tikz_view):
            if _TIKZ_LOADERS.intersection(p.strip() for p in m.group(2).split(",")):
                m_load = m
                break
        if m_load:
            code = (code[:m_load.end()] + "\n\\usetikzlibrary{calc}\n\\usetikzlibrary{positioning,arrows.meta}"
                    + code[m_load.end():])
            fixes_applied.append("Injected \\usetikzlibrary{calc} into preamble.")

    # 6b. Packages the document uses but never loads (\toprule -> booktabs, align -> amsmath, ...)
    code, package_fixes = ensure_required_packages(code)
    fixes_applied.extend(package_fixes)

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
