"""Product metrics — CLAUDE.md names these first-class from day one:
review time per artifact, % chunks auto-approved, human edits per generated
test, locator verification pass rate. All four existed as raw per-row data
(or, for edits/locator strategy, didn't exist as data at all) with no
aggregation endpoint anywhere until now.

compute_tenant_metrics() is the shared core, used by both the API endpoint
below and the eval harness (backend/evals/run_evals.py) — the harness's own
module docstring names these same metrics as in-scope, but only ever
computed classification accuracy; the other three are real, already-solved
aggregation queries, not a separate eval-specific computation.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.db.models import Chunk, TestCard
from backend.src.db.session import get_session

router = APIRouter(prefix="/metrics", tags=["metrics"])


async def compute_tenant_metrics(session: AsyncSession, tenant_id: str) -> dict[str, Any]:
    tid = uuid.UUID(tenant_id)

    # Review time per artifact — median, not average: a handful of very
    # slow/very fast reviews shouldn't dominate the number that decides
    # whether the product is actually faster than manual test authoring.
    chunk_median = await session.scalar(
        select(func.percentile_cont(0.5).within_group(Chunk.review_duration_ms))
        .where(Chunk.tenant_id == tid, Chunk.review_duration_ms.isnot(None))
    )
    card_median = await session.scalar(
        select(func.percentile_cont(0.5).within_group(TestCard.review_duration_ms))
        .where(TestCard.tenant_id == tid, TestCard.review_duration_ms.isnot(None))
    )

    # % chunks auto-approved
    chunk_total = await session.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.tenant_id == tid)
    )
    chunk_auto_approved = await session.scalar(
        select(func.count()).select_from(Chunk).where(
            Chunk.tenant_id == tid, Chunk.review_status == "auto_approved"
        )
    )
    auto_approval_rate = (chunk_auto_approved / chunk_total) if chunk_total else None

    # Human edits per generated test
    card_total = await session.scalar(
        select(func.count()).select_from(TestCard).where(TestCard.tenant_id == tid)
    )
    avg_edits = await session.scalar(
        select(func.avg(TestCard.edit_count)).where(TestCard.tenant_id == tid)
    )
    cards_edited = await session.scalar(
        select(func.count()).select_from(TestCard).where(
            TestCard.tenant_id == tid, TestCard.edit_count > 0
        )
    )
    edit_rate = (cards_edited / card_total) if card_total else None

    # Locator verification pass rate — "pass" means the preferred
    # role-based strategy resolved cleanly, no CSS/testid fallback needed
    generated_total = await session.scalar(
        select(func.count()).select_from(TestCard).where(
            TestCard.tenant_id == tid, TestCard.locator_strategy.isnot(None)
        )
    )
    role_count = await session.scalar(
        select(func.count()).select_from(TestCard).where(
            TestCard.tenant_id == tid, TestCard.locator_strategy == "role"
        )
    )
    locator_pass_rate = (role_count / generated_total) if generated_total else None

    return {
        "review_time": {
            "chunk_median_ms": chunk_median,
            "test_card_median_ms": card_median,
        },
        "chunk_auto_approval_rate": auto_approval_rate,
        "chunks_total": chunk_total,
        "chunks_auto_approved": chunk_auto_approved,
        "human_edits": {
            "avg_edits_per_test_card": float(avg_edits) if avg_edits is not None else None,
            "edit_rate": edit_rate,
            "test_cards_total": card_total,
            "test_cards_edited": cards_edited,
        },
        "locator_verification": {
            "pass_rate": locator_pass_rate,
            "generated_total": generated_total,
            "role_based": role_count,
        },
    }


@router.get("/{tenant_id}")
async def get_metrics(tenant_id: str, session: AsyncSession = Depends(get_session)):
    return await compute_tenant_metrics(session, tenant_id)
