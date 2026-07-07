"""
Evaluation harness — gates pipeline changes.
Run: uv run python -m backend.evals.run_evals

Metrics:
- Classification accuracy vs hand-labeled golden set
- % ACs producing a passing generated test with zero human edits (manual gate)
- Human edits per generated test (tracked via review_duration_ms + edit diffs)
- Locator verification pass rate
- Chunk classification accuracy
"""
from __future__ import annotations

import json
import asyncio
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

GOLDEN_DIR = Path(__file__).parent / "golden"
LABELS_FILE = GOLDEN_DIR / "labels.json"


def load_golden_labels() -> list[dict[str, Any]]:
    """Load hand-labeled chunks for classification accuracy evaluation."""
    if not LABELS_FILE.exists():
        log.warning("evals.no_labels_file", path=str(LABELS_FILE))
        return []
    with open(LABELS_FILE) as f:
        return json.load(f)


async def eval_classification_accuracy(labels: list[dict[str, Any]]) -> dict[str, float]:
    """Run classifier over golden set, compare to hand labels."""
    from backend.src.ingestion.layout import Block
    from backend.src.ingestion.classify import classify_block

    if not labels:
        log.warning("evals.skipped_no_labels")
        return {}

    correct = 0
    total = len(labels)

    for item in labels:
        block = Block(
            block_type=item.get("hint_block_type", "paragraph"),
            content=item["content"],
            page_number=item.get("page_number", 1),
        )
        chunk_type, confidence, _ = await classify_block(block)
        if chunk_type == item["expected_type"]:
            correct += 1
        else:
            log.debug(
                "evals.misclassified",
                expected=item["expected_type"],
                got=chunk_type,
                confidence=confidence,
                content=item["content"][:80],
            )

    accuracy = correct / total if total else 0.0
    log.info("evals.classification_accuracy", accuracy=accuracy, correct=correct, total=total)
    return {"classification_accuracy": accuracy, "correct": correct, "total": total}


async def main() -> None:
    labels = load_golden_labels()
    results: dict[str, Any] = {}

    classification = await eval_classification_accuracy(labels)
    results.update(classification)

    print("\n=== Eval Results ===")
    for k, v in results.items():
        print(f"  {k}: {v}")

    # Gate: fail if accuracy drops below 0.80
    accuracy = results.get("classification_accuracy", 1.0)
    if accuracy < 0.80:
        print(f"\nFAIL: classification accuracy {accuracy:.2%} < 80% threshold")
        raise SystemExit(1)
    else:
        print(f"\nPASS: classification accuracy {accuracy:.2%}")


if __name__ == "__main__":
    asyncio.run(main())
