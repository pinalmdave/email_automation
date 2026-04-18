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
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

import pending_replies
from blob_storage import bootstrap_state_from_blob, generate_resume_sas_url
from config import (
    GRAPH_RECURSION_LIMIT,
    IMAP_USER,
    MAX_EMAIL_AGE_HOURS,
    RESUME_OUTPUT_DIR,
    SCAN_FOLDERS,
    STATE_FILE_PATH,
)
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
        "job_description_text": "",
        "job_description_done": False,
        "errors": [],
        "summary": "",
    }


def _emails_state(
    folders: Optional[List[str]] = None,
    hours: Optional[int] = None,
) -> Dict[str, Any]:
    st = _base_state()
    st["run_recruiter_scan"] = True
    st["run_followup_scan"] = True
    if folders:
        st["scan_folders"] = folders
    if hours:
        st["scan_hours"] = hours
    return st


def _jd_state(jd_text: str) -> Dict[str, Any]:
    st = _base_state()
    st["job_description_text"] = jd_text
    return st


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
    logger.info("Pipeline starting — initial flags: jd=%s recruiter=%s followup=%s",
                bool(initial_state.get("job_description_text")),
                initial_state.get("run_recruiter_scan"),
                initial_state.get("run_followup_scan"))
    reset_session()
    try:
        await websocket.send_json({"event": "started", "usage": get_snapshot()})
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
    try:
        payload = await asyncio.wait_for(websocket.receive_json(), timeout=0.5)
        if isinstance(payload, dict):
            f = payload.get("folders")
            if isinstance(f, list) and all(isinstance(x, str) for x in f):
                folders = [x for x in f if x]
            h = payload.get("hours")
            if isinstance(h, (int, float)) and h > 0:
                hours = int(h)
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError):
        pass

    await _stream_pipeline(websocket, _emails_state(folders=folders, hours=hours))
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

    await _stream_pipeline(websocket, _jd_state(jd_text))
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
    return {
        "gmail_account": IMAP_USER,
        "available_folders": list(SCAN_FOLDERS),
        "default_folders": list(SCAN_FOLDERS),
        "default_hours": MAX_EMAIL_AGE_HOURS,
        "duration_options_hours": [24, 48, 72, 168],
    }


@app.get("/api/processed-emails")
def processed_emails_list() -> Dict[str, Any]:
    """Return the processed_emails ledger as a list (newest first)."""
    if not STATE_FILE_PATH.exists():
        return {"items": []}
    try:
        raw = json.loads(STATE_FILE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"items": []}

    items: List[Dict[str, Any]] = []
    for message_id, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        resume_file = entry.get("resume_file", "")
        resume_name = Path(resume_file).name if resume_file else ""
        items.append({
            "message_id": message_id,
            "subject": entry.get("subject", ""),
            "from_email": entry.get("from_email", ""),
            "processed_at": entry.get("processed_at", ""),
            "resume_filename": resume_name,
            "resume_download_url": f"/api/resume/{resume_name}" if resume_name else "",
            "pending_reply_id": entry.get("pending_reply_id", ""),
            "status": entry.get("status", "processed"),
        })
    items.sort(key=lambda x: x.get("processed_at", ""), reverse=True)
    return {"items": items}


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
