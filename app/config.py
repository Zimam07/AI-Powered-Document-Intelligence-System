from pathlib import Path
import os
import shutil

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "document_intelligence.sqlite3"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", 25 * 1024 * 1024))
TESSERACT_CMD = os.getenv("TESSERACT_CMD") or shutil.which("tesseract")
if not TESSERACT_CMD and os.name == "nt":
    for root in (os.getenv("ProgramFiles"), os.getenv("LOCALAPPDATA")):
        if root:
            candidate = Path(root) / "Tesseract-OCR" / "tesseract.exe"
            if candidate.is_file():
                TESSERACT_CMD = str(candidate)
                break
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".xlsx", ".xls", ".csv"}
API_KEY = os.getenv("DOCUMENT_API_KEY")
ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv(
    "ALLOWED_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000"
).split(",") if origin.strip()]
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "120"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
MALWARE_SIGNATURES = (b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE", b"<script", b"<?php")

def ensure_directories() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
