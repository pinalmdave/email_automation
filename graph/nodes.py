"""
LangGraph node functions for the email pipeline.

Each function takes (state: EmailPipelineState) -> dict and returns a
partial state update.  Nodes wrap the existing modules — email_scanner,
resume_generator, email_drafter, followup_handler, state_tracker — without
modifying their public APIs.
"""

import logging
from typing import Any, Dict

from graph.state import EmailPipelineState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Supervisor
# ---------------------------------------------------------------------------

def route_phases(state: EmailPipelineState) -> Dict[str, Any]:
    """Decide which phase to run next (or finish)."""
    if state.get("run_phase1") and state.get("phase") in ("start", ""):
        logger.info("=" * 60)
        logger.info("PHASE 1: Scanning for new recruiter emails...")
        return {"phase": "phase1"}

    if state.get("run_phase2") and state.get("phase") in ("start", "", "phase1"):
        logger.info("=" * 60)
        logger.info("PHASE 2: Scanning for recruiter follow-ups...")
        return {"phase": "phase2"}

    return {"phase": "done"}


# ---------------------------------------------------------------------------
# Phase 1 nodes
# ---------------------------------------------------------------------------

def scan_recruiter_emails(state: EmailPipelineState) -> Dict[str, Any]:
    """Scan Gmail for new recruiter emails and filter already-processed ones."""
    from email_scanner import scan_for_recruiter_emails
    from state_tracker import is_processed

    emails = scan_for_recruiter_emails()
    new_emails = [e for e in emails if not is_processed(e.get("message_id", ""))]

    if not new_emails:
        logger.info("No new recruiter emails to process (found %d, all processed).", len(emails))
    else:
        logger.info("Found %d new email(s) out of %d.", len(new_emails), len(emails))

    return {
        "scanned_emails": new_emails,
        "current_email_index": 0,
        "current_email": {},
        "phase1_processed": 0,
    }


def pick_next_email(state: EmailPipelineState) -> Dict[str, Any]:
    """Advance to the next email in the scanned list, or signal done."""
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

    # No more emails
    return {"current_email": {}}


def generate_resume(state: EmailPipelineState) -> Dict[str, Any]:
    """Call Claude to generate resume JSON and render the DOCX."""
    from resume_generator import generate_resume_json, render_resume_docx

    email_data = state["current_email"]
    try:
        logger.info("  Calling Claude API for resume generation...")
        resume_json = generate_resume_json(email_data)
        logger.info("  Rendering DOCX resume...")
        resume_path = render_resume_docx(resume_json)
        return {"resume_json": resume_json, "resume_path": str(resume_path)}
    except Exception as e:
        subject = email_data.get("subject", "?")
        logger.error("  FAILED to generate resume for '%s': %s", subject, e, exc_info=True)
        return {
            "resume_json": {},
            "resume_path": "",
            "errors": [f"Resume generation failed for '{subject}': {e}"],
        }


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
        # Resume generation failed — skip drafting
        return {"current_email_index": idx + 1}

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
            "phase1_processed": processed + 1,
        }
    except Exception as e:
        logger.error("  FAILED to draft for '%s': %s", subject, e, exc_info=True)
        return {
            "current_email_index": idx + 1,
            "errors": [f"Draft creation failed for '{subject}': {e}"],
        }


# ---------------------------------------------------------------------------
# Phase 2 nodes
# ---------------------------------------------------------------------------

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
    }


def pick_next_followup(state: EmailPipelineState) -> Dict[str, Any]:
    """Advance to the next follow-up email, or signal done."""
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

    return {"current_followup": {}}


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
            "phase2_processed": processed + 1,
        }
    except Exception as e:
        logger.error("  FAILED: %s", e, exc_info=True)
        return {
            "current_followup_index": idx + 1,
            "errors": [f"Follow-up failed for '{subject}': {e}"],
        }


# ---------------------------------------------------------------------------
# Finalize
# ---------------------------------------------------------------------------

def finalize(state: EmailPipelineState) -> Dict[str, Any]:
    """Build a human-readable summary of the pipeline run."""
    p1 = state.get("phase1_processed", 0)
    p2 = state.get("phase2_processed", 0)
    errors = state.get("errors", [])

    parts = []
    if state.get("run_phase1"):
        parts.append(f"Phase 1: {p1} email(s) processed")
    if state.get("run_phase2"):
        parts.append(f"Phase 2: {p2} follow-up(s) processed")
    if errors:
        parts.append(f"Errors: {len(errors)}")
        for err in errors:
            parts.append(f"  - {err}")

    summary = " | ".join(parts[:2])
    if errors:
        summary += "\n" + "\n".join(parts[2:])

    logger.info("Pipeline complete. %s", summary.split("\n")[0])
    return {"summary": summary}
