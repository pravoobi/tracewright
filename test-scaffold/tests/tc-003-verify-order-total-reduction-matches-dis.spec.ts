// ─── AI Test Agent — Generated Test ───────────────────────────────────────
// Test Card ID : TC-003
// Title        : Verify order total reduction matches discount percentage exactly
// Source AC    : None
// Priority     : P0
// Type         : functional
// ─────────────────────────────────────────────────────────────────────────
// DO NOT EDIT locators manually — regenerate via the AI test agent.

// Test Card: TC-003
// Title: Verify order total reduction matches discount percentage exactly
// Source: setup_manifest - authenticated_customer, SAVE15 discount code (15%), cart with SKU-200 x2 @ $33.33
// Page Objects: CartPage, CheckoutPage

import { test, expect } from '../fixtures/authenticated-cart.fixture';
import { CartPage } from '../page-objects/CartPage';
import { CheckoutPage } from '../page-objects/CheckoutPage';

test.describe('TC-003: Order total reduction matches discount percentage exactly', () => {
  test('applying SAVE15 discount reduces subtotal by exactly 15% with correct rounding', async ({ page }) => {
    const cartPage = new CartPage(page);

    // Precondition setup: cart contains SKU-200 x2 @ $33.33 => subtotal $66.66
    const subtotal = 2 * 33.33;
    const discountPercentage = 15;
    const expectedDiscountAmount = Math.round(subtotal * (discountPercentage / 100) * 100) / 100;
    const expectedTotal = Math.round((subtotal - expectedDiscountAmount) * 100) / 100;

    await page.goto(cartPage.url_pattern);

    // Capture the order total before applying the discount
    const preDiscountTotalText = await cartPage.orderTotal.textContent();
    const preDiscountTotal = parseFloat((preDiscountTotalText ?? '').replace(/[^0-9.]/g, ''));

    // Verify: cart subtotal matches the expected pre-discount amount based on cart contents
    expect(preDiscountTotal).toBeCloseTo(subtotal, 2);

    await cartPage.discountCodeInput.fill('SAVE15');
    await cartPage.applyDiscountButton.click();

    // Wait for the order total to reflect the discounted amount
    await expect(cartPage.orderTotal).toHaveText(new RegExp(expectedTotal.toFixed(2).replace('.', '\\.')));

    const postDiscountTotalText = await cartPage.orderTotal.textContent();
    const postDiscountTotal = parseFloat((postDiscountTotalText ?? '').replace(/[^0-9.]/g, ''));

    // Verify: applying the 15% discount reduces the order total by exactly the expected discount amount
    expect(subtotal - postDiscountTotal).toBeCloseTo(expectedDiscountAmount, 2);

    // Verify: the resulting order total matches the precisely calculated discounted amount with correct rounding
    expect(postDiscountTotal).toBeCloseTo(expectedTotal, 2);

    await cartPage.proceedToCheckoutButton.click();

    const checkoutPage = new CheckoutPage(page);
    await page.waitForURL(checkoutPage.url_pattern);

    const checkoutTotalText = await checkoutPage.orderTotal.textContent();
    const checkoutTotal = parseFloat((checkoutTotalText ?? '').replace(/[^0-9.]/g, ''));

    // Verify: the discounted total persists correctly through to the checkout page
    expect(checkoutTotal).toBeCloseTo(expectedTotal, 2);
  });
});