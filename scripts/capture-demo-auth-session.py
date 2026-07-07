"""
Capture an auth session for the demo-app's simple email/password login.

`auth_capture.sessions.capture_session()` is built for real staging apps behind
SSO — headed browser + blocking terminal input() for a human to log in manually.
The demo-app's login is a trivial form, so this script logs in programmatically
via Playwright and reuses the same encrypt/upload helpers so the resulting file
is loadable by the existing, unmodified `load_session()`.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from playwright.async_api import async_playwright
from backend.src.auth_capture.sessions import _encrypt
from backend.src.storage.files import upload_file, auth_session_path

TENANT_ID = "00000000-0000-0000-0000-000000000001"
ENVIRONMENT_ID = "7bd54680-c9f8-495a-9ae9-e16bca0e5b0a"
DEMO_APP_URL = "http://localhost:4000"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"{DEMO_APP_URL}/login")
        await page.get_by_label("Email").fill("test@example.com")
        await page.get_by_label("Password").fill("password123")
        await page.get_by_role("button", name="Log in").click()
        await page.wait_for_url(f"{DEMO_APP_URL}/cart")

        storage_state = await page.context.storage_state()
        await browser.close()

    import json
    raw = json.dumps(storage_state).encode()
    encrypted = _encrypt(raw)

    path = auth_session_path(TENANT_ID, ENVIRONMENT_ID)
    upload_file(path, encrypted, content_type="application/octet-stream")
    print(f"Captured + encrypted auth session -> {path}")


if __name__ == "__main__":
    asyncio.run(main())
