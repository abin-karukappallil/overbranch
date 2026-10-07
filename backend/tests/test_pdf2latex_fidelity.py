"""
PDF → LaTeX fidelity (N, O, P): bold detection from every signal, exact sizes
in the facts, metric-compatible fonts, and the post-compile geometry repair on
the IRCTC ticket regression page.
"""

import asyncio
import shutil

import pymupdf
import pytest

from pdf2latex_fixtures import synthetic_bold_pdf, ticket_pdf

from latex_layout.blocks import Mismatch, compare_blocks, text_blocks_from_pdf
from pdf2latex import fontmap
from pdf2latex.extract import _extract_lines
from pdf2latex.geometry import repair_body

HAS_TEX = shutil.which("pdflatex") is not None and shutil.which("pdftoppm") is not None
needs_tex = pytest.mark.skipif(not HAS_TEX, reason="pdflatex/pdftoppm not installed")
HAS_CARLITO = fontmap.tex_package_available("carlito")


# --- N. bold preservation: detection ----------------------------------------------------

@pytest.mark.parametrize("name,bold", [
    ("ABCDEF+Calibri-Bold", True), ("Arial,Bold", True), ("TimesNewRomanPS-BoldMT", True),
    ("SegoeUI-Semibold", True), ("Helvetica-Black", True), ("MyriadPro-Bd", True), ("Foo-B", True),
    ("Calibri", False), ("ArialMT", False), ("Roboto-Medium", False), ("Helvetica-Light", False),
])
def test_bold_from_font_name(name, bold):
    assert fontmap.name_is_bold(name) is bold


def test_synthetic_bold_is_detected():
    doc = pymupdf.open(stream=synthetic_bold_pdf(), filetype="pdf")
    lines = {ln.text.strip(): ln for ln in _extract_lines(doc[0])}
    assert lines["Fake bold heading"].spans[0].bold is True
    assert lines["Ordinary body text"].spans[0].bold is False


def test_descriptor_weight_marks_bold():
    doc = pymupdf.open(stream=synthetic_bold_pdf(), filetype="pdf")
    page = doc[0]
    # Give the (regular-named) font a FontDescriptor that declares weight 700.
    for xref, *_ in page.get_fonts(full=True):
        desc = doc.get_new_xref()
        doc.update_object(desc, "<< /Type /FontDescriptor /FontName /Plain /FontWeight 700 /Flags 32 >>")
        doc.xref_set_key(xref, "FontDescriptor", f"{desc} 0 R")
    assert fontmap.descriptor_bold_fonts(doc, page)


def test_ticket_labels_extract_as_bold():
    doc = pymupdf.open(stream=ticket_pdf(), filetype="pdf")
    styles = {}
    for ln in _extract_lines(doc[0]):
        for sp in ln.spans:
            if sp.text.strip():
                styles[sp.text.strip()] = sp.bold
    assert styles["Booked from"] and styles["PNR"] and styles["Passenger Details"]
    assert styles["ERNAKULAM JN (ERS)"] in (True, False)
    assert styles["IR recovers only 57% of cost of travel on an average."] is False


# --- font mapping -----------------------------------------------------------------------

@pytest.mark.skipif(not HAS_CARLITO, reason="carlito not installed")
def test_calibri_maps_to_metric_compatible_carlito():
    assert fontmap.font_class("ABCDEF+Calibri-Bold") == "carlito"
    assert fontmap.family_of("carlito") == "sans"


def test_calibri_falls_back_when_carlito_missing(monkeypatch):
    monkeypatch.setattr(fontmap, "_available", lambda pkg: False)
    assert fontmap.font_class("Calibri") == "helvetica"
    assert fontmap.font_class("Cambria") == "times"


# --- O. font size preservation -------------------------------------------------------------

def test_facts_carry_exact_sizes_and_bold():
    from pdf2latex.extract import extract_document
    from pdf2latex.facts import page_facts
    from pdf2latex.preamble import page_geometry, plan_fonts
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        ext, doc = extract_document(ticket_pdf(), Path(d), "assets/pdf_test", 5)
        fonts = plan_fonts(ext)
        facts, _ = page_facts(ext.pages[0], page_geometry(ext), fonts, 1, "c000000")
        doc.close()
    entries = {(e.get("t") or "".join(r["t"] for r in e.get("runs", []))): e for e in facts["lines"]}
    pnr = next(e for t, e in entries.items() if t.startswith("4654771990"))
    assert (pnr.get("sz") or pnr["runs"][0]["sz"]) == 10.0
    assert (pnr.get("b") or pnr["runs"][0].get("b")) == 1
    small = next(e for t, e in entries.items() if t.startswith("Invoice Number"))
    assert (small.get("sz") or small["runs"][0]["sz"]) == 8.0


def test_size_mismatch_is_detected_but_condensing_is_not_a_size_change():
    def word_pdf(size: float, scale_x: float = 1.0) -> bytes:
        d = pymupdf.open()
        p = d.new_page()
        p.insert_text((72, 100), "Heading text", fontsize=size, morph=(pymupdf.Point(72, 100),
                      pymupdf.Matrix(scale_x, 1)))
        return d.tobytes()

    src, size = text_blocks_from_pdf(word_pdf(10))
    big, _ = text_blocks_from_pdf(word_pdf(12))
    condensed, _ = text_blocks_from_pdf(word_pdf(10, 0.8))
    assert any(m.kind == "size" for m in compare_blocks(src, big, size))
    assert not any(m.kind == "size" for m in compare_blocks(src, condensed, size))


# --- repairs on a body -------------------------------------------------------------------------

def test_repair_restores_bold_and_fits_overflow_only_where_unique():
    body = ("Booked from \\hfill To\\\\\n"
            "{\\fontsize{10}{12}\\selectfont \\textcolor{c2961A6}{SLEEPER CLASS (SL)}}\\\\\n"
            "ERNAKULAM JN (ERS) \\hfill ERNAKULAM JN (ERS)\\\\\n")
    mm = [
        Mismatch("weight", "Booked from", {"bold": True}, {"bold": False}),
        Mismatch("overflow_right", "SLEEPER CLASS (SL)", {"x1": 545.0, "x0": 450.0}, {"x1": 560.0, "x0": 450.0}),
        Mismatch("weight", "ERNAKULAM JN (ERS)", {"bold": True}, {"bold": False}),  # ambiguous: left alone
    ]
    new, repairs, unresolved = repair_body(body, mm)
    assert "\\textbf{Booked from}" in new
    assert "\\textcolor{c2961A6}{\\obhfit{95pt}{SLEEPER CLASS (SL)}}" in new
    assert new.count("ERNAKULAM JN (ERS)") == 2 and "\\textbf{ERNAKULAM" not in new
    assert len(repairs) == 2 and [m.text for m in unresolved] == ["ERNAKULAM JN (ERS)"]


def test_repeated_phrase_resolved_by_reading_order():
    body = "ERNAKULAM JN (ERS) \\hfill ERNAKULAM JN (ERS)\\\\\n"
    ordered = [("ERNAKULAM JN (ERS)", 50.0, 124.0), ("ERNAKULAM JN (ERS)", 250.0, 124.0)]
    mm = [Mismatch("weight", "ERNAKULAM JN (ERS)", {"bold": True, "x0": 250.0, "y": 124.0}, {"bold": False})]
    new, repairs, _ = repair_body(body, mm, ordered)
    assert new == "ERNAKULAM JN (ERS) \\hfill \\textbf{ERNAKULAM JN (ERS)}\\\\\n"


# --- P. conversion regression (IRCTC ticket) -------------------------------------------------

def _convert(monkeypatch, tmp_path, drop_bold: bool = True):
    """Runs the real pipeline with the LLM replaced by a body that drops all bold."""
    from pdf2latex import jobs, pipeline
    from pdf2latex.facts import fallback_body

    monkeypatch.setenv("PDF2LATEX_JOB_DIR", str(tmp_path))
    monkeypatch.setenv("PDF2LATEX_CONCURRENCY", "1")

    async def fake_generate(ctx, page, facts, png, pr, note="", allow_short_retry=True):
        pr.attempts += 1
        body = fallback_body(page, ctx.geom, ctx.fonts)
        return body.replace("\\bfseries", "") if drop_bold else body

    monkeypatch.setattr(pipeline, "_generate", fake_generate)
    monkeypatch.setattr(pipeline, "llm_available", lambda: True)
    monkeypatch.setattr(pipeline, "write_output_to_project", lambda *a, **k: {"path": "main.tex"})
    state = jobs.create_job("tester", "proj-test", "ticket.pdf", 1)
    asyncio.run(pipeline.run_conversion(state["job_id"], ticket_pdf(), "proj-test"))
    done = jobs.load_job(state["job_id"])
    tex = (jobs.job_dir(state["job_id"]) / "output" / "main.tex").read_text()
    return done, tex


@needs_tex
def test_ticket_conversion_restores_bold_and_stays_inside_right_edge(monkeypatch, tmp_path):
    done, tex = _convert(monkeypatch, tmp_path)
    page = done["report"]["pages"][0]
    assert done["status"] == "done"
    assert page["text_coverage"] == 1.0
    assert page["fallback"] is None
    assert page["style_mismatches"] == 0
    assert page["overflow_lines"] == 0
    assert any(r.startswith("bold restored") for r in page["geometry_repairs"])
    assert page["similarity"] >= 0.9
    if HAS_CARLITO:
        assert "{carlito}" in tex and "\\usepackage{helvet}" not in tex


@needs_tex
def test_ticket_conversion_without_metric_font_fits_lines(monkeypatch, tmp_path):
    fontmap._available.cache_clear()
    monkeypatch.setattr(fontmap, "_available", lambda pkg: False if pkg in ("carlito", "caladea") else True)
    done, tex = _convert(monkeypatch, tmp_path)
    page = done["report"]["pages"][0]
    assert "\\usepackage{helvet}" in tex
    assert page["overflow_lines"] == 0 and page["style_mismatches"] == 0
    assert any(r.startswith("fitted to the right edge") for r in page["geometry_repairs"])
    assert "\\obhfit{" in tex and page["text_coverage"] == 1.0


@needs_tex
def test_faithful_page_is_not_touched(monkeypatch, tmp_path):
    """Existing good behaviour: a body that already matches gets no repairs."""
    done, _tex = _convert(monkeypatch, tmp_path, drop_bold=False)
    page = done["report"]["pages"][0]
    if HAS_CARLITO:
        assert page["geometry_repairs"] == []
    assert page["style_mismatches"] == 0 and page["text_coverage"] == 1.0
