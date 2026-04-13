"""
Creates a Gmail draft reply to a recruiter email with the generated resume attached.
Draft is appended to [Gmail]/Drafts via IMAP — NOT sent automatically.
"""

import imaplib
import logging
import re
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict

from config import (
    IMAP_HOST,
    IMAP_PASSWORD,
    IMAP_PORT,
    IMAP_USER,
)

logger = logging.getLogger(__name__)

AUTO_REPLY_LABEL = "AUTO_APPLY_CLAUDE"

REPLY_BODY_TEMPLATE = """Hi {sender_first_name},

\tThanks for reaching out. I am interested in this position. I have 20+ years of experience in the skills mentioned in job details.

\tAttaching my latest resume for this position.

\tI am a US Green Card (GC) holder.

\tThanks,
\tPinal Dave
\tLinkedIn: https://www.linkedin.com/in/pinal-dave/
"""


def _get_recipient_address(from_email: str) -> str:
    match = re.search(r"<([^>]+)>", from_email)
    if match:
        return match.group(1).strip()
    return from_email.strip()


def _extract_sender_name(from_email: str, resume_json: Dict[str, Any]) -> str:
    name = (resume_json.get("sender_name") or "").strip()
    if name:
        return name
    match = re.match(r"^\s*([^<]+)\s*<", from_email)
    if match:
        return match.group(1).strip().strip('"')
    match = re.search(r"([^@\s]+)@", from_email)
    return match.group(1) if match else "there"


def _format_quoted_chain(email_date: str, from_email: str, raw_email_body: str) -> str:
    if not raw_email_body and not email_date and not from_email:
        return ""
    date_part = email_date.strip() if email_date else ""
    sender_part = from_email.strip() if from_email else "sender"
    if date_part and sender_part:
        header = f"On {date_part}, {sender_part} wrote:"
    elif sender_part:
        header = f"On {sender_part} wrote:"
    else:
        header = "Previous message:"
    body_lines = (raw_email_body or "").strip().splitlines()
    quoted_lines = "\n".join("> " + line if line.strip() else ">" for line in body_lines)
    return f"\n\n{header}\n{quoted_lines}"


def create_draft_reply(
    email_data: Dict[str, Any],
    resume_json: Dict[str, Any],
    resume_path: Path,
) -> None:
    """
    Create a Gmail draft replying to the recruiter with the generated resume attached.
    The draft is NOT sent — it appears in Gmail Drafts for manual review.
    """
    if not IMAP_USER or not IMAP_PASSWORD:
        raise RuntimeError("IMAP_USER and IMAP_PASSWORD must be set in .env")

    if not resume_path.exists():
        raise FileNotFoundError(f"Resume file not found: {resume_path}")

    from_email = email_data.get("from_email", "")
    to_email = _get_recipient_address(from_email)
    subject = email_data.get("subject", "")
    reply_subject = f"Re: {subject}" if subject and not subject.strip().lower().startswith("re:") else subject

    # Extract sender first name for personalized greeting
    sender_name = _extract_sender_name(from_email, resume_json)
    sender_first_name = sender_name.split()[0] if sender_name and sender_name != "there" else ""
    # Build greeting: "Hi John," or just "Hi," if name unavailable
    greeting_name = sender_first_name if sender_first_name else ""
    reply_text = REPLY_BODY_TEMPLATE.replace("{sender_first_name}", greeting_name)
    quoted_chain = _format_quoted_chain(
        email_data.get("date", ""),
        from_email,
        email_data.get("raw_email_body", ""),
    )
    body = reply_text + quoted_chain

    # Construct MIME message
    msg = MIMEMultipart()
    msg["From"] = IMAP_USER
    msg["To"] = to_email
    msg["Subject"] = reply_subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    # Attach resume
    resume_filename = resume_path.name
    with open(resume_path, "rb") as f:
        attachment = MIMEApplication(
            f.read(),
            _subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    attachment.add_header("Content-Disposition", "attachment", filename=resume_filename)
    msg.attach(attachment)

    # Append to Gmail Drafts
    raw = msg.as_string().encode("utf-8")
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(IMAP_USER, IMAP_PASSWORD)

    drafts_folder = "[Gmail]/Drafts"
    try:
        status, data = mail.append(drafts_folder, "\\Draft", None, raw)
    except Exception:
        drafts_folder = "Drafts"
        status, data = mail.append(drafts_folder, "\\Draft", None, raw)

    # Copy to AUTO_REPLY label for tracking
    if status == "OK" and data:
        resp = data[0].decode() if isinstance(data[0], bytes) else str(data[0])
        match = re.search(r"APPENDUID\s+\d+\s+(\d+)", resp)
        if match:
            uid = match.group(1)
            mail.select(drafts_folder, readonly=False)
            try:
                mail.copy(uid, AUTO_REPLY_LABEL)
            except Exception:
                pass  # Label may not exist in Gmail

    # Mark the original email as read and apply AUTO_APPLY_CLAUDE label
    original_folder = email_data.get("folder", "INBOX")
    original_uid = email_data.get("imap_uid", "")
    if original_uid:
        try:
            mail.select(original_folder, readonly=False)
            # Mark as read
            mail.store(original_uid.encode() if isinstance(original_uid, str) else original_uid, "+FLAGS", "\\Seen")
            # Apply label by copying to label folder
            try:
                mail.copy(original_uid.encode() if isinstance(original_uid, str) else original_uid, AUTO_REPLY_LABEL)
            except Exception:
                logger.warning("Could not apply label %s — create it in Gmail first", AUTO_REPLY_LABEL)
        except Exception as e:
            logger.warning("Could not mark original email as read: %s", e)

    mail.logout()
    logger.info("Draft created for: %s -> %s (%s)", to_email, reply_subject, resume_filename)
