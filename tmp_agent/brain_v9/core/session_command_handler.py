"""
brain_v9.core.session_command_handler
====================================

B7-STRANGLER-07B: Command handlers extracted from BrainSession.
Functions receive session as duck-typed DI object.
No imports from brain_v9.core.session.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json
from brain_v9.core.session_memory_state import get_session_memory_latest

_STATE_PATH = BASE_PATH / "tmp_agent" / "state"

SLASH_COMMANDS = {
    "/help":   "Muestra los comandos disponibles.",
    "/status": "Estado del sistema Brain V9.",
    "/autonomy": "Estado del loop autónomo y acción prioritaria.",
    "/priority": "Resumen canónico de meta-gobernanza, foco y prioridades.",
    "/strategy": "Estado del strategy engine y candidatos actuales.",
    "/edge":   "Resumen canónico de edge validation.",
    "/ranking": "Resumen canónico de ranking-v2 y readiness real.",
    "/pipeline": "Integridad canónica del pipeline de trading y datos.",
    "/risk": "Estado canónico del contrato integral de riesgo.",
    "/governance": "Salud canónica de gobernanza, capas V3-V8 y mejoras.",
    "/posttrade": "Resumen canónico del análisis post-trade.",
    "/hypothesis": "Síntesis canónica de hallazgos e hipótesis post-trade.",
    "/security": "Resumen canónico de postura de seguridad y deuda crítica.",
    "/control": "Resumen canónico del control layer y scorecard de cambios.",
    "/freeze": "Activa el kill switch canónico del control layer.",
    "/unfreeze": "Libera el kill switch canónico del control layer.",
    "/trade":  "Último trade/job y contexto operativo.",
    "/memory": "Resumen canónico de memoria y contexto de la sesión.",
    "/diagnostic": "Resumen de salud y autodiagnóstico.",
    "/learning": "Estado del learning loop: decisiones por estrategia.",
    "/catalog": "Catálogo activo de estrategias operativas por venue.",
    "/context-edge": "Validación de edge por contexto (variant+symbol+timeframe).",
    "/dev":    "Activa/desactiva modo developer (/dev on | /dev off).",
    "/clear":  "Limpia la memoria de la sesión actual.",
    "/model":  "Muestra o cambia la prioridad de modelo (ej: /model agent).",
    "/mode":   "Cambia modo de ejecución (/mode plan | /mode build).",
    "/approve": "Aprueba una acción pendiente (/approve [id] o sin arg para la última).",
    "/reject": "Rechaza una acción pendiente (/reject <id>).",
    "/pending": "Muestra acciones pendientes de aprobación.",
    "/schedule": "Gestiona el scheduler proactivo (/schedule [on|off|list|run <id>|add|remove <id>]).",
}

__all__ = [
    "handle_command",
    "cmd_help",
    "cmd_status",
    "cmd_control",
    "cmd_freeze",
    "cmd_unfreeze",
    "cmd_dev",
    "cmd_clear",
    "cmd_model",
    "cmd_autonomy",
    "cmd_strategy",
    "cmd_edge",
    "cmd_ranking",
    "cmd_trade",
    "cmd_risk",
    "cmd_governance",
    "cmd_security",
    "cmd_diagnostic",
    "cmd_memory",
    "cmd_learning",
    "cmd_catalog",
    "cmd_context_edge",
    "cmd_mode",
    "cmd_approve",
    "cmd_reject",
    "cmd_pending",
]


async def handle_command(session, message: str) -> Dict:
        """Handle /slash commands. Returns result dict."""
        parts = message.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "/help":
            return cmd_help(session)
        elif cmd == "/status":
            return cmd_status(session)
        elif cmd == "/autonomy":
            return cmd_autonomy(session)
        elif cmd == "/priority":
            return session._cmd_priority()
        elif cmd == "/strategy":
            return cmd_strategy(session)
        elif cmd == "/edge":
            return cmd_edge(session)
        elif cmd == "/ranking":
            return cmd_ranking(session)
        elif cmd == "/pipeline":
            return session._cmd_pipeline()
        elif cmd == "/risk":
            return cmd_risk(session)
        elif cmd == "/governance":
            return cmd_governance(session)
        elif cmd == "/posttrade":
            return session._cmd_posttrade()
        elif cmd == "/hypothesis":
            return session._cmd_hypothesis()
        elif cmd == "/security":
            return cmd_security(session)
        elif cmd == "/control":
            return cmd_control(session)
        elif cmd == "/freeze":
            return cmd_freeze(session, arg)
        elif cmd == "/unfreeze":
            return cmd_unfreeze(session, arg)
        elif cmd == "/trade":
            return cmd_trade(session)
        elif cmd == "/memory":
            return cmd_memory(session)
        elif cmd == "/diagnostic":
            return cmd_diagnostic(session)
        elif cmd == "/dev":
            return cmd_dev(session, arg)
        elif cmd == "/clear":
            return cmd_clear(session)
        elif cmd == "/model":
            return cmd_model(session, arg)
        elif cmd == "/learning":
            return cmd_learning(session)
        elif cmd == "/catalog":
            return cmd_catalog(session)
        elif cmd == "/context-edge":
            return cmd_context_edge(session)
        elif cmd == "/mode":
            return cmd_mode(session, arg)
        elif cmd == "/approve":
            return await cmd_approve(session, arg)
        elif cmd == "/reject":
            return cmd_reject(session, arg)
        elif cmd == "/pending":
            return cmd_pending(session)
        elif cmd == "/schedule":
            return session._cmd_schedule(arg)
        else:
            text = f"Comando desconocido: {cmd}\nUsa /help para ver los disponibles."
            return session._system_reply(text, success=True)


def cmd_help(session) -> Dict:
        lines = ["Comandos disponibles:\n"]
        for cmd, desc in SLASH_COMMANDS.items():
            lines.append(f"  {cmd} — {desc}")
        return session._system_reply("\n".join(lines))


def cmd_status(session) -> Dict:
        """System status from real canonical state files."""
        utility = read_json(_STATE_PATH / "utility_u_latest.json", default={})
        cycle = read_json(_STATE_PATH / "next_level_cycle_status_latest.json", default={})
        roadmap = read_json(_STATE_PATH / "roadmap.json", default={})
        edge = read_json(_STATE_PATH / "strategy_engine" / "edge_validation_latest.json", default={})

        u_score = session._utility_score(utility)
        verdict = utility.get("verdict") or utility.get("promotion_gate", {}).get("verdict", "N/A")
        phase = cycle.get("current_phase") or roadmap.get("current_phase") or "N/A"
        blockers = session._utility_blockers(utility)
        edge_summary = edge.get("summary") or {}
        validated = edge_summary.get("validated_count", 0)
        probation = edge_summary.get("probation_count", 0)

        text = (
            f"Estado Brain V9\n"
            f"  Utility: U={u_score}, veredicto: {verdict}\n"
            f"  Fase actual: {phase}\n"
            f"  Edge: {validated} validados, {probation} en probacion\n"
            f"  Blockers: {', '.join(blockers) if blockers else 'ninguno'}"
        )
        return session._system_reply(text)


def cmd_control(session) -> Dict:
        scorecard = read_json(_STATE_PATH / "change_scorecard.json", default={})
        control = read_json(_STATE_PATH / "control_layer_status.json", default={})
        summary = scorecard.get("summary") or {}
        entries = scorecard.get("entries") or []
        latest = entries[-1] if entries else {}
        latest_id = latest.get("change_id", "N/A")
        latest_result = latest.get("result", "N/A")
        mode = control.get("mode", "ACTIVE")
        reason = control.get("reason", "N/A")
        promoted = summary.get('promoted_count', 0)
        reverted = summary.get('reverted_count', 0)
        pending = summary.get('pending_count', 0)
        rollbacks = summary.get('rollback_count', 0)
        degraded = summary.get('metric_degraded_count', 0)
        frozen_rec = summary.get('frozen_recommended', False)
        text = (
            f"Control de Cambios\n\n"
            f"Modo: {mode} — Razon: {reason}\n"
            f"Total de cambios: {summary.get('total_changes', 0)}\n"
            f"Promovidos: {promoted} | Revertidos: {reverted} | Pendientes: {pending}\n"
            f"Rollbacks: {rollbacks} | Degradacion de metricas: {degraded}\n"
            f"{'Se recomienda congelar el sistema' if frozen_rec else 'No se recomienda congelar'}\n"
            f"Ultimo cambio: {latest_id} ({latest_result})"
        )
        return session._system_reply(text)


def cmd_freeze(session, arg: str) -> Dict:
        reason = arg or "manual_freeze"
        from brain_v9.brain.control_layer import freeze_control_layer

        payload = freeze_control_layer(reason=reason, source=f"chat:{session.session_id}")
        return session._system_reply(
            f"Control layer congelado.\n"
            f"Modo: {payload.get('mode', 'N/A')}\n"
            f"Razon: {payload.get('reason', reason)}"
        )


def cmd_unfreeze(session, arg: str) -> Dict:
        reason = arg or "manual_unfreeze"
        from brain_v9.brain.control_layer import unfreeze_control_layer

        payload = unfreeze_control_layer(reason=reason, source=f"chat:{session.session_id}")
        return session._system_reply(
            f"Control layer liberado.\n"
            f"Modo: {payload.get('mode', 'N/A')}\n"
            f"Razon: {payload.get('reason', reason)}"
        )


def cmd_dev(session, arg: str) -> Dict:
        if arg.lower() == "on":
            session.dev_mode = True
            persisted = session._persist_chat_dev_mode_default(True)
            suffix = " Persistido por defecto para nuevas sesiones." if persisted else " No pude persistir el default."
            return session._system_reply("Developer mode activado. Cada respuesta incluira metadatos de routing." + suffix)
        elif arg.lower() == "off":
            session.dev_mode = False
            persisted = session._persist_chat_dev_mode_default(False)
            suffix = " Persistido por defecto para nuevas sesiones." if persisted else " No pude persistir el default."
            return session._system_reply("Developer mode desactivado." + suffix)
        else:
            estado = "activado" if session.dev_mode else "desactivado"
            persisted_default = session._load_chat_dev_mode_default()
            persisted_state = "activado" if persisted_default else "desactivado"
            return session._system_reply(
                f"Developer mode esta {estado}.\nDefault persistido: {persisted_state}.\nUsa /dev on o /dev off."
            )


def cmd_clear(session) -> Dict:
        session.memory.clear("all")
        return session._system_reply("Memoria limpiada (short + long term).")


def cmd_model(session, arg: str) -> Dict:
        if arg:
            valid = {"ollama", "agent", "code", "chat", "gpt4", "claude", "offline", "codex", "analysis_frontier", "analysis_frontier_legacy", "agent_legacy", "code_legacy", "chat_legacy", "agent_frontier_legacy"}
            if arg.lower() in valid:
                session._model_priority = arg.lower()
                return session._system_reply(f"Modelo cambiado a {session._model_priority}")
            else:
                return session._system_reply(f"Modelo invalido. Opciones: {', '.join(sorted(valid))}")
        return session._system_reply(f"Modelo actual: {session._model_priority}")


def cmd_autonomy(session) -> Dict:
        next_actions = read_json(_STATE_PATH / "autonomy_next_actions.json", default={})
        utility = read_json(_STATE_PATH / "utility_u_latest.json", default={})
        meta = read_json(_STATE_PATH / "meta_improvement_status_latest.json", default={})
        meta_governance = read_json(_STATE_PATH / "meta_governance_status_latest.json", default={})
        top_gap = meta.get("top_gap") or {}
        blockers = next_actions.get("blockers") or session._utility_blockers(utility)
        next_recommended = next_actions.get("recommended_actions") or (utility.get("promotion_gate") or {}).get("required_next_actions", [])
        focus = (meta_governance.get("current_focus") or {}).get("action", "N/A")
        text = (
            f"Autonomia\n"
            f"  Accion prioritaria: {next_actions.get('top_action', 'N/A')}\n"
            f"  Foco actual: {focus}\n"
            f"  Utility: U={next_actions.get('u_score', session._utility_score(utility))} — veredicto: {next_actions.get('verdict', utility.get('verdict', 'N/A'))}\n"
            f"  Blockers: {', '.join(blockers) or 'ninguno'}\n"
            f"  Proximas acciones: {', '.join(next_recommended) or 'ninguna'}\n"
            f"  Gap principal: {top_gap.get('gap_id', 'N/A')} ({top_gap.get('domain_id', 'N/A')})"
        )
        return session._system_reply(text)


def cmd_strategy(session) -> Dict:
        ranking = read_json(_STATE_PATH / "strategy_engine" / "strategy_ranking_v2_latest.json", default={})
        edge = read_json(_STATE_PATH / "strategy_engine" / "edge_validation_latest.json", default={})
        signals = read_json(_STATE_PATH / "strategy_engine" / "strategy_signal_snapshot_latest.json", default={})
        top = ranking.get("top_strategy") or {}
        exploit = ranking.get("exploit_candidate") or top or {}
        explore = ranking.get("explore_candidate") or {}
        probation = ranking.get("probation_candidate") or edge.get("summary", {}).get("best_probation") or {}
        ready_signals = sum(1 for item in (signals.get("items") or []) if item.get("execution_ready_now"))
        validated_ready = edge.get("summary", {}).get("validated_ready_count", 0)
        probation_ready = edge.get("summary", {}).get("probation_ready_count", 0)
        text = (
            f"Motor de Estrategias\n\n"
            f"Accion top: {ranking.get('top_action', 'N/A')}\n"
            f"Exploit: {exploit.get('strategy_id', 'N/A')} — Listo: {'si' if exploit.get('execution_ready_now') else 'no'} — Edge: {exploit.get('edge_state', 'N/A')}\n"
            f"Explore: {explore.get('strategy_id', 'N/A')} — Listo: {'si' if explore.get('execution_ready_now') else 'no'} — Edge: {explore.get('edge_state', 'N/A')}\n"
            f"Probation: {probation.get('strategy_id', 'N/A')} — Lane: {probation.get('execution_lane', 'N/A')}\n"
            f"Top ranking: {top.get('strategy_id', 'N/A')}\n"
            f"Senales listas: {ready_signals} | Validadas: {validated_ready} | En probation: {probation_ready}"
        )
        return session._system_reply(text)


def cmd_edge(session) -> Dict:
        edge = read_json(_STATE_PATH / "strategy_engine" / "edge_validation_latest.json", default={})
        summary = edge.get("summary") or {}
        top_exec = summary.get("top_execution_edge") or {}
        best_prob = summary.get("best_probation") or {}
        text = (
            f"Validacion de Edge\n\n"
            f"Promotables: {summary.get('promotable_count', 0)}\n"
            f"Validadas: {summary.get('validated_count', 0)}\n"
            f"En forward validation: {summary.get('forward_validation_count', 0)}\n"
            f"En probation: {summary.get('probation_count', 0)}\n"
            f"Bloqueadas: {summary.get('blocked_count', 0)}\n"
            f"Refutadas: {summary.get('refuted_count', 0)}\n"
            f"Top para ejecucion: {top_exec.get('strategy_id', 'N/A')} — Listo: {'si' if top_exec.get('execution_ready_now') else 'no'}\n"
            f"Mejor en probation: {best_prob.get('strategy_id', 'N/A')}"
        )
        return session._system_reply(text)


def cmd_ranking(session) -> Dict:
        ranking = read_json(_STATE_PATH / "strategy_engine" / "strategy_ranking_v2_latest.json", default={})
        edge = read_json(_STATE_PATH / "strategy_engine" / "edge_validation_latest.json", default={})
        ranked = ranking.get("ranked") or []
        top = ranking.get("top_strategy") or {}
        first = ranked[0] if ranked else {}
        probation = ranking.get("probation_candidate") or (edge.get("summary") or {}).get("best_probation") or {}
        text = (
            f"Ranking V2\n\n"
            f"Accion top: {ranking.get('top_action', 'N/A')}\n"
            f"Top strategy: {top.get('strategy_id', 'N/A')}\n"
            f"Primera en ranking: {first.get('strategy_id', 'N/A')} — Edge: {first.get('edge_state', 'N/A')} — Lista: {'si' if first.get('execution_ready_now') else 'no'}\n"
            f"Exploit: {(ranking.get('exploit_candidate') or {}).get('strategy_id', 'N/A')}\n"
            f"Explore: {(ranking.get('explore_candidate') or {}).get('strategy_id', 'N/A')}\n"
            f"Probation: {probation.get('strategy_id', 'N/A')}"
        )
        return session._system_reply(text)


def cmd_trade(session) -> Dict:
        ledger = read_json(_STATE_PATH / "autonomy_action_ledger.json", default={"entries": []})
        ranking = read_json(_STATE_PATH / "strategy_engine" / "strategy_ranking_v2_latest.json", default={})
        latest = (ledger.get("entries") or [])[-1] if (ledger.get("entries") or []) else {}
        exploit = ranking.get("exploit_candidate") or ranking.get("top_strategy") or {}
        text = (
            f"Trade / Loop\n\n"
            f"Ultima accion: {latest.get('action_name', 'N/A')}\n"
            f"Estado: {latest.get('status', 'N/A')}\n"
            f"Estrategia: {latest.get('strategy_tag', 'N/A')}\n"
            f"Simbolo: {latest.get('preferred_symbol', latest.get('symbol', 'N/A'))}\n"
            f"Exploit actual: {exploit.get('strategy_id', 'N/A')} — "
            f"Simbolo: {exploit.get('preferred_symbol', 'N/A')} — "
            f"Timeframe: {exploit.get('preferred_timeframe', 'N/A')}"
        )
        return session._system_reply(text)


def cmd_risk(session) -> Dict:
        payload = read_json(_STATE_PATH / "risk" / "risk_contract_status_latest.json", default={})
        if not payload:
            from brain_v9.brain.risk_contract import read_risk_contract_status
            payload = read_risk_contract_status()
        limits = payload.get("limits") or {}
        measures = payload.get("measures") or {}
        control = payload.get("control_layer") or {}
        utility = payload.get("utility") or {}
        exec_allowed = "si" if payload.get('execution_allowed', False) else "no"
        paper = "si" if payload.get('paper_only', False) else "no"
        text = (
            f"Contrato de Riesgo\n\n"
            f"Estado: {payload.get('status', 'desconocido')} — Ejecucion permitida: {exec_allowed} — Solo paper: {paper}\n\n"
            f"Medidas vs Limites\n"
            f"  Perdida diaria: {measures.get('daily_loss_frac', 'N/A')} / {limits.get('max_daily_loss_frac', 'N/A')}\n"
            f"  Drawdown semanal: {measures.get('weekly_drawdown_frac', 'N/A')} / {limits.get('max_weekly_drawdown_frac', 'N/A')}\n"
            f"  Exposicion total: {measures.get('total_exposure_frac', 'N/A')} / {limits.get('max_total_exposure_frac', 'N/A')}\n\n"
            f"Capital\n"
            f"  Cash actual: {measures.get('current_cash', 'N/A')} | Comprometido: {measures.get('committed_cash', 'N/A')} | Base: {measures.get('base_capital', 'N/A')}\n\n"
            f"Control layer: {control.get('mode', 'N/A')} — {control.get('reason', 'N/A')}\n"
            f"Utility: U={utility.get('u_score', 'N/A')} — Veredicto: {utility.get('verdict', 'N/A')}\n"
            f"Violaciones hard: {', '.join(payload.get('hard_violations', [])) or 'ninguna'}\n"
            f"Advertencias: {', '.join(payload.get('warnings', [])) or 'ninguna'}"
        )
        return session._system_reply(text)


def cmd_governance(session) -> Dict:
        payload = read_json(_STATE_PATH / "governance_health_latest.json", default={})
        if not payload:
            from brain_v9.governance.governance_health import read_governance_health
            payload = read_governance_health()
        layers = payload.get("layers") or {}
        layer_bits = []
        for layer_id in ["V3", "V4", "V5", "V6", "V7", "V8"]:
            layer = layers.get(layer_id) or {}
            state = layer.get('state', 'desconocido')
            layer_bits.append(f"  {layer_id}: {state}")
        change_validation = payload.get("change_validation") or {}
        improvement_summary = payload.get("improvement_summary") or {}
        kill_switch = payload.get("kill_switch") or {}
        text = (
            f"Salud de Gobernanza\n\n"
            f"Estado general: {payload.get('overall_status', 'desconocido')} — Modo: {payload.get('current_operating_mode', 'desconocido')}\n\n"
            f"Capas\n"
            + "\n".join(layer_bits) + "\n\n"
            f"Ultima validacion de cambios: {change_validation.get('last_run_utc', 'N/A')} — Estado: {change_validation.get('last_pipeline_state', 'pendiente')}\n"
            f"Rollbacks ultimos 7 dias: {payload.get('rollbacks_last_7d', 0)}\n"
            f"Kill switch: {kill_switch.get('mode', 'desconocido')}\n"
            f"Mejoras: {improvement_summary.get('implemented_count', 0)} implementadas | "
            f"{improvement_summary.get('partial_count', 0)} parciales | "
            f"{improvement_summary.get('pending_count', 0)} pendientes"
        )
        return session._system_reply(text)


def cmd_security(session) -> Dict:
        posture = read_json(_STATE_PATH / "security" / "security_posture_latest.json", default={})
        if not posture:
            from brain_v9.brain.security_posture import get_security_posture_latest
            posture = get_security_posture_latest()
        env_runtime = posture.get("env_runtime") or {}
        secrets = posture.get("secrets_audit") or {}
        triage = posture.get("secrets_triage") or {}
        source_audit = posture.get("secret_source_audit") or {}
        legacy_secret_files = posture.get("legacy_secret_files") or {}
        legacy = posture.get("legacy_runtime_refs") or {}
        deps = posture.get("dependency_audit") or {}
        dotenv_ok = "si" if env_runtime.get('dotenv_exists', False) else "no"
        gitignore_env = "si" if env_runtime.get('gitignore_protects_dotenv', False) else "no"
        gitignore_secrets = "si" if env_runtime.get('gitignore_protects_secrets', False) else "no"
        text = (
            f"Postura de Seguridad\n\n"
            f"Entorno\n"
            f"  .env existe: {dotenv_ok} | .env.example: {'si' if env_runtime.get('dotenv_example_exists', False) else 'no'}\n"
            f"  Gitignore protege .env: {gitignore_env} | Protege secrets: {gitignore_secrets}\n\n"
            f"Secretos\n"
            f"  Hallazgos raw: {secrets.get('raw_finding_count', 0)} | Sin clasificar: {secrets.get('unclassified_count', 0)}\n"
            f"  Candidatos accionables: {triage.get('actionable_candidate_count', 0)} | Actuales: {triage.get('current_actionable_candidate_count', 0)} | Stale: {triage.get('stale_actionable_candidate_count', 0)}\n"
            f"  Falsos positivos probables: {triage.get('likely_false_positive_count', 0)}\n"
            f"  Fuentes duplicadas: {source_audit.get('duplicate_source_count', 0)} | Mismatches: {source_audit.get('mismatch_count', 0)}\n"
            f"  Fallbacks JSON mapeados: {legacy_secret_files.get('mapped_json_fallback_count', 0)} | Archivos sueltos: {legacy_secret_files.get('loose_secret_file_count', 0)}\n"
            f"  Refs legacy env.bat: {legacy.get('env_bat_reference_count', 0)}\n\n"
            f"Dependencias\n"
            f"  Vulnerabilidades: {deps.get('vulnerability_count', 0)} | Parcheables: {deps.get('patchable_vulnerability_count', 0)}\n"
            f"  Bloqueadas por upstream: {deps.get('upstream_blocked_vulnerability_count', 0)} | Paquetes afectados: {deps.get('affected_package_count', 0)}"
        )
        return session._system_reply(text)


def cmd_diagnostic(session) -> Dict:
        utility = read_json(_STATE_PATH / "utility_u_latest.json", default={})
        diag = read_json(_STATE_PATH / "self_diagnostic_status_latest.json", default={})
        roadmap = read_json(_STATE_PATH / "roadmap.json", default={})
        text = (
            f"Diagnostico\n\n"
            f"Roadmap: {roadmap.get('current_phase', 'N/A')} / {roadmap.get('current_stage', 'N/A')}\n"
            f"Veredicto utility: {utility.get('verdict', 'N/A')}\n"
            f"Blockers utility: {', '.join(session._utility_blockers(utility)) or 'ninguno'}\n"
            f"Auto-diagnostico: {diag.get('status', diag.get('overall_status', 'N/A'))}"
        )
        return session._system_reply(text)


def cmd_memory(session) -> Dict:
        memory = get_session_memory_latest(session.session_id)
        important = memory.get("important_vars") or {}
        open_risks = memory.get("open_risks") or []
        text = (
            f"Memoria de Sesion\n\n"
            f"Session ID: {memory.get('session_id', session.session_id)}\n"
            f"Objetivo: {memory.get('objective', 'N/A')}\n"
            f"Foco actual: {important.get('current_focus', 'N/A')} | Accion top: {important.get('top_action', 'N/A')}\n"
            f"Mensajes: {important.get('message_count', 0)} | Intercambios recientes: {important.get('recent_exchange_count', 0)}\n"
            f"Archivos clave: {len(memory.get('key_files') or [])} | Decisiones: {len(memory.get('decisions') or [])}\n"
            f"Riesgos abiertos: {', '.join(open_risks) if open_risks else 'ninguno'}"
        )
        return session._system_reply(text)


def cmd_learning(session) -> Dict:
        """Learning loop: per-strategy learning decisions from canonical artifacts."""
        ll = read_json(_STATE_PATH / "strategy_engine" / "learning_loop_latest.json", default={})
        if not ll:
            return session._system_reply("No hay snapshot del learning loop disponible.", success=False)
        s = ll.get("summary", {})
        items = ll.get("items", [])
        operational = [i for i in items if i.get("catalog_state") in ("active", "probation")]
        variant_candidates = [i for i in items if i.get("allow_variant_generation")]
        lines = [
            "Learning Loop\n",
            f"Accion top: {s.get('top_learning_action', 'N/A')}",
            f"Operacionales: {s.get('operational_count', 0)} | En auditoria: {s.get('audit_count', 0)} | Probation continua: {s.get('probation_continue_count', 0)}",
            f"Forward validation: {s.get('forward_validation_count', 0)} | Candidatos a variante: {s.get('variant_generation_candidate_count', 0)}",
            f"Generacion de variantes permitida: {'si' if s.get('allow_variant_generation', False) else 'no'}",
        ]
        if variant_candidates:
            lines.append(f"Fuentes de variantes: {', '.join(i.get('strategy_id', '?') for i in variant_candidates)}")
        for item in operational:
            lines.append(
                f"  - {item.get('strategy_id')} [{item.get('catalog_state')}] -> "
                f"{item.get('learning_decision')} ({item.get('rationale')}) "
                f"entradas={item.get('entries_resolved')} expectancy={item.get('expectancy')}"
            )
        return session._system_reply("\n".join(lines))


def cmd_catalog(session) -> Dict:
        """Active strategy catalog: operational strategies by venue."""
        cat = read_json(_STATE_PATH / "strategy_engine" / "active_strategy_catalog_latest.json", default={})
        if not cat:
            return session._system_reply("No hay catalogo activo disponible.", success=False)
        items = cat.get("items", [])
        s = cat.get("summary", {})
        lines = [
            "Catalogo de Estrategias Activas\n",
            f"Total: {s.get('total', len(items))} | Operacionales: {s.get('operational', 0)} | Excluidas: {s.get('excluded', 0)}",
        ]
        for item in items:
            state = item.get("catalog_state", "?")
            marker = "+" if state in ("active", "probation") else "-"
            lines.append(
                f"  {marker} {item.get('strategy_id')} [{state}] "
                f"venue={item.get('venue', '?')} entradas={item.get('entries_resolved', 0)} "
                f"expectancy={item.get('expectancy', 'N/A')}"
            )
        return session._system_reply("\n".join(lines))


def cmd_context_edge(session) -> Dict:
        """Context edge validation: edge state per setup_variant+symbol+timeframe."""
        ce = read_json(_STATE_PATH / "strategy_engine" / "context_edge_validation_latest.json", default={})
        if not ce:
            return session._system_reply("No hay snapshot de context edge validation.", success=False)
        s = ce.get("summary", {})
        contexts = ce.get("contexts", [])
        lines = [
            "Validacion de Edge por Contexto\n",
            f"Total contextos: {s.get('total_contexts', 0)} | Validados: {s.get('validated', 0)} | Contradecidos: {s.get('contradicted', 0)}",
            f"Sin probar: {s.get('unproven', 0)} | Datos insuficientes: {s.get('insufficient', 0)}",
        ]
        for ctx in contexts[:10]:
            lines.append(
                f"  - {ctx.get('strategy_id')} {ctx.get('symbol','?')}|{ctx.get('setup_variant','?')}|{ctx.get('timeframe','?')} "
                f"-> {ctx.get('context_edge_state','?')} "
                f"entradas={ctx.get('entries_resolved',0)} expectancy={ctx.get('expectancy','N/A')}"
            )
        if len(contexts) > 10:
            lines.append(f"  ... y {len(contexts) - 10} contextos mas")
        return session._system_reply("\n".join(lines))


def cmd_mode(session, arg: str) -> Dict:
        """Set execution gate mode: plan or build."""
        from brain_v9.governance.execution_gate import get_gate
        gate = get_gate()
        if not arg:
            status = gate.get_status()
            return session._system_reply(
                f"Modo actual: {status['mode'].upper()}\n"
                f"Acciones pendientes: {status['pending_count']}"
            )
        result = gate.set_mode(arg.lower())
        if result.get("success"):
            return session._system_reply(
                f"Modo cambiado: {result['previous'].upper()} -> {result['mode'].upper()}"
            )
        return session._system_reply(result.get("error", "Error cambiando modo"), success=False)


async def cmd_approve(session, arg: str) -> Dict:
        """Approve a pending gated action and execute it."""
        from brain_v9.governance.execution_gate import get_gate
        gate = get_gate()
        if arg:
            item = gate.approve(arg.strip())
        else:
            item = gate.approve_latest(session.session_id)
        if not item:
            return session._system_reply("No hay accion pendiente para aprobar.", success=False)
        # Execute the approved action
        tool_name = item.get("tool", "?")
        tool_args = item.get("args", {})
        risk = item.get("risk", "?")
        text = f"Aprobado: {tool_name} ({risk})\n"
        try:
            if session._executor is None:
                from brain_v9.agent.tools import build_standard_executor
                session._executor = build_standard_executor()
            fn = session._executor._tools.get(tool_name, {}).get("func")
            if fn is None:
                return session._system_reply(f"Tool '{tool_name}' no encontrada en executor.", success=False)
            # Bypass gate for approved execution — call fn directly with _bypass_gate
            bypass_args = {**tool_args, "_bypass_gate": True}
            import asyncio as _aio
            if _aio.iscoroutinefunction(fn):
                result = await fn(**bypass_args)
            else:
                result = fn(**bypass_args)
            text += f"Resultado: {str(result)[:500]}"
            return session._system_reply(text)
        except Exception as exc:
            text += f"Error ejecutando: {exc}"
            return session._system_reply(text, success=False)


def cmd_reject(session, arg: str) -> Dict:
        """Reject a pending gated action."""
        from brain_v9.governance.execution_gate import get_gate
        gate = get_gate()
        if not arg:
            return session._system_reply("Uso: /reject <pending_id>", success=False)
        ok = gate.reject(arg.strip())
        if ok:
            return session._system_reply(f"Accion rechazada: {arg.strip()}")
        return session._system_reply(f"No se encontro accion pendiente: {arg.strip()}", success=False)


def cmd_pending(session) -> Dict:
        """Show pending gated actions."""
        from brain_v9.governance.execution_gate import get_gate
        gate = get_gate()
        pending = gate.get_pending()
        if not pending:
            status = gate.get_status()
            return session._system_reply(
                f"No hay acciones pendientes. Modo: {status['mode'].upper()}"
            )
        lines = [f"Acciones pendientes ({len(pending)}):\n"]
        for p in pending:
            lines.append(
                f"  [{p['risk']}] {p['tool']}  id={p['id']}\n"
                f"       args={str(p.get('args', {}))[:120]}\n"
                f"       {p.get('reason', '')}"
            )
        lines.append(f"\nUsa /approve <id> o /approve (sin arg = ultima).")
        return session._system_reply("\n".join(lines))

