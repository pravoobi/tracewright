"""Extend the golden codegen set: new page objects in the registry + 11 new cards.

    uv run python scripts/build-golden-codegen-set.py

Idempotent: rewrites backend/evals/golden/app_model_registry.json and
codegen_cards.json (the original 5 cards are kept as-is), then regenerates
test-scaffold/page-objects/*.ts from the registry. Every card traces to a
sentence of the golden requirement PDFs (logical id minted from its text, the
same way ingestion does) and, for regressions, to a bug in the golden export.

Locators were checked against the running demo app (demo-app/views/*.ejs).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.src.agents.generator.app_model import AppModelRegistry  # noqa: E402
from backend.src.agents.generator.page_objects import write_page_objects  # noqa: E402
from backend.src.ingestion.identity import mint_logical_id  # noqa: E402

GOLDEN = ROOT / "backend" / "evals" / "golden"
BASE = "http://localhost:4000"

ORIGINAL_CARD_IDS = {"TC-001", "TC-003", "TC-004", "TC-005", "TC-008"}

# --- source sentences (verbatim from the golden PDFs) -------------------------
AC = {
    "lock5": "The system shall lock a user account after 5 consecutive failed login attempts within a 15-minute window.",
    "lock30": "An account lockout shall persist for a minimum of 30 minutes before the user may attempt to log in again.",
    "reset0": "Failed login attempts shall reset to zero after a successful login.",
    "idle": "The system shall expire a user's session token after 30 minutes of inactivity.",
    "logout": "Session tokens are not valid after the user has logged out; a logged-out session token cannot be used to authenticate any further request.",
    "prev5": "The system shall require a new password to differ from the user's previous 5 passwords.",
    "qty99": "The quantity of any single SKU in a cart shall not exceed 99 units.",
    "min10": "A discount code may not be applied to orders with a total below $10.00.",
    "reduce": "The system shall allow authenticated users to apply a discount code at checkout. The discount shall reduce the order total by the percentage specified in the discount record.",
}


def chunk(key: str) -> dict:
    return {"type": "chunk", "logical_id": mint_logical_id(AC[key])}


def bug(bug_id: str) -> dict:
    return {"type": "bug", "logical_id": bug_id}


# --- registry ------------------------------------------------------------------
def step_login(email: str, password: str) -> list[dict]:
    return [
        {"action": "goto", "url": f"{BASE}/login"},
        {"action": "fill", "role": "textbox", "name": "Email", "testid": None, "value": email},
        {"action": "fill", "role": None, "name": None, "testid": "login-password", "value": password},
        {"action": "click", "role": "button", "name": "Log in", "testid": None},
    ]


def pages() -> dict:
    return {
        "LoginPage": {
            "url_pattern": f"{BASE}/login",
            "locators": {
                "loginHeading": 'page.getByRole("heading", { name: "Log In" })',
                "emailInput": 'page.getByRole("textbox", { name: "Email" })',
                "passwordInput": 'page.getByTestId("login-password")',
                "loginButton": 'page.getByRole("button", { name: "Log in" })',
                "loginErrorAlert": 'page.getByRole("alert")',
            },
            "locator_strategies": {
                "loginHeading": "role",
                "emailInput": "role",
                "passwordInput": "testid",
                "loginButton": "role",
                "loginErrorAlert": "role",
            },
            "warnings": [],
            "suggestions": {},
            "requires_state": {
                "loginErrorAlert": step_login("nobody@example.com", "wrong-password"),
            },
        },
        "ChangePasswordPage": {
            "url_pattern": f"{BASE}/account/password",
            "locators": {
                "changePasswordHeading": 'page.getByRole("heading", { name: "Change Password" })',
                "currentPasswordInput": 'page.getByTestId("current-password")',
                "newPasswordInput": 'page.getByTestId("new-password")',
                "confirmPasswordInput": 'page.getByTestId("confirm-password")',
                "changePasswordButton": 'page.getByRole("button", { name: "Change password" })',
                "passwordStatusMessage": 'page.getByRole("status")',
                "passwordErrorAlert": 'page.getByRole("alert")',
            },
            "locator_strategies": {
                "changePasswordHeading": "role",
                "currentPasswordInput": "testid",
                "newPasswordInput": "testid",
                "confirmPasswordInput": "testid",
                "changePasswordButton": "role",
                "passwordStatusMessage": "role",
                "passwordErrorAlert": "role",
            },
            "warnings": [],
            "suggestions": {},
            "requires_state": {
                "passwordStatusMessage": [
                    {"action": "goto", "url": f"{BASE}/account/password"},
                    {"action": "fill", "role": None, "name": None, "testid": "current-password", "value": "password123"},
                    {"action": "fill", "role": None, "name": None, "testid": "new-password", "value": "a-long-enough-pass1"},
                    {"action": "fill", "role": None, "name": None, "testid": "confirm-password", "value": "a-long-enough-pass1"},
                    {"action": "click", "role": "button", "name": "Change password", "testid": None},
                ],
                "passwordErrorAlert": [
                    {"action": "goto", "url": f"{BASE}/account/password"},
                    {"action": "fill", "role": None, "name": None, "testid": "current-password", "value": "password123"},
                    {"action": "fill", "role": None, "name": None, "testid": "new-password", "value": "short"},
                    {"action": "fill", "role": None, "name": None, "testid": "confirm-password", "value": "short"},
                    {"action": "click", "role": "button", "name": "Change password", "testid": None},
                ],
            },
        },
    }


def extend_registry() -> AppModelRegistry:
    path = GOLDEN / "app_model_registry.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(pages())
    # Navigation links shared by the cart-area pages.
    cart = data["CartPage"]
    cart["locators"]["changePasswordLink"] = 'page.getByRole("link", { name: "Change password" })'
    cart["locator_strategies"]["changePasswordLink"] = "role"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return AppModelRegistry.from_dict(data)


# --- cards ---------------------------------------------------------------------
LOCKOUT_USER = {"type": "user", "role": "customer", "email": "lockout@example.com", "password": "password123", "note": "dedicated account: its lockout state must not affect other tests"}
PWCHANGE_USER = {"type": "user", "role": "customer", "email": "pwchange@example.com", "password": "password123", "note": "dedicated account: its password is changed by the test"}
STD_USER = {"type": "user", "role": "customer", "email": "test@example.com", "password": "password123"}

ISOLATED = (
    " This test needs its OWN browser session (it logs in through the login page); it must not use the "
    "shared pre-authenticated session."
)


def card(test_id, title, description, preconditions, manifest, test_type, priority, trace) -> dict:
    return {
        "test_id": test_id,
        "title": title,
        "description": description,
        "preconditions": preconditions,
        "setup_manifest": manifest,
        "test_type": test_type,
        "priority": priority,
        "traceability": trace,
    }


def new_cards() -> list[dict]:
    return [
        card(
            "TC-009",
            "Lock account after 5 consecutive failed login attempts",
            "Verify that five consecutive failed logins for a registered account lock it, and that the 5th "
            "failed attempt tells the user the account is locked (while attempts 1-4 only say the credentials are invalid)."
            + ISOLATED,
            "Account lockout@example.com exists with no prior failed attempts; the user is logged out.",
            [LOCKOUT_USER],
            "negative", "P0", [chunk("lock5")],
        ),
        card(
            "TC-010",
            "Locked account refuses the correct password",
            "Verify that once an account is locked after 5 failed attempts, logging in with the CORRECT password "
            "is still refused with the account-locked message, because the lockout persists for at least 30 minutes."
            + ISOLATED,
            "Account lockout@example.com exists; five failed logins have just been made for it.",
            [LOCKOUT_USER],
            "negative", "P0", [chunk("lock30")],
        ),
        card(
            "TC-011",
            "Failed login counter resets after a successful login",
            "Verify that 4 failed attempts, then a successful login, then logging out and 4 more failed attempts "
            "does NOT lock the account (the 4 new failures still show only the invalid-credentials error), because "
            "the failed-attempt count resets to zero after a successful login." + ISOLATED,
            "Account lockout@example.com exists with no prior failed attempts.",
            [LOCKOUT_USER],
            "functional", "P1", [chunk("reset0")],
        ),
        card(
            "TC-012",
            "Idle session expires after 30 minutes and the user is told why",
            "Verify that a logged-in user whose session has been idle past the 30-minute timeout is sent to the login "
            "page and shown a message that the session expired due to inactivity. Use the fixture's expireSession() "
            "helper to age the session instead of waiting 30 minutes." + ISOLATED,
            "User test@example.com is logged in through the login page in this test's own session.",
            [STD_USER, {"type": "session_state", "state": "idle_longer_than_30_minutes", "how": "fixture expireSession()"}],
            "functional", "P1", [chunk("idle")],
        ),
        card(
            "TC-013",
            "Reject a new password that reuses a previous password",
            "Verify that a user who has changed their password twice (to two different long passwords, e.g. "
            "'first-new-password-1' then 'second-new-password-2') is refused when trying to change back to the first "
            "one, with an error that the new password must differ from the previous 5." + ISOLATED,
            "User pwchange@example.com exists (current password password123, password must be at least 12 characters) "
            "and is logged in through the login page.",
            [PWCHANGE_USER],
            "negative", "P1", [chunk("prev5")],
        ),
        card(
            "TC-014",
            "Logged-out session cannot reach authenticated pages",
            "Verify that after logging out, navigating directly to the cart page redirects to the login page instead of "
            "showing the cart." + ISOLATED,
            "User test@example.com is logged in through the login page, then logs out.",
            [STD_USER],
            "negative", "P1", [chunk("logout")],
        ),
        card(
            "TC-015",
            "Fewer than 5 failed attempts do not lock the account",
            "Verify that 4 failed login attempts followed by the correct password logs the user in normally to the cart "
            "page: the lockout only triggers at 5 consecutive failures." + ISOLATED,
            "Account lockout@example.com exists with no prior failed attempts.",
            [LOCKOUT_USER],
            "functional", "P2", [chunk("lock5")],
        ),
        card(
            "TC-016",
            "Reject a quantity above 99 for a single SKU and leave the cart unchanged",
            "Verify that setting the Widget quantity to 100 and updating the cart is rejected with a quantity-limit error "
            "(alert), and that the cart is unchanged (another line changed in the same update is not applied).",
            "User is logged in with the default cart (1 Widget, 1 Gadget).",
            [{"type": "user", "role": "authenticated_customer"}, {"type": "cart", "state": "default"}],
            "negative", "P1", [chunk("qty99")],
        ),
        card(
            "TC-017",
            "Accept exactly 99 units of a single SKU",
            "Verify the boundary: setting the Widget quantity to 99 and updating the cart is accepted (no error alert) and "
            "the Widget quantity input then shows 99.",
            "User is logged in with the default cart (1 Widget, 1 Gadget).",
            [{"type": "user", "role": "authenticated_customer"}, {"type": "cart", "state": "default"}],
            "functional", "P2", [chunk("qty99")],
        ),
        card(
            "TC-018",
            "REGRESSION BUG-1002: discount refused on an order below $10",
            "Verify that with a cart totalling $5.00 (1 Sticker only; Widget and Gadget at 0) applying discount code "
            "SAVE10 is refused with an error alert saying discount codes cannot be applied to orders under $10.00, and "
            "no discount line appears. Regression of a defect where codes were accepted below the minimum.",
            "User is logged in; cart contains only 1 Sticker ($5.00).",
            [
                {"type": "user", "role": "authenticated_customer"},
                {"type": "discount_code", "code": "SAVE10", "active": True, "percentage": 10},
                {"type": "cart", "items": [{"sku": "sticker", "quantity": 1, "price_usd": 5.0}]},
            ],
            "regression", "P0", [chunk("min10"), bug("BUG-1002")],
        ),
        card(
            "TC-019",
            "REGRESSION BUG-1001: checkout page shows the discounted total",
            "Verify that after applying SAVE20 on the default $50.00 cart and proceeding to checkout, the checkout page "
            "shows the discounted total ($40.00) and the discount line, not the full price. Regression of a defect where "
            "the checkout page showed a stale pre-discount total.",
            "User is logged in with the default cart (1 Widget $30, 1 Gadget $20); no discount applied yet.",
            [
                {"type": "user", "role": "authenticated_customer"},
                {"type": "discount_code", "code": "SAVE20", "active": True, "percentage": 20},
                {"type": "cart", "state": "default", "subtotal_usd": 50.0},
            ],
            "regression", "P0", [chunk("reduce"), bug("BUG-1001")],
        ),
    ]


def main() -> None:
    registry = extend_registry()
    written = write_page_objects(registry, str(ROOT / "test-scaffold" / "page-objects"))
    print("page objects:", [Path(p).name for p in written])

    path = GOLDEN / "codegen_cards.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    kept = [c for c in data["cards"] if c["test_id"] in ORIGINAL_CARD_IDS]
    data["cards"] = kept + new_cards()
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print("cards:", [c["test_id"] for c in data["cards"]])


if __name__ == "__main__":
    main()
