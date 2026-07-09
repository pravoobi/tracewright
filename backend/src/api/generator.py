"""Generator API — build the page-object registry (Phase 1) and turn an
approved test card into a real Playwright test file (Phase 2).

Phase 1 walks flows via a live Playwright session against the environment's
staging URL, verifying every locator before it's recorded (never emit an
unverified locator). The caller supplies which pages/elements to walk
(test_card_flows) — deriving that automatically from approved test cards'
descriptions would need its own LLM-based flow-extraction step; V1 keeps
that explicit rather than guessing.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any, TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException
from minio.error import S3Error
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.auth.api_key import require_tenant_access
from backend.src.db.models import Environment, TestCard
from backend.src.db.session import get_session

if TYPE_CHECKING:
    from backend.src.agents.generator.app_model import AppModelRegistry

router = APIRouter(
    prefix="/generator",
    tags=["generator"],
    dependencies=[Depends(require_tenant_access)],
)

# Fallback registry for the existing demo/eval setup, which predates
# per-environment MinIO storage — the new build-registry endpoint always
# writes to MinIO; this local file is only read if nothing's there yet.
_FALLBACK_REGISTRY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "evals", "golden", "app_model_registry.json"
)
_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "test-scaffold", "tests")

_STRATEGY_RANK = {"role": 0, "testid": 1, "css_warned": 2}


def _referenced_page_properties(code: str) -> list[tuple[str, str]]:
    """All (class_name, property_name) pairs a generated test actually
    references through the Page Object Model — `const cartPage = new
    CartPage(page);` maps the variable to its class, then every
    `cartPage.<property>` access is one reference. Shared by both
    locator-strategy inference and suggestion collection below, since both
    need the exact same "what does this test actually touch" answer."""
    var_to_class = dict(re.findall(r"const\s+(\w+)\s*=\s*new\s+(\w+)\s*\(", code))
    refs: list[tuple[str, str]] = []
    for var_name, class_name in var_to_class.items():
        for prop_name in re.findall(rf"\b{re.escape(var_name)}\.(\w+)", code):
            refs.append((class_name, prop_name))
    return refs


def _infer_locator_strategy(code: str, registry: "AppModelRegistry") -> str:
    """Worst-case locator strategy actually used by the generated test.

    Following the Page Object Model (CLAUDE.md's mandated pattern), a test
    virtually never calls page.getByRole/getByTestId/locator directly —
    it calls `cartPage.orderTotal`, and the REAL locator lives inside the
    page-object CLASS (test-scaffold/page-objects/CartPage.ts), not the
    test body. Scanning only the test file's own code (the original,
    incorrect version of this function) means the "role" fallback fires
    for every POM-based test regardless of what its page objects actually
    resolve to — confirmed wrong in practice: CartPage.ts's `orderTotal`
    and `discountSummary` are both real css_warned locators, yet every
    test referencing them was silently tagged "role".
    """
    worst = "role"

    def consider(strategy: str | None) -> None:
        nonlocal worst
        if strategy and _STRATEGY_RANK.get(strategy, 0) > _STRATEGY_RANK[worst]:
            worst = strategy

    # Locators inlined directly in the test body (not the intended
    # pattern, but a test could bypass the page-object layer)
    if "page.locator(" in code:
        consider("css_warned")
    if "getByTestId(" in code:
        consider("testid")

    # Locators referenced through a page object — the actual, intended
    # pattern.
    for class_name, prop_name in _referenced_page_properties(code):
        page_obj = registry.pages.get(class_name)
        if page_obj is not None:
            consider(page_obj.locator_strategies.get(prop_name))

    return worst


def _collect_suggestions(code: str, registry: "AppModelRegistry") -> list[str]:
    """CLAUDE.md's "recommend adding data-testid to element X" — collected
    for whichever page-object properties this specific test actually
    references, deduped, in first-seen order. Was produced by
    find_verified_locator() since day one but never captured past that
    point until app_model.py started storing it on the registry."""
    suggestions: list[str] = []
    for class_name, prop_name in _referenced_page_properties(code):
        page_obj = registry.pages.get(class_name)
        if page_obj is None:
            continue
        suggestion = page_obj.suggestions.get(prop_name)
        if suggestion and suggestion not in suggestions:
            suggestions.append(suggestion)
    return suggestions


class BuildRegistryRequest(BaseModel):
    test_card_flows: list[dict[str, Any]]


@router.post("/{tenant_id}/environments/{environment_id}/build-registry")
async def build_registry(
    tenant_id: str,
    environment_id: str,
    body: BuildRegistryRequest,
    session: AsyncSession = Depends(get_session),
):
    """Phase 1: walk the given flows against the live environment, verifying
    every locator, and persist the resulting page-object registry."""
    from urllib.parse import urlparse

    from backend.src.agents.generator.app_model import build_app_model
    from backend.src.storage.files import registry_path, upload_file

    env = await session.get(Environment, uuid.UUID(environment_id))
    if env is None or str(env.tenant_id) != tenant_id:
        raise HTTPException(status_code=404, detail="Environment not found")
    if not env.url:
        raise HTTPException(status_code=400, detail="Environment has no URL configured")

    # This endpoint drives a server-side Playwright browser, loaded with the
    # environment's decrypted auth cookies, to whatever URL a flow gives it.
    # Without this check, a caller could point that authenticated browser at
    # any internal/intranet/metadata URL via test_card_flows, independent of
    # what the environment is actually registered for (SSRF). Every flow's
    # URL must share the environment's own registered origin -- the one
    # thing the customer actually vetted when they set up the environment.
    env_origin = urlparse(env.url)
    for flow in body.test_card_flows:
        flow_url = flow.get("url")
        if not flow_url:
            continue
        flow_origin = urlparse(flow_url)
        if (flow_origin.scheme, flow_origin.netloc) != (env_origin.scheme, env_origin.netloc):
            raise HTTPException(
                status_code=400,
                detail=f"Flow URL '{flow_url}' is not on the environment's registered origin",
            )

    registry = await build_app_model(
        tenant_id=tenant_id,
        environment_id=environment_id,
        staging_url=env.url,
        test_card_flows=body.test_card_flows,
    )

    data = registry.to_dict()
    requested = sum(len(f.get("elements", [])) for f in body.test_card_flows)
    resolved = sum(len(po["locators"]) for po in data.values())

    upload_file(
        registry_path(tenant_id, environment_id),
        json.dumps(data, indent=2).encode("utf-8"),
        content_type="application/json",
    )

    return {
        "pages": list(data.keys()),
        "locators_requested": requested,
        "locators_resolved": resolved,
        "registry": data,
    }


async def _load_registry(tenant_id: str, session: AsyncSession):
    from backend.src.agents.generator.app_model import AppModelRegistry
    from backend.src.storage.files import download_file, registry_path

    from sqlalchemy import select

    env_id = await session.scalar(
        select(Environment.id).where(Environment.tenant_id == uuid.UUID(tenant_id)).limit(1)
    )
    if env_id is not None:
        try:
            raw = download_file(registry_path(tenant_id, str(env_id)))
            return AppModelRegistry.from_dict(json.loads(raw))
        except S3Error:
            pass  # no registry built via the API yet for this environment

    if os.path.exists(_FALLBACK_REGISTRY_PATH):
        with open(_FALLBACK_REGISTRY_PATH) as f:
            return AppModelRegistry.from_dict(json.load(f))

    return None


@router.post("/{tenant_id}/cards/{card_id}/generate")
async def generate_card_test(
    tenant_id: str,
    card_id: str,
    session: AsyncSession = Depends(get_session),
):
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

    registry = await _load_registry(tenant_id, session)
    if registry is None:
        raise HTTPException(
            status_code=503,
            detail="No page-object registry found — run Generator Phase 1 first "
            "(POST /generator/{tenant_id}/environments/{environment_id}/build-registry)",
        )

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
    locator_strategy = _infer_locator_strategy(code, registry)
    locator_suggestions = _collect_suggestions(code, registry)

    filename = safe_filename(card.test_id, card.title)
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(_OUTPUT_DIR, filename)

    # Defense in depth on top of safe_filename's sanitization: refuse to
    # write anywhere outside the tests directory, in case some future
    # change to filename construction reintroduces a traversal path.
    resolved_dir = os.path.realpath(_OUTPUT_DIR)
    resolved_path = os.path.realpath(out_path)
    if os.path.commonpath([resolved_dir, resolved_path]) != resolved_dir:
        raise HTTPException(status_code=400, detail="Invalid generated filename")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(code)

    relative_path = os.path.join("test-scaffold", "tests", filename)
    await session.execute(
        update(TestCard)
        .where(TestCard.id == uuid.UUID(card_id))
        .values(
            playwright_code_path=relative_path,
            locator_strategy=locator_strategy,
            locator_suggestions=locator_suggestions,
        )
    )
    await session.commit()

    return {
        "playwright_code_path": relative_path,
        "locator_strategy": locator_strategy,
        "locator_suggestions": locator_suggestions,
        "code": code,
    }
