# AI-Powered Document Intelligence System

Submission for the Senior AI Engineer assessment. The application ingests PDF, image, XLSX and CSV files, extracts invoice fields without inventing unknown values, validates financial consistency, stores processing history, and exposes a review/search UI.

The default extractor is deterministic and runs offline; it does not call an LLM. See [requirements review](./REQUIREMENTS_REVIEW.md) for the implemented scope and [verification](./VERIFICATION.md) for measured checks.

## Run locally

Use Python 3.12 or newer and install Tesseract for image/scanned-PDF OCR.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. API docs are available at `/docs`.

This app runs on FastAPI/Uvicorn; the VS Code JSON Server extension is not needed.

If port 8000 is already occupied, use `uvicorn app.main:app --port 8001` and open `http://127.0.0.1:8001`.

## Review and delete

1. Choose files and click **Upload documents**; wait for processing to complete.
2. Click a filename to open its extracted invoice and validation results. Compare values against your original document, edit the JSON and click **Save correction**.
3. Use **Compare** with another completed document to check differences, or **Retry** for a failed upload.
4. Use the row's **Delete** button and confirm to remove the app's uploaded copy, extracted invoice and history. The original file on your computer is unaffected. Processing jobs must finish before deletion.

The field-completeness percentage measures how many required fields were found; it is not an accuracy guarantee.

## OCR and storage

PDF text extraction uses `pypdf`; scanned PDFs and images use Tesseract via `pytesseract` after rendering; XLSX uses `openpyxl`; legacy XLS uses `xlrd`. The Docker image installs Tesseract automatically. On Windows, install Tesseract (for example with `winget install UB-Mannheim.TesseractOCR`) and set `TESSERACT_CMD` to the executable path if it is not on `PATH`. OCR failures are reported as failed jobs rather than silently producing incorrect data. Set `DATA_DIR`, `DB_PATH`, `MAX_UPLOAD_BYTES`, and `TESSERACT_CMD` to configure deployment.

## API

* `POST /api/documents` — multipart upload of one or more files; returns queued IDs.
* `GET /api/documents?q=...` — keyword search over filenames, extracted text and JSON.
* `GET /api/search?q=...` — deterministic vector-style token search over indexed invoice metadata. This offline adapter is auditable and dependency-free; replace it with an embedding provider and pgvector/OpenSearch for production semantic similarity.
* `GET /api/documents/{id}` — status, extracted invoice, confidence and validation errors.
* `PATCH /api/documents/{id}/invoice` — save a human correction.
* `DELETE /api/documents/{id}` — permanently delete the uploaded copy and its extracted data/history; queued or processing documents must finish first.
* `POST /api/documents/{id}/reprocess` — retry a failed upload.
* `GET /api/documents/{left_id}/compare/{right_id}` — compare two processed documents for cross-document verification.

The document detail response also includes persisted `progress`, `stage`, `history`, and `page_count` values. The web interface shows progress, exposes retry for failed jobs, and provides a comparison control in the review panel.

Set `DOCUMENT_API_KEY` to require `X-API-Key` authentication. Set `ALLOWED_ORIGINS` to a comma-separated allowlist, and use `X-User-Role: admin` or `reviewer` for protected correction/reprocessing operations. Uploads are checked against configured size/type limits and a basic malware-signature scan; production deployments should add an AV engine such as ClamAV.

When a key is configured, the browser displays a connection form. The entered key is held only in page memory and must be entered again after reload. A shared-key holder can choose a role header; use trusted identity-based roles for production access control. The same access rules apply to deletion.

Validation also checks malformed and negative monetary values, line-item quantity × unit-price arithmetic, identical file hashes, duplicate invoice numbers, and line-item differences during cross-document comparison.

## Tests and evaluation

```powershell
pytest -q
python scripts/evaluate.py
python scripts/benchmark_1000_page_pdf.py
```

The test suite covers deterministic extraction, no-invention behavior, financial validation, API validation, OCR, corrupted input, and unsupported input paths. The labeled evaluation corpus under `evaluation/labeled.jsonl` covers digital PDF, scanned-PDF OCR text, image OCR text, XLSX, XLS, CSV, missing fields, and line items. Run `python scripts/evaluate.py` from the project root to produce measured field accuracy, processing time, success rate, failure rate, and source-type counts; it never reports fabricated accuracy. Run the dedicated 1,000-page test with `RUN_LARGE_PDF_TESTS=1 pytest -q tests/test_large_pdf.py`.

To run every test, including the large PDF check, in PowerShell:

```powershell
$env:RUN_LARGE_PDF_TESTS = "1"
python -m pytest -q
```

Tests use a temporary database and upload directory. Optional browser checks also start an isolated server and exercise upload, correction, search, comparison, failure/retry, and mobile layout:

```powershell
python -m pip install playwright
python -m playwright install chromium
python scripts/check_browser.py
python scripts/check_browser.py --authenticated
```

On Windows, the app detects Tesseract in its standard `Program Files\Tesseract-OCR` location. `TESSERACT_CMD` takes precedence when explicitly configured.

## Docker and GitHub

```sh
docker build -t document-intelligence .
docker run --rm -p 8000:8000 -v document-data:/app/data document-intelligence
```

The named volume preserves uploads and SQLite records when the container is replaced. `/health` is the health endpoint. For an external deployment, configure `DOCUMENT_API_KEY`, HTTPS, and the allowed origins, and retain a persistent data volume.

The GitHub workflow runs the full suite on Python 3.12 and 3.14, checks both browser access modes, and builds/smoke-tests the Docker image. GitHub publishing stores the source; a live FastAPI service needs a Python/container host rather than GitHub Pages.

## Design decisions

The processing boundary is asynchronous (`BackgroundTasks` + `asyncio.to_thread`) so OCR and parsing never block an API request. SQLite is the default zero-configuration store; its tables separate metadata, extracted text, invoice JSON, validation errors and processing history and can be migrated to PostgreSQL. Search is deliberately transparent keyword filtering; a production deployment can add pgvector/OpenSearch embeddings behind the same endpoint. See [ARCHITECTURE.md](./ARCHITECTURE.md).

## AI use disclosure

The extraction contract is deterministic and auditable by default. A production LLM adapter should receive only extracted text, require JSON schema-constrained output, preserve field-level confidence and never fill missing values. The proposed prompt is in [PROMPTS.md](./PROMPTS.md). This repository discloses AI-assisted development and keeps validation independent of the model.
