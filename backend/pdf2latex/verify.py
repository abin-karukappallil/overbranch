"""
verify.py — Visual verification: render PDFs with pdftoppm and compare pages
using SSIM (scikit-image) plus a pixel-difference ratio. Also exposes a text-
coverage gate: word-level comparison between source and rendered PDFs, used
to detect LLM paraphrasing/drops/hallucinations that SSIM cannot see.
"""

import io
import logging
import re
import shutil
import subprocess
import tempfile
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .models import BBox

logger = logging.getLogger("pdf2latex.verify")

PIXEL_DIFF_LEVEL = 32  # grey levels; differences below this are anti-aliasing noise
SSIM_WEIGHT = 0.85
SOFTEN = 3          # block-mean downsample before SSIM: tolerates sub-pixel glyph jitter (and is ~9x faster)
MAX_SHIFT_PT = 8.0  # how far the render may sit above/below the original before it counts as misplaced
SHIFT_TIE = 0.995   # a larger offset must beat the smaller one by more than this to be preferred


@dataclass
class Region:
    bbox: BBox  # PDF points
    diff_fraction: float
    ssim_loss: float


@dataclass
class PageComparison:
    score: float
    ssim: float
    pixel_diff: float
    regions: List[Region] = field(default_factory=list)
    size_mismatch: bool = False
    shift_pt: float = 0.0  # vertical offset of the render relative to the original (negative = higher up)


def _load_png_gray(data: bytes) -> np.ndarray:
    from PIL import Image
    with Image.open(io.BytesIO(data)) as im:
        return np.asarray(im.convert("L"), dtype=np.uint8)


def render_pdf_pages(pdf_path: Path, dpi: int, first: Optional[int] = None,
                     last: Optional[int] = None) -> List[np.ndarray]:
    """Renders pages to grayscale arrays with pdftoppm (PyMuPDF fallback if poppler is missing)."""
    if shutil.which("pdftoppm"):
        with tempfile.TemporaryDirectory() as td:
            cmd = ["pdftoppm", "-gray", "-png", "-r", str(dpi)]
            if first:
                cmd += ["-f", str(first)]
            if last:
                cmd += ["-l", str(last)]
            cmd += [str(pdf_path), str(Path(td) / "p")]
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
            files = sorted(Path(td).glob("p-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
            return [_load_png_gray(f.read_bytes()) for f in files]
    import pymupdf
    out = []
    with pymupdf.open(str(pdf_path)) as doc:
        lo = (first or 1) - 1
        hi = (last or doc.page_count) - 1
        for i in range(lo, hi + 1):
            pix = doc[i].get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
            out.append(np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width).copy())
    return out


def _match_shapes(a: np.ndarray, b: np.ndarray) -> Tuple[np.ndarray, np.ndarray, bool]:
    if a.shape == b.shape:
        return a, b, False
    h, w = max(a.shape[0], b.shape[0]), max(a.shape[1], b.shape[1])

    def pad(x: np.ndarray) -> np.ndarray:
        out = np.full((h, w), 255, dtype=np.uint8)
        out[: x.shape[0], : x.shape[1]] = x
        return out

    mismatch = abs(a.shape[0] - b.shape[0]) > 2 or abs(a.shape[1] - b.shape[1]) > 2
    return pad(a), pad(b), mismatch


def _ink_profile(a: np.ndarray) -> np.ndarray:
    """Per-row ink mass — the signal used to align two renders of the same text."""
    return (255.0 - a.astype(np.float32)).sum(axis=1)


def _best_vertical_shift(a: np.ndarray, b: np.ndarray, max_px: int) -> int:
    """
    Row offset that best aligns b onto a, from the normalized correlation of the ink profiles.

    Body text has a near-constant line pitch, so the correlation is almost periodic and a
    plain argmax happily reports "shifted by one whole line". Offsets are therefore scanned
    outwards from zero and a larger one is only taken when it beats the smaller one clearly.
    """
    pa, pb = _ink_profile(a), _ink_profile(b)
    n = min(len(pa), len(pb))
    pa, pb = pa[:n], pb[:n]
    if not pa.any() or not pb.any():
        return 0

    def corr(s: int) -> float:
        if s >= 0:
            x, y = pa[s:], pb[: n - s]
        else:
            x, y = pa[: n + s], pb[-s:]
        norm = float(np.linalg.norm(x) * np.linalg.norm(y))
        return float(np.dot(x, y)) / norm if norm else 0.0

    best, best_val = 0, corr(0)
    for mag in range(1, max_px + 1):
        for s in (-mag, mag):
            val = corr(s)
            if val * SHIFT_TIE > best_val:
                best, best_val = s, val
    return best


def _apply_shift(a: np.ndarray, b: np.ndarray, s: int) -> Tuple[np.ndarray, np.ndarray]:
    if s > 0:
        return a[s:], b[: a.shape[0] - s]
    if s < 0:
        return a[: a.shape[0] + s], b[-s:]
    return a, b


def _soften(a: np.ndarray, factor: int = 0) -> np.ndarray:
    """Block-mean downsample. Two renders of the same text differ by a fraction of a pixel
    per glyph; at full resolution that noise dominates SSIM."""
    factor = factor or SOFTEN
    if factor <= 1:
        return a.astype(np.float32)
    h, w = (a.shape[0] // factor) * factor, (a.shape[1] // factor) * factor
    if h < factor or w < factor:
        return a.astype(np.float32)
    return a[:h, :w].astype(np.float32).reshape(h // factor, factor, w // factor, factor).mean(axis=(1, 3))


def compare_pages(original: np.ndarray, rendered: np.ndarray, dpi: int, grid: int = 8,
                  top_k: int = 6) -> PageComparison:
    """
    Visual comparison of two grayscale renders: SSIM + pixel diff, plus the worst grid regions.

    The render is first aligned vertically and both images are softened, so the score measures
    "does this look like the same page" rather than "are the glyphs on the same pixel". The
    result is a diagnostic — it is deliberately NOT the gate that decides whether a page is
    good enough, because full-page SSIM is dominated by the white background and so cannot
    separate a faithful reflow from a page with text missing. Text coverage does that.
    """
    from skimage.metrics import structural_similarity

    a, b, mismatch = _match_shapes(original, rendered)
    shift = _best_vertical_shift(a, b, max(1, int(round(MAX_SHIFT_PT * dpi / 72.0))))
    sa, sb = _apply_shift(a, b, shift)
    factor = SOFTEN
    fa, fb = _soften(sa, factor), _soften(sb, factor)
    if min(fa.shape) < 7:  # too small to soften and still have an SSIM window
        factor = 1
        fa, fb = sa.astype(np.float32), sb.astype(np.float32)
    ssim, ssim_map = structural_similarity(fa, fb, data_range=255.0, full=True)
    diff_mask = np.abs(fa - fb) > PIXEL_DIFF_LEVEL
    diff_frac = float(diff_mask.mean())
    score = SSIM_WEIGHT * float(ssim) + (1 - SSIM_WEIGHT) * (1.0 - diff_frac)
    if mismatch:
        score *= 0.9

    regions: List[Region] = []
    h, w = fa.shape
    ch, cw = max(1, h // grid), max(1, w // grid)
    scale = 72.0 * factor / dpi  # the grid is measured on the softened image
    y_off = max(0, shift) * 72.0 / dpi  # report region coordinates in the ORIGINAL page's frame
    for gy in range(grid):
        for gx in range(grid):
            y0, x0 = gy * ch, gx * cw
            y1 = h if gy == grid - 1 else y0 + ch
            x1 = w if gx == grid - 1 else x0 + cw
            df = float(diff_mask[y0:y1, x0:x1].mean())
            sl = float(1.0 - ssim_map[y0:y1, x0:x1].mean())
            if df > 0.002:
                regions.append(Region(bbox=(x0 * scale, y0 * scale + y_off, x1 * scale, y1 * scale + y_off),
                                      diff_fraction=df, ssim_loss=sl))
    regions.sort(key=lambda r: (r.diff_fraction + r.ssim_loss), reverse=True)
    return PageComparison(score=float(score), ssim=float(ssim), pixel_diff=diff_frac,
                          regions=regions[:top_k], size_mismatch=mismatch,
                          shift_pt=round(shift * 72.0 / dpi, 1))


def diff_heatmap_png(original: np.ndarray, rendered: np.ndarray) -> bytes:
    """Red overlay of differing pixels on top of the original (for LLM repair prompts and the UI)."""
    from PIL import Image
    a, b, _ = _match_shapes(original, rendered)
    mask = np.abs(a.astype(np.int16) - b.astype(np.int16)) > PIXEL_DIFF_LEVEL
    rgb = np.stack([a, a, a], axis=-1).astype(np.uint8)
    rgb[mask] = (255, 0, 0)
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="PNG")
    return buf.getvalue()


def gray_to_png(arr: np.ndarray) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def describe_regions(regions: List[Region]) -> str:
    if not regions:
        return "No localized differences."
    return "\n".join(
        f"- region x={r.bbox[0]:.0f}..{r.bbox[2]:.0f}pt, y={r.bbox[1]:.0f}..{r.bbox[3]:.0f}pt (from top-left): "
        f"{r.diff_fraction * 100:.1f}% pixels differ"
        for r in regions
    )


# ---------------------------------------------------------------------------
# Text-coverage gate: catches LLM paraphrasing / drops / hallucinations
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[\w\-]+", re.UNICODE)


def _normalize_word(w: str) -> str:
    return w.strip().strip("-").lower()


_LINE_HYPHEN_RE = re.compile(r"(\w)-[ \t]*\n[ \t]*(\w)")


def tokenize(text: str) -> List[str]:
    """Words, case-folded; ligatures unfolded (NFKC) and line-break hyphenation joined on both sides."""
    text = _LINE_HYPHEN_RE.sub(r"\1\2", unicodedata.normalize("NFKC", text or ""))
    return [w for w in (_normalize_word(m.group(0)) for m in _WORD_RE.finditer(text)) if w]


@dataclass
class TextCoverage:
    source_count: int
    rendered_count: int
    missing: List[Tuple[str, int]]  # (word, how many missing) — in source but not (enough) in render
    extra: List[Tuple[str, int]]    # (word, how many extra) — in render but not source (hallucinations)
    missing_total: int = 0  # full counts; `missing` / `extra` above are truncated for display
    extra_total: int = 0

    @property
    def ok(self) -> bool:
        return not self.missing and not self.extra

    @property
    def coverage(self) -> float:
        if self.source_count == 0:
            return 1.0
        return max(0.0, (self.source_count - self.missing_total) / self.source_count)

    @property
    def extra_ratio(self) -> float:
        """Invented words as a share of the source's — catches a model that pads the page."""
        return self.extra_total / self.source_count if self.source_count else 0.0


def extract_words_from_pdf(pdf_bytes: bytes) -> Dict[int, List[str]]:
    """Returns {page_number (1-based): [normalized words]} using PyMuPDF."""
    import pymupdf
    out: Dict[int, List[str]] = {}
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        for i in range(doc.page_count):
            out[i + 1] = tokenize(doc[i].get_text("text") or "")
    return out


# ---------------------------------------------------------------------------
# Layout gate: are the words in the right PLACE, not merely present?
# ---------------------------------------------------------------------------

@dataclass
class WordBox:
    text: str
    x: float
    y: float


def words_with_boxes(pdf_bytes: bytes, page_index: int = 0) -> List[WordBox]:
    """Words of one page with their centres in PDF points, in reading order."""
    import pymupdf
    out: List[WordBox] = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        if page_index >= doc.page_count:
            return out
        for x0, y0, x1, y1, w, *_ in doc[page_index].get_text("words"):
            norm = _normalize_word(unicodedata.normalize("NFKC", w))
            if len(norm) >= 2:
                out.append(WordBox(norm, (x0 + x1) / 2.0, (y0 + y1) / 2.0))
    return out


def displacement(source: List[WordBox], rendered: List[WordBox]) -> Optional[float]:
    """
    Median distance, in pt, between where a word sits in the source and where it sits in the
    output — the signal SSIM cannot give. A page may carry every word and still be scrambled:
    full-page SSIM scored one such page 0.75, barely below a faithful reproduction, because it
    is dominated by the white background. Matching is greedy and in order, so a re-set page
    (words nudged by justification) stays small while a page whose blocks were interleaved or
    pulled across by a bad \vspace does not.
    """
    if not source or not rendered:
        return None
    pool: Dict[str, List[WordBox]] = {}
    for wb in rendered:
        pool.setdefault(wb.text, []).append(wb)
    dists: List[float] = []
    for wb in source:
        bucket = pool.get(wb.text)
        if not bucket:
            continue
        best = min(bucket, key=lambda r: abs(r.y - wb.y) * 2 + abs(r.x - wb.x))
        bucket.remove(best)
        dists.append(((best.x - wb.x) ** 2 + (best.y - wb.y) ** 2) ** 0.5)
    if len(dists) < max(3, 0.3 * len(source)):
        return None  # too few matches to say anything
    return float(np.median(dists))


def compare_words(source: List[str], rendered: List[str], top_k: int = 25,
                  min_len: int = 2) -> TextCoverage:
    """Multiset comparison; ignores single-character tokens and stop-punctuation residue."""
    src = Counter(w for w in source if len(w) >= min_len)
    rnd = Counter(w for w in rendered if len(w) >= min_len)
    missing_c: Counter = Counter()
    extra_c: Counter = Counter()
    for w, n in src.items():
        d = n - rnd.get(w, 0)
        if d > 0:
            missing_c[w] = d
    for w, n in rnd.items():
        d = n - src.get(w, 0)
        if d > 0:
            extra_c[w] = d
    missing = sorted(missing_c.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]
    extra = sorted(extra_c.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]
    return TextCoverage(source_count=sum(src.values()), rendered_count=sum(rnd.values()),
                        missing=missing, extra=extra,
                        missing_total=sum(missing_c.values()), extra_total=sum(extra_c.values()))


def describe_text_coverage(cov: TextCoverage, max_show: int = 15) -> str:
    """Human-readable summary for repair prompts."""
    if cov.ok:
        return "Text coverage: all source words present."
    parts: List[str] = [f"Text coverage: {cov.coverage * 100:.1f}% of source words present."]
    if cov.missing:
        shown = ", ".join(f"{w}×{n}" if n > 1 else w for w, n in cov.missing[:max_show])
        parts.append(f"MISSING from your output (restore these verbatim): {shown}")
    if cov.extra:
        shown = ", ".join(f"{w}×{n}" if n > 1 else w for w, n in cov.extra[:max_show])
        parts.append(f"EXTRA in your output (not in source — remove or correct): {shown}")
    return "\n".join(parts)
