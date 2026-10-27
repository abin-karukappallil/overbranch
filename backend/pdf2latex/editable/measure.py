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
from typing import Dict, List, Optional, Tuple

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
# (EC / cm-super fonts: SFSS, SFSX, SFSI, SFSO sans; SFTT, SFIT… typewriter)
_OUT_SANS = re.compile(r"(sans|helvet|nimbussan|arial|lmss|cmss|heros|carlito|\bsfs[sxio]\d)", re.IGNORECASE)
_OUT_MONO = re.compile(r"(mono|courier|cmtt|lmtt|typewriter|cousine|\bsftt\d|\bsfit\d|\bsfst\d|\bsftc\d)",
                       re.IGNORECASE)


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


# ---------------------------------------------------------------------------
# Page-lock measurements: output rows, where each source page starts, figure placement, chrome
# ---------------------------------------------------------------------------

def norm_key(text: str, n: int = 16) -> str:
    return re.sub(r"[^0-9a-z]", "", (text or "").lower())[:n]


def output_rows(pdf: bytes, profile) -> List[Tuple[int, float, str, float]]:
    """The output's text rows inside the text area, in page then top-down order: (page index from 0,
    baseline, normalised text, top). Spans on one baseline make one row (a number and its title)."""
    import pymupdf
    out: List[Tuple[int, float, str, float]] = []
    with pymupdf.open(stream=pdf, filetype="pdf") as d:
        for pi, pg in enumerate(d):
            h = pg.rect.height
            lo = profile.margins.get("top", 72.0) - 4
            hi = h - profile.margins.get("bottom", 72.0) + 4
            items = []
            for blk in pg.get_text("dict").get("blocks", []):
                for ln in blk.get("lines", []):
                    spans = [sp for sp in ln.get("spans", []) if sp.get("text", "").strip()]
                    if not spans:
                        continue
                    base = spans[0]["origin"][1]
                    if not (lo <= ln["bbox"][1] and base <= hi):
                        continue
                    items.append((base, ln["bbox"][0], "".join(sp["text"] for sp in spans), ln["bbox"][1],
                                  ln["bbox"][2]))
            items.sort()
            merged: List[List] = []
            for base, x0, text, top, x1 in items:
                # one row per baseline, but never across a column gutter (two-column output)
                if merged and abs(merged[-1][0] - base) <= 1.5 and x0 - merged[-1][4] < 12:
                    merged[-1][3].append((x0, text))
                    merged[-1][2] = min(merged[-1][2], top)
                    merged[-1][4] = max(merged[-1][4], x1)
                else:
                    merged.append([base, x0, top, [(x0, text)], x1])
            for base, _x0, top, parts, _x1 in merged:
                text = " ".join(t for _x, t in sorted(parts))
                out.append((pi, base, re.sub(r"[^0-9a-z]", "", text.lower()), top))
    return out


def output_stream(pdf: bytes, doc: EditDoc) -> Tuple[str, List[int]]:
    """The output's body text, normalised (lower-case letters and digits only), in the order TeX
    shipped it (a two-column page: the left column, then the right), and each page's start offset."""
    import pymupdf
    parts: List[str] = []
    starts: List[int] = []
    pos = 0
    with pymupdf.open(stream=pdf, filetype="pdf") as d:
        for pg in d:
            area = _text_area(doc, pg.rect.width, pg.rect.height)
            kw = {"clip": pymupdf.Rect(*area)} if area else {}
            txt = []
            for blk in pg.get_text("dict", **kw).get("blocks", []):
                for ln in blk.get("lines", []):
                    txt.append("".join(sp.get("text", "") for sp in ln.get("spans", [])
                                       if not _MATH_OUT.search(sp.get("font", ""))))
            s = re.sub(r"[^0-9a-z]", "", unicodedata.normalize("NFKC", " ".join(txt)).lower())
            starts.append(pos)
            parts.append(s)
            pos += len(s)
    return "".join(parts), starts


def _row_norm(row) -> str:
    txt = " ".join("".join(r.text for r in seg.runs if not r.math) for seg in row.segments)
    return re.sub(r"[^0-9a-z]", "", unicodedata.normalize("NFKC", txt).lower())


def page_checks(doc: EditDoc) -> List[Tuple[int, int, str]]:
    """(source page, column, key) for the first row of each source page and of each column of its
    two-column bands: the text that must open that page (column) in a page-locked output."""
    checks: List[Tuple[int, int, str]] = []
    zone_rows = getattr(doc, "zone_rows", None) or {}
    mboxes = _math_boxes(doc)
    for pno in sorted(doc.rows_by_page):
        if pno in doc.scanned:
            continue
        seen_cols = set()
        bands = zone_rows.get(pno) or [((0, 1), doc.rows_by_page.get(pno, []))]
        first_page_key = None
        for (column, of_cols), rows in bands:
            col = column if of_cols == 2 else -1
            if col in seen_cols and first_page_key is not None:
                continue
            key = ""
            for r in rows:
                if _row_in_box(r, mboxes.get(pno, [])):
                    continue
                nk = _row_norm(r)
                if len(nk) >= 6:
                    # lengthen a short row with the rows after it (it is matched as a substring)
                    k = rows.index(r)
                    for r2 in rows[k + 1:k + 3]:
                        if len(nk) >= 24:
                            break
                        nk += _row_norm(r2)
                    key = nk[:24]
                    break
            if not key:
                continue
            if first_page_key is None:
                first_page_key = key
                checks.append((pno, -1, key))
                seen_cols.add(-1)
            if col >= 0 and col not in seen_cols:
                seen_cols.add(col)
                if key != first_page_key:
                    checks.append((pno, col, key))
    return checks


def page_start(doc: EditDoc, pdf: bytes) -> Dict:
    """Where each source page's (and column's) first text lands in the output. A page-locked
    output has every one on the page of the same number: score = share that do. A source page
    whose next page starts more than one output page later spilled."""
    stream, starts = output_stream(pdf, doc)

    def page_of(pos: int) -> int:
        import bisect
        return bisect.bisect_right(starts, pos)        # 1-based page

    checks = page_checks(doc)
    cursor = 0
    landing: Dict[Tuple[int, int], int] = {}
    unmatched: List[int] = []
    for pno, col, key in checks:
        pos = -1
        # prefer the page of the same number (a phrase repeated earlier must not pull the match);
        # then the key's first half (inline maths reads differently on the two sides: "f(x)")
        for k in (key, key[:12]):
            if pos < 0 and 1 <= pno <= len(starts) and len(k) >= 8:
                a = max(cursor, starts[pno - 1])
                b = starts[pno] if pno < len(starts) else len(stream)
                if a < b:
                    pos = stream.find(k, a, b + len(k))
        for k in (key, key[:12]):
            if pos < 0 and len(k) >= 8:
                pos = stream.find(k, cursor)
        if pos < 0:
            unmatched.append(pno)
            continue
        landing[(pno, col)] = page_of(pos)
        cursor = pos + 1
    ok = sum(1 for (pno, _c), out in landing.items() if out == pno)
    misplaced = sorted({(pno, out) for (pno, _c), out in landing.items() if out != pno})
    firsts = {pno: out for (pno, c), out in landing.items() if c == -1}
    order = sorted(firsts)
    spilled = []
    for a, b in zip(order, order[1:]):
        if b == a + 1 and firsts[b] - firsts[a] > 1:
            spilled.append(a)
    n = len(landing)
    return {"score": round(ok / n, 4) if n else 1.0, "checked": n, "misplaced": misplaced,
            "spilled": spilled, "unmatched": unmatched[:20], "landing": {str(k[0]) + (f".{k[1]}" if k[1] >= 0 else ""): v
                                                                        for k, v in landing.items()}}


def _png_size(path) -> Optional[Tuple[int, int]]:
    try:
        with open(path, "rb") as f:
            head = f.read(32)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            import struct
            w, h = struct.unpack(">II", head[16:24])
            return int(w), int(h)
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:  # noqa: BLE001
        return None


def figure_items(blocks) -> List[Tuple[int, str, Tuple[float, float, float, float]]]:
    """(page, image file, source box) of every picture, at any depth (title pages, boxes)."""
    from .model import Figure
    out = []
    for b in blocks:
        if isinstance(b, Figure):
            boxes = list(getattr(b, "boxes", None) or [])
            for i, img in enumerate(b.images):
                out.append((b.page, img, tuple(boxes[i]) if i < len(boxes) else tuple(b.bbox)))
        for attr in ("content", "body"):
            inner = getattr(b, attr, None)
            if inner:
                out.extend(figure_items(inner))
        for it in getattr(b, "items", []) or []:
            out.extend(figure_items(it.body))
    return out


def figure_position(doc: EditDoc, pdf: bytes, out_dir) -> Dict:
    """Each picture against the output's images, matched by the pixel size of the file it uses:
    on the same page, |dy| ≤ 24pt, width and height within 3% of the source box."""
    import pymupdf
    from pathlib import Path
    items = figure_items(doc.blocks)
    if not items:
        return {"total": 0, "ok": 0, "score": 1.0, "items": []}
    placed: List[Dict] = []
    with pymupdf.open(stream=pdf, filetype="pdf") as d:
        for pg in d:
            for info in pg.get_image_info():
                placed.append({"page": pg.number + 1, "bbox": info["bbox"],
                               "px": (int(info.get("width", 0)), int(info.get("height", 0))),
                               "used": False})
    res = []
    ok = 0
    for page, img, box in items:
        px = _png_size(Path(out_dir) / img) if out_dir else None
        cands = [p for p in placed if not p["used"] and (px is None or p["px"] == px)]
        if not cands:
            res.append({"page": page, "file": img, "found": False, "ok": False})
            continue
        best = min(cands, key=lambda p: (p["page"] != page, abs(p["page"] - page),
                                         abs(p["bbox"][1] - box[1])))
        best["used"] = True
        bw, bh = best["bbox"][2] - best["bbox"][0], best["bbox"][3] - best["bbox"][1]
        sw, sh = box[2] - box[0], box[3] - box[1]
        dy = best["bbox"][1] - box[1]
        dx = best["bbox"][0] - box[0]
        good = (best["page"] == page and abs(dy) <= 24 and sw > 0 and sh > 0
                and abs(bw - sw) <= 0.03 * sw and abs(bh - sh) <= 0.03 * sh)
        ok += good
        res.append({"page": page, "file": img, "found": True, "ok": bool(good), "out_page": best["page"],
                    "dy": round(dy, 1), "dx": round(dx, 1), "w": [round(sw, 1), round(bw, 1)],
                    "h": [round(sh, 1), round(bh, 1)]})
    return {"total": len(items), "ok": ok, "score": round(ok / len(items), 4), "items": res}


def chrome_style(extract: DocExtract, doc: EditDoc, pdf: bytes) -> Dict:
    """The running header/footer's font family, source against output, word by word per page."""
    import pymupdf
    from ..fontmap import editable_font
    furn = doc.furniture.furniture_line_ids if doc.furniture else set()
    src: Dict[int, List[Tuple[str, str]]] = {}
    for p in extract.pages:
        for i, ln in enumerate(p.lines):
            if (p.number, i) not in furn:
                continue
            for sp in ln.spans:
                _c, fam = editable_font(sp.font, sp.flags)
                for w in sp.text.split():
                    nw = _normalize_word(unicodedata.normalize("NFKC", w))
                    if len(nw) >= 2 and not nw.isdigit():
                        src.setdefault(p.number, []).append((nw, fam))
    if not src:
        return {"family": 1.0, "matched": 0}
    out: Dict[int, List[Tuple[str, str]]] = {}
    with pymupdf.open(stream=pdf, filetype="pdf") as d:
        for pg in d:
            area = _text_area(doc, pg.rect.width, pg.rect.height)
            if not area:
                continue
            for blk in pg.get_text("dict").get("blocks", []):
                for ln in blk.get("lines", []):
                    for sp in ln.get("spans", []):
                        y = (sp["bbox"][1] + sp["bbox"][3]) / 2
                        if area[1] <= y <= area[3]:
                            continue
                        fam = _out_family(sp.get("font", ""))
                        for w in sp.get("text", "").split():
                            nw = _normalize_word(unicodedata.normalize("NFKC", w))
                            if len(nw) >= 2 and not nw.isdigit():
                                out.setdefault(pg.number + 1, []).append((nw, fam))
    n = good = 0
    for pno, words in src.items():
        ow = out.get(pno, [])
        if not ow:
            continue
        sm = difflib.SequenceMatcher(None, [w for w, _ in words], [w for w, _ in ow], autojunk=False)
        for a, b, size in sm.get_matching_blocks():
            for k in range(size):
                n += 1
                good += words[a + k][1] == ow[b + k][1]
    return {"family": round(good / n, 4) if n else 1.0, "matched": n}


def page_extents(pdf: bytes, doc: EditDoc) -> Dict[int, Tuple[float, float]]:
    """Each output page's content extent inside the text area: (top, bottom) of its text and
    pictures, 1-based page → (y0, y1); a page with nothing there is absent."""
    import pymupdf
    out: Dict[int, Tuple[float, float]] = {}
    with pymupdf.open(stream=pdf, filetype="pdf") as d:
        for pg in d:
            area = _text_area(doc, pg.rect.width, pg.rect.height)
            if not area:
                continue
            ys = []
            for blk in pg.get_text("dict").get("blocks", []):
                for ln in blk.get("lines", []):
                    if any(sp.get("text", "").strip() for sp in ln.get("spans", [])):
                        y0, y1 = ln["bbox"][1], ln["bbox"][3]
                        if area[1] <= (y0 + y1) / 2 <= area[3]:
                            ys.append((y0, y1))
            for info in pg.get_image_info():
                y0, y1 = info["bbox"][1], info["bbox"][3]
                if area[1] <= (y0 + y1) / 2 <= area[3]:
                    ys.append((y0, y1))
            if ys:
                out[pg.number + 1] = (min(a for a, _ in ys), max(b for _, b in ys))
    return out


def page_overflow(doc: EditDoc, pdf: bytes) -> Dict:
    """How far each source page runs past its own output page: the height of its content on the
    extra pages it occupies (pt), from where each source page starts in the output."""
    ps = page_start(doc, pdf)
    firsts = {}
    for k, v in ps["landing"].items():
        if "." not in k:
            firsts[int(k)] = v
    n_out = 0
    import pymupdf
    with pymupdf.open(stream=pdf, filetype="pdf") as d:
        n_out = d.page_count
    ext = page_extents(pdf, doc)
    top = (doc.profile.margins or {}).get("top", 72.0)
    known = sorted(firsts)
    over: Dict[int, float] = {}
    for i, k in enumerate(known):
        nxt = firsts[known[i + 1]] if i + 1 < len(known) else n_out + 1
        # source pages between k and the next known one (no text of their own) each own a page
        between = (known[i + 1] - k - 1) if i + 1 < len(known) else (doc.page_count - k)
        extra = [e for e in range(firsts[k] + 1, nxt - between)]
        amount = 0.0
        for e in extra:
            if e in ext:
                amount += max(1.0, ext[e][1] - top)
            else:
                amount += 1.0
        if amount > 0:
            over[k] = round(amount, 1)
    return {"over": over, "total": round(sum(over.values()), 1), "landing": firsts, "pages_out": n_out,
            "page_start": ps}


def deck_overflow(doc: EditDoc, pdf: bytes) -> Dict:
    """A slide deck's slides are scaled down when their content is taller than the slide: per
    slide, the share the text was shrunk by (output size against the PDF's, by dominant size),
    as the height it overflowed, pt."""
    import pymupdf
    from collections import Counter
    m = doc.profile.margins
    height = (doc.profile.paper_pt[1] - m["top"] - m["bottom"]) if doc.profile.paper_pt else 300.0
    over: Dict[int, float] = {}
    with pymupdf.open(stream=pdf, filetype="pdf") as d:
        for pno in sorted(doc.rows_by_page):
            if pno > d.page_count:
                continue
            src = Counter()
            for r in doc.rows_by_page.get(pno, []):
                for run in r.runs:
                    if run.text.strip() and not run.math:
                        src[run.size] += len(run.text.strip())
            if not src:
                continue
            want = src.most_common(1)[0][0]
            out = Counter()
            for blk in d[pno - 1].get_text("dict").get("blocks", []):
                for ln in blk.get("lines", []):
                    for sp in ln.get("spans", []):
                        if sp.get("text", "").strip():
                            out[round(sp["size"] * 2) / 2] += len(sp["text"].strip())
            if not out:
                continue
            # the output size nearest to the PDF's (the dominant one may be another size scaled)
            got = out.most_common(1)[0][0]
            scale = got / want if want else 1.0
            if 0.2 < scale < 0.97:
                over[pno] = round((1.0 / scale - 1.0) * height, 1)
    return {"over": over, "total": round(sum(over.values()), 1), "landing": {p: p for p in doc.rows_by_page},
            "pages_out": doc.page_count, "page_start": None}
