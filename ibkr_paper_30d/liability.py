from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict


class LiabilityAssessment(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    status: str
    reason_codes: tuple[str, ...]
    structurally_bounded: bool
    analyzed_legs: int
    notes: tuple[str, ...] = ()


def _sign(action: str) -> Decimal:
    normalized = str(action or "").upper()
    if normalized in {"BUY", "LONG"}:
        return Decimal("1")
    if normalized in {"SELL", "SHORT"}:
        return Decimal("-1")
    raise ValueError("unknown leg action")


def _positive_decimal(value: Any, default: str) -> Decimal:
    try:
        parsed = Decimal(str(value if value not in (None, "") else default))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid numeric leg field") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError("numeric leg field must be finite and positive")
    return parsed


def assess_proposal_liability(proposal: dict[str, Any]) -> LiabilityAssessment:
    """
    Prove only whether the payoff is structurally bounded.

    This function deliberately does not choose a strategy or position size.
    The separate capital boundary checks the model's numeric maximum-loss
    estimate against current experimental equity.

    Equity-style underlyings (STK/OPT) are modeled on S >= 0.
    Futures-style underlyings (FUT/FOP) are conservatively modeled on an
    unbounded price axis in both directions.  Unsupported instrument families
    fail closed as UNPROVEN rather than being assigned a synthetic bound.
    """

    legs = list(proposal.get("legs") or [])
    if not legs:
        sec_type = str(
            proposal.get("security_type") or proposal.get("instrument") or ""
        ).upper()
        direction = str(proposal.get("direction") or "").upper()
        is_long = direction in {"LONG", "BUY"}

        if sec_type in {"STK", "BOND"} and is_long:
            return LiabilityAssessment(
                status="PASS",
                reason_codes=(),
                structurally_bounded=True,
                analyzed_legs=1,
                notes=("long_cash_instrument_loss_bounded_by_zero_floor",),
            )
        if sec_type in {"OPT", "FOP"} and is_long:
            return LiabilityAssessment(
                status="PASS",
                reason_codes=(),
                structurally_bounded=True,
                analyzed_legs=1,
                notes=("long_option_loss_bounded_by_premium",),
            )
        if sec_type == "STK" and not is_long:
            return LiabilityAssessment(
                status="BLOCK",
                reason_codes=("UNBOUNDED_SHORT_EQUITY",),
                structurally_bounded=False,
                analyzed_legs=1,
            )
        if sec_type in {"FUT", "CASH", "CFD"}:
            return LiabilityAssessment(
                status="BLOCK",
                reason_codes=("UNBOUNDED_OR_UNPROVEN_DIRECTIONAL_DERIVATIVE",),
                structurally_bounded=False,
                analyzed_legs=1,
            )
        if sec_type in {"OPT", "FOP"} and not is_long:
            return LiabilityAssessment(
                status="BLOCK",
                reason_codes=("SHORT_OPTION_REQUIRES_EXPLICIT_LEGS_FOR_BOUND_PROOF",),
                structurally_bounded=False,
                analyzed_legs=1,
            )
        return LiabilityAssessment(
            status="BLOCK",
            reason_codes=("LOSS_BOUND_UNPROVEN",),
            structurally_bounded=False,
            analyzed_legs=1,
        )

    # Analyze each underlying independently. Risk in one symbol may not be
    # assumed to offset an unrelated symbol.
    groups: dict[str, dict[str, Decimal | bool]] = defaultdict(
        lambda: {
            "plus_infinity_slope": Decimal("0"),
            "minus_infinity_slope": Decimal("0"),
            "futures_domain": False,
        }
    )
    reasons: list[str] = []

    for leg in legs:
        symbol = str(leg.get("symbol") or "").upper().strip()
        sec_type = str(leg.get("security_type") or "").upper().strip()
        if not symbol:
            reasons.append("LEG_SYMBOL_REQUIRED")
            continue
        try:
            sign = _sign(str(leg.get("action") or ""))
            ratio = _positive_decimal(leg.get("ratio"), "1")
        except ValueError:
            reasons.append("INVALID_LEG_ACTION_OR_RATIO")
            continue

        if sec_type == "STK":
            multiplier = _positive_decimal(leg.get("multiplier"), "1")
            groups[symbol]["plus_infinity_slope"] += sign * ratio * multiplier
            continue

        if sec_type == "FUT":
            multiplier = _positive_decimal(leg.get("multiplier"), "1")
            groups[symbol]["futures_domain"] = True
            slope = sign * ratio * multiplier
            groups[symbol]["plus_infinity_slope"] += slope
            groups[symbol]["minus_infinity_slope"] += slope
            continue

        if sec_type not in {"OPT", "FOP"}:
            reasons.append(f"UNSUPPORTED_BOUND_PROOF_SECURITY_TYPE:{sec_type or 'UNKNOWN'}")
            continue

        right = str(leg.get("right") or "").upper()
        if right not in {"C", "P", "CALL", "PUT"}:
            reasons.append("OPTION_RIGHT_REQUIRED")
            continue
        try:
            _positive_decimal(leg.get("strike"), "0")
            multiplier = _positive_decimal(leg.get("multiplier"), "100")
        except ValueError:
            reasons.append("INVALID_OPTION_STRIKE_OR_MULTIPLIER")
            continue

        if sec_type == "FOP":
            groups[symbol]["futures_domain"] = True

        magnitude = sign * ratio * multiplier
        if right in {"C", "CALL"}:
            # call payoff ~ sign * multiplier * S as S -> +infinity
            groups[symbol]["plus_infinity_slope"] += magnitude
        else:
            # put payoff ~ sign * multiplier * (K-S) as S -> -infinity
            groups[symbol]["minus_infinity_slope"] += -magnitude

    if reasons:
        return LiabilityAssessment(
            status="BLOCK",
            reason_codes=tuple(dict.fromkeys(reasons)),
            structurally_bounded=False,
            analyzed_legs=len(legs),
        )

    for symbol, slopes in groups.items():
        plus = Decimal(slopes["plus_infinity_slope"])
        if plus < 0:
            reasons.append(f"UNBOUNDED_UPSIDE_PRICE_LOSS:{symbol}")
        if bool(slopes["futures_domain"]):
            minus = Decimal(slopes["minus_infinity_slope"])
            # As S -> -infinity, a positive coefficient produces -infinity PnL.
            if minus > 0:
                reasons.append(f"UNBOUNDED_DOWNSIDE_PRICE_LOSS:{symbol}")

    if reasons:
        return LiabilityAssessment(
            status="BLOCK",
            reason_codes=tuple(dict.fromkeys(reasons)),
            structurally_bounded=False,
            analyzed_legs=len(legs),
        )

    return LiabilityAssessment(
        status="PASS",
        reason_codes=(),
        structurally_bounded=True,
        analyzed_legs=len(legs),
        notes=("asymptotic_payoff_has_no_unbounded_loss_direction",),
    )
