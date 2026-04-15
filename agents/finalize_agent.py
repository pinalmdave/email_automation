"""
Finalize Agent — builds a human-readable summary of the pipeline run.
"""

import logging
from typing import Any, Dict

from graph.state import EmailPipelineState

logger = logging.getLogger(__name__)


def finalize(state: EmailPipelineState) -> Dict[str, Any]:
    """Build a human-readable summary of the pipeline run."""
    p1 = state.get("phase1_processed", 0)
    p2 = state.get("phase2_processed", 0)
    errors = state.get("errors", [])

    parts = []
    if state.get("run_phase1"):
        parts.append(f"Recruiter emails: {p1} processed")
    if state.get("run_phase2"):
        parts.append(f"Follow-ups: {p2} processed")
    if errors:
        parts.append(f"Errors: {len(errors)}")
        for err in errors:
            parts.append(f"  - {err}")

    summary = " | ".join(parts[:2])
    if errors:
        summary += "\n" + "\n".join(parts[2:])

    logger.info("Pipeline complete. %s", summary.split("\n")[0])
    return {"summary": summary}
