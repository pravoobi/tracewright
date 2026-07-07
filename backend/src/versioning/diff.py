"""Document version diffing — logical_id-based, survives renumbering."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.src.ingestion.identity import match_to_existing, mint_logical_id


@dataclass
class ChunkDiff:
    logical_id: str
    status: str  # 'unchanged' | 'modified' | 'new' | 'removed'
    old_content: str | None = None
    new_content: str | None = None


def diff_document_versions(
    old_chunks: list[dict[str, Any]],
    new_chunks_raw: list[str],
) -> list[ChunkDiff]:
    """
    Compare a new document upload against existing chunks.
    new_chunks_raw: just the text content (pre-identity).
    Returns a diff where every item carries a logical_id.
    """
    old_by_id = {c["logical_id"]: c for c in old_chunks}
    matched_ids: set[str] = set()
    diffs: list[ChunkDiff] = []

    for new_content in new_chunks_raw:
        logical_id = match_to_existing(new_content, old_chunks)

        if logical_id:
            old = old_by_id[logical_id]
            matched_ids.add(logical_id)
            if _normalize(old["content"]) == _normalize(new_content):
                status = "unchanged"
            else:
                status = "modified"
            diffs.append(ChunkDiff(
                logical_id=logical_id,
                status=status,
                old_content=old["content"],
                new_content=new_content,
            ))
        else:
            new_id = mint_logical_id(new_content)
            diffs.append(ChunkDiff(
                logical_id=new_id,
                status="new",
                new_content=new_content,
            ))

    # Anything in old not matched → removed
    for old_id, old_chunk in old_by_id.items():
        if old_id not in matched_ids:
            diffs.append(ChunkDiff(
                logical_id=old_id,
                status="removed",
                old_content=old_chunk["content"],
            ))

    return diffs


def _normalize(text: str) -> str:
    import re
    return re.sub(r"\s+", " ", text.lower().strip())
