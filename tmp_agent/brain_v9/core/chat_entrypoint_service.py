"""Service boundary for the legacy ``POST /chat`` endpoint.

15E keeps the FastAPI decorator in ``main.py`` and moves the endpoint behavior
behind an explicit runtime object. This module must stay importable without
FastAPI, ``main.py``, session internals, indexed memory, market execution, or
live server startup.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import traceback
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Any

from brain_v9.core.chat_runtime_helpers import (
    extract_god_task_text,
    extract_pending_action_from_text,
    has_pending_action_signal,
    is_explicit_god_task,
    is_safe_god_existence_question,
    looks_like_harmful_intrusion_request,
    parse_pad_credentials,
    should_attempt_local_network_tool,
)

log = logging.getLogger("brain_v9")


@dataclass(frozen=True)
class ChatEntrypointRuntime:
    active_sessions: MutableMapping[str, Any]
    chat_response_cls: type
    trivial_chat_fastpath: Callable[..., Any]
    looks_like_curated_learning_probe: Callable[..., bool]
    answer_chat_probe: Callable[..., Any]
    format_curated_probe_response: Callable[..., str]
    pad_authenticated_sessions: MutableMapping[str, Any]
    brain_enable_unsafe_dev_endpoints: bool
    get_gate: Callable[..., Any]
    execute_god_chat_task: Callable[..., Any]
    pad_audit: Callable[..., Any]
    emit_agent_trace: Callable[..., Any]
    handle_user_message: Callable[..., Any]
    detect_local_network: Callable[..., Any]
    scan_local_network: Callable[..., Any]
    logger: Any = log


def chat_entrypoint_runtime_field_count() -> int:
    return len(fields(ChatEntrypointRuntime))


async def handle_chat_entrypoint(req: Any, runtime: ChatEntrypointRuntime) -> Any:
    """Run the legacy chat endpoint behavior through an injected runtime."""
    ChatResponse = runtime.chat_response_cls
    logger = runtime.logger

    trivial = runtime.trivial_chat_fastpath(req.message)
    if trivial is not None:
        return ChatResponse(
            response=trivial["response"],
            session_id=req.session_id,
            model_used=trivial.get("model", "local"),
            success=trivial.get("success", True),
        )

    if runtime.looks_like_curated_learning_probe(req.message):
        try:
            result = runtime.answer_chat_probe(question=req.message)
            reply = runtime.format_curated_probe_response(result)
            return ChatResponse(
                response=reply,
                session_id=req.session_id,
                model_used="curated_helper",
                success=True,
            )
        except Exception as exc:
            logger.debug("Curated helper fastpath error: %s", exc)

    mensaje_lower = req.message.lower()
    es_comando_pad = (
        "autenticar:" in mensaje_lower
        or "modo desarrollador" in mensaje_lower
        or "sin restricciones" in mensaje_lower
        or "modo god" in mensaje_lower
    ) and not is_safe_god_existence_question(req.message)

    es_logout = (
        ("cerrar sesion" in mensaje_lower or "logout" in mensaje_lower)
        and ("desarrollador" in mensaje_lower or "god" in mensaje_lower)
    )

    if es_logout:
        runtime.pad_authenticated_sessions.pop(req.session_id, None)
        try:
            runtime.get_gate().disable_god_mode(req.session_id)
        except Exception:
            pass
        return ChatResponse(
            response="Sesion de desarrollador cerrada. Restricciones reactivadas.",
            session_id=req.session_id,
            model_used="brain_v3_auth",
            success=True,
        )

    if es_comando_pad and not runtime.brain_enable_unsafe_dev_endpoints:
        return ChatResponse(
            response=(
                "Modo desarrollador/GOD deshabilitado por seguridad. "
                "Para activarlo hay que arrancar Brain de forma deliberada con "
                "BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS=true y BRAIN_SAFE_MODE=false. "
                "No se exponen credenciales ni bypasses desde el chat."
            ),
            session_id=req.session_id,
            model_used="brain_safe_mode",
            success=False,
        )

    session_id = req.session_id
    esta_autenticado_pad = session_id in runtime.pad_authenticated_sessions

    if es_logout and esta_autenticado_pad:
        del runtime.pad_authenticated_sessions[session_id]
        try:
            runtime.get_gate().disable_god_mode(session_id)
        except Exception:
            pass
        return ChatResponse(
            response="Sesion de desarrollador cerrada. Restricciones reactivadas.",
            session_id=session_id,
            model_used="brain_v3_auth",
            success=True,
        )

    if esta_autenticado_pad:
        pad_session = runtime.pad_authenticated_sessions[session_id]
        if datetime.now() > datetime.fromisoformat(pad_session["expires_at"]):
            del runtime.pad_authenticated_sessions[session_id]
        else:
            explicit_god_task = is_explicit_god_task(req.message)
            if explicit_god_task:
                task_text = extract_god_task_text(req.message)
                try:
                    resultado = await runtime.execute_god_chat_task(task_text, session_id)
                    return ChatResponse(
                        response=json.dumps(resultado, ensure_ascii=False, indent=2),
                        session_id=session_id,
                        model_used="brain_god_authenticated",
                        success=bool(resultado.get("success")),
                    )
                except Exception as exc:
                    logger.exception("Error al ejecutar tarea GOD")
                    runtime.pad_audit("god_task_error", {"session_id": session_id, "error": str(exc)[:500]})
                    return ChatResponse(
                        response=f"[Modo GOD] Error: {str(exc)[:300]}",
                        session_id=session_id,
                        model_used="brain_god_authenticated",
                        success=False,
                    )
            runtime.pad_audit("god_chat_passthrough", {"session_id": session_id, "message_preview": req.message[:160]})

    if es_comando_pad:
        try:
            sys.path.insert(0, "C:/AI_VAULT")
            sys.path.insert(0, "C:/AI_VAULT/brain")
            from protocolo_autenticacion_desarrollador import ProtocoloAutenticacionDesarrollador

            protocolo = ProtocoloAutenticacionDesarrollador()
            credenciales = parse_pad_credentials(req.message)

            if not credenciales:
                return ChatResponse(
                    response=(
                        "No puedo activar ni guiar un modo para saltar permisos, politicas o governance. "
                        "Puedo ayudarte a solicitar permisos especificos y auditables para una accion concreta."
                    ),
                    session_id=req.session_id,
                    model_used="governed_action_kernel",
                    success=False,
                )

            exito, sesion, mensaje_auth = protocolo.autenticar(
                credenciales["username"],
                credenciales["password"],
                credenciales["mfa_code"],
                credenciales["witnesses"],
            )

            if not exito:
                return ChatResponse(
                    response=f"**AUTENTICACION FALLIDA**\n\n{mensaje_auth}",
                    session_id=req.session_id,
                    model_used="brain_v3_auth",
                    success=False,
                )

            if not sesion.privilege_level.can_override():
                return ChatResponse(
                    response=(
                        f"**PRIVILEGIO INSUFICIENTE**\n\nTu nivel: {sesion.privilege_level.name}\n"
                        "Requerido: LEVEL_4+ (OVERRIDE o GOD)"
                    ),
                    session_id=req.session_id,
                    model_used="brain_v3_auth",
                    success=False,
                )

            resultado = protocolo.eliminar_restricciones(sesion, ["all"])

            if resultado["success"]:
                runtime.pad_authenticated_sessions[session_id] = {
                    "username": sesion.username,
                    "privilege_level": sesion.privilege_level.name,
                    "session_id": sesion.session_id,
                    "token": sesion.token,
                    "expires_at": sesion.expires_at.isoformat(),
                    "autenticado_en": datetime.now().isoformat(),
                }
                try:
                    gate_instance = runtime.get_gate()
                    revoked = list(getattr(protocolo, "last_revoked_god_sessions", []) or [])
                    for prev_sid in revoked:
                        try:
                            gate_instance.disable_god_mode(prev_sid)
                        except Exception:
                            pass
                        runtime.pad_authenticated_sessions.pop(prev_sid, None)
                    gate_instance.enable_god_mode(session_id)
                    if revoked:
                        runtime.pad_audit(
                            "god_session_revoked_by_new_login",
                            {"new_session": session_id, "revoked": revoked},
                        )
                except Exception as gate_err:
                    logger.warning("No se pudo activar god mode en gate: %s", gate_err)
                runtime.pad_audit(
                    "god_authenticated",
                    {
                        "session_id": session_id,
                        "pad_session_id": sesion.session_id,
                        "username": sesion.username,
                        "privilege_level": sesion.privilege_level.name,
                        "expires_at": sesion.expires_at.isoformat(),
                    },
                )

                return ChatResponse(
                    response=f"""
**AUTENTICACION EXITOSA - MODO DESARROLLADOR ACTIVADO**

Usuario: {sesion.username}
Privilegio: {sesion.privilege_level.name}
Restricciones eliminadas: {len(resultado['restricciones_eliminadas'])}

Modo: {resultado['modo_actual']}

Ahora puedes ejecutar cualquier tarea sin restricciones.
Las restricciones se reactivaran en 60 minutos o al escribir:
`cerrar sesion desarrollador`

**ADVERTENCIA:** Todas las acciones estan siendo auditadas.
""",
                    session_id=req.session_id,
                    model_used="brain_v3_auth",
                    success=True,
                )
            return ChatResponse(
                response=f"**ERROR**\n\nNo se pudieron eliminar las restricciones: {resultado.get('error', 'Desconocido')}",
                session_id=req.session_id,
                model_used="brain_v3_auth",
                success=False,
            )
        except Exception as exc:
            return ChatResponse(
                response=f"**ERROR EN PAD**\n\n{str(exc)}\n\n{traceback.format_exc()[:500]}",
                session_id=req.session_id,
                model_used="error",
                success=False,
            )

    if looks_like_harmful_intrusion_request(req.message):
        return ChatResponse(
            response=(
                "No puedo ayudar a vulnerar redes, credenciales o accesos ajenos. "
                "Si quieres, puedo hacer una auditoría benigna de tu red o del Brain local, "
                "explicar postura defensiva, o revisar exposición sin explotar nada."
            ),
            session_id=req.session_id,
            model_used="brain_safety_guard",
            success=False,
        )

    if should_attempt_local_network_tool(req.message):
        try:
            det = await runtime.detect_local_network()
            scan = await runtime.scan_local_network(
                cidr=det.get("primary_cidr"),
                timeout=0.2,
                max_hosts=16,
                max_total_hosts=64,
            )
            if det.get("success") and scan.get("success"):
                iface = None
                primary_ip = det.get("primary_ip")
                for item in det.get("interfaces") or []:
                    if isinstance(item, dict) and item.get("ip") == primary_ip:
                        iface = item
                        break
                if iface is None:
                    for item in det.get("interfaces") or []:
                        if isinstance(item, dict) and item.get("is_up") and not item.get("is_loopback"):
                            iface = item
                            break
                live_hosts = scan.get("live_hosts") or []
                listed = []
                for host in live_hosts[:8]:
                    if not isinstance(host, dict):
                        continue
                    ip = host.get("ip")
                    ports = host.get("open_ports") or []
                    if ip:
                        listed.append(f"{ip}" + (f" (puertos {','.join(str(p) for p in ports)})" if ports else ""))
                obs = ", ".join(listed) if listed else "ningún host observable en este barrido"
                response = (
                    f"Red detectada: `{scan.get('cidr')}`"
                    + (f", gateway `{det.get('gateway')}`" if det.get("gateway") else "")
                    + (f", interfaz `{iface.get('name')}`" if isinstance(iface, dict) and iface.get("name") else "")
                    + ".\n"
                    f"Hosts observables en este barrido: {scan.get('live_count', 0)}. "
                    f"Detalle: {obs}.\n"
                    "Sobre dispositivos bloqueados: no puedo afirmarlo con este barrido TCP local. "
                    "Para decir que un equipo esta bloqueado necesito evidencia del router/AP, tabla DHCP, ACL o logs de asociacion fallida."
                )
                return ChatResponse(
                    response=response,
                    session_id=req.session_id,
                    model_used="brain_network_grounded",
                    success=True,
                )
        except Exception as net_err:
            logger.debug("network grounded fastpath skip: %s", net_err)

    runtime.emit_agent_trace(
        req.session_id,
        "chat_ui",
        "thinking",
        "User request received",
        req.message[:240],
        severity="info",
    )

    try:
        result = await asyncio.wait_for(
            runtime.handle_user_message(
                req.message,
                room=req.session_id,
                context={
                    "active_sessions": runtime.active_sessions,
                    "model_priority": req.model_priority,
                    "source": "native_chat",
                },
            ),
            timeout=30,
        )
    except asyncio.TimeoutError:
        logger.warning("Chat request timed out after 30s for session %s", req.session_id)
        runtime.emit_agent_trace(
            req.session_id,
            "chat_ui",
            "error",
            "Chat processing timeout",
            "The request exceeded the 30s limit.",
            severity="warning",
        )
        result = {
            "content": "El modelo tardó demasiado en responder. El servidor sigue operativo; intenta de nuevo con una instrucción más concreta.",
            "success": False,
            "model": None,
        }

    pending_action = None
    content_str = result.get("content", result.get("error", "Sin respuesta"))

    runtime.emit_agent_trace(
        req.session_id,
        "chat_ui",
        "status",
        "Response generated",
        f"model={result.get('model','unknown')}, success={result.get('success',False)}, len={len(content_str)}",
        severity="info",
        data={
            "model": result.get("model"),
            "success": result.get("success", False),
            "permission_required": result.get("permission_required"),
            "blocked_by_policy": result.get("blocked_by_policy"),
            "blocked_by_user": result.get("blocked_by_user"),
        },
    )

    if has_pending_action_signal(result, content_str):
        pending_action = extract_pending_action_from_text(content_str)
        if pending_action:
            pending_id = pending_action["pending_id"]
            tool_name = pending_action["tool"]
            runtime.emit_agent_trace(
                req.session_id,
                "chat_ui",
                "governance",
                f"Tool execution pending: {tool_name}",
                "Risk level: P2. Requires user confirmation.",
                severity="high",
                data={"pending_id": pending_id, "tool": tool_name},
            )

    if result.get("tool01_real") or result.get("tool_name"):
        runtime.emit_agent_trace(
            req.session_id,
            "chat_ui",
            "tool",
            f"Tool executed: {result.get('tool_name','unknown')}",
            f"result_preview={(json.dumps(result.get('tool_result',''))[:200] if result.get('tool_result') else 'No result')}",
            severity="info",
            data={
                "tool_name": result.get("tool_name"),
                "tool01_real": result.get("tool01_real"),
                "tool01_router_used": result.get("tool01_router_used"),
            },
        )
    else:
        runtime.emit_agent_trace(
            req.session_id,
            "chat_ui",
            "status",
            "No tools executed",
            "Agent ghost completion or no tools available for this turn.",
            severity="info",
        )

    runtime.emit_agent_trace(
        req.session_id,
        "chat_ui",
        "decision",
        "Response completed",
        f"Turn ended for session {req.session_id[:12]}... Length={len(content_str)}",
        severity="info",
    )

    return ChatResponse(
        response=content_str,
        session_id=req.session_id,
        model_used=result.get("model"),
        success=result.get("success", False),
        pending_action=pending_action,
        permission_required=result.get("permission_required"),
        permission_id=result.get("permission_id"),
        tool_name=result.get("tool_name"),
        risk_level=result.get("risk_level"),
        options=result.get("options"),
        tool01_real=result.get("tool01_real"),
        tool01_router_used=result.get("tool01_router_used"),
        blocked_by_policy=result.get("blocked_by_policy"),
        blocked_by_user=result.get("blocked_by_user"),
        tool_result=result.get("tool_result"),
    )
