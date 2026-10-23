"""
glyphs.py — Recover private-use glyphs by shape.

Word and other producers often emit Symbol-font characters (Greek letters, ±, ×, ≤ …) through a
subset font whose ToUnicode map points every glyph at the private-use area (U+E000…). The text layer
then carries no meaning, and latex_text drops those characters, so a symbols list or an equation
loses its symbols. The glyph outlines are still there: each distinct private-use glyph is rendered
from the page and matched against reference renders of the candidate characters (MuPDF's built-in
Symbol font, the same Adobe design as SymbolMT). Only a confident, unambiguous match is substituted;
anything else is left for the math crop. Editable mode only — exact mode never calls this.
"""

from __future__ import annotations

import logging
import math
import re
import string
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..models import DocExtract

logger = logging.getLogger("pdf2latex.editable.glyphs")

GRID = 24
ACCEPT = 0.68       # minimum score for a match
MARGIN = 0.08       # and it must beat the runner-up (a different character) by this much
# Word often slants Symbol-font Greek (synthetic italic), so each reference is also rendered sheared.
SHEARS = (0.0, 0.18, 0.28)

_CANDIDATES = (
    "αβγδεζηθικλμνξοπρστυφχψωϑϕϖς"
    "ΓΔΘΛΞΠΣΥΦΨΩ"
    "±×÷≤≥≠≈≡∞∑∏∫∂∇√∈∉⊂⊃⊆⊇∪∩∧∨¬∀∃∅→←↑↓↔⇒⇐⇔°′″·•…∝∠⊥⊕⊗∼≅"
    # delimiters: without them a TeX brace (CMSY "{") is nearest to ∫ and comes out as one
    "{}()[]|⟨⟩"
)


def _is_pua(ch: str) -> bool:
    return 0xE000 <= ord(ch) <= 0xF8FF


def _base(font: str) -> str:
    return font.split("+", 1)[-1] if "+" in font[:8] else font


def _normalise(gray: np.ndarray) -> Optional[Tuple[np.ndarray, float]]:
    """Crop to the ink, pad to a square, resample to GRID×GRID; returns (vector, aspect ratio)."""
    ink = gray < 128
    if not ink.any():
        return None
    ys, xs = np.where(ink)
    crop = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.float32)
    h, w = crop.shape
    side = max(h, w)
    pad = np.zeros((side, side), np.float32)
    pad[(side - h) // 2:(side - h) // 2 + h, (side - w) // 2:(side - w) // 2 + w] = crop
    from PIL import Image
    img = Image.fromarray((pad * 255).astype(np.uint8)).resize((GRID, GRID), Image.BILINEAR)
    v = np.asarray(img, np.float32).ravel()
    v -= v.mean()
    n = np.linalg.norm(v)
    if n == 0:
        return None
    return v / n, w / h


def _pix_gray(pix) -> np.ndarray:
    arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    return arr[..., :3].mean(axis=2) if pix.n >= 3 else arr[..., 0].astype(np.float32)


# Latin ligatures that LaTeX-made PDFs (Latin Modern / Computer Modern) often expose as private-use
# glyphs inside words: "di\ue04ferent", "veri\ue002cation". A match maps back to the plain
# letters, which TeX re-ligatures when it sets the text.
_LIGATURES = ("ff", "fi", "fl", "ffi", "ffl")


@lru_cache(maxsize=1)
def _ligature_references() -> List[Tuple[str, np.ndarray, float]]:
    import pymupdf
    refs = []
    doc = pymupdf.open()
    for fname in ("tiro", "helv", "tibo", "hebo"):
        font = pymupdf.Font(fname)
        for lig in _LIGATURES:
            pg = doc.new_page(width=160, height=80)
            tw = pymupdf.TextWriter(pg.rect)
            tw.append((10, 60), lig, font=font, fontsize=48)
            tw.write_text(pg)
            norm = _normalise(_pix_gray(pg.get_pixmap(dpi=72, colorspace=pymupdf.csGRAY)))
            if norm is not None:
                refs.append((lig, norm[0], norm[1]))
    doc.close()
    return refs


@lru_cache(maxsize=1)
def _ligature_widths() -> Dict[str, float]:
    """Advance width of each ligature in ems (mean of the reference faces)."""
    import pymupdf
    out: Dict[str, float] = {}
    for lig in _LIGATURES:
        ws = [pymupdf.Font(f).text_length(lig, fontsize=1) for f in ("tiro", "helv")]
        out[lig] = sum(ws) / len(ws)
    return out


def _ligature_match(vec: np.ndarray, ar: float, em_width: float) -> Tuple[Optional[str], float, float]:
    """Ligatures differ more in width than in shape (fi vs ffi): keep those whose advance is
    within 0.15 em of the glyph's, then match by shape among them."""
    widths = _ligature_widths()
    allowed = {k for k, w in widths.items() if abs(w - em_width) <= 0.15} or set(widths)
    best_of: Dict[str, float] = {}
    for ch, ref, rar in _ligature_references():
        if ch not in allowed:
            continue
        score = float(np.dot(vec, ref)) - 0.3 * abs(math.log(max(ar, 1e-3) / max(rar, 1e-3)))
        best_of[ch] = max(best_of.get(ch, -9.0), score)
    if not best_of:
        return None, -9.0, -9.0
    scored = sorted(((v, k) for k, v in best_of.items()), reverse=True)
    return scored[0][1], scored[0][0], (scored[1][0] if len(scored) > 1 else -1.0)


LIG_ACCEPT = 0.55
LIG_MARGIN = 0.03


@lru_cache(maxsize=1)
def _references() -> List[Tuple[str, np.ndarray, float]]:
    import pymupdf
    font = pymupdf.Font("symb")
    refs = []
    doc = pymupdf.open()
    for ch in _CANDIDATES:
        if not font.has_glyph(ord(ch)):
            continue
        for shear in SHEARS:
            pg = doc.new_page(width=100, height=80)
            tw = pymupdf.TextWriter(pg.rect)
            tw.append((20, 60), ch, font=font, fontsize=48)
            tw.write_text(pg, morph=(pymupdf.Point(20, 60), pymupdf.Matrix(1, 0, shear, 1, 0, 0)))
            norm = _normalise(_pix_gray(pg.get_pixmap(dpi=72, colorspace=pymupdf.csGRAY)))
            if norm is not None:
                refs.append((ch, norm[0], norm[1]))
    doc.close()
    return refs


# Fonts whose private-use glyphs are italic Latin variables (a math italic in a document whose text
# is set in another face): newtx/tx math italic, Computer Modern math italic, generic "mathitalic".
# Their letters (K, M, P, n, …) are dropped like the Symbol glyphs, so a math-italic PUA glyph is also
# matched against the Latin alphabet, set in Times-Italic (the closest built-in to a math italic).
_MATH_ITALIC_RE = re.compile(r"(cmmi|newtxmi|txmi|mtmi|mathit|rsfs|eufm)", re.IGNORECASE)
_LATIN = string.ascii_uppercase + string.ascii_lowercase


@lru_cache(maxsize=1)
def _latin_references() -> List[Tuple[str, np.ndarray, float]]:
    import pymupdf
    refs: List[Tuple[str, np.ndarray, float]] = []
    doc = pymupdf.open()
    font = pymupdf.Font("tiit")   # Times-Italic
    for ch in _LATIN:
        for shear in SHEARS:
            pg = doc.new_page(width=100, height=90)
            tw = pymupdf.TextWriter(pg.rect)
            tw.append((20, 65), ch, font=font, fontsize=48)
            tw.write_text(pg, morph=(pymupdf.Point(20, 65), pymupdf.Matrix(1, 0, shear, 1, 0, 0)))
            norm = _normalise(_pix_gray(pg.get_pixmap(dpi=72, colorspace=pymupdf.csGRAY)))
            if norm is not None:
                refs.append((ch, norm[0], norm[1]))
    doc.close()
    return refs


def _score(vec: np.ndarray, ar: float, in_word: bool = False,
           math_letters: bool = False) -> Tuple[Optional[str], float, float]:
    """(best character, its score, runner-up score). A glyph between letters is compared with the
    Latin ligatures only; a standalone one with the Symbol characters (plus the Latin alphabet when
    it comes from a math-italic font)."""
    refs = _ligature_references() if in_word else _references()
    if math_letters and not in_word:
        refs = refs + _latin_references()
    best_of: Dict[str, float] = {}
    for ch, ref, rar in refs:
        score = float(np.dot(vec, ref)) - 0.3 * abs(math.log(max(ar, 1e-3) / max(rar, 1e-3)))
        if score > best_of.get(ch, -9.0):
            best_of[ch] = score
    if not best_of:
        return None, -9.0, -9.0
    scored = sorted(((v, k) for k, v in best_of.items()), reverse=True)
    return scored[0][1], scored[0][0], (scored[1][0] if len(scored) > 1 else -1.0)


def _match(vec: np.ndarray, ar: float) -> Optional[str]:
    ch, best, second = _score(vec, ar)
    return ch if ch and best >= ACCEPT and best - second >= MARGIN else None


def recover(doc, extract: DocExtract) -> Dict[Tuple[str, int], str]:
    """
    Find every distinct (font, private-use code) on the pages, identify it by shape, and rewrite the
    extracted spans in place. Returns the mapping applied.
    """
    import pymupdf
    samples: Dict[Tuple[str, int], List[Tuple[int, Tuple[float, float, float, float], float]]] = {}
    in_word: set = set()
    for page in extract.pages:
        if not any(_is_pua(c) for ln in page.lines for sp in ln.spans for c in sp.text):
            continue
        try:
            raw = doc[page.number - 1].get_text("rawdict")
        except Exception:  # noqa: BLE001
            continue
        for blk in raw.get("blocks", []):
            for ln in blk.get("lines", []):
                for sp in ln.get("spans", []):
                    for c in sp.get("chars", []):
                        ch = c.get("c", "")
                        if ch and _is_pua(ch):
                            key = (_base(sp.get("font", "")), ord(ch))
                            lst = samples.setdefault(key, [])
                            if len(lst) < 4:   # a few instances: one may carry a neighbour's ink
                                lst.append((page.number - 1, tuple(c["bbox"]), float(sp.get("size", 0))))
                    chars = sp.get("chars", [])
                    for k, c in enumerate(chars):
                        ch = c.get("c", "")
                        if ch and _is_pua(ch):
                            prev = chars[k - 1]["c"] if k > 0 else ""
                            nxt = chars[k + 1]["c"] if k + 1 < len(chars) else ""
                            if prev.isalpha() or nxt.isalpha():
                                in_word.add((_base(sp.get("font", "")), ord(ch)))
    if not samples:
        return {}
    mapping: Dict[Tuple[str, int], str] = {}
    for key, insts in samples.items():
        best = (None, -9.0, -9.0)
        for pidx, bbox, size in insts:
            x0, y0, x1, y1 = bbox
            if x1 - x0 < 0.5 or y1 - y0 < 0.5 or size <= 0:
                continue
            dpi = max(72, min(1200, int(72 * 60 / size)))
            try:
                pix = doc[pidx].get_pixmap(clip=pymupdf.Rect(x0, y0, x1, y1), dpi=dpi,
                                           colorspace=pymupdf.csGRAY)
            except Exception:  # noqa: BLE001
                continue
            norm = _normalise(_pix_gray(pix))
            if norm is None:
                continue
            if key in in_word:
                res = _ligature_match(norm[0], norm[1], (x1 - x0) / size)
            else:
                res = _score(norm[0], norm[1], math_letters=bool(_MATH_ITALIC_RE.search(key[0])))
            if res[0] and res[1] > best[1]:
                best = res
        ch, sc, second = best
        accept, margin = (LIG_ACCEPT, LIG_MARGIN) if key in in_word else (ACCEPT, MARGIN)
        if ch and sc >= accept and sc - second >= margin:
            mapping[key] = ch
    # LaTeX font families share one encoding across sizes and weights, so a ligature identified in
    # LMSans10-Regular is the same glyph at the same code in LMSans10-Bold.
    def family(name: str) -> str:
        # the trailing font name ("…+MIYIHS<tag>LMSans10-Bold" → "LMSans"), without size or weight
        m = re.search(r"([A-Za-z][A-Za-z0-9]*)(?:-[A-Za-z]+)?$", name)
        core = m.group(1) if m else name
        return re.sub(r"\d+.*$", "", core)
    for key in in_word:
        if key in mapping:
            continue
        sib = next((v for (f, cp), v in mapping.items()
                    if cp == key[1] and family(f) == family(key[0]) and v in _LIGATURES), None)
        if sib:
            mapping[key] = sib
    if mapping:
        for page in extract.pages:
            for ln in page.lines:
                for sp in ln.spans:
                    if any(_is_pua(c) for c in sp.text):
                        base = _base(sp.font)
                        sp.text = "".join(mapping.get((base, ord(c)), c) for c in sp.text)
        logger.info(f"recovered {len(mapping)} of {len(samples)} private-use glyphs by shape")
    return mapping
