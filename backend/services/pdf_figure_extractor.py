"""
pdf_figure_extractor.py — High-Resolution AI PDF Figure Extraction Service

Extracts specific figures from PDF documents at 300 DPI:
1. Detects figure captions (e.g. "Figure 1: System Architecture", "Fig. 2 - Pipeline")
2. Correlates captions with embedded images and vector graphics
3. Renders the exact figure region at 300 DPI (supporting both raster and vector/TikZ diagrams)
4. Auto-trims whitespace margins around the figure
5. Generates slugified filenames, LaTeX labels, and clean LaTeX figure environments
"""

import io
import re
import math
import base64
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageChops

logger = logging.getLogger("pdf_figure_extractor")

DPI_300_MATRIX = fitz.Matrix(300.0 / 72.0, 300.0 / 72.0)

CAPTION_PATTERNS = [
    # "Figure 1: System Architecture" / "Fig. 2 - Overview"
    re.compile(r"^\s*(?:figure|fig\.?)\s*(\d+[a-z]?|[a-z])\s*[:.\-—]\s*(.*)$", re.IGNORECASE | re.DOTALL),
    # "Figure 1. System Architecture"
    re.compile(r"^\s*(?:figure|fig\.?)\s*(\d+[a-z]?|[a-z])\s+(.+)$", re.IGNORECASE | re.DOTALL),
    # "Scheme 1: Synthesis" / "Diagram 1: Flow"
    re.compile(r"^\s*(?:scheme|diagram|chart)\s*(\d+[a-z]?|[a-z])\s*[:.\-—]\s*(.*)$", re.IGNORECASE | re.DOTALL),
]


@dataclass
class FigureCandidate:
    page_num: int  # 1-indexed
    figure_number: Optional[str]
    caption_text: str
    clean_title: str
    graphic_rect: fitz.Rect
    caption_rect: fitz.Rect
    score: float = 0.0
    is_vector: bool = False
    source_image_xref: Optional[int] = None


@dataclass
class ExtractedFigure:
    clean_filename: str
    asset_rel_path: str
    image_bytes: bytes
    width: int
    height: int
    caption: str
    label: str
    page_number: int
    latex_snippet: str
    document_class: str = "article"
    dimension_valid: bool = True
    dimension_warning: str = ""


def validate_figure_dimensions(
    extracted_w: int,
    extracted_h: int,
    bbox: fitz.Rect,
    dpi_scale: float = 300.0 / 72.0,
) -> Tuple[bool, str]:
    """Validates extracted image dimensions against original bounding box in PDF points."""
    expected_w = bbox.width * dpi_scale
    expected_h = bbox.height * dpi_scale

    if extracted_w < 50 or extracted_h < 50:
        return False, f"Extracted figure dimensions ({extracted_w}x{extracted_h}) too small"

    ratio_w = extracted_w / max(1.0, expected_w)
    ratio_h = extracted_h / max(1.0, expected_h)

    # If cropped dimension deviates by more than 3x from bbox, flag warning
    if ratio_w < 0.25 or ratio_w > 3.5 or ratio_h < 0.25 or ratio_h > 3.5:
        return False, f"Extracted dimensions ({extracted_w}x{extracted_h}) deviate from bbox ({int(expected_w)}x{int(expected_h)})"

    return True, ""


def slugify_name(text: str) -> str:
    """Converts a title or caption into a safe, clean snake_case filename."""
    if not text:
        return "extracted_figure"
    # Remove figure prefix like "Figure 1:" or "Fig. 2 -"
    s = re.sub(r"^(?:figure|fig\.?|scheme|diagram)\s*\d+[a-z]?\s*[:.\-—]?\s*", "", text, flags=re.IGNORECASE)
    s = s.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s-]+", "_", s).strip("_")
    # Truncate if excessively long
    if len(s) > 40:
        s = s[:40].rstrip("_")
    return s if s else "extracted_figure"


def safe_latex_escape(text: str) -> str:
    """Escapes special LaTeX characters for titles and captions."""
    if not text:
        return ""
    t = text
    t = re.sub(r"(?<!\\)&", r"\&", t)
    t = re.sub(r"(?<!\\)%", r"\%", t)
    t = re.sub(r"(?<!\\)\$", r"\$", t)
    t = re.sub(r"(?<!\\)#", r"\#", t)
    t = re.sub(r"(?<!\\)_", r"\_", t)
    return t


def decode_pdf_bytes(pdf_input: Any) -> bytes:
    """Decodes PDF input from raw bytes, file path, base64 data URL, or base64 string."""
    if isinstance(pdf_input, bytes):
        return pdf_input
    if isinstance(pdf_input, Path):
        return pdf_input.read_bytes()
    if isinstance(pdf_input, str):
        # 1. Check if string is a path to an existing PDF file
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

        # Strip all whitespace from base64 candidate
        cleaned_b64 = re.sub(r"\s+", "", cleaned)
        # Ensure it contains ONLY valid base64 ASCII characters
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


def trim_whitespace(img: Image.Image, padding: int = 28) -> Image.Image:
    """Trims solid white or near-white borders around a rendered figure with generous padding."""
    try:
        if img.mode != "RGB":
            img = img.convert("RGB")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        diff = ImageChops.difference(img, bg)
        # Bounding box of non-white pixels
        bbox = diff.getbbox()
        if bbox:
            orig_w, orig_h = img.size
            crop_w = bbox[2] - bbox[0]
            crop_h = bbox[3] - bbox[1]

            # Guard against over-trimming / collapse into tiny speck:
            # If cropped box is tiny (< 120px) but original is substantial (> 300px),
            # add generous margin so faint diagrams / axis labels are never sliced off.
            if (crop_w < 120 or crop_h < 80) and (orig_w > 300 or orig_h > 200):
                padding = max(padding, 40)

            x0 = max(0, bbox[0] - padding)
            y0 = max(0, bbox[1] - padding)
            x1 = min(orig_w, bbox[2] + padding)
            y1 = min(orig_h, bbox[3] + padding)
            return img.crop((x0, y0, x1, y1))
    except Exception as e:
        logger.warning(f"Error trimming figure whitespace: {e}")
    return img


def find_caption_candidates(page: fitz.Page) -> List[Tuple[fitz.Rect, Optional[str], str]]:
    """
    Extracts candidate caption blocks from a page.
    Returns: List of (caption_rect, figure_number, caption_text)
    """
    captions = []
    blocks = page.get_text("blocks")
    if not blocks:
        return captions
    for b in blocks:
        # b: (x0, y0, x1, y1, text, block_no, block_type)
        if len(b) < 7 or b[6] != 0:  # b[6] == 0 means text; require len >= 7 to avoid IndexError
            continue
        if len(b) < 5:
            continue
        text = b[4].strip() if b[4] else ""
        if not text:
            continue

        for pat in CAPTION_PATTERNS:
            m = pat.match(text)
            if m:
                fig_num = m.group(1).strip()
                cap_body = m.group(2).strip() if len(m.groups()) >= 2 else text
                captions.append((fitz.Rect(b[0], b[1], b[2], b[3]), fig_num, text))
                break
    return captions


def locate_figure_graphic_region(
    page: fitz.Page,
    caption_rect: fitz.Rect,
    doc: fitz.Document,
) -> Tuple[fitz.Rect, bool, Optional[int]]:
    """
    Determines the bounding box of the graphic associated with a caption.
    Searches for:
    1. Embedded raster image rects situated above (or occasionally below) the caption.
    2. Vector drawing elements clustering above the caption.
    3. Layout heuristic fallback (column width between preceding text block and caption).
    Returns: (graphic_rect, is_vector, source_image_xref)
    """
    page_rect = page.rect
    cap_y0 = caption_rect.y0
    cap_y1 = caption_rect.y1
    cap_cx = (caption_rect.x0 + caption_rect.x1) / 2.0

    # 1. Check embedded image placements
    best_img_rect = None
    best_img_xref = None
    min_dist = float("inf")

    try:
        images = page.get_images(full=True)
        if not images:
            images = []
        for img_info in images:
            xref = img_info[0]
            try:
                img_rects = page.get_image_rects(xref)
            except Exception:
                img_rects = []
            if not img_rects:
                continue
            for r in img_rects:
                if r is None or r.width < 1 or r.height < 1:
                    continue
                # Check if image sits above caption
                if r.y1 <= cap_y1 + 10 and r.y1 >= cap_y0 - 500:
                    dist = abs(cap_y0 - r.y1)
                    # Check horizontal overlap
                    overlap = max(0, min(caption_rect.x1, r.x1) - max(caption_rect.x0, r.x0))
                    if (overlap > 10 or abs(r.x0 - caption_rect.x0) < 100) and dist < min_dist:
                        min_dist = dist
                        best_img_rect = r
                        best_img_xref = xref
                # Alternatively sits below caption
                elif r.y0 >= cap_y0 - 10 and r.y0 <= cap_y1 + 400:
                    dist = abs(r.y0 - cap_y1)
                    overlap = max(0, min(caption_rect.x1, r.x1) - max(caption_rect.x0, r.x0))
                    if (overlap > 10 or abs(r.x0 - caption_rect.x0) < 100) and dist < min_dist:
                        min_dist = dist
                        best_img_rect = r
                        best_img_xref = xref
    except Exception as img_err:
        logger.warning(f"Error inspecting page images: {img_err}")

    if best_img_rect is not None and best_img_rect.width >= 65 and best_img_rect.height >= 45 and (best_img_rect.width * best_img_rect.height >= 4500):
        # Add 8pt safety padding so graphic labels/borders aren't cut
        pad_rect = fitz.Rect(
            max(0, best_img_rect.x0 - 8),
            max(0, best_img_rect.y0 - 8),
            min(page_rect.width, best_img_rect.x1 + 8),
            min(page_rect.height, best_img_rect.y1 + 8),
        )
        return pad_rect, False, best_img_xref

    # 2. Check vector drawings (TikZ, matplotlib vector lines, flowcharts)
    drawings = []
    try:
        drawings = page.get_drawings()
    except Exception:
        pass

    vector_rects = []
    for d in drawings:
        r = d.get("rect")
        if r and r.width > 5 and r.height > 5:
            # Check if within region above caption
            if r.y1 <= cap_y0 + 15 and r.y0 >= max(0, cap_y0 - 450):
                vector_rects.append(r)

    if vector_rects:
        # Union of all nearby vector rects
        vx0 = min(r.x0 for r in vector_rects)
        vy0 = min(r.y0 for r in vector_rects)
        vx1 = max(r.x1 for r in vector_rects)
        vy1 = max(r.y1 for r in vector_rects)
        union_rect = fitz.Rect(
            max(0, vx0 - 8),
            max(0, vy0 - 8),
            min(page_rect.width, vx1 + 8),
            min(page_rect.height, vy1 + 8),
        )
        if union_rect.width >= 70 and union_rect.height >= 50 and (union_rect.width * union_rect.height >= 5500):
            return union_rect, True, None

    # 3. Layout heuristic fallback:
    # Find closest text block above the caption
    blocks = page.get_text("blocks")
    top_limit = max(0, cap_y0 - 280)
    for b in blocks:
        by1 = b[3]
        if by1 < cap_y0 and by1 > top_limit:
            if (cap_y0 - by1) >= 60:
                top_limit = by1 + 5

    fallback_rect = fitz.Rect(
        max(36, caption_rect.x0 - 20),
        top_limit,
        min(page_rect.width - 36, max(caption_rect.x1 + 20, caption_rect.x0 + 250)),
        cap_y0 - 2,
    )
    if fallback_rect.height < 60:
        fallback_rect = fitz.Rect(
            max(36, caption_rect.x0 - 15),
            max(0, cap_y0 - 180),
            min(page_rect.width - 36, max(caption_rect.x1 + 15, caption_rect.x0 + 250)),
            cap_y0 - 2,
        )

    return fallback_rect, True, None


def score_candidate(candidate: FigureCandidate, query: str) -> float:
    """Computes a match score between a candidate and user query."""
    if not query:
        return 1.0

    q = query.lower().strip()
    cap = candidate.caption_text.lower()
    score = 0.0

    # 1. Exact figure number matching (e.g. "Figure 2" -> "2")
    fig_num_match = re.search(r"(?:fig(?:ure)?\.?\s*#?\s*(\d+[a-z]?))", q)
    if fig_num_match and candidate.figure_number:
        if fig_num_match.group(1).lower() == candidate.figure_number.lower():
            score += 150.0

    # 2. Substring matching
    clean_q = re.sub(r"\b(?:extract|add|insert|the|from|pdf|figure|fig|image|diagram|chart|after|before)\b", "", q).strip()
    if clean_q and len(clean_q) >= 3:
        if clean_q in cap:
            score += 80.0
        # Partial word matches
        q_words = [w for w in clean_q.split() if len(w) >= 3]
        for w in q_words:
            if w in cap:
                score += 25.0

    # 3. Size bonus (larger figures preferred over tiny fragments)
    area = candidate.graphic_rect.width * candidate.graphic_rect.height
    score += min(15.0, area / 20000.0)

    return score


def extract_all_figure_candidates(doc: fitz.Document) -> List[FigureCandidate]:
    """Scans all pages in a document and builds a list of FigureCandidates."""
    candidates = []
    for page_idx in range(len(doc)):
        page_num = page_idx + 1
        page = doc[page_idx]

        caption_items = find_caption_candidates(page)
        for cap_rect, fig_num, cap_text in caption_items:
            graphic_rect, is_vector, xref = locate_figure_graphic_region(page, cap_rect, doc)
            clean_title = re.sub(r"^\s*(?:figure|fig\.?|scheme|diagram)\s*\d+[a-z]?\s*[:.\-—]?\s*", "", cap_text, flags=re.IGNORECASE).strip()
            if not clean_title:
                clean_title = f"figure_{fig_num}" if fig_num else f"figure_p{page_num}"

            candidates.append(FigureCandidate(
                page_num=page_num,
                figure_number=fig_num,
                caption_text=cap_text,
                clean_title=clean_title,
                graphic_rect=graphic_rect,
                caption_rect=cap_rect,
                is_vector=is_vector,
                source_image_xref=xref,
            ))

    # If no caption items found anywhere, check for standalone embedded images
    if not candidates:
        for page_idx in range(len(doc)):
            page_num = page_idx + 1
            page = doc[page_idx]
            try:
                images = page.get_images(full=True)
                if not images:
                    continue
                for idx, img_info in enumerate(images):
                    xref = img_info[0]
                    try:
                        rects = page.get_image_rects(xref)
                    except Exception:
                        rects = []
                    if not rects:
                        continue
                    for r in rects:
                        if r is None or r.width < 60 or r.height < 60:
                            continue
                        candidates.append(FigureCandidate(
                            page_num=page_num,
                            figure_number=str(idx + 1),
                            caption_text=f"Figure {idx + 1} from page {page_num}",
                            clean_title=f"figure_p{page_num}_{idx + 1}",
                            graphic_rect=r,
                            caption_rect=r,
                            is_vector=False,
                            source_image_xref=xref,
                        ))
            except Exception:
                pass

    return candidates


def extract_figure(
    pdf_input: Any,
    figure_query: str = "",
    document_class: str = "article",
    target_filename: Optional[str] = None,
) -> ExtractedFigure:
    """
    Main extraction function.
    Given a PDF and figure query:
    1. Parses document and identifies figure candidates
    2. Selects the highest-scoring candidate for figure_query
    3. Renders the graphic region at 300 DPI
    4. Trims borders and saves to PNG bytes
    5. Formats clean LaTeX snippet for the target document class
    """
    pdf_bytes = decode_pdf_bytes(pdf_input)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    try:
        candidates = extract_all_figure_candidates(doc)
        if not candidates:
            # Fallback: render top half of page 1 if no graphics at all
            p1 = doc[0]
            rect = fitz.Rect(36, 36, p1.rect.width - 36, p1.rect.height / 2)
            candidates.append(FigureCandidate(
                page_num=1,
                figure_number="1",
                caption_text="Extracted Figure",
                clean_title="extracted_figure",
                graphic_rect=rect,
                caption_rect=rect,
                is_vector=True,
            ))

        # Score and pick candidate
        for c in candidates:
            c.score = score_candidate(c, figure_query)

        candidates.sort(key=lambda c: c.score, reverse=True)
        best = candidates[0]

        # Render 300 DPI pixmap
        page = doc[best.page_num - 1]
        pix = page.get_pixmap(matrix=DPI_300_MATRIX, clip=best.graphic_rect, alpha=False)

        # Open in PIL and trim excessive margins
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        trimmed = trim_whitespace(img)

        # Save to PNG buffer
        buf = io.BytesIO()
        trimmed.save(buf, format="PNG", optimize=True)
        png_bytes = buf.getvalue()

        # Generate slugified names
        slug = target_filename or slugify_name(best.clean_title)
        if not slug.endswith(".png"):
            clean_filename = f"{slug}.png"
        else:
            clean_filename = slug

        asset_rel_path = f"assets/{clean_filename}"
        label_name = f"fig:{slug.replace('.png', '')}"

        # Clean caption text (strip redundant Figure X: prefixes if needed)
        caption_clean = re.sub(r"^\s*(?:figure|fig\.?|scheme|diagram)\s*\d+[a-z]?\s*[:.\-—]?\s*", "", best.caption_text, flags=re.IGNORECASE).strip()
        if not caption_clean:
            caption_clean = best.clean_title.replace("_", " ").title()

        caption_escaped = safe_latex_escape(caption_clean)

        # Build LaTeX snippet
        is_beamer = document_class.lower() == "beamer"
        if is_beamer:
            latex_snippet = (
                f"\\begin{{frame}}{{{caption_escaped}}}\n"
                f"    \\centering\n"
                f"    \\includegraphics[width=0.85\\linewidth,height=0.75\\textheight,keepaspectratio]{{{asset_rel_path}}}\n"
                f"\\end{{frame}}"
            )
        else:
            latex_snippet = (
                f"\\begin{{figure}}[htbp]\n"
                f"    \\centering\n"
                f"    \\includegraphics[width=\\linewidth]{{{asset_rel_path}}}\n"
                f"    \\caption{{{caption_escaped}}}\n"
                f"    \\label{{{label_name}}}\n"
                f"\\end{{figure}}"
            )

        dim_valid, dim_warn = validate_figure_dimensions(trimmed.width, trimmed.height, best.graphic_rect)

        return ExtractedFigure(
            clean_filename=clean_filename,
            asset_rel_path=asset_rel_path,
            image_bytes=png_bytes,
            width=trimmed.width,
            height=trimmed.height,
            caption=caption_clean,
            label=label_name,
            page_number=best.page_num,
            latex_snippet=latex_snippet,
            document_class=document_class,
            dimension_valid=dim_valid,
            dimension_warning=dim_warn,
        )
    finally:
        doc.close()


def extract_multiple_figures(
    pdf_input: Any,
    max_figures: int = 4,
    document_class: str = "beamer",
) -> List[ExtractedFigure]:
    """
    Extracts up to max_figures distinct figures from a PDF.
    Renders each at 300 DPI, crops white borders, and generates
    unique filenames and LaTeX snippets.
    """
    pdf_bytes = decode_pdf_bytes(pdf_input)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    results = []

    try:
        candidates = extract_all_figure_candidates(doc)
        if not candidates:
            return []

        # Deduplicate candidates across pages:
        # 1. By image xref (identical embedded image used on multiple pages, like logos/headers)
        # 2. By position/rect on the same page
        unique_candidates: List[FigureCandidate] = []
        seen_xrefs = set()
        for c in candidates:
            if c.source_image_xref and c.source_image_xref in seen_xrefs:
                continue
            is_dup = False
            for u in unique_candidates:
                if u.page_num == c.page_num:
                    if abs(u.graphic_rect.y0 - c.graphic_rect.y0) < 35 and abs(u.graphic_rect.x0 - c.graphic_rect.x0) < 35:
                        is_dup = True
                        break
            if not is_dup:
                unique_candidates.append(c)
                if c.source_image_xref:
                    seen_xrefs.add(c.source_image_xref)

        chosen = unique_candidates[:max_figures]
        seen_filenames = set()
        seen_image_hashes = set()

        for cand in chosen:
            try:
                page = doc[cand.page_num - 1]
                pix = page.get_pixmap(matrix=DPI_300_MATRIX, clip=cand.graphic_rect, alpha=False)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                trimmed = trim_whitespace(img, padding=28)

                # Filter out crops that are too small (< 140x90 px or area < 16000)
                if trimmed.width < 140 or trimmed.height < 90 or (trimmed.width * trimmed.height < 16000):
                    logger.info(f"Skipping too-small figure crop ({trimmed.width}x{trimmed.height} px) on page {cand.page_num}")
                    continue

                buf = io.BytesIO()
                trimmed.save(buf, format="PNG", optimize=True)
                png_bytes = buf.getvalue()

                # Deduplicate by visual content hash across pages (e.g. repeated logos/diagrams)
                import hashlib
                img_hash = hashlib.sha256(png_bytes).hexdigest()
                if img_hash in seen_image_hashes:
                    logger.info(f"Skipping duplicate figure across pages (hash {img_hash[:8]})")
                    continue
                seen_image_hashes.add(img_hash)

                raw_slug = slugify_name(cand.clean_title)
                slug = raw_slug
                counter = 2
                while slug in seen_filenames:
                    slug = f"{raw_slug}_{counter}"
                    counter += 1
                seen_filenames.add(slug)

                clean_filename = f"{slug}.png"
                asset_rel_path = f"assets/{clean_filename}"
                label_name = f"fig:{slug}"

                caption_clean = re.sub(
                    r"^\s*(?:figure|fig\.?|scheme|diagram)\s*\d+[a-z]?\s*[:.\-—]?\s*",
                    "",
                    cand.caption_text,
                    flags=re.IGNORECASE
                ).strip()
                if "\n" in caption_clean:
                    caption_clean = caption_clean.split("\n")[0].strip()
                if not caption_clean:
                    caption_clean = cand.clean_title.replace("_", " ").title()

                caption_escaped = safe_latex_escape(caption_clean)

                is_beamer = document_class.lower() == "beamer"
                if is_beamer:
                    latex_snippet = (
                        f"\\begin{{frame}}{{{caption_escaped}}}\n"
                        f"    \\centering\n"
                        f"    \\includegraphics[width=0.85\\linewidth,height=0.75\\textheight,keepaspectratio]{{{asset_rel_path}}}\n"
                        f"\\end{{frame}}"
                    )
                else:
                    latex_snippet = (
                        f"\\begin{{figure}}[htbp]\n"
                        f"    \\centering\n"
                        f"    \\includegraphics[width=\\linewidth]{{{asset_rel_path}}}\n"
                        f"    \\caption{{{caption_escaped}}}\n"
                        f"    \\label{{{label_name}}}\n"
                        f"\\end{{figure}}"
                    )

                dim_valid, dim_warn = validate_figure_dimensions(trimmed.width, trimmed.height, cand.graphic_rect)

                results.append(ExtractedFigure(
                    clean_filename=clean_filename,
                    asset_rel_path=asset_rel_path,
                    image_bytes=png_bytes,
                    width=trimmed.width,
                    height=trimmed.height,
                    caption=caption_clean,
                    label=label_name,
                    page_number=cand.page_num,
                    latex_snippet=latex_snippet,
                    document_class=document_class,
                    dimension_valid=dim_valid,
                    dimension_warning=dim_warn,
                ))
            except Exception as e:
                logger.warning(f"Error extracting figure candidate on page {cand.page_num}: {e}")

        return results
    finally:
        doc.close()

