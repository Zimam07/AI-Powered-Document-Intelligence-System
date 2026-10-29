import os

import pytest

from app.processor import extract_text


@pytest.mark.skipif(
    not os.getenv("TESSERACT_CMD") and not os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    reason="Tesseract is not installed",
)
def test_png_ocr_extracts_visible_text():
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (900, 180), "white")
    ImageDraw.Draw(image).text((30, 60), "Invoice Number: OCR-TEST-001", fill="black")
    from io import BytesIO

    stream = BytesIO()
    image.save(stream, format="PNG")
    text, pages = extract_text(stream.getvalue(), ".png")
    assert pages == 1
    assert "OCR-TEST-001" in text


def test_corrupt_pdf_fails_explicitly():
    with pytest.raises(ValueError, match="PDF extraction failed"):
        extract_text(b"not a valid PDF", ".pdf")
