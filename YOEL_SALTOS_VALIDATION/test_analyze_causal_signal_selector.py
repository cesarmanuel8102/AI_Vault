from analyze_causal_signal_selector import pair_trace_records, select_broadest_viable_profile


def _records(year, ticker, exit_return, range_atr):
    entry_time = f"{year}-01-03T10:31:00"
    return [
        {
            "type": "entry",
            "ticker": ticker,
            "time": entry_time,
            "entry_price": 1.0,
            "estimated_roundtrip_friction": 0.02,
            "range_atr": range_atr,
        },
        {
            "type": "exit",
            "ticker": ticker,
            "entry_time": entry_time,
            "exit_price": 1.0 + exit_return,
            "reason": "TARGET" if exit_return > 0 else "FAILURE_EXIT",
        },
    ]


def test_pair_trace_records_uses_only_matched_entry_exit_and_subtracts_friction():
    records = _records(2022, "A", 0.10, 1.2)
    records.append({"type": "entry", "ticker": "B", "time": "2022-01-04T10:31:00"})

    assert pair_trace_records(records) == [
        {
            "year": 2022,
            "ticker": "A",
            "range_atr": 1.2,
            "net_return": 0.08,
            "reason": "TARGET",
        }
    ]


def test_selector_uses_training_and_confirmation_and_chooses_broadest_viable():
    records = []
    for year in (2022, 2023):
        for index in range(4):
            records += _records(year, f"T{year}{index}", 0.10, 1.4)
        records += _records(year, f"L{year}", -0.30, 1.7)
    for index in range(4):
        records += _records(2024, f"C{index}", 0.10, 1.4)
    records += _records(2024, "CL", -0.30, 1.7)

    result = select_broadest_viable_profile(
        pair_trace_records(records),
        range_atr_maxima=(1.25, 1.5, 1.75),
        minimum_training_trades=8,
        minimum_confirmation_trades=4,
    )

    assert result["selected"]["range_atr_max"] == 1.5
    assert result["selected"]["training"]["profit_factor"] > 1
    assert result["selected"]["confirmation"]["profit_factor"] > 1
    assert len(result["tested_profiles"]) == 3


def test_selector_returns_no_profile_when_confirmation_is_not_positive():
    records = []
    for year in (2022, 2023):
        for index in range(4):
            records += _records(year, f"T{year}{index}", 0.10, 1.4)
    for index in range(4):
        records += _records(2024, f"C{index}", -0.10, 1.4)

    result = select_broadest_viable_profile(
        pair_trace_records(records),
        range_atr_maxima=(1.5,),
        minimum_training_trades=8,
        minimum_confirmation_trades=4,
    )

    assert result["selected"] is None
