"""
Claude Smart Email App — CLI Entry Point

Runs the LangGraph pipeline once (Phase 1 + Phase 2) and exits. Scheduling
is handled by the UI — the React + FastAPI frontend (see api/server.py)
triggers this same graph via WebSocket on user action. This CLI is kept
for quick local testing / debugging without the UI.

Usage:
    python main.py                    # Run both phases once
    python main.py --phase1-only      # Only Phase 1 (new recruiter emails)
    python main.py --phase2-only      # Only Phase 2 (follow-up replies)
    python main.py --job-description "paste JD here"   # Run manual-JD flow
"""

import argparse
import logging
import sys

from graph import compile_graph

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("smart_email_app")


def _initial_state(
    run_recruiter_scan: bool,
    run_followup_scan: bool,
    job_description_text: str = "",
) -> dict:
    return {
        "next_node": "",
        "run_recruiter_scan": run_recruiter_scan,
        "run_followup_scan": run_followup_scan,
        "recruiter_scan_done": False,
        "followup_scan_done": False,
        "scanned_emails": [],
        "current_email_index": 0,
        "current_email": {},
        "resume_json": {},
        "resume_path": "",
        "recruiter_processed": 0,
        "resume_iterations": 0,
        "resume_feedback": "",
        "resume_evaluation_score": 0.0,
        "resume_evaluation_accepted": False,
        "resume_evaluation_done": False,
        "followup_emails": [],
        "current_followup_index": 0,
        "current_followup": {},
        "followup_processed": 0,
        "job_description_text": job_description_text,
        "job_description_done": False,
        "errors": [],
        "summary": "",
    }


def main():
    parser = argparse.ArgumentParser(description="Claude Smart Email App (CLI)")
    parser.add_argument("--phase1-only", action="store_true", help="Only run Phase 1 (new recruiter emails)")
    parser.add_argument("--phase2-only", action="store_true", help="Only run Phase 2 (follow-up replies)")
    parser.add_argument(
        "--job-description",
        type=str,
        default="",
        help="Paste a job description to run the manual-JD → resume flow",
    )
    args = parser.parse_args()

    jd_text = args.job_description.strip()
    if jd_text:
        run_p1, run_p2 = False, False
    else:
        run_p1 = not args.phase2_only
        run_p2 = not args.phase1_only

    logger.info("Claude Smart Email App starting (single run)...")
    if jd_text:
        logger.info("Mode: manual job description (%d chars)", len(jd_text))
    else:
        phases = []
        if run_p1:
            phases.append("Phase 1 (resume generation)")
        if run_p2:
            phases.append("Phase 2 (follow-up replies)")
        logger.info("Mode: %s", " + ".join(phases) or "nothing enabled")

    graph = compile_graph()
    state = _initial_state(run_p1, run_p2, jd_text)

    try:
        result = graph.invoke(state, {"recursion_limit": 100})
    except KeyboardInterrupt:
        logger.info("Interrupted by user. Shutting down.")
        sys.exit(0)

    summary = result.get("summary", "")
    if summary:
        logger.info("Summary: %s", summary.split("\n")[0])


if __name__ == "__main__":
    main()
