"""Recompute test_cards.locator_strategy from the generated spec files and the
CURRENT page-object registry -- no LLM, no file rewrites.

locator_strategy is stamped when a card's code is generated, so it goes stale
when the registry improves (e.g. css locators replaced by data-testid ones).

Usage: uv run python scripts/refresh-locator-strategies.py [--dry-run]
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")
from sqlalchemy import select

from backend.src.api.generator import _infer_locator_strategy, _load_registry
from backend.src.db.models import TestCard
from backend.src.db.session import async_session_factory

TENANT_ID = "00000000-0000-0000-0000-000000000001"


async def main(dry_run: bool) -> None:
    async with async_session_factory() as session:
        registry = await _load_registry(TENANT_ID, session)
        if registry is None:
            raise SystemExit("no registry")
        cards = (
            await session.scalars(
                select(TestCard).where(
                    TestCard.tenant_id == TENANT_ID, TestCard.playwright_code_path.isnot(None)
                )
            )
        ).all()
        for c in cards:
            path = Path(c.playwright_code_path.replace("\\", "/"))
            if not path.exists():
                print(f"{c.test_id}: spec missing ({path}), skipped")
                continue
            new = _infer_locator_strategy(path.read_text(encoding="utf-8"), registry)
            print(f"{c.test_id}: {c.locator_strategy} -> {new}")
            if not dry_run:
                c.locator_strategy = new
        if not dry_run:
            await session.commit()


asyncio.run(main("--dry-run" in sys.argv))
