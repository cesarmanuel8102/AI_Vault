"""Health and status read-only router.

B7-STRANGLER-13A: Extracted from main.py — basic health/status/read-only
GET endpoints that do not depend on main.py mutable globals.

Moved endpoints:
  - GET /v1/agent/status
  - GET /brain/health
  - GET /brain/security/posture
  - GET /brain/risk/status
  - GET /brain/governance/health
  - GET /brain/metrics
  - GET /tools/coverage

Deferred endpoints (remain in main.py due to global state deps):
  - GET /health        (uses _startup_done, _startup_error, active_sessions)
  - GET /status        (uses active_sessions, _startup_done)
  - GET /healthz       (delegates to health())
  - GET /v1/agent/healthz (delegates to health())
  - GET /brain/validators (imports brain_v9.core.session._GLOBAL_CHAT_METRICS)
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from brain_v9.brain.risk_contract import (
    build_risk_contract_status,
    read_risk_contract_status,
)
from brain_v9.governance.governance_health import (
    build_governance_health,
    read_governance_health,
)

router = APIRouter(tags=["health-status"])


@router.get("/v1/agent/status")
async def v1_agent_status(room_id: str | None = None):
    return {
        "ok": True,
        "status": "running",
        "room_id": room_id,
        "service": "brain_v9",
        "legacy_agent_status": "legacy_compatible_not_canonical",
        "canonical_agent_v2": "/v2/agent/status",
        "canonical_chat_agent": "/v2/chat/agent",
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/brain/health")
async def brain_health():
    from brain_v9.brain.health import BrainHealthMonitor
    return await BrainHealthMonitor().check_all_services()


@router.get("/brain/security/posture")
async def brain_security_posture(refresh: bool = True):
    from brain_v9.brain.security_posture import (
        build_security_posture,
        get_security_posture_latest,
    )
    if refresh:
        return build_security_posture(refresh_dependency_audit=True)
    return get_security_posture_latest()


@router.get("/brain/risk/status")
async def brain_risk_status(refresh: bool = True):
    return build_risk_contract_status(refresh=refresh) if refresh else read_risk_contract_status()


@router.get("/brain/governance/health")
async def brain_governance_health(refresh: bool = True):
    return build_governance_health(refresh=refresh) if refresh else read_governance_health()


@router.get("/brain/metrics")
async def brain_metrics(days: int = 7):
    from brain_v9.brain.metrics import MetricsAggregator
    mgr = MetricsAggregator()
    return {"current": await mgr.aggregate_system_metrics(),
            "trends":  await mgr.get_performance_trends(days),
            "errors":  await mgr.get_error_rates()}


@router.get("/tools/coverage")
async def tools_coverage():
    """R14: Per-tool reliability observability."""
    try:
        from brain_v9.core import tool_metrics as _tm
        return _tm.snapshot()
    except Exception as exc:
        return {"_error": str(exc), "tools": {}, "totals": {}, "top_failing": []}