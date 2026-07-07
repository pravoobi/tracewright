"""Stage 5 (part 1): Canonical schema, provenance capture, logical_id assignment."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog

from backend.src.ingestion.classify import classify_blocks
from backend.src.ingestion.identity import match_to_existing, mint_logical_id
from backend.src.ingestion.structure import Block, StructuredDocument

log = structlog.get_logger()


@dataclass
class NormalizedChunk:
    logical_id: str
    chunk_type: str
    content: str
    raw_content: str
    display_ref: str
    section_path: str
    page_number: int
    confidence: float
    review_status: str
    metadata: dict[str, Any] = field(default_factory=dict)
    # Populated by embed stage
    embedding: list[float] | None = None


def _build_display_ref(doc_version: str, section_path: str, ordinal: int) -> str:
    return f"REQ v{doc_version} {section_path} #{ordinal}"


def _build_section_path(blocks: list[Block], block_idx: int) -> str:
    """Walk backwards to find the current heading hierarchy."""
    headings: list[str] = []
    for i in range(block_idx, -1, -1):
        b = blocks[i]
        if b.block_type == "heading":
            headings.insert(0, b.content[:60])
            if b.level == 1:
                break
    return " > ".join(headings) if headings else "§root"


async def normalize(
    doc: StructuredDocument,
    artifact_id: str,
    tenant_id: str,
    doc_version: str,
    existing_chunks: list[dict[str, Any]] | None = None,
    auto_approve_threshold: float | None = None,
) -> list[NormalizedChunk]:
    from backend.src.config import settings

    # NOTE: `auto_approve_threshold or settings...` looks like a sane default
    # fallback but isn't one — a non-None default parameter is always truthy,
    # so `or` never actually falls through to settings, silently making
    # CONFIDENCE_AUTO_APPROVE_THRESHOLD unconfigurable via .env. Only fall
    # back when the caller genuinely passed nothing.
    threshold = auto_approve_threshold if auto_approve_threshold is not None else settings.confidence_auto_approve_threshold

    # Classify all blocks in one async batch
    classifications = await classify_blocks(doc.blocks, tenant_id=tenant_id)

    chunks: list[NormalizedChunk] = []
    ordinal_by_section: dict[str, int] = {}

    for idx, (block, (chunk_type, confidence, example_of)) in enumerate(
        zip(doc.blocks, classifications)
    ):
        if chunk_type == "out_of_scope":
            continue

        section_path = _build_section_path(doc.blocks, idx)
        ordinal_by_section[section_path] = ordinal_by_section.get(section_path, 0) + 1
        display_ref = _build_display_ref(
            doc_version, section_path, ordinal_by_section[section_path]
        )

        # Content-based logical_id: stable across versions
        logical_id = (
            match_to_existing(block.content, existing_chunks or [])
            or mint_logical_id(block.content)
        )

        review_status = (
            "auto_approved" if confidence >= threshold else "pending"
        )

        metadata: dict[str, Any] = {}
        if example_of:
            metadata["example_of"] = example_of
        if block.metadata:
            metadata.update(block.metadata)
        if block.table_data:
            metadata["table_data"] = block.table_data

        chunks.append(NormalizedChunk(
            logical_id=logical_id,
            chunk_type=chunk_type,
            content=block.content,
            raw_content=block.content,
            display_ref=display_ref,
            section_path=section_path,
            page_number=block.page_number,
            confidence=confidence,
            review_status=review_status,
            metadata=metadata,
        ))

    log.info(
        "normalize.done",
        artifact_id=artifact_id,
        total=len(chunks),
        auto_approved=sum(1 for c in chunks if c.review_status == "auto_approved"),
        pending=sum(1 for c in chunks if c.review_status == "pending"),
    )
    return chunks
