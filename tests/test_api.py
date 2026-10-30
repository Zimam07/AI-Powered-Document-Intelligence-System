from fastapi.testclient import TestClient
from app.main import app
import pytest
import io
from pathlib import Path

client = TestClient(app)

def test_health():
    assert client.get("/health").json() == {"status": "ok"}

def test_rejects_unsupported_file():
    response = client.post("/api/documents", files={"files": ("malware.exe", b"no", "application/octet-stream")})
    assert response.status_code == 415

def test_search_and_compare_routes_exist():
    assert client.get("/api/search?q=invoice").status_code == 200
    response = client.get("/api/documents/missing/compare/also-missing")
    assert response.status_code == 404

def test_rejects_empty_upload():
    response = client.post("/api/documents", files={})
    assert response.status_code in (400, 422)

def test_rejects_malware_signature():
    response = client.post("/api/documents", files={
        "files": ("invoice.csv", b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE", "text/csv")
    })
    assert response.status_code == 422


INVOICE = (b"Invoice Number,API-001\nInvoice Date,2026-10-30\nSupplier,Acme\n"
           b"Customer,Example\nCurrency,USD\nSubtotal,100\nTax,15\nTotal,115\n")


def upload(data=INVOICE, name="invoice.csv"):
    response = client.post("/api/documents", files={"files": (name, data)})
    assert response.status_code == 202
    return response.json()["documents"][0]["id"]


def test_upload_search_correct_compare_and_retry():
    first = upload()
    detail = client.get(f"/api/documents/{first}").json()
    assert detail["document"]["status"] == "completed"
    assert detail["document"]["progress"] == 100
    assert detail["invoice"]["total"] == 115
    assert detail["validation_errors"] == []
    assert detail["history"][-1]["status"] == "completed"
    assert len(client.get("/api/documents?q=Acme").json()) == 1
    assert len(client.get("/api/search?q=Acme").json()) == 1
    second = upload(INVOICE.replace(b"API-001", b"API-002"))
    comparison = client.get(f"/api/documents/{first}/compare/{second}").json()
    assert comparison["match"] is False
    correction = detail["invoice"] | {"total": 120}
    response = client.patch(f"/api/documents/{first}/invoice", json={"invoice": correction})
    assert response.status_code == 200
    assert "total_mismatch" in {e["code"] for e in response.json()["validation_errors"]}
    assert client.post(f"/api/documents/{first}/reprocess").status_code == 202
    assert client.get(f"/api/documents/{first}").json()["invoice"]["total"] == 115


def test_duplicate_file_and_invoice_are_flagged():
    upload()
    duplicate = upload()
    codes = {e["code"] for e in client.get(f"/api/documents/{duplicate}").json()["validation_errors"]}
    assert {"duplicate_document", "duplicate_invoice"} <= codes


def test_invalid_batch_does_not_leave_queued_documents():
    response = client.post("/api/documents", files=[
        ("files", ("valid.csv", INVOICE)), ("files", ("bad.exe", b"bad"))])
    assert response.status_code == 415
    assert client.get("/api/documents").json() == []
    from app.main import UPLOAD_DIR
    assert list(UPLOAD_DIR.iterdir()) == []


def test_empty_and_oversized_files(monkeypatch):
    assert client.post("/api/documents", files={"files": ("empty.csv", b"")}).status_code == 422
    monkeypatch.setattr("app.main.MAX_UPLOAD_BYTES", 10)
    assert client.post("/api/documents", files={"files": ("large.csv", b"x" * 11)}).status_code == 413


def test_rate_limit_returns_json_and_health_remains_available(monkeypatch):
    monkeypatch.setattr("app.main.RATE_LIMIT_REQUESTS", 1)
    assert client.get("/api/documents").status_code == 200
    response = client.get("/api/documents")
    assert response.status_code == 429
    assert response.headers["Retry-After"]
    assert "detail" in response.json()
    assert client.get("/health").status_code == 200


def test_authentication_and_reviewer_role(monkeypatch):
    monkeypatch.setattr("app.main.API_KEY", "test-secret")
    assert client.get("/api/documents").status_code == 401
    assert client.get("/api/documents", headers={"X-API-Key": "wrong"}).status_code == 401
    headers = {"X-API-Key": "test-secret", "X-User-Role": "viewer"}
    assert client.get("/api/documents", headers=headers).status_code == 200
    assert client.patch("/api/documents/missing/invoice", headers=headers, json={"invoice": {}}).status_code == 403


def test_corrupted_file_failure_and_correction_guard():
    document_id = upload(b"invalid pdf", "broken.pdf")
    detail = client.get(f"/api/documents/{document_id}").json()
    assert detail["document"]["status"] == "failed"
    assert "PDF extraction failed" in detail["document"]["error"]
    assert client.patch(f"/api/documents/{document_id}/invoice", json={"invoice": {}}).status_code == 409
    assert client.post(f"/api/documents/{document_id}/reprocess").status_code == 202


@pytest.mark.parametrize("items", [None, "bad", [None], [3], [{"amount": "NaN"}]])
def test_malformed_corrections_return_validation_issues(items):
    document_id = upload()
    response = client.patch(f"/api/documents/{document_id}/invoice", json={
        "invoice": {"total": "NaN", "line_items": items}})
    assert response.status_code == 200
    assert {"invalid_numeric", "invalid_line_item"} <= {e["code"] for e in response.json()["validation_errors"]}


def test_busy_reprocessing_and_missing_original():
    from app.db import record_status
    from app.main import UPLOAD_DIR
    document_id = upload()
    record_status(document_id, "processing")
    assert client.post(f"/api/documents/{document_id}/reprocess").status_code == 409
    record_status(document_id, "failed")
    next(UPLOAD_DIR.iterdir()).unlink()
    assert client.post(f"/api/documents/{document_id}/reprocess").status_code == 410


def test_cors_and_query_validation():
    response = client.options("/api/documents", headers={
        "Origin": "http://127.0.0.1:8000", "Access-Control-Request-Method": "POST"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:8000"
    assert client.get("/api/search?q=").status_code == 422
    assert client.get("/api/documents?q=" + "a" * 201).status_code == 422


@pytest.mark.parametrize("suffix", [".xlsx", ".xls", ".pdf"])
def test_real_document_formats(suffix):
    if suffix == ".xls":
        data = (Path(__file__).parent / "fixtures" / "invoice.xls").read_bytes()
    elif suffix == ".xlsx":
        from openpyxl import Workbook
        book = Workbook()
        for line in INVOICE.decode().splitlines():
            book.active.append(line.split(","))
        stream = io.BytesIO()
        book.save(stream)
        book.close()
        data = stream.getvalue()
    else:
        import fitz
        with fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_text((50, 50), INVOICE.decode().replace(",", ": "))
            data = pdf.tobytes()
    document_id = upload(data, "invoice" + suffix)
    detail = client.get(f"/api/documents/{document_id}").json()
    assert detail["document"]["status"] == "completed"
    assert detail["invoice"]["total"] == 115
    assert detail["validation_errors"] == []


def test_correction_rejects_overflowing_json_numbers():
    document_id = upload()
    response = client.patch(f"/api/documents/{document_id}/invoice",
                            content='{"invoice":{"total":1e400}}',
                            headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert client.get(f"/api/documents/{document_id}").json()["invoice"]["total"] == 115
