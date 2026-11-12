// ─── Tracewright — Generated Test ───────────────────────────────────────
// Test Card ID : TC-004
// Title        : Display applied discount code and percentage on checkout summary
// Source AC    : REQ-bc4a140d9ea3
// Regresses    : none
// Priority     : P1
// Type         : functional
// ─────────────────────────────────────────────────────────────────────────
// DO NOT EDIT locators manually — regenerate via Tracewright.

// Test ID: TC-004
// Title: Display applied discount code and percentage on checkout summary
// Source artifacts: REQ-bc4a140d9ea3
// Preconditions: User is authenticated; a valid discount code has been applied to an eligible order.
//
// Setup assumption: The setup manifest references a cart item with SKU "SKU-100" at $50.00,
// but the verified CartPage locators only expose named items (Widget, Gadget, Sticker) with no
// SKU-based locator. This test therefore relies on the authenticated-cart fixture to pre-populate
// an eligible cart and does not attempt to assert on SKU-100 directly. The customer must confirm
// that the fixture's pre-seeded cart represents an "eligible order" for discount purposes.

import { test, expect } from '../fixtures/authenticated-cart.fixture';
import { CartPage } from '../page-objects/CartPage';
import { CheckoutPage } from '../page-objects/CheckoutPage';

// Setup assumption: discount code value and percentage are taken from the setup manifest
// (SAVE10 / 10%) and have not been independently verified against the live discount service.
const DISCOUNT_CODE = 'SAVE10';
const DISCOUNT_PERCENTAGE = '10';

test.describe('TC-004: Applied discount code visibility on checkout summary', () => {
  test('displays the applied discount code and percentage before order confirmation', async ({ page }) => {
    const cartPage = new CartPage(page);
    const checkoutPage = new CheckoutPage(page);

    // Navigate to the cart page where the discount code can be applied.
    await page.goto(cartPage.url_pattern);

    // Apply the discount code to the eligible order.
    await cartPage.discountCodeInput.fill(DISCOUNT_CODE);
    await cartPage.applyDiscountButton.click();

    // Verify: the cart's discount summary confirms the code was accepted and applied.
    await expect(cartPage.discountSummary).toBeVisible();
    await expect(cartPage.discountSummary).toContainText(DISCOUNT_CODE);

    // Verify: the cart's discount summary also surfaces the discount percentage to the user.
    await expect(cartPage.discountSummary).toContainText(`${DISCOUNT_PERCENTAGE}%`);

    // Proceed to the checkout summary before the order is confirmed.
    await cartPage.proceedToCheckoutButton.click();
    await page.goto(checkoutPage.url_pattern);

    // Verify: the checkout page heading confirms successful navigation to the summary step.
    await expect(checkoutPage.checkoutHeading).toBeVisible();

    // Verify: the checkout summary still displays the applied discount code prior to order confirmation.
    await expect(checkoutPage.discountSummary).toBeVisible();
    await expect(checkoutPage.discountSummary).toContainText(DISCOUNT_CODE);

    // Verify: the checkout summary displays the correct discount percentage prior to order confirmation.
    await expect(checkoutPage.discountSummary).toContainText(`${DISCOUNT_PERCENTAGE}%`);

    // Verify: the "Place order" action is still available, confirming the order has not yet been confirmed.
    await expect(checkoutPage.placeOrderButton).toBeVisible();
  });
});