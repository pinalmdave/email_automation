"""
Generate Resume Agent — calls Claude AI to produce a tailored resume.
"""

import logging
from typing import Any, Dict

from graph.state import EmailPipelineState

logger = logging.getLogger(__name__)


def generate_resume(state: EmailPipelineState) -> Dict[str, Any]:
    """Call Claude to generate resume JSON and render the DOCX."""
    from resume_generator import generate_resume_json, render_resume_docx

    email_data = state["current_email"]
    try:
        logger.info("  Calling Claude API for resume generation...")
        resume_json = generate_resume_json(email_data)
        logger.info("  Rendering DOCX resume...")
        resume_path = render_resume_docx(resume_json)
        return {"resume_json": resume_json, "resume_path": str(resume_path)}
    except Exception as e:
        subject = email_data.get("subject", "?")
        logger.error("  FAILED to generate resume for '%s': %s", subject, e, exc_info=True)
        return {
            "resume_json": {},
            "resume_path": "",
            "errors": [f"Resume generation failed for '{subject}': {e}"],
        }
