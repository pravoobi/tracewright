"""Environments API — CRUD + staleness warnings."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.db.models import Environment, SourceArtifact
from backend.src.db.session import get_session

router = APIRouter(prefix="/environments", tags=["environments"])


class CreateEnvironmentRequest(BaseModel):
    name: str
    url: str | None = None
    code_version: str
    doc_version: str | None = None
    feature_flags: dict[str, Any] = {}


@router.post("/{tenant_id}")
async def create_environment(
    tenant_id: str,
    body: CreateEnvironmentRequest,
    session: AsyncSession = Depends(get_session),
):
    env = Environment(
        tenant_id=uuid.UUID(tenant_id),
        name=body.name,
        url=body.url,
        code_version=body.code_version,
        doc_version=body.doc_version,
        feature_flags=body.feature_flags,
    )
    session.add(env)
    await session.commit()
    return {"id": str(env.id), "name": env.name}


@router.get("/{tenant_id}")
async def list_environments(
    tenant_id: str,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Environment).where(Environment.tenant_id == uuid.UUID(tenant_id))
    result = await session.execute(stmt)
    envs = result.scalars().all()

    # Check staleness: warn if env.doc_version lags behind latest uploaded doc
    latest_doc = await _latest_doc_version(session, tenant_id)

    return [
        {
            "id": str(e.id),
            "name": e.name,
            "url": e.url,
            "code_version": e.code_version,
            "doc_version": e.doc_version,
            "updated_at": e.updated_at.isoformat() if e.updated_at else None,
            "staleness_warning": (
                f"Environment uses doc v{e.doc_version} but latest uploaded doc is v{latest_doc}"
                if latest_doc and e.doc_version and e.doc_version != latest_doc
                else None
            ),
        }
        for e in envs
    ]


async def _latest_doc_version(session: AsyncSession, tenant_id: str) -> str | None:
    stmt = (
        select(SourceArtifact.version)
        .where(
            SourceArtifact.tenant_id == uuid.UUID(tenant_id),
            SourceArtifact.type == "document",
        )
        .order_by(SourceArtifact.uploaded_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    return row
