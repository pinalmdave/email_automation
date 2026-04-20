"""
Scan Recruiter Emails Node — connects to Gmail via IMAP, scans configured
folders, and returns emails matching recruiter criteria (domain filter,
subject keywords, age limit, AI/Cloud position filter).
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
# Email parsing and filtering helpers
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


def _email_passes_domain(from_email: str) -> bool:
    domain = _get_domain(from_email)
    return bool(domain) and domain not in EXCLUDED_DOMAINS


# ---------------------------------------------------------------------------
# Smart AI / Cloud position filter
# ---------------------------------------------------------------------------

AI_CLOUD_KEYWORDS = (
    " ai ", " ai/", " ai,", " ai.", " ai-", "(ai)", "a.i.",
    "artificial intelligence",
    "gen ai", "genai", "generative ai", "agentic ai", "ai agent",
    "machine learning", " ml ", " ml/", " ml,", "ai/ml",
    "llm", "large language model", "nlp", "natural language",
    "deep learning", "computer vision", "data science",
    "azure", "aws ", "aws,", "aws/", "aws-",
    "gcp", "google cloud",
    "cloud ", "cloud,", "cloud-", "cloud/",
    "solutions architect",
    "solution architect",
)

NON_TARGET_ROLES = (
    "ui developer", "ui engineer", "ui architect",
    "ux developer", "ux engineer", "ux designer",
    "frontend developer", "front end developer", "front-end developer",
    "react developer", "angular developer", "vue developer",
    "python developer", "java developer", "java engineer",
    ".net developer", "dotnet developer", "c# developer",
    "qa engineer", "qa analyst", "test engineer", "sdet",
    "database administrator", "dba",
    "network engineer", "network administrator",
    "help desk", "desktop support", "it support",
    "project manager", "scrum master", "business analyst",
    "salesforce", "sap ", "oracle erp",
)


def _is_ai_cloud_position(subject: str, body: str = "") -> bool:
    """Returns True only for AI, GenAI, Cloud positions."""
    text = " " + (subject + " " + body[:2000]).lower() + " "
    return any(kw in text for kw in AI_CLOUD_KEYWORDS)


def _email_passes_subject(subject: str) -> bool:
    """Basic subject line checks: not a reply, contains a role-related keyword."""
    subject_lower = (subject or "").lower()
    if "re:" in subject_lower:
        return False
    role_keywords = ("architect", "engineer", "developer", "consultant", "lead", "principal", "specialist")
    return any(kw in subject_lower for kw in role_keywords)


def _email_passes_date(date_str: str, hours_window: int = MAX_EMAIL_AGE_HOURS) -> bool:
    if not date_str:
        return False
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - dt).total_seconds() <= hours_window * 3600
    except Exception:
        return False


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


def _fetch_and_parse(
    mail: imaplib.IMAP4_SSL, uid: bytes, folder: str, hours_window: int,
) -> Dict[str, Any] | None:
    _, data = mail.fetch(uid, "(RFC822)")
    if not data or not data[0]:
        return None
    msg = email.message_from_bytes(data[0][1])
    from_email = _header_str(msg.get("From"))
    to_email = _header_str(msg.get("To"))
    subject = _header_str(msg.get("Subject"))
    date_str = _header_str(msg.get("Date"))
    message_id = _header_str(msg.get("Message-ID"))
    imap_uid = uid.decode() if isinstance(uid, bytes) else str(uid)

    if not _email_passes_domain(from_email):
        return None
    if not _email_passes_subject(subject):
        return None
    if not _email_passes_date(date_str, hours_window):
        return None

    body = _extract_body(msg)

    if not _is_ai_cloud_position(subject, body):
        logger.debug("Skipped (not AI/Cloud): %s", subject)
        return None

    return {
        "raw_email_body": body,
        "from_email": from_email,
        "to_email": to_email,
        "subject": subject,
        "date": date_str,
        "message_id": message_id,
        "imap_uid": imap_uid,
        "folder": folder,
    }


def _search_folder(
    mail: imaplib.IMAP4_SSL, folder: str, since_criteria: str, hours_window: int,
) -> List[Dict[str, Any]]:
    try:
        status, detail = mail.select(folder, readonly=True)
    except Exception as e:
        logger.warning("Folder '%s': select raised exception — %s", folder, e)
        return []
    if status != "OK":
        logger.warning("Folder '%s': select returned %s (%s) — skipping", folder, status, detail)
        return []

    _, message_numbers = mail.search(None, since_criteria)
    msg_ids = message_numbers[0].split()
    logger.info("Folder '%s': %d message(s) match %s", folder, len(msg_ids), since_criteria)
    results = []
    for uid in msg_ids:
        parsed = _fetch_and_parse(mail, uid, folder, hours_window)
        if parsed:
            results.append(parsed)
    logger.info("Folder '%s': %d passed all filters", folder, len(results))
    return results


def list_imap_folders() -> List[str]:
    """Return all folder/label names visible via IMAP (for the Folders dropdown)."""
    if not IMAP_USER or not IMAP_PASSWORD:
        return list(SCAN_FOLDERS)
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(IMAP_USER, IMAP_PASSWORD)
        _, folder_list = mail.list()
        mail.logout()
        folders = []
        for item in folder_list or []:
            line = item.decode() if isinstance(item, bytes) else str(item)
            # IMAP LIST response: (\Flags) "/" "folder name"  OR  (\Flags) "/" folder
            # Extract the last token — either quoted or unquoted.
            line = line.strip()
            if line.endswith('"'):
                # Quoted: grab everything between last pair of quotes
                name = line.rsplit('"', 2)[-2]
            else:
                # Unquoted: last space-separated token
                name = line.rsplit(' ', 1)[-1]
            if name and not name.startswith('[Gmail]'):
                folders.append(name)
        return sorted(folders) if folders else list(SCAN_FOLDERS)
    except Exception as e:
        logger.warning("Could not list IMAP folders: %s", e)
        return list(SCAN_FOLDERS)


def _scan_for_recruiter_emails(
    scan_folders: List[str] | None = None,
    scan_hours: int | None = None,
) -> List[Dict[str, Any]]:
    """Connect to Gmail, scan folders, apply recruiter filters.

    Folders and lookback window can be overridden per-request (UI selections);
    otherwise the config defaults are used.
    """
    if not IMAP_USER or not IMAP_PASSWORD:
        raise RuntimeError("IMAP_USER and IMAP_PASSWORD must be set in .env")

    folders_to_scan = list(scan_folders) if scan_folders else list(SCAN_FOLDERS)
    hours_window = scan_hours if (scan_hours and scan_hours > 0) else MAX_EMAIL_AGE_HOURS
    # Use per-run flag: when user explicitly picks folders, relax UNSEEN
    # requirement so already-read emails are still picked up.
    user_selected = bool(scan_folders)

    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(IMAP_USER, IMAP_PASSWORD)

    since = (datetime.now(timezone.utc) - timedelta(hours=hours_window)).strftime("%d-%b-%Y")
    # Default: UNSEEN only — once the app marks an email processed it marks
    # it \Seen so subsequent scans skip it automatically.
    # When the user explicitly selects folders they may have already-read
    # emails they want processed, so drop the UNSEEN requirement.
    since_criteria = f"(SINCE {since})" if user_selected else f"(UNSEEN SINCE {since})"

    all_emails: List[Dict[str, Any]] = []
    seen_message_ids = set()

    try:
        for folder_name in folders_to_scan:
            logger.info("Scanning folder: %s  (criteria: %s)", folder_name, since_criteria)
            for parsed in _search_folder(mail, folder_name, since_criteria, hours_window):
                mid = parsed.get("message_id", "")
                if mid and mid not in seen_message_ids:
                    seen_message_ids.add(mid)
                    all_emails.append(parsed)
    except Exception as e:
        logger.error("Error scanning folders: %s", e)

    mail.logout()
    logger.info("Found %d recruiter email(s)", len(all_emails))
    return all_emails


# ---------------------------------------------------------------------------
# Agent node function
# ---------------------------------------------------------------------------

def _is_processed(message_id: str) -> bool:
    """Check if an email was already processed in a previous run."""
    if not message_id:
        return False
    if not STATE_FILE_PATH.exists():
        return False
    try:
        state = json.loads(STATE_FILE_PATH.read_text(encoding="utf-8"))
        return message_id in state
    except (json.JSONDecodeError, OSError):
        return False


def scan_recruiter_emails(state: EmailPipelineState) -> Dict[str, Any]:
    """Scan Gmail for new recruiter emails and filter already-processed ones."""
    emails = _scan_for_recruiter_emails(
        scan_folders=state.get("scan_folders") or None,
        scan_hours=state.get("scan_hours") or None,
    )
    new_emails = [e for e in emails if not _is_processed(e.get("message_id", ""))]

    if not new_emails:
        logger.info("No new recruiter emails to process (found %d, all processed).", len(emails))
    else:
        logger.info("Found %d new email(s) out of %d.", len(new_emails), len(emails))

    return {
        "scanned_emails": new_emails,
        "current_email_index": 0,
        "current_email": {},
        "recruiter_processed": 0,
        "recruiter_scan_done": True,
    }
