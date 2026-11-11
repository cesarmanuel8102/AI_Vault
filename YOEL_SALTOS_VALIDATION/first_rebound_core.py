"""Pure, frozen first-rebound acceptance rules."""

from __future__ import annotations


def select_first_rebound(
    *,
    direction: int,
    daily_direction: int,
    open: float,
    high: float,
    low: float,
    close: float,
    previous_low: float,
    previous_high: float,
    atr: float,
    bb_mid: float,
    bb_mid_previous: float,
    bb_width: float,
    bb_width_previous: float,
    relative_volume: float,
    levels: dict[int, float],
    used_levels: set[int],
) -> dict | None:
    if direction not in (-1, 1) or daily_direction != direction or atr <= 0:
        return None
    if relative_volume < 0.8 or bb_width_previous <= 0:
        return None
    if bb_width < 0.8 * bb_width_previous:
        return None

    if direction == 1:
        confirmation = close > open and close > bb_mid and bb_mid > bb_mid_previous
    else:
        confirmation = close < open and close < bb_mid and bb_mid < bb_mid_previous
    if not confirmation:
        return None

    candidates = []
    for period, level in levels.items():
        if period in used_levels:
            continue
        if direction == 1:
            approached_fresh = previous_low >= level + 0.25 * atr
            touched_and_rejected = low <= level and close > level
        else:
            approached_fresh = previous_high <= level - 0.25 * atr
            touched_and_rejected = high >= level and close < level
        if approached_fresh and touched_and_rejected:
            candidates.append((period, float(level)))
    if not candidates:
        return None
    period, level = max(candidates, key=lambda item: item[0])
    return {"direction": direction, "period": period, "level": level}
