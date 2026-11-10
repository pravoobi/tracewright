"""Planner agent — RAG-grounded test plan generation with full traceability."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.config import settings
from backend.src.knowledge.retrieval import retrieve_for_planning
from backend.src.llm.client import complete, extract_json_object
from backend.src.llm.langfuse_tracer import trace

_SAFE_TEST_ID = re.compile(r"[A-Za-z0-9_-]+")

log = structlog.get_logger()

_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "planner_system.txt").read_text()


async def generate_test_plan(
    session: AsyncSession,
    tenant_id: str,
    feature_area: str,
    doc_version: str,
    top_k: int = 15,
) -> dict[str, Any]:
    """
    Main entry point. Returns the full plan dict:
    {"test_cards": [...], "coverage_gaps": [...], "clarification_flags": [...]}
    Plan is a reviewable artifact — not hidden state. Caller persists to test_cards table.
    """
    tracer = trace(name="planner.generate", tenant_id=tenant_id)

    context = await retrieve_for_planning(
        session,
        query=feature_area,
        tenant_id=tenant_id,
        top_k=top_k,
        include_bugs=True,
        bug_severity_filter=["P0", "P1", "Sev1", "Sev2", "1", "2"],
    )

    user_prompt = _build_prompt(feature_area, doc_version, context)

    raw = await complete(
        messages=[{"role": "user", "content": user_prompt}],
        model=settings.planner_model,
        tenant_id=tenant_id,
        feature="planner",
        system=_SYSTEM_PROMPT,
        # 4096 was too small in practice: generating one detailed test card
        # (title, description, preconditions, setup_manifest) per retrieved
        # AC/business_rule chunk exceeds it once top_k retrieves more than a
        # handful of chunks, truncating the JSON mid-object and silently
        # producing zero test cards (caught, but only after burning the call).
        max_tokens=16384,
    )

    plan = _parse_plan(raw, doc_version, source_text=_context_text(context))

    if tracer:
        tracer.update(
            output={"test_cards": len(plan["test_cards"]), "gaps": len(plan["coverage_gaps"])}
        )

    log.info(
        "planner.done",
        tenant_id=tenant_id,
        test_cards=len(plan["test_cards"]),
        gaps=len(plan["coverage_gaps"]),
        flags=len(plan["clarification_flags"]),
    )
    return plan


def _build_prompt(feature_area: str, doc_version: str, context: dict[str, Any]) -> str:
    chunks = context["chunks"]
    bugs = context["bugs"]

    ac_text = "\n\n".join(
        f"[{c['display_ref']} | logical_id={c['logical_id']}]\n{c['content']}"
        for c in chunks
    )
    bug_text = "\n".join(
        f"- [{b['external_id']}] {b['title']} (Sev {b['severity']}, component={b['component']})"
        for b in bugs
    ) or "None"

    return (
        f"Feature area: {feature_area}\n"
        f"Document version: {doc_version}\n\n"
        f"=== ACCEPTANCE CRITERIA & BUSINESS RULES ===\n{ac_text}\n\n"
        f"=== RELATED BUG HISTORY ===\n{bug_text}\n\n"
        f"Generate test cards for all testable items above."
    )


def _parse_plan(raw: str, doc_version: str, source_text: str = "") -> dict[str, Any]:
    try:
        plan = extract_json_object(raw)
    except json.JSONDecodeError:
        log.error("planner.json_parse_failed", raw_preview=raw[:200])
        plan = {"test_cards": [], "coverage_gaps": [], "clarification_flags": []}

    # Stamp introduced_in_version and generate stable test_id
    for card in plan.get("test_cards", []):
        card.setdefault("introduced_in_version", doc_version)
        if not card.get("test_id"):
            card["test_id"] = f"TC-{uuid.uuid4().hex[:8].upper()}"
        _mark_manifest_provenance(card, source_text)

    plan.setdefault("coverage_gaps", [])
    plan.setdefault("clarification_flags", [])
    return plan


async def persist_plan(
    session: AsyncSession,
    tenant_id: str,
    plan: dict[str, Any],
) -> list[str]:
    """Save approved-or-pending test cards to DB. Returns list of test_card IDs."""
    from sqlalchemy import select
    from backend.src.db.models import TestCard, TraceabilityLink

    # The Planner LLM numbers cards sequentially (TC-001, TC-002, ...) with no
    # awareness of IDs used by a PREVIOUS generation run for this tenant —
    # test_id has a unique DB constraint, so a second call for a similar
    # feature area reliably regenerates "TC-001" and crashes the whole
    # request with an uncaught IntegrityError. Disambiguate proactively.
    existing = await session.execute(
        select(TestCard.test_id).where(TestCard.tenant_id == uuid.UUID(tenant_id))
    )
    used_ids = set(existing.scalars().all())

    card_ids: list[str] = []
    for card in plan["test_cards"]:
        if card.get("needs_clarification"):
            approval_status = "needs_clarification"
        else:
            approval_status = "pending"

        # test_id comes from the Planner LLM's JSON output, which a
        # malicious uploaded document could steer via prompt injection.
        # It later gets interpolated into a generated test's output
        # filename (codegen.py's safe_filename) -- reject anything outside
        # a safe charset here, at the point of persistence, rather than
        # only sanitizing downstream at the point of use.
        # LLM output: may be an int/None, and "$" would accept a trailing
        # newline -- coerce to a str and require a full match.
        test_id = card["test_id"] if isinstance(card["test_id"], str) else ""
        if not _SAFE_TEST_ID.fullmatch(test_id):
            log.warning("planner.unsafe_test_id_rejected", raw=test_id)
            test_id = f"TC-{uuid.uuid4().hex[:8]}"
        if test_id in used_ids:
            base, suffix = test_id, 2
            while test_id in used_ids:
                test_id = f"{base}-{suffix}"
                suffix += 1
            log.warning("planner.test_id_collision", original=base, reassigned=test_id)
        used_ids.add(test_id)

        tc = TestCard(
            tenant_id=uuid.UUID(tenant_id),
            test_id=test_id,
            title=card["title"],
            description=card["description"],
            preconditions=card.get("preconditions"),
            setup_manifest=card.get("setup_manifest", []),
            test_type=card.get("test_type"),
            priority=card.get("priority"),
            introduced_in_version=card["introduced_in_version"],
            applicability={},
            tier_sources=card.get("tier_sources", {"tier": 1, "confidence": 0.5}),
            approval_status=approval_status,
        )
        session.add(tc)
        await session.flush()  # get tc.id

        # Traceability links
        if card.get("source_logical_id"):
            session.add(TraceabilityLink(
                tenant_id=uuid.UUID(tenant_id),
                test_card_id=tc.id,
                linked_type="chunk",
                linked_logical_id=card["source_logical_id"],
                link_reason="AC coverage",
            ))
        for bug_id in card.get("regresses_bugs", []):
            session.add(TraceabilityLink(
                tenant_id=uuid.UUID(tenant_id),
                test_card_id=tc.id,
                linked_type="bug",
                linked_logical_id=bug_id,
                link_reason="regression guard",
            ))

        card_ids.append(str(tc.id))

    await session.commit()
    return card_ids


def _context_text(context: dict[str, Any]) -> str:
    parts = [c["content"] for c in context["chunks"]]
    parts += [f"{b['title']} {b.get('description') or ''}" for b in context["bugs"]]
    return " ".join(parts)


def _concrete_values(entry: dict[str, Any]) -> list[str]:
    """Strings/numbers in a manifest entry that must be traceable to the source text.
    Structural keys (type, role, source) are excluded; booleans are ignored."""
    skip = {"type", "role", "source", "state", "active"}
    out: list[str] = []

    def walk(v: Any, key: str = "") -> None:
        if key in skip or isinstance(v, bool) or v is None:
            return
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x, k)
        elif isinstance(v, list):
            for x in v:
                walk(x, key)
        else:
            out.append(str(v))

    walk(entry)
    return out


def _mark_manifest_provenance(card: dict[str, Any], source_text: str) -> None:
    """Don't trust the model's own "source": "document" claim — downgrade an
    entry to "assumed" if any concrete value in it is absent from the retrieved
    source text (this is how TC-003 got an invented SAVE15 code and a
    SKU-200 @ $33.33 cart that were presented as if they came from the doc).
    Cards with any assumed entry are tagged so reviewers and the fixture author
    see the setup is unverified: tier_sources["assumed_setup"] = count."""
    haystack = source_text.lower()
    assumed = 0
    manifest = card.get("setup_manifest") or []
    for entry in manifest:
        if not isinstance(entry, dict):
            continue
        claimed_doc = entry.get("source") == "document"
        grounded = claimed_doc and all(v.lower() in haystack for v in _concrete_values(entry))
        entry["source"] = "document" if grounded else "assumed"
        if not grounded:
            assumed += 1
    tiers = card.get("tier_sources")
    if not isinstance(tiers, dict):
        tiers = {"tier": 1, "confidence": 0.5}
    tiers["assumed_setup"] = assumed
    card["tier_sources"] = tiers
