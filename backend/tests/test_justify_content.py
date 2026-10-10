"""
justify_content, overflow detection and long words (K, L, M).

The strategy ladder is checked with font metrics (no TeX needed); the
end-to-end tests compile with pdflatex and are skipped without it.
"""

import shutil

import pytest

from latex_layout.justify import FontSpec, fit_fragment
from latex_layout.metrics import latex_to_plain, text_width
from latex_layout.overflow import parse_overfull

HAS_TEX = shutil.which("pdflatex") is not None
needs_tex = pytest.mark.skipif(not HAS_TEX, reason="pdflatex not installed")
HELV = FontSpec("helvetica", 10.0)
PRE = "\\documentclass[10pt]{article}\n\\usepackage{helvet}\\renewcommand{\\familydefault}{\\sfdefault}\n\\usepackage{graphicx}\n"


# --- K. strategy ladder ------------------------------------------------------------

def test_fitting_content_is_left_alone_or_only_aligned():
    assert fit_fragment("Short text", 200, HELV).strategy == "none"
    r = fit_fragment("Short text", 200, HELV, alignment="right")
    assert r.strategy == "align" and r.latex == "{\\raggedleft Short text\\par}"


def test_slightly_too_wide_line_is_condensed_not_shrunk():
    w = text_width("SLEEPER CLASS (SL)", "helvetica", 10)
    r = fit_fragment("SLEEPER CLASS (SL)", w / 1.05, HELV)
    assert r.strategy == "condense"
    assert r.latex.startswith("\\resizebox{") and "{\\height}" in r.latex
    assert "graphicx" in r.needs_packages


def test_much_too_wide_line_is_condensed_never_shrunk():
    """
    Type is never made smaller to make content fit. Shrinking is visible next
    to text set at the document's real size and it spreads, because the next
    overflow invites the same treatment.
    """
    w = text_width("SLEEPER CLASS (SL)", "helvetica", 10)
    for divisor in (1.15, 1.4, 2.0):
        # single_line: an unbreakable unit (a label, a heading, a table cell).
        # A fragment free to wrap is wrapped instead, which is cheaper still.
        r = fit_fragment("SLEEPER CLASS (SL)", w / divisor, HELV, single_line=True)
        assert r.strategy == "condense"
        assert "\\fontsize" not in r.latex
        assert "\\small" not in r.latex and "\\scriptsize" not in r.latex
        assert "SLEEPER CLASS (SL)" in r.latex          # content untouched
    # A large reduction is reported, so a human can widen the column instead.
    r = fit_fragment("SLEEPER CLASS (SL)", w / 2.0, HELV, single_line=True)
    assert any("consider widening" in n for n in r.notes)


def test_paragraph_is_wrapped_not_condensed():
    para = "This paragraph is long enough that TeX must wrap it over several lines of the box. " * 3
    r = fit_fragment(para, 200, HELV, single_line=False)
    assert r.strategy == "wrap"
    assert "\\emergencystretch" in r.latex
    assert "\\resizebox" not in r.latex and "\\\\" not in r.latex  # no manual line breaks


# --- L. long words -------------------------------------------------------------------

def test_only_tokens_wider_than_the_box_get_break_points():
    text = "Invoice PS26465477199011PS26465477199011PS2646 issued to Indian Railways New Delhi office"
    r = fit_fragment(text, 120, HELV, single_line=False)
    assert r.strategy == "break_tokens"
    assert "Indian Railways New Delhi" in r.latex          # ordinary words untouched
    assert "\\-" in r.latex or "\\allowbreak" in r.latex
    assert r.latex.count("\\-") + r.latex.count("\\allowbreak") <= 4


def test_separators_are_preferred_break_points():
    r = fit_fragment("Status CNF/S5/56/SIDE/UPPER/BERTH/COACH/NUMBER/SEVENTY", 60, HELV, single_line=False)
    assert "/\\allowbreak{}" in r.latex and "\\-" not in r.latex


def test_word_that_fits_is_never_broken():
    r = fit_fragment("A reasonably sized sentence of ordinary words", 120, HELV, single_line=False)
    assert "\\-" not in r.latex and "\\allowbreak" not in r.latex


# --- M. right-edge overflow -------------------------------------------------------------

def test_parse_overfull_boxes():
    log = ("Overfull \\hbox (14.27pt too wide) in paragraph at lines 12--14\n"
           "Overfull \\hbox (0.5pt too wide) detected at line 30\n")
    boxes = parse_overfull(log)
    assert boxes[0] == {"box": "hbox", "amount_pt": 14.27, "where": "paragraph", "lines": [12, 14], "severe": True}
    assert boxes[1]["lines"] == [30, 30] and boxes[1]["severe"] is False


def test_latex_to_plain_measures_visible_text_only():
    assert latex_to_plain("\\textbf{PNR} \\textcolor{c1F4E79}{4654771990}\\hspace{3pt}") == "PNR 4654771990"


@needs_tex
def test_tex_measurement_matches_document_font():
    r = fit_fragment("SLEEPER CLASS (SL)", 60, HELV, preamble=PRE)
    assert r.measured_by == "tex"
    assert abs(r.measured_w - text_width("SLEEPER CLASS (SL)", "helvetica", 10)) < 1.0


@needs_tex
def test_justify_tool_removes_right_edge_overflow():
    from opencode.layout_tools import detect_overflow_tool, justify_content_tool
    from opencode.shadow_workspace import ShadowWorkspace

    para = "Body text that fills the full width of the text block so the right edge is known. " * 4
    doc = (PRE + "\\begin{document}\n" + para + "\n\n\\noindent\\makebox[\\linewidth][l]{Left label\\hfill "
           "SLEEPER CLASS (SL) AND A VERY LONG RIGHT COLUMN VALUE THAT DOES NOT FIT ON THE LINE AT ALL}\n"
           "\\end{document}\n")
    ws = ShadowWorkspace(doc)
    before = detect_overflow_tool(ws)
    assert before["has_overflow"]
    text = "Left label\\hfill SLEEPER CLASS (SL) AND A VERY LONG RIGHT COLUMN VALUE THAT DOES NOT FIT ON THE LINE AT ALL"
    out = justify_content_tool(ws, {"scope": "text", "text": text})
    assert out["success"], out
    assert out["justify"]["strategy"] == "condense"
    assert out.get("verified") is True
    assert not detect_overflow_tool(ws)["has_overflow"]
    assert "SLEEPER CLASS (SL)" in ws.get_buffer()      # text kept, not broken or shortened


@needs_tex
def test_justify_content_tool_exact_io():
    """
    Validates exact inputs and outputs of justify_content_tool:
    - Text targeting with explicit width_pt and center alignment
    - Exact output dictionary structure (success, lines_affected, verified, justify details)
    - Automatic injection of required package (\\usepackage{graphicx}) into preamble
    """
    from opencode.layout_tools import justify_content_tool
    from opencode.shadow_workspace import ShadowWorkspace

    doc = (
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "\\noindent\\mbox{VERY-LONG-DEPARTMENT-IDENTIFIER-AND-CODE}\n"
        "\\end{document}\n"
    )
    ws = ShadowWorkspace(doc)
    args = {
        "scope": "text",
        "text": "VERY-LONG-DEPARTMENT-IDENTIFIER-AND-CODE",
        "width_pt": 120.0,
        "alignment": "center",
    }
    out = justify_content_tool(ws, args)

    # 1. Top-level result properties
    assert out["success"] is True
    assert out["lines_affected"] == [3, 3]
    assert out["verified"] is True

    # 2. Detailed justify output dictionary
    j = out["justify"]
    assert j["strategy"] == "condense"
    assert j["target_w"] == 120.0
    assert j["measured_w"] > 120.0
    assert j["ratio"] > 1.10
    assert j["changed"] is True
    assert "graphicx" in j["needs_packages"]
    assert j["measured_by"] == "tex"
    assert "\\resizebox{120pt}{\\height}" in j["latex"]
    assert "\\centering" in j["latex"]
    assert "\\fontsize" not in j["latex"]

    # 3. Buffer transformation and package injection
    buf = ws.get_buffer()
    assert "\\usepackage{graphicx}" in buf
    assert "\\resizebox{120pt}{\\height}" in buf


def test_justify_content_exact_io():
    """
    Validates exact input and output structure of fit_fragment() from latex_layout.justify.
    """
    res = fit_fragment(
        fragment="OVERFLOWING CELL TEXT",
        available_w=100.0,
        font=HELV,
        alignment="center",
        single_line=True,
    )
    data = res.as_dict()
    assert data["strategy"] == "condense"
    assert data["target_w"] == 100.0
    assert data["changed"] is True
    assert isinstance(data["latex"], str)
    assert "\\centering" in data["latex"]
    assert data["measured_by"] in ("metrics", "tex")

