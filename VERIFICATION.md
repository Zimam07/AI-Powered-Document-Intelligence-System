# Final local verification — 2026-10-31

Reviewed against the repository requirements; the feature-to-evidence mapping and explicit limitations are in [REQUIREMENTS_REVIEW.md](./REQUIREMENTS_REVIEW.md).

## Results

- Full suite with `RUN_LARGE_PDF_TESTS=1`: **66 passed**, no skipped tests, in 18.94 seconds on Python 3.14 / Windows. One upstream Starlette/httpx deprecation warning remains.
- `python scripts/check_browser.py`: Chromium passed upload, empty selection, invalid JSON, saved corrections after reload, validation, comparison, failure/retry, search, mobile layout, and confirmed/canceled deletion. No uncaught JavaScript errors.
- `python scripts/check_browser.py --authenticated`: the same browser workflows passed with API-key access, including reconnecting after reload.
- `python scripts/evaluate.py`: **64/64 labeled fields** matched across eight text fixtures. This measures extraction from supplied text, not production OCR accuracy.
- `python scripts/benchmark_1000_page_pdf.py`: **1,000 pages**, final-page text found, 0.571 seconds for a generated 359,031-byte digital PDF.
- `python -m pip check`: no broken requirements.
- `git diff --check`: passed.
- Repository credential-pattern scan found no matching credentials. Local uploads, SQLite files, logs and environment files are excluded from publication.

The full suite covers real XLS/XLSX/digital PDF, image formats and scanned PDF OCR, multi-page TIFF, partial CSV tables, missing/ambiguous values, malformed corrections, financial arithmetic, duplicates, search, correction, comparison, retry, deletion, authentication, upload limits, CORS and rate limiting. Evaluation regression tests ensure failed documents remain in the accuracy denominator.

Tests use temporary databases and uploads. The legacy XLS fixture contains fictional invoice data. No existing user document was deleted during verification.

## Automated checks

The GitHub Actions workflow runs the full suite on Python 3.12 and 3.14 with Tesseract installed, browser checks in both access modes, and a Docker build/start/health check. Docker is unavailable on the local Windows environment, so its build is verified by the GitHub container job rather than claimed as a local result. See the repository Actions page for the result of each published commit.

## Practical limits

The app uses label-based extraction, one invoice per file, token search and in-process jobs. The confidence API field represents completeness. The small fixture score and digital-PDF benchmark do not establish accuracy on arbitrary layouts or throughput for 1,000 scanned pages. See the requirements review before adapting the app for multi-user production hosting.
