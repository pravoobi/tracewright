"""Generate (or rotate) an API key for a tenant. Prints the RAW key once --
only its hash is stored, so this is the only time it's ever visible.

Usage: uv run --project backend python scripts/generate-tenant-api-key.py <tenant_id>
"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import update

from backend.src.auth.api_key import generate_api_key, hash_api_key
from backend.src.db.models import Tenant
from backend.src.db.session import async_session_factory


async def main(tenant_id: str) -> None:
    raw_key = generate_api_key()
    async with async_session_factory() as session:
        result = await session.execute(
            update(Tenant)
            .where(Tenant.id == uuid.UUID(tenant_id))
            .values(api_key_hash=hash_api_key(raw_key))
        )
        await session.commit()
        if result.rowcount == 0:
            print(f"No tenant found with id {tenant_id}")
            raise SystemExit(1)

    print(f"API key for tenant {tenant_id} (shown once, not recoverable):\n\n  {raw_key}\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: generate-tenant-api-key.py <tenant_id>")
        raise SystemExit(1)
    asyncio.run(main(sys.argv[1]))
