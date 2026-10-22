"""
polish.py — Text-only LLM polish of flagged blocks, accepted only on measurement.

The deterministic build is the product; polish can only replace a block with something verifiably
better. Today's target is a displayed equation whose glyphs carry real Unicode (a TeX-made PDF):
the crop image is replaced with real LaTeX maths when a candidate

  1. passes a safety lint (no \\input, \\write, \\def, packages …),
  2. compiles on its own, and
  3. renders the source's glyphs: ≥95% of them, and ≤15% extra.

A rejected candidate is retried with the concrete problem as feedback, only while the measured
distance keeps shrinking. After all blocks, the whole document is recompiled and re-measured; if it
fails or a gate gets worse, every polish edit is reverted. Verdicts are cached in the job directory
so a resumed job never repeats an LLM call.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .model import EditDoc, Math
from .prompts import MATH_FEEDBACK, MATH_SYSTEM, MATH_USER, PROMPT_VERSION

logger = logging.getLogger("pdf2latex.editable.polish")

MIN_GLYPHS = 0.95
MAX_EXTRA = 0.15
MAX_ATTEMPTS = 4           # a safety stop; attempts already end as soon as one doesn't improve
STANDALONE_TIMEOUT = 45

_FORBIDDEN = re.compile(r"\\(input|include|write|immediate|openout|openin|read|def|edef|gdef|xdef|let|"
                        r"newcommand|renewcommand|providecommand|usepackage|documentclass|catcode|"
                        r"csname|special|directlua|loop|begin\{document\}|end\{document\}|"
                        r"color|textcolor|fontsize|selectfont|tag)(?![A-Za-z])")  # a control word ends at a non-letter


def _fill(t: str, **kw) -> str:
    for k, v in kw.items():
        t = t.replace("{{" + k + "}}", str(v))
    return t


def _clean(text: str) -> str:
    """The maths from an answer: strip a code fence and any display delimiters."""
    t = text.strip()
    t = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", t).strip()
    t = re.sub(r"^\$\$|\$\$$|^\\\[|\\\]$|^\$|\$$", "", t).strip()
    t = re.sub(r"^\\begin\{(equation|align|gather)\*?\}|\\end\{(equation|align|gather)\*?\}$", "", t).strip()
    return t


# In the TeX maths-extension font the big operators sit in letter slots: a PDF whose fonts carry
# no Unicode map reports the display summation as "P". Mapped on both sides of the check (and in
# what the model is shown) so a literal "P" cannot pass for a summation.
_CMEX = {"P": "∑", "X": "∑", "Q": "∏", "Y": "∏", "R": "∫", "Z": "∫", "S": "∮", "H": "∮",
         "T": "⋃", "[": "⋃", "U": "⋂", "\\": "⋂", "W": "⋁", "_": "⋁", "V": "⋀", "^": "⋀"}
_CMEX_FONT = re.compile(r"(cmex|lmex|mathextension|txex|ntxexx|esint)", re.IGNORECASE)


def _glyph_text(text: str, font: str) -> str:
    if _CMEX_FONT.search(font or ""):
        return "".join(_CMEX.get(c, c) for c in text)
    return text


def _glyph_counter(text: str) -> Counter:
    return Counter(c for c in unicodedata.normalize("NFKC", text) if not c.isspace())


def _lint(math: str) -> Optional[str]:
    if not math:
        return "empty answer"
    if _FORBIDDEN.search(math):
        return f"forbidden command {_FORBIDDEN.search(math).group(0)}"
    if math.count("{") != math.count("}"):
        return "unbalanced braces"
    if len(math) > 2000:
        return "answer too long"
    return None


def _standalone(preamble: str, math: str) -> str:
    keep = [ln for ln in preamble.splitlines()
            if ln.startswith(("\\documentclass", "\\usepackage")) and "geometry" not in ln
            and "fancyhdr" not in ln and "eso-pic" not in ln]
    return "\n".join(keep + ["\\pagestyle{empty}", "\\begin{document}", "\\[", math, "\\]",
                             "\\end{document}", ""])


_ITALIC_FONT = re.compile(r"(cmmi|lmmi|mathitalic|txmi|ntxmi|cmti|italic|oblique)", re.IGNORECASE)
ROW_COVER = 0.85            # each row must hold this share of its source glyphs
ROW_ORDER = 0.75            # and in this left-to-right order (difflib ratio)
ITALIC_AGREE = 0.85         # Latin letters keep their slant (math italic vs upright)


def _rows(chars: List[Tuple[str, float, float, float, str]]) -> List[List[Tuple[str, float, float, float, str]]]:
    """Group (char, x, baseline, size, font) into rows: a new row starts where the baseline drops by
    more than 0.75 of the larger size (a fraction's denominator, limits below an operator);
    superscripts and subscripts stay in their row."""
    rows: List[List] = []
    for ch in sorted(chars, key=lambda c: c[2]):
        if rows and ch[2] - max(c[2] for c in rows[-1]) <= 0.75 * max(ch[3], max(c[3] for c in rows[-1])):
            rows[-1].append(ch)
        else:
            rows.append([ch])
    return [sorted(r, key=lambda c: c[1]) for r in rows]


def _source_chars(glyphs: List[Dict], number: Optional[str]) -> List[Tuple[str, float, float, float, str]]:
    out = []
    for g in glyphs:
        if number and g["t"].strip() == number:
            continue
        x = g["x"]
        for c in unicodedata.normalize("NFKC", g["t"]):
            if not c.isspace():
                out.append((c, x, g["y"], g["sz"], g.get("f", "")))
            x += 0.5 * g["sz"]
    return out


def _output_chars(pdf: bytes) -> List[Tuple[str, float, float, float, str]]:
    import pymupdf
    out = []
    with pymupdf.open(stream=pdf, filetype="pdf") as d:
        for pg in d:
            for blk in pg.get_text("rawdict").get("blocks", []):
                for ln in blk.get("lines", []):
                    for sp in ln.get("spans", []):
                        font = sp.get("font", "")
                        for ch in sp.get("chars", []):
                            for c in unicodedata.normalize("NFKC", _glyph_text(ch.get("c", ""), font)):
                                if not c.isspace():
                                    out.append((c, ch["origin"][0], ch["origin"][1], sp.get("size", 0), font))
    return out


def _layout_problem(src, out) -> Optional[str]:
    """The candidate's rendering against the source glyphs: same rows, same order, same slant."""
    import difflib
    rs, ro = _rows(src), _rows(out)
    if len(rs) != len(ro):
        return (f"the equation has {len(rs)} row(s) (e.g. a fraction's numerator and denominator, "
                f"limits above/below), the answer renders {len(ro)}")
    for k, (a, b) in enumerate(zip(rs, ro)):
        ca, cb = Counter(c[0] for c in a), Counter(c[0] for c in b)
        cover = sum(min(n, cb.get(ch, 0)) for ch, n in ca.items()) / max(1, sum(ca.values()))
        order = difflib.SequenceMatcher(None, [c[0] for c in a], [c[0] for c in b]).ratio()
        if cover < ROW_COVER or order < ROW_ORDER:
            return (f"row {k + 1} should read {''.join(c[0] for c in a)!r} left to right; "
                    f"the answer renders {''.join(c[0] for c in b)!r}")
    la = [c for c in src if c[0].isascii() and c[0].isalpha()]
    lb = [c for c in out if c[0].isascii() and c[0].isalpha()]
    if len(la) >= 3 and lb:
        sa = Counter((c[0], bool(_ITALIC_FONT.search(c[4]))) for c in la)
        sb = Counter((c[0], bool(_ITALIC_FONT.search(c[4]))) for c in lb)
        agree = sum(min(n, sb.get(k, 0)) for k, n in sa.items()) / len(la)
        if agree < ITALIC_AGREE:
            return "letters must keep their slant: italic maths letters vs upright (\\mathrm) text"
    return None


async def _try(ctx, compile_tex, preamble: str, math: str, want: Counter,
               src_chars=None) -> Tuple[bool, str, float]:
    """(accepted, problem, distance) for one candidate."""
    problem = _lint(math)
    if problem:
        return False, problem, 9.0
    pdf, log = await compile_tex(ctx, _standalone(preamble, math), STANDALONE_TIMEOUT)
    if pdf is None:
        from ..pipeline import _log_errors
        return False, "does not compile: " + _log_errors(log, 400), 5.0
    out_chars = _output_chars(pdf)
    got = Counter(c[0] for c in out_chars)
    total = sum(want.values()) or 1
    found = sum(min(n, got.get(c, 0)) for c, n in want.items())
    extra = sum(max(0, n - want.get(c, 0)) for c, n in got.items())
    cov, ext = found / total, extra / total
    distance = (1 - cov) + max(0.0, ext - MAX_EXTRA)
    if cov < MIN_GLYPHS or ext > MAX_EXTRA:
        missing = [c for c, n in want.items() if got.get(c, 0) < n][:12]
        added = [c for c, n in got.items() if n > want.get(c, 0)][:12]
        return False, (f"renders {cov:.0%} of the glyphs; missing {''.join(missing)!r}; "
                       f"extra {''.join(added)!r}"), distance
    if src_chars:
        lp = _layout_problem(src_chars, out_chars)
        if lp:
            return False, lp, distance + 0.5
    return True, "", distance


async def _polish_math(m: Math, ctx, compile_tex, preamble: str, settings, cache: Optional[Path],
                       stats: Dict) -> None:
    from ..llm import complete
    glyphs = [{**g, "t": _glyph_text(g["t"], g.get("f", ""))} for g in m.glyphs]
    glyph_lines = "\n".join(f"{g['t']!r}, {g['x']}, {g['y']}, {g['sz']}, {g['f']}" for g in glyphs)
    want = _glyph_counter("".join(g["t"] for g in glyphs if g["t"].strip() != (m.number or "")))
    key = hashlib.sha1((PROMPT_VERSION + glyph_lines).encode()).hexdigest()
    if cache is not None:
        hit = cache / f"{key}.json"
        if hit.exists():
            data = json.loads(hit.read_text())
            if data.get("latex"):
                m.latex = data["latex"]
                stats["accepted"] += 1
            stats["cached"] += 1
            return
    stats["tried"] += 1
    w = round(m.bbox[2] - m.bbox[0], 1)
    h = round(m.bbox[3] - m.bbox[1], 1)
    feedback = ""
    best = 9.0
    accepted = None
    for attempt in range(MAX_ATTEMPTS):
        user = _fill(MATH_USER, GLYPHS=glyph_lines, WIDTH=w, HEIGHT=h, FEEDBACK=feedback)
        try:
            answer = await complete(MATH_SYSTEM, user, None, timeout=settings.page_timeout,
                                    retries=settings.page_retries, concurrency=settings.concurrency,
                                    max_tokens=2000, label=f"math-p{m.page}")
        except Exception as e:  # noqa: BLE001 — an unavailable model leaves the image in place
            logger.info(f"math polish p{m.page}: LLM call failed: {e}")
            break
        math = _clean(answer)
        ok, problem, distance = await _try(ctx, compile_tex, preamble, math, want,
                                           _source_chars(glyphs, m.number))
        if ok:
            accepted = math
            break
        if distance >= best:
            break                       # no progress: stop here, keep the image
        best = distance
        feedback = _fill(MATH_FEEDBACK, PREVIOUS=math[:600], PROBLEM=problem)
    if accepted:
        m.latex = accepted
        stats["accepted"] += 1
    if cache is not None:
        cache.mkdir(parents=True, exist_ok=True)
        (cache / f"{key}.json").write_text(json.dumps({"latex": accepted}))


def _targets(doc: EditDoc) -> List[Math]:
    out: List[Math] = []

    def walk(blocks):
        for b in blocks:
            if isinstance(b, Math) and b.polish == "math" and b.glyphs and not b.latex:
                out.append(b)
            for attr in ("content",):
                inner = getattr(b, attr, None)
                if inner:
                    walk(inner)
    walk(doc.blocks)
    return out


async def polish_document(ctx, extract, doc: EditDoc, tex: str, pdf: bytes, lm, gate_result: Dict,
                          settings, job_id: str, compile_tex=None) -> Tuple[str, Optional[bytes], Dict]:
    """Returns (tex, pdf, gate_result) — the polished document only if it measures no worse."""
    from ..pipeline import compile_tex as _compile_tex
    from . import gates as G
    from .emit import emit_document
    compile_tex = compile_tex or _compile_tex
    gate_result = dict(gate_result)
    stats = {"tried": 0, "accepted": 0, "cached": 0, "targets": [], "reverted": False}
    targets = _targets(doc)
    stats["targets"] = [f"math p{m.page}" for m in targets]
    if not targets:
        gate_result["polish"] = stats
        return tex, pdf, gate_result
    cache = None
    try:
        from .. import jobs
        cache = jobs.job_dir(job_id) / "editable" / "polish"
    except Exception:  # noqa: BLE001 — no job directory (CLI): no cache
        cache = None
    preamble = tex.split("\\begin{document}", 1)[0]
    for m in targets:
        await _polish_math(m, ctx, compile_tex, preamble, settings, cache, stats)
    if not stats["accepted"]:
        gate_result["polish"] = stats
        return tex, pdf, gate_result
    new_tex, _lm = emit_document(doc)
    timeout = G.MERGE_TIMEOUT_BASE + 6 * max(1, doc.page_count)
    new_pdf, _log = await compile_tex(ctx, new_tex, timeout)
    if new_pdf is not None:
        new_gates = G.run_gates(extract, doc, new_tex, new_pdf, settings)
        old = gate_result.get("gates", {})
        worse = (new_gates["gates"].get("coverage", 0) < old.get("coverage", 0) - 1e-4
                 or new_gates["gates"].get("style", 0) < old.get("style", 0) - 0.005
                 or len(new_gates["failed"]) > len(gate_result.get("failed", [])))
        if not worse:
            new_gates["polish"] = stats
            return new_tex, new_pdf, new_gates
    # the polished whole is not better: put every equation image back
    for m in targets:
        m.latex = None
    stats["reverted"] = True
    stats["accepted"] = 0
    gate_result["polish"] = stats
    return tex, pdf, gate_result
