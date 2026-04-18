"""
Render and Draft Node — creates a Gmail draft reply to a recruiter email
with the generated resume attached. Draft is appended to [Gmail]/Drafts
via IMAP — NOT sent automatically.
"""

import imaplib
import json
import logging
import re
from datetime import datetime, timezone
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
    STATE_FILE_PATH,
)
from graph.state import EmailPipelineState

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


# ---------------------------------------------------------------------------
# Draft creation helpers
# ---------------------------------------------------------------------------

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


def _create_draft_reply(
    email_data: Dict[str, Any],
    resume_json: Dict[str, Any],
    resume_path: Path,
) -> None:
    """Create a Gmail draft replying to the recruiter with the resume attached."""
    if not IMAP_USER or not IMAP_PASSWORD:
        raise RuntimeError("IMAP_USER and IMAP_PASSWORD must be set in .env")

    if not resume_path.exists():
        raise FileNotFoundError(f"Resume file not found: {resume_path}")

    from_email = email_data.get("from_email", "")
    to_email = _get_recipient_address(from_email)
    subject = email_data.get("subject", "")
    reply_subject = f"Re: {subject}" if subject and not subject.strip().lower().startswith("re:") else subject

    sender_name = _extract_sender_name(from_email, resume_json)
    sender_first_name = sender_name.split()[0] if sender_name and sender_name != "there" else ""
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
                pass

    # Mark the original email as read and apply AUTO_APPLY_CLAUDE label
    original_folder = email_data.get("folder", "INBOX")
    original_uid = email_data.get("imap_uid", "")
    if original_uid:
        try:
            mail.select(original_folder, readonly=False)
            mail.store(original_uid.encode() if isinstance(original_uid, str) else original_uid, "+FLAGS", "\\Seen")
            try:
                mail.copy(original_uid.encode() if isinstance(original_uid, str) else original_uid, AUTO_REPLY_LABEL)
            except Exception:
                logger.warning("Could not apply label %s — create it in Gmail first", AUTO_REPLY_LABEL)
        except Exception as e:
            logger.warning("Could not mark original email as read: %s", e)

    mail.logout()
    logger.info("Draft created for: %s -> %s (%s)", to_email, reply_subject, resume_filename)


# ---------------------------------------------------------------------------
# Agent node function
# ---------------------------------------------------------------------------

def _mark_processed(message_id: str, subject: str, from_email: str, resume_file: str) -> None:
    """Persist a processed email to disk so it won't be reprocessed next run."""
    try:
        state = json.loads(STATE_FILE_PATH.read_text(encoding="utf-8")) if STATE_FILE_PATH.exists() else {}
    except (json.JSONDecodeError, OSError):
        state = {}
    state[message_id] = {
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "subject": subject,
        "from_email": from_email,
        "resume_file": resume_file,
    }
    STATE_FILE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        from blob_storage import upload_state_file
        upload_state_file(STATE_FILE_PATH)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Blob sync of processed_emails skipped: %s", exc)
    logger.info("Marked as processed: %s", message_id)


def render_and_draft(state: EmailPipelineState) -> Dict[str, Any]:
    """Create a Gmail draft with the resume attached and mark the email processed."""
    email_data = state["current_email"]
    resume_json = state.get("resume_json", {})
    resume_path_str = state.get("resume_path", "")
    idx = state.get("current_email_index", 0)
    processed = state.get("recruiter_processed", 0)

    if not resume_path_str or not resume_json:
        return {
            "current_email_index": idx + 1,
            "current_email": {},
            "resume_json": {},
            "resume_path": "",
        }

    resume_path = Path(resume_path_str)
    message_id = email_data.get("message_id", "")
    subject = email_data.get("subject", "")
    from_email = email_data.get("from_email", "")

    try:
        logger.info("  Creating Gmail draft...")
        _create_draft_reply(email_data, resume_json, resume_path)
        _mark_processed(message_id, subject, from_email, str(resume_path))
        logger.info("  Done! Resume: %s", resume_path.name)
        return {
            "current_email_index": idx + 1,
            "current_email": {},
            "resume_json": {},
            "resume_path": "",
            "recruiter_processed": processed + 1,
        }
    except Exception as e:
        logger.error("  FAILED to draft for '%s': %s", subject, e, exc_info=True)
        return {
            "current_email_index": idx + 1,
            "current_email": {},
            "resume_json": {},
            "resume_path": "",
            "errors": [f"Draft creation failed for '{subject}': {e}"],
        }
