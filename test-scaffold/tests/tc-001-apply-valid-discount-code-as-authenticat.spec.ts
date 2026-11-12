// ─── Tracewright — Generated Test ───────────────────────────────────────
// Test Card ID : TC-001
// Title        : Apply valid discount code as authenticated user
// Source AC    : REQ-d8ed22fa69dc
// Regresses    : none
// Priority     : P0
// Type         : functional
// ─────────────────────────────────────────────────────────────────────────
// DO NOT EDIT locators manually — regenerate via Tracewright.

// Test Card: TC-001 — Apply valid discount code as authenticated user
// Source Requirement: REQ-d8ed22fa69dc
// Preconditions: Authenticated user, valid discount code (SAVE10, 10%), cart with SKU-100 qty 1 @ $50.00

import { test, expect } from '../fixtures/authenticated-cart.fixture';
import { CartPage } from '../page-objects/CartPage';

// Setup manifest values for this scenario (as provided in the test card setup_manifest)
const DISCOUNT_CODE = 'SAVE10';
const DISCOUNT_PERCENTAGE = 10;
const ITEM_PRICE_USD = 50.0;
const ITEM_QUANTITY = 1;

test.describe('TC-001: Apply valid discount code as authenticated user', () => {
  test('authenticated user applies valid discount code and order total is reduced by the correct percentage', async ({ page }) => {
    const cartPage = new CartPage(page);

    // Navigate to the cart page where the pre-seeded cart (SKU-100 x1 @ $50.00) is available
    await page.goto(cartPage.url_pattern);

    // Verify: Cart page loaded correctly for the authenticated user
    await expect(cartPage.cartHeading).toBeVisible();

    // Calculate expected total after discount is applied
    const subtotal = ITEM_PRICE_USD * ITEM_QUANTITY;
    const expectedDiscountedTotal = subtotal * (1 - DISCOUNT_PERCENTAGE / 100);

    // Apply the valid discount code
    await cartPage.discountCodeInput.fill(DISCOUNT_CODE);
    await cartPage.applyDiscountButton.click();

    // Verify: The system confirms the discount code was applied successfully
    await expect(cartPage.discountStatusMessage).toBeVisible();

    // Verify: A discount summary is displayed reflecting the applied discount
    await expect(cartPage.discountSummary).toBeVisible();
    await expect(cartPage.discountSummary).toContainText(`${DISCOUNT_PERCENTAGE}%`);

    // Verify: The order total reflects the reduced price after applying the 10% discount
    await expect(cartPage.orderTotal).toContainText(expectedDiscountedTotal.toFixed(2));

    // Verify: No error alert is shown since the discount code is valid
    await expect(cartPage.cartErrorAlert).not.toBeVisible();
  });
});