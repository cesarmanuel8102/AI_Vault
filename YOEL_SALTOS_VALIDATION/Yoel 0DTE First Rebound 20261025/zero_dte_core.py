from math import floor, isfinite


CAUSAL_QUALITY_FIELDS = (
    "relative_volume",
    "close_location",
    "body_strength",
    "range_atr",
    "level_rejection_atr",
    "friction",
)


def _finite_candidate_values(candidate, fields=CAUSAL_QUALITY_FIELDS):
    try:
        values = {field: float(candidate[field]) for field in fields}
    except (KeyError, TypeError, ValueError):
        return None
    return values if all(isfinite(value) for value in values.values()) else None


def causal_quality_score(candidate, weights):
    values = _finite_candidate_values(candidate, tuple(weights))
    if values is None:
        return float("-inf")
    return sum(values[field] * float(weights[field]) for field in weights)


def passes_causal_quality_gate(candidate, thresholds):
    values = _finite_candidate_values(candidate)
    if values is None or values["range_atr"] <= 0:
        return False
    return (
        values["relative_volume"] >= float(thresholds["relative_volume_min"])
        and values["close_location"] >= float(thresholds["close_location_min"])
        and values["body_strength"] >= float(thresholds["body_strength_min"])
        and float(thresholds["range_atr_min"]) <= values["range_atr"] <= float(thresholds["range_atr_max"])
        and values["level_rejection_atr"] >= float(thresholds["level_rejection_atr_min"])
        and values["friction"] <= float(thresholds["friction_max"])
    )


def rank_quality_candidates(candidates, weights):
    return sorted(
        candidates,
        key=lambda item: (-causal_quality_score(item, weights), item["ticker"]),
    )


def adaptive_allocation_fraction(remaining_candidates, remaining_slots):
    if remaining_candidates <= 0 or remaining_slots <= 0:
        return 0.0
    return 1.0 / min(int(remaining_candidates), int(remaining_slots))


def entry_before_cutoff(current_hour, cutoff_hour):
    return 0 <= current_hour < 24 and 0 < cutoff_hour <= 24 and current_hour < cutoff_hour


def rank_daily_candidates(candidates):
    return sorted(
        candidates,
        key=lambda item: (
            -(float(item["relative_volume"]) * float(item["close_location"])),
            float(item["friction"]),
            item["ticker"],
        ),
    )


def select_expiry(expiries, trade_date, target_dte):
    if target_dte < 0:
        raise ValueError("target_dte must be non-negative")
    valid = sorted({expiry for expiry in expiries if expiry >= trade_date})
    if target_dte == 0:
        return trade_date if trade_date in valid else None
    if not valid:
        return None
    return min(valid, key=lambda expiry: (abs((expiry - trade_date).days - target_dte), expiry))


def select_contract_by_delta(candidates, target_delta):
    if not 0 < target_delta < 1:
        raise ValueError("target_delta must be between zero and one")
    valid = [
        candidate for candidate in candidates
        if candidate.get("bid", 0) > 0
        and candidate.get("ask", 0) >= candidate.get("bid", 0)
        and candidate.get("delta") is not None
        and 0 < abs(float(candidate["delta"])) < 1
    ]
    if not valid:
        return None
    return min(
        valid,
        key=lambda candidate: (
            abs(abs(float(candidate["delta"])) - target_delta),
            float(candidate["ask"]) - float(candidate["bid"]),
        ),
    )


def select_strike(strikes, spot, direction, mode):
    values = sorted({float(strike) for strike in strikes})
    if mode not in {"atm", "otm"}:
        raise ValueError("mode must be atm or otm")
    if direction not in {-1, 1} or not values:
        return None
    if mode == "atm":
        return min(values, key=lambda strike: (abs(strike - spot), -direction * (spot - strike)))
    eligible = [strike for strike in values if strike > spot] if direction > 0 else [strike for strike in values if strike < spot]
    if not eligible:
        return None
    return min(eligible) if direction > 0 else max(eligible)


def contract_quantity(cash, equity, ask, capital_fraction=0.10):
    if ask <= 0 or cash <= 0 or equity <= 0:
        return 0
    if not 0 < capital_fraction <= 1:
        return 0
    return max(0, floor(min(float(cash), float(equity)) * float(capital_fraction) / (float(ask) * 100)))


def contract_quantity_for_allocation(cash, equity_base, ask, capital_fraction):
    if ask <= 0 or cash <= 0 or equity_base <= 0 or not 0 < capital_fraction <= 1:
        return 0
    budget = min(float(cash), float(equity_base) * float(capital_fraction))
    return max(0, floor(budget / (float(ask) * 100)))


def scale_out_quantity(total_quantity, fraction):
    quantity = int(total_quantity)
    if quantity < 2 or not 0 < fraction < 1:
        return 0
    return min(quantity - 1, max(1, floor(quantity * fraction)))


def friction_within_target(ask, take_profit, estimated_roundtrip_cost=0.033):
    return ask > 0 and take_profit > 0 and estimated_roundtrip_cost / ask <= take_profit


def trailing_profit_exit_due(current_return, peak_return, activation, distance):
    return (
        activation > 0
        and distance > 0
        and peak_return >= activation
        and current_return <= peak_return - distance
    )


def failure_to_launch_due(minutes_held, pnl, checkpoint_minutes, minimum_pnl):
    return checkpoint_minutes > 0 and minutes_held >= checkpoint_minutes and pnl < minimum_pnl


def adverse_failure_to_launch_due(minutes_held, pnl, directional_underlying_return, checkpoint_minutes, minimum_pnl):
    return (
        checkpoint_minutes > 0
        and minutes_held >= checkpoint_minutes
        and pnl <= minimum_pnl
        and directional_underlying_return < 0
    )


def quality_signal(direction, open_, high, low, close, relative_volume):
    del open_
    if direction not in {-1, 1} or relative_volume < 1.2 or high <= low:
        return False
    directional_close_location = (
        (close - low) / (high - low)
        if direction > 0
        else (high - close) / (high - low)
    )
    return directional_close_location >= 0.75


def checkpoint_snapshot(entry_price, bid, ask, underlying_entry, underlying_now, direction, level, invalidation):
    if entry_price <= 0 or bid <= 0 or underlying_entry <= 0 or direction not in {-1, 1}:
        return None
    return {
        "option_return": round(bid / entry_price - 1, 6),
        "underlying_return": round(direction * (underlying_now / underlying_entry - 1), 6),
        "level_margin": round(direction * (underlying_now - level) / underlying_entry, 6),
        "invalidation_margin": round(direction * (underlying_now - invalidation) / underlying_entry, 6),
        "spread_fraction": round(max(0.0, ask - bid) / entry_price, 6),
    }
