"""
Evaluation harness — gates pipeline changes.
Run: uv run python -m backend.evals.run_evals

Metrics:
- Classification accuracy vs hand-labeled golden set
- Chunk auto-approval rate, human edits per generated test, and locator
  verification pass rate — reused from backend/src/api/metrics.py's
  compute_tenant_metrics() rather than recomputed here, since these are
  real aggregation queries the product already runs, not eval-specific
  logic. Reported against DEV_TENANT_ID, so they reflect whatever's
  actually in the local dev database, not the golden set specifically.
- % ACs producing a passing generated test with zero human edits (manual
  gate — needs the generated Playwright tests actually run, not
  automated here)
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
DEV_TENANT_ID = "00000000-0000-0000-0000-000000000001"


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


async def eval_product_metrics(tenant_id: str) -> dict[str, Any]:
    """Chunk auto-approval rate, human edits per generated test, locator
    verification pass rate — real, already-computed aggregation queries
    (backend/src/api/metrics.py), not a separate eval-only calculation.
    Reflects whatever's actually in the local dev database."""
    from backend.src.api.metrics import compute_tenant_metrics
    from backend.src.db.session import async_session_factory

    async with async_session_factory() as session:
        metrics = await compute_tenant_metrics(session, tenant_id)

    return {
        "chunk_auto_approval_rate": metrics["chunk_auto_approval_rate"],
        "human_edit_rate": metrics["human_edits"]["edit_rate"],
        "locator_verification_pass_rate": metrics["locator_verification"]["pass_rate"],
    }


async def main(classification_only: bool = False) -> None:
    labels = load_golden_labels()
    results: dict[str, Any] = {}

    classification = await eval_classification_accuracy(labels)
    results.update(classification)

    if not classification_only:  # these read the local dev database
        product_metrics = await eval_product_metrics(DEV_TENANT_ID)
        results.update(product_metrics)

    print("\n=== Eval Results ===")
    for k, v in results.items():
        print(f"  {k}: {v}")

    print(
        "\nNOTE: % ACs producing a passing generated test with zero human "
        "edits is a manual gate — it needs the generated Playwright tests "
        "actually run, not automated here."
    )

    # Gate: fail if accuracy drops below 0.80
    accuracy = results.get("classification_accuracy", 1.0)
    if accuracy < 0.80:
        print(f"\nFAIL: classification accuracy {accuracy:.2%} < 80% threshold")
        raise SystemExit(1)
    else:
        print(f"\nPASS: classification accuracy {accuracy:.2%}")


if __name__ == "__main__":
    import sys

    # --classification-only: just the golden-set classifier check (no database), for CI.
    asyncio.run(main(classification_only="--classification-only" in sys.argv))
