"""Scoring for the classification eval (pure functions, unit-tested).

One accuracy number hides what matters for the product: a wrong label that is
auto-approved (confidence >= threshold) skips human review entirely. So besides
overall accuracy we report per-class precision/recall, accuracy split by label
difficulty, the review burden (share below the threshold) and the
auto-approved error rate.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

CLASSES = (
    "acceptance_criterion",
    "business_rule",
    "glossary_term",
    "example",
    "out_of_scope",
    "metadata",
)


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def score(rows: list[dict[str, Any]], auto_approve_threshold: float) -> dict[str, Any]:
    """rows: {id, expected, got, confidence, difficulty?} per chunk."""
    total = len(rows)
    correct = sum(1 for r in rows if r["got"] == r["expected"])

    per_class: dict[str, dict[str, float | None]] = {}
    for c in CLASSES:
        tp = sum(1 for r in rows if r["expected"] == c and r["got"] == c)
        fn = sum(1 for r in rows if r["expected"] == c and r["got"] != c)
        fp = sum(1 for r in rows if r["expected"] != c and r["got"] == c)
        per_class[c] = {
            "support": tp + fn,
            "precision": _ratio(tp, tp + fp),
            "recall": _ratio(tp, tp + fn),
        }

    by_difficulty: dict[str, dict[str, Any]] = {}
    for d in sorted({r.get("difficulty", "standard") for r in rows}):
        sub = [r for r in rows if r.get("difficulty", "standard") == d]
        by_difficulty[d] = {
            "total": len(sub),
            "accuracy": _ratio(sum(1 for r in sub if r["got"] == r["expected"]), len(sub)),
        }

    auto = [r for r in rows if r["confidence"] >= auto_approve_threshold]
    auto_wrong = [r for r in auto if r["got"] != r["expected"]]

    confusions = Counter((r["expected"], r["got"]) for r in rows if r["got"] != r["expected"])

    return {
        "total": total,
        "correct": correct,
        "accuracy": _ratio(correct, total) or 0.0,
        "per_class": per_class,
        "by_difficulty": by_difficulty,
        "needs_review_rate": _ratio(total - len(auto), total),
        "auto_approved": len(auto),
        "auto_approved_error_rate": _ratio(len(auto_wrong), len(auto)),
        "auto_approved_errors": [r["id"] for r in auto_wrong],
        "confusions": [
            {"expected": e, "got": g, "count": n} for (e, g), n in confusions.most_common()
        ],
        "unknown_rate": _ratio(sum(1 for r in rows if r["got"] == "unknown"), total),
    }
