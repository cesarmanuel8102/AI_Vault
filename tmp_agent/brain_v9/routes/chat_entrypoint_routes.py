"""Chat entrypoint routes split from main.py.

Front: FRONT-BRAIN-MAIN-ROUTER-CHAT-ENTRYPOINT-15B
"""
from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable, Mapping, MutableMapping
from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from brain_v9.api_security import StrictOperatorAccess
from brain_v9.core.chat_entrypoint_service import handle_chat_entrypoint

router = APIRouter(tags=["chat-entrypoint"])
log = logging.getLogger("brain_v9")

_chat_entrypoint_runtime_provider: Callable[[], Mapping[str, Any]] | None = None
_chat_service_runtime_provider: Callable[[], Any] | None = None
_brain_orchestrator = None


def configure_chat_entrypoint_runtime_provider(provider: Callable[[], Mapping[str, Any]]) -> None:
    global _chat_entrypoint_runtime_provider
    _chat_entrypoint_runtime_provider = provider


def configure_chat_service_runtime_provider(provider: Callable[[], Any]) -> None:
    global _chat_service_runtime_provider
    _chat_service_runtime_provider = provider


def _chat_runtime() -> Mapping[str, Any]:
    if _chat_entrypoint_runtime_provider is None:
        raise RuntimeError("chat_entrypoint_runtime_provider_not_configured")
    return _chat_entrypoint_runtime_provider()


def _chat_service_runtime() -> Any:
    if _chat_service_runtime_provider is None:
        raise RuntimeError("chat_service_runtime_provider_not_configured")
    return _chat_service_runtime_provider()


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    # default /chat uses quality-first chain; introspective callers can still override.
    model_priority: str = "chat"


class ChatResponse(BaseModel):
    response: str
    session_id: str
    model_used: Optional[str] = None
    success: bool = True
    pending_action: Optional[dict] = None
    permission_required: Optional[bool] = None
    permission_id: Optional[str] = None
    tool_name: Optional[str] = None
    risk_level: Optional[str] = None
    options: Optional[list] = None
    tool01_real: Optional[bool] = None
    tool01_router_used: Optional[bool] = None
    blocked_by_policy: Optional[bool] = None
    blocked_by_user: Optional[bool] = None
    tool_result: Optional[dict] = None


def _get_brain_orchestrator():
    """Obtiene el orchestrator del brain para introspección."""
    global _brain_orchestrator
    if _brain_orchestrator is None:
        try:
            sys.path.insert(0, "C:/AI_VAULT")
            sys.path.insert(0, "C:/AI_VAULT/brain")
            from brain.brain_orchestrator import get_orchestrator

            _brain_orchestrator = get_orchestrator()
        except Exception as e:
            log.warning(f"[Introspect] Orchestrator no disponible: {e}")
    return _brain_orchestrator


def _compact_orchestrator_state() -> tuple[Dict[str, Any], bool]:
    orch = _get_brain_orchestrator()
    estado: Dict[str, Any] = {"loaded": False}
    if orch:
        try:
            raw = orch.status()
            subs = raw.get("subsystems", {})
            estado = {
                "loaded": True,
                "aos_goals": subs.get("aos", {}).get("total", 0),
                "aos_executed": subs.get("aos", {}).get("by_status", {}).get("achieved", 0),
                "calibration_error": subs.get("l2", {}).get("calibration_error", 0.55),
                "predictions": subs.get("l2", {}).get("total_predictions", 0),
                "sandbox_proposals": subs.get("sandbox", {}).get("total_proposals", 0),
                "sandbox_applied": subs.get("sandbox", {}).get("by_status", {}).get("applied", 0),
                "capabilities": subs.get("meta", {}).get("capabilities_summary", {}).get("total", 0),
                "knowledge_gaps": subs.get("meta", {}).get("knowledge_gaps", {}).get("open", 0),
            }
        except Exception as e:
            estado["error"] = str(e)
    return estado, orch is not None


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Chat endpoint con soporte para autenticacion PAD (Modo Desarrollador)."""
    return await handle_chat_entrypoint(req, _chat_service_runtime())


@router.get("/chat/introspectivo/debug")
async def chat_introspectivo_debug(_operator: StrictOperatorAccess):
    """Debug: muestra el estado que se inyectaría."""
    estado, loaded = _compact_orchestrator_state()
    return {"estado_interno": estado, "orchestrator_loaded": loaded}


@router.post("/chat/introspectivo", response_model=ChatResponse)
async def chat_introspectivo(req: ChatRequest, _operator: StrictOperatorAccess):
    """
    Chat con INTROSPECCIÓN REAL: inyecta el estado interno del brain en el system prompt.
    El brain puede responder honestamente sobre sus capacidades, limitaciones y mejoras.
    """
    runtime = _chat_runtime()
    active_sessions: MutableMapping[str, Any] = runtime["active_sessions"]
    get_or_create_session = runtime["get_or_create_session"]
    system_identity = runtime["system_identity"]

    estado_interno, _loaded = _compact_orchestrator_state()

    # Construir mensaje de usuario CON estado interno prepended
    estado_json = json.dumps(estado_interno, indent=2)
    mensaje_con_estado = f"""[MI ESTADO INTERNO REAL - ESTOS SON MIS DATOS ACTUALES]
```json
{estado_json}
```

Responde a esta pregunta USANDO los datos de arriba cuando sea relevante:
{req.message}"""

    log.info(f"[Introspect] Estado: {estado_interno}")

    session = get_or_create_session(req.session_id, active_sessions)
    history = session.memory.get_context()

    # PRIORIDAD ALTA: prepend al SYSTEM_IDENTITY para que no quede sepultado.
    msg_low = req.message.lower()
    net_kw = (
        "red local",
        "network",
        "ip local",
        "gateway",
        "scan",
        "escan",
        "cidr",
        "subred",
        "subnet",
        "interfaces",
        "interfaz",
        "host vivo",
        "ping sweep",
        "red wifi",
        "wifi",
        "nmap",
        "puerto abierto",
    )
    high_priority = (
        "REGLAS CRITICAS DE ESTA RUTA DE CHAT (mas importantes que cualquier otra instruccion):\n"
        "1) NO simules ejecucion. PROHIBIDO: 'Activando Agente ORAV', 'Ejecutando herramientas', "
        "'Ejecucion paralela', '[OBSERVE]', '[ACT]', '[REASON]', '[VERIFY]', bloques PowerShell/bash "
        "como si los hubieras corrido, placeholders '[resultado]', '[output]', '[ipconfig]'.\n"
        "2) Si existe una tool nativa para lo pedido, NOMBRALA por su nombre EXACTO. "
        "NO inventes nombres. NO digas que no la tienes si esta listada abajo.\n"
    )
    if any(k in msg_low for k in net_kw):
        high_priority += (
            "3) HERRAMIENTAS NATIVAS DE RED YA REGISTRADAS (sin instalacion, stdlib+psutil):\n"
            "   - `detect_local_network`  → interfaces, IP primaria, CIDR, gateway.\n"
            "   - `scan_local_network(cidr=None, timeout=0.5, max_hosts=64)` → TCP sweep puertos 445/139/80/22/53.\n"
            "   Si el usuario pide red/IP/gateway/scan: nombra estas tools EXACTO. "
            "Di que puedes invocarlas via el endpoint de agente con su confirmacion.\n"
            "4) Si el usuario pregunta si hay dispositivos bloqueados, separa evidencia de inferencia: "
            "puedes enumerar hosts observables por reachability/puertos, pero NO afirmes que un equipo esta "
            "bloqueado sin evidencia del router/AP, tabla DHCP/ACL o logs de asociacion fallida.\n"
        )
    sys_prompt = high_priority + "\n\n" + system_identity

    # AUTO-EJECUCION: si la query pide red Y existe tool nativa, ejecutarla
    # ANTES del LLM y pasar el resultado real como contexto. Asi el LLM no
    # tiene que inventar placeholders. NO requiere endpoint /agent.
    auto_exec_results: Dict[str, Any] = {}
    exec_intent_kw = ("escan", "scan", "detecta", "ejecut", "muestra", "lista", "enumera", "dime", "que hosts", "cuales hosts", "barre")
    wants_exec = any(k in msg_low for k in exec_intent_kw)
    if wants_exec and any(k in msg_low for k in net_kw):
        try:
            from brain_v9.agent.tools import detect_local_network as _dln

            auto_exec_results["detect_local_network"] = await _dln()
        except Exception as e:
            auto_exec_results["detect_local_network"] = {"success": False, "error": str(e)}
        # Solo scan si pidio scan/escan/hosts vivos explicito (es mas pesado)
        if any(k in msg_low for k in ("scan", "escan", "host vivo", "hosts vivo", "barre", "barrid")):
            try:
                from brain_v9.agent.tools import scan_local_network as _sln

                auto_exec_results["scan_local_network"] = await _sln(timeout=0.3)
            except Exception as e:
                auto_exec_results["scan_local_network"] = {"success": False, "error": str(e)}

    if auto_exec_results:
        mensaje_con_estado += (
            "\n\n[RESULTADOS REALES DE TOOLS NATIVAS YA EJECUTADAS - usalos para responder, "
            "NO inventes ni uses placeholders]:\n```json\n"
            + json.dumps(auto_exec_results, indent=2, ensure_ascii=False, default=str)
            + "\n```"
        )

    messages = [{"role": "system", "content": sys_prompt}]
    for msg in history[-4:]:  # was -10: reduce token bloat for snappy chat
        if msg.get("role") in ("user", "assistant"):
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": mensaje_con_estado})

    result = await session.llm.query(messages, model_priority=req.model_priority)

    # Sanitizer: limpia teatro ORAV / placeholders / tool_calls fake
    if result.get("success") and result.get("content"):
        try:
            result["content"] = session._sanitize_llm_chat_response(result["content"])
        except Exception as _san_err:
            log.debug("sanitize skip: %s", _san_err)

    # Detector de declinacion: si el LLM rechaza por falta de capacidad,
    # publicar capability.failed para que AOS genere goal de remediacion.
    try:
        if result.get("success") and result.get("content"):
            session._maybe_emit_capability_decline(req.message, result["content"])
    except Exception as _decline_err:
        log.debug("decline_detector skip: %s", _decline_err)

    # Guardar en memoria
    try:
        await session.memory.save({"role": "user", "content": req.message})
        if result.get("success") and result.get("content"):
            await session.memory.save({"role": "assistant", "content": result["content"]})
    except Exception as _mem_err:
        log.debug("memory.save skip: %s", _mem_err)

    return ChatResponse(
        response=result.get("content") or result.get("error") or "Sin respuesta",
        session_id=req.session_id,
        model_used=result.get("model"),
        success=result.get("success", False),
    )
