"""Conversations router — grouped email threads by recruiter."""

from fastapi import APIRouter, HTTPException

from api.data_service import get_conversation, get_conversations, _extract_name, _extract_email_addr

router = APIRouter()


@router.get("/")
def list_conversations():
    """Return all conversations grouped by recruiter email."""
    return get_conversations()


@router.get("/{recruiter_email:path}")
def get_recruiter_conversation(recruiter_email: str):
    """Return the full message thread for a single recruiter as ConversationDetail."""
    messages = get_conversation(recruiter_email)
    if not messages:
        raise HTTPException(status_code=404, detail="No conversation found for this recruiter")

    # Extract recruiter name from the first inbound message
    recruiter_name = recruiter_email
    for msg in messages:
        if msg.get("from_email"):
            recruiter_name = _extract_name(msg["from_email"])
            break

    # Transform messages into the ConversationMessage format expected by frontend
    formatted_messages = []
    for msg in messages:
        formatted_messages.append({
            "direction": "outbound" if msg.get("type") == "followup" else "inbound",
            "subject": msg.get("subject", ""),
            "body": msg.get("summary", msg.get("body", "")),
            "date": msg.get("processed_at", ""),
            "intent": msg.get("intent"),
            "resume_file": msg.get("resume_file"),
        })

    return {
        "recruiter_email": recruiter_email,
        "recruiter_name": recruiter_name,
        "messages": formatted_messages,
    }
