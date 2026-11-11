from analyze_entry_countermeasures import replay_accepted_pnl, summarize_by


def _row(*, hour=10, period=20, friction=0.02, pnl=100, option_15=None, underlying_15=None):
    checkpoints = {}
    if option_15 is not None:
        checkpoints[15] = {
            "option_return": option_15,
            "underlying_return": underlying_15,
        }
    return {
        "entry": {
            "time": f"2025-01-02T{hour:02d}:31:00",
            "period": period,
            "entry_price": 1.0,
            "quantity": 10,
            "estimated_roundtrip_friction": friction,
        },
        "fees": 13.0,
        "net_pnl": pnl,
        "checkpoints": checkpoints,
    }


def test_replay_accepted_pnl_skips_uneconomic_trade():
    assert replay_accepted_pnl(_row(friction=0.11)) is None


def test_replay_accepted_pnl_applies_frozen_adverse_loss_cut_once():
    row = _row(pnl=-900, option_15=-0.50, underlying_15=-0.001)

    assert replay_accepted_pnl(row) == -513.0


def test_summarize_by_reports_net_profit_factor_and_win_rate():
    rows = [_row(hour=10, pnl=100), _row(hour=10, pnl=-40), _row(hour=11, pnl=25)]

    result = summarize_by(rows, lambda row: int(row["entry"]["time"][11:13]))

    assert result[10] == {
        "trades": 2,
        "wins": 1,
        "win_rate": 0.5,
        "net_pnl": 60.0,
        "profit_factor": 2.5,
    }
    assert result[11]["net_pnl"] == 25.0
