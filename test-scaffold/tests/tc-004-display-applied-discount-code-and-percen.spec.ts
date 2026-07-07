// ─── AI Test Agent — Generated Test ───────────────────────────────────────
// Test Card ID : TC-004
// Title        : Display applied discount code and percentage on checkout summary
// Source AC    : REQ-bc4a140d9ea3
// Priority     : P1
// Type         : functional
// ─────────────────────────────────────────────────────────────────────────
// DO NOT EDIT locators manually — regenerate via the AI test agent.

// Test Card: TC-004 - Display applied discount code and percentage on checkout summary
// Source Requirement: REQ-bc4a140d9ea3
// Page Objects: ../page-objects/CartPage, ../page-objects/CheckoutPage
// Fixture: ../fixtures/authenticated-cart.fixture

import { test, expect } from '../fixtures/authenticated-cart.fixture';
import { CartPage } from '../page-objects/CartPage';
import { CheckoutPage } from '../page-objects/CheckoutPage';

test.describe('TC-004: Display applied discount code and percentage on checkout summary', () => {
  test('should display discount code and percentage in checkout summary after applying a valid discount', async ({ page }) => {
    const cartPage = new CartPage(page);
    const checkoutPage = new CheckoutPage(page);

    // Navigate to the cart page where the eligible order items are present
    await page.goto(cartPage.url_pattern);

    // Apply the valid discount code
    await cartPage.discountCodeInput.fill('SAVE10');
    await cartPage.applyDiscountButton.click();

    // Verify: the discount summary line reflects both the applied code and its percentage
    await expect(cartPage.discountSummary).toContainText('SAVE10');
    await expect(cartPage.discountSummary).toContainText('10%');

    // Proceed to checkout to confirm the discount persists into the checkout summary
    await cartPage.proceedToCheckoutButton.click();
    await page.waitForURL(checkoutPage.url_pattern);

    // Verify: checkout order total reflects the discounted amount (50.00 - 10% = 45.00)
    await expect(checkoutPage.orderTotal).toContainText('45');

    // Verify: the place order button is visible, confirming the checkout summary is fully rendered
    // with the discount applied before order confirmation
    await expect(checkoutPage.placeOrderButton).toBeVisible();
  });
});