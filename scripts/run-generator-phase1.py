"""
Generator Phase 1 spike driver: build a page-object registry against the live
demo-app for the flows referenced by TC-DISCOUNT-001, using the captured auth
session. Saves the resulting registry as JSON for Phase 2 to consume.
"""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.src.agents.generator.app_model import build_app_model

TENANT_ID = "00000000-0000-0000-0000-000000000001"
ENVIRONMENT_ID = "7bd54680-c9f8-495a-9ae9-e16bca0e5b0a"
BASE = "http://localhost:4000"

REGISTRY_OUT = os.path.join(
    os.path.dirname(__file__), "..", "backend", "evals", "golden", "app_model_registry.json"
)

TEST_CARD_FLOWS = [
    # NOTE: no LoginPage here. TC-DISCOUNT-001's precondition is "user is already
    # authenticated" — the generated test starts from the captured storage state,
    # not a UI login step. Walking /login with an authenticated context is a no-op:
    # the server redirects logged-in users straight to /cart, so the login form
    # never renders and (correctly) no locators resolve. A future test card that
    # actually exercises the login flow would need its own unauthenticated walk.
    {
        "page_name": "CartPage",
        "url": f"{BASE}/cart",
        "elements": [
            {"semantic_name": "discountCodeInput", "description": "discount code input", "role": "textbox", "name": "Discount code", "css": "#code"},
            {"semantic_name": "applyDiscountButton", "description": "apply discount code button", "role": "button", "name": "Apply discount code"},
            {"semantic_name": "proceedToCheckoutButton", "description": "proceed to checkout button", "role": "button", "name": "Proceed to checkout"},
            {"semantic_name": "orderTotal", "description": "cart order total", "css": "#order-total"},
        ],
    },
    {
        "page_name": "CheckoutPage",
        "url": f"{BASE}/checkout",
        "elements": [
            {"semantic_name": "placeOrderButton", "description": "place order button", "role": "button", "name": "Place order"},
            {"semantic_name": "orderTotal", "description": "checkout order total", "css": "#order-total"},
        ],
    },
]


async def main():
    registry = await build_app_model(
        tenant_id=TENANT_ID,
        environment_id=ENVIRONMENT_ID,
        staging_url=BASE,
        test_card_flows=TEST_CARD_FLOWS,
    )

    data = registry.to_dict()
    print(json.dumps(data, indent=2))

    total_requested = sum(len(f["elements"]) for f in TEST_CARD_FLOWS)
    total_resolved = sum(len(po["locators"]) for po in data.values())
    print(f"\nRequested {total_requested} locators, resolved {total_resolved}.")
    if total_resolved < total_requested:
        print("WARNING: not all locators resolved — check logs above for app_model.unresolved_locator")

    with open(REGISTRY_OUT, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\nSaved registry -> {REGISTRY_OUT}")


if __name__ == "__main__":
    asyncio.run(main())
