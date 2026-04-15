"""
Scan Follow-up Emails Tool — scans Gmail for reply emails (Re: ...) from
recruiters who were previously contacted. Manages follow-up state tracking.
"""

import email
import imaplib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List

from config import (
    EXCLUDED_DOMAINS,
    FOLLOWUP_STATE_PATH,
    IMAP_HOST,
    IMAP_PASSWORD,
    IMAP_PORT,
    IMAP_USER,
    MAX_EMAIL_AGE_HOURS,
    SCAN_FOLDERS,
    STATE_FILE_PATH,
)
from graph.state import EmailPipelineState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Follow-up state management
# ---------------------------------------------------------------------------

def _load_followup_state() -> Dict:
    if not FOLLOWUP_STATE_PATH.exists():
        return {}
    try:
        return json.loads(FOLLOWUP_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_followup_state(state: Dict) -> None:
    FOLLOWUP_STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def is_followup_processed(message_id: str) -> bool:
    return message_id in _load_followup_state()


def mark_followup_processed(message_id: str, intent: str, summary: str) -> None:
    state = _load_followup_state()
    state[message_id] = {
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "intent": intent,
        "summary": summary,
    }
    _save_followup_state(state)


# ---------------------------------------------------------------------------
# Email parsing helpers
# ---------------------------------------------------------------------------

def _header_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _get_domain(addr: str) -> str:
    if not addr:
        return ""
    match = re.search(r"@([\w.-]+\.[a-zA-Z]{2,})", addr)
    return match.group(1).lower() if match else ""


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


def _load_processed_state() -> dict:
    """Load the processed emails state from disk."""
    if not STATE_FILE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_FILE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _is_from_known_recruiter(from_email: str) -> bool:
    """Check if the sender matches someone we previously replied to."""
    match = re.search(r"<([^>]+)>", from_email)
    sender_addr = match.group(1).lower() if match else from_email.lower().strip()

    state = _load_processed_state()
    for entry in state.values():
        prior_from = entry.get("from_email", "")
        prior_match = re.search(r"<([^>]+)>", prior_from)
        prior_addr = prior_match.group(1).lower() if prior_match else prior_from.lower().strip()
        if sender_addr == prior_addr:
            return True

    return False


# ---------------------------------------------------------------------------
# Gmail scanning for follow-up emails
# ---------------------------------------------------------------------------

def _scan_for_followup_emails() -> List[Dict[str, Any]]:
    """Scan Gmail for reply emails from recruiters we previously contacted."""
    if not IMAP_USER or not IMAP_PASSWORD:
        raise RuntimeError("IMAP_USER and IMAP_PASSWORD must be set in .env")

    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(IMAP_USER, IMAP_PASSWORD)

    since = (datetime.now(timezone.utc) - timedelta(hours=MAX_EMAIL_AGE_HOURS)).strftime("%d-%b-%Y")
    since_criteria = f"SINCE {since}"

    all_followups: List[Dict[str, Any]] = []
    seen_message_ids = set()

    try:
        status, folders = mail.list()
        for f in folders or []:
            line = f.decode() if isinstance(f, bytes) else str(f)
            parts = line.split('"')
            folder_name = parts[-2] if len(parts) >= 2 else ""
            if folder_name and any(label in folder_name for label in SCAN_FOLDERS):
                try:
                    st, _ = mail.select(folder_name, readonly=True)
                except Exception:
                    continue
                if st != "OK":
                    continue

                _, message_numbers = mail.search(None, since_criteria)
                msg_ids = message_numbers[0].split()

                for uid in msg_ids:
                    _, data = mail.fetch(uid, "(RFC822)")
                    if not data or not data[0]:
                        continue
                    msg = email.message_from_bytes(data[0][1])
                    from_email = _header_str(msg.get("From"))
                    subject = _header_str(msg.get("Subject"))
                    date_str = _header_str(msg.get("Date"))
                    message_id = _header_str(msg.get("Message-ID"))
                    imap_uid = uid.decode() if isinstance(uid, bytes) else str(uid)

                    if not subject or "re:" not in subject.lower():
                        continue
                    domain = _get_domain(from_email)
                    if not domain or domain in EXCLUDED_DOMAINS:
                        continue
                    if IMAP_USER.lower() in from_email.lower():
                        continue

                    try:
                        dt = parsedate_to_datetime(date_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        if (datetime.now(timezone.utc) - dt).total_seconds() > MAX_EMAIL_AGE_HOURS * 3600:
                            continue
                    except Exception:
                        continue

                    if not _is_from_known_recruiter(from_email):
                        continue

                    if message_id and message_id not in seen_message_ids:
                        seen_message_ids.add(message_id)
                        body = _extract_body(msg)
                        all_followups.append({
                            "raw_email_body": body,
                            "from_email": from_email,
                            "to_email": _header_str(msg.get("To")),
                            "subject": subject,
                            "date": date_str,
                            "message_id": message_id,
                            "imap_uid": imap_uid,
                            "folder": folder_name,
                        })
    except Exception as e:
        logger.error("Error scanning for follow-ups: %s", e)

    mail.logout()
    logger.info("Found %d follow-up email(s)", len(all_followups))
    return all_followups


# ---------------------------------------------------------------------------
# Agent node function
# ---------------------------------------------------------------------------

def scan_followup_emails(state: EmailPipelineState) -> Dict[str, Any]:
    """Scan Gmail for follow-up emails from known recruiters."""
    followups = _scan_for_followup_emails()
    new_followups = [f for f in followups if not is_followup_processed(f.get("message_id", ""))]

    if not new_followups:
        logger.info("No new follow-up emails to process.")
    else:
        logger.info("Found %d new follow-up(s).", len(new_followups))

    return {
        "followup_emails": new_followups,
        "current_followup_index": 0,
        "current_followup": {},
        "phase2_processed": 0,
        "followup_scan_done": True,
    }
