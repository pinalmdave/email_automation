"""
Supervisor Agent — intelligent central router for the email pipeline.

Inspects the current state and decides which agent to invoke next.
Every other agent returns to the supervisor after completing its work.
No rigid phase ordering — the supervisor reasons about what needs to happen.
"""

import logging
from typing import Any, Dict

from graph.state import EmailPipelineState

logger = logging.getLogger(__name__)

# The supervisor returns a `next_agent` value that the graph's conditional
# edge uses to route to the correct node.

AGENT_SCAN_RECRUITER  = "scan_recruiter_emails_agent"
AGENT_PICK_EMAIL      = "pick_next_email_agent"
AGENT_GENERATE_RESUME = "generate_resume_agent"
AGENT_RENDER_DRAFT    = "render_and_draft_agent"
AGENT_SCAN_FOLLOWUP   = "scan_followup_emails_agent"
AGENT_PICK_FOLLOWUP   = "pick_next_followup_agent"
AGENT_ANALYZE_REPLY   = "analyze_and_reply_followup_agent"
AGENT_FINALIZE        = "finalize_agent"


def supervisor(state: EmailPipelineState) -> Dict[str, Any]:
    """
    Examine pipeline state and decide the next agent to invoke.

    Decision logic (evaluated top-to-bottom, first match wins):

    1. If a recruiter email is loaded and has a resume ready → render_and_draft
    2. If a recruiter email is loaded but no resume yet     → generate_resume
    3. If recruiter scan done & unprocessed emails remain    → pick_next_email
    4. If recruiter emails not scanned yet & enabled         → scan_recruiter_emails
    5. If a follow-up is loaded                              → analyze_and_reply
    6. If followup scan done & unprocessed followups remain   → pick_next_followup
    7. If followup emails not scanned yet & enabled          → scan_followup_emails
    8. Otherwise                                             → finalize
    """

    # ── Recruiter email processing ──────────────────────────────────
    current_email = state.get("current_email", {})
    if current_email:
        resume_path = state.get("resume_path", "")
        resume_json = state.get("resume_json", {})
        if resume_path and resume_json:
            logger.info("  Supervisor → render_and_draft_agent")
            return {"next_agent": AGENT_RENDER_DRAFT}
        else:
            logger.info("  Supervisor → generate_resume_agent")
            return {"next_agent": AGENT_GENERATE_RESUME}

    recruiter_scan_done = state.get("recruiter_scan_done", False)
    if recruiter_scan_done:
        idx = state.get("current_email_index", 0)
        emails = state.get("scanned_emails", [])
        if idx < len(emails):
            logger.info("  Supervisor → pick_next_email_agent")
            return {"next_agent": AGENT_PICK_EMAIL}

    if not recruiter_scan_done and state.get("run_phase1", False):
        logger.info("=" * 60)
        logger.info("Scanning for new recruiter emails...")
        return {"next_agent": AGENT_SCAN_RECRUITER}

    # ── Follow-up email processing ──────────────────────────────────
    current_followup = state.get("current_followup", {})
    if current_followup:
        logger.info("  Supervisor → analyze_and_reply_followup_agent")
        return {"next_agent": AGENT_ANALYZE_REPLY}

    followup_scan_done = state.get("followup_scan_done", False)
    if followup_scan_done:
        idx = state.get("current_followup_index", 0)
        followups = state.get("followup_emails", [])
        if idx < len(followups):
            logger.info("  Supervisor → pick_next_followup_agent")
            return {"next_agent": AGENT_PICK_FOLLOWUP}

    if not followup_scan_done and state.get("run_phase2", False):
        logger.info("=" * 60)
        logger.info("Scanning for recruiter follow-ups...")
        return {"next_agent": AGENT_SCAN_FOLLOWUP}

    # ── Nothing left to do ──────────────────────────────────────────
    logger.info("  Supervisor → finalize_agent")
    return {"next_agent": AGENT_FINALIZE}
