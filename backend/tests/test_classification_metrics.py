import json
from pathlib import Path

from backend.evals.classification_metrics import CLASSES, score

GOLDEN = Path(__file__).resolve().parents[1] / "evals" / "golden"


def _row(i, exp, got, conf=0.95, diff="standard"):
    return {"id": i, "expected": exp, "got": got, "confidence": conf, "difficulty": diff}


def test_score_precision_recall_and_confusions():
    rows = [
        _row("a", "example", "example"),
        _row("b", "example", "acceptance_criterion"),
        _row("c", "acceptance_criterion", "acceptance_criterion"),
        _row("d", "business_rule", "business_rule", conf=0.5),
    ]
    m = score(rows, 0.85)
    assert m["accuracy"] == 0.75 and m["correct"] == 3
    assert m["per_class"]["example"]["recall"] == 0.5
    assert m["per_class"]["acceptance_criterion"]["precision"] == 0.5
    assert m["per_class"]["glossary_term"]["recall"] is None  # no support
    assert m["confusions"] == [{"expected": "example", "got": "acceptance_criterion", "count": 1}]


def test_auto_approved_error_rate_counts_only_confident_chunks():
    rows = [
        _row("ok", "metadata", "metadata", conf=0.9),
        _row("bad-confident", "metadata", "out_of_scope", conf=0.9),
        _row("bad-unsure", "metadata", "out_of_scope", conf=0.4),  # goes to review: not an auto-approved error
    ]
    m = score(rows, 0.85)
    assert m["auto_approved"] == 2
    assert m["auto_approved_error_rate"] == 0.5
    assert m["auto_approved_errors"] == ["bad-confident"]
    assert m["needs_review_rate"] == round(1 / 3, 3)


def test_difficulty_split():
    rows = [_row("a", "example", "example"), _row("b", "example", "metadata", diff="ambiguous")]
    m = score(rows, 0.85)
    assert m["by_difficulty"]["standard"]["accuracy"] == 1.0
    assert m["by_difficulty"]["ambiguous"]["accuracy"] == 0.0


def test_golden_label_files_are_well_formed():
    seen = set()
    for name in ("labels.json", "labels_hard.json"):
        for item in json.loads((GOLDEN / name).read_text(encoding="utf-8")):
            assert item["expected_type"] in CLASSES, item["id"]
            assert item["content"].strip() and item["id"] not in seen
            seen.add(item["id"])
    hard = json.loads((GOLDEN / "labels_hard.json").read_text(encoding="utf-8"))
    assert all(h["difficulty"] in ("standard", "ambiguous") and h["rationale"] for h in hard)
    # every class has real support, so per-class recall is meaningful
    for c in CLASSES:
        assert sum(1 for h in hard if h["expected_type"] == c) >= 5, c
