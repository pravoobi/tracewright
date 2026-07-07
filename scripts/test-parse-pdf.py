"""Day-3 PoC: parse one PDF end-to-end and print structured output."""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from backend.src.ingestion.triage import triage_document
from backend.src.ingestion.layout import extract_layout
from backend.src.ingestion.structure import recover_structure


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/test-parse-pdf.py <path-to-pdf>")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    data = pdf_path.read_bytes()
    filename = pdf_path.name

    print(f"\n=== Stage 1: Triage ===")
    triage = triage_document(filename, data)
    print(f"  Total pages : {triage.total_pages}")
    print(f"  Native      : {sum(1 for p in triage.pages if p.page_type == 'native')}")
    print(f"  Scanned     : {sum(1 for p in triage.pages if p.page_type == 'scanned')}")
    print(f"  Blank       : {sum(1 for p in triage.pages if p.page_type == 'blank')}")

    print(f"\n=== Stage 2: Layout extraction (Docling) ===")
    layout = extract_layout(filename, data, triage)
    print(f"  Blocks extracted: {len(layout.blocks)}")
    by_type: dict[str, int] = {}
    for b in layout.blocks:
        by_type[b.block_type] = by_type.get(b.block_type, 0) + 1
    for t, c in sorted(by_type.items()):
        print(f"    {t}: {c}")

    print(f"\n=== Stage 3: Structure recovery ===")
    doc = recover_structure(layout)
    print(f"  Blocks after merge    : {len(doc.blocks)}")
    print(f"  Cross-references found: {len(doc.cross_references)}")

    print(f"\n=== Sample blocks (first 5) ===")
    for block in doc.blocks[:5]:
        print(f"  [{block.block_type}] page={block.page_number} conf={block.confidence:.2f}")
        print(f"    {block.content[:120]!r}")


if __name__ == "__main__":
    main()
