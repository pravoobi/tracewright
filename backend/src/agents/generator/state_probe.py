"""State-dependent elements: reach a UI state with a few vetted actions, then look.

Some elements exist only after an action (a discount summary after applying a
code, an error alert after a bad one). A plain crawl never sees them. A probe
is a short list of `fill` / `click` steps on ONE page; running it reveals what
appears. The same steps are stored with the element (`reach`) and replayed by
Phase 1 before verifying its locator, so "verified" still means "resolved to
exactly one element in the live app", just in the right state.

Probes act on a real environment, so they are deliberately narrow:
  * only `fill` and `click`, only on elements identified by role+name or testid
    that resolve to exactly one element;
  * click targets that look destructive or irreversible (pay, delete, sign out,
    place order...) are refused, whoever proposed them;
  * fill values must be quoted from the approved test cards;
  * at most MAX_STEPS steps; if a step navigates away, the probe stops;
  * the cross-origin guard (restrict_to_origin) still applies.
Probes change server-side state in the target environment (a cart, a form),
which is why build-registry only runs them when the caller opts in.
"""
from __future__ import annotations

import re
from typing import Any, Callable

import structlog

log = structlog.get_logger()

MAX_STEPS = 7  # including the leading and any trailing goto
MAX_PROBES = 6
_FILL_ROLES = {"textbox", "spinbutton", "combobox"}
_CLICK_ROLES = {"button", "link", "checkbox", "radio"}
_ACTION_ROLES = _FILL_ROLES | _CLICK_ROLES
# A fill value that is not quoted from the cards must at least be inert text
# (an obviously-invalid code like BOGUS123 is how an error state is reached).
_INERT_VALUE = re.compile(r"[A-Za-z0-9_. -]{1,40}")
_STATE_ID = re.compile(r"[a-z][A-Za-z0-9]{0,40}")
_DESTRUCTIVE = re.compile(
    r"\b(delete|remove|destroy|erase|wipe|reset|clear all|pay|purchase|buy|place order|"
    r"submit order|complete order|confirm order|checkout complete|sign ?out|log ?out|"
    r"cancel (order|subscription|account)|unsubscribe|deactivate|close account|refund|"
    r"transfer|withdraw|send|publish|approve|reject)\b",
    re.IGNORECASE,
)


def validate_steps(
    raw: Any,
    allowed_text: str | None = None,
    url_ok: Callable[[str], bool] | None = None,
) -> list[dict[str, Any]] | None:
    """Return a sanitized copy of `raw`, or None if ANY step is unsafe/malformed
    (a partly-trusted probe is not replayed at all). `allowed_text`, when given,
    is checked for fill values (quoted from it, or inert text); `url_ok` says
    which URLs a `goto` step may visit (none, if omitted)."""
    if not isinstance(raw, list) or not raw or len(raw) > MAX_STEPS:
        return None
    steps: list[dict[str, Any]] = []
    for s in raw:
        if not isinstance(s, dict):
            return None
        action, role = s.get("action"), s.get("role")
        name, testid = s.get("name"), s.get("testid")
        if action == "goto":
            url = s.get("url")
            if not (isinstance(url, str) and url_ok is not None and url_ok(url)):
                return None
            steps.append({"action": "goto", "url": url})
            continue
        if action not in ("fill", "click"):
            return None
        if not (isinstance(name, str) and name) and not (isinstance(testid, str) and testid):
            return None
        if role is not None and role not in _ACTION_ROLES:
            return None
        if role is None and not (isinstance(testid, str) and testid):
            return None
        if action == "fill" and role is not None and role not in _FILL_ROLES:
            return None
        if action == "click" and role is not None and role not in _CLICK_ROLES:
            return None
        label = f"{name or ''} {testid or ''}"
        if action == "click" and _DESTRUCTIVE.search(label):
            return None
        step: dict[str, Any] = {
            "action": action,
            "role": role,
            "name": name[:100] if isinstance(name, str) else None,
            "testid": testid[:100] if isinstance(testid, str) else None,
        }
        if action == "fill":
            value = s.get("value")
            if not isinstance(value, str) or not value or len(value) > 100:
                return None
            if (
                allowed_text is not None
                and value not in allowed_text
                and not _INERT_VALUE.fullmatch(value)
            ):
                return None
            step["value"] = value
        steps.append(step)
    return steps


def validate_probes(
    raw: Any, pages: list[dict[str, Any]], allowed_text: str
) -> list[dict[str, Any]]:
    """LLM probe plan -> [{"state_id", "url", "steps"}] on crawled URLs only."""
    known = {p["url"] for p in pages if not p.get("state_id")}
    probes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in (raw.get("probes") if isinstance(raw, dict) else None) or []:
        if len(probes) >= MAX_PROBES or not isinstance(entry, dict):
            continue
        state_id, url = entry.get("state"), entry.get("url")
        if not (isinstance(state_id, str) and _STATE_ID.fullmatch(state_id)) or state_id in seen:
            continue
        if not (isinstance(url, str) and url in known):
            continue
        steps = validate_steps(entry.get("steps"), allowed_text, url_ok=lambda u: u in known)
        if steps is not None:
            steps = [{"action": "goto", "url": url}] + steps  # a reach starts from a known page
        if steps is None or len(steps) > MAX_STEPS:
            log.warning("state_probe.rejected_probe", state=state_id)
            continue
        seen.add(state_id)
        probes.append({"state_id": state_id, "url": url, "steps": steps})
    return probes


def _step_locator(page: Any, step: dict[str, Any]):
    if step.get("role"):
        if step.get("name"):
            return page.get_by_role(step["role"], name=step["name"])
        return page.get_by_role(step["role"])
    return page.get_by_test_id(step["testid"])


async def replay_steps(
    page: Any, steps: list[dict[str, Any]], expect_url: str | None = None
) -> bool:
    """Run vetted steps from a blank page (the first step is a goto). False if a
    target is not exactly one element, a step fails, or the page does not end
    on `expect_url`; the caller then skips the state."""
    for step in steps:
        try:
            if step["action"] == "goto":
                await page.goto(step["url"], wait_until="networkidle")
                continue
            locator = _step_locator(page, step)
            if await locator.count() != 1:
                log.warning("state_probe.target_not_unique", step=step["action"], name=step.get("name"))
                return False
            if step["action"] == "fill":
                await locator.fill(step["value"], timeout=5000)
            else:
                await locator.click(timeout=5000)
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass  # long-polling pages never go idle; the snapshot is what matters
        except Exception as e:
            log.warning("state_probe.step_failed", error=str(e)[:200])
            return False
    if expect_url is not None and page.url.split("#")[0] != expect_url.split("#")[0]:
        log.info("state_probe.ended_elsewhere", expected=expect_url, actual=page.url)
        return False
    return True


def valid_reset_path(path: str | None) -> bool:
    """A same-origin absolute path, e.g. "/reset". Never a full URL: the reset
    request carries the environment's auth cookies, so it may only go to the
    environment's own origin."""
    return (
        isinstance(path, str)
        and path.startswith("/")
        and not path.startswith("//")
        and "\\" not in path
        and len(path) <= 200
        and not any(c in path for c in "\r\n ")
    )


async def reset_environment_state(context: Any, base_url: str, reset_path: str | None) -> None:
    """POST the customer-supplied reset endpoint (if any) so each probe/replay
    starts from the same server-side state. Best effort: a failed reset is
    logged, and the state it was meant to clean may then not be reached."""
    if not reset_path or not valid_reset_path(reset_path):
        return
    from urllib.parse import urljoin

    try:
        resp = await context.request.post(urljoin(base_url, reset_path))
        if resp.status >= 400:
            log.warning("state_probe.reset_failed", status=resp.status)
    except Exception as e:
        log.warning("state_probe.reset_failed", error=str(e)[:200])
