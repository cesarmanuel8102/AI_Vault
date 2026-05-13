"""
Brain V9 - Context Edge Validation
Minimal context-first validation layer for Stage 2.

Focus:
- evaluate the exact execution context the engine is about to use
- block obviously contradicted contexts early
- keep unproven contexts in probation instead of exploitation
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Dict, List

from brain_v9.config import BASE_PATH, AUTONOMY_CONFIG
from brain_v9.core.state_io import read_json, write_json

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
ENGINE_PATH = STATE_PATH / "strategy_engine"
ENGINE_PATH.mkdir(parents=True, exist_ok=True)

CONTEXT_EDGE_VALIDATION_PATH = ENGINE_PATH / "context_edge_validation_latest.json"
_LOCK = RLock()
log = logging.getLogger("context_edge_validation")

_MIN_VALIDATED_SAMPLE_QUALITY = 0.25


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception as exc:
        log.debug("_safe_float conversion failed for %r: %s", value, exc)
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception as exc:
        log.debug("_safe_int conversion failed for %r: %s", value, exc)
        return default


def _round(value: float, digits: int = 4) -> float:
    return round(_safe_float(value), digits)


def _success_thresholds(candidate: Dict[str, Any]) -> Dict[str, float | int]:
    criteria = candidate.get("success_criteria") or {}
    probation_min = _safe_int(
        criteria.get("probation_min_resolved_trades", AUTONOMY_CONFIG.get("probation_min_resolved_trades", 5)),
        int(AUTONOMY_CONFIG.get("probation_min_resolved_trades", 5)),
    )
    promote_min = max(_safe_int(criteria.get("min_resolved_trades"), 20), probation_min)
    forward_min = max(probation_min, min(promote_min, max(8, promote_min // 2)))
    min_expectancy = _safe_float(criteria.get("min_expectancy"), 0.05)
    return {
        "probation_min_resolved_trades": probation_min,
        "forward_min_resolved_trades": forward_min,
        "promote_min_resolved_trades": promote_min,
        "min_expectancy": min_expectancy,
    }


def _has_active_deadlock_grace(candidate: Dict[str, Any]) -> bool:
    """Check if strategy has an active deadlock_unfreeze grace period."""
    dl_unfreeze = candidate.get("deadlock_unfreeze_utc")
    if not dl_unfreeze:
        return False
    try:
        from datetime import timedelta
        grace_days = 3  # matches AUTONOMY_CONFIG deadlock_unfreeze_grace_days
        dl_dt = datetime.fromisoformat(str(dl_unfreeze).replace("Z", "+00:00"))
        return datetime.now(timezone.utc) < dl_dt + timedelta(days=grace_days)
    except (ValueError, TypeError):
        return False


def _build_item(candidate: Dict[str, Any]) -> Dict[str, Any]:
    thresholds = _success_thresholds(candidate)
    entries = _safe_int(candidate.get("current_context_entries_resolved"), 0)
    sample_quality = _safe_float(candidate.get("current_context_sample_quality"), 0.0)
    expectancy = _safe_float(candidate.get("current_context_expectancy"), 0.0)
    governance_state = str(candidate.get("governance_state") or "")
    context_governance_state = str(candidate.get("current_context_governance_state") or "")
    archive_state = str(candidate.get("archive_state") or "")
    signal_ready = bool(candidate.get("signal_ready", candidate.get("execution_ready")))
    execution_ready_now = bool(candidate.get("execution_ready_now", candidate.get("execution_ready")))
    probation_eligible = bool(candidate.get("probation_eligible"))
    deadlock_grace_active = _has_active_deadlock_grace(candidate)

    blockers: List[str] = []
    execution_allowed = False

    if archive_state.startswith("archived") or governance_state in {"retired", "rejected"}:
        context_edge_state = "blocked"
        blockers.append("archived_or_retired")
    elif governance_state == "frozen" or context_governance_state == "frozen" or candidate.get("freeze_recommended"):
        context_edge_state = "blocked"
        blockers.append("governance_frozen")
    elif not signal_ready:
        context_edge_state = "blocked"
        blockers.append("signal_not_ready")
    elif entries >= thresholds["probation_min_resolved_trades"] and expectancy <= 0:
        # P-OP51: Deadlock grace bypass — allow execution for strategies with
        # active deadlock_unfreeze grace period even when context expectancy is
        # negative, breaking the catch-22.
        if deadlock_grace_active:
            context_edge_state = "unproven"
            execution_allowed = execution_ready_now
            blockers.append("deadlock_grace_override_contradicted")
        else:
            context_edge_state = "contradicted"
            blockers.append("current_context_non_positive_expectancy")
    elif entries >= thresholds["forward_min_resolved_trades"] and sample_quality >= _MIN_VALIDATED_SAMPLE_QUALITY and expectancy > 0:
        context_edge_state = "validated"
        execution_allowed = execution_ready_now
    elif entries > 0 and expectancy > 0:
        context_edge_state = "supportive"
        execution_allowed = execution_ready_now
    else:
        context_edge_state = "unproven"
        # P-OP51: Allow execution during deadlock grace even without probation_eligible
        execution_allowed = bool((probation_eligible or deadlock_grace_active) and execution_ready_now)
        blockers.append("current_context_sample_incomplete")

    if context_edge_state == "contradicted":
        decision_impact = "block_execution"
    elif context_edge_state == "validated":
        decision_impact = "allow_standard_execution"
    elif context_edge_state == "supportive":
        decision_impact = "allow_guarded_execution"
    elif context_edge_state == "unproven":
        decision_impact = "probation_only"
    else:
        decision_impact = "watch_only"

    return {
        "strategy_id": candidate.get("strategy_id"),
        "venue": candidate.get("venue"),
        "preferred_symbol": candidate.get("preferred_symbol"),
        "preferred_timeframe": candidate.get("preferred_timeframe"),
        "preferred_setup_variant": candidate.get("preferred_setup_variant"),
        "current_context_key": candidate.get("current_context_key"),
        "current_context_entries_resolved": entries,
        "current_context_sample_quality": _round(sample_quality),
        "current_context_expectancy": _round(expectancy),
        "current_context_edge_state": context_edge_state,
        "current_context_execution_allowed": execution_allowed,
        "decision_impact": decision_impact,
        "signal_ready": signal_ready,
        "execution_ready_now": execution_ready_now,
        "probation_eligible": probation_eligible,
        "blockers": sorted(set(blockers)),
        "thresholds": thresholds,
    }


def build_context_edge_validation_snapshot(ranked_candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    with _LOCK:
        items = [_build_item(candidate) for candidate in ranked_candidates]
        validated_items = [item for item in items if item.get("current_context_edge_state") == "validated"]
        supportive_items = [item for item in items if item.get("current_context_edge_state") == "supportive"]
        unproven_items = [item for item in items if item.get("current_context_edge_state") == "unproven"]
        contradicted_items = [item for item in items if item.get("current_context_edge_state") == "contradicted"]
        blocked_items = [item for item in items if item.get("current_context_edge_state") == "blocked"]
        execution_allowed_items = [item for item in items if item.get("current_context_execution_allowed")]

        payload = {
            "schema_version": "context_edge_validation_v1",
            "generated_utc": _utc_now(),
            "summary": {
                "ranked_count": len(items),
                "validated_count": len(validated_items),
                "supportive_count": len(supportive_items),
                "unproven_count": len(unproven_items),
                "contradicted_count": len(contradicted_items),
                "blocked_count": len(blocked_items),
                "execution_allowed_count": len(execution_allowed_items),
                "best_validated": validated_items[0] if validated_items else None,
                "best_supportive": supportive_items[0] if supportive_items else None,
                "best_unproven": unproven_items[0] if unproven_items else None,
                "top_execution_context": execution_allowed_items[0] if execution_allowed_items else None,
            },
            "items": items,
        }
        write_json(CONTEXT_EDGE_VALIDATION_PATH, payload)
        return payload


def read_context_edge_validation_snapshot() -> Dict[str, Any]:
    return read_json(
        CONTEXT_EDGE_VALIDATION_PATH,
        {
            "schema_version": "context_edge_validation_v1",
            "generated_utc": None,
            "summary": {},
            "items": [],
        },
    )
