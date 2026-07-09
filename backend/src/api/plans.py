"""Planner review API — generate plan, approve/edit/reject test cards, bulk actions."""
from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.agents.planner import generate_test_plan, persist_plan
from backend.src.auth.api_key import require_tenant_access
from backend.src.db.models import TestCard
from backend.src.db.session import get_session

router = APIRouter(
    prefix="/plans",
    tags=["plans"],
    dependencies=[Depends(require_tenant_access)],
)


class GeneratePlanRequest(BaseModel):
    feature_area: str
    doc_version: str
    # Unbounded top_k let a caller balloon a single Planner call's retrieved-
    # chunk count arbitrarily -- context size (and $ cost, uncapped by the
    # per-tenant budget check until AFTER the call completes) scales directly
    # with it. 50 comfortably covers legitimate feature-area queries per the
    # retrieval design (top_k=15 default).
    top_k: int = Field(default=15, ge=1, le=50)


class ReviewCardAction(BaseModel):
    action: Literal["approve", "reject", "needs_clarification"]
    edits: dict[str, Any] | None = None
    review_duration_ms: int | None = None
    approved_by: str | None = None


class BulkCardAction(BaseModel):
    card_ids: list[str]
    action: Literal["approve", "reject"]
    approved_by: str | None = None


@router.post("/{tenant_id}/generate")
async def generate_plan(
    tenant_id: str,
    body: GeneratePlanRequest,
    session: AsyncSession = Depends(get_session),
):
    plan = await generate_test_plan(
        session,
        tenant_id=tenant_id,
        feature_area=body.feature_area,
        doc_version=body.doc_version,
        top_k=body.top_k,
    )
    card_ids = await persist_plan(session, tenant_id=tenant_id, plan=plan)
    return {
        "test_card_ids": card_ids,
        "coverage_gaps": plan["coverage_gaps"],
        "clarification_flags": plan["clarification_flags"],
    }


@router.get("/{tenant_id}/cards")
async def list_cards(
    tenant_id: str,
    approval_status: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(TestCard).where(TestCard.tenant_id == uuid.UUID(tenant_id))
    if approval_status:
        stmt = stmt.where(TestCard.approval_status == approval_status)
    result = await session.execute(stmt)
    cards = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "test_id": c.test_id,
            "title": c.title,
            "description": c.description,
            "preconditions": c.preconditions,
            "priority": c.priority,
            "test_type": c.test_type,
            "approval_status": c.approval_status,
            "setup_manifest": c.setup_manifest,
            "tier_sources": c.tier_sources,
            "introduced_in_version": c.introduced_in_version,
            "locator_strategy": c.locator_strategy,
            "locator_suggestions": c.locator_suggestions,
        }
        for c in cards
    ]


@router.patch("/{tenant_id}/cards/{card_id}/review")
async def review_card(
    tenant_id: str,
    card_id: str,
    body: ReviewCardAction,
    session: AsyncSession = Depends(get_session),
):
    from datetime import datetime, timezone

    status_map = {
        "approve": "approved",
        "reject": "rejected",
        "needs_clarification": "needs_clarification",
    }
    values: dict[str, Any] = {
        "approval_status": status_map[body.action],
        "review_duration_ms": body.review_duration_ms,
    }
    if body.action == "approve":
        values["approved_by"] = body.approved_by
        values["approved_at"] = datetime.now(timezone.utc)
    if body.edits:
        for field, val in body.edits.items():
            if field in ("title", "description", "preconditions", "priority", "setup_manifest"):
                values[field] = val
        # "Human edits per generated test" (CLAUDE.md product metric) — one
        # review action with a non-empty edits payload counts as one edit,
        # regardless of how many fields it touched.
        values["edit_count"] = TestCard.edit_count + 1

    await session.execute(
        update(TestCard)
        .where(TestCard.id == uuid.UUID(card_id), TestCard.tenant_id == uuid.UUID(tenant_id))
        .values(**values)
    )
    await session.commit()
    return {"status": "ok"}


@router.post("/{tenant_id}/cards/bulk-review")
async def bulk_review_cards(
    tenant_id: str,
    body: BulkCardAction,
    session: AsyncSession = Depends(get_session),
):
    from datetime import datetime, timezone

    status_map = {"approve": "approved", "reject": "rejected"}
    card_uuids = [uuid.UUID(cid) for cid in body.card_ids]
    values: dict[str, Any] = {"approval_status": status_map[body.action]}
    if body.action == "approve":
        values["approved_by"] = body.approved_by
        values["approved_at"] = datetime.now(timezone.utc)

    await session.execute(
        update(TestCard)
        .where(TestCard.id.in_(card_uuids), TestCard.tenant_id == uuid.UUID(tenant_id))
        .values(**values)
    )
    await session.commit()
    return {"updated": len(body.card_ids)}
