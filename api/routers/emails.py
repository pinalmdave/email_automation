"""Emails router — list and retrieve processed emails."""

from typing import Optional

from fastapi import APIRouter, HTTPException

from api.data_service import get_all_emails, get_email

router = APIRouter()


@router.get("/")
def list_emails(sort: Optional[str] = "processed_at", order: Optional[str] = "desc"):
    """Return all processed emails, optionally sorted."""
    emails = get_all_emails()

    if sort and any(e.get(sort) is not None for e in emails):
        reverse = order == "desc"
        emails.sort(key=lambda e: e.get(sort, ""), reverse=reverse)

    return emails


@router.get("/{message_id:path}")
def get_single_email(message_id: str):
    """Return a single email by message_id."""
    email_data = get_email(message_id)
    if email_data is None:
        raise HTTPException(status_code=404, detail="Email not found")
    return email_data
