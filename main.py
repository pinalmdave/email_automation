"""
Claude Smart Email App — Entry Point

Multi-agent pipeline powered by LangGraph.

Phase 1: Scans Gmail for recruiter emails, generates tailored resumes via Claude AI,
         and creates draft replies with the resume attached.
Phase 2: Detects follow-up replies from recruiters, analyzes intent (salary, availability,
         interview scheduling, etc.), and generates intelligent reply drafts.

Usage:
    python main.py                    # Run both phases in loop mode (every hour)
    python main.py --once             # Run both phases once and exit
    python main.py --interval 1800    # Custom interval (seconds)
    python main.py --phase1-only      # Only run Phase 1 (new recruiter emails)
    python main.py --phase2-only      # Only run Phase 2 (follow-up replies)
"""

import argparse
import logging
import sys
import time

from config import SCAN_INTERVAL_SECONDS
from graph import compile_graph

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("smart_email_app")


def _initial_state(run_recruiter_scan: bool, run_followup_scan: bool) -> dict:
    """Build the initial state dict for a single pipeline invocation."""
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
        "followup_emails": [],
        "current_followup_index": 0,
        "current_followup": {},
        "followup_processed": 0,
        "errors": [],
        "summary": "",
    }


def main():
    parser = argparse.ArgumentParser(description="Claude Smart Email App")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument(
        "--interval",
        type=int,
        default=SCAN_INTERVAL_SECONDS,
        help=f"Scan interval in seconds (default: {SCAN_INTERVAL_SECONDS})",
    )
    parser.add_argument("--phase1-only", action="store_true", help="Only run Phase 1 (new recruiter emails)")
    parser.add_argument("--phase2-only", action="store_true", help="Only run Phase 2 (follow-up replies)")
    args = parser.parse_args()

    run_p1 = not args.phase2_only
    run_p2 = not args.phase1_only

    phases = []
    if run_p1:
        phases.append("Phase 1 (resume generation)")
    if run_p2:
        phases.append("Phase 2 (follow-up replies)")

    logger.info("Claude Smart Email App starting...")
    logger.info("Mode: %s | Phases: %s", "single run" if args.once else f"loop (every {args.interval}s)", " + ".join(phases))

    graph = compile_graph()

    def run_pipeline():
        state = _initial_state(run_recruiter_scan=run_p1, run_followup_scan=run_p2)
        result = graph.invoke(state)
        summary = result.get("summary", "")
        if summary:
            logger.info("Summary: %s", summary.split("\n")[0])

    if args.once:
        run_pipeline()
        return

    # Loop mode
    while True:
        try:
            run_pipeline()
        except KeyboardInterrupt:
            logger.info("Interrupted by user. Shutting down.")
            sys.exit(0)
        except Exception as e:
            logger.error("Pipeline error: %s", e, exc_info=True)

        logger.info("Sleeping for %d seconds...", args.interval)
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            logger.info("Interrupted by user. Shutting down.")
            sys.exit(0)


if __name__ == "__main__":
    main()
