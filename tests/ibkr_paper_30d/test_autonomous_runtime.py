from datetime import datetime, timedelta, timezone

from ibkr_paper_30d.autonomous_runtime import AutonomousDecisionRuntime


def quote_evidence(contract_id: int, *, seconds_old: int = 0, market_data_type: int = 1):
    received = datetime.now(timezone.utc) - timedelta(seconds=seconds_old)
    return {
        "request": {
            "tool": "quote",
            "arguments": {"contract_id": contract_id},
        },
        "result": {
            "status": "PASS",
            "tool": "quote",
            "result": {
                "quote": {
                    "market_data_type": market_data_type,
                    "bid": 10.0,
                    "ask": 10.1,
                    "received_utc": received.isoformat().replace("+00:00", "Z"),
                }
            },
        },
    }


def test_single_contract_requires_exact_fresh_realtime_quote():
    proposal = {"contract_id": 123, "legs": []}
    ok, reasons = AutonomousDecisionRuntime._fresh_realtime_quote_coverage(
        [quote_evidence(123)], proposal
    )
    assert ok is True
    assert reasons == ()


def test_quote_for_different_contract_does_not_cover_proposal():
    proposal = {"contract_id": 123, "legs": []}
    ok, reasons = AutonomousDecisionRuntime._fresh_realtime_quote_coverage(
        [quote_evidence(456)], proposal
    )
    assert ok is False
    assert reasons == ("FRESH_REALTIME_QUOTE_REQUIRED:123",)


def test_delayed_market_data_does_not_cover_new_trade():
    proposal = {"contract_id": 123, "legs": []}
    ok, reasons = AutonomousDecisionRuntime._fresh_realtime_quote_coverage(
        [quote_evidence(123, market_data_type=3)], proposal
    )
    assert ok is False
    assert reasons == ("FRESH_REALTIME_QUOTE_REQUIRED:123",)


def test_stale_quote_does_not_cover_new_trade():
    proposal = {"contract_id": 123, "legs": []}
    ok, reasons = AutonomousDecisionRuntime._fresh_realtime_quote_coverage(
        [quote_evidence(123, seconds_old=180)], proposal
    )
    assert ok is False
    assert reasons == ("FRESH_REALTIME_QUOTE_REQUIRED:123",)


def test_every_multileg_contract_requires_its_own_quote():
    proposal = {
        "legs": [
            {"contract_id": 11},
            {"contract_id": 22},
        ]
    }
    ok, reasons = AutonomousDecisionRuntime._fresh_realtime_quote_coverage(
        [quote_evidence(11)], proposal
    )
    assert ok is False
    assert reasons == ("FRESH_REALTIME_QUOTE_REQUIRED:22",)
