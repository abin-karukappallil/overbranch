"""
backend/latex_diagnostics.py — TeX's errors, on the lines they are actually on
==============================================================================
TeX reports an error at the line its *reader* had reached, which is not where
the mistake is whenever the text was collected as a macro argument first:

* Beamer reads a whole frame, so every error in it is reported at the frame's
  ``\\end{frame}``;
* ``tabularx``, ``align`` and the other body-grabbing environments report at
  their ``\\end{...}``;
* a multi-line ``\\caption{...}`` or ``\\footnote{...}`` reports at its closing brace.

Everything downstream used that line. The deterministic repair looked at
``\\end{frame}``, found nothing to repair and changed nothing; the model was
shown ``\\end{frame}`` with three lines either side and guessed. A deck with one
bare ``&`` in an outline bullet could not be fixed by either, and the run was
rolled back.

TeX does say where the error is — just not in the line number. Under every
error it prints the tokens it had read and the ones that come next::

    ./main.tex:28: Misplaced alignment tab character &.
    \\beamer@doifinframe ...itemize} \\item Background &
                                                       Motivation \\item Methods ...
    l.28 \\end{frame}

This module reads those context pairs (``parse_tex_errors``) and finds the same
text in the source (``locate``), giving each error its true line, column and
offending token. Two things make that reliable, both set by ``compiler.py``:
a wide ``error_line`` (TeX otherwise keeps ~50 characters) and
``\\errorcontextlines``, without which *Missing $ inserted* shows only
``<inserted text> $`` and no position at all.

One record per **occurrence**. De-duplicating by ``file:line: message`` — which
is all the old pipeline kept — turned a frame with four bare ``&`` into "one
error"; the model fixed one per repair round and ran out of rounds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

# Files whose line numbers refer to text the user wrote. A fragile Beamer frame is
# compiled from <job>.vrb, a verbatim copy of the frame body.
_RE_FILE_ERROR = re.compile(r"^((?:\./)?[^\s:()]*?[\w\-]+\.(tex|ltx|vrb)):(\d+): (.*)$", re.IGNORECASE)
_RE_BANG_ERROR = re.compile(r"^! (.+)$")
_RE_L_LINE = re.compile(r"^l\.(\d+) ?(.*)$")
# Consequences of an earlier error, not errors of their own.
_CONSEQUENCES = ("emergency stop", "==> fatal error occurred", "fatal error occurred, no output",
                 "that makes 100 errors")
# Context labels that describe what TeX inserted or re-read, not where it was in the user's text.
_RE_SYNTHETIC_LABEL = re.compile(r"^<(?!argument>)[^>]*>")
_RE_MACRO_LABEL = re.compile(r"^(\\[^\s]+) ?(.*)$", re.DOTALL)
_RE_TRAILING_CS = re.compile(r"(\\[A-Za-z@]+)\s*$")
_RE_ENV_END = re.compile(r"\\end\s*\{([^}]+)\}")
_MAX_BLOCK = 400
_MAX_SPAN = 600


@dataclass
class TexError:
    file: Optional[str]                  # as TeX named it; None when the log did not say
    reported_line: Optional[int]         # the line TeX printed
    message: str
    raw: str = ""                        # the error line exactly as printed
    contexts: List[Tuple[str, str]] = field(default_factory=list)  # (read so far, what follows), innermost first
    l_before: Optional[str] = None       # TeX's "l.N" line: the source line up to its reader
    l_after: str = ""
    # Filled by locate():
    line: Optional[int] = None           # where the offending token really is
    col: Optional[int] = None            # 1-based
    token: Optional[str] = None
    located_by: Optional[str] = None     # "tex-context" | "tex-line" | None
    span: Optional[Tuple[int, int]] = None  # the construct TeX was reading (1-based, inclusive)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file, "line": self.line if self.line is not None else self.reported_line,
            "reported_line": self.reported_line, "col": self.col, "token": self.token,
            "message": self.message, "located_by": self.located_by,
            "span": list(self.span) if self.span else None,
            "context": self.context_excerpt(),
        }

    def context_excerpt(self) -> str:
        """TeX's own words around the error, for a log line or a prompt."""
        for before, after in self.user_contexts():
            return (before[-60:].strip() + " ⟂ " + after[:40].strip()).strip()
        return (self.l_before or "").strip()

    def user_contexts(self) -> List[Tuple[str, str]]:
        """Context pairs that show the user's own text (macro bodies and arguments), innermost first."""
        found: List[Tuple[str, str]] = []
        for first, second in self.contexts:
            text = _context_text(first)
            if text is not None:
                found.append((text, re.sub(r"\.\.\.\s*$", "", second)))
        return found


def _context_text(first: str) -> Optional[str]:
    """The text of a context line without its label, or None when it is not the user's text."""
    first = first.rstrip("\n")
    if first.startswith("<argument>"):
        text = first[len("<argument>"):]
        return text[4:] if text.lstrip().startswith("...") else text
    if _RE_SYNTHETIC_LABEL.match(first):
        return None
    m = _RE_MACRO_LABEL.match(first)
    if not m:
        return None
    rest = m.group(2)
    if rest.startswith("..."):
        return rest[3:]
    if "->" in rest:
        return rest.split("->", 1)[1]
    return rest


def parse_tex_errors(output: str) -> List[TexError]:
    """
    Every error in a TeX run's output, with the context TeX printed under it.

    Understands ``./main.tex:66: <message>`` (-file-line-error, every compile
    OverBranch runs) and ``! <message>`` + ``l.66 <code>`` (latexmk, pasted logs).
    """
    if not output:
        return []
    lines = output.splitlines()
    errors: List[TexError] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        m_file = _RE_FILE_ERROR.match(line)
        m_bang = None if m_file else _RE_BANG_ERROR.match(line)
        if not m_file and not m_bang:
            i += 1
            continue
        if m_file:
            fname = m_file.group(1)
            err = TexError(file=fname[2:] if fname.startswith("./") else fname,
                           reported_line=int(m_file.group(3)), message=m_file.group(4).strip(), raw=line.strip())
        else:
            err = TexError(file=None, reported_line=None, message=m_bang.group(1).strip(), raw=line.strip())
        if any(c in err.message.lower() for c in _CONSEQUENCES) or not err.message:
            i += 1
            continue

        block: List[str] = []
        j = i + 1
        while j < n and j - i < _MAX_BLOCK:
            nxt = lines[j]
            if _RE_FILE_ERROR.match(nxt) or _RE_BANG_ERROR.match(nxt) or nxt.startswith("<*>"):
                break
            m_l = _RE_L_LINE.match(nxt)
            if m_l:
                if err.reported_line is None:
                    err.reported_line = int(m_l.group(1))
                err.l_before = m_l.group(2)
                err.l_after = lines[j + 1].strip() if j + 1 < n else ""
                j += 1
                break
            block.append(nxt)
            j += 1

        # TeX prints each context as a pair: what it had read, then — indented to
        # that width — what comes next.
        k = 0
        while k + 1 < len(block):
            first, second = block[k], block[k + 1]
            if first.strip() and not first[0].isspace() and (
                    not second.strip() or second.startswith(" " * max(1, len(first) - 2))):
                err.contexts.append((first, second.strip()))
                k += 2
            else:
                k += 1
        errors.append(err)
        i = j
    return errors


def _squash(text: str) -> str:
    """Whitespace-free form used to compare TeX's token listing with source text."""
    if "^^" in text:
        # 8-bit characters TeX printed in ^^xx notation.
        try:
            raw = re.sub(r"\^\^([0-9a-f]{2})", lambda m: chr(int(m.group(1), 16)), text)
            text = raw.encode("latin-1", "ignore").decode("utf-8", "ignore") or raw
        except Exception:
            pass
    return re.sub(r"\s+", "", text).replace("##", "#")


def _comment_start(line: str) -> int:
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


def _brace_delta(line: str) -> int:
    c = _comment_start(line)
    text = re.sub(r"\\.", "", line if c < 0 else line[:c])
    return text.count("{") - text.count("}")


def enclosing_span(lines: List[str], ln: int) -> Tuple[int, int]:
    """
    The construct TeX was still reading when it reported an error at 1-based
    line ``ln``: the environment that ends there, or the brace group that closes
    there. ``(ln, ln)`` when the line stands on its own.
    """
    if not (1 <= ln <= len(lines)):
        return ln, ln
    line = lines[ln - 1]
    c = _comment_start(line)
    code = line if c < 0 else line[:c]
    m = _RE_ENV_END.search(code)
    if m:
        env = re.escape(m.group(1))
        re_begin = re.compile(r"\\begin\s*\{" + env + r"\}")
        re_end = re.compile(r"\\end\s*\{" + env + r"\}")
        depth = 0
        for k in range(ln - 1, max(-1, ln - 1 - _MAX_SPAN), -1):
            text = lines[k]
            cc = _comment_start(text)
            text = text if cc < 0 else text[:cc]
            depth += len(re_end.findall(text)) - len(re_begin.findall(text))
            if depth <= 0:
                return k + 1, ln
        return ln, ln
    if _brace_delta(line) < 0:
        depth = 0
        for k in range(ln - 1, max(-1, ln - 1 - _MAX_SPAN), -1):
            depth += _brace_delta(lines[k])
            if depth >= 0:
                return k + 1, ln
    return ln, ln


def _haystack(lines: List[str], lo: int, hi: int, keep_comments: bool = False) -> Tuple[str, List[Tuple[int, int]]]:
    chars: List[str] = []
    pos: List[Tuple[int, int]] = []
    for ln in range(lo, hi + 1):
        text = lines[ln - 1]
        if not keep_comments:
            c = _comment_start(text)
            if c >= 0:
                text = text[:c]
        for col, ch in enumerate(text, start=1):
            if not ch.isspace():
                chars.append(ch)
                pos.append((ln, col))
    return "".join(chars), pos


def _find_unique(hay: str, before: str, after: str, small_span: bool) -> Optional[int]:
    """Index in ``hay`` of the last character of ``before``, when the join is unambiguous."""
    b, a = _squash(before), _squash(after)
    if not b:
        return None
    # Longest suffix first. The head of TeX's listing is often not the user's text
    # (`\begin {beamer@frameslide}` stands where `\begin{frame}` was written, a blank
    # line is shown as `\par`), so a long suffix failing says nothing about a shorter one.
    tried = set()
    for tail in (160, 96, 64, 40, 24, 12, 6, 3, 1):
        t = b[-tail:]
        for head in (32, 12, 4, 0):
            needle = t + a[:head]
            if needle in tried or (len(needle) < 4 and not small_span):
                continue
            tried.add(needle)
            first = hay.find(needle)
            if first == -1 or hay.find(needle, first + 1) != -1:
                continue
            return first + len(t) - 1
    return None


def _token_at(before: str, lines: List[str], line: int, col: int) -> Tuple[str, int]:
    """The offending token and the column it starts at."""
    m = _RE_TRAILING_CS.search(before.rstrip())
    if m:
        name = m.group(1)
        start = col - len(name) + 1
        if start >= 1 and lines[line - 1][start - 1:col] == name:
            return name, start
    return lines[line - 1][col - 1], col


def _token_fits(message: str, token: Optional[str]) -> bool:
    """Rejects a location whose token cannot be what this error is about."""
    low = message.lower()
    if "alignment tab" in low:
        return token == "&"
    if "undefined control sequence" in low:
        return bool(token) and token.startswith("\\")
    if "macro parameter character" in low:
        return token == "#"
    return True


def locate(errors: List[TexError], read_source: Callable[[str], Optional[str]],
           main_file: str = "main.tex") -> List[TexError]:
    """
    Sets ``line`` / ``col`` / ``token`` / ``located_by`` / ``span`` on each error.

    ``read_source(file)`` returns the text TeX read for ``file`` (or None). An
    error that cannot be placed keeps TeX's line and gets ``located_by=None``
    with the ``span`` of the construct it is somewhere inside — "inside this
    frame" is the truth, and far more useful than a confident wrong line.
    """
    cache: Dict[str, Optional[List[str]]] = {}

    def source_lines(name: str) -> Optional[List[str]]:
        if name not in cache:
            try:
                text = read_source(name)
            except Exception:
                text = None
            cache[name] = text.split("\n") if text is not None else None
        return cache[name]

    for err in errors:
        fname = err.file or main_file
        if fname.lower().endswith(".vrb"):
            _locate_fragile(err, source_lines(main_file), main_file)
            continue
        lines = source_lines(fname)
        ln = err.reported_line
        if lines is None or ln is None or not (1 <= ln <= len(lines)):
            continue
        lo, hi = enclosing_span(lines, ln)
        err.span = (lo, hi)
        hay, pos = _haystack(lines, lo, hi)
        small = hi - lo <= 2

        for before, after in err.user_contexts():
            idx = _find_unique(hay, before, after, small)
            if idx is None:
                continue
            line, col = pos[idx]
            token, col = _token_at(before, lines, line, col)
            if _token_fits(err.message, token):
                err.line, err.col, err.token, err.located_by = line, col, token, "tex-context"
                break
        if err.located_by:
            continue

        # TeX's own line. It is the truth only when nothing was being collected
        # there: on a line that closes a frame it says where reading stopped.
        if err.l_before is not None and lo == hi:
            before = err.l_before[3:] if err.l_before.startswith("...") else err.l_before
            line_hay, line_pos = _haystack(lines, ln, ln, keep_comments=True)
            idx = _find_unique(line_hay, before, err.l_after, True)
            if idx is not None:
                _, col = line_pos[idx]
                token, col = _token_at(before, lines, ln, col)
                if _token_fits(err.message, token):
                    err.line, err.col, err.token, err.located_by = ln, col, token, "tex-line"
                    continue
            err.line = ln
            err.located_by = "tex-line"
    return errors


def _locate_fragile(err: TexError, lines: Optional[List[str]], main_file: str) -> None:
    """Maps an error in ``<job>.vrb`` (a fragile frame's body) back to the main source."""
    if not lines or err.l_before is None:
        return
    before = err.l_before[3:] if err.l_before.startswith("...") else err.l_before
    whole = _squash(before + err.l_after)
    if len(whole) < 3:
        return
    hits = [k + 1 for k, text in enumerate(lines) if whole in _squash(text)]
    if len(hits) != 1:
        return
    ln = hits[0]
    line_hay, line_pos = _haystack(lines, ln, ln, keep_comments=True)
    idx = _find_unique(line_hay, before, err.l_after, True)
    err.file = main_file
    err.line, err.located_by, err.span = ln, "tex-line", (ln, ln)
    if idx is not None:
        _, col = line_pos[idx]
        err.token, err.col = _token_at(before, lines, ln, col)


def diagnose(output: str, read_source: Callable[[str], Optional[str]],
             main_file: str = "main.tex") -> List[Dict[str, Any]]:
    """Parsed, located and classified errors of one TeX run, as plain dicts."""
    errors = locate(parse_tex_errors(output), read_source, main_file)
    try:
        from latex_error_fixer import _classify_tex_error
    except Exception:  # pragma: no cover - classification is advisory
        _classify_tex_error = lambda msg: ("LATEX_ERROR", "")  # noqa: E731
    out: List[Dict[str, Any]] = []
    for err in errors:
        d = err.as_dict()
        d["type"], d["suggested_action"] = _classify_tex_error(err.message)
        d["raw"] = err.raw
        out.append(d)
    return out


def error_lines(diagnostics: List[Dict[str, Any]], limit: int = 20) -> List[str]:
    """
    The ``errors`` strings the compiler returns (``./main.tex:64: <message>``),
    carrying the located line. Occurrences that land on different lines stay
    separate; exact repeats collapse.
    """
    out: List[str] = []
    for d in diagnostics:
        raw = str(d.get("raw") or "")
        fname, line = d.get("file"), d.get("line")
        if fname and line:
            prefix = "./" if raw.startswith("./") else ""
            if str(fname).lower().endswith(".vrb"):
                out.append(raw)
            else:
                out.append(f"{prefix}{fname}:{line}: {d.get('message', '')}")
        elif raw:
            out.append(raw)
    return list(dict.fromkeys(out))[:limit]
