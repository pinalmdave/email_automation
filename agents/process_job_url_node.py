"""
Process Job URL Node — handles a job-posting URL pasted by the user.

Fetches the page, extracts the JD text, creates an apply_plan record, and
loads the JD into `current_email` so the existing generate_resume_agent
and evaluate_resume_agent can run unchanged. When the flow completes,
api.server links the rendered resume back to the apply_plan entry and
flips it to "ready".

No LLM call here — plain state-shaping node.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

import apply_plans
from graph.state import EmailPipelineState
from jd_fetch import fetch_job_posting

logger = logging.getLogger(__name__)


def process_job_url(state: EmailPipelineState) -> Dict[str, Any]:
    """Fetch URL → create apply plan → shape as recruiter email for the resume pipeline."""
    url = (state.get("job_url") or "").strip()
    if not url:
        logger.warning("process_job_url invoked with empty URL")
        return {"job_url_fetched": True}

    logger.info("Fetching job posting: %s", url)
    fetched = fetch_job_posting(url)
    logger.info(
        "Fetched: source=%s title=%s company=%s chars=%d error=%s",
        fetched["source"], fetched["job_title"], fetched["company_name"],
        len(fetched["jd_text"]), fetched["error"] or "-",
    )

    jd_text = fetched["jd_text"] or url  # Fall back to URL if we got nothing useful.
    subject = fetched["job_title"] or f"Apply: {fetched['source']}"

    plan = apply_plans.create(
        job_url=url,
        job_title=fetched["job_title"],
        company_name=fetched["company_name"],
        source=fetched["source"],
        jd_text=jd_text,
        status="planning",
    )

    synthetic_email = {
        "raw_email_body": jd_text,
        "from_email": f"apply+{fetched['source'].lower()}@local",
        "to_email": "",
        "subject": subject,
        "date": datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000"),
        "message_id": f"<apply-url-{uuid.uuid4()}@local>",
        "imap_uid": "",
        "folder": "APPLY_URL",
    }
    return {
        "current_email": synthetic_email,
        "job_url_fetched": True,
        "apply_plan_id": plan["id"],
    }
