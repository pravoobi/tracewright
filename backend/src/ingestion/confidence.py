"""Confidence scoring — aggregates signals across pipeline stages."""
from __future__ import annotations


def compute_chunk_confidence(
    classification_confidence: float,
    ocr_confidence: float = 1.0,
    table_confidence: float = 1.0,
    has_unresolved_xrefs: bool = False,
) -> float:
    score = classification_confidence * ocr_confidence * table_confidence
    if has_unresolved_xrefs:
        score *= 0.9
    return round(max(0.0, min(1.0, score)), 4)
