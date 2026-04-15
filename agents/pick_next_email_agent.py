"""
Pick Next Email Agent — advances the iterator to the next recruiter email.
"""

import logging
from typing import Any, Dict

from graph.state import EmailPipelineState

logger = logging.getLogger(__name__)


def pick_next_email(state: EmailPipelineState) -> Dict[str, Any]:
    """Load the next email from the scanned list into current_email."""
    idx = state.get("current_email_index", 0)
    emails = state.get("scanned_emails", [])

    if idx < len(emails):
        email_data = emails[idx]
        total = len(emails)
        logger.info(
            "[%d/%d] Processing: %s from %s",
            idx + 1, total,
            email_data.get("subject", "(no subject)"),
            email_data.get("from_email", "(unknown)"),
        )
        return {"current_email": email_data}

    # No more emails — clear current so supervisor moves on
    return {"current_email": {}}
