"""Frozen pure rules for the direct options operability study."""

from __future__ import annotations

from datetime import date
from math import floor
from typing import Iterable, Mapping, Sequence


def select_weekly_contract(
    contracts: Iterable[Mapping],
    trade_date: date,
    spot: float,
    right: str,
) -> Mapping | None:
    """Select the earliest 2-10 DTE contract at the nearest strict OTM strike."""
    normalized_right = right.lower()
    if normalized_right not in {"call", "put"}:
        raise ValueError("right must be call or put")
    eligible = []
    for contract in contracts:
        dte = (contract["expiry"] - trade_date).days
        strike = float(contract["strike"])
        contract_right = str(contract["right"]).lower()
        is_otm = strike > spot if normalized_right == "call" else strike < spot
        if contract_right == normalized_right and 2 <= dte <= 10 and is_otm:
            eligible.append(contract)
    if not eligible:
        return None
    if normalized_right == "call":
        return min(eligible, key=lambda item: (item["expiry"], float(item["strike"])))
    return min(eligible, key=lambda item: (item["expiry"], -float(item["strike"])))


def premium_quantity(equity: float, option_price: float, fraction: float = 0.02) -> int:
    if equity <= 0 or option_price <= 0 or fraction <= 0:
        return 0
    return max(0, floor((equity * fraction) / (option_price * 100)))


def reinforcement_quantity(
    original_quantity: int,
    original_price: float,
    current_price: float,
) -> int:
    if original_quantity <= 0 or original_price <= 0 or current_price <= 0:
        return 0
    original_outlay = original_quantity * original_price * 100
    return max(0, floor(original_outlay / (current_price * 100)))


def target_price(fills: Sequence[tuple[int, float]], target_fraction: float = 0.35) -> float:
    total_quantity = sum(quantity for quantity, _ in fills)
    if total_quantity <= 0:
        raise ValueError("fills must contain positive quantity")
    weighted_cost = sum(quantity * price for quantity, price in fills) / total_quantity
    return weighted_cost * (1 + target_fraction)


def passes_options_go_gate(metrics: Mapping) -> bool:
    return bool(
        metrics.get("total_return", 0) > 0
        and metrics.get("cagr", 0) > 0
        and metrics.get("sharpe", 0) >= 0.75
        and metrics.get("profit_factor", 0) >= 1.15
        and metrics.get("max_drawdown", -1) >= -0.20
        and metrics.get("trades", 0) >= 100
        and metrics.get("positive_year_fraction", 0) >= 0.60
        and metrics.get("positive_symbol_fraction", 0) >= 0.55
        and metrics.get("reinforcement_required_for_solvency") is False
    )
