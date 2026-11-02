"""
ocr.py — Stage 2 of the AI rebuild: give scanned pages a text layer.

Runs only when the inspection found scanned pages that carry no text layer yet and OCR is enabled.
The output PDF has the same pages in the same order and size, with an invisible (render mode 3)
text layer on the scanned ones; the caller extracts from `dst` instead of the source.

Two engines, tried in this order:
  ocrmypdf   `ocrmypdf --skip-text --output-type pdf --optimize 0 -l <lang>` in a subprocess
  pymupdf    `page.get_textpage_ocr` (tesseract) and an invisible line-by-line text layer written
             over the untouched page

Failures never raise: an engine that is missing, a language without trained data, a timeout, or a
broken output all come back as `OcrResult(applied=False, warnings=[...])` and the job simply
continues from the scan with the model looking at the page image.
"""

from __future__ import annotations

import glob
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import pymupdf

from ..extract import normalize_rotation
from .model import Inspection
from .settings import get_rebuild_settings

logger = logging.getLogger(__name__)

OCR_DPI = 300                   # render resolution handed to tesseract on the PyMuPDF path
MAX_OCR_PIXELS = 9000           # longest side; huge pages are rendered at a lower dpi
_TESSDATA_CANDIDATES = ("/usr/share/tessdata", "/usr/share/tesseract-ocr/*/tessdata",
                        "/usr/local/share/tessdata", "/opt/homebrew/share/tessdata")
_NOT_A_LANGUAGE = {"osd", "equ"}    # traineddata files that cannot recognise text


@dataclass
class OcrResult:
    applied: bool = False
    engine: str = ""                                    # "ocrmypdf" | "pymupdf" | ""
    pages: List[int] = field(default_factory=list)      # 1-based pages that now have OCR text
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tesseract data and engine selection
# ---------------------------------------------------------------------------

def find_tessdata() -> Optional[Path]:
    """The tessdata directory: TESSDATA_PREFIX (itself or its `tessdata` child), else the usual places."""
    env = (os.environ.get("TESSDATA_PREFIX") or "").strip()
    candidates: List[str] = []
    if env:
        candidates += [env, os.path.join(env, "tessdata")]
    for pattern in _TESSDATA_CANDIDATES:
        candidates += sorted(glob.glob(pattern), reverse=True)
    for c in candidates:
        p = Path(c)
        if p.is_dir() and any(p.glob("*.traineddata")):
            return p
    return None


def installed_languages(tessdata: Optional[Path]) -> List[str]:
    if tessdata is None:
        return []
    return sorted(p.stem for p in tessdata.glob("*.traineddata") if p.stem not in _NOT_A_LANGUAGE)


def resolve_language(language: str, tessdata: Optional[Path]) -> Tuple[str, List[str]]:
    """
    Keeps the requested languages ("eng", "eng+afr") that have trained data.
    Returns ("eng+afr", warnings); "" when none of them is installed.
    """
    wanted = [l for l in (language or "").replace(",", "+").split("+") if l.strip()]
    wanted = [l.strip() for l in wanted] or ["eng"]
    have = set(installed_languages(tessdata))
    keep = [l for l in wanted if l in have]
    missing = [l for l in wanted if l not in have]
    warnings: List[str] = []
    if not keep:
        where = str(tessdata) if tessdata else "no tessdata directory found"
        warnings.append(f"OCR skipped: no tesseract language data for {'+'.join(wanted)} ({where}).")
        return "", warnings
    if missing:
        warnings.append(f"OCR language data missing for {'+'.join(missing)}; using {'+'.join(keep)}.")
    return "+".join(keep), warnings


def select_engine(tessdata: Optional[Path]) -> str:
    """"ocrmypdf" when it and tesseract are installed, else "pymupdf" when there is tessdata, else ""."""
    if tessdata is None:
        return ""
    if shutil.which("ocrmypdf") and shutil.which("tesseract"):
        return "ocrmypdf"
    return "pymupdf"


def build_ocrmypdf_command(exe: str, src: Path, dst: Path, language: str) -> List[str]:
    return [exe, "--skip-text", "--output-type", "pdf", "--optimize", "0", "-l", language,
            str(src), str(dst)]


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------

def _run_ocrmypdf(src: Path, dst: Path, language: str, tessdata: Optional[Path],
                  timeout_s: int) -> Tuple[bool, str]:
    """(ok, warning). Never raises."""
    exe = shutil.which("ocrmypdf") or "ocrmypdf"
    env = dict(os.environ)
    if tessdata is not None:
        env["TESSDATA_PREFIX"] = str(tessdata)
    try:
        proc = subprocess.run(build_ocrmypdf_command(exe, src, dst, language), capture_output=True,
                              text=True, timeout=timeout_s, env=env, check=False)
    except subprocess.TimeoutExpired:
        return False, f"ocrmypdf timed out after {timeout_s}s."
    except OSError as e:
        return False, f"ocrmypdf could not be started: {e}"
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] or [""]
        return False, f"ocrmypdf failed (exit {proc.returncode}): {tail[0][:200]}"
    return True, ""


def _page_scale_dpi(page: "pymupdf.Page") -> int:
    longest = max(page.rect.width, page.rect.height) or 1.0
    return max(72, min(OCR_DPI, int(MAX_OCR_PIXELS * 72 / longest)))


def _add_invisible_layer(page: "pymupdf.Page", language: str, tessdata: Optional[Path]) -> int:
    """OCRs `page` and writes the recognised lines as render-mode-3 text. Returns the line count."""
    tp = page.get_textpage_ocr(language=language, dpi=_page_scale_dpi(page), full=True,
                               tessdata=str(tessdata) if tessdata else None)
    written = 0
    for block in tp.extractDICT().get("blocks", []):
        for ln in block.get("lines", []):
            spans = [s for s in ln.get("spans", []) if s.get("text")]
            text = "".join(s["text"] for s in spans).strip()
            words = [s for s in spans if s["text"].strip()]
            if not text or not words:
                continue
            size = sorted(s["size"] for s in words)[len(words) // 2]
            size = max(2.0, min(size, 200.0))
            x0, y0, x1, y1 = ln["bbox"]
            origin = pymupdf.Point(words[0]["origin"])
            natural = pymupdf.get_text_length(text, fontname="helv", fontsize=size)
            sx = (x1 - x0) / natural if natural > 0 else 1.0
            sx = max(0.3, min(3.0, sx))        # stretch the invisible text over the recognised line box
            try:
                page.insert_text(origin, text, fontname="helv", fontsize=size, render_mode=3,
                                 morph=(origin, pymupdf.Matrix(sx, 1)))
                written += 1
            except Exception as e:  # noqa: BLE001 — a line the font cannot encode only loses that line
                logger.debug(f"OCR line skipped on page {page.number + 1}: {e}")
    return written


def _run_pymupdf(src: Path, dst: Path, pages: Sequence[int], language: str, tessdata: Optional[Path],
                 timeout_s: int) -> Tuple[bool, List[str]]:
    """Writes `dst` = `src` with an invisible text layer on `pages`. (ok, warnings). Never raises."""
    warnings: List[str] = []
    deadline = time.monotonic() + timeout_s
    try:
        doc = pymupdf.open(str(src))
    except Exception as e:  # noqa: BLE001
        return False, [f"OCR could not open the PDF: {e}"]
    try:
        normalize_rotation(doc)     # later stages work in the displayed orientation
        skipped: List[int] = []
        for n in pages:
            if time.monotonic() >= deadline:
                skipped.append(n)
                continue
            try:
                _add_invisible_layer(doc[n - 1], language, tessdata)
            except Exception as e:  # noqa: BLE001 — one bad page must not lose the others
                warnings.append(f"OCR failed on page {n}: {str(e)[:150]}")
        if skipped:
            warnings.append(f"OCR stopped after {timeout_s}s; page(s) {', '.join(map(str, skipped))} were not read.")
        doc.save(str(dst), garbage=1, deflate=True)
    except Exception as e:  # noqa: BLE001
        return False, warnings + [f"OCR output could not be written: {e}"]
    finally:
        doc.close()
    return True, warnings


def _pages_with_text(pdf: Path, pages: Sequence[int], expected_pages: int) -> Optional[List[int]]:
    """Which of `pages` have any text (visible or not) in `pdf`; None if `pdf` is not a faithful copy."""
    try:
        with pymupdf.open(str(pdf)) as doc:
            if doc.page_count != expected_pages:
                return None
            return [n for n in pages if doc[n - 1].get_text("text").strip()]
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def ensure_text_layer(src: Path, dst: Path, inspection: Inspection, *, language: str,
                      timeout_s: int) -> OcrResult:
    """
    OCRs the scanned pages of `src` into `dst`.

    Does nothing (applied=False, `dst` not written) when OCR is disabled, when no page is scanned
    without a text layer, or when no engine / language data is available; the reason is in `warnings`
    for the last case. `inspection` is UPDATED IN PLACE on success: `PageInfo.ocr=True` for the pages that
    now have OCR text and `ocr_applied=True`. Page order, count and size are unchanged. Afterwards
    the caller extracts from `dst`. Text added by OCR is invisible (render mode 3), so `PageInfo.chars`
    (visible characters) and `scanned` keep describing the source.
    """
    result = OcrResult()
    if not get_rebuild_settings().ocr_enabled:
        return result
    todo = [p.number for p in inspection.pages if p.scanned and not p.ocr]
    if not todo:
        return result
    if Path(src).resolve() == Path(dst).resolve():
        raise ValueError("ensure_text_layer: dst must differ from src")

    tessdata = find_tessdata()
    lang, warnings = resolve_language(language, tessdata)
    result.warnings.extend(warnings)
    if not lang:
        return result
    engine = select_engine(tessdata)

    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    ok = False
    if engine == "ocrmypdf":
        ok, warn = _run_ocrmypdf(Path(src), dst, lang, tessdata, timeout_s)
        if not ok:
            result.warnings.append(warn)
            if "timed out" in warn:
                dst.unlink(missing_ok=True)
                return result
            engine = "pymupdf"      # ocrmypdf is present but failed (e.g. signed PDF): try the built-in path
    if engine == "pymupdf":
        ok, warns = _run_pymupdf(Path(src), dst, todo, lang, tessdata, timeout_s)
        result.warnings.extend(warns)
    if not ok:
        dst.unlink(missing_ok=True)
        return result

    done = _pages_with_text(dst, todo, inspection.page_count)
    if done is None:
        result.warnings.append("OCR output did not match the source pages and was discarded.")
        dst.unlink(missing_ok=True)
        return result
    empty = [n for n in todo if n not in done]
    if empty:
        result.warnings.append(f"OCR found no text on page(s) {', '.join(map(str, empty))}.")
    if not done:
        dst.unlink(missing_ok=True)
        return result

    result.applied = True
    result.engine = engine
    result.pages = done
    for p in inspection.pages:
        if p.number in done:
            p.ocr = True
    inspection.ocr_applied = True
    return result
