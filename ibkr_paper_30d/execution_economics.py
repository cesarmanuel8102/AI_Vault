"""Deterministic round-trip execution cost and break-even information per sleeve.

Information only: it never authorizes, sizes or blocks a trade. Live quotes and
IBKR what-if remain authoritative for any concrete order.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

PRECISION = Decimal("0.000001")
_STOCK_MIN_COMMISSION = Decimal("1.00")
_CRYPTO_MIN_COMMISSION = Decimal("1.75")
_CRYPTO_COMMISSION_RATE = Decimal("0.0018")
_OPTION_PER_CONTRACT = Decimal("0.65")
_OPTION_MIN_COMMISSION = Decimal("1.00")
_SEC_FEE_RATE = Decimal("0.0000278")
_HALF_SPREAD_BPS = {"STK": Decimal("5"), "CRYPTO": Decimal("5")}
_SLIPPAGE_BPS_PER_SIDE = Decimal("2")
_SPREAD_SOURCE = "CONSERVATIVE_ASSUMPTION_REPLACE_WITH_LIVE_QUOTE"


def _decimal(value: Any) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() and parsed > 0 else None


def _q(value: Decimal) -> str:
    return str(value.quantize(PRECISION))


def _notional_entry(
    family: str,
    notional: Decimal,
    entry_commission: Decimal,
    exit_commission: Decimal,
    fees: Decimal,
    *,
    as_of_utc: str,
    commission_basis: str,
    observed: Mapping[str, Any] | None,
) -> dict[str, Any]:
    side_bps = _HALF_SPREAD_BPS[family]
    spread = (notional * Decimal("2") * side_bps / Decimal("10000")).quantize(PRECISION)
    slippage = (notional * Decimal("2") * _SLIPPAGE_BPS_PER_SIDE / Decimal("10000")).quantize(PRECISION)
    fees = fees.quantize(PRECISION)
    commissions = entry_commission + exit_commission
    total = commissions + spread + slippage + fees
    entry = {
        "unit": "FULL_SLEEVE_NOTIONAL",
        "notional_usd": str(notional),
        "entry_commission_usd": str(entry_commission),
        "exit_commission_usd": str(exit_commission),
        "round_trip_commission_usd": str(commissions),
        "round_trip_commission_pct": _q(commissions / notional),
        "spread_cost_usd": _q(spread),
        "half_spread_bps_assumed": str(side_bps),
        "slippage_cost_usd": _q(slippage),
        "slippage_bps_per_side_assumed": str(_SLIPPAGE_BPS_PER_SIDE),
        "fees_usd": _q(fees),
        "round_trip_cost_usd": str(total),
        "round_trip_cost_pct": _q(total / notional),
        "break_even_move_pct": _q(total / notional),
        "commission_basis": commission_basis,
        "commission_source": "DETERMINISTIC_BROKER_SCHEDULE",
        "spread_source": _SPREAD_SOURCE,
        "epistemic_status": "DETERMINISTIC_CALCULATION",
        "as_of_utc": as_of_utc,
        "note": (
            "Fixed minimum commissions dominate small orders; smaller positions need a "
            "proportionally larger move. A concrete candidate's live bid/ask and IBKR "
            "what-if supersede these assumptions."
        ),
    }
    if observed:
        entry.update(
            {
                "observed_commission_per_order_usd": str(observed.get("median_commission_per_order_usd")),
                "observed_commission_fills": observed.get("fills"),
                "observed_commission_last_fill_utc": observed.get("last_fill_utc"),
                "observed_commission_source": "HISTORICAL_ESTIMATE_FROM_EXECUTED_FILLS",
            }
        )
    return entry


def _per_contract_entry(legs: int, *, as_of_utc: str) -> dict[str, Any]:
    per_order = max(_OPTION_MIN_COMMISSION, _OPTION_PER_CONTRACT * legs)
    round_trip = per_order * 2
    return {
        "unit": "PER_CONTRACT",
        "legs": legs,
        "multiplier": "100",
        "entry_commission_usd": str(per_order),
        "exit_commission_usd": str(per_order),
        "round_trip_commission_usd": str(round_trip),
        "break_even_premium_move_per_share_usd": str(
            (round_trip / Decimal("100")).quantize(Decimal("0.0001")).normalize()
        ),
        "spread_cost_usd": None,
        "slippage_cost_usd": None,
        "fees_usd": "0",
        "commission_basis": (
            f"max({_OPTION_MIN_COMMISSION}, {_OPTION_PER_CONTRACT} x contracts x legs) per order"
        ),
        "commission_source": "DETERMINISTIC_BROKER_SCHEDULE",
        "spread_source": _SPREAD_SOURCE,
        "epistemic_status": "DETERMINISTIC_CALCULATION",
        "as_of_utc": as_of_utc,
        "note": (
            "Option bid/ask spreads are often the largest cost; add the live quoted spread "
            "per leg to the premium move required to break even."
        ),
    }


def execution_break_even_economics(
    sleeve_capital_usd: Mapping[str, Any],
    *,
    observed_commissions: Mapping[str, Mapping[str, Any]],
    as_of_utc: str,
) -> dict[str, Any]:
    """Return per-sleeve, per-instrument-family round-trip cost and break-even moves."""

    result: dict[str, Any] = {}
    for sleeve in ("REGULAR_SLEEVE", "CONTINUOUS_SLEEVE"):
        notional = _decimal(sleeve_capital_usd.get(sleeve))
        if notional is None:
            result[sleeve] = {"status": "UNAVAILABLE", "reason": "SLEEVE_EQUITY_UNAVAILABLE"}
            continue
        observed = observed_commissions.get(sleeve) or None
        observed_value = _decimal((observed or {}).get("median_commission_per_order_usd"))
        if sleeve == "REGULAR_SLEEVE":
            per_order = observed_value or _STOCK_MIN_COMMISSION
            result[sleeve] = {
                "STK": _notional_entry(
                    "STK", notional, per_order, per_order, notional * _SEC_FEE_RATE,
                    as_of_utc=as_of_utc,
                    commission_basis=(
                        "observed median per order" if observed_value
                        else "IBKR fixed USD 1.00 minimum per order"
                    ) + "; SEC fee estimate on the sell side",
                    observed=observed,
                ),
                "OPT": _per_contract_entry(1, as_of_utc=as_of_utc),
                "BAG": _per_contract_entry(2, as_of_utc=as_of_utc),
            }
        else:
            schedule = max(_CRYPTO_MIN_COMMISSION, (notional * _CRYPTO_COMMISSION_RATE).quantize(Decimal("0.01")))
            result[sleeve] = {
                "CRYPTO": _notional_entry(
                    "CRYPTO", notional, schedule, schedule, Decimal("0"),
                    as_of_utc=as_of_utc,
                    commission_basis="PAXOS max(USD 1.75, 0.18% of order value) per order",
                    observed=observed,
                )
            }
    return result
