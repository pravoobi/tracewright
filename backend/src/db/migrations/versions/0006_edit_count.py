"""Add edit_count to test_cards — "human edits per generated test" metric

CLAUDE.md names this a first-class product metric from day one, but there
was no column to record it at all: review_card() silently applied edits
with zero record that an edit had even happened.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "test_cards",
        sa.Column("edit_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("test_cards", "edit_count")
