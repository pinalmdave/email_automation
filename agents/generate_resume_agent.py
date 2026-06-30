"""
Generate Resume Agent — calls Claude AI to analyze a recruiter email,
produce a tailored resume JSON, render it to DOCX, and return paths
in the pipeline state.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from docxtpl import DocxTemplate
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from config import (
    CLAUDE_MODEL,
    RESUME_OUTPUT_DIR,
    RESUME_PROMPT_PATH,
    RESUME_TEMPLATE_PATH,
    resolve_model,
)
from graph.state import EmailPipelineState
from knowledge_base import system_prompt_with_knowledge
from usage_tracker import record_usage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Claude API — generate resume JSON from recruiter email
# ---------------------------------------------------------------------------

def _extract_json_from_text(text: str) -> Dict[str, Any]:
    """Extract JSON object from Claude response, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Could not parse JSON from Claude response:\n{text[:500]}")


def _generate_resume_json(
    email_data: Dict[str, Any],
    prior_feedback: str = "",
    iteration: int = 1,
    model: str = CLAUDE_MODEL,
) -> Dict[str, Any]:
    """Send recruiter email to Claude and get back structured resume JSON.

    On retries (iteration > 1) the evaluator's feedback from the previous
    attempt is injected into the user turn so the generator can course-correct.
    """
    system_prompt = system_prompt_with_knowledge(
        RESUME_PROMPT_PATH.read_text(encoding="utf-8")
    )

    user_payload: Dict[str, Any] = dict(email_data)
    if prior_feedback:
        user_payload["_previous_attempt_feedback"] = prior_feedback
        user_payload["_iteration"] = iteration
        logger.info(
            "Regenerating resume (iteration %d) with evaluator feedback: %s",
            iteration,
            (prior_feedback[:140] + "…") if len(prior_feedback) > 140 else prior_feedback,
        )

    llm = ChatAnthropic(model=model, max_tokens=4096)
    # The system prompt + knowledge base is static across calls — mark it
    # with ephemeral cache_control so Anthropic caches the full block and
    # subsequent calls within 5 minutes pay ~10% of normal input rate.
    response = llm.invoke([
        SystemMessage(content=[{
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }]),
        HumanMessage(content=json.dumps(user_payload, ensure_ascii=False)),
    ])
    record_usage(response)

    raw_text = response.content
    resume_json = _extract_json_from_text(raw_text)
    logger.info(
        "Generated resume JSON — role: %s, company: %s, confidence: %s",
        resume_json.get("target_role_title", "?"),
        resume_json.get("staffing_company_name", "?"),
        resume_json.get("confidence_score", "?"),
    )
    return resume_json


# ---------------------------------------------------------------------------
# DOCX rendering — populate template with resume JSON
# ---------------------------------------------------------------------------

def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v).strip()


def _format_achievements(achievements: List[str]) -> str:
    if not achievements:
        return ""
    return "\n".join("\u2022 " + str(a).strip() for a in achievements)


def _resume_json_to_context(data: Dict[str, Any]) -> Dict[str, str]:
    """Build docxtpl context from resume JSON. Keys match {{PLACEHOLDER}} in template."""
    def get(key: str, default: str = "") -> Any:
        return data.get(key, default)

    def skills_list(key: str) -> str:
        val = get(key)
        if isinstance(val, list):
            return ", ".join(str(x) for x in val)
        return _safe_str(val)

    def achievements_list(key: str) -> str:
        val = get(key)
        if isinstance(val, list):
            return _format_achievements(val)
        return _safe_str(val)

    return {
        "TARGET_ROLE_TITLE": _safe_str(get("target_role_title")),
        "PRIMARY_EXPERTISE_TAGLINE": _safe_str(get("primary_expertise_tagline")),
        "PROFESSIONAL_SUMMARY": _safe_str(get("professional_summary")),
        "SKILL_CATEGORY_1_TITLE": _safe_str(get("skill_category_1_title")),
        "SKILL_CATEGORY_1_SKILLS": skills_list("skill_category_1_skills"),
        "SKILL_CATEGORY_2_TITLE": _safe_str(get("skill_category_2_title")),
        "SKILL_CATEGORY_2_SKILLS": skills_list("skill_category_2_skills"),
        "SKILL_CATEGORY_3_TITLE": _safe_str(get("skill_category_3_title")),
        "SKILL_CATEGORY_3_SKILLS": skills_list("skill_category_3_skills"),
        "SKILL_CATEGORY_4_TITLE": _safe_str(get("skill_category_4_title")),
        "SKILL_CATEGORY_4_SKILLS": skills_list("skill_category_4_skills"),
        "SKILL_CATEGORY_5_TITLE": _safe_str(get("skill_category_5_title")),
        "SKILL_CATEGORY_5_SKILLS": skills_list("skill_category_5_skills"),
        "EXPERIENCE_1_CONTEXT": _safe_str(get("experience_1_context")),
        "EXPERIENCE_1_ACHIEVEMENTS": achievements_list("experience_1_achievements"),
        "EXPERIENCE_1_TECH_STACK": skills_list("experience_1_tech_stack"),
        "EXPERIENCE_2_CONTEXT": _safe_str(get("experience_2_context")),
        "EXPERIENCE_2_ACHIEVEMENTS": achievements_list("experience_2_achievements"),
        "EXPERIENCE_2_TECH_STACK": skills_list("experience_2_tech_stack"),
        "EXPERIENCE_3_CONTEXT": _safe_str(get("experience_3_context")),
        "EXPERIENCE_3_ACHIEVEMENTS": achievements_list("experience_3_achievements"),
        "EXPERIENCE_3_TECH_STACK": skills_list("experience_3_tech_stack"),
    }


def _render_resume_docx(resume_json: Dict[str, Any]) -> Path:
    """
    Render resume JSON into a DOCX file using the template.
    Saves to RESUME_OUTPUT_DIR and uploads to Azure Blob Storage if configured.
    Returns the local path.
    """
    from blob_storage import upload_resume

    if not RESUME_TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Resume template not found: {RESUME_TEMPLATE_PATH}")

    doc = DocxTemplate(str(RESUME_TEMPLATE_PATH))
    context = _resume_json_to_context(resume_json)
    doc.render(context)

    staffing = (resume_json.get("staffing_company_name") or "").strip()
    safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in staffing).strip() or "Resume"
    filename = f"PinalResume-{safe_name}.docx" if safe_name != "Resume" else "PinalResume.docx"

    out_path = RESUME_OUTPUT_DIR / filename
    doc.save(str(out_path))
    logger.info("Resume saved locally: %s", out_path)

    upload_resume(out_path)

    return out_path


# ---------------------------------------------------------------------------
# Agent node function
# ---------------------------------------------------------------------------

def generate_resume(state: EmailPipelineState) -> Dict[str, Any]:
    """Call Claude to generate resume JSON and render the DOCX."""
    email_data = state["current_email"]
    iterations = state.get("resume_iterations", 0)
    prior_feedback = state.get("resume_feedback", "") if iterations > 0 else ""
    next_iteration = iterations + 1
    model = resolve_model(state.get("selected_model"))

    try:
        logger.info(
            "  Calling Claude API (%s) for resume generation (iteration %d)%s...",
            model, next_iteration,
            " with evaluator feedback" if prior_feedback else "",
        )
        resume_json = _generate_resume_json(email_data, prior_feedback, next_iteration, model=model)
        logger.info("  Rendering DOCX resume...")
        resume_path = _render_resume_docx(resume_json)
        return {
            "resume_json": resume_json,
            "resume_path": str(resume_path),
            "resume_iterations": next_iteration,
            # Mark this iteration as unevaluated so the supervisor routes
            # to the evaluator next.
            "resume_evaluation_done": False,
            "resume_evaluation_accepted": False,
            # Feedback has been consumed; clear it so stale feedback doesn't
            # leak into a fresh email's first attempt.
            "resume_feedback": "",
        }
    except Exception as e:
        subject = email_data.get("subject", "?")
        logger.error("  FAILED to generate resume for '%s': %s", subject, e, exc_info=True)
        return {
            "resume_json": {},
            "resume_path": "",
            "resume_iterations": next_iteration,
            "resume_evaluation_done": True,  # skip evaluator on a hard failure
            "resume_evaluation_accepted": False,
            "errors": [f"Resume generation failed for '{subject}': {e}"],
        }
