"""
Scan Recruiter Emails Agent — connects to Gmail and fetches new recruiter emails.
"""

import logging
from typing import Any, Dict

from graph.state import EmailPipelineState

logger = logging.getLogger(__name__)


def scan_recruiter_emails(state: EmailPipelineState) -> Dict[str, Any]:
    """Scan Gmail for new recruiter emails and filter already-processed ones."""
    from email_scanner import scan_for_recruiter_emails
    from state_tracker import is_processed

    emails = scan_for_recruiter_emails()
    new_emails = [e for e in emails if not is_processed(e.get("message_id", ""))]

    if not new_emails:
        logger.info("No new recruiter emails to process (found %d, all processed).", len(emails))
    else:
        logger.info("Found %d new email(s) out of %d.", len(new_emails), len(emails))

    return {
        "scanned_emails": new_emails,
        "current_email_index": 0,
        "current_email": {},
        "phase1_processed": 0,
        "recruiter_scan_done": True,
    }
