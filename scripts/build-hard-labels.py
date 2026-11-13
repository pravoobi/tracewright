"""Build backend/evals/golden/labels_hard.json (the harder classification cases).

Authored by hand below, written out as JSON so reviewers can diff/spot-check the
file directly. `difficulty` = "ambiguous" marks labels a reasonable reviewer could
dispute; the eval reports accuracy on those separately so a disagreement there
doesn't read as a regression. Labelling convention (matches labels.json):
  metadata       title / document name / version-and-date stamp
  out_of_scope   document control (owner, author, reviewers, history), boilerplate,
                 footers, roadmap / explicitly excluded scope, nothing testable
  business_rule  constraint or invariant (including tables of constraints)
  acceptance_criterion  testable behaviour ("shall...", "Given/When/Then", "users see...")
  example        illustrates a rule with concrete values
  glossary_term  defines a domain term
"""
import json
from pathlib import Path

AC, BR, GL, EX, OOS, MD = (
    "acceptance_criterion", "business_rule", "glossary_term", "example", "out_of_scope", "metadata",
)
S, A = "standard", "ambiguous"

# (source_doc, hint_block_type, expected_type, page, difficulty, content, rationale)
ROWS = [
    # ---- returns (synthetic third document) --------------------------------------
    ("returns", "heading", MD, 1, S, "Returns & Refunds Service — Requirements Specification", "document title"),
    ("returns", "paragraph", MD, 1, A, "Version 3.1 — 12 June 2025", "version/date stamp; could be read as document control"),
    ("returns", "paragraph", MD, 1, A, "Document ID: RR-SPEC-031 | Status: Approved | Review date: 2025-12-01", "document identification line"),
    ("returns", "paragraph", GL, 2, S, "Return merchandise authorization (RMA): A unique code issued by the system that authorizes a customer to send an item back.", "definition with a colon"),
    ("returns", "paragraph", GL, 2, A, "Restocking fee: A percentage of the item price withheld from a refund when a returned item has been opened.", "definition that embeds a rule-like clause"),
    ("returns", "paragraph", AC, 4, S, "The system shall allow a customer to initiate a return from the order history page for any delivered order.", "classic shall"),
    ("returns", "paragraph", AC, 4, S, "The system shall issue an RMA code and display it to the customer after a return is submitted.", "classic shall"),
    ("returns", "paragraph", AC, 4, S, "Given a return has been marked as received, when a warehouse operator confirms inspection, then the system shall issue a refund to the original payment method.", "Given/When/Then"),
    ("returns", "paragraph", AC, 4, S, "The system shall send the customer a confirmation email containing the RMA code within 1 minute of return submission.", "shall with a measurable bound"),
    ("returns", "paragraph", AC, 4, S, "The system shall prevent a return from being initiated for an order that has not yet been delivered.", "negative-path shall"),
    ("returns", "list_item", AC, 5, A, "Customers can filter their return history by status (pending, received, refunded).", "testable behaviour without 'shall'; list item"),
    ("returns", "paragraph", BR, 3, S, "Items may be returned within 30 days of delivery.", "time-window constraint"),
    ("returns", "paragraph", BR, 3, S, "Final-sale items are not eligible for return.", "eligibility constraint"),
    ("returns", "paragraph", BR, 3, S, "Opened electronics are subject to a 15% restocking fee.", "fee constraint"),
    ("returns", "paragraph", BR, 6, S, "Refunds are issued to the original payment method only; store credit may not be substituted without the customer's consent.", "invariant"),
    ("returns", "paragraph", BR, 6, S, "Return shipping is free for defective items and paid by the customer in all other cases.", "invariant"),
    ("returns", "table", BR, 3, S, "Item category | Return window | Restocking fee\nApparel | 30 days | None\nElectronics | 30 days | 15% if opened\nFurniture | 14 days | 20%", "table of constraints"),
    ("returns", "table", BR, 6, A, "Role | Permission\nCustomer | Initiate return\nWarehouse operator | Confirm receipt\nFinance | Approve refunds over $500", "permission matrix; could be read as testable behaviour"),
    ("returns", "paragraph", EX, 5, S, "For example, a customer who received a $200 opened laptop on 1 March and returns it on 20 March is refunded $170, because the 15% restocking fee ($30) applies.", "worked example with numbers"),
    ("returns", "paragraph", EX, 5, S, "Example: an order delivered on 1 May can be returned until 31 May; a return initiated on 1 June is rejected.", "'Example:' prefix"),
    ("returns", "paragraph", EX, 6, A, "Scenario: a customer returns two of three items from one order. Only the two returned items are refunded; the original shipping charge is not refunded.", "'Scenario' framing of an illustrative case"),
    ("returns", "paragraph", OOS, 1, S, "Revision history: v3.0 (2025-04-02) added restocking fee; v3.1 (2025-06-12) clarified final-sale items.", "document control"),
    ("returns", "paragraph", OOS, 7, S, "Reviewers: Dana Whitfield (Finance), Luis Ortega (Support), Mei Chen (Legal).", "stakeholder list"),
    ("returns", "paragraph", OOS, 1, S, "This document is confidential and intended solely for internal use by Acme Corp employees.", "boilerplate"),
    ("returns", "paragraph", OOS, 2, A, "Out of scope for this release: international returns and customs documentation.", "explicit scope exclusion; mentions rules but is not testable"),
    ("returns", "paragraph", OOS, 4, S, "See Appendix B for the full list of carrier return labels.", "cross-reference, no content"),
    ("returns", "table", OOS, 1, S, "1. Introduction | 2\n2. Definitions | 3\n3. Return initiation | 4\n4. Refunds | 6", "table of contents"),
    # ---- checkout ------------------------------------------------------------------
    ("checkout", "paragraph", AC, 4, S, "Customers see an inline error message when they enter an expired or unrecognised discount code.", "testable behaviour without 'shall'"),
    ("checkout", "paragraph", AC, 4, S, "Given a cart subtotal of $5.00, when the customer submits a discount code, then the system displays an error and leaves the total unchanged.", "Given/When/Then"),
    ("checkout", "paragraph", AC, 5, A, "The checkout summary page shall render within 2 seconds at the 95th percentile under the documented load profile.", "non-functional but measurable"),
    ("checkout", "paragraph", AC, 6, S, "The system shall not store the full card number after payment authorization completes.", "negative shall"),
    ("checkout", "paragraph", AC, 5, S, "The system shall recalculate the order total whenever the quantity of a line item changes.", "classic shall"),
    ("checkout", "paragraph", BR, 4, A, "Discount codes shall not be combined with any other promotion on the same order.", "uses 'shall' but states an invariant"),
    ("checkout", "paragraph", BR, 6, S, "Gift cards are not subject to sales tax.", "tax constraint"),
    ("checkout", "paragraph", BR, 4, S, "Note: shipping charges are excluded from the amount that a discount code reduces.", "'Note:' prefix on a constraint"),
    ("checkout", "table", BR, 6, S, "Subtotal range | Shipping charge\n$0.00–$49.99 | $5.99\n$50.00 and above | Free", "table of constraints"),
    ("checkout", "list_item", BR, 4, S, "Each customer may hold at most one active promotional code at a time.", "list-item constraint"),
    ("checkout", "paragraph", EX, 4, S, "A $50.00 cart with a valid 20% code totals $40.00; the same cart with a 10% code totals $45.00.", "example with no marker phrase"),
    ("checkout", "paragraph", EX, 4, S, "Entering the code SAVE99 on the cart page displays the message \"SAVE99 is not a valid discount code.\"", "concrete case without 'for example'"),
    ("checkout", "paragraph", EX, 5, S, "Suppose a customer has two Widgets at $30.00 each and one Sticker at $5.00. The subtotal is $65.00 before any discount.", "'Suppose' framing"),
    ("checkout", "paragraph", GL, 2, S, "A SKU (stock keeping unit) is the unique identifier a merchant assigns to each purchasable product variant.", "definition without a colon"),
    ("checkout", "paragraph", GL, 2, S, "Subtotal — the sum of line-item prices before discounts, tax and shipping.", "dash-style definition"),
    ("checkout", "paragraph", OOS, 3, A, "The system shall be built and maintained in accordance with the company's secure coding standards.", "uses 'shall' but nothing testable at the feature level"),
    ("checkout", "paragraph", OOS, 7, S, "Future releases may add support for gift cards and loyalty points; these are not covered by this specification.", "roadmap"),
    ("checkout", "paragraph", OOS, 7, S, "Approved by: Commerce Platform steering committee on 2025-03-05.", "document control"),
    ("checkout", "figure_caption", OOS, 3, A, "Figure 3: Sequence diagram of the checkout flow between the web client and the order service.", "figure caption; could be read as metadata"),
    ("checkout", "heading", MD, 1, S, "Checkout Service — Requirements Specification, Version 1.1 (2025-03-05)", "title with version and date"),
    ("checkout", "paragraph", OOS, 5, S, "Page 5 of 8 — Checkout Service Requirements — Internal", "page footer"),
    # ---- auth ----------------------------------------------------------------------
    ("auth", "paragraph", AC, 7, S, "The system shall sign users out automatically and redirect them to the login page when their session expires.", "classic shall"),
    ("auth", "paragraph", AC, 4, S, "The system shall reject passwords shorter than 12 characters and display the reason.", "classic shall"),
    ("auth", "paragraph", BR, 4, S, "Passwords must be at least 12 characters long and may not contain the user's email address.", "constraint stated without 'shall'"),
    ("auth", "paragraph", AC, 4, S, "Given a locked account, when the lockout period elapses, then the user can log in again with valid credentials.", "Given/When/Then"),
    ("auth", "paragraph", AC, 4, S, "The system shall not reveal whether an email address is registered when a login attempt fails.", "negative shall"),
    ("auth", "paragraph", BR, 7, S, "Administrator accounts are exempt from the idle timeout while a privileged operation is in progress.", "exemption rule"),
    ("auth", "paragraph", BR, 7, S, "Each user may have at most 5 concurrent active sessions.", "limit"),
    ("auth", "paragraph", EX, 7, S, "A user who has been idle since 10:00 and returns at 10:45 is redirected to the login page and must sign in again.", "example with no marker phrase"),
    ("auth", "paragraph", EX, 4, A, "Entering a wrong password on the login page shows \"Invalid email or password\" and does not indicate which field was wrong.", "concrete case; could be read as acceptance criterion"),
    ("auth", "paragraph", GL, 2, S, "Authenticator app: A mobile application that generates time-based one-time passcodes (TOTP) used as a second authentication factor.", "definition with a colon"),
    ("auth", "paragraph", GL, 2, A, "Lockout window refers to the 15-minute period during which failed login attempts are counted.", "definition phrased with 'refers to'; also carries a number"),
    ("auth", "paragraph", OOS, 3, A, "Single sign-on with external identity providers is out of scope for this release.", "explicit scope exclusion"),
    ("auth", "paragraph", OOS, 8, S, "Reviewed by: Sam Torres (QA Lead) on 2025-02-17.", "document control"),
    ("auth", "table", BR, 5, A, "Role | MFA required\nAdministrator | Yes\nStandard user | Optional\nService account | No", "constraint matrix; could be read as acceptance criterion"),
    ("auth", "heading", MD, 1, S, "User Account & Authentication — Version 2.0 — 18 February 2025", "title with version and date"),
    ("auth", "list_item", AC, 7, S, "Users can sign out of all other devices from the account settings page.", "testable behaviour without 'shall'"),
    ("auth", "paragraph", BR, 6, S, "Password reset links may only be requested once every 60 seconds per email address.", "rate-limit constraint"),
    ("auth", "paragraph", OOS, 8, S, "Copyright 2025 Acme Corp. All rights reserved. Do not distribute.", "boilerplate"),
]


def main() -> None:
    out = []
    for i, (doc, hint, typ, page, diff, content, why) in enumerate(ROWS, 1):
        out.append({
            "id": f"hard-{i:03d}",
            "source_doc": doc,
            "hint_block_type": hint,
            "content": content,
            "expected_type": typ,
            "page_number": page,
            "difficulty": diff,
            "rationale": why,
        })
    path = Path(__file__).resolve().parent.parent / "backend" / "evals" / "golden" / "labels_hard.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    from collections import Counter
    print(len(out), "labels ->", path)
    print(Counter(r["expected_type"] for r in out))
    print(Counter(r["difficulty"] for r in out))


if __name__ == "__main__":
    main()
