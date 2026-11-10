"""Scope test_cards.test_id uniqueness to (tenant_id, test_id) instead of
globally unique. The global constraint meant tenant A minting "TC-001" could
collide with tenant B's own "TC-001" -- persist_plan's collision-suffix logic
(which already scopes its own lookup query per-tenant) would then silently
rename tenant B's card because of a cross-tenant DB constraint, and the
collision itself let one tenant infer another tenant's test_id existence.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-10
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("test_cards_test_id_key", "test_cards", type_="unique")
    op.create_unique_constraint(
        "uq_test_cards_tenant_test_id", "test_cards", ["tenant_id", "test_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_test_cards_tenant_test_id", "test_cards", type_="unique")
    op.create_unique_constraint("test_cards_test_id_key", "test_cards", ["test_id"])
