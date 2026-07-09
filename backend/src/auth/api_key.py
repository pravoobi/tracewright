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

from fastapi import Depends, Header, HTTPException
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
    tenant_id: str,
    x_api_key: str = Header(..., alias="X-API-Key"),
    session: AsyncSession = Depends(get_session),
) -> str:
    """Resolves the caller's tenant from the API key -- NOT from the URL --
    then checks that resolved tenant against the URL's tenant_id. This
    ordering matters: authentication must derive identity from the
    credential, not from a client-supplied value that's merely compared
    against it."""
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
