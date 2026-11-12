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


class UnsafeGeneratedCodeError(Exception):
    """Raised when generated test code contains a pattern that should never
    appear in a Playwright POM test file -- most likely a sign of prompt
    injection from an untrusted source document steering the Planner/
    Generator into emitting code that does something other than test the
    app."""


_DENY_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bchild_process\b"), "child_process usage"),
    # (?<![.\w]) so method calls like regex.exec(...) / obj.require(...) don't false-positive
    (re.compile(r"(?<![.\w])require\s*\("), "CommonJS require() -- generated tests must use ES imports only"),
    (re.compile(r"\bimport\s*\("), "dynamic import()"),
    (re.compile(r"\b(?:process|globalThis|global|window)\s*\["), "computed access on a global object"),
    (re.compile(r"\beval\s*\("), "eval()"),
    (re.compile(r"\bnew\s+Function\s*\("), "Function() constructor (dynamic code execution)"),
    (re.compile(r"\bfetch\s*\("), "raw fetch() -- tests must drive the app via page/page-objects, not raw HTTP"),
    (re.compile(r"\baxios\b"), "axios usage"),
    (re.compile(r"\b(?:http|https)\.request\s*\("), "raw http(s).request()"),
    (re.compile(r"\bprocess\.env\b"), "process.env access"),
    (re.compile(r"\bexecSync\s*\(|\bspawnSync?\s*\(|(?<![.\w])exec\s*\("), "process-spawning call"),
]

# First quoted string after an `import` keyword is the module specifier. The
# lazy [^;'"]* spans newlines, so a multi-line import
# (import { A, B } split across lines, then `from '...'`) is checked as one
# unit; a per-line check rejected those legitimate statements.
_IMPORT_STATEMENT = re.compile(r"""(?m)^[ \t]*import\b[^;'"]*?['"]([^'"\n]+)['"]""")
_ALLOWED_IMPORT_PREFIXES = ("../fixtures/", "../page-objects/")


def _import_allowed(spec: str) -> bool:
    if spec == "@playwright/test":
        return True
    # No path traversal after the allowed prefix ("../fixtures/../../x").
    return spec.startswith(_ALLOWED_IMPORT_PREFIXES) and ".." not in spec[3:].split("/")


def check_generated_code_safety(code: str) -> list[str]:
    """Deny-list scan over LLM-generated test code before it's written to
    the customer's git-tracked test scaffold. The Planner and Generator both
    read untrusted document text (an uploaded requirements PDF) as part of
    their prompt -- a malicious document can prompt-inject either agent, and
    since human review approves test CARDS (title/description/setup
    manifest), not the generated CODE itself, nothing else stands between a
    successful injection and arbitrary TypeScript landing in the customer's
    CI. This is a coarse first line of defense (deny-list + import
    allowlist), not a sandbox -- it catches the concrete escape hatches
    (spawning processes, eval, raw network calls, imports outside the
    expected page-object/fixture set), not everything a sufficiently
    creative injection could do."""
    violations: list[str] = []
    for line in code.splitlines():
        stripped = line.strip()
        for pattern, description in _DENY_PATTERNS:
            if pattern.search(line):
                violations.append(f"{description}: {stripped[:120]}")
    for match in _IMPORT_STATEMENT.finditer(code):
        if not _import_allowed(match.group(1)):
            violations.append(
                f"import outside allowed fixtures/page-objects/@playwright/test: {match.group(1)[:120]}"
            )
    return violations

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
- Setup-manifest entries marked `"source": "assumed"` are UNVERIFIED: the Planner chose their
  values, they are not in the customer's requirements and may not exist in the target app.
  Never present such values as established facts; keep them in one clearly named constant
  near the top of the test and add a `// Setup assumption:` comment saying the customer
  must provide/confirm that data. Entries marked "document" are grounded in the requirements.
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
    full_code = header + "\n\n" + code

    violations = check_generated_code_safety(full_code)
    if violations:
        log.error(
            "codegen.unsafe_code_rejected",
            test_id=test_card.get("test_id"),
            violations=violations,
        )
        raise UnsafeGeneratedCodeError(
            f"Generated code for {test_card.get('test_id', 'unknown')} failed the "
            f"safety check and was not written: {'; '.join(violations)}"
        )

    return full_code


def assumed_setup_entries(manifest: list[Any] | None) -> list[dict[str, Any]]:
    """Setup-manifest entries the Planner marked (or the grounding check
    downgraded to) "assumed". Cards from before provenance tracking have no
    "source" key at all -- that's unknown, not assumed, so they don't count."""
    return [e for e in (manifest or []) if isinstance(e, dict) and e.get("source") == "assumed"]


def _trace_ids(card: dict[str, Any], linked_type: str) -> str:
    """Comma-joined logical ids of the card's traceability links of one type.
    Bug ids come from a customer spreadsheet and chunk ids from LLM-era data,
    so strip anything that could break out of a one-line comment."""
    ids = [
        re.sub(r"[^\w.:/ -]", "", str(link.get("logical_id", "")))
        for link in card.get("traceability") or []
        if link.get("type") == linked_type
    ]
    if linked_type == "chunk" and not ids and card.get("source_logical_id"):
        ids = [re.sub(r"[^\w.:/ -]", "", str(card["source_logical_id"]))]
    return ", ".join(i for i in ids if i)


def _build_metadata_header(card: dict[str, Any]) -> str:
    lines = [
        "// ─── Tracewright — Generated Test ───────────────────────────────────────",
        f"// Test Card ID : {card.get('test_id', 'unknown')}",
        f"// Title        : {card.get('title', '')}",
        f"// Source AC    : {_trace_ids(card, 'chunk') or 'UNLINKED (no source requirement)'}",
        f"// Regresses    : {_trace_ids(card, 'bug') or 'none'}",
        f"// Priority     : {card.get('priority', '')}",
        f"// Type         : {card.get('test_type', '')}",
        "// ─────────────────────────────────────────────────────────────────────────",
        "// DO NOT EDIT locators manually — regenerate via Tracewright.",
    ]
    assumed = assumed_setup_entries(card.get("setup_manifest"))
    if assumed:
        lines.append("//")
        lines.append("// SETUP ASSUMPTIONS — not found in the source documents; the customer must")
        lines.append("// provide or confirm this data in the target environment before this test can pass:")
        for entry in assumed:
            # json.dumps keeps each entry on one line, so a value containing a
            # newline can't break out of the comment (card text is LLM output).
            lines.append("//   - " + json.dumps(entry, ensure_ascii=False))
    return "\n".join(lines)


def safe_filename(test_id: str, title: str) -> str:
    """test_id originates from the Planner LLM's JSON output, which is
    steerable via prompt injection in an uploaded document — it was
    previously interpolated into the output path with no sanitization at
    all, so a test_id like "..\\..\\x" would write outside the tests
    directory. Whitelist to the same safe charset the title slug already
    used, rather than trusting LLM output to stay well-formed."""
    safe_test_id = re.sub(r"[^\w-]", "", test_id.lower()) or "test"
    slug = re.sub(r"[^\w\s-]", "", title.lower()).strip().replace(" ", "-")[:40]
    return f"{safe_test_id}-{slug}.spec.ts"
