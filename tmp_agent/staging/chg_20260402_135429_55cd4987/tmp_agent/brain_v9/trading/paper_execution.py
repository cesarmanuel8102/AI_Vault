"""
Brain V9 - Paper execution from signal
Deferred resolution: ALL trades are recorded as pending and resolved
on the next strategy engine cycle when new price data arrives.
This ensures signal direction correlates with actual forward price movement.
"""
from __future__ import annotations

import json as _json
import logging
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import brain_v9.config as _cfg
from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import read_json, write_json
from brain_v9.trading.adaptive_duration_policy import build_trade_decision_with_duration, AdaptiveDurationConfig

log = logging.getLogger("PaperExecution")

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
ENGINE_PATH = STATE_PATH / "strategy_engine"
ENGINE_PATH.mkdir(parents=True, exist_ok=True)

PAPER_EXECUTION_LEDGER_PATH = ENGINE_PATH / "signal_paper_execution_ledger.json"
PAPER_EXECUTION_CURSOR_PATH = ENGINE_PATH / "signal_paper_execution_cursor.json"
_PO_CANDLE_BUFFER_PATH = ENGINE_PATH / "po_candle_buffer.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def _get_candle_buffer_last_price(symbol: str = "EURUSD_otc") -> Optional[float]:
    """Read the most recent close price from the PO candle buffer.

    Used as fallback when the feature snapshot is stale at binary expiry time.
    Returns None if buffer is unavailable or empty.
    """
    try:
        data = read_json(_PO_CANDLE_BUFFER_PATH, {})
        candles = data.get("candles", [])
        if not candles:
            return None
        # Buffer symbol check (if stored)
        buf_symbol = data.get("symbol", "")
        if buf_symbol and buf_symbol.lower().replace("/", "").replace("_", "") != symbol.lower().replace("/", "").replace("_", ""):
            return None
        # Get the latest candle by timestamp
        latest = max(candles, key=lambda c: c.get("t", 0))
        close = latest.get("c")
        if close and float(close) > 0:
            return float(close)
        return None
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# IBKR: LEGACY history-based resolution (DEPRECATED — kept for ledger compat)
# ═══════════════════════════════════════════════════════════════════════════════
# The old tiingo_daily_replay resolved trades against uncorrelated historical
# data (Dec 2025 candles) while signals were generated from live March 2026
# data. This produced random outcomes with zero correlation to signal quality.
# All venues now use deferred_forward_v1: entry price from live data, resolved
# on the next cycle when new prices arrive.

def _read_cursor() -> Dict[str, Any]:
    return read_json(PAPER_EXECUTION_CURSOR_PATH, {
        "schema_version": "signal_paper_execution_cursor_v1",
        "updated_utc": None,
        "cursor_by_key": {},
    })


def _write_cursor(payload: Dict[str, Any]) -> None:
    write_json(PAPER_EXECUTION_CURSOR_PATH, payload)


# ═══════════════════════════════════════════════════════════════════════════════
# NON-IBKR: deferred entry (pending_resolution until next cycle)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_deferred_entry(
    strategy: Dict[str, Any],
    signal: Dict[str, Any],
    feature: Dict[str, Any],
    decision_context: Optional[Dict[str, Any]] = None,
    gate_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Record entry conditions for later resolution.

    Instead of the old _alignment_outcome (which checked the same feature
    data that generated the signal — circular logic), we record the trade
    as pending_resolution with entry_price, and resolve on the NEXT
    strategy engine cycle when new price data is available.

    Fase 5 additions:
    - execution_state: formal lifecycle state machine
    - decision_context: why the trade was taken (from Fase 3.4)
    - gate_audit: risk + governance gate pass/fail record
    """
    entry_price = feature.get("last") or feature.get("mid")
    payout_pct = float(feature.get("payout_pct") or 80.0)
    venue = strategy.get("venue", "")

    # Fase 5: execution_state differentiates venue execution paths
    if venue == "ibkr":
        initial_state = "internal_paper_shadow"
    else:
        initial_state = "signal_generated"

    # P-OP29b: Determine holding duration so the resolver can do binary-expiry
    # resolution at the right time (instead of waiting for 0.05% threshold).
    duration_seconds = int(
        signal.get("duration_seconds")
        or feature.get("expiry_seconds")
        or strategy.get("preferred_holding_seconds")
        or 300  # default 5m for PO binary options
    )

    entry = {
        "timestamp": _utc_now(),
        "symbol": signal.get("symbol"),
        "direction": signal.get("direction"),
        "result": "pending_resolution",
        "profit": 0.0,
        "entry_price": entry_price,
        "entry_payout_pct": payout_pct,
        "paper_shadow": True,
        "paper_only": True,
        "strategy_id": strategy.get("strategy_id"),
        "venue": venue,
        "family": strategy.get("family"),
        "timeframe": signal.get("timeframe"),
        "setup_variant": signal.get("setup_variant"),
        "asset_class": signal.get("asset_class"),
        "confidence": signal.get("confidence"),
        "signal_score": signal.get("signal_score"),
        "resolution_mode": "deferred_forward_v1",
        "signal_reasons": signal.get("reasons", []),
        "signal_blockers": signal.get("blockers", []),
        "feature_key": signal.get("feature_key"),
        "duration_seconds": duration_seconds,  # P-OP29b: for binary-expiry resolution
        "resolved": False,
        # P-OP22: session awareness — record session for retrospective analysis
        "hour_utc": signal.get("hour_utc"),
        "session_name": signal.get("session_name"),
        "session_quality": signal.get("session_quality"),
        # Fase 5: execution lifecycle state
        "execution_state": initial_state,
        # P-OP32d: Capture indicator values at entry for post-hoc analysis
        "rsi_14": signal.get("rsi_14"),
        "bb_pct_b": signal.get("bb_pct_b"),
        "stoch_k": signal.get("stoch_k"),
        "stoch_d": signal.get("stoch_d"),
        "macd_histogram": signal.get("macd_histogram"),
        "indicator_confluence": signal.get("indicator_confluence"),
        "market_regime": signal.get("market_regime"),
        "price_zscore": signal.get("price_zscore"),
        "window_change_pct": signal.get("window_change_pct"),
    }

    # Fase 5.3: decision_context — why the trade was taken
    if decision_context:
        entry["decision_context"] = decision_context

    # Fase 5.3: gate_audit — which gates were checked and their results
    if gate_audit:
        entry["gate_audit"] = gate_audit

    return entry


# ═══════════════════════════════════════════════════════════════════════════════
# RESOLVER: resolve pending trades with forward-looking price data
# ═══════════════════════════════════════════════════════════════════════════════

def resolve_pending_paper_trades(feature_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve pending_resolution trades using current feature data.

    Called from refresh_strategy_engine() on each cycle.  For each pending
    trade, we look up the CURRENT price for the same feature_key and compare
    against the recorded entry_price.  If a real price move has occurred,
    the trade is resolved to win/loss.

    P5-10 improvements:
    - Configurable price-change threshold (RESOLUTION_PRICE_THRESHOLD_PCT).
    - Timeout: trades pending longer than PENDING_TRADE_TIMEOUT_SECONDS are
      auto-expired as a loss.
    - Stale feature data is rejected (uses is_stale from P5-09).
    - Missing feature_key emits a warning (PO bridge down).

    Returns a summary dict with counts of resolved/skipped/remaining/expired.
    """
    ledger = _read_ledger()
    entries = ledger.get("entries", [])

    # Index current features by key for O(1) lookup
    feature_by_key: Dict[str, Dict[str, Any]] = {
        item.get("key"): item
        for item in feature_snapshot.get("items", [])
        if isinstance(item, dict) and item.get("key")
    }

    resolved_count = 0
    skipped_count = 0
    expired_count = 0
    newly_resolved: List[Dict[str, Any]] = []  # 9X-fix: track for platform metrics
    now = datetime.now(timezone.utc)
    timeout_seconds = _cfg.PENDING_TRADE_TIMEOUT_SECONDS
    threshold_pct = _cfg.RESOLUTION_PRICE_THRESHOLD_PCT

    for entry in entries:
        if entry.get("resolved") or entry.get("result") != "pending_resolution":
            continue

        # --- P5-10: Timeout check ----------------------------------------
        trade_ts = entry.get("timestamp")
        if trade_ts and timeout_seconds > 0:
            try:
                text = str(trade_ts).replace("Z", "+00:00")
                created = datetime.fromisoformat(text)
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                age = (now - created).total_seconds()
            except Exception as exc:
                log.debug("Trade timestamp parse failed, defaulting age=0: %s", exc)
                age = 0.0

            # --- P-OP29a: Binary expiry resolution -------------------------
            # When a trade reaches its intended holding duration, resolve it
            # like a real binary option.
            # P-OP34: If price change < BINARY_EXPIRY_MIN_RELIABLE_PCT, our
            # feed might disagree with PO's server price → resolve as loss
            # (conservative: if we can't confirm the win, assume loss).
            holding_duration = float(entry.get("duration_seconds") or 300)
            if age >= holding_duration:
                # Try to get current price for binary-expiry resolution
                fk = entry.get("feature_key")
                cf = feature_by_key.get(fk) if fk else None
                ep = entry.get("entry_price")
                cp = None
                if cf and not cf.get("is_stale") and cf.get("price_available"):
                    cp = cf.get("last") or cf.get("mid")

                # P-OP54r: Candle buffer fallback — if feature snapshot is stale
                # or unavailable, use the latest close from the PO candle buffer.
                _cp_source = "feature_snapshot"
                if not cp and entry.get("venue") == "pocket_option":
                    cp_fallback = _get_candle_buffer_last_price(
                        entry.get("symbol") or "EURUSD_otc"
                    )
                    if cp_fallback:
                        cp = cp_fallback
                        _cp_source = "candle_buffer_fallback"
                        log.info(
                            "Trade %s/%s: using candle buffer fallback price %.6f",
                            entry.get("strategy_id"), entry.get("symbol"), cp,
                        )

                if ep and cp:
                    ep_f = float(ep)
                    cp_f = float(cp)
                    direction = entry.get("direction")
                    price_change_pct = abs(cp_f - ep_f) / ep_f * 100.0 if ep_f else 0.0

                    # P-OP34 / P-OP34b: Check minimum reliable threshold.
                    # With 150-200 ticks/min (WS-push), 0.001% is sufficient.
                    # Only truly flat trades (< 0.001% = ~0.01 pip) are uncertain.
                    min_reliable_pct = _cfg.BINARY_EXPIRY_MIN_RELIABLE_PCT
                    if price_change_pct < min_reliable_pct:
                        # Price change too small to trust direction → conservative loss
                        won = False
                        resolution_tag = "unreliable_margin"
                        log.info(
                            "Trade %s/%s binary-expiry: change %.5f%% < min_reliable %.4f%% → loss (uncertain)",
                            entry.get("strategy_id"), entry.get("symbol"),
                            price_change_pct, min_reliable_pct,
                        )
                    elif cp_f == ep_f:
                        # Exact same price → draw, resolve as loss (binary: no profit on tie)
                        won = False
                        resolution_tag = "tie"
                    elif direction == "call":
                        won = cp_f > ep_f
                        resolution_tag = "directional"
                    elif direction == "put":
                        won = cp_f < ep_f
                        resolution_tag = "directional"
                    else:
                        won = False
                        resolution_tag = "unknown_direction"

                    amount = _cfg.PAPER_TRADE_DEFAULT_AMOUNT
                    payout_factor = min(max(float(entry.get("entry_payout_pct") or 80.0) / 100.0, 0.5), 0.95)
                    confidence = min(max(float(entry.get("confidence") or 0.0), 0.0), 1.0)

                    if won:
                        result_str = "win"
                        # P-OP54f: Fixed payout calculation. Binary options pay
                        # a FIXED payout on win — confidence does NOT reduce it.
                        # Previously: amount * max(payout_factor, 0.8) * max(confidence, 0.6)
                        # This was artificially reducing wins from $9.20 to ~$5.50
                        # (at 92% payout × 0.6 confidence floor = 55.2%).
                        # Binary options: you win the full payout or lose everything.
                        profit = _round(amount * payout_factor)
                    else:
                        result_str = "loss"
                        profit = _round(-amount)

                    price_change_pct = abs(cp_f - ep_f) / ep_f * 100.0 if ep_f else 0.0
                    entry["result"] = result_str
                    entry["profit"] = profit
                    entry["resolved"] = True
                    entry["exit_price"] = _round(cp_f, 6)
                    entry["resolved_utc"] = _utc_now()
                    entry["resolution_mode"] = "binary_expiry"
                    entry["resolution_price_source"] = _cp_source
                    entry["resolution_tag"] = resolution_tag
                    entry["resolution_age_seconds"] = _round(age, 1)
                    entry["resolution_price_change_pct"] = _round(price_change_pct, 4)
                    entry["execution_state"] = f"resolved_{result_str}"
                    # Signed edge: positive = correct direction, negative = wrong.
                    # For CALL: (exit - entry), for PUT: (entry - exit).
                    # Expressed in price units (pips for forex, cents for stocks).
                    dir_sign = 1.0 if direction == "call" else -1.0
                    signed_edge = _round((cp_f - ep_f) * dir_sign, 6)
                    signed_edge_pct = _round((cp_f - ep_f) / ep_f * 100.0 * dir_sign, 4) if ep_f else 0.0
                    entry["signed_edge"] = signed_edge
                    entry["signed_edge_pct"] = signed_edge_pct
                    resolved_count += 1
                    newly_resolved.append(entry)
                    log.info(
                        "Trade %s/%s binary-expiry resolved: %s (entry=%.6f exit=%.6f change=%.4f%% age=%.0fs)",
                        entry.get("strategy_id"), entry.get("symbol"),
                        result_str, ep_f, cp_f, price_change_pct, age,
                    )
                    continue

            if age > timeout_seconds:
                # P-OP29a: Hard timeout — no price data available, force loss
                amount = _cfg.PAPER_TRADE_DEFAULT_AMOUNT
                entry["result"] = "loss"
                entry["profit"] = _round(-amount)
                entry["resolved"] = True
                
                # P-OP54r: Try candle buffer fallback even on timeout
                exit_price = None
                if entry.get("venue") == "pocket_option":
                    exit_price = _get_candle_buffer_last_price(
                        entry.get("symbol") or "EURUSD_otc"
                    )
                entry["exit_price"] = _round(exit_price, 6) if exit_price else None
                entry["resolved_utc"] = _utc_now()
                entry["resolution_mode"] = "timeout_expired"
                entry["resolution_age_seconds"] = _round(age, 1)
                entry["execution_state"] = "resolved_loss"  # Fase 5: timeout always loss
                expired_count += 1
                resolved_count += 1
                newly_resolved.append(entry)
                log.warning(
                    "Trade %s/%s expired after %.0fs (timeout=%ds, no price data)",
                    entry.get("strategy_id"), entry.get("symbol"),
                    age, timeout_seconds,
                )
                continue

        # --- Feature lookup -----------------------------------------------
        feature_key = entry.get("feature_key")
        current_feature = feature_by_key.get(feature_key) if feature_key else None

        if not current_feature:
            # P5-10: warn when PO bridge is down (feature_key absent)
            if feature_key:
                log.debug(
                    "Feature key %s not in snapshot — bridge down? (trade %s/%s)",
                    feature_key, entry.get("strategy_id"), entry.get("symbol"),
                )
            skipped_count += 1
            continue

        if not current_feature.get("price_available"):
            skipped_count += 1
            continue

        # P5-10: Don't resolve with stale data (P5-09 is_stale flag)
        if current_feature.get("is_stale"):
            skipped_count += 1
            continue

        current_price = current_feature.get("last") or current_feature.get("mid")
        entry_price = entry.get("entry_price")

        if not entry_price or not current_price:
            skipped_count += 1
            continue

        entry_price = float(entry_price)
        current_price = float(current_price)

        # P5-10: Configurable threshold (was hardcoded 0.01%)
        price_change_pct = abs(current_price - entry_price) / entry_price * 100.0
        if price_change_pct < threshold_pct:
            skipped_count += 1
            continue

        # Determine outcome based on direction and price movement
        direction = entry.get("direction")
        if direction == "call":
            won = current_price > entry_price
        elif direction == "put":
            won = current_price < entry_price
        else:
            skipped_count += 1
            continue

        # Compute profit/loss
        amount = _cfg.PAPER_TRADE_DEFAULT_AMOUNT
        payout_factor = min(max(float(entry.get("entry_payout_pct") or 80.0) / 100.0, 0.5), 0.95)
        confidence = min(max(float(entry.get("confidence") or 0.0), 0.0), 1.0)

        if won:
            result = "win"
            # P-OP54f: Fixed payout — binary options pay full payout on win.
            profit = _round(amount * payout_factor)
        else:
            result = "loss"
            profit = _round(-amount)

        # Update the entry in-place
        entry["result"] = result
        entry["profit"] = profit
        entry["resolved"] = True
        entry["exit_price"] = _round(current_price, 6)
        entry["resolved_utc"] = _utc_now()
        entry["resolution_price_change_pct"] = _round(price_change_pct, 4)
        entry["execution_state"] = f"resolved_{result}"  # Fase 5: resolved_win or resolved_loss
        # Signed edge metric (same logic as binary_expiry path)
        dir_sign = 1.0 if direction == "call" else -1.0
        signed_edge = _round((current_price - entry_price) * dir_sign, 6)
        signed_edge_pct = _round((current_price - entry_price) / entry_price * 100.0 * dir_sign, 4) if entry_price else 0.0
        entry["signed_edge"] = signed_edge
        entry["signed_edge_pct"] = signed_edge_pct
        resolved_count += 1
        newly_resolved.append(entry)

    remaining = sum(
        1 for e in entries
        if not e.get("resolved") and e.get("result") == "pending_resolution"
    )

    if resolved_count > 0:
        ledger["updated_utc"] = _utc_now()
        _write_ledger(ledger)
        log.info("Resolved %d pending paper trades (%d expired, %d skipped, %d remaining)",
                 resolved_count, expired_count, skipped_count, remaining)
        # 9X-fix: Push resolved outcomes to PlatformManager so platform U
        # scores and metrics reflect actual deferred resolution results.
        _update_platform_metrics(newly_resolved)
        # 9X-fix: Push resolved outcomes to strategy scorecards so
        # expectancy, sample_quality, win_rate etc. reflect real data.
        _update_strategy_scorecards(newly_resolved)
        # P-OP22: Update session performance tracker with resolved outcomes
        _update_session_performance(newly_resolved)

    return {
        "resolved": resolved_count,
        "expired": expired_count,
        "skipped": skipped_count,
        "remaining": remaining,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PLATFORM METRICS BRIDGE (9X-fix)
# ═══════════════════════════════════════════════════════════════════════════════

_VENUE_TO_PLATFORM = {
    "pocket_option": "pocket_option",
    "ibkr": "ibkr",
    "internal": "internal_paper",
    "internal_paper": "internal_paper",
}


def _update_platform_metrics(resolved_entries: List[Dict[str, Any]]) -> None:
    """Push resolved trade outcomes to PlatformManager.

    Called after deferred trades are resolved so that per-platform U scores,
    win rates, and other metrics stay in sync with the ledger.
    """
    if not resolved_entries:
        return
    try:
        from brain_v9.trading.platform_manager import get_platform_manager
        pm = get_platform_manager()
    except Exception as exc:
        log.error("Cannot load PlatformManager — metrics NOT updated: %s", exc)
        return

    for entry in resolved_entries:
        try:
            venue = entry.get("venue", "internal")
            platform = _VENUE_TO_PLATFORM.get(venue, "internal_paper")
            result = entry.get("result", "loss")
            profit_raw = float(entry.get("profit", 0.0))
            symbol = entry.get("symbol", "")
            strategy_id = entry.get("strategy_id", "")

            # record_trade expects a positive profit value;
            # losses are subtracted internally via abs().
            pm.record_trade(platform, result, abs(profit_raw), symbol, strategy_id)
            log.info(
                "Platform metrics updated: %s %s %.2f %s/%s",
                platform, result, profit_raw, strategy_id, symbol,
            )
        except Exception as exc:
            log.error(
                "Failed to update platform metrics for %s/%s: %s",
                entry.get("strategy_id"), entry.get("symbol"), exc,
            )


def _update_strategy_scorecards(resolved_entries: List[Dict[str, Any]]) -> None:
    """Push resolved trade outcomes to strategy scorecards (resolution-only).

    Called after deferred trades are resolved so that per-strategy
    sample_quality, expectancy, win_rate, and other scorecard fields
    reflect the actual resolved data.

    IMPORTANT: This does NOT call ``update_strategy_scorecard()`` because that
    function always increments ``entries_taken``.  The entry was already counted
    when the trade was *created* (with ``resolved=False``).  Here we only
    convert the open entry to a resolved one: decrement ``entries_open``,
    increment ``entries_resolved``, record win/loss/profit, and recompute
    derived metrics.
    """
    if not resolved_entries:
        return
    try:
        from brain_v9.trading.strategy_scorecard import (
            _recompute,
            _symbol_key,
            _context_key,
            read_scorecards,
            SCORECARDS_PATH,
        )
    except Exception as exc:
        log.error("Cannot import scorecard helpers: %s", exc)
        return

    payload = read_scorecards()
    scorecards = payload.get("scorecards", {})
    symbol_scorecards = payload.get("symbol_scorecards", {})
    context_scorecards = payload.get("context_scorecards", {})
    modified = False

    for entry in resolved_entries:
        try:
            strategy_id = entry.get("strategy_id", "")
            if not strategy_id:
                continue
            if strategy_id not in scorecards:
                log.warning("Scorecard not found for %s — skipping resolution update", strategy_id)
                continue

            venue = entry.get("venue", "internal_paper")
            symbol = entry.get("symbol") or "UNKNOWN"
            timeframe = entry.get("timeframe") or "unknown"
            setup_variant = entry.get("setup_variant") or "base"
            result = entry.get("result", "loss")
            profit = float(entry.get("profit", 0.0) or 0.0)
            trade_timestamp = entry.get("resolved_utc") or entry.get("timestamp") or ""

            # Build a fake strategy dict for key functions
            strat = {"strategy_id": strategy_id, "venue": venue}
            s_key = _symbol_key(strat, symbol)
            c_key = _context_key(strat, symbol, timeframe, setup_variant)

            # Collect the cards that exist for this entry
            cards_to_update = [scorecards[strategy_id]]
            if s_key in symbol_scorecards:
                cards_to_update.append(symbol_scorecards[s_key])
            if c_key in context_scorecards:
                cards_to_update.append(context_scorecards[c_key])

            for card in cards_to_update:
                # Move from open → resolved
                open_count = int(card.get("entries_open", 0) or 0)
                if open_count > 0:
                    card["entries_open"] = open_count - 1
                card["entries_resolved"] = int(card.get("entries_resolved", 0) or 0) + 1

                # Record win / loss / draw
                if result == "win":
                    card["wins"] = int(card.get("wins", 0) or 0) + 1
                    card["gross_profit"] = round(float(card.get("gross_profit", 0.0) or 0.0) + profit, 4)
                    card["largest_win"] = max(float(card.get("largest_win", 0.0) or 0.0), profit)
                elif result == "loss":
                    card["losses"] = int(card.get("losses", 0) or 0) + 1
                    card["gross_loss"] = round(float(card.get("gross_loss", 0.0) or 0.0) + abs(profit), 4)
                    card["largest_loss"] = max(float(card.get("largest_loss", 0.0) or 0.0), abs(profit))
                else:
                    card["draws"] = int(card.get("draws", 0) or 0) + 1

                card["net_pnl"] = round(float(card.get("net_pnl", 0.0) or 0.0) + profit, 4)

                # Update recent outcomes
                recent = list(card.get("recent_5_outcomes", []))
                recent.append({
                    "timestamp": trade_timestamp,
                    "symbol": symbol,
                    "direction": entry.get("direction"),
                    "result": result,
                    "profit": profit,
                    "resolved": True,
                })
                card["recent_5_outcomes"] = recent[-5:]
                card["last_trade_utc"] = trade_timestamp
                _recompute(card)

            modified = True
            log.info(
                "Scorecard resolved: %s %s %s %.2f",
                strategy_id, symbol, result, profit,
            )
        except Exception as exc:
            log.error(
                "Failed to update scorecard for %s/%s: %s",
                entry.get("strategy_id"), entry.get("symbol"), exc,
            )

    if modified:
        from brain_v9.trading.strategy_scorecard import _utc_now as _sc_utc_now
        payload["updated_utc"] = _sc_utc_now()
        write_json(SCORECARDS_PATH, payload)


# ═══════════════════════════════════════════════════════════════════════════════
# P-OP22: SESSION PERFORMANCE TRACKER
# ═══════════════════════════════════════════════════════════════════════════════

def _update_session_performance(resolved_entries: List[Dict[str, Any]]) -> None:
    """Accumulate win/loss stats per trading session for adaptive gating.

    Reads and rewrites SESSION_PERF_PATH.  Each session key contains:
      resolved, wins, losses, win_rate, net_pnl, last_updated_utc
    Also computes per-session stats from the entry's hour_utc.
    For older entries without session_name, we derive it from timestamp.
    """
    if not resolved_entries:
        return
    try:
        from brain_v9.config import SESSION_PERF_PATH, get_current_session
        perf = read_json(SESSION_PERF_PATH, {})
        if not isinstance(perf, dict):
            perf = {}

        for entry in resolved_entries:
            session_name = entry.get("session_name")
            # Fallback: derive from timestamp for older entries
            if not session_name:
                ts_str = entry.get("timestamp", "")
                try:
                    text = str(ts_str).replace("Z", "+00:00")
                    dt = datetime.fromisoformat(text)
                    session_name = get_current_session(dt.hour)["session_name"]
                except Exception:
                    session_name = "unknown"

            if session_name not in perf:
                perf[session_name] = {
                    "resolved": 0, "wins": 0, "losses": 0,
                    "win_rate": 0.0, "net_pnl": 0.0,
                }

            s = perf[session_name]
            result = entry.get("result", "loss")
            profit = float(entry.get("profit", 0.0) or 0.0)
            s["resolved"] = int(s.get("resolved", 0) or 0) + 1
            if result == "win":
                s["wins"] = int(s.get("wins", 0) or 0) + 1
            else:
                s["losses"] = int(s.get("losses", 0) or 0) + 1
            s["net_pnl"] = round(float(s.get("net_pnl", 0.0) or 0.0) + profit, 4)
            s["win_rate"] = round(
                int(s["wins"]) / int(s["resolved"]) if int(s["resolved"]) > 0 else 0.0, 4
            )
            s["last_updated_utc"] = _utc_now()

        # Write atomically
        write_json(SESSION_PERF_PATH, perf)
        log.info(
            "Session performance updated: %s",
            {k: f'{v.get("resolved",0)}t/{v.get("win_rate",0):.0%}wr' for k, v in perf.items()},
        )
    except Exception as exc:
        log.error("Failed to update session performance: %s", exc)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINTS
# ═══════════════════════════════════════════════════════════════════════════════

def _read_ledger() -> Dict[str, Any]:
    return read_json(PAPER_EXECUTION_LEDGER_PATH, {
        "schema_version": "signal_paper_execution_ledger_v1",
        "updated_utc": None,
        "entries": [],
    })


def _write_ledger(ledger: Dict[str, Any]) -> None:
    write_json(PAPER_EXECUTION_LEDGER_PATH, ledger)


def persist_trade_execution_metadata(trade: Dict[str, Any]) -> bool:
    """Persist post-execution metadata back into the canonical ledger.

    The strategy engine augments returned trades with browser execution
    evidence after the ledger entry has already been written. This helper
    patches the latest matching ledger row so canonical chronology and
    platform dashboards keep the same truth.

    Fase 5: Also advances execution_state and runs E2E verification.
    """
    if not isinstance(trade, dict):
        return False
    strategy_id = str(trade.get("strategy_id") or "")
    symbol = str(trade.get("symbol") or "")
    timestamp = str(trade.get("timestamp") or "")
    if not strategy_id or not symbol or not timestamp:
        return False

    ledger = _read_ledger()
    entries = ledger.get("entries", [])
    if not isinstance(entries, list) or not entries:
        return False

    fields = (
        "browser_order",
        "browser_command_dispatched",
        "browser_command_status",
        "browser_trade_confirmed",
        "browser_trade_id",
        "executor_platform",
    )
    modified = False
    for entry in reversed(entries):
        if (
            str(entry.get("strategy_id") or "") == strategy_id
            and str(entry.get("symbol") or "") == symbol
            and str(entry.get("timestamp") or "") == timestamp
        ):
            for field in fields:
                if field in trade:
                    entry[field] = trade.get(field)
                    modified = True

            # Fase 5: Advance execution_state based on browser evidence
            browser_confirmed = trade.get("browser_trade_confirmed")
            browser_dispatched = trade.get("browser_command_dispatched")
            if browser_confirmed:
                entry["execution_state"] = "browser_confirmed"
            elif browser_dispatched:
                entry["execution_state"] = "browser_dispatched"

            # Fase 5.1: E2E verification — validate browser evidence matches signal
            entry["verification"] = _verify_execution_e2e(entry, trade)

            break

    if not modified:
        return False

    ledger["updated_utc"] = _utc_now()
    _write_ledger(ledger)
    return True


def _verify_execution_e2e(entry: Dict[str, Any], trade: Dict[str, Any]) -> Dict[str, Any]:
    """Verify that browser execution evidence matches signal parameters.

    Returns a verification dict with status and any mismatches found.
    """
    checks = []
    mismatches = []

    browser_order = trade.get("browser_order") or {}
    raw = browser_order.get("raw") or {}
    command = raw.get("command") or {}
    result_data = command.get("result") or {}
    evidence = result_data.get("evidence") or {}

    # Check 1: Symbol match
    browser_symbol = evidence.get("current_symbol", "")
    trade_symbol = entry.get("symbol", "")
    if browser_symbol and trade_symbol:
        symbol_match = (
            trade_symbol.lower().replace("_otc", "").replace("_", "")
            in browser_symbol.lower().replace("/", "").replace(" ", "")
            or browser_symbol.lower().replace("/", "").replace(" ", "")
            in trade_symbol.lower().replace("_otc", "").replace("_", "")
        )
        checks.append("symbol")
        if not symbol_match:
            mismatches.append({
                "check": "symbol",
                "expected": trade_symbol,
                "got": browser_symbol,
            })

    # Check 2: Direction match (button text)
    button_text = str(evidence.get("button_text", "")).lower()
    direction = str(entry.get("direction", "")).lower()
    if button_text and direction:
        checks.append("direction")
        direction_match = (
            (direction in ("call", "up", "long") and any(x in button_text for x in ("call", "up", "higher", "buy")))
            or (direction in ("put", "down", "short") and any(x in button_text for x in ("put", "down", "lower", "sell")))
        )
        if not direction_match:
            mismatches.append({
                "check": "direction",
                "expected": direction,
                "got": button_text,
            })

    # Check 3: Balance delta (journal)
    journal_before = evidence.get("journal_before") or {}
    journal_after = evidence.get("journal_after") or {}
    balance_before = journal_before.get("balance_demo")
    trades_badge_delta = journal_after.get("trades_badge_delta")
    if balance_before is not None:
        checks.append("balance_captured")
    if trades_badge_delta is not None and trades_badge_delta > 0:
        checks.append("trade_registered_in_platform")

    status = "verified_match" if (checks and not mismatches) else (
        "mismatch_detected" if mismatches else "unverified"
    )

    return {
        "status": status,
        "checks_performed": checks,
        "mismatches": mismatches,
        "verified_utc": _utc_now(),
    }


def execute_signal_paper_trade(
    strategy: Dict[str, Any],
    signal: Dict[str, Any],
    feature: Dict[str, Any],
    lane: Dict[str, Any],
    decision_context: Optional[Dict[str, Any]] = None,
    gate_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute a paper trade from a strategy signal.

    ALL venues use deferred_forward_v1: entry price recorded from live feature
    data, resolved on the next strategy engine cycle when new price data arrives.
    This ensures the signal direction correlates with actual forward price moves.

    Fase 5: Accepts decision_context and gate_audit for ledger persistence.
    """
    if not signal or not signal.get("execution_ready"):
        return {
            "success": False,
            "error": "signal_not_ready_for_execution",
            "signal": signal,
            "selected_lane": lane,
        }

    if not feature.get("price_available"):
        return {
            "success": False,
            "error": "no_price_context_for_signal_execution",
            "signal": signal,
            "selected_lane": lane,
        }

    # --- Trade deduplication guard (9X-02) --------------------------------
    # Prevent multiple identical trades from being fired in the same cycle.
    cooldown_seconds = _cfg.AUTONOMY_CONFIG.get("trade_cooldown_seconds", 60)
    strategy_id = strategy.get("strategy_id", "")
    symbol = signal.get("symbol", "")
    ledger = _read_ledger()
    entries = ledger.setdefault("entries", [])

    # --- Loss-streak circuit breaker (2026-03-30, UPGRADED P-OP54l) ----------
    # P-OP54l: Aggressive money management based on binary options best practices.
    # 3 consecutive losses = 30 min pause (was 10 min).
    # 5+ consecutive losses = end of day (block until next UTC day).
    # This prevents tilt-driven cascading losses.
    venue = strategy.get("venue") or signal.get("venue") or ""
    try:
        from brain_v9.trading.platform_manager import get_platform_manager
        pm = get_platform_manager()
        pm_metrics = pm.get_metrics(venue) if hasattr(pm, "get_metrics") else None
        if pm_metrics:
            streak = getattr(pm_metrics, "current_loss_streak", 0) or 0
            if streak >= 5:
                # P-OP54l: 5+ losses = block until next UTC day
                now_utc = datetime.now(timezone.utc)
                seconds_until_midnight = (
                    (24 - now_utc.hour) * 3600
                    - now_utc.minute * 60
                    - now_utc.second
                )
                log.warning(
                    "MONEY_MGMT: %s streak=%d >= 5 — BLOCKING until next UTC day (%ds)",
                    venue, streak, seconds_until_midnight,
                )
                return {
                    "success": False,
                    "error": "loss_streak_eod_block",
                    "loss_streak": streak,
                    "cooldown_seconds": seconds_until_midnight,
                    "message": "5+ consecutive losses — trading halted until next UTC day",
                    "signal": signal,
                    "selected_lane": lane,
                }
            elif streak >= 3:
                # P-OP54l: 3-4 losses = 30 min pause (was 10 min)
                streak_cooldown = 1800  # 30 min flat
                last_trade_time_str = getattr(pm_metrics, "last_trade_time", None)
                if last_trade_time_str:
                    try:
                        ltt = datetime.fromisoformat(str(last_trade_time_str).replace("Z", "+00:00"))
                        if ltt.tzinfo is None:
                            ltt = ltt.replace(tzinfo=timezone.utc)
                        elapsed = (datetime.now(timezone.utc) - ltt).total_seconds()
                        if elapsed < streak_cooldown:
                            log.info(
                                "MONEY_MGMT: %s streak=%d, cooldown=%ds, elapsed=%.0fs — BLOCKING",
                                venue, streak, streak_cooldown, elapsed,
                            )
                            return {
                                "success": False,
                                "error": "loss_streak_cooldown_active",
                                "loss_streak": streak,
                                "cooldown_seconds": streak_cooldown,
                                "elapsed_seconds": round(elapsed),
                                "signal": signal,
                                "selected_lane": lane,
                            }
                    except (ValueError, TypeError):
                        pass
    except Exception as exc:
        log.debug("Loss-streak check unavailable: %s", exc)

    # --- P-OP54l: Daily stop-loss gate (-5% of capital) --------------------
    # Sum today's resolved P/L from ledger. If daily loss exceeds 5% of
    # paper capital ($10k → -$500), block all trades until next UTC day.
    _DAILY_STOP_LOSS_PCT = 0.05
    _PAPER_CAPITAL = 10000.0  # matches QC project capital
    try:
        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        daily_pnl = 0.0
        for entry in reversed(entries):
            ts_str = str(entry.get("timestamp", ""))
            if not ts_str.startswith(today_utc):
                break  # entries are chronological; stop when we leave today
            if entry.get("result") in ("win", "loss"):
                daily_pnl += float(entry.get("profit", 0.0))
        daily_loss_limit = -(_DAILY_STOP_LOSS_PCT * _PAPER_CAPITAL)
        if daily_pnl <= daily_loss_limit:
            log.warning(
                "MONEY_MGMT: Daily stop-loss triggered — P/L today = $%.2f (limit = $%.2f)",
                daily_pnl, daily_loss_limit,
            )
            return {
                "success": False,
                "error": "daily_stop_loss_triggered",
                "daily_pnl": round(daily_pnl, 2),
                "daily_loss_limit": daily_loss_limit,
                "message": f"Daily P/L ${daily_pnl:.2f} exceeds -5% stop (${daily_loss_limit:.2f})",
                "signal": signal,
                "selected_lane": lane,
            }
    except Exception as exc:
        log.debug("Daily stop-loss check failed: %s", exc)

    if cooldown_seconds > 0 and entries:
        now = datetime.now(timezone.utc)
        for recent in reversed(entries[-20:]):
            if (recent.get("strategy_id") == strategy_id
                    and recent.get("symbol") == symbol):
                try:
                    ts_str = str(recent.get("timestamp", "")).replace("Z", "+00:00")
                    ts = datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if (now - ts).total_seconds() < cooldown_seconds:
                        log.info(
                            "Trade dedup: skipping %s/%s — last trade %.0fs ago (cooldown=%ds)",
                            strategy_id, symbol,
                            (now - ts).total_seconds(), cooldown_seconds,
                        )
                        return {
                            "success": False,
                            "error": "trade_cooldown_active",
                            "signal": signal,
                            "selected_lane": lane,
                        }
                except (ValueError, TypeError) as exc:
                    log.debug("Trade dedup timestamp parse: %s", exc)
                break  # only check the most recent trade for this strategy+symbol

    # --- Cross-strategy direction conflict gate (2026-03-31) -----------------
    # Block trades that would create an opposing position on the same symbol
    # within DIRECTION_CONFLICT_WINDOW_SECONDS.  This prevents the guaranteed
    # loss pattern where strategy A fires CALL and strategy B fires PUT on the
    # same asset within seconds/minutes (net result: -$4.48 per pair at 92%
    # payout).  The gate is cross-strategy: it checks ALL recent trades on the
    # symbol regardless of which strategy originated them.
    DIRECTION_CONFLICT_WINDOW_SECONDS = 180  # 3 minutes
    trade_direction = signal.get("direction", "").lower()
    trade_symbol = signal.get("symbol") or strategy.get("preferred_symbol", "")

    if trade_direction in ("call", "put") and trade_symbol and entries:
        opposite = "put" if trade_direction == "call" else "call"
        now_dt = datetime.now(timezone.utc)
        for recent in reversed(entries[-50:]):
            if recent.get("symbol") != trade_symbol:
                continue
            recent_dir = (recent.get("direction") or "").lower()
            if recent_dir != opposite:
                continue
            # Check if the recent opposing trade is within the conflict window
            try:
                rts = str(recent.get("timestamp", "")).replace("Z", "+00:00")
                rt = datetime.fromisoformat(rts)
                if rt.tzinfo is None:
                    rt = rt.replace(tzinfo=timezone.utc)
                age_secs = (now_dt - rt).total_seconds()
                if 0 <= age_secs <= DIRECTION_CONFLICT_WINDOW_SECONDS:
                    log.warning(
                        "DIRECTION_CONFLICT_GATE: blocking %s %s on %s — opposing %s trade "
                        "from %s exists %.0fs ago (window=%ds)",
                        strategy_id, trade_direction, trade_symbol,
                        recent_dir, recent.get("strategy_id"),
                        age_secs, DIRECTION_CONFLICT_WINDOW_SECONDS,
                    )
                    return {
                        "success": False,
                        "error": "direction_conflict_blocked",
                        "conflicting_direction": recent_dir,
                        "conflicting_strategy": recent.get("strategy_id"),
                        "age_seconds": round(age_secs),
                        "signal": signal,
                        "selected_lane": lane,
                    }
            except (ValueError, TypeError):
                continue

    # All venues: deferred entry → resolved on next cycle with real price data
    trade = _build_deferred_entry(strategy, signal, feature, decision_context, gate_audit)

    # P-OP29c: Reject trades with no entry_price — these are unresolvable and
    # will always expire as a loss, polluting the PnL and triggering kill switch.
    if not trade.get("entry_price"):
        log.warning(
            "Rejecting trade %s/%s: entry_price is None (feature has no price data)",
            trade.get("strategy_id"), trade.get("symbol"),
        )
        return {
            "success": False,
            "error": "entry_price_missing",
            "signal": signal,
            "selected_lane": lane,
        }

    trade["executor_platform"] = lane.get("platform")

    ledger = _read_ledger()
    entries = ledger.setdefault("entries", [])
    entries.append(trade)
    ledger["updated_utc"] = trade["timestamp"]
    ledger["entries"] = entries[-_cfg.MAX_LEDGER_ENTRIES:]
    _write_ledger(ledger)

    return {
        "success": True,
        "trade": trade,
        "selected_lane": lane,
    }


_PO_BRIDGE_URL = "http://127.0.0.1:8765"
_PO_BRIDGE_COMMAND_TIMEOUT = 30  # seconds to wait for browser result


def _dispatch_po_bridge_trade_sync(
    symbol: str, direction: str, amount: float, duration: int,
) -> Dict[str, Any]:
    """P-OP4: Synchronous HTTP POST to PocketOption bridge server.

    execute_paper_trade() is called from sync contexts (accumulators, agent
    tools) that cannot await the async PocketOptionBridge.place_trade().
    This lightweight helper uses stdlib urllib so we don't need async.
    """
    payload = _json.dumps({
        "symbol": symbol,
        "direction": direction,
        "amount": amount,
        "duration": duration,
    }).encode()
    req = urllib.request.Request(
        f"{_PO_BRIDGE_URL}/trade",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
    except Exception as exc:
        log.warning("PO bridge /trade dispatch failed: %s", exc)
        return {"success": False, "status": "dispatch_exception", "reason": str(exc)}

    command_id = data.get("command_id")
    if not data.get("success") or not command_id:
        return {
            "success": False,
            "trade_id": data.get("trade_id"),
            "status": data.get("status"),
            "reason": data.get("reason"),
            "raw": data,
        }

    # Poll for browser result
    deadline = time.monotonic() + _PO_BRIDGE_COMMAND_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(1)
        try:
            with urllib.request.urlopen(
                f"{_PO_BRIDGE_URL}/commands/status/{command_id}", timeout=5,
            ) as sr:
                sp = _json.loads(sr.read())
        except Exception as exc:
            log.debug("PO bridge command poll failed: %s", exc)
            continue
        command = sp.get("command") or {}
        cmd_status = command.get("status")
        result_payload = command.get("result") or {}
        if cmd_status in {"completed", "failed"}:
            click_submitted = bool(result_payload.get("accepted_click"))
            ui_confirmed = bool(result_payload.get("ui_trade_confirmed"))
            return {
                "success": ui_confirmed,
                "click_submitted": click_submitted,
                "ui_trade_confirmed": ui_confirmed,
                "trade_id": command_id,
                "status": cmd_status,
                "reason": result_payload.get("reason"),
                "message": result_payload.get("status"),
                "raw": {"queued": data, "command": command},
            }

    return {
        "success": False,
        "trade_id": command_id,
        "status": "timed_out_waiting_browser_result",
        "reason": "browser_command_timeout",
        "raw": data,
    }


def execute_paper_trade(
    strategy: Dict[str, Any],
    signal: Dict[str, Any],
    feature: Dict[str, Any],
    amount: float = _cfg.PAPER_TRADE_DEFAULT_AMOUNT,
) -> Dict[str, Any]:
    """Simplified paper trade entry point for the agent tool.

    Wraps execute_signal_paper_trade with a synthetic lane, and marks the
    signal as execution_ready (the agent has already decided to trade).

    P-OP4: When venue is pocket_option, also dispatches the trade to the
    PocketOption bridge server so it actually executes in the browser.
    Previously this path only wrote to the ledger (paper shadow).
    """
    venue = strategy.get("venue", "internal")
    # Ensure signal is marked as ready (agent explicitly requested the trade)
    enriched_signal = dict(signal)
    enriched_signal.setdefault("execution_ready", True)
    enriched_signal.setdefault("confidence", 0.5)
    enriched_signal.setdefault("symbol", strategy.get("preferred_symbol", "unknown"))

    # Ensure feature has price_available
    enriched_feature = dict(feature)
    enriched_feature.setdefault("price_available", True)

    # P-OP4: Use demo_executor platform for PO so bridge dispatch is evident
    if venue == "pocket_option":
        lane = {"platform": "pocket_option_demo_executor"}
    else:
        lane = {"platform": f"{venue}_agent_tool"}

    # --- Adaptive Duration Policy (PocketOption only) -----------------------
    # Check volatility regime and select optimal duration before executing.
    if venue == "pocket_option":
        adp_features = {
            "bb_bandwidth": enriched_feature.get("bb_bandwidth"),
            "adx": enriched_feature.get("adx"),
            "price_zscore": enriched_feature.get("price_zscore"),
        }
        adp_candidates_raw = enriched_feature.get("duration_candidates") or []
        adp_candidates = []
        for c in adp_candidates_raw:
            if isinstance(c, dict):
                adp_candidates.append(str(c.get("label", "")))
            else:
                adp_candidates.append(str(c))
        signal_side = enriched_signal.get("direction")
        # P-OP52a: OTC bb_bandwidth is ~0.05-0.15, ADP default bb_low=1.5
        # always classifies PO as low_energy → skip. Use "normal" fallback.
        _po_adp_cfg = AdaptiveDurationConfig(low_volatility_policy="normal")
        adp_result = build_trade_decision_with_duration(
            features=adp_features,
            duration_candidates=adp_candidates,
            signal_side=signal_side,
            cfg=_po_adp_cfg,
        )
        log.info(
            "AdaptiveDuration (agent_tool) %s: decision=%s regime=%s duration=%s reason=%s",
            enriched_signal.get("symbol"),
            adp_result.get("decision"), adp_result.get("regime"),
            adp_result.get("selected_duration_seconds"), adp_result.get("reason"),
        )
        if adp_result.get("decision") == "skip":
            return {
                "success": False,
                "result": "adaptive_duration_skip",
                "profit": 0.0,
                "trade": {},
                "error": "adaptive_duration_skip",
                "adaptive_duration": adp_result,
            }
        # Inject selected duration
        adp_duration = adp_result.get("selected_duration_seconds")
        if adp_duration:
            enriched_signal["duration_seconds"] = adp_duration
            enriched_feature["expiry_seconds"] = adp_duration
        enriched_signal["adaptive_duration"] = adp_result

    result = execute_signal_paper_trade(strategy, enriched_signal, enriched_feature, lane)
    trade = result.get("trade", {})

    # ------------------------------------------------------------------
    # P-OP4: Dispatch to PocketOption bridge when venue is pocket_option.
    # This mirrors what _execute_strategy_trade() does in strategy_engine.py
    # (lines 529-571) but uses sync HTTP instead of async.
    # ------------------------------------------------------------------
    if venue == "pocket_option" and result.get("success") and trade:
        symbol = enriched_signal.get("symbol") or strategy.get("preferred_symbol", "EURUSD_otc")
        direction = enriched_signal.get("direction", "call")
        duration = int(
            enriched_signal.get("duration_seconds")
            or enriched_feature.get("expiry_seconds")
            or 300  # P-OP27: default 300s (5m) per asset_class_layer config
        )
        browser_order = _dispatch_po_bridge_trade_sync(symbol, direction, amount, duration)

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
        trade["executor_platform"] = "pocket_option_demo_executor"

        if not persist_trade_execution_metadata(trade):
            log.debug(
                "Could not persist bridge metadata for %s/%s at %s",
                trade.get("strategy_id"),
                trade.get("symbol"),
                trade.get("timestamp"),
            )

    return {
        "success": result.get("success", False),
        "result": trade.get("result", "pending_resolution"),
        "profit": trade.get("profit", 0.0),
        "trade": trade,
        "error": result.get("error"),
    }


def read_signal_paper_execution_ledger() -> Dict[str, Any]:
    return _read_ledger()
