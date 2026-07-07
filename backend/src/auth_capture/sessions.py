"""Auth session capture: guided Playwright login → encrypted storage state per environment."""
from __future__ import annotations

import base64
import json
import os

import structlog
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from backend.src.config import settings
from backend.src.storage.files import auth_session_path, download_file, upload_file

log = structlog.get_logger()


def _get_key() -> bytes:
    raw = settings.auth_session_encryption_key
    if not raw or raw == "CHANGE_ME_generate_with_secrets_module":
        raise ValueError(
            "AUTH_SESSION_ENCRYPTION_KEY is not set. "
            "Generate with: python -c \"import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())\""
        )
    return base64.b64decode(raw)


def _encrypt(data: bytes) -> bytes:
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, data, None)
    return nonce + ct


def _decrypt(data: bytes) -> bytes:
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce, ct = data[:12], data[12:]
    return aesgcm.decrypt(nonce, ct, None)


async def capture_session(
    tenant_id: str,
    environment_id: str,
    staging_url: str,
) -> str:
    """
    Launch an interactive Playwright browser session for one-time login.
    Persists encrypted storage state to MinIO. Returns the storage path.
    This is called once per environment; the storage state is reused by the Generator.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(staging_url)

        log.info(
            "auth_capture.waiting_for_login",
            environment_id=environment_id,
            url=staging_url,
        )
        print(
            f"\n[AUTH CAPTURE] Browser opened at {staging_url}.\n"
            "Log in manually, then press Enter in this terminal to capture the session."
        )
        input()

        storage_state = await context.storage_state()
        await browser.close()

    raw = json.dumps(storage_state).encode()
    encrypted = _encrypt(raw)

    path = auth_session_path(tenant_id, environment_id)
    upload_file(path, encrypted, content_type="application/octet-stream")

    log.info("auth_capture.saved", environment_id=environment_id, path=path)
    return path


def load_session(tenant_id: str, environment_id: str) -> dict:
    """Download and decrypt storage state for use by the Generator."""
    path = auth_session_path(tenant_id, environment_id)
    encrypted = download_file(path)
    raw = _decrypt(encrypted)
    return json.loads(raw.decode())
