"""Evaluate labeled JSONL fixtures without claiming metrics when no labels exist."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.processor import extract_invoice

def main() -> None:
    path = Path("evaluation/labeled.jsonl")
    if not path.exists():
        print("No evaluation/labeled.jsonl found; accuracy is not reported.")
        return
    total = correct = successful = failed = 0
    source_types: dict[str, int] = {}
    elapsed = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        item = json.loads(line)
        source_types[item.get("source_type", "unknown")] = source_types.get(item.get("source_type", "unknown"), 0) + 1
        started = time.perf_counter()
        try:
            predicted, _ = extract_invoice(item["text"])
            successful += 1
        except Exception:
            failed += 1
            continue
        elapsed += time.perf_counter() - started
        for field in item.get("fields", {}):
            total += 1
            correct += predicted.get(field) == item["fields"][field]
    documents = successful + failed
    print(json.dumps({
        "field_accuracy": correct / total if total else None,
        "fields_evaluated": total,
        "documents_evaluated": documents,
        "success_rate": successful / documents if documents else None,
        "failure_rate": failed / documents if documents else None,
        "processing_time_seconds": round(elapsed, 6),
        "average_processing_time_seconds": round(elapsed / successful, 6) if successful else None,
        "source_types": source_types,
    }, indent=2))

if __name__ == "__main__":
    main()
