"""
Fact extraction tests for the pdf2latex pipeline (PyMuPDF, no LLM).
"""

from pathlib import Path

import pytest

from pdf2latex.extract import PdfValidationError, extract_document, open_pdf
from tests import pdf2latex_fixtures as fx


def _extract(data: bytes, tmp_path: Path):
    ext, doc = extract_document(data, tmp_path, "assets/pdf_test")
    doc.close()
    return ext


def _spans(ext):
    return [sp for p in ext.pages for ln in p.lines for sp in ln.spans]


def test_rejects_non_pdf():
    with pytest.raises(PdfValidationError):
        open_pdf(b"hello world, not a pdf")
    with pytest.raises(PdfValidationError):
        open_pdf(b"%PDF-1.4 truncated garbage")


def test_page_limit(tmp_path):
    import pymupdf
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page()
    with pytest.raises(PdfValidationError):
        extract_document(doc.tobytes(), tmp_path, "assets/pdf_x", max_pages=2)


def test_text_fonts_sizes_colors(tmp_path):
    ext = _extract(fx.multi_font_pdf(), tmp_path)
    page = ext.pages[0]
    assert (round(page.width), round(page.height)) == fx.A4
    by_text = {sp.text.strip(): sp for sp in _spans(ext)}
    head = by_text["Quarterly Report"]
    assert head.size == pytest.approx(24)
    assert head.bold
    assert head.color == (13, 38, 115)
    assert head.origin == pytest.approx((72, 90), abs=0.01)
    mono = by_text["monospace: x = f(y);"]
    assert "Courier" in mono.font and mono.color == (191, 13, 13)
    assert by_text["Italic emphasis line"].italic
    assert page.lines[0].baseline == pytest.approx(90, abs=0.01)


def test_images_saved_as_page_n_img_k(tmp_path):
    ext = _extract(fx.image_pdf(), tmp_path)
    imgs = ext.pages[0].images
    assert len(imgs) == 2
    first = min(imgs, key=lambda i: i.bbox[0])
    assert first.bbox == pytest.approx((72, 72, 328, 200), abs=0.5)
    assert (first.width_px, first.height_px) == (64, 32)
    names = sorted(Path(i.file).name for i in imgs)
    assert names[0].startswith("page1_img1.") and names[1].startswith("page1_img2.")
    for im in imgs:
        assert im.file.startswith("assets/pdf_test/")
        assert Path(im.file).suffix in (".png", ".jpg")  # pdfLaTeX-compatible
        assert (tmp_path / im.file).exists()


def test_table_rules_and_cells(tmp_path):
    ext = _extract(fx.table_pdf(), tmp_path)
    page = ext.pages[0]
    texts = {ln.text.strip() for ln in page.lines}
    assert {"Metric", "Revenue", "1,450", "21%"} <= texts
    kinds = [d.kind for d in page.drawings]
    assert kinds.count("hrule") == 4 and kinds.count("vrule") == 4
    assert any(d.kind == "rect" and d.fill == (217, 224, 242) for d in page.drawings)
    assert not any(d.complex for d in page.drawings)


def test_complex_vectors_become_figure_rasters(tmp_path):
    ext = _extract(fx.vector_pdf(), tmp_path)
    page = ext.pages[0]
    figures = [i for i in page.images if i.kind == "figure"]
    assert figures, "curves / polygons must be rasterized"
    for f in figures:
        assert Path(f.file).name.startswith("page1_fig")
        assert (tmp_path / f.file).exists()
    # The plain filled rectangle and the dashed horizontal rule stay as shapes for LaTeX
    assert any(d.kind == "rect" and d.fill == (255, 217, 77) for d in page.drawings)
    assert any(d.kind == "hrule" and d.stroke == (51, 77, 204) for d in page.drawings)
    assert not any(d.complex for d in page.drawings if d.rect[2] - d.rect[0] > 40)


def test_two_columns_keep_positions(tmp_path):
    ext = _extract(fx.two_column_pdf(), tmp_path)
    lines = ext.pages[0].lines
    left = [l for l in lines if l.bbox[0] < 280 and l.bbox[1] > 85]
    right = [l for l in lines if l.bbox[0] > 300]
    assert left and right
    assert all(l.bbox[2] <= 290 for l in left)


def test_scanned_page_detection(tmp_path):
    ext = _extract(fx.scanned_pdf(), tmp_path)
    page = ext.pages[0]
    assert page.is_scanned and not page.lines
    assert page.images[0].kind == "scan"
    assert not _extract(fx.multi_font_pdf(), tmp_path / "b").pages[0].is_scanned


def test_scanned_page_uses_ocr_layer(tmp_path):
    page = _extract(fx.scanned_with_ocr_pdf(), tmp_path).pages[0]
    assert page.is_scanned and page.ocr_text
    assert "Quarterly Report" in page.text


def test_multi_page_document(tmp_path):
    ext = _extract(fx.multi_page_pdf(), tmp_path)
    assert [p.number for p in ext.pages] == [1, 2, 3]
    assert "Quarterly Report" in ext.pages[0].text
    assert any(Path(i.file).name.startswith("page2_img") for i in ext.pages[1].images)
    assert "Revenue" in ext.pages[2].text


def test_margins_from_content(tmp_path):
    ext = _extract(fx.table_pdf(), tmp_path)
    left, top, right, bottom = ext.pages[0].margins
    assert left == pytest.approx(72, abs=1.5)
    assert top == pytest.approx(100, abs=1.5)
