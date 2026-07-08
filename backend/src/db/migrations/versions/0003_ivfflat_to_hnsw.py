"""Switch chunks.embedding index from ivfflat to HNSW

`chunks` is a multi-tenant table (all tenants' chunks share one table/index),
so the "right" ivfflat `lists` value depends on the TOTAL row count across
every tenant, which keeps growing — any fixed `lists` needs periodic
re-tuning (drop+rebuild) as the table grows, or it silently degrades again.
The original migration hardcoded lists=100, tuned for roughly 100K rows;
on this dev table (16 rows) that caused ~20-40s latency on hybrid_search's
combined CTE query for what should be a near-instant lookup on a tiny table.

HNSW has no size-dependent parameter to maintain and performs well across a
wide range of table sizes without re-tuning — a better fit for a table whose
size is inherently unpredictable and growing. Slightly slower index builds
and more memory at build time, a reasonable tradeoff at this table's actual
scale (thousands-to-low-millions of rows, not web-scale).

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunks_embedding_idx")
    op.execute(
        "CREATE INDEX chunks_embedding_idx ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunks_embedding_idx")
    op.execute(
        "CREATE INDEX chunks_embedding_idx ON chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
