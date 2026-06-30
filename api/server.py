"""
FastAPI server for the Claude Smart Email App.

Exposes two WebSocket endpoints that stream LangGraph progress events
back to the React UI as each node in the supervisor pipeline executes:

  /ws/process-emails   — kicks off the Gmail scan pipeline (Phase 1 + 2)
  /ws/process-jd       — accepts a pasted job description, runs JD flow

And one HTTP endpoint for downloading generated resumes:

  GET /api/resume/{filename}

Run:  uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

import apply_plans
import pending_replies
from blob_storage import bootstrap_state_from_blob, generate_resume_sas_url
from config import (
    CLAUDE_MODEL,
    CLAUDE_MODELS,
    CLAUDE_MODEL_IDS,
    CLAUDE_PRICING,
    GRAPH_RECURSION_LIMIT,
    IMAP_USER,
    MAX_EMAIL_AGE_HOURS,
    MAX_RESUME_ITERATIONS,
    RESUME_ACCEPTANCE_THRESHOLD,
    RESUME_OUTPUT_DIR,
    SCAN_FOLDERS,
    STATE_FILE_PATH,
)
import email_accounts
from graph import compile_graph
from smtp_send import send_pending_reply
from usage_tracker import get_snapshot, reset_session

# Pull any persisted state (processed emails, follow-up state, usage totals)
# from Azure Blob before the graph is compiled, so nodes see durable state.
bootstrap_state_from_blob()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("api.server")

app = FastAPI(title="Claude Smart Email App")

_cors_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3001,http://127.0.0.1:3001,http://localhost:5173,http://127.0.0.1:5173",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Compile the LangGraph once at startup — reused across requests.
_graph = compile_graph()


# ---------------------------------------------------------------------------
# Initial-state helpers
# ---------------------------------------------------------------------------

def _base_state() -> Dict[str, Any]:
    return {
        "next_node": "",
        "run_recruiter_scan": False,
        "run_followup_scan": False,
        "scan_folders": [],
        "scan_hours": 0,
        "scan_unread_only": True,
        "target_roles": [],
        "selected_model": "",
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
        "resume_recommend_decline": False,
        "resume_decline_reason": "",
        "max_resume_iterations": 0,          # 0 = use config default
        "resume_acceptance_threshold": 0.0,  # 0 = use config default
        "followup_emails": [],
        "current_followup_index": 0,
        "current_followup": {},
        "followup_processed": 0,
        "job_description_text": "",
        "job_description_done": False,
        "job_url": "",
        "job_url_fetched": False,
        "apply_plan_id": "",
        "errors": [],
        "summary": "",
    }


def _apply_quality_overrides(
    st: Dict[str, Any],
    max_iters: Optional[int] = None,
    threshold: Optional[float] = None,
) -> None:
    """Apply per-run quality knobs from the UI onto a base state dict."""
    if max_iters and max_iters > 0:
        st["max_resume_iterations"] = int(max_iters)
    if threshold and 0.0 < threshold <= 1.0:
        st["resume_acceptance_threshold"] = float(threshold)


def _apply_common_overrides(
    st: Dict[str, Any],
    model: Optional[str] = None,
    target_roles: Optional[List[str]] = None,
) -> None:
    """Apply per-run model + target-role overrides onto a base state dict."""
    if model:
        st["selected_model"] = model
    if target_roles:
        st["target_roles"] = [r.strip() for r in target_roles if isinstance(r, str) and r.strip()]


def _emails_state(
    folders: Optional[List[str]] = None,
    hours: Optional[int] = None,
    max_iters: Optional[int] = None,
    threshold: Optional[float] = None,
    model: Optional[str] = None,
    target_roles: Optional[List[str]] = None,
) -> Dict[str, Any]:
    st = _base_state()
    st["run_recruiter_scan"] = True
    st["run_followup_scan"] = True
    if folders:
        st["scan_folders"] = folders
        # Manual folder selection historically includes already-read emails.
        st["scan_unread_only"] = False
    if hours:
        st["scan_hours"] = hours
    _apply_quality_overrides(st, max_iters, threshold)
    _apply_common_overrides(st, model, target_roles)
    return st


# Allowed lookback windows for the Auto-Apply inbox scan (hours).
_AUTO_APPLY_HOURS = (24, 48, 72, 120)


def _auto_apply_state(
    hours: Optional[int] = None,
    max_iters: Optional[int] = None,
    threshold: Optional[float] = None,
    model: Optional[str] = None,
    target_roles: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """State for Auto-Apply: scan the INBOX for NEW job positions only.

    Runs the recruiter scan (and the resume generate/evaluate/draft loop) but
    skips the follow-up-reply scan, so it focuses purely on applying to fresh
    positions. Only unread, not-yet-processed emails are considered. Generated
    drafts land in the Application Tracker for 1-click review and send —
    nothing is emailed automatically.
    """
    st = _base_state()
    st["run_recruiter_scan"] = True
    st["run_followup_scan"] = False
    st["scan_folders"] = ["INBOX"]
    st["scan_unread_only"] = True
    if hours:
        st["scan_hours"] = hours
    _apply_quality_overrides(st, max_iters, threshold)
    _apply_common_overrides(st, model, target_roles)
    return st


def _jd_state(jd_text: str,
              max_iters: Optional[int] = None,
              threshold: Optional[float] = None,
              model: Optional[str] = None) -> Dict[str, Any]:
    st = _base_state()
    st["job_description_text"] = jd_text
    _apply_quality_overrides(st, max_iters, threshold)
    _apply_common_overrides(st, model)
    return st


def _apply_url_state(url: str,
                     max_iters: Optional[int] = None,
                     threshold: Optional[float] = None,
                     model: Optional[str] = None) -> Dict[str, Any]:
    st = _base_state()
    st["job_url"] = url
    _apply_quality_overrides(st, max_iters, threshold)
    _apply_common_overrides(st, model)
    return st


def _kickoff_quality(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract max_iters, threshold, model, and target_roles from a kickoff
    payload (validated/clamped)."""
    mi = payload.get("max_iterations")
    th = payload.get("acceptance_threshold")
    try:
        mi_int: Optional[int] = max(1, min(6, int(mi))) if mi is not None else None
    except (TypeError, ValueError):
        mi_int = None
    try:
        th_f: Optional[float] = max(0.5, min(0.99, float(th))) if th is not None else None
    except (TypeError, ValueError):
        th_f = None

    # Per-run model — only honor a known Claude id; else None (→ config default).
    raw_model = payload.get("model")
    model = raw_model if (isinstance(raw_model, str) and raw_model in CLAUDE_MODEL_IDS) else None

    # Target roles — accept a list of strings or a comma-separated string.
    raw_roles = payload.get("target_roles")
    roles: List[str] = []
    if isinstance(raw_roles, list):
        roles = [r.strip() for r in raw_roles if isinstance(r, str) and r.strip()]
    elif isinstance(raw_roles, str):
        roles = [r.strip() for r in raw_roles.split(",") if r.strip()]

    return {"max_iters": mi_int, "threshold": th_f, "model": model, "target_roles": roles}


# ---------------------------------------------------------------------------
# Progress-event shaping
# ---------------------------------------------------------------------------

_NODE_LABELS = {
    "supervisor_agent":                  "Supervisor deciding next step",
    "scan_recruiter_emails_node":        "Scanning Gmail for recruiter emails",
    "generate_resume_agent":             "Generating tailored resume (Claude)",
    "evaluate_resume_agent":             "Evaluating resume quality (Claude)",
    "render_and_draft_node":             "Creating Gmail draft reply",
    "scan_followup_emails_node":         "Scanning for recruiter follow-ups",
    "analyze_and_reply_followup_agent":  "Analyzing follow-up & drafting reply",
    "process_job_description_node":      "Processing pasted job description",
    "process_job_url_node":              "Fetching job posting from URL",
    "finalize_node":                     "Finalizing",
}


def _serialize_event(node_name: str, update: Dict[str, Any]) -> Dict[str, Any]:
    """Build a small, JSON-safe event from a LangGraph stream chunk."""
    current_email = update.get("current_email") or {}
    resume_path = update.get("resume_path") or ""
    resume_json = update.get("resume_json") or {}
    scanned_emails = update.get("scanned_emails")
    errors = update.get("errors") or []

    payload: Dict[str, Any] = {
        "event": "node_complete",
        "node": node_name,
        "label": _NODE_LABELS.get(node_name, node_name),
    }
    if current_email:
        payload["current_email"] = {
            "subject": current_email.get("subject", ""),
            "from_email": current_email.get("from_email", ""),
        }
    if resume_path:
        p = Path(resume_path)
        payload["resume"] = {
            "filename": p.name,
            "download_url": f"/api/resume/{p.name}",
            "role": resume_json.get("target_role_title", ""),
            "company": resume_json.get("staffing_company_name", ""),
        }
    if isinstance(scanned_emails, list):
        payload["scanned_count"] = len(scanned_emails)
    if errors:
        payload["errors"] = errors
    summary = update.get("summary")
    if summary:
        payload["summary"] = summary

    # Evaluator verdict — only surface when the evaluator actually ran, i.e.
    # resume_evaluation_done flipped to True. The generator also writes the
    # evaluation fields (to False/0.0) to reset them, but we don't want those
    # resets to show up in the UI as a real verdict.
    if update.get("resume_evaluation_done") is True:
        payload["evaluation"] = {
            "score": update.get("resume_evaluation_score", 0.0),
            "accepted": bool(update.get("resume_evaluation_accepted", False)),
            "feedback": update.get("resume_feedback", ""),
            "recommend_decline": bool(update.get("resume_recommend_decline", False)),
            "decline_reason": update.get("resume_decline_reason", ""),
        }
    if "resume_iterations" in update:
        payload["iteration"] = update["resume_iterations"]

    payload["usage"] = get_snapshot()
    return payload


# ---------------------------------------------------------------------------
# Pipeline streaming core
# ---------------------------------------------------------------------------

async def _stream_pipeline(websocket: WebSocket, initial_state: Dict[str, Any]) -> None:
    """Invoke the LangGraph pipeline and stream per-node progress to the client.

    The LangGraph graph is synchronous, so each node runs on the event-loop
    thread. To keep heartbeats alive under Gunicorn's UvicornWorker we execute
    the blocking `graph.stream()` iterator step-by-step inside a thread-pool
    via asyncio.to_thread, yielding back to the loop between chunks.
    """
    logger.info(
        "Pipeline starting — jd=%s recruiter=%s followup=%s max_iters=%s threshold=%s",
        bool(initial_state.get("job_description_text")),
        initial_state.get("run_recruiter_scan"),
        initial_state.get("run_followup_scan"),
        initial_state.get("max_resume_iterations") or MAX_RESUME_ITERATIONS,
        initial_state.get("resume_acceptance_threshold") or RESUME_ACCEPTANCE_THRESHOLD,
    )
    reset_session()
    effective_max = int(initial_state.get("max_resume_iterations") or 0) or MAX_RESUME_ITERATIONS
    effective_thr = float(initial_state.get("resume_acceptance_threshold") or 0.0) or RESUME_ACCEPTANCE_THRESHOLD
    try:
        await websocket.send_json({
            "event": "started",
            "usage": get_snapshot(),
            "quality": {
                "max_iterations": effective_max,
                "acceptance_threshold": effective_thr,
            },
        })
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send 'started' event")
        return

    try:
        stream_iter = _graph.stream(initial_state, {"recursion_limit": GRAPH_RECURSION_LIMIT})
        sentinel = object()

        def _next_chunk():
            try:
                return next(stream_iter)
            except StopIteration:
                return sentinel

        while True:
            chunk = await asyncio.to_thread(_next_chunk)
            if chunk is sentinel:
                break
            for node_name, update in chunk.items():
                logger.info("Node complete: %s (keys=%s)",
                            node_name, list((update or {}).keys()))
                await websocket.send_json(_serialize_event(node_name, update or {}))

        await websocket.send_json({"event": "done", "usage": get_snapshot()})
        logger.info("Pipeline done")
    except WebSocketDisconnect:
        logger.info("Client disconnected mid-pipeline")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Pipeline error")
        try:
            await websocket.send_json({"event": "error", "message": str(exc)})
        except Exception:
            pass


# ---------------------------------------------------------------------------
# WebSocket endpoints
# ---------------------------------------------------------------------------

@app.websocket("/ws/process-emails")
async def ws_process_emails(websocket: WebSocket) -> None:
    """
    Kick off the Gmail scan flow (recruiter + follow-ups).

    Protocol: the client MAY send a kickoff JSON with scan parameters:
        {"folders": ["INBOX","UPDATES"], "hours": 24}
    If nothing is sent within 500 ms, fall back to config defaults.
    """
    await websocket.accept()
    folders: Optional[List[str]] = None
    hours: Optional[int] = None
    quality: Dict[str, Any] = {"max_iters": None, "threshold": None}
    try:
        payload = await asyncio.wait_for(websocket.receive_json(), timeout=0.5)
        if isinstance(payload, dict):
            f = payload.get("folders")
            if isinstance(f, list) and all(isinstance(x, str) for x in f):
                folders = [x for x in f if x]
            h = payload.get("hours")
            if isinstance(h, (int, float)) and h > 0:
                hours = int(h)
            quality = _kickoff_quality(payload)
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError):
        pass

    await _stream_pipeline(
        websocket,
        _emails_state(folders=folders, hours=hours,
                      max_iters=quality["max_iters"], threshold=quality["threshold"],
                      model=quality["model"], target_roles=quality["target_roles"]),
    )
    try:
        await websocket.close()
    except Exception:
        pass


@app.websocket("/ws/auto-apply")
async def ws_auto_apply(websocket: WebSocket) -> None:
    """
    Auto-Apply: scan the Gmail INBOX for new job positions within the selected
    lookback window, generate a tailored resume for each, and queue every
    application as a draft for 1-click review/send. Recruiter scan only — the
    follow-up-reply scan is skipped.

    Protocol: client sends a kickoff JSON:
        {"hours": 24|48|72|120, "max_iterations": N, "acceptance_threshold": F}
    `hours` is clamped to the allowed set; anything else falls back to 24.
    """
    await websocket.accept()
    hours: int = 24
    quality: Dict[str, Any] = {"max_iters": None, "threshold": None}
    try:
        payload = await asyncio.wait_for(websocket.receive_json(), timeout=0.5)
        if isinstance(payload, dict):
            h = payload.get("hours")
            if isinstance(h, (int, float)) and int(h) in _AUTO_APPLY_HOURS:
                hours = int(h)
            quality = _kickoff_quality(payload)
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError):
        pass

    await _stream_pipeline(
        websocket,
        _auto_apply_state(hours=hours,
                          max_iters=quality["max_iters"], threshold=quality["threshold"],
                          model=quality["model"], target_roles=quality["target_roles"]),
    )
    try:
        await websocket.close()
    except Exception:
        pass


@app.websocket("/ws/process-jd")
async def ws_process_jd(websocket: WebSocket) -> None:
    """
    Accept a pasted job description and run only the JD → resume flow.

    Protocol: client sends {"job_description": "..."} once, then receives
    progress events, ending in {"event": "done"}.
    """
    await websocket.accept()
    try:
        data = await websocket.receive_json()
    except WebSocketDisconnect:
        return

    jd_text = (data or {}).get("job_description", "").strip()
    if not jd_text:
        await websocket.send_json({"event": "error", "message": "Empty job description"})
        await websocket.close()
        return

    q = _kickoff_quality(data if isinstance(data, dict) else {})
    await _stream_pipeline(
        websocket,
        _jd_state(jd_text, max_iters=q["max_iters"], threshold=q["threshold"], model=q["model"]),
    )
    try:
        await websocket.close()
    except Exception:
        pass


@app.websocket("/ws/apply-from-url")
async def ws_apply_from_url(websocket: WebSocket) -> None:
    """
    Accept a job posting URL, fetch the JD, generate a tailored resume,
    and park the result in Apply History as status=ready.

    Protocol: client sends {"url": "..."}; server streams the same
    node-by-node progress events used by the other flows.
    """
    await websocket.accept()
    try:
        data = await websocket.receive_json()
    except WebSocketDisconnect:
        return

    url = (data or {}).get("url", "").strip()
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        await websocket.send_json({"event": "error", "message": "Provide a valid http(s) URL"})
        await websocket.close()
        return

    q = _kickoff_quality(data if isinstance(data, dict) else {})
    await _stream_pipeline(
        websocket,
        _apply_url_state(url, max_iters=q["max_iters"], threshold=q["threshold"], model=q["model"]),
    )
    try:
        await websocket.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/usage")
def usage() -> Dict[str, Any]:
    """Return current session + persisted total token/cost usage."""
    return get_snapshot()


@app.get("/api/config")
def config_info() -> Dict[str, Any]:
    """UI-facing config defaults — current Gmail account, folders, lookback window."""
    from agents.scan_recruiter_emails_node import list_imap_folders
    live_folders = list_imap_folders()
    active_email, _ = email_accounts.get_active_credentials()
    return {
        "gmail_account": active_email or IMAP_USER,
        "accounts": email_accounts.list_accounts(),
        "available_folders": live_folders,
        "default_folders": list(SCAN_FOLDERS),
        "default_hours": MAX_EMAIL_AGE_HOURS,
        "duration_options_hours": [24, 48, 72, 168],
        "auto_apply_duration_options_hours": list(_AUTO_APPLY_HOURS),
        "default_max_iterations": MAX_RESUME_ITERATIONS,
        "default_acceptance_threshold": RESUME_ACCEPTANCE_THRESHOLD,
        "max_iteration_options": [1, 2, 3, 4, 5],
        "threshold_options": [0.70, 0.75, 0.80, 0.85, 0.90],
        "model_options": CLAUDE_MODELS,
        "default_model": CLAUDE_MODEL,
    }


@app.get("/api/pricing")
def pricing() -> Dict[str, Any]:
    """Current Claude model pricing (USD per 1M tokens) for the Compare Pricing UI."""
    return {"currency": "USD", "unit": "per 1M tokens", "models": CLAUDE_PRICING}


# ---------------------------------------------------------------------------
# Connected email accounts
# ---------------------------------------------------------------------------

class AddAccountBody(BaseModel):
    email: str
    app_password: str


@app.get("/api/accounts")
def accounts_list() -> Dict[str, Any]:
    return {"items": email_accounts.list_accounts()}


@app.post("/api/accounts")
def accounts_add(body: AddAccountBody) -> Dict[str, Any]:
    try:
        return email_accounts.add_account(body.email, body.app_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/accounts/{account_id}/activate")
def accounts_activate(account_id: str) -> Dict[str, Any]:
    if not email_accounts.set_active(account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    return {"items": email_accounts.list_accounts()}


@app.delete("/api/accounts/{account_id}")
def accounts_delete(account_id: str) -> Dict[str, Any]:
    if not email_accounts.delete_account(account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    return {"items": email_accounts.list_accounts()}


@app.get("/api/imap-folders")
def imap_folders() -> Dict[str, Any]:
    """Return the live list of IMAP folder/label names from Gmail."""
    from agents.scan_recruiter_emails_node import list_imap_folders
    return {"folders": list_imap_folders()}


# ---------------------------------------------------------------------------
# Processed emails — state file helpers
# ---------------------------------------------------------------------------

_state_lock = threading.RLock()

_TERMINAL_EMAIL_STATUSES = {"new", "approved", "rejected", "cancelled", "sent", "archived"}


def _normalize_email_status(raw_status: str) -> str:
    """Map legacy statuses to 'new'."""
    return "new" if raw_status in ("processed", "pending_review", "", None) else raw_status


def _read_state_raw() -> Dict[str, Any]:
    if not STATE_FILE_PATH.exists():
        return {}
    try:
        data = json.loads(STATE_FILE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_state_raw(raw: Dict[str, Any]) -> None:
    STATE_FILE_PATH.write_text(
        json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    try:
        from blob_storage import upload_state_file
        upload_state_file(STATE_FILE_PATH)
    except Exception:  # noqa: BLE001
        pass


def _build_email_item(message_id: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    resume_file = entry.get("resume_file", "")
    resume_name = Path(resume_file).name if resume_file else ""
    return {
        "message_id": message_id,
        "subject": entry.get("subject", ""),
        "from_email": entry.get("from_email", ""),
        "processed_at": entry.get("processed_at", ""),
        "resume_filename": resume_name,
        "resume_download_url": f"/api/resume/{resume_name}" if resume_name else "",
        "pending_reply_id": entry.get("pending_reply_id", ""),
        "status": _normalize_email_status(entry.get("status", "")),
    }


@app.get("/api/processed-emails")
def processed_emails_list(status: Optional[str] = None) -> Dict[str, Any]:
    """Return the processed_emails ledger as a list (newest first).

    Optional ?status= filter: new | approved | rejected | cancelled | sent | all
    """
    with _state_lock:
        raw = _read_state_raw()

    items: List[Dict[str, Any]] = []
    for message_id, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        item = _build_email_item(message_id, entry)
        if status and status != "all" and item["status"] != status:
            continue
        items.append(item)
    items.sort(key=lambda x: x.get("processed_at", ""), reverse=True)
    return {"items": items}


class UpdateEmailStatusBody(BaseModel):
    status: str


@app.patch("/api/processed-emails/{message_id}/status")
def update_processed_email_status(message_id: str, body: UpdateEmailStatusBody) -> Dict[str, Any]:
    """Update the review status of a processed email."""
    if body.status not in _TERMINAL_EMAIL_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status '{body.status}'")
    with _state_lock:
        raw = _read_state_raw()
        if message_id not in raw:
            raise HTTPException(status_code=404, detail="Email not found")
        raw[message_id]["status"] = body.status
        _write_state_raw(raw)
        return _build_email_item(message_id, raw[message_id])


def _send_message_email(message_id: str) -> Dict[str, Any]:
    """Core SMTP send for a processed email's queued draft. Raises HTTPException
    on failure; returns the updated item on success."""
    with _state_lock:
        raw = _read_state_raw()
        if message_id not in raw:
            raise HTTPException(status_code=404, detail="Email not found")
        entry = raw[message_id]

    pending_reply_id = entry.get("pending_reply_id", "")
    # Look up by stored ID first; fall back to searching by original message_id.
    item = pending_replies.get(pending_reply_id) if pending_reply_id else None
    if not item:
        matches = [
            r for r in pending_replies.list_pending(status=None)
            if r.get("original", {}).get("message_id") == message_id
            and r.get("status") not in ("sent", "cancelled")
        ]
        item = matches[0] if matches else None

    if not item:
        raise HTTPException(
            status_code=400,
            detail="No draft found for this email.",
        )

    err = send_pending_reply(item)
    if err:
        raise HTTPException(status_code=502, detail=f"SMTP send failed: {err}")

    if pending_reply_id:
        pending_replies.mark_status(pending_reply_id, "sent")

    with _state_lock:
        raw = _read_state_raw()
        if message_id in raw:
            raw[message_id]["status"] = "sent"
            _write_state_raw(raw)
        return _build_email_item(message_id, raw.get(message_id, entry))


@app.post("/api/processed-emails/{message_id}/send")
def send_processed_email_endpoint(message_id: str) -> Dict[str, Any]:
    """Send the draft email with attached resume via SMTP (must be approved)."""
    with _state_lock:
        raw = _read_state_raw()
        if message_id not in raw:
            raise HTTPException(status_code=404, detail="Email not found")
        entry = raw[message_id]
    if _normalize_email_status(entry.get("status", "")) != "approved":
        raise HTTPException(status_code=409, detail="Email must be in 'approved' status to send")
    return _send_message_email(message_id)


@app.post("/api/processed-emails/{message_id}/approve-send")
def approve_and_send_processed_email(message_id: str) -> Dict[str, Any]:
    """Approve and immediately send a processed email's draft in one step."""
    with _state_lock:
        raw = _read_state_raw()
        if message_id not in raw:
            raise HTTPException(status_code=404, detail="Email not found")
        if _normalize_email_status(raw[message_id].get("status", "")) not in ("new", "approved"):
            raise HTTPException(status_code=409, detail="Email must be New or Approved to send")
        raw[message_id]["status"] = "approved"
        _write_state_raw(raw)
    return _send_message_email(message_id)


class BulkIdsBody(BaseModel):
    message_ids: List[str]


@app.post("/api/processed-emails/bulk-approve-send")
def bulk_approve_and_send(body: BulkIdsBody) -> Dict[str, Any]:
    """Approve + send several drafts. Returns per-id results (best-effort)."""
    if not body.message_ids:
        raise HTTPException(status_code=400, detail="message_ids must not be empty")
    sent: List[str] = []
    failed: List[Dict[str, str]] = []
    for mid in body.message_ids:
        try:
            with _state_lock:
                raw = _read_state_raw()
                if mid not in raw:
                    failed.append({"message_id": mid, "error": "not found"})
                    continue
                if _normalize_email_status(raw[mid].get("status", "")) not in ("new", "approved"):
                    failed.append({"message_id": mid, "error": "not sendable"})
                    continue
                raw[mid]["status"] = "approved"
                _write_state_raw(raw)
            _send_message_email(mid)
            sent.append(mid)
        except HTTPException as exc:
            failed.append({"message_id": mid, "error": str(exc.detail)})
        except Exception as exc:  # noqa: BLE001
            failed.append({"message_id": mid, "error": str(exc)})
    return {"sent": sent, "failed": failed, "sent_count": len(sent)}


class BulkStatusBody(BaseModel):
    message_ids: List[str]
    status: str


@app.post("/api/processed-emails/bulk-status")
def bulk_update_email_status(body: BulkStatusBody) -> Dict[str, Any]:
    """Set the same status on multiple emails at once (e.g. bulk archive)."""
    if body.status not in _TERMINAL_EMAIL_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status '{body.status}'")
    if not body.message_ids:
        raise HTTPException(status_code=400, detail="message_ids must not be empty")
    with _state_lock:
        raw = _read_state_raw()
        updated = []
        for mid in body.message_ids:
            if mid in raw:
                raw[mid]["status"] = body.status
                updated.append(mid)
        _write_state_raw(raw)
    return {"updated": updated, "count": len(updated)}


# ---------------------------------------------------------------------------
# Conversations — human-in-the-loop for pending replies
# ---------------------------------------------------------------------------

class EditReplyBody(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None


@app.get("/api/conversations")
def list_conversations(status: str = "pending") -> Dict[str, Any]:
    """List pending / approved / cancelled conversations."""
    if status == "all":
        return {"items": pending_replies.list_pending(status=None)}
    return {"items": pending_replies.list_pending(status=status)}


@app.get("/api/conversations/{reply_id}")
def get_conversation(reply_id: str) -> Dict[str, Any]:
    item = pending_replies.get(reply_id)
    if not item:
        raise HTTPException(status_code=404, detail="Reply not found")
    return item


@app.post("/api/conversations/{reply_id}/edit")
def edit_conversation(reply_id: str, body: EditReplyBody) -> Dict[str, Any]:
    updated = pending_replies.update_reply_text(reply_id, body.subject, body.body)
    if not updated:
        raise HTTPException(status_code=404, detail="Reply not found")
    return updated


@app.post("/api/conversations/{reply_id}/cancel")
def cancel_conversation(reply_id: str) -> Dict[str, Any]:
    updated = pending_replies.mark_status(reply_id, "cancelled")
    if not updated:
        raise HTTPException(status_code=404, detail="Reply not found")
    return updated


@app.post("/api/conversations/{reply_id}/approve")
def approve_conversation(reply_id: str) -> Dict[str, Any]:
    """Approve and SEND the pending reply via SMTP."""
    item = pending_replies.get(reply_id)
    if not item:
        raise HTTPException(status_code=404, detail="Reply not found")
    if item.get("status") != "pending":
        raise HTTPException(status_code=409, detail=f"Reply already {item.get('status')}")

    err = send_pending_reply(item)
    if err:
        pending_replies.mark_status(reply_id, "send_failed", last_error=err)
        raise HTTPException(status_code=502, detail=f"SMTP send failed: {err}")

    updated = pending_replies.mark_status(reply_id, "sent", sent_at_iso=item["updated_at"])
    return updated or item


# ---------------------------------------------------------------------------
# Apply plans — job applications prepared from pasted URLs
# ---------------------------------------------------------------------------

class ApplyNotesBody(BaseModel):
    notes: Optional[str] = ""


@app.get("/api/apply-plans")
def list_apply_plans(status: str = "all") -> Dict[str, Any]:
    return {"items": apply_plans.list_plans(status=status)}


@app.get("/api/apply-plans/{plan_id}")
def get_apply_plan(plan_id: str) -> Dict[str, Any]:
    item = apply_plans.get(plan_id)
    if not item:
        raise HTTPException(status_code=404, detail="Apply plan not found")
    return item


@app.post("/api/apply-plans/{plan_id}/mark-applied")
def apply_plan_mark_applied(plan_id: str, body: ApplyNotesBody) -> Dict[str, Any]:
    updated = apply_plans.mark_applied(plan_id, notes=body.notes or "")
    if not updated:
        raise HTTPException(status_code=404, detail="Apply plan not found")
    return updated


@app.post("/api/apply-plans/{plan_id}/cancel")
def apply_plan_cancel(plan_id: str) -> Dict[str, Any]:
    updated = apply_plans.cancel(plan_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Apply plan not found")
    return updated


@app.delete("/api/apply-plans/{plan_id}")
def apply_plan_delete(plan_id: str) -> Dict[str, Any]:
    ok = apply_plans.delete(plan_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Apply plan not found")
    return {"deleted": plan_id}


@app.get("/api/resume/{filename}")
def download_resume(filename: str):
    """Serve a generated resume DOCX.

    When Azure Blob is configured we 302-redirect to a short-lived SAS URL so
    the file survives Web App restarts. Otherwise we stream from local disk.
    """
    safe_name = Path(filename).name  # strip any path traversal

    sas_url = generate_resume_sas_url(safe_name)
    if sas_url:
        return RedirectResponse(url=sas_url, status_code=302)

    path = RESUME_OUTPUT_DIR / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Resume not found")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=safe_name,
    )
