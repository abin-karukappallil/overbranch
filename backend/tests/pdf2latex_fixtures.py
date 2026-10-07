"""
Programmatic PDF fixtures for the importer tests.

``ticket_pdf`` is the regression case from the IRCTC e-ticket screenshots: a
Calibri-style (Carlito) page with bold labels over regular values, values that
end exactly at the right border, long unbreakable IDs and small print — the
layout whose bold text came out regular and whose right column ran past the
border when Calibri was set in Helvetica.
"""

from typing import Optional

import pymupdf

from latex_layout.metrics import kpsewhich

PAGE_W, PAGE_H = 595.0, 842.0
LEFT, RIGHT = 50.0, 545.0


def _fonts(page: "pymupdf.Page") -> tuple:
    """(regular, bold) font names registered on the page: Carlito if installed, else Helvetica."""
    reg = kpsewhich("Carlito-Regular.ttf")
    bold = kpsewhich("Carlito-Bold.ttf")
    if reg and bold:
        page.insert_font(fontname="Carlito", fontfile=reg)
        page.insert_font(fontname="Carlito-Bold", fontfile=bold)
        return "Carlito", "Carlito-Bold"
    return "helv", "hebo"


def _width(text: str, font: str, size: float) -> float:
    if font.startswith("Carlito"):
        return pymupdf.Font(fontfile=kpsewhich(f"{font}.ttf") or kpsewhich("Carlito-Regular.ttf")).text_length(text, size)
    return pymupdf.get_text_length(text, fontname=font, fontsize=size)


def _right(page, y: float, text: str, font: str, size: float, x1: float = RIGHT, color=(0, 0, 0)) -> None:
    """Text that ends exactly at x1 (a straight right edge)."""
    page.insert_text((x1 - _width(text, font, size), y), text, fontname=font, fontsize=size, color=color)


def ticket_pdf(fake_bold: bool = False) -> bytes:
    """
    ``fake_bold``: bold runs are drawn the way the real IRCTC slip draws them —
    the regular font printed twice, a fraction of a point apart — instead of
    with a bold font.
    """
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    reg, bold = _fonts(page)
    if fake_bold:
        real_insert = page.insert_text

        def overprint(point, text, fontname=None, **kw):
            if fontname == bold:
                real_insert(point, text, fontname=reg, **kw)
                return real_insert((point[0] + 0.35, point[1]), text, fontname=reg, **kw)
            return real_insert(point, text, fontname=fontname, **kw)

        page.insert_text = overprint
    blue = (0.16, 0.38, 0.65)

    page.insert_text((200, 70), "Electronic Reservation Slip (ERS)", fontname=bold, fontsize=11)
    page.insert_text((372, 70), "-Normal User", fontname=reg, fontsize=7)
    page.draw_line((LEFT, 80), (RIGHT, 80), color=(0, 0, 0), width=0.8)

    y = 110
    for label, x in (("Booked from", LEFT), ("Boarding At", 250), ("To", 480)):
        page.insert_text((x, y), label, fontname=bold, fontsize=9)
    y += 14
    page.insert_text((LEFT, y), "ERNAKULAM JN (ERS)", fontname=reg, fontsize=9)
    page.insert_text((250, y), "ERNAKULAM JN (ERS)", fontname=bold, fontsize=9)
    _right(page, y, "MANGALURU CNTL (MAQ)", reg, 9)
    y += 12
    page.insert_text((LEFT, y), "Start Date* 25-Sept-2026", fontname=reg, fontsize=9)
    page.insert_text((250, y), "Departure* 23:30 25-Sept-2026", fontname=bold, fontsize=9)
    _right(page, y, "Arrival* 08:15 26-Sept-2026", reg, 9)

    y += 24
    for label, x in (("PNR", LEFT + 20), ("Train No./Name", 250), ("Class", 490)):
        page.insert_text((x, y), label, fontname=bold, fontsize=9)
    y += 13
    page.insert_text((LEFT + 10, y), "4654771990", fontname=bold, fontsize=10, color=blue)
    page.insert_text((235, y), "16604/MAVELI EXPRESS", fontname=bold, fontsize=10, color=blue)
    _right(page, y, "SLEEPER CLASS (SL)", bold, 10, color=blue)

    y += 30
    page.insert_text((LEFT, y), "Passenger Details", fontname=bold, fontsize=11)
    y += 15
    for label, x in (("# Name", LEFT), ("Age", 200), ("Gender", 240), ("Booking Status", 300), ("Current Status", 430)):
        page.insert_text((x, y), label, fontname=bold, fontsize=8.5)
    y += 12
    page.insert_text((LEFT, y), "1. JACOB PRASANTH", fontname=reg, fontsize=8.5)
    page.insert_text((300, y), "CNF/S5/56/SIDE UPPER", fontname=reg, fontsize=8.5)
    _right(page, y, "CNF/S5/56/SIDE UPPER", reg, 8.5)

    y += 30
    page.insert_text((LEFT, y), "Transaction ID: 100006736282004", fontname=bold, fontsize=9)
    y += 13
    page.insert_text((LEFT, y), "IR recovers only 57% of cost of travel on an average.", fontname=reg, fontsize=9)

    y += 26
    page.insert_text((LEFT, y), "Indian Railways GST Details:", fontname=bold, fontsize=8)
    y += 13
    page.insert_text((LEFT, y), "Invoice Number:", fontname=reg, fontsize=8)
    page.insert_text((180, y), "PS26465477199011", fontname=reg, fontsize=8)
    page.insert_text((300, y), "Address:", fontname=reg, fontsize=8)
    _right(page, y, "Indian Railways New Delhi", reg, 8)
    y += 13
    page.insert_text((LEFT, y), "SAC Code:", fontname=reg, fontsize=8)
    page.insert_text((180, y), "996421", fontname=reg, fontsize=8)
    page.insert_text((300, y), "GSTIN:", fontname=reg, fontsize=8)
    _right(page, y, "07AAAGM0289C1ZL", reg, 8)
    y += 13
    page.insert_text((LEFT, y), "Total Tax:", fontname=bold, fontsize=8)
    page.insert_text((180, y), "0.0", fontname=bold, fontsize=8)

    y += 26
    page.insert_text((LEFT, y),
                     "* The printed Departure and Arrival Times are liable to change. Please Check correct",
                     fontname=bold, fontsize=8)
    y += 11
    page.insert_text((LEFT, y), "departure, arrival from Railway Station Enquiry or Dial 139 or SMS RAIL to 139.",
                     fontname=bold, fontsize=8)
    data = doc.tobytes()
    doc.close()
    return data


def synthetic_bold_pdf() -> bytes:
    """A regular font drawn with fill+stroke (render mode 2): bold without a bold font."""
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    page.insert_text((72, 100), "Fake bold heading", fontname="helv", fontsize=12, render_mode=2, border_width=0.04)
    page.insert_text((72, 130), "Ordinary body text", fontname="helv", fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data
