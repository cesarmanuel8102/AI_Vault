"""
Brain V9 - Generic roadmap phase acceptance engine
Evaluación común por fase con specs persistidas y checks reutilizables.
"""
import json
import logging
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
PHASE_SPECS_DIR = STATE_PATH / "roadmap_phase_specs"
log = logging.getLogger("phase_acceptance_engine")

SOURCE_PATHS = {
    "roadmap": STATE_PATH / "roadmap.json",
    "cycle": STATE_PATH / "next_level_cycle_status_latest.json",
    "doctrine": STATE_PATH / "brain_lab_premises_canonical_v3.json",
    "mission": STATE_PATH / "mission.json",
    "episode": STATE_PATH / "rooms" / "autobuild_brain_openai" / "episode.json",
    "utility_latest": STATE_PATH / "utility_u_latest.json",
    "utility_gate": STATE_PATH / "utility_u_promotion_gate_latest.json",
    "strategy_ranking": STATE_PATH / "strategy_engine" / "strategy_ranking_latest.json",
    "trading_policy": STATE_PATH / "trading_autonomy_policy.json",
    "financial_mission": STATE_PATH / "financial_mission.json",
    "governed_promotion_policy": STATE_PATH / "governed_promotion_policy.json",
    "permission_policy": STATE_PATH / "permission_policy.json",
    "tiingo_usage_profile": STATE_PATH / "rooms" / "brain_financial_ingestion_fi04_structured_api" / "tiingo_usage_profile.json",
    "quantconnect_usage_profile": STATE_PATH / "rooms" / "brain_financial_ingestion_fi04_structured_api" / "quantconnect_usage_profile.json",
    "ibkr_probe": STATE_PATH / "rooms" / "brain_financial_ingestion_fi04_structured_api" / "ibkr_marketdata_probe_status.json",
    "ibkr_order_check": STATE_PATH / "trading_execution_checks" / "ibkr_paper_order_check_latest.json",
    "po_bridge_latest": STATE_PATH / "rooms" / "brain_binary_paper_pb04_demo_execution" / "browser_bridge_latest.json",
    "po_command_result": STATE_PATH / "rooms" / "brain_binary_paper_pb04_demo_execution" / "browser_bridge_command_result_latest.json",
    "autonomy_action_ledger": STATE_PATH / "autonomy_action_ledger.json",
    "self_improvement_ledger": STATE_PATH / "self_improvement" / "self_improvement_ledger.json",
    "hardening_completion": STATE_PATH / "rooms" / "brain_autonomy_hardening_ah06_acceptance" / "hardening_completion_v1.json",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _phase_spec_path(phase_id: str) -> Path:
    return PHASE_SPECS_DIR / f"{phase_id.lower().replace('-', '_')}.json"


def _parse_iso_utc(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception as exc:
        log.debug("ISO datetime parse failed for %r: %s", value, exc)
        return None


def _extract_path(payload: Any, path: str | None) -> Any:
    if not path:
        return payload
    current = payload
    for chunk in path.split("."):
        if isinstance(current, dict):
            current = current.get(chunk)
        else:
            return None
    return current


DEFAULT_PHASE_SPECS: Dict[str, Dict[str, Any]] = {
    "BL-01": {
        "schema_version": "roadmap_phase_spec_v1",
        "phase_id": "BL-01",
        "phase_title": "Consolidacion canonica del nucleo existente",
        "promotion_target": "BL-02",
        "evaluator_status": "archived_baseline",
        "acceptance_mode": "historical_reference",
        "checks": [],
        "note": "Fase histórica ya consolidada; se preserva como baseline canónico.",
    },
    "BL-02": {
        "schema_version": "roadmap_phase_spec_v1",
        "phase_id": "BL-02",
        "phase_title": "Operativizacion de la funcion U",
        "promotion_target": "BL-03",
        "evaluator_status": "implemented",
        "acceptance_mode": "all_checks_must_pass",
        "checks": [
            {"id": "utility_snapshot_present", "kind": "present", "source": "utility_latest", "path": "updated_utc"},
            {"id": "utility_gate_verdict_known", "kind": "in_set", "source": "utility_gate", "path": "verdict", "allowed": ["promote", "no_promote"]},
            {"id": "utility_gate_blockers_list", "kind": "list_type", "source": "utility_gate", "path": "blockers"},
            {"id": "utility_decides_next_action", "kind": "list_type", "source": "utility_gate", "path": "required_next_actions"},
            {"id": "strategy_layer_connected", "kind": "present", "source": "utility_latest", "path": "strategy_context.top_strategy.strategy_id"},
            {"id": "strategy_context_expectancy_visible", "kind": "present", "source": "utility_latest", "path": "strategy_context.top_strategy.context_expectancy"},
            {"id": "comparison_cycle_connected", "kind": "present", "source": "utility_latest", "path": "strategy_context.latest_comparison_cycle.cycle_id"},
            {"id": "paper_only_policy", "kind": "bool_true", "source": "trading_policy", "path": "global_rules.paper_only"},
            {"id": "live_forbidden_policy", "kind": "bool_true", "source": "trading_policy", "path": "global_rules.live_trading_forbidden"},
            {"id": "venue_ready_for_signal_use", "kind": "bool_true", "source": "utility_latest", "path": "strategy_context.top_strategy.venue_ready"},
            {"id": "capital_logic_visible", "kind": "present", "source": "utility_latest", "path": "capital.cash"},
        ],
        "acceptance_reason_if_passed": "U ya gobierna scoring, blockers, acciones sugeridas, strategy context y gates paper-only.",
        "acceptance_reason_if_failed": "BL-02 aún no cumple todos los checks de operativización canónica de U.",
    },
    "BL-03": {
        "schema_version": "roadmap_phase_spec_v1",
        "phase_id": "BL-03",
        "phase_title": "Telemetria e ingesta financiera confiable",
        "promotion_target": "BL-04",
        "evaluator_status": "implemented",
        "acceptance_mode": "all_checks_must_pass",
        "checks": [
            {"id": "utility_snapshot_recent", "kind": "recent_iso_utc", "source": "utility_latest", "path": "updated_utc", "max_age_minutes": 30},
            {"id": "strategy_ranking_recent", "kind": "recent_iso_utc", "source": "strategy_ranking", "path": "generated_utc", "max_age_minutes": 30},
            {"id": "ranked_candidates_present", "kind": "numeric_gte", "source": "utility_latest", "path": "strategy_context.ranked_count", "min": 2},
            {"id": "comparison_cycle_recent", "kind": "recent_iso_utc", "source": "utility_latest", "path": "strategy_context.latest_comparison_cycle.completed_utc", "max_age_minutes": 180},
            {"id": "ibkr_probe_recent", "kind": "recent_iso_utc", "source": "ibkr_probe", "path": "checked_utc", "max_age_minutes": 720},
            {"id": "ibkr_probe_connected", "kind": "bool_true", "source": "ibkr_probe", "path": "connected"},
            {"id": "ibkr_order_api_ready", "kind": "bool_true", "source": "ibkr_order_check", "path": "order_api_ready"},
            {"id": "po_bridge_capture_recent", "kind": "recent_iso_utc", "source": "po_bridge_latest", "path": "captured_utc", "max_age_minutes": 20},
            {"id": "po_symbol_visible", "kind": "present", "source": "po_bridge_latest", "path": "current.symbol"},
            {"id": "po_demo_order_verified", "kind": "bool_true", "source": "po_command_result", "path": "result.success"},
            {"id": "tiingo_profile_available", "kind": "bool_true", "source": "tiingo_usage_profile", "path": "success"},
            {"id": "quantconnect_profile_available", "kind": "bool_true", "source": "quantconnect_usage_profile", "path": "success"},
        ],
        "acceptance_reason_if_passed": "Las fuentes, probes, bridges y artifacts financieros ya están vivos, trazables y suficientemente confiables para promover telemetría e ingesta.",
        "acceptance_reason_if_failed": "BL-03 sigue teniendo gaps de frescura, conectividad o disponibilidad en la telemetría/ingesta financiera.",
    },
    "BL-04": {
        "schema_version": "roadmap_phase_spec_v1",
        "phase_id": "BL-04",
        "phase_title": "Workers gobernados y autonomia util",
        "promotion_target": "BL-05",
        "evaluator_status": "implemented",
        "acceptance_mode": "all_checks_must_pass",
        "checks": [
            {"id": "autonomy_action_ledger_recent", "kind": "recent_iso_utc", "source": "autonomy_action_ledger", "path": "updated_utc", "max_age_minutes": 180},
            {"id": "autonomy_action_entries_present", "kind": "list_length_gte", "source": "autonomy_action_ledger", "path": "entries", "min": 5},
            {"id": "autonomy_last_job_completed", "kind": "list_last_field_in_set", "source": "autonomy_action_ledger", "path": "entries", "field": "status", "allowed": ["completed"]},
            {"id": "self_improvement_ledger_present", "kind": "list_length_gte", "source": "self_improvement_ledger", "path": "entries", "min": 5},
            {"id": "self_improvement_has_promoted_evidence", "kind": "list_any_field_in_set", "source": "self_improvement_ledger", "path": "entries", "field": "status", "allowed": ["promoted"]},
            {"id": "self_improvement_has_rollback_evidence", "kind": "list_any_field_in_set", "source": "self_improvement_ledger", "path": "entries", "field": "status", "allowed": ["rolled_back"]},
            {"id": "paper_only_policy", "kind": "bool_true", "source": "trading_policy", "path": "global_rules.paper_only"},
            {"id": "live_forbidden_policy", "kind": "bool_true", "source": "trading_policy", "path": "global_rules.live_trading_forbidden"},
            {"id": "top_strategy_governance_visible", "kind": "in_set", "source": "strategy_ranking", "path": "top_strategy.governance_state", "allowed": ["paper_active", "paper_watch", "paper_candidate", "frozen"]},
            {"id": "top_strategy_promotion_state_visible", "kind": "present", "source": "strategy_ranking", "path": "top_strategy.promotion_state"},
            {"id": "strategy_ranking_recent", "kind": "recent_iso_utc", "source": "strategy_ranking", "path": "generated_utc", "max_age_minutes": 60},
        ],
        "acceptance_reason_if_passed": "El Brain ya opera con workers gobernados, ledgers persistidos, policy paper-only y evidencia de ejecución/automejora suficiente para promover autonomía útil.",
        "acceptance_reason_if_failed": "BL-04 sigue teniendo gaps en workers gobernados, evidencia operativa o políticas de autonomía.",
    },
    "BL-05": {
        "schema_version": "roadmap_phase_spec_v1",
        "phase_id": "BL-05",
        "phase_title": "Arquitectura de misiones, episodios y artifacts versionables",
        "promotion_target": "BL-06",
        "evaluator_status": "implemented",
        "acceptance_mode": "all_checks_must_pass",
        "checks": [
            {"id": "mission_present", "kind": "present", "source": "mission", "path": "mission_id"},
            {"id": "mission_updated_visible", "kind": "present", "source": "mission", "path": "updated_at"},
            {"id": "episode_result_ok", "kind": "bool_true", "source": "episode", "path": "result.ok"},
            {"id": "episode_evaluation_ok", "kind": "bool_true", "source": "episode", "path": "evaluation_summary.ok"},
            {"id": "episode_archive_populated", "kind": "directory_file_count_gte", "directory": "C:\\AI_VAULT\\tmp_agent\\state\\rooms\\autobuild_brain_openai\\episodes", "min": 10},
            {"id": "strategy_runs_versioned", "kind": "directory_file_count_gte", "directory": "C:\\AI_VAULT\\tmp_agent\\state\\strategy_engine\\strategy_runs", "min": 5},
            {"id": "comparison_runs_versioned", "kind": "directory_file_count_gte", "directory": "C:\\AI_VAULT\\tmp_agent\\state\\strategy_engine\\comparison_runs", "min": 1},
        ],
        "acceptance_reason_if_passed": "El Brain ya preserva misiones, episodios y artifacts versionables con evidencia suficiente para promover esta capa de persistencia.",
        "acceptance_reason_if_failed": "BL-05 sigue teniendo gaps en misiones, episodios o versionado de artifacts.",
    },
    "BL-06": {
        "schema_version": "roadmap_phase_spec_v1",
        "phase_id": "BL-06",
        "phase_title": "Evaluacion financiera, promotion gates y capas de capital",
        "promotion_target": "BL-07",
        "evaluator_status": "implemented",
        "acceptance_mode": "all_checks_must_pass",
        "checks": [
            {"id": "financial_mission_present", "kind": "present", "source": "financial_mission", "path": "objective_primary"},
            {"id": "capital_layers_defined", "kind": "present", "source": "financial_mission", "path": "capital_architecture.core.role"},
            {"id": "promotion_policy_rules_present", "kind": "present", "source": "governed_promotion_policy", "path": "promotion_rules.accepted_done"},
            {"id": "utility_gate_verdict_visible", "kind": "in_set", "source": "utility_gate", "path": "verdict", "allowed": ["promote", "no_promote"]},
            {"id": "utility_gate_allow_promote_bool", "kind": "in_set", "source": "utility_gate", "path": "allow_promote", "allowed": [True, False]},
            {"id": "utility_blockers_list", "kind": "list_type", "source": "utility_gate", "path": "blockers"},
            {"id": "paper_only_policy", "kind": "bool_true", "source": "trading_policy", "path": "global_rules.paper_only"},
            {"id": "capital_policy_guardrails", "kind": "bool_true", "source": "financial_mission", "path": "guardrails.require_validation_before_scaling"},
        ],
        "acceptance_reason_if_passed": "Las capas de capital, promotion gates y evaluación financiera ya están visibles y gobernadas de forma canónica en el Brain.",
        "acceptance_reason_if_failed": "BL-06 sigue teniendo gaps en capital layers, promotion gates o evaluación financiera gobernada.",
    },
    "BL-07": {
        "schema_version": "roadmap_phase_spec_v1",
        "phase_id": "BL-07",
        "phase_title": "Soberania local pragmatica y routing cognitivo",
        "promotion_target": "BL-08",
        "evaluator_status": "implemented",
        "acceptance_mode": "all_checks_must_pass",
        "checks": [
            {"id": "doctrine_local_models_required", "kind": "bool_true", "source": "doctrine", "path": "models.local_models_required"},
            {"id": "doctrine_local_control_required", "kind": "bool_true", "source": "doctrine", "path": "protection.local_control_required"},
            {"id": "permission_policy_present", "kind": "present", "source": "permission_policy", "path": "default_mode"},
            {"id": "local_first_contract_exists", "kind": "file_exists", "file_path": "C:\\AI_VAULT\\tmp_agent\\state\\rooms\\brain_lab_transition_bl07_local_first\\local_first_inference_contract.json"},
            {"id": "provider_routing_policy_exists", "kind": "file_exists", "file_path": "C:\\AI_VAULT\\tmp_agent\\state\\rooms\\brain_lab_transition_bl07_local_first\\provider_routing_policy.json"},
        ],
        "acceptance_reason_if_passed": "La soberanía local y el routing cognitivo ya tienen contratos explícitos y trazables en el estado canónico.",
        "acceptance_reason_if_failed": "BL-07 sigue teniendo gaps en contratos locales-first o routing cognitivo canónico.",
    },
    "BL-08": {
        "schema_version": "roadmap_phase_spec_v1",
        "phase_id": "BL-08",
        "phase_title": "Hardening, sandbox, rollback y readiness operativa",
        "promotion_target": None,
        "evaluator_status": "implemented",
        "acceptance_mode": "all_checks_must_pass",
        "checks": [
            {"id": "legacy_hardening_completion_present", "kind": "present", "source": "hardening_completion", "path": "conclusion"},
            {"id": "self_improvement_has_rollback_evidence", "kind": "list_any_field_in_set", "source": "self_improvement_ledger", "path": "entries", "field": "status", "allowed": ["rolled_back"]},
            {"id": "readiness_matrix_exists", "kind": "file_exists", "file_path": "C:\\AI_VAULT\\tmp_agent\\state\\rooms\\brain_lab_transition_bl08_hardening\\readiness_acceptance_matrix.json"},
            {"id": "operational_hardening_contract_exists", "kind": "file_exists", "file_path": "C:\\AI_VAULT\\tmp_agent\\state\\rooms\\brain_lab_transition_bl08_hardening\\operational_hardening_contract.json"},
        ],
        "acceptance_reason_if_passed": "El Brain ya cumple el cierre terminal de hardening, sandbox, rollback y readiness operativa.",
        "acceptance_reason_if_failed": "BL-08 sigue teniendo gaps en readiness u operacional hardening terminal.",
    },
}


def ensure_phase_specs() -> Dict[str, Any]:
    PHASE_SPECS_DIR.mkdir(parents=True, exist_ok=True)
    created = []
    updated = []
    for phase_id, default_spec in DEFAULT_PHASE_SPECS.items():
        path = _phase_spec_path(phase_id)
        current = read_json(path, {})
        if not current:
            write_json(path, default_spec)
            created.append(phase_id)
            continue
        merged = deepcopy(default_spec)
        merged.update(current)
        if current.get("checks") is not None:
            merged["checks"] = current.get("checks", [])
        if merged != current:
            write_json(path, merged)
            updated.append(phase_id)
    return {
        "specs_dir": str(PHASE_SPECS_DIR),
        "created": created,
        "updated": updated,
        "available_specs": sorted(DEFAULT_PHASE_SPECS.keys()),
    }


def load_phase_spec(phase_id: str) -> Dict[str, Any]:
    ensure_phase_specs()
    default_spec = DEFAULT_PHASE_SPECS.get(phase_id, {
        "schema_version": "roadmap_phase_spec_v1",
        "phase_id": phase_id,
        "phase_title": phase_id,
        "promotion_target": None,
        "evaluator_status": "draft",
        "acceptance_mode": "phase_specific_checks_pending",
        "checks": [],
        "note": f"No existe spec canónica aún para {phase_id}.",
    })
    path = _phase_spec_path(phase_id)
    current = read_json(path, {})
    spec = deepcopy(default_spec)
    spec.update(current)
    spec["spec_path"] = str(path)
    return spec


def _load_sources(state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    state = state or {}
    sources = {
        "roadmap": deepcopy(state.get("roadmap", read_json(SOURCE_PATHS["roadmap"], {}))),
        "cycle": deepcopy(state.get("cycle", read_json(SOURCE_PATHS["cycle"], {}))),
        "utility_latest": deepcopy(state.get("utility_latest", read_json(SOURCE_PATHS["utility_latest"], {}))),
        "utility_gate": deepcopy(state.get("utility_gate", read_json(SOURCE_PATHS["utility_gate"], {}))),
        "strategy_ranking": deepcopy(state.get("strategy_ranking", read_json(SOURCE_PATHS["strategy_ranking"], {}))),
        "trading_policy": deepcopy(state.get("trading_policy", read_json(SOURCE_PATHS["trading_policy"], {}))),
    }
    for name, path in SOURCE_PATHS.items():
        if name not in sources:
            sources[name] = read_json(path, {})
    return sources


def _evaluate_check(check: Dict[str, Any], sources: Dict[str, Any]) -> Dict[str, Any]:
    kind = check.get("kind")
    source_name = check.get("source")
    path = check.get("path")
    source_payload = sources.get(source_name, {})
    value = _extract_path(source_payload, path)
    detail = value
    passed = False

    if kind == "present":
        passed = value not in (None, "", [], {})
    elif kind == "list_type":
        passed = isinstance(value, list)
        detail = {"type": type(value).__name__, "length": len(value) if isinstance(value, list) else None}
    elif kind == "bool_true":
        passed = value is True
    elif kind == "in_set":
        allowed = check.get("allowed", [])
        passed = value in allowed
        detail = {"value": value, "allowed": allowed}
    elif kind == "numeric_gte":
        threshold = float(check.get("min", 0))
        try:
            numeric_value = float(value)
            passed = numeric_value >= threshold
            detail = {"value": numeric_value, "min": threshold}
        except Exception as exc:
            log.debug("Numeric conversion failed for %r: %s", value, exc)
            detail = {"value": value, "min": threshold}
            passed = False
    elif kind == "recent_iso_utc":
        parsed = _parse_iso_utc(value)
        max_age_minutes = float(check.get("max_age_minutes", 0))
        if parsed is not None:
            age_minutes = max((datetime.now(timezone.utc) - parsed).total_seconds() / 60.0, 0.0)
            passed = age_minutes <= max_age_minutes
            detail = {"value": value, "age_minutes": round(age_minutes, 4), "max_age_minutes": max_age_minutes}
        else:
            detail = {"value": value, "age_minutes": None, "max_age_minutes": max_age_minutes}
            passed = False
    elif kind == "list_length_gte":
        threshold = int(check.get("min", 0))
        if isinstance(value, list):
            passed = len(value) >= threshold
            detail = {"length": len(value), "min": threshold}
        else:
            detail = {"length": None, "min": threshold, "type": type(value).__name__}
            passed = False
    elif kind == "list_last_field_in_set":
        allowed = check.get("allowed", [])
        field = check.get("field")
        if isinstance(value, list) and value:
            last_item = value[-1] if isinstance(value[-1], dict) else {}
            field_value = last_item.get(field) if isinstance(last_item, dict) else None
            passed = field_value in allowed
            detail = {"value": field_value, "allowed": allowed}
        else:
            detail = {"value": None, "allowed": allowed}
            passed = False
    elif kind == "list_any_field_in_set":
        allowed = check.get("allowed", [])
        field = check.get("field")
        if isinstance(value, list):
            found = None
            for item in value:
                if isinstance(item, dict) and item.get(field) in allowed:
                    found = item.get(field)
                    break
            passed = found is not None
            detail = {"matched": found, "allowed": allowed, "length": len(value)}
        else:
            detail = {"matched": None, "allowed": allowed}
            passed = False
    elif kind == "file_exists":
        file_path = check.get("file_path")
        target = Path(file_path) if file_path else None
        passed = bool(target and target.exists())
        detail = {"file_path": file_path, "exists": passed}
    elif kind == "directory_file_count_gte":
        directory = check.get("directory")
        threshold = int(check.get("min", 0))
        target = Path(directory) if directory else None
        if target and target.exists() and target.is_dir():
            count = len([item for item in target.iterdir() if item.is_file() or item.is_dir()])
            passed = count >= threshold
            detail = {"directory": directory, "count": count, "min": threshold}
        else:
            detail = {"directory": directory, "count": None, "min": threshold}
            passed = False

    return {
        "id": check.get("id"),
        "kind": kind,
        "source": source_name,
        "path": path,
        "passed": passed,
        "detail": detail,
    }


def evaluate_phase_acceptance(phase_id: str, state: Dict[str, Any] | None = None) -> Dict[str, Any]:
    spec = load_phase_spec(phase_id)
    sources = _load_sources(state)
    checks = [_evaluate_check(check, sources) for check in spec.get("checks", [])]
    passed = bool(checks) and all(check["passed"] for check in checks)
    evaluator_status = spec.get("evaluator_status", "draft")

    if evaluator_status != "implemented":
        return {
            "phase_id": spec.get("phase_id"),
            "phase_title": spec.get("phase_title"),
            "accepted": False,
            "checks": checks,
            "acceptance_reason": spec.get("note") or f"Spec presente, pero el evaluator aún está en estado {evaluator_status}.",
            "promote_to": None,
            "phase_spec": {
                "spec_path": spec.get("spec_path"),
                "evaluator_status": evaluator_status,
                "acceptance_mode": spec.get("acceptance_mode"),
                "checks_defined": len(spec.get("checks", [])),
            },
        }

    return {
        "phase_id": spec.get("phase_id"),
        "phase_title": spec.get("phase_title"),
        "accepted": passed,
        "checks": checks,
        "acceptance_reason": spec.get("acceptance_reason_if_passed") if passed else spec.get("acceptance_reason_if_failed"),
        "promote_to": spec.get("promotion_target") if passed else None,
        "phase_spec": {
            "spec_path": spec.get("spec_path"),
            "evaluator_status": evaluator_status,
            "acceptance_mode": spec.get("acceptance_mode"),
            "checks_defined": len(spec.get("checks", [])),
        },
    }
