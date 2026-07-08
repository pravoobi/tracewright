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
    diff_by_block_idx: dict[int, Any] | None = None,
    prior_by_logical_id: dict[str, dict[str, Any]] | None = None,
) -> list[NormalizedChunk]:
    from backend.src.config import settings

    # NOTE: `auto_approve_threshold or settings...` looks like a sane default
    # fallback but isn't one — a non-None default parameter is always truthy,
    # so `or` never actually falls through to settings, silently making
    # CONFIDENCE_AUTO_APPROVE_THRESHOLD unconfigurable via .env. Only fall
    # back when the caller genuinely passed nothing.
    threshold = auto_approve_threshold if auto_approve_threshold is not None else settings.confidence_auto_approve_threshold

    # On a re-upload, unchanged blocks reuse their prior chunk's
    # classification and review decision instead of being re-classified —
    # saves a real LLM call per unchanged block, and (more importantly)
    # doesn't discard a human reviewer's prior approve/reject decision on
    # content that hasn't actually changed.
    diff_by_block_idx = diff_by_block_idx or {}
    prior_by_logical_id = prior_by_logical_id or {}

    # Computed once, reused by both the classify-skip pass below and the
    # main pass — must stay a single source of truth, since disagreement
    # between the two would mean a block skipped here has nothing to fall
    # back on in the main pass.
    reused_by_idx: dict[int, dict[str, Any]] = {}
    for idx in range(len(doc.blocks)):
        diff = diff_by_block_idx.get(idx)
        if diff is not None and diff.status == "unchanged":
            prior = prior_by_logical_id.get(diff.logical_id)
            if prior is not None:
                reused_by_idx[idx] = prior

    blocks_to_classify = [b for idx, b in enumerate(doc.blocks) if idx not in reused_by_idx]
    classify_idx_map = [idx for idx in range(len(doc.blocks)) if idx not in reused_by_idx]

    classifications = await classify_blocks(blocks_to_classify, tenant_id=tenant_id)
    classification_by_idx = dict(zip(classify_idx_map, classifications))

    chunks: list[NormalizedChunk] = []
    ordinal_by_section: dict[str, int] = {}

    for idx, block in enumerate(doc.blocks):
        reused = reused_by_idx.get(idx)

        if reused is not None:
            chunk_type, confidence, example_of = reused["chunk_type"], reused["confidence"], None
        else:
            chunk_type, confidence, example_of = classification_by_idx[idx]

        if chunk_type == "out_of_scope":
            continue

        section_path = _build_section_path(doc.blocks, idx)
        ordinal_by_section[section_path] = ordinal_by_section.get(section_path, 0) + 1
        display_ref = _build_display_ref(
            doc_version, section_path, ordinal_by_section[section_path]
        )

        if reused is not None:
            logical_id = reused["logical_id"]
            review_status = reused["review_status"]
        else:
            # Content-based logical_id: stable across versions
            logical_id = (
                match_to_existing(block.content, existing_chunks or [])
                or mint_logical_id(block.content)
            )
            review_status = "auto_approved" if confidence >= threshold else "pending"

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
        reused_unchanged=len(reused_by_idx),
    )
    return chunks
