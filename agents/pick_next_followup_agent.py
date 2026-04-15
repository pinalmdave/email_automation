"""
Pick Next Follow-up Agent — advances the iterator to the next follow-up email.
"""

import logging
from typing import Any, Dict

from graph.state import EmailPipelineState

logger = logging.getLogger(__name__)


def pick_next_followup(state: EmailPipelineState) -> Dict[str, Any]:
    """Load the next follow-up email into current_followup."""
    idx = state.get("current_followup_index", 0)
    followups = state.get("followup_emails", [])

    if idx < len(followups):
        followup = followups[idx]
        total = len(followups)
        logger.info(
            "[Follow-up %d/%d] %s from %s",
            idx + 1, total,
            followup.get("subject", "(no subject)"),
            followup.get("from_email", "(unknown)"),
        )
        return {"current_followup": followup}

    # No more follow-ups — clear current so supervisor moves on
    return {"current_followup": {}}
