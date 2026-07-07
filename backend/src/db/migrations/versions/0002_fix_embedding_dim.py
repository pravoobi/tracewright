"""Fix embedding column dimension to match the actual embed model (BGE-M3, 1024-dim)

The initial migration created `chunks.embedding` as vector(1536) — matching the
.env.example default meant for an OpenAI-style embedding API — but
`backend/src/ingestion/embed.py` hardcodes BAAI/bge-m3, whose dense output is
1024-dim. Never caught because Stage 6 had never been exercised end-to-end
until now. Safe to ALTER in place since `chunks` was empty at the time of
this migration.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from backend.src.config import settings
    embedding_dim = settings.embedding_dim

    op.execute("DROP INDEX IF EXISTS chunks_embedding_idx")
    op.execute(f"ALTER TABLE chunks ALTER COLUMN embedding TYPE vector({embedding_dim})")
    op.execute(
        f"CREATE INDEX chunks_embedding_idx ON chunks "
        f"USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunks_embedding_idx")
    op.execute("ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(1536)")
    op.execute(
        "CREATE INDEX chunks_embedding_idx ON chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
