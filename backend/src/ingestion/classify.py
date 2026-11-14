"""Stage 4: Semantic classification via Haiku-class LLM."""
from __future__ import annotations

import json

import structlog

from backend.src.config import settings
from backend.src.ingestion.structure import Block
from backend.src.llm.client import complete, extract_json_object

log = structlog.get_logger()

VALID_TYPES = frozenset({
    "acceptance_criterion",
    "business_rule",
    "glossary_term",
    "example",
    "out_of_scope",
    "metadata",
    "unknown",
})

_SYSTEM_PROMPT = """You are a requirements classifier. Given a block of text from a requirements document, classify it into exactly one of these categories:

- acceptance_criterion: A testable statement of expected behavior ("The system shall...", "Given X, when Y, then Z", "users see ..."). A "shall" statement about system behaviour is an acceptance criterion even when it involves a number, limit or time window
- business_rule: A constraint or invariant on business data or policy that is not itself a behaviour (e.g. "may not exceed", "is not eligible", "expire after"), including tables of limits, rates or thresholds
- glossary_term: A definition of a domain term
- example: A concrete scenario with specific values, times, inputs or messages that illustrates a rule or criterion stated elsewhere, with or without a marker such as "for example" (tag example_of with the rule it illustrates)
- out_of_scope: Document control (owner, author, reviewers, revision history), boilerplate, page headers and footers, tables of contents, roadmap or explicit exclusions, and statements about how the product is built, maintained or governed rather than what it does — nothing testable at the feature level, even when worded with "shall"
- metadata: Document metadata (title, version, date)
- unknown: Cannot determine

Respond with JSON only:
{"type": "<category>", "confidence": <0.0-1.0>, "example_of": "<brief description of rule if type=example, else null>"}"""


def aggregate_votes(votes: list[tuple[str, float, str | None]]) -> tuple[str, float, str | None]:
    """Combine repeated classifications of one block into (type, confidence, example_of).

    The model's own confidence is overconfident, but its *consistency* is
    informative: a block it labels differently on repeated calls is ambiguous.
    Confidence = mean self-reported confidence of the winning votes, scaled by
    the share of votes that agree, so a 2-of-3 split falls well under the
    auto-approve threshold and goes to human review. (Unanimous-but-wrong
    answers cannot be caught this way; the eval reports them.)
    """
    if not votes:
        return "unknown", 0.3, None
    tally: dict[str, list[float]] = {}
    for kind, conf, _ in votes:
        tally.setdefault(kind, []).append(conf)
    # most votes wins; ties broken by the higher mean confidence
    kind = max(tally, key=lambda k: (len(tally[k]), sum(tally[k]) / len(tally[k])))
    agreement = len(tally[kind]) / len(votes)
    confidence = round(sum(tally[kind]) / len(tally[kind]) * agreement, 3)
    example_of = next((e for k, _, e in votes if k == kind and e), None)
    return kind, confidence, example_of


async def _classify_once(block: Block, tenant_id: str | None) -> tuple[str, float, str | None]:
    """One classification call. Returns (chunk_type, self-reported confidence, example_of)."""
    prompt = f"Block type hint: {block.block_type}\n\nText:\n{block.content[:2000]}"

    try:
        raw = await complete(
            messages=[
                {"role": "user", "content": prompt},
            ],
            model=settings.classifier_model,
            tenant_id=tenant_id,
            feature="classification",
            system=_SYSTEM_PROMPT,
            max_tokens=128,
        )
        parsed = extract_json_object(raw)
        # extract_json_object parses whatever the first valid JSON value is —
        # a Haiku-class model occasionally wraps its response in a list
        # (e.g. `[{"type": ...}]`) instead of a bare object. That isn't a
        # parse failure extract_json_object can catch (it IS valid JSON),
        # so it has to be handled here rather than relying on the except
        # clause below.
        if not isinstance(parsed, dict):
            log.warning(
                "classify.unexpected_shape",
                parsed_type=type(parsed).__name__,
                content_preview=block.content[:100],
            )
            return "unknown", 0.3, None
        chunk_type = parsed.get("type", "unknown")
        if chunk_type not in VALID_TYPES:
            chunk_type = "unknown"
        confidence = float(parsed.get("confidence", 0.5))
        example_of = parsed.get("example_of")
        return chunk_type, confidence, example_of
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        log.warning("classify.parse_error", error=str(e), content_preview=block.content[:100])
        return "unknown", 0.3, None


async def classify_block(block: Block, tenant_id: str | None = None) -> tuple[str, float, str | None]:
    """Returns (chunk_type, confidence, example_of); sampled settings.classifier_samples times."""
    import asyncio

    n = settings.classifier_samples
    if n <= 1:
        return await _classify_once(block, tenant_id)
    votes = await asyncio.gather(*(_classify_once(block, tenant_id) for _ in range(n)))
    return aggregate_votes(list(votes))


async def classify_blocks(
    blocks: list[Block],
    tenant_id: str | None = None,
) -> list[tuple[str, float, str | None]]:
    import asyncio
    tasks = [classify_block(b, tenant_id) for b in blocks]
    return await asyncio.gather(*tasks)
