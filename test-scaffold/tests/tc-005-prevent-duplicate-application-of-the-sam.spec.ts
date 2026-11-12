// ─── Tracewright — Generated Test ───────────────────────────────────────
// Test Card ID : TC-005
// Title        : Prevent duplicate application of the same discount code on one order
// Source AC    : REQ-b8a87b822e87
// Regresses    : none
// Priority     : P1
// Type         : negative
// ─────────────────────────────────────────────────────────────────────────
// DO NOT EDIT locators manually — regenerate via Tracewright.

// Test ID: TC-005
// Title: Prevent duplicate application of the same discount code on one order
// Source: REQ-b8a87b822e87
// Precondition: User is authenticated; a discount code has already been
// successfully applied to the current order.

import { test, expect } from "../fixtures/authenticated-cart.fixture";
import { CartPage } from "../page-objects/CartPage";

// Setup assumption: the setup manifest describes an order that already has
// SAVE10 applied before the test begins. No API/DB seeding hook is available
// in the registry to pre-apply a discount directly, so this test reproduces
// that precondition by applying the code once via the UI before attempting
// the duplicate application. The customer should confirm that SAVE10 is a
// valid, active 10% discount code in the target environment.
const DISCOUNT_CODE = "SAVE10";

test.describe("TC-005: Prevent duplicate application of the same discount code", () => {
  test("rejects applying the same discount code a second time on one order", async ({ page }) => {
    const cartPage = new CartPage(page);

    await page.goto(cartPage.url_pattern);

    // Verify: cart page loaded correctly for an authenticated user
    await expect(cartPage.cartHeading).toBeVisible();

    // Capture the order total before any discount is applied, for later comparison.
    const totalBeforeDiscount = await cartPage.orderTotal.textContent();

    // Apply the discount code the first time to establish the required precondition.
    await cartPage.discountCodeInput.fill(DISCOUNT_CODE);
    await cartPage.applyDiscountButton.click();

    // Verify: the first application of the discount code succeeds
    await expect(cartPage.discountStatusMessage).toBeVisible();
    await expect(cartPage.discountStatusMessage).toContainText(/applied/i);

    const totalAfterFirstApply = await cartPage.orderTotal.textContent();

    // Verify: order total reflects the discount being applied once
    expect(totalAfterFirstApply).not.toEqual(totalBeforeDiscount);

    // Attempt to apply the exact same discount code a second time.
    await cartPage.discountCodeInput.fill(DISCOUNT_CODE);
    await cartPage.applyDiscountButton.click();

    // Verify: the system rejects the duplicate application with an error/alert
    await expect(cartPage.cartErrorAlert).toBeVisible();
    await expect(cartPage.cartErrorAlert).toContainText(/already applied|duplicate|only.*once/i);

    const totalAfterSecondAttempt = await cartPage.orderTotal.textContent();

    // Verify: the order total is unchanged by the rejected duplicate attempt,
    // confirming the discount was not applied twice (no stacked discount)
    expect(totalAfterSecondAttempt).toEqual(totalAfterFirstApply);
  });
});