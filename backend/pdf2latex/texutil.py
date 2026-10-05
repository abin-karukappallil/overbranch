"""
texutil.py — pdfLaTeX-safe text handling.

pdfLaTeX (inputenc utf8 + T1) accepts Latin-1 and Latin Extended-A characters
directly; everything else must be spelled as a LaTeX command. `latex_text` turns
extracted PDF text into compile-safe LaTeX (specials escaped, Unicode mapped);
`sanitize_unicode` maps stray Unicode in LLM-written LaTeX without touching markup.
"""

import unicodedata
from typing import Dict, List, Optional, Set, Tuple

_ESCAPES = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "&": r"\&",
    "#": r"\#",
    "^": r"\textasciicircum{}",
    "_": r"\_",
    "%": r"\%",
    "~": r"\textasciitilde{}",
}

_DROP = {"�", "​", "‌", "‍", "⁠", "﻿", "­"}


def _m(cmd: str) -> str:
    return "\\ensuremath{" + cmd + "}"


UNICODE_MAP: Dict[str, str] = {
    # spaces
    " ": "~", " ": " ", " ": "\\quad{}", " ": " ", " ": "\\,", " ": "\\,", " ": "\\,",
    # quotes & dashes
    "‘": "`", "’": "'", "‚": ",", "‛": "`", "“": "``", "”": "''", "„": ",,",
    "′": _m("'"), "″": _m("''"),
    "‐": "-", "‑": "-", "‒": "--", "–": "--", "—": "---", "―": "---", "−": _m("-"),
    # punctuation & symbols
    "…": "\\ldots{}", "•": "\\textbullet{}", "‣": "\\textbullet{}", "⁃": "-", "∙": _m("\\bullet"),
    "·": "\\textperiodcentered{}", "°": "\\textdegree{}", "©": "\\textcopyright{}",
    "®": "\\textregistered{}", "™": "\\texttrademark{}", "€": "\\texteuro{}", "£": "\\pounds{}",
    "§": "\\S{}", "¶": "\\P{}", "†": "\\dag{}", "‡": "\\ddag{}", "‰": "\\textperthousand{}",
    "№": "No.", "¬": _m("\\neg"),
    "²": "\\textsuperscript{2}", "³": "\\textsuperscript{3}", "¹": "\\textsuperscript{1}",
    "¼": "\\textonequarter{}", "½": "\\textonehalf{}", "¾": "\\textthreequarters{}",
    # math
    "×": _m("\\times"), "÷": _m("\\div"), "±": _m("\\pm"), "µ": _m("\\mu"),
    "≤": _m("\\leq"), "≥": _m("\\geq"), "≠": _m("\\neq"), "≈": _m("\\approx"),
    "≡": _m("\\equiv"), "∞": _m("\\infty"), "√": _m("\\surd"), "∑": _m("\\sum"),
    "∏": _m("\\prod"), "∫": _m("\\int"), "∂": _m("\\partial"), "∇": _m("\\nabla"),
    "∈": _m("\\in"), "∉": _m("\\notin"), "⊂": _m("\\subset"), "⊆": _m("\\subseteq"),
    "⊃": _m("\\supset"), "⊇": _m("\\supseteq"), "∪": _m("\\cup"), "∩": _m("\\cap"),
    "∀": _m("\\forall"), "∃": _m("\\exists"), "∅": _m("\\emptyset"), "∧": _m("\\wedge"),
    "∨": _m("\\vee"), "≅": _m("\\cong"), "∝": _m("\\propto"), "∘": _m("\\circ"),
    "⋅": _m("\\cdot"), "∗": _m("\\ast"), "⊕": _m("\\oplus"), "⊗": _m("\\otimes"),
    # arrows
    "→": _m("\\rightarrow"), "←": _m("\\leftarrow"), "↔": _m("\\leftrightarrow"),
    "↑": _m("\\uparrow"), "↓": _m("\\downarrow"), "⇒": _m("\\Rightarrow"),
    "⇐": _m("\\Leftarrow"), "⇔": _m("\\Leftrightarrow"), "➔": _m("\\rightarrow"),
    "➜": _m("\\rightarrow"), "➡": _m("\\rightarrow"),
    # dingbats / geometric shapes (amssymb)
    "✓": _m("\\checkmark"), "✔": _m("\\checkmark"), "✗": _m("\\times"), "✘": _m("\\times"),
    "●": _m("\\bullet"), "○": _m("\\circ"), "◦": _m("\\circ"), "■": _m("\\blacksquare"),
    "▪": _m("\\blacksquare"), "□": _m("\\square"), "▫": _m("\\square"),
    "▶": _m("\\blacktriangleright"), "►": _m("\\blacktriangleright"), "➢": _m("\\blacktriangleright"),
    "◆": _m("\\blacklozenge"), "◇": _m("\\lozenge"), "♦": _m("\\diamondsuit"), "★": _m("\\bigstar"),
    "": "\\textbullet{}", "": _m("\\blacksquare"), "": _m("\\blacktriangleright"),
}

_GREEK_UPPER_CMDS = {"GAMMA", "DELTA", "THETA", "LAMBDA", "XI", "PI", "SIGMA", "UPSILON", "PHI", "PSI", "OMEGA"}
_GREEK_LATIN = {"ALPHA": "A", "BETA": "B", "EPSILON": "E", "ZETA": "Z", "ETA": "H", "IOTA": "I", "KAPPA": "K",
                "MU": "M", "NU": "N", "OMICRON": "O", "RHO": "P", "TAU": "T", "CHI": "X"}


def _greek(ch: str) -> Optional[str]:
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return None
    if name.startswith("GREEK SMALL LETTER "):
        letter = name[len("GREEK SMALL LETTER "):]
        if letter == "FINAL SIGMA":
            return _m("\\varsigma")
        if letter == "OMICRON":
            return "o"
        if " " in letter:
            return None
        return _m("\\" + letter.lower())
    if name.startswith("GREEK CAPITAL LETTER "):
        letter = name[len("GREEK CAPITAL LETTER "):]
        if letter in _GREEK_UPPER_CMDS:
            return _m("\\" + letter.capitalize())
        return _GREEK_LATIN.get(letter)
    return None


def _map_char(ch: str, unknown: Optional[Set[str]] = None) -> str:
    cp = ord(ch)
    if cp < 128:
        return ch
    if ch in _DROP or (0xE000 <= cp <= 0xF8FF and ch not in UNICODE_MAP):
        return ""
    if ch in UNICODE_MAP:
        return UNICODE_MAP[ch]
    if 0xA0 <= cp <= 0x17F:
        return ch  # Latin-1 Supplement / Latin Extended-A: handled by inputenc utf8 + T1
    greek = _greek(ch)
    if greek is not None:
        return greek
    decomposed = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
    if decomposed and decomposed != ch and all(ord(c) < 128 or 0xA0 <= ord(c) <= 0x17F for c in decomposed):
        return decomposed
    if unknown is not None:
        unknown.add(ch)
    return ""


def latex_text(text: str, unknown: Optional[Set[str]] = None) -> str:
    """Extracted PDF text → LaTeX text for pdfLaTeX (specials escaped, Unicode mapped)."""
    out: List[str] = []
    for ch in unicodedata.normalize("NFC", text):
        if ch == "\t":
            out.append(" ")
        elif ord(ch) < 32:
            continue
        elif ch in _ESCAPES:
            out.append(_ESCAPES[ch])
        else:
            out.append(_map_char(ch, unknown))
    return "".join(out)


def sanitize_unicode(latex: str) -> Tuple[str, List[str]]:
    """Maps non-ASCII characters in LaTeX source to pdfLaTeX-safe spellings. Returns (latex, dropped chars)."""
    unknown: Set[str] = set()
    out = "".join(_map_char(ch, unknown) for ch in unicodedata.normalize("NFC", latex))
    return out, sorted(unknown)


def fmt(v: float, nd: int = 2) -> str:
    """Compact fixed-point number formatting (no exponent, trailing zeros removed)."""
    s = f"{v:.{nd}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s
