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
import logging
import os
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from config import RESUME_OUTPUT_DIR
from graph import compile_graph
from usage_tracker import get_snapshot, reset_session

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
        "job_description_text": "",
        "job_description_done": False,
        "errors": [],
        "summary": "",
    }


def _emails_state() -> Dict[str, Any]:
    st = _base_state()
    st["run_recruiter_scan"] = True
    st["run_followup_scan"] = True
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
    payload["usage"] = get_snapshot()
    return payload


# ---------------------------------------------------------------------------
# Pipeline streaming core
# ---------------------------------------------------------------------------

async def _stream_pipeline(websocket: WebSocket, initial_state: Dict[str, Any]) -> None:
    """Invoke the LangGraph pipeline and stream per-node progress to the client."""
    reset_session()
    await websocket.send_json({"event": "started", "usage": get_snapshot()})
    try:
        # graph.stream is sync — run it in a thread so the event loop stays free
        # and we can push events as each node completes.
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def run_pipeline() -> None:
            try:
                for chunk in _graph.stream(initial_state, {"recursion_limit": 100}):
                    for node_name, update in chunk.items():
                        loop.call_soon_threadsafe(queue.put_nowait, (node_name, update))
                loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel
            except Exception as exc:  # noqa: BLE001
                loop.call_soon_threadsafe(queue.put_nowait, exc)

        task = loop.run_in_executor(None, run_pipeline)

        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, Exception):
                raise item
            node_name, update = item
            await websocket.send_json(_serialize_event(node_name, update))

        await task  # surface any late exception
        await websocket.send_json({"event": "done", "usage": get_snapshot()})
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
    """Kick off the Gmail scan flow (recruiter + follow-ups) on connect."""
    await websocket.accept()
    await _stream_pipeline(websocket, _emails_state())
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


@app.get("/api/resume/{filename}")
def download_resume(filename: str):
    """Serve a generated resume DOCX from the output directory."""
    # Guard against path traversal.
    safe_name = Path(filename).name
    path = RESUME_OUTPUT_DIR / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Resume not found")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=safe_name,
    )
