"""Auth session capture: guided Playwright login → encrypted storage state per environment."""
from __future__ import annotations

import base64
import json
import os

import structlog
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from backend.src.config import settings
from backend.src.storage.files import auth_session_path, download_file, upload_file

log = structlog.get_logger()


def _get_master_key() -> bytes:
    raw = settings.auth_session_encryption_key
    if not raw or raw == "CHANGE_ME_generate_with_secrets_module":
        raise ValueError(
            "AUTH_SESSION_ENCRYPTION_KEY is not set. "
            "Generate with: python -c \"import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())\""
        )
    return base64.b64decode(raw)


def _get_tenant_key(tenant_id: str) -> bytes:
    """CLAUDE.md promises per-tenant encryption for auth storage-state files
    as a stated compliance/sales point -- a single global key for every
    tenant meant one leaked key decrypted every tenant's session cookies,
    not just one. HKDF-derive a distinct 32-byte key per tenant from the one
    stored master key (info=tenant_id) rather than storing N keys: it's a
    one-way derivation, so recovering one tenant's key doesn't expose the
    master or any other tenant's key."""
    master = _get_master_key()
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=f"auth-session:{tenant_id}".encode(),
    )
    return hkdf.derive(master)


def _encrypt(data: bytes, tenant_id: str) -> bytes:
    key = _get_tenant_key(tenant_id)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, data, None)
    return nonce + ct


def _decrypt(data: bytes, tenant_id: str) -> bytes:
    key = _get_tenant_key(tenant_id)
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
    encrypted = _encrypt(raw, tenant_id)

    path = auth_session_path(tenant_id, environment_id)
    upload_file(path, encrypted, content_type="application/octet-stream")

    log.info("auth_capture.saved", environment_id=environment_id, path=path)
    return path


def _decrypt_legacy(data: bytes) -> bytes:
    """Files written before per-tenant keys were introduced were encrypted
    directly with the master key."""
    nonce, ct = data[:12], data[12:]
    return AESGCM(_get_master_key()).decrypt(nonce, ct, None)


def load_session(tenant_id: str, environment_id: str) -> dict:
    """Download and decrypt storage state for use by the Generator.

    Switching to HKDF-derived per-tenant keys made every storage-state file
    already in object storage undecryptable (AESGCM InvalidTag), forcing every
    customer to redo the interactive login. Fall back to the legacy master
    key and re-encrypt under the tenant key on first read, so existing
    sessions migrate transparently. A failure under BOTH keys is a real
    error (tampering, wrong key, or corruption) and is raised."""
    path = auth_session_path(tenant_id, environment_id)
    encrypted = download_file(path)
    try:
        raw = _decrypt(encrypted, tenant_id)
    except InvalidTag:
        raw = _decrypt_legacy(encrypted)  # raises InvalidTag if this fails too
        try:
            upload_file(path, _encrypt(raw, tenant_id), content_type="application/octet-stream")
            log.info("auth_capture.migrated_legacy_encryption", path=path)
        except Exception:
            log.warning("auth_capture.legacy_migration_failed", path=path, exc_info=True)
    return json.loads(raw.decode())
