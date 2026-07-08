"""Generator API — turn an approved test card into a real Playwright test file.

Phase 2 only (codegen against an existing page-object registry). Phase 1
(building that registry via a live Playwright session against staging) has
no API endpoint yet either — it's only ever been run via
scripts/run-generator-phase2*.py's hardcoded registry path. Wiring Phase 1
into the API is a separate, bigger gap (needs live browser session handling
inside a request, timeout management) left for later.
"""
from __future__ import annotations

import json
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.db.models import TestCard
from backend.src.db.session import get_session

router = APIRouter(prefix="/generator", tags=["generator"])

_REGISTRY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "evals", "golden", "app_model_registry.json"
)
_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "test-scaffold", "tests")


def _infer_locator_strategy(code: str) -> str:
    """Worst-case strategy actually present in the generated file — a raw
    CSS fallback anywhere in the file makes the whole test that fragile,
    regardless of how many other locators used the preferred role-based
    approach."""
    if "page.locator(" in code:
        return "css_warned"
    if "getByTestId(" in code:
        return "testid"
    return "role"


@router.post("/{tenant_id}/cards/{card_id}/generate")
async def generate_card_test(
    tenant_id: str,
    card_id: str,
    session: AsyncSession = Depends(get_session),
):
    from backend.src.agents.generator.app_model import AppModelRegistry
    from backend.src.agents.generator.codegen import generate_test_file, safe_filename
    from sqlalchemy import update

    card = await session.get(TestCard, uuid.UUID(card_id))
    if card is None or str(card.tenant_id) != tenant_id:
        raise HTTPException(status_code=404, detail="Test card not found")
    if card.approval_status != "approved":
        raise HTTPException(
            status_code=400,
            detail=f"Test card must be approved before generation (status: {card.approval_status})",
        )

    if not os.path.exists(_REGISTRY_PATH):
        raise HTTPException(
            status_code=503,
            detail="No page-object registry found — run Generator Phase 1 first",
        )
    with open(_REGISTRY_PATH) as f:
        registry = AppModelRegistry.from_dict(json.load(f))

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

    code = await generate_test_file(test_card_dict, registry, tenant_id=tenant_id)
    locator_strategy = _infer_locator_strategy(code)

    filename = safe_filename(card.test_id, card.title)
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(_OUTPUT_DIR, filename)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(code)

    relative_path = os.path.join("test-scaffold", "tests", filename)
    await session.execute(
        update(TestCard)
        .where(TestCard.id == uuid.UUID(card_id))
        .values(playwright_code_path=relative_path, locator_strategy=locator_strategy)
    )
    await session.commit()

    return {
        "playwright_code_path": relative_path,
        "locator_strategy": locator_strategy,
        "code": code,
    }
