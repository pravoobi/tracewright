"""Generate the golden-set requirements PDF matching backend/evals/golden/labels.json.

Each section is forced onto its own page via PageBreak so the resulting
page numbers line up with the `page_number` field in labels.json.
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

# Page 1 — Document Control (out_of_scope: revision history)
story.append(Paragraph("Checkout Service — Requirements Specification", h1))
story.append(Spacer(1, 0.3 * inch))
story.append(Paragraph("1. Document Control", h2))
story.append(Paragraph(
    "Document revision history: v1.0 (2025-01-10, initial draft), "
    "v1.1 (2025-03-05, added section 4).",
    body,
))
story.append(PageBreak())

# Page 2 — Glossary (glossary_term: discount code)
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
story.append(PageBreak())

# Page 3 — Overview (filler context, not part of the labeled golden set)
story.append(Paragraph("3. Overview", h2))
story.append(Paragraph(
    "This document describes the requirements for the checkout service's "
    "discount code feature. It covers eligibility, application rules, and "
    "the acceptance criteria that govern discount behavior at checkout.",
    body,
))
story.append(PageBreak())

# Page 4 — Discount Codes at Checkout (acceptance_criterion, business_rule, example)
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
    "For example, if the user has a 20% discount code and their cart "
    "totals $50, the discount reduces the total to $40.",
    body,
))

doc = SimpleDocTemplate(str(OUT_PATH), pagesize=LETTER)
doc.build(story)

print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size} bytes)")
