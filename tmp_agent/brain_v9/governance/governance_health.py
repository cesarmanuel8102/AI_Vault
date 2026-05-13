"""
Brain V9 — Canonical governance health.

Turns Section 20 suggestions into a live, auditable runtime view:
- layer composition V3-V8
- governance health summary
- improvement suggestion status
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain_v9.brain.control_layer import build_control_layer_status, get_control_layer_status_latest
from brain_v9.brain.meta_governance import build_meta_governance_status, get_meta_governance_status_latest
from brain_v9.brain.risk_contract import build_risk_contract_status, read_risk_contract_status
from brain_v9.brain.self_improvement import get_self_improvement_ledger
from brain_v9.brain.utility import read_utility_state, write_utility_snapshots
from brain_v9.config import STATE_PATH
from brain_v9.core.state_io import read_json, write_json
from brain_v9.governance.change_validation import build_change_validation_status, read_change_validation_status
from brain_v9.trading.post_trade_hypotheses import read_post_trade_hypothesis_snapshot
from brain_v9.trading.strategy_engine import read_edge_validation_state


GOVERNANCE_HEALTH_PATH = STATE_PATH / "governance_health_latest.json"
SESSION_MEMORY_PATH = STATE_PATH / "session_memory.json"
LAYER_COMPOSITION_PATH = Path(__file__).resolve().parent / "layer_composition.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_layer_composition() -> Dict[str, Any]:
    with LAYER_COMPOSITION_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _rollbacks_last_days(days: int = 7) -> int:
    ledger = get_self_improvement_ledger()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    count = 0
    for entry in ledger.get("entries", []):
        timestamp = entry.get("timestamp")
        if not timestamp:
            continue
        try:
            ts = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        except ValueError:
            log.debug("Skipping ledger entry with unparseable timestamp: %s", timestamp)
            continue
        if ts >= cutoff and entry.get("rollback"):
            count += 1
    return count


def _operating_mode(
    *,
    control: Dict[str, Any],
    risk: Dict[str, Any],
    edge: Dict[str, Any],
    utility: Dict[str, Any],
    post_trade: Dict[str, Any],
) -> str:
    edge_summary = edge.get("summary") or {}
    validated = int(edge_summary.get("validated_count", 0) or 0)
    promotable = int(edge_summary.get("promotable_count", 0) or 0)
    probation = int(edge_summary.get("probation_count", 0) or 0)
    u_score = float(utility.get("u_score", utility.get("u_proxy_score", 0.0)) or 0.0)
    if str(control.get("mode")).upper() == "FROZEN":
        return "frozen"
    if (validated > 0 or promotable > 0) and u_score > 0 and bool(risk.get("execution_allowed", False)):
        return "edge_validated"
    if probation > 0 or bool((post_trade.get("summary") or {}).get("recent_resolved_trades", 0)):
        return "learning_active"
    if str(risk.get("status", "")).lower() in {"critical", "degraded"}:
        return "paper_strict"
    return "paper_mode"


def _layer_health(
    layer_id: str,
    *,
    included: bool,
    control: Dict[str, Any],
    change_validation: Dict[str, Any],
    risk: Dict[str, Any],
    meta: Dict[str, Any],
    post_trade: Dict[str, Any],
    session_memory: Dict[str, Any],
    edge: Dict[str, Any],
) -> Dict[str, Any]:
    if layer_id == "V3":
        healthy = bool(control)
        reason = control.get("mode", "unknown")
    elif layer_id == "V4":
        summary = change_validation.get("summary") or {}
        healthy = bool(summary.get("last_run_utc"))
        reason = summary.get("last_pipeline_state", "pending")
    elif layer_id == "V5":
        healthy = str(risk.get("status", "")).lower() != "critical"
        reason = risk.get("status", "unknown")
    elif layer_id == "V6":
        healthy = bool(meta.get("top_priority")) or bool(meta.get("current_focus"))
        reason = (meta.get("top_priority") or {}).get("action") or "no_priority"
    elif layer_id == "V7":
        healthy = bool(post_trade.get("summary")) and bool(session_memory)
        reason = (post_trade.get("summary") or {}).get("next_focus") or session_memory.get("current_focus") or "no_feedback"
    else:
        edge_summary = edge.get("summary") or {}
        healthy = int(edge_summary.get("validated_count", 0) or 0) > 0 or int(edge_summary.get("promotable_count", 0) or 0) > 0
        reason = f"validated={int(edge_summary.get('validated_count', 0) or 0)} promotable={int(edge_summary.get('promotable_count', 0) or 0)}"

    if included and healthy:
        state = "active"
    elif included or healthy:
        state = "partial"
    else:
        state = "inactive"
    return {"state": state, "included_in_mode": included, "reason": reason}


def _improvement_status() -> List[Dict[str, Any]]:
    return [
        {"id": 1, "title": "change_validation.py como módulo real", "status": "implemented"},
        {"id": 2, "title": "Secrets Manager real con python-dotenv", "status": "partial"},
        {"id": 3, "title": "Tests de integración del loop autónomo", "status": "partial"},
        {"id": 4, "title": "Protocolo de composición de capas V3-V8", "status": "implemented"},
        {"id": 5, "title": "Dashboard de salud de gobernanza", "status": "implemented"},
        {"id": 6, "title": "Log rotation automática", "status": "implemented"},
        {"id": 7, "title": "Scoring de calidad del ADN", "status": "implemented"},
        {"id": 8, "title": "Simulador de edge antes de paper", "status": "implemented"},
        {"id": 9, "title": "Explicabilidad de decisiones", "status": "implemented"},
        {"id": 10, "title": "Protocolo de upgrade de Brain", "status": "implemented"},
        {"id": 11, "title": "Ethics kernel integrado en el loop", "status": "implemented"},
    ]


def build_governance_health(refresh: bool = False) -> Dict[str, Any]:
    composition = _load_layer_composition()
    utility = (write_utility_snapshots().get("snapshot") if refresh else None) or read_utility_state()
    control = build_control_layer_status(refresh_change_scorecard=True) if refresh else get_control_layer_status_latest()
    meta = build_meta_governance_status() if refresh else get_meta_governance_status_latest()
    risk = build_risk_contract_status(refresh=True) if refresh else read_risk_contract_status()
    edge = read_edge_validation_state()
    post_trade = read_post_trade_hypothesis_snapshot()
    session_memory = read_json(SESSION_MEMORY_PATH, {})
    change_validation = build_change_validation_status(refresh_scorecard=True) if refresh else read_change_validation_status()

    mode = _operating_mode(
        control=control,
        risk=risk,
        edge=edge,
        utility=utility,
        post_trade=post_trade,
    )
    active_layers = list((composition.get("modes") or {}).get(mode, []))
    layers = {}
    for layer_id, meta_layer in (composition.get("layers") or {}).items():
        layers[layer_id] = {
            "name": meta_layer.get("name"),
            "description": meta_layer.get("description"),
            **_layer_health(
                layer_id,
                included=layer_id in active_layers,
                control=control,
                change_validation=change_validation,
                risk=risk,
                meta=meta,
                post_trade=post_trade,
                session_memory=session_memory if isinstance(session_memory, dict) else {},
                edge=edge,
            ),
        }

    rollbacks_7d = _rollbacks_last_days(7)
    overall_status = "healthy"
    if str(control.get("mode")).upper() == "FROZEN" or str(risk.get("status", "")).lower() == "critical":
        overall_status = "critical"
    elif any(layer.get("state") == "partial" for layer in layers.values()):
        overall_status = "degraded"

    suggestions = _improvement_status()
    payload = {
        "schema_version": "governance_health_v1",
        "generated_utc": _utc_now(),
        "overall_status": overall_status,
        "current_operating_mode": mode,
        "layer_composition": {
            "active_layers": active_layers,
            "available_modes": composition.get("modes") or {},
        },
        "layers": layers,
        "change_validation": change_validation.get("summary") or {},
        "rollbacks_last_7d": rollbacks_7d,
        "kill_switch": {
            "mode": control.get("mode"),
            "active": str(control.get("mode")).upper() == "FROZEN",
            "reason": control.get("reason"),
        },
        "improvement_suggestions": suggestions,
        "improvement_summary": {
            "implemented_count": sum(1 for item in suggestions if item["status"] == "implemented"),
            "partial_count": sum(1 for item in suggestions if item["status"] == "partial"),
            "pending_count": sum(1 for item in suggestions if item["status"] == "pending"),
        },
    }
    write_json(GOVERNANCE_HEALTH_PATH, payload)
    return payload


def read_governance_health() -> Dict[str, Any]:
    payload = read_json(GOVERNANCE_HEALTH_PATH, {})
    if isinstance(payload, dict) and payload:
        return payload
    return build_governance_health(refresh=False)
