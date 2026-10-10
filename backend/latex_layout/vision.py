"""
vision.py — A second opinion on pages that measure clean but may not look it.

Geometry answers "is this text where it should be?" exactly, and that covers
every defect with a position: overflow, a table off the page, a token broken
mid-word. It cannot answer "does this page look wrong?" — a table whose every
cell is inside its border but whose rows are wildly uneven, a heading adrift
from the text it introduces, spacing that is legal and still ugly.

So this pass is deliberately narrow:

* it runs only when asked (``JUSTIFY_VISION=1``) and only on pages the
  geometric detector could not explain, so the normal path costs nothing;
* it reports, and never repairs. Its findings carry no source location,
  because a model reading a picture cannot know which line produced what it
  sees — mapping stays deterministic, driven by text the detector measured;
* pages go up in small batches, never the whole document in one prompt.

The agent loop is text-only, so this is a self-contained side call, built the
same way the PDF importer's is (``pdf2latex/llm.py``).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Sequence

from .issues import SEVERITY, VISUAL_INCONSISTENCY, LayoutIssue

logger = logging.getLogger("latex_layout.vision")

BATCH_PAGES = int(os.environ.get("JUSTIFY_VISION_BATCH", "5") or 5)
RENDER_DPI = int(os.environ.get("JUSTIFY_VISION_DPI", "100") or 100)
MAX_BATCHES = 4

PROMPT = """You are inspecting rendered pages of a LaTeX document for LAYOUT quality only.

Report ONLY problems that are visible in the image and that a careful typesetter
would fix, such as:
  - a table whose rows or columns are badly unbalanced (one column cramped, another empty)
  - a heading separated from the text it introduces, or sitting alone at a page foot
  - spacing that is conspicuously uneven between comparable elements
  - an element that looks misaligned with the rest of the page

Do NOT report:
  - anything about the wording, facts, grammar or content
  - text running past the margin, broken file paths, or a table wider than the page
    (these are measured separately and precisely; repeating them adds nothing)
  - matters of taste where the page is simply plain

Answer with JSON only:
{"issues": [{"page": <number as labelled below>, "severity": "low"|"medium"|"high",
             "description": "<one sentence naming what looks wrong and where on the page>"}]}
Return {"issues": []} if the pages look well set. Never invent a line number."""


def render_pages(pdf_bytes: bytes, pages: Sequence[int], dpi: int = RENDER_DPI) -> List[tuple]:
    """[(page_number, png_bytes)] for the given 1-based pages."""
    import pymupdf

    out: List[tuple] = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        for n in pages:
            if not (1 <= n <= doc.page_count):
                continue
            try:
                pix = doc[n - 1].get_pixmap(dpi=dpi)
                out.append((n, pix.tobytes("png")))
            except Exception as e:
                logger.debug(f"Could not render page {n}: {e}")
    return out


def _parse(reply: str, allowed: Sequence[int]) -> List[LayoutIssue]:
    m = re.search(r"\{.*\}", reply or "", re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except Exception:
        return []
    found: List[LayoutIssue] = []
    for raw in (data.get("issues") or [])[:20]:
        if not isinstance(raw, dict):
            continue
        try:
            page = int(raw.get("page"))
        except (TypeError, ValueError):
            continue
        desc = str(raw.get("description") or "").strip()
        # A finding about a page that was not shown is a hallucination.
        if page not in allowed or not desc:
            continue
        sev = str(raw.get("severity") or "low").lower()
        found.append(LayoutIssue(
            page=page, type=VISUAL_INCONSISTENCY,
            severity=sev if sev in ("low", "medium", "high") else SEVERITY[VISUAL_INCONSISTENCY],
            description=desc[:300],
            evidence={"visual_observation": desc[:300], "source": "vision"}))
    return found


def inspect_pages(pdf_bytes: Optional[bytes], pages: Sequence[int],
                  model: Optional[str] = None, cancel_token: Any = None) -> List[LayoutIssue]:
    """
    Aesthetic layout problems on ``pages``, as reported by the vision model.

    Report-only: nothing here is repaired automatically, because no repair in
    the catalogue can be chosen from a sentence of prose, and guessing one
    would be exactly the unconstrained rewriting this design exists to avoid.
    Returns [] on any failure — a missing second opinion is not an error.
    """
    if not pdf_bytes or not pages:
        return []
    try:
        from providers.multimodal import image_part, text_part
        from providers.router import DEFAULT_MODEL, provider_router
    except Exception as e:
        logger.debug(f"Vision pass unavailable: {e}")
        return []

    found: List[LayoutIssue] = []
    batches = [list(pages)[i:i + BATCH_PAGES] for i in range(0, len(pages), BATCH_PAGES)][:MAX_BATCHES]
    for batch in batches:
        images = render_pages(pdf_bytes, batch)
        if not images:
            continue
        content: List[Dict[str, Any]] = [text_part(
            PROMPT + "\n\nThe images that follow are pages: "
            + ", ".join(str(n) for n, _ in images) + ", in that order.")]
        for _n, png in images:
            content.append(image_part(png))
        try:
            reply = provider_router.chat(
                messages=[{"role": "user", "content": content}],
                model=model or DEFAULT_MODEL, temperature=0.0, max_tokens=1200,
                cancel_token=cancel_token)
        except Exception as e:
            logger.info(f"Vision layout pass failed, continuing without it: {e}")
            break
        text = reply.get("content") if isinstance(reply, dict) else str(reply)
        found.extend(_parse(text or "", [n for n, _ in images]))
    return found
