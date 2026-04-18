"""
Finalize Node — builds a human-readable summary of the pipeline run.

Also links the generated resume back to the apply_plan entry for
apply-from-URL runs, flipping the plan from "planning" to "ready" so it
shows up in the Apply History tab waiting for the user.
"""

import logging
from pathlib import Path
from typing import Any, Dict

import apply_plans
from graph.state import EmailPipelineState

logger = logging.getLogger(__name__)


def finalize(state: EmailPipelineState) -> Dict[str, Any]:
    """Build a human-readable summary of the pipeline run."""
    p1 = state.get("recruiter_processed", 0)
    p2 = state.get("followup_processed", 0)
    errors = state.get("errors", [])

    # If this run was an apply-from-URL, attach the resume to the plan.
    apply_plan_id = state.get("apply_plan_id", "")
    if apply_plan_id:
        resume_path = state.get("resume_path", "")
        resume_json = state.get("resume_json", {}) or {}
        updates: Dict[str, Any] = {}
        if resume_path:
            updates["resume_path"] = resume_path
            updates["resume_filename"] = Path(resume_path).name
            updates["status"] = "ready"
        if resume_json:
            if resume_json.get("target_role_title"):
                updates["target_role_title"] = resume_json["target_role_title"]
            if resume_json.get("staffing_company_name"):
                updates["staffing_company_name"] = resume_json["staffing_company_name"]
        # Surface the evaluator's verdict on the plan so the UI can warn the user.
        updates["evaluation_score"] = state.get("resume_evaluation_score", 0.0)
        if state.get("resume_recommend_decline"):
            updates["recommendation"] = "decline"
            updates["decline_reason"] = state.get("resume_decline_reason", "")
        else:
            updates["recommendation"] = "apply"
            updates["decline_reason"] = ""
        if updates:
            apply_plans.update(apply_plan_id, **updates)
            logger.info("Apply plan %s updated — status=%s recommendation=%s score=%.2f",
                        apply_plan_id, updates.get("status", "?"),
                        updates.get("recommendation", "?"),
                        updates.get("evaluation_score", 0.0))

    parts = []
    if state.get("run_recruiter_scan"):
        parts.append(f"Recruiter emails: {p1} processed")
    if state.get("run_followup_scan"):
        parts.append(f"Follow-ups: {p2} processed")
    if apply_plan_id:
        parts.append("Apply plan ready for review")
    if errors:
        parts.append(f"Errors: {len(errors)}")
        for err in errors:
            parts.append(f"  - {err}")

    summary = " | ".join(parts[:3])
    if errors:
        summary += "\n" + "\n".join(parts[3:])

    logger.info("Pipeline complete. %s", (summary or "no-op").split("\n")[0])
    return {"summary": summary}
