"""
Brain V9 — trading/ibkr_signal_engine.py
IBKR Signal Engine: Evaluates strategy conditions against live market data
and dispatches paper orders.

Closes Gap: "Nothing calls place_paper_order()" — this module bridges
strategy entry/exit conditions → IBKR order execution.

The engine:
1. Reads live market data from ibkr_data_ingester snapshots
2. Evaluates entry/exit conditions for all live_paper strategies
3. Generates trade signals when conditions are met
4. Dispatches signals to ibkr_order_executor.place_paper_order()
5. Manages position tracking to avoid duplicate entries

Usage:
    # One-shot scan
    result = await scan_and_execute()

    # Background loop
    engine = IBKRSignalEngine(interval=120)
    await engine.start()
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain_v9.config import BASE_PATH, PAPER_ONLY
from brain_v9.core.state_io import read_json, write_json

log = logging.getLogger("IBKRSignalEngine")

# ── Paths ─────────────────────────────────────────────────────────────────────
_STATE_DIR = BASE_PATH / "tmp_agent" / "state" / "ibkr_signals"
_STATE_DIR.mkdir(parents=True, exist_ok=True)
_SIGNAL_LOG_PATH = _STATE_DIR / "signal_log.json"
_ENGINE_STATE_PATH = _STATE_DIR / "engine_state.json"
_SCORECARD_PATH = BASE_PATH / "tmp_agent" / "state" / "strategy_engine" / "strategy_scorecards.json"
_MARKET_DATA_DIR = BASE_PATH / "tmp_agent" / "state" / "ibkr_market_data"
_POSITION_PATH = BASE_PATH / "tmp_agent" / "state" / "trading_execution_checks" / "ibkr_paper_positions_latest.json"
_ORDER_AUDIT_PATH = BASE_PATH / "tmp_agent" / "state" / "trading_execution_checks" / "ibkr_paper_orders.json"

# ── Signal cooldown (don't re-signal same strategy within N seconds) ─────────
SIGNAL_COOLDOWN_SECONDS = 3600  # 1 hour between signals per strategy
MAX_SIGNALS_PER_SCAN = 3  # Don't flood with too many orders at once


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_signal_log() -> Dict:
    if _SIGNAL_LOG_PATH.exists():
        return read_json(_SIGNAL_LOG_PATH)
    return {"signals": [], "updated_utc": _now_utc()}


def _save_signal_log(data: Dict):
    data["updated_utc"] = _now_utc()
    # Keep last 500 signals
    if len(data.get("signals", [])) > 500:
        data["signals"] = data["signals"][-500:]
    write_json(_SIGNAL_LOG_PATH, data)


def _load_engine_state() -> Dict:
    if _ENGINE_STATE_PATH.exists():
        return read_json(_ENGINE_STATE_PATH)
    return {"last_scan_utc": None, "last_signal_utc": {}, "total_signals": 0}


def _save_engine_state(data: Dict):
    write_json(_ENGINE_STATE_PATH, data)


# ═══════════════════════════════════════════════════════════════════════════════
# Market Data Access
# ═══════════════════════════════════════════════════════════════════════════════

def _get_latest_market_data(symbol: str = "SPY") -> Optional[Dict]:
    """Read the latest IBKR market data snapshot for a symbol."""
    # Try the ingester's latest snapshot
    snapshot_path = _MARKET_DATA_DIR / f"{symbol.lower()}_latest.json"
    if snapshot_path.exists():
        data = read_json(snapshot_path)
        return data

    # Try the generic market data path
    generic_path = _MARKET_DATA_DIR / "latest_snapshot.json"
    if generic_path.exists():
        data = read_json(generic_path)
        for entry in data.get("snapshots", []):
            if entry.get("symbol", "").upper() == symbol.upper():
                return entry

    # Try to read from ibkr_data_ingester state
    ingester_path = BASE_PATH / "tmp_agent" / "state" / "ibkr_market_data" / "ingester_state.json"
    if ingester_path.exists():
        data = read_json(ingester_path)
        snapshots = data.get("last_snapshots", {})
        if symbol.upper() in snapshots:
            return snapshots[symbol.upper()]

    return None


def _calculate_simple_indicators(price_history: List[float]) -> Dict:
    """Calculate basic technical indicators from price history."""
    if not price_history or len(price_history) < 2:
        return {}

    indicators = {}
    n = len(price_history)

    # SMA
    if n >= 20:
        indicators["sma_20"] = sum(price_history[-20:]) / 20
    if n >= 50:
        indicators["sma_50"] = sum(price_history[-50:]) / 50
    if n >= 200:
        indicators["sma_200"] = sum(price_history[-200:]) / 200

    # Simple RSI (14-period)
    if n >= 15:
        gains, losses = [], []
        for i in range(-14, 0):
            diff = price_history[i] - price_history[i - 1]
            if diff > 0:
                gains.append(diff)
            else:
                losses.append(abs(diff))
        avg_gain = sum(gains) / 14 if gains else 0.001
        avg_loss = sum(losses) / 14 if losses else 0.001
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        indicators["rsi_14"] = 100 - (100 / (1 + rs))

    # Bollinger Bands (20-period)
    if n >= 20:
        prices_20 = price_history[-20:]
        mean = sum(prices_20) / 20
        variance = sum((p - mean) ** 2 for p in prices_20) / 20
        std = math.sqrt(variance) if variance > 0 else 0
        indicators["bb_upper"] = mean + 2 * std
        indicators["bb_lower"] = mean - 2 * std
        indicators["bb_middle"] = mean
        indicators["bb_width"] = (indicators["bb_upper"] - indicators["bb_lower"]) / mean if mean > 0 else 0

    # Current price
    indicators["current_price"] = price_history[-1]

    return indicators


# ═══════════════════════════════════════════════════════════════════════════════
# Strategy Condition Evaluator
# ═══════════════════════════════════════════════════════════════════════════════

def evaluate_entry_conditions(
    strategy_spec: Dict, market_data: Dict, indicators: Dict
) -> Dict[str, Any]:
    """
    Evaluate whether a strategy's entry conditions are met.

    Returns dict with 'signal': True/False, 'conditions_met': list,
    'conditions_failed': list.
    """
    entry_conditions = strategy_spec.get("entry_conditions", {})
    if not entry_conditions:
        return {"signal": False, "reason": "no entry conditions defined"}

    conditions_met = []
    conditions_failed = []
    conditions_unknown = []

    price = indicators.get("current_price") or market_data.get("last", 0) or market_data.get("close", 0)
    if not price:
        return {"signal": False, "reason": "no price data available"}

    # Trend filter: SMA50 > SMA200
    if "trend_filter" in entry_conditions or "sma_crossover" in entry_conditions:
        sma50 = indicators.get("sma_50")
        sma200 = indicators.get("sma_200")
        if sma50 is not None and sma200 is not None:
            if sma50 > sma200:
                conditions_met.append(f"trend_bullish: SMA50={sma50:.2f} > SMA200={sma200:.2f}")
            else:
                conditions_failed.append(f"trend_bearish: SMA50={sma50:.2f} <= SMA200={sma200:.2f}")
        else:
            conditions_unknown.append("sma_crossover: insufficient history")

    # RSI filter
    if "rsi_filter" in entry_conditions:
        rsi = indicators.get("rsi_14")
        rsi_min = entry_conditions["rsi_filter"].get("min", 40)
        rsi_max = entry_conditions["rsi_filter"].get("max", 70)
        if rsi is not None:
            if rsi_min <= rsi <= rsi_max:
                conditions_met.append(f"rsi_ok: RSI={rsi:.1f} in [{rsi_min},{rsi_max}]")
            else:
                conditions_failed.append(f"rsi_out_of_range: RSI={rsi:.1f} not in [{rsi_min},{rsi_max}]")
        else:
            conditions_unknown.append("rsi: insufficient history")

    # Bollinger Band width
    if "bb_width" in entry_conditions:
        bb_width = indicators.get("bb_width")
        min_width = entry_conditions["bb_width"].get("min", 0.02)
        if bb_width is not None:
            if bb_width >= min_width:
                conditions_met.append(f"bb_width_ok: {bb_width:.4f} >= {min_width}")
            else:
                conditions_failed.append(f"bb_width_low: {bb_width:.4f} < {min_width}")
        else:
            conditions_unknown.append("bb_width: insufficient history")

    # Price above SMA
    if "price_above_sma" in entry_conditions:
        sma_period = entry_conditions["price_above_sma"].get("period", 50)
        sma_key = f"sma_{sma_period}"
        sma_val = indicators.get(sma_key)
        if sma_val is not None:
            if price > sma_val:
                conditions_met.append(f"price_above_sma{sma_period}: {price:.2f} > {sma_val:.2f}")
            else:
                conditions_failed.append(f"price_below_sma{sma_period}: {price:.2f} <= {sma_val:.2f}")
        else:
            conditions_unknown.append(f"sma_{sma_period}: insufficient history")

    # Generic: all evaluable conditions must pass
    total_evaluable = len(conditions_met) + len(conditions_failed)
    if total_evaluable == 0:
        return {
            "signal": False,
            "reason": "no evaluable conditions (need more market data history)",
            "conditions_unknown": conditions_unknown,
        }

    signal = len(conditions_failed) == 0 and len(conditions_met) > 0

    return {
        "signal": signal,
        "conditions_met": conditions_met,
        "conditions_failed": conditions_failed,
        "conditions_unknown": conditions_unknown,
        "evaluable_ratio": f"{total_evaluable}/{total_evaluable + len(conditions_unknown)}",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Signal Generation & Dispatch
# ═══════════════════════════════════════════════════════════════════════════════

def _has_existing_position(strategy_id: str) -> bool:
    """Check if strategy already has an open position."""
    audit = read_json(_ORDER_AUDIT_PATH) if _ORDER_AUDIT_PATH.exists() else {}
    orders = audit.get("orders", [])
    # Check for recent open orders for this strategy
    for o in reversed(orders):
        if o.get("strategy_id") == strategy_id:
            status = o.get("status", "").lower()
            if status in ("filled", "submitted", "presubmitted"):
                return True
    return False


def _is_in_cooldown(strategy_id: str, engine_state: Dict) -> bool:
    """Check if strategy is in signal cooldown."""
    last_signal = engine_state.get("last_signal_utc", {}).get(strategy_id)
    if not last_signal:
        return False
    try:
        last_dt = datetime.fromisoformat(last_signal.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        elapsed = (now - last_dt).total_seconds()
        return elapsed < SIGNAL_COOLDOWN_SECONDS
    except (ValueError, TypeError):
        return False


async def scan_and_execute() -> Dict[str, Any]:
    """
    Main scan loop:
    1. Find all live_paper strategies
    2. Get market data
    3. Evaluate conditions
    4. Generate signals
    5. Dispatch orders

    Returns summary of scan results.
    """
    assert PAPER_ONLY, "PAPER_ONLY must be True"

    result = {
        "success": False,
        "timestamp": _now_utc(),
        "strategies_scanned": 0,
        "signals_generated": 0,
        "orders_dispatched": 0,
        "signals": [],
        "errors": [],
    }

    # ── 1. Load live_paper strategies ─────────────────────────────────────
    if not _SCORECARD_PATH.exists():
        result["success"] = True
        result["message"] = "No scorecards found"
        return result

    sc_data = read_json(_SCORECARD_PATH)
    scorecards = sc_data.get("scorecards", {})
    live_paper = {
        sid: card for sid, card in scorecards.items()
        if card.get("governance_state") == "live_paper"
    }

    if not live_paper:
        result["success"] = True
        result["message"] = "No strategies in live_paper state"
        result["total_strategies"] = len(scorecards)
        return result

    result["strategies_scanned"] = len(live_paper)

    # ── 2. Load strategy specs ────────────────────────────────────────────
    from brain_v9.trading.qc_strategy_bridge import BRAIN_OPTIONS_V1_STRATEGIES

    engine_state = _load_engine_state()
    signal_log = _load_signal_log()
    signals_this_scan = 0

    for sid, card in live_paper.items():
        if signals_this_scan >= MAX_SIGNALS_PER_SCAN:
            break

        spec = BRAIN_OPTIONS_V1_STRATEGIES.get(sid, {})
        if not spec:
            result["errors"].append(f"{sid}: no strategy spec found")
            continue

        # Check cooldown
        if _is_in_cooldown(sid, engine_state):
            continue

        # Check if already has position
        if _has_existing_position(sid):
            continue

        # ── 3. Get market data ────────────────────────────────────────────
        underlying = spec.get("underlying", "SPY")
        market_data = _get_latest_market_data(underlying)

        if not market_data:
            result["errors"].append(f"{sid}: no market data for {underlying}")
            continue

        # Build price history from snapshots if available
        price = market_data.get("last") or market_data.get("close") or market_data.get("price", 0)
        if not price:
            result["errors"].append(f"{sid}: no price in market data for {underlying}")
            continue

        # Get indicator data (from stored history or calculate)
        indicators = market_data.get("indicators", {})
        if not indicators:
            # Try to calculate from stored price history
            price_history = market_data.get("price_history", [])
            if price_history:
                indicators = _calculate_simple_indicators(price_history)
            else:
                indicators = {"current_price": price}

        # ── 4. Evaluate entry conditions ──────────────────────────────────
        eval_result = evaluate_entry_conditions(spec, market_data, indicators)

        signal_record = {
            "strategy_id": sid,
            "timestamp": _now_utc(),
            "underlying": underlying,
            "price": price,
            "signal": eval_result.get("signal", False),
            "conditions_met": eval_result.get("conditions_met", []),
            "conditions_failed": eval_result.get("conditions_failed", []),
            "conditions_unknown": eval_result.get("conditions_unknown", []),
        }

        if not eval_result.get("signal"):
            signal_record["action"] = "no_signal"
            signal_log["signals"].append(signal_record)
            continue

        # ── 5. Generate order parameters ──────────────────────────────────
        order_params = _generate_order_params(spec, price, indicators)
        if not order_params:
            signal_record["action"] = "signal_but_no_order_params"
            signal_log["signals"].append(signal_record)
            continue

        signal_record["action"] = "dispatched"
        signal_record["order_params"] = order_params

        # ── 6. Dispatch to IBKR ──────────────────────────────────────────
        try:
            from brain_v9.trading.ibkr_order_executor import place_paper_order
            order_result = place_paper_order(**order_params)
            signal_record["order_result"] = {
                "success": order_result.get("success"),
                "order_id": order_result.get("order_id"),
                "status": order_result.get("status"),
                "error": order_result.get("error"),
            }
            if order_result.get("success"):
                result["orders_dispatched"] += 1
                engine_state.setdefault("last_signal_utc", {})[sid] = _now_utc()
        except Exception as e:
            signal_record["order_result"] = {"success": False, "error": str(e)}
            result["errors"].append(f"{sid}: order dispatch failed: {e}")

        signal_log["signals"].append(signal_record)
        result["signals"].append(signal_record)
        signals_this_scan += 1

    result["signals_generated"] = signals_this_scan
    result["success"] = True

    # Save state
    engine_state["last_scan_utc"] = _now_utc()
    engine_state["total_signals"] = engine_state.get("total_signals", 0) + signals_this_scan
    _save_engine_state(engine_state)
    _save_signal_log(signal_log)

    log.info(
        "Signal scan: %d strategies, %d signals, %d orders dispatched",
        len(live_paper), signals_this_scan, result["orders_dispatched"],
    )

    return result


def _generate_order_params(spec: Dict, price: float, indicators: Dict) -> Optional[Dict]:
    """Generate order parameters from strategy spec and current market conditions."""
    strategy_type = spec.get("strategy_type", "").lower()
    underlying = spec.get("underlying", "SPY")
    position_sizing = spec.get("position_sizing", {})

    # Determine max capital for this trade
    max_capital = position_sizing.get("max_capital_per_trade", 2000)
    max_contracts = position_sizing.get("max_contracts", 5)

    if "covered_call" in strategy_type or "put_spread" in strategy_type or "option" in strategy_type:
        # Options order
        return {
            "symbol": underlying,
            "action": "BUY",
            "quantity": min(1, max_contracts),  # Start conservative: 1 contract
            "order_type": "MKT",
            "sec_type": "OPT",
            "strategy_id": spec.get("id", ""),
            "reason": f"Signal engine: {strategy_type} entry conditions met",
        }
        # Note: expiry, strike, right would need to be determined by
        # options chain analysis — for MVP, we use stock orders

    # Default: stock order
    shares = int(max_capital / price) if price > 0 else 0
    if shares <= 0:
        return None

    return {
        "symbol": underlying,
        "action": "BUY",
        "quantity": min(shares, 100),  # Cap at 100 shares
        "order_type": "MKT",
        "sec_type": "STK",
        "strategy_id": spec.get("id", ""),
        "reason": f"Signal engine: {strategy_type} entry conditions met at ${price:.2f}",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Background Engine Class
# ═══════════════════════════════════════════════════════════════════════════════

class IBKRSignalEngine:
    """Background task that scans strategies and dispatches signals."""

    def __init__(self, interval: int = 120):
        self.interval = interval
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        if self._running:
            log.warning("IBKRSignalEngine already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        log.info("IBKRSignalEngine started (interval=%ds)", self.interval)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        log.info("IBKRSignalEngine stopped")

    async def _loop(self):
        while self._running:
            try:
                result = await scan_and_execute()
                if not result.get("success"):
                    log.warning("Signal scan failed: %s", result.get("errors"))
            except Exception as e:
                log.error("Signal engine error: %s", e)
            await asyncio.sleep(self.interval)

    def status(self) -> Dict:
        state = _load_engine_state()
        return {
            "running": self._running,
            "interval_seconds": self.interval,
            "last_scan_utc": state.get("last_scan_utc"),
            "total_signals": state.get("total_signals", 0),
        }


def get_signal_log(limit: int = 50) -> Dict:
    """Read recent signal log entries."""
    log_data = _load_signal_log()
    signals = log_data.get("signals", [])
    return {
        "total": len(signals),
        "showing": min(limit, len(signals)),
        "signals": signals[-limit:] if signals else [],
    }
