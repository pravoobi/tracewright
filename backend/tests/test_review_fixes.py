"""Regression tests for the code-review findings on the security hardening commits."""
import base64
import os

import pytest

from backend.src.agents.generator.app_model import _origin
from backend.src.agents.generator.codegen import check_generated_code_safety
from backend.src.agents.planner import _SAFE_TEST_ID
from backend.src.llm.cost import estimate_call_usd


# --- codegen safety scan -------------------------------------------------------
def test_multiline_import_from_allowed_module_is_accepted():
    code = "import {\n  CartPage,\n  CheckoutPage\n} from '../page-objects/CartPage';\n"
    assert check_generated_code_safety(code) == []


def test_single_line_and_playwright_imports_accepted():
    code = (
        "import { test, expect } from '../fixtures/authenticated-cart.fixture';\n"
        "import { Page } from \"@playwright/test\";\n"
    )
    assert check_generated_code_safety(code) == []


@pytest.mark.parametrize(
    "code",
    [
        "import fs from 'fs';",
        "import {\n a\n} from 'node:child_process';",
        "import '../fixtures/../../secrets';",
        "import x from '../page-objects/../../x';",
        "const m = await import('node:fs');",
        "const e = process['env'];",
        "const f = globalThis['fe' + 'tch'];",
        "const r = require('fs');",
    ],
)
def test_escape_hatches_rejected(code):
    assert check_generated_code_safety(code)


def test_method_named_exec_or_require_is_not_a_false_positive():
    code = "const m = /(\\d+)/.exec(text);\nconst v = obj.require('x');\n"
    assert check_generated_code_safety(code) == []


def test_bare_exec_still_rejected():
    assert check_generated_code_safety("exec('rm -rf /')")


# --- planner test_id validation ------------------------------------------------
def test_test_id_trailing_newline_rejected():
    assert _SAFE_TEST_ID.fullmatch("TC-1") is not None
    assert _SAFE_TEST_ID.fullmatch("TC-1\n") is None  # "$" would have accepted this
    assert _SAFE_TEST_ID.fullmatch("../x") is None
    assert _SAFE_TEST_ID.fullmatch("") is None


# --- origin comparison (SSRF guard) --------------------------------------------
def test_origin_normalises_case_and_default_ports():
    assert _origin("https://Staging.Example.com/a") == _origin("https://staging.example.com:443/b")
    assert _origin("http://x.test") == _origin("http://X.test:80/")


def test_origin_differs_by_scheme_host_or_port():
    base = _origin("https://staging.example.com")
    assert _origin("http://staging.example.com") != base
    assert _origin("https://evil.example.com") != base
    assert _origin("https://staging.example.com:8443") != base
    assert _origin("http://169.254.169.254/latest") != base


# --- LLM budget reservation estimate -------------------------------------------
def test_estimate_scales_with_max_tokens_and_prompt():
    msgs = [{"role": "user", "content": "x" * 4000}]
    small = estimate_call_usd("claude-haiku-4-5-20251001", msgs, 100)
    big = estimate_call_usd("claude-haiku-4-5-20251001", msgs, 10000)
    assert 0 < small < big


# --- legacy session decryption --------------------------------------------------
def test_legacy_master_key_ciphertext_still_decrypts(monkeypatch):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    from backend.src.auth_capture import sessions
    from backend.src.config import settings

    master = os.urandom(32)
    monkeypatch.setattr(settings, "auth_session_encryption_key", base64.b64encode(master).decode())

    nonce = os.urandom(12)
    legacy = nonce + AESGCM(master).encrypt(nonce, b'{"cookies": []}', None)

    # Per-tenant key can't open it ...
    from cryptography.exceptions import InvalidTag

    with pytest.raises(InvalidTag):
        sessions._decrypt(legacy, "00000000-0000-0000-0000-000000000001")
    # ... the legacy fallback can, and new-format data round-trips.
    assert sessions._decrypt_legacy(legacy) == b'{"cookies": []}'
    tenant = "00000000-0000-0000-0000-000000000001"
    assert sessions._decrypt(sessions._encrypt(b"hello", tenant), tenant) == b"hello"


# --- derived flows validation --------------------------------------------------
def test_validate_flows_keeps_only_wellformed_flows_on_crawled_urls():
    from backend.src.agents.generator.flows import validate_flows

    pages = [{"url": "http://app.test/cart", "snapshot": ""}]
    raw = {
        "pages": [
            {"page_name": "CartPage", "url": "http://app.test/cart#x", "elements": [
                {"semantic_name": "orderTotal", "role": None, "testid": "order-total"},
                {"semantic_name": "applyButton", "role": "button", "name": "Apply"},
                {"semantic_name": "bad name", "role": "button"},          # not camelCase
                {"semantic_name": "evil", "role": "javascript"},          # unknown role
                {"semantic_name": "noHint"},                              # no role/testid
                "junk",
            ]},
            {"page_name": "cart", "url": "http://app.test/cart", "elements": [{"semantic_name": "a", "role": "button"}]},
            {"page_name": "EvilPage", "url": "http://169.254.169.254/", "elements": [{"semantic_name": "a", "role": "button"}]},
        ]
    }
    flows = validate_flows(raw, pages)
    assert [f["page_name"] for f in flows] == ["CartPage"]
    assert [e["semantic_name"] for e in flows[0]["elements"]] == ["orderTotal", "applyButton"]
    assert flows[0]["url"] == "http://app.test/cart"


def test_validate_flows_tolerates_garbage():
    from backend.src.agents.generator.flows import validate_flows

    assert validate_flows("nope", []) == []
    assert validate_flows({"pages": "x"}, []) == []


def test_header_lists_every_traceability_link_and_flags_orphans():
    from backend.src.agents.generator.codegen import _build_metadata_header

    linked = _build_metadata_header(
        {
            "test_id": "TC-1",
            "title": "t",
            "traceability": [
                {"type": "chunk", "logical_id": "REQ-a1"},
                {"type": "chunk", "logical_id": "REQ-b2"},
                {"type": "bug", "logical_id": "BUG-9\n// injected"},
            ],
        }
    )
    assert "Source AC    : REQ-a1, REQ-b2" in linked
    assert "Regresses    : BUG-9// injected" in linked
    assert "\n// injected" not in linked  # newline can't break out of the comment

    orphan = _build_metadata_header({"test_id": "TC-2", "title": "t", "traceability": []})
    assert "Source AC    : UNLINKED" in orphan


# --- state-dependent elements (state_probe / flows) -------------------------

CARDS = "Apply code SAVE10 on the cart. Applying an invalid code BOGUS shows an error."


def test_validate_steps_accepts_harmless_fill_and_click():
    from backend.src.agents.generator.state_probe import validate_steps

    steps = validate_steps(
        [
            {"action": "fill", "role": "textbox", "name": "Discount code", "value": "SAVE10"},
            {"action": "click", "role": "button", "name": "Apply discount code"},
        ],
        CARDS,
    )
    assert steps and steps[0]["value"] == "SAVE10" and steps[1]["action"] == "click"


def test_validate_steps_refuses_unsafe_or_ungrounded_steps():
    from backend.src.agents.generator.state_probe import validate_steps

    click = lambda name: [{"action": "click", "role": "button", "name": name}]  # noqa: E731
    for bad in ("Place order", "Delete account", "Sign out", "Pay now", "Reset cart"):
        assert validate_steps(click(bad)) is None, bad
    # testid of a destructive control is judged too
    assert validate_steps([{"action": "click", "role": None, "name": None, "testid": "delete-btn"}]) is None
    # fill value: quoted from the cards, or inert text; never markup/script
    inert = [{"action": "fill", "role": "textbox", "name": "Discount code", "value": "BOGUS123"}]
    assert validate_steps(inert, CARDS)
    hostile = [{"action": "fill", "role": "textbox", "name": "Discount code", "value": "<script>x</script>"}]
    assert validate_steps(hostile, CARDS) is None
    # goto only to URLs the caller allows
    go = [{"action": "goto", "url": "http://app/checkout"}]
    assert validate_steps(go) is None
    assert validate_steps(go, url_ok=lambda u: u.startswith("http://app/"))
    assert validate_steps([{"action": "goto", "url": "http://evil/x"}], url_ok=lambda u: u.startswith("http://app/")) is None
    # unknown action, bad role, too many steps, empty
    assert validate_steps([{"action": "goto", "role": "button", "name": "x"}]) is None
    assert validate_steps([{"action": "click", "role": "textbox", "name": "x"}]) is None
    assert validate_steps(click("ok") * 8) is None
    assert validate_steps([]) is None


def test_validate_probes_only_on_crawled_urls_and_drops_unsafe():
    from backend.src.agents.generator.state_probe import validate_probes

    pages = [{"url": "http://app/cart", "snapshot": "x"}]
    good = {"state": "discountApplied", "url": "http://app/cart",
            "steps": [{"action": "fill", "role": "textbox", "name": "Discount code", "value": "SAVE10"}]}
    raw = {"probes": [
        good,
        {**good, "state": "offSite", "url": "http://evil/cart"},
        {**good, "state": "bad", "steps": [{"action": "click", "role": "button", "name": "Place order"}]},
        {**good, "state": "Bad-Name"},
    ]}
    out = validate_probes(raw, pages, CARDS)
    assert [p["state_id"] for p in out] == ["discountApplied"]
    # every reach starts with a goto to its (crawled) start page
    assert out[0]["steps"][0] == {"action": "goto", "url": "http://app/cart"}


def test_validate_flows_state_reach_comes_from_probe_not_llm():
    from backend.src.agents.generator.flows import validate_flows

    steps = [{"action": "click", "role": "button", "name": "Apply", "testid": None}]
    pages = [
        {"url": "http://app/cart", "snapshot": "x"},
        {"url": "http://app/cart", "snapshot": "y", "state_id": "applied", "reach": steps},
    ]
    raw = {"pages": [{"page_name": "CartPage", "url": "http://app/cart", "elements": [
        {"semantic_name": "total", "role": None, "testid": "order-total"},
        # LLM tries to smuggle its own action list alongside a real state name
        {"semantic_name": "summary", "role": None, "testid": "discount-summary",
         "state": "applied", "reach": [{"action": "click", "name": "Place order"}]},
        {"semantic_name": "ghost", "role": None, "testid": "ghost", "state": "nope"},
    ]}]}
    els = {e["semantic_name"]: e for e in validate_flows(raw, pages)[0]["elements"]}
    assert "reach" not in els["total"]
    assert els["summary"]["reach"] == steps  # ours, not the LLM's
    assert "ghost" not in els  # unknown state: dropped


def test_reset_path_must_be_same_origin_absolute_path():
    from backend.src.agents.generator.state_probe import valid_reset_path

    assert valid_reset_path("/reset") and valid_reset_path("/api/test/reset?x=1")
    for bad in (None, "", "reset", "//evil.test/reset", "http://evil.test/reset",
                "/a b", "/a\r\nHost: x", "/\\evil", "/" + "a" * 300):
        assert not valid_reset_path(bad), bad
