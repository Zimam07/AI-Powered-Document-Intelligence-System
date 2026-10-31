"""Exercise the UI in Chromium against a temporary database (requires playwright)."""
import json
import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = (b"Invoice Number,BROWSER-001\nInvoice Date,2026-10-30\nSupplier,Acme\n"
          b"Customer,Example\nCurrency,USD\nSubtotal,100\nTax,15\nTotal,115\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authenticated", action="store_true", help="Exercise API-key-protected UI")
    args = parser.parse_args()
    api_key = "browser-test-key" if args.authenticated else ""
    with tempfile.TemporaryDirectory(prefix="document-browser-") as storage:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        env = dict(os.environ, DATA_DIR=storage, DB_PATH=str(Path(storage) / "test.sqlite3"),
                   DOCUMENT_API_KEY=api_key, RATE_LIMIT_REQUESTS="1000")
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(100):
                try:
                    urllib.request.urlopen(base + "/health", timeout=1).close()
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Test server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))

                def unlock():
                    if api_key:
                        expect(page.locator("#accessPanel")).to_be_visible()
                        page.locator("#apiKey").fill(api_key)
                        page.get_by_role("button", name="Connect", exact=True).click()
                        expect(page.locator("#accessPanel")).to_be_hidden()

                page.goto(base)
                unlock()
                expect(page.locator("#rows")).to_contain_text("No documents found")
                page.locator("#uploadButton").click()
                expect(page.locator("#message")).to_contain_text("Choose at least one")

                def upload(name, data):
                    page.locator("#files").set_input_files({
                        "name": name, "mimeType": "application/octet-stream", "buffer": data})
                    page.locator("#uploadButton").click()
                    expect(page.locator("#message")).to_contain_text("queued for processing")
                    return page.locator("#rows tr").filter(has_text=name)

                row = upload("browser-one.csv", SAMPLE)
                expect(row).to_contain_text("completed", timeout=15000)
                row.locator("a").click()
                expect(page.locator("#saveButton")).to_be_enabled()
                page.locator("#invoice").fill("{invalid")
                page.locator("#saveButton").click()
                expect(page.locator("#saveMessage")).to_contain_text("Invalid JSON")
                invoice = {"invoice_number": "BROWSER-001", "invoice_date": "2026-10-30",
                           "supplier_name": "Acme", "customer_name": "Example", "currency": "USD",
                           "subtotal": 100, "tax": 15, "total": 120, "line_items": []}
                page.locator("#invoice").fill(json.dumps(invoice))
                page.locator("#saveButton").click()
                expect(page.locator("#saveMessage")).to_have_text("Saved successfully.")
                expect(page.locator("#errors")).to_contain_text("Subtotal plus tax")
                invoice["total"] = 115
                page.locator("#invoice").fill(json.dumps(invoice))
                page.locator("#saveButton").click()
                expect(page.locator("#errors")).to_contain_text("No validation issues")
                page.reload()
                unlock()
                page.get_by_role("link", name="browser-one.csv", exact=True).click()
                expect(page.locator("#detail")).to_be_visible()
                assert json.loads(page.locator("#invoice").input_value())["total"] == 115

                row = upload("browser-two.csv", SAMPLE.replace(b"BROWSER-001", b"BROWSER-002"))
                expect(row).to_contain_text("completed", timeout=15000)
                row.locator("a").click()
                page.locator("#compareButton").click()
                expect(page.locator("#compareResult")).to_contain_text("invoice_number")
                page.locator("#compareMode").select_option("pdf-pdf")
                page.locator("#compareButton").click()
                expect(page.locator("#compareResult")).to_contain_text("requires two PDF")

                row = upload("broken.pdf", b"not a PDF")
                expect(row).to_contain_text("Processing failed", timeout=15000)
                row.locator("a").click()
                expect(page.locator("#errors")).to_contain_text("PDF extraction failed")
                expect(page.locator("#saveButton")).to_be_disabled()
                row.get_by_role("button", name="Retry").click()
                expect(page.locator("#message")).to_contain_text("queued for reprocessing")

                page.locator("#search").fill("browser-one")
                expect(page.locator("#rows tr")).to_have_count(1)
                expect(page.locator("#rows")).to_contain_text("browser-one.csv")
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), page.evaluate(
                    "({viewport:innerWidth, page:document.documentElement.scrollWidth, "
                    "panels:[...document.querySelectorAll('.panel')].map(el=>({id:el.id,width:el.scrollWidth}))})")
                page.locator("#closeReview").click()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.set_viewport_size({"width": 1280, "height": 900})
                page.locator("#search").fill("")
                expect(page.locator("#rows tr")).to_have_count(3)
                deleted_row = page.locator("#rows tr").filter(has_text="broken.pdf")
                expect(deleted_row.get_by_role("button", name="Delete", exact=True)).to_be_enabled()
                deleted_row.locator("a").click()
                expect(page.locator("#detail")).to_be_visible()
                page.once("dialog", lambda dialog: dialog.dismiss())
                deleted_row.get_by_role("button", name="Delete", exact=True).click()
                expect(deleted_row).to_have_count(1)
                page.once("dialog", lambda dialog: dialog.accept())
                deleted_row.get_by_role("button", name="Delete", exact=True).click()
                expect(deleted_row).to_have_count(0)
                expect(page.locator("#detail")).to_be_hidden()
                expect(page.locator("#totalCount")).to_have_text("2")
                page.reload()
                unlock()
                expect(page.locator("#rows tr")).to_have_count(2)
                expect(page.locator("#rows")).not_to_contain_text("broken.pdf")
                assert not errors, errors
                browser.close()
                print("Browser checks passed: upload, empty selection, correction persistence, invalid JSON, "
                      "validation, comparison, failed processing, retry, search, mobile layout, delete/cancel; no JS errors.")
        finally:
            server.terminate()
            server.wait(timeout=15)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        if os.getenv("GITHUB_ACTIONS"):
            details = traceback.format_exc().replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            print(f"::error title=Browser workflow failed::{details}", flush=True)
        raise
