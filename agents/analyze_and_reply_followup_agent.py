"""
Analyze and Reply Follow-up Agent — uses Claude AI to understand recruiter
intent and generate an intelligent reply draft via Gmail IMAP.
"""

import imaplib
import json
import logging
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from config import (
    CLAUDE_MODEL,
    IMAP_HOST,
    IMAP_PASSWORD,
    IMAP_PORT,
    IMAP_USER,
    PROMPTS_DIR,
)
from graph.state import EmailPipelineState
from knowledge_base import system_prompt_with_knowledge
from usage_tracker import record_usage

logger = logging.getLogger(__name__)

FOLLOWUP_PROMPT_PATH = PROMPTS_DIR / "followup_prompt.txt"
FOLLOWUP_LABEL = "AUTO_REPLY_CLAUDE"


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
# Draft creation for follow-up replies
# ---------------------------------------------------------------------------

def _create_followup_draft(
    email_data: Dict[str, Any],
    reply_result: Dict[str, Any],
) -> None:
    """Create a Gmail draft for the follow-up reply."""
    if not IMAP_USER or not IMAP_PASSWORD:
        raise RuntimeError("IMAP_USER and IMAP_PASSWORD must be set in .env")

    from_email = email_data.get("from_email", "")
    match = re.search(r"<([^>]+)>", from_email)
    to_email = match.group(1).strip() if match else from_email.strip()

    subject = email_data.get("subject", "")
    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"

    reply_body = reply_result.get("reply_body", "")

    # Append quoted original
    email_date = email_data.get("date", "")
    raw_body = email_data.get("raw_email_body", "")
    if raw_body:
        date_part = email_date.strip() if email_date else ""
        sender_part = from_email.strip()
        if date_part:
            quoted_header = f"\n\nOn {date_part}, {sender_part} wrote:"
        else:
            quoted_header = f"\n\nOn {sender_part} wrote:"
        body_lines = raw_body.strip().splitlines()
        quoted = "\n".join("> " + line if line.strip() else ">" for line in body_lines)
        full_body = reply_body + quoted_header + "\n" + quoted
    else:
        full_body = reply_body

    # Build MIME
    msg = MIMEMultipart()
    msg["From"] = IMAP_USER
    msg["To"] = to_email
    msg["Subject"] = reply_subject
    msg.attach(MIMEText(full_body, "plain", "utf-8"))

    raw = msg.as_string().encode("utf-8")
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(IMAP_USER, IMAP_PASSWORD)

    drafts_folder = "[Gmail]/Drafts"
    try:
        status, data = mail.append(drafts_folder, "\\Draft", None, raw)
    except Exception:
        drafts_folder = "Drafts"
        status, data = mail.append(drafts_folder, "\\Draft", None, raw)

    # Apply follow-up label
    if status == "OK" and data:
        resp = data[0].decode() if isinstance(data[0], bytes) else str(data[0])
        uid_match = re.search(r"APPENDUID\s+\d+\s+(\d+)", resp)
        if uid_match:
            uid = uid_match.group(1)
            mail.select(drafts_folder, readonly=False)
            try:
                mail.copy(uid, FOLLOWUP_LABEL)
            except Exception:
                pass

    # Mark original email as read
    original_folder = email_data.get("folder", "INBOX")
    original_uid = email_data.get("imap_uid", "")
    if original_uid:
        try:
            mail.select(original_folder, readonly=False)
            uid_bytes = original_uid.encode() if isinstance(original_uid, str) else original_uid
            mail.store(uid_bytes, "+FLAGS", "\\Seen")
            try:
                mail.copy(uid_bytes, FOLLOWUP_LABEL)
            except Exception:
                pass
        except Exception as e:
            logger.warning("Could not mark follow-up email as read: %s", e)

    mail.logout()
    logger.info(
        "Follow-up draft created for: %s [%s] -> %s",
        to_email,
        reply_result.get("intent", "?"),
        reply_subject,
    )


# ---------------------------------------------------------------------------
# Agent node function
# ---------------------------------------------------------------------------

def analyze_and_reply_followup(state: EmailPipelineState) -> Dict[str, Any]:
    """Analyze follow-up intent with Claude and create a reply draft."""
    from agents.scan_followup_emails_node import mark_followup_processed

    followup = state["current_followup"]
    idx = state.get("current_followup_index", 0)
    processed = state.get("followup_processed", 0)
    message_id = followup.get("message_id", "")
    subject = followup.get("subject", "?")

    try:
        reply_result = _generate_followup_reply(followup)
        _create_followup_draft(followup, reply_result)
        mark_followup_processed(
            message_id,
            reply_result.get("intent", "UNKNOWN"),
            reply_result.get("summary", ""),
        )
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
