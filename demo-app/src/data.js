// Seed data for the eval-harness demo app.
// Content is deliberately aligned with backend/evals/golden/labels.json
// so the golden PDFs' acceptance criteria have a real app to test against:
//   - discount codes reduce order total by a percentage (AC)
//   - codes cannot be applied to orders under $10.00 (business rule)
//   - a 20% code on a $50 cart yields $40 (example)
//   - quantity of any single SKU may not exceed 99 (business rule)
//   - account lockout after 5 failed logins in 15 min, for 30 min (auth AC/BR)
//   - sessions expire after 30 min idle (auth AC)
//   - password change: >= 12 chars, differs from the previous 5 (auth AC)

// Each test target has its own account so tests that lock an account or
// change a password never disturb the shared `test@example.com` session the
// other tests (and the eval's login) depend on.
function freshUsers() {
  return [
    { email: "test@example.com", password: "password123", history: [] },
    { email: "lockout@example.com", password: "password123", history: [] },
    { email: "pwchange@example.com", password: "password123", history: [] },
  ];
}

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
const MAX_QTY_PER_SKU = 99;

const MAX_FAILED_LOGINS = 5;
const LOCKOUT_WINDOW_MS = 15 * 60 * 1000;
const LOCKOUT_MS = 30 * 60 * 1000;
const IDLE_TIMEOUT_MS = 30 * 60 * 1000;
const PASSWORD_MIN_LENGTH = 12;
const PASSWORD_HISTORY = 5;

function defaultCart() {
  return { widget: 1, gadget: 1, sticker: 0 };
}

module.exports = {
  freshUsers,
  PRODUCTS,
  DISCOUNT_CODES,
  MIN_ORDER_FOR_DISCOUNT_CENTS,
  MAX_QTY_PER_SKU,
  MAX_FAILED_LOGINS,
  LOCKOUT_WINDOW_MS,
  LOCKOUT_MS,
  IDLE_TIMEOUT_MS,
  PASSWORD_MIN_LENGTH,
  PASSWORD_HISTORY,
  defaultCart,
};
