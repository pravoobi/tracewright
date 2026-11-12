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


class _FakePipe:
    def __init__(self, store):
        self.store, self.ops = store, []

    def incr(self, key):
        self.ops.append(("incr", key))

    def expire(self, key, seconds, nx=False):
        self.ops.append(("expire", key, seconds, nx))

    async def execute(self):
        for op in self.ops:
            if op[0] == "incr":
                self.store["v"][op[1]] = self.store["v"].get(op[1], 0) + 1
            else:
                if not (op[3] and op[1] in self.store["ttl"]):
                    self.store["ttl"][op[1]] = op[2]


class _FakeRedis:
    def __init__(self):
        self.store = {"v": {}, "ttl": {}}

    async def get(self, key):
        return self.store["v"].get(key)

    def pipeline(self):
        return _FakePipe(self.store)

    async def delete(self, key):
        self.store["v"].pop(key, None)


class _DownRedis:
    async def get(self, key):
        raise ConnectionError("down")

    def pipeline(self):
        raise ConnectionError("down")

    async def delete(self, key):
        raise ConnectionError("down")


@pytest.mark.asyncio
async def test_shared_throttle_uses_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(us, "_redis", lambda: fake)
    key = ("r@x.test", "1.2.3.4")
    for _ in range(4):
        await us.record_login_failure_shared(*key)
    assert not await us.login_throttled_shared(*key)
    await us.record_login_failure_shared(*key)
    assert await us.login_throttled_shared(*key)
    assert not await us.login_throttled_shared("r@x.test", "9.9.9.9")
    assert list(fake.store["ttl"].values()) == [15 * 60]  # one window, set once
    await us.clear_login_failures_shared(*key)
    assert not await us.login_throttled_shared(*key)
    assert "email" not in next(iter(fake.store["ttl"]), "")  # key is hashed


@pytest.mark.asyncio
async def test_shared_throttle_falls_back_when_redis_down(monkeypatch):
    monkeypatch.setattr(us, "_redis", lambda: _DownRedis())
    key = ("d@x.test", "5.5.5.5")
    us.clear_login_failures(*key)
    for _ in range(5):
        await us.record_login_failure_shared(*key)
    assert await us.login_throttled_shared(*key)
    await us.clear_login_failures_shared(*key)
    assert not await us.login_throttled_shared(*key)
