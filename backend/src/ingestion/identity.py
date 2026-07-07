"""Stage 5 (part 2): Content-based stable logical_id minting and re-upload matching."""
from __future__ import annotations

import hashlib
import re
from typing import Any

import structlog
from rapidfuzz import fuzz

log = structlog.get_logger()

# Similarity threshold for matching a new chunk to an existing logical_id
_MATCH_THRESHOLD = 0.82


def mint_logical_id(content: str) -> str:
    """Stable, opaque ID derived from normalized content. Survives doc renumbering."""
    normalized = _normalize(content)
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:12]
    return f"REQ-{digest}"


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    # Strip leading section numbers (e.g. "3.4.2 ") so renumbering doesn't change the hash
    text = re.sub(r"^[\d.]+\s+", "", text)
    return text


def match_to_existing(
    new_content: str,
    existing: list[dict[str, Any]],  # [{"logical_id": str, "content": str}, ...]
    new_embedding: list[float] | None = None,
    existing_embeddings: list[list[float]] | None = None,
) -> str | None:
    """
    Try to match new_content to an existing chunk's logical_id.
    Uses fuzzy text match + optional embedding similarity.
    Returns the matched logical_id or None (→ caller mints a new one).
    """
    if not existing:
        return None

    normalized_new = _normalize(new_content)
    best_score = 0.0
    best_id: str | None = None

    for i, ex in enumerate(existing):
        # Fuzzy text similarity (0–100 → 0–1)
        text_score = fuzz.token_sort_ratio(normalized_new, _normalize(ex["content"])) / 100.0

        # Embedding cosine similarity if available
        emb_score = 0.0
        if new_embedding and existing_embeddings and i < len(existing_embeddings):
            emb_score = _cosine(new_embedding, existing_embeddings[i])

        # Weighted blend: text 60%, embedding 40% (or text only if no embeddings)
        if new_embedding and existing_embeddings:
            score = 0.6 * text_score + 0.4 * emb_score
        else:
            score = text_score

        if score > best_score:
            best_score = score
            best_id = ex["logical_id"]

    if best_score >= _MATCH_THRESHOLD:
        log.debug("identity.matched", logical_id=best_id, score=round(best_score, 3))
        return best_id

    return None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
