"""Ingestion review API — approve/reject/edit chunks, bulk actions, review-time metrics."""
from __future__ import annotations

import time
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.db.models import Chunk, SourceArtifact
from backend.src.db.session import get_session

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


class ReviewAction(BaseModel):
    action: Literal["approve", "reject", "needs_clarification"]
    review_duration_ms: int | None = None


class BulkReviewAction(BaseModel):
    chunk_ids: list[str]
    action: Literal["approve", "reject"]
    review_duration_ms: int | None = None


@router.get("/{tenant_id}/artifacts")
async def list_artifacts(tenant_id: str, session: AsyncSession = Depends(get_session)):
    stmt = select(SourceArtifact).where(SourceArtifact.tenant_id == uuid.UUID(tenant_id))
    result = await session.execute(stmt)
    artifacts = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "filename": a.filename,
            "type": a.type,
            "version": a.version,
            "status": a.status,
            "uploaded_at": a.uploaded_at.isoformat() if a.uploaded_at else None,
        }
        for a in artifacts
    ]


@router.get("/{tenant_id}/chunks")
async def list_chunks(
    tenant_id: str,
    artifact_id: str | None = None,
    review_status: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Chunk).where(Chunk.tenant_id == uuid.UUID(tenant_id))
    if artifact_id:
        stmt = stmt.where(Chunk.artifact_id == uuid.UUID(artifact_id))
    if review_status:
        stmt = stmt.where(Chunk.review_status == review_status)
    result = await session.execute(stmt)
    chunks = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "logical_id": c.logical_id,
            "chunk_type": c.chunk_type,
            "content": c.content,
            "display_ref": c.display_ref,
            "section_path": c.section_path,
            "confidence": c.confidence,
            "review_status": c.review_status,
        }
        for c in chunks
    ]


@router.patch("/{tenant_id}/chunks/{chunk_id}/review")
async def review_chunk(
    tenant_id: str,
    chunk_id: str,
    body: ReviewAction,
    session: AsyncSession = Depends(get_session),
):
    status_map = {
        "approve": "approved",
        "reject": "rejected",
        "needs_clarification": "needs_clarification",
    }
    await session.execute(
        update(Chunk)
        .where(Chunk.id == uuid.UUID(chunk_id), Chunk.tenant_id == uuid.UUID(tenant_id))
        .values(
            review_status=status_map[body.action],
            review_duration_ms=body.review_duration_ms,
        )
    )
    await session.commit()
    return {"status": "ok"}


@router.post("/{tenant_id}/chunks/bulk-review")
async def bulk_review_chunks(
    tenant_id: str,
    body: BulkReviewAction,
    session: AsyncSession = Depends(get_session),
):
    status_map = {"approve": "approved", "reject": "rejected"}
    chunk_uuids = [uuid.UUID(cid) for cid in body.chunk_ids]
    await session.execute(
        update(Chunk)
        .where(Chunk.id.in_(chunk_uuids), Chunk.tenant_id == uuid.UUID(tenant_id))
        .values(
            review_status=status_map[body.action],
            review_duration_ms=body.review_duration_ms,
        )
    )
    await session.commit()
    return {"updated": len(body.chunk_ids)}
