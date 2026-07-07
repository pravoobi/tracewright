from __future__ import annotations

import structlog
from sqlalchemy import text

from backend.src.config import settings

log = structlog.get_logger()

# Approximate cost per 1M tokens (USD) — update as pricing changes
_COST_PER_1M: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.25, 1.25),
}


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
    # TODO: persist to a llm_calls table and enforce per-tenant daily budgets
    # For now we log so Langfuse/structured logs capture it from day one


async def check_tenant_budget(tenant_id: str, estimated_usd: float) -> bool:
    """Return False if this call would breach the tenant's daily budget."""
    budget = settings.default_tenant_daily_llm_budget_usd
    if budget == 0:
        return True  # unlimited in dev
    # TODO: query today's spend from llm_calls table and compare
    return True
