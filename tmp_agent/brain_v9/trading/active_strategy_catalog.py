"""
Brain V9 - Active strategy catalog
Reduce ruido del catálogo operativo por venue/lane antes de señal y ranking.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
ENGINE_PATH = STATE_PATH / "strategy_engine"
ENGINE_PATH.mkdir(parents=True, exist_ok=True)

ACTIVE_CATALOG_PATH = ENGINE_PATH / "active_strategy_catalog_latest.json"
log = logging.getLogger("active_strategy_catalog")


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


def _catalog_symbol(strategy: Dict[str, Any]) -> str:
    universe = list(strategy.get("universe") or strategy.get("source_universe") or [])
    if universe:
        return str(universe[0])
    return "multi"


def _catalog_timeframe(strategy: Dict[str, Any]) -> str:
    timeframes = list(strategy.get("timeframes") or [])
    if timeframes:
        return str(timeframes[0])
    return "unknown"


def _lane_key(strategy: Dict[str, Any]) -> str:
    venue = str(strategy.get("venue") or "unknown")
    family = str(strategy.get("family") or "unknown")
    asset_class = str(strategy.get("primary_asset_class") or "unknown")
    timeframe = _catalog_timeframe(strategy)
    if venue == "pocket_option":
        return f"{venue}::{_catalog_symbol(strategy)}::{timeframe}::{family}"
    return f"{venue}::{asset_class}::{timeframe}::{family}"


def _integrity_issues(strategy: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    venue = str(strategy.get("venue") or "")
    timeframes = [str(item) for item in (strategy.get("timeframes") or [])]
    source_universe = [str(item) for item in (strategy.get("source_universe") or strategy.get("universe") or [])]
    asset_classes = [str(item) for item in (strategy.get("asset_classes") or [])]
    primary_asset_class = str(strategy.get("primary_asset_class") or "")

    if not source_universe:
        issues.append("missing_universe")
    if not timeframes:
        issues.append("missing_timeframes")

    if venue == "pocket_option":
        if primary_asset_class != "otc_binary" and "otc_binary" not in asset_classes:
            issues.append("po_asset_class_invalid")
        if any(not symbol.endswith("_otc") for symbol in source_universe):
            issues.append("po_non_otc_symbol")
        allowed_po_timeframes = {"1m", "5m"}
        if any(tf not in allowed_po_timeframes for tf in timeframes):
            issues.append("po_timeframe_invalid")
    elif venue == "ibkr":
        if any(symbol.endswith("_otc") for symbol in source_universe):
            issues.append("ibkr_otc_symbol_invalid")
        allowed_timeframes = {"5m", "15m", "1d", "spot"}
        if any(tf not in allowed_timeframes for tf in timeframes):
            issues.append("ibkr_timeframe_invalid")

    return issues


def _criteria_min_resolved(strategy: Dict[str, Any]) -> int:
    criteria = strategy.get("success_criteria") or {}
    try:
        return int(criteria.get("min_resolved_trades", 20) or 20)
    except (TypeError, ValueError):
        return 20


def _base_catalog_state(
    strategy: Dict[str, Any],
    card: Dict[str, Any],
    archive_info: Dict[str, Any],
) -> tuple[str, str, List[str]]:
    governance_state = str(card.get("governance_state") or card.get("promotion_state") or "paper_candidate")
    archive_state = str(archive_info.get("archive_state") or "")
    expectancy = _safe_float(card.get("expectancy"), 0.0)
    resolved = int(card.get("entries_resolved", 0) or 0)
    issues = _integrity_issues(strategy)
    min_resolved = _criteria_min_resolved(strategy)

    if issues:
        return "excluded", "invalid_spec", issues
    if archive_state.startswith("archived"):
        return "excluded", "archived_or_refuted", [archive_state]
    if governance_state in {"retired", "rejected"}:
        return "excluded", "governance_terminal", [governance_state]
    if governance_state == "frozen":
        if resolved >= max(3, min_resolved // 4) or expectancy < 0:
            return "excluded", "frozen_negative_lane", [governance_state]
        return "watch_only", "frozen_low_sample", [governance_state]
    if governance_state in {"paper_active", "paper_watch", "promote_candidate"}:
        return "active", "governance_active", []
    if governance_state in {"paper_candidate", "paper_probe"}:
        return "probation", "governance_testing", []
    return "watch_only", "governance_unknown", [governance_state]


def _winner_rank(item: Dict[str, Any]) -> tuple:
    state_priority = {
        "active": 3,
        "probation": 2,
        "watch_only": 1,
        "excluded": 0,
    }
    return (
        state_priority.get(str(item.get("catalog_state") or ""), 0),
        0 if not item.get("auto_generated") else -1,
        _safe_float(item.get("expectancy"), 0.0),
        _safe_float(item.get("sample_quality"), 0.0),
        int(item.get("entries_resolved", 0) or 0),
    )


def _venue_reachable(venue: str, venue_health: Dict[str, Any]) -> bool:
    """Return True if the venue has *some* connectivity (ready or paper_order_ready).

    When venue_health is empty (caller did not supply it), assume reachable
    so that existing behaviour is preserved.
    """
    if not venue_health:
        return True
    info = venue_health.get(venue, {})
    if not info:
        return True  # unknown venue → assume reachable
    return bool(info.get("ready") or info.get("paper_order_ready"))


def build_active_strategy_catalog_snapshot(
    strategies: List[Dict[str, Any]],
    scorecards_payload: Dict[str, Any],
    archive_payload: Dict[str, Any],
    venue_health: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    scorecards = scorecards_payload.get("scorecards", {}) or {}
    archive_index: Dict[str, Dict[str, Any]] = {}
    for bucket in ("archived", "active", "watchlist", "testing"):
        for item in archive_payload.get(bucket, []) or []:
            if isinstance(item, dict) and item.get("strategy_id"):
                archive_index[str(item["strategy_id"])] = item

    items: List[Dict[str, Any]] = []
    lane_groups: Dict[str, List[Dict[str, Any]]] = {}

    for strategy in strategies:
        strategy_id = str(strategy.get("strategy_id") or "")
        if not strategy_id:
            continue
        card = scorecards.get(strategy_id, {}) or {}
        archive_info = archive_index.get(strategy_id, {}) or {}
        catalog_state, catalog_reason, integrity_issues = _base_catalog_state(strategy, card, archive_info)
        lane_key = _lane_key(strategy)
        item = {
            "strategy_id": strategy_id,
            "venue": strategy.get("venue"),
            "family": strategy.get("family"),
            "lane_key": lane_key,
            "catalog_symbol": _catalog_symbol(strategy),
            "catalog_timeframe": _catalog_timeframe(strategy),
            "catalog_state": catalog_state,
            "catalog_reason": catalog_reason,
            "catalog_blockers": integrity_issues,
            "governance_state": card.get("governance_state", card.get("promotion_state", "paper_candidate")),
            "archive_state": archive_info.get("archive_state", "testing"),
            "entries_resolved": int(card.get("entries_resolved", 0) or 0),
            "sample_quality": round(_safe_float(card.get("sample_quality"), 0.0), 4),
            "expectancy": round(_safe_float(card.get("expectancy"), 0.0), 4),
            "auto_generated": bool(strategy.get("auto_generated")),
            "runtime_symbol_locked": bool(strategy.get("runtime_symbol_locked")),
            "source_strategy": strategy.get("source_strategy"),
            "decision_scope": "operational" if catalog_state in {"active", "probation"} else "historical_only",
        }
        items.append(item)
        if catalog_state != "excluded":
            lane_groups.setdefault(lane_key, []).append(item)

    duplicate_excluded_count = 0
    for lane_items in lane_groups.values():
        if len(lane_items) <= 1:
            if lane_items:
                lane_items[0]["lane_winner"] = True
            continue
        lane_items.sort(key=_winner_rank, reverse=True)
        lane_items[0]["lane_winner"] = True
        for loser in lane_items[1:]:
            loser["lane_winner"] = False
            loser["catalog_state"] = "excluded"
            loser["catalog_reason"] = "redundant_same_lane"
            loser["decision_scope"] = "historical_only"
            duplicate_excluded_count += 1

    # P-OP1: Degrade operational strategies whose venue is unreachable
    # and that have zero resolved trades.  This prevents a probation
    # strategy on a disconnected venue from blocking variant generation
    # and monopolising the operational slot indefinitely.
    venue_health = venue_health or {}
    venue_degraded_count = 0
    for item in items:
        if item.get("catalog_state") not in {"active", "probation"}:
            continue
        venue = str(item.get("venue") or "")
        if _venue_reachable(venue, venue_health):
            continue
        resolved = int(item.get("entries_resolved", 0) or 0)
        if resolved > 0:
            continue  # has evidence — keep operational even if venue flaky
        log.warning(
            "P-OP1: degrading %s from %s to watch_only — venue %s unreachable, 0 resolved",
            item["strategy_id"], item["catalog_state"], venue,
        )
        item["catalog_state"] = "watch_only"
        item["catalog_reason"] = "venue_unreachable"
        item["decision_scope"] = "historical_only"
        item["catalog_blockers"] = item.get("catalog_blockers", []) + ["venue_unreachable"]
        venue_degraded_count += 1

    operational_ids = [
        item["strategy_id"]
        for item in items
        if item.get("catalog_state") in {"active", "probation"}
    ]
    payload = {
        "schema_version": "active_strategy_catalog_v1",
        "generated_utc": _utc_now(),
        "items": items,
        "summary": {
            "total_count": len(items),
            "active_count": sum(1 for item in items if item.get("catalog_state") == "active"),
            "probation_count": sum(1 for item in items if item.get("catalog_state") == "probation"),
            "watch_only_count": sum(1 for item in items if item.get("catalog_state") == "watch_only"),
            "excluded_count": sum(1 for item in items if item.get("catalog_state") == "excluded"),
            "duplicate_excluded_count": duplicate_excluded_count,
            "venue_degraded_count": venue_degraded_count,
            "lane_count": len(lane_groups),
            "operational_count": len(operational_ids),
            "operational_strategy_ids": operational_ids,
        },
    }
    write_json(ACTIVE_CATALOG_PATH, payload)
    return payload


def read_active_strategy_catalog_snapshot() -> Dict[str, Any]:
    return read_json(
        ACTIVE_CATALOG_PATH,
        {
            "schema_version": "active_strategy_catalog_v1",
            "generated_utc": None,
            "items": [],
            "summary": {
                "total_count": 0,
                "active_count": 0,
                "probation_count": 0,
                "watch_only_count": 0,
                "excluded_count": 0,
                "duplicate_excluded_count": 0,
                "venue_degraded_count": 0,
                "lane_count": 0,
                "operational_count": 0,
                "operational_strategy_ids": [],
            },
        },
    )
