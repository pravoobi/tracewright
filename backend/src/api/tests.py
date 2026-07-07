"""Test runs and results API."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.db.models import TestResult, TestRun
from backend.src.db.session import get_session
from backend.src.versioning.filtering import is_applicable

router = APIRouter(prefix="/tests", tags=["tests"])


@router.get("/{tenant_id}/applicable")
async def get_applicable_tests(
    tenant_id: str,
    environment_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Return test cards applicable to the given environment, filtered by version."""
    from backend.src.db.models import Environment, TestCard, Tenant
    from sqlalchemy import select

    env_stmt = select(Environment).where(
        Environment.id == uuid.UUID(environment_id),
        Environment.tenant_id == uuid.UUID(tenant_id),
    )
    env_result = await session.execute(env_stmt)
    env = env_result.scalar_one_or_none()
    if not env:
        return {"error": "Environment not found"}

    tenant_stmt = select(Tenant).where(Tenant.id == uuid.UUID(tenant_id))
    tenant_result = await session.execute(tenant_stmt)
    tenant = tenant_result.scalar_one_or_none()
    version_ordering = tenant.version_ordering if tenant else []

    cards_stmt = select(TestCard).where(
        TestCard.tenant_id == uuid.UUID(tenant_id),
        TestCard.approval_status == "approved",
    )
    cards_result = await session.execute(cards_stmt)
    all_cards = cards_result.scalars().all()

    applicable = [
        {
            "id": str(c.id),
            "test_id": c.test_id,
            "title": c.title,
            "playwright_code_path": c.playwright_code_path,
            "setup_manifest": c.setup_manifest,
        }
        for c in all_cards
        if is_applicable(
            card={"introduced_in_version": c.introduced_in_version,
                  "deprecated_in_version": c.deprecated_in_version,
                  "applicability": c.applicability},
            env_code_version=env.code_version,
            env_name=env.name,
            version_ordering=version_ordering,
        )
    ]
    return {"environment": env.name, "applicable_tests": applicable, "count": len(applicable)}


@router.get("/{tenant_id}/runs")
async def list_runs(tenant_id: str, session: AsyncSession = Depends(get_session)):
    stmt = select(TestRun).where(TestRun.tenant_id == uuid.UUID(tenant_id))
    result = await session.execute(stmt)
    runs = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "environment_id": str(r.environment_id),
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "total": r.total_tests,
            "passed": r.passed,
            "failed": r.failed,
            "skipped": r.skipped,
        }
        for r in runs
    ]
