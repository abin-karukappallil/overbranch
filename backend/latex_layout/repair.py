"""
repair.py — The smallest LaTeX change that fixes a layout defect.

Every repair here is a closed, structured operation over a known source span.
The model never writes LaTeX for these: it decides *that* a document should be
tidied, and this module decides *how*, from the measured defect. That is what
keeps "fix the formatting" from turning into a rewrite.

Two rules are enforced in code rather than asked for in a prompt, because a
prompt cannot guarantee either:

* **The text never changes.** Every operation is checked with
  ``preserves_text``: the visible characters before and after must be equal
  once the inserted break commands are removed. A repair that would drop,
  reword or truncate content is discarded, whatever it would do for the layout.
* **Type is never shrunk to fit.** ``\\small``, ``\\scriptsize``, ``\\tiny``,
  ``\\fontsize`` and any change to the page geometry are forbidden outputs. A
  local overflow gets a local fix; it is not an excuse to restyle the document.

The fixes are ordered cheapest and least visible first: a break opportunity
inside one over-long token costs the reader nothing, a column specification
change costs a little, and converting a table environment costs the most.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .issues import (CODE_WRAP, COLUMN_IMBALANCE, LONG_IDENTIFIER, LONG_PATH, LONG_URL,
                     MARGIN_VIOLATION, OVERFLOW, TABLE_CELL_OVERFLOW, TABLE_WIDTH,
                     VERTICAL_OVERFLOW, LayoutIssue, classify_token)
from .metrics import latex_to_plain

logger = logging.getLogger("latex_layout.repair")

# Never emitted by a layout repair, at any severity. Making the page fit by
# shrinking the type or moving the margins is a restyle, not a repair.
FORBIDDEN = re.compile(r"\\(?:tiny|scriptsize|footnotesize|small|fontsize|linespread"
                       r"|(?:new|restore)?geometry|baselinestretch"
                       r"|setlength\s*\{\s*\\(?:textwidth|textheight|oddsidemargin|hoffset|parindent))\b")

BREAK = "\\allowbreak{}"
_SEPARATORS = "/-_.:,=&?@+"
# Where a technical token may be broken without a hyphen appearing. A hyphen
# would be read as part of the identifier, which is why \- is never used here.
_RE_SEP = re.compile(r"([/\-_.:,=?@+])(?=[^\s])")
_RE_CAMEL_BREAK = re.compile(r"(?<=[a-z0-9])(?=[A-Z][a-z])")

MIN_PIECE = 3          # don't offer a break that leaves a 1-2 character orphan


@dataclass
class RepairOp:
    """One concrete edit: replace ``code[start:end]`` with ``new_text``."""
    kind: str
    start: int
    end: int
    new_text: str
    description: str
    needs_packages: List[str] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> Dict[str, object]:
        return {"kind": self.kind, "description": self.description,
                "needs_packages": list(self.needs_packages),
                "chars": [self.start, self.end], "note": self.note}


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

_RE_BREAKCMD = re.compile(r"\\(?:allowbreak|linebreak|nolinebreak|hspace\*?\{0pt\}|discretionary\{\}\{\}\{\})(?:\{\})?")


_RE_BEGIN_END = re.compile(r"\\(?:begin|end)\s*\{[^}]*\}")


def _strip_env_args(code: str) -> str:
    """
    ``\\begin{env}`` with *all* of its arguments removed, not just one.

    ``latex_to_plain`` drops one optional and one mandatory argument, which is
    right for most environments but leaves the column specification of
    ``\\begin{tabularx}{\\textwidth}{|l|X|}`` behind as visible text — so a
    tabular→tabularx conversion looked like it had *added* the characters
    "|l|X|" to the document and was rejected as changing the content.
    """
    out: List[str] = []
    i = 0
    while i < len(code):
        m = _RE_BEGIN_END.search(code, i)
        if not m:
            out.append(code[i:])
            break
        out.append(code[i:m.start()])
        j = m.end()
        while j < len(code):
            k = j
            while k < len(code) and code[k] in " \t":
                k += 1
            if k < len(code) and code[k] == "{":
                j = _skip_group(code, k)
            elif k < len(code) and code[k] == "[":
                close = code.find("]", k)
                if close < 0:
                    break
                j = close + 1
            else:
                break
        i = j
    return "".join(out)


def _visible(code: str) -> str:
    """The characters a reader would see, with inserted break commands removed."""
    stripped = _strip_env_args(_RE_BREAKCMD.sub("", code))
    return re.sub(r"\s+", "", latex_to_plain(stripped))


def preserves_text(before: str, after: str) -> bool:
    """
    True when ``after`` says exactly what ``before`` said.

    This is the mechanical form of "same information, better presentation": a
    repair that deletes half a description to make the page fit passes every
    compile and geometry check there is, and only this stops it.
    """
    return _visible(before) == _visible(after)


def is_safe_output(text: str) -> bool:
    return not FORBIDDEN.search(text)


# ---------------------------------------------------------------------------
# Break opportunities inside one token
# ---------------------------------------------------------------------------

def add_break_points(token: str) -> str:
    """
    ``token`` with break opportunities after its separators, and at camelCase
    boundaries when it has no separators at all.

    ``\\allowbreak`` is a zero-width penalty: it adds no character, so the
    identifier still reads exactly as written when it does not break, and
    shows no hyphen when it does. ``\\-`` (the obvious alternative) inserts a
    *visible* hyphen, which inside ``device_network_connections`` or a file
    path invents punctuation that is not in the data.
    """
    if BREAK in token or "\\" in token:
        return token

    def place(m: "re.Match") -> str:
        i = m.end()
        # Don't strand a tiny fragment at either end of the line.
        if i < MIN_PIECE or len(token) - i < MIN_PIECE:
            return m.group(0)
        return m.group(1) + BREAK

    out = _RE_SEP.sub(place, token)
    if out == token:
        pieces = []
        last = 0
        for m in _RE_CAMEL_BREAK.finditer(token):
            if m.start() >= MIN_PIECE and len(token) - m.start() >= MIN_PIECE:
                pieces.append(token[last:m.start()])
                last = m.start()
        if pieces:
            pieces.append(token[last:])
            out = BREAK.join(pieces)
    return out


_RE_TECH = re.compile(r"[A-Za-z0-9_~./:\\\\@+-]{8,}")


def _source_token_candidates(rendered: str) -> List[str]:
    """Long technical tokens of a rendered line, longest first."""
    seen: List[str] = []
    for m in _RE_TECH.finditer(rendered or ""):
        t = m.group(0).strip(".,;:()[]{}")
        if len(t) >= 8 and classify_token(t) and t not in seen:
            seen.append(t)
    return sorted(seen, key=len, reverse=True)


def _find_in_source(code: str, token: str, lo: int, hi: int) -> Optional[Tuple[int, int]]:
    """
    Where ``token`` sits in ``code[lo:hi]``, allowing for LaTeX escaping of the
    characters PyMuPDF gives back unescaped (``_`` renders as ``_`` but is
    written ``\\_``). Only an unambiguous single occurrence is accepted.
    """
    region = code[lo:hi]
    # PyMuPDF gives the token as the reader sees it ("device_network_connections");
    # the source writes LaTeX's specials escaped ("device\_network\_connections").
    # Build a pattern that accepts either. (re.escape is no help for this: since
    # Python 3.7 it does not escape "_" at all, so the obvious
    # `re.escape(token).replace(r"\_", ...)` substitution never matched anything
    # and every identifier in a table was reported unlocatable.)
    specials = set("_%&#${}")
    tolerant = "".join(("\\\\?" + re.escape(c)) if c in specials else re.escape(c) for c in token)
    for pat in (re.escape(token), tolerant):
        hits = [m.span() for m in re.finditer(pat, region)]
        if len(hits) == 1:
            return hits[0][0] + lo, hits[0][1] + lo
    return None


# ---------------------------------------------------------------------------
# Column specifications
# ---------------------------------------------------------------------------

@dataclass
class Column:
    """
    One column of a tabular preamble, with its decorations kept apart from the
    column letter itself.

    They have to be separable: replacing the whole entry ``|l|`` with an ``X``
    silently deletes the two vertical rules around that column, so a table
    that was ruled comes back unruled — a visible change to a document nobody
    asked to restyle.
    """
    pre: str = ""      # "|", "@{}", ">{...}" preceding the column
    core: str = ""     # "l", "c", "r", "X", "p{3cm}", ...
    post: str = ""     # "|", "<{...}" following it
    kind: str = "other"

    @property
    def spec(self) -> str:
        return self.pre + self.core + self.post

    def replaced_with(self, core: str) -> str:
        """This column's spec with a different column type, decorations kept."""
        return self.pre + core + self.post


def parse_colspec(spec: str) -> List[Column]:
    """
    The column entries of a tabular preamble. ``|``, ``@{...}``, ``!{...}`` and
    ``>{...}`` attach to the column they precede; a trailing ``|`` or ``<{...}``
    attaches to the column it follows.
    """
    cols: List[Column] = []
    i, n = 0, len(spec)
    pending = ""
    while i < n:
        c = spec[i]
        if c.isspace():
            i += 1
            continue
        if c == "|":
            # A bar after a column belongs to it; a bar with no column yet is a prefix.
            if cols and not pending:
                cols[-1].post += "|"
            else:
                pending += "|"
            i += 1
            continue
        if c == "<":
            j = _skip_group(spec, i + 1)
            if cols and not pending:
                cols[-1].post += spec[i:j]
            else:
                pending += spec[i:j]
            i = j
            continue
        if c in "@!>":
            j = _skip_group(spec, i + 1)
            pending += spec[i:j]
            i = j
            continue
        if c == "*":                      # *{n}{cols} — expanded verbatim
            j = _skip_group(spec, i + 1)
            k = _skip_group(spec, j)
            rep = spec[i + 1:j].strip("{}")
            inner = spec[j:k].strip("{}")
            try:
                for _ in range(int(rep)):
                    for sub in parse_colspec(inner):
                        cols.append(Column(pending + sub.pre, sub.core, sub.post, sub.kind))
                        pending = ""
            except ValueError:
                cols.append(Column(pending, spec[i:k], "", "other"))
                pending = ""
            i = k
            continue
        if c in "pmb":
            j = _skip_group(spec, i + 1)
            cols.append(Column(pending, spec[i:j], "", c))
            pending = ""
            i = j
            continue
        cols.append(Column(pending, c, "", c if c in "lcrX" else "other"))
        pending = ""
        i += 1
    if pending:
        if cols:
            cols[-1].post += pending
        else:
            cols.append(Column("", pending, "", "other"))
    return cols


def _skip_group(s: str, i: int) -> int:
    """Index just past a balanced {...} starting at or after ``i``."""
    while i < len(s) and s[i].isspace():
        i += 1
    if i >= len(s) or s[i] != "{":
        return min(i + 1, len(s))
    depth = 0
    while i < len(s):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(s)


RAGGED_X_CORE = ">{\\raggedright\\arraybackslash}X"


# ---------------------------------------------------------------------------
# Tables in the source
# ---------------------------------------------------------------------------

@dataclass
class TabularSpan:
    start: int          # offset of \begin{tabular}
    end: int            # offset just past \end{tabular}
    env: str
    spec: str
    spec_start: int
    spec_end: int
    body_start: int
    body_end: int


_RE_TABULAR = re.compile(r"\\begin\s*\{(tabular\*?|tabularx|longtable|array)\}")


def find_tabular(code: str, lo: int = 0, hi: Optional[int] = None) -> Optional[TabularSpan]:
    """The first tabular-like environment overlapping ``code[lo:hi]``."""
    hi = len(code) if hi is None else hi
    for m in _RE_TABULAR.finditer(code):
        env = m.group(1)
        i = m.end()
        if env in ("tabularx", "tabular*"):       # takes a width argument first
            i = _skip_group(code, i)
        while i < len(code) and code[i].isspace():
            i += 1
        if i < len(code) and code[i] == "[":      # optional vertical position
            j = code.find("]", i)
            i = j + 1 if j > 0 else i
        spec_start = i
        spec_end = _skip_group(code, i)
        close = code.find(f"\\end{{{env}}}", spec_end)
        if close < 0:
            continue
        end = close + len(f"\\end{{{env}}}")
        if end <= lo or m.start() >= hi:
            continue
        return TabularSpan(m.start(), end, env, code[spec_start:spec_end].strip("{} \n"),
                           spec_start, spec_end, spec_end, close)
    return None


def _rows(body: str) -> List[List[str]]:
    """Cells of a tabular body, by row then column."""
    clean = re.sub(r"\\(?:hline|toprule|midrule|bottomrule|cline\s*\{[^}]*\})", "", body)
    out = []
    for raw in re.split(r"\\\\(?:\s*\[[^\]]*\])?", clean):
        if raw.strip():
            out.append([c.strip() for c in re.split(r"(?<!\\)&", raw)])
    return out


def widest_column(body: str, n_cols: int) -> int:
    """Index of the column carrying the most text — the one that should flex."""
    totals = [0] * max(n_cols, 1)
    for row in _rows(body):
        for i, cell in enumerate(row[:n_cols]):
            totals[i] += len(latex_to_plain(cell))
    return totals.index(max(totals)) if totals else 0


def column_of_text(body: str, needle: str, n_cols: int) -> Optional[int]:
    """Which column a rendered cell's text sits in, if it can be told."""
    probe = re.sub(r"\s+", "", latex_to_plain(needle))[:40]
    if len(probe) < 6:
        return None
    for row in _rows(body):
        for i, cell in enumerate(row[:n_cols]):
            if probe in re.sub(r"\s+", "", latex_to_plain(cell)):
                return i
    return None


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

def _token_repair(issue: LayoutIssue, code: str, lo: int, hi: int) -> List[RepairOp]:
    """
    Give every over-long token on an overflowing line somewhere to break.

    All of them, not just the first: one line of a technical document often
    carries three file paths, and fixing one at a time would need a compile
    and a re-measure per path to discover the line is still too wide.
    """
    ops: List[RepairOp] = []
    taken: List[Tuple[int, int]] = []
    for token in _source_token_candidates(issue.text):
        span = _find_in_source(code, token, lo, hi)
        if not span or any(not (span[1] <= a or span[0] >= b) for a, b in taken):
            continue
        original = code[span[0]:span[1]]
        fixed = add_break_points(original)
        if fixed == original:
            continue
        if not preserves_text(original, fixed) or not is_safe_output(fixed):
            continue
        taken.append(span)
        kind = classify_token(token) or LONG_IDENTIFIER
        ops.append(RepairOp(
            kind=kind, start=span[0], end=span[1], new_text=fixed,
            description=(f"Added break opportunities inside '{token[:60]}' so it can wrap "
                         f"instead of running past the margin."),
            note="\\allowbreak adds no character: the token is unchanged when it does not break."))
    return ops


def _url_repair(issue: LayoutIssue, code: str, lo: int, hi: int) -> List[RepairOp]:
    """A bare URL in prose becomes \\url{...}, which knows how to break one."""
    for token in _source_token_candidates(issue.text):
        if classify_token(token) != LONG_URL:
            continue
        span = _find_in_source(code, token, lo, hi)
        if not span or "\\" in code[span[0]:span[1]]:
            continue
        before = code[max(lo, span[0] - 12):span[0]]
        if re.search(r"\\(?:url|path|href|texttt|verb)\s*\{?$", before):
            continue                       # already inside a command that owns it
        new = f"\\url{{{code[span[0]:span[1]]}}}"
        return [RepairOp(kind=LONG_URL, start=span[0], end=span[1], new_text=new,
                        description=f"Wrapped the URL '{token[:60]}' in \\url{{}} so it can break.",
                        needs_packages=["url"])]
    return []


_RE_IN_TABULAR = re.compile(r"\\(begin|end)\s*\{(tabular\*?|tabularx|longtable|array)\}")


def inside_tabular(code: str, pos: int) -> bool:
    """Whether ``pos`` lies between a tabular-like \\begin and its \\end."""
    depth = 0
    for m in _RE_IN_TABULAR.finditer(code, 0, max(pos, 0)):
        depth += 1 if m.group(1) == "begin" else -1
    return depth > 0


_RE_TEXT_CMD = re.compile(r"\\[A-Za-z@]+\*?\s*(?:\[[^\]]*\])?\s*$")


def _in_command_argument(code: str, pos: int) -> bool:
    """True when ``pos`` sits inside the braced argument of a LaTeX command."""
    depth = 0
    i = pos - 1
    lo = max(0, pos - 4000)
    while i >= lo:
        c = code[i]
        if c == "}" and (i == 0 or code[i - 1] != "\\"):
            depth += 1
        elif c == "{" and (i == 0 or code[i - 1] != "\\"):
            if depth == 0:
                return bool(_RE_TEXT_CMD.search(code[max(0, i - 80):i]))
            depth -= 1
        i -= 1
    return False


_RE_STRUCTURAL = re.compile(r"\\(?:documentclass|usepackage|begin\s*\{document\}|end\s*\{document\}"
                            r"|begin\s*\{(?:tabular\*?|tabularx|longtable|array|verbatim|lstlisting)\})")


def paragraph_bounds(code: str, anchor: int) -> Optional[Tuple[int, int]]:
    """
    The blank-line-delimited paragraph containing ``anchor``, or None when
    that region is not plain running text.

    The search runs over the whole document, never over the caller's span.
    The span handed in is wherever the *defect* was located — often a single
    matched phrase — and clipping to it wraps that phrase alone, which both
    fails to help (TeX needs the whole paragraph to re-break it) and can cut
    a command in half. The guards below, not the span, are what keep the fix
    from escaping into the preamble or a table cell.
    """
    para_start = code.rfind("\n\n", 0, anchor)
    para_start = 0 if para_start < 0 else para_start + 2
    para_end = code.find("\n\n", anchor)
    para_end = len(code) if para_end < 0 else para_end
    # Never cross a \begin{document} / \end{document} or swallow the preamble.
    for m in re.finditer(r"\\(?:begin|end)\s*\{document\}", code):
        if para_start <= m.start() < para_end:
            if m.start() < anchor:
                para_start = m.end()
            else:
                para_end = m.start()
    region = code[para_start:para_end]
    if not region.strip() or _RE_STRUCTURAL.search(region):
        return None
    return para_start, para_end


def _paragraph_repair(issue: LayoutIssue, code: str, lo: int, hi: int) -> List[RepairOp]:
    """
    Prose that will not fit gets more room to stretch, not a smaller font.

    ``sloppypar`` lets TeX loosen interword spacing on the one paragraph that
    needs it — what a typesetter does by hand — instead of shrinking the type
    or widening the page, both of which would be visible everywhere else.
    """
    anchor = None
    for token in _source_token_candidates(issue.text):
        span = _find_in_source(code, token, lo, hi)
        if span:
            anchor = span[0]
            break
    if anchor is None:
        probe = re.sub(r"\s+", " ", (issue.text or "").strip())[:40]
        if len(probe) >= 12:
            at = code.find(probe, lo, hi)
            anchor = at if at >= 0 else None
    if anchor is None:
        anchor = lo if lo > 0 else None
    if anchor is None:
        return []

    # A paragraph environment cannot go inside a table cell or a command
    # argument: \\begin{sloppypar} between \\texttt{ and } is not a layout fix,
    # it is broken LaTeX that happens to compile. Overflow inside a table is a
    # table problem and is handled by the column repair instead.
    if inside_tabular(code, anchor) or _in_command_argument(code, anchor):
        return []
    bounds = paragraph_bounds(code, anchor)
    if bounds is None:
        return []
    ps, pe = bounds
    para = code[ps:pe]
    if "\\emergencystretch" in para or "sloppypar" in para:
        return []
    new = "\\begin{sloppypar}\n" + para.strip("\n") + "\n\\end{sloppypar}"
    if not preserves_text(para, new) or not is_safe_output(new):
        return []
    return [RepairOp(kind=OVERFLOW, start=ps, end=pe, new_text=new,
                     description="Allowed this paragraph looser interword spacing so TeX can break it.",
                     note="Scoped to the one paragraph; no font size or margin was changed.")]


def _table_repair(issue: LayoutIssue, code: str, lo: int, hi: int) -> List[RepairOp]:
    """
    A table too wide for the page gets a column that can flex, not smaller type.

    ``tabularx`` with an ``X`` column makes the table exactly ``\\textwidth``
    and gives the overrun to the column that holds the prose, which is the
    column a human would widen.
    """
    tab = find_tabular(code, lo, hi)
    if tab is None:
        return []
    cols = parse_colspec(tab.spec)
    if not cols:
        return []
    body = code[tab.body_start:tab.body_end]

    if tab.env in ("tabularx", "longtable") and any(c.kind == "X" for c in cols):
        target = column_of_text(body, issue.text, len(cols))
        if target is None or cols[target].kind != "X" or "raggedright" in cols[target].spec:
            return []
        spec = "".join(c.replaced_with(RAGGED_X_CORE) if i == target else c.spec
                       for i, c in enumerate(cols))
        return [RepairOp(kind=TABLE_CELL_OVERFLOW, start=tab.spec_start, end=tab.spec_end,
                        new_text="{" + spec + "}",
                        description=f"Let column {target + 1} wrap ragged-right instead of overflowing.",
                        needs_packages=["array", "tabularx"])]

    if tab.env != "tabular":
        return []
    target = column_of_text(body, issue.text, len(cols)) if issue.text else None
    if target is None or cols[target].kind not in ("l", "c", "r"):
        target = widest_column(body, len(cols))
    if cols[target].kind not in ("l", "c", "r"):
        return []
    spec = "".join(c.replaced_with(RAGGED_X_CORE) if i == target else c.spec
                   for i, c in enumerate(cols))
    new = (f"\\begin{{tabularx}}{{\\textwidth}}{{{spec}}}"
           + code[tab.body_start:tab.body_end] + "\\end{tabularx}")
    old = code[tab.start:tab.end]
    if not preserves_text(old, new) or not is_safe_output(new):
        return []
    return [RepairOp(kind=TABLE_WIDTH, start=tab.start, end=tab.end, new_text=new,
                    description=(f"Converted the tabular to tabularx at \\textwidth and let column "
                                 f"{target + 1} take the slack, so the table fits the text block."),
                    needs_packages=["tabularx", "array"],
                    note="Column content is unchanged; only the column specification differs.")]


def _longtable_repair(issue: LayoutIssue, code: str, lo: int, hi: int) -> List[RepairOp]:
    """
    A table taller than the page becomes a longtable, so it breaks across
    pages instead of running over the footer.

    A plain ``tabular`` is one unbreakable box: TeX cannot split it, so it
    overprints whatever is below. ``longtable`` is the mechanism LaTeX has for
    this, and ``\\endhead`` repeats the header row on each new page.
    """
    tab = find_tabular(code, lo, hi)
    if tab is None or tab.env not in ("tabular", "tabularx"):
        return []
    cols = parse_colspec(tab.spec)
    if not cols:
        return []
    body = code[tab.body_start:tab.body_end]
    # Repeat the header: everything up to and including the first row break.
    m = re.search(r"\\\\(?:\s*\[[^\]]*\])?\s*(?:\\hline|\\midrule|\\toprule)*", body)
    head, rest = (body[:m.end()], body[m.end():]) if m else ("", body)
    spec = "".join(c.spec for c in cols)
    new = (f"\\begin{{longtable}}{{{spec}}}\n" + head.strip("\n")
           + ("\n\\endhead\n" if head.strip() else "\n") + rest.strip("\n") + "\n\\end{longtable}")
    old = code[tab.start:tab.end]
    if not preserves_text(old, new) or not is_safe_output(new):
        return []
    return [RepairOp(kind=VERTICAL_OVERFLOW, start=tab.start, end=tab.end, new_text=new,
                    description=("Converted the table to a longtable so it breaks across pages "
                                 "instead of running over the page bottom; the header row repeats."),
                    needs_packages=["longtable"],
                    note="Rows and cell content are unchanged.")]


# Cheapest and least visible first: a break opportunity inside one token costs
# the reader nothing; converting a table environment costs the most.
_LADDER: Dict[str, List] = {
    LONG_PATH: [_token_repair],
    LONG_IDENTIFIER: [_token_repair],
    CODE_WRAP: [_token_repair],
    LONG_URL: [_url_repair, _token_repair],
    MARGIN_VIOLATION: [_url_repair, _token_repair, _paragraph_repair],
    OVERFLOW: [_url_repair, _token_repair, _paragraph_repair],
    TABLE_WIDTH: [_table_repair],
    TABLE_CELL_OVERFLOW: [_table_repair, _token_repair],
    COLUMN_IMBALANCE: [_table_repair],
    VERTICAL_OVERFLOW: [_longtable_repair],
}

def plan_repairs(issue: LayoutIssue, code: str, span: Tuple[int, int]) -> List[RepairOp]:
    """
    The smallest safe repairs for ``issue`` within ``code[span[0]:span[1]]``.

    An empty list is a normal outcome and strictly better than a speculative
    edit: the issue is then reported to the user unrepaired.
    """
    lo, hi = max(0, span[0]), min(len(code), span[1])
    if lo >= hi:
        return []
    ladder = list(_LADDER.get(issue.type, []))
    # Text overflowing inside a table is a table problem. Giving a token break
    # opportunities does nothing in an `l` column, which never wraps at all —
    # the column specification has to change first, so try that first.
    if issue.type in (MARGIN_VIOLATION, OVERFLOW) and inside_tabular(code, lo):
        ladder = [_table_repair] + [f for f in ladder if f is not _table_repair]
    for strategy in ladder:
        try:
            ops = strategy(issue, code, lo, hi)
        except Exception as e:
            logger.debug(f"{strategy.__name__} failed on {issue.type}: {e}")
            continue
        ops = [o for o in (ops or []) if is_safe_output(o.new_text)]
        if ops:
            return ops
    return []


def plan_repair(issue: LayoutIssue, code: str, span: Tuple[int, int]) -> Optional[RepairOp]:
    """The first repair ``plan_repairs`` would make, or None."""
    ops = plan_repairs(issue, code, span)
    return ops[0] if ops else None
