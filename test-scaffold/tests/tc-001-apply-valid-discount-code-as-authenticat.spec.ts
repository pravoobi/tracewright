// ─── AI Test Agent — Generated Test ───────────────────────────────────────
// Test Card ID : TC-001
// Title        : Apply valid discount code as authenticated user
// Source AC    : None
// Priority     : P0
// Type         : functional
// ─────────────────────────────────────────────────────────────────────────
// DO NOT EDIT locators manually — regenerate via the AI test agent.

// Test Card: TC-001 - Apply valid discount code as authenticated user
// Source: setup_manifest defines authenticated_customer, discount_code SAVE10 (10%), cart item SKU-100 qty 1 @ $50.00
// Page Objects: ../page-objects/CartPage

import { test, expect } from '../fixtures/authenticated-cart.fixture';
import { CartPage } from '../page-objects/CartPage';

test.describe('TC-001 - Apply valid discount code as authenticated user', () => {
  test('should reduce order total by discount percentage when a valid code is applied', async ({ page }) => {
    const cartPage = new CartPage(page);

    // Navigate to the cart page where the pre-seeded cart item (SKU-100, $50.00) is available
    await page.goto(cartPage.url_pattern);

    // Capture the order total before applying the discount code
    const initialTotalText = await cartPage.orderTotal.textContent();
    const initialTotal = parseFloat(initialTotalText?.replace(/[^0-9.]/g, '') ?? '0');

    // Verify: precondition - cart total exceeds $10.00 as required by the test card
    expect(initialTotal).toBeGreaterThan(10.0);

    // Apply the valid discount code
    await cartPage.discountCodeInput.fill('SAVE10');
    await cartPage.applyDiscountButton.click();

    // Wait for the order total to reflect the discount by polling until it changes
    await expect(async () => {
      const updatedTotalText = await cartPage.orderTotal.textContent();
      const updatedTotal = parseFloat(updatedTotalText?.replace(/[^0-9.]/g, '') ?? '0');
      expect(updatedTotal).not.toBe(initialTotal);
    }).toPass();

    const finalTotalText = await cartPage.orderTotal.textContent();
    const finalTotal = parseFloat(finalTotalText?.replace(/[^0-9.]/g, '') ?? '0');

    const expectedTotal = initialTotal * 0.9; // 10% discount applied

    // Verify: the order total is reduced by exactly the discount percentage (10%) defined for SAVE10
    expect(finalTotal).toBeCloseTo(expectedTotal, 2);
  });
});