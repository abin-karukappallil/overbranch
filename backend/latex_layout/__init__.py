"""
latex_layout — measuring and correcting the geometry of typeset LaTeX.

Shared by the agent (justify_content / detect_overflow / inspect_pdf_geometry
tools) and the PDF importer (pre-emptive width facts and post-compile repair):

* metrics   — width of a string in the TeX font that will actually set it
* blocks    — TextBlock lines read from a PDF page, and source/output comparison
* overflow  — overfull boxes from the log + glyphs past the text area / page
* justify   — fit one fragment to a width (the single-target primitive)
* issues    — every layout defect of a rendered document, measured and ranked
* repair    — the smallest safe LaTeX change for one defect, text preserved
* vision    — an optional, advisory second opinion on how a page looks

``issues`` + ``repair`` are the detect → fix half of the render-aware loop that
``opencode.layout_tools.justify_content_tool`` drives; nothing in this package
compiles anything or touches a document.
"""

from .issues import LayoutIssue, detect_layout_issues, issue_counts, layout_score, sort_issues
from .justify import JustifyResult, FontSpec, fit_fragment, probe_page_geometry
from .repair import RepairOp, plan_repair, plan_repairs, preserves_text

__all__ = [
    "LayoutIssue", "detect_layout_issues", "issue_counts", "layout_score", "sort_issues",
    "JustifyResult", "FontSpec", "fit_fragment", "probe_page_geometry",
    "RepairOp", "plan_repair", "plan_repairs", "preserves_text",
]
