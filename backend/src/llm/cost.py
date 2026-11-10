from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, func, text

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
    """Raised by reserve_budget when a tenant is over their daily LLM spend cap."""


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
    reservation_id: uuid.UUID | None = None,
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
    #
    # Best-effort: the LLM call has ALREADY completed and cost real money by
    # this point, so a transient DB error here must not fail the whole
    # request (and hand the customer a 500 for a call that actually
    # succeeded) -- log and move on, at the cost of that one call being
    # invisible to budget tracking and the cost dashboard.
    try:
        async with async_session_factory() as session:
            if reservation_id is not None:
                # Replace the pre-call worst-case reservation with the real cost.
                row = await session.get(LlmCall, reservation_id)
                if row is not None:
                    row.input_tokens = input_tokens
                    row.output_tokens = output_tokens
                    row.estimated_usd = estimated_usd
                    row.latency_ms = latency_ms
                    await session.commit()
                    return
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
    except Exception:
        log.error(
            "llm.cost_record_failed",
            tenant_id=tenant_id,
            feature=feature,
            estimated_usd=estimated_usd,
            exc_info=True,
        )


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


def estimate_call_usd(model: str, messages: list[dict], max_tokens: int | None) -> float:
    """Worst-case cost of one call, used to reserve budget before it runs:
    prompt size (~4 chars/token) at the input rate plus max_tokens at the
    output rate."""
    prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
    return _estimate_usd(model, prompt_chars // 4 + 1, max_tokens or 4096)


async def reserve_budget(
    tenant_id: str | None, feature: str, model: str, estimate_usd: float
) -> uuid.UUID | None:
    """Atomically check the tenant's daily budget and reserve this call's
    worst-case cost, in ONE short transaction -- nothing is held while the
    (multi-second) LLM call runs.

    The previous design held a session-level advisory lock plus a pooled
    connection for the whole call. That serialized a tenant's calls, let a
    few concurrent tenants exhaust the pool, and -- because session-level
    advisory locks survive the pool's rollback-on-return -- a cancelled
    request or failed unlock left the lock held forever, deadlocking every
    later call for that tenant. Here the lock is transaction-scoped
    (pg_advisory_xact_lock), so it is always released at commit/rollback,
    and concurrent calls see each other's reservations as already-spent.

    Returns the reservation row id (pass to record_llm_call, or
    release_budget on failure), or None when budgets are disabled."""
    budget = settings.default_tenant_daily_llm_budget_usd
    if not tenant_id or budget <= 0:
        return None

    async with async_session_factory() as session:
        async with session.begin():
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:k)"), {"k": _advisory_lock_key(tenant_id)}
            )
            spent_today = await _spent_today(session, tenant_id)
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
            row = LlmCall(
                tenant_id=uuid.UUID(tenant_id),
                feature=feature,
                model=model,
                input_tokens=0,
                output_tokens=0,
                estimated_usd=estimate_usd,
                latency_ms=0,
            )
            session.add(row)
            await session.flush()
            return row.id


async def release_budget(reservation_id: uuid.UUID | None) -> None:
    """Drop a reservation whose LLM call failed (it cost nothing)."""
    if reservation_id is None:
        return
    try:
        async with async_session_factory() as session:
            row = await session.get(LlmCall, reservation_id)
            if row is not None:
                await session.delete(row)
                await session.commit()
    except Exception:
        log.error("llm.reservation_release_failed", reservation_id=str(reservation_id), exc_info=True)


def _advisory_lock_key(tenant_id: str) -> int:
    # pg_advisory_xact_lock takes a signed 64-bit int; fold the tenant UUID
    # down into that range deterministically (collisions just mean two
    # tenants occasionally serialize their short reserve step).
    return uuid.UUID(tenant_id).int & 0x7FFFFFFFFFFFFFFF
