"""
raster.py — Stage 4 of the AI rebuild: page PNGs.

`rasterize_pages` writes `page_N.png` for every page (the image the model sees and the visual
reference for measuring), `page_png_bytes` and `crop_png` render one page or one region in memory.
All renders are RGB without alpha, in the displayed orientation (PyMuPDF applies /Rotate).

PyMuPDF documents are not thread-safe, so each function opens its own document and works
sequentially; callers run them with `asyncio.to_thread`, one call per job.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, Optional, Sequence

import pymupdf
from PIL import Image

from .model import Rect
from .settings import get_rebuild_settings

logger = logging.getLogger(__name__)


def _scale(dpi: int) -> "pymupdf.Matrix":
    return pymupdf.Matrix(dpi / 72.0, dpi / 72.0)


def _expected_size(page: "pymupdf.Page", dpi: int) -> tuple:
    """Pixel size `get_pixmap(dpi=dpi)` produces for this page."""
    irect = (page.rect * _scale(dpi)).irect
    return irect.width, irect.height


def _up_to_date(path: Path, pdf_mtime: float, size: tuple) -> bool:
    """An existing PNG is reusable if it is newer than the PDF, readable and has the wanted size."""
    try:
        st = path.stat()
        if st.st_size == 0 or st.st_mtime < pdf_mtime:
            return False
        with Image.open(path) as im:
            return im.size == size
    except Exception:  # noqa: BLE001 — unreadable or truncated: render again
        return False


def _render(page: "pymupdf.Page", dpi: int, clip: Optional[Sequence[float]] = None) -> "pymupdf.Pixmap":
    return page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False,
                           clip=pymupdf.Rect(*clip) if clip is not None else None)


def rasterize_pages(pdf: Path, out_dir: Path, dpi: Optional[int] = None) -> Dict[int, Path]:
    """
    Renders every page of `pdf` to `out_dir/page_N.png` and returns {page number: path}.

    Resumable: a PNG that is newer than the PDF and already has the size this `dpi` produces is kept
    as is. Files are written to a temporary name and renamed, so a killed run never leaves a
    half-written PNG that a resume would trust. `dpi` defaults to the PDF2LATEX_RASTER_DPI setting.
    """
    dpi = dpi or get_rebuild_settings().raster_dpi
    pdf = Path(pdf)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_mtime = pdf.stat().st_mtime
    out: Dict[int, Path] = {}
    with pymupdf.open(str(pdf)) as doc:
        for i in range(doc.page_count):
            n = i + 1
            path = out_dir / f"page_{n}.png"
            page = doc[i]
            if not _up_to_date(path, pdf_mtime, _expected_size(page, dpi)):
                tmp = out_dir / f".page_{n}.png.tmp"
                _render(page, dpi).save(str(tmp), output="png")
                os.replace(tmp, path)
            out[n] = path
    return out


def page_png_bytes(pdf: Path, n: int, dpi: int) -> bytes:
    """PNG bytes of 1-based page `n`."""
    with pymupdf.open(str(pdf)) as doc:
        if not 1 <= n <= doc.page_count:
            raise ValueError(f"page {n} is outside 1..{doc.page_count}")
        return _render(doc[n - 1], dpi).tobytes("png")


def crop_png(pdf: Path, n: int, rect: Rect, dpi: int) -> bytes:
    """PNG bytes of the region `rect` (pt, page space) of page `n`, clipped to the page."""
    with pymupdf.open(str(pdf)) as doc:
        if not 1 <= n <= doc.page_count:
            raise ValueError(f"page {n} is outside 1..{doc.page_count}")
        page = doc[n - 1]
        clip = pymupdf.Rect(*rect) & page.rect
        if clip.is_empty or clip.width < 0.5 or clip.height < 0.5:
            raise ValueError(f"crop {tuple(rect)} does not overlap page {n}")
        return _render(page, dpi, tuple(clip)).tobytes("png")
