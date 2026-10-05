"""
Preamble generation, facts, pdfLaTeX text handling and page merging (no LLM, no TeX).
"""

import json
from pathlib import Path

import pytest

from pdf2latex.extract import extract_document
from pdf2latex.facts import fallback_body, page_facts
from pdf2latex.preamble import (
    assemble_document,
    body_of,
    build_preamble,
    clean_body,
    collect_colors,
    font_class,
    page_for_line,
    page_geometry,
    plan_fonts,
    referenced_files,
)
from pdf2latex.prompts import fill, page_user_prompt
from pdf2latex.texutil import latex_text, sanitize_unicode
from tests import pdf2latex_fixtures as fx


def _extract(data: bytes, tmp_path: Path):
    ext, doc = extract_document(data, tmp_path, "assets/pdf_t")
    doc.close()
    return ext


@pytest.fixture
def multi(tmp_path):
    return _extract(fx.multi_page_pdf(), tmp_path)


# --- preamble ---------------------------------------------------------------

def test_geometry_matches_page_size_and_margins(multi):
    g = page_geometry(multi)
    assert (g.paper_w, g.paper_h) == pytest.approx(fx.A4, abs=0.5)
    assert g.left == pytest.approx(71, abs=1.5)  # smallest content margin over pages, minus 1pt safety
    assert g.text_w > 0 and g.text_h > 0


def test_every_distinct_color_defined_with_exact_rgb(multi):
    colors = collect_colors(multi)
    assert colors["c0D2673"] == (13, 38, 115)  # heading
    assert colors["cBF0D0D"] == (191, 13, 13)  # monospace line
    assert colors["cD9E0F2"] == (217, 224, 242)  # table header fill
    assert "c000000" in colors
    pre = build_preamble(page_geometry(multi), colors, plan_fonts(multi))
    assert "\\definecolor{c0D2673}{RGB}{13,38,115}" in pre
    assert "\\definecolor{cD9E0F2}{RGB}{217,224,242}" in pre


def test_preamble_is_pdflatex_compatible(multi):
    pre = build_preamble(page_geometry(multi), collect_colors(multi), plan_fonts(multi))
    assert pre.splitlines()[1] == "\\documentclass{article}"
    for pkg in ("[T1]{fontenc}", "[utf8]{inputenc}", "{graphicx}", "{amsmath,amssymb}", "[table]{xcolor}"):
        assert f"\\usepackage{pkg}" in pre
    assert "\\usepackage[paperwidth=595bp,paperheight=842bp," in pre
    assert "fontspec" not in pre and "!TEX program" not in pre


@pytest.mark.parametrize("name,flags,expected", [
    ("Times-Roman", 4, "times"), ("ABCDEF+TimesNewRomanPSMT", 0, "times"), ("Helvetica-Bold", 16, "helvetica"),
    ("ArialMT", 0, "helvetica"), ("Calibri", 0, "helvetica"), ("Courier", 0, "courier"), ("CMR10", 4, "lmodern"),
    ("BookAntiqua", 4, "palatino"), ("UnknownFont", 4, "times"), ("UnknownFont", 0, "helvetica"),
])
def test_font_mapping(name, flags, expected):
    assert font_class(name, flags) == expected


def test_main_font_and_secondary_families(tmp_path):
    fonts = plan_fonts(_extract(fx.multi_font_pdf(), tmp_path))
    pre = build_preamble(page_geometry(_extract(fx.multi_font_pdf(), tmp_path / "b")), {}, fonts)
    assert fonts.uses_mono
    assert "\\usepackage{courier}" in pre
    assert f"\\fontsize{{{fonts.body_size:g}bp}}" in pre


# --- text handling ------------------------------------------------------------

def test_latex_text_escapes_specials_and_maps_unicode():
    assert latex_text("50% & $5 #1 {a_b}") == "50\\% \\& \\$5 \\#1 \\{a\\_b\\}"
    assert latex_text("“Hi” – ok…") == "``Hi'' -- ok\\ldots{}"
    assert latex_text("x ≤ y • α") == "x \\ensuremath{\\leq} y \\textbullet{} \\ensuremath{\\alpha}"
    assert latex_text("café ﬁle") == "café file"  # Latin-1 kept, ligature decomposed


def test_sanitize_unicode_keeps_markup_and_reports_unknown():
    out, dropped = sanitize_unicode("\\textbf{→ done} 🙂")
    assert out == "\\textbf{\\ensuremath{\\rightarrow} done} "
    assert dropped == ["🙂"]


# --- facts --------------------------------------------------------------------

def test_facts_are_compact_relative_and_escaped(tmp_path):
    ext = _extract(fx.multi_font_pdf(), tmp_path)
    geom, fonts, colors = page_geometry(ext), plan_fonts(ext), collect_colors(ext)
    facts, unknown = page_facts(ext.pages[0], geom, fonts, 1, next(iter(colors)))
    assert not unknown
    head = facts["lines"][0]
    assert head["t"] == "Quarterly Report" and head["sz"] == 24 and head["b"] == 1
    assert head["c"] == "c0D2673" and head["f"] == "sans"
    assert head["x"] == pytest.approx(72 - geom.left, abs=0.5)
    assert head["y"] == pytest.approx(90 - geom.top, abs=0.5)  # baseline, relative to the text area
    special = next(l for l in facts["lines"] if "Special" in l["t"])
    assert "50\\% \\& \\$5" in special["t"]
    body = next(l for l in facts["lines"] if l["t"].startswith("Body text"))
    assert "c" not in body  # default color omitted
    json.dumps(facts)


def test_facts_list_images_and_shapes(tmp_path):
    ext = _extract(fx.table_pdf(), tmp_path)
    facts, _ = page_facts(ext.pages[0], page_geometry(ext), plan_fonts(ext), 1, "c000000")
    kinds = [s["k"] for s in facts["shapes"]]
    assert kinds.count("hrule") == 4 and kinds.count("vrule") == 4
    assert any(s.get("fill") == "cD9E0F2" for s in facts["shapes"])
    ext2 = _extract(fx.image_pdf(), tmp_path / "i")
    facts2, _ = page_facts(ext2.pages[0], page_geometry(ext2), plan_fonts(ext2), 1, "c000000")
    assert {Path(i["file"]).stem for i in facts2["images"]} == {"page1_img1", "page1_img2"}


def test_user_prompt_has_colors_facts_and_last_page_note(tmp_path):
    ext = _extract(fx.multi_font_pdf(), tmp_path)
    facts, _ = page_facts(ext.pages[0], page_geometry(ext), plan_fonts(ext), 1, "c000000")
    prompt = page_user_prompt(facts, ["c000000", "c0D2673"])
    assert "page 1 of 1" in prompt and "LAST page" in prompt
    assert "c000000, c0D2673" in prompt
    assert json.loads(prompt.split("Page facts (JSON):\n", 1)[1].split("\n\nReturn only")[0])["page"] == 1
    assert fill("a {{X}} 50% {{X}}", X="b") == "a b 50% b"


def test_fallback_body_places_every_line(tmp_path):
    ext = _extract(fx.multi_font_pdf(), tmp_path)
    body = fallback_body(ext.pages[0], page_geometry(ext), plan_fonts(ext))
    assert body.startswith("\\noindent\\begin{tikzpicture}") and body.endswith("\\end{tikzpicture}")
    for text in ("Quarterly Report", "Italic emphasis line", "monospace: x = f(y);", "50\\% \\&"):
        assert text in body
    assert "text=c0D2673" in body


# --- merging ------------------------------------------------------------------

def test_clean_body_strips_fences_preamble_and_page_breaks():
    raw = ("Here you go:\n```latex\n\\documentclass{article}\n\\usepackage{xcolor}\n\\begin{document}\n"
           "Hello\n\\newpage\n\\end{document}\n```\nThanks")
    assert clean_body(raw) == "Hello"
    assert clean_body("\\clearpage\nText\n\\newpage") == "Text"


def test_assemble_separates_pages_with_newpage_and_maps_lines():
    tex = assemble_document("PRE", {1: "One", 2: "", 3: "Three\n\\includegraphics[width=2bp]{assets/x.png}"})
    body = tex.split("\\begin{document}\n", 1)[1]
    assert body.count("\\newpage") == 2  # pages - 1, none after the last page
    assert "\\null" in body  # empty page kept
    assert tex.rstrip().endswith("\\end{document}")
    lines = tex.splitlines()
    assert page_for_line(tex, lines.index("Three") + 1) == 3
    assert body_of(tex, 1) == "One"
    assert referenced_files(tex) == ["assets/x.png"]
