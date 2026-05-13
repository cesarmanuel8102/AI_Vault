"""
Brain V9 — Canonical Control Layer / Kill Switch
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from brain_v9.brain.change_control import build_change_scorecard, get_change_scorecard_latest
from brain_v9.brain.utility import read_utility_state
from brain_v9.config import AGENT_EVENTS_LOG_PATH, CONTROL_LAYER_STATUS_PATH
from brain_v9.core.state_io import append_ndjson, read_json, write_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_existing() -> Dict[str, Any]:
    payload = read_json(CONTROL_LAYER_STATUS_PATH, {})
    return payload if isinstance(payload, dict) else {}


def _manual_override(existing: Dict[str, Any]) -> Dict[str, Any]:
    override = existing.get("manual_override") or {}
    return override if isinstance(override, dict) else {}


def _derive_mode(change_scorecard: Dict[str, Any], utility: Dict[str, Any], manual_override: Dict[str, Any]) -> Dict[str, Any]:
    if manual_override.get("active"):
        return {
            "mode": "FROZEN",
            "reason": manual_override.get("reason") or "manual_override",
            "source": manual_override.get("source", "user"),
        }
    summary = change_scorecard.get("summary") or {}
    if summary.get("critical_recent_failures", 0) >= 3:
        return {
            "mode": "FROZEN",
            "reason": "critical_recent_change_failures",
            "source": "automatic",
        }
    return {
        "mode": "ACTIVE",
        "reason": "no_control_trigger",
        "source": "automatic",
    }


def build_control_layer_status(refresh_change_scorecard: bool = False) -> Dict[str, Any]:
    existing = _load_existing()
    manual_override = _manual_override(existing)
    change_scorecard = build_change_scorecard() if refresh_change_scorecard else get_change_scorecard_latest()
    utility = read_utility_state()
    mode_info = _derive_mode(change_scorecard, utility, manual_override)
    summary = change_scorecard.get("summary", {}) if isinstance(change_scorecard, dict) else {}
    reason = str(mode_info.get("reason", ""))
    source = str(mode_info.get("source", ""))
    frozen = mode_info["mode"] == "FROZEN"
    trading_risk_freeze = reason.startswith("risk_contract_violation")
    manual_risk_freeze = manual_override.get("active") and trading_risk_freeze
    critical_failures = int(summary.get("critical_recent_failures", 0) or 0)

    # A financial/trading freeze must not automatically block code quality work.
    # Keep strategy/live execution frozen, but allow staged code self-improvement
    # when the freeze reason is explicitly trading-risk related and change
    # control has no critical failure streak.
    autonomy_mutation_allowed = (
        (not frozen) or (trading_risk_freeze and critical_failures < 3)
    )
    if autonomy_mutation_allowed and frozen and (trading_risk_freeze or manual_risk_freeze):
        mutation_scope = "code_self_improvement_only"
    elif autonomy_mutation_allowed:
        mutation_scope = "full"
    else:
        mutation_scope = "blocked"

    payload = {
        "schema_version": "control_layer_status_v1",
        "generated_utc": _utc_now(),
        "mode": mode_info["mode"],
        "reason": mode_info["reason"],
        "source": mode_info["source"],
        "manual_override": manual_override,
        "execution_allowed": not frozen,
        "strategy_execution_allowed": not frozen,
        "live_trading_allowed": False if frozen else None,
        "autonomy_mutation_allowed": autonomy_mutation_allowed,
        "mutation_scope": mutation_scope,
        "scope_reason": (
            "trading_risk_freeze_does_not_block_staged_code_self_improvement"
            if mutation_scope == "code_self_improvement_only"
            else reason
        ),
        "change_control_summary": summary,
        "utility_summary": {
            "u_score": utility.get("u_score", utility.get("u_proxy_score")),
            "verdict": utility.get("verdict"),
            "blockers": utility.get("blockers", []),
        },
    }
    write_json(CONTROL_LAYER_STATUS_PATH, payload)
    return payload


def get_control_layer_status_latest() -> Dict[str, Any]:
    payload = read_json(CONTROL_LAYER_STATUS_PATH, {})
    if isinstance(payload, dict) and payload:
        return payload
    return build_control_layer_status()


def freeze_control_layer(reason: str, source: str = "user") -> Dict[str, Any]:
    existing = _load_existing()
    existing["manual_override"] = {
        "active": True,
        "reason": reason,
        "source": source,
        "updated_utc": _utc_now(),
    }
    write_json(CONTROL_LAYER_STATUS_PATH, existing)
    payload = build_control_layer_status(refresh_change_scorecard=True)
    append_ndjson(AGENT_EVENTS_LOG_PATH, {
        "event": "control_layer_frozen",
        "room_id": "runtime_global",
        "action": "freeze_control_layer",
        "result": "success",
        "files_changed": [str(CONTROL_LAYER_STATUS_PATH)],
        "metrics_before": {},
        "metrics_after": {"mode": payload.get("mode")},
        "timestamp": _utc_now(),
        "reason": reason,
        "source": source,
    }, ensure_ascii=False)
    return payload


def unfreeze_control_layer(reason: str, source: str = "user") -> Dict[str, Any]:
    existing = _load_existing()
    existing["manual_override"] = {
        "active": False,
        "reason": reason,
        "source": source,
        "updated_utc": _utc_now(),
    }
    write_json(CONTROL_LAYER_STATUS_PATH, existing)
    payload = build_control_layer_status(refresh_change_scorecard=True)
    append_ndjson(AGENT_EVENTS_LOG_PATH, {
        "event": "control_layer_unfrozen",
        "room_id": "runtime_global",
        "action": "unfreeze_control_layer",
        "result": "success",
        "files_changed": [str(CONTROL_LAYER_STATUS_PATH)],
        "metrics_before": {},
        "metrics_after": {"mode": payload.get("mode")},
        "timestamp": _utc_now(),
        "reason": reason,
        "source": source,
    }, ensure_ascii=False)
    return payload
