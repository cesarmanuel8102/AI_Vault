from __future__ import annotations

from copy import deepcopy

import pytest

from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.trader_invocation import (
    InvocationRequest,
    ProviderResponse,
    TraderInputBundle,
    TraderInvocationAdapter,
)


class StubProvider:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def invoke(self, request, bundle):
        self.calls += 1
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


@pytest.fixture
def database(tmp_path):
    with Database.open(tmp_path / "trader.sqlite3") as db:
        yield db


@pytest.fixture
def valid_bundle() -> TraderInputBundle:
    return TraderInputBundle(
        decision_cycle_id="cycle-1",
        utc_timestamp="2026-09-20T00:00:00Z",
        market_session_state="REGULAR",
        reconciliation_receipt={"status": "PASS", "sha256": "r" * 64},
        experiment_subledger_snapshot={"equity": "500.00"},
        broker_account_snapshot={"cash": "512.70"},
        positions_snapshot=[],
        open_orders_snapshot=[],
        risk_snapshot={"status": "PASS"},
        kill_switch_state="KILL_SWITCH_CLEAR",
        market_data_snapshot={"gate_status": "PASS", "symbols": ["SPY"]},
        candidate_screen_results=[{"symbol": "SPY"}],
        relevant_previous_immutable_decisions=[],
        process_policy_version="PROCESS_V1",
        execution_realism_version="REALISM_V1",
        benchmark_state={"cash": "500.00"},
    )


def request(bundle, *, cycle="cycle-1", invocation="invocation-1", **updates):
    values = {
        "decision_cycle_id": cycle,
        "invocation_id": invocation,
        "utc_timestamp": "2026-09-20T00:00:01Z",
        "requested_model": "codex-highest",
        "actual_model": "codex-highest",
        "model_configuration": {"temperature": 0},
        "reasoning_effort": "HIGH",
        "input_bundle_sha256": bundle.sha256,
        "risk_policy_version": "CAPITAL_BOUNDARY_V2",
        "experiment_id": "experiment-1",
        "invocation_trigger": "SCHEDULED_SCAN",
        "timeout_seconds": 60,
    }
    values.update(updates)
    return InvocationRequest(**values)


def no_trade_output(bundle, *, cycle="cycle-1", invocation="invocation-1"):
    return {
        "decision_cycle_id": cycle,
        "invocation_id": invocation,
        "decision": "NO_TRADE",
        "input_bundle_sha256": bundle.sha256,
        "utc_timestamp": "2026-09-20T00:00:02Z",
        "confidence": "0.80",
        "reason_codes": ["NO_VALID_CANDIDATE"],
    }


def proposal_output(bundle, symbol="SPY"):
    result = no_trade_output(bundle)
    result.update(
        {
            "decision": "PROPOSE_TRADE",
            "reason_codes": ["VALID_CANDIDATE"],
            "proposal": {
                "thesis": "Price continuation after confirmed catalyst",
                "mechanism": "Demand imbalance",
                "catalyst": "Scheduled event",
                "symbol": symbol,
                "instrument": "STK",
                "direction": "LONG",
                "entry_condition": "Ask remains below frozen threshold",
                "invalidation_condition": "Price closes below support",
                "profit_taking_rule": "Exit at predefined target",
                "expected_holding_period": "1-3 days",
                "expected_reward": "10.00",
                "expected_risk": "5.00",
                "expected_reward_risk": "2.00",
                "why_now": "Catalyst is active",
                "why_this_beats_cash": "Expected reward exceeds cash return",
                "best_reasonable_alternative": "Remain in cash",
                "disconfirming_evidence": ["Weak breadth"],
                "confidence": "0.70",
            },
        }
    )
    return result


def adapter(database, raw, *, actual_model="codex-highest", fallback_reason=None):
    provider = StubProvider(
        ProviderResponse(
            actual_model=actual_model,
            fallback_reason=fallback_reason,
            structured_output=raw,
        )
        if not isinstance(raw, BaseException)
        else raw
    )
    return TraderInvocationAdapter(database, provider), provider


def test_valid_no_trade_is_accepted(database, valid_bundle) -> None:
    subject, _ = adapter(database, no_trade_output(valid_bundle))

    result = subject.invoke(request(valid_bundle), valid_bundle)

    assert result.accepted is True
    assert result.effective_decision == "NO_TRADE"
    assert result.validation == "PASS"


def test_valid_trade_proposal_is_structured_but_has_no_order_authority(
    database, valid_bundle
) -> None:
    subject, _ = adapter(database, proposal_output(valid_bundle))

    result = subject.invoke(request(valid_bundle), valid_bundle)

    assert result.accepted is True
    assert result.effective_decision == "PROPOSE_TRADE"
    assert result.order_authority is False
    assert result.final_decision_hash


@pytest.mark.parametrize(
    "raw,expected_reason",
    [
        ("not-json", "MALFORMED_OUTPUT"),
        ({"decision": "NO_TRADE"}, "MALFORMED_OUTPUT"),
        ({"decision": "PLACE_ORDER"}, "MALFORMED_OUTPUT"),
    ],
)
def test_malformed_wrong_schema_and_authority_excess_fail_to_no_trade(
    database, valid_bundle, raw, expected_reason
) -> None:
    subject, _ = adapter(database, raw)

    result = subject.invoke(request(valid_bundle), valid_bundle)

    assert result.validation == "INVALID"
    assert result.effective_decision == "NO_TRADE"
    assert expected_reason in result.reason_codes


def test_timeout_fails_to_no_trade(database, valid_bundle) -> None:
    subject, _ = adapter(database, TimeoutError("provider timeout"))

    result = subject.invoke(request(valid_bundle), valid_bundle)

    assert result.validation == "INVALID"
    assert result.reason_codes == ("PROVIDER_TIMEOUT",)


def test_duplicate_cycle_accepts_at_most_one_result(database, valid_bundle) -> None:
    subject, provider = adapter(database, no_trade_output(valid_bundle))
    first = subject.invoke(request(valid_bundle), valid_bundle)
    second = subject.invoke(
        request(valid_bundle, invocation="invocation-2"), valid_bundle
    )

    assert first.accepted is True
    assert second.accepted is False
    assert second.effective_decision == "NO_TRADE"
    assert second.reason_codes == ("DUPLICATE_ACCEPTED_CYCLE",)
    assert provider.calls == 1


def test_stale_input_hash_fails_before_provider_call(database, valid_bundle) -> None:
    subject, provider = adapter(database, no_trade_output(valid_bundle))
    bad_request = request(valid_bundle, input_bundle_sha256="0" * 64)

    result = subject.invoke(bad_request, valid_bundle)

    assert result.reason_codes == ("INPUT_HASH_MISMATCH",)
    assert provider.calls == 0


def test_output_cycle_or_bundle_contradiction_fails(database, valid_bundle) -> None:
    raw = no_trade_output(valid_bundle, cycle="other-cycle")
    subject, _ = adapter(database, raw)

    result = subject.invoke(request(valid_bundle), valid_bundle)

    assert result.validation == "INVALID"
    assert result.reason_codes == ("CYCLE_MISMATCH",)


def test_symbol_outside_advisory_candidates_is_allowed(
    database, valid_bundle
) -> None:
    subject, _ = adapter(database, proposal_output(valid_bundle, symbol="QQQ"))

    result = subject.invoke(request(valid_bundle), valid_bundle)

    assert result.validation == "PASS"
    assert result.accepted is True
    assert result.effective_decision == "PROPOSE_TRADE"


def test_stale_market_gate_blocks_invocation(database, valid_bundle) -> None:
    payload = valid_bundle.model_dump()
    payload["market_data_snapshot"] = {"gate_status": "BLOCK", "symbols": ["SPY"]}
    stale = TraderInputBundle(**payload)
    subject, provider = adapter(database, no_trade_output(stale))

    result = subject.invoke(request(stale), stale)

    assert result.reason_codes == ("MARKET_DATA_GATE_BLOCK",)
    assert provider.calls == 0


def test_explicit_model_fallback_metadata_is_persisted(database, valid_bundle) -> None:
    subject, _ = adapter(
        database,
        no_trade_output(valid_bundle),
        actual_model="codex-secondary",
        fallback_reason="requested model unavailable",
    )
    req = request(
        valid_bundle,
        actual_model="codex-secondary",
        fallback_reason="requested model unavailable",
    )

    result = subject.invoke(req, valid_bundle)

    assert result.accepted is True
    stored = database.execute(
        "SELECT payload_json FROM trader_invocations WHERE invocation_id=?",
        (req.invocation_id,),
    ).fetchone()[0]
    assert "requested model unavailable" in stored


def test_silent_model_substitution_is_invalid(database, valid_bundle) -> None:
    subject, _ = adapter(
        database, no_trade_output(valid_bundle), actual_model="codex-secondary"
    )

    result = subject.invoke(request(valid_bundle), valid_bundle)

    assert result.validation == "INVALID"
    assert result.reason_codes == ("SILENT_MODEL_SUBSTITUTION",)


def test_failed_new_cycle_never_reuses_previous_decision(database, valid_bundle) -> None:
    first_adapter, _ = adapter(database, proposal_output(valid_bundle))
    assert first_adapter.invoke(request(valid_bundle), valid_bundle).accepted is True

    next_payload = deepcopy(valid_bundle.model_dump())
    next_payload["decision_cycle_id"] = "cycle-2"
    next_bundle = TraderInputBundle(**next_payload)
    second_adapter, _ = adapter(database, "malformed")
    result = second_adapter.invoke(
        request(next_bundle, cycle="cycle-2", invocation="invocation-2"), next_bundle
    )

    assert result.accepted is False
    assert result.effective_decision == "NO_TRADE"
    assert result.final_decision_hash != first_adapter.last_result.final_decision_hash


def test_real_codex_gate_is_not_claimed_by_stub_provider(database, valid_bundle) -> None:
    subject, _ = adapter(database, no_trade_output(valid_bundle))
    subject.invoke(request(valid_bundle), valid_bundle)

    assert subject.local_gate_status == "PASS"
    assert subject.real_codex_gate_status == "NOT_TESTED"
