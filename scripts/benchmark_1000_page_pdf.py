"""Measure extraction time and memory-friendly page handling for a 1,000-page PDF."""
import json
import sys
import time
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.processor import extract_text


def main() -> None:
    pdf = fitz.open()
    for page_number in range(1000):
        page = pdf.new_page(width=612, height=792)
        page.insert_text((72, 72), f"Invoice page {page_number + 1}")
    data = pdf.tobytes()
    pdf.close()

    started = time.perf_counter()
    text, pages = extract_text(data, ".pdf")
    elapsed = time.perf_counter() - started
    print(json.dumps({
        "pages": pages,
        "text_found": "Invoice page 1000" in text,
        "processing_time_seconds": round(elapsed, 3),
        "pdf_size_bytes": len(data),
    }, indent=2))


if __name__ == "__main__":
    main()
