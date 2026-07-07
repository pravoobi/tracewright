from __future__ import annotations

import time
from typing import Any

import litellm
import structlog

from backend.src.config import settings
from backend.src.llm.cost import record_llm_call

log = structlog.get_logger()

# litellm reads ANTHROPIC_API_KEY from env automatically
litellm.drop_params = True


async def complete(
    messages: list[dict[str, str]],
    model: str | None = None,
    tenant_id: str | None = None,
    feature: str = "unknown",
    **kwargs: Any,
) -> str:
    """Single-turn completion. Model is swappable via config — never wire SDK calls directly."""
    resolved_model = model or settings.planner_model
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
