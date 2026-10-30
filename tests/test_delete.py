from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def upload():
    response = client.post("/api/documents", files={"files": ("invoice.csv", b"Invoice Number,A\nTotal,10")})
    assert response.status_code == 202
    return response.json()["documents"][0]["id"]


def test_delete_removes_upload_and_related_records():
    from app.db import connect
    from app.main import UPLOAD_DIR
    document_id = upload()
    other_id = upload()
    response = client.delete(f"/api/documents/{document_id}")
    assert response.status_code == 204
    assert not response.content
    assert not (UPLOAD_DIR / f"{document_id}.csv").exists()
    assert client.get(f"/api/documents/{document_id}").status_code == 404
    assert client.get(f"/api/documents/{other_id}").status_code == 200
    assert [d["id"] for d in client.get("/api/documents").json()] == [other_id]
    assert all(item["id"] != document_id for item in client.get("/api/search?q=invoice").json())
    with connect() as db:
        for table in ("extracted_text", "invoices", "processing_history"):
            assert db.execute(f"SELECT COUNT(*) FROM {table} WHERE document_id=?", (document_id,)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM validation_errors WHERE invoice_id=?", (f"inv_{document_id}",)).fetchone()[0] == 0
    assert client.delete(f"/api/documents/{document_id}").status_code == 404


@pytest.mark.parametrize("status", ["queued", "processing"])
def test_delete_rejects_active_jobs(status):
    from app.db import record_status
    document_id = upload()
    record_status(document_id, status)
    assert client.delete(f"/api/documents/{document_id}").status_code == 409
    assert client.get(f"/api/documents/{document_id}").status_code == 200


def test_delete_failed_document_with_missing_original():
    from app.main import UPLOAD_DIR
    response = client.post("/api/documents", files={"files": ("broken.pdf", b"bad")})
    document_id = response.json()["documents"][0]["id"]
    (UPLOAD_DIR / f"{document_id}.pdf").unlink()
    assert client.delete(f"/api/documents/{document_id}").status_code == 204


def test_delete_requires_reviewer_authorization(monkeypatch):
    document_id = upload()
    monkeypatch.setattr("app.main.API_KEY", "test-key")
    assert client.delete(f"/api/documents/{document_id}").status_code == 401
    assert client.delete(f"/api/documents/{document_id}", headers={
        "X-API-Key": "test-key", "X-User-Role": "viewer"}).status_code == 403
    assert client.delete(f"/api/documents/{document_id}", headers={
        "X-API-Key": "test-key", "X-User-Role": "reviewer"}).status_code == 204


def test_delete_preserves_record_when_file_removal_fails(monkeypatch):
    document_id = upload()

    def fail_unlink(*args, **kwargs):
        raise PermissionError("File is locked")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_unlink)
        assert client.delete(f"/api/documents/{document_id}").status_code == 500
    assert client.get(f"/api/documents/{document_id}").status_code == 200
