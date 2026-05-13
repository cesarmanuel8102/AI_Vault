"""
Brain V9 - Strategy Engine V1
Formaliza estrategias, genera candidatos, scorecards y ranking canónico.
"""
import json
import asyncio
import logging
import re
import socket
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Dict, List, Optional

import brain_v9.config as _cfg
from brain_v9.config import BASE_PATH, PAPER_ONLY, IBKR_HOST, IBKR_PORT
from brain_v9.core.state_io import read_json, write_json, append_ndjson
from brain_v9.research.knowledge_base import (
    _strategy_seed,
    build_strategy_candidates,
    generate_strategy_variants,
    read_hypothesis_queue,
    read_strategy_specs,
)
from brain_v9.trading.expectancy_engine import (
    build_expectancy_snapshot,
    read_expectancy_snapshot,
)
from brain_v9.trading.edge_validation import (
    EDGE_VALIDATION_PATH,
    build_edge_validation_snapshot,
    read_edge_validation_snapshot,
)
from brain_v9.trading.context_edge_validation import (
    CONTEXT_EDGE_VALIDATION_PATH,
    build_context_edge_validation_snapshot,
    read_context_edge_validation_snapshot,
)
from brain_v9.trading.pipeline_integrity import (
    PIPELINE_INTEGRITY_PATH,
    build_pipeline_integrity_snapshot,
    read_pipeline_integrity_snapshot,
)
from brain_v9.trading.active_strategy_catalog import (
    ACTIVE_CATALOG_PATH,
    build_active_strategy_catalog_snapshot,
    read_active_strategy_catalog_snapshot,
)
from brain_v9.brain.risk_contract import enforce_risk_contract_for_execution
from brain_v9.trading.asset_class_layer import normalize_strategy_asset_profile
from brain_v9.trading.feature_engine import build_market_feature_snapshot, FEATURE_SNAPSHOT_PATH
from brain_v9.trading.market_history_engine import build_market_history_snapshot, read_market_history_snapshot, MARKET_HISTORY_PATH
from brain_v9.trading.hypothesis_engine import evaluate_hypotheses, HYP_RESULTS_PATH
from brain_v9.trading.paper_execution import (
    execute_signal_paper_trade,
    persist_trade_execution_metadata,
    resolve_pending_paper_trades,
    PAPER_EXECUTION_LEDGER_PATH,
)
from brain_v9.trading.connectors import PocketOptionBridge
from brain_v9.trading.adaptive_duration_policy import build_trade_decision_with_duration, AdaptiveDurationConfig
from brain_v9.trading.signal_engine import build_strategy_signal_snapshot, read_strategy_signal_snapshot, SIGNAL_SNAPSHOT_PATH
from brain_v9.trading.strategy_archive import build_strategy_archive, read_strategy_archive, ARCHIVE_PATH
from brain_v9.trading.strategy_scorecard import (
    SCORECARDS_PATH,
    _context_key,
    _symbol_key,
    ensure_scorecards,
    read_scorecards,
    update_strategy_scorecard,
)
from brain_v9.trading.strategy_selector import (
    build_ranking,
    choose_explore_candidate,
    choose_exploit_candidate,
    choose_probation_candidate,
    choose_recovery_candidate,
    choose_top_candidate,
    choose_top_n_candidates,
)

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
ENGINE_PATH = STATE_PATH / "strategy_engine"
ENGINE_PATH.mkdir(parents=True, exist_ok=True)

log = logging.getLogger("StrategyEngine")

CANDIDATES_PATH = ENGINE_PATH / "strategy_candidates_latest.json"
RANKING_PATH = ENGINE_PATH / "strategy_ranking_latest.json"
RANKING_V2_PATH = ENGINE_PATH / "strategy_ranking_v2_latest.json"
MIN_EXECUTION_SIGNAL_SCORE = 0.30
REPORTS_PATH = ENGINE_PATH / "strategy_engine_reports.ndjson"
RUNS_PATH = ENGINE_PATH / "strategy_runs"
RUNS_PATH.mkdir(parents=True, exist_ok=True)
COMPARISON_RUNS_PATH = ENGINE_PATH / "comparison_runs"
COMPARISON_RUNS_PATH.mkdir(parents=True, exist_ok=True)
NEXT_ACTIONS_PATH = STATE_PATH / "autonomy_next_actions.json"
PO_BRIDGE_PATH = STATE_PATH / "rooms" / "brain_binary_paper_pb04_demo_execution" / "browser_bridge_latest.json"
IBKR_PROBE_PATH = STATE_PATH / "rooms" / "brain_financial_ingestion_fi04_structured_api" / "ibkr_marketdata_probe_status.json"
IBKR_ORDER_CHECK_PATH = STATE_PATH / "trading_execution_checks" / "ibkr_paper_order_check_latest.json"
ENGINE_LOCK = RLock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _latest_comparison_cycle() -> Dict:
    try:
        latest = max(COMPARISON_RUNS_PATH.glob("*/result.json"), key=lambda p: p.stat().st_mtime)
    except ValueError:
        return {}  # Empty glob — expected when no comparison runs exist
    payload = read_json(latest, {})
    if payload:
        payload["artifact"] = str(latest)
    return payload


def _append_report(event: Dict):
    append_ndjson(REPORTS_PATH, event)


def _annotate_candidate(candidate: Dict | None, selection_mode: str) -> Dict | None:
    if not candidate:
        return None
    annotated = dict(candidate)
    annotated["selection_mode"] = selection_mode
    annotated["allow_frozen_execution"] = bool(
        annotated.get("freeze_recommended")
        or str(annotated.get("governance_state") or "") == "frozen"
    )
    return annotated


def _run_id(prefix: str = "strun") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    return f"{prefix}_{stamp}"


def _default_direction(family: Optional[str]) -> str:
    return "call" if family in {"trend_following", "breakout"} else "put"


def _timeframe_to_seconds(timeframe: Optional[str]) -> Optional[int]:
    text = str(timeframe or "").strip().lower()
    if not text:
        return None
    if text.endswith("s") and text[:-1].isdigit():
        return int(text[:-1])
    if text.endswith("m") and text[:-1].isdigit():
        return int(text[:-1]) * 60
    if text.endswith("h") and text[:-1].isdigit():
        return int(text[:-1]) * 3600
    return None


def _pick_symbol(strategy: Dict, venue: str) -> str:
    universe = strategy.get("universe", [])
    if venue == "pocket_option":
        bridge = read_json(PO_BRIDGE_PATH, {})
        current = bridge.get("current", {}) if isinstance(bridge.get("current"), dict) else {}
        current_symbol = current.get("symbol")
        if current_symbol:
            return current_symbol
    if universe:
        return universe[0]
    if venue in {"ibkr", "quantconnect"}:
        return "SPY"
    return "EURUSD_otc"


def _strategy_data_inputs(venue: str) -> List[str]:
    inputs = [str(STATE_PATH / "autonomy_next_actions.json"), str(SCORECARDS_PATH)]
    if venue == "ibkr":
        inputs.append(str(IBKR_PROBE_PATH))
    elif venue == "pocket_option":
        inputs.append(str(PO_BRIDGE_PATH))
    return inputs


def _best_symbol_snapshot(strategy: Dict, symbol_scorecards: Dict) -> Dict:
    prefix = f'{strategy["venue"]}::{strategy["strategy_id"]}::'
    matching = []
    for key, card in (symbol_scorecards or {}).items():
        if key.startswith(prefix):
            matching.append(card)
    if not matching:
        return {
            "symbol": None,
            "expectancy": 0.0,
            "sample_quality": 0.0,
            "consistency_score": 0.0,
            "entries_resolved": 0,
        }
    matching.sort(
        key=lambda c: (
            float(c.get("expectancy", 0.0) or 0.0),
            float(c.get("sample_quality", 0.0) or 0.0),
            float(c.get("consistency_score", 0.0) or 0.0),
            int(c.get("entries_resolved", 0) or 0),
        ),
        reverse=True,
    )
    best = matching[0]
    return {
        "symbol": best.get("symbol"),
        "expectancy": best.get("expectancy", 0.0),
        "sample_quality": best.get("sample_quality", 0.0),
        "consistency_score": best.get("consistency_score", 0.0),
        "entries_resolved": best.get("entries_resolved", 0),
    }


def _best_context_snapshot(strategy: Dict, context_scorecards: Dict) -> Dict:
    prefix = f'{strategy["venue"]}::{strategy["strategy_id"]}::'
    matching = []
    for key, card in (context_scorecards or {}).items():
        if key.startswith(prefix):
            matching.append(card)
    if not matching:
        return {
            "symbol": None,
            "timeframe": None,
            "setup_variant": None,
            "expectancy": 0.0,
            "sample_quality": 0.0,
            "consistency_score": 0.0,
            "entries_resolved": 0,
        }
    matching.sort(
        key=lambda c: (
            float(c.get("expectancy", 0.0) or 0.0),
            float(c.get("sample_quality", 0.0) or 0.0),
            float(c.get("consistency_score", 0.0) or 0.0),
            int(c.get("entries_resolved", 0) or 0),
        ),
        reverse=True,
    )
    best = matching[0]
    return {
        "symbol": best.get("symbol"),
        "timeframe": best.get("timeframe"),
        "setup_variant": best.get("setup_variant"),
        "expectancy": best.get("expectancy", 0.0),
        "sample_quality": best.get("sample_quality", 0.0),
        "consistency_score": best.get("consistency_score", 0.0),
        "entries_resolved": best.get("entries_resolved", 0),
    }


def _specific_context_snapshot(
    strategy: Dict,
    context_scorecards: Dict,
    symbol: str | None,
    timeframe: str | None,
    setup_variant: str | None,
) -> Dict:
    if not symbol or not timeframe or not setup_variant:
        return {
            "key": None,
            "symbol": symbol,
            "timeframe": timeframe,
            "setup_variant": setup_variant,
            "expectancy": 0.0,
            "sample_quality": 0.0,
            "consistency_score": 0.0,
            "entries_resolved": 0,
            "governance_state": "paper_candidate",
        }
    key = _context_key(strategy, symbol, timeframe, setup_variant)
    card = context_scorecards.get(key, {})
    return {
        "key": key,
        "symbol": symbol,
        "timeframe": timeframe,
        "setup_variant": setup_variant,
        "expectancy": card.get("expectancy", 0.0),
        "sample_quality": card.get("sample_quality", 0.0),
        "consistency_score": card.get("consistency_score", 0.0),
        "entries_resolved": card.get("entries_resolved", 0),
        "governance_state": card.get("governance_state", "paper_candidate"),
    }


def _recommended_iterations(candidate: Dict) -> int:
    if not candidate.get("execution_ready_now", candidate.get("execution_ready")):
        return 0
    if str(candidate.get("archive_state") or "").startswith("archived"):
        return 0
    sample_quality = float(candidate.get("sample_quality", 0.0) or 0.0)
    symbol_sample_quality = float(candidate.get("symbol_sample_quality", 0.0) or 0.0)
    expectancy = float(candidate.get("expectancy", 0.0) or 0.0)
    venue = candidate.get("venue")

    if venue == "pocket_option":
        if sample_quality < 0.5:
            return 3
        if expectancy > 0 and symbol_sample_quality < 0.3:
            return 2
        return 1

    if venue == "ibkr":
        if sample_quality < 0.2:
            return 2
        return 1

    return 1


def _probation_window_cap(candidate: Dict) -> int:
    if str(candidate.get("governance_lane") or "") != "probation":
        return 0
    criteria = candidate.get("success_criteria") or {}
    try:
        return int(
            criteria.get(
                "probation_min_resolved_trades",
                _cfg.AUTONOMY_CONFIG.get("probation_min_resolved_trades", 5),
            ) or 5
        )
    except (TypeError, ValueError):
        return int(_cfg.AUTONOMY_CONFIG.get("probation_min_resolved_trades", 5))


def _governance_ready(candidate: Dict) -> bool:
    governance_state = str(candidate.get("governance_state") or "")
    context_governance_state = str(candidate.get("context_governance_state") or "")
    archive_state = str(candidate.get("archive_state") or "")
    if archive_state.startswith("archived"):
        return False
    if governance_state in {"frozen", "retired", "rejected"}:
        return False
    if context_governance_state in {"frozen", "rejected"}:
        return False
    if candidate.get("freeze_recommended"):
        return False
    return True


def _setup_variants(strategy: Dict) -> List[str]:
    family = strategy.get("family")
    if family == "trend_following":
        return ["pullback_continuation", "break_reclaim"]
    if family == "breakout":
        return ["compression_break", "range_expansion"]
    if family == "mean_reversion":
        return ["range_reversion", "payout_filtered_reversion"]
    return ["base"]


def _runtime_aligned_text(text: Optional[str], strategy: Dict) -> Optional[str]:
    if not text:
        return text
    if strategy.get("venue") != "pocket_option":
        return text
    source_universe = list(strategy.get("source_universe") or [])
    runtime_universe = list(strategy.get("universe") or [])
    if not runtime_universe:
        return text
    runtime_symbol = str(runtime_universe[0] or "")
    if not runtime_symbol:
        return text

    def _symbol_variants(symbol: str) -> List[tuple[str, str]]:
        normalized = str(symbol or "").strip()
        if not normalized:
            return []
        base = normalized.replace("_otc", "")
        if len(base) != 6 or not base.isalpha():
            return [("normalized", normalized)]
        slash = f"{base[:3]}/{base[3:]}"
        return [
            ("normalized", f"{base}_otc"),
            ("spaced", f"{base} OTC"),
            ("slashed", f"{slash} OTC"),
            ("compact", base),
        ]

    runtime_variants = dict(_symbol_variants(runtime_symbol))
    aligned_text = str(text)

    for source_symbol in source_universe:
        source_variants = _symbol_variants(str(source_symbol or ""))
        for variant_kind, source_variant in source_variants:
            replacement = runtime_variants.get(variant_kind)
            if replacement:
                aligned_text = aligned_text.replace(source_variant, replacement)

    if strategy.get("runtime_symbol_locked") and runtime_symbol.endswith("_otc"):
        runtime_base = runtime_symbol.replace("_otc", "")
        runtime_slash = f"{runtime_base[:3]}/{runtime_base[3:]} OTC" if len(runtime_base) == 6 else runtime_symbol
        aligned_text = re.sub(r"\b[A-Z]{6}_otc\b", runtime_symbol, aligned_text)
        aligned_text = re.sub(r"\b[A-Z]{6}\sOTC\b", f"{runtime_base} OTC", aligned_text)
        aligned_text = re.sub(r"\b[A-Z]{3}/[A-Z]{3}\sOTC\b", runtime_slash, aligned_text)

    return aligned_text


def _default_invalidators(strategy: Dict) -> List[str]:
    family = strategy.get("family")
    if family == "trend_following":
        return ["trend_break", "spread_expansion", "imbalance_deterioration"]
    if family == "breakout":
        return ["failed_breakout", "spread_expansion", "liquidity_collapse"]
    if family == "mean_reversion":
        return ["missing_price_context", "payout_below_threshold", "regime_breakout"]
    return ["signal_invalidated"]


def _signal_maps(signal_snapshot: Dict) -> tuple[Dict[str, Dict], Dict[str, Dict]]:
    by_strategy = {
        item.get("strategy_id"): item
        for item in signal_snapshot.get("by_strategy", [])
        if isinstance(item, dict) and item.get("strategy_id")
    }
    by_feature = {
        item.get("feature_key"): item
        for item in signal_snapshot.get("items", [])
        if isinstance(item, dict) and item.get("feature_key")
    }
    return by_strategy, by_feature


def _resolve_lane_for_strategy(strategy: Dict) -> Dict:
    venue = strategy.get("venue")
    venues = _venue_health()
    if venue == "ibkr":
        return {
            "platform": "ibkr_paper_executor",
            "venue": "ibkr",
            "status": "market_data_api_ready" if venues["ibkr"]["ready"] else "venue_not_ready",
            "paper_only": True,
            "ready": venues["ibkr"]["ready"],
            "detail": venues["ibkr"]["detail"],
            "symbols_universe": strategy.get("universe", []),
            "reason": "ibkr_paper_shadow_executor",
        }
    if venue == "pocket_option":
        return {
            "platform": "pocket_option_demo_executor",
            "venue": "pocket_option",
            "status": "demo_bridge_live" if venues["pocket_option"]["ready"] else "venue_not_ready",
            "paper_only": True,
            "ready": venues["pocket_option"]["ready"],
            "detail": venues["pocket_option"]["detail"],
            "symbols_universe": strategy.get("universe", []),
            "reason": "pocket_option_demo_shadow_executor",
        }
    return {
        "platform": "internal_paper_simulator",
        "venue": "internal_paper_simulator",
        "status": "available",
        "paper_only": True,
        "ready": True,
        "detail": "safe_fallback",
        "symbols_universe": strategy.get("universe", []),
        "reason": "safe_internal_fallback",
    }


async def _execute_strategy_trade(
    strategy: Dict,
    signal_override: Dict | None = None,
    feature_override: Dict | None = None,
    symbol_override: str | None = None,
    timeframe_override: str | None = None,
    setup_variant_override: str | None = None,
    decision_context: Dict | None = None,
    gate_audit: Dict | None = None,
) -> Dict:
    lane = _resolve_lane_for_strategy(strategy)
    if not lane.get("ready"):
        return {
            "success": False,
            "strategy_id": strategy["strategy_id"],
            "venue": strategy["venue"],
            "paper_only": True,
            "error": "venue_not_ready",
            "selected_lane": lane,
            "data_inputs": _strategy_data_inputs(strategy.get("venue")),
            "symbols_universe": strategy.get("universe", []),
        }

    selected_signal = dict(signal_override or {})
    symbol = symbol_override or selected_signal.get("symbol") or _pick_symbol(strategy, strategy.get("venue"))
    timeframes = strategy.get("timeframes", []) or ["unknown"]
    setup_variants = strategy.get("setup_variants", []) or ["base"]
    timeframe = timeframe_override or selected_signal.get("timeframe") or strategy.get("preferred_timeframe") or timeframes[0]
    setup_variant = setup_variant_override or selected_signal.get("setup_variant") or strategy.get("preferred_setup_variant") or setup_variants[0]

    if not selected_signal:
        return {
            "success": False,
            "strategy_id": strategy["strategy_id"],
            "venue": strategy["venue"],
            "paper_only": True,
            "error": "missing_signal_context",
            "selected_lane": lane,
            "data_inputs": _strategy_data_inputs(strategy.get("venue")),
            "symbols_universe": strategy.get("universe", []),
        }

    selected_signal["symbol"] = symbol
    selected_signal["timeframe"] = timeframe
    selected_signal["setup_variant"] = setup_variant
    selected_signal["duration_seconds"] = (
        selected_signal.get("duration_seconds")
        or _timeframe_to_seconds(timeframe)
        or (feature_override.get("expiry_seconds") if isinstance(feature_override, dict) else None)
    )
    feature = feature_override or {
        "last": selected_signal.get("entry_price"),
        "mid": selected_signal.get("entry_price"),
        "price_available": selected_signal.get("price_available"),
        "last_vs_close_pct": selected_signal.get("last_vs_close_pct", 0.0),
        "bid_ask_imbalance": selected_signal.get("bid_ask_imbalance", 0.0),
        "payout_pct": selected_signal.get("payout_pct"),
        "expiry_seconds": selected_signal.get("duration_seconds"),
    }
    # --- Adaptive Duration Policy (PocketOption only) -----------------------
    # Before executing, check if the volatility regime warrants trading and
    # select the optimal duration.  This replaces the hardcoded 300s fallback.
    venue_for_adp = strategy.get("venue", "")
    if venue_for_adp == "pocket_option":
        adp_features = {
            "bb_bandwidth": feature.get("bb_bandwidth"),
            "adx": feature.get("adx"),
            "price_zscore": feature.get("price_zscore"),
        }
        adp_candidates_raw = feature.get("duration_candidates") or []
        # Extract labels from candidate dicts if needed
        adp_candidates = []
        for c in adp_candidates_raw:
            if isinstance(c, dict):
                adp_candidates.append(str(c.get("label", "")))
            else:
                adp_candidates.append(str(c))
        signal_side = selected_signal.get("direction")
        # P-OP52a: OTC binary pairs have ultra-low bb_bandwidth (~0.05-0.15)
        # compared to normal assets (1-5%). The default ADP config classifies
        # everything as "low_energy" and skips. Use "normal" fallback instead:
        # when energy is low, pick the normal-duration target (300s) so the
        # trade still executes — the signal layer already gated quality.
        _po_adp_cfg = AdaptiveDurationConfig(low_volatility_policy="normal")
        adp_result = build_trade_decision_with_duration(
            features=adp_features,
            duration_candidates=adp_candidates,
            signal_side=signal_side,
            cfg=_po_adp_cfg,
        )
        log.info(
            "AdaptiveDuration %s/%s: decision=%s regime=%s duration=%s reason=%s",
            strategy.get("strategy_id"), symbol,
            adp_result.get("decision"), adp_result.get("regime"),
            adp_result.get("selected_duration_seconds"), adp_result.get("reason"),
        )
        if adp_result.get("decision") == "skip":
            return {
                "success": False,
                "strategy_id": strategy["strategy_id"],
                "venue": strategy["venue"],
                "paper_only": True,
                "error": "adaptive_duration_skip",
                "adaptive_duration": adp_result,
                "selected_lane": lane,
                "signal": selected_signal,
                "data_inputs": _strategy_data_inputs(strategy.get("venue")),
                "symbols_universe": strategy.get("universe", []),
            }
        # Inject selected duration into signal for downstream use
        adp_duration = adp_result.get("selected_duration_seconds")
        if adp_duration:
            selected_signal["duration_seconds"] = adp_duration
            feature["expiry_seconds"] = adp_duration
        # Attach diagnostics to signal for ledger persistence
        selected_signal["adaptive_duration"] = adp_result

    result = execute_signal_paper_trade(strategy, selected_signal, feature, lane, decision_context, gate_audit)
    trade = result.get("trade")
    if not result.get("success") or not trade:
        return {
            "success": False,
            "strategy_id": strategy["strategy_id"],
            "venue": strategy["venue"],
            "paper_only": True,
            "error": result.get("error", "signal_paper_trade_failed"),
            "selected_lane": lane,
            "signal": selected_signal,
            "data_inputs": _strategy_data_inputs(strategy.get("venue")),
            "symbols_universe": strategy.get("universe", []),
        }

    browser_order = None
    if lane.get("platform") == "pocket_option_demo_executor":
        duration = int(
            selected_signal.get("duration_seconds")
            or feature.get("expiry_seconds")
            or _timeframe_to_seconds(timeframe)
            or 60
        )
        amount = float(getattr(_cfg, "PAPER_TRADE_DEFAULT_AMOUNT", 10.0))
        try:
            async with PocketOptionBridge() as po_bridge:  # P-OP28: close session after use
                browser_order = await po_bridge.place_trade(
                    symbol=symbol,
                    direction=selected_signal.get("direction"),
                    amount=amount,
                    duration=duration,
                )
        except Exception as exc:
            log.warning("Pocket Option bridge order dispatch failed for %s: %s", strategy["strategy_id"], exc)
            browser_order = {
                "success": False,
                "status": "dispatch_exception",
                "reason": str(exc),
            }

        trade["browser_order"] = browser_order
        trade["browser_command_dispatched"] = bool(
            isinstance(browser_order, dict) and (
                browser_order.get("click_submitted")
                or browser_order.get("success")
                or browser_order.get("trade_id")
            )
        )
        trade["browser_command_status"] = browser_order.get("status") if isinstance(browser_order, dict) else None
        trade["browser_trade_confirmed"] = bool(browser_order.get("ui_trade_confirmed")) if isinstance(browser_order, dict) else False
        trade["browser_trade_id"] = browser_order.get("trade_id") if isinstance(browser_order, dict) else None
        if not persist_trade_execution_metadata(trade):
            log.debug(
                "Could not persist browser execution metadata for %s/%s at %s",
                trade.get("strategy_id"),
                trade.get("symbol"),
                trade.get("timestamp"),
            )

    return {
        "success": True,
        "trade": trade,
        "signal": selected_signal,
        "selected_lane": lane,
        "browser_order": browser_order,
        "data_inputs": _strategy_data_inputs(strategy.get("venue")),
        "symbols_universe": strategy.get("universe", []),
        "paper_only": True,
    }


def _normalize_strategy_specs() -> Dict:
    raw = read_strategy_specs()
    if raw.get("strategies") and all(not (s.get("strategy_id") or s.get("id")) for s in raw.get("strategies", [])):
        raw = _strategy_seed()
    strategies = []
    seen_ids: set = set()  # P5-08: dedup guard
    hypotheses = {h["strategy_id"]: h for h in read_hypothesis_queue().get("hypotheses", [])}
    for strategy in raw.get("strategies", []):
        strategy_id = strategy.get("strategy_id") or strategy.get("id")
        if not strategy_id:
            continue
        if strategy_id in seen_ids:
            log.warning("P5-08: duplicate strategy_id %r skipped during normalization", strategy_id)
            continue
        seen_ids.add(strategy_id)
        venue_pref = strategy.get("venue_preference") or ([strategy.get("venue")] if strategy.get("venue") else [])
        venue = venue_pref[0] if venue_pref else "internal_paper_simulator"
        live_po_symbol = None
        if venue == "pocket_option":
            bridge = read_json(PO_BRIDGE_PATH, {})
            current = bridge.get("current", {}) if isinstance(bridge.get("current"), dict) else {}
            live_po_symbol = current.get("symbol")
        hyp = hypotheses.get(strategy_id, {})
        raw_universe = strategy.get("universe") or strategy.get("source_universe") or []
        source_universe = list(raw_universe)
        if not source_universe:
            if venue in {"ibkr", "quantconnect"}:
                source_universe = ["SPY", "QQQ", "AAPL"]
            else:
                source_universe = ["EURUSD_otc", "USDCHF_otc", "GBPUSD_otc"]
        universe = list(source_universe)
        runtime_symbol_locked = False
        if venue == "pocket_option" and live_po_symbol:
            # Pocket Option is intentionally operated in single-visible-symbol mode.
            # Keep the knowledge base logic and indicators, but bind the effective
            # runtime universe to the currently visible chart so governance,
            # signals, and execution all speak about the same lane.
            universe = [live_po_symbol]
            runtime_symbol_locked = True
        normalized = {
            "strategy_id": strategy_id,
            "venue": venue,
            "family": strategy.get("family"),
            "status": strategy.get("status", "paper_candidate"),
            # P-OP27: PO bridge streams at 1m granularity; the 5m refers to
            # the trade holding duration, not the chart timeframe.  Accept
            # both so signal_engine doesn't flag "timeframe_not_supported".
            "timeframes": strategy.get("timeframes", ["5m", "15m"] if venue == "ibkr" else ["1m", "5m"]),
            "universe": universe,
            "source_universe": source_universe,
            "runtime_symbol_locked": runtime_symbol_locked,
            "entry": strategy.get("entry", {
                "required_conditions": strategy.get("entry_logic", []),
                "trigger": [],
            }),
            "exit": strategy.get("exit", {
                "stop_loss": "1.0 * atr_14",
                "take_profit": "1.5 * atr_14",
                "time_stop_bars": 12 if venue == "ibkr" else 1,
            }),
            "filters": strategy.get("filters", {
                "spread_pct_max": 0.25 if venue == "ibkr" else None,
                "volatility_min_atr_pct": 0.35 if venue == "ibkr" else None,
                "market_regime_allowed": ["trend_up", "trend_strong_up", "trend_strong_down", "trend_down_mild", "range_break_down", "mild"] if strategy.get("family") in ("trend_following", "breakout") else (["range", "mild", "trend_up", "range_break_down", "trend_strong_up", "trend_strong_down"] if venue == "pocket_option" else ["range", "mild", "trend_up", "trend_down_mild"]),
            }),
            "success_criteria": strategy.get("success_criteria", {
                "min_resolved_trades": 30 if venue == "ibkr" else 20,
                "min_expectancy": 0.10 if venue == "ibkr" else 0.10,
                "min_win_rate": 0.52 if venue == "ibkr" else 0.70,
            }),
            "core_indicators": strategy.get("core_indicators", []),
            "setup_variants": strategy.get("setup_variants") or _setup_variants(strategy),
            "summary": strategy.get("summary"),
            "paper_only": PAPER_ONLY,
            "linked_hypotheses": strategy.get("linked_hypotheses") or ([hyp.get("id")] if hyp.get("id") else []),
            "asset_classes": strategy.get("asset_classes", []),
            "invalidators": strategy.get("invalidators") or _default_invalidators(strategy),
            "auto_generated": bool(strategy.get("auto_generated")),
            "source_strategy": strategy.get("source_strategy"),
        }
        strategies.append(normalize_strategy_asset_profile(normalized))
    payload = {
        "schema_version": "strategy_specs_v1_normalized",
        "updated_utc": _utc_now(),
        "strategies": strategies,
    }
    # Reescribe el archivo canónico con campos formales faltantes sin perder la intención original.
    write_json(STATE_PATH / "trading_knowledge_base" / "strategy_specs.json", payload)
    return payload


# ---------------------------------------------------------------------------
# P3-06: Strategy parameter adaptation
# ---------------------------------------------------------------------------
# P-OP32n: Raised from 0.55 to 0.58 — with new confidence formula (floor 0.20,
# distinct_indicators * 0.08), a 2-indicator mild setup produces ~0.56 confidence.
# Requiring 0.58 means at least 2 indicators + partial strength, or 2 indicators
# with MACD confirmation. Filters out weak single-indicator setups.
_BASE_CONFIDENCE_THRESHOLD = 0.52  # 2026-03-31: raised from 0.45 to reduce noise (was 0.58 pre-relaxation)
_CONFIDENCE_MAX_DELTA = 0.04  # FIX-MZ4 (2026-03-31): 0.10→0.04. Floor=0.48, ceiling=0.56. Prevents over-loosening.
_MIN_SAMPLE_FOR_ADAPTATION = 10

import logging as _logging
_adapt_log = _logging.getLogger("StrategyAdapt")


def adapt_strategy_parameters(strategies: List[Dict], scorecards: Dict) -> List[Dict]:
    """Mutate strategy parameters based on scorecard performance data.

    For each strategy with enough resolved trades (≥ MIN_SAMPLE_FOR_ADAPTATION):
      - Adjusts ``confidence_threshold`` based on win-rate deviation from target.
        Higher win-rate → lower threshold (more permissive signals).
        Lower win-rate → higher threshold (stricter signals).
      - Adjusts ``filters.spread_pct_max`` — good performance loosens the filter
        slightly, bad performance tightens it.

    Clamping:
      - confidence_threshold is clamped to [BASE - 0.04, BASE + 0.04] = [0.48, 0.56]
      - spread_pct_max is clamped to ±30% of the original value

    Strategies with fewer than MIN_SAMPLE_FOR_ADAPTATION resolved trades are
    left untouched (keeps defaults until there's enough evidence).

    Returns the strategies list (modified in-place for convenience).
    """
    for strategy in strategies:
        sid = strategy.get("strategy_id")
        card = scorecards.get(sid, {})
        resolved = int(card.get("entries_resolved", 0) or 0)
        if resolved < _MIN_SAMPLE_FOR_ADAPTATION:
            # Not enough data — keep defaults
            strategy.setdefault("confidence_threshold", _BASE_CONFIDENCE_THRESHOLD)
            continue

        win_rate = float(card.get("win_rate", 0.0) or 0.0)
        expectancy = float(card.get("expectancy", 0.0) or 0.0)
        target_win_rate = float(
            strategy.get("success_criteria", {}).get("min_win_rate", 0.55) or 0.55
        )

        # --- Confidence threshold adaptation ---
        # If win_rate is above target, the strategy is performing well;
        # we can be slightly more permissive on signal confidence.
        # If win_rate is below target, tighten the confidence requirement.
        win_rate_delta = win_rate - target_win_rate  # positive = outperforming
        # Scale: every 0.10 win-rate above target → lower threshold by 0.05
        confidence_adjustment = -(win_rate_delta * 0.5)
        confidence_adjustment = max(-_CONFIDENCE_MAX_DELTA, min(_CONFIDENCE_MAX_DELTA, confidence_adjustment))
        new_threshold = _BASE_CONFIDENCE_THRESHOLD + confidence_adjustment
        new_threshold = round(max(
            _BASE_CONFIDENCE_THRESHOLD - _CONFIDENCE_MAX_DELTA,
            min(_BASE_CONFIDENCE_THRESHOLD + _CONFIDENCE_MAX_DELTA, new_threshold),
        ), 4)
        strategy["confidence_threshold"] = new_threshold

        # --- Filter adaptation (spread_pct_max) ---
        filters = strategy.get("filters", {})
        if filters and filters.get("spread_pct_max") is not None:
            base_spread = float(filters["spread_pct_max"])
            if base_spread > 0 and expectancy > 0:
                # Good performance: loosen filter slightly (up to +30%)
                spread_factor = min(1.30, 1.0 + (win_rate_delta * 0.5))
                filters["spread_pct_max"] = round(base_spread * spread_factor, 4)
            elif base_spread > 0 and expectancy < 0:
                # Bad performance: tighten filter (down to -30%)
                spread_factor = max(0.70, 1.0 + (win_rate_delta * 0.5))
                filters["spread_pct_max"] = round(base_spread * spread_factor, 4)

        # --- P-OP23: Signal threshold adaptation ---
        # Adapt RSI/BB/Stoch thresholds based on trade outcome patterns.
        # Logic: if a strategy is losing, TIGHTEN signal thresholds (require
        # more extreme indicators = fewer but higher-quality signals).
        # If winning, LOOSEN slightly (capture more opportunities).
        # Only for PO strategies (indicator-driven signals).
        if strategy.get("venue") == "pocket_option" and resolved >= _cfg.SIGNAL_THRESHOLD_MIN_SAMPLE:
            _adapt_signal_thresholds(strategy, win_rate, expectancy, target_win_rate, card)

        _adapt_log.debug(
            "Adapted %s: confidence=%.4f (delta=%.4f), resolved=%d, wr=%.2f",
            sid, new_threshold, confidence_adjustment, resolved, win_rate,
        )

    # P-OP23: Persist adaptation snapshot for dashboard visibility
    _persist_adaptation_snapshot(strategies, scorecards)

    return strategies


def _adapt_signal_thresholds(
    strategy: Dict, win_rate: float, expectancy: float,
    target_win_rate: float, card: Dict,
) -> None:
    """Adjust indicator signal thresholds per-strategy based on scorecard.

    Losing strategies get TIGHTER thresholds (more extreme indicators needed
    to trigger, fewer signals but higher quality).
    Winning strategies get LOOSER thresholds (capture more opportunities).

    The shift is bounded by SIGNAL_THRESHOLD_MAX_SHIFT (default ±30%).

    Additionally, uses avg_price_delta from resolved trades to detect if
    signals are triggering on noise (very small moves) vs real setups.
    """
    base = _cfg.SIGNAL_THRESHOLDS_BASE
    max_shift = _cfg.SIGNAL_THRESHOLD_MAX_SHIFT

    # Performance factor: positive = outperforming, negative = underperforming
    # Range roughly [-1, +1] mapped from win_rate deviation
    perf_factor = (win_rate - target_win_rate) / max(target_win_rate, 0.01)
    perf_factor = max(-1.0, min(1.0, perf_factor))

    # Shift direction: underperforming → tighten (shift > 0 for extreme thresholds)
    # For "oversold_strong" (e.g. RSI<25): tighter means LOWER (e.g. RSI<20)
    # For "overbought_strong" (e.g. RSI>75): tighter means HIGHER (e.g. RSI>80)
    # shift_pct: negative = tighten (make thresholds more extreme),
    #            positive = loosen  (make thresholds less extreme)
    shift_pct = perf_factor * max_shift  # e.g. -0.15 if underperforming

    # Also factor in avg price delta — if trades are resolving on tiny
    # moves, signals are triggering on noise → tighten regardless
    avg_resolution_pct = float(card.get("avg_resolution_price_change_pct", 0.0) or 0.0)
    if avg_resolution_pct > 0 and avg_resolution_pct < 0.02:
        # Trades resolving on <0.02% moves — noise territory, tighten more
        shift_pct = min(shift_pct, shift_pct - 0.10)

    shift_pct = max(-max_shift, min(max_shift, shift_pct))

    # Build adapted thresholds
    adapted = {}

    # RSI thresholds
    rsi_base = base["rsi"]
    # "strong oversold" at 25: tighten → lower (e.g. 20), loosen → higher (e.g. 30)
    adapted["rsi_oversold_strong"] = round(
        rsi_base["oversold_strong"] * (1.0 + shift_pct), 1)
    adapted["rsi_oversold_mild"] = round(
        rsi_base["oversold_mild"] * (1.0 + shift_pct), 1)
    # "strong overbought" at 75: tighten → higher (e.g. 80), loosen → lower (e.g. 70)
    adapted["rsi_overbought_strong"] = round(
        rsi_base["overbought_strong"] * (1.0 - shift_pct), 1)
    adapted["rsi_overbought_mild"] = round(
        rsi_base["overbought_mild"] * (1.0 - shift_pct), 1)

    # BB thresholds
    bb_base = base["bb"]
    # "lower_strong" at -0.10: tighten → even more negative, loosen → less negative
    adapted["bb_lower_strong"] = round(
        bb_base["lower_strong"] + (bb_base["lower_strong"] * -shift_pct), 4)
    adapted["bb_lower_mild"] = round(
        bb_base["lower_mild"] * (1.0 + shift_pct), 4)
    # "upper_strong" at 1.10: tighten → higher, loosen → lower
    adapted["bb_upper_strong"] = round(
        bb_base["upper_strong"] + (bb_base["upper_strong"] * -shift_pct * 0.1), 4)
    adapted["bb_upper_mild"] = round(
        bb_base["upper_mild"] * (1.0 - shift_pct), 4)

    # Stoch thresholds
    stoch_base = base["stoch"]
    adapted["stoch_oversold_strong"] = round(
        stoch_base["oversold_strong"] * (1.0 + shift_pct), 1)
    adapted["stoch_oversold_mild"] = round(
        stoch_base["oversold_mild"] * (1.0 + shift_pct), 1)
    adapted["stoch_overbought_strong"] = round(
        stoch_base["overbought_strong"] * (1.0 - shift_pct), 1)
    adapted["stoch_overbought_mild"] = round(
        stoch_base["overbought_mild"] * (1.0 - shift_pct), 1)

    # Stoch crossover zones
    cross_base = base["stoch_crossover"]
    adapted["stoch_call_zone"] = round(
        cross_base["call_zone"] * (1.0 + shift_pct), 1)
    adapted["stoch_put_zone"] = round(
        cross_base["put_zone"] * (1.0 - shift_pct), 1)

    # Store on strategy dict — signal_engine reads these
    strategy["adapted_signal_thresholds"] = adapted
    strategy["_signal_shift_pct"] = round(shift_pct, 4)
    strategy["_signal_perf_factor"] = round(perf_factor, 4)

    _adapt_log.debug(
        "Signal thresholds %s: shift=%.2f%%, perf=%.2f, rsi_os=%.1f/%.1f, rsi_ob=%.1f/%.1f",
        strategy.get("strategy_id"), shift_pct * 100, perf_factor,
        adapted["rsi_oversold_strong"], adapted["rsi_oversold_mild"],
        adapted["rsi_overbought_strong"], adapted["rsi_overbought_mild"],
    )


def _persist_adaptation_snapshot(strategies: List[Dict], scorecards: Dict) -> None:
    """Write a snapshot of current adapted parameters for dashboard visibility."""
    items = []
    for strategy in strategies:
        sid = strategy.get("strategy_id")
        thresholds = strategy.get("adapted_signal_thresholds")
        card = scorecards.get(sid, {})
        items.append({
            "strategy_id": sid,
            "venue": strategy.get("venue"),
            "confidence_threshold": strategy.get("confidence_threshold"),
            "adapted_signal_thresholds": thresholds,
            "signal_shift_pct": strategy.get("_signal_shift_pct"),
            "signal_perf_factor": strategy.get("_signal_perf_factor"),
            "win_rate": float(card.get("win_rate", 0) or 0),
            "expectancy": float(card.get("expectancy", 0) or 0),
            "resolved": int(card.get("entries_resolved", 0) or 0),
        })
    snapshot = {
        "schema_version": "adaptation_snapshot_v1",
        "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "items": items,
        "adapted_count": sum(1 for i in items if i.get("adapted_signal_thresholds")),
        "total_strategies": len(items),
    }
    write_json(_cfg.ADAPTATION_HISTORY_PATH, snapshot)
    _adapt_log.debug("Persisted adaptation snapshot: %d/%d adapted", snapshot["adapted_count"], len(items))


def _venue_health() -> Dict[str, Dict]:
    po = read_json(PO_BRIDGE_PATH, {})
    ibkr = read_json(IBKR_PROBE_PATH, {})
    ibkr_order = read_json(IBKR_ORDER_CHECK_PATH, {})
    ibkr_port_open = False
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        ibkr_port_open = sock.connect_ex((IBKR_HOST, IBKR_PORT)) == 0
        sock.close()
    except Exception as exc:
        log.debug("IBKR socket probe failed: %s", exc)
        ibkr_port_open = False
    ibkr_connected = bool(ibkr.get("connected"))
    ibkr_market_data_ready = ibkr_port_open and ibkr_connected
    # P-OP30a: Also gate on market hours — no IBKR trades when US market closed
    from brain_v9.config import is_venue_market_open
    if not is_venue_market_open("ibkr"):
        ibkr_market_data_ready = False
    ibkr_order_ready = bool(ibkr_order.get("order_api_ready"))
    ibkr_detail = "market_data_api_ready" if ibkr_market_data_ready else "socket_or_gateway_unavailable"
    if not is_venue_market_open("ibkr"):
        ibkr_detail = "market_closed"
    if ibkr_market_data_ready and ibkr_order_ready:
        ibkr_detail = "paper_order_api_ready"
    return {
        "ibkr": {
            "ready": ibkr_market_data_ready,
            "detail": ibkr_detail,
            "paper_shadow_ready": ibkr_market_data_ready,
            "paper_order_ready": ibkr_order_ready,
        },
        "pocket_option": {
            "ready": bool(po.get("current") and po.get("captured_utc")),
            "detail": "demo_bridge_live" if po.get("current") and po.get("captured_utc") else "bridge_not_ready",
        },
        "internal_paper_simulator": {
            "ready": True,
            "detail": "safe_fallback",
        },
    }


def refresh_strategy_engine() -> Dict:
    with ENGINE_LOCK:
        specs = _normalize_strategy_specs()
        strategies = specs.get("strategies", [])
        ensure_scorecards(strategies)
        # P3-06: Adapt strategy parameters (confidence thresholds, filters)
        # based on scorecard performance BEFORE signal evaluation uses them.
        pre_adapt_scorecards = read_scorecards().get("scorecards", {})
        adapt_strategy_parameters(strategies, pre_adapt_scorecards)
        scorecards_payload = read_scorecards()
        scorecards = scorecards_payload.get("scorecards", {})
        symbol_scorecards = scorecards_payload.get("symbol_scorecards", {})
        context_scorecards = scorecards_payload.get("context_scorecards", {})
        top_action = read_json(NEXT_ACTIONS_PATH, {}).get("top_action")
        venues = _venue_health()
        hypothesis_payload = evaluate_hypotheses(read_hypothesis_queue().get("hypotheses", []), scorecards)
        archive_payload = build_strategy_archive(strategies, scorecards_payload, hypothesis_payload)
        active_catalog_payload = build_active_strategy_catalog_snapshot(
            strategies,
            scorecards_payload,
            archive_payload,
            venue_health=venues,
        )
        active_catalog_by_strategy = {
            item.get("strategy_id"): item
            for item in active_catalog_payload.get("items", [])
            if isinstance(item, dict) and item.get("strategy_id")
        }
        operational_ids = set(active_catalog_payload.get("summary", {}).get("operational_strategy_ids", []) or [])
        operational_strategies = [s for s in strategies if s.get("strategy_id") in operational_ids]
        history_snapshot = build_market_history_snapshot(operational_strategies)
        feature_snapshot = build_market_feature_snapshot()
        # Resolve pending paper trades with fresh feature data (P3-02 deferred resolution)
        resolve_pending_paper_trades(feature_snapshot)
        signal_snapshot = build_strategy_signal_snapshot(operational_strategies, feature_snapshot)
        expectancy_snapshot = build_expectancy_snapshot()
        signal_by_strategy, signal_by_feature = _signal_maps(signal_snapshot)
        feature_by_key = {
            item.get("key"): item
            for item in feature_snapshot.get("items", [])
            if isinstance(item, dict) and item.get("key")
        }
        history_by_symbol = history_snapshot.get("symbols", {}) or {}
        expectancy_by_strategy = {
            item.get("strategy_id"): item
            for item in expectancy_snapshot.get("by_strategy", {}).get("items", [])
        }
        expectancy_by_symbol = {
            item.get("key"): item
            for item in expectancy_snapshot.get("by_strategy_symbol", {}).get("items", [])
        }
        expectancy_by_context = {
            item.get("key"): item
            for item in expectancy_snapshot.get("by_strategy_context", {}).get("items", [])
        }
        archived_index = {
            item.get("strategy_id"): item
            for item in archive_payload.get("archived", [])
            if item.get("strategy_id")
        }

        raw_candidates = build_strategy_candidates(operational_strategies)
        candidates = []
        for candidate in raw_candidates:
            strategy = next((s for s in strategies if s["strategy_id"] == candidate["strategy_id"]), None)
            if not strategy:
                continue
            venue = strategy["venue"]
            card = scorecards.get(strategy["strategy_id"], {})
            best_symbol = _best_symbol_snapshot(strategy, symbol_scorecards)
            best_context = _best_context_snapshot(strategy, context_scorecards)
            expectancy_strategy = expectancy_by_strategy.get(strategy["strategy_id"], {})
            best_symbol_key = _symbol_key(strategy, best_symbol.get("symbol")) if best_symbol.get("symbol") else None
            best_context_key = (
                _context_key(
                    strategy,
                    best_context.get("symbol"),
                    best_context.get("timeframe"),
                    best_context.get("setup_variant"),
                )
                if best_context.get("symbol") and best_context.get("timeframe") and best_context.get("setup_variant")
                else None
            )
            expectancy_symbol = expectancy_by_symbol.get(best_symbol_key, {})
            expectancy_context = expectancy_by_context.get(best_context_key, {})
            signal_info = signal_by_strategy.get(strategy["strategy_id"], {})
            best_signal = signal_info.get("best_signal") or {}
            feature_ref = feature_by_key.get(best_signal.get("feature_key"), {})
            archive_info = archived_index.get(strategy["strategy_id"], {})
            catalog_info = active_catalog_by_strategy.get(strategy["strategy_id"], {})
            history_symbol = history_by_symbol.get(best_signal.get("symbol") or best_context.get("symbol") or best_symbol.get("symbol") or "") or {}
            venue_health_score = 1.0 if venues.get(venue, {}).get("paper_order_ready") else 0.8 if venues.get(venue, {}).get("ready") else 0.0
            regime_alignment_score = 1.0 if expectancy_context.get("expectancy", 0.0) > 0 else 0.6 if expectancy_symbol.get("expectancy", 0.0) > 0 else 0.3
            candidate_payload = {
                "strategy_id": strategy["strategy_id"],
                "venue": venue,
                "family": strategy.get("family"),
                "asset_classes": strategy.get("asset_classes", []),
                "primary_asset_class": strategy.get("primary_asset_class"),
                "invalidators": strategy.get("invalidators", []),
                "summary": _runtime_aligned_text(strategy.get("summary"), strategy),
                "indicators": strategy.get("core_indicators", []),
                "objective": _runtime_aligned_text(candidate.get("objective"), strategy),
                "success_metric": candidate.get("success_metric"),
                "success_criteria": strategy.get("success_criteria", {}),
                "paper_only": True,
                "venue_ready": venues.get(venue, {}).get("ready", False),
                "venue_detail": venues.get(venue, {}).get("detail"),
                "sample_quality": expectancy_strategy.get("sample_quality", card.get("sample_quality", 0.0)),
                "entries_resolved": expectancy_strategy.get("entries_resolved", card.get("entries_resolved", 0)),
                "expectancy": expectancy_strategy.get("expectancy", card.get("expectancy", 0.0)),
                "consistency_score": expectancy_strategy.get("consistency_score", card.get("consistency_score", 0.0)),
                "profit_factor": expectancy_strategy.get("profit_factor", card.get("profit_factor", 0.0)),
                "win_rate": expectancy_strategy.get("win_rate", card.get("win_rate", 0.0)),
                "drawdown_penalty": expectancy_strategy.get("drawdown_penalty", 0.0),
                "expectancy_score": expectancy_strategy.get("expectancy_score", 0.0),
                "win_rate_score": expectancy_strategy.get("win_rate_score", 0.0),
                "profit_factor_score": expectancy_strategy.get("profit_factor_score", 0.0),
                "recent_stability": expectancy_strategy.get("recent_stability", 0.0),
                "recent_5_outcomes": expectancy_strategy.get("recent_5_outcomes", []),
                "last_trade_utc": expectancy_strategy.get("last_trade_utc"),
                "promotion_state": card.get("promotion_state", "paper_candidate"),
                "governance_state": card.get("governance_state", card.get("promotion_state", "paper_candidate")),
                "freeze_recommended": card.get("freeze_recommended", False),
                "promote_candidate": card.get("promote_candidate", False),
                "watch_recommended": card.get("watch_recommended", False),
                "universe": strategy.get("universe", []),
                "best_symbol": best_symbol.get("symbol"),
                "symbol_expectancy": expectancy_symbol.get("expectancy", best_symbol.get("expectancy", 0.0)),
                "symbol_sample_quality": expectancy_symbol.get("sample_quality", best_symbol.get("sample_quality", 0.0)),
                "symbol_consistency_score": expectancy_symbol.get("consistency_score", best_symbol.get("consistency_score", 0.0)),
                "symbol_entries_resolved": expectancy_symbol.get("entries_resolved", best_symbol.get("entries_resolved", 0)),
                "symbol_expectancy_score": expectancy_symbol.get("expectancy_score", 0.0),
                "symbol_win_rate": expectancy_symbol.get("win_rate", 0.0),
                "symbol_profit_factor": expectancy_symbol.get("profit_factor", 0.0),
                "context_symbol": best_context.get("symbol"),
                "context_timeframe": best_context.get("timeframe"),
                "context_setup_variant": best_context.get("setup_variant"),
                "context_expectancy": expectancy_context.get("expectancy", best_context.get("expectancy", 0.0)),
                "context_sample_quality": expectancy_context.get("sample_quality", best_context.get("sample_quality", 0.0)),
                "context_consistency_score": expectancy_context.get("consistency_score", best_context.get("consistency_score", 0.0)),
                "context_entries_resolved": expectancy_context.get("entries_resolved", best_context.get("entries_resolved", 0)),
                "context_expectancy_score": expectancy_context.get("expectancy_score", 0.0),
                "context_win_rate": expectancy_context.get("win_rate", 0.0),
                "context_profit_factor": expectancy_context.get("profit_factor", 0.0),
                "context_governance_state": next(
                    (
                        context_scorecards.get(key, {}).get("governance_state")
                        for key in context_scorecards.keys()
                        if key == f'{strategy["venue"]}::{strategy["strategy_id"]}::{best_context.get("symbol")}::{best_context.get("timeframe")}::{best_context.get("setup_variant")}'
                    ),
                    "paper_candidate",
                ),
                "venue_health_score": venue_health_score,
                "regime_alignment_score": regime_alignment_score,
                "execution_ready": bool(best_signal.get("execution_ready")),
                "signal_valid": bool(best_signal.get("signal_valid")),
                "signal_confidence": best_signal.get("confidence", 0.0),
                "signal_score": best_signal.get("signal_score", 0.0),
                "signal_direction": best_signal.get("direction"),
                "signal_symbol": best_signal.get("symbol"),
                "signal_timeframe": best_signal.get("timeframe"),
                "signal_setup_variant": best_signal.get("setup_variant"),
                "signal_blockers": best_signal.get("blockers", []),
                "signal_reasons": best_signal.get("reasons", []),
                "signal_market_regime": best_signal.get("market_regime"),
                "archive_state": archive_info.get("archive_state", "testing"),
                "archive_reason": archive_info.get("archive_reason"),
                "catalog_state": catalog_info.get("catalog_state"),
                "catalog_reason": catalog_info.get("catalog_reason"),
                "catalog_lane_key": catalog_info.get("lane_key"),
                "catalog_timeframe": catalog_info.get("catalog_timeframe"),
                "catalog_symbol": catalog_info.get("catalog_symbol"),
                "catalog_decision_scope": catalog_info.get("decision_scope"),
                "catalog_lane_winner": catalog_info.get("lane_winner", True),
                "feature_price_available": feature_ref.get("price_available"),
                "feature_last": feature_ref.get("last"),
                "feature_last_vs_close_pct": feature_ref.get("last_vs_close_pct"),
                "feature_bid_ask_imbalance": feature_ref.get("bid_ask_imbalance"),
                "feature_payout_pct": feature_ref.get("payout_pct"),
                "feature_indicator_count": feature_ref.get("indicator_count"),
                "feature_indicator_access_ready": feature_ref.get("indicator_access_ready"),
                "feature_available_timeframes": feature_ref.get("available_timeframes", []),
                "feature_expiry_seconds": feature_ref.get("expiry_seconds"),
                "history_ready": bool(history_symbol.get("history_ready")),
                "history_rows": history_symbol.get("row_count", 0),
                "history_granularity": history_symbol.get("granularity"),
            }
            candidate_payload["deadlock_unfreeze_utc"] = card.get("deadlock_unfreeze_utc")
            candidate_payload["signal_ready"] = bool(best_signal.get("execution_ready"))
            candidate_payload["governance_ready"] = _governance_ready(candidate_payload)
            candidate_payload["execution_ready_now"] = bool(
                candidate_payload["signal_ready"] and candidate_payload["governance_ready"]
            )
            candidate_payload["preferred_symbol"] = (
                best_signal.get("symbol")
                or best_context.get("symbol")
                or best_symbol.get("symbol")
                or (strategy.get("universe", [None])[0])
            )
            candidate_payload["recommended_iterations"] = _recommended_iterations(candidate_payload)
            candidate_payload["preferred_timeframe"] = best_signal.get("timeframe") or best_context.get("timeframe") or (strategy.get("timeframes") or ["unknown"])[0]
            candidate_payload["preferred_duration_seconds"] = (
                best_signal.get("duration_seconds")
                or feature_ref.get("expiry_seconds")
                or _timeframe_to_seconds(candidate_payload["preferred_timeframe"])
            )
            candidate_payload["preferred_setup_variant"] = best_signal.get("setup_variant") or best_context.get("setup_variant") or (strategy.get("setup_variants") or ["base"])[0]
            current_context = _specific_context_snapshot(
                strategy,
                context_scorecards,
                candidate_payload["preferred_symbol"],
                candidate_payload["preferred_timeframe"],
                candidate_payload["preferred_setup_variant"],
            )
            current_context_expectancy = expectancy_by_context.get(current_context.get("key"), {})
            candidate_payload["current_context_key"] = current_context.get("key")
            candidate_payload["current_context_symbol"] = current_context.get("symbol")
            candidate_payload["current_context_timeframe"] = current_context.get("timeframe")
            candidate_payload["current_context_setup_variant"] = current_context.get("setup_variant")
            candidate_payload["current_context_expectancy"] = current_context_expectancy.get("expectancy", current_context.get("expectancy", 0.0))
            candidate_payload["current_context_sample_quality"] = current_context_expectancy.get("sample_quality", current_context.get("sample_quality", 0.0))
            candidate_payload["current_context_consistency_score"] = current_context_expectancy.get("consistency_score", current_context.get("consistency_score", 0.0))
            candidate_payload["current_context_entries_resolved"] = current_context_expectancy.get("entries_resolved", current_context.get("entries_resolved", 0))
            candidate_payload["current_context_expectancy_score"] = current_context_expectancy.get("expectancy_score", 0.0)
            candidate_payload["current_context_governance_state"] = current_context.get("governance_state", "paper_candidate")
            candidate_payload["context_scorecards_available"] = len([
                key for key in context_scorecards.keys()
                if key.startswith(f'{strategy["venue"]}::{strategy["strategy_id"]}::{candidate_payload["preferred_symbol"]}::')
            ])
            candidates.append(candidate_payload)

        pre_rank_context_edge_validation = build_context_edge_validation_snapshot(candidates)
        pre_rank_context_by_strategy = {
            item.get("strategy_id"): item
            for item in pre_rank_context_edge_validation.get("items", [])
            if item.get("strategy_id")
        }
        for candidate in candidates:
            candidate.update(pre_rank_context_by_strategy.get(candidate.get("strategy_id"), {}))

        ranked = build_ranking(candidates, top_action)
        edge_validation_payload = build_edge_validation_snapshot(ranked)
        context_edge_validation_payload = build_context_edge_validation_snapshot(ranked)
        edge_by_strategy = {
            item.get("strategy_id"): item
            for item in edge_validation_payload.get("items", [])
            if item.get("strategy_id")
        }
        context_edge_by_strategy = {
            item.get("strategy_id"): item
            for item in context_edge_validation_payload.get("items", [])
            if item.get("strategy_id")
        }
        for candidate in ranked:
            candidate.update(edge_by_strategy.get(candidate.get("strategy_id"), {}))
            candidate.update(context_edge_by_strategy.get(candidate.get("strategy_id"), {}))
        allow_frozen_top = top_action == "select_and_compare_strategies"
        top_candidate = _annotate_candidate(
            choose_top_candidate(ranked, allow_frozen=allow_frozen_top),
            "strict_top" if not allow_frozen_top else "comparison_top",
        )
        recovery_candidate = _annotate_candidate(choose_recovery_candidate(ranked), "recovery_candidate")
        exploit_candidate = _annotate_candidate(
            choose_exploit_candidate(ranked),
            "exploit_candidate",
        )
        explore_candidate = _annotate_candidate(
            choose_explore_candidate(ranked, exclude_strategy_id=(exploit_candidate or {}).get("strategy_id")),
            "explore_candidate",
        )
        probation_candidate = _annotate_candidate(
            choose_probation_candidate(
                ranked,
                exclude_strategy_id=(exploit_candidate or {}).get("strategy_id"),
            ),
            "probation_candidate",
        )
        candidates_payload = {
            "schema_version": "strategy_candidates_latest_v1",
            "generated_utc": _utc_now(),
            "top_action": top_action,
            "top_candidate": top_candidate,
            "top_recovery_candidate": recovery_candidate,
            "exploit_candidate": exploit_candidate,
            "explore_candidate": explore_candidate,
            "probation_candidate": probation_candidate,
            "candidates": ranked,
        }
        write_json(CANDIDATES_PATH, candidates_payload)

        ranking_payload = {
            "schema_version": "strategy_ranking_latest_v2",
            "generated_utc": _utc_now(),
            "top_action": top_action,
            "top_strategy": top_candidate,
            "top_recovery_candidate": recovery_candidate,
            "exploit_candidate": exploit_candidate,
            "explore_candidate": explore_candidate,
            "probation_candidate": probation_candidate,
            "ranked": ranked,
            "scorecards_path": str(SCORECARDS_PATH),
            "hypothesis_results_path": str(HYP_RESULTS_PATH),
            "expectancy_snapshot_path": str(ENGINE_PATH / "expectancy_snapshot_latest.json"),
            "feature_snapshot_path": str(FEATURE_SNAPSHOT_PATH),
            "signal_snapshot_path": str(SIGNAL_SNAPSHOT_PATH),
            "strategy_archive_path": str(ARCHIVE_PATH),
            "edge_validation_path": str(EDGE_VALIDATION_PATH),
            "edge_validation_summary": edge_validation_payload.get("summary", {}),
            "context_edge_validation_path": str(CONTEXT_EDGE_VALIDATION_PATH),
            "context_edge_validation_summary": context_edge_validation_payload.get("summary", {}),
            "active_catalog_path": str(ACTIVE_CATALOG_PATH),
            "active_catalog_summary": active_catalog_payload.get("summary", {}),
            "ranking_spread_top1_top2": round(
                (
                    float(ranked[0].get("rank_score", 0.0) or 0.0)
                    - float(ranked[1].get("rank_score", 0.0) or 0.0)
                ) if len(ranked) > 1 else float(ranked[0].get("rank_score", 0.0) or 0.0) if ranked else 0.0,
                4,
            ),
        }
        write_json(RANKING_PATH, ranking_payload)
        write_json(RANKING_V2_PATH, ranking_payload)
        from brain_v9.brain.utility import write_utility_snapshots

        utility_payload = write_utility_snapshots()
        pipeline_integrity_payload = build_pipeline_integrity_snapshot()

        # Fase 3.3: Build learning loop snapshot and trigger variant generation
        # when the loop indicates refuted lanes are ready for variant exploration.
        learning_loop_payload = {}
        generated_variants: list[str] = []
        sim_gate_results: list[dict] = []
        try:
            from brain_v9.trading.learning_loop import build_learning_loop_snapshot
            learning_loop_payload = build_learning_loop_snapshot()
            ll_summary = learning_loop_payload.get("summary", {})
            if ll_summary.get("allow_variant_generation") and ll_summary.get("variant_generation_sources"):
                generated_variants = generate_strategy_variants(max_variants=2)
                if generated_variants:
                    log.info(
                        "Learning loop triggered variant generation: %s",
                        generated_variants,
                    )
                    # Fase 6: Run backtest gate on new variants before probation
                    try:
                        from brain_v9.trading.backtest_gate import research_to_probation_gate
                        all_specs = _normalize_strategy_specs().get("strategies", [])
                        for vid in generated_variants:
                            vspec = next((s for s in all_specs if s.get("strategy_id") == vid), None)
                            if vspec:
                                gate_result = research_to_probation_gate(vspec)
                                sim_gate_results.append(gate_result)
                                if not gate_result.get("passed"):
                                    log.warning(
                                        "Backtest gate REJECTED variant %s: %s",
                                        vid,
                                        gate_result.get("checks", {}).get("simulation", {}).get("reason", "unknown"),
                                    )
                                else:
                                    log.info("Backtest gate PASSED variant %s", vid)
                    except Exception as gate_exc:
                        log.warning("Backtest gate error (non-fatal): %s", gate_exc)
        except Exception as exc:
            log.warning("Learning loop integration error (non-fatal): %s", exc)

        _append_report({
            "timestamp": _utc_now(),
            "event": "strategy_engine_refresh",
            "top_action": top_action,
            "top_strategy_id": top_candidate.get("strategy_id") if top_candidate else None,
            "top_recovery_strategy_id": recovery_candidate.get("strategy_id") if recovery_candidate else None,
            "exploit_candidate_id": exploit_candidate.get("strategy_id") if exploit_candidate else None,
            "explore_candidate_id": explore_candidate.get("strategy_id") if explore_candidate else None,
            "candidates_count": len(ranked),
        })
        return {
            "summary": {
                "updated_utc": ranking_payload["generated_utc"],
                "top_action": top_action,
                "top_candidate": top_candidate,
                "top_recovery_candidate": recovery_candidate,
                "probation_candidate": probation_candidate,
                "strategies_count": len(strategies),
                "scorecards_count": len(scorecards),
                "symbol_scorecards_count": len(symbol_scorecards),
                "context_scorecards_count": len(context_scorecards),
                "feature_snapshot": feature_snapshot.get("summary", {}),
                "history_snapshot": history_snapshot.get("summary", {}),
                "signal_summary": {
                    "signals_count": signal_snapshot.get("signals_count", 0),
                    "ready_signals": sum(
                        1 for item in ranked
                        if item.get("execution_ready_now") and item.get("current_context_execution_allowed")
                    ),
                    "probation_ready_signals": sum(
                        1 for item in ranked
                        if item.get("probation_eligible")
                        and str(item.get("current_context_edge_state") or "") == "unproven"
                        and item.get("execution_ready_now")
                    ),
                },
                "edge_validation_summary": edge_validation_payload.get("summary", {}),
                "context_edge_validation_summary": context_edge_validation_payload.get("summary", {}),
                "active_catalog_summary": active_catalog_payload.get("summary", {}),
                "pipeline_integrity_summary": pipeline_integrity_payload.get("summary", {}),
                "archive_summary": archive_payload.get("summary", {}),
                "expectancy_snapshot": expectancy_snapshot.get("summary", {}),
                "hypotheses_count": len(hypothesis_payload.get("results", [])),
                "latest_comparison_cycle": _latest_comparison_cycle(),
            },
            "candidates": candidates_payload,
            "scorecards": scorecards_payload,
            "history": history_snapshot,
            "features": feature_snapshot,
            "signals": signal_snapshot,
            "archive": archive_payload,
            "active_catalog": active_catalog_payload,
            "expectancy": expectancy_snapshot,
            "edge_validation": edge_validation_payload,
            "context_edge_validation": context_edge_validation_payload,
            "pipeline_integrity": pipeline_integrity_payload,
            "ranking": ranking_payload,
            "hypotheses": hypothesis_payload,
            "utility": utility_payload,
            "learning_loop": learning_loop_payload,
            "generated_variants": generated_variants,
            "sim_gate_results": sim_gate_results,
        }


async def execute_top_candidate() -> Dict:
    refreshed = refresh_strategy_engine()
    ranking = refreshed["ranking"]
    top_candidate = (
        ranking.get("top_strategy")
        or ranking.get("exploit_candidate")
        or ranking.get("top_recovery_candidate")
        or ranking.get("probation_candidate")
    )
    if not top_candidate:
        return {"success": False, "error": "No hay top candidate disponible"}

    return await execute_candidate(
        top_candidate.get("strategy_id"),
        top_candidate.get("preferred_symbol"),
        top_candidate.get("preferred_timeframe"),
        top_candidate.get("preferred_setup_variant"),
    )


async def execute_candidate(
    strategy_id: str,
    symbol_override: str | None = None,
    timeframe_override: str | None = None,
    setup_variant_override: str | None = None,
    allow_frozen: bool = False,
) -> Dict:
    with ENGINE_LOCK:
        refreshed = refresh_strategy_engine()
        ranked = refreshed["ranking"].get("ranked", [])
        candidate = next((item for item in ranked if item.get("strategy_id") == strategy_id), None)
        signal_snapshot = refreshed.get("signals", read_strategy_signal_snapshot())
        signal_by_strategy, _ = _signal_maps(signal_snapshot)
        signal_info = signal_by_strategy.get(strategy_id, {})
        best_signal = dict(signal_info.get("best_signal") or {})
        feature_snapshot = refreshed.get("features", read_feature_snapshot())
        feature_ref = next(
            (
                item for item in feature_snapshot.get("items", [])
                if isinstance(item, dict) and item.get("key") == best_signal.get("feature_key")
            ),
            {},
        )
        archive_payload = refreshed.get("archive", read_strategy_archive())
        archived_ids = {item.get("strategy_id") for item in archive_payload.get("archived", [])}
        specs = _normalize_strategy_specs()
        strategy = next((s for s in specs.get("strategies", []) if s["strategy_id"] == strategy_id), None)
        if not strategy:
            return {"success": False, "error": "Strategy no encontrada en specs", "strategy_id": strategy_id}
        force_sample_expansion = False
        sample_quality = 0.0
        if candidate:
            sample_quality = max(
                float(candidate.get("sample_quality", 0.0) or 0.0),
                float(candidate.get("context_sample_quality", 0.0) or 0.0),
            )
        if strategy_id in archived_ids:
            return {
                "success": False,
                "error": "strategy_archived_for_execution",
                "strategy_id": strategy_id,
                "venue": strategy.get("venue"),
                "paper_only": True,
            }
        if candidate and not allow_frozen:
            governance_state = candidate.get("governance_state")
            context_governance_state = candidate.get("context_governance_state")
            if candidate.get("freeze_recommended") or governance_state == "frozen" or context_governance_state == "frozen":
                return {
                    "success": False,
                    "error": "strategy_frozen_for_execution",
                    "strategy_id": strategy_id,
                    "venue": strategy.get("venue"),
            "paper_only": PAPER_ONLY,
                    "governance_state": governance_state,
                    "context_governance_state": context_governance_state,
                    "freeze_recommended": candidate.get("freeze_recommended", False),
                }
        if candidate and not (candidate.get("execution_ready") or candidate.get("execution_ready_now")):
            # P-OP31b: For operational under-sampled strategies, allow
            # synthetic paper execution to expand sample depth even when
            # the live signal engine has no ready signal.
            catalog_state = str(candidate.get("catalog_state") or "")
            if catalog_state in {"active", "probation"} and sample_quality < 0.55:
                force_sample_expansion = True
            else:
                return {
                    "success": False,
                    "error": "strategy_signal_not_ready",
                    "strategy_id": strategy_id,
                    "venue": strategy.get("venue"),
                    "paper_only": True,
                    "signal_blockers": candidate.get("signal_blockers", []),
                    "signal_reasons": candidate.get("signal_reasons", []),
                }
        if candidate and str(candidate.get("governance_lane") or "") == "probation":
            probation_cap = _probation_window_cap(candidate)
            resolved = int(candidate.get("entries_resolved") or 0)
            if probation_cap > 0 and resolved >= probation_cap:
                return {
                    "success": False,
                    "error": "probation_window_complete_refresh_required",
                    "strategy_id": strategy_id,
                    "venue": strategy.get("venue"),
                    "paper_only": True,
                    "governance_lane": "probation",
                    "entries_resolved": resolved,
                    "probation_cap": probation_cap,
                }
        risk_status = enforce_risk_contract_for_execution(source="strategy_engine.execute_candidate")
        if not risk_status.get("execution_allowed", False):
            return {
                "success": False,
                "error": "risk_contract_violation",
                "strategy_id": strategy_id,
                "venue": strategy.get("venue"),
                "paper_only": True,
                "risk_status": risk_status,
            }
        if symbol_override:
            strategy = dict(strategy)
            strategy["preferred_symbol"] = symbol_override
            strategy["preferred_timeframe"] = timeframe_override or strategy.get("preferred_timeframe")
            strategy["preferred_setup_variant"] = setup_variant_override or strategy.get("preferred_setup_variant")
            if best_signal:
                best_signal["symbol"] = symbol_override
                best_signal["timeframe"] = timeframe_override or best_signal.get("timeframe")
                best_signal["setup_variant"] = setup_variant_override or best_signal.get("setup_variant")

        if force_sample_expansion:
            preferred_symbol = (
                symbol_override
                or (candidate or {}).get("preferred_symbol")
                or strategy.get("preferred_symbol")
                or _pick_symbol(strategy, strategy.get("venue"))
            )
            timeframes = strategy.get("timeframes", []) or ["1d"]
            setup_variants = strategy.get("setup_variants", []) or ["base"]
            preferred_timeframe = (
                timeframe_override
                or (candidate or {}).get("preferred_timeframe")
                or strategy.get("preferred_timeframe")
                or timeframes[0]
            )
            preferred_setup_variant = (
                setup_variant_override
                or (candidate or {}).get("preferred_setup_variant")
                or strategy.get("preferred_setup_variant")
                or setup_variants[0]
            )
            default_direction = _default_direction(strategy.get("family"))
            duration_seconds = _timeframe_to_seconds(preferred_timeframe) or 300
            synthetic_feature_key = f"sample_expansion::{strategy_id}::{preferred_symbol}::{preferred_timeframe}"
            best_signal = dict(best_signal or {})
            best_signal.setdefault("direction", default_direction)
            best_signal.setdefault("confidence", 0.5)
            best_signal.setdefault("signal_score", 0.0)
            sample_signal_score = float(best_signal.get("signal_score") or 0.0)
            if sample_signal_score < MIN_EXECUTION_SIGNAL_SCORE:
                return {
                    "success": False,
                    "error": "sample_expansion_signal_score_below_minimum",
                    "strategy_id": strategy_id,
                    "venue": strategy.get("venue"),
                    "paper_only": True,
                    "signal_score": sample_signal_score,
                    "minimum_signal_score": MIN_EXECUTION_SIGNAL_SCORE,
                    "signal_blockers": list(best_signal.get("blockers") or []) + [
                        f"signal_score_below_minimum({sample_signal_score:.3f}<{MIN_EXECUTION_SIGNAL_SCORE})"
                    ],
                    "sample_quality": sample_quality,
                }
            best_signal["execution_ready"] = True
            best_signal["signal_valid"] = True
            best_signal["price_available"] = True
            best_signal["symbol"] = preferred_symbol
            best_signal["timeframe"] = preferred_timeframe
            best_signal["setup_variant"] = preferred_setup_variant
            best_signal["duration_seconds"] = duration_seconds
            best_signal["feature_key"] = str(best_signal.get("feature_key") or synthetic_feature_key)
            reasons = list(best_signal.get("reasons") or [])
            if "sample_expansion_fallback" not in reasons:
                reasons.append("sample_expansion_fallback")
            best_signal["reasons"] = reasons

            feature_ref = dict(feature_ref or {})
            baseline_price = feature_ref.get("last") or feature_ref.get("mid")
            if baseline_price in (None, "", 0):
                baseline_price = 1.0 if str(preferred_symbol).endswith("_otc") else 100.0
            try:
                baseline_price = float(baseline_price)
            except Exception:
                baseline_price = 1.0 if str(preferred_symbol).endswith("_otc") else 100.0
            feature_ref["last"] = baseline_price
            feature_ref["mid"] = baseline_price
            feature_ref["price_available"] = True
            feature_ref["symbol"] = preferred_symbol
            feature_ref["timeframe"] = preferred_timeframe
            feature_ref["key"] = best_signal["feature_key"]
            feature_ref.setdefault("expiry_seconds", duration_seconds)

        # Fase 5.3: gate_audit — record which gates passed before execution
        gate_audit = {
            "governance_state": (candidate or {}).get("governance_state"),
            "context_governance_state": (candidate or {}).get("context_governance_state"),
            "freeze_recommended": (candidate or {}).get("freeze_recommended", False),
            "archive_state": (candidate or {}).get("archive_state"),
            "risk_contract_execution_allowed": risk_status.get("execution_allowed", False),
            "risk_contract_kill_switch_active": risk_status.get("kill_switch_active", False),
            "risk_daily_loss_ok": risk_status.get("daily_loss_within_limit", True),
            "risk_weekly_drawdown_ok": risk_status.get("weekly_drawdown_within_limit", True),
            "execution_ready": (candidate or {}).get("execution_ready"),
            "governance_lane": (candidate or {}).get("governance_lane"),
            "force_sample_expansion": force_sample_expansion,
            "sample_quality": sample_quality,
        }

        # Fase 5.3: decision_context — why the trade was taken (pre-build for ledger)
        pre_decision_context = {
            "observation": {
                "signal_reasons": (best_signal or {}).get("signal_reasons", []) or (best_signal or {}).get("reasons", []),
                "signal_blockers": (best_signal or {}).get("signal_blockers", []) or (best_signal or {}).get("blockers", []),
                "signal_score": (best_signal or {}).get("signal_score"),
                "confidence": (best_signal or {}).get("confidence"),
            },
            "why_acted": {
                "governance_state": (candidate or {}).get("governance_state"),
                "governance_lane": (candidate or {}).get("governance_lane"),
                "edge_state": (candidate or {}).get("edge_state"),
                "context_edge_state": (candidate or {}).get("current_context_edge_state"),
                "rank_position": next(
                    (i + 1 for i, r in enumerate(ranked) if r.get("strategy_id") == strategy["strategy_id"]),
                    None,
                ),
                "execution_ready_now": (candidate or {}).get("execution_ready_now"),
            },
            "expected_validation": {
                "linked_hypotheses": strategy.get("linked_hypotheses", []),
                "success_criteria": strategy.get("success_criteria", {}),
            },
            "measurement_plan": {
                "metric": "expectancy_and_win_rate_after_resolved",
                "min_sample_for_verdict": strategy.get("success_criteria", {}).get("min_sample", 8),
                "abort_criteria": "expectancy < -2.0 after min_sample OR 10 consecutive losses",
            },
        }

    result = await _execute_strategy_trade(
        strategy,
        best_signal,
        feature_ref,
        symbol_override or strategy.get("preferred_symbol"),
        timeframe_override or strategy.get("preferred_timeframe"),
        setup_variant_override or strategy.get("preferred_setup_variant"),
        decision_context=pre_decision_context,
        gate_audit=gate_audit,
    )
    trade = result.get("trade")
    if not result.get("success") or not trade:
        return {
            "success": False,
            "strategy_id": strategy["strategy_id"],
            "venue": strategy["venue"],
            "paper_only": True,
            "selected_lane": result.get("selected_lane"),
            "data_inputs": result.get("data_inputs", []),
            "symbols_universe": result.get("symbols_universe", []),
            "preferred_symbol": symbol_override or strategy.get("preferred_symbol"),
            "preferred_timeframe": timeframe_override or strategy.get("preferred_timeframe"),
            "preferred_setup_variant": setup_variant_override or strategy.get("preferred_setup_variant"),
            "signal": result.get("signal") or best_signal,
            "error": result.get("error", "paper_trade_failed"),
        }

    with ENGINE_LOCK:
        scorecard_update = update_strategy_scorecard(strategy, trade)
        # NOTE: Skipping second refresh_strategy_engine() here.
        # The first refresh (line 779) already loaded all data needed for
        # execution.  A full re-refresh after every single trade is wasteful
        # (each refresh rebuilds 8+ market snapshots, signals, features, ranking).
        # The ranking will be naturally updated on the next autonomy cycle.
        execution = {
            "success": True,
            "executed_utc": _utc_now(),
            "strategy_id": strategy["strategy_id"],
            "venue": strategy["venue"],
            "family": strategy["family"],
            "paper_only": True,
            "selected_lane": result.get("selected_lane"),
            "data_inputs": result.get("data_inputs", []),
            "symbols_universe": result.get("symbols_universe", []),
            "preferred_symbol": symbol_override or strategy.get("preferred_symbol"),
            "preferred_timeframe": trade.get("timeframe"),
            "preferred_setup_variant": trade.get("setup_variant"),
            "signal": result.get("signal"),
            "trade": trade,
            "strategy_scorecard": scorecard_update.get("aggregate"),
            "symbol_scorecard": scorecard_update.get("symbol"),
            "context_scorecard": scorecard_update.get("context"),
            "top_candidate_after_execution": refreshed["ranking"].get("top_strategy"),
            # Fase 3.4 / Fase 5.3: decision_context already built pre-execution and persisted in ledger
            "decision_context": pre_decision_context,
            # Fase 5.3: gate_audit record
            "gate_audit": gate_audit,
        }
        _append_report({
            "timestamp": _utc_now(),
            "event": "strategy_top_candidate_executed",
            "strategy_id": strategy["strategy_id"],
            "venue": strategy["venue"],
            "platform": execution["selected_lane"]["platform"] if execution.get("selected_lane") else None,
            "result": trade.get("result"),
            "profit": trade.get("profit"),
        })
        return execution


async def execute_candidate_batch(strategy_id: str, iterations: int = 3, allow_frozen: bool = False) -> Dict:
    refreshed = refresh_strategy_engine()
    ranked = refreshed["ranking"].get("ranked", [])
    candidate = next((item for item in ranked if item.get("strategy_id") == strategy_id), None)
    preferred_symbol = candidate.get("preferred_symbol") if candidate else None
    preferred_timeframe = candidate.get("preferred_timeframe") if candidate else None
    preferred_setup_variant = candidate.get("preferred_setup_variant") if candidate else None
    recommended_iterations = candidate.get("recommended_iterations") if candidate else None
    iterations = int(iterations or recommended_iterations or 1)
    if candidate and str(candidate.get("governance_lane") or "") == "probation":
        probation_budget = int(candidate.get("probation_budget") or 0)
        if probation_budget > 0:
            iterations = min(iterations, probation_budget)
    iterations = max(1, min(iterations, 10))
    run_id = _run_id()
    run_dir = RUNS_PATH / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    results = []
    successes = 0
    total_profit = 0.0
    for _ in range(iterations):
        execution = await execute_candidate(
            strategy_id,
            preferred_symbol,
            preferred_timeframe,
            preferred_setup_variant,
            allow_frozen=allow_frozen,
        )
        # P-OP31c: If the preferred symbol is in cooldown, retry once with
        # an alternative symbol from the same strategy universe.
        if (
            not execution.get("success")
            and str(execution.get("error") or "") == "trade_cooldown_active"
            and candidate
        ):
            universe = [str(sym) for sym in (candidate.get("universe") or []) if sym]
            for alt_symbol in universe:
                if alt_symbol == preferred_symbol:
                    continue
                retry_execution = await execute_candidate(
                    strategy_id,
                    alt_symbol,
                    preferred_timeframe,
                    preferred_setup_variant,
                    allow_frozen=allow_frozen,
                )
                retry_execution = dict(retry_execution or {})
                retry_execution["retry_from_cooldown"] = True
                retry_execution["retry_symbol"] = alt_symbol
                execution = retry_execution
                if execution.get("success") or str(execution.get("error") or "") != "trade_cooldown_active":
                    break
        results.append(execution)
        if execution.get("success"):
            successes += 1
            total_profit += float(execution.get("trade", {}).get("profit", 0.0) or 0.0)
    refreshed = refresh_strategy_engine()
    top_after = refreshed["ranking"].get("top_strategy")
    artifact = {
        "schema_version": "strategy_batch_run_v1",
        "run_id": run_id,
        "strategy_id": strategy_id,
        "requested_iterations": iterations,
        "preferred_symbol": preferred_symbol,
        "preferred_timeframe": preferred_timeframe,
        "preferred_setup_variant": preferred_setup_variant,
        "recommended_iterations": recommended_iterations,
        "completed_utc": _utc_now(),
        "paper_only": True,
        "successful_executions": successes,
        "failed_executions": iterations - successes,
        "total_profit": round(total_profit, 4),
        "results": results,
        "top_candidate_after_run": top_after,
    }
    artifact_path = run_dir / "result.json"
    write_json(artifact_path, artifact)
    _append_report({
        "timestamp": _utc_now(),
        "event": "strategy_batch_run_completed",
        "run_id": run_id,
        "strategy_id": strategy_id,
        "iterations": iterations,
        "successful_executions": successes,
        "total_profit": round(total_profit, 4),
    })
    return {
        "success": True,
        "run_id": run_id,
        "artifact": str(artifact_path),
        "paper_only": True,
        "strategy_id": strategy_id,
        "requested_iterations": iterations,
        "preferred_symbol": preferred_symbol,
        "preferred_timeframe": preferred_timeframe,
        "preferred_setup_variant": preferred_setup_variant,
        "recommended_iterations": recommended_iterations,
        "successful_executions": successes,
        "failed_executions": iterations - successes,
        "total_profit": round(total_profit, 4),
        "top_candidate_after_run": top_after,
    }


async def execute_comparison_cycle(max_candidates: int = 2, iterations_per_candidate: int | None = None) -> Dict:
    refreshed_before = refresh_strategy_engine()
    ranked_before = list(refreshed_before["ranking"].get("ranked", []))
    ranking_before = refreshed_before["ranking"]
    exploit_before = ranking_before.get("exploit_candidate") or ranking_before.get("top_strategy") or ranking_before.get("top_recovery_candidate") or {}
    explore_before = ranking_before.get("explore_candidate") or {}

    # --- P4-13: Use cross-venue diverse selector ---
    allow_frozen = True
    top_n = choose_top_n_candidates(
        ranked_before,
        n=max(1, min(int(max_candidates or 2), 5)),
        allow_frozen=allow_frozen,
    )

    # Enrich with comparison_role labels
    selected_candidates: List[Dict] = []
    for idx, candidate in enumerate(top_n):
        enriched = dict(candidate)
        if idx == 0:
            enriched["comparison_role"] = "exploit"
        elif idx == 1:
            enriched["comparison_role"] = "explore"
        else:
            enriched["comparison_role"] = "ranked_fill"
        selected_candidates.append(enriched)

    cycle_id = _run_id("strcmp")
    cycle_dir = COMPARISON_RUNS_PATH / cycle_id
    cycle_dir.mkdir(parents=True, exist_ok=True)

    # --- P4-13: Group by venue for parallel cross-venue dispatch ---
    venue_groups: Dict[str, List[Dict]] = {}
    for candidate in selected_candidates:
        venue = str(candidate.get("venue") or "unknown")
        venue_groups.setdefault(venue, []).append(candidate)

    async def _run_venue_group(candidates_in_venue: List[Dict]) -> List[Dict]:
        """Execute candidates in a single venue sequentially."""
        group_results = []
        for candidate in candidates_in_venue:
            requested_iterations = int(
                iterations_per_candidate
                or candidate.get("recommended_iterations")
                or 1
            )
            requested_iterations = max(1, min(requested_iterations, 3))
            batch_result = await execute_candidate_batch(candidate["strategy_id"], requested_iterations, allow_frozen=True)
            group_results.append({
                "strategy_id": candidate.get("strategy_id"),
                "comparison_role": candidate.get("comparison_role") or "ranked_fill",
                "venue": candidate.get("venue"),
                "family": candidate.get("family"),
                "preferred_symbol": candidate.get("preferred_symbol"),
                "preferred_timeframe": candidate.get("preferred_timeframe"),
                "preferred_setup_variant": candidate.get("preferred_setup_variant"),
                "priority_score_before": candidate.get("priority_score"),
                "expectancy_before": candidate.get("expectancy"),
                "context_expectancy_before": candidate.get("context_expectancy"),
                "sample_quality_before": candidate.get("sample_quality"),
                "requested_iterations": requested_iterations,
                "batch_result": batch_result,
            })
        return group_results

    # Fan out across venues with asyncio.gather, sequential within each venue
    venue_tasks = [_run_venue_group(group) for group in venue_groups.values()]
    venue_results = await asyncio.gather(*venue_tasks, return_exceptions=True)

    executed = []
    for result in venue_results:
        if isinstance(result, BaseException):
            # Log but don't crash the cycle — partial results are still valuable
            _append_report({
                "timestamp": _utc_now(),
                "event": "comparison_venue_group_error",
                "error": str(result),
            })
            continue
        executed.extend(result)

    refreshed_after = refresh_strategy_engine()
    ranked_after = list(refreshed_after["ranking"].get("ranked", []))
    ranking_after = refreshed_after["ranking"]
    comparison_rows = []
    for item in executed:
        strategy_id = item["strategy_id"]
        after = next((row for row in ranked_after if row.get("strategy_id") == strategy_id), {})
        comparison_rows.append({
            "strategy_id": strategy_id,
            "comparison_role": item.get("comparison_role") or "ranked_fill",
            "venue": item.get("venue"),
            "preferred_symbol": item.get("preferred_symbol"),
            "preferred_timeframe": item.get("preferred_timeframe"),
            "preferred_setup_variant": item.get("preferred_setup_variant"),
            "requested_iterations": item.get("requested_iterations"),
            "priority_score_before": item.get("priority_score_before"),
            "priority_score_after": after.get("priority_score"),
            "expectancy_before": item.get("expectancy_before"),
            "expectancy_after": after.get("expectancy"),
            "context_expectancy_before": item.get("context_expectancy_before"),
            "context_expectancy_after": after.get("context_expectancy"),
            "sample_quality_before": item.get("sample_quality_before"),
            "sample_quality_after": after.get("sample_quality"),
            "batch_run": item.get("batch_result", {}),
        })

    total_profit = round(sum(float(row.get("batch_run", {}).get("total_profit", 0.0) or 0.0) for row in comparison_rows), 4)
    successful_runs = sum(1 for row in comparison_rows if row.get("batch_run", {}).get("success"))
    artifact = {
        "schema_version": "strategy_comparison_cycle_v1",
        "cycle_id": cycle_id,
        "completed_utc": _utc_now(),
        "paper_only": True,
        "requested_max_candidates": max_candidates,
        "selected_candidates": len(selected_candidates),
        "iterations_per_candidate_override": iterations_per_candidate,
        "top_strategy_before": refreshed_before["ranking"].get("top_strategy"),
        "top_recovery_candidate_before": refreshed_before["ranking"].get("top_recovery_candidate"),
        "exploit_candidate_before": exploit_before,
        "explore_candidate_before": explore_before,
        "top_strategy_after": refreshed_after["ranking"].get("top_strategy"),
        "top_recovery_candidate_after": ranking_after.get("top_recovery_candidate"),
        "exploit_candidate_after": ranking_after.get("exploit_candidate"),
        "explore_candidate_after": ranking_after.get("explore_candidate"),
        "comparison_rows": comparison_rows,
        "successful_runs": successful_runs,
        "failed_runs": len(comparison_rows) - successful_runs,
        "total_profit": total_profit,
        "ranked_before": ranked_before[:5],
        "ranked_after": ranked_after[:5],
    }
    artifact_path = cycle_dir / "result.json"
    write_json(artifact_path, artifact)
    _append_report({
        "timestamp": _utc_now(),
        "event": "strategy_comparison_cycle_completed",
        "cycle_id": cycle_id,
        "selected_candidates": len(selected_candidates),
        "successful_runs": successful_runs,
        "total_profit": total_profit,
        "top_strategy_before": (artifact.get("top_strategy_before") or {}).get("strategy_id"),
        "top_strategy_after": (artifact.get("top_strategy_after") or {}).get("strategy_id"),
        "exploit_candidate_before": (artifact.get("exploit_candidate_before") or {}).get("strategy_id"),
        "explore_candidate_before": (artifact.get("explore_candidate_before") or {}).get("strategy_id"),
        "exploit_candidate_after": (artifact.get("exploit_candidate_after") or {}).get("strategy_id"),
        "explore_candidate_after": (artifact.get("explore_candidate_after") or {}).get("strategy_id"),
    })
    return {
        "success": True,
        "cycle_id": cycle_id,
        "artifact": str(artifact_path),
        "paper_only": True,
        "selected_candidates": len(selected_candidates),
        "successful_runs": successful_runs,
        "failed_runs": len(comparison_rows) - successful_runs,
        "total_profit": total_profit,
        "top_strategy_before": artifact.get("top_strategy_before"),
        "top_strategy_after": artifact.get("top_strategy_after"),
        "comparison_rows": comparison_rows,
    }


def read_candidates() -> Dict:
    return read_json(CANDIDATES_PATH, {"schema_version": "strategy_candidates_latest_v1", "candidates": []})


def read_ranking() -> Dict:
    return read_json(RANKING_PATH, {"schema_version": "strategy_ranking_latest_v2", "ranked": []})


def read_ranking_v2() -> Dict:
    return read_json(RANKING_V2_PATH, {"schema_version": "strategy_ranking_latest_v2", "ranked": []})


def read_feature_snapshot() -> Dict:
    return read_json(FEATURE_SNAPSHOT_PATH, {"schema_version": "market_feature_snapshot_v1", "items": []})


def read_market_history_state() -> Dict:
    return read_json(MARKET_HISTORY_PATH, {"schema_version": "market_history_snapshot_v1", "symbols": {}, "summary": {}})


def read_signal_snapshot() -> Dict:
    return read_json(SIGNAL_SNAPSHOT_PATH, {"schema_version": "strategy_signal_snapshot_v1", "items": [], "by_strategy": []})


def read_strategy_archive_state() -> Dict:
    return read_strategy_archive()


def read_edge_validation_state() -> Dict:
    return read_edge_validation_snapshot()


def read_context_edge_validation_state() -> Dict:
    return read_context_edge_validation_snapshot()


def read_active_strategy_catalog_state() -> Dict:
    return read_active_strategy_catalog_snapshot()


def read_pipeline_integrity_state() -> Dict:
    return read_pipeline_integrity_snapshot()


def get_top_strategy_candidate() -> Dict | None:
    refresh_strategy_engine()
    ranking = read_ranking()
    return ranking.get("top_strategy") or ranking.get("top_recovery_candidate")


def get_recovery_strategy_candidate() -> Dict | None:
    refresh_strategy_engine()
    ranking = read_ranking()
    return ranking.get("top_recovery_candidate")
