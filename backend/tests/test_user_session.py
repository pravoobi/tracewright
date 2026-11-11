"""Pure-logic tests for browser sessions (DB/HTTP flow is covered by the live script)."""
import pytest

from backend.src.auth import user_session as us


def test_password_roundtrip_and_min_length():
    h = us.hash_password("correct horse battery")
    assert h.startswith("$argon2id$")
    assert us.verify_password(h, "correct horse battery")
    assert not us.verify_password(h, "wrong horse battery!")
    with pytest.raises(ValueError):
        us.hash_password("short")


def test_unknown_user_never_verifies():
    assert us.verify_password(None, "anything-at-all-123") is False


def test_token_hash_is_stable_and_not_the_token():
    assert us.hash_token("abc") == us.hash_token("abc")
    assert us.hash_token("abc") != "abc" and len(us.hash_token("abc")) == 64


def test_csrf_valid():
    assert us.csrf_valid("tok", "tok")
    assert not us.csrf_valid("tok", "other")
    assert not us.csrf_valid("tok", None) and not us.csrf_valid("tok", "")


def test_origin_allowed():
    assert us.origin_allowed(None)  # non-browser: CSRF token decides
    assert us.origin_allowed("http://localhost:5173")
    assert not us.origin_allowed("http://evil.test")


def test_login_throttle_window():
    key = ("t@x.test", "1.2.3.4")
    us.clear_login_failures(*key)
    for _ in range(4):
        us.record_login_failure(*key)
    assert not us.login_throttled(*key)
    us.record_login_failure(*key)
    assert us.login_throttled(*key)
    us.clear_login_failures(*key)
    assert not us.login_throttled(*key)
    assert not us.login_throttled("t@x.test", "9.9.9.9")  # per-IP
