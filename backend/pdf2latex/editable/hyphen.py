"""
hyphen.py — Tell a word broken by hyphenation from a compound broken at its own hyphen.

A line that ends "high-" before a line starting "dimensional" may be the word "highdimensional"
hyphenated by the typesetter or the compound "high-dimensional" broken after its hyphen; dropping
the hyphen is right for the first and corrupts the text for the second. The document itself
usually decides it (the compound, or the joined word, appears elsewhere on one line); otherwise
TeX's own US English patterns (hyphen.tex, Liang's algorithm) do: TeX only ever breaks a word at a
point its patterns allow, so a break the patterns don't allow was a real hyphen.
"""

from __future__ import annotations

import re
import subprocess
from functools import lru_cache
from typing import Dict, Iterable, Optional, Set, Tuple

_WORD = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)*")
LEFT_MIN, RIGHT_MIN = 2, 3        # \lefthyphenmin / \righthyphenmin of LaTeX's English


@lru_cache(maxsize=1)
def _patterns() -> Optional[Tuple[Dict[str, Tuple[int, ...]], Dict[str, Set[int]]]]:
    try:
        path = subprocess.run(["kpsewhich", "hyphen.tex"], capture_output=True, text=True,
                              timeout=10).stdout.strip()
        text = open(path, encoding="latin-1").read() if path else ""
    except (OSError, subprocess.SubprocessError):
        return None
    text = re.sub(r"%.*", "", text)
    pm = re.search(r"\\patterns\{([^}]*)\}", text)
    if not pm:
        return None
    pats: Dict[str, Tuple[int, ...]] = {}
    for tok in pm.group(1).split():
        letters = re.sub(r"\d", "", tok)
        vals = [0] * (len(letters) + 1)
        k = 0
        for ch in tok:
            if ch.isdigit():
                vals[k] = int(ch)
            else:
                k += 1
        pats[letters] = tuple(vals)
    exc: Dict[str, Set[int]] = {}
    em = re.search(r"\\hyphenation\{([^}]*)\}", text)
    for tok in (em.group(1).split() if em else []):
        parts = tok.split("-")
        pos, acc = set(), 0
        for p in parts[:-1]:
            acc += len(p)
            pos.add(acc)
        exc["".join(parts)] = pos
    return pats, exc


def tex_breaks(word: str) -> Optional[Set[int]]:
    """Positions where TeX may hyphenate the word (a break before word[i]); None if TeX's patterns
    are not available here."""
    data = _patterns()
    if data is None:
        return None
    pats, exc = data
    w = word.lower()
    if w in exc:
        return set(exc[w])
    s = f".{w}."
    vals = [0] * (len(s) + 1)
    for i in range(len(s)):
        for j in range(i + 1, len(s) + 1):
            p = pats.get(s[i:j])
            if p:
                for k, v in enumerate(p):
                    if v > vals[i + k]:
                        vals[i + k] = v
    # vals[i] sits before s[i]; s[0] is the leading dot, so word position n is vals[n + 1]
    return {n for n in range(LEFT_MIN, len(w) - RIGHT_MIN + 1) if vals[n + 1] % 2 == 1}


def vocabulary(lines: Iterable[str]) -> Tuple[Set[str], Set[str]]:
    """(plain words, hyphenated compounds) of the document's lines, leaving out each line's
    trailing "fragment-" and the fragment that continues it on the next line."""
    words: Set[str] = set()
    compounds: Set[str] = set()
    cont = False
    for text in lines:
        toks = text.split()
        if not toks:
            cont = False
            continue
        ends_hyphen = toks[-1].endswith("-") and len(toks[-1]) > 1
        body = toks[1 if cont else 0:len(toks) - (1 if ends_hyphen else 0)]
        for t in body:
            for m in _WORD.finditer(t):
                w = m.group(0).lower()
                (compounds if "-" in w else words).add(w)
        cont = ends_hyphen
    return words, compounds


def keep_hyphen(left: str, right: str, words: Set[str], compounds: Set[str]) -> bool:
    """Whether the hyphen ending ``left`` (a line's last token, "high-") belongs to the word it
    joins with ``right`` (the next line's first token)."""
    lm = re.search(r"([A-Za-z]+(?:-[A-Za-z]+)*)-$", left)
    rm = re.match(r"[A-Za-z]+(?:-[A-Za-z]+)*", right)
    if not lm or not rm:
        return False
    a, b = lm.group(1), rm.group(0)
    if f"{a}-{b}".lower() in compounds:
        return True
    tail = a.split("-")[-1]
    if (tail + b.split("-")[0]).lower() in words:
        return False
    breaks = tex_breaks(tail + b.split("-")[0])
    if breaks is None:
        return False
    return len(tail) not in breaks
