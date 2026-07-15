"""Provider-backed read-only routes split from main.py.

Front: FRONT-BRAIN-MAIN-ROUTER-MEGA-AGGRESSIVE-SWEEP-14B
"""
from __future__ import annotations

from typing import Any, Callable, Dict

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["provider-readonly"])

_operating_context_builder: Callable[[Dict[str, Any]], Dict[str, Any]] | None = None
_maintenance_status_builder: Callable[[], Dict[str, Any]] | None = None


def configure_provider_readonly(
    operating_context_builder: Callable[[Dict[str, Any]], Dict[str, Any]],
    maintenance_status_builder: Callable[[], Dict[str, Any]],
) -> None:
    global _operating_context_builder, _maintenance_status_builder
    _operating_context_builder = operating_context_builder
    _maintenance_status_builder = maintenance_status_builder


@router.get("/brain-dashboard/agent-v2/status")
async def brain_dashboard_agent_v2_status():
    from brain_v9.core.agent_kernel_v2.finalizer import PRIMARY_KIMI_MODEL
    from brain_v9.core.agent_kernel_v2.runtime import get_agent_runtime_v2

    rt = get_agent_runtime_v2()
    runs = rt.list_runs()
    latest = runs[-1] if runs else {}
    meta = latest.get("provider_metadata") or {}
    return {
        "ok": True,
        "canonical_for_new_agent_runs": True,
        "backend": rt.backend,
        "primary_finalizer_model": PRIMARY_KIMI_MODEL,
        "latest_provider_used": meta.get("provider_used"),
        "latest_model_used": meta.get("model_used"),
        "latest_provider_degraded": meta.get("provider_degraded"),
        "runs": len(runs),
        "latest_run_id": latest.get("run_id"),
        "chat_agent_route": "/v2/chat/agent",
        "legacy_agent_status": "legacy_compatible_not_canonical",
    }


@router.get("/brain/operating-context")
async def brain_operating_context():
    if _operating_context_builder is None:
        raise HTTPException(status_code=503, detail="operating context provider not configured")
    from brain_v9.trading.router import trading_policy

    policy = await trading_policy()
    return _operating_context_builder(policy)


@router.get("/brain/maintenance/status")
async def brain_maintenance_status():
    if _maintenance_status_builder is None:
        raise HTTPException(status_code=503, detail="maintenance status provider not configured")
    return _maintenance_status_builder()
