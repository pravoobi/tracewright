"""Generator Phase 1: Build shared page-object registry against the live staging app."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import structlog

from backend.src.auth_capture.sessions import load_session

log = structlog.get_logger()


@dataclass
class PageObject:
    name: str  # e.g. "LoginPage", "CheckoutPage"
    url_pattern: str
    locators: dict[str, str] = field(default_factory=dict)  # semantic_name → locator_code
    locator_strategies: dict[str, str] = field(default_factory=dict)  # semantic_name → strategy
    warnings: list[str] = field(default_factory=list)
    # semantic_name → "Add data-testid attribute to element matching X" —
    # CLAUDE.md's customer-facing recommendation for a css_warned/unresolved
    # locator. find_verified_locator() has always produced this on
    # LocatorResult; nothing ever captured it into the registry until now.
    suggestions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url_pattern": self.url_pattern,
            "locators": self.locators,
            "locator_strategies": self.locator_strategies,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
        }


@dataclass
class AppModelRegistry:
    pages: dict[str, PageObject] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {name: po.to_dict() for name, po in self.pages.items()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppModelRegistry":
        registry = cls()
        for name, po_data in data.items():
            registry.pages[name] = PageObject(
                name=name,
                url_pattern=po_data["url_pattern"],
                locators=po_data.get("locators", {}),
                locator_strategies=po_data.get("locator_strategies", {}),
                warnings=po_data.get("warnings", []),
                suggestions=po_data.get("suggestions", {}),
            )
        return registry


def _origin(url: str) -> tuple[str, str, int | None]:
    """(scheme, host, port) with case-folding and default ports normalised, so
    https://Host and https://host:443 compare equal."""
    from urllib.parse import urlparse

    u = urlparse(url)
    scheme = (u.scheme or "").lower()
    port = u.port or {"http": 80, "https": 443}.get(scheme)
    return scheme, (u.hostname or "").lower(), port


async def build_app_model(
    tenant_id: str,
    environment_id: str,
    staging_url: str,
    test_card_flows: list[dict[str, Any]],
) -> AppModelRegistry:
    """
    Phase 1: Walk flows from approved test cards, build shared page-object registry.
    One LoginPage, one CheckoutPage — not five slightly different ones per test.
    """
    from playwright.async_api import async_playwright
    from backend.src.agents.generator.locators import find_verified_locator

    storage_state = load_session(tenant_id, environment_id)
    registry = AppModelRegistry()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=storage_state)

        # The decrypted auth cookies are loaded into this browser, so it must
        # never be steered off the environment's registered origin -- by a flow
        # URL, or by a redirect (e.g. an open redirect on the app, or a 302 to a
        # cloud metadata address). Checking only the initial URL string is not
        # enough: every navigation hop, including redirects, passes through this.
        allowed_origin = _origin(staging_url)

        async def _same_origin_navigations_only(route):
            request = route.request
            if request.is_navigation_request() and _origin(request.url) != allowed_origin:
                log.warning("app_model.blocked_cross_origin_navigation", url=request.url)
                await route.abort()
                return
            await route.continue_()

        await context.route("**/*", _same_origin_navigations_only)

        for flow in test_card_flows:
            page_name = flow.get("page_name", "UnknownPage")
            url = flow.get("url") or staging_url

            if page_name in registry.pages:
                continue  # already built this page object

            page_obj = PageObject(name=page_name, url_pattern=url)
            pw_page = await context.new_page()

            try:
                await pw_page.goto(url, wait_until="networkidle")

                for element in flow.get("elements", []):
                    result = await find_verified_locator(
                        pw_page,
                        description=element.get("description", ""),
                        role_hint=element.get("role"),
                        name_hint=element.get("name"),
                        testid_hint=element.get("testid"),
                        css_hint=element.get("css"),
                    )
                    semantic_name = element.get("semantic_name", element.get("description", "el"))
                    if result.verified:
                        page_obj.locators[semantic_name] = result.locator_code
                        page_obj.locator_strategies[semantic_name] = result.strategy
                        if result.warning:
                            page_obj.warnings.append(result.warning)
                        if result.suggestion:
                            page_obj.suggestions[semantic_name] = result.suggestion
                    else:
                        log.warning(
                            "app_model.unresolved_locator",
                            page=page_name,
                            element=element.get("description"),
                        )
                        # Never emit an unverified locator, but the
                        # data-testid recommendation is still real and
                        # actionable even though there's no locator entry.
                        if result.suggestion:
                            page_obj.suggestions[semantic_name] = result.suggestion

            except Exception as e:
                log.error("app_model.page_error", page=page_name, url=url, error=str(e))
            finally:
                await pw_page.close()

            registry.pages[page_name] = page_obj

        await browser.close()

    log.info(
        "app_model.built",
        tenant_id=tenant_id,
        pages=list(registry.pages.keys()),
    )
    return registry
