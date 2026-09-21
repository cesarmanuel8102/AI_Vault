from ibkr_paper_30d.liability import assess_proposal_liability


def test_long_stock_is_structurally_bounded():
    result = assess_proposal_liability(
        {"security_type": "STK", "instrument": "STK", "direction": "LONG", "legs": []}
    )
    assert result.status == "PASS"
    assert result.structurally_bounded is True


def test_short_stock_is_unbounded():
    result = assess_proposal_liability(
        {"security_type": "STK", "instrument": "STK", "direction": "SHORT", "legs": []}
    )
    assert result.status == "BLOCK"
    assert "UNBOUNDED_SHORT_EQUITY" in result.reason_codes


def test_long_option_is_bounded_by_premium():
    result = assess_proposal_liability(
        {"security_type": "OPT", "instrument": "OPT", "direction": "LONG", "legs": []}
    )
    assert result.status == "PASS"


def test_naked_short_option_without_leg_proof_is_blocked():
    result = assess_proposal_liability(
        {"security_type": "OPT", "instrument": "OPT", "direction": "SHORT", "legs": []}
    )
    assert result.status == "BLOCK"
    assert "SHORT_OPTION_REQUIRES_EXPLICIT_LEGS_FOR_BOUND_PROOF" in result.reason_codes


def test_bull_call_spread_has_bounded_upside_loss():
    result = assess_proposal_liability(
        {
            "legs": [
                {
                    "symbol": "XYZ",
                    "security_type": "OPT",
                    "action": "BUY",
                    "ratio": 1,
                    "strike": 100,
                    "right": "C",
                    "multiplier": "100",
                },
                {
                    "symbol": "XYZ",
                    "security_type": "OPT",
                    "action": "SELL",
                    "ratio": 1,
                    "strike": 110,
                    "right": "C",
                    "multiplier": "100",
                },
            ]
        }
    )
    assert result.status == "PASS"


def test_naked_short_call_leg_is_unbounded():
    result = assess_proposal_liability(
        {
            "legs": [
                {
                    "symbol": "XYZ",
                    "security_type": "OPT",
                    "action": "SELL",
                    "ratio": 1,
                    "strike": 110,
                    "right": "C",
                    "multiplier": "100",
                }
            ]
        }
    )
    assert result.status == "BLOCK"
    assert any(code.startswith("UNBOUNDED_UPSIDE_PRICE_LOSS") for code in result.reason_codes)


def test_covered_call_is_structurally_bounded():
    result = assess_proposal_liability(
        {
            "legs": [
                {
                    "symbol": "XYZ",
                    "security_type": "STK",
                    "action": "BUY",
                    "ratio": 100,
                    "multiplier": "1",
                },
                {
                    "symbol": "XYZ",
                    "security_type": "OPT",
                    "action": "SELL",
                    "ratio": 1,
                    "strike": 110,
                    "right": "C",
                    "multiplier": "100",
                },
            ]
        }
    )
    assert result.status == "PASS"


def test_directional_future_without_hedge_is_not_admissible():
    result = assess_proposal_liability(
        {"security_type": "FUT", "instrument": "FUT", "direction": "LONG", "legs": []}
    )
    assert result.status == "BLOCK"
