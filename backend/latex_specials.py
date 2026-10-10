"""
backend/latex_specials.py — Where ``&`` is legal, decided from structure
========================================================================
The most common way an LLM-written document fails to compile is one character:
an ``&`` that is not a column separator. ``Research & Development`` in a bullet,
``\\textbf{Pros & Cons}`` in a table cell, ``a &= b`` in a bare ``equation``.

TeX cannot be asked where these are. Beamer reads a whole frame as one macro
argument and reports every error in it at the frame's ``\\end{frame}`` line
(``tabularx``, ``align`` and any multi-line ``\\caption{...}`` do the same), so
a repair that looks at "the line TeX named" looks at a line with no ``&`` on it
and concludes there is nothing to fix. That is exactly what happened: the
deterministic repair returned no change, the model was shown ``\\end{frame}``,
and the run was rolled back with *Misplaced alignment tab character &*.

So legality is decided here, from the document itself, in one left-to-right scan
of the validator's masked view (comments, verbatim bodies, URLs and macro
definitions already neutralised, offsets unchanged). Each unescaped ``&`` gets a
verdict:

* ``legal``            — inside an alignment (tabular / align / matrix families,
                         ``\\matrix{...}``, ``\\halign{...}``).
* ``text``             — certainly illegal: prose, or the argument of a command
                         that typesets text (``\\section``, ``\\caption``,
                         ``\\textbf``, the 3rd argument of ``\\multicolumn``, a
                         frame title *or subtitle*, a TikZ ``\\node`` label).
                         The repair is ``\\&``.
* ``display_math``     — ``equation`` / ``\\[...\\]`` / ``$$...$$`` with no
                         alignment inside. ``\\&`` would print an ampersand in
                         the formula; the repair is ``aligned``.
* ``row_outside_table``— rows that have lost their ``\\begin{tabular}``. Never
                         escaped: turning a table into prose that happens to
                         compile hides the real defect. Reported as what it is.
* ``unknown``          — everything this module cannot be sure about: an
                         environment or command it does not know (it may well
                         build an alignment), the preamble, a fragment file.
                         Left alone.

"Certain or untouched" is the whole design. The classifier was checked against
every bundled template (no ``&`` flagged) before it was allowed to edit anything.

Also here, because they are the same family of fault:

* ``terminate_lone_backslash_rows`` — a row break ``\\\\`` that reached the
  document as a single ``\\`` (the model wrote two backslashes inside otherwise
  correctly escaped JSON). The rows of a table then run together and TeX reports
  *Extra alignment tab has been changed to \\cr*.
* ``widen_tabular_columns`` — a column specification narrower than its rows.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

from edit_validator import clean_latex_for_validation

LEGAL = "legal"
TEXT = "text"
DISPLAY_MATH = "display_math"
ROW_OUTSIDE_TABLE = "row_outside_table"
UNKNOWN = "unknown"

# Environments that set an alignment in text mode.
TABLE_ENVS = frozenset({
    "tabular", "tabular*", "tabularx", "tabulary", "tabu", "longtabu", "longtable", "xltabular",
    "supertabular", "xtabular", "mpsupertabular", "ltablex", "tblr", "longtblr", "talltblr",
    "NiceTabular", "NiceTabular*", "NiceTabularX",
})
# Environments that set an alignment in math mode.
MATH_ALIGNMENT_ENVS = frozenset({
    "array", "align", "align*", "alignat", "alignat*", "flalign", "flalign*", "xalignat", "xalignat*",
    "xxalignat", "eqnarray", "eqnarray*", "aligned", "alignedat", "split", "cases", "cases*", "dcases",
    "dcases*", "rcases", "drcases", "numcases", "subnumcases", "matrix", "pmatrix", "bmatrix", "Bmatrix",
    "vmatrix", "Vmatrix", "smallmatrix", "matrix*", "pmatrix*", "bmatrix*", "Bmatrix*", "vmatrix*",
    "Vmatrix*", "psmallmatrix", "bsmallmatrix", "vsmallmatrix", "IEEEeqnarray", "IEEEeqnarray*",
    "IEEEeqnarraybox", "NiceArray", "NiceMatrix", "pNiceMatrix", "bNiceMatrix", "vNiceMatrix",
    "VNiceMatrix", "BNiceMatrix", "tikzcd", "tikzcd*", "blockarray", "empheq",
})
ALIGNMENT_ENVS = TABLE_ENVS | MATH_ALIGNMENT_ENVS
# Display math with no alignment of its own: an & here is always an error.
DISPLAY_MATH_ENVS = frozenset({
    "equation", "equation*", "displaymath", "gather", "gather*", "multline", "multline*", "math",
})
# Environments whose body is ordinary text. They are *transparent*: an & inside
# one is judged by whatever encloses it (an itemize in a p{} cell is still in the table).
TEXT_ENVS = frozenset({
    "document", "frame", "itemize", "enumerate", "description", "center", "flushleft", "flushright",
    "quote", "quotation", "verse", "abstract", "columns", "column", "block", "alertblock", "exampleblock",
    "minipage", "figure", "figure*", "table", "table*", "titlepage", "theorem", "lemma", "proof",
    "definition", "example", "remark", "corollary", "proposition", "multicols", "multicols*", "onlyenv",
    "uncoverenv", "visibleenv", "overprint", "overlayarea", "beamercolorbox", "subfigure", "subtable",
    "wrapfigure", "wraptable", "sloppypar", "samepage", "spacing", "singlespace", "onehalfspace",
    "doublespace", "thebibliography", "appendix", "landscape", "subequations", "letter", "framed",
    "shaded", "mdframed", "adjustbox", "sidewaystable", "sidewaysfigure", "tiny", "scriptsize",
    "footnotesize", "small", "normalsize", "large", "Large", "LARGE", "huge", "Huge",
    "tikzpicture", "scope", "pgfonlayer", "circuitikz",
})
# Commands whose brace argument is typeset as text. Value = how many brace groups belong to it.
TEXT_COMMANDS: Dict[str, int] = {
    "textbf": 1, "textit": 1, "emph": 1, "texttt": 1, "textsc": 1, "textsf": 1, "textrm": 1,
    "textmd": 1, "textsl": 1, "textup": 1, "textnormal": 1, "underline": 1, "uline": 1, "sout": 1,
    "hl": 1, "mbox": 1, "fbox": 1, "text": 1, "enquote": 1, "section": 1, "subsection": 1,
    "subsubsection": 1, "chapter": 1, "part": 1, "paragraph": 1, "subparagraph": 1, "caption": 1,
    "captionof": 2, "footnote": 1, "title": 1, "subtitle": 1, "author": 1, "institute": 1, "date": 1,
    "frametitle": 1, "framesubtitle": 1, "item": 1, "multicolumn": 3, "multirow": 3, "centerline": 1,
    "alert": 1, "structure": 1, "textsuperscript": 1, "textsubscript": 1, "textcolor": 2,
    "colorbox": 2, "parbox": 2, "makebox": 1, "framebox": 1, "raisebox": 2, "href": 2,
    # TikZ: the brace group of a node is its label.
    "node": 1, "draw": 1, "path": 1, "fill": 1, "filldraw": 1,
}
# Commands whose brace argument is itself an alignment.
ALIGNMENT_COMMANDS = frozenset({
    "matrix", "pmatrix", "bordermatrix", "cases", "halign", "ialign", "xymatrix", "eqalign",
    "eqalignno", "leqalignno", "displaylines", "Qcircuit",
})
# Declarations take no argument, so they never own the brace group that follows:
# `\centering {\Large A & B}` is text, not "an argument of \centering".
_DECLARATIONS = frozenset({
    "tiny", "scriptsize", "footnotesize", "small", "normalsize", "large", "Large", "LARGE", "huge",
    "Huge", "bfseries", "mdseries", "itshape", "slshape", "scshape", "upshape", "sffamily", "ttfamily",
    "rmfamily", "normalfont", "bf", "it", "em", "tt", "sc", "rm", "sf", "sl", "centering", "raggedright",
    "raggedleft", "noindent", "indent", "par", "newline", "linebreak", "hfill", "vfill", "quad", "qquad",
    "today", "LaTeX", "TeX", "ldots", "dots", "maketitle", "titlepage", "newpage", "clearpage", "pause",
    "hline", "toprule", "midrule", "bottomrule", "smallskip", "medskip", "bigskip", "and", "selectfont",
    "tableofcontents", "justifying", "arraybackslash", "displaystyle", "textstyle", "relax",
})
# Commands with a fixed number of arguments that are not text (lengths, keys, labels).
# Their groups are opaque, and nothing after them belongs to them.
_OPAQUE_COMMANDS: Dict[str, int] = {
    "vspace": 1, "hspace": 1, "vskip": 1, "hskip": 1, "color": 1, "label": 1, "ref": 1, "eqref": 1,
    "pageref": 1, "cite": 1, "citep": 1, "citet": 1, "includegraphics": 1, "input": 1, "include": 1,
    "rule": 2, "fontsize": 2, "setlength": 2, "addtolength": 2, "pagestyle": 1, "thispagestyle": 1,
    "linespread": 1, "setcounter": 2, "addtocounter": 2, "usebeamerfont": 1, "usebeamercolor": 1,
    "bibliographystyle": 1, "bibliography": 1, "url": 1, "nolinkurl": 1, "path": 1,
}
# Commands that take an optional argument which is text.
_TEXT_OPTIONAL = frozenset({"item", "section", "subsection", "subsubsection", "chapter", "caption", "title"})

_RE_ENV = re.compile(r"\\(begin|end)\s*\{\s*([A-Za-z@*]+)\s*\}")
_RE_CMD = re.compile(r"\\([A-Za-z@]+)\*?")
_RE_BEGIN_DOC = re.compile(r"\\begin\s*\{document\}")
_RE_ROW_END = re.compile(
    r"\\\\\s*(?:\[[^\]]*\])?\s*(?:\\(?:hline|toprule|midrule|bottomrule|addlinespace|cline\{[^}]*\}"
    r"|cmidrule(?:\([^)]*\))?\{[^}]*\})\s*)*$")
_RE_RULE_LINE = re.compile(r"^\s*(?:\\(?:hline|toprule|midrule|bottomrule)\s*)+$")
_RE_UNESCAPED_AMP = re.compile(r"(?<!\\)(?:\\\\)*&")
# How far a command keeps "owning" the next brace group. `\node[draw] at (0,0) {label}` and
# `\matrix (m) [matrix of nodes] {` put a lot between the command and its group.
_OWNER_REACH = 240


@dataclass(frozen=True)
class Ampersand:
    """One unescaped ``&``: where it is, what it is, and why."""
    offset: int
    line: int      # 1-based
    col: int       # 1-based
    verdict: str
    reason: str
    # For display_math: (kind, name, open_start, open_end) of the construct that holds it.
    construct: Optional[Tuple[str, str, int, int]] = None


def _line_starts(code: str) -> List[int]:
    starts = [0]
    for m in re.finditer("\n", code):
        starts.append(m.end())
    return starts


def _matching_bracket(view: str, open_pos: int) -> int:
    """Index of the ``]`` closing the ``[`` at ``open_pos`` on the same line, or -1."""
    depth = 0
    i, n = open_pos + 1, len(view)
    while i < n:
        ch = view[i]
        if ch == "\n":
            return -1
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            if depth == 0:
                return -1
            depth -= 1
        elif ch == "]" and depth == 0:
            return i
        i += 1
    return -1


def _looks_like_table_rows(view_lines: List[str], idx: int) -> bool:
    """
    Whether line ``idx`` (0-based) is a table row that has lost its table, as
    opposed to a line of prose that happens to hold an ampersand.

    One such line proves nothing — a title page is full of
    ``Computer Science & Engineering \\\\``. Rows come in runs, or sit next to a rule.
    """
    def is_row(k: int) -> bool:
        return bool(_RE_ROW_END.search(view_lines[k].rstrip()) and _RE_UNESCAPED_AMP.search(view_lines[k]))

    def neighbour(step: int) -> Optional[int]:
        k = idx + step
        while 0 <= k < len(view_lines):
            if view_lines[k].strip():
                return k
            k += step
        return None

    near = [k for k in (neighbour(-1), neighbour(1)) if k is not None]
    if any(_RE_RULE_LINE.match(view_lines[k]) for k in near):
        return True
    return is_row(idx) and any(is_row(k) for k in near)


def classify_ampersands(code: str, fragment_top: str = UNKNOWN) -> List[Ampersand]:
    """
    Every unescaped ``&`` in ``code`` with its verdict (see the module docstring).

    ``fragment_top`` is the verdict for an ``&`` at the top level of a file with
    no ``\\begin{document}``. Nothing in such a file says what encloses it — a
    chapter is ``\\input`` into prose, a rows file into a tabular — so it is
    ``unknown`` unless the caller has other evidence (TeX has just reported a
    misplaced ``&`` there).
    """
    if not code or "&" not in code:
        return []
    view = clean_latex_for_validation(code)
    if len(view) != len(code):
        return []

    starts = _line_starts(code)
    view_lines = view.split("\n")
    m_doc = _RE_BEGIN_DOC.search(view)
    body_start = m_doc.start() if m_doc else None
    n = len(view)
    out: List[Ampersand] = []

    def record(off: int, verdict: str, reason: str, construct=None) -> None:
        ln = bisect.bisect_right(starts, off)
        out.append(Ampersand(off, ln, off - starts[ln - 1] + 1, verdict, reason, construct))

    # Context stack, innermost last.
    #   environments: ("env", name, kind, open_start, open_end)
    #   brace groups: ("grp", owner, kind, args_left)
    stack: List[tuple] = []
    math_inline = False
    display_open: Optional[Tuple[str, str, int, int]] = None  # the \[ or $$ currently open
    math_depth = 0           # len(stack) when the open math was opened
    owner: Optional[str] = None   # command that owns the next brace group
    args_left = 0
    owner_at = 0
    adjacent = False         # the owner only holds across whitespace (argument 2, 3, ... of a command)

    def drop_owner() -> None:
        nonlocal owner, args_left, adjacent
        owner, args_left, adjacent = None, 0, False

    def math_env_open() -> bool:
        return any(e[0] == "env" and (e[2] == "dmath" or e[1] in MATH_ALIGNMENT_ENVS) for e in stack)

    i = 0
    while i < n:
        ch = view[i]
        if owner and i - owner_at > _OWNER_REACH:
            drop_owner()

        if ch == "\\":
            m = _RE_ENV.match(view, i)
            if m:
                name = m.group(2)
                drop_owner()
                i = m.end()
                if m.group(1) == "begin":
                    if name in ALIGNMENT_ENVS:
                        kind = "align"
                    elif name in DISPLAY_MATH_ENVS:
                        kind = "dmath"
                    elif name in TEXT_ENVS:
                        kind = "text"
                    else:
                        kind = "unknown"
                    stack.append(("env", name, kind, m.start(), m.end()))
                    if name == "frame":
                        # \begin{frame}<1->[fragile]{Title}{Subtitle}
                        owner, args_left, owner_at, adjacent = "frametitle", 2, i, False
                    else:
                        # \begin{tcolorbox}[title=A & B], \begin{tabular}[t]: options, not content.
                        j = i
                        while j < n and view[j] in " \t":
                            j += 1
                        if j < n and view[j] == "[":
                            close = _matching_bracket(view, j)
                            if close != -1:
                                i = close + 1
                else:
                    for k in range(len(stack) - 1, -1, -1):
                        if stack[k][0] == "env" and stack[k][1] == name:
                            del stack[k:]
                            break
                    if name == "frame":
                        math_inline, display_open = False, None
                continue
            nxt = view[i + 1] if i + 1 < n else ""
            if nxt in "[]()":
                if nxt == "[":
                    display_open, math_depth = ("bracket", "\\[", i, i + 2), len(stack)
                elif nxt == "]":
                    display_open = None
                elif nxt == "(":
                    math_inline, math_depth = True, len(stack)
                else:
                    math_inline = False
                drop_owner()
                i += 2
                continue
            m = _RE_CMD.match(view, i)
            if m:
                name = m.group(1)
                if "@" in name and name not in TEXT_COMMANDS:
                    # `\xymatrix@C=1pc{...}`: in a document body @ is not part of the name.
                    name = name.split("@", 1)[0] or name
                if name in _DECLARATIONS:
                    drop_owner()
                else:
                    owner = name
                    args_left = TEXT_COMMANDS.get(name) or _OPAQUE_COMMANDS.get(name) or 1
                    owner_at, adjacent = m.end(), False
                i = m.end()
                continue
            drop_owner()  # an escaped character: \&, \\, \{, \%
            i += 2
            continue

        if ch == "$":
            if view.startswith("$$", i):
                if display_open is None:
                    display_open, math_depth = ("dollars", "$$", i, i + 2), len(stack)
                else:
                    display_open = None
                i += 2
            else:
                math_inline = not math_inline
                if math_inline:
                    math_depth = len(stack)
                i += 1
            drop_owner()
            continue

        if ch == "{":
            own = owner if owner and args_left > 0 else None
            if own is None:
                kind = "bare"
            elif own in ALIGNMENT_COMMANDS:
                kind = "align"
            elif own in TEXT_COMMANDS:
                kind = "textarg"
            else:
                kind = "unknown"
            stack.append(("grp", own, kind, args_left))
            drop_owner()
            i += 1
            continue

        if ch == "}":
            drop_owner()
            for k in range(len(stack) - 1, -1, -1):
                if stack[k][0] == "env":
                    break
                _, own, kind, left = stack[k]
                del stack[k:]
                if own is not None:
                    if own in TEXT_COMMANDS or own in _OPAQUE_COMMANDS:
                        if left > 1:      # \multicolumn{2}{c}{...}: the next group is still its own
                            owner, args_left, owner_at, adjacent = own, left - 1, i + 1, True
                    elif kind == "unknown":
                        # \cventry{..}{..}{..}: every adjacent group belongs to the same command.
                        owner, args_left, owner_at, adjacent = own, 1, i + 1, True
                break
            i += 1
            continue

        if ch == "[" and owner:
            close = _matching_bracket(view, i)
            if close != -1:
                if owner in _TEXT_OPTIONAL:
                    # \item[R&D], \section[short & sweet]{...}: text.
                    for mm in _RE_UNESCAPED_AMP.finditer(view, i + 1, close):
                        record(mm.end() - 1, TEXT, f"inside the optional argument of \\{owner}")
                i = close + 1
                owner_at = i
                continue

        if ch == "&":
            verdict, reason, construct = UNKNOWN, "", None
            decided = False
            for k in range(len(stack) - 1, -1, -1):
                e = stack[k]
                kind = e[2]
                math_inside = (math_inline or display_open is not None) and math_depth > k
                if kind == "align":
                    verdict, reason = LEGAL, f"in {e[1]}"
                elif kind == "textarg":
                    if math_inside:
                        verdict, reason = UNKNOWN, "in math inside a text argument"
                    else:
                        label = "a frame title" if e[1] == "frametitle" else f"\\{e[1]}{{...}}"
                        verdict, reason = TEXT, f"inside {label}"
                elif kind == "unknown":
                    verdict, reason = UNKNOWN, f"inside {e[1]}"
                elif kind == "dmath":
                    verdict, reason = DISPLAY_MATH, f"in {e[1]} with no alignment environment"
                    construct = ("env", e[1], e[3], e[4])
                elif kind == "bare" and (math_inline or display_open is not None or math_env_open()):
                    # `\[ \mystack @C=1em { a & b } \]`: a bare group in math is somebody's alignment.
                    verdict, reason = UNKNOWN, "inside a brace group in math"
                else:
                    continue  # a bare group in text, or a text environment: judged by what encloses it
                decided = True
                break
            if not decided:
                if display_open is not None:
                    verdict, reason, construct = DISPLAY_MATH, "in display math with no alignment environment", display_open
                elif math_inline:
                    verdict, reason = UNKNOWN, "in inline math"
                elif body_start is None:
                    verdict, reason = fragment_top, "top level of a file with no \\begin{document}"
                    if verdict == TEXT:
                        reason = "in plain text"
                elif i < body_start:
                    verdict, reason = UNKNOWN, "in the preamble"
                else:
                    verdict, reason = TEXT, "in plain text"
            if verdict == TEXT and reason == "in plain text":
                ln = bisect.bisect_right(starts, i)
                if _looks_like_table_rows(view_lines, ln - 1):
                    verdict, reason = ROW_OUTSIDE_TABLE, "a table row outside any tabular environment"
            record(i, verdict, reason, construct)
            drop_owner()
            i += 1
            continue

        if ch == "\n":
            # A blank line ends a paragraph, and with it any inline math the model
            # forgot to close — otherwise one stray $ hides every later & as "math".
            j = i + 1
            while j < n and view[j] in " \t":
                j += 1
            if j < n and view[j] == "\n":
                math_inline, display_open = False, None
                drop_owner()
        elif ch == ";":
            drop_owner()  # end of a TikZ statement
        elif adjacent and not ch.isspace():
            drop_owner()
        i += 1

    out.sort(key=lambda a: a.offset)
    return out


def describe(amp: Ampersand) -> str:
    """One sentence for the model: what this ``&`` is and what to do about it."""
    if amp.verdict == TEXT:
        return f"this & is {amp.reason}, not a column separator: write \\&"
    if amp.verdict == DISPLAY_MATH:
        return (f"this & is {amp.reason}: use align, or put \\begin{{aligned}} ... \\end{{aligned}} "
                f"inside the equation")
    if amp.verdict == ROW_OUTSIDE_TABLE:
        return ("this looks like a table row outside any tabular environment: the "
                "\\begin{tabular}{...} line is missing or the table was closed too early")
    if amp.verdict == LEGAL:
        return f"this & is a column separator {amp.reason}; check the number of columns in this row"
    return f"this & is {amp.reason}"


def escape_misplaced_ampersands(code: str, lines: Optional[Iterable[int]] = None,
                                fragment_top: str = UNKNOWN) -> Tuple[str, List[str]]:
    """
    Writes ``\\&`` for every ``&`` that is certainly text (optionally only on the
    1-based ``lines``). Column separators and anything uncertain are not touched.
    """
    wanted = None if lines is None else set(lines)
    hits = [a for a in classify_ampersands(code, fragment_top)
            if a.verdict == TEXT and (wanted is None or a.line in wanted)]
    if not hits:
        return code, []
    parts = list(code)
    for a in sorted(hits, key=lambda a: a.offset, reverse=True):
        parts[a.offset] = "\\&"
    where = sorted({a.line for a in hits})
    shown = ", ".join(str(n) for n in where[:8]) + ("…" if len(where) > 8 else "")
    return "".join(parts), [f"Escaped {len(hits)} '&' used as text (line{'s' if len(where) != 1 else ''} {shown}) to '\\&'."]


_RE_NO_WRAP = re.compile(r"\\(?:tag|intertext|shortintertext)(?![A-Za-z])")
_RE_LEADING_LABEL = re.compile(r"\s*\\label\s*\{[^{}]*\}")


def wrap_unaligned_display_math(code: str, lines: Optional[Iterable[int]] = None) -> Tuple[str, List[str]]:
    """
    ``\\begin{equation} a &= b \\\\ c &= d \\end{equation}`` → the body goes inside
    ``aligned`` (``gather`` becomes ``align``).

    Nothing is added on a line of its own: the write gate keeps a repair only on
    lines the edit changed, and a wrapper on its own new line would be a line the
    edit did not write.
    """
    wanted = None if lines is None else set(lines)
    amps = [a for a in classify_ampersands(code) if a.verdict == DISPLAY_MATH and a.construct]
    if not amps:
        return code, []
    view = clean_latex_for_validation(code)
    by_construct: Dict[Tuple[str, str, int, int], List[Ampersand]] = {}
    for a in amps:
        by_construct.setdefault(a.construct, []).append(a)

    fixes: List[str] = []
    edits: List[Tuple[int, int, str]] = []  # (start, end, replacement)
    for (kind, name, open_start, open_end), members in by_construct.items():
        if wanted is not None and not any(a.line in wanted for a in members):
            continue
        if kind == "env":
            m_close = re.compile(r"\\end\s*\{\s*" + re.escape(name) + r"\s*\}").search(view, open_end)
        elif kind == "bracket":
            m_close = re.compile(r"(?<!\\)(?:\\\\)*\\\]").search(view, open_end)
        else:
            m_close = re.compile(r"\$\$").search(view, open_end)
        if not m_close:
            continue
        close_start = m_close.end() - 2 if kind != "env" else m_close.start()
        if _RE_NO_WRAP.search(view, open_end, close_start):
            continue  # \tag is not allowed inside aligned
        base = name.rstrip("*")
        star = "*" if name.endswith("*") else ""
        line_no = members[0].line
        if kind == "env" and base == "gather":
            edits.append((open_start, open_end, f"\\begin{{align{star}}}"))
            edits.append((m_close.start(), m_close.end(), f"\\end{{align{star}}}"))
            fixes.append(f"Changed gather to align around the '&' on line {line_no}.")
            continue
        if kind == "env" and base in ("multline", "math"):
            continue
        m_label = _RE_LEADING_LABEL.match(code, open_end) if kind == "env" else None
        insert_at = m_label.end() if m_label else open_end
        edits.append((insert_at, insert_at, "\\begin{aligned}"))
        edits.append((close_start, close_start, "\\end{aligned}"))
        what = f"\\begin{{{name}}}" if kind == "env" else name
        fixes.append(f"Wrapped the body of {what} in aligned (it uses '&' on line {line_no}).")

    if not edits:
        return code, []
    out = code
    for start, end, text in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        out = out[:start] + text + out[end:]
    return out, fixes


# Commands that leave TeX in vertical mode: `\\` after one of these is "There's no line here to end".
_VERTICAL_LEADERS = re.compile(
    r"^\s*\\(?:vspace|vskip|smallskip|medskip|bigskip|begin|end|section|subsection|subsubsection|chapter|"
    r"part|paragraph|maketitle|tableofcontents|newpage|clearpage|pagebreak|centering|raggedright|"
    r"raggedleft|label|caption|hline|toprule|midrule|bottomrule|setlength|input|include|par|hrule|"
    r"frametitle|titlepage|bibliography|printbibliography|usepackage|item\s*$)(?![A-Za-z])")
_RE_LONE_BACKSLASH = re.compile(r"(?<!\\)\\[ \t]*$")
_TEXTY_END = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,:;)!?}$'\"")


def terminate_lone_backslash_rows(code: str, lines: Optional[Iterable[int]] = None) -> Tuple[str, List[str]]:
    """
    Restores ``\\\\`` where a line ends in a single ``\\``.

    A model escaping LaTeX for JSON writes a row break as four backslashes and
    regularly slips to two, which decode to one. ``\\`` before a newline is a
    control space: nothing is reported there, but a table's rows are no longer
    terminated, so they merge and TeX reports *Extra alignment tab* (or
    *Misplaced \\noalign* at the next rule) rows later.

    Inside an alignment this is always the intent. In prose it is restored only
    where a line break can stand — text before it, more text after it — because
    ``\\\\`` with no line to end is itself an error.
    """
    if "\\" not in code:
        return code, []
    view = clean_latex_for_validation(code)
    if len(view) != len(code):
        return code, []
    wanted = None if lines is None else set(lines)
    view_lines = view.split("\n")
    starts = _line_starts(code)
    m_doc = _RE_BEGIN_DOC.search(view)
    first_line = bisect.bisect_right(starts, m_doc.start()) if m_doc else 0  # 0-based index of the body

    env_stack: List[str] = []
    hits: List[int] = []
    for idx, vline in enumerate(view_lines):
        in_alignment = any(e in ALIGNMENT_ENVS for e in env_stack)
        for m in _RE_ENV.finditer(vline):
            if m.group(1) == "begin":
                env_stack.append(m.group(2))
            elif m.group(2) in env_stack:
                while env_stack and env_stack.pop() != m.group(2):
                    pass
        if idx < first_line or (wanted is not None and (idx + 1) not in wanted):
            continue
        m = _RE_LONE_BACKSLASH.search(vline)
        if not m:
            continue
        before = vline[:m.start()].rstrip()
        if not before:
            continue
        if not in_alignment:
            following = view_lines[idx + 1] if idx + 1 < len(view_lines) else ""
            if (before[-1] not in _TEXTY_END or not following.strip()
                    or _VERTICAL_LEADERS.match(vline) or _RE_ENV.match(following.strip())):
                continue
        hits.append(starts[idx] + m.start())

    if not hits:
        return code, []
    out = code
    for off in sorted(hits, reverse=True):
        out = out[:off] + "\\" + out[off:]
    return out, [f"Restored {len(hits)} line/row break(s) written as a single '\\' (now '\\\\')."]


# ----------------------------------------------------------------------------
# Tables: columns declared vs cells written
# ----------------------------------------------------------------------------

_RE_TABULAR_BEGIN = re.compile(
    r"\\begin\s*\{(tabular\*|tabularx|tabulary|tabular|longtable|xltabular|supertabular|xtabular|array)\}")
_WIDTH_FIRST = frozenset({"tabular*", "tabularx", "tabulary", "xltabular"})
_RE_MULTICOLUMN = re.compile(r"\\multicolumn\s*\{\s*(\d+)\s*\}")
_RE_ROW_BREAK = re.compile(r"\\\\\*?|\\tabularnewline(?![A-Za-z])|\\cr(?![A-Za-z])")
_RE_ROW_NOISE = re.compile(
    r"\\(?:hline|toprule|midrule|bottomrule|addlinespace|endhead|endfirsthead|endfoot|endlastfoot|"
    r"cline\{[^}]*\}|cmidrule(?:\([^)]*\))?\{[^}]*\}|noalign\{[^}]*\})|\[[^\]]*\]")


@dataclass
class TabularInfo:
    env: str
    begin_line: int               # 1-based line of \begin{...}
    end_line: int
    spec_start: int               # offsets of the column specification, braces excluded
    spec_end: int
    columns: Optional[int]        # None when the specification could not be read with certainty
    rows: List[Tuple[int, int]]   # (line of the row, cells in it)

    @property
    def widest(self) -> int:
        return max((cells for _, cells in self.rows), default=0)

    @property
    def overflowing(self) -> List[Tuple[int, int]]:
        if self.columns is None:
            return []
        return [(ln, cells) for ln, cells in self.rows if cells > self.columns]


def _brace_end(text: str, open_pos: int) -> int:
    depth = 0
    i, n = open_pos, len(text)
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
    return -1


def count_columns(spec: str) -> Optional[int]:
    """Columns declared by a tabular column specification; None when it cannot be read."""
    count = 0
    i, n = 0, len(spec)
    while i < n:
        ch = spec[i]
        if ch in "|: \t\n":
            i += 1
        elif ch in "@!><":
            j = i + 1
            while j < n and spec[j] in " \t\n":
                j += 1
            if j >= n or spec[j] != "{":
                return None
            end = _brace_end(spec, j)
            if end == -1:
                return None
            i = end + 1
        elif ch == "*":
            j = spec.find("{", i)
            if j == -1:
                return None
            e1 = _brace_end(spec, j)
            if e1 == -1 or e1 + 1 >= n:
                return None
            k = e1 + 1
            while k < n and spec[k] in " \t\n":
                k += 1
            if k >= n or spec[k] != "{":
                return None
            e2 = _brace_end(spec, k)
            if e2 == -1:
                return None
            try:
                times = int(spec[j + 1:e1].strip())
            except ValueError:
                return None
            inner = count_columns(spec[k + 1:e2])
            if inner is None:
                return None
            count += times * inner
            i = e2 + 1
        elif ch.isalpha():
            count += 1
            i += 1
            # p{3cm}, w{c}{2cm}, D{.}{.}{2}, S[table-format=2.1], L{3cm}: arguments of the column type.
            while i < n and spec[i] in "{[":
                if spec[i] == "{":
                    end = _brace_end(spec, i)
                else:
                    end = spec.find("]", i)
                if end == -1:
                    return None
                i = end + 1
        else:
            return None
    return count or None


def find_tabulars(code: str) -> List[TabularInfo]:
    """Every tabular-like environment with its declared columns and the cells of each row."""
    if "\\begin" not in code:
        return []
    view = clean_latex_for_validation(code)
    if len(view) != len(code):
        return []
    starts = _line_starts(code)

    def line_of(off: int) -> int:
        return bisect.bisect_right(starts, off)

    found: List[TabularInfo] = []
    for m in _RE_TABULAR_BEGIN.finditer(view):
        env = m.group(1)
        i, n = m.end(), len(view)

        def skip_ws(j: int) -> int:
            while j < n and view[j] in " \t\n":
                j += 1
            return j

        i = skip_ws(i)
        if i < n and view[i] == "[":
            close = view.find("]", i)
            if close == -1:
                continue
            i = skip_ws(close + 1)
        if env in _WIDTH_FIRST:
            if i >= n or view[i] != "{":
                continue
            end = _brace_end(view, i)
            if end == -1:
                continue
            i = skip_ws(end + 1)
        if i >= n or view[i] != "{":
            continue
        spec_close = _brace_end(view, i)
        if spec_close == -1:
            continue
        spec_start, spec_end = i + 1, spec_close

        # The matching \end, counting nested environments of the same name.
        depth, body_end = 1, -1
        for e in re.finditer(r"\\(begin|end)\s*\{" + re.escape(env) + r"\}", view[spec_close:]):
            depth += 1 if e.group(1) == "begin" else -1
            if depth == 0:
                body_end = spec_close + e.start()
                break
        if body_end == -1:
            continue

        rows: List[Tuple[int, int]] = []
        brace = nested = 0
        row_start = j = spec_close + 1
        amps = 0
        first_amp = -1

        def close_row(upto: int) -> None:
            nonlocal amps, first_amp, row_start
            text = view[row_start:upto]
            if _RE_ROW_NOISE.sub("", text).strip() or amps:
                extra = sum(int(x) - 1 for x in _RE_MULTICOLUMN.findall(text))
                anchor = first_amp if first_amp != -1 else row_start + (len(text) - len(text.lstrip()))
                rows.append((line_of(anchor), 1 + amps + extra))
            amps, first_amp = 0, -1

        while j < body_end:
            ch = view[j]
            if ch == "\\":
                e = _RE_ENV.match(view, j)
                if e:
                    nested += 1 if e.group(1) == "begin" else -1
                    nested = max(nested, 0)
                    j = e.end()
                    continue
                rb = _RE_ROW_BREAK.match(view, j) if (brace == 0 and nested == 0) else None
                if rb:
                    close_row(j)
                    j = rb.end()
                    row_start = j
                    continue
                j += 2
                continue
            if ch == "{":
                brace += 1
            elif ch == "}":
                brace = max(brace - 1, 0)
            elif ch == "&" and brace == 0 and nested == 0:
                amps += 1
                if first_amp == -1:
                    first_amp = j
            j += 1
        close_row(body_end)

        found.append(TabularInfo(env, line_of(m.start()), line_of(body_end), spec_start, spec_end,
                                 count_columns(view[spec_start:spec_end]), rows))
    return found


def widen_tabular_columns(code: str, lines: Optional[Iterable[int]] = None) -> Tuple[str, List[str]]:
    """
    Adds columns to a specification that declares fewer than its widest row uses
    (*Extra alignment tab has been changed to \\cr*). Content is never dropped:
    the row keeps every cell and the table gains the column it was written for.

    With ``lines``, only tables that have an overflowing row — or their
    ``\\begin`` — on one of those 1-based lines are changed.
    """
    wanted = None if lines is None else set(lines)
    edits: List[Tuple[int, str]] = []
    fixes: List[str] = []
    for t in find_tabulars(code):
        over = t.overflowing
        if not over:
            continue
        if wanted is not None and not (t.begin_line in wanted or any(ln in wanted for ln, _ in over)):
            continue
        spec = code[t.spec_start:t.spec_end]
        missing = t.widest - (t.columns or 0)
        letters = [c for c in re.sub(r"[@!><]\s*\{[^{}]*\}", "", spec) if c.isalpha()]
        col = letters[-1] if letters and letters[-1] in "lcr" else "l"
        tail = spec.rstrip()
        insert_at = len(tail)
        m_at = re.search(r"@\s*\{[^{}]*\}$", tail)
        if m_at:
            insert_at = m_at.start()
            tail = tail[:insert_at].rstrip()
        addition = (col + "|") * missing if tail.endswith("|") else col * missing
        edits.append((t.spec_start + insert_at, addition))
        fixes.append(f"Widened \\begin{{{t.env}}} on line {t.begin_line} from {t.columns} to {t.widest} "
                     f"columns (a row has {t.widest} cells).")
    if not edits:
        return code, []
    out = code
    for off, text in sorted(edits, reverse=True):
        out = out[:off] + text + out[off:]
    return out, fixes


def probable_alignment_tab_lines(code: str) -> List[Tuple[int, str]]:
    """
    Lines that will raise an alignment-tab error, with the reason, for the cases
    where TeX's own location is not available (a pasted log, a summary).
    """
    if not code:
        return []
    found: Dict[int, str] = {}
    for a in classify_ampersands(code):
        if a.verdict == TEXT:
            found.setdefault(a.line, "Bare '&' found in text outside tabular/align environment. Escape as '\\&'.")
        elif a.verdict == DISPLAY_MATH:
            found.setdefault(a.line, "'&' in display math with no alignment environment. Use align, or "
                                     "aligned inside the equation.")
        elif a.verdict == ROW_OUTSIDE_TABLE:
            found.setdefault(a.line, "Table row outside any tabular environment (the \\begin{tabular}{...} "
                                     "line is missing or the table was closed too early).")
    for t in find_tabulars(code):
        for ln, cells in t.overflowing:
            found.setdefault(ln, f"Row has {cells} columns ({cells - 1} '&'), but {t.env} on line "
                                 f"{t.begin_line} only defines {t.columns} columns.")
    return sorted(found.items())
