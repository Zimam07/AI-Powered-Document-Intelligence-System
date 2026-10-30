"""Evaluate labeled JSONL fixtures without claiming metrics when no labels exist."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.processor import extract_invoice

def evaluate(records: list[dict]) -> dict:
    total = correct = successful = failed = 0
    source_types: dict[str, int] = {}
    elapsed = 0.0
    for item in records:
        labels = item.get("fields", {})
        total += len(labels)
        source_types[item.get("source_type", "unknown")] = source_types.get(item.get("source_type", "unknown"), 0) + 1
        started = time.perf_counter()
        try:
            predicted, _ = extract_invoice(item["text"])
            successful += 1
        except Exception:
            failed += 1
            continue
        finally:
            elapsed += time.perf_counter() - started
        for field, expected in labels.items():
            correct += predicted.get(field) == expected
    documents = successful + failed
    return {
        "field_accuracy": correct / total if total else None,
        "fields_evaluated": total,
        "documents_evaluated": documents,
        "success_rate": successful / documents if documents else None,
        "failure_rate": failed / documents if documents else None,
        "processing_time_seconds": round(elapsed, 6),
        "average_processing_time_seconds": round(elapsed / documents, 6) if documents else None,
        "source_types": source_types,
    }


def main() -> None:
    path = Path(__file__).resolve().parents[1] / "evaluation" / "labeled.jsonl"
    if not path.exists():
        raise SystemExit("No evaluation/labeled.jsonl found; accuracy is not reported.")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    metrics = evaluate(records)
    print(json.dumps(metrics, indent=2))
    if metrics["failure_rate"] != 0 or metrics["field_accuracy"] != 1:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
