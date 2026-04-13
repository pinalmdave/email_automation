"""
Calls Claude API to analyze a recruiter email and generate resume JSON,
then renders the DOCX resume from the template.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

import anthropic
from docxtpl import DocxTemplate

from config import (
    CLAUDE_MODEL,
    RESUME_OUTPUT_DIR,
    RESUME_PROMPT_PATH,
    RESUME_TEMPLATE_PATH,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Claude API — generate resume JSON from recruiter email
# ---------------------------------------------------------------------------

def _extract_json_from_text(text: str) -> Dict[str, Any]:
    """Extract JSON object from Claude response, handling markdown fences."""
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: find the outermost { ... } block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Could not parse JSON from Claude response:\n{text[:500]}")


def generate_resume_json(email_data: Dict[str, Any]) -> Dict[str, Any]:
    """Send recruiter email to Claude and get back structured resume JSON."""
    system_prompt = RESUME_PROMPT_PATH.read_text(encoding="utf-8")

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": json.dumps(email_data, ensure_ascii=False)}],
    )

    raw_text = response.content[0].text
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


def render_resume_docx(resume_json: Dict[str, Any]) -> Path:
    """
    Render resume JSON into a DOCX file using the template.
    Saves to both RESUME_OUTPUT_DIR (Desktop) and returns the path.
    """
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
    logger.info("Resume saved: %s", out_path)
    return out_path
