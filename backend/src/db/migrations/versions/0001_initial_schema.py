"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extensions (idempotent — also created by init-db.sql)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Read embedding_dim from settings at migration time
    from backend.src.config import settings
    embedding_dim = settings.embedding_dim

    op.create_table(
        "tenants",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("version_ordering", JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "source_artifacts",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("version", sa.Text, nullable=False),
        sa.Column("storage_path", sa.Text, nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("status", sa.Text, nullable=False, server_default="processing"),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("artifact_id", sa.UUID(as_uuid=True), sa.ForeignKey("source_artifacts.id"), nullable=False),
        sa.Column("logical_id", sa.Text, nullable=False),
        sa.Column("chunk_type", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("raw_content", sa.Text),
        sa.Column("display_ref", sa.Text),
        sa.Column("section_path", sa.Text),
        sa.Column("page_number", sa.Integer),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("review_status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_duration_ms", sa.Integer),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("tsv", TSVECTOR),
        # Vector dimension from config — never hardcoded
        sa.Column("embedding", sa.Text),  # placeholder; actual column created below
    )
    # Create the real vector column with runtime dimension
    op.execute(f"ALTER TABLE chunks DROP COLUMN embedding")
    op.execute(f"ALTER TABLE chunks ADD COLUMN embedding vector({embedding_dim})")
    op.execute("CREATE INDEX chunks_tsv_idx ON chunks USING gin(tsv)")
    op.execute(
        f"CREATE INDEX chunks_embedding_idx ON chunks "
        f"USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    op.create_table(
        "bugs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("artifact_id", sa.UUID(as_uuid=True), sa.ForeignKey("source_artifacts.id"), nullable=False),
        sa.Column("external_id", sa.Text),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("severity", sa.Text),
        sa.Column("component", sa.Text),
        sa.Column("status", sa.Text),
        sa.Column("root_cause", sa.Text),
        sa.Column("fix_version", sa.Text),
        sa.Column("linked_story", sa.Text),
        sa.Column("closed_at", sa.Date),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
    )

    op.create_table(
        "test_cards",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("test_id", sa.Text, nullable=False, unique=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("preconditions", sa.Text),
        sa.Column("setup_manifest", JSONB, nullable=False, server_default="[]"),
        sa.Column("test_type", sa.Text),
        sa.Column("priority", sa.Text),
        sa.Column("introduced_in_version", sa.Text, nullable=False),
        sa.Column("deprecated_in_version", sa.Text),
        sa.Column("supersedes", JSONB, nullable=False, server_default="[]"),
        sa.Column("applicability", JSONB, nullable=False, server_default="{}"),
        sa.Column("tier_sources", JSONB, nullable=False),
        sa.Column("locator_strategy", sa.Text),
        sa.Column("heal_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("approval_status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("approved_by", sa.Text),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("review_duration_ms", sa.Integer),
        sa.Column("playwright_code_path", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "traceability_links",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("test_card_id", sa.UUID(as_uuid=True), sa.ForeignKey("test_cards.id"), nullable=False),
        sa.Column("linked_type", sa.Text, nullable=False),
        sa.Column("linked_logical_id", sa.Text, nullable=False),
        sa.Column("link_reason", sa.Text),
    )

    op.create_table(
        "environments",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("url", sa.Text),
        sa.Column("code_version", sa.Text, nullable=False),
        sa.Column("doc_version", sa.Text),
        sa.Column("bug_cutoff", sa.Date),
        sa.Column("feature_flags", JSONB, nullable=False, server_default="{}"),
        sa.Column("auth_state_path", sa.Text),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
    )

    op.create_table(
        "test_runs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("environment_id", sa.UUID(as_uuid=True), sa.ForeignKey("environments.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("total_tests", sa.Integer),
        sa.Column("passed", sa.Integer),
        sa.Column("failed", sa.Integer),
        sa.Column("skipped", sa.Integer),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
    )

    op.create_table(
        "test_results",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", sa.UUID(as_uuid=True), sa.ForeignKey("test_runs.id"), nullable=False),
        sa.Column("test_card_id", sa.UUID(as_uuid=True), sa.ForeignKey("test_cards.id"), nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("healed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("error_message", sa.Text),
        sa.Column("trace_path", sa.Text),
        sa.Column("screenshot_path", sa.Text),
    )


def downgrade() -> None:
    op.drop_table("test_results")
    op.drop_table("test_runs")
    op.drop_table("environments")
    op.drop_table("traceability_links")
    op.drop_table("test_cards")
    op.drop_table("bugs")
    op.drop_table("chunks")
    op.drop_table("source_artifacts")
    op.drop_table("tenants")
