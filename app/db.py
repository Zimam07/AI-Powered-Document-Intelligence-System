import json
import re
from math import sqrt
import sqlite3
from datetime import datetime, timezone
from typing import Any
from .config import DB_PATH, ensure_directories

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def connect() -> sqlite3.Connection:
    ensure_directories()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db() -> None:
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
          id TEXT PRIMARY KEY, filename TEXT NOT NULL, content_type TEXT NOT NULL,
          size_bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, status TEXT NOT NULL,
          error TEXT, progress INTEGER NOT NULL DEFAULT 0, stage TEXT NOT NULL DEFAULT 'queued',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS extracted_text (
          document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
          text TEXT NOT NULL, page_count INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS invoices (
          id TEXT PRIMARY KEY, document_id TEXT NOT NULL UNIQUE REFERENCES documents(id) ON DELETE CASCADE,
          invoice_json TEXT NOT NULL, confidence REAL NOT NULL, requires_review INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS validation_errors (
          id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id TEXT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
          code TEXT NOT NULL, message TEXT NOT NULL, severity TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS processing_history (
          id INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
          status TEXT NOT NULL, message TEXT, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
        CREATE INDEX IF NOT EXISTS idx_documents_sha256 ON documents(sha256);
        CREATE INDEX IF NOT EXISTS idx_history_document ON processing_history(document_id);
        """)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(documents)")}
        if "progress" not in columns:
            db.execute("ALTER TABLE documents ADD COLUMN progress INTEGER NOT NULL DEFAULT 0")
        if "stage" not in columns:
            db.execute("ALTER TABLE documents ADD COLUMN stage TEXT NOT NULL DEFAULT 'queued'")
        db.execute("""UPDATE documents SET progress=CASE status
          WHEN 'completed' THEN 100 WHEN 'failed' THEN 100 ELSE progress END,
          stage=CASE status WHEN 'completed' THEN 'complete' WHEN 'failed' THEN 'failed' ELSE stage END
          WHERE (status='completed' AND progress=0) OR (status='failed' AND progress=0)""")

def document_row(document_id: str) -> dict[str, Any] | None:
    with connect() as db:
        row = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        return dict(row) if row else None

def record_status(document_id: str, status: str, message: str | None = None,
                  progress: int | None = None, stage: str | None = None) -> None:
    with connect() as db:
        timestamp = now()
        current = db.execute("SELECT progress,stage FROM documents WHERE id=?", (document_id,)).fetchone()
        db.execute("""UPDATE documents SET status=?, error=?, progress=?, stage=?, updated_at=?
                   WHERE id=?""",
                   (status, message if status == "failed" else None,
                    progress if progress is not None else current["progress"],
                    stage if stage is not None else current["stage"], timestamp, document_id))
        db.execute("INSERT INTO processing_history(document_id,status,message,created_at) VALUES(?,?,?,?)",
                   (document_id, status, message, timestamp))

def save_result(document_id: str, text: str, page_count: int, invoice: dict[str, Any],
                confidence: float, errors: list[dict[str, str]]) -> None:
    with connect() as db:
        timestamp = now()
        db.execute("INSERT OR REPLACE INTO extracted_text(document_id,text,page_count) VALUES(?,?,?)",
                   (document_id, text, page_count))
        invoice_id = f"inv_{document_id}"
        db.execute("""INSERT OR REPLACE INTO invoices
          (id,document_id,invoice_json,confidence,requires_review,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?)""",
                   (invoice_id, document_id, json.dumps(invoice), confidence, bool(errors), timestamp, timestamp))
        db.execute("DELETE FROM validation_errors WHERE invoice_id=?", (invoice_id,))
        db.executemany("INSERT INTO validation_errors(invoice_id,code,message,severity) VALUES(?,?,?,?)",
                       [(invoice_id, e["code"], e["message"], e["severity"]) for e in errors])

def has_duplicate_invoice(document_id: str, invoice_number: str | None) -> bool:
    if not invoice_number:
        return False
    with connect() as db:
        rows = db.execute("SELECT invoice_json FROM invoices WHERE document_id != ?", (document_id,)).fetchall()
    return any(json.loads(row["invoice_json"]).get("invoice_number") == invoice_number for row in rows)

def has_duplicate_hash(document_id: str, content_hash: str) -> bool:
    with connect() as db:
        row = db.execute(
            "SELECT 1 FROM documents WHERE sha256=? AND id != ? LIMIT 1",
            (content_hash, document_id),
        ).fetchone()
        return row is not None

def result(document_id: str) -> dict[str, Any] | None:
    with connect() as db:
        doc = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        inv = db.execute("SELECT * FROM invoices WHERE document_id=?", (document_id,)).fetchone()
        if not doc:
            return None
        payload: dict[str, Any] = {"document": dict(doc), "invoice": None, "validation_errors": []}
        payload["history"] = [dict(x) for x in db.execute(
            "SELECT status,message,created_at FROM processing_history WHERE document_id=? ORDER BY id",
            (document_id,))]
        text_row = db.execute("SELECT page_count FROM extracted_text WHERE document_id=?",
                              (document_id,)).fetchone()
        payload["page_count"] = text_row["page_count"] if text_row else None
        if inv:
            payload["invoice"] = json.loads(inv["invoice_json"])
            payload["confidence"] = inv["confidence"]
            payload["requires_review"] = bool(inv["requires_review"])
            payload["validation_errors"] = [dict(x) for x in db.execute(
                "SELECT code,message,severity FROM validation_errors WHERE invoice_id=?", (inv["id"],))]
        return payload

def list_results(query: str = "") -> list[dict[str, Any]]:
    with connect() as db:
        like = f"%{query}%"
        rows = db.execute("""SELECT d.id,d.filename,d.status,d.progress,d.stage,d.created_at,
          i.invoice_json,i.confidence,i.requires_review
          FROM documents d LEFT JOIN invoices i ON d.id=i.document_id
          LEFT JOIN extracted_text t ON d.id=t.document_id
          WHERE ?='' OR d.filename LIKE ? OR t.text LIKE ? OR i.invoice_json LIKE ?
          ORDER BY d.created_at DESC""", (query, like, like, like)).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["invoice"] = json.loads(item.pop("invoice_json")) if item["invoice_json"] else None
            item["requires_review"] = bool(item["requires_review"])
            output.append(item)
        return output

def semantic_results(query: str) -> list[dict[str, Any]]:
    tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    if not tokens:
        return list_results()
    ranked = []
    for item in list_results():
        haystack = json.dumps(item.get("invoice") or {}).lower() + " " + item["filename"].lower()
        words = set(re.findall(r"[a-z0-9]+", haystack))
        score = len(tokens & words) / sqrt(max(len(tokens) * len(words), 1))
        if score:
            item["semantic_score"] = round(score, 4)
            ranked.append(item)
    return sorted(ranked, key=lambda item: item["semantic_score"], reverse=True)

def update_invoice(document_id: str, invoice: dict[str, Any]) -> None:
    with connect() as db:
        db.execute("UPDATE invoices SET invoice_json=?,requires_review=1,updated_at=? WHERE document_id=?",
                   (json.dumps(invoice), now(), document_id))

def update_invoice_review(document_id: str, invoice: dict[str, Any],
                          errors: list[dict[str, str]]) -> None:
    with connect() as db:
        invoice_id = f"inv_{document_id}"
        db.execute("UPDATE invoices SET invoice_json=?,requires_review=?,updated_at=? WHERE document_id=?",
                   (json.dumps(invoice), bool(errors), now(), document_id))
        db.execute("DELETE FROM validation_errors WHERE invoice_id=?", (invoice_id,))
        db.executemany("INSERT INTO validation_errors(invoice_id,code,message,severity) VALUES(?,?,?,?)",
                       [(invoice_id, e["code"], e["message"], e["severity"]) for e in errors])
