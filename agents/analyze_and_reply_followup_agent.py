"""
Analyze and Reply Follow-up Agent — uses Claude AI to understand recruiter
intent and generate an intelligent reply draft.
"""

import logging
from typing import Any, Dict

from graph.state import EmailPipelineState

logger = logging.getLogger(__name__)


def analyze_and_reply_followup(state: EmailPipelineState) -> Dict[str, Any]:
    """Analyze follow-up intent with Claude and create a reply draft."""
    from followup_handler import (
        create_followup_draft,
        generate_followup_reply,
        _mark_followup_processed,
    )

    followup = state["current_followup"]
    idx = state.get("current_followup_index", 0)
    processed = state.get("phase2_processed", 0)
    message_id = followup.get("message_id", "")
    subject = followup.get("subject", "?")

    try:
        reply_result = generate_followup_reply(followup)
        create_followup_draft(followup, reply_result)
        _mark_followup_processed(
            message_id,
            reply_result.get("intent", "UNKNOWN"),
            reply_result.get("summary", ""),
        )
        logger.info("  Done! Intent: %s", reply_result.get("intent"))
        return {
            "current_followup_index": idx + 1,
            "current_followup": {},
            "phase2_processed": processed + 1,
        }
    except Exception as e:
        logger.error("  FAILED: %s", e, exc_info=True)
        return {
            "current_followup_index": idx + 1,
            "current_followup": {},
            "errors": [f"Follow-up failed for '{subject}': {e}"],
        }
