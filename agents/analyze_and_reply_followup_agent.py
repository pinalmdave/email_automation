"""
Analyze and Reply Follow-up Agent — uses Claude to classify recruiter
follow-up intent and draft a reply body. The reply is queued as a
pending item for human review (Conversations tab); the actual SMTP
send happens when the user approves from the UI.
"""

import json
import logging
import re
from typing import Any, Dict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from config import CLAUDE_MODEL, PROMPTS_DIR
from gmail_mark import mark_email_processed
from graph.state import EmailPipelineState
from knowledge_base import system_prompt_with_knowledge
from usage_tracker import record_usage

logger = logging.getLogger(__name__)

FOLLOWUP_PROMPT_PATH = PROMPTS_DIR / "followup_prompt.txt"


# ---------------------------------------------------------------------------
# Claude-powered intent analysis and reply generation
# ---------------------------------------------------------------------------

def _generate_followup_reply(email_data: Dict[str, Any]) -> Dict[str, Any]:
    """Use Claude to analyze recruiter follow-up and generate a smart reply."""
    system_prompt = system_prompt_with_knowledge(
        FOLLOWUP_PROMPT_PATH.read_text(encoding="utf-8")
    )

    llm = ChatAnthropic(model=CLAUDE_MODEL, max_tokens=2048)
    # Static system prompt + knowledge — cache via ephemeral cache_control.
    response = llm.invoke([
        SystemMessage(content=[{
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }]),
        HumanMessage(content=json.dumps(email_data, ensure_ascii=False)),
    ])
    record_usage(response)

    raw_text = response.content.strip()
    # Strip markdown fences
    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```(?:json)?\s*\n?", "", raw_text)
        raw_text = re.sub(r"\n?```\s*$", "", raw_text)

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start != -1 and end > start:
            result = json.loads(raw_text[start:end + 1])
        else:
            raise ValueError(f"Could not parse follow-up reply JSON: {raw_text[:500]}")

    logger.info(
        "Follow-up analyzed — intent: %s, confidence: %s",
        result.get("intent", "?"),
        result.get("confidence", "?"),
    )
    return result


# ---------------------------------------------------------------------------
# Reply construction for follow-ups (body + subject only — no MIME/draft here)
# ---------------------------------------------------------------------------

def _build_followup_reply(
    email_data: Dict[str, Any],
    reply_result: Dict[str, Any],
) -> Dict[str, str]:
    from_email = email_data.get("from_email", "")
    match = re.search(r"<([^>]+)>", from_email)
    to_email = match.group(1).strip() if match else from_email.strip()

    subject = email_data.get("subject", "")
    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    reply_body = reply_result.get("reply_body", "")

    email_date = email_data.get("date", "")
    raw_body = email_data.get("raw_email_body", "")
    if raw_body:
        date_part = email_date.strip() if email_date else ""
        sender_part = from_email.strip()
        header = f"\n\nOn {date_part}, {sender_part} wrote:" if date_part else f"\n\nOn {sender_part} wrote:"
        body_lines = raw_body.strip().splitlines()
        quoted = "\n".join("> " + line if line.strip() else ">" for line in body_lines)
        full_body = reply_body + header + "\n" + quoted
    else:
        full_body = reply_body

    return {"to": to_email, "subject": reply_subject, "body": full_body}


# ---------------------------------------------------------------------------
# Agent node function — HITL: queue pending instead of drafting
# ---------------------------------------------------------------------------

def analyze_and_reply_followup(state: EmailPipelineState) -> Dict[str, Any]:
    """Analyze follow-up intent with Claude and queue a pending reply."""
    from agents.scan_followup_emails_node import mark_followup_processed
    from pending_replies import create as create_pending_reply

    followup = state["current_followup"]
    idx = state.get("current_followup_index", 0)
    processed = state.get("followup_processed", 0)
    message_id = followup.get("message_id", "")
    subject = followup.get("subject", "?")

    try:
        reply_result = _generate_followup_reply(followup)
        reply = _build_followup_reply(followup, reply_result)
        pending = create_pending_reply(
            kind="followup",
            original_message_id=message_id,
            original_from=followup.get("from_email", ""),
            original_subject=subject,
            original_date=followup.get("date", ""),
            original_imap_uid=followup.get("imap_uid", ""),
            original_folder=followup.get("folder", "INBOX"),
            reply_to=reply["to"],
            reply_subject=reply["subject"],
            reply_body=reply["body"],
            intent=reply_result.get("intent", "UNKNOWN"),
            extra={"intent_confidence": reply_result.get("confidence", 0.0)},
        )
        logger.info("  Queued follow-up pending reply: id=%s intent=%s",
                    pending["id"], reply_result.get("intent"))
        mark_followup_processed(
            message_id,
            reply_result.get("intent", "UNKNOWN"),
            reply_result.get("summary", ""),
        )

        # Mark original follow-up \Seen + apply CLAUDE_PROCESSED label.
        mark_err = mark_email_processed(
            followup.get("folder", "INBOX"),
            followup.get("imap_uid", ""),
        )
        if mark_err:
            logger.warning("Gmail label/read mark failed for follow-up %s: %s",
                           message_id, mark_err)
        logger.info("  Done! Intent: %s", reply_result.get("intent"))
        return {
            "current_followup_index": idx + 1,
            "current_followup": {},
            "followup_processed": processed + 1,
        }
    except Exception as e:
        logger.error("  FAILED: %s", e, exc_info=True)
        return {
            "current_followup_index": idx + 1,
            "current_followup": {},
            "errors": [f"Follow-up failed for '{subject}': {e}"],
        }
