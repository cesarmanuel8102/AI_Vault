"""
Brain V9 - Meta improvement engine
Autoinspeccion, gaps priorizados, memoria reutilizable y roadmap continuo
de automejora para que el Brain no tenga que recomputar desde cero cada vez.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

log = logging.getLogger("meta_improvement")

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
ROOMS_PATH = STATE_PATH / "rooms"

FILES = {
    "roadmap": STATE_PATH / "roadmap.json",
    "roadmap_governance": STATE_PATH / "roadmap_governance_status.json",
    "roadmap_dev": STATE_PATH / "roadmap_development_status_latest.json",
    "utility_latest": STATE_PATH / "utility_u_latest.json",
    "utility_gate": STATE_PATH / "utility_u_promotion_gate_latest.json",
    "utility_governance_status": STATE_PATH / "utility_governance_status_latest.json",
    "utility_governance_spec": STATE_PATH / "utility_governance_acceptance_spec.json",
    "utility_governance_roadmap": STATE_PATH / "utility_governance_roadmap.json",
    "strategy_ranking": STATE_PATH / "strategy_engine" / "strategy_ranking_latest.json",
    "strategy_scorecards": STATE_PATH / "strategy_engine" / "strategy_scorecards.json",
    "self_improvement_ledger": STATE_PATH / "self_improvement" / "self_improvement_ledger.json",
    "action_ledger": STATE_PATH / "autonomy_action_ledger.json",
    "trading_policy": STATE_PATH / "trading_autonomy_policy.json",
    "ibkr_probe": ROOMS_PATH / "brain_financial_ingestion_fi04_structured_api" / "ibkr_marketdata_probe_status.json",
    "ibkr_order_check": STATE_PATH / "trading_execution_checks" / "ibkr_paper_order_check_latest.json",
    "po_bridge": ROOMS_PATH / "brain_binary_paper_pb04_demo_execution" / "browser_bridge_latest.json",
    "meta_status": STATE_PATH / "meta_improvement_status_latest.json",
    "self_model": STATE_PATH / "brain_self_model_latest.json",
    "gaps": STATE_PATH / "brain_gap_registry_latest.json",
    "roadmap_meta": STATE_PATH / "brain_meta_roadmap_latest.json",
    "memory": STATE_PATH / "brain_self_improvement_memory.json",
    "execution_ledger": STATE_PATH / "brain_meta_execution_ledger.json",
    "chat_product_status": STATE_PATH / "chat_product_status_latest.json",
    "chat_product_spec": STATE_PATH / "chat_product_acceptance_spec.json",
    "chat_product_roadmap": STATE_PATH / "chat_product_roadmap.json",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _parse_utc(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception as exc:
        log.debug("_parse_utc failed for %r: %s", raw, exc)
        return None


def _hours_since(raw: str | None) -> float | None:
    dt = _parse_utc(raw)
    if dt is None:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0


def _build_memory_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    previous = read_json(FILES["memory"], {"playbooks": [], "recurring_gaps": {}, "resolved_gaps": []})
    ledger_entries = state["self_improvement_ledger"].get("entries", [])
    execution_entries = state["execution_ledger"].get("entries", [])
    action_entries = state["action_ledger"].get("entries", [])
    roadmap = state["roadmap"]
    trading_policy = state["trading_policy"].get("global_rules", {})

    promoted = sum(1 for entry in ledger_entries if entry.get("status") == "promoted")
    rolled_back = sum(1 for entry in ledger_entries if entry.get("status") == "rolled_back")
    passed_validations = sum(1 for entry in ledger_entries if entry.get("validation") == "passed")
    healthy_restarts = sum(1 for entry in ledger_entries if entry.get("restart") == "ok")
    completed_action_counts: Dict[str, int] = {}
    for entry in action_entries:
        if entry.get("status") != "completed":
            continue
        action_name = str(entry.get("action_name") or "").strip()
        if not action_name:
            continue
        completed_action_counts[action_name] = int(completed_action_counts.get(action_name, 0) or 0) + 1

    dynamic_playbooks: List[Dict[str, Any]] = []
    lessons: List[Dict[str, Any]] = []
    last_successful_method = None
    for entry in reversed(action_entries):
        if entry.get("status") == "completed" and entry.get("action_name"):
            last_successful_method = entry.get("action_name")
            break

    playbooks = [
        {
            "playbook_id": "validate_before_promote",
            "title": "Validar antes de promover",
            "description": "Usar validation passed, gate positivo y smoke/health checks antes de promover cambios.",
            "confidence": _clamp((passed_validations + healthy_restarts) / 12.0),
            "evidence_count": passed_validations,
            "steps": [
                "staging_controlado",
                "validation_passed",
                "promotion_gate",
                "restart_y_smoke_tests",
            ],
        },
        {
            "playbook_id": "rollback_preserves_operability",
            "title": "Rollback preserva operatividad",
            "description": "Si un cambio falla, rollback automático y health check para volver a estado sano.",
            "confidence": _clamp(0.35 + rolled_back / 5.0),
            "evidence_count": rolled_back,
            "steps": [
                "detectar_fallo",
                "rollback_controlado",
                "verificar_health",
            ],
        },
        {
            "playbook_id": "phase_specs_enable_autopromotion",
            "title": "Phase specs habilitan autopromoción",
            "description": "Specs + checks + artifacts canónicos permiten promocionar fases sin revisión manual.",
            "confidence": 1.0 if roadmap.get("current_stage") == "done" else 0.65,
            "evidence_count": int(roadmap.get("counts", {}).get("done", 0) or 0),
            "steps": [
                "definir_spec",
                "evaluar_acceptance",
                "emitir_completion_artifact",
                "promover_roadmap",
            ],
        },
        {
            "playbook_id": "paper_only_first",
            "title": "Paper-only primero",
            "description": "Mantener paper_only y live_forbidden como default mientras el Brain aprende o se modifica.",
            "confidence": 1.0 if trading_policy.get("paper_only") and trading_policy.get("live_trading_forbidden") else 0.5,
            "evidence_count": 1 if trading_policy else 0,
            "steps": [
                "paper_only",
                "medir",
                "comparar",
                "promover_solo_si_hay_evidencia",
            ],
        },
    ]

    if completed_action_counts.get("improve_expectancy_or_reduce_penalties", 0) >= 3:
        dynamic_playbooks.append({
            "playbook_id": "expectancy_tuning_iterative",
            "title": "Iterar expectancy de forma controlada",
            "description": "Cuando Utility y estrategia siguen débiles, iterar ajustes de expectancy con paper-only y scorecard antes de promover.",
            "confidence": _clamp(0.45 + completed_action_counts["improve_expectancy_or_reduce_penalties"] / 15.0),
            "evidence_count": completed_action_counts["improve_expectancy_or_reduce_penalties"],
            "steps": [
                "detectar_gap_en_utility",
                "ejecutar_improve_expectancy_or_reduce_penalties",
                "medir_scorecard_y_u",
                "repetir_si_hay_mejora_o_muestra_insuficiente",
            ],
        })
        lessons.append({
            "lesson_id": "lesson_expectancy_tuning",
            "title": "Expectancy tuning es un método reutilizable",
            "observation": "El Brain ya usa repetidamente improve_expectancy_or_reduce_penalties como respuesta interna al gap principal de Utility.",
            "source": "autonomy_action_ledger",
            "method": "improve_expectancy_or_reduce_penalties",
            "confidence": _clamp(0.4 + completed_action_counts["improve_expectancy_or_reduce_penalties"] / 20.0),
            "evidence_count": completed_action_counts["improve_expectancy_or_reduce_penalties"],
        })

    if completed_action_counts.get("select_and_compare_strategies", 0) >= 2:
        dynamic_playbooks.append({
            "playbook_id": "compare_before_commit",
            "title": "Comparar antes de consolidar",
            "description": "Antes de asumir que una estrategia mejora el sistema, correr comparación entre candidatos y usar expectancy/contexto para decidir.",
            "confidence": _clamp(0.45 + completed_action_counts["select_and_compare_strategies"] / 10.0),
            "evidence_count": completed_action_counts["select_and_compare_strategies"],
            "steps": [
                "refresh_ranking",
                "execute_comparison_cycle",
                "recalcular_expectancy",
                "ajustar_governance",
            ],
        })
        lessons.append({
            "lesson_id": "lesson_comparison_cycle",
            "title": "El comparison cycle ayuda a filtrar estrategias",
            "observation": "El Brain ya dispone de evidencia suficiente para tratar select_and_compare_strategies como método normal de aprendizaje, no como experimento aislado.",
            "source": "autonomy_action_ledger",
            "method": "select_and_compare_strategies",
            "confidence": _clamp(0.45 + completed_action_counts["select_and_compare_strategies"] / 8.0),
            "evidence_count": completed_action_counts["select_and_compare_strategies"],
        })

    if len(execution_entries) >= 2:
        dynamic_playbooks.append({
            "playbook_id": "meta_gap_delegation_loop",
            "title": "Delegar el gap meta al worker adecuado",
            "description": "La capa meta inspecciona gaps, elige el dominante y delega la acción interna más adecuada dejando handoff y memoria.",
            "confidence": _clamp(0.4 + len(execution_entries) / 8.0),
            "evidence_count": len(execution_entries),
            "steps": [
                "autoinspeccionar_dominios",
                "priorizar_gap",
                "delegar_accion_interna",
                "persistir_handoff_y_aprendizaje",
            ],
        })
        lessons.append({
            "lesson_id": "lesson_meta_delegation",
            "title": "La meta-mejora ya puede delegar trabajo real",
            "observation": "La capa meta ya no solo describe gaps; también ejecuta o delega acciones internas y guarda evidencia reutilizable.",
            "source": "brain_meta_execution_ledger",
            "method": "advance_meta_improvement_roadmap",
            "confidence": _clamp(0.45 + len(execution_entries) / 8.0),
            "evidence_count": len(execution_entries),
        })

    seen_playbooks = set()
    merged_playbooks: List[Dict[str, Any]] = []
    for item in playbooks + dynamic_playbooks:
        playbook_id = item.get("playbook_id")
        if not playbook_id or playbook_id in seen_playbooks:
            continue
        merged_playbooks.append(item)
        seen_playbooks.add(playbook_id)

    recurring_gaps = dict(previous.get("recurring_gaps", {}))
    memory = {
        "schema_version": "brain_self_improvement_memory_v1",
        "updated_utc": _utc_now(),
        "memory_goal": "reusar playbooks y lecciones de mejora para no recomputar el proceso de autodesarrollo desde cero.",
        "playbooks": merged_playbooks,
        "lessons": lessons[:6],
        "resolved_gaps": previous.get("resolved_gaps", []),
        "recurring_gaps": recurring_gaps,
        "summary": {
            "playbook_count": len(merged_playbooks),
            "lessons_count": len(lessons[:6]),
            "promoted_changes": promoted,
            "rolled_back_changes": rolled_back,
            "validated_changes": passed_validations,
            "meta_executions": len(execution_entries),
            "last_successful_method": last_successful_method,
        },
    }
    return memory


def _build_self_model(state: Dict[str, Any], memory: Dict[str, Any]) -> Dict[str, Any]:
    utility_score = float(state["utility_latest"].get("u_proxy_score", -1.0) or -1.0)
    gate_blockers = state["utility_gate"].get("blockers", [])
    utility_governance = state["utility_governance_status"]
    top_strategy = state["strategy_ranking"].get("top_strategy") or {}
    roadmap = state["roadmap"]
    roadmap_dev = state["roadmap_dev"]
    ibkr_order_ready = bool(state["ibkr_order_check"].get("order_api_ready"))
    po_capture_age = _hours_since(state["po_bridge"].get("captured_at_utc") or state["po_bridge"].get("captured_utc"))
    po_live = po_capture_age is not None and po_capture_age <= 2.0
    playbook_count = memory.get("summary", {}).get("playbook_count", 0)

    domains = [
        {
            "domain_id": "utility_governance",
            "title": "Utility y promotion gates",
            "score": _round(_clamp(
                0.2
                + (0.2 if utility_governance.get("accepted_baseline") else 0.0)
                + ((utility_score + 1.0) / 2.0) * 0.35
                - (0.06 * len(gate_blockers))
            )),
            "status": (
                "healthy"
                if utility_governance.get("accepted_baseline") and utility_score >= 0.75 and not gate_blockers
                else "needs_work"
            ),
            "evidence": [
                str(FILES["utility_latest"]),
                str(FILES["utility_gate"]),
                str(FILES["utility_governance_status"]),
                str(FILES["utility_governance_spec"]),
                str(FILES["utility_governance_roadmap"]),
            ],
        },
        {
            "domain_id": "strategy_learning",
            "title": "Strategy learning",
            "score": _round(_clamp(
                0.35
                + float(top_strategy.get("sample_quality", 0.0) or 0.0) * 0.35
                + float(top_strategy.get("consistency_score", 0.0) or 0.0) * 0.2
                + _clamp(float(top_strategy.get("expectancy", 0.0) or 0.0) / 2.0, -0.2, 0.2)
            )),
            "status": "healthy" if float(top_strategy.get("sample_quality", 0.0) or 0.0) >= 0.85 else "needs_work",
            "evidence": [str(FILES["strategy_ranking"]), str(FILES["strategy_scorecards"])],
        },
        {
            "domain_id": "venue_execution",
            "title": "Venue execution",
            "score": _round(_clamp((0.55 if ibkr_order_ready else 0.2) + (0.35 if po_live else 0.1))),
            "status": "healthy" if ibkr_order_ready and po_live else "needs_work",
            "evidence": [str(FILES["ibkr_order_check"]), str(FILES["po_bridge"])],
        },
        {
            "domain_id": "meta_governance",
            "title": "Meta governance",
            "score": _round(1.0 if roadmap.get("current_stage") == "done" and roadmap_dev.get("work_status") == "completed" else 0.55),
            "status": "healthy" if roadmap.get("current_stage") == "done" else "needs_work",
            "evidence": [str(FILES["roadmap"]), str(FILES["roadmap_governance"])],
        },
        {
            "domain_id": "self_improvement_memory",
            "title": "Memory and playbooks",
            "score": _round(_clamp(0.3 + (playbook_count / 6.0))),
            "status": "healthy" if playbook_count >= 4 else "needs_work",
            "evidence": [str(FILES["memory"]), str(FILES["self_improvement_ledger"])],
        },
        {
            "domain_id": "chat_product",
            "title": "Chat UX/product",
            "score": _round(
                0.25
                + (0.35 if state["chat_product_status"].get("accepted_baseline") else 0.0)
                + min(len(state["chat_product_status"].get("acceptance_checks", [])) * 0.05, 0.2)
            ),
            "status": "healthy" if state["chat_product_status"].get("accepted_baseline") else "needs_work",
            "evidence": [
                str(FILES["chat_product_status"]),
                str(FILES["chat_product_spec"]),
                str(FILES["chat_product_roadmap"]),
            ],
        },
    ]

    overall_score = _round(sum(domain["score"] for domain in domains) / max(len(domains), 1))
    return {
        "schema_version": "brain_self_model_v1",
        "updated_utc": _utc_now(),
        "identity": {
            "current_mode": "continual_self_improvement",
            "mission": "seguir mejorando mientras existan gaps de alto beneficio con evidencia y política de ejecución segura.",
            "continuation_rule": "si hay gaps priorizados abiertos, el Brain sigue trabajando; si no, mantiene vigilancia y busca nuevos gaps.",
        },
        "overall_score": overall_score,
        "domains": domains,
    }


def _gap(
    gap_id: str,
    domain_id: str,
    title: str,
    description: str,
    objective: str,
    benefit: float,
    readiness: float,
    execution_mode: str,
    suggested_actions: List[str],
    evidence_paths: List[str],
    blockers: List[str] | None = None,
    current_state: str = "open",
    target_metric: str | None = None,
) -> Dict[str, Any]:
    blockers = blockers or []
    priority = _round(benefit * 0.65 + readiness * 0.35)
    return {
        "gap_id": gap_id,
        "domain_id": domain_id,
        "title": title,
        "description": description,
        "objective": objective,
        "benefit_score": _round(benefit),
        "readiness_score": _round(readiness),
        "priority_score": priority,
        "current_state": current_state,
        "execution_mode": execution_mode,
        "suggested_actions": suggested_actions,
        "blockers": blockers,
        "target_metric": target_metric,
        "evidence_paths": evidence_paths,
    }


def _build_gaps(state: Dict[str, Any], self_model: Dict[str, Any], memory: Dict[str, Any]) -> Dict[str, Any]:
    top_strategy = state["strategy_ranking"].get("top_strategy") or {}
    gaps: List[Dict[str, Any]] = []
    execution_counts: Dict[str, int] = {}
    for entry in state["execution_ledger"].get("entries", []):
        gap_id = str(entry.get("gap_id") or "").strip()
        if not gap_id:
            continue
        execution_counts[gap_id] = int(execution_counts.get(gap_id, 0) or 0) + 1

    if float(top_strategy.get("sample_quality", 0.0) or 0.0) < 0.85:
        gaps.append(_gap(
            gap_id="strategy_sample_depth",
            domain_id="strategy_learning",
            title="Profundizar muestra de estrategia top",
            description="La estrategia líder ya es útil, pero todavía no tiene muestra suficiente para excelencia o promoción fuerte.",
            objective="Subir sample_quality y contexto comparado sin degradar expectancy.",
            benefit=0.92,
            readiness=0.93,
            execution_mode="internal_candidate",
            suggested_actions=["select_and_compare_strategies"],
            evidence_paths=[str(FILES["strategy_ranking"]), str(FILES["strategy_scorecards"])],
            target_metric="sample_quality>=0.85 y context_sample_quality>=0.35",
        ))

    if float(state["utility_latest"].get("u_proxy_score", 0.0) or 0.0) < 0.75:
        utility_status = state["utility_governance_status"]
        utility_status_path = FILES["utility_governance_status"]
        if not utility_status_path.exists():
            gaps.append(_gap(
                gap_id="utility_governance_contract_missing",
                domain_id="utility_governance",
                title="Formalizar contrato y roadmap de Utility",
                description="Utility ya opera, pero aún no tiene un estado canónico propio de gobernanza y mejora como dominio interno.",
                objective="Crear status, acceptance y roadmap propios para que el Brain mejore Utility de forma acumulativa y explicable.",
                benefit=0.92,
                readiness=0.9,
                execution_mode="internal_candidate",
                suggested_actions=["synthesize_utility_governance_contract"],
                evidence_paths=[str(FILES["utility_governance_status"]), str(FILES["utility_governance_spec"]), str(FILES["utility_governance_roadmap"])],
                target_metric="utility_governance.accepted_baseline=true",
            ))
        elif not utility_status.get("accepted_baseline"):
            gaps.append(_gap(
                gap_id="utility_governance_baseline_finish",
                domain_id="utility_governance",
                title="Cerrar baseline de gobernanza de Utility",
                description="El dominio de Utility ya existe, pero todavía no cumple todos sus checks canónicos de baseline.",
                objective="Completar el baseline de gobernanza de Utility para que la mejora fina ocurra sobre contratos estables.",
                benefit=0.88,
                readiness=0.84,
                execution_mode="internal_candidate",
                suggested_actions=["synthesize_utility_governance_contract"],
                evidence_paths=[str(FILES["utility_governance_status"]), str(FILES["utility_governance_spec"]), str(FILES["utility_governance_roadmap"])],
                blockers=[item.get("check_id") for item in utility_status.get("acceptance_checks", []) if not item.get("passed")],
                target_metric="utility_governance.accepted_baseline=true",
            ))
        else:
            gaps.append(_gap(
                gap_id="utility_sensitivity_and_lift",
                domain_id="utility_governance",
                title="Fortalecer sensibilidad y lift de Utility U",
                description="U ya funciona, pero aún debe discriminar mejor mejoras pequeñas y priorizar contexto ganador con más precisión.",
                objective="Aumentar discriminación fina de U y alinear mejor score global con strategy/context evidence.",
                benefit=0.87,
                readiness=0.82,
                execution_mode="internal_candidate",
                suggested_actions=["improve_expectancy_or_reduce_penalties", "select_and_compare_strategies"],
                evidence_paths=[
                    str(FILES["utility_latest"]),
                    str(FILES["utility_gate"]),
                    str(FILES["utility_governance_status"]),
                    str(FILES["strategy_ranking"]),
                ],
                target_metric="u_proxy_score>=0.75 con blockers coherentes",
            ))

    po_age = _hours_since(state["po_bridge"].get("captured_at_utc") or state["po_bridge"].get("captured_utc"))
    if po_age is None or po_age > 2.0:
        blockers = [] if po_age is not None else ["no_fresh_bridge_capture"]
        gaps.append(_gap(
            gap_id="pocket_option_freshness",
            domain_id="venue_execution",
            title="Recuperar frescura de Pocket Option demo",
            description="El lane de PO sigue siendo útil, pero sin captura fresca el Brain pierde comparabilidad y confiabilidad de venue.",
            objective="Mantener bridge demo fresco y verificable dentro de ventana corta.",
            benefit=0.68,
            readiness=0.45 if blockers else 0.7,
            execution_mode="needs_meta_brain" if blockers else "internal_candidate",
            suggested_actions=[] if blockers else ["advance_meta_improvement_roadmap"],
            evidence_paths=[str(FILES["po_bridge"])],
            blockers=blockers,
            target_metric="captura <= 2h",
        ))

    if memory.get("summary", {}).get("playbook_count", 0) < 5:
        gaps.append(_gap(
            gap_id="memory_playbook_depth",
            domain_id="self_improvement_memory",
            title="Aumentar densidad de playbooks reutilizables",
            description="El Brain ya tiene memoria base, pero necesita más patrones canónicos de cómo mejorarse para no re-razonar todo.",
            objective="Expandir playbooks y lecciones reutilizables a más dominios del Brain.",
            benefit=0.74,
            readiness=0.9,
            execution_mode="internal_candidate",
            suggested_actions=["advance_meta_improvement_roadmap"],
            evidence_paths=[str(FILES["memory"]), str(FILES["self_improvement_ledger"])],
            target_metric="playbook_count>=5",
        ))

    chat_status = state["chat_product_status"]
    chat_status_path = FILES["chat_product_status"]
    if not chat_status_path.exists():
        gaps.append(_gap(
            gap_id="chat_product_acceptance_missing",
            domain_id="chat_product",
            title="Formalizar aceptación y roadmap del chat",
            description="El chat sigue siendo funcional pero no tiene un estado canónico de producto, aceptación y deuda pendiente visible.",
            objective="Crear estado canónico, acceptance criteria y roadmap específico del chat para que el Brain pueda mejorarlo de forma autónoma.",
            benefit=0.89,
            readiness=0.88,
            execution_mode="internal_candidate",
            suggested_actions=["synthesize_chat_product_contract"],
            evidence_paths=[str(FILES["chat_product_status"]), str(FILES["chat_product_spec"]), str(FILES["chat_product_roadmap"])],
            blockers=[],
            target_metric="chat_product_status_latest.json + spec + evaluator",
        ))
    elif not chat_status.get("accepted_baseline"):
        failed_checks = [
            item.get("check_id")
            for item in chat_status.get("acceptance_checks", [])
            if not item.get("passed")
        ]
        gaps.append(_gap(
            gap_id="chat_product_baseline_finish",
            domain_id="chat_product",
            title="Cerrar baseline canónico del chat",
            description="El Brain ya tiene contrato/base del chat, pero aún debe cerrar checks pendientes para gobernarlo autónomamente.",
            objective="Completar los checks pendientes del producto chat y dejarlo listo para mejoras de UX y calidad.",
            benefit=0.84,
            readiness=0.74,
            execution_mode="needs_meta_brain" if failed_checks else "internal_candidate",
            suggested_actions=[] if failed_checks else ["improve_chat_product_quality"],
            evidence_paths=[str(FILES["chat_product_status"]), str(FILES["chat_product_spec"]), str(FILES["chat_product_roadmap"])],
            blockers=failed_checks,
            target_metric="accepted_baseline=true",
        ))
    elif chat_status.get("work_status") in {"ready_for_chat_improvement", "ready_for_conversational_tuning"}:
        gaps.append(_gap(
            gap_id="chat_product_quality_and_ux",
            domain_id="chat_product",
            title="Elevar calidad y observabilidad del chat",
            description="El chat ya tiene baseline, pero aún debe mejorar continuidad, telemetría y calidad observable como producto.",
            objective="Cerrar el siguiente escalón del chat como producto gobernado y visible en el dashboard.",
            benefit=0.79,
            readiness=0.83,
            execution_mode="internal_candidate",
            suggested_actions=["improve_chat_product_quality"],
            evidence_paths=[str(FILES["chat_product_status"]), str(FILES["chat_product_spec"]), str(FILES["chat_product_roadmap"])],
            blockers=[],
            target_metric="chat current_state=quality_observable",
        ))

    recurring = dict(memory.get("recurring_gaps", {}))
    for gap in gaps:
        recurring[gap["gap_id"]] = int(recurring.get(gap["gap_id"], 0) or 0) + 1
        gap["recurrence_count"] = recurring[gap["gap_id"]]
        gap["attempt_count"] = int(execution_counts.get(gap["gap_id"], 0) or 0)

    gaps.sort(key=lambda item: (item["priority_score"], item["benefit_score"], item["readiness_score"]), reverse=True)
    memory["recurring_gaps"] = recurring
    return {
        "schema_version": "brain_gap_registry_v1",
        "updated_utc": _utc_now(),
        "open_gaps": gaps,
        "summary": {
            "open_count": len(gaps),
            "internal_candidate_count": sum(1 for gap in gaps if gap["execution_mode"] == "internal_candidate"),
            "needs_meta_brain_count": sum(1 for gap in gaps if gap["execution_mode"] == "needs_meta_brain"),
        },
    }


def _update_memory_resolution_state(memory: Dict[str, Any], gap_registry: Dict[str, Any], previous_status: Dict[str, Any]) -> Dict[str, Any]:
    current_gaps = {item.get("gap_id") for item in gap_registry.get("open_gaps", []) if item.get("gap_id")}
    previous_gaps = {
        item.get("gap_id"): item
        for item in previous_status.get("gap_registry", {}).get("open_gaps", [])
        if item.get("gap_id")
    }
    resolved = list(memory.get("resolved_gaps", []))
    resolved_ids = {item.get("gap_id") for item in resolved if item.get("gap_id")}

    for gap_id, previous_gap in previous_gaps.items():
        if gap_id in current_gaps or gap_id in resolved_ids:
            continue
        resolved.append({
            "gap_id": gap_id,
            "title": previous_gap.get("title"),
            "resolved_utc": _utc_now(),
            "resolution_reason": "gap_absent_in_latest_autoinspection",
            "last_priority_score": previous_gap.get("priority_score"),
            "previous_execution_mode": previous_gap.get("execution_mode"),
        })

    memory["resolved_gaps"] = resolved[-8:]
    memory.setdefault("summary", {})
    memory["summary"]["resolved_gap_count"] = len(memory["resolved_gaps"])
    memory["summary"]["recurring_gap_count"] = len(memory.get("recurring_gaps", {}))
    return memory


def _select_gap_method(gap: Dict[str, Any], memory: Dict[str, Any]) -> Dict[str, Any]:
    suggested_actions = list(gap.get("suggested_actions", []))
    last_successful_method = memory.get("summary", {}).get("last_successful_method")
    playbooks = {item.get("playbook_id"): item for item in memory.get("playbooks", [])}
    selected_action = suggested_actions[0] if suggested_actions else None
    selected_playbooks: List[str] = []
    reason = "fallback_to_first_suggested_action"

    if gap.get("gap_id") == "utility_sensitivity_and_lift":
        if "compare_before_commit" in playbooks and last_successful_method != "select_and_compare_strategies" and "select_and_compare_strategies" in suggested_actions:
            selected_action = "select_and_compare_strategies"
            selected_playbooks = ["compare_before_commit"]
            reason = "utility_gap_prefers_comparison_before_tuning"
        elif "expectancy_tuning_iterative" in playbooks and "improve_expectancy_or_reduce_penalties" in suggested_actions:
            selected_action = "improve_expectancy_or_reduce_penalties"
            selected_playbooks = ["expectancy_tuning_iterative"]
            reason = "utility_gap_reuses_expectancy_tuning_playbook"
    elif gap.get("domain_id") == "chat_product":
        if "improve_chat_product_quality" in suggested_actions:
            selected_action = "improve_chat_product_quality"
            reason = "chat_product_gap_prefers_quality_iteration"
    elif gap.get("gap_id") == "memory_playbook_depth" and "advance_meta_improvement_roadmap" in suggested_actions:
        selected_action = "advance_meta_improvement_roadmap"
        selected_playbooks = ["meta_gap_delegation_loop"]
        reason = "memory_gap_expands_meta_playbooks"

    return {
        "selected_action": selected_action,
        "selected_playbooks": selected_playbooks,
        "reason": reason,
    }


def _build_meta_roadmap(state: Dict[str, Any], gap_registry: Dict[str, Any]) -> Dict[str, Any]:
    gaps = gap_registry.get("open_gaps", [])
    memory = state.get("memory_snapshot") or {}
    items = []
    for order, gap in enumerate(gaps, start=1):
        status = "active" if order == 1 else "queued"
        method_choice = _select_gap_method(gap, memory)
        items.append({
            "item_id": f"MI-{order:02d}",
            "order": order,
            "gap_id": gap["gap_id"],
            "domain_id": gap["domain_id"],
            "title": gap["title"],
            "objective": gap["objective"],
            "priority_score": gap["priority_score"],
            "execution_mode": gap["execution_mode"],
            "status": status,
            "suggested_actions": gap.get("suggested_actions", []),
            "blockers": gap.get("blockers", []),
            "recommended_method": method_choice.get("selected_action"),
            "method_selection_reason": method_choice.get("reason"),
            "selected_playbooks": method_choice.get("selected_playbooks", []),
        })

    top_item = items[0] if items else None
    top_gap = gaps[0] if gaps else None
    if not top_item:
        work_status = "observe_only"
        current_work = "No hay gaps de alta prioridad abiertos; mantener vigilancia y refrescar autoinspección."
    elif top_gap.get("execution_mode") == "needs_meta_brain":
        work_status = "blocked_needs_meta_brain"
        current_work = "El Brain detectó un gap de alto valor pero necesita ayuda externa/meta-cerebro para seguir."
    else:
        work_status = "internal_execution_ready"
        current_work = "El Brain puede seguir por sí mismo con el siguiente gap priorizado."

    return {
        "schema_version": "brain_meta_roadmap_v1",
        "updated_utc": _utc_now(),
        "roadmap_id": "brain_meta_self_improvement_v1",
        "mission": "seguir mejorando de forma continua mientras existan gaps de alto beneficio y ejecución segura.",
        "work_status": work_status,
        "current_work_summary": current_work,
        "top_item": top_item,
        "items": items,
    }


def _build_handoff(status: Dict[str, Any]) -> str:
    top_gap = status.get("top_gap") or {}
    roadmap = status.get("roadmap", {})
    memory = status.get("memory", {})
    lines = [
        f"meta_roadmap={roadmap.get('roadmap_id')}",
        f"work_status={roadmap.get('work_status')}",
        f"top_gap={top_gap.get('gap_id')} · domain={top_gap.get('domain_id')} · execution_mode={top_gap.get('execution_mode')}",
        f"title={top_gap.get('title')}",
        f"objective={top_gap.get('objective')}",
        f"priority={top_gap.get('priority_score')} · benefit={top_gap.get('benefit_score')} · readiness={top_gap.get('readiness_score')} · attempts={top_gap.get('attempt_count', 0)} · recurrences={top_gap.get('recurrence_count', 0)}",
        f"suggested_actions={' | '.join(top_gap.get('suggested_actions', [])) or 'none'}",
        f"recommended_method={top_gap.get('recommended_method') or 'none'} · reason={top_gap.get('method_selection_reason') or 'none'}",
        f"blockers={' | '.join(top_gap.get('blockers', [])) or 'none'}",
        f"last_successful_method={memory.get('summary', {}).get('last_successful_method') or 'none'}",
        "evidence_paths=",
    ]
    for path in top_gap.get("evidence_paths", []):
        lines.append(f"- {path}")
    for playbook in memory.get("playbooks", [])[:3]:
        lines.append(f"playbook::{playbook.get('playbook_id')} -> {playbook.get('description')}")
    for lesson in memory.get("lessons", [])[:2]:
        lines.append(f"lesson::{lesson.get('lesson_id')} -> {lesson.get('observation')}")
    return "\n".join(lines)


def refresh_meta_improvement_status() -> Dict[str, Any]:
    state = {
        "previous_meta_status": read_json(FILES["meta_status"], {}),
        "roadmap": read_json(FILES["roadmap"], {}),
        "roadmap_governance": read_json(FILES["roadmap_governance"], {}),
        "roadmap_dev": read_json(FILES["roadmap_dev"], {}),
        "utility_latest": read_json(FILES["utility_latest"], {}),
        "utility_gate": read_json(FILES["utility_gate"], {}),
        "utility_governance_status": read_json(FILES["utility_governance_status"], {}),
        "strategy_ranking": read_json(FILES["strategy_ranking"], {}),
        "strategy_scorecards": read_json(FILES["strategy_scorecards"], {}),
        "self_improvement_ledger": read_json(FILES["self_improvement_ledger"], {"entries": []}),
        "action_ledger": read_json(FILES["action_ledger"], {"entries": []}),
        "trading_policy": read_json(FILES["trading_policy"], {}),
        "ibkr_probe": read_json(FILES["ibkr_probe"], {}),
        "ibkr_order_check": read_json(FILES["ibkr_order_check"], {}),
        "po_bridge": read_json(FILES["po_bridge"], {}),
        "execution_ledger": read_json(FILES["execution_ledger"], {"entries": []}),
        "chat_product_status": read_json(FILES["chat_product_status"], {}),
    }

    memory = _build_memory_snapshot(state)
    state["memory_snapshot"] = memory
    self_model = _build_self_model(state, memory)
    gap_registry = _build_gaps(state, self_model, memory)
    memory = _update_memory_resolution_state(memory, gap_registry, state["previous_meta_status"])
    state["memory_snapshot"] = memory
    roadmap = _build_meta_roadmap(state, gap_registry)
    last_execution = (state["execution_ledger"].get("entries") or [None])[-1]
    top_item = roadmap.get("top_item") or {}
    top_gap = dict((gap_registry.get("open_gaps") or [None])[0] or {})
    if top_gap:
        top_gap["recommended_method"] = top_item.get("recommended_method")
        top_gap["method_selection_reason"] = top_item.get("method_selection_reason")
        top_gap["selected_playbooks"] = top_item.get("selected_playbooks", [])
    status = {
        "schema_version": "meta_improvement_status_v1",
        "updated_utc": _utc_now(),
        "mission": {
            "goal": "automejorarse continuamente en arquitectura, evaluación, aprendizaje, producto y memoria.",
            "continuation_rule": "seguir mientras existan gaps priorizados abiertos o dominios con score insuficiente.",
            "terminal_rule": "si no hay gaps abiertos, quedar en observe_only y volver a inspeccionar periódicamente.",
        },
        "self_model": self_model,
        "gap_registry": gap_registry,
        "roadmap": roadmap,
        "top_gap": top_gap or None,
        "memory": memory,
        "last_execution": last_execution,
    }
    status["meta_brain_handoff"] = _build_handoff(status)

    write_json(FILES["self_model"], self_model)
    write_json(FILES["gaps"], gap_registry)
    write_json(FILES["roadmap_meta"], roadmap)
    write_json(FILES["memory"], memory)
    write_json(FILES["meta_status"], status)
    return status


def read_meta_improvement_status() -> Dict[str, Any]:
    status = read_json(FILES["meta_status"], {})
    if status:
        return status
    return refresh_meta_improvement_status()


def append_meta_execution(entry: Dict[str, Any]) -> Dict[str, Any]:
    ledger = read_json(FILES["execution_ledger"], {"schema_version": "brain_meta_execution_ledger_v1", "entries": []})
    ledger["entries"].append(entry)
    ledger["updated_utc"] = entry.get("updated_utc", _utc_now())
    write_json(FILES["execution_ledger"], ledger)
    return ledger
