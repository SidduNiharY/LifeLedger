from io import BytesIO

import pikepdf
import pytest
from fpdf import FPDF

from app.sandbox.pdf import PdfLockedError, pdf_to_markdown, unlock_pdf


def make_pdf(*lines: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    for line in lines:
        pdf.cell(0, 10, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def encrypt(data: bytes, password: str) -> bytes:
    out = BytesIO()
    with pikepdf.open(BytesIO(data)) as p:
        p.save(out, encryption=pikepdf.Encryption(owner="owner-pw", user=password))
    return out.getvalue()


BILL = make_pdf("BESCOM Electricity Bill", "Amount Due: Rs. 1,250.50", "Due Date: 20-11-2026")


def test_unlock_with_matching_password():
    with pikepdf.open(BytesIO(unlock_pdf(encrypt(BILL, "secret123"), ["wrong", "secret123"]))) as p:
        assert not p.is_encrypted


def test_locked_with_no_matching_password():
    with pytest.raises(PdfLockedError):
        unlock_pdf(encrypt(BILL, "secret123"), ["wrong"])


def test_unencrypted_passes_through():
    with pikepdf.open(BytesIO(unlock_pdf(BILL, []))) as p:
        assert len(p.pages) == 1


@pytest.mark.slow
def test_pdf_to_markdown_reads_text():
    md = pdf_to_markdown(BILL)
    assert "1,250.50" in md and "20-11-2026" in md
