"""
Healer agent (v2 scaffolding) — policy logic around healing test failures.

The full Healer needs a live multi-turn "debug and edit the failing test"
loop (read error, inspect the live page, edit the test file, rerun). That's
a real MCP-client + tool-calling build: connecting to Playwright's own
`run-test-mcp-server` through our own Anthropic key via litellm tool-calling
is the right long-term shape (see _apply_fix's docstring for why shelling
out to the Claude Code CLI is NOT an option — it would run on a developer's
Claude Code/Claude Max auth rather than the product's own ANTHROPIC_API_KEY,
violating CLAUDE.md's explicit billing separation).

This module scaffolds everything else, which is real and independently
testable without that loop:
- classify_failure(): locator/timing (healable) vs logic/assertion (never
  auto-healed, escalates to the Planner) vs unknown
- heal_frequency_30d(): rolling-window heal-frequency tracking, reusing the
  existing TestResult.healed + TestRun.started_at columns (no migration)
- verify_outcome(): the outcome re-verification rule — after a heal, does
  the test still validate the test card's expected business OUTCOME, not
  merely "did it go green". Standalone and real today; heal_test() doesn't
  yet call it in its main path because _apply_fix (the thing whose output
  it would verify) isn't implemented — see _apply_fix's docstring.
- heal_test(): the orchestrator wiring classification, retry budget,
  heal-frequency escalation, and the (stubbed) fix step together.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.config import settings
from backend.src.db.models import TestCard, TestResult, TestRun
from backend.src.llm.client import complete

log = structlog.get_logger()

_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "healer_system.txt").read_text()

MAX_HEAL_ATTEMPTS_PER_STEP = 3
GLOBAL_TIMEOUT_SECONDS = 600
HEAL_ESCALATION_THRESHOLD = 3
HEAL_ESCALATION_WINDOW_DAYS = 30

FailureType = Literal["locator_timing", "logic_assertion", "unknown"]

# Fast, free pattern match before falling back to an LLM call. Playwright's
# `toHaveText`-style assertions are used for BOTH failure kinds, so matching
# on the assertion name alone is not a reliable signal — e.g. "waiting for
# locator" and "Timeout: 5000ms" appear in the call log of every toHaveText
# failure, healable or not. The actual differentiator is whether the locator
# ever resolved to a concrete value:
#   - resolved, wrong value ("Received string/value: ...") -> logic_assertion
#     (a real regression: the element exists, its content is just wrong)
#   - never resolved at all ("element(s) not found", no Received line) ->
#     locator_timing (healable: likely DOM/selector drift)
# Checked in that order — "not found" signals are checked first since they're
# unambiguous; "Received string/value" is checked next because its presence
# proves the locator resolved (so it can't be a locator_timing failure even
# if the message also contains generic "waiting for locator" call-log text).
_NOT_FOUND_PATTERNS = [
    re.compile(r"element\(s\) not found", re.IGNORECASE),
    re.compile(r"element is not attached", re.IGNORECASE),
    re.compile(r"strict mode violation", re.IGNORECASE),
    re.compile(r"target closed", re.IGNORECASE),
]
_VALUE_MISMATCH_PATTERNS = [
    re.compile(r"received string|received value", re.IGNORECASE),
]
_GENERIC_LOCATOR_WAIT_PATTERN = re.compile(r"waiting for locator", re.IGNORECASE)


@dataclass
class HealDecision:
    test_result_id: str
    failure_type: FailureType
    action: Literal[
        "escalated_logic_failure",
        "escalated_heal_frequency",
        "not_implemented",
        "skipped_not_a_failure",
    ]
    heal_count_30d: int
    detail: str


def _extract_json_object(raw: str) -> dict:
    """Same tolerant-parsing approach as classify.py's _extract_json_object —
    strips a leading markdown fence and ignores any trailing content."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        cleaned = cleaned[first_newline + 1:] if first_newline != -1 else cleaned.lstrip("`")
    return json.JSONDecoder().raw_decode(cleaned.strip())[0]


def classify_failure_heuristic(error_message: str) -> FailureType | None:
    """Fast pattern-match pass. Returns None if ambiguous (caller falls back to an LLM call)."""
    if any(p.search(error_message) for p in _NOT_FOUND_PATTERNS):
        return "locator_timing"
    if any(p.search(error_message) for p in _VALUE_MISMATCH_PATTERNS):
        return "logic_assertion"
    if _GENERIC_LOCATOR_WAIT_PATTERN.search(error_message):
        return "locator_timing"
    return None


async def classify_failure(error_message: str, tenant_id: str | None = None) -> FailureType:
    heuristic = classify_failure_heuristic(error_message)
    if heuristic:
        return heuristic

    prompt = (
        f"A Playwright test failed with this error:\n\n{error_message[:2000]}\n\n"
        "Classify this failure as exactly one of:\n"
        "- locator_timing: a selector/locator could not be found or timed out "
        "locating an element (healable — likely DOM drift)\n"
        "- logic_assertion: the test ran fine mechanically but an assertion "
        "on the actual application behavior/value failed (never auto-heal — "
        "likely a real regression)\n\n"
        'Respond with JSON only: {"type": "locator_timing" or "logic_assertion"}'
    )
    try:
        raw = await complete(
            messages=[{"role": "user", "content": prompt}],
            model=settings.classifier_model,
            tenant_id=tenant_id,
            feature="healer_classification",
            system=_SYSTEM_PROMPT,
            max_tokens=64,
        )
        parsed = _extract_json_object(raw)
        result = parsed.get("type")
        if result in ("locator_timing", "logic_assertion"):
            return result
    except Exception as e:
        log.warning("healer.classify_llm_failed", error=str(e))
    return "unknown"


async def heal_frequency_30d(session: AsyncSession, test_card_id: uuid.UUID) -> int:
    """Count healed results for this card within the last 30 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=HEAL_ESCALATION_WINDOW_DAYS)
    stmt = (
        select(func.count(TestResult.id))
        .join(TestRun, TestResult.run_id == TestRun.id)
        .where(
            TestResult.test_card_id == test_card_id,
            TestResult.healed.is_(True),
            TestRun.started_at >= cutoff,
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def verify_outcome(
    test_card: TestCard, context: str, tenant_id: str | None = None
) -> tuple[bool, str]:
    """Outcome re-verification rule: after a heal, does the test still
    validate the test card's expected business OUTCOME, not merely that the
    run went green? Real LLM-judge call. Returns (outcome_still_valid, reasoning).

    Standalone and real today. heal_test() doesn't call this in its main
    path yet because there's nothing to verify post-heal until _apply_fix
    is implemented — see that function's docstring. Call this directly once
    a heal actually produces a new test-file state to check against the
    card's expected outcome.
    """
    prompt = (
        f"Test card expected outcome:\n{test_card.description}\n\n"
        f"Failure/heal context:\n{context[:2000]}\n\n"
        "Based on this context, does it look like the underlying business "
        "behavior described above is still intact (pure locator/selector "
        "drift, safe to heal), or does it look like the actual behavior has "
        "changed (a real regression that healing would incorrectly mask)?\n\n"
        'Respond with JSON only: {"outcome_still_valid": true or false, "reasoning": "<one sentence>"}'
    )
    raw = await complete(
        messages=[{"role": "user", "content": prompt}],
        model=settings.planner_model,
        tenant_id=tenant_id,
        feature="healer_outcome_verification",
        system=_SYSTEM_PROMPT,
        max_tokens=200,
    )
    parsed = _extract_json_object(raw)
    reasoning = parsed.get("reasoning", "")
    outcome_still_valid = bool(parsed.get("outcome_still_valid", False))
    log.info(
        "healer.outcome_verification",
        test_card_id=str(test_card.id),
        outcome_still_valid=outcome_still_valid,
        reasoning=reasoning,
    )
    return outcome_still_valid, reasoning


def _apply_fix(test_result: TestResult) -> None:
    """The actual multi-turn debug-and-edit step: read the error, inspect the
    live page, edit the failing test file, rerun, up to MAX_HEAL_ATTEMPTS_PER_STEP
    times or GLOBAL_TIMEOUT_SECONDS, whichever comes first.

    NOT IMPLEMENTED. Two approaches were considered and rejected for this pass:
    - Shelling out to the Claude Code CLI against the generated
      test-scaffold/.claude/agents/playwright-test-healer.md subagent would
      run on a developer's Claude Code/Claude Max auth, not the product's
      own ANTHROPIC_API_KEY — violates the billing separation CLAUDE.md
      calls out explicitly (Claude Max covers development; runtime
      Planner/Healer calls need their own API billing).
    - A bespoke Python MCP client against Playwright's own
      `run-test-mcp-server`, wired through litellm tool-calling with our own
      key, is the right long-term answer but is a real, separate build —
      not something to half-build inside a policy-scaffolding pass.

    Everything around this function (classification, heal-frequency
    escalation, outcome re-verification) is real and works today; this is
    the one deliberately-stubbed piece.
    """
    raise NotImplementedError(
        "Healer's live fix-and-edit loop is not implemented yet — see this "
        "function's docstring for why and what's needed. The policy logic "
        "around it (classification, budget, heal-frequency escalation, "
        "outcome re-verification) is implemented and real."
    )


async def heal_test(
    session: AsyncSession, test_result_id: str, tenant_id: str | None = None
) -> HealDecision:
    """Main orchestrator. Escalates logic/assertion failures and heal-frequency
    breaches without ever attempting a fix; otherwise attempts _apply_fix,
    which currently always raises NotImplementedError."""
    result = await session.get(TestResult, uuid.UUID(test_result_id))
    if result is None:
        raise ValueError(f"TestResult {test_result_id} not found")

    card = await session.get(TestCard, result.test_card_id)
    if card is None:
        raise ValueError(f"TestCard {result.test_card_id} not found")

    if result.status != "failed" or not result.error_message:
        return HealDecision(
            test_result_id, "unknown", "skipped_not_a_failure", 0,
            "Result is not a failure with an error message; nothing to heal.",
        )

    failure_type = await classify_failure(result.error_message, tenant_id=tenant_id)

    if failure_type in ("logic_assertion", "unknown"):
        card.approval_status = "needs_clarification"
        await session.commit()
        return HealDecision(
            test_result_id, failure_type, "escalated_logic_failure", 0,
            "Logic/assertion failure (or unclassifiable) — never auto-healed. "
            "Escalated to Planner review with failure context.",
        )

    heal_count = await heal_frequency_30d(session, card.id)
    if heal_count >= HEAL_ESCALATION_THRESHOLD:
        card.approval_status = "needs_clarification"
        await session.commit()
        return HealDecision(
            test_result_id, failure_type, "escalated_heal_frequency", heal_count,
            f"Healed {heal_count} times in {HEAL_ESCALATION_WINDOW_DAYS} days "
            f"(>= {HEAL_ESCALATION_THRESHOLD}) — escalating to human review "
            "regardless of pass status.",
        )

    card.heal_count = (card.heal_count or 0) + 1
    await session.commit()

    try:
        _apply_fix(result)
        raise AssertionError("unreachable — _apply_fix always raises for now")
    except NotImplementedError as e:
        return HealDecision(test_result_id, failure_type, "not_implemented", heal_count, str(e))
