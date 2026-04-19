"""
Render and Queue Node — builds the recruiter reply (body + resume
attachment) and persists it as a pending reply for human review.

This replaces the previous "auto-append to Gmail Drafts" behavior: the
UI now lists pending replies and the user approves/edits/cancels each
one before any SMTP send. The original email is still marked as
processed so it isn't re-scanned on the next run.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from config import STATE_FILE_PATH
from gmail_mark import mark_email_processed
from graph.state import EmailPipelineState
from pending_replies import create as create_pending_reply

logger = logging.getLogger(__name__)

REPLY_BODY_TEMPLATE = """Hi {sender_first_name},

\tThanks for reaching out. I am interested in this position. I have 20+ years of experience in the skills mentioned in job details.

\tAttaching my latest resume for this position.

\tI am a US Green Card (GC) holder.

\tThanks,
\tPinal Dave
\tLinkedIn: https://www.linkedin.com/in/pinal-dave/
"""


# ---------------------------------------------------------------------------
# Reply body construction
# ---------------------------------------------------------------------------

def _recipient_address(from_email: str) -> str:
    match = re.search(r"<([^>]+)>", from_email)
    return match.group(1).strip() if match else from_email.strip()


def _extract_sender_name(from_email: str, resume_json: Dict[str, Any]) -> str:
    name = (resume_json.get("sender_name") or "").strip()
    if name:
        return name
    match = re.match(r"^\s*([^<]+)\s*<", from_email)
    if match:
        return match.group(1).strip().strip('"')
    match = re.search(r"([^@\s]+)@", from_email)
    return match.group(1) if match else "there"


def _format_quoted_chain(email_date: str, from_email: str, raw_email_body: str) -> str:
    if not raw_email_body and not email_date and not from_email:
        return ""
    date_part = email_date.strip() if email_date else ""
    sender_part = from_email.strip() if from_email else "sender"
    if date_part and sender_part:
        header = f"On {date_part}, {sender_part} wrote:"
    elif sender_part:
        header = f"On {sender_part} wrote:"
    else:
        header = "Previous message:"
    body_lines = (raw_email_body or "").strip().splitlines()
    quoted_lines = "\n".join("> " + line if line.strip() else ">" for line in body_lines)
    return f"\n\n{header}\n{quoted_lines}"


def _build_reply(
    email_data: Dict[str, Any],
    resume_json: Dict[str, Any],
) -> Dict[str, str]:
    from_email = email_data.get("from_email", "")
    to_email = _recipient_address(from_email)
    subject = email_data.get("subject", "")
    reply_subject = f"Re: {subject}" if subject and not subject.strip().lower().startswith("re:") else subject

    sender_name = _extract_sender_name(from_email, resume_json)
    first_name = sender_name.split()[0] if sender_name and sender_name != "there" else ""
    greeting = first_name if first_name else ""
    reply_text = REPLY_BODY_TEMPLATE.replace("{sender_first_name}", greeting)
    quoted = _format_quoted_chain(
        email_data.get("date", ""),
        from_email,
        email_data.get("raw_email_body", ""),
    )
    return {
        "to": to_email,
        "subject": reply_subject,
        "body": reply_text + quoted,
    }


# ---------------------------------------------------------------------------
# Processed-email ledger (dedup across scans)
# ---------------------------------------------------------------------------

def _mark_processed(
    message_id: str,
    subject: str,
    from_email: str,
    resume_file: str,
    pending_id: str,
) -> None:
    try:
        state = json.loads(STATE_FILE_PATH.read_text(encoding="utf-8")) if STATE_FILE_PATH.exists() else {}
    except (json.JSONDecodeError, OSError):
        state = {}
    state[message_id] = {
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "subject": subject,
        "from_email": from_email,
        "resume_file": resume_file,
        "pending_reply_id": pending_id,
        "status": "new",
    }
    STATE_FILE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        from blob_storage import upload_state_file
        upload_state_file(STATE_FILE_PATH)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Blob sync of processed_emails skipped: %s", exc)
    logger.info("Marked as processed (pending review): %s", message_id)


# ---------------------------------------------------------------------------
# Node function — HITL: persist pending instead of drafting
# ---------------------------------------------------------------------------

def render_and_draft(state: EmailPipelineState) -> Dict[str, Any]:
    """Build recruiter reply + queue it for human review (no Gmail draft)."""
    email_data = state["current_email"]
    resume_json = state.get("resume_json", {})
    resume_path_str = state.get("resume_path", "")
    idx = state.get("current_email_index", 0)
    processed = state.get("recruiter_processed", 0)

    if not resume_path_str or not resume_json:
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
        reply = _build_reply(email_data, resume_json)
        pending = create_pending_reply(
            kind="recruiter_initial",
            original_message_id=message_id,
            original_from=from_email,
            original_subject=subject,
            original_date=email_data.get("date", ""),
            original_imap_uid=email_data.get("imap_uid", ""),
            original_folder=email_data.get("folder", "INBOX"),
            reply_to=reply["to"],
            reply_subject=reply["subject"],
            reply_body=reply["body"],
            resume_path=str(resume_path),
            extra={
                "resume_filename": resume_path.name,
                "staffing_company_name": resume_json.get("staffing_company_name", ""),
                "target_role_title": resume_json.get("target_role_title", ""),
            },
        )
        _mark_processed(message_id, subject, from_email, str(resume_path), pending["id"])

        # Mark original email \Seen + apply CLAUDE_PROCESSED so next scan skips it.
        mark_err = mark_email_processed(
            email_data.get("folder", "INBOX"),
            email_data.get("imap_uid", ""),
        )
        if mark_err:
            logger.warning("Gmail label/read mark failed for %s: %s", message_id, mark_err)

        logger.info("  Queued pending reply for review: %s (resume=%s)", pending["id"], resume_path.name)
        return {
            "current_email_index": idx + 1,
            "current_email": {},
            "resume_json": {},
            "resume_path": "",
            "recruiter_processed": processed + 1,
            "resume_iterations": 0,
            "resume_feedback": "",
            "resume_evaluation_done": False,
            "resume_evaluation_accepted": False,
            "resume_evaluation_score": 0.0,
        }
    except Exception as e:
        logger.error("  FAILED to queue pending for '%s': %s", subject, e, exc_info=True)
        return {
            "current_email_index": idx + 1,
            "current_email": {},
            "resume_json": {},
            "resume_path": "",
            "resume_iterations": 0,
            "resume_feedback": "",
            "resume_evaluation_done": False,
            "resume_evaluation_accepted": False,
            "resume_evaluation_score": 0.0,
            "errors": [f"Pending-reply queue failed for '{subject}': {e}"],
        }
