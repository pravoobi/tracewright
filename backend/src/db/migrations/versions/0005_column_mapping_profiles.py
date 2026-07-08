"""Add column_mapping_profiles table for the Excel bug-export column mapper

suggest_column_mapping() existed but was never called from the real upload
flow, and there was no way to persist a customer's confirmed mapping so it
could be reused on their NEXT export (CLAUDE.md: "Store mapping per export
format"). This table is that persistence layer, keyed by a stable signature
of the raw column set so the same export format is recognized automatically
on repeat uploads without asking the customer again.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "column_mapping_profiles",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("column_signature", sa.Text(), nullable=False),
        sa.Column("mapping", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "column_signature", name="uq_column_mapping_tenant_signature"),
    )


def downgrade() -> None:
    op.drop_table("column_mapping_profiles")
