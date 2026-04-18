"""
Apply-plans store — the job-application queue.

Each entry represents one job posting the user has asked the app to prepare
an application for. Lifecycle:

    planning  →  ready  →  applied
                   │
                   └─→ cancelled

- `planning`  the JD is being fetched / resume is being generated
- `ready`     the tailored resume + autofill plan are waiting for the user
- `applied`   the user confirmed they applied (manually today; Playwright
              autofill in a later iteration)
- `cancelled` user dismissed this one

Persistence: JSON on disk, mirrored to Azure Blob (state/apply_plans.json)
via blob_storage.upload_state_file — same pattern as pending_replies.
"""

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import APPLY_PLANS_PATH

logger = logging.getLogger(__name__)

_lock = threading.RLock()


def _load() -> List[Dict[str, Any]]:
    if not APPLY_PLANS_PATH.exists():
        return []
    try:
        data = json.loads(APPLY_PLANS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save(items: List[Dict[str, Any]]) -> None:
    try:
        APPLY_PLANS_PATH.write_text(
            json.dumps(items, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Could not persist apply_plans locally: %s", exc)
        return
    try:
        from blob_storage import upload_state_file
        upload_state_file(APPLY_PLANS_PATH)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Blob sync of apply_plans skipped: %s", exc)


def list_plans(status: Optional[str] = None) -> List[Dict[str, Any]]:
    with _lock:
        items = _load()
    if status is None or status == "all":
        return items
    return [i for i in items if i.get("status") == status]


def get(plan_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        for item in _load():
            if item.get("id") == plan_id:
                return item
    return None


def create(
    *,
    job_url: str,
    job_title: str = "",
    company_name: str = "",
    source: str = "",
    jd_text: str = "",
    status: str = "planning",
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    item = {
        "id": str(uuid.uuid4()),
        "status": status,
        "job_url": job_url,
        "job_title": job_title,
        "company_name": company_name,
        "source": source,
        "jd_text": jd_text,
        "resume_filename": "",
        "resume_path": "",
        "target_role_title": "",
        "staffing_company_name": "",
        "notes": "",
        "created_at": now,
        "updated_at": now,
        "applied_at": "",
    }
    with _lock:
        items = _load()
        items.insert(0, item)
        _save(items)
    logger.info("Apply plan created: id=%s url=%s", item["id"], job_url)
    return item


def update(plan_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
    with _lock:
        items = _load()
        for item in items:
            if item.get("id") == plan_id:
                item.update(fields)
                item["updated_at"] = datetime.now(timezone.utc).isoformat()
                _save(items)
                return item
    return None


def mark_applied(plan_id: str, notes: str = "") -> Optional[Dict[str, Any]]:
    return update(
        plan_id,
        status="applied",
        applied_at=datetime.now(timezone.utc).isoformat(),
        notes=notes,
    )


def cancel(plan_id: str) -> Optional[Dict[str, Any]]:
    return update(plan_id, status="cancelled")


def delete(plan_id: str) -> bool:
    with _lock:
        items = _load()
        new_items = [i for i in items if i.get("id") != plan_id]
        if len(new_items) == len(items):
            return False
        _save(new_items)
        return True
