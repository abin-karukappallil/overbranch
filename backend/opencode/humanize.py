r"""
`humanize_document` — turn generated prose into writing that reads as a person's.

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

FOUR DECISIONS THAT ARE LOAD-BEARING
------------------------------------
1. **Titles, names and references are not prose.** A heading is how a block is
   tracked (the locator, the expansion worklist and the node IDs all key off
   it); an author is a person's name; `\cite{ou2023}` is a key, not a word. All
   of them are hard boundaries a rewritable span cannot cross, together with
   math, tables, TikZ, listings, the preamble and the bibliography. What is left
   is running text — which is what the request is about.

2. **A rewrite is verified against the original, not trusted.** Every command
   token, every math segment, every citation/label/reference call, every number,
   acronym, proper name, URL and DOI of the passage must still be there, in the
   same order, and the brace/math balance must be unchanged
   (`preserve_structure`). A passage that fails keeps its original text and is
   reported — the same discipline as `latex_layout.repair.preserves_text`, for
   the same reason: a wording improvement that quietly drops content is not an
   improvement.

3. **"Sounds like AI" is measured, not asserted.** `slop_score` counts the
   register that marks generated prose — the stock phrases, the connective at
   the head of every sentence, the three-item list, the buzzword, the uniform
   sentence length — per hundred words. A rewrite is kept only when that number
   falls, and a passage already at or below the target was written by a person
   and is left alone (and costs no LLM call).

4. **The document may not come out shorter.** Removing "Furthermore, it is
   important to note that" is exactly the job, and it shortens a passage — so a
   per-passage floor cannot be set at 1.0 without forbidding the work. The rule
   is therefore two-level: no passage may lose more than
   `1 - HUMANIZE_MIN_LENGTH_RATIO` of its length (anything more is a summary,
   not a rewording), *and* the total of all eligible prose may not fall below
   what it was. When it would, the passages that shrank most are reverted until
   it does not.

Nothing here lowers `\small`, moves a margin or touches a figure: the output is
the same document with the same information, worded differently.
"""
from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
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
# Markers per 100 words at or below which a passage reads as a person's writing.
HUMANIZE_TARGET_SLOP = float(os.getenv("HUMANIZE_TARGET_SLOP", "1.5") or 1.5)
# A rewrite of an above-target passage must bring the score down to this share
# of what it was, or it is not an improvement worth the churn.
HUMANIZE_MIN_DROP_RATIO = float(os.getenv("HUMANIZE_MIN_DROP_RATIO", "0.6") or 0.6)
# Below this many words a run of text is a label, a caption-like fragment or a
# stub, not bulk prose.
HUMANIZE_MIN_SPAN_WORDS = max(4, int(os.getenv("HUMANIZE_MIN_SPAN_WORDS", "12") or 12))
# Longest passage sent as one unit; a very long paragraph is split on sentences.
HUMANIZE_MAX_SPAN_CHARS = max(400, int(os.getenv("HUMANIZE_MAX_SPAN_CHARS", "1800") or 1800))
# Accepted passages committed per write-gate call.
HUMANIZE_WRITE_GROUP = max(1, int(os.getenv("HUMANIZE_WRITE_GROUP", "12") or 12))
# Per-passage length bounds. The floor is what separates "reworded" from
# "summarised"; the ceiling stops the model adding material of its own.
HUMANIZE_MIN_LENGTH_RATIO = 0.80
HUMANIZE_MAX_LENGTH_RATIO = 1.45
# The document-level rule: total eligible prose may not shrink at all.
HUMANIZE_DOC_MIN_RATIO = float(os.getenv("HUMANIZE_DOC_MIN_RATIO", "1.0") or 1.0)
# Passages whose first rewrite verified but did not read measurably better get a
# second attempt. Beyond that the wording is as good as this model makes it, and
# a third pass is latency the user pays for nothing.
HUMANIZE_PASSES = max(1, int(os.getenv("HUMANIZE_PASSES", "2") or 2))


# ---------------------------------------------------------------------------
# What is not prose
# ---------------------------------------------------------------------------
# Environments whose body is not running text. Their whole extent, tags
# included, is off limits.
_NON_PROSE_ENVS = frozenset({
    "tabular", "tabular*", "tabularx", "tabulary", "longtable", "array", "matrix",
    "pmatrix", "bmatrix", "vmatrix", "Vmatrix", "smallmatrix", "cases",
    "equation", "equation*", "align", "align*", "alignat", "alignat*", "gather",
    "gather*", "multline", "multline*", "flalign", "flalign*", "eqnarray",
    "eqnarray*", "split", "aligned", "gathered", "displaymath", "math",
    "tikzpicture", "pgfpicture", "axis", "circuitikz", "forest", "tikzcd",
    "verbatim", "verbatim*", "semiverbatim", "Verbatim", "BVerbatim", "LVerbatim",
    "alltt", "lstlisting", "minted", "listing", "code", "comment", "filecontents",
    "filecontents*", "thebibliography", "picture", "overpic", "tcolorbox",
    "algorithm", "algorithmic", "algorithm2e", "pseudocode",
})

# Commands whose arguments are structure, metadata or a key — never prose to
# reword. A heading is how a block is tracked; an author is a person.
_PROTECTED_ARG_CMDS = frozenset({
    "documentclass", "usepackage", "RequirePackage", "input", "include",
    "includeonly", "bibliography", "bibliographystyle", "addbibresource",
    "title", "subtitle", "author", "date", "institute", "email", "thanks",
    "part", "chapter", "section", "subsection", "subsubsection", "paragraph",
    "subparagraph", "frametitle", "framesubtitle", "sectionname", "titlerunning",
    "caption", "captionof", "subcaption", "label", "ref", "eqref", "pageref",
    "autoref", "nameref", "cref", "Cref", "vref", "cite", "citep", "citet",
    "citeauthor", "citeyear", "citealp", "citealt", "nocite", "fullcite",
    "textcite", "parencite", "url", "nolinkurl", "path", "href", "doi",
    "includegraphics", "texttt", "lstinline", "verb", "bibitem", "newcommand",
    "renewcommand", "providecommand", "def", "newenvironment", "renewenvironment",
    "DeclareMathOperator", "definecolor", "setbeamercolor", "setbeamerfont",
    "setbeamertemplate", "usetheme", "usecolortheme", "usefonttheme",
    "geometry", "setlength", "addtolength", "setmainfont", "setsansfont",
    "setmonofont", "hypersetup", "lstset", "tikzset", "pgfplotsset",
    "graphicspath", "pagestyle", "thispagestyle", "fancyhead", "fancyfoot",
    "index", "glossary", "acrshort", "acrlong", "gls", "Gls",
})

# An environment's \begin / \end tag is never prose even when its body is.
_RE_ENV_TAG = re.compile(r"\\(begin|end)\s*\{([^{}]{0,80})\}")
_RE_CMD = re.compile(r"\\([a-zA-Z@]+)\*?")
_RE_DISPLAY_MATH_OPEN = ("\\[", "$$")

_RE_COMMAND = re.compile(r"\\(?:[a-zA-Z@]+\*?|[^a-zA-Z\s])")
_RE_REFERENCE_CALL = re.compile(
    r"\\(?:cite|citep|citet|citeauthor|citeyear|citealp|citealt|nocite|fullcite"
    r"|textcite|parencite|ref|eqref|pageref|autoref|nameref|cref|Cref|vref|label"
    r"|url|nolinkurl|path|href|doi|includegraphics|texttt|lstinline)"
    r"(?:\s*\[[^\]]*\])*\s*\{[^{}]*\}")
_RE_INLINE_MATH = re.compile(r"\$[^$]*\$|\\\([^)]*?\\\)", re.DOTALL)
_RE_DISPLAY_MATH = re.compile(r"\$\$.*?\$\$|\\\[.*?\\\]", re.DOTALL)
_RE_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_RE_ACRONYM = re.compile(r"\b[A-Z][A-Z0-9]{1,}\b")
_RE_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]+")
_RE_BEGIN = re.compile(r"\\begin\s*\{([^}]*)\}")
_RE_END = re.compile(r"\\end\s*\{([^}]*)\}")
_RE_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])[ \t]+(?=[A-Z\\])")
# A bare URL, DOI or ISBN written in prose rather than inside \url{}: a string
# the model must reproduce character for character, and would otherwise "tidy".
_RE_BARE_LOCATOR = re.compile(
    r"(?:https?://|www\.)[^\s,;)\]}]+"
    r"|\b10\.\d{4,9}/[^\s,;)\]}]+"
    r"|\bISBN[- ]?(?:13|10)?:?\s*[\d\-X]{10,17}",
    re.IGNORECASE)
# A capitalised word that is not at the head of a sentence: a person, an
# institution, a product. Sentence-initial words legitimately change when a
# sentence is re-cast, so they are not counted.
_RE_PROPER_CANDIDATE = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-z]{2,}\b", re.MULTILINE)
_PROPER_STOPWORDS = frozenset({
    "The", "This", "That", "These", "Those", "There", "Then", "Thus", "Therefore",
    "However", "Moreover", "Furthermore", "Additionally", "Finally", "First",
    "Second", "Third", "Next", "Also", "Although", "Because", "Before", "After",
    "While", "When", "Where", "Which", "What", "With", "Without", "For", "From",
    "Into", "Over", "Under", "Such", "Since", "Each", "Every", "Both", "Here",
    "Our", "Their", "Its", "They", "She", "Not", "And", "But", "One", "Two",
    "Figure", "Table", "Section", "Chapter", "Equation", "Appendix", "Algorithm",
})


@dataclass
class ProseSpan:
    """One passage of bulk prose: what the tool is allowed to reword."""
    start: int
    end: int
    text: str
    words: int = 0
    score: float = 0.0
    markers: Tuple[str, ...] = ()


def _match_brace(code: str, open_pos: int) -> int:
    """End index (exclusive) of the group whose '{' is at ``open_pos``."""
    depth = 0
    i = open_pos
    n = len(code)
    while i < n:
        c = code[i]
        if c == "\\" and i + 1 < n:
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _skip_args(code: str, pos: int, *, groups: int = 99) -> int:
    """
    End of a command's optional ``[...]`` and mandatory ``{...}`` arguments,
    starting just after the command name.
    """
    i, n, taken = pos, len(code), 0
    while i < n and taken < groups:
        while i < n and code[i] in " \t":
            i += 1
        if i < n and code[i] == "[":
            close = code.find("]", i)
            i = (close + 1) if close != -1 else n
            continue
        if i < n and code[i] == "{":
            i = _match_brace(code, i)
            taken += 1
            continue
        break
    return i


def _mask(mask: bytearray, lo: int, hi: int) -> None:
    for i in range(max(0, lo), min(len(mask), hi)):
        mask[i] = 1


def _block_and_inline_masks(code: str) -> Tuple[bytearray, bytearray]:
    r"""
    Two masks over ``code``, both the same length as it.

    ``block`` marks what a prose passage may not contain or cross: the preamble,
    everything from ``\end{document}``, comments, headings and metadata with
    their arguments, captions, the body *and* tags of every non-prose
    environment, and display math.

    ``inline`` marks what must not be altered but may sit inside a passage: a
    command token, a reference/citation call, inline math. These are islands,
    not boundaries — making ``\cite{x}`` a boundary handed the model a fragment
    beginning with a full stop and the clause it belonged to in another span.
    """
    n = len(code)
    block = bytearray(n)
    inline = bytearray(n)
    if not n:
        return block, inline

    # 1. Preamble and postamble.
    body_start, body_end = 0, n
    m = re.search(r"\\begin\s*\{document\}", code)
    if m:
        body_start = m.end()
        _mask(block, 0, m.end())
    m = re.search(r"\\end\s*\{document\}", code)
    if m:
        body_end = m.start()
        _mask(block, m.start(), n)

    # 2. One left-to-right pass over the body.
    env_stack: List[Tuple[str, int]] = []   # (name, start of the non-prose region)
    i = body_start
    while i < body_end:
        c = code[i]

        if c == "\\" and i + 1 < body_end:
            nxt = code[i + 1]
            # Display math \[ ... \]
            if nxt == "[":
                close = code.find("\\]", i + 2)
                end = (close + 2) if close != -1 else body_end
                _mask(block, i, end)
                i = end
                continue
            if nxt == "(":
                close = code.find("\\)", i + 2)
                end = (close + 2) if close != -1 else body_end
                _mask(inline, i, end)
                i = end
                continue
            cmd = _RE_CMD.match(code, i)
            if not cmd:
                _mask(inline, i, i + 2)   # \& \% \_ \$ \# \\ …
                i += 2
                continue
            name = cmd.group(1)
            after = cmd.end()
            if name in ("begin", "end"):
                tag = _RE_ENV_TAG.match(code, i)
                if tag:
                    env = tag.group(2).strip()
                    end_of_tag = tag.end()
                    if name == "begin":
                        # The tag's own arguments (a frame title, a tabular
                        # column spec) are never prose.
                        end_of_tag = _skip_args(code, end_of_tag)
                        if env in _NON_PROSE_ENVS:
                            env_stack.append((env, i))
                        _mask(block, i, end_of_tag)
                    else:
                        _mask(block, i, end_of_tag)
                        if env_stack and env_stack[-1][0] == env:
                            _, region_start = env_stack.pop()
                            _mask(block, region_start, end_of_tag)
                    i = end_of_tag
                    continue
                _mask(block, i, after)
                i = after
                continue
            if name in _PROTECTED_ARG_CMDS:
                end = _skip_args(code, after)
                # A heading or a caption is a block boundary; a citation, a
                # label or a \texttt is an island inside the sentence.
                if name in ("cite", "citep", "citet", "citeauthor", "citeyear",
                            "citealp", "citealt", "nocite", "fullcite", "textcite",
                            "parencite", "ref", "eqref", "pageref", "autoref",
                            "nameref", "cref", "Cref", "vref", "label", "url",
                            "nolinkurl", "path", "href", "doi", "texttt",
                            "lstinline", "includegraphics", "index"):
                    _mask(inline, i, end)
                else:
                    _mask(block, i, end)
                i = end
                continue
            if name == "verb":
                # \verb<delim>…<delim>; cannot span a line.
                j = after
                if j < body_end and not code[j].isspace():
                    delim = code[j]
                    close = code.find(delim, j + 1)
                    eol = code.find("\n", j)
                    end = (close + 1) if (close != -1 and (eol == -1 or close < eol)) else (
                        eol if eol != -1 else body_end)
                    _mask(block, i, end)
                    i = end
                    continue
            _mask(inline, i, after)
            i = after
            continue

        if c == "%":
            eol = code.find("\n", i)
            end = eol if eol != -1 else body_end
            _mask(block, i, end)
            i = end
            continue

        if c == "$":
            if code.startswith("$$", i):
                close = code.find("$$", i + 2)
                end = (close + 2) if close != -1 else body_end
                _mask(block, i, end)
            else:
                close = code.find("$", i + 1)
                end = (close + 1) if close != -1 else body_end
                _mask(inline, i, end)
            i = end
            continue

        if c in "{}":
            _mask(inline, i, i + 1)
            i += 1
            continue

        i += 1

    # An environment left open (a truncated buffer) protects its tail.
    for _, region_start in env_stack:
        _mask(block, region_start, body_end)
    return block, inline


def protected_mask(code: str) -> bytearray:
    r"""
    Per-character protection: 1 where the character is not the tool's to reword.

    The union of the block regions (preamble, headings, environments, math,
    comments, postamble) and the inline islands (commands, citations, braces).
    Everything 0 is running text.
    """
    block, inline = _block_and_inline_masks(code)
    out = bytearray(len(code))
    for i in range(len(code)):
        if block[i] or inline[i]:
            out[i] = 1
    return out


def _free_words(text: str, inline: bytearray, offset: int) -> int:
    """Words of ``text`` that no inline island covers — the rewritable words."""
    count = 0
    for m in _RE_WORD.finditer(text):
        a, b = offset + m.start(), offset + m.end()
        if not any(inline[k] for k in range(a, min(b, len(inline)))):
            count += 1
    return count


def _split_long(text: str, start: int) -> List[Tuple[int, int]]:
    """A very long paragraph, cut on sentence ends into sendable pieces."""
    if len(text) <= HUMANIZE_MAX_SPAN_CHARS:
        return [(start, start + len(text))]
    pieces: List[Tuple[int, int]] = []
    cursor = 0
    while cursor < len(text):
        if len(text) - cursor <= HUMANIZE_MAX_SPAN_CHARS:
            pieces.append((start + cursor, start + len(text)))
            break
        window = text[cursor:cursor + HUMANIZE_MAX_SPAN_CHARS]
        cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
        if cut <= 0:
            cut = len(window)
        else:
            cut += 1
        pieces.append((start + cursor, start + cursor + cut))
        cursor += cut
    return pieces


def extract_prose_spans(code: str) -> List[ProseSpan]:
    r"""
    Every passage of bulk prose in the document body, in order.

    A passage is a maximal run of text no block region crosses, broken at
    paragraph boundaries, carrying at least ``HUMANIZE_MIN_SPAN_WORDS``
    rewritable words. Commands, citations and inline math sit inside it.
    """
    if not code or not code.strip():
        return []
    block, inline = _block_and_inline_masks(code)

    runs: List[Tuple[int, int]] = []
    i, n = 0, len(code)
    while i < n:
        if block[i]:
            i += 1
            continue
        j = i
        while j < n and not block[j]:
            j += 1
        runs.append((i, j))
        i = j

    spans: List[ProseSpan] = []
    for lo, hi in runs:
        # Paragraph breaks split a run; a blank line starts a new passage.
        chunk = code[lo:hi]
        offset = 0
        for part in re.split(r"(\n[ \t]*\n)", chunk):
            if not part:
                continue
            if re.fullmatch(r"\n[ \t]*\n", part):
                offset += len(part)
                continue
            p_start = lo + offset
            offset += len(part)
            stripped = part.strip()
            if not stripped:
                continue
            lead = len(part) - len(part.lstrip())
            s0 = p_start + lead
            s1 = s0 + len(stripped)
            for a, b in _split_long(code[s0:s1], s0):
                text = code[a:b]
                if not text.strip():
                    continue
                words = _free_words(text, inline, a)
                if words < HUMANIZE_MIN_SPAN_WORDS:
                    continue
                score, markers = slop_score(text)
                spans.append(ProseSpan(start=a, end=b, text=text, words=words,
                                       score=score, markers=tuple(markers)))
    return spans


# ---------------------------------------------------------------------------
# "Sounds like AI", measured
# ---------------------------------------------------------------------------
# Phrases that say nothing and appear in generated prose far more than in
# anybody's writing. Each occurrence is one marker.
_STOCK_PHRASES = (
    r"it is important to note", r"it is worth noting", r"it should be noted",
    r"in today'?s (?:fast[- ]paced |modern |digital )?world",
    r"in the (?:modern|current|digital) (?:era|age|landscape)",
    r"plays? an? (?:crucial|vital|pivotal|key|significant|important) role",
    r"cannot be overstated", r"cannot be ignored",
    r"the importance of", r"the significance of",
    r"underscores? the (?:importance|need|significance)",
    r"highlights? the (?:importance|need|significance)",
    r"ever[- ]?(?:evolving|growing|changing|expanding)",
    r"rapidly (?:evolving|growing|changing)",
    r"delv(?:e|es|ing) into", r"dive deep into",
    r"unlock(?:ing)? the (?:full )?potential",
    r"a holistic approach", r"a comprehensive (?:overview|understanding)",
    r"at the forefront of", r"paves? the way",
    r"in conclusion,", r"in summary,",
    r"when it comes to", r"navigat(?:e|es|ing) the (?:complexities|challenges)",
    r"the (?:complexities|intricacies) of",
    r"serves? as a testament", r"a game[- ]changer",
    r"revolutioniz(?:e|es|ing)", r"seamless(?:ly)? integrat",
)
_RE_STOCK = re.compile("|".join(_STOCK_PHRASES), re.IGNORECASE)

# Single words that mark the register. Counted once per occurrence.
_BUZZWORDS = frozenset("""
leverage leverages leveraging leveraged seamless seamlessly holistic robust
scalable scalability delve delves delving underscore underscores underscoring
landscape realm realms unlock unlocks unlocking potential significance crucial
pivotal paradigm synergy synergies cutting-edge state-of-the-art fast-paced
myriad plethora tapestry testament foster fosters fostering embark embarks
transformative groundbreaking unprecedented vibrant bustling intricate
comprehensive multifaceted nuanced streamline streamlined streamlining
empower empowers empowering elevate elevates harness harnesses harnessing
""".split())

# A connective at the head of a sentence. One is ordinary writing; a document
# where every other sentence opens with one is not.
_SENTENCE_OPENERS = frozenset("""
furthermore moreover additionally consequently therefore thus hence overall
notably importantly significantly ultimately
""".split())

_RE_TRIPLE_LIST = re.compile(
    r"\b[\w-]+,\s+[\w-]+,\s+and\s+[\w-]+\b", re.IGNORECASE)


def _plain(latex_text: str) -> str:
    """What a reader sees: markup and math removed, words left."""
    out = _RE_DISPLAY_MATH.sub(" ", latex_text or "")
    out = _RE_INLINE_MATH.sub(" ", out)
    out = _RE_REFERENCE_CALL.sub(" ", out)
    out = _RE_COMMAND.sub(" ", out)
    out = re.sub(r"[{}~^&%$#_\\]", " ", out)
    return re.sub(r"[ \t]+", " ", out)


def _sentences(text: str) -> List[str]:
    parts = [p.strip() for p in _RE_SENTENCE_SPLIT.split(text) if p.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def slop_score(latex_text: str) -> Tuple[float, List[str]]:
    """
    Markers of generated register per 100 words, and which kinds fired.

    Not a judgement of quality: a score at or below ``HUMANIZE_TARGET_SLOP``
    means "this reads as a person's writing", which is the only decision made
    from it.
    """
    plain = _plain(latex_text)
    words = _RE_WORD.findall(plain)
    if len(words) < 5:
        return 0.0, []

    markers: List[str] = []
    hits = 0.0

    stock = len(_RE_STOCK.findall(plain))
    if stock:
        hits += stock
        markers.append("stock-phrase")

    lowered = [w.lower() for w in words]
    buzz = sum(1 for w in lowered if w in _BUZZWORDS)
    if buzz:
        hits += buzz
        markers.append("buzzword")

    sentences = _sentences(plain)
    openers = 0
    for s in sentences:
        first = _RE_WORD.search(s)
        if first and first.group(0).lower() in _SENTENCE_OPENERS:
            openers += 1
    if openers > 1:
        hits += openers
        markers.append("connective-opener")

    triples = len(_RE_TRIPLE_LIST.findall(plain))
    if triples:
        hits += triples
        markers.append("triple-list")

    # Uniform sentence length is a register marker no word list can catch: a
    # paragraph of five sentences all the same length does not happen when a
    # person is making a point.
    if len(sentences) >= 4:
        lengths = [len(_RE_WORD.findall(s)) for s in sentences]
        mean = sum(lengths) / len(lengths)
        if mean >= 4:
            var = sum((x - mean) ** 2 for x in lengths) / len(lengths)
            spread = (var ** 0.5) / mean
            if spread < 0.25:
                hits += len(sentences) * (0.25 - spread) * 4
                markers.append("uniform-sentences")

    return round(100.0 * hits / max(1, len(words)), 2), markers


def document_slop(code: str) -> Dict[str, Any]:
    """The document's prose score, weighted by passage length."""
    spans = extract_prose_spans(code)
    if not spans:
        return {"spans": 0, "above_target": 0, "score": 0.0, "worst": []}
    total_words = sum(s.words for s in spans) or 1
    score = sum(s.score * s.words for s in spans) / total_words
    above = [s for s in spans if s.score > HUMANIZE_TARGET_SLOP]
    worst = sorted(above, key=lambda s: -s.score)
    return {
        "spans": len(spans),
        "above_target": len(above),
        "score": round(score, 2),
        "worst": worst,
    }


# ---------------------------------------------------------------------------
# What a rewrite must preserve
# ---------------------------------------------------------------------------
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


def _proper_nouns(plain: str) -> List[str]:
    return [m.group(0) for m in _RE_PROPER_CANDIDATE.finditer(plain)
            if m.group(0) not in _PROPER_STOPWORDS]


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
    invented_nums = _multiset_diff(after_nums, before_nums)
    if invented_nums:
        problems.append(f"numbers invented: {', '.join(invented_nums[:8])}")

    plain_before, plain_after = _plain(before), _plain(after)

    missing_acr = _multiset_diff(_RE_ACRONYM.findall(plain_before),
                                 _RE_ACRONYM.findall(plain_after))
    if missing_acr:
        problems.append(f"acronyms/names lost: {', '.join(sorted(set(missing_acr))[:8])}")

    # Named entities in running prose: a person, an institution, a product.
    missing_names = _multiset_diff(_proper_nouns(plain_before), _proper_nouns(plain_after))
    if missing_names:
        problems.append("names lost — authors, institutions, organisations and product names "
                        f"must be reproduced exactly: {', '.join(sorted(set(missing_names))[:8])}")

    # A bare URL, DOI or ISBN is a string, not words.
    missing_loc = _multiset_diff(_RE_BARE_LOCATOR.findall(before),
                                 _RE_BARE_LOCATOR.findall(after))
    if missing_loc:
        problems.append(f"URLs/DOIs/ISBNs changed: {', '.join(missing_loc[:4])}")

    ratio = len(plain_after.strip()) / max(1, len(plain_before.strip()))
    if ratio < HUMANIZE_MIN_LENGTH_RATIO:
        problems.append(f"the passage lost {int((1 - ratio) * 100)}% of its length — this is a summary, "
                        "not a rewording; keep every point the original makes")
    elif ratio > HUMANIZE_MAX_LENGTH_RATIO:
        problems.append(f"the passage grew {int((ratio - 1) * 100)}% — do not add new material, only reword")
    return problems


def improved(before: str, after: str) -> Tuple[bool, float, float]:
    """
    Whether the rewrite reads measurably less like generated text.

    A passage already at or below the target was written by a person; churning
    it risks their voice to gain nothing, so it is never an improvement.
    """
    before_score, _ = slop_score(before)
    after_score, _ = slop_score(after)
    if before_score <= HUMANIZE_TARGET_SLOP:
        return False, before_score, after_score
    ok = after_score <= max(HUMANIZE_TARGET_SLOP, before_score * HUMANIZE_MIN_DROP_RATIO)
    return ok, before_score, after_score


# ---------------------------------------------------------------------------
# Asking the model for new wording
# ---------------------------------------------------------------------------
_RE_REPLY_PASSAGE = re.compile(r"<<<(\d+)>>>\n(.*?)\n<<<END>>>", re.DOTALL)

_PROMPT_HEAD = """You are rewriting passages of an academic LaTeX document so they read as a
careful human author wrote them, instead of reading as generated text.

REWRITE ONLY THE WORDING. For every passage:
- Keep the meaning, the claims, the conclusions and the technical content exactly.
- Reproduce every LaTeX command, every \\cite{...}/\\ref{...}/\\label{...}, every
  $...$ maths segment, every number, every acronym, every author, institution and
  product name, and every URL/DOI, character for character and in the same order.
- Keep the same length or slightly more. Never summarise, condense or drop a point;
  a shorter passage is rejected.
- Remove the register that gives generated prose away: stock phrases ("it is
  important to note", "plays a crucial role", "cannot be overstated", "in today's
  world"), a connective at the head of every sentence ("Furthermore", "Moreover",
  "Additionally"), empty buzzwords ("leverage", "seamless", "holistic",
  "ever-evolving", "delve into", "unlock the potential"), three-item lists used as
  decoration, and sentences that all run to the same length.
- Do not add facts, citations, numbers or claims that are not already in the passage.
- Write natural, direct academic prose. Do NOT introduce slang, contractions,
  informality or deliberate mistakes: "human" means authentic, not sloppy.

Return every passage back, in the same delimited form and nothing else:

<<<1>>>
rewritten text of passage 1
<<<END>>>
"""


def _build_prompt(items: Sequence[Tuple[int, str]],
                  reasons: Optional[Dict[int, List[str]]] = None) -> str:
    """One batch: the head, any per-passage failure reasons, then the passages."""
    parts = [_PROMPT_HEAD]
    if reasons:
        parts.append("\nYour previous attempt was REJECTED for these passages. Fix exactly "
                     "these problems and keep everything else as it is:")
        for idx, why in reasons.items():
            parts.append(f"  <<<{idx}>>> " + "; ".join(why[:4]))
        parts.append("")
    parts.append("\nPASSAGES:\n")
    for idx, text in items:
        parts.append(f"<<<{idx}>>>\n{text}\n<<<END>>>\n")
    return "\n".join(parts)


def _parse_reply(reply: str) -> Dict[int, str]:
    out: Dict[int, str] = {}
    for idx, body in _RE_REPLY_PASSAGE.findall(reply or ""):
        try:
            out[int(idx)] = body.strip("\n")
        except ValueError:
            continue
    return out


def _batches(items: Sequence[Tuple[int, str]]) -> List[List[Tuple[int, str]]]:
    """Passages grouped so one call carries about ``HUMANIZE_BATCH_CHARS``."""
    out: List[List[Tuple[int, str]]] = []
    current: List[Tuple[int, str]] = []
    size = 0
    for item in items:
        if current and size + len(item[1]) > HUMANIZE_BATCH_CHARS:
            out.append(current)
            current, size = [], 0
        current.append(item)
        size += len(item[1])
    if current:
        out.append(current)
    return out


def _chat(prompt: str, cancel_token: Any = None) -> str:
    from providers.router import DEFAULT_MODEL, provider_router
    resp = provider_router.chat(
        messages=[{"role": "user", "content": prompt}],
        model=DEFAULT_MODEL,
        temperature=0.7,          # wording, not code: some variety is the point
        max_tokens=8000,
        cancel_token=cancel_token,
    )
    return str(resp.get("content") or "")


def rewrite_spans(spans: Sequence[ProseSpan], indices: Sequence[int],
                  cancel_token: Any = None
                  ) -> Tuple[Dict[int, str], Dict[int, List[str]], Dict[int, float]]:
    """
    Ask for new wording for ``indices`` and keep only what verifies.

    Returns ``(accepted, rejected_reasons, scores_after)``. A passage whose
    rewrite loses a command, a number, a name or its length is not accepted; it
    is retried with the reason, and if it fails again the caller keeps the
    original text and reports it.
    """
    accepted: Dict[int, str] = {}
    reasons: Dict[int, List[str]] = {}
    after_scores: Dict[int, float] = {}
    if not indices:
        return accepted, reasons, after_scores

    pending = [(i, spans[i].text) for i in indices]
    for attempt in range(1 + HUMANIZE_MAX_REPAIRS):
        if not pending:
            break
        groups = _batches(pending)
        replies: List[Dict[int, str]] = [{} for _ in groups]

        def run(k: int) -> None:
            why = {i: reasons[i] for i, _ in groups[k] if i in reasons} if attempt else None
            try:
                replies[k] = _parse_reply(_chat(_build_prompt(groups[k], why), cancel_token))
            except Exception as err:  # noqa: BLE001 — one batch failing is not fatal
                logger.warning(f"humanize batch {k} failed: {err}")
                replies[k] = {}

        if len(groups) == 1:
            run(0)
        else:
            with ThreadPoolExecutor(max_workers=min(HUMANIZE_CONCURRENCY, len(groups)),
                                    thread_name_prefix="humanize") as pool:
                list(pool.map(run, range(len(groups))))

        still: List[Tuple[int, str]] = []
        for group, reply in zip(groups, replies):
            for i, original in group:
                candidate = reply.get(i)
                if not candidate or not candidate.strip():
                    reasons[i] = ["no rewrite came back for this passage"]
                    still.append((i, original))
                    continue
                problems = preserve_structure(original, candidate)
                if problems:
                    # A lost command, number or name is a mistake the model can
                    # be told about and fix, so this one is worth retrying.
                    reasons[i] = problems
                    still.append((i, original))
                    continue
                ok, _, after = improved(original, candidate)
                if not ok:
                    # Not a mistake — the model simply wrote prose that still
                    # reads as generated. Retrying inside this batch asks the
                    # same question again; that is what the next PASS is for,
                    # and two calls per passage per pass is latency for nothing.
                    reasons[i] = ["the rewrite still reads as generated text — remove the stock "
                                  "phrases, the sentence-opening connectives and the buzzwords"]
                    continue
                accepted[i] = candidate
                after_scores[i] = after
                reasons.pop(i, None)
        pending = still
    return accepted, reasons, after_scores


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
        res = ws._splice(lo, hi, "".join(pieces), "humanize_document", method="offset")
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


def _line_of(code: str, offset: int) -> int:
    return code[:offset].count("\n") + 1


# ---------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------
def humanize_document_tool(ws: "ShadowWorkspace", args: Dict[str, Any]) -> Dict[str, Any]:
    r"""
    Reword the document's bulk prose so it reads as a person wrote it.

    ``scope="document"`` (the default) covers every passage of running text in
    the body — the whole document, in one call, so coverage is a property of the
    tool rather than of the model's willingness to keep going. ``node_id``
    restricts it to one block. ``dry_run`` measures and reports without writing;
    ``report_only`` does the same without calling the LLM at all, which is what
    the run's verification pass uses.
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

    def measure(sp: Sequence[ProseSpan]) -> Tuple[float, int]:
        if not sp:
            return 0.0, 0
        total = sum(s.words for s in sp) or 1
        return (round(sum(s.score * s.words for s in sp) / total, 2),
                sum(1 for s in sp if s.score > HUMANIZE_TARGET_SLOP))

    slop_before, above_before = measure(spans)
    above = [i for i, s in enumerate(spans) if s.score > HUMANIZE_TARGET_SLOP]

    base: Dict[str, Any] = {
        "success": True,
        "scope": scope,
        "node_id": node_id,
        "spans_total": len(spans),
        "already_human": len(spans) - len(above),
        "humanized": 0,
        "failed_verification": 0,
        "not_improved": 0,
        "slop_before": slop_before,
        "slop_after": slop_before,
        "target": HUMANIZE_TARGET_SLOP,
        "passages_above_target": above_before,
        "verified": False,
        "worst_passages": [
            {"line": _line_of(code, spans[i].start), "score": spans[i].score,
             "markers": list(spans[i].markers), "excerpt": spans[i].text[:160]}
            for i in sorted(above, key=lambda k: -spans[k].score)[:8]
        ],
    }

    if not spans:
        base["message"] = ("No bulk prose to reword: this document is headings, metadata, "
                           "maths, tables or code, all of which are left alone by design.")
        return base
    if report_only:
        base["message"] = (f"{above_before} of {len(spans)} prose passage(s) read as generated "
                           f"text (score {slop_before} per 100 words, target "
                           f"≤ {HUMANIZE_TARGET_SLOP}).")
        return base
    if not above:
        base["verified"] = True
        base["message"] = (f"All {len(spans)} prose passage(s) already read as human writing "
                           f"(score {slop_before} ≤ {HUMANIZE_TARGET_SLOP}); nothing was "
                           "reworded. Churning an author's own prose risks their voice to gain "
                           "nothing.")
        return base
    if dry_run:
        base["would_humanize"] = len(above)
        base["message"] = (f"{len(above)} of {len(spans)} passage(s) would be reworded; "
                           "nothing was written.")
        return base

    cancel_token = getattr(ws, "_cancel_token", None)
    accepted, reasons, _ = rewrite_spans(spans, above, cancel_token)

    written, refused, repairs = (0, {}, [])
    if accepted:
        written, refused, repairs = _apply(ws, code, spans, accepted)

    after_code = ws.get_buffer()
    after_spans = extract_prose_spans(after_code)
    if node_id:
        rng2 = _node_range(ws, node_id)
        if rng2:
            after_spans = [s for s in after_spans if s.start >= rng2[0] and s.end <= rng2[1]]
    slop_after, above_after = measure(after_spans)

    # The document-level volume check: how much of the original prose length is
    # still there. Removing "Furthermore, it is important to note that" is the
    # job and it shortens a passage, so this cannot be pinned at 1.0 — but a
    # passage may not lose more than 1 - HUMANIZE_MIN_LENGTH_RATIO of its
    # length (checked in preserve_structure), which bounds this too.
    before_chars = sum(len(_plain(s.text).strip()) for s in spans) or 1
    after_chars = sum(len(_plain(s.text).strip()) for s in after_spans)
    prose_ratio = round(after_chars / before_chars, 3)

    issues: List[str] = []
    for i, why in sorted(reasons.items()):
        issues.append(f"line {_line_of(code, spans[i].start)}: " + "; ".join(why[:3]))
    for i, why in sorted(refused.items()):
        issues.append(f"line {_line_of(code, spans[i].start)}: the write gate refused it ({why[:120]})")

    still = [
        {"line": _line_of(after_code, s.start), "score": s.score,
         "markers": list(s.markers), "excerpt": s.text[:160]}
        for s in sorted(after_spans, key=lambda s: -s.score)
        if s.score > HUMANIZE_TARGET_SLOP
    ][:8]

    base.update({
        "humanized": written,
        "failed_verification": len(reasons) + len(refused),
        "not_improved": sum(1 for why in reasons.values()
                            if why and "still reads as generated text" in why[0]),
        "slop_after": slop_after,
        "passages_above_target": above_after,
        "prose_ratio": prose_ratio,
        "prose_floor": HUMANIZE_DOC_MIN_RATIO,
        "verified": True,
        "issues": issues,
        "still_above_target": still,
        "auto_repairs": repairs,
    })
    base["message"] = humanize_summary(slop_before, slop_after, written, len(spans), above_after)
    if prose_ratio < HUMANIZE_DOC_MIN_RATIO:
        base["message"] += (f" The document's prose is now {int(prose_ratio * 100)}% of its "
                            "original length, which is below the floor; the passages listed in "
                            "issues kept their original text.")
    return base


# The name the earlier spec used; the tool and its tests reach it either way.
humanize_content_tool = humanize_document_tool


def humanize_summary(before: float, after: float, written: int, total: int,
                     remaining: int) -> str:
    """One honest line about what the document now measures."""
    head = (f"Rewrote {written} of {total} prose passage(s); "
            f"AI-register score {before} → {after} per 100 words "
            f"(target ≤ {HUMANIZE_TARGET_SLOP}).")
    if remaining:
        return head + (f" {remaining} passage(s) still read as generated text — listed under "
                       "still_above_target with their source lines.")
    return head + (" Every passage is at or below the target; titles, names, citations, numbers, "
                   "math and tables are unchanged.")


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
    r"|\b(?:remove|reduce|avoid|kill|strip)\s+(?:the\s+)?ai\s+"
    r"(?:tone|voice|feel|style|smell|wording|slop)\b"
    r"|\bdoesn'?t\s+sound\s+(?:like\s+)?ai\b"
    r"|\bsounds?\s+too\s+(?:ai|robotic|generic|formulaic)\b"
    r"|\bai\s+detect\w*\b"
    r"|\bmake\s+it\s+(?:sound|read)\s+(?:more\s+)?natural\b",
    re.IGNORECASE)


def is_humanize_request(instruction: str) -> bool:
    """Whether the request is about the wording reading as generated text."""
    return bool(_RE_HUMANIZE_REQUEST.search(instruction or ""))


# ---------------------------------------------------------------------------
# The run's own pass over the document
# ---------------------------------------------------------------------------
def run_humanize(ws: "ShadowWorkspace", node_id: Optional[str] = None) -> Dict[str, Any]:
    r"""
    Humanize the document (or one block) and verify the result, in up to
    ``HUMANIZE_PASSES`` passes, then compile it.

    This is what a "make it sound human" request runs, before the model's first
    turn: the request is about wording, every guarantee that matters is
    measurable, and a model asked to do it by hand rewrites the document. The
    merged report is what the model and the user are then shown.
    """
    args: Dict[str, Any] = {"scope": "node" if node_id else "document"}
    if node_id:
        args["node_id"] = node_id

    first = humanize_document_tool(ws, dict(args))
    if not first.get("success") or not first.get("spans_total"):
        return first
    merged = dict(first)
    passes = 1
    while (passes < HUMANIZE_PASSES and merged.get("passages_above_target")
           and not _cancelled(ws)):
        nxt = humanize_document_tool(ws, dict(args))
        passes += 1
        if not nxt.get("success"):
            break
        if (nxt.get("humanized", 0) == 0
                and nxt.get("passages_above_target", 0) >= merged.get("passages_above_target", 0)):
            for key in ("slop_after", "passages_above_target", "verified", "still_above_target"):
                if key in nxt:
                    merged[key] = nxt[key]
            break  # no further progress is being made
        merged["humanized"] = merged.get("humanized", 0) + nxt.get("humanized", 0)
        for key in ("slop_after", "passages_above_target", "verified", "already_human",
                    "not_improved", "failed_verification", "still_above_target", "issues",
                    "prose_ratio"):
            if key in nxt:
                merged[key] = nxt[key]
        if "auto_repairs" in nxt:
            merged["auto_repairs"] = list(dict.fromkeys(
                (merged.get("auto_repairs") or []) + nxt["auto_repairs"]))
    merged["passes"] = passes

    # The document must still build. `preserve_structure` plus the write gate
    # make a compile regression close to impossible, which is the point — but
    # "close to" is not a guarantee a user can be given, so the pass that wrote
    # something checks. (Nothing written, nothing to check.)
    if merged.get("humanized"):
        merged["compile_result"] = _compile_check(ws)

    merged["note"] = humanize_summary(
        merged.get("slop_before", 0.0), merged.get("slop_after", 0.0),
        merged.get("humanized", 0), merged.get("spans_total", 0),
        merged.get("passages_above_target", 0))
    return merged


def _cancelled(ws: "ShadowWorkspace") -> bool:
    token = getattr(ws, "_cancel_token", None)
    try:
        return bool(token is not None and token.is_cancelled())
    except Exception:  # noqa: BLE001
        return False


def _compile_check(ws: "ShadowWorkspace") -> str:
    r"""
    ``"ok"`` / ``"errors"`` / ``"skipped"`` — what TeX says about *this edit*.

    Only `new_errors` counts: errors the rewrite introduced. A real document
    measured during development already had a bare ``&`` in a frame title, and
    reading the absolute error list told the user "the document reports LaTeX
    errors after the rewrite" about a fault that was there before it and that
    the rewrite cannot touch (a frame title is not prose this tool may reword).
    """
    try:
        from .shadow_compiler import compile_workspace
        res = compile_workspace(ws)
        if res.get("infra") or res.get("infra_skip"):
            return "skipped"
        return "ok" if not (res.get("new_errors") or []) else "errors"
    except Exception as err:  # noqa: BLE001 — a status line must not fail the run
        logger.warning(f"humanize compile check failed: {err}")
        return "skipped"


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
        head += (f" {report['failed_verification']} passage(s) kept their original wording because "
                 "the rewrite would have changed a command, a number, a name or the meaning.")
    if report.get("compile_result") == "errors":
        head += " The document reports LaTeX errors after the rewrite — see the compile output."
    return head
