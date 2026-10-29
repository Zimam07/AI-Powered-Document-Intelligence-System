# AI-Powered Document Intelligence System

Submission for the Senior AI Engineer assessment. The application ingests PDF, image, XLSX and CSV files, extracts invoice fields without inventing unknown values, validates financial consistency, stores processing history, and exposes a review/search UI.

## Run locally

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. API docs are available at `/docs`.

PDF text extraction uses `pypdf`; scanned PDFs and images use Tesseract via `pytesseract` after rendering; XLSX uses `openpyxl`; legacy XLS uses `xlrd`. The Docker image installs Tesseract automatically. On Windows, install Tesseract (for example with `winget install UB-Mannheim.TesseractOCR`) and set `TESSERACT_CMD` to the executable path if it is not on `PATH`. OCR failures are reported as failed jobs rather than silently producing incorrect data. Set `DATA_DIR`, `DB_PATH`, `MAX_UPLOAD_BYTES`, and `TESSERACT_CMD` to configure deployment.

## API

* `POST /api/documents` — multipart upload of one or more files; returns queued IDs.
* `GET /api/documents?q=...` — keyword search over filenames, extracted text and JSON.
* `GET /api/search?q=...` — deterministic vector-style token search over indexed invoice metadata. This offline adapter is auditable and dependency-free; replace it with an embedding provider and pgvector/OpenSearch for production semantic similarity.
* `GET /api/documents/{id}` — status, extracted invoice, confidence and validation errors.
* `PATCH /api/documents/{id}/invoice` — save a human correction.
* `POST /api/documents/{id}/reprocess` — retry a failed upload.
* `GET /api/documents/{left_id}/compare/{right_id}` — compare two processed documents for cross-document verification.

The document detail response also includes persisted `progress`, `stage`, `history`, and `page_count` values. The web interface shows progress, exposes retry for failed jobs, and provides a comparison control in the review panel.

Set `DOCUMENT_API_KEY` to require `X-API-Key` authentication. Set `ALLOWED_ORIGINS` to a comma-separated allowlist, and use `X-User-Role: admin` or `reviewer` for protected correction/reprocessing operations. Uploads are checked against configured size/type limits and a basic malware-signature scan; production deployments should add an AV engine such as ClamAV.

Validation also checks malformed and negative monetary values, line-item quantity × unit-price arithmetic, identical file hashes, duplicate invoice numbers, and line-item differences during cross-document comparison.

## Tests and evaluation

```powershell
pytest -q
python scripts/evaluate.py
python scripts/benchmark_1000_page_pdf.py
```

The test suite covers deterministic extraction, no-invention behavior, financial validation, API validation, OCR, corrupted input, and unsupported input paths. The labeled evaluation corpus under `evaluation/labeled.jsonl` covers digital PDF, scanned-PDF OCR text, image OCR text, XLSX, XLS, CSV, missing fields, and line items. Run `python scripts/evaluate.py` from the project root to produce measured field accuracy, processing time, success rate, failure rate, and source-type counts; it never reports fabricated accuracy. Run the dedicated 1,000-page test with `RUN_LARGE_PDF_TESTS=1 pytest -q tests/test_large_pdf.py`.

## Design decisions

The processing boundary is asynchronous (`BackgroundTasks` + `asyncio.to_thread`) so OCR and parsing never block an API request. SQLite is the default zero-configuration store; its tables separate metadata, extracted text, invoice JSON, validation errors and processing history and can be migrated to PostgreSQL. Search is deliberately transparent keyword filtering; a production deployment can add pgvector/OpenSearch embeddings behind the same endpoint. See [ARCHITECTURE.md](./ARCHITECTURE.md).

## AI use disclosure

The extraction contract is deterministic and auditable by default. A production LLM adapter should receive only extracted text, require JSON schema-constrained output, preserve field-level confidence and never fill missing values. The proposed prompt is in [PROMPTS.md](./PROMPTS.md). This repository discloses AI-assisted development and keeps validation independent of the model.
