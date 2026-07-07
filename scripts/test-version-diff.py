"""
Test versioning/diff.py's diff_document_versions() directly against real
ingested chunk data from the golden checkout PDF, simulating a v1.2 edit:
- most chunks unchanged verbatim
- 2 chunks reworded (modified)
- 1 chunk dropped (removed)
- 1 genuinely new chunk added
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.src.db.session import async_session_factory
from backend.src.db.models import Chunk
from sqlalchemy import select
from backend.src.versioning.diff import diff_document_versions

ARTIFACT_ID = "c2a519bf-e544-49d9-8f3b-7927c9d3ee94"

# Reworded versions of two real chunks (modified)
_MODIFIED = {
    "A discount code may not be applied to orders with a total below $10.00.":
        "A discount code may not be applied to orders with a subtotal under $15.00.",
    "Discount code: A string of 6-12 alphanumeric characters issued by the marketing team to reduce order price.":
        "Discount code: A string of 6-14 alphanumeric characters issued by the marketing team to reduce the customer's order price.",
}

# A chunk to drop entirely (removed) — the orphaned fragment
_REMOVE_CONTENT = "addition and displays a quantity-limit error."

# A genuinely new business rule not present in v1.1 at all
_NEW_CHUNK = "Discount codes expire 90 days after issuance and cannot be applied after their expiration date."


async def main():
    async with async_session_factory() as session:
        result = await session.execute(
            select(Chunk.logical_id, Chunk.content).where(Chunk.artifact_id == ARTIFACT_ID)
        )
        old_chunks = [{"logical_id": row.logical_id, "content": row.content} for row in result.all()]

    new_chunks_raw = []
    for c in old_chunks:
        if c["content"] == _REMOVE_CONTENT:
            continue  # simulate removal — omit from the new version
        new_chunks_raw.append(_MODIFIED.get(c["content"], c["content"]))
    new_chunks_raw.append(_NEW_CHUNK)

    diffs = diff_document_versions(old_chunks, new_chunks_raw)

    by_status: dict[str, list] = {}
    for d in diffs:
        by_status.setdefault(d.status, []).append(d)

    for status in ("unchanged", "modified", "new", "removed"):
        items = by_status.get(status, [])
        print(f"\n=== {status.upper()} ({len(items)}) ===")
        for d in items:
            preview = (d.new_content or d.old_content or "")[:70]
            print(f"  {d.logical_id} | {preview}")


if __name__ == "__main__":
    asyncio.run(main())
