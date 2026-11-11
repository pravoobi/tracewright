"""Generator Phase 1 input: derive `test_card_flows` from approved test cards.

Grounded, not guessed: the live app is crawled first (same origin only, with
the environment's auth session) and each page's accessibility snapshot is
captured. The LLM then only *selects* which of those real elements the
approved cards need and gives them semantic names. Every element it returns is
still re-verified by `find_verified_locator` in build_app_model, so a bad
choice becomes an unresolved locator, never an emitted one.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urldefrag, urljoin

import structlog

from backend.src.agents.generator.app_model import _origin, restrict_to_origin
from backend.src.auth_capture.sessions import load_session
from backend.src.config import settings
from backend.src.llm.client import complete, extract_json_object

log = structlog.get_logger()

_PAGE_NAME = re.compile(r"[A-Z][A-Za-z0-9]{0,40}Page")
_SEMANTIC_NAME = re.compile(r"[a-z][A-Za-z0-9]{0,50}")
_ROLES = {
    "button", "link", "textbox", "checkbox", "radio", "combobox", "spinbutton",
    "heading", "alert", "status", "listitem", "row", "cell", "table", "img", "term", "definition",
}
MAX_PAGES = 8
MAX_ELEMENTS_PER_PAGE = 30
_SNAPSHOT_CHARS = 6000

_SYSTEM = """You pick which UI elements a Playwright test suite needs.
You are given approved test cards and, for each real page of the app, its
accessibility snapshot. Choose elements ONLY from those snapshots: use the
exact role and accessible name shown there. Never invent an element or a page.

Return one JSON object:
{"pages": [{"page_name": "CartPage", "url": "<one of the given page URLs>",
  "elements": [{"semantic_name": "orderTotal", "description": "...",
                "role": "<aria role>", "name": "<exact accessible name or null>",
                "testid": "<data-testid if visible in the snapshot, else null>"}]}]}
Rules: page_name is PascalCase ending in "Page"; semantic_name is camelCase; one entry per page.
Include EVERY element the cards' steps interact with or assert on (inputs, buttons, totals, messages);
for elements with no useful role/name use the data-testid listed under the snapshot (role null).
Also include every other interactive control (inputs, buttons) and every data-testid element on a
page you list, since page objects are shared across tests. Omit pages no card touches.
Only list elements present in the snapshot; skip unnamed non-unique ones (e.g. a bare definition)."""


async def crawl_pages(
    tenant_id: str, environment_id: str, base_url: str, max_pages: int = MAX_PAGES
) -> list[dict[str, str]]:
    """Breadth-first walk of same-origin links from base_url. Returns
    [{"url", "snapshot"}]. Redirect/cross-origin navigation is blocked by
    restrict_to_origin, same as Phase 1."""
    from playwright.async_api import async_playwright

    storage_state = load_session(tenant_id, environment_id)
    origin = _origin(base_url)
    seen: set[str] = set()
    queue = [base_url]
    pages: list[dict[str, str]] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=storage_state)
        await restrict_to_origin(context, base_url)
        try:
            while queue and len(pages) < max_pages:
                url = urldefrag(queue.pop(0))[0]
                if url in seen:
                    continue
                seen.add(url)
                page = await context.new_page()
                try:
                    resp = await page.goto(url, wait_until="networkidle")
                    if resp is None or resp.status >= 400:
                        continue
                    final = urldefrag(page.url)[0]
                    if _origin(final) != origin:
                        continue
                    seen.add(final)
                    snapshot = await page.locator("body").aria_snapshot()
                    # The accessibility tree omits data-testid, which is the
                    # fallback for elements with no role/name (totals, messages).
                    testids = await page.eval_on_selector_all(
                        "[data-testid]",
                        "els => els.map(e => [e.getAttribute('data-testid'), (e.textContent || '').trim().slice(0, 60)])",
                    )
                    if testids:
                        listing = "\n".join(
                            f"- {tid}: {txt!r}" for tid, txt in testids[:MAX_ELEMENTS_PER_PAGE]
                        )
                        snapshot += f"\n\nElements with data-testid (testid: current text):\n{listing}"
                    pages.append({"url": final, "snapshot": snapshot[:_SNAPSHOT_CHARS]})
                    hrefs = await page.eval_on_selector_all(
                        "a[href]", "els => els.map(e => e.getAttribute('href'))"
                    )
                    for href in hrefs:
                        target = urldefrag(urljoin(final, href or ""))[0]
                        if _origin(target) == origin and target not in seen:
                            queue.append(target)
                except Exception as e:  # unreachable page: skip, don't fail the crawl
                    log.warning("flows.crawl_page_failed", url=url, error=str(e))
                finally:
                    await page.close()
        finally:
            await browser.close()
    return pages


def validate_flows(raw: Any, pages: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Keep only well-formed flows on crawled URLs (LLM output is untrusted:
    it may be steered by text inside an uploaded requirements document)."""
    known = {p["url"] for p in pages}
    flows: dict[str, dict[str, Any]] = {}
    for entry in (raw.get("pages") if isinstance(raw, dict) else None) or []:
        if not isinstance(entry, dict):
            continue
        name, url = entry.get("page_name"), entry.get("url")
        if not (isinstance(name, str) and _PAGE_NAME.fullmatch(name)):
            continue
        if not (isinstance(url, str) and urldefrag(url)[0] in known):
            continue
        flow = flows.setdefault(name, {"page_name": name, "url": urldefrag(url)[0], "elements": []})
        for el in entry.get("elements") or []:
            if not isinstance(el, dict):
                continue
            sem = el.get("semantic_name")
            role, ename, testid = el.get("role"), el.get("name"), el.get("testid")
            if not (isinstance(sem, str) and _SEMANTIC_NAME.fullmatch(sem)):
                continue
            if role is not None and role not in _ROLES:
                if not (isinstance(testid, str) and testid):
                    continue
                role = None  # unusable role, but the testid can still resolve it
            if not (role or testid):
                continue
            if len(flow["elements"]) >= MAX_ELEMENTS_PER_PAGE:
                break
            flow["elements"].append(
                {
                    "semantic_name": sem,
                    "description": str(el.get("description") or sem)[:200],
                    "role": role,
                    "name": ename if isinstance(ename, str) else None,
                    "testid": testid if isinstance(testid, str) else None,
                }
            )
    return [f for f in flows.values() if f["elements"]]


async def derive_flows(
    tenant_id: str,
    environment_id: str,
    base_url: str,
    cards: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pages = await crawl_pages(tenant_id, environment_id, base_url)
    if not pages or not cards:
        return []
    card_text = "\n\n".join(
        f"[{c['test_id']}] {c['title']}\nPreconditions: {c.get('preconditions') or ''}\n{c['description']}"
        for c in cards
    )
    page_text = "\n\n".join(f"PAGE {p['url']}\n{p['snapshot']}" for p in pages)
    raw = await complete(
        messages=[{"role": "user", "content": f"Approved test cards:\n{card_text}\n\nApp pages:\n{page_text}"}],
        model=settings.planner_model,
        tenant_id=tenant_id,
        feature="derive_flows",
        system=_SYSTEM,
        max_tokens=4096,
    )
    flows = validate_flows(extract_json_object(raw), pages)
    log.info("flows.derived", pages=[f["page_name"] for f in flows], crawled=len(pages))
    return flows
