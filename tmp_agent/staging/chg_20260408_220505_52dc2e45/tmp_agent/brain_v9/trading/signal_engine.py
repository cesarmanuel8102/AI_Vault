"""
Brain V9 - Signal engine
Evalua estrategias contra features reales disponibles.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from brain_v9.config import BASE_PATH
from brain_v9.config import SIGNAL_THRESHOLDS_BASE
from brain_v9.core.state_io import read_json, write_json
from brain_v9.trading.feature_engine import build_market_feature_snapshot, read_market_feature_snapshot

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
ENGINE_PATH = STATE_PATH / "strategy_engine"
ENGINE_PATH.mkdir(parents=True, exist_ok=True)

SIGNAL_SNAPSHOT_PATH = ENGINE_PATH / "strategy_signal_snapshot_latest.json"
log = logging.getLogger("signal_engine")


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


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# P-OP23: Adaptive signal thresholds — read from strategy or fall back to base
# ---------------------------------------------------------------------------
def _get_thresholds(strategy: Dict[str, Any] | None) -> Dict[str, float]:
    """Return signal thresholds for a strategy, with fallback to base config.

    If the strategy has been through adapt_strategy_parameters() it will have
    ``adapted_signal_thresholds`` set; otherwise we flatten the base config
    into the same key format.
    """
    adapted = (strategy or {}).get("adapted_signal_thresholds")
    if adapted and isinstance(adapted, dict):
        return adapted
    # Flatten base config to the same key format
    base = SIGNAL_THRESHOLDS_BASE
    return {
        "rsi_oversold_strong": base["rsi"]["oversold_strong"],
        "rsi_oversold_mild": base["rsi"]["oversold_mild"],
        "rsi_overbought_strong": base["rsi"]["overbought_strong"],
        "rsi_overbought_mild": base["rsi"]["overbought_mild"],
        "bb_lower_strong": base["bb"]["lower_strong"],
        "bb_lower_mild": base["bb"]["lower_mild"],
        "bb_upper_strong": base["bb"]["upper_strong"],
        "bb_upper_mild": base["bb"]["upper_mild"],
        "stoch_oversold_strong": base["stoch"]["oversold_strong"],
        "stoch_oversold_mild": base["stoch"]["oversold_mild"],
        "stoch_overbought_strong": base["stoch"]["overbought_strong"],
        "stoch_overbought_mild": base["stoch"]["overbought_mild"],
        "stoch_call_zone": base["stoch_crossover"]["call_zone"],
        "stoch_put_zone": base["stoch_crossover"]["put_zone"],
    }


def _strategy_filter_pass(feature: Dict[str, Any], strategy: Dict[str, Any]) -> tuple[bool, List[str]]:
    blockers: List[str] = []
    filters = strategy.get("filters", {}) or {}
    venue = str(feature.get("venue") or "")

    # P-OP8: For PocketOption, allow all non-unknown regimes.
    # OTC operates 24/7 and all regimes are tradeable. The old filter
    # blocked range_break_down and trend_mild, which are common PO states
    # and caused the system to sit idle for hours.
    regimes_allowed = filters.get("market_regime_allowed") or []
    current_regime = feature.get("market_regime")
    if venue == "pocket_option":
        # P-OP54k: Block unusable AND empirically losing regimes.
        # range_break_down: 24.1% WR across 29 trades — most frequent loser.
        # Also block unknown/dislocated as before.
        if current_regime in ("unknown", "dislocated", "range_break_down"):
            blockers.append("regime_not_allowed")
    else:
        # FIX v2 (2026-03-30): direction-aware regime defaults.
        # trend_strong split into trend_strong_up / trend_strong_down.
        if not regimes_allowed:
            family = strategy.get("family", "")
            if family in ("trend_following", "breakout"):
                regimes_allowed = [
                    "trend_up", "trend_strong_up", "trend_strong_down",
                    "trend_down_mild", "range_break_down", "mild",
                ]
            else:
                regimes_allowed = ["range", "mild", "trend_up", "trend_down_mild"]
        if regimes_allowed and current_regime not in regimes_allowed:
            blockers.append("regime_not_allowed")

    spread_pct = _safe_float(feature.get("spread_pct"))
    spread_max = filters.get("spread_pct_max")
    if spread_max is not None and spread_pct > _safe_float(spread_max):
        blockers.append("spread_too_wide")

    volatility_min = filters.get("volatility_min_atr_pct")
    if volatility_min is not None and _safe_float(feature.get("volatility_proxy_pct")) < _safe_float(volatility_min):
        blockers.append("volatility_too_low")

    return len(blockers) == 0, blockers


def _indicator_support(feature: Dict[str, Any], strategy: Dict[str, Any]) -> tuple[bool, List[str], List[str]]:
    required = [str(item).lower() for item in (strategy.get("core_indicators") or [])]
    available_labels = [str(item).lower() for item in (feature.get("indicator_candidates") or [])]
    if not required:
        return True, [], []
    if feature.get("venue") != "pocket_option":
        return True, [], []
    # P-OP9: Check that computed indicators are available (rsi_14, bb_*, stoch_*, macd_*)
    has_computed = feature.get("rsi_14") is not None and feature.get("bb_mid") is not None
    if has_computed or available_labels:
        reasons = ["indicator_controls_detected"]
        if has_computed:
            reasons.append("computed_indicators_available")
        return True, [], reasons
    return False, ["indicator_controls_unavailable"], []


def _trend_signal(feature: Dict[str, Any]) -> Dict[str, Any]:
    move = _safe_float(feature.get("last_vs_close_pct"))
    imbalance = _safe_float(feature.get("bid_ask_imbalance"))
    spread = _safe_float(feature.get("spread_pct"))
    venue = str(feature.get("venue") or "")
    regime = str(feature.get("market_regime") or "")
    confidence = 0.55
    
    # For IBKR: direction MUST align with regime (FIX 2026-03-30)
    if venue != "pocket_option":
        regime_bullish = regime in ("trend_strong_up", "trend_up")
        regime_bearish = regime in ("trend_strong_down", "trend_down_mild", "range_break_down")
        if regime_bullish:
            direction = "call"
        elif regime_bearish:
            direction = "put"
        else:
            direction = "call" if move >= 0 else "put"
        # Move must agree with direction for valid signal
        move_agrees = (move >= 0 and direction == "call") or (move < 0 and direction == "put")
        signal_valid = abs(move) > 0.1 and imbalance > -0.15 and move_agrees
    else:
        # FIX-MZ5 (2026-03-31): Disable trend following for PO/OTC binaries.
        # This family uses ZERO oscillator indicators (no RSI, BB, Stoch).
        # It only checks price movement and bid-ask imbalance, which means
        # it can enter at any indicator zone including dead center.
        # For 1-5 min binary options, entries must be at indicator extremes.
        direction = "call" if move >= 0 else "put"
        signal_valid = False  # Hard-blocked for PO
    
    if abs(move) > 0.35:
        confidence += 0.15
    if imbalance > 0.2:
        confidence += 0.10
    if spread <= 0.05:
        confidence += 0.05
    return {
        "direction": direction,
        "signal_valid": signal_valid,
        "confidence": round(_clamp(confidence, 0.0, 1.0), 4),
        "signal_score": round(_clamp(move / 1.5, -1.0, 1.0), 4),
        "reasons": ["trend_move_detected", "microstructure_support"],
    }


def _breakout_signal(feature: Dict[str, Any], thresholds: Dict[str, float] | None = None) -> Dict[str, Any]:
    move = _safe_float(feature.get("last_vs_close_pct"))
    spread = _safe_float(feature.get("spread_pct"))
    liquidity = _safe_float(feature.get("liquidity_score"))
    asset_class = str(feature.get("asset_class") or "")
    venue = str(feature.get("venue") or "")

    if venue == "pocket_option" or asset_class == "otc_binary":
        payout_pct = _safe_float(feature.get("payout_pct"))
        micro_move = _safe_float(feature.get("recent_micro_move_pct"))
        volatility = abs(_safe_float(feature.get("volatility_proxy_pct")))
        move_abs = abs(move)

        # P-OP9: Use computed indicators for direction and validation
        rsi = _safe_float(feature.get("rsi_14"), 50.0)
        bb_pct_b = _safe_float(feature.get("bb_pct_b"), 0.5)
        stoch_k = _safe_float(feature.get("stoch_k"), 50.0)
        macd_hist = _safe_float(feature.get("macd_histogram"), 0.0)
        confluence = int(feature.get("indicator_confluence", 0))

        # P-OP9/P-OP12: Direction based on indicator confluence, not raw micro-moves.
        # For breakout: follow momentum. Positive confluence = bullish, negative = bearish.
        # If confluence is 0 (no clear signal), use MACD histogram as tiebreaker.
        if confluence > 0:
            direction = "call"
        elif confluence < 0:
            direction = "put"
        elif macd_hist > 0:
            direction = "call"
        elif macd_hist < 0:
            direction = "put"
        else:
            direction = "call" if move >= 0 else "put"

        strength = max(
            move_abs / 0.02 if 0.02 else 0.0,
            abs(micro_move) / 0.015 if 0.015 else 0.0,
            volatility / 0.03 if 0.03 else 0.0,
        )

        # P-OP11 + P-OP13: Require minimum indicator confluence for signal validity.
        # Breakout needs momentum alignment: at least 1 indicator must agree.
        # P-OP13: Relaxed from >= 2 to >= 1 for paper testing on low-vol OTC.
        abs_confluence = abs(confluence)

        # FIX-MZ2 (2026-03-31): Require at least 1 oscillator in extreme zone.
        # Without this, MACD alone (almost always != 0) could satisfy confluence,
        # allowing entries in the dead middle of RSI/Stoch/BB range.
        _th = thresholds or _get_thresholds(None)
        _rsi_extreme = (
            rsi < _th.get("rsi_oversold_mild", 35.0)
            or rsi > _th.get("rsi_overbought_mild", 65.0)
        )
        _bb_extreme = (
            bb_pct_b < _th.get("bb_lower_mild", 0.15)
            or bb_pct_b > _th.get("bb_upper_mild", 0.85)
        )
        _stoch_extreme = (
            stoch_k < _th.get("stoch_oversold_mild", 30.0)
            or stoch_k > _th.get("stoch_overbought_mild", 70.0)
        )
        _has_oscillator_extreme = _rsi_extreme or _bb_extreme or _stoch_extreme

        # P-OP FIX: Lowered breakout payout threshold from 70 to 60.
        # PO payouts range 60-85%; 70% was filtering valid opportunities.
        # P-OP50: Lowered move_abs from 0.01 to 0.0005 and strength from 1.0
        # to 0.10 — OTC binary pairs exhibit micro-moves (~0.001% range) and
        # the old thresholds NEVER fired in low-volatility conditions.
        # Real OTC data: move_abs ~0.0009, strength ~0.11, so 0.0005/0.10
        # allows signals while still filtering absolute zero-movement ticks.
        #
        # P-OP52b: In OTC, last_vs_close_pct is frequently 0.0 (candle just
        # opened or price unchanged vs prior close), yet oscillators computed
        # from the full candle window (RSI, Stoch, BB%b) show real extremes.
        # When an oscillator is extreme AND at least 1 indicator agrees on
        # direction, waive the move_abs/strength gate — oscillator extremes
        # are a more robust momentum signal than a single tick's price delta.
        # (Relaxed from abs_confluence>=2 to >=1: in OTC, single-indicator
        # extreme + confluence already provides enough quality filter given
        # that _has_oscillator_extreme is also required.)
        _oscillator_consensus = _has_oscillator_extreme and abs_confluence >= 1
        signal_valid = (
            payout_pct >= 50
            and (
                (move_abs >= 0.0005 and strength >= 0.10)
                or _oscillator_consensus  # P-OP52b: oscillator-driven override
            )
            and abs_confluence >= 1  # At least 1 of 4 indicators agrees on direction
            and _has_oscillator_extreme  # FIX-MZ2: block middle-zone entries
        )

        # P-OP10: Confidence based on indicator alignment, NOT payout.
        # Base 0.35, +0.15 per agreeing indicator (max 4), +0.05 for strong momentum.
        confidence = 0.35 + abs_confluence * 0.15
        if strength >= 2.0:
            confidence += 0.05
        # Penalize if RSI contradicts direction
        # P-OP23: Use adaptive thresholds (reuse _th from FIX-MZ2 above)
        if direction == "call" and rsi > _th.get("rsi_overbought_strong", 75.0):
            confidence -= 0.10
        elif direction == "put" and rsi < _th.get("rsi_oversold_strong", 25.0):
            confidence -= 0.10

        reasons = ["range_break_or_expansion", "short_horizon_breakout_context"]
        if abs_confluence >= 1:
            reasons.append("indicator_confluence_strong")
        if abs_confluence >= 3:
            reasons.append("indicator_consensus")

        # ------------------------------------------------------------------
        # P-OP37: Trend continuation enhancement — ADX/DI/EMA/BB awareness.
        # Make breakout strategy regime-aware: boost when trending market
        # confirms breakout direction, penalize/block when contradicted.
        # ------------------------------------------------------------------
        _adx = _safe_float(feature.get("adx"))
        _plus_di = _safe_float(feature.get("plus_di"))
        _minus_di = _safe_float(feature.get("minus_di"))
        _adx_available = _adx > 0  # 0.0 means not computed yet
        _ema_50 = _safe_float(feature.get("ema_50"))
        _ema_trend = str(feature.get("ema_50_trend") or "unknown")
        _bb_bw = _safe_float(feature.get("bb_bandwidth"))
        _last_price = _safe_float(feature.get("last"))

        _adx_trend_confirmed = _adx_available and _adx > 25
        _adx_range = _adx_available and _adx < 15
        _di_dominance_ratio = 1.1

        # DI alignment: does the dominant DI match breakout direction?
        _di_confirms = False
        _di_contradicts = False
        if _adx_available and (_plus_di > 0 or _minus_di > 0):
            if direction == "call" and _plus_di > _minus_di * _di_dominance_ratio:
                _di_confirms = True
            elif direction == "put" and _minus_di > _plus_di * _di_dominance_ratio:
                _di_confirms = True
            elif direction == "call" and _minus_di > _plus_di:
                _di_contradicts = True
            elif direction == "put" and _plus_di > _minus_di:
                _di_contradicts = True

        # Hard block: breakout against a CONFIRMED trend.
        # ADX > 25 says "strong trend", DI says it's opposite to our direction
        # → this is a false breakout, not a continuation.
        _trend_contra_block = _adx_trend_confirmed and _di_contradicts
        if _trend_contra_block:
            signal_valid = False
            reasons.append("breakout_against_confirmed_trend")

        # ADX + DI confidence adjustments
        if _adx_trend_confirmed and _di_confirms:
            confidence += 0.08  # ideal: trending market + DI aligned
            reasons.append("adx_di_confirms_breakout")
        elif _adx_trend_confirmed:
            confidence += 0.04  # trending but DI not decisively dominant
            reasons.append("adx_confirms_breakout")
        elif _adx_range:
            confidence -= 0.06  # strong range → breakouts unreliable
            reasons.append("adx_range_penalizes_breakout")

        if _di_confirms and not _adx_trend_confirmed:
            confidence += 0.03  # DI aligned even without strong ADX trend
            reasons.append("di_confirms_direction")

        # EMA 50 alignment: price on the right side of EMA for breakout
        if _ema_50 > 0 and _last_price > 0:
            if direction == "call" and _last_price > _ema_50 and _ema_trend == "bullish":
                confidence += 0.04
                reasons.append("ema_confirms_breakout")
            elif direction == "put" and _last_price < _ema_50 and _ema_trend == "bearish":
                confidence += 0.04
                reasons.append("ema_confirms_breakout")
            elif direction == "call" and _ema_trend == "bearish":
                confidence -= 0.05
                reasons.append("ema_contradicts_breakout")
            elif direction == "put" and _ema_trend == "bullish":
                confidence -= 0.05
                reasons.append("ema_contradicts_breakout")

        # BB bandwidth: narrow bands → compression (breakout unreliable yet),
        # wide bands → expansion underway (breakout more reliable).
        if _bb_bw > 0:
            if _bb_bw < 0.03:
                confidence -= 0.03
                reasons.append("bb_bandwidth_narrow")
            elif _bb_bw > 0.08:
                confidence += 0.03
                reasons.append("bb_bandwidth_expanding")

        # FIX-MZ1 (2026-03-31): REMOVED RSI middle-zone bonus.
        # Previously rewarded RSI 40-65 (call) / 35-60 (put) with +0.03,
        # which actively encouraged entries in the dead center.
        # Replaced with extreme-zone bonus: reward RSI confirming the direction
        # at an extreme (oversold for calls, overbought for puts).
        if direction == "call" and rsi < _th.get("rsi_oversold_mild", 35.0):
            confidence += 0.04
            reasons.append("rsi_extreme_confirms_call")
        elif direction == "put" and rsi > _th.get("rsi_overbought_mild", 65.0):
            confidence += 0.04
            reasons.append("rsi_extreme_confirms_put")

        # P-OP54g: Empirical CALL penalty (breakout path).
        # Same rationale as mean reversion — CALL WR=20.7% across all strategies.
        if direction == "call":
            confidence -= 0.06
            reasons.append("call_direction_empirical_penalty")

        return {
            "direction": direction,
            "signal_valid": signal_valid,
            "confidence": round(_clamp(confidence, 0.0, 1.0), 4),
            "signal_score": round(_clamp(strength / 1.6, 0.0, 1.0), 4),
            "reasons": reasons,
        }

    # --- IBKR / non-OTC breakout path (FIX 2026-03-30) ---
    # Direction MUST align with market regime. Previously used only
    # last_vs_close_pct which could be stale/misleading.
    regime = str(feature.get("market_regime") or "")
    
    # Regime encodes direction: trend_strong_up, trend_up = bullish;
    # trend_strong_down, trend_down_mild, range_break_down = bearish.
    regime_bullish = regime in ("trend_strong_up", "trend_up")
    regime_bearish = regime in ("trend_strong_down", "trend_down_mild", "range_break_down")
    
    # Direction from regime (primary) with move as tiebreaker for neutral regimes
    if regime_bullish:
        direction = "call"
    elif regime_bearish:
        direction = "put"
    else:
        # Neutral regimes (range, mild, unknown): follow the move
        direction = "call" if move >= 0 else "put"
    
    # Signal validity: require meaningful move AND direction-regime agreement
    move_valid = abs(move) >= 0.35 and spread <= 0.25 and liquidity >= 0.5
    # Block if move direction contradicts regime direction
    move_agrees = (move >= 0 and direction == "call") or (move < 0 and direction == "put")
    signal_valid = move_valid and move_agrees
    
    confidence = 0.45 + min(abs(move), 1.5) * 0.25 + liquidity * 0.15
    # Boost confidence when regime and move strongly agree
    if move_agrees and abs(move) >= 0.5:
        confidence += 0.05
    
    reasons = ["ibkr_breakout"]
    if regime_bullish or regime_bearish:
        reasons.append(f"regime_aligned:{regime}")
    if not move_agrees:
        reasons.append("move_regime_conflict")
    
    return {
        "direction": direction,
        "signal_valid": signal_valid,
        "confidence": round(_clamp(confidence, 0.0, 1.0), 4),
        "signal_score": round(_clamp(abs(move) / 1.5, 0.0, 1.0), 4),
        "reasons": reasons,
    }


def _mean_reversion_signal(feature: Dict[str, Any], thresholds: Dict[str, float] | None = None) -> Dict[str, Any]:
    payout_pct = _safe_float(feature.get("payout_pct"))
    price_available = bool(feature.get("price_available"))
    venue = str(feature.get("venue") or "")
    if not price_available:
        return {
            "direction": None,
            "signal_valid": False,
            "confidence": 0.0,
            "signal_score": 0.0,
            "reasons": ["missing_price_context"],
        }
    move = _safe_float(feature.get("last_vs_close_pct"))
    zscore = _safe_float(feature.get("price_zscore"))
    micro_move = _safe_float(feature.get("recent_micro_move_pct"))
    volatility = _safe_float(feature.get("volatility_proxy_pct"))

    if venue == "pocket_option":
        # P-OP9: Use computed indicators for mean reversion signals.
        # Mean reversion fires when price is at an extreme and indicators confirm reversal.
        rsi = _safe_float(feature.get("rsi_14"), 50.0)
        bb_pct_b = _safe_float(feature.get("bb_pct_b"), 0.5)
        stoch_k = _safe_float(feature.get("stoch_k"), 50.0)
        stoch_d = _safe_float(feature.get("stoch_d"), 50.0)
        macd_hist = _safe_float(feature.get("macd_histogram"), 0.0)
        confluence = int(feature.get("indicator_confluence", 0))

        # P-OP9/P-OP12: Mean reversion direction — fade the extreme.
        # For mean reversion, the confluence is already computed as a
        # contrarian signal (RSI oversold = bullish = +1), so follow it directly.
        if confluence > 0:
            direction = "call"
        elif confluence < 0:
            direction = "put"
        else:
            # Fallback: use z-score (negative zscore = price below mean = expect bounce up)
            direction = "call" if zscore < 0 else "put"

        # P-OP9: Setup strength based on indicator extremes, not raw price moves.
        # Each extreme condition adds to setup strength.
        # P-OP23: Thresholds are now adaptive per-strategy (read from dict).
        setup_strength = 0.0
        reversion_signals = 0
        # P-OP32j: Track how many DISTINCT indicators (RSI, BB, Stoch, MACD)
        # are at extreme. Stochastic crossover is a bonus but does NOT count
        # as a separate indicator for the distinct-indicator gate.
        _distinct_indicators = 0
        _th = thresholds or _get_thresholds(None)

        # RSI extreme — P-OP13/P-OP23: adaptive thresholds
        _rsi_os = _th.get("rsi_oversold_strong", 25.0)
        _rsi_om = _th.get("rsi_oversold_mild", 35.0)
        _rsi_obs = _th.get("rsi_overbought_strong", 75.0)
        _rsi_obm = _th.get("rsi_overbought_mild", 65.0)
        if rsi < _rsi_os or rsi > _rsi_obs:
            setup_strength += 1.0
            reversion_signals += 1
            _distinct_indicators += 1
        elif rsi < _rsi_om or rsi > _rsi_obm:
            setup_strength += 0.5
            reversion_signals += 1
            _distinct_indicators += 1

        # Bollinger extreme — P-OP13/P-OP23: adaptive thresholds
        _bb_ls = _th.get("bb_lower_strong", -0.1)
        _bb_lm = _th.get("bb_lower_mild", 0.15)
        _bb_us = _th.get("bb_upper_strong", 1.1)
        _bb_um = _th.get("bb_upper_mild", 0.85)
        if bb_pct_b < _bb_ls or bb_pct_b > _bb_us:
            setup_strength += 1.0
            reversion_signals += 1
            _distinct_indicators += 1
        elif bb_pct_b < _bb_lm or bb_pct_b > _bb_um:
            setup_strength += 0.5
            reversion_signals += 1
            _distinct_indicators += 1

        # Stochastic extreme — P-OP13/P-OP23: adaptive thresholds
        _st_os = _th.get("stoch_oversold_strong", 15.0)
        _st_om = _th.get("stoch_oversold_mild", 30.0)
        _st_obs = _th.get("stoch_overbought_strong", 85.0)
        _st_obm = _th.get("stoch_overbought_mild", 70.0)
        if stoch_k < _st_os or stoch_k > _st_obs:
            setup_strength += 1.0
            reversion_signals += 1
            _distinct_indicators += 1
        elif stoch_k < _st_om or stoch_k > _st_obm:
            setup_strength += 0.5
            reversion_signals += 1
            _distinct_indicators += 1

        # Stochastic crossover (K crossing D from extreme) — P-OP23: adaptive zones
        # P-OP32k: This is a BONUS — it adds to setup_strength but does NOT
        # count as a distinct indicator (it's still Stochastic).
        _st_cz = _th.get("stoch_call_zone", 35.0)
        _st_pz = _th.get("stoch_put_zone", 65.0)
        if direction == "call" and stoch_k < _st_cz and stoch_k > stoch_d:
            setup_strength += 0.5
            reversion_signals += 1
        elif direction == "put" and stoch_k > _st_pz and stoch_k < stoch_d:
            setup_strength += 0.5
            reversion_signals += 1

        # P-OP32l: MACD as a participative indicator — not just a bonus.
        # When MACD histogram confirms the reversion direction, it counts as
        # a distinct confirming indicator and adds to setup strength.
        # When MACD contradicts, it penalizes confidence (divergence warning).
        _macd_confirms = False
        _macd_contradicts = False
        if (direction == "call" and macd_hist > 0) or (direction == "put" and macd_hist < 0):
            setup_strength += 0.5
            reversion_signals += 1
            _distinct_indicators += 1
            _macd_confirms = True
        elif (direction == "call" and macd_hist < 0) or (direction == "put" and macd_hist > 0):
            _macd_contradicts = True

        # P-OP32e: Momentum penalty — when 3+ indicators are at extremes
        # simultaneously, the move is likely a strong trend, NOT a reversion
        # opportunity. Data shows confidence [0.85+] has 22.2% WR (worst
        # bucket) while [0.55-0.65] has 52.9% (best). Penalize overconfidence.
        _regime = str(feature.get("market_regime") or "")

        # P-OP32f: Trend direction filter — don't fade a confirmed trend.
        # Mean reversion against a trend within a 5-min binary window is
        # a losing proposition (PUT WR 31.7% vs CALL 50%).
        _wc_pct = _safe_float(feature.get("window_change_pct"))
        _trend_blocked = False
        if _regime == "trend_strong":
            # Block all mean reversion in strong trends — the reversion
            # won't arrive within 5 minutes.
            _trend_blocked = True
        elif abs(_wc_pct) >= 0.10:
            # Moderate trend: block the contra-trend direction only.
            if _wc_pct > 0 and direction == "put":
                _trend_blocked = True   # uptrend → don't fade with PUT
            elif _wc_pct < 0 and direction == "call":
                _trend_blocked = True   # downtrend → don't fade with CALL

        # P-OP36a: ADX regime filter — quantitative trend/range classification.
        # ADX > 40 → market in extreme trend → hard-block mean reversion.
        # ADX 30-40 → transition zone → apply confidence penalty.
        # ADX < 30 → range/mild trend → allow mean reversion.
        # RELAXED 2026-03-31: was 25/20, now 40/30 to allow more trades.
        _adx = _safe_float(feature.get("adx"))
        _plus_di = _safe_float(feature.get("plus_di"))
        _minus_di = _safe_float(feature.get("minus_di"))
        _adx_available = _adx > 0  # 0.0 means not computed yet
        _adx_trend_block = False
        _adx_transition = False
        _di_contra = False
        if _adx_available:
            if _adx > 40:
                _adx_trend_block = True  # hard block — market in extreme trend
                _trend_blocked = True
            elif _adx > 30:
                _adx_transition = True   # caution zone — penalty only
            # DI directional alignment: confirm trade direction matches pressure
            if _plus_di > 0 or _minus_di > 0:
                if direction == "call" and _minus_di > _plus_di:
                    _di_contra = True  # buying into bearish pressure
                elif direction == "put" and _plus_di > _minus_di:
                    _di_contra = True  # selling into bullish pressure

        # P-OP36b: EMA 50 macro trend filter (was EMA 100 in P-OP35c).
        # If EMA 50 is available and the trade goes AGAINST the macro trend,
        # apply a confidence penalty (soft filter) rather than a hard block.
        # Hard block only when window_change also confirms the macro trend.
        _ema_trend = str(feature.get("ema_50_trend") or "unknown")
        _ema_contra = False  # True when trade direction opposes EMA 50 trend
        if _ema_trend == "bullish" and direction == "put":
            _ema_contra = True
        elif _ema_trend == "bearish" and direction == "call":
            _ema_contra = True
        # Hard block: EMA 50 + window_change both confirm trend against us
        if _ema_contra and abs(_wc_pct) >= 0.06:
            _trend_blocked = True

        # P-OP32j: Signal valid requires 2+ DISTINCT indicators at extreme.
        # Previously only required reversion_signals >= 1, which allowed a
        # single indicator (e.g. Stochastic extreme + crossover) to trigger.
        # Real confluence means at least 2 different indicators (RSI, BB,
        # Stoch, MACD) agree on the reversion setup.
        # P-OP32f: Also invalidate when trend filter blocks the setup.
        # P-OP FIX: 2026-03-31: Restored >= 2 distinct indicators now that
        # _BASE_CONFIDENCE_THRESHOLD is lowered to 0.52 (from 0.58). With
        # the confidence formula floor 0.20 + setup*0.15 + distinct*0.08,
        # 2 indicators + mild setup (1.0) → 0.20 + 0.15 + 0.16 = 0.51
        # which is just below 0.52 threshold, requiring at least moderate
        # setup_strength OR 3 indicators.  This filters out single-indicator
        # noise that was generating the opposing-trade problem.
        #
        # P-OP52c: Lowered volatility threshold from 0.002 → 0.0005 for OTC.
        # OTC binary pairs have typical window_range_pct of 0.0005-0.002%.
        # The 0.002 threshold blocked ALL mean reversion signals in low-vol
        # sessions. 0.0005 still filters truly frozen prices (caught by
        # P-OP44 frozen-price detection) while allowing normal OTC ranges.
        signal_valid = (
            payout_pct >= 50
            and volatility >= 0.0005
            and setup_strength >= 1.0
            and _distinct_indicators >= 2
            and not _trend_blocked
        )

        # P-OP32m: Confidence formula — lower floor (0.20), steeper climb,
        # so that confidence more accurately reflects setup quality.
        # Old: 0.30 + setup*0.15 + signals*0.05 → range [0.425, 0.80]
        # New: 0.20 + setup*0.15 + distinct*0.08 → range [0.46, 0.80]
        # The distinct_indicators term replaces reversion_signals to reward
        # genuine multi-indicator confluence, not same-indicator double-count.
        confidence = 0.20 + min(setup_strength, 3.5) * 0.15 + min(_distinct_indicators, 4) * 0.08

        # P-OP32l: MACD confirmation bonus / contradiction penalty
        if _macd_confirms:
            confidence += 0.03  # small additional nudge (already counted in distinct)
        if _macd_contradicts:
            # P-OP52e: Relaxed from 0.04 to 0.02 for OTC. MACD histogram in
            # OTC binary pairs is frequently 0 or near-zero (discrete price
            # steps), making "contradiction" mostly noise rather than a genuine
            # momentum divergence. The DI contra penalty already captures
            # directional pressure more reliably.
            confidence -= 0.02

        # P-OP32e: Apply momentum penalties after base calculation.
        if _distinct_indicators >= 3:
            confidence -= 0.08  # strong alignment = trend, not reversion (relaxed from 0.15)
        if _regime == "trend_strong":
            confidence -= 0.10

        # P-OP36b: EMA 50 contra-trend soft penalty (was EMA 100 in P-OP35c).
        # When trade opposes the macro trend (EMA 50) but isn't hard-blocked,
        # reduce confidence. Stacks with other penalties.
        if _ema_contra:
            confidence -= 0.06

        # P-OP36a: ADX transition zone penalty + DI contra penalty.
        if _adx_transition:
            confidence -= 0.04  # ADX 20-25: not full trend but caution
        if _di_contra:
            confidence -= 0.04  # trading against directional pressure

        # P-OP54g: Empirical directional bias penalty for EUR/USD OTC.
        # 65 trades show CALL WR=20.7% vs PUT WR=38.9%. CALL signals
        # lose money consistently. Apply a confidence penalty to CALL
        # to reduce trade frequency in the losing direction. This is
        # data-driven, not theoretical — to be revisited after 100+ trades.
        if direction == "call":
            confidence -= 0.06
            reasons_extra_call_penalty = True
        else:
            reasons_extra_call_penalty = False

        reasons = ["range_reversion_setup", "payout_filter", "short_horizon_price_context"]
        if reasons_extra_call_penalty:
            reasons.append("call_direction_empirical_penalty")
        if _distinct_indicators >= 2:
            reasons.append("indicator_extreme_confluence")
        if _distinct_indicators >= 3:
            reasons.append("strong_reversion_setup")
        if _macd_confirms:
            reasons.append("macd_confirms_direction")
        if _macd_contradicts:
            reasons.append("macd_contradicts_direction")
        if _trend_blocked:
            reasons.append("trend_direction_blocked")
        if _ema_contra:
            reasons.append("ema_contra_penalty")
        if _adx_trend_block:
            reasons.append("adx_trend_block")
        if _adx_transition:
            reasons.append("adx_transition_penalty")
        if _di_contra:
            reasons.append("di_contra_penalty")
        if _distinct_indicators < 2:
            reasons.append("insufficient_indicator_confluence")

        return {
            "direction": direction,
            "signal_valid": signal_valid,
            "confidence": round(_clamp(confidence, 0.0, 1.0), 4),
            "signal_score": round(_clamp(setup_strength / 3.5, 0.0, 1.0), 4),
            "reasons": reasons,
        }

    # Non-PO mean reversion (unchanged)
    direction_basis = zscore if abs(zscore) >= 0.2 else (micro_move if abs(micro_move) >= 0.01 else move)
    direction = "put" if direction_basis > 0 else "call"
    setup_strength = max(abs(zscore) / 2.0, abs(micro_move) / 0.04, abs(move) / 0.08)
    signal_valid = payout_pct >= 50 and volatility >= 0.01 and setup_strength >= 1.0
    confidence = 0.32 + min(setup_strength, 1.5) * 0.22 + min(payout_pct / 100.0, 1.0) * 0.16 + min(volatility / 0.15, 1.0) * 0.08
    return {
        "direction": direction,
        "signal_valid": signal_valid,
        "confidence": round(_clamp(confidence, 0.0, 1.0), 4),
        "signal_score": round(_clamp(setup_strength / 1.5, 0.0, 1.0), 4),
        "reasons": ["range_reversion_setup", "payout_filter", "short_horizon_price_context"],
    }


# ---------------------------------------------------------------------------
# P-OP22: Adaptive session blocking — reads session performance tracker
# ---------------------------------------------------------------------------
_SESSION_PERF_CACHE: Dict[str, Any] = {}
_SESSION_PERF_CACHE_TS: float = 0.0

def _check_adaptive_session_block(session_name: str) -> bool:
    """Return True if this session should be blocked based on accumulated evidence."""
    import time
    global _SESSION_PERF_CACHE, _SESSION_PERF_CACHE_TS
    from brain_v9.config import SESSION_PERF_PATH, SESSION_MIN_SAMPLE_FOR_BLOCK, SESSION_BLOCK_WIN_RATE_THRESHOLD

    # Re-read file at most every 60s to avoid I/O per signal eval
    now = time.monotonic()
    if now - _SESSION_PERF_CACHE_TS > 60.0:
        _SESSION_PERF_CACHE = read_json(SESSION_PERF_PATH, {})
        if not isinstance(_SESSION_PERF_CACHE, dict):
            _SESSION_PERF_CACHE = {}
        _SESSION_PERF_CACHE_TS = now

    session_data = _SESSION_PERF_CACHE.get(session_name, {})
    resolved = session_data.get("resolved", 0)
    wins = session_data.get("wins", 0)
    if resolved < SESSION_MIN_SAMPLE_FOR_BLOCK:
        return False
    win_rate = wins / resolved if resolved > 0 else 0.0
    return win_rate < SESSION_BLOCK_WIN_RATE_THRESHOLD


def _evaluate_strategy_feature(strategy: Dict[str, Any], feature: Dict[str, Any]) -> Dict[str, Any]:
    blockers: List[str] = []
    reasons: List[str] = []
    signal_family = strategy.get("family")
    symbol = feature.get("symbol")
    strategy_timeframes = strategy.get("timeframes") or ["spot"]
    feature_timeframe = feature.get("timeframe") or "spot"
    timeframe_supported = feature_timeframe in strategy_timeframes or feature_timeframe == "spot"
    timeframe = feature_timeframe if feature_timeframe in strategy_timeframes else strategy_timeframes[0]
    setup_variant = (strategy.get("setup_variants") or ["base"])[0]

    if symbol not in (strategy.get("universe") or []):
        blockers.append("symbol_not_in_universe")
    if feature.get("venue") == "pocket_option" and feature.get("stream_symbol_match") is False:
        blockers.append("stream_symbol_mismatch")
    if feature.get("asset_class") not in (strategy.get("asset_classes") or []):
        blockers.append("asset_class_not_supported")
    if not timeframe_supported:
        blockers.append("timeframe_not_supported")
    if not feature.get("price_available"):
        blockers.append("price_unavailable")
    # P-OP44: Frozen-price guard — feature_engine detected constant price stream.
    # Indicators are degenerate (BB=0, ADX→100, RSI→0/100), signal is meaningless.
    if feature.get("price_frozen"):
        blockers.append("price_frozen")
    # P5-09: Reject stale data — computed by feature_engine._compute_data_age()
    if feature.get("is_stale"):
        blockers.append("data_too_stale")

    # P-OP22: Session-aware gating — block or annotate based on trading session
    _session_name = feature.get("session_name", "unknown")
    _session_quality = feature.get("session_quality", "unknown")
    from brain_v9.config import SESSION_FILTER_MODE, SESSION_BLOCKED_QUALITIES
    if SESSION_FILTER_MODE == "enforce" and _session_quality in SESSION_BLOCKED_QUALITIES:
        blockers.append("session_blocked")
    elif SESSION_FILTER_MODE == "adaptive":
        _adaptive_blocked = _check_adaptive_session_block(_session_name)
        if _adaptive_blocked:
            blockers.append("session_blocked_adaptive")

    filters_ok, filter_blockers = _strategy_filter_pass(feature, strategy)
    blockers.extend(filter_blockers)
    indicator_ok, indicator_blockers, indicator_reasons = _indicator_support(feature, strategy)
    blockers.extend(indicator_blockers)
    reasons.extend(indicator_reasons)

    # P-OP23: Get adaptive thresholds for this strategy (falls back to base config)
    _signal_th = _get_thresholds(strategy)

    if signal_family == "trend_following":
        family_signal = _trend_signal(feature)
    elif signal_family == "breakout":
        family_signal = _breakout_signal(feature, thresholds=_signal_th)
    elif signal_family == "mean_reversion":
        family_signal = _mean_reversion_signal(feature, thresholds=_signal_th)
        setup_variant = "payout_filtered_reversion" if _safe_float(feature.get("payout_pct")) >= 60 else "range_reversion"
    else:
        family_signal = {"direction": None, "signal_valid": False, "confidence": 0.0, "signal_score": 0.0, "reasons": ["unsupported_family"]}

    reasons.extend(family_signal.get("reasons", []))
    if not filters_ok:
        reasons.append("filters_failed")

    signal_valid = bool(family_signal.get("signal_valid")) and not blockers and indicator_ok
    confidence = _safe_float(family_signal.get("confidence"))
    signal_score = _safe_float(family_signal.get("signal_score"))

    # ── P-OP54h: Block trades without substantive signal_reasons ──────────
    # Trades WITH signal_reasons win 52.4% vs 20.5% WITHOUT. The presence of
    # detailed reasons means the signal passed the full indicator evaluation
    # path (RSI/BB/Stoch/MACD confluence checks). Without them, the signal
    # is a shallow shell with no indicator backing.
    # "Substantive" = at least 3 reasons beyond generic boilerplate.
    _BOILERPLATE_REASONS = {
        "indicator_controls_detected", "computed_indicators_available",
        "filters_failed", "trend_move_detected", "microstructure_support",
    }
    _substantive_reasons = [r for r in reasons if r not in _BOILERPLATE_REASONS]
    if feature.get("venue") == "pocket_option" and len(_substantive_reasons) < 3:
        signal_valid = False
        blockers.append("insufficient_signal_reasons")

    # ── P-OP54i: Trading hour filter for PO ─────────────────────────────────
    # Hour 16 = 62.5% WR, Hour 14 = 46.2% WR (best empirical hours).
    # All other hours are catastrophic (0-37.5% WR) in old data.
    #
    # BASELINE MODE (2026-04-02): Hour filter DISABLED for 24h data collection.
    # All other filters (PUT only, signal_reasons, regime) stay active.
    # Tomorrow we compare WR-by-hour with the new filter stack to validate
    # whether the hour restriction adds value on top of the other filters.
    # To re-enable: uncomment the block below.
    # _PO_ALLOWED_HOURS_UTC = {14, 16}
    # _hour = feature.get("hour_utc")
    # if feature.get("venue") == "pocket_option" and _hour is not None:
    #     if int(_hour) not in _PO_ALLOWED_HOURS_UTC:
    #         signal_valid = False
    #         blockers.append("hour_not_in_profitable_window")

    # ── P-OP54j: Block CALL direction entirely for PO ─────────────────────
    # 65 trades: CALL WR = 20.7%, PUT WR = 38.9%. CALL is catastrophic.
    # The -0.06 penalty from P-OP54g wasn't enough — CALL still fires.
    # Hard block: no CALL trades on PO until data proves otherwise.
    _direction = family_signal.get("direction")
    if feature.get("venue") == "pocket_option" and _direction == "call":
        signal_valid = False
        blockers.append("call_direction_blocked")

    # ── P-OP54o: Candle data quality gate ─────────────────────────────────
    # Indicators computed on mostly-frozen candles produce artificial extremes
    # (e.g. RSI 86 from 1 real candle after 13 flat ones).  The existing
    # P-OP44 frozen guard only triggers when ALL last-10 candles are identical;
    # it misses the case where 1-2 live candles mask 80%+ frozen data.
    # Block PO trades when < 50% of recent candles have real price movement.
    _candle_alive = _safe_float(feature.get("candle_alive_ratio"), 1.0)
    if feature.get("venue") == "pocket_option" and _candle_alive < 0.50:
        signal_valid = False
        blockers.append("low_candle_quality")

    # ── P-OP54p: Contradiction ratio gate ─────────────────────────────────
    # When signal_reasons contain penalties/contradictions, the system itself
    # is flagging that conditions don't support the trade.  Block when
    # contradictions >= confirmations OR any contradiction with low score.
    _CONTRADICTION_KEYWORDS = {
        "contra_penalty", "contradicts", "penalty", "blocked",
    }
    _contra_count = sum(
        1 for r in reasons
        if any(kw in r for kw in _CONTRADICTION_KEYWORDS)
    )
    _confirm_count = len(_substantive_reasons) - _contra_count
    # Only block when contradictions genuinely outnumber confirmations.
    # The previous "weak_score < 0.40" branch killed ALL signals because
    # OTC scores never reach 0.40, and EMA/MACD contradictions are normal
    # noise in ranging OTC markets.  Removed to unblock the pipeline.
    if feature.get("venue") == "pocket_option" and _contra_count > 0:
        if _contra_count >= _confirm_count:
            signal_valid = False
            blockers.append("contradiction_majority")

    # ── P-OP54q: Minimum signal_score gate ────────────────────────────────
    # OTC scores naturally cluster 0.10–0.25 because setup_strength/3.5
    # compresses the scale.  The winning trade (ledger #1) had score 0.1625.
    # Floor at 0.12 filters truly empty signals (setup_strength < 0.42)
    # while allowing any signal with at least one mild indicator extreme.
    _MIN_SIGNAL_SCORE_PO = 0.12
    if feature.get("venue") == "pocket_option" and signal_score < _MIN_SIGNAL_SCORE_PO:
        signal_valid = False
        blockers.append(f"signal_score_below_minimum({signal_score:.3f}<{_MIN_SIGNAL_SCORE_PO})")

    # P3-06: Use per-strategy confidence threshold (set by adapt_strategy_parameters)
    # instead of global hardcoded value.  Falls back to 0.58 (BASE) if not set.
    # Lowered fallback from 0.50 to 0.42: with 2-indicator confluence + 1
    # soft EMA penalty, confidence lands ~0.45.  Threshold 0.42 permits
    # these while still requiring meaningful indicator support.
    
    # ── MINIMUM SIGNAL SCORE GATE ─────────────────────────────────────
    # Block trades with signal scores below 0.30 to prevent noise trading
    if signal_score < 0.30:
        signal_valid = False
        blockers.append(f"signal_score_below_minimum({signal_score:.3f}<0.30)")
    
    confidence_threshold = _safe_float(strategy.get("confidence_threshold"), 0.42)
    execution_ready = signal_valid and confidence >= confidence_threshold
    if not execution_ready and signal_valid:
        blockers.append("confidence_below_threshold")

    entry_price = feature.get("last") or feature.get("mid")
    return {
        "strategy_id": strategy.get("strategy_id"),
        "venue": strategy.get("venue"),
        "symbol": symbol,
        "timeframe": timeframe,
        "setup_variant": setup_variant,
        "asset_class": feature.get("asset_class"),
        "direction": family_signal.get("direction"),
        "signal_valid": signal_valid,
        "execution_ready": execution_ready,
        "confidence": round(_clamp(confidence, 0.0, 1.0), 4),
        "signal_score": round(signal_score, 4),
        "entry_price": entry_price,
        "market_regime": feature.get("market_regime"),
        "spread_pct": feature.get("spread_pct"),
        "payout_pct": feature.get("payout_pct"),
        "price_available": bool(feature.get("price_available")),
        "price_frozen": bool(feature.get("price_frozen")),  # P-OP44
        "data_age_seconds": feature.get("data_age_seconds"),
        "is_stale": bool(feature.get("is_stale")),
        "indicator_count": feature.get("indicator_count"),
        "indicator_access_ready": bool(feature.get("indicator_access_ready")),
        # P-OP9: Computed indicator values for diagnostics
        "rsi_14": feature.get("rsi_14"),
        "bb_pct_b": feature.get("bb_pct_b"),
        "stoch_k": feature.get("stoch_k"),
        "stoch_d": feature.get("stoch_d"),
        "macd_histogram": feature.get("macd_histogram"),
        "indicator_confluence": feature.get("indicator_confluence"),
        "bb_bandwidth": feature.get("bb_bandwidth"),           # adaptive duration regime indicator
        "adx": feature.get("adx"),                             # adaptive duration regime indicator
        "price_zscore": feature.get("price_zscore"),           # adaptive duration regime indicator
        "stream_symbol_match": feature.get("stream_symbol_match"),
        "visible_symbol": feature.get("visible_symbol"),
        "last_stream_symbol": feature.get("last_stream_symbol"),
        "available_timeframes": feature.get("available_timeframes", []),
        "reasons": sorted(set(reasons)),
        "blockers": sorted(set(blockers)),
        "feature_key": feature.get("key"),
        "feature_snapshot_utc": feature.get("captured_utc"),
        # P-OP22: session awareness fields
        "hour_utc": feature.get("hour_utc"),
        "session_name": _session_name,
        "session_quality": _session_quality,
        # P-OP23: adaptive signal thresholds used for this evaluation
        "adapted_thresholds": bool(strategy.get("adapted_signal_thresholds")),
        "signal_shift_pct": strategy.get("_signal_shift_pct"),
    }


def build_strategy_signal_snapshot(strategies: List[Dict[str, Any]], feature_snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
    snapshot = feature_snapshot or read_market_feature_snapshot()
    if not snapshot.get("items"):
        snapshot = build_market_feature_snapshot()
    feature_items = snapshot.get("items", []) or []
    by_strategy: List[Dict[str, Any]] = []
    all_signals: List[Dict[str, Any]] = []

    for strategy in strategies:
        strategy_signals = [
            _evaluate_strategy_feature(strategy, feature)
            for feature in feature_items
            if feature.get("venue") == strategy.get("venue")
        ]
        strategy_signals.sort(
            key=lambda item: (
                1 if item.get("execution_ready") else 0,
                item.get("confidence", 0.0),
                item.get("signal_score", 0.0),
            ),
            reverse=True,
        )
        best = strategy_signals[0] if strategy_signals else None
        by_strategy.append({
            "strategy_id": strategy.get("strategy_id"),
            "venue": strategy.get("venue"),
            "best_signal": best,
            "signal_candidates": strategy_signals,
            "execution_ready": bool(best and best.get("execution_ready")),
            "ready_signals_count": sum(1 for item in strategy_signals if item.get("execution_ready")),
        })
        all_signals.extend(strategy_signals)

    payload = {
        "schema_version": "strategy_signal_snapshot_v1",
        "generated_utc": _utc_now(),
        "feature_snapshot_path": str(ENGINE_PATH / "market_feature_snapshot_latest.json"),
        "strategies_count": len(strategies),
        "signals_count": len(all_signals),
        "items": all_signals,
        "by_strategy": by_strategy,
    }
    write_json(SIGNAL_SNAPSHOT_PATH, payload)
    return payload


def read_strategy_signal_snapshot() -> Dict[str, Any]:
    return read_json(SIGNAL_SNAPSHOT_PATH, {
        "schema_version": "strategy_signal_snapshot_v1",
        "generated_utc": None,
        "items": [],
        "by_strategy": [],
    })
