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
# labels.json: the original set; labels_hard.json: harder / ambiguous cases and a
# third document (each row carries a rationale and a difficulty).
LABEL_FILES = (GOLDEN_DIR / "labels.json", GOLDEN_DIR / "labels_hard.json")
RESULTS_DIR = Path(__file__).parent / "results"
# Gates. Overall accuracy was 100% on the original 50; the harder set is where
# regressions will show, so it also gates the auto-approved error rate.
MIN_ACCURACY = 0.92
MAX_AUTO_APPROVED_ERROR_RATE = 0.07
CLASSIFY_CONCURRENCY = 8
DEV_TENANT_ID = "00000000-0000-0000-0000-000000000001"


def load_golden_labels() -> list[dict[str, Any]]:
    """Load hand-labeled chunks for classification accuracy evaluation."""
    labels: list[dict[str, Any]] = []
    for path in LABEL_FILES:
        if not path.exists():
            log.warning("evals.no_labels_file", path=str(path))
            continue
        labels.extend(json.loads(path.read_text(encoding="utf-8")))
    return labels


async def eval_classification_accuracy(labels: list[dict[str, Any]]) -> dict[str, Any]:
    """Run the classifier over the golden set; score it (see classification_metrics)."""
    from backend.src.config import settings
    from backend.src.ingestion.classify import classify_block
    from backend.src.ingestion.layout import Block
    from backend.evals.classification_metrics import score

    if not labels:
        log.warning("evals.skipped_no_labels")
        return {}

    sem = asyncio.Semaphore(CLASSIFY_CONCURRENCY)

    async def one(item: dict[str, Any]) -> dict[str, Any]:
        block = Block(
            block_type=item.get("hint_block_type", "paragraph"),
            content=item["content"],
            page_number=item.get("page_number", 1),
        )
        async with sem:
            got, confidence, _ = await classify_block(block)
        return {
            "id": item.get("id", item["content"][:30]),
            "expected": item["expected_type"],
            "got": got,
            "confidence": confidence,
            "difficulty": item.get("difficulty", "standard"),
            "content": item["content"],
        }

    rows = await asyncio.gather(*(one(i) for i in labels))
    for r in rows:
        if r["got"] != r["expected"]:
            log.info(
                "evals.misclassified",
                id=r["id"],
                expected=r["expected"],
                got=r["got"],
                confidence=r["confidence"],
                content=r["content"][:80],
            )

    metrics = score(rows, settings.confidence_auto_approve_threshold)
    metrics["misclassified"] = [
        {k: r[k] for k in ("id", "expected", "got", "confidence", "difficulty")}
        for r in rows
        if r["got"] != r["expected"]
    ]
    return metrics


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

    if not classification_only:  # these read the local dev database
        results.update(await eval_product_metrics(DEV_TENANT_ID))

    print("\n=== Classification eval ===")
    if classification:
        print(f"  accuracy: {classification['accuracy']:.1%} ({classification['correct']}/{classification['total']})")
        for d, v in classification["by_difficulty"].items():
            print(f"    {d}: {v['accuracy']} over {v['total']}")
        print("  per class (support / precision / recall):")
        for c, v in classification["per_class"].items():
            print(f"    {c:22s} {v['support']:3d}  {v['precision']}  {v['recall']}")
        print(f"  needs_review_rate: {classification['needs_review_rate']}")
        print(f"  auto_approved_error_rate: {classification['auto_approved_error_rate']}"
              f" ({len(classification['auto_approved_errors'])}/{classification['auto_approved']})")
        print(f"  unknown_rate: {classification['unknown_rate']}")
        for c in classification["confusions"]:
            print(f"  confused: expected {c['expected']} -> got {c['got']} x{c['count']}")
        for m in classification["misclassified"]:
            print(f"  [MISS] {m['id']} ({m['difficulty']}) {m['expected']} -> {m['got']} @{m['confidence']}")
        RESULTS_DIR.mkdir(exist_ok=True)
        (RESULTS_DIR / "classification-latest.json").write_text(
            json.dumps(classification, indent=2), encoding="utf-8"
        )
    for k, v in results.items():
        print(f"  {k}: {v}")

    print(
        "\nNOTE: % ACs producing a passing generated test with zero human "
        "edits is measured by run_codegen_eval.py."
    )

    failures = []
    accuracy = classification.get("accuracy", 1.0)
    if accuracy < MIN_ACCURACY:
        failures.append(f"accuracy {accuracy:.1%} < {MIN_ACCURACY:.0%}")
    auto_err = classification.get("auto_approved_error_rate") or 0.0
    if auto_err > MAX_AUTO_APPROVED_ERROR_RATE:
        failures.append(f"auto-approved error rate {auto_err:.1%} > {MAX_AUTO_APPROVED_ERROR_RATE:.0%}")
    if failures:
        print("\nFAIL: " + "; ".join(failures))
        raise SystemExit(1)
    print(f"\nPASS: accuracy {accuracy:.1%}, auto-approved error rate {auto_err:.1%}")


if __name__ == "__main__":
    import sys

    # --classification-only: just the golden-set classifier check (no database), for CI.
    asyncio.run(main(classification_only="--classification-only" in sys.argv))
