"""Cookie-based browser sessions.

Why: the SPA used to ship the tenant API key in its bundle, readable by anyone
who loads the page. Browsers now authenticate as a *user*: login sets an
HttpOnly, SameSite=Lax cookie holding a random token (only its SHA-256 is
stored server-side). No credential is ever readable from JavaScript.

Cookie auth brings CSRF risk, so every state-changing cookie-authenticated
request must carry the session's CSRF token in X-CSRF-Token (delivered by
/auth/login and /auth/me, never in a cookie) and, when a browser sends an
Origin header, that origin must be on the allowlist. API-key requests are not
cookie-based and are exempt.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.config import settings
from backend.src.db.models import AuthSession, User

_hasher = PasswordHasher()
# Verified against when the email is unknown, so login time doesn't reveal
# whether an account exists.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")

MIN_PASSWORD_LENGTH = 12
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# --- login throttling ------------------------------------------------------------
# The *_shared functions below are what the API uses: Redis-backed so the limit
# holds across replicas and restarts. The in-process functions are the
# fallback when Redis is unavailable (or login_throttle_backend="memory").
_MAX_FAILURES = 5
_WINDOW_SECONDS = 15 * 60
_failures: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def _recent_failures(key: tuple[str, str]) -> deque[float]:
    q = _failures[key]
    cutoff = time.monotonic() - _WINDOW_SECONDS
    while q and q[0] < cutoff:
        q.popleft()
    return q


def login_throttled(email: str, ip: str) -> bool:
    return len(_recent_failures((email, ip))) >= _MAX_FAILURES


def record_login_failure(email: str, ip: str) -> None:
    _recent_failures((email, ip)).append(time.monotonic())


def clear_login_failures(email: str, ip: str) -> None:
    _failures.pop((email, ip), None)


# Shared (Redis) limiter: counters survive restarts and are common to every
# replica. Fixed window starting at the first failure. If Redis is unreachable
# we fall back to the in-process limiter above rather than failing logins
# (closed) or dropping the throttle entirely (open).
_redis_client = None


def _redis():
    global _redis_client
    if settings.login_throttle_backend != "redis":
        return None
    if _redis_client is None:
        import redis.asyncio as aioredis

        _redis_client = aioredis.from_url(
            settings.redis_url, socket_timeout=1.0, socket_connect_timeout=1.0
        )
    return _redis_client


def _redis_key(email: str, ip: str) -> str:
    return "login_fail:" + hashlib.sha256(f"{email}\n{ip}".encode()).hexdigest()


async def login_throttled_shared(email: str, ip: str) -> bool:
    client = _redis()
    if client is not None:
        try:
            raw = await client.get(_redis_key(email, ip))
            return int(raw or 0) >= _MAX_FAILURES
        except Exception:
            pass
    return login_throttled(email, ip)


async def record_login_failure_shared(email: str, ip: str) -> None:
    client = _redis()
    if client is not None:
        try:
            key = _redis_key(email, ip)
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.expire(key, _WINDOW_SECONDS, nx=True)
            await pipe.execute()
            return
        except Exception:
            pass
    record_login_failure(email, ip)


async def clear_login_failures_shared(email: str, ip: str) -> None:
    clear_login_failures(email, ip)
    client = _redis()
    if client is not None:
        try:
            await client.delete(_redis_key(email, ip))
        except Exception:
            pass


# --- sessions ----------------------------------------------------------------------
async def authenticate(session: AsyncSession, email: str, password: str) -> User | None:
    user = await session.scalar(select(User).where(User.email == email.strip().lower()))
    ok = verify_password(user.password_hash if user else None, password)
    if not (ok and user is not None and user.is_active):
        return None
    return user


async def create_session(session: AsyncSession, user: User) -> tuple[str, AuthSession]:
    """Always mints a fresh token (no session fixation). Returns (raw_token, row)."""
    raw = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    row = AuthSession(
        token_hash=hash_token(raw),
        user_id=user.id,
        tenant_id=user.tenant_id,
        csrf_token=secrets.token_urlsafe(32),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.session_absolute_hours),
    )
    session.add(row)
    await session.commit()
    return raw, row


async def load_session(
    session: AsyncSession, raw_token: str | None
) -> tuple[AuthSession, User] | None:
    """The live session + user for a cookie token, or None (unknown, revoked,
    expired absolutely or by idleness, or user deactivated). Slides last_seen."""
    if not raw_token:
        return None
    row = await session.scalar(
        select(AuthSession).where(AuthSession.token_hash == hash_token(raw_token))
    )
    if row is None or row.revoked_at is not None:
        return None
    now = datetime.now(timezone.utc)
    if row.expires_at <= now or row.last_seen_at + timedelta(minutes=settings.session_idle_minutes) <= now:
        return None
    user = await session.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    # Only write when it matters, to keep reads cheap.
    if now - row.last_seen_at > timedelta(minutes=1):
        row.last_seen_at = now
        await session.commit()
    return row, user


async def revoke_session(session: AsyncSession, raw_token: str | None) -> None:
    if not raw_token:
        return
    row = await session.scalar(
        select(AuthSession).where(AuthSession.token_hash == hash_token(raw_token))
    )
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        await session.commit()


# --- CSRF --------------------------------------------------------------------------
def origin_allowed(origin: str | None) -> bool:
    """A browser sends Origin on cross-site and on same-site unsafe requests.
    Absent Origin (non-browser client) is left to the CSRF token check."""
    return origin is None or origin in settings.cors_allowed_origins


def csrf_valid(expected: str, supplied: str | None) -> bool:
    return bool(supplied) and hmac.compare_digest(expected, supplied)
