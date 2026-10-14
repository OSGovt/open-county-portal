"""Outgoing email (receipts, request confirmations).

Uses the SMTP relay set in /opt/county-portal/.env (PORTAL_SMTP_HOST and
friends). If no relay is configured, messages are written to the log and the
site keeps working; the go-live checklist flags the missing relay.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

log = logging.getLogger("portal.notify")


def configured() -> bool:
    return bool(os.environ.get("PORTAL_SMTP_HOST"))


def send(to: str | None, subject: str, body: str) -> bool:
    if not to:
        return False
    host = os.environ.get("PORTAL_SMTP_HOST")
    sender = os.environ.get("PORTAL_SMTP_FROM", "no-reply@localhost")
    if not host:
        log.info("Email not sent (no SMTP relay configured): to=%s subject=%s", to, subject)
        return False
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    port = int(os.environ.get("PORTAL_SMTP_PORT", "587"))
    user = os.environ.get("PORTAL_SMTP_USER")
    password = os.environ.get("PORTAL_SMTP_PASSWORD")
    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            if os.environ.get("PORTAL_SMTP_STARTTLS", "true").lower() != "false":
                smtp.starttls(context=ssl.create_default_context())
            if user:
                smtp.login(user, password or "")
            smtp.send_message(msg)
        return True
    except Exception as exc:  # never let email trouble break a payment
        log.error("Email to %s failed: %s", to, exc)
        return False
