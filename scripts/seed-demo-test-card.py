"""
Seed one manually-authored, pre-approved test card for the Generator spike.

This intentionally bypasses the Planner's RAG/LLM pipeline (`agents/planner.py`) —
that pipeline was already exercised conceptually and needs an ingested,
embedded document to retrieve against. This spike is scoped to de-risking the
*Generator* (Phase 1 page-object registry + Phase 2 codegen), so the test card
below is authored by hand from the golden set's AC instead:

  "The system shall allow authenticated users to apply a discount code at
  checkout. The discount shall reduce the order total by the percentage
  specified in the discount record." (golden-001, acceptance_criterion)
  + "A discount code may not be applied to orders with a total below $10.00."
    (golden-002, business_rule)
  + "...if the user has a 20% discount code and their cart totals $50, the
    discount reduces the total to $40." (golden-005, example)
"""
import asyncio
import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from backend.src.db.session import async_session_factory
from backend.src.db.models import TestCard

TENANT_ID = "00000000-0000-0000-0000-000000000001"
TEST_ID = "TC-DISCOUNT-001"


async def seed():
    async with async_session_factory() as session:
        existing = await session.scalar(
            select(TestCard).where(TestCard.test_id == TEST_ID)
        )
        if existing:
            print(f"Test card '{TEST_ID}' already exists id={existing.id}")
            return

        card = TestCard(
            tenant_id=uuid.UUID(TENANT_ID),
            test_id=TEST_ID,
            title="Applying a 20% discount code at checkout reduces a $50 cart to $40",
            description=(
                "An authenticated user with a cart totaling $50.00 (1x Widget $30 + "
                "1x Gadget $20) applies the discount code SAVE20 at checkout. The "
                "system shall reduce the order total by the discount's percentage "
                "(20%), yielding a final total of $40.00. The discount and its "
                "percentage must be visible on the cart page before checkout, and "
                "the checkout page must reflect the same discounted total."
            ),
            preconditions=(
                "User test@example.com is authenticated. Cart contains 1x Widget "
                "($30.00) and 1x Gadget ($20.00), subtotal $50.00. No discount "
                "code is currently applied."
            ),
            setup_manifest=[
                {"type": "user", "role": "authenticated", "email": "test@example.com"},
                {"type": "cart_state", "items": {"widget": 1, "gadget": 1}, "subtotal_usd": 50.00},
            ],
            test_type="functional",
            priority="P1",
            introduced_in_version="1.0",
            applicability={},
            tier_sources={
                "tier": 1,
                "confidence": 1.0,
                "source": "manual_spike_seed",
                "note": (
                    "Generator spike — manually authored from golden set ACs "
                    "(golden-001, golden-002, golden-005), bypassing the Planner "
                    "LLM/RAG pipeline which needs an ingested+embedded document."
                ),
            },
            approval_status="approved",
            approved_by="generator-spike-script",
        )
        session.add(card)
        await session.commit()
        print(f"Created approved test card '{TEST_ID}' id={card.id}")


if __name__ == "__main__":
    asyncio.run(seed())
