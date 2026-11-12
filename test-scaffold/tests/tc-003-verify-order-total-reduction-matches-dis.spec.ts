// ─── Tracewright — Generated Test ───────────────────────────────────────
// Test Card ID : TC-003
// Title        : Verify order total reduction matches discount percentage exactly
// Source AC    : REQ-d8ed22fa69dc
// Regresses    : none
// Priority     : P0
// Type         : functional
// ─────────────────────────────────────────────────────────────────────────
// DO NOT EDIT locators manually — regenerate via Tracewright.

// Test ID: TC-003
// Title: Verify order total reduction matches discount percentage exactly
// Source artifacts: REQ-d8ed22fa69dc
// Page objects: CartPage, CheckoutPage

import { test, expect } from '../fixtures/authenticated-cart.fixture';
import { CartPage } from '../page-objects/CartPage';
import { CheckoutPage } from '../page-objects/CheckoutPage';

// Setup data grounded in test card preconditions/setup manifest.
const DISCOUNT_CODE = 'SAVE10';
const DISCOUNT_PERCENTAGE = 10;
const EXPECTED_SUBTOTAL_USD = 55.0; // widget 30.00 + gadget 20.00 + sticker 5.00
const EXPECTED_TOTAL_AFTER_DISCOUNT_USD =
  EXPECTED_SUBTOTAL_USD * (1 - DISCOUNT_PERCENTAGE / 100); // 49.50

test.describe('TC-003: Order total reduction matches discount percentage exactly', () => {
  test('applying SAVE10 reduces subtotal by exactly 10%', async ({ page }) => {
    const cartPage = new CartPage(page);
    const checkoutPage = new CheckoutPage(page);

    // Setup: navigate to cart and establish known item quantities so the
    // subtotal matches the precondition of $55.00 (widget 1, gadget 1, sticker 1).
    await page.goto(cartPage.url_pattern);
    await cartPage.widgetQuantityInput.fill('1');
    await cartPage.gadgetQuantityInput.fill('1');
    await cartPage.stickerQuantityInput.fill('1');
    await cartPage.updateCartButton.click();

    // Verify: cart reflects the expected subtotal before any discount is applied.
    await expect(cartPage.orderTotal).toContainText(
      EXPECTED_SUBTOTAL_USD.toFixed(2)
    );

    // Apply the discount code under test.
    await cartPage.discountCodeInput.fill(DISCOUNT_CODE);
    await cartPage.applyDiscountButton.click();

    // Verify: the application confirms the discount was accepted/applied.
    await expect(cartPage.discountStatusMessage).toBeVisible();

    // Verify: the discount summary communicates the correct percentage applied.
    await expect(cartPage.discountSummary).toContainText(
      `${DISCOUNT_PERCENTAGE}%`
    );

    // Verify: the order total is reduced by exactly the discount percentage,
    // i.e. $55.00 * (1 - 10%) = $49.50, confirming the discount math is exact.
    await expect(cartPage.orderTotal).toContainText(
      EXPECTED_TOTAL_AFTER_DISCOUNT_USD.toFixed(2)
    );

    // Proceed to checkout to confirm the discounted total persists through the flow.
    await cartPage.proceedToCheckoutButton.click();
    await expect(checkoutPage.checkoutHeading).toBeVisible();

    // Verify: checkout page displays the same discounted total as the cart,
    // ensuring consistency of the discount application across pages.
    await expect(checkoutPage.orderTotal).toContainText(
      EXPECTED_TOTAL_AFTER_DISCOUNT_USD.toFixed(2)
    );

    // Verify: checkout discount summary still reflects the applied percentage.
    await expect(checkoutPage.discountSummary).toContainText(
      `${DISCOUNT_PERCENTAGE}%`
    );
  });
});