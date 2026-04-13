"""
SMTP email sender with optional DOCX attachment support.
"""

import logging
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from config import IMAP_USER, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER

logger = logging.getLogger(__name__)


def send_email(
    to: str,
    subject: str,
    body: str,
    attachment_path: Optional[str] = None,
) -> None:
    """
    Send an email via SMTP with STARTTLS.
    Optionally attach a DOCX file.
    """
    msg = MIMEMultipart()
    msg["From"] = SMTP_USER or IMAP_USER
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if attachment_path:
        path = Path(attachment_path)
        if path.exists() and path.is_file():
            with open(path, "rb") as f:
                part = MIMEApplication(f.read(), Name=path.name)
            part["Content-Disposition"] = f'attachment; filename="{path.name}"'
            msg.attach(part)
        else:
            logger.warning("Attachment not found, sending without: %s", attachment_path)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(SMTP_USER or IMAP_USER, SMTP_PASSWORD)
        server.sendmail(msg["From"], [to], msg.as_string())

    logger.info("Email sent to %s — subject: %s", to, subject)
