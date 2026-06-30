"""
Connected email accounts store.

Lets the user connect more than one Gmail account (email + App Password) and
pick which one the pipeline uses. One account is "active" at a time; all IMAP
and SMTP operations resolve their credentials through get_active_credentials().

If no accounts have been added, we fall back to the env-configured
IMAP_USER / IMAP_PASSWORD (config defaults / Azure App Settings) so existing
single-account behavior keeps working unchanged.

Persistence: JSON on disk, mirrored to Azure Blob (same pattern as the other
state files). App passwords are stored as-is (they are scoped, revocable
Gmail App Passwords) and are NEVER returned by the list API — only masked.
"""

import imaplib
import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from config import (
    EMAIL_ACCOUNTS_PATH,
    IMAP_HOST,
    IMAP_PASSWORD,
    IMAP_PORT,
    IMAP_USER,
)

logger = logging.getLogger(__name__)

_lock = threading.RLock()


def _load() -> List[Dict[str, Any]]:
    if not EMAIL_ACCOUNTS_PATH.exists():
        return []
    try:
        data = json.loads(EMAIL_ACCOUNTS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save(items: List[Dict[str, Any]]) -> None:
    try:
        EMAIL_ACCOUNTS_PATH.write_text(
            json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("Could not persist email_accounts locally: %s", exc)
        return
    try:
        from blob_storage import upload_state_file
        upload_state_file(EMAIL_ACCOUNTS_PATH)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Blob sync of email_accounts skipped: %s", exc)


def _mask(pw: str) -> str:
    if not pw:
        return ""
    return ("•" * max(0, len(pw) - 4)) + pw[-4:]


def _public(item: Dict[str, Any]) -> Dict[str, Any]:
    """Account shape returned to the UI — password masked, never raw."""
    return {
        "id": item.get("id", ""),
        "email": item.get("email", ""),
        "active": bool(item.get("active", False)),
        "added_at": item.get("added_at", ""),
        "password_masked": _mask(item.get("app_password", "")),
    }


def verify_credentials(email: str, app_password: str) -> Optional[str]:
    """Try an IMAP login. Returns None on success, an error string on failure."""
    try:
        m = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        m.login(email, app_password)
        m.logout()
        return None
    except imaplib.IMAP4.error as exc:
        return f"IMAP login failed: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"Could not connect: {exc}"


def list_accounts() -> List[Dict[str, Any]]:
    """All connected accounts (masked). Includes the env default as a
    read-only pseudo-account when no accounts have been added yet."""
    with _lock:
        items = _load()
    if items:
        return [_public(i) for i in items]
    # No stored accounts — surface the env-configured account (if any) so the
    # UI shows what's actually being used.
    if IMAP_USER:
        return [{
            "id": "__env__",
            "email": IMAP_USER,
            "active": True,
            "added_at": "",
            "password_masked": _mask(IMAP_PASSWORD),
            "env_default": True,
        }]
    return []


def add_account(email: str, app_password: str) -> Dict[str, Any]:
    """Verify + add an account. First account becomes active. Returns public shape.

    Raises ValueError on validation/credential failure.
    """
    email = (email or "").strip()
    app_password = (app_password or "").replace(" ", "").strip()
    if not email or "@" not in email:
        raise ValueError("A valid email address is required")
    if not app_password:
        raise ValueError("An app password is required")

    err = verify_credentials(email, app_password)
    if err:
        raise ValueError(err)

    with _lock:
        items = _load()
        if any(i.get("email", "").lower() == email.lower() for i in items):
            raise ValueError(f"{email} is already connected")
        make_active = len(items) == 0
        item = {
            "id": str(uuid.uuid4()),
            "email": email,
            "app_password": app_password,
            "active": make_active,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        if make_active:
            for i in items:
                i["active"] = False
        items.append(item)
        _save(items)
    logger.info("Connected email account: %s (active=%s)", email, item["active"])
    return _public(item)


def set_active(account_id: str) -> bool:
    with _lock:
        items = _load()
        if not any(i.get("id") == account_id for i in items):
            return False
        for i in items:
            i["active"] = (i.get("id") == account_id)
        _save(items)
    logger.info("Active email account set: %s", account_id)
    return True


def delete_account(account_id: str) -> bool:
    with _lock:
        items = _load()
        new_items = [i for i in items if i.get("id") != account_id]
        if len(new_items) == len(items):
            return False
        # If we removed the active account, promote the first remaining one.
        if new_items and not any(i.get("active") for i in new_items):
            new_items[0]["active"] = True
        _save(new_items)
    logger.info("Removed email account: %s", account_id)
    return True


def get_active_credentials() -> Tuple[str, str]:
    """Resolve (user, app_password) for IMAP/SMTP.

    Active stored account wins; otherwise fall back to env-configured creds.
    """
    with _lock:
        items = _load()
    for i in items:
        if i.get("active") and i.get("email") and i.get("app_password"):
            return i["email"], i["app_password"]
    # Fall back to the first stored account, then env defaults.
    for i in items:
        if i.get("email") and i.get("app_password"):
            return i["email"], i["app_password"]
    return IMAP_USER, IMAP_PASSWORD
