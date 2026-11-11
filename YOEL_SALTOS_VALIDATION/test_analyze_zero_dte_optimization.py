from analyze_zero_dte_optimization import choose_candidate, trade_metrics, validation_verdict


def trade(net_before_fees, fees, exit_time):
    return {
        "profitLoss": net_before_fees,
        "totalFees": fees,
        "exitTime": exit_time,
    }


def test_trade_metrics_are_net_of_fees_and_split_by_semester():
    trades = [
        trade(120, 20, "2025-03-01T10:00:00Z"),
        trade(-40, 10, "2025-05-01T10:00:00Z"),
        trade(80, 10, "2025-08-01T10:00:00Z"),
        trade(-30, 10, "2025-10-01T10:00:00Z"),
    ]
    result = trade_metrics(trades)
    assert result["net_pnl"] == 80
    assert result["expectancy"] == 20
    assert result["profit_factor"] == 170 / 90
    assert result["semester_net_pnl"] == {"2025-H1": 50, "2025-H2": 30}
    assert result["positive_semesters"] == 2


def test_selector_prefers_profit_factor_then_expectancy_drawdown_and_stability():
    summaries = {
        "control": {"positive_semesters": 2, "profit_factor": 1.1, "expectancy": 50, "drawdown_pct": 10},
        "five_zero": {"positive_semesters": 2, "profit_factor": 1.15, "expectancy": 5, "drawdown_pct": 20},
        "eight_minus_two": {"positive_semesters": 2, "profit_factor": 1.2, "expectancy": 4, "drawdown_pct": 25},
        "quality": {"positive_semesters": 1, "profit_factor": 1.2, "expectancy": 4, "drawdown_pct": 15},
    }
    assert choose_candidate(summaries) == "quality"


def test_validation_verdict_requires_sample_profitability_and_lower_drawdown():
    control = {"drawdown_pct": 20}
    good = {"trades": 12, "expectancy": 1, "profit_factor": 1.01, "return_pct": 0.1, "drawdown_pct": 19}
    assert validation_verdict({**good, "trades": 11}, control) == "INSUFFICIENT"
    assert validation_verdict(good, control) == "GO"
    assert validation_verdict({**good, "expectancy": -1}, control) == "NO-GO"
    assert validation_verdict({**good, "drawdown_pct": 21}, control) == "NO-GO"
