from __future__ import annotations

from typing import Any

from backend.src.config import settings

_client: Any = None


def get_langfuse() -> Any:
    global _client
    if _client is None and settings.langfuse_secret_key:
        from langfuse import Langfuse
        _client = Langfuse(
            secret_key=settings.langfuse_secret_key,
            public_key=settings.langfuse_public_key,
            host=settings.langfuse_host,
        )
    return _client


def trace(name: str, tenant_id: str | None = None, **kwargs: Any) -> Any:
    """Start a Langfuse trace. Returns None if Langfuse isn't configured (see
    get_langfuse) — callers must guard with `if tracer:` before using it.

    NOTE: our self-hosted server is pinned to langfuse/langfuse:2 (v3+ needs
    ClickHouse, deliberately avoided — see docker-compose.yml). The Python
    SDK must stay pinned to the matching 2.x range in pyproject.toml
    ("langfuse>=2.0.0,<3.0.0") — the v3+ SDK rewrote tracing around
    OpenTelemetry (start_observation()/.end() instead of .trace()/.update())
    and its client expects response fields (project.organization,
    project.metadata) that a v2 server doesn't return, so pairing the v4
    SDK with this server fails outright (401 first if pointed at the wrong
    host entirely, then a Pydantic validation error once pointed at the
    right host with the right keys).
    """
    lf = get_langfuse()
    if lf is None:
        return None
    return lf.trace(name=name, user_id=tenant_id, **kwargs)
