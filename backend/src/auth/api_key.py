"""Per-tenant API key authentication.

Every endpoint previously took tenant_id as a plain URL path parameter
with no credential check at all -- any caller could read/write any
tenant's chunks, bugs, test cards, environments, or metrics just by
supplying that tenant's UUID. require_tenant_access is a router-level
FastAPI dependency: identity comes from the X-API-Key header (hashed and
looked up), and the URL's tenant_id is only accepted if it matches the
tenant that key actually belongs to.
"""
from __future__ import annotations

import hashlib
import secrets

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.db.models import Tenant
from backend.src.db.session import get_session


def generate_api_key() -> str:
    """A fresh, high-entropy key -- shown to the caller once, never stored
    in plaintext."""
    return secrets.token_urlsafe(32)


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def require_tenant_access(
    request: Request,
    tenant_id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    session: AsyncSession = Depends(get_session),
) -> str:
    """Resolves the caller's tenant from a credential -- NOT from the URL --
    then checks that resolved tenant against the URL's tenant_id. This
    ordering matters: authentication must derive identity from the
    credential, not from a client-supplied value that's merely compared
    against it.

    Two credentials are accepted: X-API-Key (machine clients: CI, scripts) or
    the browser login session cookie (the web UI; see auth/user_session.py).
    A present API key is authoritative -- it is never silently ignored in
    favour of a cookie."""
    if x_api_key is not None:
        key_hash = hash_api_key(x_api_key)
        resolved_id = await session.scalar(
            select(Tenant.id).where(Tenant.api_key_hash == key_hash)
        )
        if resolved_id is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        if str(resolved_id) != tenant_id:
            raise HTTPException(
                status_code=403,
                detail="API key does not grant access to this tenant_id",
            )
        return tenant_id

    from backend.src.auth import user_session
    from backend.src.config import settings

    loaded = await user_session.load_session(
        session, request.cookies.get(settings.session_cookie_name)
    )
    if loaded is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    auth_session, user = loaded
    if str(auth_session.tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Session does not grant access to this tenant_id")
    if request.method not in user_session.SAFE_METHODS:
        if not user_session.origin_allowed(request.headers.get("origin")):
            raise HTTPException(status_code=403, detail="Origin not allowed")
        if not user_session.csrf_valid(auth_session.csrf_token, x_csrf_token):
            raise HTTPException(status_code=403, detail="Missing or invalid CSRF token")
    request.state.user_email = user.email
    request.state.user_id = str(user.id)
    return tenant_id
