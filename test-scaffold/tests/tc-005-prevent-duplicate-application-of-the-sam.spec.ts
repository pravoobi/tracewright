// ─── AI Test Agent — Generated Test ───────────────────────────────────────
// Test Card ID : TC-005
// Title        : Prevent duplicate application of the same discount code on one order
// Source AC    : None
// Priority     : P1
// Type         : negative
// ─────────────────────────────────────────────────────────────────────────
// DO NOT EDIT locators manually — regenerate via the AI test agent.

/**
 * Test Card: TC-005
 * Title: Prevent duplicate application of the same discount code on one order
 * Priority: P1
 * Type: Negative
 *
 * Source artifacts:
 * - Page Object Registry: CartPage, CheckoutPage
 * - Fixture: ../fixtures/authenticated-cart.fixture
 */

import { test, expect } from '../fixtures/authenticated-cart.fixture';
import { CartPage } from '../page-objects/CartPage';

test.describe('TC-005: Prevent duplicate application of the same discount code on one order', () => {
  test('rejects re-applying an already-applied discount code to the same order', async ({ page }) => {
    const cartPage = new CartPage(page);

    // Navigate to the cart which already has SAVE10 applied per preconditions
    await page.goto(cartPage.url_pattern);

    // Verify: discount summary confirms the discount code is already applied before attempting duplication
    await expect(cartPage.discountSummary).toBeVisible();

    const totalBeforeSecondAttempt = await cartPage.orderTotal.textContent();

    // Attempt to apply the same discount code a second time
    await cartPage.discountCodeInput.fill('SAVE10');
    await cartPage.applyDiscountButton.click();

    // Verify: the system does not allow the discount code to be applied twice — only one discount line remains
    await expect(cartPage.discountSummary).toHaveCount(1);

    // Verify: the order total remains unchanged, confirming no additional discount was applied
    await expect(cartPage.orderTotal).toHaveText(totalBeforeSecondAttempt ?? '');
  });
});