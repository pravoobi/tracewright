// ─── AI Test Agent — Generated Test ───────────────────────────────────────
// Test Card ID : TC-008
// Title        : Prevent checkout when cart contains zero items
// Source AC    : None
// Priority     : P0
// Type         : negative
// ─────────────────────────────────────────────────────────────────────────
// DO NOT EDIT locators manually — regenerate via the AI test agent.

// Test Card: TC-008 - Prevent checkout when cart contains zero items
// Source: setup_manifest requires authenticated_customer with an empty cart
// Page Objects: CartPage, CheckoutPage

import { test, expect } from '../fixtures/authenticated-cart.fixture';
import { CartPage } from '../page-objects/CartPage';
import { CheckoutPage } from '../page-objects/CheckoutPage';

test.describe('TC-008: Prevent checkout when cart contains zero items', () => {
  test('should block checkout action when cart is empty', async ({ page }) => {
    const cartPage = new CartPage(page);
    const checkoutPage = new CheckoutPage(page);

    // Navigate to the cart page with an empty cart (precondition set via fixture/setup_manifest)
    await page.goto(cartPage.url_pattern);

    // Verify: the proceed to checkout button should be disabled when the cart has zero items
    await expect(cartPage.proceedToCheckoutButton).toBeDisabled();

    // Attempt to navigate directly to the checkout page as an alternate path to bypass the disabled button
    await page.goto(checkoutPage.url_pattern);

    // Verify: the system should not allow the user to remain on/reach the checkout page with an empty cart,
    // redirecting back to the cart instead of permitting checkout to proceed
    await expect(page).toHaveURL(cartPage.url_pattern);
  });
});