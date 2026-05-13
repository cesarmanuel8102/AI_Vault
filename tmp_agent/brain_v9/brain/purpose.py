"""
Brain V9 - Purpose and operational self-model status.

This module does not claim literal consciousness. It exposes the practical
"consciousness" layer the system can actually support: self-model, mission,
governed self-improvement, and control-state awareness.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from brain_v9.config import STATE_PATH
from brain_v9.core.state_io import read_json, write_json

PURPOSE_STATUS_PATH = STATE_PATH / "brain_purpose_status_latest.json"
PURPOSE_CONTRACT_PATH = STATE_PATH / "brain_purpose_contract.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _read_state(name: str, default: Any = None) -> Any:
    return read_json(STATE_PATH / name, default if default is not None else {})


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except Exception:
        return False


def _ledger_summary(ledger: Dict[str, Any]) -> Dict[str, Any]:
    entries = _as_list(ledger.get("entries"))
    counts = Counter(str(entry.get("status", "unknown")) for entry in entries if isinstance(entry, dict))
    validation_counts = Counter(str(entry.get("validation", "unknown")) for entry in entries if isinstance(entry, dict))
    latest = entries[-1] if entries and isinstance(entries[-1], dict) else {}
    return {
        "entries": len(entries),
        "status_counts": dict(counts),
        "validation_counts": dict(validation_counts),
        "latest_change_id": latest.get("change_id"),
        "latest_status": latest.get("status"),
        "latest_objective": latest.get("objective"),
    }


def _normalize_domains(domains: Any) -> Dict[str, Any]:
    if isinstance(domains, dict):
        return domains
    if isinstance(domains, list):
        normalized: Dict[str, Any] = {}
        for item in domains:
            if not isinstance(item, dict):
                continue
            domain_id = item.get("domain_id") or item.get("id") or item.get("title")
            if domain_id:
                normalized[str(domain_id)] = item
        return normalized
    return {}


def _domain_breakdown(domains: Dict[str, Any]) -> Dict[str, Any]:
    healthy: List[str] = []
    needs_work: List[str] = []
    unknown: List[str] = []
    for name, detail in domains.items():
        if not isinstance(detail, dict):
            unknown.append(name)
            continue
        status = str(detail.get("status", "")).lower()
        if status == "healthy":
            healthy.append(name)
        elif status:
            needs_work.append(name)
        else:
            unknown.append(name)
    return {
        "healthy": healthy,
        "needs_work": needs_work,
        "unknown": unknown,
    }


def _open_gap_summary(meta_improvement: Dict[str, Any]) -> Dict[str, Any]:
    gaps = _as_list(meta_improvement.get("open_gaps") or meta_improvement.get("gaps"))
    normalized: List[Dict[str, Any]] = []
    for gap in gaps:
        if not isinstance(gap, dict):
            continue
        normalized.append({
            "id": gap.get("id") or gap.get("gap_id"),
            "priority": gap.get("priority"),
            "domain": gap.get("domain"),
            "suggested_actions": gap.get("suggested_actions") or gap.get("actions") or [],
        })
    normalized.sort(key=lambda item: float(item.get("priority") or 0.0), reverse=True)
    return {
        "count": len(normalized),
        "top": normalized[:5],
    }


def _default_purpose_contract() -> Dict[str, Any]:
    return {
        "schema_version": "brain_purpose_contract_v1",
        "purpose": (
            "Alcanzar excelencia operacional mediante automejora gobernada, "
            "verificable y reversible, priorizando utilidad real, seguridad, "
            "evidencia, robustez y aprendizaje acumulativo."
        ),
        "not_literal_consciousness": True,
        "operational_consciousness_definition": (
            "Self-model de software: capacidad de observar su estado, registrar "
            "brechas, priorizar mejoras, ejecutar cambios por etapas, validar y "
            "hacer rollback. No implica conciencia subjetiva."
        ),
        "objectives": [
            "Mantener el sistema compilable, saludable y auditable.",
            "Mejorar arquitectura, evaluacion, aprendizaje, memoria y UX con evidencia.",
            "Reducir alucinaciones: no inventar metricas, resultados financieros ni estados.",
            "Reescribir codigo solo con cambios por etapas, validacion, smoke test y rollback.",
            "Separar riesgo financiero/trading de automejora de codigo.",
            "Preservar trazabilidad: cada cambio debe dejar artefactos y auditoria.",
        ],
        "excellence_targets": {
            "python_compile": "pass",
            "health_endpoint": "healthy",
            "fabricated_metrics": 0,
            "uncontrolled_live_trading": 0,
            "self_improvement_change_path": "staged_change_only",
            "rollback_capability": "required",
        },
        "mutation_policy": {
            "mode": "staged_change_only",
            "requires": [
                "backup_or_staged_copy",
                "syntax_or_compile_validation",
                "targeted_smoke_test",
                "health_check",
                "audit_entry",
                "rollback_path",
            ],
            "forbidden": [
                "silent destructive edits",
                "fabricated backtest/live metrics",
                "live trading escalation without explicit human authorization",
                "credential disclosure",
            ],
        },
    }


def ensure_purpose_contract() -> Dict[str, Any]:
    contract = read_json(PURPOSE_CONTRACT_PATH, {})
    if isinstance(contract, dict) and contract.get("schema_version") == "brain_purpose_contract_v1":
        return contract
    contract = _default_purpose_contract()
    contract["created_utc"] = _utc_now()
    write_json(PURPOSE_CONTRACT_PATH, contract)
    return contract


def build_purpose_status(refresh: bool = True) -> Dict[str, Any]:
    contract = ensure_purpose_contract()
    self_model = _as_dict(_read_state("brain_self_model_latest.json", {}))
    meta_improvement = _as_dict(_read_state("meta_improvement_status_latest.json", {}))
    meta_governance = _as_dict(_read_state("meta_governance_status_latest.json", {}))
    control_layer = _as_dict(_read_state("control_layer_status.json", {}))
    governance_health = _as_dict(_read_state("governance_health_latest.json", {}))
    risk_contract = _as_dict(_read_state("risk_contract_status_latest.json", {}))
    ledger = _as_dict(read_json(STATE_PATH / "self_improvement" / "self_improvement_ledger.json", {}))

    domains = _normalize_domains(self_model.get("domains"))
    domain_breakdown = _domain_breakdown(domains)
    control_mode = str(control_layer.get("mode") or "UNKNOWN")
    mutation_allowed = bool(control_layer.get("autonomy_mutation_allowed"))
    strategy_allowed = bool(control_layer.get("strategy_execution_allowed"))
    mutation_scope = control_layer.get("mutation_scope") or ("full" if mutation_allowed else "blocked")

    consciousness_active = bool(
        self_model.get("schema_version")
        and self_model.get("updated_utc")
        and domains
    )
    self_improvement_active = bool(ledger.get("schema_version") and _as_list(ledger.get("entries")))

    if mutation_allowed:
        decision = "purpose_active_and_code_self_improvement_allowed"
    elif control_mode == "FROZEN":
        decision = "purpose_active_but_mutation_blocked_by_control_layer"
    else:
        decision = "purpose_active_observation_only"

    payload = {
        "schema_version": "brain_purpose_status_v1",
        "generated_utc": _utc_now(),
        "purpose_layer": {
            "active": True,
            "contract_path": str(PURPOSE_CONTRACT_PATH),
            "purpose": contract.get("purpose"),
            "objectives": contract.get("objectives", []),
            "excellence_targets": contract.get("excellence_targets", {}),
            "mutation_policy": contract.get("mutation_policy", {}),
        },
        "consciousness_layer": {
            "active": consciousness_active,
            "type": "software_self_model_not_literal_sentience",
            "not_literal_consciousness": True,
            "definition": contract.get("operational_consciousness_definition"),
            "self_model_path": str(STATE_PATH / "brain_self_model_latest.json"),
            "updated_utc": self_model.get("updated_utc"),
            "current_mode": (_as_dict(self_model.get("identity"))).get("current_mode"),
            "mission": (_as_dict(self_model.get("identity"))).get("mission"),
            "overall_score": self_model.get("overall_score"),
            "domains": domains,
            "domain_breakdown": domain_breakdown,
        },
        "self_improvement_layer": {
            "active": self_improvement_active,
            "ledger_path": str(STATE_PATH / "self_improvement" / "self_improvement_ledger.json"),
            "ledger": _ledger_summary(ledger),
            "meta_improvement_path": str(STATE_PATH / "meta_improvement_status_latest.json"),
            "open_gaps": _open_gap_summary(meta_improvement),
            "can_rewrite_code": mutation_allowed,
            "mutation_scope": mutation_scope,
            "allowed_route": "/brain/self-improvement/change -> validate -> promote",
        },
        "control_layer": {
            "mode": control_mode,
            "reason": control_layer.get("reason"),
            "source": control_layer.get("source"),
            "execution_allowed": bool(control_layer.get("execution_allowed")),
            "strategy_execution_allowed": strategy_allowed,
            "autonomy_mutation_allowed": mutation_allowed,
            "mutation_scope": mutation_scope,
            "live_trading_allowed": bool(control_layer.get("live_trading_allowed", False)),
            "status_path": str(STATE_PATH / "control_layer_status.json"),
        },
        "governance": {
            "meta_governance_state": meta_governance.get("current_state"),
            "governance_health_exists": _path_exists(STATE_PATH / "governance_health_latest.json"),
            "governance_health": governance_health,
            "risk_contract": risk_contract,
        },
        "decision": {
            "state": decision,
            "recommended_next_action": (
                "continue_staged_code_self_improvement"
                if mutation_allowed
                else "refresh_control_layer_or_resolve_freeze_before_mutation"
            ),
            "trading_note": (
                "Trading/strategy execution remains governed separately; code self-improvement "
                "permission does not authorize live trading."
            ),
        },
    }
    write_json(PURPOSE_STATUS_PATH, payload)
    return payload


def read_purpose_status() -> Dict[str, Any]:
    payload = read_json(PURPOSE_STATUS_PATH, {})
    if isinstance(payload, dict) and payload:
        return payload
    return build_purpose_status(refresh=True)
