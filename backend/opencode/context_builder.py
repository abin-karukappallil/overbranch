"""
opencode/context_builder.py — Sending the model what the edit needs, not the document.

A targeted edit used to ship the whole file in the first message (every model
we route to has a large window, so WHOLE_FILE always "fit"), and that first
message is re-sent on every step. Cost and latency scaled with document length
for an edit that touches three lines.

The initial context is now assembled from a hierarchy and stops as early as
the request allows:

    Level 1  the block(s) the request is about (matched by node, title, label,
             ordinal or quoted text)
    Level 2  the parent's heading line (where the block sits)
    Level 3  a few neighbouring lines, for small blocks
    Level 4  preamble lines that style it (\\setbeamerfont/color{X},
             \\definecolor of colours it uses, macros it calls)
    Level 5  the whole document — only for small documents, creation, or full
             rewrites (decided by the caller)

Everything else is reachable with get_block / read_file_range, and the outline
(node IDs + line ranges) is always included so the model can ask precisely.

``ContextLedger`` stops the same unchanged lines from being sent twice while
they are still visible to the model.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

from document_index import DocumentNode, find_node, slugify

if TYPE_CHECKING:
    from .shadow_workspace import ShadowWorkspace

SMALL_DOC_LINES = 150          # at or below this, the whole document is cheaper than choosing
MAX_TARGET_NODES = 3
MAX_NODE_LINES = 160
NEIGHBOUR_LINES = 8
OUTLINE_MAX = 120

_OUTLINE_ENVS = {
    "figure", "figure*", "table", "table*", "tabular", "tabularx", "itemize", "enumerate", "description",
    "tikzpicture", "equation", "equation*", "align", "align*", "abstract", "thebibliography", "minipage",
    "block", "columns", "titlepage", "lstlisting", "verbatim", "tabularx", "multicols",
}
UNSTRUCTURED_FULL_LINES = 400  # no node and no text match: send a document up to this size whole
MAX_TEXT_HITS = 6
TEXT_HIT_RADIUS = 3

_STOPWORDS = {
    "the", "and", "for", "with", "into", "from", "that", "this", "these", "those", "then", "than", "change",
    "replace", "rename", "update", "edit", "make", "set", "put", "add", "remove", "delete", "fix", "please",
    "text", "word", "words", "line", "lines", "name", "instead", "should", "would", "could", "can", "want",
    "need", "also", "all", "every", "each", "bigger", "smaller", "larger", "bold", "italic", "color", "colour",
    "font", "size", "title", "section", "slide", "page", "frame", "document", "latex", "code", "here", "there",
    "move", "write", "rewrite", "correct", "spelling", "typo", "new", "old", "only", "just", "now", "use",
}

# Request words → beamer/LaTeX elements whose styling lives in the preamble.
_STYLE_ELEMENTS = {
    "title": ("title", "subtitle", "author", "date", "institute", "title page"),
    "frametitle": ("frametitle", "frame title", "slide title", "heading"),
    "footline": ("footer", "footline", "page number"),
    "headline": ("header", "headline"),
    "itemize": ("bullet", "itemize", "list"),
    "block": ("block",),
    "normal text": ("text color", "body text", "font"),
    "background canvas": ("background",),
}


# ---------------------------------------------------------------------------
# Outline
# ---------------------------------------------------------------------------

def _outline_nodes(nodes: List[DocumentNode]) -> List[DocumentNode]:
    keep = []
    for n in nodes:
        if n.kind == "env" and n.name not in _OUTLINE_ENVS and not n.labels:
            continue
        keep.append(n)
    return keep


def build_outline(workspace: "ShadowWorkspace", nodes: Optional[List[DocumentNode]] = None) -> str:
    """One line per structural node: ``L12-40  sec:results  [section] Results``."""
    nodes = nodes if nodes is not None else workspace.get_nodes()
    depth: Dict[str, int] = {}
    rows = []
    shown = _outline_nodes(nodes)
    for n in shown[:OUTLINE_MAX]:
        d = depth.get(n.parent_id, -1) + 1 if n.parent_id else 0
        depth[n.node_id] = d
        title = re.sub(r"\s+", " ", n.title)[:60]
        label = f" label={n.labels[0]}" if n.labels else ""
        rows.append(f"{'  ' * min(d, 4)}L{n.start_line}-{n.end_line}  {n.node_id}  [{n.kind if n.kind != 'env' else n.name}]"
                    f"{' ' + title if title else ''}{label}")
    if len(shown) > OUTLINE_MAX:
        rows.append(f"... {len(shown) - OUTLINE_MAX} more nodes (use inspect_document)")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Matching the request to nodes
# ---------------------------------------------------------------------------

_ORDINAL_RE = re.compile(r"\b(slide|frame|section|chapter|subsection|page)\s*(?:no\.?|number|#)?\s*(\d+)\b", re.I)
_QUOTED_RE = re.compile(r"[\"“'‘`]([^\"”'’`]{4,80})[\"”'’`]")
_WORD_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "last": -1}


def match_nodes(code: str, nodes: List[DocumentNode], instruction: str) -> List[Tuple[DocumentNode, str]]:
    """Nodes the request is about, with the reason each was picked (best first)."""
    low = instruction.lower()
    picked: List[Tuple[DocumentNode, str]] = []
    seen: Set[str] = set()

    def add(n: Optional[DocumentNode], why: str) -> None:
        if n is not None and n.node_id not in seen and n.kind != "preamble":
            seen.add(n.node_id)
            picked.append((n, why))

    # Explicit ordinals: "slide 3", "section 2", "page 4" (a page of a deck is a frame).
    for m in _ORDINAL_RE.finditer(instruction):
        kind = {"page": "frame", "slide": "frame"}.get(m.group(1).lower(), m.group(1).lower())
        if kind == "frame" and not any(n.kind == "frame" for n in nodes):
            continue
        add(find_node(nodes, f"{kind} {m.group(2)}"), f"{m.group(1)} {m.group(2)}")
    for word, idx in _WORD_ORDINALS.items():
        m = re.search(rf"\b{word}\s+(slide|frame|section|chapter)\b", low)
        if m:
            kind = {"slide": "frame"}.get(m.group(1), m.group(1))
            same = [n for n in nodes if n.kind == kind]
            if same:
                add(same[idx] if idx == -1 else (same[idx - 1] if idx <= len(same) else None), m.group(0))

    # Labels and node IDs written out.
    for n in nodes:
        if n.node_id.lower() in low or any(l.lower() in low for l in n.labels):
            add(n, "named")

    # The document title.
    if re.search(r"\b(title|heading of the (?:document|presentation|paper)|title slide|title page)\b", low) \
            and not re.search(r"\b(frame|slide|section)\s+title", low):
        add(find_node(nodes, "meta:title"), "title")
        add(next((n for n in nodes if n.kind == "maketitle"), None), "title page")
        add(next((n for n in nodes if n.kind == "frame" and "\\titlepage" in code[n.start:n.end]), None), "title frame")

    # Titles mentioned in the request.
    for n in nodes:
        if n.kind in ("frame", "section", "subsection", "subsubsection", "chapter", "part") and n.title:
            t = slugify(n.title).replace("-", " ")
            if len(t) >= 4 and re.search(r"\b" + re.escape(t) + r"\b", re.sub(r"[^a-z0-9]+", " ", low)):
                add(n, f"title '{n.title[:40]}'")

    # Quoted text from the document.
    for m in _QUOTED_RE.finditer(instruction):
        q = m.group(1).strip()
        pos = code.find(q)
        if pos != -1 and code.find(q, pos + 1) == -1:
            inner = [n for n in nodes if n.start <= pos < n.end and n.kind != "preamble"]
            if inner:
                add(min(inner, key=lambda n: n.end - n.start), f"quoted '{q[:30]}'")

    # Pages of an imported PDF: "page 2" when the document has no frames.
    for m in re.finditer(r"\bpage\s*(\d+)\b", low):
        if not any(n.kind == "frame" for n in nodes):
            add(find_node(nodes, f"page {m.group(1)}"), f"page {m.group(1)}")

    # Environment kinds named in the request.
    for env, words in (("abstract", ("abstract",)), ("thebibliography", ("bibliography", "references")),):
        if any(w in low for w in words):
            add(next((n for n in nodes if n.name == env), None), env)

    return picked[:MAX_TARGET_NODES]


def request_terms(instruction: str) -> List[str]:
    """Words and quoted phrases of the request that could name text in the document."""
    terms = [m.group(1).strip() for m in _QUOTED_RE.finditer(instruction)]
    for w in re.findall(r"[A-Za-z0-9][\w.\-/]{2,}", _QUOTED_RE.sub(" ", instruction)):
        if w.lower() not in _STOPWORDS and w not in terms:
            terms.append(w)
    return terms[:12]


def text_hits(code: str, instruction: str) -> List[Tuple[int, str]]:
    """
    (line number, term) of body lines containing a word the request mentions,
    ignoring case. Documents without structure — an imported PDF is one long
    flow of text — have no node to match, and the request's own words ("change
    jacob to …") are the only pointer to the target. Terms occurring on more
    than a handful of lines are too common to point anywhere and are skipped.
    """
    m = re.search(r"\\begin\s*\{document\}", code)
    body_start_line = code[:m.end()].count("\n") + 1 if m else 1
    lines = code.splitlines()
    hits: List[Tuple[int, str]] = []
    for term in request_terms(instruction):
        pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.IGNORECASE)
        found = [i + 1 for i, ln in enumerate(lines) if i + 1 > body_start_line and pat.search(ln)]
        if 0 < len(found) <= 5:
            hits.extend((n, term) for n in found)
    seen: Set[int] = set()
    out = []
    for n, t in hits:
        if n not in seen:
            seen.add(n)
            out.append((n, t))
    return out[:MAX_TEXT_HITS]


# ---------------------------------------------------------------------------
# Styling lines from the preamble
# ---------------------------------------------------------------------------

def style_lines_for(code: str, fragment: str, instruction: str = "") -> List[str]:
    """
    Preamble lines that decide how ``fragment`` looks: beamer font/colour/template
    settings for elements the fragment or request involves, colour definitions
    it uses, and the definitions of macros it calls. Line-numbered.
    """
    m = re.search(r"\\begin\s*\{document\}", code)
    pre = code[:m.start()] if m else ""
    if not pre:
        return []
    low = (instruction or "").lower() + " " + fragment.lower()
    elements: Set[str] = set()
    for element, words in _STYLE_ELEMENTS.items():
        if any(w in low for w in words):
            elements.add(element)
    if "\\titlepage" in fragment or "\\maketitle" in fragment or "\\title" in fragment:
        elements.add("title")
    if "\\begin{frame}" in fragment or "\\frametitle" in fragment:
        elements.add("frametitle")
    colors = set(re.findall(r"(?:\\textcolor|\\color|\\colorbox|\\cellcolor)\s*\{([^}]+)\}", fragment))
    colors |= set(re.findall(r"(?:fg|bg|fill|draw|text)=([A-Za-z][\w!.-]*)", fragment))
    macros = set(re.findall(r"\\([A-Za-z]+)", fragment))

    out = []
    for i, line in enumerate(pre.splitlines(), start=1):
        s = line.strip()
        if not s or s.startswith("%"):
            continue
        keep = False
        bm = re.match(r"\\setbeamer(?:font|color|template)\*?\s*\{([^}]+)\}", s)
        if bm and any(e == bm.group(1) or bm.group(1).startswith(e) for e in elements):
            keep = True
        dm = re.match(r"\\(?:definecolor|colorlet)\s*\{([^}]+)\}", s)
        if dm and dm.group(1) in colors:
            keep = True
        nm = re.match(r"\\(?:re)?newcommand\*?\s*\{?\\([A-Za-z]+)\}?", s)
        if nm and nm.group(1) in macros:
            keep = True
        if ("title" in elements and re.match(r"\\(?:title|subtitle|author|date|institute)\b", s)):
            keep = True
        if keep:
            out.append(f"{i}: {line}")
    return out[:30]


# ---------------------------------------------------------------------------
# Initial context
# ---------------------------------------------------------------------------

def build_targeted_context(workspace: "ShadowWorkspace", instruction: str) -> Tuple[str, Dict[str, Any]]:
    """
    Initial context for a targeted edit (levels 1–4). Returns (text, info) where
    info records which levels/nodes were used, for the trace.
    """
    code = workspace.get_buffer()
    nodes = workspace.get_nodes()
    total = workspace.get_line_count()
    outline = build_outline(workspace, nodes)
    matched = match_nodes(code, nodes, instruction)
    info: Dict[str, Any] = {"levels": [], "nodes": [n.node_id for n, _ in matched], "strategy": "targeted"}

    parts = [f"DOCUMENT OUTLINE ({total} lines; node_id per block — address blocks by node_id):", outline]
    sent: List[Tuple[int, int]] = []

    def add_lines(a: int, b: int, header: str) -> None:
        a, b = max(1, a), min(total, b)
        for s, e in sent:
            if a >= s and b <= e:
                return
        sent.append((a, b))
        parts.append(f"\n--- {header} (lines {a}-{b}) ---")
        parts.append(workspace.read_lines(a, b))

    if matched:
        info["levels"].append(1)
        for node, why in matched:
            a, b = node.start_line, node.end_line
            if node.kind == "meta":
                a, b = a, b
            if b - a + 1 > MAX_NODE_LINES:
                add_lines(a, a + MAX_NODE_LINES // 2, f"TARGET {node.node_id} [{why}] — start")
                add_lines(b - MAX_NODE_LINES // 4, b, f"TARGET {node.node_id} — end (middle omitted; use get_block)")
            else:
                small = (b - a) < 30
                lo = a - (NEIGHBOUR_LINES if small and node.kind != "meta" else 0)
                hi = b + (NEIGHBOUR_LINES if small and node.kind != "meta" else 0)
                if small and node.kind != "meta":
                    info["levels"].append(3)
                add_lines(lo, hi, f"TARGET {node.node_id} [{why}]")
            if node.parent_id:
                parent = next((n for n in nodes if n.node_id == node.parent_id), None)
                if parent and parent.kind != "preamble" and not any(s <= parent.start_line <= e for s, e in sent):
                    info["levels"].append(2)
                    parts.append(f"\n(parent {parent.node_id} starts at line {parent.start_line}: "
                                 f"{workspace.read_lines(parent.start_line, parent.start_line).split(': ', 1)[-1][:120]})")
        style = style_lines_for(code, "\n".join(code[n.start:n.end] for n, _ in matched), instruction)
        style = [l for l in style if not any(s <= int(l.split(":", 1)[0]) <= e for s, e in sent)]
        if style:
            info["levels"].append(4)
            parts.append("\n--- RELEVANT PREAMBLE STYLE LINES ---")
            parts.extend(style)
    hits = [] if matched else text_hits(code, instruction)
    if hits:
        info["levels"].append(1)
        info["text_hits"] = [t for _, t in hits]
        for n, term in hits:
            add_lines(n - TEXT_HIT_RADIUS, n + TEXT_HIT_RADIUS, f"TEXT MATCH '{term}' (case-insensitive)")
    if not matched and not hits and total <= UNSTRUCTURED_FULL_LINES and not any(
            n.kind in ("section", "chapter", "frame", "subsection") for n in nodes):
        # Nothing points anywhere and the document has no structure to navigate
        # by: a modest document is cheaper to show whole than to search blind.
        info["levels"].append(5)
        add_lines(1, total, "FULL DOCUMENT (no block could be identified from the request)")
    elif not matched and not hits:
        # Nothing identifiable: the outline plus preamble styling the request mentions.
        style = style_lines_for(code, "", instruction)
        if style:
            info["levels"].append(4)
            parts.append("\n--- RELEVANT PREAMBLE STYLE LINES ---")
            parts.extend(style)
        parts.append("\nNo specific block was identified from the request. Use get_block(node_id) or "
                     "search_document to read only what you need before editing.")

    info["levels"] = sorted(set(info["levels"]))
    info["sent_ranges"] = sent
    return "\n".join(parts), info


# ---------------------------------------------------------------------------
# De-duplication of re-sent content
# ---------------------------------------------------------------------------

class ContextLedger:
    """
    Remembers which numbered lines the model has already been shown and can
    still see: the first message (never compacted) permanently, tool output
    only for the recent turns that history compaction keeps verbatim.
    """

    def __init__(self, visible_steps: int = 2):
        self.visible_steps = visible_steps
        self.step = 0
        self._permanent: Set[Tuple[int, str]] = set()
        self._recent: Dict[Tuple[int, str], int] = {}

    @staticmethod
    def _lines(content: str) -> List[Tuple[int, str]]:
        out = []
        for ln in content.splitlines():
            m = re.match(r"^(\d+): (.*)$", ln)
            if m:
                out.append((int(m.group(1)), m.group(2)))
        return out

    def mark_permanent(self, content: str) -> None:
        self._permanent.update(self._lines(content))

    def _visible(self, key: Tuple[int, str]) -> bool:
        if key in self._permanent:
            return True
        st = self._recent.get(key)
        return st is not None and self.step - st < self.visible_steps

    def filter(self, content: str) -> str:
        """Collapses runs of already-visible, unchanged lines to a pointer; records the rest."""
        lines = content.splitlines()
        out: List[str] = []
        run: List[int] = []

        def flush() -> None:
            if not run:
                return
            if len(run) >= 3:
                out.append(f"[lines {run[0]}-{run[-1]} unchanged — already in your context above]")
            else:
                out.extend(f"{n}: {t}" for n, t in pending)
            run.clear()
            pending.clear()

        pending: List[Tuple[int, str]] = []
        for raw in lines:
            m = re.match(r"^(\d+): (.*)$", raw)
            if not m:
                flush()
                out.append(raw)
                continue
            key = (int(m.group(1)), m.group(2))
            if self._visible(key):
                run.append(key[0])
                pending.append(key)
                continue
            flush()
            out.append(raw)
            self._recent[key] = self.step
        flush()
        return "\n".join(out)
