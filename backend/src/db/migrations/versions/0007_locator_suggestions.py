"""Add locator_suggestions to test_cards

CLAUDE.md's designed customer-facing recommendation ("recommend adding
data-testid to element X") has always been produced by
find_verified_locator() as LocatorResult.suggestion, but nothing ever
captured it anywhere past that point — not the registry, not a test
card, nowhere a customer could see it.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "test_cards",
        sa.Column("locator_suggestions", JSONB, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("test_cards", "locator_suggestions")
