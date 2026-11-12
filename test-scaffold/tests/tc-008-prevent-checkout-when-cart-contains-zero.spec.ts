// ─── Tracewright — Generated Test ───────────────────────────────────────
// Test Card ID : TC-008
// Title        : Prevent checkout when cart contains zero items
// Source AC    : REQ-51ebe9df0ecc
// Regresses    : none
// Priority     : P0
// Type         : negative
// ─────────────────────────────────────────────────────────────────────────
// DO NOT EDIT locators manually — regenerate via Tracewright.

// TC-008: Prevent checkout when cart contains zero items
// Source test card: TC-008
// Traceability: REQ-51ebe9df0ecc (cart limits requirement)
// Page objects: CartPage, CheckoutPage

import { test, expect } from '../fixtures/authenticated-cart.fixture';
import { CartPage } from '../page-objects/CartPage';
import { CheckoutPage } from '../page-objects/CheckoutPage';

// Setup assumption: the setup manifest specifies a cart with zero items, but no
// documented flow for emptying the cart was provided. We assume quantities can be
// reduced to 0 for each known product and persisted via "Update cart". The customer
// should confirm this is the correct way to reach a zero-item cart state.
const ZERO_QUANTITY = 0;

test.describe('TC-008: Prevent checkout when cart contains zero items', () => {
  test('checkout link and direct /checkout visit both return user to cart with an error when cart is empty', async ({ page }) => {
    const cartPage = new CartPage(page);
    const checkoutPage = new CheckoutPage(page);

    // Navigate to the cart page to set up the zero-item precondition.
    await page.goto(cartPage.url_pattern);

    // Setup assumption: drive all known product quantities to zero and persist the change.
    await cartPage.widgetQuantityInput.fill(String(ZERO_QUANTITY));
    await cartPage.gadgetQuantityInput.fill(String(ZERO_QUANTITY));
    await cartPage.stickerQuantityInput.fill(String(ZERO_QUANTITY));
    await cartPage.updateCartButton.click();

    // Verify: cart heading is still visible, confirming we remain on the cart page after the update.
    await expect(cartPage.cartHeading).toBeVisible();

    // Attempt checkout via the in-app "Proceed to checkout" control with an empty cart.
    await cartPage.proceedToCheckoutButton.click();

    // Verify: the app blocks checkout and keeps/returns the user on the cart page (business rule: no checkout with zero items).
    await expect(page).toHaveURL(cartPage.url_pattern);

    // Verify: an error alert is surfaced explaining why checkout was blocked.
    await expect(cartPage.cartErrorAlert).toBeVisible();

    // Now attempt a direct navigation to /checkout while the cart remains empty.
    await page.goto(checkoutPage.url_pattern);

    // Verify: direct navigation to /checkout is also redirected back to the cart page.
    await expect(page).toHaveURL(cartPage.url_pattern);

    // Verify: the same error alert is shown on the cart page after the direct checkout attempt.
    await expect(cartPage.cartErrorAlert).toBeVisible();
  });
});