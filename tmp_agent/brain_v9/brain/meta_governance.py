"""
Brain V9 — Canonical Meta-Governance / Priority Engine

Decides what the Brain should focus on each cycle, above raw utility blockers.
It does not replace Utility U; it orders and stabilizes execution focus.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from brain_v9.config import AUTONOMY_CYCLE_LATEST_PATH, CONTROL_LAYER_STATUS_PATH, STATE_PATH
from brain_v9.core.state_io import read_json, write_json


META_GOVERNANCE_STATUS_PATH = STATE_PATH / "meta_governance_status_latest.json"
UTILITY_LATEST_PATH = STATE_PATH / "utility_u_latest.json"
UTILITY_GATE_PATH = STATE_PATH / "utility_u_promotion_gate_latest.json"
AUTONOMY_NEXT_ACTIONS_PATH = STATE_PATH / "autonomy_next_actions.json"
EDGE_VALIDATION_PATH = STATE_PATH / "strategy_engine" / "edge_validation_latest.json"
RANKING_V2_PATH = STATE_PATH / "strategy_engine" / "strategy_ranking_v2_latest.json"
POST_TRADE_ANALYSIS_PATH = STATE_PATH / "strategy_engine" / "post_trade_analysis_latest.json"

FOCUS_LOCK_MIN_CYCLES = 10
MIN_OPTIMIZE_RESOLVED_TRADES = 15
ANTI_OVERREACT_MIN_TRADES = 5

_BASE_ALLOCATOR = {
    "trading": 35,
    "stability_control": 25,
    "improvement_autobuild": 20,
    "observability": 15,
    "exploration": 5,
}
_DRAWDOWN_ALLOCATOR = {
    "trading": 15,
    "stability_control": 50,
    "improvement_autobuild": 10,
    "observability": 20,
    "exploration": 5,
}
_VALIDATED_EDGE_ALLOCATOR = {
    "trading": 50,
    "stability_control": 15,
    "improvement_autobuild": 20,
    "observability": 10,
    "exploration": 5,
}

_ACTION_PROFILES: Dict[str, Dict[str, Any]] = {
    "break_system_deadlock": {
        "category": "stability_control",
        "base_impact": 10.0,
        "base_urgency": 10.0,
        "base_confidence": 0.95,
        "base_efficiency": 0.85,
        "reason": "system_deadlock_detected",
        "critical": True,
    },
    "increase_resolved_sample": {
        "category": "trading",
        "base_impact": 8.0,
        "base_urgency": 8.0,
        "base_confidence": 0.82,
        "base_efficiency": 0.92,
        "reason": "sample_gap_blocks_edge_validation",
    },
    "run_probation_carefully": {
        "category": "trading",
        "base_impact": 7.5,
        "base_urgency": 7.0,
        "base_confidence": 0.70,
        "base_efficiency": 0.78,
        "reason": "probation_lane_is_available",
    },
    "improve_expectancy_or_reduce_penalties": {
        "category": "trading",
        "base_impact": 8.5,
        "base_urgency": 7.5,
        "base_confidence": 0.65,
        "base_efficiency": 0.72,
        "reason": "utility_and_expectancy_need_repair",
    },
    "select_and_compare_strategies": {
        "category": "trading",
        "base_impact": 8.0,
        "base_urgency": 7.0,
        "base_confidence": 0.78,
        "base_efficiency": 0.76,
        "reason": "ranking_needs_comparison_cycle",
    },
    "improve_signal_capture_and_context_window": {
        "category": "observability",
        "base_impact": 6.5,
        "base_urgency": 6.0,
        "base_confidence": 0.68,
        "base_efficiency": 0.74,
        "reason": "signal_pipeline_needs_more_context",
    },
    "reduce_drawdown_and_capital_at_risk": {
        "category": "stability_control",
        "base_impact": 9.0,
        "base_urgency": 9.0,
        "base_confidence": 0.92,
        "base_efficiency": 0.88,
        "reason": "drawdown_guardrail_requires_reduction",
    },
    "rebalance_capital_exposure": {
        "category": "stability_control",
        "base_impact": 8.0,
        "base_urgency": 8.0,
        "base_confidence": 0.88,
        "base_efficiency": 0.82,
        "reason": "capital_commitment_is_too_high",
    },
    "advance_meta_improvement_roadmap": {
        "category": "improvement_autobuild",
        "base_impact": 5.5,
        "base_urgency": 4.5,
        "base_confidence": 0.75,
        "base_efficiency": 0.78,
        "reason": "meta_gap_is_ready_for_internal_execution",
    },
    "improve_chat_product_quality": {
        "category": "improvement_autobuild",
        "base_impact": 4.5,
        "base_urgency": 4.0,
        "base_confidence": 0.70,
        "base_efficiency": 0.70,
        "reason": "chat_product_has_open_quality_gap",
    },
    "synthesize_chat_product_contract": {
        "category": "improvement_autobuild",
        "base_impact": 3.5,
        "base_urgency": 3.0,
        "base_confidence": 0.82,
        "base_efficiency": 0.80,
        "reason": "chat_contract_can_be_formalized",
    },
    "synthesize_utility_governance_contract": {
        "category": "improvement_autobuild",
        "base_impact": 3.5,
        "base_urgency": 3.0,
        "base_confidence": 0.85,
        "base_efficiency": 0.82,
        "reason": "utility_governance_can_be_formalized",
    },
    "run_qc_backtest_validation": {
        "category": "exploration",
        "base_impact": 4.0,
        "base_urgency": 2.5,
        "base_confidence": 0.60,
        "base_efficiency": 0.55,
        "reason": "offline_validation_supports_research",
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load(path, default: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = read_json(path, default or {})
    return payload if isinstance(payload, dict) else (default or {})


def _allocator_profile(utility_snapshot: Dict[str, Any], edge_summary: Dict[str, Any], blockers: List[str]) -> Tuple[str, Dict[str, int]]:
    drawdown_penalty = float((utility_snapshot.get("components") or {}).get("drawdown_penalty", 0.0) or 0.0)
    validated_count = _safe_int(edge_summary.get("validated_count"), 0)
    promotable_count = _safe_int(edge_summary.get("promotable_count"), 0)
    if drawdown_penalty >= 0.8 or "drawdown_limit_breached" in blockers or "top_strategy_drawdown_excessive" in blockers:
        return "drawdown_high", dict(_DRAWDOWN_ALLOCATOR)
    if validated_count > 0 or promotable_count > 0:
        return "validated_edge_present", dict(_VALIDATED_EDGE_ALLOCATOR)
    return "base", dict(_BASE_ALLOCATOR)


def _priority_band(score: float, critical: bool) -> str:
    if critical:
        return "CRITICAL"
    if score >= 30.0:
        return "HIGH"
    if score >= 15.0:
        return "MEDIUM"
    return "LOW"


def _minimal_action(action_rows: List[Dict[str, Any]]) -> str | None:
    ordered = [
        "increase_resolved_sample",
        "run_probation_carefully",
        "select_and_compare_strategies",
        "improve_signal_capture_and_context_window",
        "advance_meta_improvement_roadmap",
    ]
    available = {row["action"] for row in action_rows}
    for action in ordered:
        if action in available:
            return action
    return action_rows[0]["action"] if action_rows else None


def _build_action_rows(
    actions: List[str],
    *,
    utility_snapshot: Dict[str, Any],
    utility_gate: Dict[str, Any],
    edge_summary: Dict[str, Any],
    raw_top_action: str | None,
) -> List[Dict[str, Any]]:
    blockers = set(utility_gate.get("blockers", []) or [])
    sample = utility_snapshot.get("sample") or {}
    entries_resolved = _safe_int(sample.get("entries_resolved"), 0)
    validated_count = _safe_int(edge_summary.get("validated_count"), 0)
    promotable_count = _safe_int(edge_summary.get("promotable_count"), 0)
    probation_count = _safe_int(edge_summary.get("probation_count"), 0)
    ranking_ctx = utility_snapshot.get("strategy_context") or {}
    reference_strategy = ranking_ctx.get("reference_strategy") or {}
    best_entries = _safe_int(reference_strategy.get("best_entries_resolved"), entries_resolved)
    best_sample_quality = float(reference_strategy.get("best_sample_quality", 0.0) or 0.0)

    rows: List[Dict[str, Any]] = []
    for action in actions:
        profile = dict(_ACTION_PROFILES.get(action) or {
            "category": "trading",
            "base_impact": 5.0,
            "base_urgency": 5.0,
            "base_confidence": 0.60,
            "base_efficiency": 0.65,
            "reason": "utility_requested_action",
        })
        impact = float(profile["base_impact"])
        urgency = float(profile["base_urgency"])
        confidence = float(profile["base_confidence"])
        efficiency = float(profile["base_efficiency"])
        critical = bool(profile.get("critical"))

        if action == raw_top_action:
            impact += 0.6
            urgency += 0.4
        if action == "break_system_deadlock" and "system_deadlock" in blockers:
            critical = True
            impact = max(impact, 10.0)
            urgency = max(urgency, 10.0)
        if action in {"increase_resolved_sample", "run_probation_carefully"}:
            if "sample_not_ready" in blockers or "insufficient_resolved_sample" in blockers:
                confidence += 0.12
                urgency += 0.8
            if probation_count > 0:
                impact += 0.5
        if action == "improve_expectancy_or_reduce_penalties":
            if entries_resolved < MIN_OPTIMIZE_RESOLVED_TRADES:
                confidence -= 0.22
                urgency -= 0.8
                efficiency -= 0.12
            if "no_positive_edge" in blockers or utility_snapshot.get("u_score", utility_snapshot.get("u_proxy_score", 0.0)) <= 0:
                urgency += 0.6
        if action == "select_and_compare_strategies":
            if any(b in blockers for b in ("no_validated_edge", "top_strategy_frozen", "comparison_cycle_non_positive")):
                confidence += 0.10
                urgency += 0.7
        if action == "improve_signal_capture_and_context_window":
            if "signal_pipeline_underpowered" in blockers:
                confidence += 0.12
                urgency += 0.6
            if ranking_ctx.get("top_strategy") in (None, {}, ""):
                urgency += 0.4
        if action in {"reduce_drawdown_and_capital_at_risk", "rebalance_capital_exposure"}:
            if any(b in blockers for b in ("drawdown_limit_breached", "top_strategy_drawdown_excessive", "capital_commitment_too_high")):
                confidence += 0.12
                urgency += 1.2
                impact += 0.8
        if action == "advance_meta_improvement_roadmap" and (validated_count > 0 or promotable_count > 0):
            urgency -= 0.5
        if action == "run_qc_backtest_validation" and (validated_count > 0 or promotable_count > 0):
            urgency -= 0.8
            efficiency -= 0.1

        if best_entries < ANTI_OVERREACT_MIN_TRADES and action not in {"increase_resolved_sample", "run_probation_carefully", "break_system_deadlock"}:
            confidence -= 0.12
        if best_sample_quality < 0.15 and action == "improve_expectancy_or_reduce_penalties":
            confidence -= 0.10

        impact = _clamp(impact, 0.0, 10.0)
        urgency = _clamp(urgency, 0.0, 10.0)
        confidence = _clamp(confidence, 0.05, 1.0)
        efficiency = _clamp(efficiency, 0.05, 1.0)
        score = _round(impact * urgency * confidence * efficiency)
        rows.append({
            "action": action,
            "category": profile["category"],
            "reason": profile["reason"],
            "impact": _round(impact),
            "urgency": _round(urgency),
            "confidence": _round(confidence),
            "resource_efficiency": _round(efficiency),
            "priority_score": score,
            "priority": _priority_band(score, critical),
            "critical": critical,
        })

    rows.sort(key=lambda item: (item["critical"], item["priority_score"]), reverse=True)
    return rows


def build_meta_governance_status(
    *,
    utility_snapshot: Dict[str, Any] | None = None,
    utility_gate: Dict[str, Any] | None = None,
    raw_next_actions: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    utility_snapshot = utility_snapshot or _load(UTILITY_LATEST_PATH)
    utility_gate = utility_gate or _load(UTILITY_GATE_PATH)
    raw_next_actions = raw_next_actions or _load(AUTONOMY_NEXT_ACTIONS_PATH)
    edge = _load(EDGE_VALIDATION_PATH)
    ranking = _load(RANKING_V2_PATH)
    cycle = _load(AUTONOMY_CYCLE_LATEST_PATH)
    control = _load(CONTROL_LAYER_STATUS_PATH)
    post_trade = _load(POST_TRADE_ANALYSIS_PATH)
    previous = _load(META_GOVERNANCE_STATUS_PATH)

    edge_summary = edge.get("summary") or {}
    blockers = list(utility_gate.get("blockers", []) or raw_next_actions.get("blockers", []) or [])
    raw_actions = list(raw_next_actions.get("recommended_actions", []) or utility_gate.get("required_next_actions", []) or [])
    raw_top_action = raw_next_actions.get("top_action")
    cycle_count = _safe_int(cycle.get("cycle_count"), 0)

    allocator_profile, allocator = _allocator_profile(utility_snapshot, edge_summary, blockers)
    rows = _build_action_rows(
        raw_actions,
        utility_snapshot=utility_snapshot,
        utility_gate=utility_gate,
        edge_summary=edge_summary,
        raw_top_action=raw_top_action,
    )

    previous_focus = (previous.get("current_focus") or {}) if isinstance(previous, dict) else {}
    previous_focus_action = previous_focus.get("action")
    last_focus_change_cycle = _safe_int(previous_focus.get("last_focus_change_cycle"), cycle_count)
    cycles_since_switch = max(cycle_count - last_focus_change_cycle, 0)
    critical_present = any(row.get("critical") for row in rows)
    focus_switch_allowed = critical_present or previous_focus_action is None or cycles_since_switch >= FOCUS_LOCK_MIN_CYCLES

    forced_minimum_action = False
    if _safe_int(raw_next_actions.get("consecutive_skips"), 0) <= 0:
        consecutive_skips = _safe_int((_load(STATE_PATH / "autonomy_skip_state.json")).get("consecutive_skips"), 0)
    else:
        consecutive_skips = _safe_int(raw_next_actions.get("consecutive_skips"), 0)

    top_row = rows[0] if rows else None
    if not focus_switch_allowed and previous_focus_action:
        locked = next((row for row in rows if row["action"] == previous_focus_action), None)
        if locked is not None:
            top_row = locked
            rows = [locked] + [row for row in rows if row["action"] != previous_focus_action]

    if consecutive_skips >= 3 and rows and not critical_present:
        forced = _minimal_action(rows)
        if forced:
            forced_row = next((row for row in rows if row["action"] == forced), None)
            if forced_row is not None:
                top_row = forced_row
                rows = [forced_row] + [row for row in rows if row["action"] != forced]
                forced_minimum_action = True

    top_action = top_row.get("action") if top_row else None
    recommended_actions = [row["action"] for row in rows]
    entries_resolved = _safe_int((utility_snapshot.get("sample") or {}).get("entries_resolved"), 0)
    optimization_allowed = entries_resolved >= MIN_OPTIMIZE_RESOLVED_TRADES
    optimize_blockers: List[str] = []
    if entries_resolved < MIN_OPTIMIZE_RESOLVED_TRADES:
        optimize_blockers.append("resolved_sample_below_15")
    if _safe_int(edge_summary.get("validated_count"), 0) <= 0 and _safe_int(edge_summary.get("promotable_count"), 0) <= 0:
        optimize_blockers.append("no_validated_edge")

    if control.get("mode") == "FROZEN":
        top_action = None
        recommended_actions = []

    focus_changed = not previous_focus_action or previous_focus_action != top_action
    current_focus = {
        "action": top_action,
        "category": top_row.get("category") if top_row else None,
        "priority": top_row.get("priority") if top_row else None,
        "priority_score": top_row.get("priority_score") if top_row else None,
        "focus_lock_active": bool(previous_focus_action and not focus_switch_allowed and top_action == previous_focus_action),
        "focus_switch_allowed": focus_switch_allowed,
        "cycles_since_switch": cycles_since_switch,
        "last_focus_change_cycle": cycle_count if focus_changed else last_focus_change_cycle,
        "focus_started_cycle": cycle_count if focus_changed else _safe_int(previous_focus.get("focus_started_cycle"), cycle_count),
        "forced_minimum_action": forced_minimum_action,
    }

    payload = {
        "schema_version": "meta_governance_status_v1",
        "updated_utc": _utc_now(),
        "current_state": "control_frozen" if control.get("mode") == "FROZEN" else "active",
        "control_layer_mode": control.get("mode", "ACTIVE"),
        "allocator_profile": allocator_profile,
        "allocator": allocator,
        "system_profile": {
            "u_score": utility_snapshot.get("u_score", utility_snapshot.get("u_proxy_score")),
            "verdict": utility_gate.get("verdict") or utility_snapshot.get("verdict"),
            "blockers": blockers,
            "validated_count": _safe_int(edge_summary.get("validated_count"), 0),
            "promotable_count": _safe_int(edge_summary.get("promotable_count"), 0),
            "probation_count": _safe_int(edge_summary.get("probation_count"), 0),
            "blocked_count": _safe_int(edge_summary.get("blocked_count"), 0),
            "refuted_count": _safe_int(edge_summary.get("refuted_count"), 0),
            "consecutive_skips": consecutive_skips,
            "raw_top_action": raw_top_action,
            "top_strategy_id": (ranking.get("summary") or {}).get("top_strategy_id"),
            "recent_trade_count": _safe_int((post_trade.get("summary") or {}).get("recent_resolved_trades"), 0),
        },
        "priority_queue": rows,
        "top_priority": top_row or {},
        "top_action": top_action,
        "recommended_actions": recommended_actions,
        "current_focus": current_focus,
        "discipline": {
            "focus_lock_min_cycles": FOCUS_LOCK_MIN_CYCLES,
            "focus_switch_allowed": focus_switch_allowed,
            "anti_overreact_window_cycles": 10,
            "optimization_allowed": optimization_allowed,
            "optimize_blockers": optimize_blockers,
            "entries_resolved": entries_resolved,
        },
        "utility_source": {
            "top_action": raw_top_action,
            "recommended_actions": raw_actions,
        },
    }
    write_json(META_GOVERNANCE_STATUS_PATH, payload)
    return payload


def get_meta_governance_status_latest() -> Dict[str, Any]:
    payload = _load(META_GOVERNANCE_STATUS_PATH)
    if payload:
        return payload
    return build_meta_governance_status()
