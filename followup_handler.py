"""
Phase 2: Intelligent Recruiter Follow-up Handler

Scans for reply emails (subject starts with "Re:") from recruiters who were
previously contacted. Uses Claude to understand intent and generate smart replies.
Creates Gmail drafts for review.
"""

import email
import imaplib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

import anthropic
from config import (
    CLAUDE_MODEL,
    EXCLUDED_DOMAINS,
    IMAP_HOST,
    IMAP_PASSWORD,
    IMAP_PORT,
    IMAP_USER,
    MAX_EMAIL_AGE_HOURS,
    SCAN_FOLDERS,
)
from state_tracker import load_state

logger = logging.getLogger(__name__)

FOLLOWUP_PROMPT_PATH = __import__("config").PROMPTS_DIR / "followup_prompt.txt"
FOLLOWUP_STATE_PATH = __import__("config").BASE_DIR / "followup_state.json"

FOLLOWUP_LABEL = "AUTO_REPLY_CLAUDE"


# ---------------------------------------------------------------------------
# State management for follow-ups
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


def _is_followup_processed(message_id: str) -> bool:
    return message_id in _load_followup_state()


def _mark_followup_processed(message_id: str, intent: str, summary: str) -> None:
    state = _load_followup_state()
    state[message_id] = {
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "intent": intent,
        "summary": summary,
    }
    _save_followup_state(state)


# ---------------------------------------------------------------------------
# Email scanning for follow-ups
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


def _is_from_known_recruiter(from_email: str) -> bool:
    """Check if the sender matches someone we previously replied to."""
    # Extract sender's email address
    match = re.search(r"<([^>]+)>", from_email)
    sender_addr = match.group(1).lower() if match else from_email.lower().strip()

    # Check processed_emails.json for any prior interaction
    state = load_state()
    for entry in state.values():
        prior_from = entry.get("from_email", "")
        prior_match = re.search(r"<([^>]+)>", prior_from)
        prior_addr = prior_match.group(1).lower() if prior_match else prior_from.lower().strip()
        if sender_addr == prior_addr:
            return True

    # Also check the sender's domain in our followup state
    followup_state = _load_followup_state()
    for entry in followup_state.values():
        # Broader check can be added here
        pass

    return False


def scan_for_followup_emails() -> List[Dict[str, Any]]:
    """
    Scan Gmail for reply emails (Re: ...) from recruiters we previously contacted.
    Returns list of email dicts ready for follow-up processing.
    """
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

                    # Must be a reply (Re: in subject)
                    if not subject or "re:" not in subject.lower():
                        continue

                    # Must not be from excluded domains
                    domain = _get_domain(from_email)
                    if not domain or domain in EXCLUDED_DOMAINS:
                        continue

                    # Must not be from ourselves
                    if IMAP_USER.lower() in from_email.lower():
                        continue

                    # Must be within age window
                    try:
                        dt = parsedate_to_datetime(date_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        if (datetime.now(timezone.utc) - dt).total_seconds() > MAX_EMAIL_AGE_HOURS * 3600:
                            continue
                    except Exception:
                        continue

                    # Must be from a recruiter we already interacted with
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
# Claude-powered intent analysis and reply generation
# ---------------------------------------------------------------------------

def generate_followup_reply(email_data: Dict[str, Any]) -> Dict[str, Any]:
    """Use Claude to analyze recruiter follow-up and generate a smart reply."""
    system_prompt = FOLLOWUP_PROMPT_PATH.read_text(encoding="utf-8")

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": json.dumps(email_data, ensure_ascii=False)}],
    )

    raw_text = response.content[0].text.strip()
    # Strip markdown fences
    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```(?:json)?\s*\n?", "", raw_text)
        raw_text = re.sub(r"\n?```\s*$", "", raw_text)

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start != -1 and end > start:
            result = json.loads(raw_text[start:end + 1])
        else:
            raise ValueError(f"Could not parse follow-up reply JSON: {raw_text[:500]}")

    logger.info(
        "Follow-up analyzed — intent: %s, confidence: %s",
        result.get("intent", "?"),
        result.get("confidence", "?"),
    )
    return result


# ---------------------------------------------------------------------------
# Draft creation for follow-up replies
# ---------------------------------------------------------------------------

def create_followup_draft(
    email_data: Dict[str, Any],
    reply_result: Dict[str, Any],
) -> None:
    """Create a Gmail draft for the follow-up reply."""
    if not IMAP_USER or not IMAP_PASSWORD:
        raise RuntimeError("IMAP_USER and IMAP_PASSWORD must be set in .env")

    from_email = email_data.get("from_email", "")
    match = re.search(r"<([^>]+)>", from_email)
    to_email = match.group(1).strip() if match else from_email.strip()

    subject = email_data.get("subject", "")
    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"

    reply_body = reply_result.get("reply_body", "")

    # Append quoted original
    email_date = email_data.get("date", "")
    raw_body = email_data.get("raw_email_body", "")
    if raw_body:
        date_part = email_date.strip() if email_date else ""
        sender_part = from_email.strip()
        if date_part:
            quoted_header = f"\n\nOn {date_part}, {sender_part} wrote:"
        else:
            quoted_header = f"\n\nOn {sender_part} wrote:"
        body_lines = raw_body.strip().splitlines()
        quoted = "\n".join("> " + line if line.strip() else ">" for line in body_lines)
        full_body = reply_body + quoted_header + "\n" + quoted
    else:
        full_body = reply_body

    # Build MIME
    msg = MIMEMultipart()
    msg["From"] = IMAP_USER
    msg["To"] = to_email
    msg["Subject"] = reply_subject
    msg.attach(MIMEText(full_body, "plain", "utf-8"))

    raw = msg.as_string().encode("utf-8")
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(IMAP_USER, IMAP_PASSWORD)

    drafts_folder = "[Gmail]/Drafts"
    try:
        status, data = mail.append(drafts_folder, "\\Draft", None, raw)
    except Exception:
        drafts_folder = "Drafts"
        status, data = mail.append(drafts_folder, "\\Draft", None, raw)

    # Apply follow-up label
    if status == "OK" and data:
        resp = data[0].decode() if isinstance(data[0], bytes) else str(data[0])
        uid_match = re.search(r"APPENDUID\s+\d+\s+(\d+)", resp)
        if uid_match:
            uid = uid_match.group(1)
            mail.select(drafts_folder, readonly=False)
            try:
                mail.copy(uid, FOLLOWUP_LABEL)
            except Exception:
                pass

    # Mark original email as read
    original_folder = email_data.get("folder", "INBOX")
    original_uid = email_data.get("imap_uid", "")
    if original_uid:
        try:
            mail.select(original_folder, readonly=False)
            uid_bytes = original_uid.encode() if isinstance(original_uid, str) else original_uid
            mail.store(uid_bytes, "+FLAGS", "\\Seen")
            try:
                mail.copy(uid_bytes, FOLLOWUP_LABEL)
            except Exception:
                pass
        except Exception as e:
            logger.warning("Could not mark follow-up email as read: %s", e)

    mail.logout()
    logger.info(
        "Follow-up draft created for: %s [%s] -> %s",
        to_email,
        reply_result.get("intent", "?"),
        reply_subject,
    )


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run_followup_pipeline() -> int:
    """
    Scan for follow-up emails, analyze with Claude, create smart reply drafts.
    Returns number processed.
    """
    logger.info("--- Follow-up pipeline starting ---")

    followups = scan_for_followup_emails()
    if not followups:
        logger.info("No follow-up emails found.")
        return 0

    new_followups = [f for f in followups if not _is_followup_processed(f.get("message_id", ""))]
    if not new_followups:
        logger.info("All %d follow-up(s) already processed.", len(followups))
        return 0

    logger.info("Processing %d new follow-up(s).", len(new_followups))
    processed = 0

    for i, email_data in enumerate(new_followups, 1):
        subject = email_data.get("subject", "(no subject)")
        from_email = email_data.get("from_email", "(unknown)")
        message_id = email_data.get("message_id", "")

        logger.info("[Follow-up %d/%d] %s from %s", i, len(new_followups), subject, from_email)

        try:
            # Analyze and generate reply
            reply_result = generate_followup_reply(email_data)

            # Create draft
            create_followup_draft(email_data, reply_result)

            # Mark processed
            _mark_followup_processed(
                message_id,
                reply_result.get("intent", "UNKNOWN"),
                reply_result.get("summary", ""),
            )
            processed += 1
            logger.info("  Done! Intent: %s", reply_result.get("intent"))

        except Exception as e:
            logger.error("  FAILED: %s", e, exc_info=True)

    logger.info("Follow-up pipeline complete. Processed %d/%d.", processed, len(new_followups))
    return processed
