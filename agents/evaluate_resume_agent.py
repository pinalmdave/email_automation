"""
Evaluate Resume Agent — the evaluator half of the evaluator-optimizer
pattern (https://www.anthropic.com/engineering/building-effective-agents).

Judges the most recently generated resume JSON against the job
description, returns a numeric score plus concrete feedback the generator
can use on the next iteration. Supervisor uses the score and the
iteration counter to decide: accept, retry, or give up.
"""

import json
import logging
import re
from typing import Any, Dict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from config import (
    CLAUDE_MODEL,
    PROMPTS_DIR,
    RESUME_ACCEPTANCE_THRESHOLD,
)
from graph.state import EmailPipelineState
from knowledge_base import system_prompt_with_knowledge
from usage_tracker import record_usage

logger = logging.getLogger(__name__)

EVALUATE_RESUME_PROMPT_PATH = PROMPTS_DIR / "evaluate_resume_prompt.txt"


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Evaluator returned non-JSON:\n{text[:500]}")


def _run_evaluator(
    email_data: Dict[str, Any],
    resume_json: Dict[str, Any],
    iteration: int,
) -> Dict[str, Any]:
    """Call Claude with the evaluator prompt. Returns parsed verdict dict."""
    system_prompt = system_prompt_with_knowledge(
        EVALUATE_RESUME_PROMPT_PATH.read_text(encoding="utf-8")
    )
    user_payload = {
        "job_description": email_data.get("raw_email_body", ""),
        "resume_json": resume_json,
        "iteration": iteration,
    }

    llm = ChatAnthropic(model=CLAUDE_MODEL, max_tokens=1024)
    response = llm.invoke([
        SystemMessage(content=[{
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }]),
        HumanMessage(content=json.dumps(user_payload, ensure_ascii=False)),
    ])
    record_usage(response)

    return _extract_json(response.content)


def evaluate_resume(state: EmailPipelineState) -> Dict[str, Any]:
    """
    Ask Claude to grade the current resume against the JD and emit
    actionable feedback. On any error the resume is auto-accepted so the
    pipeline never gets stuck on a broken evaluator.
    """
    email_data = state.get("current_email", {})
    resume_json = state.get("resume_json", {})
    iteration = state.get("resume_iterations", 0)

    if not email_data or not resume_json:
        logger.warning("evaluate_resume invoked without email+resume; auto-accepting")
        return {
            "resume_evaluation_accepted": True,
            "resume_evaluation_score": 1.0,
            "resume_feedback": "",
            "resume_evaluation_done": True,
        }

    try:
        verdict = _run_evaluator(email_data, resume_json, iteration)
        score = float(verdict.get("score", 0.0))
        feedback = str(verdict.get("feedback", "")).strip()
        # The config threshold is a hard floor: the LLM must say accepted
        # AND clear the numeric bar. If the LLM doesn't emit an accepted
        # field, fall back to threshold comparison alone.
        explicit = verdict.get("accepted")
        above_threshold = score >= RESUME_ACCEPTANCE_THRESHOLD
        if isinstance(explicit, bool):
            accepted = bool(explicit) and above_threshold
        else:
            accepted = above_threshold

        logger.info(
            "Resume evaluated — iter=%d score=%.2f accepted=%s  feedback=%s",
            iteration, score, accepted,
            (feedback[:140] + "…") if len(feedback) > 140 else feedback,
        )
        return {
            "resume_evaluation_score": score,
            "resume_evaluation_accepted": accepted,
            "resume_feedback": "" if accepted else feedback,
            "resume_evaluation_done": True,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Resume evaluation failed — auto-accepting: %s", exc, exc_info=True)
        return {
            "resume_evaluation_score": 0.0,
            "resume_evaluation_accepted": True,
            "resume_feedback": "",
            "resume_evaluation_done": True,
        }
