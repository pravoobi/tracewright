"""Generate the golden-set requirements PDF matching backend/evals/golden/labels.json.

Each section is forced onto its own page via PageBreak so the resulting
page numbers line up with the `page_number` field in labels.json.

Doc 1 of 2 in the golden set — see generate-golden-pdf-auth.py for doc 2.
"""
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.units import inch

OUT_PATH = Path(__file__).parents[1] / "backend" / "evals" / "golden" / "checkout-requirements-v1.1.pdf"

styles = getSampleStyleSheet()
h1 = styles["Heading1"]
h2 = styles["Heading2"]
body = styles["BodyText"]

story = []

# Page 1 — Document Control (metadata: title, owner; out_of_scope: revision history)
story.append(Paragraph("Checkout Service — Requirements Specification", h1))
story.append(Spacer(1, 0.1 * inch))
story.append(Paragraph("Document owner: Commerce Platform Team. Classification: Internal.", body))
story.append(Spacer(1, 0.3 * inch))
story.append(Paragraph("1. Document Control", h2))
story.append(Paragraph(
    "Document revision history: v1.0 (2025-01-10, initial draft), "
    "v1.1 (2025-03-05, added section 4), v1.2 (2025-04-02, added cart limits, "
    "shipping &amp; tax, and stakeholders sections).",
    body,
))
story.append(PageBreak())

# Page 2 — Glossary (glossary_term x5)
story.append(Paragraph("2. Glossary", h2))
story.append(Paragraph(
    "Discount code: A string of 6–12 alphanumeric characters issued by "
    "the marketing team to reduce order price.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "Order total: The sum of all line-item prices in a customer's cart, "
    "prior to tax and shipping, expressed in USD.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "Cart: A collection of one or more line items a customer intends to "
    "purchase, persisted per user session.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "SKU: Stock Keeping Unit — a unique alphanumeric identifier for a "
    "purchasable product variant.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "Tax rate: The percentage of an order's subtotal charged as sales tax, "
    "determined by the shipping destination's jurisdiction.",
    body,
))
story.append(PageBreak())

# Page 3 — Overview (out_of_scope, filler context)
story.append(Paragraph("3. Overview", h2))
story.append(Paragraph(
    "This document describes the requirements for the checkout service's "
    "discount code feature. It covers eligibility, application rules, and "
    "the acceptance criteria that govern discount behavior at checkout.",
    body,
))
story.append(PageBreak())

# Page 4 — Discount Codes at Checkout (acceptance_criterion x2, business_rule x2, example)
story.append(Paragraph("4. Discount Codes at Checkout", h2))
story.append(Paragraph(
    "The system shall allow authenticated users to apply a discount code "
    "at checkout. The discount shall reduce the order total by the "
    "percentage specified in the discount record.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "A discount code may not be applied to orders with a total below $10.00.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "A discount code may only be applied once per order.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "The system shall display the applied discount code and percentage on "
    "the checkout summary before order confirmation.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "For example, if the user has a 20% discount code and their cart "
    "totals $50, the discount reduces the total to $40.",
    body,
))
story.append(PageBreak())

# Page 5 — Cart Limits (acceptance_criterion, business_rule x2, example)
story.append(Paragraph("5. Cart Limits", h2))
story.append(Paragraph(
    "The system shall prevent checkout when the cart contains zero items.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "A single order may contain a maximum of 20 distinct line items.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "The quantity of any single SKU in a cart shall not exceed 99 units.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "For example, if a customer attempts to add a 100th unit of the same "
    "SKU, the system rejects the addition and displays a quantity-limit error.",
    body,
))
story.append(PageBreak())

# Page 6 — Shipping & Tax (acceptance_criterion, business_rule, example)
story.append(Paragraph("6. Shipping &amp; Tax", h2))
story.append(Paragraph(
    "The system shall calculate sales tax based on the shipping address's "
    "jurisdiction tax rate at the time of checkout.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "Orders shipped to addresses outside the United States are not "
    "eligible for standard shipping and shall default to international "
    "shipping rates.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "For example, an order with an $80.00 subtotal shipped to a "
    "jurisdiction with a 7.5% tax rate incurs $6.00 in sales tax, for an "
    "order total of $86.00.",
    body,
))
story.append(PageBreak())

# Page 7 — Stakeholders (out_of_scope)
story.append(Paragraph("7. Stakeholders", h2))
story.append(Paragraph(
    "Stakeholders: Jane Doe (Product Owner, Commerce Platform), Raj Patel "
    "(Engineering Lead), Priya Nair (QA Lead). Approval status: Approved "
    "by Commerce Platform Steering Committee on 2025-03-10.",
    body,
))

doc = SimpleDocTemplate(str(OUT_PATH), pagesize=LETTER)
doc.build(story)

print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size} bytes)")
