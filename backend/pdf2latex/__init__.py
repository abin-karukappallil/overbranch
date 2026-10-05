"""
pdf2latex — Per-page PDF → LaTeX conversion.

Facts (text, fonts, sizes, colors, positions, images, vectors) are extracted locally
with PyMuPDF; a deterministic preamble is built from them; each page body is written
by the same LLM the AI copilot uses, compiled, repaired and compared with the source.
"""

from .config import Pdf2LatexSettings, get_settings

__all__ = ["Pdf2LatexSettings", "get_settings"]
