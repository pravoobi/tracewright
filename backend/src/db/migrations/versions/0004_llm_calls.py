"""Add llm_calls table for per-tenant daily LLM budget enforcement

cost.py's check_tenant_budget() has always existed but had nothing to
query — llm.cost was only ever written to structured logs, never persisted,
so there was no way to compute a tenant's spend-so-far today. This table is
that persistence layer.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), nullable=True),
        sa.Column("feature", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_usd", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Budget checks query "today's spend for this tenant" on every LLM call
    op.create_index("llm_calls_tenant_created_idx", "llm_calls", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("llm_calls_tenant_created_idx", table_name="llm_calls")
    op.drop_table("llm_calls")
