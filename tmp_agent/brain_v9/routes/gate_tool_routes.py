"""Gate and Tool01 permission routes split from main.py.

Front: FRONT-BRAIN-MAIN-ROUTER-EXTRA-AGGRESSIVE-COMPLETE-MIGRATION-14A
"""
from __future__ import annotations

import asyncio as _aio
from typing import Annotated, Callable, Dict, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from brain_v9.api_security import StrictOperatorAccess, require_strict_operator_access

router = APIRouter(tags=["gate-tool-permissions"])
StrictAccess = Annotated[None, Depends(require_strict_operator_access)]
_active_sessions_provider: Callable[[], Dict] = lambda: {}


def configure_active_sessions_provider(provider: Callable[[], Dict]) -> None:
    global _active_sessions_provider
    _active_sessions_provider = provider


def _active_sessions() -> Dict:
    return _active_sessions_provider()


class GateApproveRequest(BaseModel):
    approval_token: Optional[str] = None


class Tool01PermissionRequest(BaseModel):
    session_id: str
    permission_id: str
    decision: str  # allow_once, allow_session, deny


@router.post("/gate/approve/{pending_id}")
async def gate_approve(pending_id: str, req: GateApproveRequest, _operator: StrictAccess):
    """Approve a pending gated action via API (used by UI button)."""
    from brain_v9.governance.execution_gate import get_gate
    gate = get_gate()
    approval_token = req.approval_token if req else None
    item = gate.approve(pending_id, approval_token=approval_token)
    if not item:
        return JSONResponse(content={"success": False, "error": f"Approval failed or signed approval required: {pending_id}"}, status_code=403)

    # Fail close if signed approval is required but not validated
    if gate._pending_requires_signed_approval(item) and not item.get("signed_approval_validated"):
        return JSONResponse(
            content={"success": False, "error": "Signed approval required but not validated.", "signed_approval_validated": False},
            status_code=403,
        )

    # Strip approval metadata from response so tokens/secrets are never leaked
    item.pop("approval_token", None)
    item.pop("approval_secret", None)

    tool_name = item.get("tool", "?")
    tool_args = item.get("args", {})
    try:
        from brain_v9.agent.tools import build_standard_executor
        executor = build_standard_executor()
        fn = executor._tools.get(tool_name, {}).get("func")
        if fn is None:
            return JSONResponse(content={"success": False, "error": f"Tool '{tool_name}' not found"}, status_code=404)
        # Add _bypass_gate flag so the tool skips its internal gate check
        approved_args = {**tool_args, "_bypass_gate": True}
        if _aio.iscoroutinefunction(fn):
            result = await fn(**approved_args)
        else:
            result = fn(**approved_args)
        return {"success": True, "tool": tool_name, "result": str(result)[:500], "signed_approval_validated": item.get("signed_approval_validated", False)}
    except Exception as exc:
        return JSONResponse(content={"success": False, "tool": tool_name, "error": str(exc)[:500]}, status_code=500)


@router.post("/gate/reject/{pending_id}")
async def gate_reject(pending_id: str, _operator: StrictAccess):
    """Reject a pending gated action via API (used by UI button)."""
    from brain_v9.governance.execution_gate import get_gate
    gate = get_gate()
    ok = gate.reject(pending_id)
    return {"success": ok, "pending_id": pending_id}


@router.post("/tool01/permission/approve")
async def tool01_permission_approve(req: Tool01PermissionRequest, _operator: StrictAccess):
    """Approve a TOOL-01 permission request via API."""
    active_sessions = _active_sessions()
    session = active_sessions.get(req.session_id)
    if not session:
        return {"success": False, "error": "Session not found"}
    result = session._tool01_approve_permission(req.permission_id, req.decision)
    if result.get("success"):
        # Buscar original_message para ejecutar la tool
        tool_name = result.get("tool_name", "")
        # mapear nombre público a interno
        for internal_name, public_name in session._TOOL01_PUBLIC_NAMES.items():
            if public_name == tool_name:
                tool_name = internal_name
                break
        original_message = ""
        for grant_info in session._tool01_permission_grants.values():
            if grant_info.get("permission_id") == req.permission_id:
                original_message = grant_info.get("original_message", "")
                break
        # Ejecutar la tool directamente si es allow_once o allow_session
        tool_result = None
        if req.decision in ("allow_once", "allow_session") and tool_name in session._TOOL01_ROUTER_PATTERNS:
            tool_result = await session._tool01_execute(tool_name, original_message)
        return {
            "success": True,
            "decision": result["decision"],
            "tool_name": result.get("tool_name"),
            "tool_executed": tool_result is not None,
            "tool_result": tool_result,
            "message": f"Permission {result['decision']} granted and tool executed for {result.get('tool_name')}",
        }
    if result.get("blocked_by_user"):
        return {
            "success": False,
            "blocked_by_user": True,
            "decision": result.get("decision"),
            "tool_name": result.get("tool_name"),
            "message": f"Permission denied for {result.get('tool_name')}",
        }
    return {"success": False, "error": result.get("error", "Unknown error")}


@router.get("/tool01/permission/pending/{session_id}")
async def tool01_permission_pending(session_id: str):
    """Get pending TOOL-01 permission for a session."""
    active_sessions = _active_sessions()
    session = active_sessions.get(session_id)
    if not session:
        return {"success": False, "error": "Session not found"}
    perm = getattr(session, '_pending_tool01_permission', None)
    if not perm:
        return {"success": True, "permission_required": False}
    return {"success": True, "permission_required": True, **perm}


@router.get("/tool01/permission/grants/{session_id}")
async def tool01_permission_grants(session_id: str):
    """List active TOOL-01 permission grants for a session."""
    active_sessions = _active_sessions()
    session = active_sessions.get(session_id)
    if not session:
        return {"success": False, "error": "Session not found"}
    grants = session._tool01_permission_grants
    # Sanitize: remove internal objects
    safe_grants = {}
    for tool_name, grant in grants.items():
        safe_grants[tool_name] = {
            "granted": grant.get("granted"),
            "grant_type": grant.get("grant_type"),
            "scope": grant.get("scope"),
            "blocked_prefixes": grant.get("blocked_prefixes"),
        }
    return {"success": True, "grants": safe_grants}
