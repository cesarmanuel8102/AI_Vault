"""
Brain V9 - Edge Validation
Formaliza la validacion de edge por estrategia/contexto usando el ranking vivo.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Dict, List

import brain_v9.config as _cfg
from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
ENGINE_PATH = STATE_PATH / "strategy_engine"
ENGINE_PATH.mkdir(parents=True, exist_ok=True)

EDGE_VALIDATION_PATH = ENGINE_PATH / "edge_validation_latest.json"
_LOCK = RLock()
log = logging.getLogger("edge_validation")

_MIN_FORWARD_SAMPLE_QUALITY = 0.25
_MIN_VALIDATED_SAMPLE_QUALITY = 0.45
_MIN_PROMOTABLE_SAMPLE_QUALITY = 0.70
_MAX_VALIDATED_DRAWDOWN_PENALTY = 0.75
_MAX_PROMOTABLE_DRAWDOWN_PENALTY = 0.50


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


def _candidate_identity(candidate: Dict[str, Any]) -> str:
    return str(candidate.get("strategy_id") or "")


def _best_entries(candidate: Dict[str, Any]) -> int:
    return max(
        _safe_int(candidate.get("entries_resolved"), 0),
        _safe_int(candidate.get("symbol_entries_resolved"), 0),
        _safe_int(candidate.get("context_entries_resolved"), 0),
    )


def _best_sample(candidate: Dict[str, Any]) -> float:
    return max(
        _safe_float(candidate.get("sample_quality"), 0.0),
        _safe_float(candidate.get("symbol_sample_quality"), 0.0),
        _safe_float(candidate.get("context_sample_quality"), 0.0),
    )


def _effective_expectancy(candidate: Dict[str, Any]) -> float:
    contexts = [
        (
            _safe_int(candidate.get("context_entries_resolved"), 0),
            _safe_float(candidate.get("context_sample_quality"), 0.0),
            _safe_float(candidate.get("context_expectancy"), 0.0),
        ),
        (
            _safe_int(candidate.get("symbol_entries_resolved"), 0),
            _safe_float(candidate.get("symbol_sample_quality"), 0.0),
            _safe_float(candidate.get("symbol_expectancy"), 0.0),
        ),
        (
            _safe_int(candidate.get("entries_resolved"), 0),
            _safe_float(candidate.get("sample_quality"), 0.0),
            _safe_float(candidate.get("expectancy"), 0.0),
        ),
    ]
    contexts.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return _round(contexts[0][2] if contexts else 0.0)


def _success_thresholds(candidate: Dict[str, Any]) -> Dict[str, float | int]:
    criteria = candidate.get("success_criteria") or {}
    probation_min = _safe_int(
        criteria.get("probation_min_resolved_trades", _cfg.AUTONOMY_CONFIG.get("probation_min_resolved_trades", 5)),
        int(_cfg.AUTONOMY_CONFIG.get("probation_min_resolved_trades", 5)),
    )
    promote_min = max(_safe_int(criteria.get("min_resolved_trades"), 20), probation_min)
    forward_min = max(probation_min, min(promote_min, max(8, promote_min // 2)))
    min_expectancy = _safe_float(criteria.get("min_expectancy"), 0.05)
    min_win_rate = _safe_float(criteria.get("min_win_rate"), 0.55)
    return {
        "probation_min_resolved_trades": probation_min,
        "forward_min_resolved_trades": forward_min,
        "promote_min_resolved_trades": promote_min,
        "min_expectancy": min_expectancy,
        "min_win_rate": min_win_rate,
    }


def _recent_loss_penalty(candidate: Dict[str, Any]) -> float:
    outcomes = candidate.get("recent_5_outcomes") or []
    if not outcomes:
        return 0.0
    latest = str(outcomes[-1] or "").strip().lower()
    return 0.08 if latest == "loss" else 0.0


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


def _build_edge_item(candidate: Dict[str, Any]) -> Dict[str, Any]:
    thresholds = _success_thresholds(candidate)
    archive_state = str(candidate.get("archive_state") or "")
    governance_state = str(candidate.get("governance_state") or "")
    context_governance_state = str(candidate.get("context_governance_state") or "")
    signal_ready = bool(candidate.get("signal_ready", candidate.get("execution_ready")))
    governance_ready = bool(candidate.get("governance_ready", False))
    execution_ready_now = bool(candidate.get("execution_ready_now", candidate.get("execution_ready")))
    probation_eligible = bool(candidate.get("probation_eligible"))
    venue_ready = bool(candidate.get("venue_ready"))
    drawdown_penalty = _safe_float(candidate.get("drawdown_penalty"), 0.0)
    effective_expectancy = _effective_expectancy(candidate)
    best_entries = _best_entries(candidate)
    best_sample = _best_sample(candidate)
    signal_confidence = _safe_float(candidate.get("signal_confidence"), 0.0)
    recent_loss_penalty = _recent_loss_penalty(candidate)
    deadlock_grace_active = _has_active_deadlock_grace(candidate)
    blockers: List[str] = []
    forward_validated = False
    validated = False
    promotable = False

    if archive_state.startswith("archived") or governance_state in {"retired", "rejected"}:
        edge_state = "refuted"
        execution_lane = "blocked"
        blockers.append("archived_or_retired")
    elif governance_state == "frozen" or context_governance_state == "frozen" or candidate.get("freeze_recommended"):
        edge_state = "blocked"
        execution_lane = "blocked"
        blockers.append("governance_frozen")
    elif not venue_ready:
        edge_state = "blocked"
        execution_lane = "blocked"
        blockers.append("venue_not_ready")
    elif best_entries < thresholds["probation_min_resolved_trades"] or best_sample < 0.10:
        edge_state = "probation"
        execution_lane = "probation" if probation_eligible and execution_ready_now else "watch"
        blockers.append("probation_sample_incomplete")
    else:
        forward_validated = (
            best_entries >= thresholds["forward_min_resolved_trades"]
            and best_sample >= _MIN_FORWARD_SAMPLE_QUALITY
            and effective_expectancy > 0
            and drawdown_penalty <= 1.0
        )
        validated = (
            forward_validated
            and best_entries >= thresholds["forward_min_resolved_trades"]
            and best_sample >= _MIN_VALIDATED_SAMPLE_QUALITY
            and effective_expectancy >= max(thresholds["min_expectancy"] * 0.5, 0.02)
            and drawdown_penalty <= _MAX_VALIDATED_DRAWDOWN_PENALTY
        )
        promotable = (
            validated
            and best_entries >= thresholds["promote_min_resolved_trades"]
            and best_sample >= _MIN_PROMOTABLE_SAMPLE_QUALITY
            and effective_expectancy >= thresholds["min_expectancy"]
            and _safe_float(candidate.get("win_rate"), 0.0) >= max(thresholds["min_win_rate"] - 0.02, 0.50)
            and drawdown_penalty <= _MAX_PROMOTABLE_DRAWDOWN_PENALTY
            and governance_ready
            and signal_ready
        )
        if promotable:
            edge_state = "promotable"
            execution_lane = "promotable" if execution_ready_now else "validated"
        elif validated:
            edge_state = "validated"
            execution_lane = "validated" if execution_ready_now else "watch"
            blockers.append("promotion_threshold_not_reached")
        elif forward_validated:
            edge_state = "forward_validation"
            execution_lane = "watch"
            blockers.append("forward_window_incomplete")
        elif effective_expectancy <= 0 or drawdown_penalty > 1.0 or recent_loss_penalty > 0:
            # P-OP51: Deadlock grace bypass — strategies with active
            # deadlock_unfreeze grace period get probation lane instead of
            # degraded/watch, breaking the catch-22 where negative expectancy
            # prevents execution which prevents expectancy improvement.
            # Note: probation_eligible may be False (leadership_eligible blocks
            # it) so we grant execution_lane directly when grace is active.
            if deadlock_grace_active and drawdown_penalty <= 1.0:
                edge_state = "probation"
                execution_lane = "probation" if execution_ready_now else "watch"
                blockers.append("deadlock_grace_probation_override")
                if effective_expectancy <= 0:
                    blockers.append("non_positive_expectancy")
            else:
                edge_state = "degraded"
                execution_lane = "watch"
                if effective_expectancy <= 0:
                    blockers.append("non_positive_expectancy")
                if drawdown_penalty > 1.0:
                    blockers.append("drawdown_excessive")
                if recent_loss_penalty > 0:
                    blockers.append("recent_loss_not_absorbed")
        else:
            edge_state = "probation"
            execution_lane = "probation" if probation_eligible and execution_ready_now else "watch"
            blockers.append("more_sample_needed")

    return {
        "strategy_id": candidate.get("strategy_id"),
        "venue": candidate.get("venue"),
        "preferred_symbol": candidate.get("preferred_symbol"),
        "preferred_timeframe": candidate.get("preferred_timeframe"),
        "preferred_setup_variant": candidate.get("preferred_setup_variant"),
        "edge_state": edge_state,
        "execution_lane": execution_lane,
        "forward_validated": forward_validated,
        "validated": validated,
        "promotable": promotable,
        "best_entries_resolved": best_entries,
        "best_sample_quality": _round(best_sample),
        "effective_expectancy": effective_expectancy,
        "signal_confidence": _round(signal_confidence),
        "drawdown_penalty": _round(drawdown_penalty),
        "probation_budget": _safe_int(candidate.get("probation_budget"), 0),
        "signal_ready": signal_ready,
        "governance_ready": governance_ready,
        "execution_ready_now": execution_ready_now,
        "blockers": sorted(set(blockers)),
        "thresholds": thresholds,
    }


def build_edge_validation_snapshot(ranked_candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    with _LOCK:
        items = [_build_edge_item(candidate) for candidate in ranked_candidates]
        promotable_items = [item for item in items if item.get("edge_state") == "promotable"]
        validated_items = [item for item in items if item.get("edge_state") == "validated"]
        probation_items = [item for item in items if item.get("edge_state") == "probation"]
        forward_items = [item for item in items if item.get("edge_state") == "forward_validation"]
        degraded_items = [item for item in items if item.get("edge_state") == "degraded"]
        refuted_items = [item for item in items if item.get("edge_state") == "refuted"]
        blocked_items = [item for item in items if item.get("edge_state") == "blocked"]
        active_execution_items = [
            item for item in items
            if item.get("execution_lane") in {"validated", "promotable"} and item.get("execution_ready_now")
        ]
        probation_execution_items = [
            item for item in items
            if item.get("execution_lane") == "probation" and item.get("execution_ready_now")
        ]

        summary = {
            "ranked_count": len(items),
            "promotable_count": len(promotable_items),
            "validated_count": len(validated_items),
            "forward_validation_count": len(forward_items),
            "probation_count": len(probation_items),
            "degraded_count": len(degraded_items),
            "blocked_count": len(blocked_items),
            "refuted_count": len(refuted_items),
            "validated_ready_count": len(active_execution_items),
            "probation_ready_count": len(probation_execution_items),
            "best_promotable": promotable_items[0] if promotable_items else None,
            "best_validated": validated_items[0] if validated_items else None,
            "best_probation": probation_items[0] if probation_items else None,
            "best_forward_validation": forward_items[0] if forward_items else None,
            "top_execution_edge": (
                active_execution_items[0] if active_execution_items
                else probation_execution_items[0] if probation_execution_items
                else None
            ),
        }

        payload = {
            "schema_version": "edge_validation_v1",
            "generated_utc": _utc_now(),
            "summary": summary,
            "items": items,
        }
        write_json(EDGE_VALIDATION_PATH, payload)
        return payload


def read_edge_validation_snapshot() -> Dict[str, Any]:
    return read_json(
        EDGE_VALIDATION_PATH,
        {
            "schema_version": "edge_validation_v1",
            "generated_utc": None,
            "summary": {},
            "items": [],
        },
    )
