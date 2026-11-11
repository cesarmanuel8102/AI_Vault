"""Pure helpers for the post-shock operability study."""

from __future__ import annotations

import math
from typing import Iterable


def atr(
    highs: Iterable[float],
    lows: Iterable[float],
    closes: Iterable[float],
    period: int,
) -> list[float]:
    highs = list(highs)
    lows = list(lows)
    closes = list(closes)
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("OHLC lengths differ")
    if period < 1:
        raise ValueError("period must be positive")

    true_ranges: list[float] = []
    result: list[float] = []
    for index, (high, low) in enumerate(zip(highs, lows)):
        if index == 0:
            true_range = high - low
        else:
            previous_close = closes[index - 1]
            true_range = max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )
        true_ranges.append(float(true_range))
        if index + 1 < period:
            result.append(math.nan)
        else:
            result.append(sum(true_ranges[-period:]) / period)
    return result


def position_size(
    equity: float,
    entry_price: float,
    risk_per_share: float,
    risk_fraction: float = 0.005,
    max_notional_fraction: float = 0.10,
) -> int:
    if equity <= 0 or entry_price <= 0 or risk_per_share <= 0:
        return 0
    by_risk = int((equity * risk_fraction) // risk_per_share)
    by_notional = int((equity * max_notional_fraction) // entry_price)
    return max(0, min(by_risk, by_notional))


def choose_barrier_exit(
    stop_price: float,
    target_price: float,
    low: float,
    high: float,
    close: float,
    direction: int,
) -> tuple[float, str]:
    """Choose a daily-bar exit, assigning ambiguous bars to the stop."""
    if direction not in (-1, 1):
        raise ValueError("direction must be -1 or 1")
    stop_touched = low <= stop_price if direction == 1 else high >= stop_price
    target_touched = high >= target_price if direction == 1 else low <= target_price
    if stop_touched:
        return float(stop_price), "STOP"
    if target_touched:
        return float(target_price), "TARGET"
    return float(close), "HOLD"


def passes_go_gate(metrics: dict) -> bool:
    return bool(
        metrics.get("total_return", 0) > 0
        and metrics.get("cagr", 0) > 0
        and metrics.get("sharpe", 0) >= 0.75
        and metrics.get("profit_factor", 0) >= 1.15
        and metrics.get("max_drawdown", -1) >= -0.20
        and metrics.get("trades", 0) >= 100
        and metrics.get("positive_year_fraction", 0) >= 0.60
        and metrics.get("positive_symbol_fraction", 0) >= 0.55
        and metrics.get("neighbor_sign_consistent") is True
        and metrics.get("portfolio_contribution") is True
    )
