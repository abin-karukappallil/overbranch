"""
justify_content, overflow detection and long words (K, L, M).

The strategy ladder is checked with font metrics (no TeX needed); the
end-to-end tests compile with pdflatex and are skipped without it.
"""

import shutil

import pytest

from latex_layout.justify import FontSpec, justify_content
from latex_layout.metrics import latex_to_plain, text_width
from latex_layout.overflow import parse_overfull

HAS_TEX = shutil.which("pdflatex") is not None
needs_tex = pytest.mark.skipif(not HAS_TEX, reason="pdflatex not installed")
HELV = FontSpec("helvetica", 10.0)
PRE = "\\documentclass[10pt]{article}\n\\usepackage{helvet}\\renewcommand{\\familydefault}{\\sfdefault}\n\\usepackage{graphicx}\n"


# --- K. strategy ladder ------------------------------------------------------------

def test_fitting_content_is_left_alone_or_only_aligned():
    assert justify_content("Short text", 200, HELV).strategy == "none"
    r = justify_content("Short text", 200, HELV, alignment="right")
    assert r.strategy == "align" and r.latex == "{\\raggedleft Short text\\par}"


def test_slightly_too_wide_line_is_condensed_not_shrunk():
    w = text_width("SLEEPER CLASS (SL)", "helvetica", 10)
    r = justify_content("SLEEPER CLASS (SL)", w / 1.05, HELV)
    assert r.strategy == "condense"
    assert r.latex.startswith("\\resizebox{") and "{\\height}" in r.latex
    assert "graphicx" in r.needs_packages


def test_much_too_wide_line_shrinks_font_within_floor_then_condenses():
    w = text_width("SLEEPER CLASS (SL)", "helvetica", 10)
    r = justify_content("SLEEPER CLASS (SL)", w / 1.15, HELV)
    assert r.strategy == "shrink"
    assert "\\fontsize{8.7" in r.latex or "\\fontsize{8.6" in r.latex
    r = justify_content("SLEEPER CLASS (SL)", w / 1.4, HELV)
    assert r.strategy == "shrink+condense"
    assert "\\fontsize{8.5}" in r.latex  # never below 85%


def test_paragraph_is_wrapped_not_condensed():
    para = "This paragraph is long enough that TeX must wrap it over several lines of the box. " * 3
    r = justify_content(para, 200, HELV, single_line=False)
    assert r.strategy == "wrap"
    assert "\\emergencystretch" in r.latex
    assert "\\resizebox" not in r.latex and "\\\\" not in r.latex  # no manual line breaks


# --- L. long words -------------------------------------------------------------------

def test_only_tokens_wider_than_the_box_get_break_points():
    text = "Invoice PS26465477199011PS26465477199011PS2646 issued to Indian Railways New Delhi office"
    r = justify_content(text, 120, HELV, single_line=False)
    assert r.strategy == "break_tokens"
    assert "Indian Railways New Delhi" in r.latex          # ordinary words untouched
    assert "\\-" in r.latex or "\\allowbreak" in r.latex
    assert r.latex.count("\\-") + r.latex.count("\\allowbreak") <= 4


def test_separators_are_preferred_break_points():
    r = justify_content("Status CNF/S5/56/SIDE/UPPER/BERTH/COACH/NUMBER/SEVENTY", 60, HELV, single_line=False)
    assert "/\\allowbreak{}" in r.latex and "\\-" not in r.latex


def test_word_that_fits_is_never_broken():
    r = justify_content("A reasonably sized sentence of ordinary words", 120, HELV, single_line=False)
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
    r = justify_content("SLEEPER CLASS (SL)", 60, HELV, preamble=PRE)
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
    out = justify_content_tool(ws, {"text": text})
    assert out["success"], out
    assert out["justify"]["strategy"] in ("condense", "shrink", "shrink+condense")
    assert out.get("verified") is True
    assert not detect_overflow_tool(ws)["has_overflow"]
    assert "SLEEPER CLASS (SL)" in ws.get_buffer()      # text kept, not broken or shortened
