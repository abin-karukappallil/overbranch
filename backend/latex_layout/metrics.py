"""
metrics.py — How wide a string will be in the TeX font that sets it.

Widths come from the real font files of the TeX distribution (located with
kpsewhich), so a measurement matches what pdfLaTeX will produce: helvet is the
URW Nimbus Sans clone, carlito is metric-compatible with Calibri, and so on.
When a file is missing the PDF Base-14 metrics stand in (Helvetica, Times and
Courier are exactly what helvet / mathptmx / courier load).
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from functools import lru_cache
from typing import Dict, Optional, Tuple

logger = logging.getLogger("latex_layout.metrics")

# family -> (regular, bold, italic, bold-italic) font files
_FILES: Dict[str, Tuple[str, str, str, str]] = {
    "helvetica": ("uhvr8a.pfb", "uhvb8a.pfb", "uhvro8a.pfb", "uhvbo8a.pfb"),
    "times": ("utmr8a.pfb", "utmb8a.pfb", "utmri8a.pfb", "utmbi8a.pfb"),
    "courier": ("ucrr8a.pfb", "ucrb8a.pfb", "ucrro8a.pfb", "ucrbo8a.pfb"),
    "palatino": ("uplr8a.pfb", "uplb8a.pfb", "uplri8a.pfb", "uplbi8a.pfb"),
    "carlito": ("Carlito-Regular.ttf", "Carlito-Bold.ttf", "Carlito-Italic.ttf", "Carlito-BoldItalic.ttf"),
    "arimo": ("Arimo-Regular.ttf", "Arimo-Bold.ttf", "Arimo-Italic.ttf", "Arimo-BoldItalic.ttf"),
    "tinos": ("Tinos-Regular.ttf", "Tinos-Bold.ttf", "Tinos-Italic.ttf", "Tinos-BoldItalic.ttf"),
    "caladea": ("Caladea-Regular.ttf", "Caladea-Bold.ttf", "Caladea-Italic.ttf", "Caladea-BoldItalic.ttf"),
    "lmodern": ("lmroman10-regular.otf", "lmroman10-bold.otf", "lmroman10-italic.otf", "lmroman10-bolditalic.otf"),
    "lmsans": ("lmsans10-regular.otf", "lmsans10-bold.otf", "lmsans10-oblique.otf", "lmsans10-boldoblique.otf"),
    "lmmono": ("lmmono10-regular.otf", "lmmonolt10-bold.otf", "lmmono10-italic.otf", "lmmonolt10-boldoblique.otf"),
}

# Base-14 stand-ins: (regular, bold, italic, bold-italic)
_BASE14 = {
    "sans": ("helv", "hebo", "heit", "hebi"),
    "serif": ("tiro", "tibo", "tiit", "tibi"),
    "mono": ("cour", "cobo", "coit", "cobi"),
}
_FAMILY_CLASS = {
    "helvetica": "sans", "carlito": "sans", "arimo": "sans", "lmsans": "sans",
    "times": "serif", "palatino": "serif", "tinos": "serif", "caladea": "serif", "lmodern": "serif",
    "courier": "mono", "lmmono": "mono",
}


@lru_cache(maxsize=256)
def kpsewhich(name: str) -> Optional[str]:
    if not shutil.which("kpsewhich"):
        return None
    try:
        out = subprocess.run(["kpsewhich", name], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return None
    return out or None


def tex_package_available(pkg: str) -> bool:
    return kpsewhich(f"{pkg}.sty") is not None


@lru_cache(maxsize=64)
def _font(family: str, bold: bool, italic: bool):
    import pymupdf

    idx = (1 if bold else 0) + (2 if italic else 0)
    files = _FILES.get(family)
    if files:
        path = kpsewhich(files[idx]) or (kpsewhich(files[idx & 1]) if idx >= 2 else None)
        if path:
            try:
                return pymupdf.Font(fontfile=path)
            except Exception as e:
                logger.debug(f"Could not load {path}: {e}")
    base = _BASE14[_FAMILY_CLASS.get(family, family if family in _BASE14 else "serif")]
    return pymupdf.Font(base[idx])


def text_width(text: str, family: str = "helvetica", size: float = 10.0,
               bold: bool = False, italic: bool = False) -> float:
    """Width in pt of plain ``text`` set in ``family`` at ``size`` pt."""
    if not text:
        return 0.0
    return float(_font(family, bold, italic).text_length(text, fontsize=size))


def char_widths_ratio(text: str, family_a: str, family_b: str, bold: bool = False) -> float:
    """Width of ``text`` in family_a relative to family_b (1.0 = same)."""
    wb = text_width(text, family_b, 10.0, bold)
    return text_width(text, family_a, 10.0, bold) / wb if wb else 1.0


_RE_COMMENT = re.compile(r"(?<!\\)%.*")
_RE_ESCAPED = {r"\&": "&", r"\%": "%", r"\$": "$", r"\#": "#", r"\_": "_", r"\{": "{", r"\}": "}",
               r"\textbackslash": "\\", r"\ldots": "...", r"\dots": "...", r"\textendash": "-",
               r"\textemdash": "-", r"\rupee": "R", r"\textrupee": "R"}


def latex_to_plain(fragment: str) -> str:
    """
    Visible text of a LaTeX fragment, for measuring: comments, commands and
    optional arguments dropped, mandatory arguments kept, ``~`` and ``\\ `` as
    spaces, ``\\\\`` as a line break.
    """
    s = _RE_COMMENT.sub("", fragment or "")
    for k, v in _RE_ESCAPED.items():
        s = s.replace(k, v)
    s = s.replace("\\\\", "\n").replace("~", " ").replace("\\ ", " ")
    # Commands whose argument is not printed text.
    s = re.sub(r"\\(?:textcolor|color)\s*\{[^}]*\}", "", s)
    s = re.sub(r"\\(?:fontsize)\s*\{[^}]*\}\s*\{[^}]*\}", "", s)
    s = re.sub(r"\\(?:definecolor)\s*\{[^}]*\}\s*\{[^}]*\}\s*\{[^}]*\}", "", s)
    s = re.sub(r"\\(?:rule)\s*(?:\[[^\]]*\])?\s*\{[^}]*\}\s*\{[^}]*\}", "", s)
    s = re.sub(r"\\(?:setlength)\s*\{[^}]*\}\s*\{[^}]*\}", "", s)
    s = re.sub(r"\\(?:hspace|vspace|includegraphics|label|ref)\*?\s*(?:\[[^\]]*\])?\s*\{[^}]*\}", "", s)
    s = re.sub(r"\\(?:makebox|parbox|framebox|raisebox|resizebox|scalebox|obhfit)\s*(?:\[[^\]]*\])*\s*\{[^}]*\}(?:\s*\[[^\]]*\])?", "", s)
    s = re.sub(r"\\begin\s*\{[^}]*\}(?:\s*\[[^\]]*\])?(?:\s*\{[^}]*\})?|\\end\s*\{[^}]*\}", "", s)
    s = re.sub(r"\\[A-Za-z@]+\*?\s*(?:\[[^\]]*\])?", "", s)
    s = s.replace("{", "").replace("}", "")
    return re.sub(r"[ \t]+", " ", s).strip()


@lru_cache(maxsize=1)
def available_families() -> Tuple[str, ...]:
    return tuple(f for f, files in _FILES.items() if kpsewhich(files[0]))
