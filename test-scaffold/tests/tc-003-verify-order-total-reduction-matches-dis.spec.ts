// ─── AI Test Agent — Generated Test ───────────────────────────────────────
// Test Card ID : TC-003
// Title        : Verify order total reduction matches discount percentage exactly
// Source AC    : None
// Priority     : P0
// Type         : functional
// ─────────────────────────────────────────────────────────────────────────
// DO NOT EDIT locators manually — regenerate via the AI test agent.

// Test Card: TC-003 - Verify order total reduction matches discount percentage exactly
// Source: setup_manifest (authenticated_customer, SAVE15 discount code, cart with SKU-200 x2)
// Page Objects: ../page-objects/CartPage, ../page-objects/CheckoutPage
// Fixture: ../fixtures/authenticated-cart.fixture

import { test, expect } from '../fixtures/authenticated-cart.fixture';
import { CartPage } from '../page-objects/CartPage';

test.describe('TC-003: Order total reduction matches discount percentage', () => {
  test('applying SAVE15 discount reduces subtotal by exactly 15% with correct rounding', async ({ page }) => {
    const cartPage = new CartPage(page);

    // Setup: cart contains SKU-200 x2 @ $33.33 = $66.66 subtotal
    const subtotal = 2 * 33.33;
    const discountPercentage = 15;
    const expectedDiscountAmount = Math.round(subtotal * (discountPercentage / 100) * 100) / 100;
    const expectedTotal = Math.round((subtotal - expectedDiscountAmount) * 100) / 100;

    await page.goto(cartPage.url_pattern);

    // Capture the subtotal before discount is applied
    const totalBeforeDiscountText = await cartPage.orderTotal.textContent();
    const totalBeforeDiscount = parseFloat(totalBeforeDiscountText?.replace(/[^0-9.]/g, '') ?? '0');

    // Verify: pre-discount total matches expected cart subtotal from setup manifest
    expect(totalBeforeDiscount).toBeCloseTo(subtotal, 2);

    await cartPage.discountCodeInput.fill('SAVE15');
    await cartPage.applyDiscountButton.click();

    // Wait for order total to update after discount application
    await expect(cartPage.orderTotal).not.toHaveText(totalBeforeDiscountText ?? '');

    const totalAfterDiscountText = await cartPage.orderTotal.textContent();
    const totalAfterDiscount = parseFloat(totalAfterDiscountText?.replace(/[^0-9.]/g, '') ?? '0');

    // Verify: order total after discount reflects exact 15% reduction with correct rounding
    expect(totalAfterDiscount).toBeCloseTo(expectedTotal, 2);

    const actualDiscountAmount = Math.round((totalBeforeDiscount - totalAfterDiscount) * 100) / 100;

    // Verify: the discounted amount matches exactly 15% of the subtotal
    expect(actualDiscountAmount).toBeCloseTo(expectedDiscountAmount, 2);
  });
});