"""Dashboard router — summary stats for the Smart Email App."""

from fastapi import APIRouter

from api.data_service import get_all_emails, get_all_followups, list_resumes
from api.pipeline_runner import get_status

router = APIRouter()


@router.get("/")
def dashboard_stats():
    """Return summary statistics for the dashboard."""
    emails = get_all_emails()
    followups = get_all_followups()
    resumes = list_resumes()
    pipeline_status = get_status()

    # Recent emails (top 10 by processed_at descending)
    sorted_emails = sorted(emails, key=lambda e: e.get("processed_at", ""), reverse=True)
    recent_emails = sorted_emails[:10]

    return {
        "total_emails": len(emails),
        "total_followups": len(followups),
        "total_resumes": len(resumes),
        "recent_emails": recent_emails,
        "pipeline_status": pipeline_status,
    }
