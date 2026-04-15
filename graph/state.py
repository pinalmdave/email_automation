"""
Shared state schema for the LangGraph email pipeline.
"""

import operator
from typing import Annotated, Any, Dict, List

from typing_extensions import TypedDict


class EmailPipelineState(TypedDict):
    """State that flows through every agent in the email pipeline graph."""

    # -- Supervisor control --
    next_agent: str  # set by supervisor, read by conditional edge
    run_phase1: bool
    run_phase2: bool

    # -- Scan tracking --
    recruiter_scan_done: bool
    followup_scan_done: bool

    # -- Recruiter email processing --
    scanned_emails: List[Dict[str, Any]]
    current_email_index: int
    current_email: Dict[str, Any]
    resume_json: Dict[str, Any]
    resume_path: str
    phase1_processed: int

    # -- Follow-up email processing --
    followup_emails: List[Dict[str, Any]]
    current_followup_index: int
    current_followup: Dict[str, Any]
    phase2_processed: int

    # -- Results --
    errors: Annotated[List[str], operator.add]
    summary: str
