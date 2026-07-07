"""RAG retrieval for the Planner — combines chunks and bugs into ranked context."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.db.models import Bug
from backend.src.knowledge.vector_store import hybrid_search


async def retrieve_for_planning(
    session: AsyncSession,
    query: str,
    tenant_id: str,
    top_k: int = 15,
    include_bugs: bool = True,
    bug_severity_filter: list[str] | None = None,
) -> dict[str, Any]:
    """
    Returns {"chunks": [...], "bugs": [...]} for the Planner to reason over.
    Chunks come from hybrid search; bugs are filtered by severity/component.
    """
    chunks = await hybrid_search(
        session,
        query=query,
        tenant_id=tenant_id,
        limit=top_k,
        chunk_types=["acceptance_criterion", "business_rule"],
    )

    bugs: list[dict[str, Any]] = []
    if include_bugs:
        stmt = select(Bug).where(Bug.tenant_id == tenant_id)  # type: ignore[arg-type]
        if bug_severity_filter:
            stmt = stmt.where(Bug.severity.in_(bug_severity_filter))
        result = await session.execute(stmt)
        bugs = [
            {
                "external_id": b.external_id,
                "title": b.title,
                "severity": b.severity,
                "component": b.component,
                "root_cause": b.root_cause,
                "fix_version": b.fix_version,
            }
            for b in result.scalars().all()
        ]

    return {"chunks": chunks, "bugs": bugs}
