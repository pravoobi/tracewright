// ─── AI Test Agent — Generated Test ───────────────────────────────────────
// Test Card ID : TC-DISCOUNT-001
// Title        : Applying a 20% discount code at checkout reduces a $50 cart to $40
// Source AC    : None
// Priority     : P1
// Type         : functional
// ─────────────────────────────────────────────────────────────────────────
// DO NOT EDIT locators manually — regenerate via the AI test agent.

// TC-DISCOUNT-001: Applying a 20% discount code at checkout reduces a $50 cart to $40
// Source test card: TC-DISCOUNT-001
// Source artifacts: CartPage, CheckoutPage (page-object registry)
// Priority: P1 | Type: functional

import { test } from '../fixtures/authenticated-cart.fixture';
import { expect } from '@playwright/test';
import { CartPage } from '../page-objects/CartPage';
import { CheckoutPage } from '../page-objects/CheckoutPage';

/**
 * Preconditions (provided by fixture):
 * - User test@example.com is authenticated.
 * - Cart contains 1x Widget ($30.00) and 1x Gadget ($20.00), subtotal $50.00.
 * - No discount code is currently applied.
 */

test.describe('TC-DISCOUNT-001: Discount code application at checkout', () => {
  test('applying SAVE20 reduces a $50 cart to $40 on cart and checkout pages', async ({ page }) => {
    const cartPage = new CartPage(page);
    const checkoutPage = new CheckoutPage(page);

    await page.goto(cartPage.url_pattern ?? 'http://localhost:4000/cart');

    // Verify: subtotal before discount reflects the expected $50.00 precondition
    await expect(cartPage.orderTotal).toHaveText(/\$50\.00/);

    // Apply the discount code SAVE20
    await cartPage.discountCodeInput.fill('SAVE20');
    await cartPage.applyDiscountButton.click();

    // Verify: cart page order total updates to reflect the 20% discount ($50 -> $40)
    await expect(cartPage.orderTotal).toHaveText(/\$40\.00/);

    // Proceed to checkout
    await cartPage.proceedToCheckoutButton.click();
    await page.waitForURL(checkoutPage.url_pattern ?? 'http://localhost:4000/checkout');

    // Verify: checkout page reflects the same discounted total carried over from the cart
    await expect(checkoutPage.orderTotal).toHaveText(/\$40\.00/);
  });
});