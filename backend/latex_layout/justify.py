"""
justify.py — The smallest LaTeX change that makes content fit its width.

Measurement first, then a fixed ladder of fixes, cheapest and least visible
first. Nothing is guessed: the decision depends only on the measured natural
width of the content against the available width.

    fits                           → alignment only (\\raggedright, \\centering,
                                     \\raggedleft, \\justifying) or no change
    paragraph too wide             → over-long unbreakable tokens get break
                                     points (only those tokens); the paragraph
                                     gets \\emergencystretch so TeX can wrap it
    one-line unit ≤ 10% too wide   → horizontal condense to the exact width
                                     (\\resizebox{W}{\\height}{…}: height kept)
    one-line unit > 10% too wide   → font size reduced (never below 85%), then
                                     condensed for whatever is left

Words are never broken unless the word alone is wider than the space it has.

Widths are measured by TeX itself when pdflatex is available (``\\settowidth``
in draft mode, with the document's own preamble, so fonts, sizes and macros are
exactly the document's), otherwise from the font files (metrics.py).
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .metrics import latex_to_plain, text_width

logger = logging.getLogger("latex_layout.justify")

CONDENSE_LIMIT = 1.10   # up to 10% too wide: condense horizontally
MIN_FONT_SCALE = 0.85   # never shrink type below 85% of its size
FIT_SLACK = 0.25        # pt: a measurement this close to the limit already fits

_ALIGN_CMD = {"left": "\\raggedright", "right": "\\raggedleft", "center": "\\centering", "justify": "\\justifying"}


@dataclass
class JustifyResult:
    latex: str
    strategy: str             # none | align | wrap | break_tokens | condense | shrink | shrink+condense
    measured_w: float
    target_w: float
    ratio: float
    changed: bool
    needs_packages: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    measured_by: str = "metrics"

    def as_dict(self) -> Dict[str, object]:
        d = asdict(self)
        d["measured_w"] = round(self.measured_w, 2)
        d["target_w"] = round(self.target_w, 2)
        d["ratio"] = round(self.ratio, 4)
        return d


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

def _pt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def tex_probe(preamble: str, fragments: List[str], extra_files: Optional[Dict[str, str]] = None,
              timeout: int = 30) -> Optional[Dict[str, float]]:
    """
    Measures with TeX: natural widths of ``fragments`` (as one-line boxes) and
    the document's \\textwidth / \\linewidth, all in pt. None when pdflatex is
    unavailable or the probe fails to run.
    """
    if not shutil.which("pdflatex"):
        return None
    body = ["\\makeatletter\\newlength\\obprobew\\makeatother"]
    for i, frag in enumerate(fragments):
        body.append(f"\\settowidth\\obprobew{{\\mbox{{{frag}}}}}\\typeout{{OB-W{i}=\\the\\obprobew}}")
    body.append("\\typeout{OB-TW=\\the\\textwidth}\\typeout{OB-LW=\\the\\linewidth}")
    src = preamble.rstrip() + "\n\\begin{document}\n" + "\n".join(body) + "\n\\end{document}\n"
    with tempfile.TemporaryDirectory() as d:
        for name, content in (extra_files or {}).items():
            p = Path(d) / name
            if ".." in Path(name).parts:
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        (Path(d) / "probe.tex").write_text(src)
        try:
            out = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-draftmode", "probe.tex"],
                                 cwd=d, capture_output=True, text=True, timeout=timeout).stdout
        except Exception as e:
            logger.debug(f"TeX probe failed: {e}")
            return None
    vals: Dict[str, float] = {}
    for m in re.finditer(r"OB-(W\d+|TW|LW)=([0-9.]+)pt", out):
        vals[m.group(1)] = float(m.group(2))
    return vals or None


def split_preamble(code: str) -> str:
    m = re.search(r"\\begin\s*\{document\}", code)
    return code[:m.start()] if m else code


@dataclass
class FontSpec:
    family: str = "helvetica"
    size: float = 10.0
    bold: bool = False


def _measure(fragment: str, font: FontSpec, preamble: Optional[str],
             extra_files: Optional[Dict[str, str]]) -> Tuple[float, List[Tuple[str, float]], str, Optional[float]]:
    """(width of the widest line, [(token, width)], measured_by, text width if probed)."""
    plain = latex_to_plain(fragment)
    lines = [ln for ln in plain.split("\n") if ln.strip()] or [plain]
    tokens = [t for t in re.split(r"\s+", plain) if t]
    if preamble is not None:
        raw_lines = [ln for ln in re.split(r"\\\\(?:\[[^\]]*\])?", fragment) if ln.strip()]
        probe = tex_probe(preamble, raw_lines + [_escape_token(t) for t in tokens], extra_files)
        if probe and all(f"W{i}" in probe for i in range(len(raw_lines))):
            widest = max(probe[f"W{i}"] for i in range(len(raw_lines)))
            toks = [(t, probe.get(f"W{len(raw_lines) + k}", 0.0)) for k, t in enumerate(tokens)]
            return widest, toks, "tex", probe.get("LW") or probe.get("TW")
    widest = max(text_width(ln, font.family, font.size, font.bold) for ln in lines)
    toks = [(t, text_width(t, font.family, font.size, font.bold)) for t in tokens]
    return widest, toks, "metrics", None


_SPECIALS = {"&": "\\&", "%": "\\%", "$": "\\$", "#": "\\#", "_": "\\_", "{": "\\{", "}": "\\}",
             "~": "\\textasciitilde{}", "^": "\\textasciicircum{}", "\\": "\\textbackslash{}"}


def _escape_token(t: str) -> str:
    return "".join(_SPECIALS.get(c, c) for c in t)


# ---------------------------------------------------------------------------
# Fixes
# ---------------------------------------------------------------------------

def _break_points(token: str, token_w: float, target_w: float) -> str:
    """
    Break opportunities for one over-long token: after separators first
    (/ - _ . : , digit/letter boundaries), and only if none exist, a
    discretionary break every n characters so each piece fits.
    """
    seps = re.sub(r"([/\-_.:,])(?=.)", r"\1\\allowbreak{}", token)
    if seps != token:
        return seps
    n = max(4, int(len(token) * target_w / max(token_w, 1e-6)) - 1)
    return "\\-".join(token[i:i + n] for i in range(0, len(token), n))


def _align(content: str, alignment: Optional[str]) -> str:
    cmd = _ALIGN_CMD.get((alignment or "").lower())
    return f"{{{cmd} {content}\\par}}" if cmd else content


def justify_content(fragment: str, available_w: float, font: Optional[FontSpec] = None,
                    alignment: Optional[str] = None, single_line: Optional[bool] = None,
                    preamble: Optional[str] = None, extra_files: Optional[Dict[str, str]] = None) -> JustifyResult:
    """
    Decides and writes the smallest fix that makes ``fragment`` fit
    ``available_w`` pt. ``preamble`` (the document's) turns on TeX measurement.
    ``single_line`` says whether the content is a unit that must stay on one
    line (a label, a table cell, a heading); by default it is a single line
    when it contains no line break and is under 1.6× the available width.
    """
    font = font or FontSpec()
    fragment = fragment.strip()
    measured, tokens, by, probed_lw = _measure(fragment, font, preamble, extra_files)
    if available_w <= 0:
        available_w = probed_lw or available_w
    ratio = measured / available_w if available_w > 0 else 1.0
    needs: List[str] = []
    if (alignment or "").lower() == "justify":
        needs.append("ragged2e")

    if single_line is None:
        single_line = "\\\\" not in fragment and "\n\n" not in fragment and ratio <= 1.6

    def result(latex: str, strategy: str, notes: Optional[List[str]] = None, extra: Optional[List[str]] = None) -> JustifyResult:
        return JustifyResult(latex=latex, strategy=strategy, measured_w=measured, target_w=available_w,
                             ratio=ratio, changed=latex != fragment, needs_packages=needs + (extra or []),
                             notes=notes or [], measured_by=by)

    # 1. Fits.
    if measured <= available_w + FIT_SLACK:
        if alignment:
            return result(_align(fragment, alignment), "align")
        return result(fragment, "none", ["The content already fits the available width."])

    # 2. A paragraph: let TeX wrap it; give over-long tokens break points.
    if not single_line:
        out = fragment
        broken = []
        for tok, w in tokens:
            if w > available_w + FIT_SLACK and tok in out:
                out = out.replace(tok, _break_points(tok, w, available_w), 1)
                broken.append(tok)
        body = f"\\emergencystretch=1em\\relax {out}"
        if re.search(r"\\(?:mbox|makebox|hbox)\b", fragment):
            latex = f"\\parbox[t]{{{_pt(available_w)}pt}}{{{_ALIGN_CMD.get(alignment or '', '')} {body}}}"
            strategy = "wrap"
        else:
            latex = _align(f"{{{body}\\par}}", alignment)
            strategy = "break_tokens" if broken else "wrap"
        notes = [f"Added break points only inside over-long token(s): {', '.join(broken)}"] if broken else []
        return result(latex, strategy, notes)

    # 3/4. A single-line unit.
    if ratio <= CONDENSE_LIMIT:
        latex = f"\\resizebox{{{_pt(available_w)}pt}}{{\\height}}{{{fragment}}}"
        return result(_align(latex, alignment), "condense",
                      [f"Condensed horizontally by {(1 - 1 / ratio) * 100:.1f}%."], ["graphicx"])

    scale = max(MIN_FONT_SCALE, 1.0 / ratio)
    size = font.size * scale
    sized = f"{{\\fontsize{{{_pt(size)}}}{{{_pt(size * 1.2)}}}\\selectfont {fragment}}}"
    remaining = ratio * scale
    if remaining <= 1.0 + FIT_SLACK / max(available_w, 1):
        return result(_align(sized, alignment), "shrink", [f"Font size {font.size:g}pt → {size:.2f}pt."])
    latex = f"\\resizebox{{{_pt(available_w)}pt}}{{\\height}}{{{sized}}}"
    return result(_align(latex, alignment), "shrink+condense",
                  [f"Font size {font.size:g}pt → {size:.2f}pt (floor), then condensed {(1 - 1 / remaining) * 100:.1f}%."],
                  ["graphicx"])


def hfit_line(content: str, width_pt: float) -> str:
    """
    The PDF importer's form of the condense fix: ``\\obhfit`` (defined in the
    import preamble) condenses only if the content is wider than ``width_pt``,
    so it stays correct when the text is edited later.
    """
    return f"\\obhfit{{{_pt(width_pt)}pt}}{{{content}}}"
