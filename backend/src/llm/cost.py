from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, func, text

from backend.src.config import settings
from backend.src.db.models import LlmCall
from backend.src.db.session import async_session_factory, engine

log = structlog.get_logger()

# Approximate cost per 1M tokens (USD) — update as pricing changes
_COST_PER_1M: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.25, 1.25),
}


class TenantBudgetExceededError(Exception):
    """Raised by budget_guard when a tenant is over their daily LLM spend cap."""


def _estimate_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    input_rate, output_rate = _COST_PER_1M.get(model, (3.0, 15.0))
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000


async def record_llm_call(
    tenant_id: str | None,
    feature: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
) -> None:
    estimated_usd = _estimate_usd(model, input_tokens, output_tokens)
    log.info(
        "llm.cost",
        tenant_id=tenant_id,
        feature=feature,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_usd=estimated_usd,
        latency_ms=latency_ms,
    )

    # Own short-lived session, deliberately decoupled from the caller's
    # transaction: the LLM call already cost real money by this point, so
    # the cost record must persist even if the caller's own business-logic
    # transaction later rolls back.
    async with async_session_factory() as session:
        session.add(
            LlmCall(
                tenant_id=uuid.UUID(tenant_id) if tenant_id else None,
                feature=feature,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_usd=estimated_usd,
                latency_ms=latency_ms,
            )
        )
        await session.commit()


async def _spent_today(conn, tenant_id: str) -> float:
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    result = await conn.execute(
        select(func.coalesce(func.sum(LlmCall.estimated_usd), 0.0)).where(
            LlmCall.tenant_id == uuid.UUID(tenant_id),
            LlmCall.created_at >= today_start,
        )
    )
    return result.scalar_one()


def _advisory_lock_key(tenant_id: str) -> int:
    # pg_advisory_lock takes a signed 64-bit int; fold the tenant UUID down
    # into that range deterministically (collisions just mean two tenants
    # occasionally serialize against each other, not a correctness problem).
    return uuid.UUID(tenant_id).int & 0x7FFFFFFFFFFFFFFF


@asynccontextmanager
async def budget_guard(tenant_id: str | None):
    """Check-then-spend on the daily LLM budget used to race: the check ran
    BEFORE the (multi-second) LLM call, and spend was only recorded AFTER —
    so N concurrent calls for the same tenant could all read the same
    pre-call spend total, all pass, and only get caught after collectively
    overshooting the cap by up to N call-costs. Holds a Postgres session-
    level advisory lock keyed by tenant for the ENTIRE check-call-record
    window (not just the check), so a second call for the same tenant can't
    even start until the first one's spend has actually landed. Different
    tenants never block each other. No-op when budgets are disabled
    (the default) or tenant_id is absent."""
    budget = settings.default_tenant_daily_llm_budget_usd
    if not tenant_id or budget <= 0:
        yield
        return

    lock_key = _advisory_lock_key(tenant_id)
    async with engine.connect() as conn:
        await conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": lock_key})
        try:
            spent_today = await _spent_today(conn, tenant_id)
            if spent_today >= budget:
                log.warning(
                    "llm.budget_exceeded",
                    tenant_id=tenant_id,
                    spent_today=spent_today,
                    budget=budget,
                )
                raise TenantBudgetExceededError(
                    f"Tenant {tenant_id} has spent ${spent_today:.4f} today, "
                    f"at or above the ${budget:.4f} daily LLM budget."
                )
            yield
        finally:
            await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": lock_key})
