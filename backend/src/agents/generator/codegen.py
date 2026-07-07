"""Generator Phase 2: TypeScript Playwright test generation with verified locators."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import structlog

from backend.src.agents.generator.app_model import AppModelRegistry
from backend.src.config import settings
from backend.src.llm.client import complete

log = structlog.get_logger()

_CODEGEN_SYSTEM = """You are an expert Playwright TypeScript test author.
Given a test card, page-object registry, and fixture context, generate a complete Playwright test file.

Rules:
- Use ONLY locators from the provided page-object registry — never invent locators.
- Each page object in the registry has a `url_pattern: string` property holding its URL.
  To navigate to a page, use exactly `await page.goto(pageObject.url_pattern)`. Do NOT
  invent a different property name (e.g. `.url`) — it does not exist on the page-object
  classes and will fail to compile.
- Follow Page Object Model (POM) pattern.
- Import from the shared page-objects directory.
- If the test card's preconditions require an authenticated user (most do), import
  `test` and `expect` from `../fixtures/authenticated-cart.fixture` — NOT from
  `@playwright/test` directly. That fixture overrides Playwright's `storageState`
  option with a pre-captured logged-in session; importing from `@playwright/test`
  instead runs the test unauthenticated and every request redirects to the login
  page, causing every subsequent locator wait to time out.
- Each test file starts with metadata comments linking to the test card ID and source artifacts.
- Use TypeScript with strict types.
- Use async/await throughout.
- Never use page.waitForTimeout — use proper wait conditions instead.
- Include a clear // Verify: comment before every assertion explaining what business outcome it checks.

Respond with the raw TypeScript file content only — no markdown fences."""


async def generate_test_file(
    test_card: dict[str, Any],
    registry: AppModelRegistry,
    tenant_id: str,
) -> str:
    """Generate a TypeScript Playwright test file for one approved test card."""
    registry_json = json.dumps(registry.to_dict(), indent=2)
    card_json = json.dumps(test_card, indent=2)

    prompt = (
        f"Test card:\n{card_json}\n\n"
        f"Page-object registry (verified locators only):\n{registry_json}\n\n"
        f"Generate the test file."
    )

    code = await complete(
        messages=[{"role": "user", "content": prompt}],
        model=settings.planner_model,
        tenant_id=tenant_id,
        feature="codegen",
        system=_CODEGEN_SYSTEM,
        max_tokens=4096,
    )

    # Prepend mandatory metadata header
    header = _build_metadata_header(test_card)
    return header + "\n\n" + code


def _build_metadata_header(card: dict[str, Any]) -> str:
    lines = [
        "// ─── AI Test Agent — Generated Test ───────────────────────────────────────",
        f"// Test Card ID : {card.get('test_id', 'unknown')}",
        f"// Title        : {card.get('title', '')}",
        f"// Source AC    : {card.get('source_logical_id', 'N/A')}",
        f"// Priority     : {card.get('priority', '')}",
        f"// Type         : {card.get('test_type', '')}",
        "// ─────────────────────────────────────────────────────────────────────────",
        "// DO NOT EDIT locators manually — regenerate via the AI test agent.",
    ]
    return "\n".join(lines)


def safe_filename(test_id: str, title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title.lower()).strip().replace(" ", "-")[:40]
    return f"{test_id.lower()}-{slug}.spec.ts"
