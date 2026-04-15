"""
Shared state schema for the LangGraph email pipeline.
"""

import operator
from typing import Annotated, Any, Dict, List

from typing_extensions import TypedDict


class EmailPipelineState(TypedDict):
    """State that flows through every node in the email pipeline graph."""

    # -- Control flow --
    phase: str  # "start", "phase1", "phase2", "done"
    run_phase1: bool
    run_phase2: bool

    # -- Phase 1: new recruiter emails --
    scanned_emails: List[Dict[str, Any]]
    current_email_index: int
    current_email: Dict[str, Any]
    resume_json: Dict[str, Any]
    resume_path: str
    phase1_processed: int

    # -- Phase 2: follow-up emails --
    followup_emails: List[Dict[str, Any]]
    current_followup_index: int
    current_followup: Dict[str, Any]
    phase2_processed: int

    # -- Results --
    errors: Annotated[List[str], operator.add]
    summary: str
