"""Pipeline router — trigger and monitor background pipeline execution."""

from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.pipeline_runner import get_status, start_pipeline

router = APIRouter()


class PipelineRunRequest(BaseModel):
    phase: str = "all"
    phases: List[str] = []


@router.post("/run")
def run_pipeline(request: PipelineRunRequest):
    """Start the pipeline in a background thread."""
    # Support both 'phase' (single string from frontend) and 'phases' (list)
    if request.phases:
        run_phases = request.phases
    elif request.phase == "all":
        run_phases = ["phase1", "phase2"]
    else:
        run_phases = [request.phase]

    valid_phases = {"phase1", "phase2"}
    invalid = [p for p in run_phases if p not in valid_phases]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid phases: {invalid}")
    if not run_phases:
        raise HTTPException(status_code=400, detail="At least one phase must be specified")

    started = start_pipeline(run_phases)
    if not started:
        raise HTTPException(status_code=409, detail="Pipeline is already running")

    return {"status": "started", "phases": run_phases}


@router.get("/status")
def pipeline_status():
    """Return the current pipeline status."""
    return get_status()
