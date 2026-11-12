import json

from backend.evals.run_codegen_eval import _collect_results, compare_to_baseline, summarize


def _row(tid, ac, generated=True, passed=True, traced=True, retried=False):
    return {"test_id": tid, "traceability": [{"type": "chunk", "logical_id": ac}],
            "generated": generated, "passed": passed, "traced": traced, "retried": retried}


def test_summarize_counts_failures_and_ac_coverage():
    rows = [
        _row("A", "REQ-1"),
        _row("B", "REQ-1", passed=False),   # same AC, one passing spec is enough
        _row("C", "REQ-2", passed=False),   # AC with no passing spec
        _row("D", "REQ-3", generated=False, passed=False, traced=False),
    ]
    s = summarize(rows)
    assert s["cards_attempted"] == 4 and s["cards_generated"] == 3
    assert s["pass_rate"] == round(1 / 3, 3)
    assert s["pass_rate_of_attempted"] == 0.25
    assert s["ac_coverage_pass"] == round(1 / 3, 3)  # REQ-1 only, of REQ-1/2/3


def test_compare_to_baseline_flags_only_regressions():
    base = {"generated_rate": 1.0, "pass_rate": 1.0, "pass_rate_of_attempted": 1.0,
            "ac_coverage_pass": 1.0, "traceability_rate": 1.0}
    same = dict(base, retry_rate=0.0)
    assert compare_to_baseline(same, base) == []
    worse = dict(same, pass_rate=0.8, retry_rate=0.5)
    flagged = compare_to_baseline(worse, base)
    assert flagged == ["pass_rate: 1.0 -> 0.8"]  # retry_rate is informational


def test_collect_results_marks_failed_and_missing_specs(tmp_path):
    report = tmp_path / "r.json"
    report.write_text(json.dumps({"suites": [{"suites": [], "specs": [
        {"file": "_eval_1/tc-001.spec.ts", "ok": True, "tests": []},
        {"file": "_eval_1/tc-002.spec.ts", "ok": False, "tests": [
            {"results": [{"error": {"message": "expect(received).toBe(expected)"}}]}]},
    ]}]}), encoding="utf-8")
    res = _collect_results(report)
    assert res["tc-001.spec.ts"]["passed"] is True
    assert res["tc-002.spec.ts"]["passed"] is False and "toBe" in res["tc-002.spec.ts"]["error"]
    assert "tc-003.spec.ts" not in res  # a spec that never ran has no entry
    assert _collect_results(tmp_path / "missing.json") == {}
