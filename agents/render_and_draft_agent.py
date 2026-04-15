"""
Render and Draft Agent — creates a Gmail draft with the resume attached.
"""

import logging
from typing import Any, Dict

from graph.state import EmailPipelineState

logger = logging.getLogger(__name__)


def render_and_draft(state: EmailPipelineState) -> Dict[str, Any]:
    """Create a Gmail draft with the resume attached and mark the email processed."""
    from pathlib import Path

    from email_drafter import create_draft_reply
    from state_tracker import mark_processed

    email_data = state["current_email"]
    resume_json = state.get("resume_json", {})
    resume_path_str = state.get("resume_path", "")
    idx = state.get("current_email_index", 0)
    processed = state.get("phase1_processed", 0)

    if not resume_path_str or not resume_json:
        # Resume generation failed — skip drafting, advance index, clear current
        return {
            "current_email_index": idx + 1,
            "current_email": {},
            "resume_json": {},
            "resume_path": "",
        }

    resume_path = Path(resume_path_str)
    message_id = email_data.get("message_id", "")
    subject = email_data.get("subject", "")
    from_email = email_data.get("from_email", "")

    try:
        logger.info("  Creating Gmail draft...")
        create_draft_reply(email_data, resume_json, resume_path)
        mark_processed(message_id, subject, from_email, str(resume_path))
        logger.info("  Done! Resume: %s", resume_path.name)
        return {
            "current_email_index": idx + 1,
            "current_email": {},
            "resume_json": {},
            "resume_path": "",
            "phase1_processed": processed + 1,
        }
    except Exception as e:
        logger.error("  FAILED to draft for '%s': %s", subject, e, exc_info=True)
        return {
            "current_email_index": idx + 1,
            "current_email": {},
            "resume_json": {},
            "resume_path": "",
            "errors": [f"Draft creation failed for '{subject}': {e}"],
        }
