// Seed data for the eval-harness demo app.
// Content is deliberately aligned with backend/evals/golden/labels.json
// so the golden PDF's acceptance criteria have a real app to test against:
//   - discount codes reduce order total by a percentage (AC)
//   - codes cannot be applied to orders under $10.00 (business rule)
//   - a 20% code on a $50 cart yields $40 (example)

const USERS = [
  { email: "test@example.com", password: "password123" },
];

const PRODUCTS = [
  { id: "widget", name: "Widget", priceCents: 3000 },
  { id: "gadget", name: "Gadget", priceCents: 2000 },
  { id: "sticker", name: "Sticker", priceCents: 500 },
];

const DISCOUNT_CODES = {
  SAVE20: { code: "SAVE20", percentOff: 20 },
  SAVE10: { code: "SAVE10", percentOff: 10 },
};

const MIN_ORDER_FOR_DISCOUNT_CENTS = 1000; // $10.00

function defaultCart() {
  return { widget: 1, gadget: 1, sticker: 0 };
}

module.exports = { USERS, PRODUCTS, DISCOUNT_CODES, MIN_ORDER_FOR_DISCOUNT_CENTS, defaultCart };
