"""Browser login: POST /auth/login, POST /auth/logout, GET /auth/me.

These routes are deliberately NOT behind require_tenant_access -- they are how
a browser obtains a session in the first place.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.auth import user_session
from backend.src.config import settings
from backend.src.db.session import get_session

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=1024)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _set_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_absolute_hours * 3600,
        httponly=True,  # never readable from JavaScript
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def _identity(user, auth_session) -> dict:
    return {
        "user": {"id": str(user.id), "email": user.email, "role": user.role},
        "tenant_id": str(user.tenant_id),
        "csrf_token": auth_session.csrf_token,
    }


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    # A cross-site page must not be able to log a victim into the attacker's account.
    if not user_session.origin_allowed(request.headers.get("origin")):
        raise HTTPException(status_code=403, detail="Origin not allowed")

    email, ip = body.email.strip().lower(), _client_ip(request)
    if await user_session.login_throttled_shared(email, ip):
        raise HTTPException(status_code=429, detail="Too many failed attempts; try again later")

    user = await user_session.authenticate(session, email, body.password)
    if user is None:
        await user_session.record_login_failure_shared(email, ip)
        # Same message for unknown account, wrong password and disabled account.
        raise HTTPException(status_code=401, detail="Invalid email or password")

    await user_session.clear_login_failures_shared(email, ip)
    raw, auth_session = await user_session.create_session(session, user)
    _set_cookie(response, raw)
    return _identity(user, auth_session)


@router.get("/me")
async def me(request: Request, session: AsyncSession = Depends(get_session)):
    loaded = await user_session.load_session(
        session, request.cookies.get(settings.session_cookie_name)
    )
    if loaded is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    auth_session, user = loaded
    return _identity(user, auth_session)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    loaded = await user_session.load_session(
        session, request.cookies.get(settings.session_cookie_name)
    )
    if loaded is not None:
        auth_session, _ = loaded
        # Logout is state-changing and cookie-authenticated: same CSRF rules.
        if not user_session.origin_allowed(request.headers.get("origin")):
            raise HTTPException(status_code=403, detail="Origin not allowed")
        if not user_session.csrf_valid(auth_session.csrf_token, request.headers.get("x-csrf-token")):
            raise HTTPException(status_code=403, detail="Missing or invalid CSRF token")
        await user_session.revoke_session(session, request.cookies.get(settings.session_cookie_name))
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"status": "logged_out"}
