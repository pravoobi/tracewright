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
    lf = get_langfuse()
    if lf is None:
        return None
    return lf.trace(name=name, user_id=tenant_id, **kwargs)
