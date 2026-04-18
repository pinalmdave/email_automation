"""
Pending-replies store — the human-in-the-loop queue.

Replaces the old "auto-create Gmail draft" behavior. When a resume is
generated (recruiter path) or a follow-up intent is classified, we persist
a pending reply here instead of pushing a draft to Gmail. The UI
presents each pending item with edit/approve/cancel controls; on
approve the backend sends the email via SMTP.

Persistence is JSON on disk with synchronous blob mirroring via
blob_storage.upload_state_file — same pattern as processed_emails.json
and usage_totals.json.
"""

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import PENDING_REPLIES_PATH

logger = logging.getLogger(__name__)

_lock = threading.RLock()


def _load() -> List[Dict[str, Any]]:
    if not PENDING_REPLIES_PATH.exists():
        return []
    try:
        data = json.loads(PENDING_REPLIES_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save(items: List[Dict[str, Any]]) -> None:
    try:
        PENDING_REPLIES_PATH.write_text(
            json.dumps(items, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Could not persist pending_replies locally: %s", exc)
        return
    try:
        from blob_storage import upload_state_file
        upload_state_file(PENDING_REPLIES_PATH)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Blob sync of pending_replies skipped: %s", exc)


def list_pending(status: Optional[str] = "pending") -> List[Dict[str, Any]]:
    """Return pending replies (optionally filtered by status)."""
    with _lock:
        items = _load()
    if status is None:
        return items
    return [i for i in items if i.get("status") == status]


def get(reply_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        for item in _load():
            if item.get("id") == reply_id:
                return item
    return None


def create(
    *,
    kind: str,                      # "recruiter_initial" | "followup"
    original_message_id: str,
    original_from: str,
    original_subject: str,
    original_date: str,
    original_imap_uid: str,
    original_folder: str,
    reply_to: str,
    reply_subject: str,
    reply_body: str,
    resume_path: Optional[str] = None,
    intent: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Insert a new pending reply, return it."""
    item = {
        "id": str(uuid.uuid4()),
        "kind": kind,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "original": {
            "message_id": original_message_id,
            "from_email": original_from,
            "subject": original_subject,
            "date": original_date,
            "imap_uid": original_imap_uid,
            "folder": original_folder,
        },
        "reply": {
            "to": reply_to,
            "subject": reply_subject,
            "body": reply_body,
        },
        "resume_path": resume_path or "",
        "intent": intent or "",
    }
    if extra:
        item.update(extra)

    with _lock:
        items = _load()
        items.insert(0, item)  # newest first
        _save(items)
    logger.info("Pending reply queued: id=%s kind=%s subject=%s",
                item["id"], kind, reply_subject)
    return item


def update_reply_text(reply_id: str, subject: Optional[str], body: Optional[str]) -> Optional[Dict[str, Any]]:
    """User edited the draft — update subject/body."""
    with _lock:
        items = _load()
        for item in items:
            if item.get("id") == reply_id:
                if subject is not None:
                    item["reply"]["subject"] = subject
                if body is not None:
                    item["reply"]["body"] = body
                item["updated_at"] = datetime.now(timezone.utc).isoformat()
                _save(items)
                return item
    return None


def mark_status(reply_id: str, status: str, **extra: Any) -> Optional[Dict[str, Any]]:
    """Move reply to approved | sent | cancelled; merge extra fields."""
    with _lock:
        items = _load()
        for item in items:
            if item.get("id") == reply_id:
                item["status"] = status
                item["updated_at"] = datetime.now(timezone.utc).isoformat()
                for k, v in extra.items():
                    item[k] = v
                _save(items)
                return item
    return None
