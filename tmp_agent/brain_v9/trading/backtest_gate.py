"""
Brain V9 — Fase 6: Backtest Gate (Simulation-based probation filter)

Runs a lightweight offline simulation of a strategy against historical
normalized feed ticks before allowing it to enter paper probation.

The gate replays price ticks from the PO browser bridge normalized feed,
converts them to synthetic feature dicts, evaluates signals using the
same signal_engine logic as live, and simulates deferred resolution
(each signal resolved against the next tick).

Pass/fail criteria:
- min_simulated_trades: at least N signals fired (default 3)
- min_win_rate: win rate above threshold (default 0.35)
- min_expectancy: positive or near-zero expectancy (default -0.5)

If a strategy fails the gate, it is tagged sim_rejected and excluded
from probation until the hypothesis or parameters change.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import brain_v9.config as _cfg
from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json

log = logging.getLogger("BacktestGate")

# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_MIN_SIMULATED_TRADES = 3
DEFAULT_MIN_WIN_RATE = 0.35
DEFAULT_MIN_EXPECTANCY = -0.5
DEFAULT_PAYOUT_PCT = 82.0
DEFAULT_TRADE_AMOUNT = float(getattr(_cfg, "PAPER_TRADE_DEFAULT_AMOUNT", 10.0))

# Path to normalized feed — only PO feed available currently
PO_FEED_PATH = (
    BASE_PATH / "tmp_agent" / "state" / "rooms"
    / "brain_binary_paper_pb04_demo_execution"
    / "browser_bridge_normalized_feed.json"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ═══════════════════════════════════════════════════════════════════════════════
# Feed reader — extract price ticks from normalized feed
# ═══════════════════════════════════════════════════════════════════════════════

def _load_feed_ticks(feed_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load and sort price ticks from the PO normalized feed.

    Returns a list of dicts with: price, payout_pct, symbol, captured_utc,
    and basic indicator flags, sorted chronologically.
    """
    path = feed_path or PO_FEED_PATH
    feed = read_json(path, {})
    rows = feed.get("rows", [])
    if not rows or not isinstance(rows, list):
        return []

    # Sort by source_timestamp (ascending = chronological)
    valid = [r for r in rows if isinstance(r, dict) and r.get("price")]
    valid.sort(key=lambda r: float(r.get("source_timestamp", 0)))
    return valid


def _tick_to_feature(tick: Dict[str, Any], prev_tick: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Convert a raw feed tick into a synthetic feature dict.

    Produces the same fields that signal_engine._evaluate_strategy_feature()
    needs to evaluate a strategy.
    """
    price = float(tick.get("price", 0))
    payout = float(tick.get("payout_pct", DEFAULT_PAYOUT_PCT))
    symbol = tick.get("symbol", "EURUSD_otc")

    # Compute basic price context from previous tick
    prev_price = float(prev_tick["price"]) if prev_tick and prev_tick.get("price") else price
    price_change_pct = ((price - prev_price) / prev_price * 100.0) if prev_price else 0.0

    indicator_candidates = tick.get("indicator_candidates", [])
    if not isinstance(indicator_candidates, list):
        indicator_candidates = []

    return {
        "key": f"sim::pocket_option::{symbol}::5m",
        "captured_utc": tick.get("captured_utc"),
        "data_age_seconds": 0,
        "is_stale": False,
        "venue": "pocket_option",
        "symbol": symbol,
        "timeframe": "5m",
        "asset_class": "otc_binary",
        "price_available": True,
        "last": price,
        "bid": None,
        "ask": None,
        "close": prev_price,
        "mid": price,
        "spread_pct": 0.0,
        "spread_bps": 0.0,
        "bid_ask_imbalance": 0.0,
        "last_vs_close_pct": round(price_change_pct, 4),
        "volatility_proxy_pct": round(abs(price_change_pct), 4),
        "window_range_pct": round(abs(price_change_pct), 4),
        "price_zscore": 0.0,
        "recent_micro_move_pct": round(price_change_pct, 4),
        "price_rows_count": 10,
        "liquidity_score": round(min(max(payout / 100.0, 0.0), 1.0), 4),
        "market_regime": "range",
        "payout_pct": payout,
        "expiry_seconds": 300,
        "is_current_duration": True,
        "available_timeframes": ["5m"],
        "duration_candidates": [],
        "indicator_candidates": indicator_candidates,
        "indicator_readouts": [],
        "indicator_count": len(indicator_candidates),
        "indicator_readout_count": 0,
        "indicator_access_ready": len(indicator_candidates) > 0,
        "visible_symbol": symbol,
        "last_stream_symbol": symbol,
        "stream_symbol_match": True,
        "source_artifact": "simulation",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Simulation engine
# ═══════════════════════════════════════════════════════════════════════════════

def simulate_strategy(
    strategy: Dict[str, Any],
    feed_path: Optional[Path] = None,
    min_simulated_trades: int = DEFAULT_MIN_SIMULATED_TRADES,
    min_win_rate: float = DEFAULT_MIN_WIN_RATE,
    min_expectancy: float = DEFAULT_MIN_EXPECTANCY,
) -> Dict[str, Any]:
    """Run offline simulation of a strategy against historical ticks.

    Returns a result dict with:
    - passed: bool — whether the strategy passed the gate
    - simulated_trades: int — number of signals that fired
    - wins / losses: int
    - win_rate: float
    - expectancy: float
    - reason: str — why it passed or failed
    - signals: list of signal summaries (for debugging)
    """
    from brain_v9.trading.signal_engine import _evaluate_strategy_feature

    ticks = _load_feed_ticks(feed_path)
    if not ticks:
        return {
            "passed": False,
            "reason": "no_feed_data_available",
            "simulated_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "expectancy": 0.0,
            "signals": [],
            "ticks_available": 0,
        }

    # Build synthetic features from ticks
    features = []
    for i, tick in enumerate(ticks):
        prev = ticks[i - 1] if i > 0 else None
        features.append(_tick_to_feature(tick, prev))

    # Evaluate signals on each feature
    trades: List[Dict[str, Any]] = []
    for i, feature in enumerate(features[:-1]):  # Skip last — need next tick for resolution
        signal = _evaluate_strategy_feature(strategy, feature)

        if not signal.get("execution_ready"):
            continue

        # Resolve against next tick (deferred forward resolution)
        next_feature = features[i + 1]
        entry_price = float(signal.get("entry_price", 0))
        exit_price = float(next_feature.get("last", 0))
        direction = signal.get("direction")

        if not entry_price or not exit_price or not direction:
            continue

        if direction == "call":
            won = exit_price > entry_price
        elif direction == "put":
            won = exit_price < entry_price
        else:
            continue

        payout_factor = min(max(float(feature.get("payout_pct", 80)) / 100.0, 0.5), 0.95)
        confidence = min(max(float(signal.get("confidence", 0.5)), 0.0), 1.0)

        if won:
            profit = round(DEFAULT_TRADE_AMOUNT * max(payout_factor, 0.8) * max(confidence, 0.6), 4)
        else:
            profit = round(-DEFAULT_TRADE_AMOUNT, 4)

        trades.append({
            "tick_index": i,
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "won": won,
            "profit": profit,
            "confidence": signal.get("confidence"),
            "signal_score": signal.get("signal_score"),
            "blockers": signal.get("blockers", []),
        })

    # Compute metrics
    total_trades = len(trades)
    wins = sum(1 for t in trades if t["won"])
    losses = total_trades - wins
    win_rate = (wins / total_trades) if total_trades > 0 else 0.0
    total_profit = sum(t["profit"] for t in trades)
    expectancy = (total_profit / total_trades) if total_trades > 0 else 0.0

    # Gate decision
    reasons = []
    passed = True

    if total_trades < min_simulated_trades:
        passed = False
        reasons.append(f"insufficient_signals ({total_trades} < {min_simulated_trades})")

    if total_trades >= min_simulated_trades and win_rate < min_win_rate:
        passed = False
        reasons.append(f"win_rate_too_low ({win_rate:.2%} < {min_win_rate:.0%})")

    if total_trades >= min_simulated_trades and expectancy < min_expectancy:
        passed = False
        reasons.append(f"expectancy_too_low ({expectancy:.2f} < {min_expectancy})")

    if passed and total_trades >= min_simulated_trades:
        reasons.append("simulation_passed")

    return {
        "passed": passed,
        "reason": " | ".join(reasons) if reasons else "no_evaluation",
        "simulated_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 4),
        "expectancy": round(expectancy, 4),
        "total_profit": round(total_profit, 4),
        "ticks_available": len(ticks),
        "signals": trades[:20],  # Cap for readability
        "gate_criteria": {
            "min_simulated_trades": min_simulated_trades,
            "min_win_rate": min_win_rate,
            "min_expectancy": min_expectancy,
        },
        "simulated_utc": _utc_now(),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Research-to-probation gate (6.2)
# ═══════════════════════════════════════════════════════════════════════════════

def research_to_probation_gate(
    strategy: Dict[str, Any],
    feed_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Full research-to-probation gate check.

    A strategy must pass ALL of:
    1. Simulation gate (if feed data available for its venue)
    2. Venue constraints (strategy must have a valid venue)
    3. Explicit hypothesis (strategy should have linked_hypotheses or a clear objective)
    4. Budget check (probation budget must be > 0)

    Returns a dict with overall pass/fail and individual check results.
    """
    checks = {}

    # Check 1: Venue constraints
    venue = strategy.get("venue", "")
    valid_venues = {"pocket_option", "ibkr"}
    venue_ok = venue in valid_venues
    checks["venue_valid"] = {
        "passed": venue_ok,
        "venue": venue,
        "reason": "valid" if venue_ok else f"unknown_venue ({venue})",
    }

    # Check 2: Explicit hypothesis
    hypotheses = strategy.get("linked_hypotheses", [])
    objective = strategy.get("objective", "")
    has_hypothesis = bool(hypotheses) or bool(objective)
    checks["hypothesis_present"] = {
        "passed": has_hypothesis,
        "linked_hypotheses": hypotheses,
        "has_objective": bool(objective),
        "reason": "hypothesis_present" if has_hypothesis else "no_hypothesis_or_objective",
    }

    # Check 3: Budget
    probation_budget = int(strategy.get("probation_budget", 0))
    # Default budget if not set: use success_criteria min_sample
    if probation_budget <= 0:
        sc = strategy.get("success_criteria", {})
        probation_budget = int(sc.get("min_sample", 5))
    budget_ok = probation_budget > 0
    checks["budget_available"] = {
        "passed": budget_ok,
        "probation_budget": probation_budget,
        "reason": "budget_available" if budget_ok else "no_budget",
    }

    # Check 4: Simulation (only for venues with feed data)
    sim_result: Optional[Dict[str, Any]] = None
    if venue == "pocket_option":
        sim_result = simulate_strategy(strategy, feed_path)
        checks["simulation"] = {
            "passed": sim_result["passed"],
            "simulated_trades": sim_result["simulated_trades"],
            "win_rate": sim_result["win_rate"],
            "expectancy": sim_result["expectancy"],
            "reason": sim_result["reason"],
        }
    elif venue == "ibkr":
        # No IBKR feed data for simulation — pass with advisory
        checks["simulation"] = {
            "passed": True,
            "simulated_trades": 0,
            "reason": "ibkr_no_feed_data_simulation_skipped",
        }
    else:
        checks["simulation"] = {
            "passed": False,
            "simulated_trades": 0,
            "reason": f"no_simulation_support_for_{venue}",
        }

    # Overall gate
    all_passed = all(c["passed"] for c in checks.values())

    return {
        "strategy_id": strategy.get("strategy_id"),
        "passed": all_passed,
        "checks": checks,
        "gate_utc": _utc_now(),
        "simulation_detail": sim_result,
    }
