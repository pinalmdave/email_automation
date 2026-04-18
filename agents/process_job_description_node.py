"""
Process Job Description Node — handles a job description pasted by the user
via the UI. Converts the raw JD text into a `current_email`-shaped dict so
the existing generate_resume_agent can reuse its pipeline unchanged.

No LLM call here — this is a plain state-shaping node.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from config import IMAP_USER
from graph.state import EmailPipelineState

logger = logging.getLogger(__name__)


def _first_nonempty_line(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:200]
    return fallback


def process_job_description(state: EmailPipelineState) -> Dict[str, Any]:
    """Wrap a user-pasted job description as a synthetic recruiter email."""
    jd_text = (state.get("job_description_text") or "").strip()
    if not jd_text:
        logger.warning("process_job_description invoked with empty JD text")
        return {"job_description_done": True}

    subject = _first_nonempty_line(jd_text, "Manual Job Description")
    synthetic_email = {
        "raw_email_body": jd_text,
        "from_email": "manual-jd@local",
        "to_email": IMAP_USER or "user@local",
        "subject": subject,
        "date": datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000"),
        "message_id": f"<manual-jd-{uuid.uuid4()}@local>",
        "imap_uid": "",
        "folder": "MANUAL_JD",
    }
    logger.info("Manual JD loaded (%d chars) — subject: %s", len(jd_text), subject)
    return {
        "current_email": synthetic_email,
        "job_description_done": True,
    }
