"""
latex_layout — measuring and correcting the horizontal geometry of typeset LaTeX.

Shared by the agent (justify_content / detect_overflow / inspect_pdf_geometry
tools) and the PDF importer (pre-emptive width facts and post-compile repair):

* metrics   — width of a string in the TeX font that will actually set it
* blocks    — TextBlock lines read from a PDF page, and source/output comparison
* overflow  — overfull boxes from the log + glyphs past the text area / page
* justify   — the smallest LaTeX change that makes content fit its width
"""
