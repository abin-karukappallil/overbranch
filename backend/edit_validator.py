"""
edit_validator.py — Coverage, AST Integrity & Leftover-Content Validation
========================================================================
Runs pre-output validation passes after the agent loop finishes:
1. AST Coverage Check: Verifies that every content chunk (chapter, section, slide/frame)
   was explicitly rewritten during a FULL_DOCUMENT_REWRITE session. Blocks finalization
   if any content chunk was missed, feeding the missed IDs back to the agent loop.
2. Leftover Content Sweep: Scans the buffer for forbidden keywords and old topic terms
   if a topic change was requested.
3. Structural Validation: environment nesting, math delimiters, curly braces and
   \\left / \\right pairing.

This module only *validates*. Repair lives in
``latex_error_fixer.auto_heal_latex_code``, which closes environments positionally
(before the enclosing \\end) rather than appending them at end-of-file.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from document_index import DocumentChunk, DocumentIndex

logger = logging.getLogger("edit_validator")


# Environments whose body is literal text: a \begin{...}, $, { or % inside one of
# these is content, not structure. Starred forms come first so the alternation
# cannot match the unstarred prefix and then fail on the closing brace.
VERBATIM_ENVS = (
    "verbatim*", "verbatim",
    "Verbatim*", "Verbatim",
    "BVerbatim*", "BVerbatim",
    "LVerbatim*", "LVerbatim",
    "SaveVerbatim*", "SaveVerbatim",
    "semiverbatim",
    "alltt",
    "lstlisting*", "lstlisting",
    "minted*", "minted",
    "listing*", "listing",
    "comment",
    "filecontents*", "filecontents",
)

# Macros whose brace-group bodies hold *template* LaTeX that must not be counted as
# live structure: \newcommand{\openlist}{\begin{itemize}} is balanced, valid code.
# Value = how many trailing brace groups are bodies.
_MACRO_DEF_BODIES = {
    "newcommand": 1,
    "renewcommand": 1,
    "providecommand": 1,
    "DeclareRobustCommand": 1,
    "newenvironment": 2,
    "renewenvironment": 2,
}

_RE_VERBATIM_BLOCK = re.compile(
    r"\\begin\{(" + "|".join(re.escape(e) for e in VERBATIM_ENVS) + r")\}"
    r"(?:\[[^\]]*\])?(?:\{[^}]*\})?(.*?)\\end\{\1\}",
    re.DOTALL,
)
# \verb cannot span lines in TeX, so [^\n]*? makes the line-count invariant
# structural rather than incidental: an unterminated \verb can never swallow a newline.
_RE_VERB_INLINE = re.compile(r"\\verb(\*?)([^a-zA-Z0-9\s*])([^\n]*?)\2")
_RE_URL_ARG = re.compile(r"(\\(?:url|nolinkurl|path|href)\s*\{)([^{}\n]*)(\})")
_RE_COMMENT = re.compile(r"(?<!\\)(?:\\\\)*%")
_RE_ENV_TAG = re.compile(r"\\(begin|end)\s*\{\s*([A-Za-z@*][A-Za-z0-9@*]*)\s*\}")
_RE_MACRO_DEF = re.compile(
    r"\\(" + "|".join(_MACRO_DEF_BODIES) + r")\*?(?![a-zA-Z])"
)
_RE_DEF = re.compile(r"\\(?:def|gdef|edef|xdef)\\[A-Za-z@]+")
_RE_LEFT = re.compile(r"\\left(?![a-zA-Z])")
_RE_RIGHT = re.compile(r"\\right(?![a-zA-Z])")
_RE_ESCAPED_BRACE = re.compile(r"(?<!\\)(?:\\\\)*\\[{}]")
_RE_DOUBLE_DOLLAR = re.compile(r"(?<!\\)(?:\\\\)*\$\$")
_RE_SINGLE_DOLLAR = re.compile(r"(?<!\\)(?:\\\\)*\$")
_RE_PAREN_OPEN = re.compile(r"(?<!\\)(?:\\\\)*\\\(")
_RE_PAREN_CLOSE = re.compile(r"(?<!\\)(?:\\\\)*\\\)")
_RE_BRACKET_OPEN = re.compile(
    r"(?<!\\)(?:\\\\)*\\\[(?!\s*-?\d+(?:\.\d+)?\s*(?:pt|mm|cm|in|ex|em|bp|dd|pc|sp)\s*\])"
)
_RE_BRACKET_CLOSE = re.compile(r"(?<!\\)(?:\\\\)*\\\]")


def _blank(text: str) -> str:
    """Replaces every character with a space, keeping newlines (and total length)."""
    return "".join("\n" if ch == "\n" else " " for ch in text)


def _blank_group(m: "re.Match", group: int) -> str:
    """Returns the whole match with one group blanked in place, preserving length."""
    full = m.group(0)
    base = m.start(0)
    a, b = m.start(group) - base, m.end(group) - base
    return full[:a] + _blank(full[a:b]) + full[b:]


def _match_brace(s: str, i: int) -> int:
    """Given s[i] == '{', returns the index of the matching '}', or -1."""
    depth = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def mask_macro_definition_bodies(code: str) -> str:
    """
    Blanks the bodies of \\newcommand / \\newenvironment / \\def definitions.

    The enclosing braces are kept, so brace balance is still validated; only the
    template content inside is neutralised. Without this,
    ``\\newcommand{\\openlist}{\\begin{itemize}}`` is reported as an unclosed
    environment, which makes every later edit fail pre-commit validation.
    """
    if not code:
        return code

    out = list(code)
    n = len(code)

    def skip_ws(j: int) -> int:
        while j < n and code[j] in " \t\r\n":
            j += 1
        return j

    def skip_optional(j: int) -> int:
        j = skip_ws(j)
        while j < n and code[j] == "[":
            k = code.find("]", j)
            if k == -1:
                return j
            j = skip_ws(k + 1)
        return j

    def blank_span(a: int, b: int) -> None:
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

    for m in _RE_MACRO_DEF.finditer(code):
        bodies = _MACRO_DEF_BODIES[m.group(1)]
        j = skip_ws(m.end())
        # The macro/environment name: either {\foo} or a bare \foo
        if j < n and code[j] == "{":
            k = _match_brace(code, j)
            if k == -1:
                continue
            j = k + 1
        elif j < n and code[j] == "\\":
            j += 1
            while j < n and (code[j].isalpha() or code[j] == "@"):
                j += 1
        j = skip_optional(j)
        for _ in range(bodies):
            j = skip_ws(j)
            if j >= n or code[j] != "{":
                break
            k = _match_brace(code, j)
            if k == -1:
                break
            blank_span(j + 1, k)
            j = k + 1

    for m in _RE_DEF.finditer(code):
        j = m.end()
        while j < n and code[j] not in "{\n":
            j += 1
        if j < n and code[j] == "{":
            k = _match_brace(code, j)
            if k != -1:
                blank_span(j + 1, k)

    return "".join(out)


def clean_latex_for_validation(latex_code: str) -> str:
    """
    Neutralises content that must not be read as LaTeX structure:
    verbatim-like environments, inline \\verb, URL arguments, macro definition
    bodies, and % comments.

    Every character is replaced in place, so both the total length and the exact
    newline count are preserved and reported line numbers stay accurate.
    """
    if not latex_code:
        return ""

    # 1. Verbatim-like environment bodies
    cleaned = _RE_VERBATIM_BLOCK.sub(lambda m: _blank_group(m, 2), latex_code)

    # 2. Inline \verb<delim>...<delim> (any delimiter, starred form included)
    cleaned = _RE_VERB_INLINE.sub(lambda m: _blank_group(m, 3), cleaned)

    # 3. URL-ish arguments: % # $ & _ inside them are literal, not TeX specials.
    #    Only the first brace group, so $math$ in \href link *text* is still checked.
    cleaned = _RE_URL_ARG.sub(lambda m: _blank_group(m, 2), cleaned)

    # 4. Macro definition bodies
    cleaned = mask_macro_definition_bodies(cleaned)

    # 5. Comments (% to end of line, unless escaped by an odd number of backslashes)
    out_lines = []
    for line in cleaned.splitlines(keepends=True):
        m = _RE_COMMENT.search(line)
        if m:
            pct = m.end() - 1
            nl = "\n" if line.endswith("\n") else ""
            body = line[:-1] if nl else line
            out_lines.append(body[:pct] + _blank(body[pct:]) + nl)
        else:
            out_lines.append(line)

    return "".join(out_lines)


def validate_latex_pre_commit(latex_code: str) -> Tuple[bool, List[str]]:
    """
    Strict pre-commit validation step for the edit pipeline.
    Validates:
    1. Every \\begin{X} has a matching \\end{X} in correct nesting order.
    2. $, $$, \\( \\), \\[ \\] delimiters are balanced.
    3. Braces { } are balanced.
    4. \\left and \\right are paired.

    Comments, verbatim-like environments, URL arguments and macro definition
    bodies are neutralised first (see ``clean_latex_for_validation``).

    Returns:
        (passed: bool, errors: List[str])
    """
    if not latex_code or not latex_code.strip():
        return True, []

    errors: List[str] = []
    cleaned = clean_latex_for_validation(latex_code)
    lines = cleaned.splitlines(keepends=True)

    # 1. Environment Matching Stack
    stack: List[Tuple[str, int]] = []

    for idx, line in enumerate(lines, start=1):
        for m in _RE_ENV_TAG.finditer(line):
            tag_type = m.group(1)
            env_name = m.group(2)
            if tag_type == "begin":
                stack.append((env_name, idx))
            elif tag_type == "end":
                if not stack:
                    errors.append(f"Line {idx}: Unmatched \\end{{{env_name}}} (no open environment)")
                else:
                    top_env, top_line = stack.pop()
                    if top_env != env_name:
                        errors.append(
                            f"Line {idx}: Mismatched \\end{{{env_name}}}, expected \\end{{{top_env}}} from line {top_line}"
                        )

    for env_name, line_no in stack:
        errors.append(f"Line {line_no}: Unclosed \\begin{{{env_name}}}")

    # 2. Math Delimiters Balance
    double_dollar_matches = list(_RE_DOUBLE_DOLLAR.finditer(cleaned))
    if len(double_dollar_matches) % 2 != 0:
        errors.append(f"Unbalanced '$$' display math delimiters (found {len(double_dollar_matches)} occurrences)")

    temp_no_dd = _RE_DOUBLE_DOLLAR.sub("", cleaned)
    single_dollar_matches = list(_RE_SINGLE_DOLLAR.finditer(temp_no_dd))
    if len(single_dollar_matches) % 2 != 0:
        errors.append(f"Unbalanced '$' inline math delimiters (found {len(single_dollar_matches)} occurrences)")

    open_paren_math = len(list(_RE_PAREN_OPEN.finditer(cleaned)))
    close_paren_math = len(list(_RE_PAREN_CLOSE.finditer(cleaned)))
    if open_paren_math != close_paren_math:
        errors.append(f"Unbalanced math mode delimiters: \\( ({open_paren_math}) vs \\) ({close_paren_math})")

    open_bracket_math = len(list(_RE_BRACKET_OPEN.finditer(cleaned)))
    close_bracket_math = len(list(_RE_BRACKET_CLOSE.finditer(cleaned)))
    if open_bracket_math != close_bracket_math:
        errors.append(f"Unbalanced display math delimiters: \\[ ({open_bracket_math}) vs \\] ({close_bracket_math})")

    # 3. Curly Braces Balance { }
    brace_depth = 0
    for idx, line in enumerate(lines, start=1):
        line_clean = _RE_ESCAPED_BRACE.sub("", line)
        for char in line_clean:
            if char == "{":
                brace_depth += 1
            elif char == "}":
                brace_depth -= 1
                if brace_depth < 0:
                    errors.append(f"Line {idx}: Extra closing brace '}}'")
                    brace_depth = 0

    if brace_depth > 0:
        errors.append(f"Unclosed '{{' curly brace(s) (nesting depth: {brace_depth})")

    # 4. \left / \right pairing
    n_left = len(_RE_LEFT.findall(cleaned))
    n_right = len(_RE_RIGHT.findall(cleaned))
    if n_left != n_right:
        errors.append(f"Unbalanced \\left ({n_left}) vs \\right ({n_right})")

    return len(errors) == 0, errors


@dataclass
class CoverageValidationResult:
    passed: bool
    total_chunks: int
    edited_chunks: int
    missing_chunk_ids: List[str] = field(default_factory=list)
    missing_chunk_titles: List[str] = field(default_factory=list)
    leftover_terms_found: List[Dict[str, Any]] = field(default_factory=list)
    feedback_message: str = ""


def validate_coverage(
    workspace: Any,
    user_instruction: str,
    scope: str = "FULL_DOCUMENT_REWRITE",
    forbidden_terms: Optional[List[str]] = None,
) -> CoverageValidationResult:
    """
    Validates that:
    1. Every content chunk in the original document was touched/rewritten in full-rewrite mode.
    2. No forbidden or obsolete topic terms remain in the updated shadow buffer.
    """
    doc_index = DocumentIndex()
    orig_code = workspace.get_original() if hasattr(workspace, "get_original") else ""
    current_code = workspace.get_buffer() if hasattr(workspace, "get_buffer") else ""

    content_chunks = doc_index.get_content_chunks(orig_code)
    total_content_chunks = len(content_chunks)
    touched_ids: Set[str] = workspace.get_touched_chunks() if hasattr(workspace, "get_touched_chunks") else set()

    # If document has no structural content chunks (e.g. single small document or empty), coverage is trivially satisfied
    if total_content_chunks == 0:
        return CoverageValidationResult(
            passed=True,
            total_chunks=0,
            edited_chunks=0,
            feedback_message="Document has no distinct content chunks to validate.",
        )

    # 1. Chunk Coverage Check
    missing_chunks: List[DocumentChunk] = [c for c in content_chunks if c.chunk_id not in touched_ids]
    edited_count = total_content_chunks - len(missing_chunks)

    is_rewrite = scope == "FULL_DOCUMENT_REWRITE" or "FULL_DOCUMENT_REWRITE" in scope
    is_expansion = scope == "FULL_DOCUMENT_EXPANSION" or "FULL_DOCUMENT_EXPANSION" in scope

    if missing_chunks and (is_rewrite or is_expansion):
        missing_ids = [c.chunk_id for c in missing_chunks]
        missing_titles = [c.title for c in missing_chunks]
        chunks_bullet_list = "\n".join([f"  - `{c.chunk_id}`: {c.title}" for c in missing_chunks])

        mode_name = "FULL_DOCUMENT_EXPANSION" if is_expansion else "FULL_DOCUMENT_REWRITE"
        action_name = "expand and detail" if is_expansion else "replace"
        tool_hint = "`insert_into_chunk(chunk_id, ...)` or `rewrite_chunk(chunk_id, ...)` or `str_replace(...)`" if is_expansion else "`rewrite_chunk(chunk_id, new_content)`"

        feedback = (
            f"COVERAGE CHECK FAILED: In {mode_name} mode, you must {action_name} all content chunks across the document.\n"
            f"You have edited {edited_count}/{total_content_chunks} content chunks.\n"
            f"The following {len(missing_chunks)} chunk(s) have NOT been touched:\n"
            f"{chunks_bullet_list}\n\n"
            f"ACTION REQUIRED: Use {tool_hint} for each unedited chunk before setting done=true."
        )

        logger.warning(f"Coverage check failed ({mode_name}): {len(missing_chunks)} chunks untouched: {missing_ids}")
        return CoverageValidationResult(
            passed=False,
            total_chunks=total_content_chunks,
            edited_chunks=edited_count,
            missing_chunk_ids=missing_ids,
            missing_chunk_titles=missing_titles,
            feedback_message=feedback,
        )

    # 2. Leftover Content & Forbidden Terms Sweep
    leftover_matches: List[Dict[str, Any]] = []
    if forbidden_terms:
        for term in forbidden_terms:
            t = term.strip()
            if not t or len(t) < 3:
                continue
            # Search current buffer
            grep_results = workspace.grep(t) if hasattr(workspace, "grep") else []
            valid_hits = [g for g in grep_results if "line_no" in g]
            if valid_hits:
                leftover_matches.append({
                    "term": t,
                    "count": len(valid_hits),
                    "lines": [h["line_no"] for h in valid_hits[:5]],
                })

    if leftover_matches and (scope == "FULL_DOCUMENT_REWRITE" or "FULL_DOCUMENT_REWRITE" in scope):
        summary_items = [f"'{m['term']}' (found on lines {m['lines']})" for m in leftover_matches]
        summary_str = ", ".join(summary_items)
        feedback = (
            f"LEFTOVER CONTENT CHECK FAILED: The following terms from the old document/topic were found remaining:\n"
            f"  {summary_str}\n\n"
            f"ACTION REQUIRED: Replace or remove these obsolete topic terms using `rewrite_chunk` or `str_replace` before finishing."
        )
        logger.warning(f"Leftover terms check failed: {summary_str}")
        return CoverageValidationResult(
            passed=False,
            total_chunks=total_content_chunks,
            edited_chunks=edited_count,
            leftover_terms_found=leftover_matches,
            feedback_message=feedback,
        )

    # All checks passed
    logger.info(f"Coverage check PASSED: all {total_content_chunks} chunks edited, 0 leftover forbidden terms.")
    return CoverageValidationResult(
        passed=True,
        total_chunks=total_content_chunks,
        edited_chunks=total_content_chunks,
        missing_chunk_ids=[],
        missing_chunk_titles=[],
        feedback_message=f"Coverage verified: all {total_content_chunks} chunks rewritten and verified.",
    )
