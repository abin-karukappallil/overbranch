"""
AI rebuild — the LLM-driven PDF → LaTeX pipeline behind the "editable" import mode.

inspect/OCR → layout + classification → page rasters → assets → Gemini writes a preamble then each
page → sandboxed compile/repair → per-page measure + correct → package. Stage modules talk through
the dataclasses in `model.py` and read their knobs from `settings.py`; they do not import each
other's internals. The deterministic engine in `pdf2latex.editable` stays as the whole-job fallback.
"""
