"""
Auth-capture spike — the REAL flow, unmodified.

Unlike scripts/capture-demo-auth-session.py (which reuses sessions.py's
crypto/upload helpers but drives the login form itself, headlessly, for the
Generator spike), this calls auth_capture.sessions.capture_session()
directly: it opens a real, visible Chromium window, waits for a human to
log in manually, then captures + encrypts + persists the storage state.

Must be run from an interactive terminal — it blocks on input().
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.src.auth_capture.sessions import capture_session

TENANT_ID = "00000000-0000-0000-0000-000000000001"
ENVIRONMENT_ID = "7bd54680-c9f8-495a-9ae9-e16bca0e5b0a"
DEMO_APP_LOGIN_URL = "http://localhost:4000/login"


async def main():
    path = await capture_session(TENANT_ID, ENVIRONMENT_ID, DEMO_APP_LOGIN_URL)
    print(f"\nDone. Encrypted storage state saved to: {path}")


if __name__ == "__main__":
    asyncio.run(main())
