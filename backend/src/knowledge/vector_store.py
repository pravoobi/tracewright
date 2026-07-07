"""Hybrid search: pgvector cosine similarity + Postgres tsvector keyword matching."""
from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.ingestion.embed import embed_texts

log = structlog.get_logger()


async def hybrid_search(
    session: AsyncSession,
    query: str,
    tenant_id: str,
    limit: int = 20,
    chunk_types: list[str] | None = None,
    vector_weight: float = 0.6,
    keyword_weight: float = 0.4,
) -> list[dict[str, Any]]:
    """
    Hybrid retrieval: vector similarity + tsvector keyword match, RRF-blended.
    V1 keyword side uses Postgres native full-text (tsvector/ts_rank).
    Upgrade path: ParadeDB pg_search or VectorChord-bm25 for true BM25.
    """
    query_embedding = embed_texts([query])[0]

    type_filter = ""
    params: dict[str, Any] = {
        "tenant_id": tenant_id,
        "query_embedding": str(query_embedding),
        "tsquery": " & ".join(query.split()),
        "limit": limit,
        "vector_weight": vector_weight,
        "keyword_weight": keyword_weight,
    }
    if chunk_types:
        type_filter = "AND chunk_type = ANY(:chunk_types)"
        params["chunk_types"] = chunk_types

    # NOTE: bind tenant_id as a real uuid.UUID and use CAST(... AS vector) rather
    # than the ":name::type" shorthand — SQLAlchemy's text() bind-parameter
    # parser collides with Postgres's "::" cast operator when it directly
    # follows a ":name" parameter (no space), silently leaving the cast as
    # literal, un-substituted text that then fails at the database layer.
    # Same root cause as the embed.py fix.
    params["tenant_id"] = uuid.UUID(tenant_id)

    sql = text(f"""
        WITH vector_results AS (
            SELECT id, logical_id, chunk_type, content, display_ref, section_path,
                   page_number, confidence, review_status, metadata,
                   1 - (embedding <=> CAST(:query_embedding AS vector)) AS vector_score,
                   ROW_NUMBER() OVER (ORDER BY embedding <=> CAST(:query_embedding AS vector)) AS vector_rank
            FROM chunks
            WHERE tenant_id = :tenant_id
              AND review_status IN ('auto_approved', 'approved')
              AND embedding IS NOT NULL
              {type_filter}
            ORDER BY embedding <=> CAST(:query_embedding AS vector)
            LIMIT :limit
        ),
        keyword_results AS (
            SELECT id, logical_id, chunk_type, content, display_ref, section_path,
                   page_number, confidence, review_status, metadata,
                   ts_rank(tsv, plainto_tsquery('english', :tsquery)) AS keyword_score,
                   ROW_NUMBER() OVER (
                     ORDER BY ts_rank(tsv, plainto_tsquery('english', :tsquery)) DESC
                   ) AS keyword_rank
            FROM chunks
            WHERE tenant_id = :tenant_id
              AND review_status IN ('auto_approved', 'approved')
              AND tsv @@ plainto_tsquery('english', :tsquery)
              {type_filter}
            ORDER BY keyword_score DESC
            LIMIT :limit
        ),
        combined AS (
            SELECT
                COALESCE(v.id, k.id) AS id,
                COALESCE(v.logical_id, k.logical_id) AS logical_id,
                COALESCE(v.chunk_type, k.chunk_type) AS chunk_type,
                COALESCE(v.content, k.content) AS content,
                COALESCE(v.display_ref, k.display_ref) AS display_ref,
                COALESCE(v.section_path, k.section_path) AS section_path,
                COALESCE(v.page_number, k.page_number) AS page_number,
                COALESCE(v.confidence, k.confidence) AS confidence,
                COALESCE(v.review_status, k.review_status) AS review_status,
                COALESCE(v.metadata, k.metadata) AS metadata,
                -- Reciprocal Rank Fusion
                :vector_weight * (1.0 / (60 + COALESCE(v.vector_rank, :limit + 1)))
                + :keyword_weight * (1.0 / (60 + COALESCE(k.keyword_rank, :limit + 1))) AS rrf_score
            FROM vector_results v
            FULL OUTER JOIN keyword_results k ON v.id = k.id
        )
        SELECT * FROM combined ORDER BY rrf_score DESC LIMIT :limit
    """)

    result = await session.execute(sql, params)
    rows = result.mappings().all()
    return [dict(row) for row in rows]
