"""
Tracks processed emails in a JSON file to avoid reprocessing.
Each entry maps message_id -> {processed_at, subject, from_email, resume_file}.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict

from config import STATE_FILE_PATH

logger = logging.getLogger(__name__)


def load_state() -> Dict:
    if not STATE_FILE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_FILE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read state file, starting fresh: %s", e)
        return {}


def save_state(state: Dict) -> None:
    STATE_FILE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def is_processed(message_id: str) -> bool:
    if not message_id:
        return False
    state = load_state()
    return message_id in state


def mark_processed(message_id: str, subject: str, from_email: str, resume_file: str) -> None:
    state = load_state()
    state[message_id] = {
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "subject": subject,
        "from_email": from_email,
        "resume_file": resume_file,
    }
    save_state(state)
    logger.info("Marked as processed: %s", message_id)
