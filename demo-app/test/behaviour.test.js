// Behavioural tests for the demo app: the target of the eval harness must
// itself behave as the golden requirements documents say it does.
// Run: node --test demo-app/test   (spawns the server on a free port)
const { test, before, after } = require("node:test");
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const path = require("node:path");

const PORT = 4100 + Math.floor(Math.random() * 800);
const BASE = `http://127.0.0.1:${PORT}`;
let server;

before(async () => {
  // The test runner marks its environment; a child node process would inherit it.
  const env = { ...process.env, PORT: String(PORT), NODE_ENV: "test" };
  delete env.NODE_TEST_CONTEXT;
  server = spawn(process.execPath, [path.join(__dirname, "..", "src", "server.js")], {
    env,
    stdio: "ignore",
  });
  for (let i = 0; i < 50; i++) {
    try {
      await fetch(`${BASE}/login`);
      return;
    } catch {
      await new Promise((r) => setTimeout(r, 100));
    }
  }
  throw new Error("demo app did not start");
});

after(() => server.kill());

// Minimal cookie-keeping client.
class Client {
  constructor() {
    this.cookie = "";
  }
  async req(method, url, form) {
    const res = await fetch(BASE + url, {
      method,
      redirect: "manual",
      headers: {
        cookie: this.cookie,
        ...(form ? { "content-type": "application/x-www-form-urlencoded" } : {}),
      },
      body: form ? new URLSearchParams(form).toString() : undefined,
    });
    const set = res.headers.getSetCookie?.() ?? [];
    if (set.length) this.cookie = set.map((c) => c.split(";")[0]).join("; ");
    return res;
  }
  // Follows one redirect and returns the final page's text.
  async page(method, url, form) {
    let res = await this.req(method, url, form);
    if (res.status >= 300 && res.status < 400) res = await this.req("GET", res.headers.get("location"));
    return { status: res.status, text: await res.text() };
  }
  login(email, password = "password123") {
    return this.page("POST", "/login", { email, password });
  }
}

const reset = () => fetch(`${BASE}/test/reset-auth`, { method: "POST" });

test("lockout: 5 failures lock the account, even for the right password", async () => {
  await reset();
  const c = new Client();
  for (let i = 0; i < 4; i++) {
    const r = await c.login("lockout@example.com", "wrong");
    assert.match(r.text, /Invalid email or password/);
  }
  const fifth = await c.login("lockout@example.com", "wrong");
  assert.match(fifth.text, /Account locked after 5 failed login attempts/);
  const correct = await c.login("lockout@example.com", "password123");
  assert.match(correct.text, /Account locked/);
  // other accounts are unaffected
  const other = await new Client().login("test@example.com");
  assert.match(other.text, /Your Cart/);
});

test("lockout: a successful login resets the failure counter", async () => {
  await reset();
  const c = new Client();
  for (let i = 0; i < 4; i++) await c.login("lockout@example.com", "wrong");
  assert.match((await new Client().login("lockout@example.com")).text, /Your Cart/);
  for (let i = 0; i < 4; i++) {
    assert.match((await c.login("lockout@example.com", "wrong")).text, /Invalid email or password/);
  }
});

test("login failure never reveals whether the email is registered", async () => {
  await reset();
  const known = await new Client().login("test@example.com", "nope");
  const unknown = await new Client().login("nobody@example.com", "nope");
  assert.match(known.text, /Invalid email or password/);
  assert.match(unknown.text, /Invalid email or password/);
});

test("idle session expires and the user is told why", async () => {
  await reset();
  const c = new Client();
  assert.match((await c.login("test@example.com")).text, /Your Cart/);
  assert.equal((await c.req("POST", "/test/expire-session")).status, 204);
  const after = await c.page("GET", "/cart");
  assert.match(after.text, /Log In/);
  assert.match(after.text, /session has expired due to inactivity/);
});

test("password change enforces length, email, confirmation, history and current password", async () => {
  await reset();
  const c = new Client();
  await c.login("pwchange@example.com");
  const change = (current, next, confirm = next) => c.page("POST", "/account/password", { current, next, confirm });

  assert.match((await change("wrong", "a-long-enough-pass1")).text, /Current password is incorrect/);
  assert.match((await change("password123", "short")).text, /at least 12 characters/);
  assert.match((await change("password123", "pwchange@example.com1")).text, /must not contain your email/);
  assert.match((await change("password123", "a-long-enough-pass1", "different-confirmation")).text, /do not match/);
  // (the seed password is 11 characters, so history is exercised with longer ones)
  assert.match((await change("password123", "second-password-01")).text, /Password changed/);
  assert.match((await change("second-password-01", "second-password-01")).text, /must differ from your previous 5/);
  assert.match((await change("second-password-01", "third-password-002")).text, /Password changed/);
  assert.match((await change("third-password-002", "second-password-01")).text, /must differ from your previous 5/);

  // the new password works at the login page; the old one does not
  assert.match((await new Client().login("pwchange@example.com", "third-password-002")).text, /Your Cart/);
  assert.match((await new Client().login("pwchange@example.com", "password123")).text, /Invalid email/);
  await reset();
  assert.match((await new Client().login("pwchange@example.com", "password123")).text, /Your Cart/);
});

test("quantity of a single SKU cannot exceed 99 and a rejected update changes nothing", async () => {
  await reset();
  const c = new Client();
  await c.login("test@example.com");
  const bad = await c.page("POST", "/cart/update", { "qty-widget": "100", "qty-gadget": "3", "qty-sticker": "0" });
  assert.match(bad.text, /Quantity for Widget cannot exceed 99/);
  assert.match(bad.text, /id="qty-gadget"[^>]*value="1"/); // cart unchanged
  const ok = await c.page("POST", "/cart/update", { "qty-widget": "99", "qty-gadget": "0", "qty-sticker": "0" });
  assert.doesNotMatch(ok.text, /cannot exceed/);
});

test("order history link only appears after an order has been placed", async () => {
  await reset();
  const c = new Client();
  const cart = await c.login("test@example.com");
  assert.doesNotMatch(cart.text, /Order history/);
  const empty = await c.page("GET", "/orders");
  assert.match(empty.text, /not placed any orders/);

  const conf = await c.page("POST", "/checkout/place-order");
  assert.match(conf.text, /Order Confirmed/);
  const afterOrder = await c.page("GET", "/cart");
  assert.match(afterOrder.text, /href="\/orders">Order history/);
  const list = await c.page("GET", "/orders");
  assert.match(list.text, /data-testid="order-history"/);
  assert.match(list.text, /ORD-/);

  await c.req("POST", "/reset");
  assert.doesNotMatch((await c.page("GET", "/cart")).text, /Order history/);
});

test("existing behaviour: discount minimum and duplicate code still enforced", async () => {
  await reset();
  const c = new Client();
  await c.login("test@example.com");
  const first = await c.page("POST", "/cart/discount", { code: "SAVE20" });
  assert.match(first.text, /applied: 20% off/);
  const dup = await c.page("POST", "/cart/discount", { code: "SAVE20" });
  assert.match(dup.text, /already applied/);
  await c.req("POST", "/cart/update", { "qty-widget": "0", "qty-gadget": "0", "qty-sticker": "1" });
  const low = await c.page("POST", "/cart/discount", { code: "SAVE10" });
  assert.match(low.text, /cannot be applied to orders under \$10\.00/);
});
