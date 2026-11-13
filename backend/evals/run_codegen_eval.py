"""Codegen eval: do approved test cards turn into specs that actually run green?

    uv run python -m backend.evals.run_codegen_eval [--cards TC-001,TC-003]
        [--baseline backend/evals/results/codegen-baseline.json]
        [--min-pass-rate 0.8] [--save-baseline]
        [--golden [--base-url http://localhost:4000]]

--golden is the hermetic mode used in CI: cards and the page-object registry
come from backend/evals/golden/ (codegen_cards.json, app_model_registry.json)
instead of the dev database and MinIO, and the demo app is logged into
directly. It needs only the demo app running, Playwright (Python and the
scaffold's), and the LLM key.

For every approved card of the dev tenant that traces to a requirement, this
generates the spec exactly as the product does (generate_test_file: safety
check, import/member check, retry), writes it unedited into a throwaway
folder of test-scaffold, runs it against the live demo environment, and
reports:

  generated_rate        cards that produced a spec / cards attempted
  pass_rate             specs that passed / specs generated
                        (= "% of ACs producing a passing test with ZERO human
                        edits": the specs are never touched)
  ac_coverage_pass      distinct source requirements with >=1 passing spec /
                        distinct source requirements among attempted cards
  traceability_rate     specs whose header names a source requirement
  retry_rate            generations that needed the invented-import/member retry

Exit status is non-zero if pass_rate < --min-pass-rate or it regresses against
--baseline. Needs: the demo app up, a fresh captured auth session for the
environment (scripts/capture-demo-auth-session.py), a built registry, the LLM
key, and Playwright installed in test-scaffold. It spends real LLM tokens
(one codegen call per card, two if it retries).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import structlog

from backend.src.agents.generator.app_model import AppModelRegistry
from backend.src.agents.generator.codegen import (
    UnsafeGeneratedCodeError,
    generate_test_file,
    rebase_scaffold_imports,
    safe_filename,
)

log = structlog.get_logger()

REPO = Path(__file__).resolve().parents[2]
SCAFFOLD = REPO / "test-scaffold"
RESULTS_DIR = Path(__file__).parent / "results"
DEV_TENANT_ID = "00000000-0000-0000-0000-000000000001"


async def _load_inputs(tenant_id: str, only: set[str] | None):
    from sqlalchemy import select

    from backend.src.db.models import Environment, TestCard, TraceabilityLink
    from backend.src.db.session import async_session_factory
    from backend.src.storage.files import download_file, registry_path

    async with async_session_factory() as s:
        env = await s.scalar(
            select(Environment)
            .where(Environment.tenant_id == uuid.UUID(tenant_id), Environment.url.is_not(None))
            .order_by(Environment.updated_at.desc(), Environment.id.asc())
        )
        if env is None:
            raise SystemExit("No environment with a URL for this tenant")
        cards = (
            await s.scalars(
                select(TestCard).where(
                    TestCard.tenant_id == uuid.UUID(tenant_id), TestCard.approval_status == "approved"
                ).order_by(TestCard.test_id)
            )
        ).all()
        out = []
        for c in cards:
            if only and c.test_id not in only:
                continue
            links = (
                await s.scalars(select(TraceabilityLink).where(TraceabilityLink.test_card_id == c.id))
            ).all()
            if not any(l.linked_type == "chunk" for l in links):
                log.info("codegen_eval.skip_unlinked", test_id=c.test_id)
                continue
            out.append(
                {
                    "test_id": c.test_id,
                    "title": c.title,
                    "description": c.description,
                    "preconditions": c.preconditions,
                    "setup_manifest": c.setup_manifest,
                    "test_type": c.test_type,
                    "priority": c.priority,
                    "traceability": [
                        {"type": l.linked_type, "logical_id": l.linked_logical_id} for l in links
                    ],
                }
            )
        try:
            registry = AppModelRegistry.from_dict(
                json.loads(download_file(registry_path(tenant_id, str(env.id))))
            )
        except Exception as e:
            raise SystemExit(f"No registry for environment {env.id}: build it first ({e})")
    return env, out, registry


GOLDEN_DIR = Path(__file__).parent / "golden"


def _load_inputs_golden(only: set[str] | None):
    """Cards + registry from the committed golden files; no DB or object store."""
    from types import SimpleNamespace

    cards_file = json.loads((GOLDEN_DIR / "codegen_cards.json").read_text(encoding="utf-8"))
    cards = [c for c in cards_file["cards"] if not only or c["test_id"] in only]
    registry = AppModelRegistry.from_dict(
        json.loads((GOLDEN_DIR / "app_model_registry.json").read_text(encoding="utf-8"))
    )
    return SimpleNamespace(url=cards_file["environment_url"], id="golden"), cards, registry


async def _login_demo_session(base_url: str) -> Path:
    """Log into the demo app (public seeded demo credentials) and write the
    storage state where the scaffold fixture expects it."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(f"{base_url}/login")
            await page.get_by_label("Email").fill("test@example.com")
            await page.get_by_label("Password").fill("password123")
            await page.get_by_role("button", name="Log in").click()
            await page.wait_for_url(f"{base_url}/cart")
            state = await page.context.storage_state()
        finally:
            await browser.close()
    path = SCAFFOLD / ".auth" / "demo-app.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


def _check_reachable(url: str) -> None:
    try:
        urllib.request.urlopen(url, timeout=5)  # noqa: S310 - the environment URL we registered
    except Exception as e:
        raise SystemExit(f"Environment {url} is not reachable: {e}")


def _export_session(tenant_id: str, environment_id: str) -> Path:
    """Decrypt the captured auth session where the scaffold fixture expects it."""
    from backend.src.auth_capture.sessions import load_session

    path = SCAFFOLD / ".auth" / "demo-app.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(load_session(tenant_id, environment_id)), encoding="utf-8")
    return path


def _run_playwright(spec_dir: Path, base_url: str, storage_state: Path, report: Path) -> None:
    env = {
        **os.environ,
        "BASE_URL": base_url,
        "STORAGE_STATE_PATH": str(storage_state),
        "PLAYWRIGHT_JSON_OUTPUT_NAME": str(report),
        "CI": "",
    }
    npx = "npx.cmd" if sys.platform == "win32" else "npx"
    rel = spec_dir.relative_to(SCAFFOLD).as_posix()
    subprocess.run(  # noqa: S603 - fixed argv, paths are ours
        [npx, "playwright", "test", rel, "--reporter=json"],
        cwd=SCAFFOLD,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        timeout=600,
        check=False,
    )


def _collect_results(report: Path) -> dict[str, dict[str, Any]]:
    """{spec file name: {"passed": bool, "error": str|None}} from the JSON report."""
    if not report.exists():
        return {}
    data = json.loads(report.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}

    def walk(suite: dict[str, Any]) -> None:
        for spec in suite.get("specs", []):
            name = Path(spec.get("file", "")).name
            ok = spec.get("ok", False)
            err = None
            if not ok:
                for t in spec.get("tests", []):
                    for r in t.get("results", []):
                        if r.get("error"):
                            err = (r["error"].get("message") or "")[:300]
            prev = out.get(name)
            out[name] = {"passed": ok and (prev is None or prev["passed"]), "error": err or (prev or {}).get("error")}
        for child in suite.get("suites", []):
            walk(child)

    for suite in data.get("suites", []):
        walk(suite)
    return out


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    attempted = len(rows)
    generated = [r for r in rows if r["generated"]]
    passed = [r for r in generated if r["passed"]]
    acs = {l["logical_id"] for r in rows for l in r["traceability"] if l["type"] == "chunk"}
    acs_passing = {
        l["logical_id"] for r in passed for l in r["traceability"] if l["type"] == "chunk"
    }
    return {
        "cards_attempted": attempted,
        "cards_generated": len(generated),
        "generated_rate": round(len(generated) / attempted, 3) if attempted else 0.0,
        "specs_passed": len(passed),
        "pass_rate": round(len(passed) / len(generated), 3) if generated else 0.0,
        "pass_rate_of_attempted": round(len(passed) / attempted, 3) if attempted else 0.0,
        "ac_coverage_pass": round(len(acs_passing) / len(acs), 3) if acs else 0.0,
        "traceability_rate": round(sum(1 for r in generated if r["traced"]) / len(generated), 3)
        if generated
        else 0.0,
        "retry_rate": round(sum(1 for r in generated if r["retried"]) / len(generated), 3)
        if generated
        else 0.0,
    }


def compare_to_baseline(
    summary: dict[str, Any], baseline: dict[str, Any], allow_card_drops: int = 0
) -> list[str]:
    """Metrics that got worse than the baseline (higher is better for all but retry_rate).

    LLM generation is nondeterministic, so a baseline over a handful of cards
    would flag a single flaky card as a regression. `allow_card_drops` forgives
    that many cards' worth of drop (N / cards_attempted) per metric; the absolute
    pass-rate floor is enforced separately and is not loosened by this.
    """
    worse = []
    slack = allow_card_drops / max(summary.get("cards_attempted", 0), 1)
    for key in ("generated_rate", "pass_rate", "pass_rate_of_attempted", "ac_coverage_pass", "traceability_rate"):
        if summary[key] < baseline.get(key, 0.0) - slack - 1e-9:
            worse.append(f"{key}: {baseline[key]} -> {summary[key]}")
    return worse


async def _generate_all(cards, registry, tenant_id, spec_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for card in cards:
        row = {
            "test_id": card["test_id"],
            "traceability": card["traceability"],
            "generated": False,
            "passed": False,
            "traced": False,
            "retried": False,
            "file": None,
            "error": None,
        }
        retries_before = _count_retries()
        try:
            code = await generate_test_file(card, registry, tenant_id=tenant_id)
            fname = safe_filename(card["test_id"], card["title"])
            (spec_dir / fname).write_text(rebase_scaffold_imports(code), encoding="utf-8", newline="\n")
            row.update(generated=True, file=fname, traced=not re.search(r"Source AC\s*: UNLINKED", code))
        except UnsafeGeneratedCodeError as e:
            row["error"] = str(e)[:300]
        except Exception as e:  # LLM/API failure counts as not generated
            row["error"] = f"{type(e).__name__}: {e}"[:300]
        row["retried"] = _count_retries() > retries_before
        rows.append(row)
        log.info("codegen_eval.card", test_id=card["test_id"], generated=row["generated"], error=row["error"])
    return rows


_retry_count = 0


def _count_retries() -> int:
    return _retry_count


def _install_retry_counter() -> None:
    """Count codegen's invented-import/member retries via its warning log event."""
    import backend.src.agents.generator.codegen as codegen

    real = codegen.log

    class _Counting:
        def __getattr__(self, name):
            fn = getattr(real, name)
            if name != "warning":
                return fn

            def wrapper(event, *a, **kw):
                global _retry_count
                if event == "codegen.unresolved_imports":
                    _retry_count += 1
                return fn(event, *a, **kw)

            return wrapper

    codegen.log = _Counting()  # type: ignore[assignment]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant-id", default=DEV_TENANT_ID)
    ap.add_argument("--cards", help="comma-separated test ids (default: all approved, linked)")
    ap.add_argument("--baseline", help="JSON file of a previous summary to compare against")
    ap.add_argument("--golden", action="store_true", help="use backend/evals/golden/ instead of the dev DB/MinIO")
    ap.add_argument("--base-url", help="with --golden: where the demo app is running (default: the golden file's URL)")
    ap.add_argument("--min-pass-rate", type=float, default=0.8)
    ap.add_argument(
        "--allow-card-drops",
        type=int,
        default=1,
        help="with --baseline: tolerate this many cards worse than baseline (LLM flakiness)",
    )
    ap.add_argument("--save-baseline", action="store_true", help="write this run to results/codegen-baseline.json")
    args = ap.parse_args()

    _install_retry_counter()
    only = set(args.cards.split(",")) if args.cards else None
    if args.golden:
        env, cards, registry = _load_inputs_golden(only)
        if args.base_url:
            env.url = args.base_url.rstrip("/")
    else:
        env, cards, registry = await _load_inputs(args.tenant_id, only)
    if not cards:
        raise SystemExit("No approved, requirement-linked cards to evaluate")
    _check_reachable(env.url)
    if args.golden:
        storage_state = await _login_demo_session(env.url)
    else:
        storage_state = _export_session(args.tenant_id, str(env.id))

    spec_dir = SCAFFOLD / "tests" / f"_eval_{int(time.time())}"
    spec_dir.mkdir(parents=True)
    report = Path(tempfile.gettempdir()) / f"codegen-eval-{uuid.uuid4().hex[:8]}.json"
    try:
        rows = await _generate_all(cards, registry, args.tenant_id, spec_dir)
        if any(r["generated"] for r in rows):
            await asyncio.to_thread(_run_playwright, spec_dir, env.url, storage_state, report)
        results = _collect_results(report)
    finally:
        # Keep what was generated so a failing card can be diagnosed from the
        # CI artifact (the temp spec dir is removed below).
        kept = RESULTS_DIR / "specs-latest"
        shutil.rmtree(kept, ignore_errors=True)
        if spec_dir.exists():
            RESULTS_DIR.mkdir(exist_ok=True)
            shutil.copytree(spec_dir, kept)
        shutil.rmtree(spec_dir, ignore_errors=True)
        report.unlink(missing_ok=True)

    for r in rows:
        if r["generated"]:
            res = results.get(r["file"])
            r["passed"] = bool(res and res["passed"])
            if res and not res["passed"]:
                r["error"] = res["error"]
            elif res is None:
                r["error"] = "spec produced no result (failed to load?)"

    summary = summarize(rows)
    RESULTS_DIR.mkdir(exist_ok=True)
    out = {"run_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "summary": summary, "cards": rows}
    (RESULTS_DIR / "codegen-latest.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    if args.save_baseline:
        (RESULTS_DIR / "codegen-baseline.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n=== Codegen Eval ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    for r in rows:
        status = "PASS" if r["passed"] else ("GEN-FAIL" if not r["generated"] else "FAIL")
        print(f"  [{status}] {r['test_id']}" + (f" - {r['error']}" if r["error"] else ""))

    failed = False
    if summary["pass_rate_of_attempted"] < args.min_pass_rate:
        print(f"\nFAIL: pass rate {summary['pass_rate_of_attempted']} < {args.min_pass_rate}")
        failed = True
    if args.baseline:
        worse = compare_to_baseline(
            summary,
            json.loads(Path(args.baseline).read_text(encoding="utf-8")),
            allow_card_drops=args.allow_card_drops,
        )
        if worse:
            print("\nFAIL: regressed vs baseline:\n  " + "\n  ".join(worse))
            failed = True
    if not failed:
        print("\nPASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
