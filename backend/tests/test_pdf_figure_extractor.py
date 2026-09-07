"""
test_pdf_figure_extractor.py — Automated Tests for AI PDF Figure Extraction

Tests:
1. High-resolution 300 DPI figure extraction from PDF.
2. Caption and title matching (both by name and figure number).
3. Beamer vs Article LaTeX snippet generation.
4. Intelligent semantic section placement without explicit location.
5. Disk persistence into project assets/ directory.
6. Figure extraction intent detection.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest
import pymupdf as fitz
from PIL import Image
import io

from services.pdf_figure_extractor import (
    extract_figure,
    FigureCandidate,
    ExtractedFigure,
    slugify_name,
)
from services.project_file_writer import save_project_asset
from document_index import parse_document_structure, find_best_figure_section
from agent import detect_figure_extraction_intent


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """Generates an in-memory 2-page academic PDF with diagrams and captions."""
    doc = fitz.open()

    # Page 1: Architecture diagram
    p1 = doc.new_page(width=612, height=792)
    p1.insert_text(fitz.Point(100, 80), "Introduction to Scalable Systems", fontsize=16)
    # Draw vector diagram box
    p1.draw_rect(fitz.Rect(100, 140, 512, 340), color=(0, 0, 0.8), fill=(0.92, 0.96, 1.0), width=2)
    p1.insert_text(fitz.Point(180, 240), "[ System Architecture Component Diagram ]", fontsize=13)
    p1.insert_text(fitz.Point(100, 365), "Figure 1: System Architecture of OverBranch", fontsize=10)

    # Page 2: Benchmark plot
    p2 = doc.new_page(width=612, height=792)
    p2.insert_text(fitz.Point(100, 80), "Experimental Evaluation", fontsize=16)
    p2.draw_rect(fitz.Rect(100, 140, 512, 340), color=(0.8, 0, 0), fill=(1.0, 0.94, 0.94), width=2)
    p2.insert_text(fitz.Point(180, 240), "[ Benchmark Latency Comparison Chart ]", fontsize=13)
    p2.insert_text(fitz.Point(100, 365), "Figure 2: Performance Evaluation on Benchmarks", fontsize=10)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_extract_figure_by_caption_name(sample_pdf_bytes):
    """Verifies extracting a figure using semantic title match ('System Architecture')."""
    fig = extract_figure(sample_pdf_bytes, figure_query="System Architecture")

    assert fig is not None
    assert "system_architecture" in fig.clean_filename
    assert fig.clean_filename.endswith(".png")
    assert fig.asset_rel_path.startswith("assets/")
    assert len(fig.image_bytes) > 1000

    # Verify image integrity and high-res dimensions (300 DPI)
    img = Image.open(io.BytesIO(fig.image_bytes))
    assert img.format == "PNG"
    assert img.width >= 500
    assert img.height >= 200

    # Caption and LaTeX block
    assert "System Architecture" in fig.caption
    assert "\\begin{figure}[htbp]" in fig.latex_snippet
    assert "\\includegraphics[width=\\linewidth]" in fig.latex_snippet
    assert fig.asset_rel_path in fig.latex_snippet
    assert "\\caption{" in fig.latex_snippet
    assert "\\label{fig:" in fig.latex_snippet


def test_extract_figure_by_number(sample_pdf_bytes):
    """Verifies extracting a figure using figure number ('Figure 2')."""
    fig = extract_figure(sample_pdf_bytes, figure_query="Figure 2")

    assert fig is not None
    assert "performance_evaluation" in fig.clean_filename
    assert fig.page_number == 2
    assert "Performance Evaluation" in fig.caption


def test_extract_figure_beamer_format(sample_pdf_bytes):
    """Verifies Beamer frame generation for slide presentations."""
    fig = extract_figure(sample_pdf_bytes, figure_query="System Architecture", document_class="beamer")

    assert fig is not None
    assert "\\begin{frame}" in fig.latex_snippet
    assert "\\end{frame}" in fig.latex_snippet
    assert "\\includegraphics[width=0.85\\linewidth" in fig.latex_snippet
    assert "\\begin{figure}" not in fig.latex_snippet


def test_semantic_figure_placement_without_location():
    """Verifies intelligent placement in the appropriate section when no location is specified."""
    latex_code = r"""\documentclass{article}
\usepackage{amsmath}

\begin{document}

\section{Introduction}
Introduction to the problem.

\section{Related Work}
Existing approaches in literature.

\section{Methodology}
Our proposed pipeline and approach details.

\section{Experiments and Results}
Evaluation metrics, accuracy, and latency benchmarks.

\section{Conclusion}
Final remarks and future directions.

\end{document}
"""
    doc_index = parse_document_structure(latex_code)

    # 1. Architecture figure -> should automatically place in Methodology
    target_arch = find_best_figure_section(doc_index, "System Architecture", "Block diagram of pipeline")
    assert target_arch is not None
    assert target_arch.title == "Methodology"

    # 2. Benchmark/Loss figure -> should automatically place in Experiments and Results
    target_perf = find_best_figure_section(doc_index, "Performance Loss Curves", "Epochs vs loss chart")
    assert target_perf is not None
    assert target_perf.title == "Experiments and Results"

    # 3. Literature taxonomy -> should automatically place in Related Work
    target_rel = find_best_figure_section(doc_index, "Taxonomy of Prior Art", "Comparison of related work")
    assert target_rel is not None
    assert target_rel.title == "Related Work"


def test_save_project_asset(tmp_path, monkeypatch):
    """Verifies saving figure assets to the project directory structure."""
    fake_uploads = tmp_path / "uploads" / "projects"
    fake_uploads.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("services.project_file_writer.UPLOADS_BASE_DIR", fake_uploads)

    # Disable remote Supabase calls in unit test
    class DummySupabase:
        def table(self, *args):
            return self
        def upsert(self, *args):
            return self
        def execute(self):
            return True

    monkeypatch.setattr("services.project_file_writer.get_supabase_client", lambda: DummySupabase())

    project_id = "test_project_123"
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

    saved_rel_path = save_project_asset(project_id, "architecture_overview.png", fake_png)

    assert saved_rel_path == "assets/architecture_overview.png"
    target_file = fake_uploads / project_id / "assets" / "architecture_overview.png"
    assert target_file.exists()
    assert target_file.read_bytes() == fake_png


def test_extract_multiple_figures(sample_pdf_bytes):
    """Verifies extracting multiple distinct figures from a PDF document."""
    from services.pdf_figure_extractor import extract_multiple_figures
    figs = extract_multiple_figures(sample_pdf_bytes, max_figures=3, document_class="beamer")

    assert len(figs) == 2
    assert "system_architecture" in figs[0].clean_filename
    assert "performance_evaluation" in figs[1].clean_filename
    assert figs[0].clean_filename != figs[1].clean_filename
    for f in figs:
        assert len(f.image_bytes) > 500
        assert f.asset_rel_path.startswith("assets/")
        assert "\\begin{frame}" in f.latex_snippet


def test_detect_figure_extraction_intent():
    """Verifies intent detection across different user phrasing, plurals, typos, and optional location anchors."""
    # Explicit anchor
    intent, q, anchor, pos, is_mult = detect_figure_extraction_intent(
        "Add the System Architecture figure from this PDF after Methodology", has_pdf=True
    )
    assert intent is True
    assert "System Architecture" in q
    assert anchor == "Methodology"
    assert pos == "after"
    assert is_mult is False

    # Plural request with typo: "add some figures to this ppt form this pdf"
    intent_plural, q_plural, anchor_plural, pos_plural, is_mult_plural = detect_figure_extraction_intent(
        "add some figures to this ppt form this pdf", has_pdf=True
    )
    assert intent_plural is True
    assert is_mult_plural is True
    assert anchor_plural is None

    # Without mentioning location (semantic placement intended)
    intent2, q2, anchor2, pos2, is_mult2 = detect_figure_extraction_intent(
        "Add the System Architecture figure from this PDF", has_pdf=True
    )
    assert intent2 is True
    assert "System Architecture" in q2
    assert anchor2 is None
    assert pos2 == "after"
    assert is_mult2 is False

    # Figure number query
    intent3, q3, anchor3, _, _ = detect_figure_extraction_intent(
        "Extract Figure 2 from the uploaded document", has_pdf=True
    )
    assert intent3 is True
    assert "Figure 2" in q3
    assert anchor3 is None

    # Negative test (general question)
    intent4, _, _, _, _ = detect_figure_extraction_intent(
        "Can you explain the main contribution of this paper?", has_pdf=True
    )
    assert intent4 is False

    # User requirement: "add these comtents in pdf for fill using pdf or just pdf think it need s a image extartcion and image addition"
    fill_and_content_prompts = [
        "add these comtents in pdf",
        "add these contents in pdf",
        "fill using pdf",
        "for fill using pdf",
        "just pdf",
        "fill this ppt using pdf",
        "fill slides using pdf",
        "add content from this pdf",
        "add these comtents in pdf for fill using pdf or just pdf think it need s a image extartcion and image addition",
    ]
    for prompt in fill_and_content_prompts:
        intent_fc, q_fc, _, _, is_mult_fc = detect_figure_extraction_intent(prompt, has_pdf=True)
        assert intent_fc is True, f"Failed to detect figure intent for: {prompt}"
        assert is_mult_fc is True, f"Expected is_multiple=True for: {prompt}"
        assert q_fc in ("figures", "figure"), f"Expected figures query for: {prompt}, got {q_fc}"


def test_safe_latex_escape():
    """Verifies escaping of LaTeX special characters in captions."""
    from services.pdf_figure_extractor import safe_latex_escape
    assert safe_latex_escape("System Architecture & Pipeline") == r"System Architecture \& Pipeline"
    assert safe_latex_escape(r"Already \& Escaped") == r"Already \& Escaped"
    assert safe_latex_escape("100% Accuracy with $5 cost") == r"100\% Accuracy with \$5 cost"
    assert safe_latex_escape("Figure #1_test") == r"Figure \#1\_test"


def test_slide_targeting_and_deletion():
    """
    Verifies targeting specific slides/pages (e.g. "slide no 3 remove", "last slide",
    "this slide containing this topic") and direct slide deletion.
    """
    from document_index import parse_document_structure, find_target_page, is_explicit_single_target, detect_full_slide_deletion

    beamer_code = r"""\documentclass{beamer}
\begin{document}

\begin{frame}{Title Slide}
Welcome to the presentation.
\end{frame}

\begin{frame}{Introduction}
Background and problem statement.
\end{frame}

\begin{frame}{System Architecture}
Detailed pipeline and component layout.
\end{frame}

\begin{frame}{Evaluation and Results}
Accuracy and benchmark comparisons.
\end{frame}

\begin{frame}{Conclusion}
Final remarks and wrap up.
\end{frame}

\end{document}
"""
    doc_index = parse_document_structure(beamer_code)

    # 1. Slide number queries ("slide no 3", "slide number 2", etc.)
    target_no3 = find_target_page(doc_index, "slide no 3 remove")
    assert target_no3 is not None
    assert doc_index.get_page_by_index(target_no3).title == "System Architecture"

    target_num2 = find_target_page(doc_index, "slide number 2 delete")
    assert target_num2 is not None
    assert doc_index.get_page_by_index(target_num2).title == "Introduction"

    # 2. Position queries ("last slide remove", "remove last slide")
    target_last = find_target_page(doc_index, "last slide remove")
    assert target_last is not None
    assert doc_index.get_page_by_index(target_last).title == "Conclusion"

    # 3. Topic queries with typo ("to this slide conatining System Architecture remove")
    target_topic = find_target_page(doc_index, "to this slide conatining System Architecture remove")
    assert target_topic is not None
    assert doc_index.get_page_by_index(target_topic).title == "System Architecture"

    # 4. is_explicit_single_target
    assert is_explicit_single_target("slide no 3 remove") is True
    assert is_explicit_single_target("last slide remove") is True
    assert is_explicit_single_target("to this slide containing this topic add a diagram") is True
    assert is_explicit_single_target("fix all slides") is False

    # 5. detect_full_slide_deletion
    del_res = detect_full_slide_deletion("slide no 3 remove", doc_index)
    assert del_res is not None
    del_page, del_exp = del_res
    assert del_page.title == "System Architecture"
    assert "System Architecture" in del_exp

    del_last = detect_full_slide_deletion("remove last slide", doc_index)
    assert del_last is not None
    assert del_last[0].title == "Conclusion"

    # Sub-element deletion should NOT be detected as full slide deletion
    del_sub = detect_full_slide_deletion("in slide 3 remove the second bullet", doc_index)
    assert del_sub is None

