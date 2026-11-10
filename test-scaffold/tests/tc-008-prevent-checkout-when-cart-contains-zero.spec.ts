// ─── AI Test Agent — Generated Test (hand-corrected, see note) ────────────
// Test Card ID : TC-008
// Title        : Prevent checkout when cart contains zero items
// Source AC    : "The system shall prevent checkout when the cart contains zero items."
// Priority     : P0
// Type         : negative
// ─────────────────────────────────────────────────────────────────────────
// Correction note: the first generated version (a) asserted the checkout link
// is `disabled` — the requirement says checkout is *prevented*, not how, and
// the app blocks it server-side — and (b) never emptied the cart, so its
// "empty cart" precondition was not actually established. The setup manifest
// (empty cart) is now fulfilled through the cart UI.

import { test, expect } from '../fixtures/authenticated-cart.fixture';
import { CartPage } from '../page-objects/CartPage';

test.describe('TC-008: Prevent checkout when cart contains zero items', () => {
  test('should block checkout action when cart is empty', async ({ page }) => {
    const cartPage = new CartPage(page);

    // Setup: empty the cart (default cart is 1x Widget + 1x Gadget)
    await page.goto(cartPage.url_pattern);
    await cartPage.widgetQuantityInput.fill('0');
    await cartPage.gadgetQuantityInput.fill('0');
    await cartPage.stickerQuantityInput.fill('0');
    await cartPage.updateCartButton.click();
    await expect(cartPage.orderTotal).toHaveText('$0.00');

    // Verify: following the checkout link does not reach checkout
    await cartPage.proceedToCheckoutButton.click();
    await expect(page).toHaveURL(cartPage.url_pattern);
    await expect(cartPage.errorAlert).toHaveText('Your cart is empty.');

    // Verify: navigating to checkout directly is also blocked
    await page.goto('/checkout');
    await expect(page).toHaveURL(cartPage.url_pattern);
    await expect(cartPage.errorAlert).toHaveText('Your cart is empty.');
  });
});
