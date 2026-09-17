"""
layout_verifier.py — Layout Verification & Position Drift Calibration

Analyzes positional drift between original PDF pages and newly compiled LaTeX PDF pages.
Calibrates vertical spacing and offsets to match the source document geometry.
"""

import re
import logging
from typing import Dict, Any, Optional, List, Tuple
import pymupdf as fitz

logger = logging.getLogger("layout_verifier")


def _get_block_bbox(b: Any) -> Optional[Tuple[float, float, float, float]]:
    """Safely extract (x0, y0, x1, y1) from a dict, dataclass, or tuple/list block."""
    if b is None:
        return None
    if isinstance(b, dict):
        bbox = b.get("bbox")
        if bbox and isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            try:
                return (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
            except (ValueError, TypeError):
                return None
    elif hasattr(b, "bbox"):
        bbox = getattr(b, "bbox", None)
        if bbox and isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            try:
                return (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
            except (ValueError, TypeError):
                return None
    elif isinstance(b, (list, tuple)) and len(b) >= 4:
        try:
            return (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
        except (ValueError, TypeError):
            return None
    return None


def _get_block_text(b: Any) -> str:
    """Safely extract text content from a dict, dataclass, or tuple/list block."""
    if b is None:
        return ""
    if isinstance(b, dict):
        return str(b.get("text", "") or "").strip()
    elif hasattr(b, "text"):
        return str(getattr(b, "text", "") or "").strip()
    elif isinstance(b, (list, tuple)) and len(b) >= 5:
        return str(b[4] or "").strip()
    return ""


def _get_block_color(b: Any) -> Optional[str]:
    """Safely extract hex color code from a dict or dataclass block."""
    if b is None:
        return None
    if isinstance(b, dict):
        return b.get("font_color")
    elif hasattr(b, "font_color"):
        return getattr(b, "font_color", None)
    return None


def analyze_page_positional_drift(
    page_data: Any,
    pdf_bytes: bytes,
    page_number: int = 1,
) -> Dict[str, Any]:
    """
    Compares the layout of a compiled PDF page against the original page_data.
    Returns:
        drift_info: dict with top_drift, left_drift, height_diff, width_diff,
                    matched_drifts, image_drift, color_fidelity_score, page_missing
    """
    default_empty = {
        "page_missing": True,
        "top_drift": 0.0,
        "left_drift": 0.0,
        "height_diff": 0.0,
        "width_diff": 0.0,
        "matched_drifts": [],
        "image_drift": [],
        "color_fidelity_score": 1.0,
    }

    if not pdf_bytes:
        return default_empty

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        logger.warning(f"Could not open compiled PDF: {e}")
        return default_empty

    if page_number > len(doc) or page_number < 1:
        doc.close()
        return default_empty

    try:
        compiled_page = doc[page_number - 1]
        compiled_blocks = compiled_page.get_text("blocks") or []
        comp_h = compiled_page.rect.height
        comp_w = compiled_page.rect.width

        orig_blocks = getattr(page_data, "blocks", []) or []
        orig_h = getattr(page_data, "height", 792.0) or 792.0
        orig_w = getattr(page_data, "width", 612.0) or 612.0

        if not orig_blocks or not compiled_blocks:
            doc.close()
            return {
                "page_missing": False,
                "top_drift": 0.0,
                "left_drift": 0.0,
                "height_diff": round(comp_h - orig_h, 2),
                "width_diff": round(comp_w - orig_w, 2),
                "matched_drifts": [],
                "image_drift": [],
                "color_fidelity_score": 1.0,
            }

        matched_drifts = []
        orig_first_y0 = None
        orig_first_x0 = None
        for b in orig_blocks:
            bbox = _get_block_bbox(b)
            txt = _get_block_text(b)
            if bbox and txt:
                orig_first_x0 = bbox[0]
                orig_first_y0 = bbox[1]
                break

        compiled_first_y0 = None
        compiled_first_x0 = None
        for b in compiled_blocks:
            if len(b) >= 5 and str(b[4]).strip():
                compiled_first_x0 = float(b[0])
                compiled_first_y0 = float(b[1])
                break

        top_drift = 0.0
        left_drift = 0.0
        if orig_first_y0 is not None and compiled_first_y0 is not None:
            top_drift = compiled_first_y0 - orig_first_y0
            if orig_first_x0 is not None and compiled_first_x0 is not None:
                left_drift = compiled_first_x0 - orig_first_x0
            matched_drifts.append({
                "orig_x": orig_first_x0,
                "orig_y": orig_first_y0,
                "comp_x": compiled_first_x0,
                "comp_y": compiled_first_y0,
                "drift_y": round(top_drift, 2),
                "drift_x": round(left_drift, 2),
            })

        # Match additional text blocks by prefix to detect drift pattern
        for ob in orig_blocks[:8]:
            otxt = _get_block_text(ob)
            obbox = _get_block_bbox(ob)
            if not otxt or not obbox or len(otxt) < 6:
                continue
            prefix = otxt[:15].lower()
            for cb in compiled_blocks[:15]:
                if len(cb) >= 5 and str(cb[4]).strip().lower().startswith(prefix):
                    dy = float(cb[1]) - obbox[1]
                    dx = float(cb[0]) - obbox[0]
                    matched_drifts.append({
                        "prefix": prefix,
                        "orig_y": obbox[1],
                        "comp_y": float(cb[1]),
                        "drift_y": round(dy, 2),
                        "drift_x": round(dx, 2),
                    })
                    break

        # Image drift analysis
        image_drifts = []
        try:
            compiled_images = compiled_page.get_images(full=True) or []
            comp_img_rects = []
            for img in compiled_images:
                xref = img[0]
                try:
                    for r in compiled_page.get_image_rects(xref):
                        if r and r.width > 20 and r.height > 20:
                            comp_img_rects.append(r)
                except Exception:
                    pass

            orig_figures = getattr(page_data, "figures", []) or []
            for fig in orig_figures:
                fig_rect = getattr(fig, "graphic_rect", None)
                if fig_rect and comp_img_rects:
                    # Find closest compiled image
                    fx = getattr(fig_rect, "x0", 0)
                    fy = getattr(fig_rect, "y0", 0)
                    best_match = min(comp_img_rects, key=lambda cr: abs(cr.x0 - fx) + abs(cr.y0 - fy))
                    image_drifts.append({
                        "orig_bbox": [round(fx, 1), round(fy, 1), round(getattr(fig_rect, "x1", 0), 1), round(getattr(fig_rect, "y1", 0), 1)],
                        "comp_bbox": [round(best_match.x0, 1), round(best_match.y0, 1), round(best_match.x1, 1), round(best_match.y1, 1)],
                        "dx": round(best_match.x0 - fx, 2),
                        "dy": round(best_match.y0 - fy, 2),
                    })
        except Exception as img_err:
            logger.debug(f"Image drift check skipped: {img_err}")

        # Color fidelity check
        color_fidelity_score = 1.0
        try:
            colored_orig_blocks = [
                b for b in orig_blocks
                if _get_block_color(b) and _get_block_color(b).lower() not in ("#000000", "#000", "black")
            ]
            if colored_orig_blocks:
                # Check compiled page text spans for non-black color
                compiled_text_dict = compiled_page.get_text("dict") or {}
                comp_colors = set()
                for cblock in compiled_text_dict.get("blocks", []):
                    for line in cblock.get("lines", []):
                        for span in line.get("spans", []):
                            c_int = span.get("color", 0)
                            if c_int and c_int != 0:
                                r = (c_int >> 16) & 0xFF
                                g = (c_int >> 8) & 0xFF
                                b_col = c_int & 0xFF
                                if not (r < 30 and g < 30 and b_col < 30):
                                    comp_colors.add(f"#{r:02x}{g:02x}{b_col:02x}".lower())

                if comp_colors:
                    color_fidelity_score = 1.0
                else:
                    # Original had colors, compiled has none detected
                    color_fidelity_score = 0.5
        except Exception as col_err:
            logger.debug(f"Color fidelity check skipped: {col_err}")

        height_diff = comp_h - orig_h
        width_diff = comp_w - orig_w

        doc.close()

        return {
            "page_missing": False,
            "top_drift": round(top_drift, 2),
            "left_drift": round(left_drift, 2),
            "height_diff": round(height_diff, 2),
            "width_diff": round(width_diff, 2),
            "matched_drifts": matched_drifts,
            "image_drift": image_drifts,
            "color_fidelity_score": round(color_fidelity_score, 2),
        }
    except Exception as e:
        logger.warning(f"Error analyzing page positional drift: {e}")
        try:
            doc.close()
        except Exception:
            pass
        return default_empty


def calibrate_page_spacing(latex_content: str, drift_info: Dict[str, Any]) -> str:
    """
    Calibrates LaTeX page spacing using measured positional drift.
    Inserts or scales \\vspace offsets.
    """
    if not latex_content or not drift_info:
        return latex_content

    top_drift = drift_info.get("top_drift", 0.0)
    height_diff = drift_info.get("height_diff", 0.0)

    result = latex_content

    if abs(top_drift) > 3.0:
        offset = -top_drift
        vspace_cmd = f"\\vspace*{{{offset:.1f}pt}}\n"
        if "\\begin{document}" in result:
            result = result.replace("\\begin{document}", f"\\begin{{document}}\n{vspace_cmd}", 1)
        elif "\\begin{frame}" in result:
            result = result.replace("\\begin{frame}", f"\\begin{{frame}}\n{vspace_cmd}", 1)
        else:
            result = vspace_cmd + result

    if height_diff > 15.0 and "\\vspace{" in result:
        def scale_vspace(match):
            val_str = match.group(1)
            unit = match.group(2)
            try:
                val = float(val_str)
                new_val = max(2.0, val * 0.7)
                return f"\\vspace{{{new_val:.1f}{unit}}}"
            except Exception:
                return match.group(0)

        result = re.sub(r'\\vspace\{(\d+(?:\.\d+)?)(pt|mm|cm|ex|em)\}', scale_vspace, result)

    return result

