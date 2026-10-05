"""
Programmatically generated fixture PDFs for the pdf2latex test suites (no binaries in git).
"""

import pymupdf

A4 = (595, 842)


def multi_font_pdf() -> bytes:
    """Text in several fonts, sizes and colors."""
    doc = pymupdf.open()
    p = doc.new_page(width=A4[0], height=A4[1])
    p.insert_text((72, 90), "Quarterly Report", fontname="hebo", fontsize=24, color=(0.05, 0.15, 0.45))
    p.insert_text((72, 130), "Body text set in Times Roman at eleven points.", fontname="tiro", fontsize=11)
    p.insert_text((72, 150), "Italic emphasis line", fontname="tiit", fontsize=11, color=(0.4, 0.4, 0.4))
    p.insert_text((72, 175), "monospace: x = f(y);", fontname="cour", fontsize=10, color=(0.75, 0.05, 0.05))
    p.insert_text((72, 200), "Special chars: 50% & $5 #1 {a_b}", fontname="helv", fontsize=12)
    return doc.tobytes()


def image_pdf() -> bytes:
    """An opaque RGB image and an image with an alpha channel."""
    doc = pymupdf.open()
    p = doc.new_page(width=A4[0], height=A4[1])
    rgb = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 64, 32), 0)
    rgb.set_rect(rgb.irect, (200, 40, 40))
    rgb.set_rect(pymupdf.IRect(0, 0, 32, 32), (40, 40, 200))
    p.insert_image(pymupdf.Rect(72, 72, 328, 200), pixmap=rgb)
    rgba = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 32, 32), 1)
    rgba.set_rect(rgba.irect, (20, 160, 60, 128))
    p.insert_image(pymupdf.Rect(360, 72, 460, 172), pixmap=rgba)
    p.insert_text((72, 230), "Figure 1: Two images", fontname="helv", fontsize=10)
    return doc.tobytes()


def table_pdf() -> bytes:
    """A 3x3 table with full borders and a shaded header row."""
    doc = pymupdf.open()
    p = doc.new_page(width=A4[0], height=A4[1])
    x0, y0, cw, rh = 72, 100, 140, 24
    p.draw_rect(pymupdf.Rect(x0, y0, x0 + 3 * cw, y0 + rh), color=None, fill=(0.85, 0.88, 0.95))
    for r in range(4):
        p.draw_line((x0, y0 + r * rh), (x0 + 3 * cw, y0 + r * rh), color=(0, 0, 0), width=0.8)
    for c in range(4):
        p.draw_line((x0 + c * cw, y0), (x0 + c * cw, y0 + 3 * rh), color=(0, 0, 0), width=0.8)
    rows = [["Metric", "Q1", "Q2"], ["Revenue", "1,200", "1,450"], ["Margin", "18%", "21%"]]
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            p.insert_text((x0 + c * cw + 6, y0 + r * rh + 16), cell, fontname="hebo" if r == 0 else "helv", fontsize=10)
    return doc.tobytes()


def vector_pdf() -> bytes:
    """Bezier curve, filled rectangle, dashed line, circle and polygon."""
    doc = pymupdf.open()
    p = doc.new_page(width=A4[0], height=A4[1])
    p.draw_rect(pymupdf.Rect(72, 72, 272, 172), color=(0.1, 0.1, 0.1), fill=(1.0, 0.85, 0.3), width=2)
    p.draw_line((72, 220), (520, 220), color=(0.2, 0.3, 0.8), width=1.5, dashes="[6 3] 0")
    p.draw_bezier((72, 400), (180, 260), (320, 520), (520, 380), color=(0.0, 0.55, 0.2), width=3)
    p.draw_circle((420, 120), 50, color=(0.6, 0.0, 0.6), fill=(0.9, 0.8, 0.95), width=1)
    p.draw_polyline([(100, 600), (200, 500), (300, 600), (100, 600)], color=(0, 0, 0), fill=(0.7, 0.9, 0.7), closePath=True)
    return doc.tobytes()


LOREM = ("Structured extraction keeps fonts, sizes and colors exact. "
         "Every glyph is positioned at its measured origin so the layout matches the source page. ") * 6


def two_column_pdf() -> bytes:
    doc = pymupdf.open()
    p = doc.new_page(width=A4[0], height=A4[1])
    p.insert_text((72, 70), "Two Column Article", fontname="tibo", fontsize=18)
    p.insert_textbox(pymupdf.Rect(72, 90, 287, 760), LOREM, fontname="tiro", fontsize=10)
    p.insert_textbox(pymupdf.Rect(308, 90, 523, 760), LOREM, fontname="tiro", fontsize=10)
    return doc.tobytes()


def scanned_pdf() -> bytes:
    """A page that is just an image (no text layer)."""
    src = pymupdf.open(stream=multi_font_pdf(), filetype="pdf")
    pix = src[0].get_pixmap(dpi=100)
    doc = pymupdf.open()
    p = doc.new_page(width=A4[0], height=A4[1])
    p.insert_image(p.rect, pixmap=pix)
    return doc.tobytes()


def scanned_with_ocr_pdf() -> bytes:
    """A scanned page carrying an invisible OCR text layer (render mode 3)."""
    data = scanned_pdf()
    doc = pymupdf.open(stream=data, filetype="pdf")
    doc[0].insert_text((72, 90), "Quarterly Report", fontname="helv", fontsize=24, render_mode=3)
    return doc.tobytes()


def multi_page_pdf() -> bytes:
    """Three pages mixing colors/sizes, an image and a table."""
    doc = pymupdf.open()
    for src in (multi_font_pdf(), image_pdf(), table_pdf()):
        doc.insert_pdf(pymupdf.open(stream=src, filetype="pdf"))
    return doc.tobytes()


def margin_notes_pdf() -> bytes:
    """A title page with a right-hand annotation column drawn AFTER the body, as Word emits it."""
    doc = pymupdf.open()
    pg = doc.new_page(width=595, height=842)
    body = [(150, "<PREPARE THE SAME DOCUMENT IN LATEX>", 11, (0, 0, 0), "Times-Roman"),
            (175, "TITLE OF THE SEMINAR", 13, (0, 0, 1), "Times-Bold"),
            (210, "Seminar Report", 11, (0, 0, 0), "Times-Bold"),
            (245, "Submitted in partial fulfillment", 10, (0, 0, 0), "Times-Italic"),
            (285, "Bachelor of Technology", 11, (0, 0, 0), "Times-Bold"),
            (315, "Computer Science and Engineering", 10, (0, 0, 1), "Times-Bold"),
            (375, "ABCD", 11, (0, 0, 1), "Times-Bold")]
    for y, t, sz, c, f in body:
        w = pymupdf.get_text_length(t, fontname=f, fontsize=sz)
        pg.insert_text(((595 - w) / 2, y), t, fontsize=sz, fontname=f, color=c)
    notes = [(160, "Blue colour indicates matter, which"), (170, "may require modifications. The"),
             (180, "colour shall be changed to black after"), (190, "editing this template."),
             (205, "Red colour indicates instructions,"), (215, "which shall be followed strictly."),
             (370, "Name of student and Register"), (380, "no (Preferably in capital letter)")]
    for y, t in notes:
        pg.insert_text((400, y), t, fontsize=6, fontname="Times-Roman", color=(1, 0, 0))
    return doc.tobytes()
