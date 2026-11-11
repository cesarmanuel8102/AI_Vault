from first_rebound_core import select_first_rebound


def base_snapshot(**overrides):
    snapshot = {
        "direction": 1,
        "daily_direction": 1,
        "open": 105.0,
        "high": 107.0,
        "low": 99.5,
        "close": 106.0,
        "previous_low": 102.0,
        "previous_high": 108.0,
        "atr": 4.0,
        "bb_mid": 104.0,
        "bb_mid_previous": 103.0,
        "bb_width": 10.0,
        "bb_width_previous": 10.0,
        "relative_volume": 1.0,
        "levels": {20: 103.0, 40: 101.0, 100: 100.0, 200: 95.0},
        "used_levels": set(),
    }
    snapshot.update(overrides)
    return snapshot


def test_bullish_bar_chooses_strongest_touched_average():
    signal = select_first_rebound(**base_snapshot())
    assert signal == {"direction": 1, "period": 100, "level": 100.0}


def test_used_average_cannot_signal_twice_in_regime():
    signal = select_first_rebound(**base_snapshot(used_levels={100}))
    assert signal == {"direction": 1, "period": 40, "level": 101.0}


def test_daily_disagreement_blocks_signal():
    assert select_first_rebound(**base_snapshot(daily_direction=-1)) is None


def test_contracting_bollinger_structure_blocks_signal():
    assert select_first_rebound(**base_snapshot(bb_width=7.9)) is None


def test_bearish_first_touch_is_symmetric():
    signal = select_first_rebound(**base_snapshot(
        direction=-1,
        daily_direction=-1,
        open=95.0,
        high=100.5,
        low=93.0,
        close=94.0,
        previous_low=92.0,
        previous_high=98.0,
        bb_mid=96.0,
        bb_mid_previous=97.0,
        levels={20: 97.0, 40: 99.0, 100: 100.0, 200: 105.0},
    ))
    assert signal == {"direction": -1, "period": 100, "level": 100.0}
