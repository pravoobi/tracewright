"""Decrypt the captured demo-app auth session to a local file for Playwright's storageState."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.src.auth_capture.sessions import load_session

TENANT_ID = "00000000-0000-0000-0000-000000000001"
ENVIRONMENT_ID = "7bd54680-c9f8-495a-9ae9-e16bca0e5b0a"

OUT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "test-scaffold", ".auth", "demo-app.json"
)


def main():
    state = load_session(TENANT_ID, ENVIRONMENT_ID)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(state, f, indent=2)
    print(f"Exported storage state -> {OUT_PATH}")


if __name__ == "__main__":
    main()
