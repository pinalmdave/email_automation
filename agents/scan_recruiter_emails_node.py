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
    IMAP_PORT,
    MAX_EMAIL_AGE_HOURS,
    SCAN_FOLDERS,
    STATE_FILE_PATH,
)
from email_accounts import get_active_credentials
from gmail_mark import CLAUDE_PROCESSED_LABEL
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


def _email_passes_roles(subject: str, body: str, target_roles: List[str]) -> bool:
    """When the user supplies target roles, an email qualifies only if its
    subject matches one of them (e.g. 'AI Architect', 'Cloud Architect').
    With no target roles, fall back to the built-in AI/Cloud filter."""
    roles = [r.strip().lower() for r in (target_roles or []) if r and r.strip()]
    if not roles:
        return _is_ai_cloud_position(subject, body)
    text = " " + (subject or "").lower() + " "
    return any(role in text for role in roles)


# --- Job-location extraction (heuristic, no LLM) ------------------------------
_REMOTE_RE = re.compile(
    r"\b(100%\s*remote|fully\s*remote|remote\s*(?:position|role|opportunity|job|work)?|"
    r"work\s*from\s*home|telecommut\w*|\bwfh\b)\b",
    re.I,
)
# "Location: City, ST"  /  "based in City, ST"  /  "onsite in City, ST"
_LABELED_LOC_RE = re.compile(
    r"(?:location|located in|based in|onsite in|office in|position is in)\s*[:\-]?\s*"
    r"([A-Za-z][A-Za-z .'\-]{1,40},\s*[A-Za-z]{2,})",
    re.I,
)
# Generic "City, ST" (two-letter state)
_CITY_ST_RE = re.compile(r"\b([A-Z][a-zA-Z.'\-]+(?:\s+[A-Z][a-zA-Z.'\-]+){0,2},\s*[A-Z]{2})\b")


def _clean_loc(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip(" .,-")


def _extract_job_location(subject: str, body: str) -> str:
    """Best-effort job location from subject/body. Returns '' if undeterminable."""
    text = (subject or "") + "  " + (body or "")[:4000]
    m = _LABELED_LOC_RE.search(text)
    if m:
        return _clean_loc(m.group(1))
    if _REMOTE_RE.search(text):
        return "Remote"
    m = _CITY_ST_RE.search(text)
    if m:
        return _clean_loc(m.group(1))
    return ""


def _email_passes_location(detected_loc: str, location_filter: str) -> bool:
    """Apply the user's job-location filter.

    - No filter -> everything passes.
    - Unknown location -> always passes (process it too, per requirement).
    - 'remote' filter -> only emails whose detected location is Remote.
    - Otherwise -> substring match against the detected location.
    """
    f = (location_filter or "").strip().lower()
    if not f:
        return True
    if not detected_loc:
        return True
    dl = detected_loc.lower()
    if f in ("remote", "remote only", "wfh", "work from home", "telecommute"):
        return "remote" in dl
    return f in dl


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
    target_roles: List[str] | None = None, location_filter: str = "",
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
    # Skip replies regardless of role filter.
    if "re:" in (subject or "").lower():
        return None
    if not _email_passes_date(date_str, hours_window):
        return None

    body = _extract_body(msg)

    if not _email_passes_roles(subject, body, target_roles or []):
        logger.debug("Skipped (role filter): %s", subject)
        return None

    job_location = _extract_job_location(subject, body)
    if not _email_passes_location(job_location, location_filter):
        logger.debug("Skipped (location filter '%s' vs '%s'): %s", location_filter, job_location, subject)
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
        "job_location": job_location,
    }


def _folder_search(mail: imaplib.IMAP4_SSL, gmail_query: str, since_criteria: str):
    """Search a selected folder, preferring Gmail's X-GM-RAW (so we can exclude
    the CLAUDE_PROCESSED label server-side). Falls back to a plain IMAP search
    if the Gmail extension isn't available."""
    try:
        typ, nums = mail.search(None, "X-GM-RAW", f'"{gmail_query}"')
        if typ == "OK":
            return nums
    except Exception as e:  # noqa: BLE001
        logger.debug("X-GM-RAW search unavailable (%s) — falling back to IMAP search", e)
    return mail.search(None, since_criteria)[1]


def _search_folder(
    mail: imaplib.IMAP4_SSL, folder: str, gmail_query: str, since_criteria: str,
    hours_window: int, target_roles: List[str] | None = None, location_filter: str = "",
) -> List[Dict[str, Any]]:
    try:
        status, detail = mail.select(folder, readonly=True)
    except Exception as e:
        logger.warning("Folder '%s': select raised exception — %s", folder, e)
        return []
    if status != "OK":
        logger.warning("Folder '%s': select returned %s (%s) — skipping", folder, status, detail)
        return []

    message_numbers = _folder_search(mail, gmail_query, since_criteria)
    msg_ids = message_numbers[0].split() if message_numbers and message_numbers[0] else []
    logger.info("Folder '%s': %d message(s) match query", folder, len(msg_ids))
    results = []
    for uid in msg_ids:
        parsed = _fetch_and_parse(mail, uid, folder, hours_window, target_roles, location_filter)
        if parsed:
            results.append(parsed)
    logger.info("Folder '%s': %d passed all filters", folder, len(results))
    return results


def list_imap_folders() -> List[str]:
    """Return all folder/label names visible via IMAP (for the Folders dropdown)."""
    imap_user, imap_password = get_active_credentials()
    if not imap_user or not imap_password:
        return list(SCAN_FOLDERS)
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(imap_user, imap_password)
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
    target_roles: List[str] | None = None,
    unread_only: bool = True,
    location_filter: str = "",
) -> List[Dict[str, Any]]:
    """Connect to Gmail, scan folders, apply recruiter filters.

    Dedup is primarily server-side: the Gmail query excludes anything already
    tagged CLAUDE_PROCESSED (applied by the app after it queues a reply), so
    previously-processed emails are never re-fetched regardless of read state.
    """
    imap_user, imap_password = get_active_credentials()
    if not imap_user or not imap_password:
        raise RuntimeError("No connected email account (set IMAP_USER/IMAP_PASSWORD or add an account)")

    folders_to_scan = list(scan_folders) if scan_folders else list(SCAN_FOLDERS)
    hours_window = scan_hours if (scan_hours and scan_hours > 0) else MAX_EMAIL_AGE_HOURS

    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(imap_user, imap_password)

    # Gmail search (X-GM-RAW): lookback window + exclude already-processed.
    # newer_than uses day granularity; the precise hours filter is applied
    # per-email in _fetch_and_parse.
    days = max(1, (hours_window + 23) // 24)
    gmail_query = f"newer_than:{days}d -label:{CLAUDE_PROCESSED_LABEL}"
    if unread_only:
        gmail_query += " is:unread"

    # Plain-IMAP fallback (no Gmail extensions): SINCE + optional UNSEEN.
    since = (datetime.now(timezone.utc) - timedelta(hours=hours_window)).strftime("%d-%b-%Y")
    since_criteria = f"(UNSEEN SINCE {since})" if unread_only else f"(SINCE {since})"

    all_emails: List[Dict[str, Any]] = []
    seen_message_ids = set()

    try:
        for folder_name in folders_to_scan:
            logger.info("Scanning folder: %s  (gmail: %s)", folder_name, gmail_query)
            for parsed in _search_folder(mail, folder_name, gmail_query, since_criteria,
                                         hours_window, target_roles, location_filter):
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
        target_roles=state.get("target_roles") or None,
        unread_only=state.get("scan_unread_only", True),
        location_filter=state.get("job_location_filter") or "",
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
