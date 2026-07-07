import { Page } from "@playwright/test";
import { BasePage } from "./BasePage";

// Generated from the Generator Phase 1 page-object registry (backend/evals/golden/app_model_registry.json)
// DO NOT EDIT locators manually — regenerate via the AI test agent.
export class CheckoutPage extends BasePage {
  readonly url_pattern = "http://localhost:4000/checkout";

  constructor(page: Page) {
    super(page);
  }

  get placeOrderButton() {
    return this.page.getByRole("button", { name: "Place order" });
  }

  // css_warned strategy — no stable role/name on this element, flagged for a data-testid
  get orderTotal() {
    return this.page.locator("#order-total");
  }
}
