# Evaluation report

The repository includes an eight-document labeled corpus so the evaluation command is reproducible:

```powershell
python scripts/evaluate.py
```

The script reports:

* Field-level extraction accuracy
* Documents evaluated
* Success and failure rates
* Total and average extraction time

The corpus covers digital PDFs, scanned-PDF OCR text, image OCR text, XLS/XLSX, CSV, missing fields, and line items. It is still a development evaluation set rather than a statistically representative production dataset; expand it with real labeled files before claiming production accuracy. The dedicated `scripts/benchmark_1000_page_pdf.py` and opt-in `tests/test_large_pdf.py` measure 1,000-page digital PDF handling. Report generated JSON output without rounding away failures.

The automated regression suite is run with:

```powershell
pytest -q
```

The latest expanded suite includes automated OCR and corrupt-PDF tests, plus an opt-in 1,000-page test. Native OCR is exercised by a generated-PNG test when Tesseract is installed.
