"""Generate a sample bug-export .xlsx matching the checkout/discount domain
used by the golden requirements PDFs, for testing the Excel ingestion path.

Column headers deliberately mix standard aliases (that ingestion/excel.py's
_ALIAS_MAP already knows) with two genuinely novel columns ("Reporter",
"Environment") to exercise both the unmapped-column detection and the
LLM-assisted suggest_column_mapping() path. One row has a blank title to
test the worker's "skip untitled rows" logic.
"""
from pathlib import Path

import openpyxl

OUT_PATH = Path(__file__).parents[1] / "backend" / "evals" / "golden" / "checkout-bugs-export.xlsx"

HEADERS = [
    "Bug ID", "Summary", "Details", "Priority", "Module", "State",
    "Root Cause", "Resolved In", "Jira", "Resolved Date",
    "Reporter", "Environment",
]

ROWS = [
    [
        "BUG-1001", "Discount code SAVE20 not reducing total on checkout page",
        "Applying SAVE20 shows correct cart total but checkout page still shows full price",
        "P1", "Checkout", "Closed",
        "Checkout page cached stale cart total before discount recalculation",
        "1.1", "COMM-482", "2025-03-01",
        "jane.doe@example.com", "staging",
    ],
    [
        "BUG-1002", "Discount code accepted below $10 minimum order threshold",
        "Business rule requires order >= $10 for discount eligibility, but codes were accepted on a $5 order",
        "P0", "Checkout", "Closed",
        "Missing server-side validation, only client-side check existed",
        "1.0", "COMM-410", "2025-01-20",
        "raj.patel@example.com", "production",
    ],
    [
        "BUG-1003", "Cart allows 25 distinct line items despite documented max of 20",
        "",
        "Sev2", "Cart", "Open",
        "",
        "", "COMM-501", "",
        "priya.nair@example.com", "staging",
    ],
    [
        "BUG-1004", "",
        "Placeholder row for QA tracking",
        "P3", "Misc", "Open",
        "",
        "", "", "",
        "", "",
    ],
    [
        "BUG-1005", "International shipping rate not applied for non-US addresses",
        "Orders shipped outside the US were charged standard domestic shipping instead of international rate",
        "P1", "Shipping", "Closed",
        "Shipping rate lookup defaulted to domestic when country code was missing",
        "1.1", "COMM-495", "2025-03-05",
        "raj.patel@example.com", "production",
    ],
]

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Bugs"
ws.append(HEADERS)
for row in ROWS:
    ws.append(row)

wb.save(OUT_PATH)
print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size} bytes)")
