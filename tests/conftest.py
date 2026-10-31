import pytest
import os


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.failed and os.getenv("GITHUB_ACTIONS"):
        details = report.longreprtext.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error title=Test failed::{details}", flush=True)


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
