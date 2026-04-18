"""
Supervisor Agent — intelligent central router for the email pipeline.

Inspects the current state and decides which node to invoke next.
Every other node returns to the supervisor after completing its work.
No rigid ordering — the supervisor reasons about what needs to happen.

The supervisor also handles iterator logic (picking the next email /
follow-up from the scanned list) inline, eliminating the need for
separate pick-next-email and pick-next-followup nodes.
"""

import logging
from typing import Any, Dict

from graph.state import EmailPipelineState

logger = logging.getLogger(__name__)

# The supervisor returns a `next_node` value that the graph's conditional
# edge uses to route to the correct node.

NODE_SCAN_RECRUITER   = "scan_recruiter_emails_node"
AGENT_GENERATE_RESUME = "generate_resume_agent"
NODE_RENDER_DRAFT     = "render_and_draft_node"
NODE_SCAN_FOLLOWUP    = "scan_followup_emails_node"
AGENT_ANALYZE_REPLY   = "analyze_and_reply_followup_agent"
NODE_PROCESS_JD       = "process_job_description_node"
NODE_FINALIZE         = "finalize_node"


def supervisor(state: EmailPipelineState) -> Dict[str, Any]:
    """
    Examine pipeline state and decide the next agent to invoke.

    Decision logic (evaluated top-to-bottom, first match wins):

    1. If a manual JD is pending (text set, not yet processed) → process_job_description
    2. If a recruiter email is loaded and has a resume ready  → render_and_draft
       (manual-JD flow skips drafting — goes straight to finalize)
    3. If a recruiter email is loaded but no resume yet      → generate_resume
    4. If recruiter scan done & unprocessed emails remain    → load next, → generate_resume
    5. If recruiter scan not done & enabled                  → scan_recruiter_emails
    6. If a follow-up is loaded                              → analyze_and_reply
    7. If followup scan done & unprocessed followups remain  → load next, → analyze_and_reply
    8. If followup scan not done & enabled                   → scan_followup_emails
    9. Otherwise                                             → finalize
    """

    # ── Manual job description (UI paste) ───────────────────────────
    jd_text = (state.get("job_description_text") or "").strip()
    if jd_text and not state.get("job_description_done", False):
        logger.info("  Supervisor → process_job_description_node")
        return {"next_node": NODE_PROCESS_JD}

    # ── Recruiter / JD email processing ─────────────────────────────
    current_email = state.get("current_email", {})
    if current_email:
        resume_path = state.get("resume_path", "")
        resume_json = state.get("resume_json", {})
        if resume_path and resume_json:
            # Manual-JD flow has no recruiter to reply to — skip drafting.
            if jd_text:
                logger.info("  Supervisor → finalize_node (manual JD, skip draft)")
                return {"next_node": NODE_FINALIZE}
            logger.info("  Supervisor → render_and_draft_node")
            return {"next_node": NODE_RENDER_DRAFT}
        else:
            logger.info("  Supervisor → generate_resume_agent")
            return {"next_node": AGENT_GENERATE_RESUME}

    recruiter_scan_done = state.get("recruiter_scan_done", False)
    if recruiter_scan_done:
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
            logger.info("  Supervisor → generate_resume_agent")
            return {
                "next_node": AGENT_GENERATE_RESUME,
                "current_email": email_data,
            }

    if not recruiter_scan_done and state.get("run_recruiter_scan", False):
        logger.info("=" * 60)
        logger.info("Scanning for new recruiter emails...")
        return {"next_node": NODE_SCAN_RECRUITER}

    # ── Follow-up email processing ──────────────────────────────────
    current_followup = state.get("current_followup", {})
    if current_followup:
        logger.info("  Supervisor → analyze_and_reply_followup_agent")
        return {"next_node": AGENT_ANALYZE_REPLY}

    followup_scan_done = state.get("followup_scan_done", False)
    if followup_scan_done:
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
            logger.info("  Supervisor → analyze_and_reply_followup_agent")
            return {
                "next_node": AGENT_ANALYZE_REPLY,
                "current_followup": followup,
            }

    if not followup_scan_done and state.get("run_followup_scan", False):
        logger.info("=" * 60)
        logger.info("Scanning for recruiter follow-ups...")
        return {"next_node": NODE_SCAN_FOLLOWUP}

    # ── Nothing left to do ──────────────────────────────────────────
    logger.info("  Supervisor → finalize_node")
    return {"next_node": NODE_FINALIZE}
