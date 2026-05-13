"""
Brain V9 - Learning loop
Convierte resultados post-trade en decisiones de aprendizaje accionables.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json
from brain_v9.trading.post_trade_analysis import build_post_trade_analysis_snapshot
from brain_v9.trading.post_trade_hypotheses import build_post_trade_hypothesis_base

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
ENGINE_PATH = STATE_PATH / "strategy_engine"
ACTIVE_CATALOG_PATH = ENGINE_PATH / "active_strategy_catalog_latest.json"
EDGE_PATH = ENGINE_PATH / "edge_validation_latest.json"
RANKING_PATH = ENGINE_PATH / "strategy_ranking_v2_latest.json"
LEARNING_LOOP_PATH = ENGINE_PATH / "learning_loop_latest.json"
SIGNAL_SNAPSHOT_PATH = ENGINE_PATH / "strategy_signal_snapshot_latest.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _strategy_stats(post_trade: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        str(item.get("strategy_id")): item
        for item in (post_trade.get("by_strategy") or [])
        if isinstance(item, dict) and item.get("strategy_id")
    }


def _strategy_anomalies(post_trade: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in (post_trade.get("anomalies") or []):
        if not isinstance(item, dict):
            continue
        strategy_id = str(item.get("strategy_id") or "")
        if strategy_id:
            grouped[strategy_id].append(item)
    return grouped


def _decision_for_item(
    item: Dict[str, Any],
    stats: Dict[str, Any],
    anomalies: List[Dict[str, Any]],
) -> Dict[str, Any]:
    strategy_id = item.get("strategy_id")
    catalog_state = str(item.get("catalog_state") or "")
    expectancy = _safe_float(item.get("expectancy"), 0.0)
    resolved = int(item.get("entries_resolved", 0) or 0)
    win_rate = _safe_float(stats.get("win_rate"), 0.0)
    net_profit = _safe_float(stats.get("net_profit"), 0.0)

    decision = "historical_only"
    rationale = "excluded_from_operational_catalog"
    allow_sampling = False
    allow_variant_generation = False

    if catalog_state == "probation":
        if anomalies:
            decision = "audit_integrity_before_sampling"
            rationale = "recent_duplicate_or_execution_anomaly"
        elif resolved < 5:
            decision = "continue_probation"
            rationale = "probation_sample_incomplete"
            allow_sampling = True
        elif expectancy <= 0:
            decision = "tighten_filters_before_more_sampling"
            rationale = "probation_negative_after_minimum_window"
        else:
            decision = "forward_validate"
            rationale = "probation_positive_and_ready_for_forward_window"
            allow_sampling = True
    elif catalog_state == "active":
        if anomalies:
            decision = "audit_integrity_before_sampling"
            rationale = "recent_duplicate_or_execution_anomaly"
        elif expectancy <= 0 or net_profit < 0:
            decision = "tighten_filters_before_more_sampling"
            rationale = "active_lane_dragging_recent_results"
        else:
            decision = "continue_forward_validation"
            rationale = "active_lane_still_constructive"
            allow_sampling = True
    elif catalog_state == "excluded":
        if str(item.get("catalog_reason") or "") == "frozen_negative_lane" and resolved >= 3:
            decision = "generate_variant"
            rationale = "lane_refuted_but_not_archived"
            allow_variant_generation = True

    return {
        "strategy_id": strategy_id,
        "catalog_state": catalog_state,
        "catalog_reason": item.get("catalog_reason"),
        "entries_resolved": resolved,
        "expectancy": expectancy,
        "recent_net_profit": round(net_profit, 4),
        "recent_win_rate": round(win_rate, 4),
        "anomaly_count": len(anomalies),
        "learning_decision": decision,
        "rationale": rationale,
        "allow_sampling": allow_sampling,
        "allow_variant_generation": allow_variant_generation,
    }


def build_learning_loop_snapshot() -> Dict[str, Any]:
    post_trade = build_post_trade_analysis_snapshot()
    hypothesis_base = build_post_trade_hypothesis_base(force_refresh_analysis=False)
    active_catalog = read_json(ACTIVE_CATALOG_PATH, {})
    edge = read_json(EDGE_PATH, {})
    ranking = read_json(RANKING_PATH, {})

    stats_by_strategy = _strategy_stats(post_trade)
    anomalies_by_strategy = _strategy_anomalies(post_trade)

    items: List[Dict[str, Any]] = []
    for catalog_item in active_catalog.get("items", []) or []:
        if not isinstance(catalog_item, dict) or not catalog_item.get("strategy_id"):
            continue
        strategy_id = str(catalog_item.get("strategy_id"))
        items.append(
            _decision_for_item(
                catalog_item,
                stats_by_strategy.get(strategy_id, {}),
                anomalies_by_strategy.get(strategy_id, []),
            )
        )

    operational = [item for item in items if item.get("catalog_state") in {"active", "probation"}]
    audit_targets = [item for item in operational if item.get("learning_decision") == "audit_integrity_before_sampling"]
    probation_targets = [item for item in operational if item.get("learning_decision") == "continue_probation"]
    forward_targets = [item for item in operational if item.get("learning_decision") in {"forward_validate", "continue_forward_validation"}]
    variant_targets = [item for item in items if item.get("allow_variant_generation")]

    top_learning_action = "hold"
    if audit_targets:
        top_learning_action = "audit_integrity_before_sampling"
    elif probation_targets:
        top_learning_action = "continue_probation"
    elif forward_targets:
        top_learning_action = "forward_validate"
    elif variant_targets:
        top_learning_action = "generate_variant"

    # P-OP2: Allow variant generation to coexist with probation when
    # *none* of the probation strategies can currently execute (e.g.
    # market closed, venue stalled, signal not ready).  Without this,
    # a stuck probation strategy blocks variant generation indefinitely,
    # starving venues that could trade (e.g. PO runs 24/7 OTC while
    # IBKR is closed on weekends).
    probation_blocks_variants = (
        top_learning_action == "continue_probation"
        and variant_targets
        and probation_targets
    )
    if probation_blocks_variants:
        signal_snap = read_json(SIGNAL_SNAPSHOT_PATH, {})
        signal_ready_by_strategy = {}
        for by_strat in signal_snap.get("by_strategy", []):
            if isinstance(by_strat, dict) and by_strat.get("strategy_id"):
                signal_ready_by_strategy[by_strat["strategy_id"]] = bool(
                    by_strat.get("execution_ready") or by_strat.get("ready_signals_count", 0) > 0
                )
        any_probation_executable = any(
            signal_ready_by_strategy.get(item.get("strategy_id"), False)
            for item in probation_targets
        )
        if not any_probation_executable:
            top_learning_action = "generate_variant"

    payload = {
        "schema_version": "learning_loop_v1",
        "updated_utc": _utc_now(),
        "summary": {
            "operational_count": len(operational),
            "audit_count": len(audit_targets),
            "probation_continue_count": len(probation_targets),
            "forward_validation_count": len(forward_targets),
            "variant_generation_candidate_count": len(variant_targets),
            "top_learning_action": top_learning_action,
            "allow_variant_generation": top_learning_action == "generate_variant",
            "variant_generation_sources": [item.get("strategy_id") for item in variant_targets],
            "top_hypothesis_id": ((hypothesis_base.get("suggested_hypotheses") or [{}])[0]).get("hypothesis_id"),
            "top_hypothesis_target_strategy_id": ((hypothesis_base.get("suggested_hypotheses") or [{}])[0]).get("target_strategy_id"),
            "validated_edge_count": (edge.get("summary") or {}).get("validated_count", 0),
            "probation_count": (edge.get("summary") or {}).get("probation_count", 0),
            "ranking_top_action": ranking.get("top_action"),
        },
        "items": items,
        "post_trade_summary": post_trade.get("summary") or {},
        "hypothesis_summary": hypothesis_base.get("summary") or {},
    }
    write_json(LEARNING_LOOP_PATH, payload)
    return payload


def read_learning_loop_snapshot() -> Dict[str, Any]:
    payload = read_json(LEARNING_LOOP_PATH, {})
    if payload:
        return payload
    return build_learning_loop_snapshot()
