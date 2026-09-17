"""
pdf_parser.py — PyMuPDF-based PDF extraction service with layout-aware block extraction

Extracts rich structural content from PDF documents:
- Layout-aware block extraction using PyMuPDF dict mode with bounding boxes and font metadata
- Block classification: heading, paragraph, figure, table, equation, caption, footnote, reference_entry
- Two-column reading order detection and re-sequencing (for academic papers)
- Math block detection for equation OCR
- Color palette, typography, and geometry blueprint
- High-resolution page image rendering (300 DPI and 150 DPI)
"""

import io
import re
import base64
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

import pymupdf as fitz

logger = logging.getLogger("pdf_parser")

MAX_ALLOWED_PAGES = 50


class BlockType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    FIGURE = "figure"
    TABLE = "table"
    EQUATION = "equation"
    CAPTION = "caption"
    FOOTNOTE = "footnote"
    REFERENCE_ENTRY = "reference_entry"


@dataclass
class ExtractedBlock:
    block_type: BlockType
    text: str
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1)
    font_size: float = 10.0
    is_bold: bool = False
    is_italic: bool = False
    font_color: str = "#000000"  # Dominant non-black hex color of this block's text
    alignment: str = "left"  # "center", "left", "right", "justified"
    column_index: int = 0  # 0=full-width/left, 1=right
    reading_order: int = 0
    confidence: float = 1.0


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
class ColorPalette:
    primary_hex: str = "#003366"      # Dominant header / brand color
    secondary_hex: str = "#4A5568"    # Subheader / caption color
    accent_hex: str = "#2563EB"       # Links / highlights / badge color
    background_hex: str = "#FFFFFF"   # Slide or page background
    is_dark_theme: bool = False


@dataclass
class TypographyInfo:
    body_font_family: str = "helvet"
    is_serif: bool = False
    title_font: str = "Helvetica-Bold"
    body_font_size: float = 11.0
    title_font_size: float = 18.0
    font_package: str = "\\usepackage{helvet}\\renewcommand{\\familydefault}{\\sfdefault}"


@dataclass
class LayoutInfo:
    margin_left_pt: float = 72.0
    margin_right_pt: float = 72.0
    margin_top_pt: float = 72.0
    margin_bottom_pt: float = 72.0
    columns: int = 1
    is_two_column: bool = False


@dataclass
class PageData:
    page_number: int  # 1-indexed
    width: float  # points
    height: float  # points
    aspect_ratio: float  # width / height
    text: str
    blocks: List[Dict[str, Any]]
    structured_blocks: List[ExtractedBlock] = field(default_factory=list)
    rendered_300dpi_png: Optional[bytes] = None
    rendered_150dpi_png: Optional[bytes] = None
    layout: Optional[Dict[str, Any]] = None


@dataclass
class PDFParseResult:
    num_pages: int
    pages: List[PageData]
    embedded_images: List[ExtractedImage]
    doc_type_hint: str  # "beamer", "resume", "article", "report"
    aspect_ratio_hint: str  # "169", "43", "portrait"
    full_text: str
    page_size_hint: str  # "letter", "a4", "custom"
    color_palette: ColorPalette = field(default_factory=ColorPalette)
    typography: TypographyInfo = field(default_factory=TypographyInfo)
    layout: LayoutInfo = field(default_factory=LayoutInfo)
    layout_data: Optional[Dict[str, Any]] = None


def decode_pdf_input(pdf_input: Any) -> bytes:
    """Decodes PDF input from raw bytes, file path, base64 data URL, or plain base64 string."""
    if isinstance(pdf_input, bytes):
        return pdf_input
    if isinstance(pdf_input, Path):
        return pdf_input.read_bytes()
    if isinstance(pdf_input, str):
        if len(pdf_input) < 1024 and "\n" not in pdf_input:
            try:
                p = Path(pdf_input)
                if p.is_file():
                    return p.read_bytes()
            except Exception:
                pass

        cleaned = pdf_input.strip()
        if cleaned.startswith("data:application/pdf;base64,"):
            cleaned = cleaned.split("data:application/pdf;base64,", 1)[1].strip()
        elif "," in cleaned and ("base64" in cleaned[:60]):
            cleaned = cleaned.split(",", 1)[1].strip()
        elif cleaned.startswith("%PDF-"):
            return cleaned.encode("latin-1", errors="ignore")

        cleaned_b64 = re.sub(r"\s+", "", cleaned)
        if re.match(r"^[A-Za-z0-9+/=]+$", cleaned_b64):
            padding = len(cleaned_b64) % 4
            if padding:
                cleaned_b64 += "=" * (4 - padding)
            try:
                decoded = base64.b64decode(cleaned_b64)
                if decoded.startswith(b"%PDF-") or b"%PDF-" in decoded[:1024] or len(decoded) > 50:
                    return decoded
            except Exception:
                pass

        raise ValueError("Invalid PDF input: string does not contain valid PDF binary data or base64 stream.")
    raise ValueError("Invalid PDF input: expected bytes, file path, or base64 string")


def classify_raw_block(
    text: str,
    bbox: Tuple[float, float, float, float],
    font_size: float,
    is_bold: bool,
    body_font_size: float = 10.0,
) -> BlockType:
    """Classifies an extracted text block into a structural BlockType."""
    t_clean = text.strip()
    t_lower = t_clean.lower()

    # 1. Caption Check
    if re.match(r"^(?:figure|fig\.?|table|tab\.?|scheme|chart)\s*\d+", t_lower):
        return BlockType.CAPTION

    # 2. Footnote Check (starts with small digit/symbol at bottom)
    if re.match(r"^\d{1,2}\s+[A-Z]", t_clean) and bbox[1] > 650:
        return BlockType.FOOTNOTE

    # 3. Reference Entry Check (e.g. [1] Author, Title)
    if re.match(r"^\[\d+\]\s+[A-Z]", t_clean) or re.match(r"^\d+\.\s+[A-Z][a-z]+,", t_clean):
        return BlockType.REFERENCE_ENTRY

    # 4. Heading Check (significantly larger font or bold short title)
    if font_size >= body_font_size * 1.25 or (is_bold and len(t_clean.split()) <= 10 and not t_clean.endswith(".")):
        if not re.search(r"=\s*[0-9a-zA-Z]", t_clean):  # avoid equation definitions
            return BlockType.HEADING

    # 5. Equation Check (contains math symbols, integral, sum, fractions, equals)
    math_indicators = ["\\int", "\\sum", "\\frac", "∑", "∫", "∂", "√", "±", "≤", "≥", "≠", "∈", "∀", "∃", "λ", "μ", "σ", "θ", "π", "α", "β"]
    has_math_symbols = any(sym in t_clean for sym in math_indicators)
    has_equation_format = bool(re.search(r"\b[a-zA-Z]\s*=\s*[^,\n]+", t_clean)) and len(t_clean.split()) <= 15

    if (has_math_symbols or has_equation_format) and len(t_clean.split()) < 25:
        return BlockType.EQUATION

    # 6. Table / Data row check (many aligned numbers/tabs/pipes)
    if "\t" in t_clean or (t_clean.count(" ") >= 4 and len(re.findall(r"\b\d+(?:\.\d+)?\b", t_clean)) >= 4):
        return BlockType.TABLE

    return BlockType.PARAGRAPH


def extract_page_blocks_and_reading_order(
    page: fitz.Page,
    body_font_size: float = 10.0,
    is_two_column: bool = False,
) -> List[ExtractedBlock]:
    """
    Extracts structural blocks with bounding boxes and sequences them in correct
    reading order (supporting two-column layout ordering).
    """
    raw_dict = page.get_text("dict")
    page_w = page.rect.width
    mid_x = page_w * 0.50

    def _rgb_to_hex(color_int: int) -> str:
        r = (color_int >> 16) & 0xFF
        g = (color_int >> 8) & 0xFF
        b_val = color_int & 0xFF
        return f"#{r:02X}{g:02X}{b_val:02X}"

    def _is_near_black(color_int: int) -> bool:
        r = (color_int >> 16) & 0xFF
        g = (color_int >> 8) & 0xFF
        b_val = color_int & 0xFF
        return (r + g + b_val) < 80

    blocks_raw = []
    for b in raw_dict.get("blocks", []):
        if b.get("type") == 0:  # Text block
            full_text = []
            font_sizes = []
            is_bold = False
            is_italic = False
            span_colors: List[Tuple[int, int]] = []  # (color_int, char_count)

            for line in b.get("lines", []):
                line_spans = []
                for s in line.get("spans", []):
                    span_text = s.get("text", "")
                    if span_text:
                        line_spans.append(span_text)
                        font_sizes.append(s.get("size", 10.0))
                        flags = s.get("flags", 0)
                        if flags & 16 or "bold" in s.get("font", "").lower():
                            is_bold = True
                        if flags & 2 or "italic" in s.get("font", "").lower() or "oblique" in s.get("font", "").lower():
                            is_italic = True
                        color_int = s.get("color", 0)
                        span_colors.append((color_int, len(span_text)))
                full_text.append(" ".join(line_spans))

            combined_text = "\n".join(full_text).strip()
            if not combined_text:
                continue

            avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 10.0

            # Guard bbox access — skip block if bbox is missing or malformed
            raw_bbox = b.get("bbox")
            if not raw_bbox or not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) < 4:
                logger.warning(f"Skipping text block with missing/malformed bbox on page")
                continue
            try:
                bbox = (float(raw_bbox[0]), float(raw_bbox[1]), float(raw_bbox[2]), float(raw_bbox[3]))
            except (TypeError, ValueError, IndexError):
                logger.warning(f"Skipping text block with invalid bbox values")
                continue

            # Determine dominant non-black color for this block
            non_black_colors = [(c, n) for c, n in span_colors if not _is_near_black(c)]
            if non_black_colors:
                # Pick the color with most character coverage
                dominant_color_int = max(non_black_colors, key=lambda x: x[1])[0]
                font_color = _rgb_to_hex(dominant_color_int)
            else:
                font_color = "#000000"

            col_idx = 0
            if is_two_column:
                if bbox[0] >= mid_x - 10:
                    col_idx = 1
                elif bbox[2] <= mid_x + 10:
                    col_idx = 0
                else:
                    col_idx = -1  # Spans both columns (e.g. Title, abstract, wide figure)

            # Compute block alignment based on geometry and margins
            pw = page.rect.width
            bx0, by0, bx1, by1 = bbox
            bw = bx1 - bx0
            b_mid_x = (bx0 + bx1) / 2.0
            p_mid_x = pw / 2.0

            if abs(b_mid_x - p_mid_x) <= 24.0 and bw < pw * 0.82:
                alignment = "center"
            elif is_two_column and col_idx == 0 and abs(b_mid_x - (pw * 0.25)) <= 18.0 and bw < pw * 0.40:
                alignment = "center"
            elif is_two_column and col_idx == 1 and abs(b_mid_x - (pw * 0.75)) <= 18.0 and bw < pw * 0.40:
                alignment = "center"
            elif bx0 > pw * 0.48 and bx1 >= pw - 72.0:
                alignment = "right"
            elif bw >= (pw * 0.60 if not is_two_column else pw * 0.34):
                alignment = "justified"
            else:
                alignment = "left"

            b_type = classify_raw_block(
                text=combined_text,
                bbox=bbox,
                font_size=avg_font_size,
                is_bold=is_bold,
                body_font_size=body_font_size,
            )

            blocks_raw.append({
                "block_type": b_type,
                "text": combined_text,
                "bbox": bbox,
                "font_size": avg_font_size,
                "is_bold": is_bold,
                "is_italic": is_italic,
                "font_color": font_color,
                "alignment": alignment,
                "column_index": col_idx,
            })

    # Sort blocks in reading order:
    # 1. Full-width top blocks (col_idx == -1) sorted by y0
    # 2. Left column blocks (col_idx == 0) sorted by y0
    # 3. Right column blocks (col_idx == 1) sorted by y0
    if is_two_column:
        span_top = [b for b in blocks_raw if b["column_index"] == -1 and b["bbox"][1] < 300]
        left_col = [b for b in blocks_raw if b["column_index"] == 0]
        right_col = [b for b in blocks_raw if b["column_index"] == 1]
        span_bottom = [b for b in blocks_raw if b["column_index"] == -1 and b["bbox"][1] >= 300]

        span_top.sort(key=lambda b: b["bbox"][1])
        left_col.sort(key=lambda b: b["bbox"][1])
        right_col.sort(key=lambda b: b["bbox"][1])
        span_bottom.sort(key=lambda b: b["bbox"][1])

        ordered = span_top + left_col + right_col + span_bottom
    else:
        ordered = sorted(blocks_raw, key=lambda b: b["bbox"][1])

    result_blocks = []
    for order_idx, b in enumerate(ordered, 1):
        result_blocks.append(ExtractedBlock(
            block_type=b["block_type"],
            text=b["text"],
            bbox=b["bbox"],
            font_size=b["font_size"],
            is_bold=b["is_bold"],
            is_italic=b["is_italic"],
            font_color=b.get("font_color", "#000000"),
            alignment=b.get("alignment", "left"),
            column_index=b["column_index"],
            reading_order=order_idx,
        ))

    return result_blocks


def infer_doc_type(
    pages: List[PageData],
    full_text: str,
    doc_type_override: Optional[str] = None,
) -> Tuple[str, str, str]:
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

    if ar >= 1.25:
        aspect_ratio_hint = "169" if ar >= 1.50 else "43"
        return "beamer", aspect_ratio_hint, "custom"

    resume_keywords = ["curriculum vitae", "resume", "work experience", "education", "technical skills", "projects", "certifications"]
    matches = sum(1 for kw in resume_keywords if kw in text_lower)
    if (matches >= 3 and len(pages) <= 3) or "curriculum vitae" in text_lower or (len(pages) <= 2 and "experience" in text_lower and "education" in text_lower):
        return "resume", "portrait", "letterpaper"

    if any(k in text_lower for k in ["table of contents", "chapter 1", "chapter 2", "thesis", "technical report", "dissertation", "seminar report"]):
        return "report", "portrait", "a4paper"

    return "article", "portrait", "a4paper"


def extract_visual_style_and_layout(
    doc: fitz.Document,
    pages_data: List[PageData],
) -> Tuple[ColorPalette, TypographyInfo, LayoutInfo]:
    import collections

    header_colors: collections.Counter = collections.Counter()
    body_colors: collections.Counter = collections.Counter()
    font_counts: collections.Counter = collections.Counter()
    font_sizes: List[float] = []
    header_sizes: List[float] = []

    def rgb_to_hex(r: int, g: int, b: int) -> str:
        return f"#{max(0, min(255, r)):02X}{max(0, min(255, g)):02X}{max(0, min(255, b)):02X}"

    def is_neutral_color(r: int, g: int, b: int) -> bool:
        max_c = max(r, g, b)
        min_c = min(r, g, b)
        spread = max_c - min_c
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        if luminance < 35 or luminance > 240:
            return True
        if spread < 18:
            return True
        return False

    for page_idx in range(min(len(doc), 15)):
        page = doc[page_idx]
        try:
            p_dict = page.get_text("dict")
            for block in p_dict.get("blocks", []):
                if block.get("type") == 0:
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            txt = span.get("text", "").strip()
                            if not txt:
                                continue
                            font = span.get("font", "")
                            size = span.get("size", 10.0)
                            color_int = span.get("color", 0)
                            flags = span.get("flags", 0)
                            font_counts[font] += len(txt)
                            font_sizes.append(size)

                            r = (color_int >> 16) & 0xFF
                            g = (color_int >> 8) & 0xFF
                            b = color_int & 0xFF

                            if not is_neutral_color(r, g, b):
                                hx = rgb_to_hex(r, g, b)
                                if size >= 13.0 or (flags & 16):
                                    header_colors[hx] += len(txt)
                                    header_sizes.append(size)
                                else:
                                    body_colors[hx] += len(txt)
        except Exception as e:
            logger.warning(f"Text dict extraction warning on page {page_idx + 1}: {e}")

    top_headers = [c for c, _ in header_colors.most_common(5)]
    top_body = [c for c, _ in body_colors.most_common(5)]

    primary = top_headers[0] if top_headers else (top_body[0] if top_body else "#003366")
    secondary = top_headers[1] if len(top_headers) > 1 else (top_body[0] if top_body and top_body[0] != primary else "#4A5568")
    accent = top_headers[2] if len(top_headers) > 2 else "#2563EB"

    palette = ColorPalette(
        primary_hex=primary,
        secondary_hex=secondary,
        accent_hex=accent,
        background_hex="#FFFFFF",
        is_dark_theme=False,
    )

    serif_chars = sum(cnt for f, cnt in font_counts.items() if any(k in f.lower() for k in ["times", "roman", "serif", "cmr", "georgia", "minion", "cambria", "palatino"]))
    sans_chars = sum(cnt for f, cnt in font_counts.items() if any(k in f.lower() for k in ["helv", "arial", "calibri", "sans", "roboto", "inter"]))
    is_serif = serif_chars > sans_chars

    dominant_font = font_counts.most_common(1)[0][0] if font_counts else ("Times" if is_serif else "Helvetica")
    font_lower = dominant_font.lower()

    if is_serif:
        font_pkg = "\\usepackage{newtxtext,newtxmath}"
        body_family = "newtxtext"
    elif "roboto" in font_lower:
        font_pkg = "\\usepackage[sfdefault]{roboto}"
        body_family = "roboto"
    else:
        font_pkg = "\\usepackage{helvet}\\renewcommand{\\familydefault}{\\sfdefault}"
        body_family = "helvet"

    avg_body_size = sum(font_sizes) / len(font_sizes) if font_sizes else 11.0
    avg_head_size = sum(header_sizes) / len(header_sizes) if header_sizes else 16.0

    typography = TypographyInfo(
        body_font_family=body_family,
        is_serif=is_serif,
        title_font=dominant_font,
        body_font_size=round(avg_body_size, 1),
        title_font_size=round(avg_head_size, 1),
        font_package=font_pkg,
    )

    two_column_votes = 0
    total_checked_pages = 0
    margin_lefts = []
    margin_rights = []
    margin_tops = []
    margin_bottoms = []

    for p in pages_data[:8]:
        if p.aspect_ratio >= 1.15:
            continue
        total_checked_pages += 1
        w, h = p.width, p.height
        if not p.blocks:
            continue

        left_blocks = 0
        right_blocks = 0
        mid_crossing = 0

        for b in p.blocks:
            bbox = b.get("bbox")
            if not bbox:
                continue
            x0, y0, x1, y1 = bbox
            margin_lefts.append(x0)
            margin_rights.append(w - x1)
            margin_tops.append(y0)
            margin_bottoms.append(h - y1)

            if x1 <= w * 0.52:
                left_blocks += 1
            elif x0 >= w * 0.48:
                right_blocks += 1
            else:
                mid_crossing += 1

        if left_blocks >= 2 and right_blocks >= 2 and (left_blocks + right_blocks) >= (mid_crossing - 1):
            two_column_votes += 1

    is_two_col = (two_column_votes >= 2) or (total_checked_pages == 1 and two_column_votes == 1)

    m_left = round(max(36.0, min(90.0, sum(margin_lefts) / len(margin_lefts))), 1) if margin_lefts else 72.0
    m_right = round(max(36.0, min(90.0, sum(margin_rights) / len(margin_rights))), 1) if margin_rights else 72.0
    m_top = round(max(36.0, min(90.0, sum(margin_tops) / len(margin_tops))), 1) if margin_tops else 72.0
    m_bottom = round(max(36.0, min(90.0, sum(margin_bottoms) / len(margin_bottoms))), 1) if margin_bottoms else 72.0

    layout = LayoutInfo(
        margin_left_pt=m_left,
        margin_right_pt=m_right,
        margin_top_pt=m_top,
        margin_bottom_pt=m_bottom,
        columns=2 if is_two_col else 1,
        is_two_column=is_two_col,
    )

    return palette, typography, layout


def parse_pdf(
    pdf_input: Any,
    render_300dpi: bool = True,
    render_150dpi: bool = True,
    max_pages: int = MAX_ALLOWED_PAGES,
    doc_type_override: Optional[str] = None,
) -> PDFParseResult:
    """
    Parses a PDF using PyMuPDF and extracts structured blocks, layout, embedded images,
    rendered page images, color palette, typography, and geometry.
    """
    pdf_bytes = decode_pdf_input(pdf_input)
    if not pdf_bytes.startswith(b"%PDF"):
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
    seen_image_hashes: set = set()
    full_text_parts: List[str] = []

    mat_300 = fitz.Matrix(300 / 72, 300 / 72)
    mat_150 = fitz.Matrix(150 / 72, 150 / 72)

    for page_idx in range(total_pages):
        page_num = page_idx + 1
        page = doc[page_idx]
        rect = page.rect
        width, height = rect.width, rect.height
        aspect_ratio = width / height if height > 0 else 1.0

        page_text = page.get_text("text") or ""
        full_text_parts.append(f"--- PAGE {page_num} ---\n{page_text}")

        blocks = []
        try:
            raw_blocks = page.get_text("blocks")
            for b in raw_blocks:
                if len(b) >= 5 and b[4].strip():
                    blocks.append({
                        "bbox": (b[0], b[1], b[2], b[3]),
                        "text": b[4].strip(),
                        "type": b[6] if len(b) > 6 else 0,
                    })
        except Exception as b_err:
            logger.warning(f"Block extraction warning on page {page_num}: {b_err}")

        # Extract structured blocks with reading order
        structured_blocks = extract_page_blocks_and_reading_order(
            page,
            body_font_size=11.0,
            is_two_column=False,
        )

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

                img_w = base_image.get("width", 0)
                img_h = base_image.get("height", 0)

                if (img_w > 0 and img_w < 50) or (img_h > 0 and img_h < 50) or (img_w * img_h < 3000):
                    continue

                aspect = img_w / max(1, img_h)
                if aspect > 12.0 or aspect < (1.0 / 12.0):
                    continue

                import hashlib
                img_hash = hashlib.sha256(img_bytes).hexdigest()
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
            structured_blocks=structured_blocks,
            rendered_300dpi_png=rendered_300,
            rendered_150dpi_png=rendered_150,
        ))

    color_palette, typography, layout = extract_visual_style_and_layout(doc, pages_data)
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
        color_palette=color_palette,
        typography=typography,
        layout=layout,
    )
