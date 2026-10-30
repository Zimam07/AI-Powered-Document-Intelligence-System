import pytest

from app.processor import extract_text
from app.config import TESSERACT_CMD


@pytest.mark.skipif(
    not TESSERACT_CMD,
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


@pytest.mark.skipif(not TESSERACT_CMD, reason="Tesseract is not installed")
@pytest.mark.parametrize("suffix", [".jpg", ".jpeg", ".png", ".tif", ".tiff", ".pdf"])
def test_image_formats_and_scanned_pdf(suffix):
    import io
    import fitz
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1200, 250), "white")
    ImageDraw.Draw(image).text((40, 70), "Invoice Number: SCAN-001", fill="black",
                              font=ImageFont.load_default(size=36))
    stream = io.BytesIO()
    image.save(stream, format={".jpg": "JPEG", ".jpeg": "JPEG", ".tif": "TIFF", ".tiff": "TIFF"}.get(suffix, "PNG"))
    data = stream.getvalue()
    if suffix == ".pdf":
        with fitz.open() as pdf:
            page = pdf.new_page(width=1200, height=250)
            page.insert_image(page.rect, stream=data)
            data = pdf.tobytes()
    text, pages = extract_text(data, suffix)
    assert pages == 1
    assert "SCAN-001" in text


@pytest.mark.skipif(not TESSERACT_CMD, reason="Tesseract is not installed")
def test_multipage_tiff_extracts_every_page():
    import io
    from PIL import Image, ImageDraw, ImageFont

    frames = []
    for number in (1, 2):
        frame = Image.new("RGB", (1000, 200), "white")
        ImageDraw.Draw(frame).text((40, 60), f"Invoice Page {number}", fill="black",
                                  font=ImageFont.load_default(size=36))
        frames.append(frame)
    stream = io.BytesIO()
    frames[0].save(stream, format="TIFF", save_all=True, append_images=frames[1:])
    text, count = extract_text(stream.getvalue(), ".tiff")
    assert count == 2
    assert "Invoice Page 1" in text and "Invoice Page 2" in text
