from __future__ import annotations
from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from .finalizer import PRIMARY_KIMI_MODEL
from .runtime import get_agent_runtime_v2, LANGGRAPH_USED, LANGGRAPH_BLOCKER
from .state import CANONICAL_AGENT_VERSION

router = APIRouter(prefix="/v2/agent", tags=["Agent V2"])
chat_router = APIRouter(prefix="/v2/chat", tags=["Agent V2 Chat"])

class CreateRunRequest(BaseModel):
    goal: str
    mode: str = "read_only"
    user_id: str = "local"

class AgentChatRequest(BaseModel):
    message: str
    mode: str = "read_only"
    user_id: str = "local"

@router.get("/capabilities")
def capabilities():
    rt = get_agent_runtime_v2()
    return {
        "ok": True,
        "canonical": True,
        "version": CANONICAL_AGENT_VERSION,
        "backend": rt.backend,
        "langgraph_used": LANGGRAPH_USED,
        "primary_finalizer_model": PRIMARY_KIMI_MODEL,
        "planner_classes": [
            "repo_audit", "code_search", "endpoint_probe", "memory_question", "dashboard_diagnosis",
            "provider_diagnosis", "frontend_diagnosis", "smoke_test", "documentation_task",
            "safe_patch_dry_run", "approval_required_write", "general_reasoning",
        ],
        "capabilities": rt.list_capabilities(),
    }

@router.get("/status")
def status():
    rt = get_agent_runtime_v2()
    runs = rt.list_runs()
    latest = runs[-1] if runs else None
    latest_meta = (latest or {}).get("provider_metadata") or {}
    return {
        "ok": True,
        "canonical_for_new_agent_runs": True,
        "backend": rt.backend,
        "langgraph_used": LANGGRAPH_USED,
        "langgraph_blocker": LANGGRAPH_BLOCKER,
        "runs": len(runs),
        "primary_finalizer_model": PRIMARY_KIMI_MODEL,
        "latest_provider_used": latest_meta.get("provider_used"),
        "latest_model_used": latest_meta.get("model_used"),
        "latest_provider_degraded": latest_meta.get("provider_degraded"),
        "trace_available": True,
        "checkpointed": True,
        "legacy_agent_status": "legacy_compatible_not_canonical",
    }

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
    trace = get_agent_runtime_v2().get_trace(run_id)
    return {
        "ok": True,
        "run_id": run_id,
        "trace": trace,
        "event_count": len(trace),
    }

@router.get("/operator-presets")
def operator_presets():
    from .operator_presets import list_operator_presets
    return {"ok": True, "presets": list_operator_presets()}

@router.get("/maintenance/modes")
def maintenance_modes():
    return {
        "ok": True,
        "repo_maintenance_read_only": True,
        "repo_maintenance_dry_run": True,
        "repo_maintenance_approval_required": True,
        "can_inspect_repo": True,
        "can_run_allowlisted_smoke_tests": True,
        "can_propose_patches_dry_run": True,
        "patch_apply_requires_approval": True,
        "commit_requires_approval": True,
        "push_requires_external_operator": True,
        "semantic_faiss_writes_blocked": True,
        "trading_blocked": True,
    }

@chat_router.post("/agent")
def chat_agent(req: AgentChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message required")
    from .governance import validate_mode, parse_mode_from_message
    nl_mode = parse_mode_from_message(req.message.strip())
    validated_mode = nl_mode or validate_mode(req.mode)
    rt = get_agent_runtime_v2()
    run = rt.create_run(req.message, validated_mode, req.user_id)
    run = rt.plan_run(run["run_id"])
    run = rt.execute_run(run["run_id"])
    return {
        "ok": True,
        "canonical_agent_v2": True,
        "route": "/v2/chat/agent",
        "run_id": run["run_id"],
        "trace_url": f"/v2/agent/runs/{run['run_id']}/trace",
        "final_answer": run.get("final_answer"),
        "provider_metadata": run.get("provider_metadata") or {},
        "classification": run.get("classification"),
        "status": run.get("status"),
        "mode_requested": run.get("mode_requested"),
        "mode_effective": run.get("mode_effective"),
        "auto_decision": run.get("auto_decision"),
        "mode_escalation_required": run.get("mode_escalation_required"),
        "mode_escalation_reason": run.get("mode_escalation_reason"),
        "required_permission": run.get("required_permission"),
        "expected_write_scope": run.get("expected_write_scope"),
        "confirmation_id": run.get("confirmation_id"),
        "blocked_tools": run.get("blocked_tools"),
    }
