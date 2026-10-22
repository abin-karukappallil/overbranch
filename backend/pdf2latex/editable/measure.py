"""
measure.py — Measure the compiled output PDF against the source extraction.

Coverage/order reuse verify.tokenize/compare_words. Style fidelity reads the output PDF's own spans
and aligns them, word by word and in order (difflib), with the source's styled words, then scores
the share whose size/weight/slant/colour/family match. The output-side bold/italic detection must
recognise the TeX font names pdfLaTeX emits (NimbusRomNo9L-Medi/-ReguItal, CMBX, CMTI, lmbx, …),
which the PDF-producer-oriented fontmap regexes miss.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Dict, List, Tuple

from ..models import DocExtract
from ..verify import _normalize_word, compare_words, extract_words_from_pdf, tokenize
from .model import EditDoc, Math, RGB, StyledWord

# Output-side (TeX) font-name tokens.
_OUT_BOLD = re.compile(r"(bold|bld|\bbd\b|medi\b|-medi|cmbx|lmbx|-b\b|black|heavy|semibold|demi)",
                       re.IGNORECASE)
_OUT_ITALIC = re.compile(r"(italic|ital\b|-ital|oblique|obli\b|slanted|cmti|cmsl|lmri|-it\b|kursiv)",
                         re.IGNORECASE)
# fonts pdfLaTeX sets maths in (Computer/Latin Modern, AMS, Times maths, newtx)
_MATH_OUT = re.compile(r"(cmmi|cmsy|cmex|cmbsy|msam|msbm|lmmath|rsfs|eufm|stmary|wasy|esint|"
                       r"rtxmi|txsy|txex|txmia|psyr|symbol|mathptmx|ntxmi|ntxsy|ntxexx)", re.IGNORECASE)
_OUT_SANS = re.compile(r"(sans|helvet|nimbussan|arial|lmss|cmss|heros|carlito)", re.IGNORECASE)
_OUT_MONO = re.compile(r"(mono|courier|cmtt|lmtt|typewriter|cousine)", re.IGNORECASE)


def _int_to_rgb(c: int) -> RGB:
    return ((c >> 16) & 255, (c >> 8) & 255, c & 255)


def _out_family(font: str) -> str:
    if _OUT_MONO.search(font or ""):
        return "mono"
    if _OUT_SANS.search(font or ""):
        return "sans"
    return "serif"


# ---------------------------------------------------------------------------
# Source words (body only)
# ---------------------------------------------------------------------------

def _math_boxes(doc: EditDoc) -> Dict[int, List[Tuple[float, float, float, float]]]:
    boxes: Dict[int, List] = {}
    for b in doc.blocks:
        if isinstance(b, Math):     # an equation (image or rebuilt maths) is checked by its own gate
            boxes.setdefault(b.page, []).append(b.bbox)
    return boxes


def _in_box(ln, boxes) -> bool:
    cx = (ln.bbox[0] + ln.bbox[2]) / 2
    cy = (ln.bbox[1] + ln.bbox[3]) / 2
    return any(x0 - 2 <= cx <= x1 + 2 and y0 - 2 <= cy <= y1 + 2 for x0, y0, x1, y1 in boxes)


def _row_in_box(row, boxes) -> bool:
    cx = (row.x0 + row.x1) / 2
    cy = (row.top + row.bottom) / 2
    return any(x0 - 2 <= cx <= x1 + 2 and y0 - 2 <= cy <= y1 + 2 for x0, y0, x1, y1 in boxes)


def _reading_rows(extract: DocExtract, doc: EditDoc):
    """(page, row) in document reading order, skipping scanned pages and math crops; None when the
    doc carries no rebuilt rows (callers then fall back to the extractor's line order)."""
    if not doc.rows_by_page:
        return None
    mboxes = _math_boxes(doc)
    out = []
    for p in extract.pages:
        if p.number in doc.scanned:
            continue
        pm = mboxes.get(p.number, [])
        for r in doc.rows_by_page.get(p.number, []):
            if r.text.strip() and not _row_in_box(r, pm):
                out.append((p.number, r))
    return out


def source_styled_words(extract: DocExtract, doc: EditDoc) -> List[StyledWord]:
    rows = _reading_rows(extract, doc)
    if rows is not None:
        out: List[StyledWord] = []
        for pno, r in rows:
            for run in r.runs:
                if run.math:
                    continue        # maths is measured by the glyph gate, not as words
                for w in run.text.split():
                    norm = _normalize_word(unicodedata.normalize("NFKC", w))
                    if len(norm) >= 2:
                        out.append(StyledWord(norm=norm, size=run.size, bold=run.bold, italic=run.italic,
                                              color=run.color, family=run.family, page=pno))
        return out
    furn = doc.furniture.furniture_line_ids
    mboxes = _math_boxes(doc)
    out: List[StyledWord] = []
    for p in extract.pages:
        if p.number in doc.scanned:
            continue
        pm = mboxes.get(p.number, [])
        for i, ln in enumerate(p.lines):
            if (p.number, i) in furn or not ln.text.strip() or _in_box(ln, pm):
                continue
            for sp in ln.spans:
                for w in sp.text.split():
                    norm = _normalize_word(unicodedata.normalize("NFKC", w))
                    if len(norm) >= 2:
                        from ..fontmap import editable_font
                        _c, fam = editable_font(sp.font, sp.flags)
                        out.append(StyledWord(norm=norm, size=round(sp.size * 2) / 2, bold=sp.bold,
                                              italic=sp.italic, color=sp.color, family=fam, page=p.number))
    return out


def source_body_tokens(extract: DocExtract, doc: EditDoc) -> Dict[int, List[str]]:
    rows = _reading_rows(extract, doc)
    if rows is not None:
        texts: Dict[int, List[str]] = {}
        for pno, r in rows:
            prose = " ".join(" ".join(run.text for run in seg.runs if not run.math) for seg in r.segments)
            texts.setdefault(pno, []).append(prose)
        return {pno: tokenize(_join_eol_hyphens("\n".join(t), doc)) for pno, t in texts.items()}
    furn = doc.furniture.furniture_line_ids
    mboxes = _math_boxes(doc)
    per_page: Dict[int, List[str]] = {}
    for p in extract.pages:
        if p.number in doc.scanned:
            continue
        pm = mboxes.get(p.number, [])
        texts = []
        for i, ln in enumerate(p.lines):
            if (p.number, i) in furn or _in_box(ln, pm):
                continue
            texts.append(ln.text)
        per_page[p.number] = tokenize(_join_eol_hyphens("\n".join(texts), doc))
    return per_page


# ---------------------------------------------------------------------------
# Output words with style
# ---------------------------------------------------------------------------

def output_styled_words(pdf_bytes: bytes, skip_bands: Dict[int, Tuple[float, float]] = None
                        ) -> List[StyledWord]:
    import pymupdf
    skip_bands = skip_bands or {}
    out: List[StyledWord] = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        for i in range(doc.page_count):
            page = doc[i]
            top, bot = skip_bands.get(i + 1, (None, None))
            for blk in page.get_text("dict").get("blocks", []):
                for ln in blk.get("lines", []):
                    for sp in ln.get("spans", []):
                        if _MATH_OUT.search(sp.get("font", "")):
                            continue
                        y = sp["bbox"][1]
                        if top is not None and (y < top or y > bot):
                            continue
                        font = sp.get("font", "")
                        flags = sp.get("flags", 0)
                        bold = bool(flags & 16) or bool(_OUT_BOLD.search(font))
                        italic = bool(flags & 2) or bool(_OUT_ITALIC.search(font))
                        rgb = _int_to_rgb(int(sp.get("color", 0)))
                        fam = _out_family(font)
                        size = round(float(sp.get("size", 0)) * 2) / 2
                        for w in sp.get("text", "").split():
                            norm = _normalize_word(unicodedata.normalize("NFKC", w))
                            if len(norm) >= 2:
                                out.append(StyledWord(norm=norm, size=size, bold=bold, italic=italic,
                                                      color=rgb, family=fam, page=i + 1))
    return out


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

def _text_area(doc: EditDoc, w: float, h: float):
    """The output's text area (inside the margins), so its own page numbers don't count as text."""
    m = getattr(doc.profile, "margins", None) if doc.profile else None
    if not m:
        return None
    return (0.0, max(0.0, m["top"] - 4), w, min(h, h - m["bottom"] + 4))


_EOL_HYPHEN = re.compile(r"([A-Za-z]+(?:-[A-Za-z]+)*)-[ \t]*\n[ \t]*([A-Za-z]+)")


def _join_eol_hyphens(text: str, doc: EditDoc) -> str:
    """Join words broken at line ends the way the emitter does (hyphen.keep_hyphen), on both the
    source and the output side, so a compound kept whole ("paragraph-level") counts as itself."""
    from .hyphen import keep_hyphen
    words = getattr(doc.profile, "words", None) or set()
    comps = getattr(doc.profile, "compounds", None) or set()

    def join(m):
        left, right = m.group(1), m.group(2)
        return f"{left}-{right}" if keep_hyphen(left + "-", right, words, comps) else left + right
    return _EOL_HYPHEN.sub(join, text)


def output_tokens(pdf: bytes, doc: EditDoc, vocab=None) -> Dict[int, List[str]]:
    """Words of the output. A hyphen at a line end is joined away (TeX hyphenation) unless the
    hyphenated form is a word of the source ("cyber-domain" broken after its own hyphen)."""
    import pymupdf
    vocab = vocab or set()

    out: Dict[int, List[str]] = {}
    with pymupdf.open(stream=pdf, filetype="pdf") as d:
        for i in range(d.page_count):
            pg = d[i]
            area = _text_area(doc, pg.rect.width, pg.rect.height)
            kw = {"clip": pymupdf.Rect(*area)} if area else {}
            lines = []
            for blk in pg.get_text("dict", **kw).get("blocks", []):
                for ln in blk.get("lines", []):
                    lines.append("".join(sp.get("text", "") for sp in ln.get("spans", [])
                                         if not _MATH_OUT.search(sp.get("font", ""))))
            out[i + 1] = tokenize(_join_eol_hyphens("\n".join(lines), doc))
    return out


def coverage_and_order(extract: DocExtract, doc: EditDoc, pdf: bytes) -> Dict:
    src_per_page = source_body_tokens(extract, doc)
    src = [w for toks in src_per_page.values() for w in toks]
    out_per_page = output_tokens(pdf, doc, set(src))
    out = [w for toks in out_per_page.values() for w in toks]
    cov = compare_words(src, out)
    order = _order_ratio(src, out)
    # per source-page coverage against the whole output multiset
    page_cov = {}
    from collections import Counter
    out_c = Counter(w for w in out if len(w) >= 2)
    for pno, toks in src_per_page.items():
        src_c = Counter(w for w in toks if len(w) >= 2)
        if not src_c:
            page_cov[pno] = 1.0
            continue
        got = sum(min(n, out_c.get(w, 0)) for w, n in src_c.items())
        page_cov[pno] = round(got / sum(src_c.values()), 4)
    return {"coverage": round(cov.coverage, 4), "extra_ratio": round(cov.extra_ratio, 4),
            "order": round(order, 4), "page_coverage": page_cov,
            "missing": cov.missing[:25], "extra": cov.extra[:25]}


def _order_ratio(src: List[str], out: List[str]) -> float:
    src = [w for w in src if len(w) >= 2]
    out = [w for w in out if len(w) >= 2]
    if not src:
        return 1.0
    sm = difflib.SequenceMatcher(None, src, out, autojunk=False)
    matched = sum(b.size for b in sm.get_matching_blocks())
    return matched / len(src)


def style_fidelity(extract: DocExtract, doc: EditDoc, pdf: bytes) -> Dict:
    src = source_styled_words(extract, doc)
    bands = {}
    if doc.profile and getattr(doc.profile, "margins", None):
        import pymupdf
        with pymupdf.open(stream=pdf, filetype="pdf") as d:
            for i in range(d.page_count):
                a = _text_area(doc, d[i].rect.width, d[i].rect.height)
                bands[i + 1] = (a[1], a[3])
    out = output_styled_words(pdf, bands)
    if not src or not out:
        return {"overall": 1.0, "size": 1.0, "bold": 1.0, "italic": 1.0, "color": 1.0,
                "family": 1.0, "matched": 0}
    sm = difflib.SequenceMatcher(None, [w.norm for w in src], [w.norm for w in out], autojunk=False)
    attr = {"size": 0, "bold": 0, "italic": 0, "color": 0, "family": 0}
    n = 0
    all_ok = 0
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            s = src[a + k]
            o = out[b + k]
            n += 1
            ok_size = abs(s.size - o.size) <= 0.6
            ok_bold = s.bold == o.bold
            ok_ital = s.italic == o.italic
            ok_color = max(abs(sc - oc) for sc, oc in zip(s.color, o.color)) <= 10
            ok_fam = s.family == o.family
            attr["size"] += ok_size
            attr["bold"] += ok_bold
            attr["italic"] += ok_ital
            attr["color"] += ok_color
            attr["family"] += ok_fam
            if ok_size and ok_bold and ok_ital and ok_color and ok_fam:
                all_ok += 1
    if n == 0:
        return {"overall": 1.0, "size": 1.0, "bold": 1.0, "italic": 1.0, "color": 1.0,
                "family": 1.0, "matched": 0}
    return {"overall": round(all_ok / n, 4), "matched": n,
            **{k: round(v / n, 4) for k, v in attr.items()}}
