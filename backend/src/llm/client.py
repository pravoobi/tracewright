from __future__ import annotations

import json
import time
from typing import Any

import litellm
import structlog

from backend.src.config import settings
from backend.src.llm.cost import budget_guard, record_llm_call

log = structlog.get_logger()

# litellm reads ANTHROPIC_API_KEY from env automatically
litellm.drop_params = True


def extract_json_object(raw: str) -> dict:
    """Parse the first JSON object in an LLM response, tolerating a markdown
    fence and/or trailing prose after it (models sometimes add an unsolicited
    explanation sentence after the closing fence). A plain
    `raw.removesuffix("```")` only handles a fence that's the literal last
    thing in the string — it silently does nothing once there's text after
    it, so `json.loads` then fails with "Extra data". Centralized here after
    the identical fix was independently copy-pasted into classify.py,
    healer.py, and planner.py."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        cleaned = cleaned[first_newline + 1:] if first_newline != -1 else cleaned.lstrip("`")
    return json.JSONDecoder().raw_decode(cleaned.strip())[0]


async def complete(
    messages: list[dict[str, str]],
    model: str | None = None,
    tenant_id: str | None = None,
    feature: str = "unknown",
    **kwargs: Any,
) -> str:
    """Single-turn completion. Model is swappable via config — never wire SDK calls directly."""
    resolved_model = model or settings.planner_model

    async with budget_guard(tenant_id):
        started = time.monotonic()

        response = await litellm.acompletion(
            model=resolved_model,
            messages=messages,
            **kwargs,
        )

        elapsed_ms = int((time.monotonic() - started) * 1000)
        usage = response.usage  # type: ignore[union-attr]

        await record_llm_call(
            tenant_id=tenant_id,
            feature=feature,
            model=resolved_model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            latency_ms=elapsed_ms,
        )

    content = response.choices[0].message.content  # type: ignore[union-attr]
    log.debug("llm.complete", model=resolved_model, feature=feature, latency_ms=elapsed_ms)
    return content or ""
