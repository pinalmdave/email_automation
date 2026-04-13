"""
Claude Smart Email App — Entry Point

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
from email_drafter import create_draft_reply
from email_scanner import scan_for_recruiter_emails
from followup_handler import run_followup_pipeline
from resume_generator import generate_resume_json, render_resume_docx
from state_tracker import is_processed, mark_processed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("smart_email_app")


def run_phase1_pipeline() -> int:
    """
    Phase 1: scan -> filter AI/Cloud positions -> generate resume -> create draft.
    Returns number of emails processed.
    """
    logger.info("=" * 60)
    logger.info("PHASE 1: Scanning for new recruiter emails...")

    emails = scan_for_recruiter_emails()
    if not emails:
        logger.info("No new recruiter emails found.")
        return 0

    new_emails = [e for e in emails if not is_processed(e.get("message_id", ""))]
    if not new_emails:
        logger.info("All %d email(s) already processed.", len(emails))
        return 0

    logger.info("Processing %d new email(s) out of %d found.", len(new_emails), len(emails))
    processed_count = 0

    for i, email_data in enumerate(new_emails, 1):
        subject = email_data.get("subject", "(no subject)")
        from_email = email_data.get("from_email", "(unknown)")
        message_id = email_data.get("message_id", "")

        logger.info("[%d/%d] Processing: %s from %s", i, len(new_emails), subject, from_email)

        try:
            # Step 1: Generate resume JSON via Claude
            logger.info("  Calling Claude API for resume generation...")
            resume_json = generate_resume_json(email_data)

            # Step 2: Render DOCX from template
            logger.info("  Rendering DOCX resume...")
            resume_path = render_resume_docx(resume_json)

            # Step 3: Create Gmail draft with resume attached
            logger.info("  Creating Gmail draft...")
            create_draft_reply(email_data, resume_json, resume_path)

            # Step 4: Mark as processed
            mark_processed(message_id, subject, from_email, str(resume_path))
            processed_count += 1
            logger.info("  Done! Resume: %s", resume_path.name)

        except Exception as e:
            logger.error("  FAILED to process '%s': %s", subject, e, exc_info=True)

    logger.info("Phase 1 complete. Processed %d/%d email(s).", processed_count, len(new_emails))
    return processed_count


def run_phase2_pipeline() -> int:
    """Phase 2: Intelligent follow-up conversation with recruiters."""
    logger.info("=" * 60)
    logger.info("PHASE 2: Scanning for recruiter follow-ups...")
    return run_followup_pipeline()


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

    def run_all():
        if run_p1:
            run_phase1_pipeline()
        if run_p2:
            run_phase2_pipeline()

    if args.once:
        run_all()
        return

    # Loop mode
    while True:
        try:
            run_all()
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
