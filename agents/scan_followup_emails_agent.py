"""
Scan Follow-up Emails Agent — finds reply emails from known recruiters.
"""

import logging
from typing import Any, Dict

from graph.state import EmailPipelineState

logger = logging.getLogger(__name__)


def scan_followup_emails(state: EmailPipelineState) -> Dict[str, Any]:
    """Scan Gmail for follow-up emails from known recruiters."""
    from followup_handler import scan_for_followup_emails, _is_followup_processed

    followups = scan_for_followup_emails()
    new_followups = [f for f in followups if not _is_followup_processed(f.get("message_id", ""))]

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
