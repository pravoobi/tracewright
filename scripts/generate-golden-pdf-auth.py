"""Generate the second golden-set requirements PDF (user account & auth).

Doc 2 of 2 in the golden set — see generate-golden-pdf.py for doc 1
(checkout). Content matches backend/evals/golden/labels.json verbatim,
page-for-page, same pattern as doc 1.
"""
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.units import inch

OUT_PATH = Path(__file__).parents[1] / "backend" / "evals" / "golden" / "auth-requirements-v2.0.pdf"

styles = getSampleStyleSheet()
h1 = styles["Heading1"]
h2 = styles["Heading2"]
body = styles["BodyText"]

story = []

# Page 1 — Document Control (metadata: title, owner; out_of_scope: revision history)
story.append(Paragraph("User Account &amp; Authentication — Requirements Specification", h1))
story.append(Spacer(1, 0.1 * inch))
story.append(Paragraph("Document owner: Identity &amp; Access Team. Classification: Confidential.", body))
story.append(Spacer(1, 0.3 * inch))
story.append(Paragraph("1. Document Control", h2))
story.append(Paragraph(
    "Document revision history: v1.0 (2024-11-02, initial draft), "
    "v2.0 (2025-02-18, added multi-factor authentication requirements).",
    body,
))
story.append(PageBreak())

# Page 2 — Glossary (glossary_term x4)
story.append(Paragraph("2. Glossary", h2))
story.append(Paragraph(
    "Session token: An opaque, server-issued credential that authenticates "
    "a user's browser session after successful login.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "Multi-factor authentication (MFA): A login process requiring two or "
    "more independent verification factors.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "Account lockout: A temporary suspension of login capability for an "
    "account, triggered by repeated failed authentication attempts.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "Password reset token: A single-use, time-limited credential issued "
    "to verify a user's identity during a password reset flow.",
    body,
))
story.append(PageBreak())

# Page 3 — Overview (out_of_scope, filler context)
story.append(Paragraph("3. Overview", h2))
story.append(Paragraph(
    "This document describes requirements for user account authentication, "
    "including login, multi-factor authentication, account lockout, and "
    "password reset flows.",
    body,
))
story.append(PageBreak())

# Page 4 — Login & Lockout (acceptance_criterion x2, business_rule x2, example)
story.append(Paragraph("4. Login &amp; Lockout", h2))
story.append(Paragraph(
    "The system shall lock a user account after 5 consecutive failed "
    "login attempts within a 15-minute window.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "An account lockout shall persist for a minimum of 30 minutes before "
    "the user may attempt to log in again.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "The system shall notify a user by email when their account is "
    "locked due to failed login attempts.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "Failed login attempts shall reset to zero after a successful login.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "For example, if a user enters an incorrect password 5 times between "
    "2:00pm and 2:10pm, the account is locked until at least 2:40pm.",
    body,
))
story.append(PageBreak())

# Page 5 — Multi-Factor Authentication (acceptance_criterion x2, business_rule x2, example)
story.append(Paragraph("5. Multi-Factor Authentication", h2))
story.append(Paragraph(
    "The system shall require multi-factor authentication for accounts "
    "with administrator privileges.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "MFA codes delivered via SMS shall expire 5 minutes after issuance.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "The system shall allow users to register at least one authenticator "
    "app as an MFA method.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "MFA cannot be disabled on accounts with administrator privileges.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "For example, an administrator logging in receives a 6-digit MFA "
    "code by SMS that must be entered within 5 minutes or a new code "
    "must be requested.",
    body,
))
story.append(PageBreak())

# Page 6 — Password Reset (acceptance_criterion x2, business_rule x2, example)
story.append(Paragraph("6. Password Reset", h2))
story.append(Paragraph(
    "The system shall allow a user to request a password reset link via "
    "their registered email address.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "Password reset links shall expire 1 hour after issuance.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "Password reset links are single-use: once a link has been used to reset "
    "a password, it is no longer valid for any subsequent request.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "The system shall require a new password to differ from the user's "
    "previous 5 passwords.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "For example, if a user requests a password reset at 9:00am, the "
    "reset link becomes invalid at 10:00am even if unused.",
    body,
))
story.append(PageBreak())

# Page 7 — Session Management (acceptance_criterion x2, business_rule, glossary_term)
story.append(Paragraph("7. Session Management", h2))
story.append(Paragraph(
    "The system shall expire a user's session token after 30 minutes of "
    "inactivity.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "Session tokens are not valid after the user has logged out; a "
    "logged-out session token cannot be used to authenticate any further "
    "request.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "Idle timeout: The duration of user inactivity after which a session "
    "is automatically terminated.",
    body,
))
story.append(Spacer(1, 0.2 * inch))
story.append(Paragraph(
    "The system shall allow a user to view and revoke active sessions "
    "from their account settings.",
    body,
))
story.append(PageBreak())

# Page 8 — Stakeholders (out_of_scope)
story.append(Paragraph("8. Stakeholders", h2))
story.append(Paragraph(
    "Stakeholders: Alex Kim (Security Lead), Morgan Lee (Product Owner, "
    "Identity &amp; Access), Sam Torres (QA Lead). Approval status: Approved "
    "by the Security Review Board on 2025-02-20.",
    body,
))

doc = SimpleDocTemplate(str(OUT_PATH), pagesize=LETTER)
doc.build(story)

print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size} bytes)")
