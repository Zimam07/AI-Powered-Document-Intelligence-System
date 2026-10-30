from scripts import evaluate


def test_failed_documents_count_against_accuracy(monkeypatch):
    def extraction(text):
        if text == "broken":
            raise ValueError("Extraction failed")
        return {"total": 10}, 1

    monkeypatch.setattr(evaluate, "extract_invoice", extraction)
    metrics = evaluate.evaluate([
        {"text": "ok", "fields": {"total": 10}},
        {"text": "broken", "fields": {"total": 20}},
    ])
    assert metrics["field_accuracy"] == 0.5
    assert metrics["fields_evaluated"] == 2
    assert metrics["failure_rate"] == 0.5
    assert metrics["success_rate"] == 0.5


def test_empty_evaluation_does_not_report_accuracy():
    assert evaluate.evaluate([])["field_accuracy"] is None
