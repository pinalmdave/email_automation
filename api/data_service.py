"""
Read-only data layer for the Smart Email App API.
Reads from JSON state files and the resume output directory.
"""

import json
import os
import re
from datetime import datetime, timezone
from email.header import decode_header
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import FOLLOWUP_STATE_PATH, RESUME_OUTPUT_DIR, STATE_FILE_PATH


def _load_json(path: Path) -> Dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _decode_mime_header(value: str) -> str:
    """Decode MIME-encoded header values like =?UTF-8?q?...?= into plain text."""
    if not value or "=?" not in value:
        # Strip stray \r\n even from non-MIME headers
        return value.replace("\r\n", " ").replace("\n", " ").strip() if value else ""
    try:
        parts = decode_header(value)
        decoded_parts = []
        for data, charset in parts:
            if isinstance(data, bytes):
                decoded_parts.append(data.decode(charset or "utf-8", errors="replace"))
            else:
                decoded_parts.append(data)
        result = " ".join(decoded_parts)
        return result.replace("\r\n", " ").replace("\n", " ").strip()
    except Exception:
        return value.replace("\r\n", " ").replace("\n", " ").strip()


def _clean_email_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Decode MIME headers and clean up fields for API responses."""
    if "subject" in entry:
        entry["subject"] = _decode_mime_header(entry["subject"])
    if "from_email" in entry:
        entry["from_email"] = _decode_mime_header(entry["from_email"])
    # Ensure resume_file only contains the filename for the API
    if entry.get("resume_file"):
        entry["resume_file"] = Path(entry["resume_file"]).name
    return entry


# ---------------------------------------------------------------------------
# Emails
# ---------------------------------------------------------------------------

def get_all_emails() -> List[Dict[str, Any]]:
    """Return all processed emails as a list of dicts (message_id added as field)."""
    state = _load_json(STATE_FILE_PATH)
    results = []
    for message_id, data in state.items():
        entry = dict(data)
        entry["message_id"] = message_id
        _clean_email_entry(entry)
        results.append(entry)
    return results


def get_email(message_id: str) -> Optional[Dict[str, Any]]:
    """Return a single email dict by message_id, or None."""
    state = _load_json(STATE_FILE_PATH)
    data = state.get(message_id)
    if data is None:
        return None
    entry = dict(data)
    entry["message_id"] = message_id
    _clean_email_entry(entry)
    return entry


# ---------------------------------------------------------------------------
# Follow-ups
# ---------------------------------------------------------------------------

def get_all_followups() -> List[Dict[str, Any]]:
    """Return all follow-ups as a list of dicts."""
    state = _load_json(FOLLOWUP_STATE_PATH)
    results = []
    for message_id, data in state.items():
        entry = dict(data)
        entry["message_id"] = message_id
        _clean_email_entry(entry)
        results.append(entry)
    return results


# ---------------------------------------------------------------------------
# Resumes (delegates to blob_storage for Azure/local abstraction)
# ---------------------------------------------------------------------------

def list_resumes() -> List[Dict[str, Any]]:
    """List all DOCX resume files with metadata."""
    from blob_storage import list_resumes as blob_list_resumes
    return blob_list_resumes()


def get_resume_path(filename: str) -> Optional[Path]:
    """Return a local file path for a resume (downloads from blob if needed)."""
    from blob_storage import get_resume_local_path
    safe_name = Path(filename).name
    if safe_name != filename or ".." in filename:
        return None
    return get_resume_local_path(safe_name)


# ---------------------------------------------------------------------------
# Conversations (grouped by recruiter)
# ---------------------------------------------------------------------------

def _extract_email_addr(from_field: str) -> str:
    """Extract bare email address from a From header."""
    match = re.search(r"<([^>]+)>", from_field)
    return match.group(1).lower().strip() if match else from_field.lower().strip()


def _extract_name(from_field: str) -> str:
    """Extract display name from a From header."""
    match = re.match(r'^"?([^"<]+)"?\s*<', from_field)
    if match:
        return match.group(1).strip()
    return from_field.strip()


def get_conversations() -> List[Dict[str, Any]]:
    """Group emails + followups by sender email, return conversation summaries."""
    emails = get_all_emails()
    followups = get_all_followups()

    convos: Dict[str, Dict[str, Any]] = {}

    for e in emails:
        addr = _extract_email_addr(e.get("from_email", ""))
        if not addr:
            continue
        if addr not in convos:
            convos[addr] = {
                "recruiter_email": addr,
                "recruiter_name": _extract_name(e.get("from_email", "")),
                "latest_subject": e.get("subject", ""),
                "message_count": 0,
                "last_activity": e.get("processed_at", ""),
                "messages": [],
            }
        convos[addr]["message_count"] += 1
        convos[addr]["messages"].append(e)
        if e.get("processed_at", "") > convos[addr]["last_activity"]:
            convos[addr]["last_activity"] = e["processed_at"]
            convos[addr]["latest_subject"] = e.get("subject", "")

    # Followups don't have from_email directly; they're keyed by message_id.
    # Match them to emails by checking the processed_emails state.
    email_lookup = {e["message_id"]: e for e in emails}
    for f in followups:
        # Try to find the original email to get the sender
        mid = f.get("message_id", "")
        matched_email = email_lookup.get(mid)
        if matched_email:
            addr = _extract_email_addr(matched_email.get("from_email", ""))
        else:
            # Followups might not match directly; skip if we can't associate
            continue

        if addr and addr in convos:
            convos[addr]["message_count"] += 1
            convos[addr]["messages"].append(f)
            if f.get("processed_at", "") > convos[addr]["last_activity"]:
                convos[addr]["last_activity"] = f["processed_at"]

    # Return without the messages list in the summary
    results = []
    for c in convos.values():
        results.append({
            "recruiter_email": c["recruiter_email"],
            "recruiter_name": c["recruiter_name"],
            "latest_subject": c["latest_subject"],
            "message_count": c["message_count"],
            "last_activity": c["last_activity"],
        })

    results.sort(key=lambda x: x["last_activity"], reverse=True)
    return results


def get_conversation(recruiter_email: str) -> List[Dict[str, Any]]:
    """Return all messages for a single recruiter, sorted by date."""
    emails = get_all_emails()
    followups = get_all_followups()

    messages = []
    recruiter_email_lower = recruiter_email.lower().strip()

    for e in emails:
        addr = _extract_email_addr(e.get("from_email", ""))
        if addr == recruiter_email_lower:
            entry = dict(e)
            entry["type"] = "email"
            messages.append(entry)

    email_lookup = {e["message_id"]: e for e in emails}
    for f in followups:
        mid = f.get("message_id", "")
        matched_email = email_lookup.get(mid)
        if matched_email:
            addr = _extract_email_addr(matched_email.get("from_email", ""))
            if addr == recruiter_email_lower:
                entry = dict(f)
                entry["type"] = "followup"
                messages.append(entry)

    messages.sort(key=lambda x: x.get("processed_at", ""))
    return messages
