import asyncio
import shutil
from io import BytesIO

import pymupdf
import pytest
from PIL import Image

from pdf2latex.editable.gates import _asset_gate
from pdf2latex.editable.measure import figure_position
from pdf2latex.editable.pagefit import async_sync_compile, finish
from pdf2latex.editable.run import EditCtx, assemble
from pdf2latex.extract import extract_document
from pdf2latex.preamble import referenced_files


def _source_document():
    with pymupdf.open() as pdf:
        for number in range(1, 4):
            page = pdf.new_page(width=595, height=842)
            page.insert_text((46, 34), "REFERENCE GUIDE", fontsize=8, fontname="hebo")
            page.draw_line((46, 42), (548, 42), color=(0.6, 0.7, 0.8), width=1)
            page.insert_text((520, 808), f"Page {number}", fontsize=8)
            if number == 1:
                page.insert_text((62, 182), "Reference guide", fontsize=27, fontname="hebo")
                page.insert_text((62, 222), "Reflowable documents", fontsize=24, fontname="hebo")
                page.draw_line((62, 246), (532, 246), color=(0.2, 0.45, 0.65), width=2)
                page.insert_text((62, 270), "A short introduction to the guide.", fontsize=9.5)
            else:
                page.insert_text((62, 80), "Reference index", fontsize=14, fontname="hebo")
                for entry in range(10):
                    page.insert_text(
                        (62, 105 + 13 * entry), f"Ref {entry:02d} | Volume A | A reference description.",
                        fontsize=9.5,
                    )
        return pdf.tobytes()


def _baseline(page, label):
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = line["spans"]
            if "".join(span["text"] for span in spans).startswith(label):
                return spans[0]["origin"][1]
    raise AssertionError(f"Missing rendered line {label!r}")


@pytest.mark.skipif(not shutil.which("pdflatex"), reason="pdfLaTeX is required for layout checks")
def test_editable_cover_rules_and_index_remain_in_place(tmp_path):
    extract, source = extract_document(_source_document(), tmp_path, "assets/test", 3)
    with source:
        tex, model, line_map = assemble(extract, source)
        tex, _, compiled, _ = asyncio.run(
            finish(EditCtx(tmp_path), extract, model, tex, line_map, async_sync_compile)
        )
        assert compiled is not None
        assert r"\newline" in tex
        assert r"\includegraphics" not in tex

        with pymupdf.open(stream=compiled, filetype="pdf") as output:
            assert len(output) == len(source)
            assert _baseline(output[0], "Reference guide") == pytest.approx(182, abs=8)

            rules = output[0].get_drawings()
            for source_rule in source[0].get_drawings():
                candidates = [
                    rule for rule in rules
                    if (rule.get("fill") or rule.get("color"))
                    == pytest.approx(source_rule["color"], abs=0.01)
                ]
                assert candidates
                match = candidates[0]["rect"]
                assert match.width == pytest.approx(source_rule["rect"].width, abs=2)

            for entry in range(10):
                label = f"Ref {entry:02d}"
                assert _baseline(output[1], label) == pytest.approx(_baseline(source[1], label), abs=8)


def _insert_graphic(page, box, color, size):
    with BytesIO() as image:
        Image.new("RGB", size, color).save(image, format="PNG")
        page.insert_image(box, stream=image.getvalue())


@pytest.mark.skipif(not shutil.which("pdflatex"), reason="pdfLaTeX is required for layout checks")
def test_editable_keeps_each_unnumbered_pages_artwork(tmp_path):
    logo_box = pymupdf.Rect(258, 24, 338, 64)
    body_box = pymupdf.Rect(480, 161, 520, 201)
    logo_colors = [(32, 96, 160), (128, 36, 64), None, (27, 120, 65)]
    with pymupdf.open() as fixture:
        for number, color in enumerate(logo_colors, 1):
            page = fixture.new_page(width=595, height=842)
            if color is not None:
                _insert_graphic(page, logo_box, color, (80, 40))
            if number != 4:
                page.insert_text(
                    (62, 125), f"Receipt {number}                         Document reference",
                    fontsize=11,
                )
                page.insert_text(
                    (62, 240), "Item description and amount appear in the original document.",
                    fontsize=10,
                )
                _insert_graphic(page, body_box, (24, 45, 80), (30, 30))
        extract, source = extract_document(fixture.tobytes(), tmp_path, "assets/artwork", 4)

    with source:
        tex, model, line_map = assemble(extract, source)
        assert not model.furniture.page_numbers
        assert set(model.furniture.images_by_page) == {1, 2, 4}
        tex, _, compiled, _ = asyncio.run(
            finish(EditCtx(tmp_path), extract, model, tex, line_map, async_sync_compile)
        )
        assert compiled is not None
        assert _asset_gate(extract, model, tex, tmp_path)["ok"]
        logos = {img.file for images in model.furniture.images_by_page.values() for img in images}
        assert logos <= set(referenced_files(tex))
        placements = figure_position(model, compiled, tmp_path)
        logo_placements = [item for item in placements["items"] if item["file"] in logos]
        assert len(logo_placements) == 3
        for placement in logo_placements:
            assert placement["ok"]
            assert placement["dx"] == pytest.approx(0, abs=1)
            assert placement["dy"] == pytest.approx(0, abs=1)

        with pymupdf.open(stream=compiled, filetype="pdf") as output:
            assert len(output) == len(source)
            for page, color in zip(output, logo_colors):
                pixel = page.get_pixmap(clip=pymupdf.Rect(280, 40, 281, 41)).pixel(0, 0)
                assert pixel == pytest.approx(color or (255, 255, 255), abs=2)
