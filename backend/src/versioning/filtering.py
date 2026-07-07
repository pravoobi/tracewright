"""Runtime test filtering: select applicable test cards for a given environment."""
from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger()


def is_applicable(
    card: dict[str, Any],
    env_code_version: str,
    env_name: str,
    version_ordering: list[str],
) -> bool:
    """
    Return True if a test card applies to the given environment.
    Uses structured applicability (not free-text), with tenant-declared version ordering.
    """
    applicability = card.get("applicability", {})
    introduced = card.get("introduced_in_version", "")
    deprecated = card.get("deprecated_in_version")

    order = _version_index(version_ordering)

    # Must have been introduced at or before env version
    if introduced and env_code_version:
        if not _version_lte(introduced, env_code_version, order):
            return False

    # Must not be deprecated at or before env version
    if deprecated and env_code_version:
        if _version_lte(deprecated, env_code_version, order):
            return False

    # Allow/deny lists
    allowlist = applicability.get("env_allowlist")
    denylist = applicability.get("env_denylist") or []

    if env_name in denylist:
        return False
    if allowlist is not None and env_name not in allowlist:
        return False

    return True


def _version_index(ordering: list[str]) -> dict[str, int]:
    return {v: i for i, v in enumerate(ordering)}


def _version_lte(a: str, b: str, order: dict[str, int]) -> bool:
    """Return True if version a <= b per the declared ordering."""
    if a not in order or b not in order:
        # Fall back to string comparison if ordering not declared
        log.warning("versioning.unknown_version", a=a, b=b)
        return a <= b
    return order[a] <= order[b]
