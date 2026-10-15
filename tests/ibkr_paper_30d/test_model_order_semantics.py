import pytest

from ibkr_paper_30d.autonomous_execution import AutonomousPaperExecutor, WriterOwnedModelExecutionMechanics
from ibkr_paper_30d.autonomous_research import AutonomousPositionAction, TraderDecision
from ibkr_paper_30d.continuity_models import TimeInForce
from ibkr_paper_30d.ibkr_research_tools import IBKRResearchToolbox
from ibkr_paper_30d.persistence import Database
from test_autonomous_execution import bundle, proposal, bag_proposal, _ResolvedBagToolbox, _DirectRoutedPositionIB
from test_broker_feasibility_runtime import WhatIfOnlyBroker


def test_explicit_ioc_survives_proposal_feasibility(monkeypatch):
    candidate = proposal().model_copy(update={"time_in_force": TimeInForce.IOC})
    broker = WhatIfOnlyBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    toolbox._broker_feasibility_from_args({"proposal": candidate.model_dump(mode="json")})
    assert broker.what_if_calls[0][1].tif == "IOC"


def test_nested_ioc_is_bound_to_validated_proposal(monkeypatch):
    broker = WhatIfOnlyBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    result = toolbox._broker_feasibility_from_args({"proposal": proposal().model_dump(mode="json"), "order": {"tif": "IOC"}})
    assert broker.what_if_calls[0][1].tif == "IOC"
    assert result["validated_proposal"]["time_in_force"] == "IOC"


def test_conflicting_tif_is_rejected_before_broker(monkeypatch):
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: pytest.fail("conflicting intent reached broker"))
    candidate = proposal().model_copy(update={"time_in_force": TimeInForce.IOC})
    result = toolbox._broker_feasibility_from_args({"proposal": candidate.model_dump(mode="json"), "order": {"tif": "DAY"}})
    assert result["success"] is False


def test_legacy_proposal_serialization_is_unchanged():
    assert "time_in_force" not in proposal().model_dump(mode="json")
    assert "good_till_date_utc" not in proposal().model_dump(mode="json")


def test_entry_ioc_reaches_actual_writer(tmp_path):
    toolbox = _ResolvedBagToolbox()
    sent = []
    original = toolbox.ib.placeOrder
    def capture(contract, order):
        sent.append(order.tif)
        return original(contract, order)
    toolbox.ib.placeOrder = capture
    with Database.open(tmp_path / "entry.sqlite3") as db:
        result = AutonomousPaperExecutor(
            toolbox, armed=True, database=db,
            fresh_safety_check=lambda scope: (), operator_control_check=lambda: (),
        ).execute(bag_proposal().model_copy(update={"time_in_force": TimeInForce.IOC}), bundle())
    assert result.success is True
    assert sent == ["IOC"]


def test_exit_ioc_reaches_actual_writer(tmp_path):
    broker = _DirectRoutedPositionIB()
    toolbox = IBKRResearchToolbox()
    toolbox._connect = lambda *, client_id=None: broker
    toolbox.live_contract_quote_evidence = lambda *_args, **_kwargs: {"success": True, "market_data_type": 1}
    sent = []
    original = broker.placeOrder
    def capture(contract, order):
        sent.append(order.tif)
        return original(contract, order)
    broker.placeOrder = capture
    action = AutonomousPositionAction(
        symbol="HAE", sec_type="STK", action="SELL", quantity="1",
        order_type="MKT", contract_id=7884, reason="Reduce exposure.", time_in_force="IOC",
    )
    with Database.open(tmp_path / "exit.sqlite3") as db:
        result = AutonomousPaperExecutor(
            toolbox, armed=True, database=db,
            fresh_safety_check=lambda scope: (), operator_control_check=lambda: (),
        ).execute_position_action(action, bundle(), TraderDecision.REDUCE_POSITION)
    assert result.success is True
    assert sent == ["IOC"]


@pytest.mark.parametrize("updates", [
    {"time_in_force": "GTD"},
    {"time_in_force": "GTD", "good_till_date_utc": "2026-10-15T02:00:00"},
    {"time_in_force": "IOC", "good_till_date_utc": "2026-10-15T02:00:00Z"},
])
def test_invalid_temporal_intent_rejected(updates):
    from ibkr_paper_30d.autonomous_research import AutonomousTradeProposal
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        AutonomousTradeProposal.model_validate({**proposal().model_dump(mode="json"), **updates})


@pytest.mark.parametrize("certified", [True, False])
def test_writer_admission_uses_certified_open_family_not_closed_regular_quotes(certified):
    value = bundle(market_gate="BLOCK").model_copy(update={
        "multi_sleeve_portfolio": {"schema": "MULTI_SLEEVE_PORTFOLIO_V4", "entry_eligibility": {"CONTINUOUS_SLEEVE": {"status": "PASS", "eligible_family_sha256": ["f" * 64]}}},
        "product_capability_snapshot": {"executable_family_sha256": ["f" * 64], "families": [{"family_sha256": "f" * 64, "status": "FULL_LIFECYCLE_VERIFIED", "executable": certified}], "authenticated_sessions": {"f" * 64: {"authenticated": True, "tradable_now": True, "eligible_sleeves": ["CONTINUOUS_SLEEVE"]}}},
    })
    reasons = WriterOwnedModelExecutionMechanics._frozen_bundle_reasons(value)
    assert ("MARKET_DATA_GATE_BLOCK" not in reasons) is certified
