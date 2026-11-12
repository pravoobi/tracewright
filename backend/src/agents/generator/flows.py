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
from backend.src.agents.generator.state_probe import (
    replay_steps,
    reset_environment_state,
    validate_probes,
)
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
An alert or status message has no accessible name of its own: give it role alert/status with name null
(it is matched by role alone), never its message text, which changes.
Only list elements present in the snapshot; skip unnamed non-unique ones (e.g. a bare definition).
Some snapshots are marked STATE <id> (the page after a few actions). An element visible ONLY in a
state snapshot (not in the plain page) must carry "state": "<that id>"; otherwise omit "state"."""

_PROBE_SYSTEM = """You plan short UI probes that reveal elements which only appear after an action
(confirmation summaries, validation or error messages). You are given approved test cards and the
real pages' accessibility snapshots. Return one JSON object:
{"probes": [{"state": "discountApplied", "url": "<one of the given page URLs>",
  "steps": [{"action": "fill", "role": "textbox", "name": "<exact accessible name>", "value": "<value>"},
            {"action": "click", "role": "button", "name": "<exact accessible name>"},
            {"action": "goto", "url": "<another given page URL>"}]}]}
Rules: state is camelCase; at most 6 steps per probe (url is where it starts; end with a goto step
when the state is shown on a DIFFERENT page, e.g. a summary on the checkout page after acting on the cart) and 6 probes; steps act on elements that exist in
that page's snapshot (role+name, or "testid" with role null); "fill" values must be quoted verbatim
from the test cards (e.g. a discount code a card names), or for an invalid-input case a plain
alphanumeric placeholder such as BOGUS123; include probes for the failure paths the cards
describe (invalid or duplicate input) as well as the success path. Be concise: no commentary,
only the JSON object. NEVER click anything that places an
order, pays, deletes, signs out or otherwise cannot be undone; the state you want is a message or summary
shown after a harmless action. Skip pages/cards where no such state is needed."""


async def _snapshot_with_testids(page) -> str:
    snapshot = await page.locator("body").aria_snapshot()
    # The accessibility tree omits data-testid, which is the fallback for
    # elements with no role/name (totals, messages).
    testids = await page.eval_on_selector_all(
        "[data-testid]",
        "els => els.map(e => [e.getAttribute('data-testid'), (e.textContent || '').trim().slice(0, 60)])",
    )
    if testids:
        listing = "\n".join(f"- {tid}: {txt!r}" for tid, txt in testids[:MAX_ELEMENTS_PER_PAGE])
        snapshot += f"\n\nElements with data-testid (testid: current text):\n{listing}"
    return snapshot[:_SNAPSHOT_CHARS]


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
                    snapshot = await _snapshot_with_testids(page)
                    pages.append({"url": final, "snapshot": snapshot})
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
    states = {p["state_id"]: p for p in pages if p.get("state_id")}
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
            element = {
                "semantic_name": sem,
                "description": str(el.get("description") or sem)[:200],
                "role": role,
                "name": ename if isinstance(ename, str) else None,
                "testid": testid if isinstance(testid, str) else None,
            }
            state = el.get("state")
            if state is not None:
                # The steps come from our own probe run, never from the LLM's
                # answer: it can only name a state, not write an action.
                known_state = states.get(state) if isinstance(state, str) else None
                if known_state is None or known_state["url"] != flow["url"]:
                    continue
                element["reach"] = known_state["reach"]
            flow["elements"].append(element)
    return [f for f in flows.values() if f["elements"]]


async def _run_probes(
    tenant_id: str,
    environment_id: str,
    base_url: str,
    probes: list[dict[str, Any]],
    known_urls: set[str],
    reset_path: str | None = None,
) -> list[dict[str, Any]]:
    """Replay each probe on a fresh page and snapshot the resulting state."""
    from playwright.async_api import async_playwright

    out: list[dict[str, Any]] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=load_session(tenant_id, environment_id))
        await restrict_to_origin(context, base_url)
        try:
            for probe in probes:
                await reset_environment_state(context, base_url, reset_path)
                page = await context.new_page()
                try:
                    if not await replay_steps(page, probe["steps"]):
                        continue
                    final = urldefrag(page.url)[0]
                    if final not in known_urls:
                        continue
                    out.append(
                        {
                            "url": final,
                            "state_id": probe["state_id"],
                            "reach": probe["steps"],
                            "snapshot": await _snapshot_with_testids(page),
                        }
                    )
                except Exception as e:
                    log.warning("flows.probe_failed", state=probe["state_id"], error=str(e)[:200])
                finally:
                    await page.close()
        finally:
            await browser.close()
    return out


def _describe_steps(steps: list[dict[str, Any]]) -> str:
    return "; ".join(
        f"{s['action']} {s.get('role') or 'testid'} {s.get('name') or s.get('testid')!r}"
        + (f" = {s['value']!r}" if s["action"] == "fill" else "")
        for s in steps
    )


async def derive_flows(
    tenant_id: str,
    environment_id: str,
    base_url: str,
    cards: list[dict[str, Any]],
    explore_states: bool = False,
    reset_path: str | None = None,
) -> list[dict[str, Any]]:
    pages = await crawl_pages(tenant_id, environment_id, base_url)
    if not pages or not cards:
        return []
    card_text = "\n\n".join(
        f"[{c['test_id']}] {c['title']}\nPreconditions: {c.get('preconditions') or ''}\n{c['description']}"
        for c in cards
    )
    page_text = "\n\n".join(f"PAGE {p['url']}\n{p['snapshot']}" for p in pages)

    if explore_states:
        states: list[dict[str, Any]] = []
        probes: list[dict[str, Any]] = []
        try:
            raw_plan = await complete(
                messages=[{"role": "user", "content": f"Approved test cards:\n{card_text}\n\nApp pages:\n{page_text}"}],
                model=settings.planner_model,
                tenant_id=tenant_id,
                feature="plan_state_probes",
                system=_PROBE_SYSTEM,
                max_tokens=4096,
            )
            probes = validate_probes(extract_json_object(raw_plan), pages, card_text)
            if probes:
                known_urls = {p["url"] for p in pages}
                states = await _run_probes(
                    tenant_id, environment_id, base_url, probes, known_urls, reset_path
                )
        except Exception as e:  # best effort: plain derivation must still work
            log.warning("flows.state_exploration_failed", error=str(e)[:200])
        log.info("flows.states_explored", planned=len(probes), reached=len(states))
        for st in states:
            page_text += (
                f"\n\nPAGE {st['url']} -- STATE {st['state_id']} "
                f"(after: {_describe_steps(st['reach'])})\n{st['snapshot']}"
            )
        pages = pages + states

    raw = await complete(
        messages=[{"role": "user", "content": f"Approved test cards:\n{card_text}\n\nApp pages:\n{page_text}"}],
        model=settings.planner_model,
        tenant_id=tenant_id,
        feature="derive_flows",
        system=_SYSTEM,
        max_tokens=8192,
    )
    flows = validate_flows(extract_json_object(raw), pages)
    log.info("flows.derived", pages=[f["page_name"] for f in flows], crawled=len(pages))
    return flows
