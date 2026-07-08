from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, func

from backend.src.config import settings
from backend.src.db.models import LlmCall
from backend.src.db.session import async_session_factory

log = structlog.get_logger()

# Approximate cost per 1M tokens (USD) — update as pricing changes
_COST_PER_1M: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.25, 1.25),
}


class TenantBudgetExceededError(Exception):
    """Raised by check_tenant_budget when a tenant is over their daily LLM spend cap."""


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


async def check_tenant_budget(tenant_id: str) -> None:
    """Raise TenantBudgetExceededError if this tenant has already reached or
    exceeded their daily LLM spend cap. Checked BEFORE making a call — this
    blocks further spend once a tenant is over budget, rather than trying to
    predict whether the specific incoming call would push them over (which
    would require knowing output tokens before the call completes)."""
    budget = settings.default_tenant_daily_llm_budget_usd
    if budget <= 0:
        return  # unlimited in dev (default)

    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.coalesce(func.sum(LlmCall.estimated_usd), 0.0)).where(
                LlmCall.tenant_id == uuid.UUID(tenant_id),
                LlmCall.created_at >= today_start,
            )
        )
        spent_today = result.scalar_one()

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
