from __future__ import annotations
from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from .runtime import get_agent_runtime_v2, LANGGRAPH_USED, LANGGRAPH_BLOCKER
from .state import CANONICAL_AGENT_VERSION

router = APIRouter(prefix="/v2/agent", tags=["Agent V2"])

class CreateRunRequest(BaseModel):
    goal: str
    mode: str = "read_only"
    user_id: str = "local"

@router.get("/capabilities")
def capabilities():
    rt = get_agent_runtime_v2()
    return {"ok": True, "canonical": True, "version": CANONICAL_AGENT_VERSION, "capabilities": rt.list_capabilities()}

@router.get("/status")
def status():
    rt = get_agent_runtime_v2()
    return {"ok": True, "canonical_for_new_agent_runs": True, "backend": rt.backend, "langgraph_used": LANGGRAPH_USED, "langgraph_blocker": LANGGRAPH_BLOCKER, "runs": len(rt.list_runs()), "legacy_agent_status": "legacy_compatible_not_canonical"}

@router.get("/runs")
def list_runs():
    return {"ok": True, "runs": get_agent_runtime_v2().list_runs()}

@router.post("/runs")
def create_run(req: CreateRunRequest):
    if not req.goal.strip():
        raise HTTPException(status_code=400, detail="goal required")
    return {"ok": True, "run": get_agent_runtime_v2().create_run(req.goal, req.mode, req.user_id)}

@router.get("/runs/{run_id}")
def get_run(run_id: str):
    try: return {"ok": True, "run": get_agent_runtime_v2().get_run(run_id)}
    except KeyError: raise HTTPException(status_code=404, detail="run not found")

@router.post("/runs/{run_id}/plan")
def plan_run(run_id: str):
    try: return {"ok": True, "run": get_agent_runtime_v2().plan_run(run_id)}
    except KeyError: raise HTTPException(status_code=404, detail="run not found")

@router.post("/runs/{run_id}/execute")
def execute_run(run_id: str):
    try: return {"ok": True, "run": get_agent_runtime_v2().execute_run(run_id)}
    except KeyError: raise HTTPException(status_code=404, detail="run not found")

@router.post("/runs/{run_id}/pause")
def pause_run(run_id: str):
    try: return {"ok": True, "run": get_agent_runtime_v2().pause_run(run_id)}
    except KeyError: raise HTTPException(status_code=404, detail="run not found")

@router.post("/runs/{run_id}/resume")
def resume_run(run_id: str):
    try: return {"ok": True, "run": get_agent_runtime_v2().resume_run(run_id)}
    except KeyError: raise HTTPException(status_code=404, detail="run not found")

@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str):
    try: return {"ok": True, "run": get_agent_runtime_v2().cancel_run(run_id)}
    except KeyError: raise HTTPException(status_code=404, detail="run not found")

@router.get("/runs/{run_id}/trace")
def get_trace(run_id: str):
    return {"ok": True, "run_id": run_id, "trace": get_agent_runtime_v2().get_trace(run_id)}
