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
    one-line unit too wide         → horizontal condense to the exact width
                                     (\\resizebox{W}{\\height}{…}: height kept),
                                     with a warning when the reduction is large

Type is never made smaller to fit. That is a restyle, not a repair: it shows
on the page next to text set at the document's real size, and it spreads,
because the next overflow invites the same treatment.

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
FIT_SLACK = 0.25        # pt: a measurement this close to the limit already fits

_ALIGN_CMD = {"left": "\\raggedright", "right": "\\raggedleft", "center": "\\centering", "justify": "\\justifying"}


@dataclass
class JustifyResult:
    latex: str
    strategy: str             # none | align | wrap | break_tokens | condense
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
            proc = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-draftmode", "probe.tex"],
                                 cwd=d, capture_output=True, timeout=timeout)
            out = proc.stdout
            if isinstance(out, bytes):
                out = out.decode("utf-8", errors="replace")
        except Exception as e:
            logger.debug(f"TeX probe failed: {e}")
            return None
    vals: Dict[str, float] = {}
    for m in re.finditer(r"OB-(W\d+|TW|LW)=([0-9.]+)pt", out):
        vals[m.group(1)] = float(m.group(2))
    return vals or None


# TeX's pt is 1/72.27 inch; PDF coordinates are big points, 1/72 inch.
PT_TO_BP = 72.0 / 72.27


def probe_page_geometry(preamble: str, extra_files: Optional[Dict[str, str]] = None,
                        timeout: int = 30) -> Optional[Dict[str, float]]:
    """
    The document's page geometry in PDF big points: where the body text block
    starts and how large it is.

    This is measured rather than inferred because inference fails on exactly
    the pages that need checking: ``text_right_edge`` needs three lines to
    agree on a right edge, and a page dominated by a wide table has no such
    agreement, so it returns None and every overflow check silently passes.
    LaTeX knows the answer exactly, so ask LaTeX.

    Returns {left, top, right, bottom, text_width, text_height}, or None when
    pdflatex is unavailable or the probe fails.
    """
    if not shutil.which("pdflatex"):
        return None
    names = ("textwidth", "textheight", "oddsidemargin", "topmargin", "headheight", "headsep")
    body = "\n".join(f"\\typeout{{OB-G-{n}=\\the\\{n}}}" for n in names)
    src = preamble.rstrip() + "\n\\begin{document}\n" + body + "\n\\end{document}\n"
    with tempfile.TemporaryDirectory() as d:
        for name, content in (extra_files or {}).items():
            if ".." in Path(name).parts:
                continue
            fp = Path(d) / name
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content)
        (Path(d) / "geom.tex").write_text(src)
        try:
            proc = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-draftmode", "geom.tex"],
                                  cwd=d, capture_output=True, timeout=timeout)
            out = proc.stdout
            if isinstance(out, bytes):
                out = out.decode("utf-8", errors="replace")
        except Exception as e:
            logger.debug(f"Geometry probe failed: {e}")
            return None
    vals: Dict[str, float] = {}
    for m in re.finditer(r"OB-G-([a-z]+)=(-?[0-9.]+)pt", out):
        vals[m.group(1)] = float(m.group(2)) * PT_TO_BP
    if "textwidth" not in vals or "textheight" not in vals:
        return None
    # LaTeX's reference point is 1 inch in from the top-left of the paper.
    left = 72.0 + vals.get("oddsidemargin", 0.0)
    top = 72.0 + vals.get("topmargin", 0.0) + vals.get("headheight", 0.0) + vals.get("headsep", 0.0)
    return {
        "left": left, "top": top,
        "right": left + vals["textwidth"], "bottom": top + vals["textheight"],
        "text_width": vals["textwidth"], "text_height": vals["textheight"],
    }


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


def fit_fragment(fragment: str, available_w: float, font: Optional[FontSpec] = None,
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

    # No font-size rung. Making content fit by setting it smaller than the text
    # around it is a restyle disguised as a repair: it is visible on the page,
    # it spreads (the next overflow gets the same treatment), and it is never
    # what a typesetter would do. An unbreakable unit that is badly too wide is
    # condensed to the width it has and the caller is told by how much, so a
    # human can decide whether the content or the column is the real problem.
    latex = f"\\resizebox{{{_pt(available_w)}pt}}{{\\height}}{{{fragment}}}"
    return result(_align(latex, alignment), "condense",
                  [f"Condensed horizontally by {(1 - 1 / ratio) * 100:.1f}% to fit "
                   f"{_pt(available_w)}pt. This is a large reduction — consider widening the "
                   f"column or shortening the content instead."],
                  ["graphicx"])


def hfit_line(content: str, width_pt: float) -> str:
    """
    The PDF importer's form of the condense fix: ``\\obhfit`` (defined in the
    import preamble) condenses only if the content is wider than ``width_pt``,
    so it stays correct when the text is edited later.
    """
    return f"\\obhfit{{{_pt(width_pt)}pt}}{{{content}}}"


# The fragment fitter used to be the whole of justify_content. The agent tool
# of that name is now the document-level layout repair in
# opencode/layout_tools.py; this remains its one-fragment primitive.
justify_content = fit_fragment
