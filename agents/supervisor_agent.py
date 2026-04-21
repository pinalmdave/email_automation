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

from config import MAX_RESUME_ITERATIONS
from graph.state import EmailPipelineState

logger = logging.getLogger(__name__)

# The supervisor returns a `next_node` value that the graph's conditional
# edge uses to route to the correct node.

NODE_SCAN_RECRUITER   = "scan_recruiter_emails_node"
AGENT_GENERATE_RESUME = "generate_resume_agent"
AGENT_EVALUATE_RESUME = "evaluate_resume_agent"
NODE_RENDER_DRAFT     = "render_and_draft_node"
NODE_SCAN_FOLLOWUP    = "scan_followup_emails_node"
AGENT_ANALYZE_REPLY   = "analyze_and_reply_followup_agent"
NODE_PROCESS_JD       = "process_job_description_node"
NODE_PROCESS_JOB_URL  = "process_job_url_node"
NODE_FINALIZE         = "finalize_node"


def _clear_email_state(state: EmailPipelineState) -> Dict[str, Any]:
    """
    Return the state delta that skips the current email and resets all
    per-email resume fields. The caller must also set `next_node`.

    Does NOT touch current_email_index — callers must increment that
    themselves so the supervisor picks up the NEXT email on re-entry.
    """
    return {
        "current_email": {},
        "resume_json": {},
        "resume_path": "",
        "resume_iterations": 0,
        "resume_feedback": "",
        "resume_evaluation_done": False,
        "resume_evaluation_accepted": False,
        "resume_recommend_decline": False,
        "resume_evaluation_score": 0.0,
    }


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

    # ── Apply from URL (UI-pasted job posting URL) ──────────────────
    job_url = (state.get("job_url") or "").strip()
    if job_url and not state.get("job_url_fetched", False):
        logger.info("  Supervisor → process_job_url_node")
        return {"next_node": NODE_PROCESS_JOB_URL}

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
        iterations = state.get("resume_iterations", 0)

        if not resume_path or not resume_json:
            # Safety net: if the generator has already failed MAX times
            # without producing a resume, skip this email and move on so
            # the remaining emails in the batch are still processed.
            _max_iters = int(state.get("max_resume_iterations") or 0) or MAX_RESUME_ITERATIONS
            if iterations >= _max_iters:
                subject = current_email.get("subject", "(no subject)")
                idx = state.get("current_email_index", 0)
                logger.error(
                    "Generator failed %d times for '%s' — skipping, next email index=%d",
                    iterations, subject, idx + 1,
                )
                skip = _clear_email_state(state)
                skip["next_node"] = "supervisor_agent"   # self-loop: pick up next email
                skip["current_email_index"] = idx + 1
                skip["errors"] = [f"Gave up on '{subject}' after {iterations} failed generations"]
                return skip

            logger.info("  Supervisor → generate_resume_agent")
            return {"next_node": AGENT_GENERATE_RESUME}

        # Resume generated. Evaluator-optimizer loop decides whether to
        # accept, regenerate with feedback, or give up at the iteration cap.
        evaluated = state.get("resume_evaluation_done", False)
        accepted = state.get("resume_evaluation_accepted", False)
        recommend_decline = state.get("resume_recommend_decline", False)
        # Per-run override from UI, or fall back to config.
        max_iters = int(state.get("max_resume_iterations") or 0) or MAX_RESUME_ITERATIONS

        if not evaluated:
            logger.info("  Supervisor → evaluate_resume_agent (iter %d)", iterations)
            return {"next_node": AGENT_EVALUATE_RESUME}

        # Hard-mismatch short-circuit: evaluator flagged the JD as a wrong
        # fit — skip this email and continue with the remaining batch.
        if recommend_decline:
            subject = current_email.get("subject", "(no subject)")
            idx = state.get("current_email_index", 0)
            logger.info(
                "  Evaluator recommends decline (score %.2f) for '%s' — skipping, "
                "next email index=%d. Reason: %s",
                state.get("resume_evaluation_score", 0.0),
                subject,
                idx + 1,
                state.get("resume_decline_reason", ""),
            )
            skip = _clear_email_state(state)
            skip["next_node"] = "supervisor_agent"   # self-loop: pick up next email
            skip["current_email_index"] = idx + 1
            return skip

        if not accepted and iterations < max_iters:
            logger.info(
                "  Supervisor → generate_resume_agent (retry %d/%d, score %.2f)",
                iterations + 1, max_iters,
                state.get("resume_evaluation_score", 0.0),
            )
            return {
                "next_node": AGENT_GENERATE_RESUME,
                # Clear the rejected resume so the generator runs again
                # and the "resume already set" check doesn't short-circuit.
                "resume_path": "",
                "resume_json": {},
                "resume_evaluation_done": False,
            }

        # Accepted, or we've hit the iteration cap — proceed.
        if not accepted:
            logger.info(
                "  Iteration cap hit (%d) — using last resume (score %.2f)",
                iterations, state.get("resume_evaluation_score", 0.0),
            )
        if jd_text or state.get("apply_plan_id"):
            reason = "manual JD" if jd_text else "apply-from-URL"
            logger.info("  Supervisor → finalize_node (%s, skip draft)", reason)
            return {"next_node": NODE_FINALIZE}
        logger.info("  Supervisor → render_and_draft_node")
        return {"next_node": NODE_RENDER_DRAFT}

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
            reset = _clear_email_state(state)
            reset["next_node"] = AGENT_GENERATE_RESUME
            reset["current_email"] = email_data
            return reset

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
