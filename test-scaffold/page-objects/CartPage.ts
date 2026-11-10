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

  get orderTotal() {
    return this.page.getByTestId("order-total");
  }

  get discountSummary() {
    return this.page.getByTestId("discount-summary");
  }

  get widgetQuantityInput() {
    return this.page.getByRole("spinbutton", { name: "Quantity for Widget" });
  }

  get gadgetQuantityInput() {
    return this.page.getByRole("spinbutton", { name: "Quantity for Gadget" });
  }

  get stickerQuantityInput() {
    return this.page.getByRole("spinbutton", { name: "Quantity for Sticker" });
  }

  get updateCartButton() {
    return this.page.getByRole("button", { name: "Update cart" });
  }

  get errorAlert() {
    return this.page.getByRole("alert");
  }
}
