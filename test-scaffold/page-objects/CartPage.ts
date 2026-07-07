import { Page } from "@playwright/test";
import { BasePage } from "./BasePage";

// Generated from the Generator Phase 1 page-object registry (backend/evals/golden/app_model_registry.json)
// DO NOT EDIT locators manually — regenerate via the AI test agent.
export class CartPage extends BasePage {
  readonly url_pattern = "http://localhost:4000/cart";

  constructor(page: Page) {
    super(page);
  }

  get discountCodeInput() {
    return this.page.getByRole("textbox", { name: "Discount code" });
  }

  get applyDiscountButton() {
    return this.page.getByRole("button", { name: "Apply discount code" });
  }

  get proceedToCheckoutButton() {
    return this.page.getByRole("button", { name: "Proceed to checkout" });
  }

  // css_warned strategy — no stable role/name on this element, flagged for a data-testid
  get orderTotal() {
    return this.page.locator("#order-total");
  }

  // css_warned strategy — no stable role/name on this element, flagged for a data-testid
  get discountSummary() {
    return this.page.locator('dt:has-text("Discount")');
  }
}
