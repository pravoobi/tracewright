"""Seed an `environments` row for the local demo-app (Generator spike target)."""
import asyncio
import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from backend.src.db.session import async_session_factory
from backend.src.db.models import Environment

TENANT_ID = "00000000-0000-0000-0000-000000000001"
ENV_NAME = "demo-app"
ENV_URL = "http://localhost:4000"


async def seed():
    async with async_session_factory() as session:
        existing = await session.scalar(
            select(Environment).where(
                Environment.tenant_id == uuid.UUID(TENANT_ID),
                Environment.name == ENV_NAME,
            )
        )
        if existing:
            print(f"Environment '{ENV_NAME}' already exists id={existing.id}")
            return

        env = Environment(
            tenant_id=uuid.UUID(TENANT_ID),
            name=ENV_NAME,
            url=ENV_URL,
            code_version="1.0",
            doc_version="1.1",
        )
        session.add(env)
        await session.commit()
        print(f"Created environment '{ENV_NAME}' id={env.id}")


if __name__ == "__main__":
    asyncio.run(seed())
