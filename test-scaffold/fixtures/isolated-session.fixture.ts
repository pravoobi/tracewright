import { test as base, expect } from "@playwright/test";

/**
 * Fixture for tests that need their OWN session instead of the shared
 * pre-captured one: login/lockout, session expiry, logout and password-change
 * tests. They log in through the login page, and may destroy or change the
 * session / account, which would break every other test if they used the
 * shared storage state.
 *
 * - The browser context starts logged out (empty storage state).
 * - Before each test the app's accounts and lockout counters are restored
 *   (`/test/reset-auth`, a test-only hook of the demo app).
 * - `expireSession()` ages the current session past the idle timeout so
 *   expiry can be tested without waiting 30 minutes.
 */
export const test = base.extend<{ resetAuth: void; expireSession: () => Promise<void> }>({
  storageState: { cookies: [], origins: [] },

  resetAuth: [
    async ({ context, baseURL }, use) => {
      await context.request.post(`${baseURL ?? "http://localhost:4000"}/test/reset-auth`);
      await use();
    },
    { auto: true },
  ],

  expireSession: async ({ context, baseURL }, use) => {
    await use(async () => {
      await context.request.post(`${baseURL ?? "http://localhost:4000"}/test/expire-session`);
    });
  },
});

export { expect };
