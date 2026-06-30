from __future__ import annotations
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from .finalizer import PRIMARY_KIMI_MODEL
from .runtime import get_agent_runtime_v2
from .response_normalizer import normalize_agent_v2_chat_response
from .state import CANONICAL_AGENT_VERSION
from brain_v9.api_security import require_strict_operator_access


def _build_capability_metadata(run: Dict[str, Any]) -> Dict[str, Any]:
    """Derive capability activation metadata from the V2 run object."""
    plan = run.get("plan") or []
    intent_route = run.get("intent_route")
    semantic_steps = [s for s in plan if s.get("tool_name") == "semantic_retrieve"]
    retrieval_attempted = bool(semantic_steps)
    retrieval_no_results = any(
        not (s.get("output", {}).get("result", {}).get("hits", []))
        for s in semantic_steps
    )
    retrieval_skipped = (
        not retrieval_attempted
        and intent_route not in {"direct_assistant", "promotion_adapter_dry_run"}
    )
    tools_considered = [s for s in plan if s.get("tool_name")]
    tools_executed = [
        s for s in tools_considered
        if s.get("status") in ("completed", "failed", "blocked")
    ]
    return {
        "memory_used": retrieval_attempted,
        "retrieval_attempted": retrieval_attempted,
        "retrieval_no_results": retrieval_no_results,
        "retrieval_skipped": retrieval_skipped,
        "planner_used": bool(plan and any(s.get("tool_name") for s in plan)),
        "evidence_routed": bool(run.get("evidence_sources")),
        "evidence_sources_count": len(run.get("evidence_sources") or []),
        "tools_considered": len(tools_considered),
        "tools_executed": len(tools_executed),
        "tools_blocked": len(run.get("blocked_tools") or []),
        "governance_checked": bool(
            run.get("mode_escalation_required") or run.get("blocked_tools")
        ),
        "intent_route": intent_route,
        "classification": run.get("classification"),
    }

router = APIRouter(prefix="/v2/agent", tags=["Agent V2"], dependencies=[Depends(require_strict_operator_access)])
chat_router = APIRouter(prefix="/v2/chat", tags=["Agent V2 Chat"], dependencies=[Depends(require_strict_operator_access)])

class CreateRunRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    goal: str
    mode: str = "read_only"
    user_id: str = "local"

class AgentChatRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
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
        "backend_selected": getattr(rt, "backend_selected", rt.backend),
        "backend_default": getattr(rt, "backend_default", None),
        "backend_fallback_used": getattr(rt, "backend_fallback_used", False),
        "backend_fallback_reason": getattr(rt, "backend_fallback_reason", None),
        "runtime_type": getattr(rt, "runtime_type", type(rt).__name__),
        "langgraph_default_active": getattr(rt, "backend_default", None) == "langgraph_parity",
        "rollback_backend": getattr(rt, "rollback_backend", "native_runtime"),
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
        "backend_selected": getattr(rt, "backend_selected", rt.backend),
        "backend_default": getattr(rt, "backend_default", None),
        "backend_fallback_used": getattr(rt, "backend_fallback_used", False),
        "backend_fallback_reason": getattr(rt, "backend_fallback_reason", None),
        "runtime_type": getattr(rt, "runtime_type", type(rt).__name__),
        "langgraph_default_active": getattr(rt, "backend_default", None) == "langgraph_parity",
        "rollback_backend": getattr(rt, "rollback_backend", "native_runtime"),
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
    # CONTRACT B: Reject requests containing forbidden bypass/override fields in the message
    from .governance import contains_forbidden_request_fields
    if contains_forbidden_request_fields({"message": req.message}):
        raise HTTPException(status_code=403, detail="forbidden bypass/override fields detected in request")
    from .governance import validate_mode, parse_mode_from_message
    from .intent_adapter import AgentV2IntentAdapter
    from .context_assembler import assemble_recent_context, _is_follow_up
    nl_mode = parse_mode_from_message(req.message.strip())
    validated_mode = nl_mode or validate_mode(req.mode)
    
    # Load recent context for this user_id
    recent_ctx = assemble_recent_context(
        user_id=req.user_id or "local",
        current_goal=req.message.strip(),
        max_turns=5,
        max_chars=3000,
    )
    
    # Intent-based pre-planner gate with context awareness
    adapter = AgentV2IntentAdapter()
    route_info = adapter.select_route(req.message.strip(), recent_context=recent_ctx)
    
    rt = get_agent_runtime_v2()
    run = rt.create_run(req.message, validated_mode, req.user_id)

    # For direct_assistant and brain_evidence routes, we already handle in execute_run
    # For mixed_brain_reasoning and operational_agent, we need the planner
    if route_info["route"] in {"mixed_brain_reasoning", "operational_agent"}:
        run = rt.plan_run(run["run_id"])

    run = rt.execute_run(run["run_id"])
    trace_events = rt.get_trace(run["run_id"])
    capability_metadata = _build_capability_metadata(run)
    capability_metadata["trace_events_count"] = len(trace_events)
    raw_response = {
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
        "intent_route": run.get("intent_route"),
        "intent_detected": run.get("intent_detected"),
        "intent_confidence": run.get("intent_confidence"),
        "capability_metadata": capability_metadata,
        "backend_selected": getattr(rt, "backend_selected", rt.backend),
        "backend_default": getattr(rt, "backend_default", None),
        "backend_fallback_used": getattr(rt, "backend_fallback_used", False),
        "backend_fallback_reason": getattr(rt, "backend_fallback_reason", None),
        "runtime_type": getattr(rt, "runtime_type", type(rt).__name__),
        "langgraph_default_active": getattr(rt, "backend_default", None) == "langgraph_parity",
        "rollback_backend": getattr(rt, "rollback_backend", "native_runtime"),
    }
    return normalize_agent_v2_chat_response(
        raw_response,
        backend=getattr(rt, "backend", "native_runtime"),
        mode_requested=validated_mode,
    )
