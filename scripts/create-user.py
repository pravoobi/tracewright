"""Create (or reset the password of) a web-UI user.

Usage: uv run --project backend python scripts/create-user.py <tenant_id> <email> [--role reviewer|admin]
The password is read from the TRACEWRIGHT_PASSWORD env var, or prompted for
(not echoed). Minimum 12 characters. Never pass it as an argument.
"""
import asyncio
import getpass
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select

from backend.src.auth.user_session import hash_password
from backend.src.db.models import Tenant, User
from backend.src.db.session import async_session_factory


async def main(tenant_id: str, email: str, role: str) -> None:
    password = os.environ.get("TRACEWRIGHT_PASSWORD") or getpass.getpass("Password: ")
    pw_hash = hash_password(password)  # raises on < 12 chars
    email = email.strip().lower()
    async with async_session_factory() as session:
        if await session.get(Tenant, uuid.UUID(tenant_id)) is None:
            raise SystemExit(f"No tenant {tenant_id}")
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            session.add(User(tenant_id=uuid.UUID(tenant_id), email=email, password_hash=pw_hash, role=role))
            action = "created"
        else:
            if str(user.tenant_id) != tenant_id:
                raise SystemExit("That email belongs to a different tenant")
            user.password_hash, user.role, user.is_active = pw_hash, role, True
            action = "updated"
        await session.commit()
    print(f"User {email} {action} for tenant {tenant_id}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    role = sys.argv[sys.argv.index("--role") + 1] if "--role" in sys.argv else "reviewer"
    if "--role" in sys.argv:
        args.remove(role)
    if len(args) != 2:
        raise SystemExit(__doc__)
    asyncio.run(main(args[0], args[1], role))
