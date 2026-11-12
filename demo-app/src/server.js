const path = require("path");
const express = require("express");
const session = require("express-session");
const { USERS, PRODUCTS, DISCOUNT_CODES, MIN_ORDER_FOR_DISCOUNT_CENTS, defaultCart } = require("./data");

// This app is the eval harness's seeded test target ONLY (CLAUDE.md's
// "demo-app: a small seeded web app for the eval harness") -- it has a
// hardcoded session secret, plaintext password comparison, and an
// unauthenticated /reset endpoint that wipes session state on request.
// None of that is acceptable outside a local/CI test fixture, so refuse to
// start under NODE_ENV=production and never bind beyond localhost by
// default, rather than relying on nobody ever pointing a deploy config at
// this directory by mistake.
if (process.env.NODE_ENV === "production") {
  console.error(
    "demo-app refuses to start with NODE_ENV=production -- it is a test fixture " +
      "(hardcoded session secret, plaintext credential check, unauthenticated /reset), " +
      "never a deployable app."
  );
  process.exit(1);
}

const app = express();
const PORT = process.env.PORT || 4000;
const HOST = process.env.DEMO_APP_HOST || "127.0.0.1";

app.set("view engine", "ejs");
app.set("views", path.join(__dirname, "..", "views"));
app.use(express.static(path.join(__dirname, "..", "public")));
app.use(express.urlencoded({ extended: false }));
app.use((req, res, next) => {
  console.log(`${req.method} ${req.path}`, req.method === "POST" ? req.body : "");
  next();
});
app.use(
  session({
    secret: "demo-app-dev-secret",
    resave: false,
    saveUninitialized: false,
    cookie: { maxAge: 1000 * 60 * 60 },
  })
);

function requireAuth(req, res, next) {
  if (!req.session.user) return res.redirect("/login");
  next();
}

function centsToDollars(cents) {
  return (cents / 100).toFixed(2);
}

function cartLines(cart) {
  return PRODUCTS.map((p) => ({
    ...p,
    qty: cart[p.id] || 0,
    lineTotalCents: p.priceCents * (cart[p.id] || 0),
  })).filter((line) => line.qty > 0 || cart[line.id] !== undefined);
}

function subtotalCents(cart) {
  return PRODUCTS.reduce((sum, p) => sum + p.priceCents * (cart[p.id] || 0), 0);
}

function popFlash(req) {
  const flash = req.session.flash;
  req.session.flash = null;
  return flash;
}

function setFlash(req, type, text) {
  req.session.flash = { type, text };
}

app.get("/", (req, res) => {
  res.redirect(req.session.user ? "/cart" : "/login");
});

app.get("/login", (req, res) => {
  if (req.session.user) return res.redirect("/cart");
  res.render("login", { error: popFlash(req) });
});

app.post("/login", (req, res) => {
  const { email, password } = req.body;
  const user = USERS.find((u) => u.email === email && u.password === password);
  if (!user) {
    setFlash(req, "error", "Invalid email or password.");
    return res.redirect("/login");
  }
  req.session.user = { email: user.email };
  req.session.cart = defaultCart();
  req.session.discount = null;
  res.redirect("/cart");
});

app.post("/logout", (req, res) => {
  req.session.destroy(() => res.redirect("/login"));
});

// Test-only: every generated Playwright test presents the same
// pre-captured storage-state session cookie, so without this they all
// share one server-side session (default express-session MemoryStore)
// and mutate the same cart/discount state. Called from a beforeEach hook
// so each test starts from a known-clean precondition regardless of
// what a previous test left behind.
app.post("/reset", (req, res) => {
  if (req.session) {
    req.session.cart = defaultCart();
    req.session.discount = null;
    req.session.flash = null;
  }
  res.status(204).end();
});

app.get("/cart", requireAuth, (req, res) => {
  const cart = req.session.cart || defaultCart();
  const subtotal = subtotalCents(cart);
  const discount = req.session.discount;
  const discountCents = discount ? Math.round((subtotal * discount.percentOff) / 100) : 0;
  res.render("cart", {
    lines: cartLines(cart),
    subtotalDisplay: centsToDollars(subtotal),
    discount,
    discountDisplay: centsToDollars(discountCents),
    totalDisplay: centsToDollars(subtotal - discountCents),
    message: popFlash(req),
  });
});

app.post("/cart/update", requireAuth, (req, res) => {
  const cart = {};
  for (const p of PRODUCTS) {
    const raw = req.body[`qty-${p.id}`];
    const qty = Math.max(0, parseInt(raw, 10) || 0);
    cart[p.id] = qty;
  }
  req.session.cart = cart;
  // Re-applying an existing discount against the new subtotal keeps behavior honest
  // instead of silently carrying a stale discount forward.
  if (req.session.discount) {
    const subtotal = subtotalCents(cart);
    if (subtotal < MIN_ORDER_FOR_DISCOUNT_CENTS) {
      req.session.discount = null;
      setFlash(req, "error", "Your discount code was removed because the order total fell below $10.00.");
    }
  }
  res.redirect("/cart");
});

app.post("/cart/discount", requireAuth, (req, res) => {
  const code = (req.body.code || "").trim().toUpperCase();
  const cart = req.session.cart || defaultCart();
  const subtotal = subtotalCents(cart);

  if (subtotal < MIN_ORDER_FOR_DISCOUNT_CENTS) {
    setFlash(req, "error", "Discount codes cannot be applied to orders under $10.00.");
    return res.redirect("/cart");
  }

  const discount = DISCOUNT_CODES[code];
  if (!discount) {
    setFlash(req, "error", `"${code}" is not a valid discount code.`);
    return res.redirect("/cart");
  }

  // A discount code may only be applied once per order (REQ: "applied once
  // per order"): re-submitting the code already on the order is rejected, not
  // silently accepted again.
  if (req.session.discount && req.session.discount.code === discount.code) {
    setFlash(req, "error", `Discount code ${discount.code} is already applied to this order.`);
    return res.redirect("/cart");
  }

  req.session.discount = discount;
  setFlash(req, "success", `Discount code ${discount.code} applied: ${discount.percentOff}% off.`);
  res.redirect("/cart");
});

app.get("/checkout", requireAuth, (req, res) => {
  const cart = req.session.cart || defaultCart();
  const subtotal = subtotalCents(cart);
  if (subtotal <= 0) {
    setFlash(req, "error", "Your cart is empty.");
    return res.redirect("/cart");
  }
  const discount = req.session.discount;
  const discountCents = discount ? Math.round((subtotal * discount.percentOff) / 100) : 0;
  res.render("checkout", {
    lines: cartLines(cart),
    subtotalDisplay: centsToDollars(subtotal),
    discount,
    discountDisplay: centsToDollars(discountCents),
    totalDisplay: centsToDollars(subtotal - discountCents),
  });
});

app.post("/checkout/place-order", requireAuth, (req, res) => {
  const cart = req.session.cart || defaultCart();
  const subtotal = subtotalCents(cart);
  const discount = req.session.discount;
  const discountCents = discount ? Math.round((subtotal * discount.percentOff) / 100) : 0;
  const total = subtotal - discountCents;

  const orderId = `ORD-${Date.now().toString(36).toUpperCase()}`;
  req.session.cart = defaultCart();
  req.session.discount = null;

  res.render("confirmation", { orderId, totalDisplay: centsToDollars(total) });
});

app.listen(PORT, HOST, () => {
  console.log(`demo-app (test fixture, not for production use) listening on http://${HOST}:${PORT}`);
});
