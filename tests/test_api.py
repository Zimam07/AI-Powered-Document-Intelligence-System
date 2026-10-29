from fastapi.testclient import TestClient
from app.main import app

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
