"""
pdf_parser.py — PyMuPDF-based PDF extraction service

Extracts rich structural content from PDF documents:
- Text content with page breakdown and layout analysis
- Page dimensions and aspect ratio (to distinguish Beamer vs Article)
- Embedded images (figures, photos, logos) saved to asset buffers
- Rendered page images at 300 DPI (high-resolution) and 150 DPI (LLM vision reference)
- Document type heuristics (slides, academic paper, resume, report)
"""

import io
import re
import base64
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

import pymupdf as fitz

logger = logging.getLogger("pdf_parser")

MAX_ALLOWED_PAGES = 50


@dataclass
class ExtractedImage:
    filename: str
    data_bytes: bytes
    source_page: int
    width: int
    height: int
    ext: str = "png"
    mime_type: str = "image/png"


@dataclass
class PageData:
    page_number: int  # 1-indexed
    width: float  # points
    height: float  # points
    aspect_ratio: float  # width / height
    text: str
    blocks: List[Dict[str, Any]]
    rendered_300dpi_png: Optional[bytes] = None
    rendered_150dpi_png: Optional[bytes] = None


@dataclass
class PDFParseResult:
    num_pages: int
    pages: List[PageData]
    embedded_images: List[ExtractedImage]
    doc_type_hint: str  # "beamer", "resume", "article", "report"
    aspect_ratio_hint: str  # "169", "43", "portrait"
    full_text: str
    page_size_hint: str  # "letter", "a4", "custom"


def decode_pdf_input(pdf_input: Any) -> bytes:
    """Decodes PDF input from raw bytes, base64 data URL, or plain base64 string."""
    if isinstance(pdf_input, bytes):
        return pdf_input
    if isinstance(pdf_input, str):
        cleaned = pdf_input.strip()
        if cleaned.startswith("data:application/pdf;base64,"):
            cleaned = cleaned.split("data:application/pdf;base64,", 1)[1]
        elif "," in cleaned and ("base64" in cleaned[:50]):
            cleaned = cleaned.split(",", 1)[1]
        # Pad if needed
        padding = len(cleaned) % 4
        if padding:
            cleaned += "=" * (4 - padding)
        return base64.b64decode(cleaned)
    raise ValueError("Invalid PDF input: expected bytes or base64 string")


def infer_doc_type(
    pages: List[PageData],
    full_text: str,
    doc_type_override: Optional[str] = None,
) -> Tuple[str, str, str]:
    """
    Infers document type, aspect ratio, and paper size from extracted pages and text.
    Returns: (doc_type, aspect_ratio_hint, page_size_hint)
    """
    if doc_type_override and doc_type_override.lower() in ["beamer", "article", "report", "resume"]:
        override = doc_type_override.lower()
        aspect_ratio_hint = "169" if override == "beamer" else "portrait"
        page_size_hint = "custom" if override == "beamer" else "a4paper"
        return override, aspect_ratio_hint, page_size_hint

    if not pages:
        return "article", "portrait", "a4paper"

    first_page = pages[0]
    ar = first_page.aspect_ratio
    text_lower = full_text.lower()

    # Landscape check: Slide presentations are strictly landscape with width >= 1.25x height.
    # PowerPoint, Google Slides, Keynote, and Beamer decks have AR ~1.78 (16:9) or ~1.33 (4:3).
    # Academic papers, reports, theses, resumes are portrait (AR ~0.70-0.77).
    is_landscape = ar >= 1.25

    if is_landscape:
        aspect_ratio_hint = "169" if ar >= 1.50 else "43"
        return "beamer", aspect_ratio_hint, "custom"

    # Resume / CV check (typically 1-3 pages portrait with work history / education)
    resume_keywords = ["curriculum vitae", "resume", "work experience", "education", "technical skills", "projects", "certifications"]
    matches = sum(1 for kw in resume_keywords if kw in text_lower)
    if (matches >= 3 and len(pages) <= 3) or "curriculum vitae" in text_lower or (len(pages) <= 2 and "experience" in text_lower and "education" in text_lower):
        return "resume", "portrait", "letterpaper"

    # Report / Thesis / Multi-chapter document check
    if any(k in text_lower for k in ["table of contents", "chapter 1", "chapter 2", "thesis", "technical report", "dissertation", "seminar report"]):
        return "report", "portrait", "a4paper"

    # Research Paper / Academic Article (Default)
    return "article", "portrait", "a4paper"


def parse_pdf(
    pdf_input: Any,
    render_300dpi: bool = True,
    render_150dpi: bool = True,
    max_pages: int = MAX_ALLOWED_PAGES,
    doc_type_override: Optional[str] = None,
) -> PDFParseResult:
    """
    Parses a PDF using PyMuPDF and extracts text, layout, embedded images, and rendered pages.
    Enforces maximum 50 pages.
    """
    pdf_bytes = decode_pdf_input(pdf_input)
    if not pdf_bytes.startswith(b"%PDF"):
        # Try finding %PDF- header
        idx = pdf_bytes.find(b"%PDF-")
        if idx != -1:
            pdf_bytes = pdf_bytes[idx:]
        else:
            raise ValueError("Input data is not a valid PDF document (missing %PDF header).")

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)

    if total_pages > max_pages:
        raise ValueError(
            f"PDF exceeds the maximum {max_pages}-page limit ({total_pages} pages detected). "
            f"Please upload a document with {max_pages} or fewer pages."
        )

    if total_pages == 0:
        raise ValueError("The provided PDF document has 0 pages.")

    pages_data: List[PageData] = []
    extracted_images: List[ExtractedImage] = []
    seen_image_hashes = set()
    full_text_parts = []

    # 300 DPI zoom matrix (300 / 72 ≈ 4.1666667)
    mat_300 = fitz.Matrix(300 / 72, 300 / 72)
    # 150 DPI zoom matrix for LLM multimodal vision
    mat_150 = fitz.Matrix(150 / 72, 150 / 72)

    for page_idx in range(total_pages):
        page_num = page_idx + 1
        page = doc[page_idx]
        rect = page.rect
        width, height = rect.width, rect.height
        aspect_ratio = width / height if height > 0 else 1.0

        # 1. Text extraction
        page_text = page.get_text("text") or ""
        full_text_parts.append(f"--- PAGE {page_num} ---\n{page_text}")

        # Block-level extraction with bounding boxes
        blocks = []
        try:
            raw_blocks = page.get_text("blocks")
            for b in raw_blocks:
                # b format: (x0, y0, x1, y1, text, block_no, block_type)
                if len(b) >= 5 and b[4].strip():
                    blocks.append({
                        "bbox": (b[0], b[1], b[2], b[3]),
                        "text": b[4].strip(),
                        "type": b[6] if len(b) > 6 else 0,
                    })
        except Exception as b_err:
            logger.warning(f"Block extraction warning on page {page_num}: {b_err}")

        # 2. Rendered page images
        rendered_300 = None
        if render_300dpi:
            try:
                pix_300 = page.get_pixmap(matrix=mat_300, alpha=False)
                rendered_300 = pix_300.tobytes("png")
            except Exception as r_err:
                logger.warning(f"Failed to render 300 DPI page {page_num}: {r_err}")

        rendered_150 = None
        if render_150dpi:
            try:
                pix_150 = page.get_pixmap(matrix=mat_150, alpha=False)
                rendered_150 = pix_150.tobytes("png")
            except Exception as r_err:
                logger.warning(f"Failed to render 150 DPI page {page_num}: {r_err}")

        # 3. Embedded images extraction
        try:
            image_list = page.get_images(full=True)
            for img_idx, img_info in enumerate(image_list):
                xref = img_info[0]
                base_image = doc.extract_image(xref)
                if not base_image:
                    continue

                img_bytes = base_image.get("image")
                if not img_bytes:
                    continue

                # Filter out tiny icon/tracking images (< 4KB or < 30x30 px)
                img_w = base_image.get("width", 0)
                img_h = base_image.get("height", 0)
                if len(img_bytes) < 2048 or (img_w > 0 and img_w < 30 and img_h < 30):
                    continue

                # Deduplicate identical images appearing on multiple pages (like headers/footers)
                import hashlib
                img_hash = hashlib.md5(img_bytes).hexdigest()
                if img_hash in seen_image_hashes:
                    continue
                seen_image_hashes.add(img_hash)

                raw_ext = base_image.get("ext", "png").lower()
                ext = "jpg" if raw_ext in ["jpeg", "jpg"] else "png"
                clean_name = f"image_p{page_num}_{img_idx + 1}.{ext}"

                extracted_images.append(ExtractedImage(
                    filename=clean_name,
                    data_bytes=img_bytes,
                    source_page=page_num,
                    width=img_w,
                    height=img_h,
                    ext=ext,
                    mime_type=f"image/{'jpeg' if ext == 'jpg' else 'png'}",
                ))
        except Exception as img_err:
            logger.warning(f"Embedded image extraction error on page {page_num}: {img_err}")

        pages_data.append(PageData(
            page_number=page_num,
            width=width,
            height=height,
            aspect_ratio=aspect_ratio,
            text=page_text,
            blocks=blocks,
            rendered_300dpi_png=rendered_300,
            rendered_150dpi_png=rendered_150,
        ))

    doc.close()

    full_text = "\n\n".join(full_text_parts)
    doc_type, aspect_ratio_hint, page_size_hint = infer_doc_type(
        pages_data, full_text, doc_type_override=doc_type_override
    )

    return PDFParseResult(
        num_pages=total_pages,
        pages=pages_data,
        embedded_images=extracted_images,
        doc_type_hint=doc_type,
        aspect_ratio_hint=aspect_ratio_hint,
        full_text=full_text,
        page_size_hint=page_size_hint,
    )
