"""Health and status read-only router.

B7-STRANGLER-13A/13C: Extracted from main.py — health/status/read-only
GET endpoints. The startup-state-dependent endpoints (/health, /status,
/healthz, /v1/agent/healthz) receive their state via a provider callback
registered by main.py at import time, avoiding any import of main.py
from this module.

Moved endpoints:
  - GET /health
  - GET /status
  - GET /healthz
  - GET /v1/agent/healthz
  - GET /v1/agent/status
  - GET /brain/health
  - GET /brain/security/posture
  - GET /brain/risk/status
  - GET /brain/governance/health
  - GET /brain/metrics
  - GET /tools/coverage

Deferred endpoints (remain in main.py):
  - GET /brain/validators (imports core module with global chat metrics)
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from brain_v9.brain.risk_contract import (
    build_risk_contract_status,
    read_risk_contract_status,
)
from brain_v9.governance.governance_health import (
    build_governance_health,
    read_governance_health,
)
from brain_v9.routes.health_status_state import (
    build_health_response,
    build_status_payload,
)

router = APIRouter(tags=["health-status"])

# ── Startup state provider (registered by main.py) ───────────────

StartupStateProvider = Callable[[], Mapping[str, Any]]

_startup_state_provider: StartupStateProvider | None = None


def configure_startup_state_provider(provider: StartupStateProvider) -> None:
    global _startup_state_provider
    _startup_state_provider = provider


def _startup_state() -> Mapping[str, Any]:
    if _startup_state_provider is None:
        raise RuntimeError("startup_state_provider_not_configured")
    return _startup_state_provider()


# ── Startup-state-dependent endpoints ────────────────────────────

@router.get("/health")
async def health():
    state = _startup_state()
    resp = build_health_response(
        startup_done=bool(state["startup_done"]),
        startup_error=state.get("startup_error"),
        active_sessions_count=int(state["active_sessions_count"]),
        safe_mode=bool(state["safe_mode"]),
    )
    if resp["status_code"] != 200:
        return JSONResponse(content=resp["content"], status_code=resp["status_code"])
    return resp["content"]


@router.get("/status")
async def status():
    state = _startup_state()
    return build_status_payload(
        active_session_keys=list(state["active_session_keys"]),
        startup_done=bool(state["startup_done"]),
        safe_mode=bool(state["safe_mode"]),
    )


@router.get("/healthz")
async def healthz():
    return await health()


@router.get("/v1/agent/healthz")
async def v1_agent_healthz():
    return await health()


# ── Static / lazy-import endpoints ───────────────────────────────

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