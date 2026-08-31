"""
test_pdf_to_latex.py — Unit tests for PDF to LaTeX conversion prompt building,
line spacing preservation, and position drift calibration.
"""

import unittest
from services.pdf_parser import PDFParseResult, PageData, ExtractedImage
from services.pdf_to_latex import (
    compute_typography_metrics,
    build_conversion_prompt,
    resolve_and_inline_all_inputs,
)
from services.layout_verifier import (
    analyze_page_positional_drift,
    calibrate_page_spacing,
)
import pymupdf as fitz


class TestPdfToLatexSpacingAndPosition(unittest.TestCase):
    def setUp(self):
        self.mock_page_layout = {
            "page_number": 1,
            "width": 612.0,
            "height": 792.0,
            "margins": [54.0, 54.0, 54.0, 54.0],
            "columns": 1,
            "elements": [
                {
                    "type": "title",
                    "text": "RESEARCH PAPER TITLE",
                    "alignment": "center",
                    "bbox": [100.0, 60.0, 512.0, 95.0],
                    "font_size": 24.0,
                    "font_weight": "bold",
                    "line_spacing": 1.15,
                },
                {
                    "type": "paragraph",
                    "text": "John Doe, Department of Physics",
                    "alignment": "center",
                    "bbox": [150.0, 110.0, 462.0, 126.0],
                    "font_size": 12.0,
                    "line_spacing": 1.15,
                },
                {
                    "type": "heading",
                    "text": "1. Introduction",
                    "alignment": "left",
                    "bbox": [54.0, 160.0, 200.0, 180.0],
                    "font_size": 14.0,
                    "font_weight": "bold",
                    "line_spacing": 1.2,
                },
                {
                    "type": "paragraph",
                    "text": "This is the first paragraph of the body text.",
                    "alignment": "justified",
                    "bbox": [54.0, 190.0, 558.0, 250.0],
                    "font_size": 11.0,
                    "line_spacing": 1.15,
                },
            ],
        }

        self.mock_page_data = PageData(
            page_number=1,
            width=612.0,
            height=792.0,
            aspect_ratio=612.0 / 792.0,
            text="RESEARCH PAPER TITLE\nJohn Doe, Department of Physics\n1. Introduction\nThis is the first paragraph of the body text.",
            blocks=[
                {"bbox": (100.0, 60.0, 512.0, 95.0), "text": "RESEARCH PAPER TITLE", "type": 0},
                {"bbox": (150.0, 110.0, 462.0, 126.0), "text": "John Doe, Department of Physics", "type": 0},
                {"bbox": (54.0, 160.0, 200.0, 180.0), "text": "1. Introduction", "type": 0},
                {"bbox": (54.0, 190.0, 558.0, 250.0), "text": "This is the first paragraph of the body text.", "type": 0},
            ],
            layout=self.mock_page_layout,
        )

        self.mock_parse_result = PDFParseResult(
            num_pages=1,
            pages=[self.mock_page_data],
            embedded_images=[],
            doc_type_hint="article",
            aspect_ratio_hint="portrait",
            full_text=self.mock_page_data.text,
            page_size_hint="letterpaper",
            layout_data={"document": {}, "pages": [self.mock_page_layout]},
        )

    def test_compute_typography_metrics(self):
        metrics = compute_typography_metrics(self.mock_parse_result)
        self.assertIn("line_spacing", metrics)
        self.assertIn("body_font_size", metrics)
        self.assertIn("par_gap", metrics)
        self.assertEqual(metrics["line_spacing"], 1.15)
        self.assertEqual(metrics["body_font_size"], 11.5)
        self.assertGreater(metrics["par_gap"], 0)

    def test_build_conversion_prompt_includes_positions_and_line_spacing(self):
        prompt = build_conversion_prompt(self.mock_parse_result)
        # Check typography instructions
        self.assertIn("\\usepackage{setspace}", prompt)
        self.assertIn("\\setstretch{1.15}", prompt)
        self.assertIn("\\setlength{\\parskip}", prompt)
        # Check that exact element positions are specified
        self.assertIn("y=60.0pt", prompt)
        self.assertIn("y=110.0pt", prompt)
        self.assertIn("y=160.0pt", prompt)
        self.assertIn("gap_before=", prompt)

    def test_resolve_and_inline_preserves_optional_line_spacing(self):
        raw_files = [
            {
                "path": "main.tex",
                "content": r"\begin{document}Header \\[6pt] Subheader \\[12pt] Body\end{document}",
            }
        ]
        resolved = resolve_and_inline_all_inputs(raw_files, self.mock_parse_result)
        main_content = next(f["content"] for f in resolved if f["path"] == "main.tex")
        # Must preserve \\[6pt] and \\[12pt], NOT replace with \par\vspace
        self.assertIn(r"\\[6pt]", main_content)
        self.assertIn(r"\\[12pt]", main_content)
        self.assertNotIn(r"\par\vspace{6pt}", main_content)
        self.assertNotIn(r"\par\vspace{12pt}", main_content)

    def test_analyze_page_positional_drift_with_mock_pdf(self):
        # Create a small compiled PDF with fitz
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        # Shift text down by 15pt
        page.insert_text((100, 75), "RESEARCH PAPER TITLE", fontsize=24)
        page.insert_text((150, 125), "John Doe, Department of Physics", fontsize=12)
        page.insert_text((54, 175), "1. Introduction", fontsize=14)
        pdf_bytes = doc.write()
        doc.close()

        drift_info = analyze_page_positional_drift(self.mock_page_data, pdf_bytes, page_number=1)
        self.assertFalse(drift_info["page_missing"])
        self.assertIn("matched_drifts", drift_info)
        # Should detect top drift shift
        self.assertGreater(abs(drift_info["top_drift"]), 0.0)

    def test_calibrate_page_spacing_applies_offset_and_scaling(self):
        # Top drift > 3pt
        drift_down = {"top_drift": 12.0, "height_diff": 0.0}
        calibrated = calibrate_page_spacing("Content on page", drift_down)
        self.assertIn(r"\vspace*{-12.0pt}", calibrated)

        # Stretched content > 15pt
        drift_stretched = {"top_drift": 0.0, "height_diff": 40.0}
        calibrated_stretched = calibrate_page_spacing(r"Header\vspace{20pt}Body", drift_stretched)
        self.assertNotIn(r"\vspace{20pt}", calibrated_stretched)
        self.assertIn(r"\vspace{", calibrated_stretched)


if __name__ == "__main__":
    unittest.main()
