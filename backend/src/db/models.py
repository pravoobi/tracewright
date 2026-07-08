from __future__ import annotations

import uuid
from datetime import datetime, date
from typing import Any

from sqlalchemy import (
    UUID,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from backend.src.config import settings


class Base(DeclarativeBase):
    pass


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Declared ordered list of version strings — customers set this once
    version_ordering: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    artifacts: Mapped[list[SourceArtifact]] = relationship(back_populates="tenant")
    chunks: Mapped[list[Chunk]] = relationship(back_populates="tenant")
    bugs: Mapped[list[Bug]] = relationship(back_populates="tenant")
    test_cards: Mapped[list[TestCard]] = relationship(back_populates="tenant")
    environments: Mapped[list[Environment]] = relationship(back_populates="tenant")


class SourceArtifact(Base):
    __tablename__ = "source_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)  # document | bug_export | codebase_snapshot
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[str] = mapped_column(Text, default="processing")
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    tenant: Mapped[Tenant] = relationship(back_populates="artifacts")
    chunks: Mapped[list[Chunk]] = relationship(back_populates="artifact")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_artifacts.id"), nullable=False
    )
    # Content-based identity — stable across doc versions, survives renumbering
    logical_id: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_type: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    raw_content: Mapped[str | None] = mapped_column(Text)
    display_ref: Mapped[str | None] = mapped_column(Text)  # 'REQ v2.4 §4.2' — derived, NOT identity
    section_path: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    review_status: Mapped[str] = mapped_column(Text, default="pending")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_duration_ms: Mapped[int | None] = mapped_column(Integer)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    tsv: Mapped[Any] = mapped_column(TSVECTOR)
    # Dimension driven by config — never hardcoded
    embedding: Mapped[Any] = mapped_column(Vector(settings.embedding_dim), nullable=True)

    tenant: Mapped[Tenant] = relationship(back_populates="chunks")
    artifact: Mapped[SourceArtifact] = relationship(back_populates="chunks")
    traceability_links: Mapped[list[TraceabilityLink]] = relationship(
        back_populates="chunk",
        primaryjoin="and_(TraceabilityLink.linked_type=='chunk', "
                    "foreign(TraceabilityLink.linked_logical_id)==Chunk.logical_id)",
        viewonly=True,
    )


class Bug(Base):
    __tablename__ = "bugs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_artifacts.id"), nullable=False
    )
    external_id: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str | None] = mapped_column(Text)
    component: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(Text)
    fix_version: Mapped[str | None] = mapped_column(Text)
    linked_story: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[date | None] = mapped_column(Date)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    tenant: Mapped[Tenant] = relationship(back_populates="bugs")


class TestCard(Base):
    __tablename__ = "test_cards"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    test_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    preconditions: Mapped[str | None] = mapped_column(Text)
    setup_manifest: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    test_type: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str | None] = mapped_column(Text)
    introduced_in_version: Mapped[str] = mapped_column(Text, nullable=False)
    deprecated_in_version: Mapped[str | None] = mapped_column(Text)
    supersedes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # Structured: min/max version, allow/deny lists — no free-text expressions
    applicability: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    tier_sources: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    locator_strategy: Mapped[str | None] = mapped_column(Text)
    heal_count: Mapped[int] = mapped_column(Integer, default=0)
    approval_status: Mapped[str] = mapped_column(Text, default="pending")
    approved_by: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_duration_ms: Mapped[int | None] = mapped_column(Integer)
    playwright_code_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    tenant: Mapped[Tenant] = relationship(back_populates="test_cards")
    traceability_links: Mapped[list[TraceabilityLink]] = relationship(back_populates="test_card")
    test_results: Mapped[list[TestResult]] = relationship(back_populates="test_card")


class TraceabilityLink(Base):
    __tablename__ = "traceability_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    test_card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_cards.id"), nullable=False
    )
    linked_type: Mapped[str] = mapped_column(Text, nullable=False)  # 'chunk' | 'bug'
    # Links to logical_id — survives doc versions
    linked_logical_id: Mapped[str] = mapped_column(Text, nullable=False)
    link_reason: Mapped[str | None] = mapped_column(Text)

    test_card: Mapped[TestCard] = relationship(back_populates="traceability_links")
    chunk: Mapped[Chunk | None] = relationship(
        "Chunk",
        primaryjoin="and_(TraceabilityLink.linked_type=='chunk', "
                    "foreign(TraceabilityLink.linked_logical_id)==Chunk.logical_id)",
        viewonly=True,
    )


class Environment(Base):
    __tablename__ = "environments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    code_version: Mapped[str] = mapped_column(Text, nullable=False)
    doc_version: Mapped[str | None] = mapped_column(Text)
    bug_cutoff: Mapped[date | None] = mapped_column(Date)
    feature_flags: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    auth_state_path: Mapped[str | None] = mapped_column(Text)  # encrypted storage-state in MinIO
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    revision: Mapped[int] = mapped_column(Integer, default=1)

    tenant: Mapped[Tenant] = relationship(back_populates="environments")
    test_runs: Mapped[list[TestRun]] = relationship(back_populates="environment")


class TestRun(Base):
    __tablename__ = "test_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_tests: Mapped[int | None] = mapped_column(Integer)
    passed: Mapped[int | None] = mapped_column(Integer)
    failed: Mapped[int | None] = mapped_column(Integer)
    skipped: Mapped[int | None] = mapped_column(Integer)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    environment: Mapped[Environment] = relationship(back_populates="test_runs")
    results: Mapped[list[TestResult]] = relationship(back_populates="run")


class TestResult(Base):
    __tablename__ = "test_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_runs.id"), nullable=False
    )
    test_card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_cards.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)  # passed | failed | skipped | healed
    healed: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    trace_path: Mapped[str | None] = mapped_column(Text)
    screenshot_path: Mapped[str | None] = mapped_column(Text)

    run: Mapped[TestRun] = relationship(back_populates="results")
    test_card: Mapped[TestCard] = relationship(back_populates="test_results")


class LlmCall(Base):
    """One row per LLM completion — the persistence layer for cost.py's
    per-tenant daily budget enforcement. tenant_id has no FK: cost recording
    must survive even if the caller's own transaction rolls back, and some
    calls (e.g. eval harness runs) may use tenant ids that don't exist in
    the tenants table."""

    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    feature: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_usd: Mapped[float] = mapped_column(Float, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ColumnMappingProfile(Base):
    """A customer's confirmed Excel bug-export column mapping, keyed by a
    stable signature of the raw column set so the same export format is
    recognized automatically on repeat uploads (CLAUDE.md: "Store mapping
    per export format")."""

    __tablename__ = "column_mapping_profiles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "column_signature", name="uq_column_mapping_tenant_signature"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    column_signature: Mapped[str] = mapped_column(Text, nullable=False)
    mapping: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
