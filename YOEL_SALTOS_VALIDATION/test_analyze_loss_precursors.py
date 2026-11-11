from analyze_loss_precursors import evaluate_rule, join_traces_to_trades


def test_join_traces_to_trades_pairs_each_ticker_chronologically():
    traces = [
        {"type": "entry", "ticker": "SPY", "time": "2023-01-01T10:00:00", "entry_price": 1.0, "quantity": 10, "estimated_roundtrip_friction": 0.03},
        {"type": "checkpoint", "ticker": "SPY", "entry_time": "2023-01-01T10:00:00", "checkpoint": 15, "option_return": -0.5, "level_margin": -0.01, "invalidation_margin": 0.01},
    ]
    trades = [{
        "symbols": [{"underlying": {"value": "SPY"}}],
        "entryTime": "2023-01-01T15:00:00Z",
        "profitLoss": -500,
        "totalFees": 13,
    }]

    rows = join_traces_to_trades(traces, trades)

    assert len(rows) == 1
    assert rows[0]["net_pnl"] == -513
    assert rows[0]["checkpoints"][15]["option_return"] == -0.5


def test_evaluate_rule_applies_economics_gate_and_causal_failure_exit():
    rows = [
        {
            "entry": {"entry_price": 1.0, "quantity": 10, "estimated_roundtrip_friction": 0.03},
            "net_pnl": -513,
            "fees": 13,
            "checkpoints": {15: {"option_return": -0.5, "level_margin": -0.01, "invalidation_margin": 0.01}},
        },
        {
            "entry": {"entry_price": 0.2, "quantity": 10, "estimated_roundtrip_friction": 0.10},
            "net_pnl": 100,
            "fees": 13,
            "checkpoints": {},
        },
    ]

    result = evaluate_rule(rows, take_profit=0.05, checkpoint=15)

    assert result["trades"] == 1
    assert result["cuts"] == 1
    assert result["net_pnl"] == -513.0
