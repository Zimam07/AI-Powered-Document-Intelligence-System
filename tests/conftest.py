import pytest


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    from app import db, main

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "UPLOAD_DIR", uploads)
    main.request_windows.clear()
    db.init_db()
    yield
    main.request_windows.clear()
