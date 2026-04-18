"""
Shared state schema for the LangGraph email pipeline.
"""

import operator
from typing import Annotated, Any, Dict, List

from typing_extensions import TypedDict


class EmailPipelineState(TypedDict):
    """State that flows through every node (agent or tool) in the pipeline graph."""

    # -- Supervisor control --
    next_node: str  # set by supervisor, read by conditional edge
    run_recruiter_scan: bool
    run_followup_scan: bool

    # -- Scan parameters (overridable from UI; fall back to config defaults) --
    scan_folders: List[str]        # e.g. ["INBOX", "UPDATES"]
    scan_hours: int                # lookback window in hours

    # -- Scan tracking --
    recruiter_scan_done: bool
    followup_scan_done: bool

    # -- Manual job description (pasted via UI) --
    job_description_text: str
    job_description_done: bool

    # -- Apply-from-URL flow (user pastes a job URL) --
    job_url: str
    job_url_fetched: bool
    apply_plan_id: str

    # -- Recruiter email processing --
    scanned_emails: List[Dict[str, Any]]
    current_email_index: int
    current_email: Dict[str, Any]
    resume_json: Dict[str, Any]
    resume_path: str
    recruiter_processed: int

    # -- Resume evaluator-optimizer loop --
    resume_iterations: int             # incremented by generator each attempt
    resume_feedback: str               # evaluator's suggestions, fed back to generator
    resume_evaluation_score: float     # last score 0.0 - 1.0
    resume_evaluation_accepted: bool   # last evaluator verdict
    resume_evaluation_done: bool       # False after generator, True after evaluator

    # -- Follow-up email processing --
    followup_emails: List[Dict[str, Any]]
    current_followup_index: int
    current_followup: Dict[str, Any]
    followup_processed: int

    # -- Results --
    errors: Annotated[List[str], operator.add]
    summary: str
