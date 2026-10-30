# Requirements review

Reviewed on 2026-10-31 against this repository's README, architecture, evaluation notes, and extraction prompt. No separate assessment brief was supplied.

| Requirement | Implementation and verification |
| --- | --- |
| PDF, image, XLS, XLSX and CSV input | Real-format regression tests cover digital/scanned PDF, JPG/JPEG/PNG/TIF/TIFF, legacy XLS, XLSX and CSV. Multi-page TIFF preserves every page. |
| Multiple uploads and asynchronous processing | Multipart batches are validated before persistence. Background processing updates status/progress while API requests remain available. |
| Preserve unknown values | Missing fields remain null. Dollar symbols do not imply USD. Blank labels, partial CSV headers and malformed amounts have regression coverage. |
| Financial validation | Required fields, finite numbers, negative values, subtotal/tax/total, line-item arithmetic and duplicate checks are covered. |
| Persistence and processing history | SQLite stores metadata, text, invoices, errors and history. Connections close after each transaction; custom database parent directories are created. |
| Human review and corrections | UI edits persist after reload and validation is rerun. Failed/unfinished jobs cannot be corrected. |
| Retry and failure handling | Corrupt inputs become failed jobs. Retry claims a queued status transactionally; missing files and active jobs receive explicit errors. |
| Search and comparison | Keyword search and deterministic token ranking are implemented; comparison checks scalar values, missing values and line items. |
| Delete uploaded documents | Confirmation in the UI; original upload and related database rows are removed. Active jobs are protected; permission and file-failure cases are tested. |
| Configurable access and upload limits | API-key headers, browser key entry, role-header checks, CORS, size/type checks, signature scan and request limiting. These are a local/shared-key baseline. |
| Evaluation and large documents | Eight labeled text fixtures measure 64 fields; failed extractions count against accuracy. A generated 1,000-page digital PDF is tested. |
| Reproducible run and repository delivery | Local and Docker instructions, automated GitHub tests and container checks, ignored local data/secrets, and current verification notes. |

## Deliberate scope and limits

- Extraction is deterministic and label-based. No LLM service is called. The prompt documents a future adapter contract.
- The `confidence` API value is required-field completeness, not a calibrated probability; the UI labels it accordingly.
- Token ranking is not neural semantic search. One invoice is extracted per file; a table with multiple invoice rows uses its first data row.
- SQLite and in-process background tasks/rate limits suit a local demonstration. Jobs are not durable across a server crash. Multi-user production deployment needs a durable queue, backups and tenant isolation.
- An API-key holder can submit a role header; this is not server-verified per-user RBAC. Production authentication should derive roles from trusted identities. Signature matching is not an antivirus engine.
- The 64-field score evaluates provided text, not end-to-end accuracy on arbitrary scans. The large-file benchmark covers digital PDF extraction, not 1,000 pages of OCR.
- GitHub hosts the source and checks. A running FastAPI deployment needs a Python/container host with persistent storage; GitHub Pages cannot run the backend.
