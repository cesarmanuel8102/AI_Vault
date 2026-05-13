"""
Brain V9 - Chat product governance
Sintetiza y mantiene el estado canónico del producto chat para que el Brain
pueda evaluarlo y mejorarlo sin depender de criterio externo ad hoc.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json, read_text as _state_read_text

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
ROOMS_PATH = STATE_PATH / "rooms"
CHAT_ROOM = ROOMS_PATH / "brain_chat_product_cp01_contract"

FILES = {
    "dashboard_ui": BASE_PATH / "00_identity" / "autonomy_system" / "unified_dashboard.html",
    "dashboard_server": BASE_PATH / "00_identity" / "autonomy_system" / "dashboard_server.py",
    "brain_ui": BASE_PATH / "tmp_agent" / "brain_v9" / "ui" / "index.html",
    "main": BASE_PATH / "tmp_agent" / "brain_v9" / "main.py",
    "session": BASE_PATH / "tmp_agent" / "brain_v9" / "core" / "session.py",
    "memory": BASE_PATH / "tmp_agent" / "brain_v9" / "core" / "memory.py",
    "chat_status": STATE_PATH / "chat_product_status_latest.json",
    "chat_spec": STATE_PATH / "chat_product_acceptance_spec.json",
    "chat_roadmap": STATE_PATH / "chat_product_roadmap.json",
    "chat_telemetry": STATE_PATH / "chat_product_telemetry_latest.json",
    "chat_metrics_runtime": STATE_PATH / "brain_metrics" / "chat_metrics_latest.json",
    "self_test_latest": STATE_PATH / "brain_metrics" / "self_test_latest.json",
    "chat_contract": CHAT_ROOM / "chat_product_contract.json",
    "chat_activation": CHAT_ROOM / "chat_product_activation.json",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

log = logging.getLogger("chat_product_governance")


def _read_text(path: Path) -> str:
    return _state_read_text(path, "")


def _bool_check(check_id: str, passed: bool, detail: str, repair_hint: str) -> Dict[str, Any]:
    return {
        "check_id": check_id,
        "passed": bool(passed),
        "detail": detail,
        "repair_hint": repair_hint,
    }


def _build_chat_spec() -> Dict[str, Any]:
    return {
        "schema_version": "chat_product_acceptance_spec_v2",
        "updated_utc": _utc_now(),
        "product_id": "brain_chat_v9_product",
        "title": "Brain Chat V9 product governance",
        "mission": "mantener un chat usable, visible, gobernable y mejorable por el propio Brain.",
        "acceptance_mode": "all_checks_must_pass",
        "baseline_checks": [
            {
                "id": "dashboard_has_chat_link",
                "kind": "html_contains",
                "source": str(FILES["dashboard_ui"]),
                "pattern": 'href="/chat"',
                "description": "El dashboard debe exponer un acceso directo al chat operativo.",
            },
            {
                "id": "brain_ui_exists",
                "kind": "file_exists",
                "source": str(FILES["brain_ui"]),
                "description": "La UI del chat debe existir como artefacto local del Brain.",
            },
            {
                "id": "main_exposes_chat_route",
                "kind": "py_contains",
                "source": str(FILES["main"]),
                "pattern": '@app.post("/chat"',
                "description": "El runtime debe exponer el endpoint /chat.",
            },
            {
                "id": "main_exposes_chat_product_status",
                "kind": "py_contains",
                "source": str(FILES["main"]),
                "pattern": '/brain/chat-product/status',
                "description": "El runtime debe exponer el estado canónico del producto chat.",
            },
        ],
        "quality_checks": [
            {
                "id": "ui_has_status_panel",
                "kind": "html_contains",
                "source": str(FILES["brain_ui"]),
                "pattern": 'id="panel-status"',
                "description": "La UI del chat debe exponer panel de estado.",
            },
            {
                "id": "ui_has_model_selector",
                "kind": "html_contains",
                "source": str(FILES["brain_ui"]),
                "pattern": 'id="model-select"',
                "description": "La UI debe permitir elegir modelo/route de forma explícita.",
            },
            {
                "id": "session_uses_memory_manager",
                "kind": "py_contains",
                "source": str(FILES["session"]),
                "pattern": "MemoryManager",
                "description": "La sesión del chat debe usar MemoryManager.",
            },
            {
                "id": "session_normalizes_response",
                "kind": "py_contains",
                "source": str(FILES["session"]),
                "pattern": "_normalize(",
                "description": "La sesión debe normalizar response/content para continuidad de UX.",
            },
            {
                "id": "memory_persists_short_and_long_term",
                "kind": "py_contains",
                "source": str(FILES["memory"]),
                "pattern": "_save_long_term",
                "description": "La memoria del chat debe persistir corto y largo plazo.",
            },
            {
                "id": "main_exposes_chat_product_refresh",
                "kind": "py_contains",
                "source": str(FILES["main"]),
                "pattern": '/brain/chat-product/refresh',
                "description": "El runtime debe permitir refrescar el estado del producto chat.",
            },
        ],
        "roadmap_projection": [
            {
                "item_id": "CP-01",
                "title": "Formalizar estado, spec y roadmap del chat",
                "status": "active",
            },
            {
                "item_id": "CP-02",
                "title": "Mejorar claridad conversacional y continuidad de contexto",
                "status": "queued",
            },
            {
                "item_id": "CP-03",
                "title": "Agregar medición de calidad UX y handoff operatorio",
                "status": "queued",
            },
        ],
    }


def refresh_chat_product_status() -> Dict[str, Any]:
    dashboard_ui = _read_text(FILES["dashboard_ui"])
    main_py = _read_text(FILES["main"])
    session_py = _read_text(FILES["session"])
    memory_py = _read_text(FILES["memory"])
    brain_ui = _read_text(FILES["brain_ui"])
    runtime_metrics = read_json(FILES["chat_metrics_runtime"], {}) or {}
    self_test_latest = read_json(FILES["self_test_latest"], {}) or {}
    runtime_latency_ms = float(runtime_metrics.get("avg_latency_ms") or 0.0) if runtime_metrics else 0.0
    self_test_latency_ms = float(self_test_latest.get("avg_latency_ms") or 0.0) if self_test_latest else 0.0
    effective_latency_ms = 0.0
    if runtime_latency_ms and self_test_latency_ms:
        effective_latency_ms = min(runtime_latency_ms, self_test_latency_ms)
    else:
        effective_latency_ms = runtime_latency_ms or self_test_latency_ms
    episodic_stats = {}
    try:
        from brain_v9.core.knowledge import EpisodicMemory
        episodic_stats = EpisodicMemory().get_stats()
    except Exception:
        episodic_stats = {}
    chat_ui_exists = FILES["brain_ui"].exists()
    spec = _build_chat_spec()

    baseline_checks: List[Dict[str, Any]] = [
        _bool_check(
            "dashboard_has_chat_link",
            'href="/chat"' in dashboard_ui,
            "El dashboard ya enlaza al chat operativo." if 'href="/chat"' in dashboard_ui else "No se encontró enlace directo al chat en el dashboard.",
            "Añadir o reparar href=\"/chat\" en el dashboard principal.",
        ),
        _bool_check(
            "brain_ui_exists",
            chat_ui_exists,
            f"UI del chat encontrada en {FILES['brain_ui']}" if chat_ui_exists else "No existe la UI local del chat.",
            "Crear o restaurar la UI del chat en tmp_agent/brain_v9/ui/index.html.",
        ),
        _bool_check(
            "main_exposes_chat_route",
            '@app.post("/chat"' in main_py,
            "El runtime expone POST /chat." if '@app.post("/chat"' in main_py else "No se encontró POST /chat en main.py.",
            "Exponer el endpoint /chat en el runtime principal.",
        ),
        _bool_check(
            "main_exposes_chat_product_status",
            '/brain/chat-product/status' in main_py,
            "El runtime expone /brain/chat-product/status." if '/brain/chat-product/status' in main_py else "Aún no existe endpoint de estado del producto chat.",
            "Agregar endpoint canónico /brain/chat-product/status.",
        ),
    ]
    quality_checks: List[Dict[str, Any]] = [
        _bool_check(
            "ui_has_status_panel",
            'id="panel-status"' in brain_ui,
            "La UI del chat ya expone panel de estado." if 'id="panel-status"' in brain_ui else "La UI del chat no expone panel de estado.",
            "Añadir panel de estado visible en la UI del chat.",
        ),
        _bool_check(
            "ui_has_model_selector",
            'id="model-select"' in brain_ui,
            "La UI del chat permite seleccionar modelo." if 'id="model-select"' in brain_ui else "La UI del chat no expone selector de modelo.",
            "Agregar selector explícito de modelo/route en la UI.",
        ),
        _bool_check(
            "session_uses_memory_manager",
            "MemoryManager" in session_py,
            "La sesión del chat usa MemoryManager." if "MemoryManager" in session_py else "La sesión del chat no usa MemoryManager.",
            "Conectar BrainSession con MemoryManager.",
        ),
        _bool_check(
            "session_normalizes_response",
            "_normalize(" in session_py,
            "La sesión normaliza response/content." if "_normalize(" in session_py else "La sesión no normaliza response/content.",
            "Normalizar response/content para continuidad de UX.",
        ),
        _bool_check(
            "memory_persists_short_and_long_term",
            "_save_long_term" in memory_py and "_save_short_term" in memory_py,
            "La memoria persiste corto y largo plazo." if "_save_long_term" in memory_py and "_save_short_term" in memory_py else "La memoria aún no persiste ambos niveles.",
            "Persistir memoria de corto y largo plazo del chat.",
        ),
        _bool_check(
            "main_exposes_chat_product_refresh",
            '/brain/chat-product/refresh' in main_py,
            "El runtime expone /brain/chat-product/refresh." if '/brain/chat-product/refresh' in main_py else "No existe endpoint de refresh del producto chat.",
            "Agregar endpoint /brain/chat-product/refresh.",
        ),
        _bool_check(
            "runtime_latency_under_15s",
            effective_latency_ms <= 15000 if effective_latency_ms else False,
            (
                f"Latencia operativa efectiva {effective_latency_ms:.0f}ms "
                f"(runtime={runtime_latency_ms:.0f}ms, self_test={self_test_latency_ms:.0f}ms)"
            ) if effective_latency_ms else "No hay telemetria runtime reciente de latencia.",
            "Reducir latencia media del chat y/o refrescar telemetria runtime.",
        ),
        _bool_check(
            "runtime_tool_fail_rate_under_25pct",
            (
                (int(runtime_metrics.get("agent_tool_calls_fail") or 0) / max(
                    1,
                    int(runtime_metrics.get("agent_tool_calls_ok") or 0)
                    + int(runtime_metrics.get("agent_tool_calls_fail") or 0),
                )) <= 0.25
            ) if runtime_metrics else False,
            "La tasa de fallo de tools está en rango aceptable." if runtime_metrics else "No hay telemetria runtime reciente de fallos de tools.",
            "Corregir registry/firma de tools y bajar fallos del agente.",
        ),
        _bool_check(
            "self_test_score_at_least_0_70",
            float(self_test_latest.get("score") or 0.0) >= 0.70 if self_test_latest else False,
            f"Self-test operativo score={float(self_test_latest.get('score') or 0.0):.2f}"
            if self_test_latest else "No existe snapshot reciente de self-test.",
            "Ejecutar y estabilizar self-test del chat antes de promover calidad.",
        ),
        _bool_check(
            "episodic_memory_has_no_exact_duplicates",
            int(episodic_stats.get("duplicate_exact_count") or 0) == 0 if episodic_stats else False,
            (
                f"Memoria episódica sin duplicados exactos (entries={episodic_stats.get('total_entries')}, duplicates={episodic_stats.get('duplicate_exact_count')})"
            ) if episodic_stats else "No se pudo medir la higiene de memoria episódica.",
            "Compactar memoria episódica y reparar duplicados exactos persistidos.",
        ),
        _bool_check(
            "runtime_ghost_completions_zero",
            int(runtime_metrics.get("ghost_completion_count") or 0) == 0 if runtime_metrics else False,
            (
                f"Ghost completions visibles={int(runtime_metrics.get('ghost_completion_count') or 0)}"
            ) if runtime_metrics else "No hay telemetría runtime reciente de ghost completions.",
            "Corregir la ruta agente->sesión para no completar turnos sin tools ejecutadas.",
        ),
        _bool_check(
            "runtime_tool_markup_leaks_zero",
            int(runtime_metrics.get("tool_markup_leak_count") or 0) == 0 if runtime_metrics else False,
            (
                f"Fugas visibles de markup de tools={int(runtime_metrics.get('tool_markup_leak_count') or 0)}"
            ) if runtime_metrics else "No hay telemetría runtime reciente de fugas de markup.",
            "Sanitizar respuestas y bloquear salida cruda de function_calls/invoke.",
        ),
        _bool_check(
            "runtime_canned_no_result_rate_under_10pct",
            (
                int(runtime_metrics.get("canned_no_result_count") or 0)
                / max(1, int(runtime_metrics.get("total_conversations") or 0))
            ) <= 0.10 if runtime_metrics else False,
            (
                "Uso de canned no-result "
                f"{int(runtime_metrics.get('canned_no_result_count') or 0)}/"
                f"{int(runtime_metrics.get('total_conversations') or 0)} turnos"
            ) if runtime_metrics else "No hay telemetría runtime reciente de fallbacks canned.",
            "Reducir respuestas canned y reemplazarlas por fallos honestos o evidencia real.",
        ),
    ]

    accepted = all(item["passed"] for item in baseline_checks)
    failed_checks = [item for item in baseline_checks if not item["passed"]]
    failed_quality_checks = [item for item in quality_checks if not item["passed"]]
    quality_pass_count = sum(1 for item in quality_checks if item["passed"])
    quality_score = round(quality_pass_count / max(len(quality_checks), 1), 4)
    pending_items = [
        "formalizar calidad conversacional y continuidad de contexto",
        "añadir telemetría y acceptance de UX del chat",
    ]
    current_state = (
        "quality_observable"
        if accepted and quality_score >= 0.8
        else "accepted_baseline"
        if accepted
        else "needs_product_work"
    )
    work_status = (
        "ready_for_conversational_tuning"
        if accepted and quality_score >= 0.8
        else "ready_for_chat_improvement"
        if accepted
        else "blocked_missing_baseline"
    )
    telemetry = {
        "schema_version": "chat_product_telemetry_v1",
        "updated_utc": _utc_now(),
        "product_id": "brain_chat_v9_product",
        "baseline_pass_count": sum(1 for item in baseline_checks if item["passed"]),
        "baseline_total": len(baseline_checks),
        "quality_pass_count": quality_pass_count,
        "quality_total": len(quality_checks),
        "quality_score": quality_score,
        "ui_features": {
            "chat_route_linked": 'href="/chat"' in dashboard_ui,
            "status_panel": 'id="panel-status"' in brain_ui,
            "model_selector": 'id="model-select"' in brain_ui,
            "agent_toggle": 'id="agent-toggle"' in brain_ui,
            "api_panel": 'id="panel-api"' in brain_ui,
        },
        "runtime_features": {
            "chat_endpoint": '@app.post("/chat"' in main_py,
            "chat_product_status_endpoint": '/brain/chat-product/status' in main_py,
            "chat_product_refresh_endpoint": '/brain/chat-product/refresh' in main_py,
            "session_memory_manager": "MemoryManager" in session_py,
            "response_normalization": "_normalize(" in session_py,
        },
        "operational_features": {
            "avg_latency_ms": runtime_latency_ms,
            "self_test_avg_latency_ms": self_test_latency_ms if self_test_latest else None,
            "effective_latency_ms": effective_latency_ms if effective_latency_ms else None,
            "agent_tool_calls_ok": int(runtime_metrics.get("agent_tool_calls_ok") or 0),
            "agent_tool_calls_fail": int(runtime_metrics.get("agent_tool_calls_fail") or 0),
            "self_test_score": float(self_test_latest.get("score") or 0.0) if self_test_latest else None,
            "self_test_passed": self_test_latest.get("passed") if self_test_latest else None,
            "self_test_failed": self_test_latest.get("failed") if self_test_latest else None,
            "episodic_duplicate_exact_count": int(episodic_stats.get("duplicate_exact_count") or 0) if episodic_stats else None,
            "episodic_total_entries": int(episodic_stats.get("total_entries") or 0) if episodic_stats else None,
            "ghost_completion_count": int(runtime_metrics.get("ghost_completion_count") or 0),
            "tool_markup_leak_count": int(runtime_metrics.get("tool_markup_leak_count") or 0),
            "canned_no_result_count": int(runtime_metrics.get("canned_no_result_count") or 0),
        },
    }

    contract = {
        "schema_version": "chat_product_contract_v1",
        "updated_utc": _utc_now(),
        "product_id": "brain_chat_v9_product",
        "title": "Contrato canónico del producto chat",
        "goal": "tener un chat operativo, visible y mejorable con criterios explícitos.",
        "accepted_baseline": accepted,
        "current_state": current_state,
        "failed_checks": [item["check_id"] for item in failed_checks + failed_quality_checks],
        "quality_score": quality_score,
        "pending_improvement_items": pending_items,
    }

    roadmap = {
        "schema_version": "chat_product_roadmap_v1",
        "updated_utc": _utc_now(),
        "roadmap_id": "brain_chat_product_v1",
        "product_id": "brain_chat_v9_product",
        "mission": "elevar el chat desde baseline usable hacia producto conversacional robusto y observable.",
        "current_state": current_state,
        "work_status": work_status,
        "items": [
            {
                "item_id": "CP-01",
                "title": "Formalizar estado, spec y roadmap del chat",
                "status": "done" if accepted else "active",
            },
            {
                "item_id": "CP-02",
                "title": "Mejorar claridad conversacional y continuidad de contexto",
                "status": "active" if accepted else "queued",
            },
            {
                "item_id": "CP-03",
                "title": "Agregar telemetría, handoff y acceptance UX",
                "status": "active" if accepted and quality_score < 1.0 else "queued",
            },
        ],
    }

    status = {
        "schema_version": "chat_product_status_v1",
        "updated_utc": _utc_now(),
        "product_id": "brain_chat_v9_product",
        "title": "Brain Chat V9",
        "mission": "servir como interfaz conversacional operativa del Brain con estado canónico y mejora gobernada.",
        "current_state": current_state,
        "work_status": work_status,
        "accepted_baseline": accepted,
        "acceptance_checks": baseline_checks,
        "quality_checks": quality_checks,
        "failed_check_count": len(failed_checks) + len(failed_quality_checks),
        "quality_score": quality_score,
        "pending_improvement_items": pending_items,
        "next_actions": [
            "improve_chat_product_quality"
        ] if accepted else [
            "synthesize_chat_product_contract"
        ],
        "meta_brain_handoff": "\n".join([
            "product=brain_chat_v9_product",
            f"current_state={current_state}",
            f"work_status={work_status}",
            f"accepted_baseline={accepted}",
            f"failed_checks={' | '.join(item['check_id'] for item in (failed_checks + failed_quality_checks)) or 'none'}",
            f"quality_score={quality_score}",
            f"pending_items={' | '.join(pending_items)}",
        ]),
        "evidence_paths": [
            str(FILES["dashboard_ui"]),
            str(FILES["brain_ui"]),
            str(FILES["main"]),
            str(FILES["session"]),
            str(FILES["memory"]),
            str(FILES["chat_spec"]),
            str(FILES["chat_roadmap"]),
            str(FILES["chat_telemetry"]),
            str(FILES["chat_metrics_runtime"]),
            str(FILES["self_test_latest"]),
        ],
    }

    activation = {
        "schema_version": "chat_product_activation_v1",
        "updated_utc": _utc_now(),
        "product_id": "brain_chat_v9_product",
        "activation_reason": "chat_product_contract_synthesized" if accepted else "chat_product_baseline_still_needs_work",
        "accepted_baseline": accepted,
    }

    write_json(FILES["chat_spec"], spec)
    write_json(FILES["chat_roadmap"], roadmap)
    write_json(FILES["chat_telemetry"], telemetry)
    write_json(FILES["chat_contract"], contract)
    write_json(FILES["chat_activation"], activation)
    write_json(FILES["chat_status"], status)
    return status


def read_chat_product_status() -> Dict[str, Any]:
    status = read_json(FILES["chat_status"], {})
    if status:
        return status
    return refresh_chat_product_status()
