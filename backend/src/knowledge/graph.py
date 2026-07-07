"""Traceability graph — links between test cards and chunks/bugs."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.db.models import TraceabilityLink


async def add_links(
    session: AsyncSession,
    tenant_id: str,
    test_card_id: str,
    links: list[dict[str, str]],
) -> None:
    """Add traceability links. links = [{"type": "chunk"|"bug", "logical_id": ..., "reason": ...}]"""
    for link in links:
        obj = TraceabilityLink(
            tenant_id=uuid.UUID(tenant_id),
            test_card_id=uuid.UUID(test_card_id),
            linked_type=link["type"],
            linked_logical_id=link["logical_id"],
            link_reason=link.get("reason"),
        )
        session.add(obj)
    await session.commit()


async def get_links_for_test(
    session: AsyncSession, test_card_id: str
) -> list[dict[str, Any]]:
    stmt = select(TraceabilityLink).where(
        TraceabilityLink.test_card_id == uuid.UUID(test_card_id)
    )
    result = await session.execute(stmt)
    return [
        {
            "linked_type": r.linked_type,
            "linked_logical_id": r.linked_logical_id,
            "link_reason": r.link_reason,
        }
        for r in result.scalars().all()
    ]
