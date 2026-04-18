"""
Gmail IMAP helpers — apply the CLAUDE_PROCESSED label to an original
recruiter email and mark it as read, so subsequent scans (which use the
UNSEEN filter) skip it.

Called after a pending reply is successfully queued. Failures are logged
but never raise — we don't want a labeling glitch to block the pipeline.
"""

import imaplib
import logging
from typing import Optional

from config import IMAP_HOST, IMAP_PASSWORD, IMAP_PORT, IMAP_USER

logger = logging.getLogger(__name__)

CLAUDE_PROCESSED_LABEL = "CLAUDE_PROCESSED"


def mark_email_processed(folder: str, imap_uid: str, label: str = CLAUDE_PROCESSED_LABEL) -> Optional[str]:
    """
    Mark the given email \\Seen and copy it to the given label.

    Gmail treats IMAP folders and labels interchangeably: copying a message
    to a non-existent folder auto-creates the label (for user labels).

    Returns None on full success, error string on partial/failure.
    """
    if not imap_uid or not folder:
        return "missing folder or imap_uid"
    if not IMAP_USER or not IMAP_PASSWORD:
        return "IMAP credentials not configured"

    uid_bytes = imap_uid.encode() if isinstance(imap_uid, str) else imap_uid

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(IMAP_USER, IMAP_PASSWORD)
    except Exception as exc:  # noqa: BLE001
        logger.warning("IMAP login failed while marking processed: %s", exc)
        return f"login failed: {exc}"

    errs = []
    try:
        try:
            status, _ = mail.select(folder, readonly=False)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"select {folder}: {exc}")
            status = "NO"

        if status == "OK":
            try:
                mail.store(uid_bytes, "+FLAGS", "\\Seen")
            except Exception as exc:  # noqa: BLE001
                errs.append(f"store Seen: {exc}")

            # Gmail auto-creates user labels on first copy; a missing label
            # copy raises imaplib.error which we treat as a warning only.
            try:
                mail.copy(uid_bytes, label)
            except Exception as exc:  # noqa: BLE001
                errs.append(f"copy to {label}: {exc}")
                logger.warning(
                    "Could not apply label %s — create it in Gmail (Labels > Create new) if missing",
                    label,
                )
        else:
            errs.append(f"folder select status={status}")
    finally:
        try:
            mail.logout()
        except Exception:
            pass

    if errs:
        return "; ".join(errs)
    logger.info("Gmail: marked %s as \\Seen + labeled %s in %s", imap_uid, label, folder)
    return None
