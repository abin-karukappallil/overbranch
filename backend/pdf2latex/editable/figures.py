"""
figures.py — Pictures cropped to their ink.

A picture's PDF box often carries white padding (Ryve's "507pt" diagrams are ~380pt of drawing in a
white canvas). Placed and sized by its box, the drawing comes out smaller than in the PDF once the
box is capped to the line, and the white margin pushes the text around it. Each figure PNG is
cropped to its ink (pixels differing from white by more than ``THRESHOLD``, plus 1px), written next
to the original as ``*_trim.png``, and the ink box in PDF points replaces the picture's box. Pages
with background art or shaded boxes are left alone (white there is not "nothing").
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Tuple

logger = logging.getLogger("pdf2latex.editable.figures")

THRESHOLD = 12
PAD = 1


def ink_box(path: Path):
    """(x0, y0, x1, y1) pixel box of the image's ink, its size (w, h); None when unreadable or blank."""
    try:
        from PIL import Image
        import numpy as np
    except ImportError:  # pragma: no cover
        return None
    try:
        with Image.open(path) as im:
            im.load()
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                rgba = im.convert("RGBA")
                bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                bg.alpha_composite(rgba)
                rgb = bg.convert("RGB")
            else:
                rgb = im.convert("RGB")
            a = np.asarray(rgb, dtype=np.int16)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"ink box unreadable {path}: {e}")
        return None
    ink = (255 - a).max(axis=2) > THRESHOLD
    ys = np.where(ink.any(axis=1))[0]
    xs = np.where(ink.any(axis=0))[0]
    h, w = ink.shape
    if not len(xs) or not len(ys):
        return None
    x0 = max(0, int(xs[0]) - PAD)
    y0 = max(0, int(ys[0]) - PAD)
    x1 = min(w, int(xs[-1]) + 1 + PAD)
    y1 = min(h, int(ys[-1]) + 1 + PAD)
    return (x0, y0, x1, y1), (w, h)


def trim_images(extract, out_dir) -> Dict[str, Tuple]:
    """{image file: (trimmed file, ink box in PDF points, trimmed pixel size)} for every picture
    worth cropping."""
    out: Dict[str, Tuple] = {}
    out_dir = Path(out_dir)
    decorated = set(extract.metadata.get("_editable_backgrounds", {}) or {}) | \
        set(extract.metadata.get("_editable_boxes", {}) or {})
    for p in extract.pages:
        if p.background or p.is_scanned or p.number in decorated:
            continue
        for img in p.images:
            if img.kind not in ("image", "figure") or img.file in out:
                continue
            src = out_dir / img.file
            got = ink_box(src)
            if got is None:
                continue
            (x0, y0, x1, y1), (w, h) = got
            if x1 - x0 >= w - 2 * PAD - 1 and y1 - y0 >= h - 2 * PAD - 1:
                continue                      # no margin to take off
            if (x1 - x0) < 4 or (y1 - y0) < 4:
                continue
            bx0, by0, bx1, by1 = img.bbox
            sx, sy = (bx1 - bx0) / w, (by1 - by0) / h
            box = (bx0 + x0 * sx, by0 + y0 * sy, bx0 + x1 * sx, by0 + y1 * sy)
            stem = img.file.rsplit(".", 1)[0]
            rel = f"{stem}_trim.png"
            try:
                from PIL import Image
                with Image.open(src) as im:
                    im.crop((x0, y0, x1, y1)).save(out_dir / rel)
            except Exception as e:  # noqa: BLE001
                logger.debug(f"trim failed {img.file}: {e}")
                continue
            out[img.file] = (rel, tuple(round(v, 2) for v in box), (x1 - x0, y1 - y0))
    return out
