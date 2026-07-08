import { test as base, expect } from "@playwright/test";
import path from "path";

/**
 * Fixture for TC-DISCOUNT-001's precondition: an authenticated user with a
 * $50.00 cart (1x Widget + 1x Gadget — the demo-app's default cart on login).
 * Auth is provided via a pre-captured storage state, not a UI login step —
 * see backend/src/auth_capture/sessions.py and scripts/capture-demo-auth-session.py.
 */
export const test = base.extend<{ resetDemoApp: void }>({
  storageState: path.join(__dirname, "..", ".auth", "demo-app.json"),

  // Every generated test shares the same pre-captured session cookie, so
  // without this they'd all mutate the same server-side cart/discount
  // state. `auto` means every test using this fixture gets a clean cart
  // precondition without needing to remember to call it. Uses
  // context.request (not the bare `request` fixture) specifically so the
  // POST carries this test's own storageState cookie, not a separate
  // unauthenticated context.
  resetDemoApp: [
    async ({ context, baseURL }, use) => {
      await context.request.post(`${baseURL ?? "http://localhost:4000"}/reset`);
      await use();
    },
    { auto: true },
  ],
});

export { expect };
