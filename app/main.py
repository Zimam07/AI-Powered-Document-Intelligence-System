import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any
from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .config import (ALLOWED_EXTENSIONS, ALLOWED_ORIGINS, API_KEY, MALWARE_SIGNATURES,
                     MAX_UPLOAD_BYTES, RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS,
                     UPLOAD_DIR, ensure_directories)
from .db import (connect, document_row, has_duplicate_hash, has_duplicate_invoice, init_db,
                 list_results, now, record_status, result, save_result, semantic_results,
                 update_invoice_review)
from .processor import compare_invoices, extract_invoice, extract_text, sha256, validate_invoice

app = FastAPI(title="Document Intelligence API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["GET", "POST", "PATCH"],
                   allow_headers=["Content-Type", "X-API-Key", "X-User-Role"], max_age=600)
jobs: dict[str, asyncio.Task[None]] = {}
request_windows: dict[str, list[float]] = {}
init_db()

class Correction(BaseModel):
    invoice: dict[str, Any] = Field(..., description="Corrected invoice JSON")

def require_api_access(
    x_api_key: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
) -> str:
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(401, "A valid X-API-Key header is required")
    return (x_user_role or "reviewer").lower()

def require_admin(role: str = Depends(require_api_access)) -> str:
    if role not in {"admin", "reviewer"}:
        raise HTTPException(403, "This operation requires reviewer authorization")
    return role

@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path == "/health":
        return await call_next(request)
    identity = request.client.host if request.client else "unknown"
    now_value = time.monotonic()
    window = [stamp for stamp in request_windows.get(identity, []) if now_value - stamp < RATE_LIMIT_WINDOW_SECONDS]
    if len(window) >= RATE_LIMIT_REQUESTS:
        raise HTTPException(429, "Rate limit exceeded; try again later")
    window.append(now_value)
    request_windows[identity] = window
    return await call_next(request)

@app.on_event("startup")
def startup() -> None:
    ensure_directories()
    init_db()

async def process(document_id: str, path: Path, suffix: str) -> None:
    try:
        record_status(document_id, "processing", progress=10, stage="reading")
        data = path.read_bytes()
        record_status(document_id, "processing", progress=25, stage="extracting text")
        text, pages = await asyncio.to_thread(extract_text, data, suffix)
        record_status(document_id, "processing", progress=65, stage="extracting invoice")
        invoice, confidence = await asyncio.to_thread(extract_invoice, text)
        record_status(document_id, "processing", progress=85, stage="validating")
        errors = validate_invoice(invoice, text, sha256(data))
        if await asyncio.to_thread(has_duplicate_hash, document_id, sha256(data)):
            errors.append({"code": "duplicate_document", "message": "An identical file was uploaded previously", "severity": "error"})
        if await asyncio.to_thread(has_duplicate_invoice, document_id, invoice.get("invoice_number")):
            errors.append({"code": "duplicate_invoice", "message": "Invoice number already exists in another document", "severity": "error"})
        save_result(document_id, text, pages, invoice, confidence, errors)
        record_status(document_id, "completed", progress=100, stage="complete")
    except Exception as exc:
        record_status(document_id, "failed", str(exc), progress=100, stage="failed")

async def schedule(document_id: str, path: Path, suffix: str) -> None:
    task = asyncio.create_task(process(document_id, path, suffix))
    jobs[document_id] = task
    try:
        await task
    finally:
        jobs.pop(document_id, None)

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.post("/api/documents", status_code=202)
async def upload_documents(background: BackgroundTasks, files: list[UploadFile] = File(...),
                           _: str = Depends(require_api_access)) -> dict[str, Any]:
    if not files:
        raise HTTPException(400, "At least one file is required")
    accepted = []
    for upload in files:
        suffix = Path(upload.filename or "").suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(415, f"Unsupported file type: {suffix or 'unknown'}")
        data = await upload.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"{upload.filename} exceeds the upload limit")
        if any(signature.lower() in data.lower() for signature in MALWARE_SIGNATURES):
            raise HTTPException(422, f"{upload.filename} was rejected by the malware content scan")
        document_id = f"doc_{uuid.uuid4().hex}"
        path = UPLOAD_DIR / f"{document_id}{suffix}"
        path.write_bytes(data)
        timestamp = now()
        with connect() as db:
            db.execute("INSERT INTO documents(id,filename,content_type,size_bytes,sha256,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                       (document_id, upload.filename or path.name, upload.content_type or "application/octet-stream",
                        len(data), sha256(data), "queued", timestamp, timestamp))
            db.execute("UPDATE documents SET progress=0,stage='queued' WHERE id=?", (document_id,))
        background.add_task(schedule, document_id, path, suffix)
        accepted.append({"id": document_id, "filename": upload.filename, "status": "queued"})
    return {"documents": accepted}

@app.get("/api/documents")
def documents(q: str = Query("", max_length=200), _: str = Depends(require_api_access)) -> list[dict[str, Any]]:
    return list_results(q)

@app.get("/api/search")
def search(q: str = Query(..., min_length=1, max_length=200), _: str = Depends(require_api_access)) -> list[dict[str, Any]]:
    """Rank invoice metadata and filenames by token similarity."""
    return semantic_results(q)

@app.get("/api/documents/{document_id}")
def document(document_id: str, _: str = Depends(require_api_access)) -> dict[str, Any]:
    payload = result(document_id)
    if not payload:
        raise HTTPException(404, "Document not found")
    return payload

@app.post("/api/documents/{document_id}/reprocess", status_code=202)
def reprocess(document_id: str, background: BackgroundTasks,
              _: str = Depends(require_admin)) -> dict[str, str]:
    row = document_row(document_id)
    if not row:
        raise HTTPException(404, "Document not found")
    path = next(UPLOAD_DIR.glob(f"{document_id}.*"), None)
    if not path:
        raise HTTPException(410, "Original upload is no longer available")
    background.add_task(schedule, document_id, path, path.suffix.lower())
    return {"id": document_id, "status": "queued"}

@app.get("/api/documents/{left_id}/compare/{right_id}")
def compare_documents(left_id: str, right_id: str, _: str = Depends(require_api_access)) -> dict[str, Any]:
    left = result(left_id)
    right = result(right_id)
    if not left or not right:
        raise HTTPException(404, "Both documents must exist")
    if not left["invoice"] or not right["invoice"]:
        raise HTTPException(409, "Both documents must finish processing before comparison")
    mismatches = compare_invoices(left["invoice"], right["invoice"])
    return {"match": not mismatches, "mismatches": mismatches, "left_id": left_id, "right_id": right_id}

@app.patch("/api/documents/{document_id}/invoice")
def correct_invoice(document_id: str, correction: Correction,
                    _: str = Depends(require_admin)) -> dict[str, Any]:
    row = document_row(document_id)
    if not row:
        raise HTTPException(404, "Document not found")
    with connect() as db:
        text_row = db.execute("SELECT text FROM extracted_text WHERE document_id=?", (document_id,)).fetchone()
    errors = validate_invoice(correction.invoice, text_row["text"] if text_row else "")
    if row["sha256"] and has_duplicate_hash(document_id, row["sha256"]):
        errors.append({"code": "duplicate_document", "message": "An identical file was uploaded previously", "severity": "error"})
    if has_duplicate_invoice(document_id, correction.invoice.get("invoice_number")):
        errors.append({"code": "duplicate_invoice", "message": "Invoice number already exists in another document", "severity": "error"})
    update_invoice_review(document_id, correction.invoice, errors)
    return result(document_id) or {}

@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(Path(__file__).parent.parent / "web" / "index.html")
