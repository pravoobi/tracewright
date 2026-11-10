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
