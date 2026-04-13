"""
Drafts router — manage Gmail drafts via IMAP.
List, view, edit, send, and delete drafts from [Gmail]/Drafts.
"""

import email
import imaplib
import logging
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.data_service import get_all_emails
from api.email_sender import send_email
from config import IMAP_HOST, IMAP_PASSWORD, IMAP_PORT, IMAP_USER

logger = logging.getLogger(__name__)
router = APIRouter()

DRAFTS_FOLDER = "[Gmail]/Drafts"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _imap_connect() -> imaplib.IMAP4_SSL:
    """Connect and authenticate to Gmail IMAP."""
    if not IMAP_USER or not IMAP_PASSWORD:
        raise HTTPException(status_code=500, detail="IMAP credentials not configured")
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(IMAP_USER, IMAP_PASSWORD)
    return mail


def _select_drafts(mail: imaplib.IMAP4_SSL) -> None:
    """Select the Gmail Drafts folder."""
    status, _ = mail.select(DRAFTS_FOLDER, readonly=False)
    if status != "OK":
        # Fallback to plain "Drafts"
        status, _ = mail.select("Drafts", readonly=False)
        if status != "OK":
            raise HTTPException(status_code=500, detail="Cannot open Drafts folder")


def _decode_payload(part: email.message.Message) -> str:
    raw = part.get_payload(decode=True)
    if not raw:
        return ""
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def _extract_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return _decode_payload(part)
    else:
        return _decode_payload(msg)
    return ""


def _header_str(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_draft(uid: bytes, raw_data: bytes) -> Dict[str, Any]:
    """Parse a raw email into a draft dict."""
    msg = email.message_from_bytes(raw_data)
    return {
        "uid": uid.decode() if isinstance(uid, bytes) else str(uid),
        "to": _header_str(msg.get("To")),
        "from": _header_str(msg.get("From")),
        "subject": _header_str(msg.get("Subject")),
        "date": _header_str(msg.get("Date")),
        "message_id": _header_str(msg.get("Message-ID")),
        "body": _extract_body(msg),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/")
def list_drafts():
    """List all drafts from Gmail Drafts folder, enriched with processed email metadata."""
    mail = _imap_connect()
    try:
        _select_drafts(mail)
        status, data = mail.search(None, "ALL")
        if status != "OK" or not data[0]:
            return []

        uids = data[0].split()
        drafts: List[Dict[str, Any]] = []

        # Build lookup for enrichment
        processed = get_all_emails()
        subject_lookup = {}
        for e in processed:
            subj = e.get("subject", "").lower().strip()
            if subj:
                subject_lookup[subj] = e

        for uid in uids:
            status, msg_data = mail.fetch(uid, "(RFC822)")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            draft = _parse_draft(uid, raw)

            # Try to match against processed emails by subject
            draft_subject = draft.get("subject", "").lower().strip()
            # Strip "Re: " prefix for matching
            clean_subject = re.sub(r"^re:\s*", "", draft_subject, flags=re.IGNORECASE)
            matched = subject_lookup.get(clean_subject) or subject_lookup.get(draft_subject)
            if matched:
                draft["matched_email"] = matched

            drafts.append(draft)

        return drafts
    finally:
        mail.logout()


@router.get("/{uid}")
def get_draft(uid: str):
    """Get a single draft by IMAP UID."""
    mail = _imap_connect()
    try:
        _select_drafts(mail)
        status, msg_data = mail.fetch(uid.encode(), "(RFC822)")
        if status != "OK" or not msg_data or not msg_data[0]:
            raise HTTPException(status_code=404, detail="Draft not found")
        raw = msg_data[0][1]
        return _parse_draft(uid.encode(), raw)
    finally:
        mail.logout()


class DraftUpdate(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None


@router.put("/{uid}")
def edit_draft(uid: str, update: DraftUpdate):
    """Edit a draft: delete old version and append new one."""
    mail = _imap_connect()
    try:
        _select_drafts(mail)

        # Fetch old draft
        status, msg_data = mail.fetch(uid.encode(), "(RFC822)")
        if status != "OK" or not msg_data or not msg_data[0]:
            raise HTTPException(status_code=404, detail="Draft not found")

        old_msg = email.message_from_bytes(msg_data[0][1])
        new_subject = update.subject if update.subject is not None else _header_str(old_msg.get("Subject"))
        new_body = update.body if update.body is not None else _extract_body(old_msg)

        # Delete old draft
        mail.store(uid.encode(), "+FLAGS", "\\Deleted")
        mail.expunge()

        # Build new draft
        new_msg = MIMEMultipart()
        new_msg["From"] = _header_str(old_msg.get("From")) or IMAP_USER
        new_msg["To"] = _header_str(old_msg.get("To"))
        new_msg["Subject"] = new_subject
        new_msg.attach(MIMEText(new_body, "plain", "utf-8"))

        # Append new draft
        raw = new_msg.as_string().encode("utf-8")
        status, data = mail.append(DRAFTS_FOLDER, "\\Draft", None, raw)
        if status != "OK":
            raise HTTPException(status_code=500, detail="Failed to save updated draft")

        return {"status": "updated", "subject": new_subject}
    finally:
        mail.logout()


@router.post("/{uid}/send")
def send_draft(uid: str):
    """Send a draft via SMTP, then delete it from Gmail Drafts."""
    mail = _imap_connect()
    try:
        _select_drafts(mail)

        # Fetch draft
        status, msg_data = mail.fetch(uid.encode(), "(RFC822)")
        if status != "OK" or not msg_data or not msg_data[0]:
            raise HTTPException(status_code=404, detail="Draft not found")

        msg = email.message_from_bytes(msg_data[0][1])
        to = _header_str(msg.get("To"))
        subject = _header_str(msg.get("Subject"))
        body = _extract_body(msg)

        if not to:
            raise HTTPException(status_code=400, detail="Draft has no recipient")

        # Send via SMTP
        send_email(to=to, subject=subject, body=body)

        # Delete the draft
        mail.store(uid.encode(), "+FLAGS", "\\Deleted")
        mail.expunge()

        return {"status": "sent", "to": to, "subject": subject}
    finally:
        mail.logout()


@router.delete("/{uid}")
def delete_draft(uid: str):
    """Delete a draft from Gmail."""
    mail = _imap_connect()
    try:
        _select_drafts(mail)
        mail.store(uid.encode(), "+FLAGS", "\\Deleted")
        mail.expunge()
        return {"status": "deleted", "uid": uid}
    finally:
        mail.logout()
