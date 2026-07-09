"""Add tenants.api_key_hash — every API endpoint took tenant_id as a plain
URL path parameter with no credential check at all, so any caller could
read/write any tenant's data just by supplying that tenant's UUID. This is
the persistence side of closing that gap; see auth/api_key.py for the
verification dependency applied to every router.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("api_key_hash", sa.Text(), nullable=True))
    op.create_index("tenants_api_key_hash_idx", "tenants", ["api_key_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("tenants_api_key_hash_idx", table_name="tenants")
    op.drop_column("tenants", "api_key_hash")
