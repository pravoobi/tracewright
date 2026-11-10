"""arq worker — parses uploaded artifacts through the full ingestion pipeline."""
from __future__ import annotations

import uuid
from typing import Any

import structlog
from arq import create_pool
from arq.connections import RedisSettings

from backend.src.config import settings
from backend.src.versioning.diff import ChunkDiff

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
    allow_oversized: bool = False,
) -> None:
    pool = await create_pool(_redis_settings())
    await pool.enqueue_job(
        "parse_artifact",
        artifact_id=artifact_id,
        tenant_id=tenant_id,
        filename=filename,
        storage_path=storage_path,
        artifact_type=artifact_type,
        allow_oversized=allow_oversized,
    )
    await pool.aclose()


async def parse_artifact(
    ctx: dict[str, Any],
    artifact_id: str,
    tenant_id: str,
    filename: str,
    storage_path: str,
    artifact_type: str,
    allow_oversized: bool = False,
) -> None:
    """arq task: full ingestion pipeline for one artifact."""
    log.info("worker.parse_start", artifact_id=artifact_id, filename=filename)

    try:
        await _parse_artifact_inner(
            artifact_id, tenant_id, filename, storage_path, artifact_type, allow_oversized
        )
    except Exception as exc:
        # Without this, any pipeline exception (a classifier crash, a bad
        # parse, a transient DB error) left the artifact stuck at
        # status="queued" forever from the customer's/UI's perspective --
        # no error status, no indication anything went wrong, no retry path.
        # Re-raise after recording so arq's own failure logging still sees it.
        log.error("worker.parse_failed", artifact_id=artifact_id, error=str(exc), exc_info=True)
        # Recording the failure must never replace the real exception (e.g. if
        # the DB itself is what failed, _set_status would raise too and the
        # original error would be lost).
        try:
            await _set_status(artifact_id, "error", error_reason=str(exc)[:1000])
        except Exception:
            log.error("worker.set_error_status_failed", artifact_id=artifact_id, exc_info=True)
        raise


async def _parse_artifact_inner(
    artifact_id: str,
    tenant_id: str,
    filename: str,
    storage_path: str,
    artifact_type: str,
    allow_oversized: bool = False,
) -> None:
    from backend.src.db.models import Chunk, SourceArtifact
    from backend.src.db.session import async_session_factory
    from backend.src.ingestion.embed import embed_and_store_chunks
    from backend.src.ingestion.layout import extract_layout
    from backend.src.ingestion.normalize import normalize
    from backend.src.ingestion.structure import recover_structure
    from backend.src.ingestion.triage import triage_document
    from backend.src.storage.files import download_file
    from sqlalchemy import update

    data = download_file(storage_path)

    if artifact_type == "bug_export":
        await _ingest_bug_export(artifact_id, tenant_id, filename, data)
        return

    # Document pipeline: Stages 1–6
    # An oversized document is held for explicit confirmation (CLAUDE.md:
    # "reject oversized docs with confirmation prompt"); the customer confirms
    # via POST .../artifacts/{id}/confirm-oversized, which re-enqueues with
    # allow_oversized=True and a raised (but still bounded) page cap.
    triage = triage_document(filename, data, max_pages=5000) if allow_oversized else triage_document(filename, data)
    if triage.is_password_protected:
        log.error("worker.password_protected", artifact_id=artifact_id)
        await _set_status(artifact_id, "error_password_protected")
        return
    if triage.is_oversized and not allow_oversized:
        # triage_document already computed this (Stage 1) but nothing ever
        # checked it -- an oversized doc silently proceeded through the full
        # LLM-classification pipeline (Stage 4), burning the tenant's LLM
        # budget on a document CLAUDE.md says should be rejected outright.
        log.error("worker.oversized", artifact_id=artifact_id, total_pages=triage.total_pages)
        await _set_status(artifact_id, "error_oversized")
        return

    layout = extract_layout(filename, data, triage)
    structured = recover_structure(layout)

    async with async_session_factory() as session:
        artifact = await session.get(SourceArtifact, uuid.UUID(artifact_id))
        doc_version = artifact.version if artifact else "1.0"

        existing = await _fetch_existing_chunks(session, tenant_id)

        # Version diffing: only meaningful against a PRIOR version of this
        # SAME document (same filename), not the tenant-wide identity pool
        # `existing` draws from — diffing against unrelated documents would
        # flag every one of their chunks as spuriously "removed".
        prior_chunks = await _fetch_prior_version_chunks(
            session, tenant_id, filename, artifact_id
        )
        diff_by_block_idx: dict[int, ChunkDiff] | None = None
        prior_by_logical_id: dict[str, dict] = {}
        diff_summary: dict[str, int] = {}
        if prior_chunks:
            from backend.src.versioning.diff import diff_document_versions

            prior_by_logical_id = {c["logical_id"]: c for c in prior_chunks}
            new_raw = [b.content for b in structured.blocks]
            diffs = diff_document_versions(prior_chunks, new_raw)
            # diff_document_versions emits one entry per new_raw item, in
            # the same order, THEN appends "removed" entries for anything
            # in prior_chunks that didn't match — so the first len(new_raw)
            # entries align 1:1 with structured.blocks by index.
            diff_by_block_idx = {i: d for i, d in enumerate(diffs[: len(new_raw)])}
            removed = [d for d in diffs if d.status == "removed"]
            if removed:
                deprecated_cards = await _deprecate_removed_chunks(
                    session, tenant_id, removed, doc_version
                )
                diff_summary["deprecated_test_cards"] = deprecated_cards
                diff_summary["removed"] = len(removed)

        chunks = await normalize(
            structured,
            artifact_id=artifact_id,
            tenant_id=tenant_id,
            doc_version=doc_version,
            existing_chunks=existing,
            diff_by_block_idx=diff_by_block_idx,
            prior_by_logical_id=prior_by_logical_id,
        )

        if prior_chunks:
            # Recomputed from the actual PERSISTED chunks rather than the
            # raw per-block diff — the raw diff counts every block
            # (headings, document-control text, anything out_of_scope) as
            # "new" the moment it isn't in prior_chunks, since prior_chunks
            # only ever contained real, previously-persisted chunks. That
            # inflates "new" with blocks that were never chunks in the
            # first place and still won't be after classification.
            unchanged = modified = new = 0
            for c in chunks:
                prior = prior_by_logical_id.get(c.logical_id)
                if prior is None:
                    new += 1
                elif prior["content"].strip().lower() == c.content.strip().lower():
                    unchanged += 1
                else:
                    modified += 1
            diff_summary["unchanged"] = unchanged
            diff_summary["modified"] = modified
            diff_summary["new"] = new
            diff_summary.setdefault("removed", 0)

        if diff_summary:
            metadata = dict(artifact.metadata_ or {}) if artifact else {}
            metadata["diff_summary"] = diff_summary
            await session.execute(
                update(SourceArtifact)
                .where(SourceArtifact.id == uuid.UUID(artifact_id))
                .values(metadata_=metadata)
            )
            log.info("worker.diff_summary", artifact_id=artifact_id, **diff_summary)

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
    from sqlalchemy import select, update

    from backend.src.db.models import Bug, ColumnMappingProfile, SourceArtifact
    from backend.src.db.session import async_session_factory
    from backend.src.ingestion.excel import (
        column_signature,
        parse_bug_export,
        parse_closed_at,
        peek_columns,
    )

    raw_columns = peek_columns(data, filename)
    signature = column_signature(raw_columns)

    # A previously-confirmed mapping for this exact export format (same
    # column set) is applied automatically — the customer shouldn't have to
    # re-map the same spreadsheet template on every subsequent upload.
    saved_mapping: dict[str, str] = {}
    async with async_session_factory() as session:
        result = await session.execute(
            select(ColumnMappingProfile.mapping).where(
                ColumnMappingProfile.tenant_id == uuid.UUID(tenant_id),
                ColumnMappingProfile.column_signature == signature,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            saved_mapping = row

    records, unmapped = parse_bug_export(data, filename, column_mapping=saved_mapping)

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
                closed_at=parse_closed_at(rec.closed_at),
                metadata_={"unmapped_columns": unmapped, "raw": rec.raw or {}},
            ))
            ingested += 1

        await session.execute(
            update(SourceArtifact)
            .where(SourceArtifact.id == uuid.UUID(artifact_id))
            .values(
                status="processed",
                metadata_={
                    "unmapped_columns": unmapped,
                    "all_columns": raw_columns,
                    "column_signature": signature,
                },
            )
        )
        await session.commit()

    log.info(
        "worker.bugs_ingested",
        artifact_id=artifact_id,
        bugs=ingested,
        skipped_untitled=len(records) - ingested,
        unmapped_columns=unmapped,
    )


async def _fetch_existing_chunks(session: Any, tenant_id: str) -> list[dict]:
    from backend.src.db.models import Chunk
    from sqlalchemy import select

    result = await session.execute(
        select(Chunk.logical_id, Chunk.content).where(
            Chunk.tenant_id == uuid.UUID(tenant_id)
        )
    )
    return [{"logical_id": row.logical_id, "content": row.content} for row in result.all()]


async def _fetch_prior_version_chunks(
    session: Any, tenant_id: str, filename: str, current_artifact_id: str
) -> list[dict]:
    """Chunks from the tenant's most recent PRIOR artifact with the same
    filename — the actual lineage to diff against, as opposed to
    _fetch_existing_chunks's tenant-wide pool (used for identity matching,
    where a chunk moving between documents is still a legitimate match).
    Diffing against unrelated documents would flag every one of their
    chunks as spuriously "removed"."""
    from backend.src.db.models import Chunk, SourceArtifact
    from sqlalchemy import select

    prior_artifact_id = await session.scalar(
        select(SourceArtifact.id)
        .where(
            SourceArtifact.tenant_id == uuid.UUID(tenant_id),
            SourceArtifact.filename == filename,
            SourceArtifact.id != uuid.UUID(current_artifact_id),
            SourceArtifact.status == "processed",
        )
        .order_by(SourceArtifact.uploaded_at.desc())
        .limit(1)
    )
    if prior_artifact_id is None:
        return []

    result = await session.execute(
        select(Chunk.logical_id, Chunk.content, Chunk.chunk_type, Chunk.confidence, Chunk.review_status)
        .where(Chunk.artifact_id == prior_artifact_id)
    )
    return [
        {
            "logical_id": row.logical_id,
            "content": row.content,
            "chunk_type": row.chunk_type,
            "confidence": row.confidence,
            "review_status": row.review_status,
        }
        for row in result.all()
    ]


async def _deprecate_removed_chunks(
    session: Any, tenant_id: str, removed: list[ChunkDiff], doc_version: str
) -> list[str]:
    """CLAUDE.md: "removed sections deprecate linked tests." Sets
    deprecated_in_version on any test_card linked to a chunk that no
    longer exists in this document version — test filtering already
    excludes deprecated cards at or past that version, so this is a real,
    load-bearing signal, not cosmetic. Returns the test_ids touched, for
    logging/visibility rather than silently mutating them."""
    from sqlalchemy import select, update

    from backend.src.db.models import TestCard, TraceabilityLink

    removed_logical_ids = [d.logical_id for d in removed]
    result = await session.execute(
        select(TraceabilityLink.test_card_id)
        .where(
            TraceabilityLink.tenant_id == uuid.UUID(tenant_id),
            TraceabilityLink.linked_type == "chunk",
            TraceabilityLink.linked_logical_id.in_(removed_logical_ids),
        )
        .distinct()
    )
    card_ids = [row[0] for row in result.all()]
    if not card_ids:
        return []

    test_ids = await session.scalars(
        select(TestCard.test_id).where(TestCard.id.in_(card_ids))
    )
    test_ids_list = list(test_ids)

    await session.execute(
        update(TestCard)
        .where(TestCard.id.in_(card_ids), TestCard.deprecated_in_version.is_(None))
        .values(deprecated_in_version=doc_version)
    )
    log.warning(
        "worker.test_cards_deprecated",
        test_ids=test_ids_list,
        removed_logical_ids=removed_logical_ids,
        doc_version=doc_version,
    )
    return test_ids_list


async def _set_status(artifact_id: str, status: str, error_reason: str | None = None) -> None:
    from backend.src.db.models import SourceArtifact
    from backend.src.db.session import async_session_factory
    from sqlalchemy import update

    async with async_session_factory() as session:
        values: dict[str, Any] = {"status": status}
        if error_reason is not None:
            artifact = await session.get(SourceArtifact, uuid.UUID(artifact_id))
            metadata = dict(artifact.metadata_ or {}) if artifact else {}
            metadata["error_reason"] = error_reason
            values["metadata_"] = metadata
        await session.execute(
            update(SourceArtifact)
            .where(SourceArtifact.id == uuid.UUID(artifact_id))
            .values(**values)
        )
        await session.commit()


class WorkerSettings:
    functions = [parse_artifact]
    redis_settings = _redis_settings()
    max_jobs = 4
    job_timeout = 600
    # The pipeline is not idempotent (it inserts chunks and makes paid LLM
    # calls), so arq's default of 5 automatic retries would duplicate chunks
    # and cost on a transient failure. Failed artifacts end in status "error"
    # and are re-run deliberately.
    max_tries = 1
