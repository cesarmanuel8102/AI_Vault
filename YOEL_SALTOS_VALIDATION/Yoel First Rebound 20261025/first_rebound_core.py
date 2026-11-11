def select_first_rebound(*, direction, daily_direction, open, high, low, close,
                         previous_low, previous_high, atr, bb_mid,
                         bb_mid_previous, bb_width, bb_width_previous,
                         relative_volume, levels, used_levels):
    if direction not in (-1, 1) or daily_direction != direction or atr <= 0:
        return None
    if relative_volume < 0.8 or bb_width_previous <= 0 or bb_width < 0.8 * bb_width_previous:
        return None
    if direction == 1:
        confirmed = close > open and close > bb_mid and bb_mid > bb_mid_previous
    else:
        confirmed = close < open and close < bb_mid and bb_mid < bb_mid_previous
    if not confirmed:
        return None
    candidates = []
    for period, level in levels.items():
        if period in used_levels:
            continue
        if direction == 1:
            fresh = previous_low >= level + 0.25 * atr
            touched = low <= level and close > level
        else:
            fresh = previous_high <= level - 0.25 * atr
            touched = high >= level and close < level
        if fresh and touched:
            candidates.append((period, float(level)))
    if not candidates:
        return None
    period, level = max(candidates, key=lambda item: item[0])
    return {"direction": direction, "period": period, "level": level}

