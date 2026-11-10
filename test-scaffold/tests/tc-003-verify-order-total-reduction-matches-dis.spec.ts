// ─── AI Test Agent — Generated Test (hand-corrected, see note) ────────────
// Test Card ID : TC-003
// Title        : Verify order total reduction matches discount percentage exactly
// Source AC    : A valid discount code reduces the order total by its percentage.
// Priority     : P0
// Type         : functional
// ─────────────────────────────────────────────────────────────────────────
// Correction note: the first generated version used a SAVE15 code and a
// SKU-200 @ $33.33 cart that do not exist in the demo app, so no discount was
// ever applied. The setup manifest now uses data the app really has:
// SAVE10 (10%) and a $55.00 cart (1 Widget + 1 Gadget + 1 Sticker).

import { test, expect } from '../fixtures/authenticated-cart.fixture';
import { CartPage } from '../page-objects/CartPage';

test.describe('TC-003: Order total reduction matches discount percentage', () => {
  test('applying SAVE10 discount reduces subtotal by exactly 10%', async ({ page }) => {
    const cartPage = new CartPage(page);

    await page.goto(cartPage.url_pattern);

    // Setup: $30.00 + $20.00 + $5.00 = $55.00 subtotal
    await cartPage.stickerQuantityInput.fill('1');
    await cartPage.updateCartButton.click();
    await expect(cartPage.orderTotal).toHaveText('$55.00');

    await cartPage.discountCodeInput.fill('SAVE10');
    await cartPage.applyDiscountButton.click();

    // Verify: exactly 10% off $55.00 = $5.50 -> $49.50
    await expect(cartPage.discountSummary).toContainText('SAVE10');
    await expect(cartPage.orderTotal).toHaveText('$49.50');
  });
});
