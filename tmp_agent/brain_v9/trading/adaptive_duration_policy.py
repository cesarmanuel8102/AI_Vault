"""
Adaptive Duration Policy for PocketOption
==========================================
Selects trade duration based on volatility regime using
bb_bandwidth + adx, with price_zscore exhaustion filter.

Regimes:
  - low_energy:            BB < 1.5 and ADX < 18  -> SKIP
  - high_vol_directional:  BB > 3.0 and ADX >= 25 -> 60s-120s
  - high_vol_weak_trend:   BB > 3.0 and ADX < 25  -> 120s-180s or skip
  - normal:                1.5 <= BB <= 3.0        -> 180s-300s

Exhaustion filter:
  - CALL with zscore >= 2.2 -> SKIP
  - PUT  with zscore <= -2.2 -> SKIP

Integration:
  from adaptive_duration_policy import (
      AdaptiveDurationConfig,
      build_trade_decision_with_duration,
  )
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple


# ============================================================
# Config
# ============================================================

@dataclass
class AdaptiveDurationConfig:
    # -- Volatility thresholds --
    bb_low: float = 1.5
    bb_high: float = 3.0
    adx_low: float = 18.0
    adx_high: float = 25.0

    # -- Target durations (seconds) --
    # P-OP54b: Data from 64 trades shows 300s MASSIVELY outperforms shorter:
    #   reversion_probe: 300s=60% WR vs 60s=0% WR
    #   v3_auto: 300s=12.5% vs 60s=100% (1 trade)
    # Moved all targets towards 300s. Even "short" targets now 180s min.
    target_short_seconds: int = 180
    target_medium_seconds: int = 300
    target_normal_seconds: int = 300

    # -- Exhaustion filter --
    zscore_exhaustion_threshold: float = 2.2

    # -- ATR optional confirmation --
    use_atr_confirmation: bool = False
    atr_low_pct: float = 0.15
    atr_high_pct: float = 0.50

    # -- Fallback --
    allow_fallback_to_nearest: bool = True

    # -- Low volatility policy: "skip" or "normal" --
    low_volatility_policy: str = "skip"

    # -- High BB + low ADX policy: "skip", "short", or "medium" --
    high_bb_low_adx_policy: str = "medium"

    # -- Tie-breaking --
    prefer_shorter_on_short_target: bool = True
    prefer_longer_on_medium_target: bool = True


@dataclass
class AdaptiveDurationDecision:
    decision: str                           # "trade" | "skip"
    selected_duration_label: Optional[str]
    selected_duration_seconds: Optional[int]
    regime: str
    reason: str
    diagnostics: Dict[str, Any]


# ============================================================
# Duration parsing utilities
# ============================================================

_DURATION_RE = re.compile(r"^\s*(\d+)\s*([smhSMH])\s*$")
# Matches HH:MM:SS or MM:SS formats (e.g. "00:05:00", "05:00")
_HMS_RE = re.compile(r"^\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\s*$")
# Matches unit-prefixed labels like "M5", "H1", "S30"
_PREFIX_UNIT_RE = re.compile(r"^\s*([smhSMH])(\d+)\s*$")
# Matches "current_expiry_seconds:NNN" from PO bridge full field
_EXPIRY_SECS_RE = re.compile(r"current_expiry_seconds[:\s]*(\d+)", re.IGNORECASE)


def parse_duration_label_to_seconds(label: str) -> Optional[int]:
    """Parse a duration label to seconds.

    Supported formats:
      - "60s", "1m", "5m", "1h"          (number + unit suffix)
      - "M5", "H1", "S30"                (unit prefix + number)
      - "00:05:00", "05:00"              (HH:MM:SS or MM:SS)
      - "current_expiry_seconds:60"      (PO bridge full field)
    """
    if not isinstance(label, str):
        return None
    raw = label.strip()
    if not raw:
        return None

    # 1) Standard: "5m", "60s", "1h"
    m = _DURATION_RE.match(raw)
    if m:
        value = int(m.group(1))
        unit = m.group(2).lower()
        if unit == "s":
            return value
        if unit == "m":
            return value * 60
        if unit == "h":
            return value * 3600

    # 2) Prefix-unit: "M5" -> 5 minutes, "H1" -> 1 hour, "S30" -> 30 seconds
    m = _PREFIX_UNIT_RE.match(raw)
    if m:
        unit = m.group(1).lower()
        value = int(m.group(2))
        if unit == "s":
            return value
        if unit == "m":
            return value * 60
        if unit == "h":
            return value * 3600

    # 3) HH:MM:SS or MM:SS: "00:05:00" -> 300, "05:00" -> 300
    m = _HMS_RE.match(raw)
    if m:
        hours = int(m.group(1)) if m.group(1) else 0
        minutes = int(m.group(2))
        seconds = int(m.group(3))
        total = hours * 3600 + minutes * 60 + seconds
        if total > 0:
            return total

    # 4) PO bridge "current_expiry_seconds:60"
    m = _EXPIRY_SECS_RE.search(raw)
    if m:
        return int(m.group(1))

    return None


def normalize_duration_candidates(duration_candidates: List[str]) -> List[Tuple[str, int]]:
    normalized: List[Tuple[str, int]] = []
    seen_seconds = set()
    for raw in duration_candidates or []:
        secs = parse_duration_label_to_seconds(raw)
        if secs is None or secs <= 0:
            continue
        if secs in seen_seconds:
            continue
        seen_seconds.add(secs)
        normalized.append((raw.strip(), secs))
    normalized.sort(key=lambda x: x[1])
    return normalized


def choose_nearest_duration(
    candidates: List[Tuple[str, int]],
    target_seconds: int,
    prefer_shorter: bool = False,
    prefer_longer: bool = False,
) -> Optional[Tuple[str, int]]:
    if not candidates:
        return None
    best = None
    best_key = None
    for label, secs in candidates:
        distance = abs(secs - target_seconds)
        if prefer_shorter:
            tie_break = secs
        elif prefer_longer:
            tie_break = -secs
        else:
            tie_break = abs(secs - target_seconds)
        key = (distance, tie_break)
        if best is None or key < best_key:
            best = (label, secs)
            best_key = key
    return best


# ============================================================
# Exhaustion filter
# ============================================================

def is_exhausted_for_signal(
    signal_side: Optional[str],
    price_zscore: Optional[float],
    threshold: float,
) -> bool:
    if signal_side is None or price_zscore is None or not math.isfinite(price_zscore):
        return False
    s = signal_side.strip().lower()
    if s == "call":
        return price_zscore >= threshold
    if s == "put":
        return price_zscore <= -threshold
    return False


# ============================================================
# Regime classification
# ============================================================

def classify_regime(
    bb_bandwidth: Optional[float],
    adx: Optional[float],
    atr_pct: Optional[float],
    cfg: AdaptiveDurationConfig,
) -> str:
    """
    Returns one of:
      low_energy, high_vol_directional, high_vol_weak_trend, normal, unknown
    """
    if bb_bandwidth is None or adx is None:
        return "unknown"
    if not math.isfinite(bb_bandwidth) or not math.isfinite(adx):
        return "unknown"

    # Low energy: compression + weak ADX
    if bb_bandwidth < cfg.bb_low and adx < cfg.adx_low:
        return "low_energy"

    # High vol directional
    if bb_bandwidth > cfg.bb_high and adx >= cfg.adx_high:
        if cfg.use_atr_confirmation and atr_pct is not None and math.isfinite(atr_pct):
            if atr_pct >= cfg.atr_high_pct:
                return "high_vol_directional"
            return "normal"
        return "high_vol_directional"

    # High amplitude but weak trend
    if bb_bandwidth > cfg.bb_high and adx < cfg.adx_high:
        return "high_vol_weak_trend"

    return "normal"


# ============================================================
# Main selection logic
# ============================================================

def select_adaptive_duration(
    features: Dict[str, Any],
    duration_candidates: List[str],
    signal_side: Optional[str] = None,
    cfg: Optional[AdaptiveDurationConfig] = None,
) -> AdaptiveDurationDecision:
    if cfg is None:
        cfg = AdaptiveDurationConfig()

    normalized_candidates = normalize_duration_candidates(duration_candidates)

    bb_bandwidth = _to_float_or_none(features.get("bb_bandwidth"))
    adx = _to_float_or_none(features.get("adx"))
    price_zscore = _to_float_or_none(features.get("price_zscore"))
    atr_pct = _to_float_or_none(features.get("atr_pct"))

    diagnostics: Dict[str, Any] = {
        "bb_bandwidth": bb_bandwidth,
        "adx": adx,
        "price_zscore": price_zscore,
        "atr_pct": atr_pct,
        "signal_side": signal_side,
        "duration_candidates_raw": duration_candidates,
        "duration_candidates_normalized": [
            {"label": x[0], "seconds": x[1]} for x in normalized_candidates
        ],
    }

    # 1) No valid candidates
    if not normalized_candidates:
        return AdaptiveDurationDecision(
            decision="skip",
            selected_duration_label=None,
            selected_duration_seconds=None,
            regime="invalid",
            reason="no_valid_duration_candidates",
            diagnostics=diagnostics,
        )

    # 2) Exhaustion filter
    if is_exhausted_for_signal(signal_side, price_zscore, cfg.zscore_exhaustion_threshold):
        diagnostics["skip_due_to_exhaustion"] = True
        return AdaptiveDurationDecision(
            decision="skip",
            selected_duration_label=None,
            selected_duration_seconds=None,
            regime="exhausted",
            reason="price_zscore_exhaustion_filter",
            diagnostics=diagnostics,
        )

    # 3) Classify regime
    regime = classify_regime(bb_bandwidth, adx, atr_pct, cfg)
    diagnostics["regime"] = regime

    # 4) Route by regime
    if regime == "low_energy":
        if cfg.low_volatility_policy == "skip":
            return AdaptiveDurationDecision(
                decision="skip",
                selected_duration_label=None,
                selected_duration_seconds=None,
                regime=regime,
                reason="low_energy_skip",
                diagnostics=diagnostics,
            )
        target_seconds = cfg.target_normal_seconds
        chosen = choose_nearest_duration(
            normalized_candidates, target_seconds,
            prefer_longer=cfg.prefer_longer_on_medium_target,
        )
        if chosen is None:
            return _skip(regime, "low_energy_no_duration_found", diagnostics)
        return _trade(chosen, regime, "low_energy_fallback_to_normal_duration", diagnostics)

    if regime == "high_vol_directional":
        target_seconds = cfg.target_short_seconds
        chosen = choose_nearest_duration(
            normalized_candidates, target_seconds,
            prefer_shorter=cfg.prefer_shorter_on_short_target,
        )
        if chosen is None:
            return _skip(regime, "high_vol_directional_no_duration_found", diagnostics)
        return _trade(chosen, regime, "high_vol_directional_short_duration", diagnostics)

    if regime == "high_vol_weak_trend":
        policy = cfg.high_bb_low_adx_policy
        if policy == "skip":
            return _skip(regime, "high_bb_low_adx_skip", diagnostics)
        if policy == "short":
            target_seconds = cfg.target_short_seconds
            prefer_shorter = cfg.prefer_shorter_on_short_target
        else:  # "medium" (default)
            target_seconds = cfg.target_medium_seconds
            prefer_shorter = False
        chosen = choose_nearest_duration(
            normalized_candidates, target_seconds,
            prefer_shorter=prefer_shorter,
            prefer_longer=(not prefer_shorter and cfg.prefer_longer_on_medium_target),
        )
        if chosen is None:
            return _skip(regime, f"high_bb_low_adx_{policy}_no_duration_found", diagnostics)
        return _trade(chosen, regime, f"high_bb_low_adx_{policy}_policy", diagnostics)

    if regime == "normal":
        target_seconds = cfg.target_medium_seconds
        chosen = choose_nearest_duration(
            normalized_candidates, target_seconds,
            prefer_longer=cfg.prefer_longer_on_medium_target,
        )
        if chosen is None:
            return _skip(regime, "normal_no_duration_found", diagnostics)
        return _trade(chosen, regime, "normal_medium_duration", diagnostics)

    # unknown - fallback to normal
    chosen = choose_nearest_duration(
        normalized_candidates, cfg.target_normal_seconds,
        prefer_longer=cfg.prefer_longer_on_medium_target,
    )
    if chosen is None:
        return _skip("unknown", "unknown_regime_no_duration_found", diagnostics)
    return _trade(chosen, "unknown", "unknown_regime_fallback_normal_duration", diagnostics)


# ============================================================
# ATR from OHLC (optional, Phase 2)
# ============================================================

def compute_atr_pct_from_ohlc(
    candles: List[Dict[str, Any]],
    period: int = 14,
) -> Optional[float]:
    """Compute ATR as percentage of last close from OHLC candles."""
    if not candles or len(candles) < period + 1:
        return None
    highs, lows, closes = [], [], []
    for c in candles:
        try:
            highs.append(float(c["high"]))
            lows.append(float(c["low"]))
            closes.append(float(c["close"]))
        except Exception:
            return None
    trs = []
    for i in range(1, len(candles)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return None
    atr = sum(trs[-period:]) / period
    last_close = closes[-1]
    if last_close == 0:
        return None
    return (atr / last_close) * 100.0


# ============================================================
# Integration helper
# ============================================================

def build_trade_decision_with_duration(
    features: Dict[str, Any],
    duration_candidates: List[str],
    signal_side: Optional[str],
    cfg: Optional[AdaptiveDurationConfig] = None,
) -> Dict[str, Any]:
    """Helper for pipeline integration. Returns serializable dict."""
    decision = select_adaptive_duration(
        features=features,
        duration_candidates=duration_candidates,
        signal_side=signal_side,
        cfg=cfg,
    )
    return {
        "decision": decision.decision,
        "selected_duration_label": decision.selected_duration_label,
        "selected_duration_seconds": decision.selected_duration_seconds,
        "regime": decision.regime,
        "reason": decision.reason,
        "diagnostics": decision.diagnostics,
    }


# ============================================================
# Internal helpers
# ============================================================

def _to_float_or_none(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except Exception:
        return None


def _skip(regime: str, reason: str, diagnostics: Dict) -> AdaptiveDurationDecision:
    return AdaptiveDurationDecision(
        decision="skip",
        selected_duration_label=None,
        selected_duration_seconds=None,
        regime=regime,
        reason=reason,
        diagnostics=diagnostics,
    )


def _trade(chosen: Tuple[str, int], regime: str, reason: str, diagnostics: Dict) -> AdaptiveDurationDecision:
    return AdaptiveDurationDecision(
        decision="trade",
        selected_duration_label=chosen[0],
        selected_duration_seconds=chosen[1],
        regime=regime,
        reason=reason,
        diagnostics=diagnostics,
    )


# ============================================================
# Smoke test
# ============================================================

if __name__ == "__main__":
    cfg = AdaptiveDurationConfig(
        bb_low=1.5,
        bb_high=3.0,
        adx_low=18.0,
        adx_high=25.0,
        target_short_seconds=60,
        target_medium_seconds=180,
        target_normal_seconds=300,
        low_volatility_policy="skip",
        high_bb_low_adx_policy="medium",
        use_atr_confirmation=False,
    )

    cases = [
        {
            "name": "alta_vol_direccional_call",
            "features": {"bb_bandwidth": 3.8, "adx": 29.0, "price_zscore": 0.8},
            "duration_candidates": ["30s", "1m", "2m", "5m"],
            "signal_side": "call",
        },
        {
            "name": "baja_energia_skip",
            "features": {"bb_bandwidth": 1.1, "adx": 14.0, "price_zscore": 0.2},
            "duration_candidates": ["1m", "5m"],
            "signal_side": "call",
        },
        {
            "name": "normal_medium",
            "features": {"bb_bandwidth": 2.1, "adx": 21.0, "price_zscore": -0.4},
            "duration_candidates": ["1m", "3m", "5m"],
            "signal_side": "put",
        },
        {
            "name": "call_agotado_skip",
            "features": {"bb_bandwidth": 3.4, "adx": 27.0, "price_zscore": 2.5},
            "duration_candidates": ["1m", "2m", "5m"],
            "signal_side": "call",
        },
        {
            "name": "high_bb_low_adx_medium",
            "features": {"bb_bandwidth": 3.7, "adx": 17.0, "price_zscore": 0.4},
            "duration_candidates": ["30s", "1m", "3m", "5m"],
            "signal_side": "call",
        },
    ]

    for case in cases:
        result = build_trade_decision_with_duration(
            features=case["features"],
            duration_candidates=case["duration_candidates"],
            signal_side=case["signal_side"],
            cfg=cfg,
        )
        print("=" * 70)
        print(f"  {case['name']}")
        print(f"  decision: {result['decision']}")
        print(f"  duration: {result['selected_duration_label']} ({result['selected_duration_seconds']}s)")
        print(f"  regime:   {result['regime']}")
        print(f"  reason:   {result['reason']}")
