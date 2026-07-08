"""Stage 6: Embed chunks at multiple granularities and write to pgvector + tsvector."""
from __future__ import annotations

import asyncio
import uuid

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.config import settings
from backend.src.ingestion.normalize import NormalizedChunk

log = structlog.get_logger()

_model: object = None


def _get_embedding_model() -> object:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        # Default: open-weight BGE-M3 (honors open-source-first policy)
        # Switch to API embeddings via config when needed
        _model = SentenceTransformer("BAAI/bge-m3", device="cpu")
        log.info("embed.model_loaded", model="BAAI/bge-m3", dim=settings.embedding_dim)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = _get_embedding_model()
    embeddings = model.encode(texts, normalize_embeddings=True)  # type: ignore[union-attr]
    return [e.tolist() for e in embeddings]


async def embed_and_store_chunks(
    session: AsyncSession,
    chunks: list[NormalizedChunk],
    tenant_id: str,
    artifact_id: str,
) -> None:
    if not chunks:
        return

    texts = [c.content for c in chunks]
    # embed_texts is synchronous, CPU-bound (SentenceTransformer.encode()) --
    # calling it directly would block the entire asyncio event loop for
    # every tenant's requests during this whole call (and much worse on
    # first use, while BGE-M3 loads from disk). Offload to a thread instead.
    embeddings = await asyncio.to_thread(embed_texts, texts)

    for chunk, embedding in zip(chunks, embeddings):
        chunk.embedding = embedding

        # tsvector for keyword side of hybrid search
        # NOTE: bind tenant_id/artifact_id as real uuid.UUID objects rather than
        # casting strings with "::uuid" — SQLAlchemy's text() bind-parameter
        # parser collides with Postgres's "::" cast operator when it directly
        # follows a ":name" parameter (no space), producing a stray ":" that
        # asyncpg then fails to parse as a syntax error.
        await session.execute(
            text("""
                UPDATE chunks
                SET tsv = to_tsvector('english', :content),
                    embedding = :embedding
                WHERE logical_id = :logical_id
                  AND tenant_id = :tenant_id
                  AND artifact_id = :artifact_id
            """),
            {
                "content": chunk.content,
                "embedding": str(embedding),
                "logical_id": chunk.logical_id,
                "tenant_id": uuid.UUID(tenant_id),
                "artifact_id": uuid.UUID(artifact_id),
            },
        )

    await session.commit()
    log.info("embed.stored", count=len(chunks), tenant_id=tenant_id)
