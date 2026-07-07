import { test as base, expect } from "@playwright/test";
import path from "path";

/**
 * Fixture for TC-DISCOUNT-001's precondition: an authenticated user with a
 * $50.00 cart (1x Widget + 1x Gadget — the demo-app's default cart on login).
 * Auth is provided via a pre-captured storage state, not a UI login step —
 * see backend/src/auth_capture/sessions.py and scripts/capture-demo-auth-session.py.
 */
export const test = base.extend({
  storageState: path.join(__dirname, "..", ".auth", "demo-app.json"),
});

export { expect };
