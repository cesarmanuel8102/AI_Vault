"""Chat/session/agent lifecycle routes split from main.py.

Front: FRONT-BRAIN-MAIN-ROUTER-SESSION-LIFECYCLE-15A
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from collections.abc import Callable, Mapping, MutableMapping
from datetime import datetime
from typing import Annotated, Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from brain_v9.agent.loop import AgentLoop
from brain_v9.agent.tools import build_standard_executor
from brain_v9.api_security import StrictOperatorAccess, require_strict_operator_access

router = APIRouter(tags=["chat-session-lifecycle"])
log = logging.getLogger("brain_v9")

_active_sessions_provider: Callable[[], MutableMapping[str, Any]] | None = None
_chat_runtime_provider: Callable[[], Mapping[str, Any]] | None = None


def configure_active_sessions_provider(provider: Callable[[], MutableMapping[str, Any]]) -> None:
    global _active_sessions_provider
    _active_sessions_provider = provider


def configure_chat_runtime_provider(provider: Callable[[], Mapping[str, Any]]) -> None:
    global _chat_runtime_provider
    _chat_runtime_provider = provider


def _active_sessions() -> MutableMapping[str, Any]:
    if _active_sessions_provider is None:
        raise RuntimeError("active_sessions_provider_not_configured")
    return _active_sessions_provider()


def _chat_runtime() -> Mapping[str, Any]:
    if _chat_runtime_provider is None:
        raise RuntimeError("chat_runtime_provider_not_configured")
    return _chat_runtime_provider()


class AgentRequest(BaseModel):
    task: str
    session_id: str = "default"
    model_priority: str = "ollama"
    max_steps: int = 10


class DevModeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task: str
    auth_token: Optional[str] = None


class GodModeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task: str
    session_id: str


@router.delete("/sessions/{session_id}", dependencies=[Depends(require_strict_operator_access)])
async def delete_session(session_id: str):
    sessions = _active_sessions()
    if session_id in sessions:
        await sessions[session_id].close()
        del sessions[session_id]
    return {"success": True}


@router.delete("/sessions/{session_id}/memory", dependencies=[Depends(require_strict_operator_access)])
async def clear_session_memory(session_id: str, memory_type: str = "all"):
    sessions = _active_sessions()
    if session_id not in sessions:
        return {"success": False, "error": "session_not_found"}
    sessions[session_id].memory.clear(memory_type)
    return {"success": True, "session_id": session_id, "memory_type": memory_type}


@router.post("/agent")
async def run_agent(req: AgentRequest, _operator: StrictOperatorAccess):
    """
    [INTERNAL/DEPRECATED] Ciclo ORAV completo.

    NOTA OPERATIVA (CHAT-OPS-ARCH-01): /agent es endpoint interno para operador.
    Para flujo gobernado con permisos y pending_action, use POST /chat.
    /chat es la autoridad operacional única para usuarios.
    """
    runtime = _chat_runtime()
    executor = runtime["get_agent_executor"]()
    if executor is None:
        executor = build_standard_executor()
        runtime["set_agent_executor"](executor)

    get_or_create_session = runtime["get_or_create_session"]
    session = get_or_create_session(req.session_id, _active_sessions())
    canonical_result = runtime["canonical_agent_fastpath"](req.task, session)
    if canonical_result is not None:
        return canonical_result
    loop = AgentLoop(session.llm, executor)
    loop.MAX_STEPS = req.max_steps

    agent_timeout = min(req.max_steps * 45, 360)  # 45s per step, max 6 min
    try:
        result = await asyncio.wait_for(
            loop.run(req.task, context={"model_priority": req.model_priority}),
            timeout=agent_timeout,
        )
    except asyncio.TimeoutError:
        log.warning("Agent request timed out after %ds for task: %s", agent_timeout, req.task[:80])
        result = {
            "success": False,
            "result": f"El agente excedió el tiempo límite ({agent_timeout}s).",
            "steps": len(loop.history),
            "summary": "timeout",
            "status": "timeout",
        }
    raw_result = result.get("result")
    result_text = runtime["summarize_agent_payload"](raw_result, fallback=result.get("summary", ""))
    return {
        "task": req.task,
        "success": result["success"],
        "result": result_text,
        "raw_result": raw_result,
        "steps": result.get("steps", 0),
        "summary": result.get("summary", ""),
        "status": result.get("status"),
        "metacognition": result.get("metacognition", {}),
        "history": loop.get_history(),
    }


@router.post("/dev", dependencies=[Depends(require_strict_operator_access)])
async def dev_mode_endpoint(req: DevModeRequest):
    """
    Endpoint de Modo Desarrollador - Ejecuta tareas sin restricciones del ORAV.
    Requiere autenticacion previa.
    """
    runtime = _chat_runtime()
    if not runtime["unsafe_dev_endpoints_enabled"]:
        raise HTTPException(
            status_code=403,
            detail="Endpoint /dev deshabilitado por seguridad. Set BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS=true para habilitar.",
        )

    pad_sessions: MutableMapping[str, Dict[str, Any]] = runtime["pad_authenticated_sessions"]

    session_id = req.auth_token or "dev_default"
    esta_autenticado = session_id in pad_sessions

    if not esta_autenticado:
        return {
            "success": False,
            "error": "Modo desarrollador requiere autenticacion previa",
            "instrucciones": "Autenticacion PAD requerida. No se publican credenciales desde el endpoint.",
            "auth_token": session_id,
        }

    pad_session = pad_sessions[session_id]
    if datetime.now() > datetime.fromisoformat(pad_session["expires_at"]):
        del pad_sessions[session_id]
        return {
            "success": False,
            "error": "Sesion expirada. Re-autenticate.",
        }

    try:
        result = await runtime["execute_god_chat_task"](req.task, session_id)
        return {
            "success": bool(result.get("success")),
            "task": req.task,
            "executed_by": "dev_mode",
            "privilege": pad_session.get("privilege_level"),
            "result": result,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()[:500],
        }


@router.get("/godmode/status", dependencies=[Depends(require_strict_operator_access)])
async def godmode_status(session_id: Optional[str] = None):
    """Inspecciona estado god mode. Si session_id provisto, devuelve si esa sesion es god."""
    runtime = _chat_runtime()
    pad_sessions: MutableMapping[str, Dict[str, Any]] = runtime["pad_authenticated_sessions"]
    out = {
        "unsafe_endpoints_enabled": runtime["unsafe_dev_endpoints_enabled"],
        "safe_mode": runtime["safe_mode"],
        "active_pad_sessions": list(pad_sessions.keys()),
        "active_pad_count": len(pad_sessions),
    }
    try:
        from brain_v9.governance.execution_gate import get_gate

        gate = get_gate()
        out["gate_god_sessions"] = sorted(gate._god_sessions)
        if session_id:
            out["session_is_god"] = gate.is_god_mode(session_id)
            out["session_in_pad"] = session_id in pad_sessions
            if session_id in pad_sessions:
                out["session_expires_at"] = pad_sessions[session_id].get("expires_at")
    except Exception as e:
        out["gate_error"] = str(e)
    return out


@router.post("/godmode", dependencies=[Depends(require_strict_operator_access)])
async def godmode_endpoint(req: GodModeRequest):
    """
    Endpoint MODO GOD - Ejecuta tareas reales sin restricciones.
    Requiere autenticacion PAD previa via /chat.
    """
    runtime = _chat_runtime()
    if not runtime["unsafe_dev_endpoints_enabled"]:
        raise HTTPException(
            status_code=403,
            detail="Endpoint /godmode deshabilitado por seguridad. Set BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS=true para habilitar.",
        )

    pad_sessions: MutableMapping[str, Dict[str, Any]] = runtime["pad_authenticated_sessions"]

    if req.session_id not in pad_sessions:
        return {
            "success": False,
            "error": "Requiere autenticacion previa",
            "authenticate_first": "Autenticacion PAD requerida. No se publican credenciales desde el endpoint.",
        }

    pad_session = pad_sessions[req.session_id]
    if datetime.now() > datetime.fromisoformat(pad_session["expires_at"]):
        del pad_sessions[req.session_id]
        return {"success": False, "error": "Sesion expirada"}

    try:
        result = await runtime["execute_god_chat_task"](req.task, req.session_id)
        return {
            "success": bool(result.get("success")),
            "task": req.task,
            "executed_by": "god_mode",
            "privilege": pad_session.get("privilege_level"),
            "result": result,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()[:500],
        }
