import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LARGE_PDF_TESTS") != "1",
    reason="Set RUN_LARGE_PDF_TESTS=1 to run the 1,000-page performance test",
)


def test_1000_page_pdf_processing():
    import fitz

    from app.processor import extract_text

    pdf = fitz.open()
    for page_number in range(1000):
        page = pdf.new_page(width=612, height=792)
        page.insert_text((72, 72), f"Invoice page {page_number + 1}")
    data = pdf.tobytes()
    pdf.close()

    text, pages = extract_text(data, ".pdf")
    assert pages == 1000
    assert "Invoice page 1000" in text
