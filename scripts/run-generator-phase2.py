"""
Generator Phase 2 spike driver: generate a TypeScript Playwright test for
TC-DISCOUNT-001 using the verified page-object registry from Phase 1, via the
real LLM (Anthropic, through litellm).
"""
import asyncio
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from backend.src.db.session import async_session_factory
from backend.src.db.models import TestCard
from backend.src.agents.generator.app_model import AppModelRegistry
from backend.src.agents.generator.codegen import generate_test_file, safe_filename

TENANT_ID = "00000000-0000-0000-0000-000000000001"
TEST_ID = "TC-DISCOUNT-001"

REGISTRY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "backend", "evals", "golden", "app_model_registry.json"
)
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "test-scaffold", "tests")


async def main():
    async with async_session_factory() as session:
        card = await session.scalar(
            select(TestCard).where(TestCard.test_id == TEST_ID)
        )
        if not card:
            raise SystemExit(f"Test card {TEST_ID} not found — run scripts/seed-demo-test-card.py first")

        test_card_dict = {
            "test_id": card.test_id,
            "title": card.title,
            "description": card.description,
            "preconditions": card.preconditions,
            "setup_manifest": card.setup_manifest,
            "test_type": card.test_type,
            "priority": card.priority,
            "source_logical_id": None,
        }

    with open(REGISTRY_PATH) as f:
        registry = AppModelRegistry.from_dict(json.load(f))

    code = await generate_test_file(test_card_dict, registry, tenant_id=TENANT_ID)

    filename = safe_filename(card.test_id, card.title)
    out_path = os.path.join(OUTPUT_DIR, filename)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(code)

    print(f"Generated test -> {out_path}\n")
    print("─" * 80)
    print(code)


if __name__ == "__main__":
    asyncio.run(main())
