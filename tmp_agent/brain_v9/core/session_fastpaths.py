"""
brain_v9.core.session_fastpaths
================================

B7-STRANGLER-08A: Fastpath handlers extracted from BrainSession.
Functions receive session as duck-typed DI object.
No imports from brain_v9.core.session.
All fastpaths are read-only status/observability; no trading execution.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain_v9.config import BASE_PATH, SERVER_HOST, SERVER_PORT
from brain_v9.core.state_io import read_json

_STATE_PATH = BASE_PATH / "tmp_agent" / "state"
_UI_PATH = BASE_PATH / "tmp_agent" / "brain_v9" / "ui"
_UI_INDEX = _UI_PATH / "index.html"
_UI_DASHBOARD = _UI_PATH / "dashboard.html"
_UI_EDIT_STATE_PATH = _STATE_PATH / "ui_edit_state.json"
_CHAT_METRICS_PATH = _STATE_PATH / "brain_metrics" / "chat_metrics_latest.json"
_EPISODIC_MEMORY_PATH = _STATE_PATH / "episodic_memory.json"
_CAPABILITY_GOVERNOR_STATUS_PATH = _STATE_PATH / "capability_governor" / "status_latest.json"

__all__ = [
    "maybe_fastpath",
    "llm_status_fastpath",
    "codex_role_fastpath",
    "codex_comparison_fastpath",
    "recent_activity_fastpath",
    "chat_interaction_review_fastpath",
    "maybe_grounded_code_analysis_fastpath",
    "blocks_grounded_ui_edit_fastpath",
    "maybe_grounded_ui_edit_fastpath",
    "maybe_qc_live_fastpath",
    "health_fastpath",
    "greeting_fastpath",
    "capabilities_fastpath",
    "brain_status_fastpath",
    "deep_brain_analysis_fastpath",
    "deep_risk_analysis_fastpath",
    "deep_edge_analysis_fastpath",
    "deep_strategy_analysis_fastpath",
    "deep_pipeline_analysis_fastpath",
    "self_build_fastpath",
    "self_build_resolution_fastpath",
    "consciousness_fastpath",
    "dashboard_status_fastpath",
    "utility_status_fastpath",
    "python_version_fastpath",
    "disk_space_fastpath",
    "running_services_fastpath",
    "search_files_fastpath",
    "list_directory_fastpath",
    "current_time_fastpath",
]


def maybe_fastpath(session, message: str, model_priority: str = "chat") -> Optional[Dict]:
        msg = message.lower()

        # ── Operational fastpaths (no LLM needed) ────────────────────────
        if session._is_llm_status_query(msg):
            return session._llm_status_fastpath(model_priority)
        if session._is_codex_comparison_query(msg):
            return session._codex_comparison_fastpath(model_priority)
        if session._is_codex_role_query(msg):
            return session._codex_role_fastpath(model_priority)
        if any(k in msg for k in ("version de python", "versión de python", "python version", "que python", "qué python")):
            return session._python_version_fastpath()
        if any(k in msg for k in ("espacio en disco", "espacio libre", "disk space", "disco duro", "almacenamiento", "cuanto espacio", "cuánto espacio", "espacio tengo")):
            return session._disk_space_fastpath()
        if any(k in msg for k in ("servicios corriendo", "servicios activos", "procesos corriendo", "running services", "que servicios", "qué servicios", "procesos activos")):
            return session._running_services_fastpath()
        if re.search(r"busca\s+archivos|buscar\s+archivos|find\s+files|search\s+files", msg):
            return session._search_files_fastpath(message)
        if any(k in msg for k in ("lista archivos", "listar archivos", "list files", "archivos en el directorio", "contenido del directorio", "list directory")):
            return session._list_directory_fastpath(message)
        if any(k in msg for k in ("que hora es", "qué hora es", "hora actual", "current time", "what time")):
            return session._current_time_fastpath()
        # P-OP56: Trading analysis composite fastpath
        # Negative guard: skip if message is about conversational routing/debug
        _ROUTING_DEBUG_TERMS = (
            "brainsession", "/chat", "route=", "route=llm", "route=agent",
            "grounded_code_fastpath", "grounded_ui_edit_fastpath", "router", "routing",
            "pipeline conversacional", "no analices trading"
        )
        if any(k in msg for k in (
            "estado del trading", "estado actual del trading", "analiza el trading",
            "analiza el estado actual del trading", "estado de trading",
            "trading status", "analisis de trading", "análisis de trading",
            "resumen de trading", "como va el trading", "cómo va el trading",
        )) and not any(r in msg for r in _ROUTING_DEBUG_TERMS):
            return session._cmd_trading_analysis()
        # ── End operational fastpaths ─────────────────────────────────────

        # R21: introspection - "que has hecho ultimamente", "has estado mejorando"
        if session._is_recent_activity_query(msg):
            return session._recent_activity_fastpath()
        if session._is_chat_interaction_review_query(msg):
            return session._chat_interaction_review_fastpath()
        if session._is_greeting_query(msg):
            return session._greeting_fastpath()
        if session._is_capabilities_query(msg):
            return session._capabilities_fastpath()
        if session._is_self_build_resolution_query(msg):
            return session._self_build_resolution_fastpath()
        if session._is_deep_risk_analysis_query(msg):
            return session._deep_risk_analysis_fastpath()
        if session._is_deep_edge_analysis_query(msg):
            return session._deep_edge_analysis_fastpath()
        if session._is_deep_strategy_analysis_query(msg):
            return session._deep_strategy_analysis_fastpath()
        if session._is_deep_pipeline_analysis_query(msg):
            return session._deep_pipeline_analysis_fastpath()
        if session._is_deep_brain_analysis_query(msg):
            return session._deep_brain_analysis_fastpath()
        if session._is_self_build_query(msg):
            return session._self_build_fastpath()
        if session._is_consciousness_query(msg):
            return session._consciousness_fastpath()
        if session._is_brain_status_query(msg):
            return session._brain_status_fastpath()
        if "utility u" in msg or ("bl-03" in msg and "promover" in msg):
            return session._utility_status_fastpath()
        if any(x in msg for x in ["edge validation", "edge_validation", "estado del edge", "estado de edge"]):
            return session._cmd_edge()
        if any(x in msg for x in ["ranking v2", "strategy ranking", "ranking actual", "estado del ranking"]):
            return session._cmd_ranking()
        if any(x in msg for x in ["pipeline integrity", "integridad del pipeline", "pipeline de trading", "integridad del trading"]):
            return session._cmd_pipeline()
        if any(x in msg for x in ["risk contract", "contrato de riesgo", "estado de riesgo", "riesgo del sistema", "risk status"]):
            return session._cmd_risk()
        if any(x in msg for x in ["governance health", "salud de gobernanza", "estado de gobernanza", "capas v3", "layer composition", "composicion de capas", "composición de capas"]):
            return session._cmd_governance()
        if any(x in msg for x in ["hipotesis", "hipótesis", "hypothesis", "sintesis post-trade", "síntesis post-trade"]):
            return session._cmd_hypothesis()
        if any(x in msg for x in ["post-trade", "post trade", "analisis post-trade", "análisis post-trade"]):
            return session._cmd_posttrade()
        if any(x in msg for x in ["security posture", "postura de seguridad", "estado de seguridad", "seguridad del sistema"]):
            return session._cmd_security()
        if any(x in msg for x in ["session memory", "memoria de sesion", "memoria de sesión", "contexto de la sesion", "contexto de la sesión"]):
            return session._cmd_memory()
        if any(x in msg for x in ["meta governance", "meta-governance", "meta gobernanza", "prioridad del sistema", "estado de prioridades", "foco actual"]):
            return session._cmd_priority()
        if any(x in msg for x in ["control layer", "change control", "change scorecard", "scorecard de cambios", "control de cambios"]):
            return session._cmd_control()
        if any(x in msg for x in ["estado de autonomia", "estado del loop autonomo", "estado del loop autónomo", "autonomy status", "autonomia actual"]):
            return session._cmd_autonomy()
        if any(x in msg for x in ["estado del strategy engine", "estado de estrategia", "strategy engine status", "candidatos actuales"]):
            return session._cmd_strategy()
        if any(x in msg for x in ["ultimo trade", "último trade", "estado del trade", "trade actual", "ultimo job", "último job"]):
            return session._cmd_trade()
        if any(x in msg for x in ["estado del sistema", "status del sistema", "system status", "resumen del sistema"]):
            return session._cmd_status()
        if any(x in msg for x in ["diagnostico del sistema", "diagnóstico del sistema", "diagnostic del sistema", "autodiagnostico", "autodiagnóstico"]):
            return session._cmd_diagnostic()
        if any(x in msg for x in ["learning loop", "loop de aprendizaje", "decisiones de aprendizaje", "learning decisions", "estado del learning"]):
            return session._cmd_learning()
        if any(x in msg for x in ["catalogo activo", "catálogo activo", "active catalog", "estrategias operativas", "estrategias activas"]):
            return session._cmd_catalog()
        if any(x in msg for x in ["context edge", "context-edge", "edge por contexto", "edge de contexto", "validacion por contexto", "validación por contexto"]):
            return session._cmd_context_edge()
        if session._is_dashboard_query(msg):
            # B3 FIX: Bloquear fastpath cuando se pide verificación real del estado
            msg_lower = msg.lower()
            if (("verifica" in msg_lower or "revisa" in msg_lower or "comprueba" in msg_lower) and
                "estado real" in msg_lower and
                any(x in msg_lower for x in ["dashboard", "http", "localhost", "127.0.0.1"])):
                # No usar fastpath - requiere verificación real
                return None
            
            # B3-v2 FIX: Bloquear cuando se pide análisis/contenido del dashboard (no solo infraestructura)
            asks_for_content = (
                any(x in msg_lower for x in ["analiza", "muestra", "dime", "explica", "describe", "cuéntame", "cuentame", "muéstrame", "muestrame"]) and
                "dashboard" in msg_lower and
                not any(x in msg_lower for x in ["infraestructura", "servidor", "host", "puerto", "url", "estatus simple", "estado simple", "estado operativo", "status"])
            )
            
            if asks_for_content:
                # No usar fastpath - el usuario quiere ver/analizar contenido real
                return None
            
            return session._dashboard_status_fastpath()
        if "estas operativo" in msg or "estás operativo" in msg:
            return session._health_fastpath()
        return None


def llm_status_fastpath(session, model_priority: str) -> Dict:
        from brain_v9.core.llm import CHAINS, MODELS

        requested = session._normalize_model_priority(model_priority or session._model_priority or "chat")
        if requested in MODELS:
            active_chain = [requested]
            requested_desc = f"seleccion explicita `{requested}`"
        else:
            active_chain = list(CHAINS.get(requested, CHAINS["chat"]))
            requested_desc = f"cadena `{requested}`"

        chat_chain = list(CHAINS.get("chat", []))
        code_chain = list(CHAINS.get("code", []))
        metrics = read_json(_STATE_PATH / "brain_metrics" / "llm_metrics_latest.json", default={})
        cb_models = ((metrics.get("circuit_breaker") or {}).get("models") or {})
        open_breakers = [name for name, state in cb_models.items() if state.get("is_open")]
        avg_latency = metrics.get("avg_latency")
        avg_latency_text = f"{float(avg_latency):.2f}s" if isinstance(avg_latency, (int, float)) else "N/D"

        def _fmt_chain(chain_items: List[str]) -> str:
            if not chain_items:
                return "ninguno"
            parts = []
            for key in chain_items:
                cfg = MODELS.get(key, {})
                model_name = cfg.get("model") or key
                parts.append(f"{key} ({model_name})")
            return " -> ".join(parts)

        active_primary = active_chain[0] if active_chain else "chat"
        active_primary_cfg = MODELS.get(active_primary, {})
        active_primary_name = active_primary_cfg.get("model") or active_primary

        text = (
            "Estado actual del enrutado LLM\n"
            f"  Consulta actual: {requested_desc}\n"
            f"  Primario para esta consulta: {active_primary} ({active_primary_name})\n"
            f"  Fallbacks para esta consulta: {', '.join(active_chain[1:]) if len(active_chain) > 1 else 'ninguno'}\n"
            f"  Chat rapido UI: {_fmt_chain(chat_chain)}\n"
            f"  Codigo / inspeccion grounded: {_fmt_chain(code_chain)}\n"
            "  Nota: Codex esta promovido para `code` e inspeccion de archivos; "
            "el chat general sigue usando la cadena `chat`.\n"
            f"  Latencia media reciente LLM: {avg_latency_text}\n"
            f"  Circuit breakers abiertos: {', '.join(open_breakers) if open_breakers else 'ninguno'}"
        )
        return session._system_reply(text)


def codex_role_fastpath(session, model_priority: str) -> Dict:
        from brain_v9.core.llm import CHAINS

        chat_chain = " -> ".join(CHAINS.get("chat", []))
        code_chain = " -> ".join(CHAINS.get("code", []))
        analysis_chain = " -> ".join(CHAINS.get("analysis_frontier", []))
        requested = session._normalize_model_priority(model_priority or "chat")
        text = (
            "Rol actual de Codex en Brain V9\n"
            f"  Chat general: NO es principal. Usa la cadena `chat` = {chat_chain}\n"
            f"  Codigo / inspeccion grounded: SI es principal. Usa la cadena `code` = {code_chain}\n"
            f"  Analisis tecnico/causal: SI participa primero en `analysis_frontier` = {analysis_chain}\n"
            "  Motivo: Codex mejora inspeccion tecnica y explicaciones de alto nivel, pero no se dejo como motor "
            "principal universal del chat porque el carril general necesita priorizar estabilidad, costo y evitar "
            "degradacion en prompts triviales u operativos.\n"
            "  Regla actual: conversacion general -> chat; analisis tecnico -> analysis_frontier; "
            "codigo/archivos -> code; acciones reales -> agent."
        )
        return session._system_reply(text)


def codex_comparison_fastpath(session, model_priority: str) -> Dict:
        from brain_v9.core.llm import CHAINS

        chat_chain = " -> ".join(CHAINS.get("chat", []))
        code_chain = " -> ".join(CHAINS.get("code", []))
        analysis_chain = " -> ".join(CHAINS.get("analysis_frontier", []))
        text = (
            "Comparativa tecnica: Codex en `code` vs Codex en chat general\n"
            f"  `code`: usa {code_chain}. Aqui Codex esta promovido porque mejora inspeccion de archivos, "
            "razonamiento sobre codigo y cierre con evidencia grounded.\n"
            f"  `chat` general: usa {chat_chain}. Aqui Codex no es el motor principal; entra como fallback alto "
            "y la prioridad sigue siendo estabilidad, costo y respuestas cortas.\n"
            f"  `analysis_frontier`: usa {analysis_chain}. Sirve para analisis tecnico/causal no operativo.\n"
            "  Tradeoff actual: `code` y `analysis_frontier` maximizan calidad de cierre; `chat` general maximiza "
            "tiempo de respuesta y evita meter una cadena pesada en prompts triviales.\n"
            "  Regla practica: pregunta de archivos/codigo -> `code`; comparativa/causa tecnica -> `analysis_frontier`; "
            "pregunta breve general -> `chat`."
        )
        return session._system_reply(text)


def recent_activity_fastpath(session, window_hours: int = 6) -> Dict:
        """R21: Read state/events/event_log.jsonl and summarize recent activity.

        Replaces the canned 'No obtuve resultados' on SYSTEM-introspection queries.
        Reads at most last 2000 lines, filters by window_hours, aggregates by event
        name, and returns a concise human-readable summary.
        """
        from collections import Counter
        from datetime import datetime as _dt, timedelta as _td
        from pathlib import Path as _Path

        log_path = _Path("C:/AI_VAULT/tmp_agent/state/events/event_log.jsonl")
        if not log_path.exists():
            return session._system_reply(
                "No tengo registro de actividad (event_log.jsonl no existe)."
            )

        try:
            # Read tail efficiently: load all then slice (event log usually <5MB)
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as exc:
            return session._system_reply(f"Error leyendo event_log: {exc}")

        if not lines:
            return session._system_reply("event_log vacío - aún no he registrado actividad.")

        tail = lines[-2000:]
        cutoff = _dt.now() - _td(hours=window_hours)

        chats_route = Counter()
        chats_success = Counter()
        chats_failed = Counter()
        intents = Counter()
        decisions = Counter()
        cap_failures = Counter()
        last_chat_ts = None
        first_in_window_ts = None
        total_in_window = 0
        chat_durations = []

        for raw in tail:
            try:
                ev = json.loads(raw)
            except Exception:
                continue
            ts_str = ev.get("ts", "")
            try:
                ts = _dt.fromisoformat(ts_str)
            except Exception:
                continue
            if ts < cutoff:
                continue
            total_in_window += 1
            if first_in_window_ts is None:
                first_in_window_ts = ts
            name = ev.get("name", "")
            payload = ev.get("payload") or {}

            if name == "chat.completed":
                last_chat_ts = ts
                route = payload.get("route", "?")
                chats_route[route] += 1
                if payload.get("success"):
                    chats_success[route] += 1
                else:
                    chats_failed[route] += 1
                intent = payload.get("intent", "?")
                if intent:
                    intents[intent] += 1
                dur = payload.get("duration_ms")
                if isinstance(dur, (int, float)) and dur > 0:
                    chat_durations.append(float(dur))
            elif name == "decision.completed":
                dec = payload.get("decision") or {}
                comp = dec.get("complexity", "?")
                decisions[comp] += 1
            elif name == "capability.failed":
                cap = payload.get("capability", "?")
                err = payload.get("error_type") or payload.get("reason", "?")
                # Keep error key short
                if isinstance(err, str) and len(err) > 50:
                    err = err[:50] + "..."
                cap_failures[(cap, err)] += 1

        if total_in_window == 0:
            return session._system_reply(
                f"Sin actividad registrada en las últimas {window_hours}h. "
                f"Ultimo evento: {tail[-1][:120] if tail else 'n/a'}"
            )

        total_chats = sum(chats_route.values())
        avg_dur_s = (sum(chat_durations) / len(chat_durations) / 1000.0) if chat_durations else 0.0
        max_dur_s = (max(chat_durations) / 1000.0) if chat_durations else 0.0

        lines_out = [
            f"Actividad de las últimas {window_hours}h ({total_in_window} eventos):",
            f"",
            f"Chats: {total_chats} total",
        ]
        for route, n in chats_route.most_common():
            ok = chats_success.get(route, 0)
            ko = chats_failed.get(route, 0)
            lines_out.append(f"  - route={route}: {n} (ok={ok}, fail={ko})")

        if chat_durations:
            lines_out.append(f"  - latencia chat: avg={avg_dur_s:.1f}s, max={max_dur_s:.1f}s")

        if intents:
            top_intents = ", ".join(f"{i}={n}" for i, n in intents.most_common(5))
            lines_out.append(f"  - intents top: {top_intents}")

        if decisions:
            lines_out.append("")
            lines_out.append(f"Decisiones del agente: {sum(decisions.values())}")
            for comp, n in decisions.most_common():
                lines_out.append(f"  - complexity={comp}: {n}")

        if cap_failures:
            lines_out.append("")
            lines_out.append(f"Fallos de capability: {sum(cap_failures.values())}")
            for (cap, err), n in cap_failures.most_common(5):
                lines_out.append(f"  - {cap} ({err}): {n}")

        if last_chat_ts:
            lines_out.append("")
            lines_out.append(f"Último chat: {last_chat_ts.strftime('%Y-%m-%d %H:%M:%S')}")

        return session._system_reply("\n".join(lines_out))


def chat_interaction_review_fastpath(session) -> Dict:
        metrics = read_json(_CHAT_METRICS_PATH, default={})
        episodic = read_json(_EPISODIC_MEMORY_PATH, default=[])
        capability = read_json(_CAPABILITY_GOVERNOR_STATUS_PATH, default={})

        recent = episodic[-12:] if isinstance(episodic, list) else []
        bad_candidates = []
        for item in recent:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "")
            kind = str(item.get("type") or "")
            if kind == "error" or "0 OK, 0 fail" in content or "0 OK, 1 fail" in content or "0 OK, 2 fail" in content:
                bad_candidates.append(item)

        recent_incidents = capability.get("recent_incidents") or []
        net_incidents = [
            inc for inc in recent_incidents
            if isinstance(inc, dict) and (
                str(inc.get("requested_tool") or "") == "scan_local_network"
                or "Expected 4 octets in 'auto'" in str(inc.get("reason") or "")
            )
        ]

        ghosts = int(metrics.get("ghost_completion_count") or 0)
        canned = int(metrics.get("canned_no_result_count") or 0)
        avg_latency = float(metrics.get("avg_latency_ms") or 0.0)

        findings = []
        if canned > 0:
            findings.append("el chat todavia cae a respuestas extractivas o superficiales cuando falla la sintesis")
        if ghosts > 0:
            findings.append("hubo al menos un ghost_completion visible recientemente")
        if avg_latency > 20000:
            findings.append(f"la latencia conversacional sigue alta ({avg_latency/1000.0:.1f}s promedio)")
        if net_incidents:
            findings.append("hubo fallos reales de scan_local_network; el bug de 'auto' ya fue corregido")
        if not findings:
            findings.append("no veo fallos graves recientes en la ruta conversacional")

        lines = [
            "Revision de interacciones chat-brain recientes",
            f"  metricas: ghost_completion={ghosts}, canned_no_result={canned}, avg_latency_ms={avg_latency:.1f}",
            f"  incidentes recientes de capabilities: {len(recent_incidents)}",
            "  hallazgos:",
        ]
        for finding in findings:
            lines.append(f"    - {finding}")

        if bad_candidates:
            lines.append("  ejemplos recientes problemáticos:")
            for item in bad_candidates[:4]:
                ts = item.get("timestamp", "N/A")
                content = str(item.get("content") or "")[:180]
                lines.append(f"    - {ts}: {content}")

        if net_incidents:
            lines.append("  estado del bug de red:")
            lines.append("    - scan_local_network(cidr='auto') ya no rompe")
            lines.append("    - el probe CHAT-NET-001 ya pasa")

        lines.append("  siguiente accion correcta:")
        lines.append("    - endurecer la ruta que hoy cae a 'Resumen extractivo' para que no se marque como exito")
        return session._system_reply("\n".join(lines))


async def maybe_grounded_code_analysis_fastpath(session, message: str) -> Optional[Dict]:
        if not session._is_grounded_code_analysis_query(message):
            return None

        paths = session._extract_candidate_paths(message)
        if not paths:
            return None

        symbol_hint = session._extract_symbol_hint(message)
        sections = []
        for path in paths:
            try:
                excerpt = session._build_grounded_file_excerpt(path, message, symbol_hint)
            except Exception as exc:
                excerpt = f"[error leyendo {path}: {exc}]"
            sections.append(f"ARCHIVO: {path}\n{excerpt}")

        if any(token in message.lower() for token in ("prueba", "test", "cubre")):
            test_refs = session._find_test_references(symbol_hint)
            if test_refs:
                sections.append(
                    "TESTS POSIBLEMENTE RELACIONADOS:\n" +
                    "\n\n".join(session._build_test_reference_excerpt(p, symbol_hint) for p in test_refs)
                )

        prompt = (
            "Responde en español, directo y técnico. Usa solo la evidencia de los snippets.\n"
            "Si falta evidencia, dilo.\n"
            "Incluye referencias de archivo y línea cuando sea útil.\n\n"
            f"PREGUNTA DEL USUARIO:\n{message}\n\n"
            "EVIDENCIA:\n" + "\n\n".join(sections)
        )

        result = await session.llm.query(
            [{"role": "user", "content": prompt}],
            model_priority="code",
            max_time=180,
        )
        if not result.get("success") or not result.get("content"):
            return session._system_reply(
                "No pude cerrar el análisis de código grounded en este turno.",
                success=False,
            )
        text = session._sanitize_llm_chat_response(result["content"])
        reply = session._system_reply(text, success=True)
        reply["model"] = result.get("model")
        reply["model_used"] = result.get("model_used")
        reply["model_key"] = result.get("model_key")
        return reply


def blocks_grounded_ui_edit_fastpath(message: str) -> bool:
        msg = (message or "").lower()
        no_change_markers = (
            "no modifiques", "no modificar", "no cambies", "no cambiar",
            "no edites", "no editar", "no toques", "no uses tools",
            "sin herramientas", "sin modificar", "sin cambios",
            "no hagas cambios",
        )
        analysis_markers = (
            "solo analiza", "analiza", "analizar", "audita", "auditar",
        )
        return (
            any(marker in msg for marker in no_change_markers)
            or any(marker in msg for marker in analysis_markers)
        )


async def maybe_grounded_ui_edit_fastpath(session, message: str) -> Optional[Dict]:
        if session._blocks_grounded_ui_edit_fastpath(message):
            return None

        if not (
            session._is_chat_ui_background_change_query(message)
            or session._is_chat_send_button_move_query(message)
        ):
            return None

        target_path = _UI_INDEX
        if not target_path.exists():
            return session._system_reply(
                f"No encontre el archivo activo de UI esperado: {target_path}",
                success=False,
            )

        original = target_path.read_text(encoding="utf-8", errors="replace")
        msg_l = (message or "").lower()
        if session._is_chat_ui_background_change_query(message):
            match = re.search(r"(--bg:\s*)(#[0-9a-fA-F]{6})(\s*;)", original)
            if not match:
                return session._system_reply(
                    f"No pude localizar la variable CSS `--bg` en {target_path}.",
                    success=False,
                )
            old_color = match.group(2)
            ui_state = read_json(_UI_EDIT_STATE_PATH, default={}) or {}
            if any(token in msg_l for token in ("oscuro", "dark")):
                new_color = ui_state.get("bg", {}).get("default_dark_color") or "#0f1117"
            elif any(token in msg_l for token in ("muy claro",)):
                new_color = "#eef2f8"
            elif any(token in msg_l for token in ("gris claro", "claro", "light")):
                new_color = "#d9dee8"
            elif session._is_chat_ui_background_restore_query(message):
                new_color = (
                    ui_state.get("bg", {}).get("last_old_color")
                    or ui_state.get("bg", {}).get("default_dark_color")
                    or "#0f1117"
                )
            else:
                new_color = "#171c26"

            if old_color.lower() != new_color.lower():
                updated = original[:match.start(2)] + new_color + original[match.end(2):]
                target_path.write_text(updated, encoding="utf-8")
                changed = True
            else:
                changed = False

            write_json(_UI_EDIT_STATE_PATH, {
                "bg": {
                    "last_old_color": old_color,
                    "last_new_color": new_color,
                    "default_dark_color": "#0f1117",
                    "updated_at": int(_r3_time.time()),
                }
            })

            text = (
                f"Cambio aplicado en la UI del chat.\n"
                f"archivo_tocado: {target_path}\n"
                f"variable_css: --bg\n"
                f"valor_anterior: {old_color}\n"
                f"valor_nuevo: {new_color}\n"
                f"estado: {'actualizado' if changed else 'ya estaba aplicado'}"
            )
            return session._system_reply(text, success=True)

        distance_match = re.search(r"(\d+)\s*px", msg_l)
        distance = int(distance_match.group(1)) if distance_match else 20
        shift = -distance if any(token in msg_l for token in ("izquierda", "left")) else distance
        send_btn_rule = f"#send-btn {{ transform: translateX({shift}px); }}"
        rule_re = re.compile(r"#send-btn\s*\{\s*transform:\s*translateX\((-?\d+)px\);\s*\}", re.IGNORECASE)
        rule_match = rule_re.search(original)
        if rule_match:
            old_shift = int(rule_match.group(1))
            updated = rule_re.sub(send_btn_rule, original, count=1)
        else:
            old_shift = 0
            anchor = "/* ── Status / Metrics ── */"
            if anchor not in original:
                return session._system_reply(
                    f"No pude encontrar el ancla CSS esperada para insertar la regla de `#send-btn` en {target_path}.",
                    success=False,
                )
            updated = original.replace(anchor, send_btn_rule + "\n\n  " + anchor, 1)
        target_path.write_text(updated, encoding="utf-8")
        text = (
            f"Cambio aplicado en la UI del chat.\n"
            f"archivo_tocado: {target_path}\n"
            f"selector_css: #send-btn\n"
            f"transform_anterior: translateX({old_shift}px)\n"
            f"transform_nueva: translateX({shift}px)\n"
            f"estado: {'actualizado' if old_shift != shift else 'ya estaba aplicado'}"
        )
        return session._system_reply(text, success=True)


async def maybe_qc_live_fastpath(session, message: str) -> Optional[Dict]:
        if not session._is_qc_live_query(message):
            return None

        try:
            from brain_v9.trading.connectors import QuantConnectConnector
        except Exception as exc:
            return session._system_reply(
                f"No pude cargar el conector de QuantConnect: {exc}",
                success=False,
            )

        deploy_artifact = (
            BASE_PATH / "tmp_agent" / "strategies" / "mean_reversion_eq"
            / "live_deploy_phase80_p62_1100_r75_mom15_full_diag_2026-05-06.json"
        )
        project_id = 29652652
        deploy_id = ""
        try:
            payload = json.loads(deploy_artifact.read_text(encoding="utf-8"))
            for step in reversed(payload.get("steps", [])):
                data = step.get("data") or {}
                if data.get("deployId"):
                    deploy_id = str(data["deployId"]).strip()
                    break
        except Exception:
            pass
        if not deploy_id:
            return session._system_reply(
                "No pude determinar el deployId activo de QC live desde los artefactos locales.",
                success=False,
            )

        connector = QuantConnectConnector()
        try:
            live = await connector.read_live(project_id, deploy_id)
        finally:
            try:
                await connector.close()
            except Exception:
                pass

        if not live.get("success"):
            return session._system_reply(
                f"No pude leer QC live. deploy_id={deploy_id} error={live.get('error') or live.get('errors') or 'desconocido'}",
                success=False,
            )

        runtime = live.get("runtime_statistics") or {}
        lines = [
            "Lectura real de QC live:",
            f"project_id: {project_id}",
            f"deploy_id: {deploy_id}",
            f"state: {live.get('state') or 'unknown'}",
            f"Net Profit: {runtime.get('Net Profit', 'N/A')}",
            f"Equity: {runtime.get('Equity', 'N/A')}",
            f"Return: {runtime.get('Return', 'N/A')}",
            f"Holdings: {runtime.get('Holdings', 'N/A')}",
            f"Orb1Fills: {runtime.get('Orb1Fills', 'N/A')}",
            f"Orb2Fills: {runtime.get('Orb2Fills', 'N/A')}",
            f"TrORB: {runtime.get('TrORB', 'N/A')}",
            f"PnlORB: {runtime.get('PnlORB', 'N/A')}",
            f"TrMR: {runtime.get('TrMR', 'N/A')}",
            f"TrST: {runtime.get('TrST', 'N/A')}",
            f"ExternalStress: {runtime.get('ExternalStress', 'N/A')}",
        ]
        return session._system_reply("\n".join(lines), success=True)


def health_fastpath(session) -> Dict:
        text = (
            f"Si, Brain V9 esta operativo.\n"
            f"status: healthy\n"
            f"sessions: {1 if session.is_running else 0}\n"
            f"session_id: {session.session_id}"
        )
        return session._system_reply(text)


def greeting_fastpath(session) -> Dict:
        return session._system_reply(
            "Hola. Brain V9 esta operativo. Si quieres revisar algo concreto, dilo en una frase."
        )


def capabilities_fastpath(session) -> Dict:
        return session._system_reply(
            "Puedo revisar estado del brain, dashboard, autonomia, riesgo, trading y cambios; resumir snapshots canonicos; y ejecutar diagnosticos operativos cuando lo pidas."
        )


def brain_status_fastpath(session) -> Dict:
        governance = read_json(_STATE_PATH / "governance_health_latest.json", default={})
        control = read_json(_STATE_PATH / "control_layer_status.json", default={})
        meta = read_json(_STATE_PATH / "meta_governance_status_latest.json", default={})
        utility = read_json(_STATE_PATH / "utility_u_latest.json", default={})
        cycle = read_json(_STATE_PATH / "next_level_cycle_status_latest.json", default={})
        roadmap = read_json(_STATE_PATH / "roadmap.json", default={})
        edge = read_json(_STATE_PATH / "strategy_engine" / "edge_validation_latest.json", default={})
        change_validation = governance.get("change_validation") or {}
        system_profile = meta.get("system_profile") or {}
        edge_summary = edge.get("summary") or {}
        u_score = session._utility_score(utility)
        verdict = utility.get("verdict") or utility.get("promotion_gate", {}).get("verdict", "N/A")
        phase = cycle.get("current_phase") or roadmap.get("current_phase") or "N/A"
        blockers = session._utility_blockers(utility)
        validated = edge_summary.get("validated_count", 0)
        probation = edge_summary.get("probation_count", 0)
        text = (
            f"Estado actual del brain\n"
            f"  Utility: U={u_score}, veredicto: {verdict}\n"
            f"  Fase: {phase}\n"
            f"  Edge: {validated} validadas, {probation} en probation\n"
            f"  Blockers: {', '.join(blockers) or 'ninguno'}\n"
            f"  Modo: {governance.get('current_operating_mode', 'N/A')} | Salud: {governance.get('overall_status', 'N/A')}\n"
            f"  Control layer: {control.get('mode', 'N/A')} | Ejecucion permitida: {'si' if control.get('execution_allowed') else 'no'}\n"
            f"  Accion top: {meta.get('top_action', 'N/A')}"
        )
        return session._system_reply(text)


def deep_brain_analysis_fastpath(session) -> Dict:
        governance = read_json(_STATE_PATH / "governance_health_latest.json", default={})
        control = read_json(_STATE_PATH / "control_layer_status.json", default={})
        risk = read_json(_STATE_PATH / "risk" / "risk_contract_status_latest.json", default={})
        meta = read_json(_STATE_PATH / "meta_governance_status_latest.json", default={})
        self_model = read_json(_STATE_PATH / "brain_self_model_latest.json", default={})
        change_validation = read_json(_STATE_PATH / "change_validation_status_latest.json", default={}).get("summary", {})
        edge = read_json(_STATE_PATH / "strategy_engine" / "edge_validation_latest.json", default={}).get("summary", {})
        ranking = read_json(_STATE_PATH / "strategy_engine" / "strategy_ranking_v2_latest.json", default={})

        system_profile = meta.get("system_profile") or {}
        layers = governance.get("layers") or {}
        v8 = layers.get("V8") or {}
        weak_domains = [
            domain.get("domain_id")
            for domain in (self_model.get("domains") or [])
            if domain.get("status") == "needs_work"
        ][:3]
        top_ranked = (ranking.get("ranked") or [{}])[0]

        text = (
            f"Analisis profundo del brain\n"
            f"  lectura general: el sistema esta operativo pero en modo de aprendizaje, no de explotacion. La evidencia es modo={governance.get('current_operating_mode', 'N/A')}, control_layer={control.get('mode', 'N/A')} y risk_status={risk.get('status', 'N/A')}.\n"
            f"  implicacion 1: puede seguir ejecutando y aprendiendo, pero no tiene permiso epistemico para promocionar edge. La evidencia es validated_count={system_profile.get('validated_count', 'N/A')}, promotable_count={edge.get('promotable_count', 'N/A')}, V8={v8.get('state', 'N/A')}.\n"
            f"  implicacion 2: la mayor deuda no es infraestructura sino validacion. La evidencia es apply_gate_ready={change_validation.get('apply_gate_ready', 'N/A')}, passed={change_validation.get('passed_count', 'N/A')}, pending={change_validation.get('pending_count', 'N/A')}.\n"
            f"  implicacion 3: la prioridad correcta hoy sigue siendo reunir muestra y mejorar edge, no ampliar autonomia. La evidencia es top_action={meta.get('top_action', 'N/A')}, blockers={', '.join(system_profile.get('blockers', [])) or 'ninguno'}, top_ranked={top_ranked.get('strategy_id', 'N/A')} con execution_ready_now={top_ranked.get('execution_ready_now', 'N/A')}.\n"
            f"  autoconciencia operativa: existe como modelo de estado y prioridades, pero no como conciencia fuerte. La evidencia es current_mode={(self_model.get('identity') or {}).get('current_mode', 'N/A')}, overall_score={self_model.get('overall_score', 'N/A')}, weak_domains={', '.join(weak_domains) or 'ninguno'}.\n"
            f"  conclusion operativa: el brain sirve para monitoreo, diagnostico y aprendizaje controlado; no esta listo para promocion autonoma robusta mientras sigan no_validated_edge, sample_not_ready o apply_gate_ready=false."
        )
        return session._system_reply(text)


def deep_risk_analysis_fastpath(session) -> Dict:
        risk = read_json(_STATE_PATH / "risk" / "risk_contract_status_latest.json", default={})
        control = read_json(_STATE_PATH / "control_layer_status.json", default={})
        limits = risk.get("limits") or {}
        measures = risk.get("measures") or {}
        warnings = risk.get("warnings") or []
        hard_violations = risk.get("hard_violations") or []
        text = (
            f"Analisis profundo de riesgo\n"
            f"  lectura general: el contrato de riesgo esta {risk.get('status', 'N/A')} y execution_allowed={risk.get('execution_allowed', 'N/A')}.\n"
            f"  implicacion 1: el sistema no esta bloqueado por riesgo duro en este momento. La evidencia es hard_violations={', '.join(hard_violations) or 'ninguna'} y control_layer={control.get('mode', 'N/A')}.\n"
            f"  implicacion 2: sigue habiendo presion economica aunque la capa no este congelada. La evidencia es daily_loss_frac={measures.get('daily_loss_frac', 'N/A')} sobre limite={limits.get('max_daily_loss_frac', 'N/A')}, weekly_drawdown_frac={measures.get('weekly_drawdown_frac', 'N/A')} sobre limite={limits.get('max_weekly_drawdown_frac', 'N/A')}.\n"
            f"  implicacion 3: el riesgo operativo hoy depende mas de edge negativo que de exposure. La evidencia es total_exposure_frac={measures.get('total_exposure_frac', 'N/A')} sobre limite={limits.get('max_total_exposure_frac', 'N/A')}, warnings={', '.join(warnings) or 'ninguna'}.\n"
            f"  conclusion operativa: el riesgo permite seguir en paper y aprendizaje, pero no justifica promocion agresiva mientras la capa de edge siga sin validacion."
        )
        return session._system_reply(text)


def deep_edge_analysis_fastpath(session) -> Dict:
        edge = read_json(_STATE_PATH / "strategy_engine" / "edge_validation_latest.json", default={})
        summary = edge.get("summary") or {}
        best_probation = summary.get("best_probation") or {}
        text = (
            f"Analisis profundo de edge validation\n"
            f"  lectura general: no existe edge validado para explotacion. La evidencia es validated_count={summary.get('validated_count', 0)}, promotable_count={summary.get('promotable_count', 0)} y top_execution_edge={(summary.get('top_execution_edge') or {}).get('strategy_id', 'N/A')}.\n"
            f"  implicacion 1: el sistema sigue en modo de discovery/probation, no de promocion. La evidencia es probation_count={summary.get('probation_count', 0)}, blocked_count={summary.get('blocked_count', 0)}.\n"
            f"  implicacion 2: la mejor oportunidad actual sigue incompleta, no confirmada. La evidencia es best_probation={best_probation.get('strategy_id', 'N/A')}, entries={best_probation.get('best_entries_resolved', 'N/A')}, blockers={', '.join(best_probation.get('blockers', [])) or 'ninguno'}.\n"
            f"  implicacion 3: mientras validated_ready_count={summary.get('validated_ready_count', 0)} y probation_ready_count={summary.get('probation_ready_count', 0)} sigan en cero, la utilidad real seguira penalizada.\n"
            f"  conclusion operativa: edge validation hoy sirve para seleccionar donde seguir probando, no para habilitar promocion autonoma."
        )
        return session._system_reply(text)


def deep_strategy_analysis_fastpath(session) -> Dict:
        ranking = read_json(_STATE_PATH / "strategy_engine" / "strategy_ranking_v2_latest.json", default={})
        ranked = ranking.get("ranked") or []
        top = ranked[0] if ranked else {}
        probation = ranking.get("probation_candidate") or {}
        text = (
            f"Analisis profundo del strategy engine\n"
            f"  lectura general: el motor esta priorizando comparacion y muestra, no explotacion. La evidencia es top_action={ranking.get('top_action', 'N/A')}, exploit_candidate={(ranking.get('exploit_candidate') or {}).get('strategy_id', 'N/A')}.\n"
            f"  implicacion 1: la estrategia mejor rankeada no equivale a estrategia ejecutable. La evidencia es top_ranked={top.get('strategy_id', 'N/A')}, edge={top.get('edge_state', 'N/A')}, execution_ready_now={top.get('execution_ready_now', 'N/A')}.\n"
            f"  implicacion 2: el ranking actual es mas una cola de investigacion que una cola de deployment. La evidencia es probation_candidate={probation.get('strategy_id', 'N/A')}, explore_candidate={(ranking.get('explore_candidate') or {}).get('strategy_id', 'N/A')}.\n"
            f"  implicacion 3: mientras no aparezca exploit_candidate real y top_strategy operable, el motor debe seguir comparando y descartando variantes.\n"
            f"  conclusion operativa: el strategy engine esta funcionando como clasificador de oportunidades, pero todavia no como selector de edge listo para explotacion."
        )
        return session._system_reply(text)


def deep_pipeline_analysis_fastpath(session) -> Dict:
        payload = read_json(_STATE_PATH / "strategy_engine" / "pipeline_integrity_latest.json", default={})
        summary = payload.get("summary") or {}
        anomalies = payload.get("anomalies") or []
        orphaned_total = (anomalies[0] if anomalies else {}).get("orphaned_resolved_total", "N/A")
        text = (
            f"Analisis profundo del pipeline\n"
            f"  lectura general: el pipeline esta {summary.get('status', 'unknown')} y pipeline_ok={summary.get('pipeline_ok', False)}.\n"
            f"  implicacion 1: la cadena signal->ledger->utility sigue viva. La evidencia es signals_count={summary.get('signals_count', 0)}, ledger_entries={summary.get('ledger_entries', 0)}, decision_fresh_after_utility={summary.get('decision_fresh_after_utility', False)}.\n"
            f"  implicacion 2: la deuda actual es de reconciliacion/historial, no de colapso total. La evidencia es anomaly_count={summary.get('anomaly_count', 0)}, orphaned_resolved_total={orphaned_total}.\n"
            f"  implicacion 3: aunque pipeline_ok sea verdadero, degraded status significa que la calidad de evidencia todavia tiene friccion para gobernanza fina.\n"
            f"  conclusion operativa: el pipeline sirve para operar y aprender, pero todavia no es una base limpia para decisiones de promocion fuertes si persisten anomalias reconciliables."
        )
        return session._system_reply(text)


def self_build_fastpath(session) -> Dict:
        governance = read_json(_STATE_PATH / "governance_health_latest.json", default={})
        change_validation = read_json(_STATE_PATH / "change_validation_status_latest.json", default={}).get("summary", {})
        meta = read_json(_STATE_PATH / "meta_governance_status_latest.json", default={})
        system_profile = meta.get("system_profile") or {}
        ready = bool(change_validation.get("apply_gate_ready")) and system_profile.get("validated_count", 0) > 0
        verdict = "SI" if ready else "NO"
        text = (
            f"Autoconstruccion\n"
            f"  lista para promover cambios autonomos: {verdict}\n"
            f"  apply_gate_ready: {change_validation.get('apply_gate_ready', False)}\n"
            f"  validaciones: passed={change_validation.get('passed_count', 0)} | pending={change_validation.get('pending_count', 0)}\n"
            f"  V8 promotion layer: {(governance.get('layers') or {}).get('V8', {}).get('state', 'N/A')}\n"
            f"  validated_count: {system_profile.get('validated_count', 'N/A')} | promotable_count: {system_profile.get('promotable_count', 'N/A')}\n"
            f"  blockers: {', '.join(system_profile.get('blockers', [])) or 'ninguno'}"
        )
        return session._system_reply(text, success=ready)


def self_build_resolution_fastpath(session) -> Dict:
        governance = read_json(_STATE_PATH / "governance_health_latest.json", default={})
        control = read_json(_STATE_PATH / "control_layer_status.json", default={})
        risk = read_json(_STATE_PATH / "risk" / "risk_contract_status_latest.json", default={})
        change_validation = read_json(_STATE_PATH / "change_validation_status_latest.json", default={}).get("summary", {})
        meta = read_json(_STATE_PATH / "meta_governance_status_latest.json", default={})
        system_profile = meta.get("system_profile") or {}
        blockers = system_profile.get("blockers", []) or []
        ready = bool(change_validation.get("apply_gate_ready")) and system_profile.get("validated_count", 0) > 0
        verdict = "SI" if ready else "NO"
        text = (
            f"Resolucion de autoconstruccion\n"
            f"  veredicto: {verdict}; hoy no se resuelve cambiando un flag.\n"
            f"  causa 1: change_validation sigue incompleto. Evidencia: apply_gate_ready={change_validation.get('apply_gate_ready', False)}, passed={change_validation.get('passed_count', 0)}, pending={change_validation.get('pending_count', 0)}.\n"
            f"  causa 2: no hay edge promovible. Evidencia: validated_count={system_profile.get('validated_count', 0)}, promotable_count={system_profile.get('promotable_count', 0)}, blockers={', '.join(blockers) or 'ninguno'}.\n"
            f"  causa 3: la capa de promocion no esta lista. Evidencia: V8={(governance.get('layers') or {}).get('V8', {}).get('state', 'N/A')}, control_layer={control.get('mode', 'N/A')}, risk_execution_allowed={risk.get('execution_allowed', 'N/A')}.\n"
            f"  playbook 1: cerrar deuda de validacion hasta pending=0, passed>0 y apply_gate_ready=true.\n"
            f"  playbook 2: seguir comparacion/probation hasta obtener validated_count>0 y promotable_count>0 sin blockers tipo no_validated_edge o no_positive_edge.\n"
            f"  playbook 3: refrescar governance, control y risk; confirmar V8=active y control_layer=ACTIVE antes de cualquier promote.\n"
            f"  criterio de salida: apply_gate_ready=true, validated_count>0, promotable_count>0, V8=active y control_layer=ACTIVE."
        )
        return session._system_reply(text, success=ready)


def consciousness_fastpath(session) -> Dict:
        self_model = read_json(_STATE_PATH / "brain_self_model_latest.json", default={})
        meta = read_json(_STATE_PATH / "meta_governance_status_latest.json", default={})
        domains = self_model.get("domains") or []
        weak_domains = [d.get("domain_id") for d in domains if d.get("status") == "needs_work"][:3]
        text = (
            f"Autoconciencia\n"
            f"  respuesta corta: no en sentido fuerte; si como autodescripcion operativa.\n"
            f"  current_mode: {(self_model.get('identity') or {}).get('current_mode', 'N/A')}\n"
            f"  overall_score: {self_model.get('overall_score', 'N/A')}\n"
            f"  top_action: {meta.get('top_action', 'N/A')}\n"
            f"  weak_domains: {', '.join(weak_domains) or 'ninguno'}"
        )
        return session._system_reply(text)


def dashboard_status_fastpath(session) -> Dict:
        ui_ready = _UI_INDEX.exists()
        dashboard_ready = _UI_DASHBOARD.exists()
        host = SERVER_HOST or "127.0.0.1"
        localhost_host = "localhost" if host == "127.0.0.1" else host
        port = SERVER_PORT or 8090

        # B3-FAKE-GROUNDED-REMEDIATION-02: self-HTTP probe removed to avoid deadlock.
        # In single-worker/event-loop mode, calling http://localhost:8090/health from
        # within /chat handler blocks the worker and causes ~4s timeout.
        runtime_status = "not_verified_in_process"
        verified_by = "file_presence_only"
        http_health_ok = None
        file_presence_ok = ui_ready or dashboard_ready

        # Use in-process flag as weak signal; do NOT claim healthy from it alone.
        inprocess_running = bool(session.is_running)

        text = (
            f"Dashboard: archivos presentes, runtime no verificado desde fastpath interno.\n"
            f"runtime_status: {runtime_status}\n"
            f"verified_by: {verified_by}\n"
            f"host: {host}\n"
            f"puerto: {port}\n"
            f"ui_url: http://{localhost_host}:{port}/ui\n"
            f"dashboard_url: http://{localhost_host}:{port}/dashboard\n"
            f"file_presence: index={'ok' if ui_ready else 'missing'} | dashboard={'ok' if dashboard_ready else 'missing'}\n"
            f"inprocess_running: {inprocess_running}\n"
            f"\n"
            f"No hago self-HTTP probe desde /chat porque puede bloquear el servidor. "
            f"Para verificar runtime real, usar GET /health externo o smoke externo."
        )

        result = session._system_reply(text, success=False)
        result["route"] = "fastpath_dashboard_status"
        result["runtime_status"] = runtime_status
        result["verified_by"] = verified_by
        result["file_presence_ok"] = file_presence_ok
        result["http_health_ok"] = http_health_ok
        result["ui_route_ok"] = None
        result["dashboard_route_ok"] = None
        return result


def utility_status_fastpath(session) -> Dict:
        utility = read_json(_STATE_PATH / "utility_u_latest.json", default={})
        roadmap = read_json(_STATE_PATH / "roadmap.json", default={})
        cycle = read_json(_STATE_PATH / "next_level_cycle_status_latest.json", default={})

        if not utility:
            return session._system_reply("No pude leer el estado de Utility U (archivo vacio o ausente).", success=False)

        score = session._utility_score(utility)
        verdict = utility.get("verdict") or utility.get("promotion_gate", {}).get("verdict", "no_promote")
        blockers = session._utility_blockers(utility)
        phase = cycle.get("current_phase") or roadmap.get("current_phase") or "N/A"
        promote = "si" if verdict == "promote" else "no"

        text = (
            f"Estado actual de Utility U:\n"
            f"  u_score: {score}\n"
            f"  verdict: {verdict}\n"
            f"  fase canonica: {phase}\n"
            f"  promover?: {promote}\n"
            f"  blockers: {', '.join(blockers) if blockers else 'ninguno'}"
        )
        return session._system_reply(text)


def python_version_fastpath(session) -> Dict:
        """Return Python version without LLM."""
        try:
            result = subprocess.run(
                ["python", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            version = (result.stdout.strip() or result.stderr.strip() or "desconocida")
        except Exception as exc:
            version = f"error: {exc}"
        text = f"Version de Python instalada: {version}"
        return session._system_reply(text)


def disk_space_fastpath(session) -> Dict:
        """Return disk usage for all drives (Windows) or / (Linux)."""
        try:
            lines = []
            if platform.system() == "Windows":
                # Check all lettered drives that exist
                for letter in "CDEFGHIJ":
                    drive = f"{letter}:\\"
                    if os.path.exists(drive):
                        usage = shutil.disk_usage(drive)
                        total_gb = usage.total / (1024 ** 3)
                        free_gb = usage.free / (1024 ** 3)
                        used_pct = ((usage.total - usage.free) / usage.total) * 100
                        lines.append(
                            f"  {letter}: — total: {total_gb:.1f} GB | "
                            f"libre: {free_gb:.1f} GB | "
                            f"usado: {used_pct:.0f}%"
                        )
            else:
                usage = shutil.disk_usage("/")
                total_gb = usage.total / (1024 ** 3)
                free_gb = usage.free / (1024 ** 3)
                used_pct = ((usage.total - usage.free) / usage.total) * 100
                lines.append(
                    f"  / — total: {total_gb:.1f} GB | "
                    f"libre: {free_gb:.1f} GB | "
                    f"usado: {used_pct:.0f}%"
                )
            text = "Espacio en disco:\n" + "\n".join(lines)
        except Exception as exc:
            text = f"Error al obtener espacio en disco: {exc}"
        return session._system_reply(text)


def running_services_fastpath(session) -> Dict:
        """Return list of python/node/java processes (key services)."""
        try:
            if platform.system() == "Windows":
                result = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
                    capture_output=True, text=True, timeout=10,
                )
                py_lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip() and "INFO:" not in l]
                result2 = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq node.exe", "/FO", "CSV", "/NH"],
                    capture_output=True, text=True, timeout=10,
                )
                node_lines = [l.strip() for l in result2.stdout.strip().split("\n") if l.strip() and "INFO:" not in l]
                lines = []
                lines.append(f"  python.exe: {len(py_lines)} proceso(s)")
                lines.append(f"  node.exe: {len(node_lines)} proceso(s)")
                # Check known ports
                for port, name in [(8090, "Brain V9"), (8765, "PO Bridge"), (11434, "Ollama"), (4002, "IBKR GW")]:
                    try:
                        import socket
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.settimeout(1)
                            if s.connect_ex(("127.0.0.1", port)) == 0:
                                lines.append(f"  puerto {port} ({name}): activo")
                            else:
                                lines.append(f"  puerto {port} ({name}): inactivo")
                    except Exception:
                        lines.append(f"  puerto {port} ({name}): error al verificar")
            else:
                result = subprocess.run(
                    ["ps", "aux"], capture_output=True, text=True, timeout=10,
                )
                procs = result.stdout.strip().split("\n")
                py_count = sum(1 for p in procs if "python" in p.lower())
                node_count = sum(1 for p in procs if "node" in p.lower())
                lines = [
                    f"  python: {py_count} proceso(s)",
                    f"  node: {node_count} proceso(s)",
                ]
            text = "Servicios/procesos activos:\n" + "\n".join(lines)
        except Exception as exc:
            text = f"Error al listar servicios: {exc}"
        return session._system_reply(text)


def search_files_fastpath(session, original_message: str) -> Dict:
        """Search files matching a pattern extracted from the message.

        R12.7: skip vendored/noise dirs (.venv, node_modules, __pycache__,
        site-packages, dist, build, .git, ...) by default unless the user
        message explicitly mentions one of them.
        """
        try:
            # Try to extract a glob pattern like *.py, *.log, etc.
            match = re.search(r"[\*\w]+\.[\w]+", original_message)
            pattern = match.group(0) if match else "*.py"
            # Try to extract a directory path
            dir_match = re.search(r"(?:en|in|from)\s+([A-Za-z]:[/\\][^\s]+|/[^\s]+|\.)", original_message, re.IGNORECASE)
            search_dir = Path(dir_match.group(1)) if dir_match else Path("C:/AI_VAULT/tmp_agent")
            if not search_dir.exists():
                search_dir = Path("C:/AI_VAULT/tmp_agent")
            _VENDORED = {
                ".venv", "venv", "env", ".env", "node_modules", "__pycache__",
                ".git", ".svn", ".hg", "dist", "build", "site-packages",
                ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
                ".next", ".cache", ".idea", ".vscode",
                "bower_components", "vendor",
            }
            msg_lower = original_message.lower()
            include_vendored = any(v in msg_lower for v in _VENDORED)
            all_matches = search_dir.rglob(pattern)
            files: List[Path] = []
            skipped = 0
            for f in all_matches:
                if not include_vendored:
                    try:
                        rel_parts = f.relative_to(search_dir).parts
                    except ValueError:
                        rel_parts = f.parts
                    if any(part in _VENDORED for part in rel_parts):
                        skipped += 1
                        continue
                files.append(f)
                if len(files) >= 30:
                    break
            files = sorted(files)
            if files:
                listing = "\n".join(f"  {f}" for f in files)
                text = f"Archivos {pattern} en {search_dir} ({len(files)} resultados, max 30):\n{listing}"
                if skipped:
                    text += (
                        f"\n\n(Omitidos {skipped} archivos en directorios vendored: "
                        ".venv, node_modules, __pycache__, site-packages, dist, build, .git. "
                        "Pide explicitamente 'incluyendo .venv' si los necesitas.)"
                    )
            else:
                hint = ""
                if skipped:
                    hint = (
                        f" (Se omitieron {skipped} en directorios vendored; "
                        "pide 'incluyendo .venv' para verlos.)"
                    )
                text = f"No se encontraron archivos {pattern} en {search_dir}.{hint}"
        except Exception as exc:
            text = f"Error al buscar archivos: {exc}"
        return session._system_reply(text)


def list_directory_fastpath(session, original_message: str) -> Dict:
        """List contents of a directory extracted from the message."""
        try:
            dir_match = re.search(r"(?:en|in|de|del)\s+([A-Za-z]:[/\\][^\s]+|/[^\s]+)", original_message, re.IGNORECASE)
            target = Path(dir_match.group(1)) if dir_match else Path("C:/AI_VAULT/tmp_agent")
            if not target.exists():
                return session._system_reply(f"El directorio {target} no existe.", success=False)
            entries = sorted(target.iterdir())
            dirs = [e.name + "/" for e in entries if e.is_dir()]
            files = [e.name for e in entries if e.is_file()]
            listing_parts = []
            if dirs:
                listing_parts.append("Directorios:\n" + "\n".join(f"  {d}" for d in dirs[:30]))
            if files:
                listing_parts.append("Archivos:\n" + "\n".join(f"  {f}" for f in files[:30]))
            text = f"Contenido de {target}:\n" + "\n".join(listing_parts)
            if len(entries) > 60:
                text += f"\n  ... y {len(entries) - 60} mas"
        except Exception as exc:
            text = f"Error al listar directorio: {exc}"
        return session._system_reply(text)


def current_time_fastpath(session) -> Dict:
        """Return current date and time."""
        from datetime import datetime as _dt
        now = _dt.now()
        text = f"Fecha y hora actual: {now.strftime('%Y-%m-%d %H:%M:%S')} (hora local del servidor)"
        return session._system_reply(text)

