"""
Planner eval: does the planner turn requirements + bug history into a traceable,
honest test plan?

Run: uv run python -m backend.evals.run_planner_eval

Hermetic (no retrieval/database reads): golden chunks are handed to the planner
directly, so only the planning step is measured. Needs the LLM key; the cost
recorder writes to the dev database like every other LLM call.
Scores: AC coverage, traceability validity, bug-regression links, schema,
setup-manifest grounding, and judgement on planted requirements (a
contradiction, an untestable statement, a prompt injection).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import structlog

from backend.evals.planner_cases import build_cases
from backend.evals.planner_metrics import aggregate, gate, score_case

log = structlog.get_logger()
RESULTS_DIR = Path(__file__).parent / "results"
TENANT = "00000000-0000-0000-0000-000000000001"


async def _run_case(case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    from backend.src.agents.planner import plan_from_context

    context = {"chunks": case["chunks"], "bugs": case["bugs"]}
    plan = await plan_from_context(TENANT, case["feature_area"], case["doc_version"], context)
    return plan, score_case(plan, case)


async def main() -> int:
    cases = build_cases()
    results = await asyncio.gather(*(_run_case(c) for c in cases))
    scored = [r[1] for r in results]
    summary = aggregate(scored)

    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "planner-latest.json").write_text(
        json.dumps(
            {"summary": summary, "cases": scored, "plans": {c["name"]: p for c, (p, _) in zip(cases, results)}},
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n=== Planner eval ===")
    for s in scored:
        print(
            f"  [{s['name']}] chunks {s['gold_chunks']}, cards {s['cards']}, covered {s['covered']}, "
            f"accounted {s['accounted']}, bugs {s['bugs_found']}/{s['bugs_expected']}, "
            f"clarification cards {s['needs_clarification_cards']}"
        )
        if s["uncovered"]:
            print(f"      uncovered: {s['uncovered']}")
        if s["bugs_missed"]:
            print(f"      bugs not linked: {s['bugs_missed']}")
        if s["schema_problems"]:
            print(f"      schema: {s['schema_problems'][:5]}")
        for name, ok in s["planted_checks"].items():
            print(f"      planted {name}: {'ok' if ok else 'FAILED'}")
    print()
    for k, v in summary.items():
        print(f"  {k}: {v}")

    failures = gate(summary)
    if failures:
        print("\nFAIL:\n  " + "\n  ".join(failures))
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
