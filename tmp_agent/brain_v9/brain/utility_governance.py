"""
Brain V9 - Utility governance
Formaliza Utility U como dominio canónico de autodesarrollo para que el Brain
pueda inspeccionarla, mejorarla y explicar sus bloqueos sin reinterpretarla
desde cero en cada ciclo.
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
UTILITY_ROOM = ROOMS_PATH / "brain_utility_governance_ug01_contract"

FILES = {
    "main": BASE_PATH / "tmp_agent" / "brain_v9" / "main.py",
    "utility_module": BASE_PATH / "tmp_agent" / "brain_v9" / "brain" / "utility.py",
    "utility_snapshot": STATE_PATH / "utility_u_latest.json",
    "utility_gate": STATE_PATH / "utility_u_promotion_gate_latest.json",
    "autonomy_next_actions": STATE_PATH / "autonomy_next_actions.json",
    "ranking": STATE_PATH / "strategy_engine" / "strategy_ranking_latest.json",
    "status": STATE_PATH / "utility_governance_status_latest.json",
    "spec": STATE_PATH / "utility_governance_acceptance_spec.json",
    "roadmap": STATE_PATH / "utility_governance_roadmap.json",
    "contract": UTILITY_ROOM / "utility_governance_contract.json",
    "activation": UTILITY_ROOM / "utility_governance_activation.json",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

log = logging.getLogger("utility_governance")


def _read_text(path: Path) -> str:
    return _state_read_text(path, "")


def _bool_check(check_id: str, passed: bool, detail: str, repair_hint: str) -> Dict[str, Any]:
    return {
        "check_id": check_id,
        "passed": bool(passed),
        "detail": detail,
        "repair_hint": repair_hint,
    }


def _build_utility_spec() -> Dict[str, Any]:
    return {
        "schema_version": "utility_governance_acceptance_spec_v1",
        "updated_utc": _utc_now(),
        "domain_id": "utility_governance",
        "title": "Utility U governance",
        "mission": "mantener Utility U como función operativa sensible, trazable y alineada con ranking, blockers y gates.",
        "acceptance_mode": "all_checks_must_pass",
        "acceptance_checks": [
            {
                "id": "utility_snapshot_exists",
                "kind": "file_exists",
                "source": str(FILES["utility_snapshot"]),
                "description": "Debe existir un snapshot vivo de Utility U.",
            },
            {
                "id": "utility_gate_exists",
                "kind": "file_exists",
                "source": str(FILES["utility_gate"]),
                "description": "Debe existir un gate vivo de promoción de Utility.",
            },
            {
                "id": "utility_module_has_lifts",
                "kind": "py_contains",
                "source": str(FILES["utility_module"]),
                "pattern": "strategy_lift",
                "description": "La fórmula de Utility debe incorporar lifts explícitos de estrategia y comparación.",
            },
            {
                "id": "main_exposes_utility_route",
                "kind": "py_contains",
                "source": str(FILES["main"]),
                "pattern": '@app.get("/brain/utility"',
                "description": "El runtime debe exponer el endpoint /brain/utility.",
            },
            {
                "id": "main_exposes_utility_governance_status",
                "kind": "py_contains",
                "source": str(FILES["main"]),
                "pattern": '/brain/utility-governance/status',
                "description": "El runtime debe exponer el estado canónico de gobernanza de Utility.",
            },
        ],
        "roadmap_projection": [
            {
                "item_id": "UG-01",
                "title": "Formalizar estado, spec y roadmap de Utility",
                "status": "active",
            },
            {
                "item_id": "UG-02",
                "title": "Alinear sensibilidad fina con ranking y contexto ganador",
                "status": "queued",
            },
            {
                "item_id": "UG-03",
                "title": "Conectar Utility con gates de capital y promoción más robustos",
                "status": "queued",
            },
        ],
    }


def refresh_utility_governance_status() -> Dict[str, Any]:
    main_py = _read_text(FILES["main"])
    utility_module = _read_text(FILES["utility_module"])
    utility_snapshot = read_json(FILES["utility_snapshot"], {})
    utility_gate = read_json(FILES["utility_gate"], {})
    autonomy_next_actions = read_json(FILES["autonomy_next_actions"], {})
    ranking = read_json(FILES["ranking"], {})
    spec = _build_utility_spec()

    snapshot_exists = FILES["utility_snapshot"].exists() and bool(utility_snapshot)
    gate_exists = FILES["utility_gate"].exists() and bool(utility_gate)
    has_strategy_lift = "strategy_lift" in utility_module and "comparison_lift" in utility_module
    checks: List[Dict[str, Any]] = [
        _bool_check(
            "utility_snapshot_exists",
            snapshot_exists,
            f"Snapshot vivo encontrado en {FILES['utility_snapshot']}" if snapshot_exists else "No existe o no carga el snapshot de Utility U.",
            "Recalcular y persistir utility_u_latest.json.",
        ),
        _bool_check(
            "utility_gate_exists",
            gate_exists,
            f"Gate vivo encontrado en {FILES['utility_gate']}" if gate_exists else "No existe o no carga el gate vivo de Utility.",
            "Recalcular y persistir utility_u_promotion_gate_latest.json.",
        ),
        _bool_check(
            "utility_module_has_lifts",
            has_strategy_lift,
            "La fórmula de Utility incorpora strategy_lift y comparison_lift." if has_strategy_lift else "Utility todavía no incorpora lifts explícitos de estrategia/comparación.",
            "Agregar strategy_lift y comparison_lift a la fórmula de Utility.",
        ),
        _bool_check(
            "main_exposes_utility_route",
            '@app.get("/brain/utility"' in main_py,
            "El runtime expone /brain/utility." if '@app.get("/brain/utility"' in main_py else "No se encontró /brain/utility en main.py.",
            "Exponer /brain/utility en el runtime principal.",
        ),
        _bool_check(
            "main_exposes_utility_governance_status",
            '/brain/utility-governance/status' in main_py,
            "El runtime expone /brain/utility-governance/status." if '/brain/utility-governance/status' in main_py else "No existe endpoint de gobernanza de Utility.",
            "Agregar endpoint /brain/utility-governance/status.",
        ),
    ]

    accepted = all(item["passed"] for item in checks)
    blockers = list(utility_gate.get("blockers", []))
    failed_checks = [item for item in checks if not item["passed"]]
    top_strategy = ranking.get("top_strategy") or {}
    reference_strategy = (utility_snapshot.get("strategy_context") or {}).get("reference_strategy", {})
    effective_signal_score = (utility_snapshot.get("strategy_context") or {}).get("effective_signal_score")
    current_state = "accepted_baseline" if accepted else "needs_governance_baseline"
    work_status = "ready_for_utility_improvement" if accepted else "blocked_missing_baseline"
    pending_items = [
        "aumentar sensibilidad fina de Utility frente a mejoras pequeñas",
        "alinear ranking, freeze y contexto ganador sin incoherencias",
        "conectar mejor Utility con capital logic y promotion gates",
    ]
    if utility_gate.get("allow_promote"):
        pending_items.insert(0, "verificar si el promote actual de Utility resiste nueva muestra y comparación")

    contract = {
        "schema_version": "utility_governance_contract_v1",
        "updated_utc": _utc_now(),
        "domain_id": "utility_governance",
        "title": "Contrato canónico de Utility U",
        "goal": "mantener Utility U como criterio operativo interpretable, sensible y gobernable.",
        "accepted_baseline": accepted,
        "current_state": current_state,
        "failed_checks": [item["check_id"] for item in failed_checks],
        "active_blockers": blockers,
        "pending_improvement_items": pending_items,
    }

    roadmap = {
        "schema_version": "utility_governance_roadmap_v1",
        "updated_utc": _utc_now(),
        "roadmap_id": "brain_utility_governance_v1",
        "domain_id": "utility_governance",
        "mission": "llevar Utility U desde baseline operativo a función de evaluación fina y meta-gobernanza robusta.",
        "current_state": current_state,
        "work_status": work_status,
        "items": [
            {
                "item_id": "UG-01",
                "title": "Formalizar estado, spec y roadmap de Utility",
                "status": "done" if accepted else "active",
            },
            {
                "item_id": "UG-02",
                "title": "Alinear sensibilidad fina con ranking y contexto ganador",
                "status": "active" if accepted else "queued",
            },
            {
                "item_id": "UG-03",
                "title": "Conectar Utility con gates de capital y promoción más robustos",
                "status": "queued",
            },
        ],
    }

    status = {
        "schema_version": "utility_governance_status_v1",
        "updated_utc": _utc_now(),
        "domain_id": "utility_governance",
        "title": "Utility U Governance",
        "mission": "hacer que Utility U se gobierne y explique como dominio interno del Brain, no como número aislado.",
        "current_state": current_state,
        "work_status": work_status,
        "accepted_baseline": accepted,
        "acceptance_checks": checks,
        "failed_check_count": len(failed_checks),
        "u_proxy_score": utility_snapshot.get("u_proxy_score"),
        "effective_signal_score": effective_signal_score,
        "verdict": utility_gate.get("verdict") or utility_snapshot.get("promotion_gate", {}).get("verdict"),
        "allow_promote": utility_gate.get("allow_promote"),
        "blockers": blockers,
        "next_actions": utility_gate.get("required_next_actions", []) or ["improve_expectancy_or_reduce_penalties"],
        "pending_improvement_items": pending_items,
        "top_strategy_reference": {
            "strategy_id": top_strategy.get("strategy_id"),
            "promotion_state": top_strategy.get("promotion_state"),
            "context_governance_state": top_strategy.get("context_governance_state"),
            "expectancy": top_strategy.get("expectancy"),
            "context_expectancy": top_strategy.get("context_expectancy"),
        },
        "effective_reference_strategy": reference_strategy,
        "meta_brain_handoff": "\n".join([
            "domain=utility_governance",
            f"current_state={current_state}",
            f"work_status={work_status}",
            f"accepted_baseline={accepted}",
            f"u_proxy_score={utility_snapshot.get('u_proxy_score')}",
            f"effective_signal_score={effective_signal_score}",
            f"verdict={utility_gate.get('verdict')}",
            f"blockers={' | '.join(blockers) or 'none'}",
            f"top_strategy={top_strategy.get('strategy_id') or 'none'}",
            f"top_strategy_state={top_strategy.get('promotion_state') or 'none'}",
            f"effective_reference_strategy={reference_strategy.get('strategy_id') or 'none'}",
            f"next_actions={' | '.join(utility_gate.get('required_next_actions', []) or ['improve_expectancy_or_reduce_penalties'])}",
        ]),
        "evidence_paths": [
            str(FILES["utility_snapshot"]),
            str(FILES["utility_gate"]),
            str(FILES["autonomy_next_actions"]),
            str(FILES["ranking"]),
            str(FILES["spec"]),
            str(FILES["roadmap"]),
        ],
    }

    activation = {
        "schema_version": "utility_governance_activation_v1",
        "updated_utc": _utc_now(),
        "domain_id": "utility_governance",
        "activation_reason": "utility_governance_contract_synthesized" if accepted else "utility_governance_baseline_still_needs_work",
        "accepted_baseline": accepted,
        "u_proxy_score": utility_snapshot.get("u_proxy_score"),
        "verdict": utility_gate.get("verdict"),
    }

    write_json(FILES["spec"], spec)
    write_json(FILES["roadmap"], roadmap)
    write_json(FILES["contract"], contract)
    write_json(FILES["activation"], activation)
    write_json(FILES["status"], status)
    return status


def read_utility_governance_status() -> Dict[str, Any]:
    status = read_json(FILES["status"], {})
    if status:
        return status
    return refresh_utility_governance_status()
