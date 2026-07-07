"""Stage 3: Structure recovery — multi-page table merge, cross-reference resolution."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

from backend.src.ingestion.layout import Block, LayoutResult

log = structlog.get_logger()

_XREF_PATTERN = re.compile(
    r"(?:see|refer to|as (?:described|defined) in)\s+(?:section|§)\s*([\d.]+)",
    re.IGNORECASE,
)


@dataclass
class StructuredDocument:
    filename: str
    blocks: list[Block] = field(default_factory=list)
    cross_references: list[dict[str, Any]] = field(default_factory=list)


def recover_structure(layout: LayoutResult) -> StructuredDocument:
    blocks = _merge_multipage_tables(layout.blocks)
    doc = StructuredDocument(filename=layout.filename, blocks=blocks)
    doc.cross_references = _resolve_cross_references(blocks)
    return doc


def _merge_multipage_tables(blocks: list[Block]) -> list[Block]:
    """Merge consecutive table blocks that look like page-split continuations."""
    if not blocks:
        return blocks

    merged: list[Block] = []
    i = 0
    while i < len(blocks):
        block = blocks[i]
        if block.block_type != "table" or not block.table_data:
            merged.append(block)
            i += 1
            continue

        # Look ahead for a table on the next page with the same column structure
        j = i + 1
        while j < len(blocks):
            next_block = blocks[j]
            if next_block.block_type == "table" and next_block.table_data:
                # Same number of columns and sequential page → merge
                if (
                    len(next_block.table_data[0]) == len(block.table_data[0])
                    and next_block.page_number == block.page_number + 1
                ):
                    # Skip repeated header row on continuation page
                    continuation = next_block.table_data
                    if continuation and continuation[0] == block.table_data[0]:
                        continuation = continuation[1:]
                    block = Block(
                        block_type="table",
                        content=block.content,
                        page_number=block.page_number,
                        table_data=block.table_data + continuation,
                        confidence=min(block.confidence, next_block.confidence),
                        metadata={**block.metadata, "merged_from_pages": True},
                    )
                    j += 1
                    continue
            break

        merged.append(block)
        i = j

    if len(merged) < len(blocks):
        log.info("structure.tables_merged", before=len(blocks), after=len(merged))
    return merged


def _resolve_cross_references(blocks: list[Block]) -> list[dict[str, Any]]:
    """Find 'see section X.Y' references and store with original text + resolved target."""
    # Build section-number → block index map
    section_map: dict[str, int] = {}
    for idx, block in enumerate(blocks):
        if block.block_type == "heading":
            # Extract leading section number if present
            m = re.match(r"^([\d.]+)\s", block.content)
            if m:
                section_map[m.group(1)] = idx

    refs: list[dict[str, Any]] = []
    for idx, block in enumerate(blocks):
        for m in _XREF_PATTERN.finditer(block.content):
            section_num = m.group(1)
            target_idx = section_map.get(section_num)
            refs.append({
                "source_block_idx": idx,
                "original_text": m.group(0),
                "referenced_section": section_num,
                "resolved_block_idx": target_idx,
                "resolved": target_idx is not None,
            })

    return refs
