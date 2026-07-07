"""arq worker — parses uploaded artifacts through the full ingestion pipeline."""
from __future__ import annotations

import uuid
from typing import Any

import structlog
from arq import create_pool
from arq.connections import RedisSettings

from backend.src.config import settings

log = structlog.get_logger()


def _redis_settings() -> RedisSettings:
    url = settings.redis_url
    # arq RedisSettings from URL
    host = "localhost"
    port = 6379
    if "://" in url:
        parts = url.split("://", 1)[1].split(":")
        host = parts[0]
        if len(parts) > 1:
            port = int(parts[1].split("/")[0])
    return RedisSettings(host=host, port=port)


async def enqueue_parse_job(
    artifact_id: str,
    tenant_id: str,
    filename: str,
    storage_path: str,
    artifact_type: str,
) -> None:
    pool = await create_pool(_redis_settings())
    await pool.enqueue_job(
        "parse_artifact",
        artifact_id=artifact_id,
        tenant_id=tenant_id,
        filename=filename,
        storage_path=storage_path,
        artifact_type=artifact_type,
    )
    await pool.aclose()


async def parse_artifact(
    ctx: dict[str, Any],
    artifact_id: str,
    tenant_id: str,
    filename: str,
    storage_path: str,
    artifact_type: str,
) -> None:
    """arq task: full ingestion pipeline for one artifact."""
    from backend.src.db.models import Chunk, SourceArtifact
    from backend.src.db.session import async_session_factory
    from backend.src.ingestion.embed import embed_and_store_chunks
    from backend.src.ingestion.excel import parse_bug_export
    from backend.src.ingestion.layout import extract_layout
    from backend.src.ingestion.normalize import normalize
    from backend.src.ingestion.structure import recover_structure
    from backend.src.ingestion.triage import triage_document
    from backend.src.storage.files import download_file
    from sqlalchemy import update

    log.info("worker.parse_start", artifact_id=artifact_id, filename=filename)

    data = download_file(storage_path)

    if artifact_type == "bug_export":
        await _ingest_bug_export(artifact_id, tenant_id, filename, data)
        return

    # Document pipeline: Stages 1–6
    triage = triage_document(filename, data)
    if triage.is_password_protected:
        log.error("worker.password_protected", artifact_id=artifact_id)
        await _set_status(artifact_id, "error_password_protected")
        return

    layout = extract_layout(filename, data, triage)
    structured = recover_structure(layout)

    async with async_session_factory() as session:
        existing = await _fetch_existing_chunks(session, tenant_id)
        chunks = await normalize(
            structured,
            artifact_id=artifact_id,
            tenant_id=tenant_id,
            doc_version="1.0",
            existing_chunks=existing,
        )

        # Persist chunks
        chunk_models = []
        for c in chunks:
            chunk_models.append(Chunk(
                tenant_id=uuid.UUID(tenant_id),
                artifact_id=uuid.UUID(artifact_id),
                logical_id=c.logical_id,
                chunk_type=c.chunk_type,
                content=c.content,
                raw_content=c.raw_content,
                display_ref=c.display_ref,
                section_path=c.section_path,
                page_number=c.page_number,
                confidence=c.confidence,
                review_status=c.review_status,
                metadata_=c.metadata,
            ))
        session.add_all(chunk_models)
        await session.flush()

        # Stage 6: embed + store
        await embed_and_store_chunks(session, chunks, tenant_id, artifact_id)

        await session.execute(
            update(SourceArtifact)
            .where(SourceArtifact.id == uuid.UUID(artifact_id))
            .values(status="processed")
        )
        await session.commit()

    log.info("worker.parse_done", artifact_id=artifact_id, chunks=len(chunks))


async def _ingest_bug_export(
    artifact_id: str, tenant_id: str, filename: str, data: bytes
) -> None:
    from backend.src.db.models import Bug, SourceArtifact
    from backend.src.db.session import async_session_factory
    from backend.src.ingestion.excel import parse_bug_export
    from sqlalchemy import update

    records, unmapped = parse_bug_export(data)

    ingested = 0
    async with async_session_factory() as session:
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
                closed_at=_parse_closed_at(rec.closed_at),
                metadata_={"unmapped_columns": unmapped, "raw": rec.raw or {}},
            ))
            ingested += 1

        await session.execute(
            update(SourceArtifact)
            .where(SourceArtifact.id == uuid.UUID(artifact_id))
            .values(status="processed", metadata_={"unmapped_columns": unmapped})
        )
        await session.commit()

    log.info(
        "worker.bugs_ingested",
        artifact_id=artifact_id,
        bugs=ingested,
        skipped_untitled=len(records) - ingested,
    )


def _parse_closed_at(value: str | None):
    """Bug export date columns arrive as free-text strings with no
    guaranteed format. Try ISO first (what most exports use), fall back to
    a couple of common alternates, and give up to None rather than crash
    the whole ingestion job over one bad date cell."""
    if not value:
        return None
    from datetime import datetime

    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    log.warning("worker.unparseable_closed_at", value=value)
    return None


async def _fetch_existing_chunks(session: Any, tenant_id: str) -> list[dict]:
    from backend.src.db.models import Chunk
    from sqlalchemy import select

    result = await session.execute(
        select(Chunk.logical_id, Chunk.content).where(
            Chunk.tenant_id == uuid.UUID(tenant_id)
        )
    )
    return [{"logical_id": row.logical_id, "content": row.content} for row in result.all()]


async def _set_status(artifact_id: str, status: str) -> None:
    from backend.src.db.models import SourceArtifact
    from backend.src.db.session import async_session_factory
    from sqlalchemy import update

    async with async_session_factory() as session:
        await session.execute(
            update(SourceArtifact)
            .where(SourceArtifact.id == uuid.UUID(artifact_id))
            .values(status=status)
        )
        await session.commit()


class WorkerSettings:
    functions = [parse_artifact]
    redis_settings = _redis_settings()
    max_jobs = 4
    job_timeout = 600
