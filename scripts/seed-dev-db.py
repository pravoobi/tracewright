"""Seed dev DB with a default tenant for local development."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.src.db.session import async_session_factory
from backend.src.db.models import Tenant

TENANT_ID = "00000000-0000-0000-0000-000000000001"
TENANT_NAME = "dev-tenant"


async def seed():
    async with async_session_factory() as session:
        existing = await session.get(Tenant, TENANT_ID)
        if existing:
            print(f"Tenant '{TENANT_NAME}' already exists.")
            return
        import uuid
        tenant = Tenant(
            id=uuid.UUID(TENANT_ID),
            name=TENANT_NAME,
            version_ordering=["1.0", "1.1", "2.0", "2.1"],
        )
        session.add(tenant)
        await session.commit()
        print(f"Created tenant '{TENANT_NAME}' id={TENANT_ID}")


if __name__ == "__main__":
    asyncio.run(seed())
