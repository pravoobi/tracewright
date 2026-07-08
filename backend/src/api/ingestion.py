"""Ingestion review API — approve/reject/edit chunks, bulk actions, review-time metrics."""
from __future__ import annotations

import time
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select, update
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
            "unmapped_columns": (a.metadata_ or {}).get("unmapped_columns", []),
        }
        for a in artifacts
    ]


class ConfirmColumnMapping(BaseModel):
    mapping: dict[str, str]


@router.get("/{tenant_id}/bug-exports/{artifact_id}/column-mapping")
async def get_column_mapping_suggestion(
    tenant_id: str,
    artifact_id: str,
    session: AsyncSession = Depends(get_session),
):
    from backend.src.ingestion.excel import suggest_column_mapping

    artifact = await session.get(SourceArtifact, uuid.UUID(artifact_id))
    if artifact is None or str(artifact.tenant_id) != tenant_id:
        raise HTTPException(status_code=404, detail="Artifact not found")

    unmapped = (artifact.metadata_ or {}).get("unmapped_columns", [])
    if not unmapped:
        return {"unmapped_columns": [], "suggested_mapping": {}}

    suggested = await suggest_column_mapping(unmapped, tenant_id=tenant_id)
    return {"unmapped_columns": unmapped, "suggested_mapping": suggested}


@router.post("/{tenant_id}/bug-exports/{artifact_id}/column-mapping")
async def confirm_column_mapping(
    tenant_id: str,
    artifact_id: str,
    body: ConfirmColumnMapping,
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from backend.src.db.models import Bug, ColumnMappingProfile
    from backend.src.ingestion.excel import column_signature, parse_bug_export, parse_closed_at, peek_columns
    from backend.src.storage.files import download_file

    artifact = await session.get(SourceArtifact, uuid.UUID(artifact_id))
    if artifact is None or str(artifact.tenant_id) != tenant_id:
        raise HTTPException(status_code=404, detail="Artifact not found")

    # Derived fresh from the actual file rather than trusting it was
    # pre-stored in metadata — artifacts uploaded before this feature existed
    # (or before worker.py started recording all_columns/column_signature)
    # have no such metadata, and requiring it here made confirmation fail
    # outright for them with a 400 the frontend didn't even surface.
    data = download_file(artifact.storage_path)
    signature = column_signature(peek_columns(data))

    # Save for reuse on the customer's next upload of this same export format
    await session.execute(
        pg_insert(ColumnMappingProfile)
        .values(
            tenant_id=uuid.UUID(tenant_id),
            column_signature=signature,
            mapping=body.mapping,
        )
        .on_conflict_do_update(
            index_elements=["tenant_id", "column_signature"],
            set_={"mapping": body.mapping},
        )
    )

    # Re-parse the original file with the confirmed mapping applied, and
    # replace this artifact's previously-ingested (partially-mapped) bugs
    records, unmapped = parse_bug_export(data, column_mapping=body.mapping)

    await session.execute(delete(Bug).where(Bug.artifact_id == uuid.UUID(artifact_id)))

    ingested = 0
    for rec in records:
        if not rec.title or rec.title == "Untitled":
            continue
        session.add(Bug(
            tenant_id=uuid.UUID(tenant_id),
            artifact_id=uuid.UUID(artifact_id),
            external_id=rec.external_id,
            title=rec.title,
            description=rec.description,
            severity=rec.severity,
            component=rec.component,
            status=rec.status,
            root_cause=rec.root_cause,
            fix_version=rec.fix_version,
            linked_story=rec.linked_story,
            closed_at=parse_closed_at(rec.closed_at),
            metadata_={"unmapped_columns": unmapped, "raw": rec.raw or {}},
        ))
        ingested += 1

    metadata = dict(artifact.metadata_ or {})
    metadata["unmapped_columns"] = unmapped
    await session.execute(
        update(SourceArtifact).where(SourceArtifact.id == uuid.UUID(artifact_id)).values(metadata_=metadata)
    )
    await session.commit()

    return {"bugs_ingested": ingested, "still_unmapped": unmapped}


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
