"""
SMTP send — invoked when a user approves a pending reply in the UI.

Uses the same Gmail account (IMAP_USER / IMAP_PASSWORD — an app password)
over SMTP 587 with STARTTLS. Attaches the resume if present.

This is the only place in the app that actually TRANSMITS an email.
Until a user explicitly approves a pending reply, nothing goes out.
"""

import logging
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, Optional

from config import IMAP_PASSWORD, IMAP_USER, SMTP_HOST, SMTP_PORT

logger = logging.getLogger(__name__)


def send_pending_reply(pending: Dict[str, Any]) -> Optional[str]:
    """Send a pending reply via SMTP. Returns None on success, error msg on failure."""
    if not IMAP_USER or not IMAP_PASSWORD:
        return "IMAP_USER and IMAP_PASSWORD must be set for SMTP send"

    reply = pending.get("reply", {})
    to_addr = reply.get("to", "").strip()
    subject = reply.get("subject", "")
    body = reply.get("body", "")
    if not to_addr:
        return "Pending reply has no recipient"

    msg = MIMEMultipart()
    msg["From"] = IMAP_USER
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    resume_path_str = pending.get("resume_path") or ""
    if resume_path_str:
        resume_path = Path(resume_path_str)
        if resume_path.exists() and resume_path.is_file():
            with open(resume_path, "rb") as f:
                attachment = MIMEApplication(
                    f.read(),
                    _subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            attachment.add_header(
                "Content-Disposition", "attachment", filename=resume_path.name
            )
            msg.attach(attachment)
        else:
            logger.warning("Resume path %s no longer exists — sending without attachment",
                           resume_path_str)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=60) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(IMAP_USER, IMAP_PASSWORD)
            server.sendmail(IMAP_USER, [to_addr], msg.as_string())
        logger.info("SMTP send OK — to=%s subject=%s pending_id=%s",
                    to_addr, subject, pending.get("id"))
        return None
    except Exception as exc:  # noqa: BLE001
        logger.error("SMTP send failed for pending %s: %s",
                     pending.get("id"), exc, exc_info=True)
        return str(exc)
