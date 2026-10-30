import io
import pytest
from app.processor import compare_invoices, extract_invoice, extract_text, validate_invoice

SAMPLE = """Invoice Number: INV-100
Invoice Date: 2026-01-15
Supplier: Acme Supplies
Customer: Example Ltd
Currency: USD
Subtotal: 100.00
Tax: 15.00
Total: 115.00
1 | Widget | 1 | 100.00
"""

def test_extracts_invoice_and_line_item():
    invoice, confidence = extract_invoice(SAMPLE)
    assert invoice["invoice_number"] == "INV-100"
    assert invoice["total"] == 115.0
    assert invoice["line_items"][0]["amount"] == 100.0
    assert confidence == 1.0

def test_validation_detects_mismatch_and_missing_data():
    invoice, _ = extract_invoice(SAMPLE.replace("Total: 115.00", "Total: 125.00").replace("Currency: USD", ""))
    errors = validate_invoice(invoice, SAMPLE)
    assert {error["code"] for error in errors} >= {"missing_field", "total_mismatch"}

def test_no_invented_values_for_unknown_fields():
    invoice, _ = extract_invoice("A document with no invoice labels")
    assert invoice["invoice_number"] is None
    assert invoice["total"] is None

def test_csv_and_xlsx_are_parsed():
    text, sheets = extract_text(b"invoice_number,total\nINV-1,12.50\n", ".csv")
    assert "INV-1" in text and sheets == 1
    from openpyxl import Workbook
    workbook = Workbook()
    workbook.active.append(["invoice_number", "total"])
    workbook.active.append(["INV-2", 25])
    stream = io.BytesIO()
    workbook.save(stream)
    text, sheets = extract_text(stream.getvalue(), ".xlsx")
    assert "INV-2" in text and sheets == 1

def test_structured_csv_maps_data_row_instead_of_header():
    text = (
        "invoice_number | invoice_date | supplier_name | customer_name | subtotal | tax | total | currency\n"
        "INV-1 | 2026-10-28 | Supplier | Customer | 100 | 15 | 115 | USD"
    )
    invoice, confidence = extract_invoice(text)
    assert invoice["invoice_number"] == "INV-1"
    assert invoice["supplier_name"] == "Supplier"
    assert invoice["total"] == 115.0
    assert confidence == 1.0

def test_spreadsheet_key_value_rows_are_extracted():
    invoice, confidence = extract_invoice(
        "Invoice Number | XLS-001\nInvoice Date | 2026-01-01\n"
        "Supplier | Spreadsheet Supplier\nCustomer | Spreadsheet Customer\n"
        "Currency | USD\nSubtotal | 100\nTax | 15\nTotal | 115"
    )
    assert invoice["invoice_number"] == "XLS-001"
    assert invoice["supplier_name"] == "Spreadsheet Supplier"
    assert invoice["total"] == 115.0
    assert confidence == 1.0

def test_cross_document_comparison_reports_mismatches():
    assert compare_invoices({"invoice_number": "A", "total": 10}, {"invoice_number": "B", "total": 10}) == [
        {"field": "invoice_number", "left": "A", "right": "B"}
    ]

def test_validation_detects_numeric_and_line_item_errors():
    errors = validate_invoice({
        "invoice_number": "A", "invoice_date": "2026-01-01",
        "supplier_name": "S", "customer_name": "C", "currency": "USD",
        "subtotal": -10, "tax": "not-a-number", "total": 1,
        "line_items": [{"quantity": 2, "unit_price": 3, "amount": 5}],
    }, "")
    codes = {error["code"] for error in errors}
    assert {"negative_numeric", "invalid_numeric", "line_item_math_mismatch"} <= codes

def test_duplicate_word_in_supplier_is_not_a_duplicate_signal():
    invoice, _ = extract_invoice(SAMPLE.replace("Acme Supplies", "Duplicate Supplies"))
    assert "possible_duplicate" not in {error["code"] for error in validate_invoice(invoice, "Duplicate Supplies")}

def test_comparison_includes_line_items():
    errors = compare_invoices({"line_items": [{"amount": 1}]}, {"line_items": [{"amount": 2}]})
    assert errors == [{"field": "line_items", "left": "different", "right": "different"}]


def test_blank_label_does_not_capture_next_line():
    invoice, _ = extract_invoice("Invoice Number:\nInvoice Date: 2026-10-30\nTotal:\nTax: 5")
    assert invoice["invoice_number"] is None
    assert invoice["total"] is None


def test_sub_total_is_not_mistaken_for_total():
    invoice, _ = extract_invoice("Sub-total: 100\nTax: 15\nTotal: 115")
    assert invoice["subtotal"] == 100
    assert invoice["total"] == 115


@pytest.mark.parametrize("amount", ["12.345", "1,23.00", "NaN", "Infinity", "12abc"])
def test_malformed_money_is_not_truncated(amount):
    invoice, _ = extract_invoice(f"Total: {amount}")
    assert invoice["total"] is None


def test_blank_structured_values_remain_unknown():
    invoice, _ = extract_invoice("invoice number | invoice date | total | tax\nA | 2026-10-30 | | 5")
    assert invoice["total"] is None


def test_comparison_detects_missing_field():
    assert compare_invoices({"total": 100}, {"total": None}) == [
        {"field": "total", "left": "100", "right": "None"}]


def test_dollar_sign_does_not_invent_currency():
    invoice, _ = extract_invoice("Subtotal: $100\nTax: $15\nTotal: $115")
    assert invoice["total"] == 115
    assert invoice["currency"] is None


def test_partial_csv_headers_extract_available_values():
    text, _ = extract_text(b"invoice_number,total\nPARTIAL-1,12.50", ".csv")
    invoice, _ = extract_invoice(text)
    assert invoice["invoice_number"] == "PARTIAL-1"
    assert invoice["total"] == 12.5
    assert invoice["invoice_date"] is None


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "1,23", "12.345"])
def test_structured_invalid_money_stays_unknown(amount):
    invoice, _ = extract_invoice(f"invoice_number | total\nA | {amount}")
    assert invoice["total"] is None
