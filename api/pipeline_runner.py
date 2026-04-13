"""
Background pipeline execution for the Smart Email App.
Runs Phase 1 and/or Phase 2 in a background thread.
"""

import logging
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

# Ensure project root is on sys.path so we can import main
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

logger = logging.getLogger(__name__)

_status: Dict = {
    "running": False,
    "current_phase": None,
    "last_run": None,
    "last_result": None,
    "emails_processed": 0,
}

_lock = threading.Lock()


def _run_pipeline(phases: List[str]) -> None:
    """Execute the pipeline phases in sequence."""
    from main import run_phase1_pipeline, run_phase2_pipeline

    global _status
    total_processed = 0

    try:
        if "phase1" in phases:
            with _lock:
                _status["current_phase"] = "phase1"
            count = run_phase1_pipeline()
            total_processed += count

        if "phase2" in phases:
            with _lock:
                _status["current_phase"] = "phase2"
            count = run_phase2_pipeline()
            total_processed += count

        with _lock:
            _status["last_result"] = "success"
            _status["emails_processed"] = total_processed

    except Exception as e:
        logger.error("Pipeline error: %s", e, exc_info=True)
        with _lock:
            _status["last_result"] = f"error: {e}"

    finally:
        with _lock:
            _status["running"] = False
            _status["current_phase"] = None
            _status["last_run"] = datetime.now(timezone.utc).isoformat()


def start_pipeline(phases: List[str]) -> bool:
    """
    Start the pipeline in a background thread.
    Returns True if started, False if already running.
    """
    global _status
    with _lock:
        if _status["running"]:
            return False
        _status["running"] = True
        _status["current_phase"] = None
        _status["last_result"] = None
        _status["emails_processed"] = 0

    thread = threading.Thread(target=_run_pipeline, args=(phases,), daemon=True)
    thread.start()
    return True


def get_status() -> Dict:
    """Return the current pipeline status."""
    with _lock:
        return dict(_status)
