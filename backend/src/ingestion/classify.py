"""Stage 4: Semantic classification via Haiku-class LLM."""
from __future__ import annotations

import json
import structlog

from backend.src.config import settings
from backend.src.ingestion.structure import Block
from backend.src.llm.client import complete

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

- acceptance_criterion: A testable statement of expected behavior ("The system shall...", "Given X, when Y, then Z")
- business_rule: A constraint or invariant governing business logic
- glossary_term: A definition of a domain term
- example: An illustrative example of a rule or criterion (tag example_of with the rule it illustrates)
- out_of_scope: Revision history, stakeholder lists, document control, boilerplate — nothing testable
- metadata: Document metadata (title, version, date, author)
- unknown: Cannot determine

Respond with JSON only:
{"type": "<category>", "confidence": <0.0-1.0>, "example_of": "<brief description of rule if type=example, else null>"}"""


async def classify_block(block: Block, tenant_id: str | None = None) -> tuple[str, float, str | None]:
    """Returns (chunk_type, confidence, example_of)."""
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
        parsed = json.loads(raw)
        chunk_type = parsed.get("type", "unknown")
        if chunk_type not in VALID_TYPES:
            chunk_type = "unknown"
        confidence = float(parsed.get("confidence", 0.5))
        example_of = parsed.get("example_of")
        return chunk_type, confidence, example_of
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        log.warning("classify.parse_error", error=str(e), content_preview=block.content[:100])
        return "unknown", 0.3, None


async def classify_blocks(
    blocks: list[Block],
    tenant_id: str | None = None,
) -> list[tuple[str, float, str | None]]:
    import asyncio
    tasks = [classify_block(b, tenant_id) for b in blocks]
    return await asyncio.gather(*tasks)
