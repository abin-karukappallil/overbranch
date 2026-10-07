"""
opencode/locator.py — Finding where an edit belongs without trusting exact text.

The model names a target the way it remembers it: a node ID from the outline,
a snippet copied from an earlier read, a line number. By the time the edit is
applied, an earlier edit may have changed the neighbourhood, the model may have
normalised whitespace or quotes, or the user may have typed. Failing on the
first exact-match miss turned each of those into another LLM round trip (or an
edit silently dropped in the UI).

``resolve`` walks a fixed hierarchy and stops at the first confident answer:

    1. node      — stable structural node ID / label / ordinal (document_index)
    2. exact     — the text occurs exactly once (within the node, if one was named)
    3. exact+hint — several exact hits, disambiguated by context or line hint
    4. normalized — same text modulo line endings, indentation, runs of blanks,
                    smart quotes, ``~`` and trailing whitespace
    5. fuzzy     — the most similar line window, accepted only when clearly
                    better than the runner-up (never on a tie)

Every step is recorded in ``attempts`` so a failure can say exactly what was
tried. Nothing here mutates the document.
"""

from __future__ import annotations

import bisect
import difflib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from document_index import DocumentNode, find_node, index_nodes

FUZZY_ACCEPT = 0.88      # minimum similarity for a fuzzy match
FUZZY_MARGIN = 0.05      # how much better than the runner-up it must be
FUZZY_MIN_CHARS = 24     # shorter snippets are too ambiguous to match fuzzily
FUZZY_MAX_CANDIDATES = 60


@dataclass
class Target:
    node_id: Optional[str] = None
    text: Optional[str] = None
    line_hint: Optional[int] = None
    context_before: Optional[str] = None
    context_after: Optional[str] = None


@dataclass
class Resolution:
    ok: bool
    start: int = 0
    end: int = 0
    method: str = ""
    confidence: float = 0.0
    node_id: Optional[str] = None
    attempts: List[Dict[str, Any]] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok, "method": self.method, "confidence": round(self.confidence, 3),
            "node_id": self.node_id, "attempts": self.attempts, "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Normalisation with an offset map back into the original text
# ---------------------------------------------------------------------------

_QUOTES = {"‘": "'", "’": "'", "“": '"', "”": '"', " ": " ", "~": " "}


def normalize_with_map(text: str) -> Tuple[str, List[Tuple[int, int]]]:
    """
    Returns (normalized, spans) where spans[i] = (orig_start, orig_end) of the
    original characters that produced normalized[i].

    Rules: CRLF → LF; leading and trailing blanks of each line dropped; runs of
    blanks collapsed to one space; ``` `` ``` / ``''`` / smart quotes → ``"``,
    single smart quotes → ``'``; ``~`` and NBSP → space.
    """
    out: List[str] = []
    spans: List[Tuple[int, int]] = []
    i, n = 0, len(text)
    at_line_start = True
    while i < n:
        c = text[i]
        if c == "\r":
            i += 1
            continue
        if c == "\n":
            # drop trailing blank emitted before the newline
            while out and out[-1] == " ":
                out.pop()
                spans.pop()
            out.append("\n")
            spans.append((i, i + 1))
            i += 1
            at_line_start = True
            continue
        if c in " \t" or _QUOTES.get(c) == " ":
            j = i
            while j < n and (text[j] in " \t" or _QUOTES.get(text[j]) == " "):
                j += 1
            if not at_line_start:
                out.append(" ")
                spans.append((i, j))
            i = j
            continue
        at_line_start = False
        if text.startswith("``", i) or text.startswith("''", i):
            out.append('"')
            spans.append((i, i + 2))
            i += 2
            continue
        out.append(_QUOTES.get(c, c))
        spans.append((i, i + 1))
        i += 1
    while out and out[-1] in " \n":
        out.pop()
        spans.pop()
    return "".join(out), spans


def _normalize(text: str) -> str:
    return normalize_with_map(text)[0].strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _Lines:
    def __init__(self, code: str):
        self.starts = [0] + [m.end() for m in re.finditer(r"\n", code)]

    def line_of(self, offset: int) -> int:
        return bisect.bisect_right(self.starts, offset)


def _all_occurrences(hay: str, needle: str, lo: int, hi: int) -> List[int]:
    out = []
    i = hay.find(needle, lo, hi)
    while i != -1:
        out.append(i)
        i = hay.find(needle, i + 1, hi)
    return out


def _pick_by_hint(code: str, hits: List[int], length: int, target: Target, lines: _Lines) -> Optional[int]:
    """Disambiguates several hits by surrounding context, then by line hint."""
    if target.context_before or target.context_after:
        cb = _normalize(target.context_before or "")
        ca = _normalize(target.context_after or "")
        good = []
        for h in hits:
            before = _normalize(code[max(0, h - 400):h])
            after = _normalize(code[h + length:h + length + 400])
            if (not cb or before.endswith(cb[-120:])) and (not ca or after.startswith(ca[:120])):
                good.append(h)
        if len(good) == 1:
            return good[0]
        if good:
            hits = good
    if target.line_hint:
        dist = sorted((abs(lines.line_of(h) - target.line_hint), h) for h in hits)
        if len(dist) == 1 or dist[0][0] < dist[1][0]:
            return dist[0][1]
    return None


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def resolve_node(code: str, ref: str, aliases: Optional[Dict[str, str]] = None,
                 nodes: Optional[List[DocumentNode]] = None) -> Optional[DocumentNode]:
    nodes = nodes if nodes is not None else index_nodes(code)
    seen = set()
    while aliases and ref in aliases and ref not in seen:
        seen.add(ref)
        ref = aliases[ref]
    node = find_node(nodes, ref)
    if node is None:
        # Legacy positional chunk IDs (section_2, frame_3, chapter_1, preamble).
        m = re.fullmatch(r"(section|frame|chapter)_(\d+)", ref or "")
        if m:
            node = find_node(nodes, f"{m.group(1)} {m.group(2)}")
    return node


def resolve(code: str, target: Target, aliases: Optional[Dict[str, str]] = None) -> Resolution:
    """Locates ``target`` in ``code``. See the module docstring for the hierarchy."""
    attempts: List[Dict[str, Any]] = []
    lines = _Lines(code)
    nodes = index_nodes(code)
    node: Optional[DocumentNode] = None

    if target.node_id:
        node = resolve_node(code, target.node_id, aliases, nodes)
        attempts.append({"method": "node", "ref": target.node_id, "outcome": "found" if node else "not_found"})
        if node and not target.text:
            return Resolution(True, node.start, node.end, "node", 1.0, node.node_id, attempts)

    if not target.text:
        return Resolution(False, attempts=attempts, reason="target_not_found" if target.node_id else "no_target")

    scopes: List[Tuple[int, int, Optional[str]]] = []
    if node:
        scopes.append((node.start, node.end, node.node_id))
    scopes.append((0, len(code), None))

    # Cheap, certain methods first everywhere; similarity only after they all
    # failed. (A fuzzy hit inside the named node must not beat an exact or
    # normalised hit that merely extends past the node's end.)
    for phase in ("exact", "normalized", "fuzzy"):
        for lo, hi, scope_id in scopes:
            res = _resolve_text(code, target, lo, hi, scope_id, lines, attempts, phase)
            if res is not None:
                res.attempts = attempts
                if res.node_id is None:
                    res.node_id = _innermost_node(nodes, res.start, res.end)
                return res

    ambiguous = any(a.get("outcome") == "ambiguous" for a in attempts)
    return Resolution(False, attempts=attempts, node_id=node.node_id if node else None,
                      reason="ambiguous" if ambiguous else "target_not_found")


def _innermost_node(nodes: List[DocumentNode], start: int, end: int) -> Optional[str]:
    best = None
    for n in nodes:
        if n.start <= start and end <= n.end and n.kind != "preamble":
            if best is None or (n.end - n.start) <= (best.end - best.start):
                best = n
    if best is None:
        pre = next((n for n in nodes if n.kind == "preamble"), None)
        if pre and end <= pre.end:
            return pre.node_id
    return best.node_id if best else None


def _resolve_text(code: str, target: Target, lo: int, hi: int, scope_id: Optional[str],
                  lines: _Lines, attempts: List[Dict[str, Any]], phase: str) -> Optional[Resolution]:
    needle = target.text or ""
    scope = scope_id or "document"
    if phase == "exact":
        return _exact(code, needle, target, lo, hi, scope, lines, attempts)
    if phase == "normalized":
        return _normalized(code, needle, target, lo, hi, scope, lines, attempts)
    return _fuzzy_phase(code, needle, target, lo, hi, scope, lines, attempts)


def _exact(code: str, needle: str, target: Target, lo: int, hi: int, scope: str,
           lines: _Lines, attempts: List[Dict[str, Any]]) -> Optional[Resolution]:
    hits = _all_occurrences(code, needle, lo, hi)
    if len(hits) == 1:
        attempts.append({"method": "exact", "scope": scope, "outcome": "found"})
        return Resolution(True, hits[0], hits[0] + len(needle), "exact", 1.0, None)
    if len(hits) > 1:
        pick = _pick_by_hint(code, hits, len(needle), target, lines)
        attempts.append({"method": "exact", "scope": scope, "outcome": "found" if pick is not None else "ambiguous",
                         "matches": len(hits)})
        if pick is not None:
            return Resolution(True, pick, pick + len(needle), "exact+hint", 0.97, None)
        return None
    attempts.append({"method": "exact", "scope": scope, "outcome": "not_found"})
    return None


def _normalized(code: str, needle: str, target: Target, lo: int, hi: int, scope: str,
                lines: _Lines, attempts: List[Dict[str, Any]]) -> Optional[Resolution]:
    hay, spans = normalize_with_map(code[lo:hi])
    n_needle = _normalize(needle)
    if n_needle:
        n_hits = _all_occurrences(hay, n_needle, 0, len(hay))
        mapped = [(lo + spans[h][0], lo + spans[h + len(n_needle) - 1][1]) for h in n_hits]
        if len(mapped) == 1:
            attempts.append({"method": "normalized", "scope": scope, "outcome": "found"})
            s, e = _extend_to_line_ends(code, mapped[0], needle)
            return Resolution(True, s, e, "normalized", 0.95, None)
        if len(mapped) > 1:
            starts = [m[0] for m in mapped]
            pick = _pick_by_hint(code, starts, 0, target, lines)
            attempts.append({"method": "normalized", "scope": scope,
                             "outcome": "found" if pick is not None else "ambiguous", "matches": len(mapped)})
            if pick is not None:
                s, e = _extend_to_line_ends(code, next(m for m in mapped if m[0] == pick), needle)
                return Resolution(True, s, e, "normalized+hint", 0.93, None)
            return None
        attempts.append({"method": "normalized", "scope": scope, "outcome": "not_found"})
        # Same text in a different case ("jacob" for "JACOB"): accepted only when
        # it occurs exactly once, and only if lower-casing keeps offsets aligned.
        low_hay, low_needle = hay.lower(), n_needle.lower()
        if len(low_hay) == len(hay) and len(low_needle) == len(n_needle):
            ci = _all_occurrences(low_hay, low_needle, 0, len(low_hay))
            if len(ci) == 1:
                attempts.append({"method": "normalized_ci", "scope": scope, "outcome": "found"})
                h = ci[0]
                s_, e_ = lo + spans[h][0], lo + spans[h + len(n_needle) - 1][1]
                return Resolution(True, s_, e_, "normalized_ci", 0.9, None)
            attempts.append({"method": "normalized_ci", "scope": scope,
                             "outcome": "ambiguous" if ci else "not_found"})
    return None


def _fuzzy_phase(code: str, needle: str, target: Target, lo: int, hi: int, scope: str,
                 lines: _Lines, attempts: List[Dict[str, Any]]) -> Optional[Resolution]:
    n_needle = _normalize(needle)
    if len(n_needle) < FUZZY_MIN_CHARS:
        attempts.append({"method": "fuzzy", "scope": scope, "outcome": "skipped_short"})
        return None
    fz = _fuzzy(code, n_needle, lo, hi, target, lines)
    if fz is None:
        attempts.append({"method": "fuzzy", "scope": scope, "outcome": "not_found"})
        return None
    s, e, score, runner_up = fz
    if score < FUZZY_ACCEPT:
        attempts.append({"method": "fuzzy", "scope": scope, "outcome": "below_threshold", "score": round(score, 3)})
        return None
    if score - runner_up < FUZZY_MARGIN:
        attempts.append({"method": "fuzzy", "scope": scope, "outcome": "ambiguous",
                         "score": round(score, 3), "runner_up": round(runner_up, 3)})
        return None
    attempts.append({"method": "fuzzy", "scope": scope, "outcome": "found", "score": round(score, 3)})
    return Resolution(True, s, e, "fuzzy", score, None)


def _extend_to_line_ends(code: str, span: Tuple[int, int], needle: str) -> Tuple[int, int]:
    """
    A normalized match drops leading indentation and trailing blanks. When the
    needle started at a line start (or ended at a line end) the replacement is
    meant to cover the whole line, so the span is widened to match.
    """
    s, e = span
    if needle[:1] in (" ", "\t"):
        ls = code.rfind("\n", 0, s) + 1
        if code[ls:s].strip() == "":
            s = ls
    if needle.endswith("\n"):
        nl = code.find("\n", e)
        if nl != -1 and code[e:nl].strip() == "":
            e = nl + 1
    return s, e


def _fuzzy(code: str, n_needle: str, lo: int, hi: int, target: Target,
           lines: _Lines) -> Optional[Tuple[int, int, float, float]]:
    """
    Best line window similar to the needle. Returns (start, end, score,
    runner_up_score) with the span narrowed to the matched characters.
    """
    needle_lines = [ln for ln in n_needle.split("\n") if ln.strip()]
    if not needle_lines:
        return None
    k = len(needle_lines)
    first, last = needle_lines[0], needle_lines[-1]

    first_line = lines.line_of(lo)
    last_line = lines.line_of(max(lo, hi - 1))
    doc_lines: List[Tuple[int, str]] = []
    for ln in range(first_line, last_line + 1):
        s = lines.starts[ln - 1]
        e = lines.starts[ln] - 1 if ln < len(lines.starts) else len(code)
        doc_lines.append((ln, _normalize(code[max(s, lo):min(e, hi)])))

    # Candidate window starts: lines resembling the needle's first (or last) line.
    def sim(a: str, b: str) -> float:
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        if sm.real_quick_ratio() < 0.5 or sm.quick_ratio() < 0.5:
            return 0.0
        return sm.ratio()

    scored = []
    for idx, (_ln, text) in enumerate(doc_lines):
        if not text:
            continue
        sc = max(sim(first, text), sim(last, text) if k > 1 else 0.0)
        if sc >= 0.5:
            scored.append((sc, idx))
    scored.sort(reverse=True)
    starts = set()
    for _sc, idx in scored[:FUZZY_MAX_CANDIDATES]:
        starts.add(idx)
        if k > 1:
            starts.add(max(0, idx - (k - 1)))  # matched the needle's last line

    results: List[Tuple[float, int, int]] = []
    for idx in sorted(starts):
        for size in (k - 1, k, k + 1):
            if size < 1:
                continue
            window = [t for _, t in doc_lines[idx:idx + size + 4] if t][:size]
            if not window:
                continue
            text = "\n".join(window)
            sm = difflib.SequenceMatcher(None, text, n_needle, autojunk=False)
            if sm.quick_ratio() < FUZZY_ACCEPT - 0.1:
                continue
            results.append((sm.ratio(), idx, size))
    if not results:
        return None
    results.sort(reverse=True)
    best_score, best_idx, best_size = results[0]

    # Window → original offsets (non-empty lines only, as matched).
    picked = []
    j = best_idx
    while j < len(doc_lines) and len(picked) < best_size:
        if doc_lines[j][1]:
            picked.append(doc_lines[j][0])
        j += 1
    start_line, end_line = picked[0], picked[-1]
    s = max(lo, lines.starts[start_line - 1])
    e = min(hi, lines.starts[end_line] - 1 if end_line < len(lines.starts) else len(code))

    # The runner-up is the best window that does not overlap the winner: two
    # overlapping windows are the same place, not a competing one.
    runner_up = 0.0
    for score, idx, size in results[1:]:
        cand_line = doc_lines[idx][0]
        if cand_line <= end_line and cand_line + size - 1 >= start_line:
            continue
        runner_up = score
        break
    if target.line_hint and runner_up and abs(start_line - target.line_hint) > 40:
        runner_up = max(runner_up, best_score)  # far from where the model said: do not guess
    return s, e, best_score, runner_up
