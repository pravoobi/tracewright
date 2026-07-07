"""Locator strategy ladder: role → testid → CSS+warning. Never emit unverified locators."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger()


@dataclass
class LocatorResult:
    strategy: str  # 'role' | 'testid' | 'css_warned' | 'unresolved'
    locator_code: str  # the Playwright locator expression
    verified: bool
    warning: str | None = None
    suggestion: str | None = None  # e.g. "add data-testid='submit-btn' to this element"


async def find_verified_locator(
    page: Any,  # Playwright Page object
    description: str,
    role_hint: str | None = None,
    name_hint: str | None = None,
    testid_hint: str | None = None,
    css_hint: str | None = None,
) -> LocatorResult:
    """
    Try locators in priority order; verify each resolves to exactly one element.
    NEVER return an unverified locator — caller must check result.verified.

    Verification runs against the real Playwright Python API (page.get_by_role /
    get_by_test_id / locator). `locator_code` is a *separate* string in Playwright's
    TypeScript syntax (page.getByRole / getByTestId / locator) — that's what the
    Generator embeds in the generated .spec.ts file, since verification happens here
    in Python but the emitted test runs in Node/TypeScript.
    """
    # 1. Role-based (accessibility-tree-first)
    if role_hint:
        py_locator = page.get_by_role(role_hint, name=name_hint) if name_hint else page.get_by_role(role_hint)
        if await _verify(py_locator):
            ts_name_arg = f', {{ name: {json.dumps(name_hint)} }}' if name_hint else ""
            loc_code = f'page.getByRole({json.dumps(role_hint)}{ts_name_arg})'
            return LocatorResult(strategy="role", locator_code=loc_code, verified=True)

    # 2. Test ID
    if testid_hint:
        py_locator = page.get_by_test_id(testid_hint)
        if await _verify(py_locator):
            loc_code = f'page.getByTestId({json.dumps(testid_hint)})'
            return LocatorResult(strategy="testid", locator_code=loc_code, verified=True)

    # 3. CSS with explicit warning
    if css_hint:
        py_locator = page.locator(css_hint)
        if await _verify(py_locator):
            loc_code = f'page.locator({json.dumps(css_hint)})'
            warning = (
                f"CSS locator used for '{description}' — fragile to DOM changes. "
                "Consider adding a data-testid attribute."
            )
            suggestion = f"Add data-testid attribute to element matching '{css_hint}'"
            log.warning("locator.css_fallback", description=description, css=css_hint)
            return LocatorResult(
                strategy="css_warned",
                locator_code=loc_code,
                verified=True,
                warning=warning,
                suggestion=suggestion,
            )

    # All strategies failed — do NOT emit an unverified locator
    log.error("locator.unresolved", description=description)
    return LocatorResult(
        strategy="unresolved",
        locator_code="",
        verified=False,
        suggestion=f"Could not find a reliable locator for '{description}'. Add data-testid to the element.",
    )


async def _verify(locator: Any) -> bool:
    """Return True iff the (Python) Playwright locator resolves to exactly one element."""
    try:
        return await locator.count() == 1
    except Exception:
        return False
