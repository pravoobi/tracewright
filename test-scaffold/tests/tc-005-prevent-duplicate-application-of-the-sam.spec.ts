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

    // Set up the test card's stated precondition ourselves: the fixture only
    // guarantees an authenticated user with a clean cart, not an arbitrary
    // per-test discount state, so "SAVE10 already applied" has to be applied
    // here rather than assumed.
    await page.goto(cartPage.url_pattern);
    await cartPage.discountCodeInput.fill('SAVE10');
    await cartPage.applyDiscountButton.click();

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