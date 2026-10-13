r"""
`humanize_content` — turn generated prose into writing that reads as a person's.

WHY THIS IS A TOOL AND NOT A PROMPT
-----------------------------------
"Make this not sound like AI" asked of the model editing the document produces a
rewrite of the document: headings reworded, citations dropped, numbers rounded,
a table turned into a sentence. The request is about *wording*, and everything
else must come out byte-identical — which is a property that can be measured,
and therefore a property a tool can be made to guarantee instead of asked for.

So the work is split the way every other verified edit in this codebase is:

  this module decides WHAT may be rewritten (bulk prose, and nothing else),
  the LLM supplies the new wording for one passage at a time,
  this module decides whether to KEEP it (structure, facts and meaning intact,
  and measurably less of the register that gives generated text away).

THREE DECISIONS THAT ARE LOAD-BEARING
-------------------------------------
1. **Titles, names and references are not prose.** A heading is how a block is
   tracked (the locator, the expansion worklist and the node IDs all key off
   it); an author is a person's name; `\cite{ou2023}` is a key, not a word. All
   of them are hard boundaries a rewritable span cannot cross, together with
   math, tables, TikZ, listings, the preamble and the bibliography. What is left
   is running text — which is what the request is about.

2. **A rewrite is verified against the original, not trusted.** Every command
   token, every math segment, every citation/label/reference call, every number
   and every acronym of the passage must still be there, in the same order,
   and the brace/math balance must be unchanged (`preserve_structure`). A
   passage that fails keeps its original text and is reported — the same
   discipline as `latex_layout.repair.preserves_text`, for the same reason: a
   layout or wording improvement that quietly drops content is not an
   improvement.

3. **"Sounds like AI" is measured, not asserted.** `slop_score` counts the
   register that marks generated prose — the stock phrases, the connective at
   the head of every sentence, the three-item list, the uniform sentence
   length — per hundred words. A rewrite is kept only when that number falls
   (or was already low, in which case the passage was human to begin with and
   is left alone). The same measure runs again after the edit, so the run can
   state what the document scores rather than claiming it was humanized.

Nothing here lowers `\small`, moves a margin or touches a figure: the output is
the same document with the same information, worded differently.
"""
from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .shadow_workspace import ShadowWorkspace

logger = logging.getLogger("opencode.humanize")

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
# Characters of prose per LLM call. Large enough that a 60-page report is a
# handful of calls, small enough that one bad reply costs little.
HUMANIZE_BATCH_CHARS = int(os.getenv("HUMANIZE_BATCH_CHARS", "6000") or 6000)
HUMANIZE_CONCURRENCY = max(1, int(os.getenv("HUMANIZE_CONCURRENCY", "4") or 4))
# Retries for a batch whose passages failed verification, with the reasons.
HUMANIZE_MAX_REPAIRS = max(0, int(os.getenv("HUMANIZE_MAX_REPAIRS", "1") or 1))
# A passage is in compliance at or below this slop score (markers per 100 words).
HUMANIZE_TARGET_SLOP = float(os.getenv("HUMANIZE_TARGET_SLOP", "1.5") or 1.5)
# …or when the rewrite takes it to this share of what it was.
HUMANIZE_MIN_DROP_RATIO = float(os.getenv("HUMANIZE_MIN_DROP_RATIO", "0.6") or 0.6)
# Below this many words a run of text is a label or a fragment, not bulk prose.
HUMANIZE_MIN_SPAN_WORDS = max(4, int(os.getenv("HUMANIZE_MIN_SPAN_WORDS", "12") or 12))
# A passage longer than this is split on sentence boundaries, so one reply is
# never asked to reproduce several pages verbatim-but-reworded.
HUMANIZE_MAX_SPAN_CHARS = int(os.getenv("HUMANIZE_MAX_SPAN_CHARS", "1800") or 1800)
# Spans per write. One splice per group bounds the number of whole-document
# validations; a group that fails validation is retried span by span.
HUMANIZE_WRITE_GROUP = max(1, int(os.getenv("HUMANIZE_WRITE_GROUP", "12") or 12))
# A rewrite may not change a passage's length beyond these ratios: much shorter
# is a summary, much longer is padding. Both are failures of "same meaning".
HUMANIZE_MIN_LENGTH_RATIO = 0.70
HUMANIZE_MAX_LENGTH_RATIO = 1.45


# ---------------------------------------------------------------------------
# What may be rewritten
# ---------------------------------------------------------------------------
# Environments whose body is not running prose. A span never crosses into one.
_SKIP_ENVS = frozenset({
    "tabular", "tabular*", "tabularx", "longtable", "array", "matrix", "bmatrix",
    "pmatrix", "vmatrix", "Vmatrix", "smallmatrix", "align", "align*", "alignat",
    "alignat*", "aligned", "gather", "gather*", "gathered", "multline", "multline*",
    "equation", "equation*", "eqnarray", "eqnarray*", "displaymath", "math",
    "split", "cases", "tikzpicture", "pgfpicture", "axis", "picture", "verbatim",
    "verbatim*", "semiverbatim", "Verbatim", "BVerbatim", "LVerbatim", "alltt",
    "lstlisting", "minted", "listing", "comment", "filecontents", "filecontents*",
    "thebibliography", "titlepage", "tabbing", "algorithmic", "algorithm",
    "algorithm2e", "forest", "circuitikz", "tcolorbox",
})

# Commands whose brace arguments are titles, names, keys or paths — never prose.
# The count is how many consecutive brace groups belong to the command.
#
# These are *block* boundaries: a span stops at them, because a heading, an
# author or a `\usepackage` is not part of the paragraph around it.
#
# Inline reference calls (\cite, \ref, \texttt …) are deliberately NOT here.
# Making them boundaries split a sentence in half around its own citation and
# handed the model a fragment beginning with a full stop. They stay inside the
# passage and `preserve_structure` holds the model to reproducing them byte for
# byte, which is the same guarantee without the mutilation.
_INLINE_PROTECTED = frozenset({
    "cite", "citep", "citet", "citeauthor", "citeyear", "nocite", "ref", "eqref",
    "pageref", "autoref", "nameref", "cref", "Cref", "label", "url", "nolinkurl",
    "path", "href", "includegraphics", "texttt", "lstinline", "verb",
})

_PROTECTED_ARGS: Dict[str, int] = {
    "title": 1, "subtitle": 1, "author": 1, "date": 1, "institute": 1, "thanks": 1,
    "email": 1, "address": 1, "affiliation": 1, "keywords": 1, "IEEEauthorblockN": 1,
    "IEEEauthorblockA": 1, "part": 1, "chapter": 1, "section": 1, "subsection": 1,
    "subsubsection": 1, "paragraph": 1, "subparagraph": 1, "frametitle": 1,
    "framesubtitle": 1, "sectionname": 1, "caption": 1, "captionof": 2,
    "label": 1, "ref": 1, "eqref": 1, "pageref": 1, "autoref": 1, "nameref": 1,
    "cref": 1, "Cref": 1, "cite": 1, "citep": 1, "citet": 1, "citeauthor": 1,
    "citeyear": 1, "nocite": 1, "bibitem": 1, "bibliography": 1, "bibliographystyle": 1,
    "url": 1, "nolinkurl": 1, "path": 1, "href": 2, "includegraphics": 1,
    "input": 1, "include": 1, "usepackage": 1, "documentclass": 1, "graphicspath": 1,
    "newcommand": 2, "renewcommand": 2, "providecommand": 2, "def": 1,
    "newenvironment": 3, "definecolor": 3, "setbeamertemplate": 2, "setbeamercolor": 2,
    "setbeamerfont": 2, "usetheme": 1, "usecolortheme": 1, "lstinputlisting": 1,
    "verb": 1, "texttt": 1, "lstinline": 1, "hypersetup": 1, "pagestyle": 1,
}

# Inline constructs a rewrite must reproduce exactly. They live *inside* a span
# (splitting a sentence around every \cite would leave nothing to rewrite), and
# `preserve_structure` is what holds the model to them.
_RE_INLINE_MATH = re.compile(r"\$\$.*?\$\$|\$(?:\\.|[^$\\])*\$|\\\(.*?\\\)", re.DOTALL)
_RE_DISPLAY_MATH = re.compile(r"\\\[.*?\\\]", re.DOTALL)
_RE_COMMAND = re.compile(r"\\(?:[a-zA-Z@]+\*?|[^a-zA-Z\s])")
_RE_REFERENCE_CALL = re.compile(
    r"\\(?:cite|citep|citet|citeauthor|citeyear|nocite|ref|eqref|pageref|autoref"
    r"|nameref|cref|Cref|label|url|nolinkurl|path|includegraphics|texttt|lstinline)"
    r"(?:\s*\[[^\]]*\])*\s*\{[^{}]*\}")
_RE_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_RE_ACRONYM = re.compile(r"\b[A-Z][A-Z0-9]{1,}\b")
_RE_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]+")
_RE_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])[ \t]+(?=[A-Z\\])")
_RE_BEGIN = re.compile(r"\\begin\s*\{([^}]*)\}")
_RE_END = re.compile(r"\\end\s*\{([^}]*)\}")


@dataclass
class ProseSpan:
    """One passage of bulk prose: what the tool is allowed to reword."""
    start: int
    end: int
    text: str
    words: int = 0
    slop: float = 0.0
    markers: List[str] = field(default_factory=list)

    @property
    def length(self) -> int:
        return self.end - self.start


def _match_brace(code: str, open_idx: int) -> int:
    """Index just past the `}` closing the group at ``open_idx``, or -1."""
    depth = 0
    i = open_idx
    n = len(code)
    while i < n:
        c = code[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def _body_bounds(code: str) -> Tuple[int, int]:
    r"""
    The region a rewrite may touch: inside `\begin{document}`…`\end{document}`.

    The preamble is configuration and the matter after `\end{document}` is not
    typeset; a fragment with no document environment is all body.
    """
    m = re.search(r"\\begin\s*\{document\}", code)
    start = m.end() if m else 0
    m2 = re.search(r"\\end\s*\{document\}", code)
    end = m2.start() if m2 else len(code)
    return (start, end) if end > start else (0, len(code))


def protected_mask(code: str) -> bytearray:
    r"""
    1 for every character a prose span may not contain.

    Marked: the preamble and anything after `\end{document}`; comments,
    verbatim bodies, `\verb` spans and URL arguments (via the validator's
    masking pass, which preserves offsets exactly); the bodies of the
    environments in ``_SKIP_ENVS``; the brace arguments of ``_PROTECTED_ARGS``
    and the title/subtitle arguments of `\begin{frame}`; and display math.
    """
    from edit_validator import clean_latex_for_validation

    n = len(code)
    mask = bytearray(n)
    if not n:
        return mask

    body_start, body_end = _body_bounds(code)
    for i in range(0, min(body_start, n)):
        mask[i] = 1
    for i in range(max(0, body_end), n):
        mask[i] = 1

    # Literal regions: offsets are preserved 1:1 by the masking pass, so a
    # character the view changed is a character that is not structure.
    view = clean_latex_for_validation(code)
    if len(view) == len(code):
        for i in range(n):
            if view[i] != code[i]:
                mask[i] = 1

    def block(a: int, b: int) -> None:
        for k in range(max(0, a), min(b, n)):
            mask[k] = 1

    # Environment bodies that are not prose (nested: an align inside a figure).
    stack: List[Tuple[str, int]] = []
    for m in re.finditer(r"\\(begin|end)\s*\{([^}]*)\}", code):
        kind, env = m.group(1), m.group(2)
        if kind == "begin":
            stack.append((env, m.end()))
            if env in _SKIP_ENVS:
                block(m.start(), m.end())
        else:
            while stack:
                env0, from_idx = stack.pop()
                if env0 in _SKIP_ENVS:
                    block(from_idx, m.end())
                if env0 == env:
                    break
            if env in _SKIP_ENVS:
                block(m.start(), m.end())
    for env0, from_idx in stack:
        if env0 in _SKIP_ENVS:
            block(from_idx, n)

    # Protected command arguments, and the command token itself.
    for m in re.finditer(r"\\([a-zA-Z@]+)\*?", code):
        name = m.group(1)
        groups = _PROTECTED_ARGS.get(name)
        if groups is None or name in _INLINE_PROTECTED:
            continue
        block(m.start(), m.end())
        i = m.end()
        taken = 0
        while taken < groups and i < n:
            while i < n and code[i] in " \t":
                i += 1
            if i < n and code[i] == "[":
                close = code.find("]", i)
                if close == -1:
                    break
                block(i, close + 1)
                i = close + 1
                continue
            if i >= n or code[i] != "{":
                break
            close = _match_brace(code, i)
            if close == -1:
                break
            block(i, close)
            i = close
            taken += 1

    # A frame's title and subtitle: `\begin{frame}{Results}{Detail}`.
    for m in re.finditer(r"\\begin\s*\{frame\}", code):
        i = m.end()
        for _ in range(2):
            while i < n and code[i] in " \t":
                i += 1
            if i < n and code[i] == "[":
                close = code.find("]", i)
                if close == -1:
                    break
                block(i, close + 1)
                i = close + 1
                continue
            if i >= n or code[i] != "{":
                break
            close = _match_brace(code, i)
            if close == -1:
                break
            block(i, close)
            i = close

    for m in _RE_DISPLAY_MATH.finditer(code):
        block(m.start(), m.end())

    return mask


def _split_long(text: str, start: int) -> List[Tuple[int, str]]:
    """A long passage split on sentence boundaries, as (offset, text) pieces."""
    if len(text) <= HUMANIZE_MAX_SPAN_CHARS:
        return [(start, text)]
    pieces: List[Tuple[int, str]] = []
    cursor = 0
    buf_start = 0
    for part in _RE_SENTENCE_SPLIT.split(text):
        idx = text.find(part, cursor)
        if idx == -1:
            idx = cursor
        cursor = idx + len(part)
        if cursor - buf_start >= HUMANIZE_MAX_SPAN_CHARS:
            pieces.append((start + buf_start, text[buf_start:cursor]))
            buf_start = cursor
    if buf_start < len(text):
        pieces.append((start + buf_start, text[buf_start:]))
    return pieces or [(start, text)]


def extract_prose_spans(code: str) -> List[ProseSpan]:
    """
    Every passage of bulk prose in the document body, in order.

    A span is a maximal unprotected run, split at blank lines (a paragraph is
    the natural unit of rewording) and at sentence boundaries when a paragraph
    is very long. Runs with fewer than ``HUMANIZE_MIN_SPAN_WORDS`` words, or
    that are mostly markup, are not bulk prose and are left alone.
    """
    if not code:
        return []
    mask = protected_mask(code)
    spans: List[ProseSpan] = []

    i = 0
    n = len(code)
    while i < n:
        if mask[i]:
            i += 1
            continue
        j = i
        while j < n and not mask[j]:
            j += 1
        run = code[i:j]
        # Paragraphs inside the run.
        offset = 0
        for para in re.split(r"(?:[ \t]*\n){2,}", run):
            idx = run.find(para, offset)
            if idx == -1:
                idx = offset
            offset = idx + len(para)
            for p_start, piece in _split_long(para, i + idx):
                stripped = piece.strip()
                if not stripped:
                    continue
                lead = len(piece) - len(piece.lstrip())
                tail = len(piece) - len(piece.rstrip())
                s0, s1 = p_start + lead, p_start + len(piece) - tail
                body = code[s0:s1]
                if not _is_bulk_prose(body):
                    continue
                score, markers = slop_score(body)
                spans.append(ProseSpan(start=s0, end=s1, text=body,
                                       words=len(_RE_WORD.findall(_plain(body))),
                                       slop=score, markers=markers))
        i = j
    return spans


def _plain(latex_text: str) -> str:
    """The words a reader sees: markup, math and reference calls removed."""
    out = _RE_REFERENCE_CALL.sub(" ", latex_text)
    out = _RE_DISPLAY_MATH.sub(" ", out)
    out = _RE_INLINE_MATH.sub(" ", out)
    out = _RE_COMMAND.sub(" ", out)
    return re.sub(r"[{}\[\]~^&%$#_]", " ", out)


def _is_bulk_prose(text: str) -> bool:
    """Whether a run is running text rather than a label, a path or markup."""
    plain = _plain(text)
    words = _RE_WORD.findall(plain)
    if len(words) < HUMANIZE_MIN_SPAN_WORDS:
        return False
    # Mostly markup: there is little here to reword, and what there is is
    # probably holding a structure together.
    if len(plain.strip()) < 0.45 * len(text.strip()):
        return False
    return True


# ---------------------------------------------------------------------------
# Measuring the register that gives generated prose away
# ---------------------------------------------------------------------------
# Weights are relative: a stock phrase is worth more than a connective, because
# a connective is ordinary academic writing and only its DENSITY is a tell —
# which is what a per-100-words score measures.
_LEXICAL_MARKERS: Sequence[Tuple[str, str, float]] = (
    ("stock-phrase", r"\b(?:delve|delving)\s+(?:in)?to\b", 3.0),
    ("stock-phrase", r"\bin\s+the\s+(?:realm|world|landscape)\s+of\b", 3.0),
    ("stock-phrase", r"\bit\s+is\s+(?:important|worth|crucial|essential)\s+to\s+note\b", 3.0),
    ("stock-phrase", r"\bit\s+should\s+be\s+noted\s+that\b", 2.0),
    ("stock-phrase", r"\bnavigat\w*\s+the\s+(?:complexit|challeng|landscape)\w*", 3.0),
    ("stock-phrase", r"\b(?:rich|intricate|complex)\s+tapestry\b", 3.0),
    ("stock-phrase", r"\b(?:a\s+)?testament\s+to\b", 3.0),
    ("stock-phrase", r"\bunlock(?:ing|s)?\s+the\s+(?:full\s+)?potential\b", 3.0),
    ("stock-phrase", r"\bgame[\s-]?changer\b", 2.5),
    ("stock-phrase", r"\bparadigm\s+shift\b", 2.0),
    ("stock-phrase", r"\bever[\s-]?(?:evolving|changing|growing)\b", 2.5),
    ("stock-phrase", r"\bin\s+today'?s\s+(?:fast[\s-]?paced\s+)?(?:world|era|landscape|environment)\b", 3.0),
    ("stock-phrase", r"\bat\s+its\s+core\b", 2.0),
    ("stock-phrase", r"\bthe\s+key\s+takeaway\b", 2.5),
    ("stock-phrase", r"\bwhen\s+it\s+comes\s+to\b", 2.0),
    ("stock-phrase", r"\bplays?\s+(?:a|an)\s+(?:pivotal|crucial|vital|key|significant|critical)\s+role\b", 2.5),
    ("stock-phrase", r"\bunderscor\w+\s+the\s+(?:importance|need|significance)\b", 2.5),
    ("stock-phrase", r"\bcannot\s+be\s+overstated\b", 3.0),
    ("stock-phrase", r"\bharness(?:ing|es)?\s+the\s+power\b", 3.0),
    ("stock-phrase", r"\b(?:dive|diving)\s+(?:deep|into)\b", 2.0),
    ("stock-phrase", r"\bshed(?:s|ding)?\s+light\s+on\b", 2.0),
    ("stock-phrase", r"\bpave(?:s|d)?\s+the\s+way\b", 2.0),
    ("stock-phrase", r"\bbridg\w+\s+the\s+gap\b", 1.5),
    ("stock-phrase", r"\bthe\s+(?:advent|rise)\s+of\b", 1.5),
    ("stock-phrase", r"\bby\s+leveraging\b", 2.0),
    ("stock-phrase", r"\bserves?\s+as\s+a\b", 1.5),
    ("stock-phrase", r"\bin\s+essence\b", 2.0),
    ("stock-phrase", r"\bthat\s+said\b", 1.5),
    ("buzzword", r"\bleverag(?:e|es|ed|ing)\b", 1.5),
    ("buzzword", r"\butiliz(?:e|es|ed|ing)\b", 1.5),
    ("buzzword", r"\bseamless(?:ly)?\b", 2.0),
    ("buzzword", r"\brobust(?:ness)?\b", 0.8),
    ("buzzword", r"\bholistic(?:ally)?\b", 2.0),
    ("buzzword", r"\bsynerg(?:y|ies|istic)\b", 2.0),
    ("buzzword", r"\bmyriad\b", 2.0),
    ("buzzword", r"\bplethora\b", 2.5),
    ("buzzword", r"\b(?:vast|wide)\s+(?:array|range)\s+of\b", 2.0),
    ("buzzword", r"\bcutting[\s-]?edge\b", 2.0),
    ("buzzword", r"\bstate[\s-]?of[\s-]?the[\s-]?art\b", 0.6),
    ("buzzword", r"\bcomprehensive(?:ly)?\b", 0.8),
    ("buzzword", r"\bmeticulous(?:ly)?\b", 2.0),
    ("buzzword", r"\bunparalleled\b", 2.0),
    ("buzzword", r"\brevolutioniz\w+\b", 2.0),
    ("buzzword", r"\bempower(?:s|ed|ing)?\b", 1.5),
    ("buzzword", r"\bfoster(?:s|ed|ing)?\b", 1.0),
    ("buzzword", r"\bfacilitat(?:e|es|ed|ing)\b", 1.0),
    ("buzzword", r"\bdelve\b", 2.5),
    ("buzzword", r"\bnuanced\b", 1.5),
    ("buzzword", r"\binvaluable\b", 1.5),
    ("connective", r"(?:^|(?<=[.!?]\s))\s*(?:Furthermore|Moreover|Additionally|Consequently|"
                   r"Notably|Importantly|Crucially|Ultimately|Essentially|Nevertheless|"
                   r"Nonetheless|Subsequently)\b", 0.9),
    ("connective", r"(?:^|(?<=[.!?]\s))\s*In\s+(?:conclusion|summary|addition|essence|contrast)\b", 1.2),
    ("connective", r"(?:^|(?<=[.!?]\s))\s*Overall\s*,", 1.2),
    ("hedge", r"\bcan\s+(?:help|serve)\s+to\b", 1.0),
    ("hedge", r"\bmay\s+(?:potentially|possibly)\b", 1.5),
    ("construction", r"\bnot\s+only\b[^.]{0,80}\bbut\s+also\b", 2.0),
    ("construction", r"\bit'?s\s+not\s+(?:just|only)\b[^.]{0,60},\s*it'?s\b", 3.0),
    ("construction", r"\bis\s+(?:more\s+than\s+just|not\s+merely)\b", 2.0),
    ("construction", r"\bfrom\b[^.]{0,40}\bto\b[^.]{0,40},\s*\w+\s+(?:is|are|has|have)\b", 0.8),
)

_COMPILED_MARKERS = [(name, re.compile(rx, re.IGNORECASE | re.MULTILINE), w)
                     for name, rx, w in _LEXICAL_MARKERS]


def _sentences(plain: str) -> List[str]:
    parts = [p.strip() for p in _RE_SENTENCE_SPLIT.split(plain) if p.strip()]
    return [p for p in parts if _RE_WORD.search(p)]


def slop_score(latex_text: str) -> Tuple[float, List[str]]:
    """
    How much this passage reads as generated text: markers per 100 words.

    Lexical markers plus three structural ones, each of which is a tell no
    single phrase shows: a connective opening most sentences, lists that are
    always three items long, and sentences that are all the same length.
    Returns ``(score, marker names worst first)``.
    """
    plain = _plain(latex_text)
    words = _RE_WORD.findall(plain)
    if len(words) < 5:
        return 0.0, []

    hits: Dict[str, float] = {}
    total = 0.0
    for name, rx, weight in _COMPILED_MARKERS:
        found = rx.findall(plain)
        if found:
            total += weight * len(found)
            hits[name] = hits.get(name, 0.0) + weight * len(found)

    sents = _sentences(plain)
    structural: List[Tuple[str, float]] = []
    if len(sents) >= 4:
        lengths = [len(_RE_WORD.findall(s)) for s in sents]
        mean = sum(lengths) / len(lengths)
        if mean > 0:
            var = sum((x - mean) ** 2 for x in lengths) / len(lengths)
            cv = (var ** 0.5) / mean
            # Human paragraphs vary; generated ones march.
            if cv < 0.28:
                structural.append(("uniform-sentence-length", 2.0 * (0.28 - cv) / 0.28 * len(sents) / 2))
        openers = sum(1 for s in sents if re.match(
            r"(?:Furthermore|Moreover|Additionally|However|Therefore|Thus|Consequently|"
            r"Overall|Notably|Importantly|Ultimately|In\s+\w+)\b", s))
        if openers / len(sents) > 0.34:
            structural.append(("connective-opener-density", 1.5 * openers))
    triples = len(re.findall(r"\b\w+,\s+\w+,\s+and\s+\w+\b", plain))
    if triples >= 2:
        structural.append(("rule-of-three", 0.9 * triples))

    for name, value in structural:
        total += value
        hits[name] = hits.get(name, 0.0) + value

    score = 100.0 * total / max(1, len(words))
    ranked = [n for n, _ in sorted(hits.items(), key=lambda kv: -kv[1])]
    return round(score, 3), ranked[:8]


def document_slop(code: str) -> Dict[str, Any]:
    """The document's prose, measured: one score over every eligible span."""
    spans = extract_prose_spans(code)
    words = sum(s.words for s in spans)
    if not spans or not words:
        return {"score": 0.0, "spans": 0, "words": 0, "above_target": 0, "markers": []}
    weighted = sum(s.slop * s.words for s in spans) / words
    markers: Dict[str, int] = {}
    for s in spans:
        for m in s.markers:
            markers[m] = markers.get(m, 0) + 1
    return {
        "score": round(weighted, 3),
        "spans": len(spans),
        "words": words,
        "above_target": sum(1 for s in spans if s.slop > HUMANIZE_TARGET_SLOP),
        "markers": [m for m, _ in sorted(markers.items(), key=lambda kv: -kv[1])][:8],
    }


# ---------------------------------------------------------------------------
# Verification: same document, different wording
# ---------------------------------------------------------------------------

def _structure_signature(text: str) -> Dict[str, Any]:
    return {
        "commands": _RE_COMMAND.findall(text),
        "refs": _RE_REFERENCE_CALL.findall(text),
        "math": [m.group(0) for m in _RE_INLINE_MATH.finditer(text)]
                + [m.group(0) for m in _RE_DISPLAY_MATH.finditer(text)],
        "braces": (text.count("{") - text.count("\\{"), text.count("}") - text.count("\\}")),
        "envs": (_RE_BEGIN.findall(text), _RE_END.findall(text)),
    }


def preserve_structure(before: str, after: str) -> List[str]:
    """
    Everything that must be byte-identical after a rewording, checked.

    Empty list means the rewrite is a rewording. Each string is a reason the
    caller can hand straight back to the model.
    """
    problems: List[str] = []
    a, b = _structure_signature(before), _structure_signature(after)

    if a["commands"] != b["commands"]:
        lost = _multiset_diff(a["commands"], b["commands"])
        added = _multiset_diff(b["commands"], a["commands"])
        if lost or added:
            problems.append(
                "LaTeX commands changed: "
                + (f"removed {', '.join(sorted(set(lost))[:6])}" if lost else "")
                + ("; " if lost and added else "")
                + (f"added {', '.join(sorted(set(added))[:6])}" if added else ""))
        else:
            problems.append("LaTeX commands were re-ordered; keep them where they are.")
    if a["refs"] != b["refs"]:
        problems.append("citations/references/labels changed — reproduce them exactly: "
                        + ", ".join(sorted(set(a["refs"]) ^ set(b["refs"]))[:6]))
    if a["math"] != b["math"]:
        problems.append("math changed — every $…$ and \\[…\\] must be copied character for character")
    if a["braces"] != b["braces"]:
        problems.append("brace balance changed (the { } counts differ from the original)")
    if a["envs"] != b["envs"]:
        problems.append("\\begin/\\end environments changed")

    before_nums, after_nums = _RE_NUMBER.findall(before), _RE_NUMBER.findall(after)
    missing_nums = _multiset_diff(before_nums, after_nums)
    if missing_nums:
        problems.append(f"numbers lost or altered: {', '.join(missing_nums[:8])}")
    if _multiset_diff(after_nums, before_nums):
        problems.append(f"numbers invented: {', '.join(_multiset_diff(after_nums, before_nums)[:8])}")

    plain_before, plain_after = _plain(before), _plain(after)
    missing_acr = _multiset_diff(_RE_ACRONYM.findall(plain_before), _RE_ACRONYM.findall(plain_after))
    if missing_acr:
        problems.append(f"acronyms/names lost: {', '.join(sorted(set(missing_acr))[:8])}")

    ratio = len(plain_after.strip()) / max(1, len(plain_before.strip()))
    if ratio < HUMANIZE_MIN_LENGTH_RATIO:
        problems.append(f"the passage lost {int((1 - ratio) * 100)}% of its length — this is a summary, "
                        "not a rewording; keep every point the original makes")
    elif ratio > HUMANIZE_MAX_LENGTH_RATIO:
        problems.append(f"the passage grew {int((ratio - 1) * 100)}% — do not add new material, only reword")
    return problems


def _multiset_diff(a: Sequence[str], b: Sequence[str]) -> List[str]:
    """Items of ``a`` that ``b`` does not cover, counting duplicates."""
    counts: Dict[str, int] = {}
    for x in b:
        counts[x] = counts.get(x, 0) + 1
    out: List[str] = []
    for x in a:
        if counts.get(x, 0) > 0:
            counts[x] -= 1
        else:
            out.append(x)
    return out


def improved(before: str, after: str) -> Tuple[bool, float, float]:
    """
    Whether the rewrite reads measurably less like generated text.

    ``(accept, score before, score after)``. A passage already at or below the
    target was human to begin with: it is left as the author wrote it rather
    than churned, which is why `already_human` is reported separately.
    """
    sb, _ = slop_score(before)
    sa, _ = slop_score(after)
    if sb <= HUMANIZE_TARGET_SLOP:
        return False, sb, sa
    return (sa <= HUMANIZE_TARGET_SLOP or sa <= sb * HUMANIZE_MIN_DROP_RATIO), sb, sa


# ---------------------------------------------------------------------------
# The rewrite
# ---------------------------------------------------------------------------
_PROMPT_HEAD = r"""You are rewriting passages of a LaTeX document so they read as a careful human
author wrote them, instead of reading as generated text. The information must not change.

RULES — every one of these is checked mechanically and a passage that breaks one is thrown away:
1. SAME MEANING, SAME FACTS. Every claim, number, name, acronym and ordering of points stays.
   Invent nothing: no new examples, no new figures, no new citations, no added conclusions.
2. SAME LATEX. Copy every backslash command, every $...$ and \[...\] exactly as it appears
   (\textbf{...}, \item, \cite{key}, \ref{fig:x}, \% , \&). Do not add, remove, re-order or
   re-spell a single command. Do not touch anything inside braces of \cite, \ref, \label or \url.
3. SAME LENGTH, ROUGHLY. Between 85% and 115% of the original. Do not summarise and do not pad.
4. HOW TO MAKE IT HUMAN:
   - Vary sentence length deliberately: follow a long sentence with a short one.
   - Use plain verbs. "use", not "utilize"; "build on", not "leverage"; "lets", not "facilitates".
   - Delete the stock openers: "It is important to note that", "In today's world", "At its core",
     "plays a crucial role", "a testament to", "delve into", "navigate the complexities",
     "unlock the potential", "cannot be overstated", "seamless", "holistic", "myriad",
     "cutting-edge", "robust and scalable", "paradigm shift".
   - Do not start consecutive sentences with Furthermore / Moreover / Additionally / Overall.
     Join the thought to the previous sentence instead, or just state it.
   - Break the three-item rhythm ("fast, reliable, and scalable"): two items, or four, or a clause.
   - Prefer the active voice and a concrete subject when the original allows it.
   - Say the thing once. Drop the sentence that restates the previous sentence in other words.
   - Keep the register of the surrounding document: this is technical/academic writing, not chat.
     No contractions, no rhetorical questions, no exclamation marks, no first-person asides,
     no emoji, no headings, no bullet characters you did not find in the original.

OUTPUT FORMAT — exactly this, nothing else, no commentary, no code fences:
<<<N>>>
the rewritten passage
<<<END>>>
one block per passage, using the same numbers you were given, in any order. If a passage already
reads as human writing and you would not change it, return it unchanged.

PASSAGES:
"""

_RE_BLOCK = re.compile(r"<<<\s*(\d+)\s*>>>\s*\n?(.*?)(?:\n?<<<\s*END\s*>>>|\Z)", re.DOTALL)


def _build_prompt(batch: Sequence[Tuple[int, str]],
                  problems: Optional[Dict[int, List[str]]] = None) -> str:
    parts = [_PROMPT_HEAD]
    for idx, text in batch:
        parts.append(f"<<<{idx}>>>\n{text}\n<<<END>>>\n")
        if problems and problems.get(idx):
            parts.append("Your previous attempt at passage %d was rejected: %s\n"
                         % (idx, "; ".join(problems[idx][:4])))
    return "".join(parts)


def _parse_reply(content: str) -> Dict[int, str]:
    out: Dict[int, str] = {}
    for m in _RE_BLOCK.finditer(content or ""):
        try:
            key = int(m.group(1))
        except ValueError:
            continue
        body = m.group(2)
        body = re.sub(r"^\s*```[a-zA-Z]*\s*\n|\n?\s*```\s*$", "", body)
        if body.strip():
            out[key] = body.strip("\n")
    return out


def _batches(spans: Sequence[ProseSpan], indices: Sequence[int]) -> List[List[Tuple[int, str]]]:
    batches: List[List[Tuple[int, str]]] = []
    current: List[Tuple[int, str]] = []
    size = 0
    for i in indices:
        text = spans[i].text
        if current and size + len(text) > HUMANIZE_BATCH_CHARS:
            batches.append(current)
            current, size = [], 0
        current.append((i, text))
        size += len(text)
    if current:
        batches.append(current)
    return batches


def rewrite_spans(spans: Sequence[ProseSpan], indices: Sequence[int],
                  cancel_token: Any = None) -> Tuple[Dict[int, str], Dict[int, List[str]]]:
    r"""
    New wording for the given spans: ``(accepted, rejected -> reasons)``.

    Batches go out concurrently; a batch whose passages failed verification is
    retried once with the reasons, because the commonest failure (a dropped
    `\cite`, a reworded `\textbf`) is one the model fixes when told.
    """
    try:
        from providers.router import DEFAULT_MODEL, provider_router
        from providers.base_provider import LLMProviderError
    except Exception as e:  # pragma: no cover
        logger.warning(f"humanize: no LLM provider ({e})")
        return {}, {i: [f"LLM provider unavailable: {e}"] for i in indices}

    accepted: Dict[int, str] = {}
    failed: Dict[int, List[str]] = {}

    def run_batch(batch: List[Tuple[int, str]]) -> None:
        pending = list(batch)
        problems: Dict[int, List[str]] = {}
        for attempt in range(1 + HUMANIZE_MAX_REPAIRS):
            if not pending:
                return
            if cancel_token is not None and getattr(cancel_token, "is_cancelled", lambda: False)():
                return
            prompt = _build_prompt(pending, problems if attempt else None)
            try:
                resp = provider_router.chat(
                    [{"role": "user", "content": prompt}], model=DEFAULT_MODEL,
                    temperature=0.75, max_tokens=8192, cancel_token=cancel_token)
            except LLMProviderError as e:
                for idx, _ in pending:
                    problems.setdefault(idx, []).append(f"LLM call failed: {e}")
                break
            except Exception as e:  # noqa: BLE001 — one batch must not end the run
                logger.warning(f"humanize batch failed: {e}")
                for idx, _ in pending:
                    problems.setdefault(idx, []).append(f"LLM call failed: {e}")
                break

            replies = _parse_reply(resp.get("content", ""))
            still: List[Tuple[int, str]] = []
            for idx, original in pending:
                candidate = replies.get(idx)
                if candidate is None:
                    problems[idx] = ["the model returned no block for this passage"]
                    still.append((idx, original))
                    continue
                reasons = preserve_structure(original, candidate)
                if reasons:
                    problems[idx] = reasons
                    still.append((idx, original))
                    continue
                accepted[idx] = candidate
                problems.pop(idx, None)
            pending = still
        for idx, _ in pending:
            failed[idx] = problems.get(idx, ["not rewritten"])

    batches = _batches(spans, indices)
    if not batches:
        return {}, {}
    if len(batches) == 1 or HUMANIZE_CONCURRENCY == 1:
        for b in batches:
            run_batch(b)
    else:
        with ThreadPoolExecutor(max_workers=min(HUMANIZE_CONCURRENCY, len(batches)),
                                thread_name_prefix="humanize") as pool:
            list(pool.map(run_batch, batches))
    return accepted, failed


# ---------------------------------------------------------------------------
# Writing it back
# ---------------------------------------------------------------------------

def _groups(indices: Sequence[int]) -> List[List[int]]:
    """Accepted spans in document order, in groups of ``HUMANIZE_WRITE_GROUP``."""
    ordered = sorted(indices)
    return [ordered[i:i + HUMANIZE_WRITE_GROUP]
            for i in range(0, len(ordered), HUMANIZE_WRITE_GROUP)]


def _apply(ws: "ShadowWorkspace", code: str, spans: Sequence[ProseSpan],
           accepted: Dict[int, str]) -> Tuple[int, Dict[int, str], List[str]]:
    r"""
    Commit the accepted rewrites through the ordinary write gate.

    Groups of spans are spliced together, which bounds the number of
    whole-document validations on a 60-page report to a handful; a group the
    gate refuses is retried span by span so one bad passage cannot discard a
    hundred good ones. Returns ``(written, index -> refusal, auto_repairs)``.
    """
    written = 0
    refused: Dict[int, str] = {}
    repairs: List[str] = []

    def splice(group: Sequence[int]) -> Optional[str]:
        """One edit covering ``group``; None on success, else the gate's reason."""
        lo, hi = spans[group[0]].start, spans[group[-1]].end
        pieces: List[str] = []
        cursor = lo
        for i in group:
            pieces.append(code[cursor:spans[i].start])
            pieces.append(accepted[i])
            cursor = spans[i].end
        pieces.append(code[cursor:hi])
        res = ws._splice(lo, hi, "".join(pieces), "humanize_content", method="offset")
        if res.get("success"):
            for fix in (res.get("auto_repairs") or []):
                if fix not in repairs:
                    repairs.append(fix)
            return None
        return str(res.get("error") or "rejected by the write gate")

    # Last group first: a commit shifts only the offsets after it.
    for group in reversed(_groups(list(accepted.keys()))):
        reason = splice(group)
        if reason is None:
            written += len(group)
            continue
        logger.info("humanize: group of %d refused (%s); retrying one at a time",
                    len(group), reason[:120])
        for i in reversed(group):
            r = splice([i])
            if r is None:
                written += 1
            else:
                refused[i] = r
    return written, refused, repairs


def _node_range(ws: "ShadowWorkspace", node_id: str) -> Optional[Tuple[int, int]]:
    node = ws.resolve_node(node_id)
    if node is None:
        return None
    return (getattr(node, "body_start", None) or node.start,
            getattr(node, "body_end", None) or node.end)


def humanize_content_tool(ws: "ShadowWorkspace", args: Dict[str, Any]) -> Dict[str, Any]:
    r"""
    Reword the document's bulk prose so it reads as a person wrote it.

    ``scope="document"`` (the default) covers every passage of running text in
    the body; ``node_id`` restricts it to one block. ``dry_run`` measures and
    reports without writing; ``report_only`` does the same without calling the
    LLM at all, which is what the run's verification pass uses.
    """
    code = ws.get_buffer()
    node_id = args.get("node_id") or None
    scope = str(args.get("scope") or ("node" if node_id else "document"))
    dry_run = bool(args.get("dry_run"))
    report_only = bool(args.get("report_only"))

    spans = extract_prose_spans(code)
    if node_id:
        rng = _node_range(ws, node_id)
        if rng is None:
            return {"error": f"No block with id '{node_id}'. Call inspect_document for the ids."}
        lo, hi = rng
        spans = [s for s in spans if s.start >= lo and s.end <= hi]

    if not spans:
        return {"success": True, "scope": scope, "spans_total": 0, "humanized": 0,
                "note": ("No bulk prose to humanize here — every passage in range is a title, a "
                         "caption, a reference, math, a table or too short to be running text.")}

    before = {"score": round(sum(s.slop * s.words for s in spans) / max(1, sum(s.words for s in spans)), 3),
              "words": sum(s.words for s in spans),
              "above_target": sum(1 for s in spans if s.slop > HUMANIZE_TARGET_SLOP)}

    worst = sorted(spans, key=lambda s: -s.slop)[:6]
    sample = [{"line": code[:s.start].count("\n") + 1, "slop": s.slop,
               "markers": s.markers, "text": s.text.strip()[:160]} for s in worst if s.slop > 0]

    if report_only:
        return {"success": True, "scope": scope, "spans_total": len(spans),
                "humanized": 0, "written": 0,
                "slop_before": before["score"], "slop_after": before["score"],
                "target_slop": HUMANIZE_TARGET_SLOP,
                "passages_above_target": before["above_target"],
                "verified": before["above_target"] == 0,
                "worst_passages": sample,
                "note": "Measurement only; nothing was rewritten."}

    # Only passages that MEASURE as generated text are sent. One already at or
    # below the target reads as a person's writing: rewriting it would burn a
    # call to produce something `improved()` then refuses anyway, and it risks
    # the author's own voice for nothing.
    todo = [i for i, s in enumerate(spans) if s.slop > HUMANIZE_TARGET_SLOP]
    already_human = len(spans) - len(todo)
    accepted, failed = rewrite_spans(spans, todo, cancel_token=getattr(ws, "_cancel_token", None))

    # Keep only rewrites that read measurably better.
    keep: Dict[int, str] = {}
    no_gain: List[int] = []
    for i, text in accepted.items():
        ok, _sb, _sa = improved(spans[i].text, text)
        if ok:
            keep[i] = text
        else:
            no_gain.append(i)

    if dry_run:
        return {"success": True, "scope": scope, "spans_total": len(spans),
                "would_humanize": len(keep), "already_human": already_human,
                "not_improved": len(no_gain), "failed_verification": len(failed),
                "slop_before": before["score"], "target_slop": HUMANIZE_TARGET_SLOP,
                "worst_passages": sample, "note": "Dry run — the document was not modified."}

    written, refused, repairs = _apply(ws, code, spans, keep)

    # Verify against the document as it now stands, not against what was sent.
    after_code = ws.get_buffer()
    after_spans = extract_prose_spans(after_code)
    if node_id:
        rng = _node_range(ws, node_id)
        if rng:
            lo, hi = rng
            after_spans = [s for s in after_spans if s.start >= lo and s.end <= hi]
    after_words = max(1, sum(s.words for s in after_spans))
    after_score = round(sum(s.slop * s.words for s in after_spans) / after_words, 3)
    remaining = [s for s in after_spans if s.slop > HUMANIZE_TARGET_SLOP]

    issues: List[str] = []
    for i, reasons in list(failed.items())[:6]:
        issues.append(f"line {code[:spans[i].start].count('\n') + 1}: " + "; ".join(reasons[:2]))
    for i, reason in list(refused.items())[:4]:
        issues.append(f"line {code[:spans[i].start].count('\n') + 1}: the write gate refused it — "
                      + reason.splitlines()[0][:140])

    out: Dict[str, Any] = {
        "success": True,
        "scope": scope,
        "spans_total": len(spans),
        "humanized": written,
        "already_human": already_human,
        "not_improved": len(no_gain),
        "failed_verification": len(failed) + len(refused),
        "slop_before": before["score"],
        "slop_after": after_score,
        "target_slop": HUMANIZE_TARGET_SLOP,
        "passages_above_target": len(remaining),
        "verified": not remaining and not failed and not refused,
        "meaning_preserved": True,
        "note": humanize_summary(before["score"], after_score, written, len(spans), len(remaining)),
    }
    if issues:
        out["issues"] = issues
    if remaining:
        out["still_above_target"] = [
            {"line": after_code[:s.start].count("\n") + 1, "slop": s.slop,
             "markers": s.markers, "text": s.text.strip()[:160]} for s in remaining[:8]]
    if repairs:
        out["auto_repairs"] = repairs
    return out


def humanize_summary(before: float, after: float, written: int, total: int,
                     remaining: int) -> str:
    """One honest line about what the document now measures."""
    head = (f"Rewrote {written} of {total} prose passage(s); "
            f"AI-register score {before} → {after} per 100 words "
            f"(target ≤ {HUMANIZE_TARGET_SLOP}).")
    if remaining:
        return head + (f" {remaining} passage(s) still read as generated text — listed under "
                       "still_above_target with their source lines.")
    return head + " Every passage is at or below the target; titles, names, citations, numbers, " \
                  "math and tables are unchanged."


# ---------------------------------------------------------------------------
# Recognising the request
# ---------------------------------------------------------------------------
_RE_HUMANIZE_REQUEST = re.compile(
    r"\bhumani[sz]\w*\b"
    r"|\bhuman[\s-]?(?:like|written|sounding)\b"
    r"|\b(?:sound|read|feel)s?\s+(?:more\s+)?(?:like\s+)?(?:a\s+)?human\b"
    r"|\b(?:less|not)\s+(?:like\s+)?(?:an?\s+)?(?:ai|a\.i\.|robot|robotic|machine|chatgpt|gpt)\b"
    r"|\bai[\s-]?(?:slop|ish|generated\s+(?:tone|feel|style))\b"
    r"|\banti[\s-]?ai\b"
    r"|\bde[\s-]?ai\b"
    r"|\b(?:remove|reduce|avoid|kill)\s+(?:the\s+)?ai\s+(?:tone|voice|feel|style|smell|wording)\b"
    r"|\bdoesn'?t\s+sound\s+(?:like\s+)?ai\b"
    r"|\bsounds?\s+too\s+(?:ai|robotic|generic|formulaic)\b"
    r"|\bai\s+detect\w*\b"
    r"|\bmake\s+it\s+(?:sound|read)\s+natural\b",
    re.IGNORECASE)


def is_humanize_request(instruction: str) -> bool:
    """Whether the request is about the wording reading as generated text."""
    return bool(_RE_HUMANIZE_REQUEST.search(instruction or ""))


# ---------------------------------------------------------------------------
# The run's own pass over the document
# ---------------------------------------------------------------------------
# Passages whose first rewrite verified but did not read measurably better get a
# second attempt. Beyond that the wording is as good as this model makes it, and
# a third pass is latency the user pays for nothing.
HUMANIZE_PASSES = max(1, int(os.getenv("HUMANIZE_PASSES", "2") or 2))


def run_humanize(ws: "ShadowWorkspace", node_id: Optional[str] = None) -> Dict[str, Any]:
    r"""
    Humanize the document (or one block) and verify the result, in up to
    ``HUMANIZE_PASSES`` passes.

    This is what a "make it sound human" request runs, before the model's first
    turn: the request is about wording, every guarantee that matters is
    measurable, and a model asked to do it by hand rewrites the document. The
    merged report is what the model and the user are then shown.
    """
    args: Dict[str, Any] = {"scope": "node" if node_id else "document"}
    if node_id:
        args["node_id"] = node_id

    first = humanize_content_tool(ws, dict(args))
    if not first.get("success") or not first.get("spans_total"):
        return first
    merged = dict(first)
    passes = 1
    while (passes < HUMANIZE_PASSES and merged.get("passages_above_target")
           and not (getattr(ws, "_cancel_token", None) is not None
                    and ws._cancel_token.is_cancelled())):
        nxt = humanize_content_tool(ws, dict(args))
        passes += 1
        if not nxt.get("success"):
            break
        if nxt.get("humanized", 0) == 0 and nxt.get("passages_above_target", 0) >= \
                merged.get("passages_above_target", 0):
            merged.update({k: nxt[k] for k in ("slop_after", "passages_above_target",
                                               "verified", "still_above_target") if k in nxt})
            break  # no further progress is being made
        merged["humanized"] = merged.get("humanized", 0) + nxt.get("humanized", 0)
        for key in ("slop_after", "passages_above_target", "verified", "already_human",
                    "not_improved", "failed_verification", "still_above_target", "issues"):
            if key in nxt:
                merged[key] = nxt[key]
        if "auto_repairs" in nxt:
            merged["auto_repairs"] = list(dict.fromkeys(
                (merged.get("auto_repairs") or []) + nxt["auto_repairs"]))
    merged["passes"] = passes
    merged["note"] = humanize_summary(
        merged.get("slop_before", 0.0), merged.get("slop_after", 0.0),
        merged.get("humanized", 0), merged.get("spans_total", 0),
        merged.get("passages_above_target", 0))
    return merged


def humanize_status_note(report: Dict[str, Any]) -> str:
    """The line that ends the run's explanation: what the prose measures now."""
    if not report or not report.get("success"):
        return ""
    total = report.get("spans_total") or 0
    if not total:
        return ""
    written = report.get("humanized") or 0
    remaining = report.get("passages_above_target") or 0
    head = (f"✓ Humanized {written} prose passage(s) of {total} "
            f"(AI-register score {report.get('slop_before')} → {report.get('slop_after')} "
            f"per 100 words); titles, names, citations, numbers, math and tables unchanged.")
    if report.get("already_human"):
        head += f" {report['already_human']} passage(s) already read as human writing."
    if remaining:
        head += (f" {remaining} passage(s) still measure above the target and are listed in the "
                 "tool output with their line numbers.")
    if report.get("failed_verification"):
        head += (f" {report['failed_verification']} passage(s) kept their original wording because the "
                 "rewrite would have changed a command, a number or the meaning.")
    return head
