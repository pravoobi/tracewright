"""
Generator Phase 1 for TC-004 (real Planner-generated card): "Display applied
discount code and percentage on checkout summary."

Reuses the existing CartPage/CheckoutPage registry entries from the
Generator spike, adding one new locator: the discount-code-and-percentage
summary line, which only exists in the DOM after a discount is actually
applied (cart.ejs wraps it in `<% if (discount) %>`). build_app_model()
only checks elements on initial page load, not after an action, so this
walks the flow manually: apply SAVE10, then verify the new locator.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from playwright.async_api import async_playwright
from backend.src.agents.generator.app_model import AppModelRegistry
from backend.src.agents.generator.locators import find_verified_locator
from backend.src.auth_capture.sessions import load_session

TENANT_ID = "00000000-0000-0000-0000-000000000001"
ENVIRONMENT_ID = "7bd54680-c9f8-495a-9ae9-e16bca0e5b0a"
BASE = "http://localhost:4000"

REGISTRY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "backend", "evals", "golden", "app_model_registry.json"
)


async def main():
    with open(REGISTRY_PATH) as f:
        registry = AppModelRegistry.from_dict(json.load(f))

    storage_state = load_session(TENANT_ID, ENVIRONMENT_ID)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=storage_state)
        page = await context.new_page()

        await page.goto(f"{BASE}/cart", wait_until="networkidle")
        await page.get_by_role("textbox", name="Discount code").fill("SAVE10")
        await page.get_by_role("button", name="Apply discount code").click()
        await page.wait_for_load_state("networkidle")

        result = await find_verified_locator(
            page,
            description="discount code and percentage summary line",
            css_hint='dt:has-text("Discount")',
        )
        print("discountSummary:", result)

        if result.verified:
            registry.pages["CartPage"].locators["discountSummary"] = result.locator_code
            registry.pages["CartPage"].locator_strategies["discountSummary"] = result.strategy
            if result.warning:
                registry.pages["CartPage"].warnings.append(result.warning)

        await browser.close()

    data = registry.to_dict()
    with open(REGISTRY_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\nUpdated registry -> {REGISTRY_PATH}")
    print(json.dumps(data["CartPage"], indent=2))


if __name__ == "__main__":
    asyncio.run(main())
