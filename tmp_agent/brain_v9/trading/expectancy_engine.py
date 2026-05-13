"""
Brain V9 - Expectancy Engine
Calcula métricas de expectancy canónicas desde strategy_scorecards.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json, append_ndjson
from brain_v9.trading.strategy_scorecard import SCORECARDS_PATH, read_scorecards

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
ENGINE_PATH = STATE_PATH / "strategy_engine"
ENGINE_PATH.mkdir(parents=True, exist_ok=True)

EXPECTANCY_BY_STRATEGY_PATH = ENGINE_PATH / "expectancy_by_strategy.json"
EXPECTANCY_BY_STRATEGY_VENUE_PATH = ENGINE_PATH / "expectancy_by_strategy_venue.json"
EXPECTANCY_BY_STRATEGY_SYMBOL_PATH = ENGINE_PATH / "expectancy_by_strategy_symbol.json"
EXPECTANCY_BY_STRATEGY_CONTEXT_PATH = ENGINE_PATH / "expectancy_by_strategy_context.json"
EXPECTANCY_SNAPSHOT_PATH = ENGINE_PATH / "expectancy_snapshot_latest.json"
EXPECTANCY_REPORTS_PATH = ENGINE_PATH / "expectancy_engine_reports.ndjson"

_LOCK = RLock()
log = logging.getLogger("expectancy_engine")


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


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _append_ndjson(path: Path, payload: Dict[str, Any]) -> None:
    append_ndjson(path, payload)


def _recent_stability(recent: List[Dict[str, Any]]) -> float:
    if not recent:
        return 0.0
    profits = [_safe_float(item.get("profit"), 0.0) for item in recent[-5:]]
    if len(profits) == 1:
        return 0.5 if profits[0] != 0 else 0.25
    magnitude = [abs(x) for x in profits]
    mean_abs = sum(magnitude) / max(len(magnitude), 1)
    if mean_abs <= 0:
        return 1.0
    variance = sum((x - mean_abs) ** 2 for x in magnitude) / len(magnitude)
    coeff = (variance ** 0.5) / mean_abs if mean_abs > 0 else 1.0
    return _round(1.0 - _clamp(coeff, 0.0, 1.0))


def _profit_factor(gross_profit: float, gross_loss: float) -> float:
    if abs(gross_loss) < 1e-9:
        return 99.0 if gross_profit > 0 else 0.0
    return _round(gross_profit / abs(gross_loss))


def _sample_quality(entries_resolved: int, min_sample_target: int = 100) -> float:
    return _round(_clamp(entries_resolved / max(float(min_sample_target), 1.0), 0.0, 1.0))


def _drawdown_penalty(card: Dict[str, Any], max_allowed_drawdown_pct: float = 0.20) -> float:
    turnover = _safe_float(card.get("gross_profit"), 0.0) + abs(_safe_float(card.get("gross_loss"), 0.0))
    largest_loss = abs(_safe_float(card.get("largest_loss"), 0.0))
    proxy_drawdown_pct = (largest_loss / turnover) if turnover > 0 else 0.0
    return _round(_clamp(proxy_drawdown_pct / max(max_allowed_drawdown_pct, 0.01), 0.0, 1.0))


def _expectancy_score(expectancy: float, expectancy_target: float = 0.10) -> float:
    return _round(_clamp(expectancy / max(expectancy_target, 0.01), -1.0, 1.0))


def _win_rate_score(win_rate: float) -> float:
    return _round(_clamp((win_rate - 0.5) / 0.2, -1.0, 1.0))


def _profit_factor_score(profit_factor: float) -> float:
    return _round(_clamp((profit_factor - 1.0) / 1.0, -1.0, 1.0))


def _consistency_score(
    sample_quality_value: float,
    profit_factor_value: float,
    recent_stability_value: float,
    expectancy_value: float,
) -> float:
    normalized_profit_factor = _clamp(profit_factor_value / 2.0, 0.0, 1.0)
    expectancy_positive_score = 1.0 if expectancy_value > 0 else 0.0
    return _round(_clamp(
        (0.35 * sample_quality_value)
        + (0.25 * normalized_profit_factor)
        + (0.20 * recent_stability_value)
        + (0.20 * expectancy_positive_score),
        0.0,
        1.0,
    ))


def _base_metrics(card: Dict[str, Any], *, min_sample_target: int = 30) -> Dict[str, Any]:
    wins = _safe_int(card.get("wins"), 0)
    losses = _safe_int(card.get("losses"), 0)
    draws = _safe_int(card.get("draws"), 0)
    entries_taken = _safe_int(card.get("entries_taken"), 0)
    entries_resolved = _safe_int(card.get("entries_resolved"), 0)
    gross_profit = _safe_float(card.get("gross_profit"), 0.0)
    gross_loss = abs(_safe_float(card.get("gross_loss"), 0.0))
    net_pnl = _safe_float(card.get("net_pnl"), 0.0)
    avg_win = _safe_float(card.get("avg_win"), 0.0)
    avg_loss = _safe_float(card.get("avg_loss"), 0.0)
    win_rate = _safe_float(card.get("win_rate"), 0.0)
    loss_rate = _round(losses / entries_resolved) if entries_resolved else 0.0
    expectancy = _safe_float(card.get("expectancy"), 0.0)
    profit_factor = _profit_factor(gross_profit, gross_loss)
    sample_quality_value = _sample_quality(entries_resolved, min_sample_target=min_sample_target)
    recent = list(card.get("recent_5_outcomes", []) or [])
    recent_stability_value = _recent_stability(recent)
    drawdown_penalty_value = _drawdown_penalty(card)
    consistency_value = _consistency_score(
        sample_quality_value=sample_quality_value,
        profit_factor_value=profit_factor,
        recent_stability_value=recent_stability_value,
        expectancy_value=expectancy,
    )
    return {
        "entries_taken": entries_taken,
        "entries_resolved": entries_resolved,
        "wins": wins,
        "losses": losses,
        "breakeven": draws,
        "gross_profit": _round(gross_profit),
        "gross_loss": _round(-gross_loss),
        "net_pnl": _round(net_pnl),
        "avg_win": _round(avg_win),
        "avg_loss": _round(avg_loss),
        "win_rate": _round(win_rate),
        "loss_rate": _round(loss_rate),
        "expectancy": _round(expectancy),
        "profit_factor": _round(profit_factor),
        "sample_quality": sample_quality_value,
        "expectancy_score": _expectancy_score(expectancy),
        "win_rate_score": _win_rate_score(win_rate),
        "profit_factor_score": _profit_factor_score(profit_factor),
        "drawdown_penalty": drawdown_penalty_value,
        "recent_stability": recent_stability_value,
        "consistency_score": consistency_value,
        "largest_loss": abs(_safe_float(card.get("largest_loss"), 0.0)),
        "largest_win": _safe_float(card.get("largest_win"), 0.0),
        "recent_5_outcomes": recent[-5:],
        "last_trade_utc": card.get("last_trade_utc"),
        "promotion_state": card.get("promotion_state"),
        "governance_state": card.get("governance_state"),
        "freeze_recommended": bool(card.get("freeze_recommended", False)),
        "promote_candidate": bool(card.get("promote_candidate", False)),
        "watch_recommended": bool(card.get("watch_recommended", False)),
        "success_criteria": card.get("success_criteria", {}),
    }


def _decorate_strategy_item(strategy_id: str, card: Dict[str, Any]) -> Dict[str, Any]:
    item = {
        "strategy_id": strategy_id,
        "venue": card.get("venue"),
        "family": card.get("family"),
    }
    item.update(_base_metrics(card))
    return item


def _decorate_symbol_item(key: str, card: Dict[str, Any]) -> Dict[str, Any]:
    item = {
        "key": key,
        "strategy_id": card.get("strategy_id"),
        "venue": card.get("venue"),
        "family": card.get("family"),
        "symbol": card.get("symbol"),
        "scope": card.get("scope"),
    }
    item.update(_base_metrics(card))
    return item


def _decorate_context_item(key: str, card: Dict[str, Any]) -> Dict[str, Any]:
    item = _decorate_symbol_item(key, card)
    item["timeframe"] = card.get("timeframe")
    item["setup_variant"] = card.get("setup_variant")
    return item


def build_expectancy_snapshot(min_sample_target: int = 30) -> Dict[str, Any]:
    with _LOCK:
        payload = read_scorecards()
        strategy_cards = payload.get("scorecards", {}) or {}
        symbol_cards = payload.get("symbol_scorecards", {}) or {}
        context_cards = payload.get("context_scorecards", {}) or {}

        by_strategy_items = [
            _decorate_strategy_item(strategy_id, card)
            for strategy_id, card in strategy_cards.items()
        ]
        by_strategy_items.sort(
            key=lambda x: (x["expectancy"], x["sample_quality"], x["consistency_score"]),
            reverse=True,
        )

        by_strategy_venue_items = [
            _decorate_strategy_item(f"{card.get('strategy_id')}::{card.get('venue')}", card)
            | {"strategy_id": card.get("strategy_id"), "venue": card.get("venue")}
            for _, card in strategy_cards.items()
        ]
        by_strategy_venue_items.sort(
            key=lambda x: (x["expectancy"], x["sample_quality"], x["consistency_score"]),
            reverse=True,
        )

        by_strategy_symbol_items = [
            _decorate_symbol_item(key, card)
            for key, card in symbol_cards.items()
        ]
        by_strategy_symbol_items.sort(
            key=lambda x: (x["expectancy"], x["sample_quality"], x["consistency_score"]),
            reverse=True,
        )

        by_strategy_context_items = [
            _decorate_context_item(key, card)
            for key, card in context_cards.items()
        ]
        by_strategy_context_items.sort(
            key=lambda x: (x["expectancy"], x["sample_quality"], x["consistency_score"]),
            reverse=True,
        )

        top_strategy = by_strategy_items[0] if by_strategy_items else None
        top_symbol = by_strategy_symbol_items[0] if by_strategy_symbol_items else None
        top_context = by_strategy_context_items[0] if by_strategy_context_items else None

        snapshot = {
            "schema_version": "expectancy_snapshot_v1",
            "generated_utc": _utc_now(),
            "source_scorecards_path": str(SCORECARDS_PATH),
            "min_sample_target": min_sample_target,
            "summary": {
                "strategies_count": len(by_strategy_items),
                "strategy_symbols_count": len(by_strategy_symbol_items),
                "strategy_contexts_count": len(by_strategy_context_items),
                "positive_expectancy_strategies_count": sum(1 for item in by_strategy_items if item["expectancy"] > 0),
                "positive_expectancy_symbols_count": sum(1 for item in by_strategy_symbol_items if item["expectancy"] > 0),
                "positive_expectancy_contexts_count": sum(1 for item in by_strategy_context_items if item["expectancy"] > 0),
                "top_strategy": top_strategy,
                "top_symbol": top_symbol,
                "top_context": top_context,
            },
            "by_strategy": {
                "group_by": "strategy",
                "count": len(by_strategy_items),
                "items": by_strategy_items,
            },
            "by_strategy_venue": {
                "group_by": "strategy_venue",
                "count": len(by_strategy_venue_items),
                "items": by_strategy_venue_items,
            },
            "by_strategy_symbol": {
                "group_by": "strategy_venue_symbol",
                "count": len(by_strategy_symbol_items),
                "items": by_strategy_symbol_items,
            },
            "by_strategy_context": {
                "group_by": "strategy_venue_symbol_timeframe_setup",
                "count": len(by_strategy_context_items),
                "items": by_strategy_context_items,
            },
        }

        write_json(EXPECTANCY_BY_STRATEGY_PATH, snapshot["by_strategy"])
        write_json(EXPECTANCY_BY_STRATEGY_VENUE_PATH, snapshot["by_strategy_venue"])
        write_json(EXPECTANCY_BY_STRATEGY_SYMBOL_PATH, snapshot["by_strategy_symbol"])
        write_json(EXPECTANCY_BY_STRATEGY_CONTEXT_PATH, snapshot["by_strategy_context"])
        write_json(EXPECTANCY_SNAPSHOT_PATH, snapshot)
        _append_ndjson(
            EXPECTANCY_REPORTS_PATH,
            {
                "generated_utc": snapshot["generated_utc"],
                "type": "expectancy_refresh",
                "strategies_count": snapshot["summary"]["strategies_count"],
                "positive_expectancy_strategies_count": snapshot["summary"]["positive_expectancy_strategies_count"],
                "top_strategy_id": (top_strategy or {}).get("strategy_id"),
                "top_strategy_expectancy": (top_strategy or {}).get("expectancy"),
            },
        )
        return snapshot


def read_expectancy_snapshot() -> Dict[str, Any]:
    with _LOCK:
        payload = read_json(EXPECTANCY_SNAPSHOT_PATH, {})
        if payload:
            return payload
        return build_expectancy_snapshot()


def read_expectancy_by_strategy() -> Dict[str, Any]:
    return read_json(EXPECTANCY_BY_STRATEGY_PATH, {"group_by": "strategy", "count": 0, "items": []})


def read_expectancy_by_strategy_venue() -> Dict[str, Any]:
    return read_json(EXPECTANCY_BY_STRATEGY_VENUE_PATH, {"group_by": "strategy_venue", "count": 0, "items": []})


def read_expectancy_by_strategy_symbol() -> Dict[str, Any]:
    return read_json(EXPECTANCY_BY_STRATEGY_SYMBOL_PATH, {"group_by": "strategy_venue_symbol", "count": 0, "items": []})


def read_expectancy_by_strategy_context() -> Dict[str, Any]:
    return read_json(EXPECTANCY_BY_STRATEGY_CONTEXT_PATH, {"group_by": "strategy_venue_symbol_timeframe_setup", "count": 0, "items": []})

