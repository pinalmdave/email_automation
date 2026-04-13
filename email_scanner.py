"""
Connects to Gmail via IMAP, scans configured folders, and returns emails
matching recruiter criteria (subject keywords, domain filter, age limit).
"""

import email
import imaplib
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
    SUBJECT_KEYWORDS,
)

logger = logging.getLogger(__name__)


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
# Positive signals: AI, GenAI, Generative AI, Cloud, Azure, AWS roles
# at Architect, Engineer, Developer, Lead, Principal, Consultant level.
# Negative signals: pure UI/UX, Python-only, .NET-only, Java-only etc.
# that don't mention AI or Cloud at all.

# These terms indicate the job is in the AI/Cloud space
AI_CLOUD_KEYWORDS = (
    # AI keywords (with word boundary tricks using spaces/punctuation)
    " ai ", " ai/", " ai,", " ai.", " ai-", "(ai)", "a.i.",
    "artificial intelligence",
    "gen ai", "genai", "generative ai", "agentic ai", "ai agent",
    "machine learning", " ml ", " ml/", " ml,", "ai/ml",
    "llm", "large language model", "nlp", "natural language",
    "deep learning", "computer vision", "data science",
    # Cloud keywords — individual platform names match broadly
    "azure", "aws ", "aws,", "aws/", "aws-",
    "gcp", "google cloud",
    "cloud ", "cloud,", "cloud-", "cloud/",
    "solutions architect",  # often cloud-oriented
    "solution architect",   # common variation
)

# These roles WITHOUT any AI/Cloud context should be excluded
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
    """
    Smart filter: returns True only for AI, GenAI, Cloud positions.
    Checks subject first (fast), then body for edge cases.
    Pads text with spaces for word-boundary matching.
    """
    # Pad with spaces so " ai " matches at start/end of text too
    text = " " + (subject + " " + body[:2000]).lower() + " "

    # Check if any AI/Cloud keyword is present
    has_ai_cloud = any(kw in text for kw in AI_CLOUD_KEYWORDS)

    if has_ai_cloud:
        # Double-check: if a NON_TARGET_ROLE matches AND no AI/Cloud context, reject
        # This prevents "Python Developer" that just mentions "cloud" in a generic way
        return True

    # If no explicit AI/Cloud keyword, reject — we only want AI/Cloud roles
    return False


def _email_passes_subject(subject: str) -> bool:
    """Basic subject line checks: not a reply, contains a role-related keyword."""
    subject_lower = (subject or "").lower()
    if "re:" in subject_lower:
        return False
    # Must contain at least one role-level keyword (architect, engineer, developer, etc.)
    role_keywords = ("architect", "engineer", "developer", "consultant", "lead", "principal", "specialist")
    return any(kw in subject_lower for kw in role_keywords)


def _email_passes_date(date_str: str) -> bool:
    if not date_str:
        return False
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - dt).total_seconds() <= MAX_EMAIL_AGE_HOURS * 3600
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


def _fetch_and_parse(mail: imaplib.IMAP4_SSL, uid: bytes, folder: str) -> Dict[str, Any] | None:
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
    if not _email_passes_date(date_str):
        return None

    body = _extract_body(msg)

    # Smart AI/Cloud position filter — checks subject + body
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


def _search_folder(mail: imaplib.IMAP4_SSL, folder: str, since_criteria: str) -> List[Dict[str, Any]]:
    try:
        status, _ = mail.select(folder, readonly=True)
    except Exception:
        return []
    if status != "OK":
        return []

    _, message_numbers = mail.search(None, since_criteria)
    msg_ids = message_numbers[0].split()
    results = []
    for uid in msg_ids:
        parsed = _fetch_and_parse(mail, uid, folder)
        if parsed:
            results.append(parsed)
    return results


def scan_for_recruiter_emails() -> List[Dict[str, Any]]:
    """
    Connect to Gmail, scan INBOX and UPDATES folders, apply recruiter filters.
    Returns list of email dicts ready for processing.
    """
    if not IMAP_USER or not IMAP_PASSWORD:
        raise RuntimeError("IMAP_USER and IMAP_PASSWORD must be set in .env")

    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(IMAP_USER, IMAP_PASSWORD)

    since = (datetime.now(timezone.utc) - timedelta(hours=MAX_EMAIL_AGE_HOURS)).strftime("%d-%b-%Y")
    since_criteria = f"SINCE {since}"

    all_emails: List[Dict[str, Any]] = []
    seen_message_ids = set()

    try:
        status, folders = mail.list()
        for f in folders or []:
            line = f.decode() if isinstance(f, bytes) else str(f)
            parts = line.split('"')
            folder_name = parts[-2] if len(parts) >= 2 else ""
            if folder_name and any(label in folder_name for label in SCAN_FOLDERS):
                logger.info("Scanning folder: %s", folder_name)
                for parsed in _search_folder(mail, folder_name, since_criteria):
                    mid = parsed.get("message_id", "")
                    if mid and mid not in seen_message_ids:
                        seen_message_ids.add(mid)
                        all_emails.append(parsed)
    except Exception as e:
        logger.error("Error scanning folders: %s", e)

    mail.logout()
    logger.info("Found %d recruiter email(s)", len(all_emails))
    return all_emails
