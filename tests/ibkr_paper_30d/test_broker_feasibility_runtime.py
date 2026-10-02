from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from ibkr_paper_30d.autonomous_research import (
    AutonomousTradeProposal,
    ResearchRequest,
    ResearchTool,
)
from ibkr_paper_30d.ibkr_research_tools import IBKRResearchToolbox
from ibkr_paper_30d.trader_invocation import TraderInputBundle


def _bundle() -> TraderInputBundle:
    return TraderInputBundle(
        decision_cycle_id="cycle-broker-feasibility-runtime",
        utc_timestamp="2026-09-25T18:15:06Z",
        market_session_state="REGULAR",
        reconciliation_receipt={"status": "PASS"},
        experiment_subledger_snapshot={"allocation": "500.00", "equity": "500.00"},
        broker_account_snapshot={"declared_options_level": 4},
        positions_snapshot=[],
        open_orders_snapshot=[],
        risk_snapshot={"policy": "AGGRESSIVE_CAPITAL_BOUNDARY_V1"},
        kill_switch_state="KILL_SWITCH_CLEAR",
        market_data_snapshot={"gate_status": "PASS"},
        candidate_screen_results=[],
        relevant_previous_immutable_decisions=[],
        process_policy_version="AUTONOMOUS_RESEARCH_V1",
        execution_realism_version="PAPER_V1",
        benchmark_state={},
        experiment_clock={"remaining_days": 28},
    )


def _order_state(**updates):
    values = {
        "commission": "1.00",
        "minCommission": "1.00",
        "maxCommission": "1.00",
        "initMarginBefore": "1000.00",
        "initMarginChange": "252.80",
        "initMarginAfter": "1252.80",
        "maintMarginBefore": "1000.00",
        "maintMarginChange": "252.80",
        "maintMarginAfter": "1252.80",
        "equityWithLoanBefore": "500.00",
        "equityWithLoanChange": "-1.00",
        "equityWithLoanAfter": "499.00",
        "warningText": "",
    }
    values.update(updates)
    return SimpleNamespace(**values)


class WhatIfOnlyBroker:
    def __init__(self, state=None):
        self.state = state or _order_state()
        self.qualified_contracts = []
        self.what_if_calls = []
        self.disconnected = False

    def qualifyContracts(self, contract):
        self.qualified_contracts.append(contract)
        contract.symbol = contract.symbol or "GENI"
        contract.localSymbol = contract.localSymbol or contract.symbol
        contract.secType = contract.secType or "STK"
        contract.exchange = contract.exchange or "SMART"
        contract.currency = contract.currency or "USD"
        return [contract]

    def whatIfOrder(self, contract, order):
        assert order.whatIf is True
        self.what_if_calls.append((contract, order))
        return self.state

    def placeOrder(self, *_args, **_kwargs):
        raise AssertionError("normal broker order path must not be used")

    def disconnect(self):
        self.disconnected = True


@pytest.mark.parametrize(
    ("contract_key", "contract_id"),
    (("con_id", 482880561), ("contract_id", 656365592)),
)
def test_flat_runtime_request_reaches_authoritative_what_if(
    monkeypatch, contract_key, contract_id
):
    broker = WhatIfOnlyBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id=f"feasibility-{contract_id}",
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "action": "BUY",
            contract_key: contract_id,
            "quantity": 40,
            "order_type": "LMT",
            "limit_price": 6.32,
            "time_in_force": "DAY",
        },
        purpose="authoritative paper what-if",
    )

    result = toolbox.execute(request, _bundle())

    assert result.success is True
    assert result.error is None
    assert result.data["whatIf"] is True
    assert result.data["paper_only"] is True
    assert result.data["initMarginChange"] == "252.80"
    assert result.data["maintMarginChange"] == "252.80"
    assert result.data["commission"] == "1.00"
    assert len(broker.what_if_calls) == 1
    contract, order = broker.what_if_calls[0]
    assert contract.conId == contract_id
    assert order.action == "BUY"
    assert order.orderType == "LMT"
    assert Decimal(str(order.totalQuantity)) == Decimal("40")
    assert Decimal(str(order.lmtPrice)) == Decimal("6.32")
    assert order.tif == "DAY"
    assert order.whatIf is True
    assert order.transmit is True
    assert broker.disconnected is True


def test_flat_combo_request_builds_qualified_bag_for_authoritative_what_if(
    monkeypatch,
):
    class ComboBroker(WhatIfOnlyBroker):
        def qualifyContracts(self, contract):
            self.qualified_contracts.append(contract)
            contract.localSymbol = f"QQQ-{contract.conId}"
            contract.secType = "OPT"
            contract.exchange = "SMART"
            contract.currency = "USD"
            return [contract]

    broker = ComboBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id="feasibility-qqq-bear-put-spread",
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "action": "BUY",
            "currency": "USD",
            "exchange": "SMART",
            "legs": [
                {
                    "action": "BUY",
                    "contract_id": 911011733,
                    "exchange": "SMART",
                    "ratio": 1,
                },
                {
                    "action": "SELL",
                    "contract_id": 910640656,
                    "exchange": "SMART",
                    "ratio": 1,
                },
            ],
            "limit_price": 2.0,
            "order_type": "LMT",
            "quantity": 1,
            "sec_type": "BAG",
            "symbol": "QQQ",
        },
        purpose="authoritative paper combo what-if",
    )

    result = toolbox.execute(request, _bundle())

    assert result.success is True
    assert result.error is None
    assert [contract.conId for contract in broker.qualified_contracts] == [
        911011733,
        910640656,
    ]
    assert len(broker.what_if_calls) == 1
    contract, order = broker.what_if_calls[0]
    assert contract.symbol == "QQQ"
    assert contract.secType == "BAG"
    assert contract.exchange == "SMART"
    assert contract.currency == "USD"
    assert [leg.conId for leg in contract.comboLegs] == [911011733, 910640656]
    assert [leg.action for leg in contract.comboLegs] == ["BUY", "SELL"]
    assert [leg.ratio for leg in contract.comboLegs] == [1, 1]
    assert order.tif == "DAY"
    assert order.whatIf is True
    assert order.transmit is True
    assert broker.disconnected is True


class _ComboBroker(WhatIfOnlyBroker):
    def qualifyContracts(self, contract):
        self.qualified_contracts.append(contract)
        contract.localSymbol = f"IOVA-{contract.conId}"
        contract.secType = "OPT"
        contract.exchange = "SMART"
        contract.currency = "USD"
        return [contract]


# Canonical repository contract identity emitted to the model by
# IBKRResearchToolbox._serialize_contract(). Reproduces the exact leg shape
# the autonomous model supplied on 2026-10-02 after resolving real IBKR
# option contracts (request_id=retry_whatif_iova_oct16_15_18_with_contracts).
_CANONICAL_NESTED_LEGS = [
    {
        "action": "BUY",
        "ratio": 1,
        "contract": {
            "conId": 913925915,
            "symbol": "IOVA",
            "localSymbol": "IOVA  261016C00015000",
            "secType": "OPT",
            "exchange": "SMART",
            "currency": "USD",
            "expiry": "20261016",
            "strike": 15.0,
            "right": "C",
            "multiplier": "100",
        },
    },
    {
        "action": "SELL",
        "ratio": 1,
        "contract": {
            "conId": 926221865,
            "symbol": "IOVA",
            "localSymbol": "IOVA  261016C00018000",
            "secType": "OPT",
            "exchange": "SMART",
            "currency": "USD",
            "expiry": "20261016",
            "strike": 18.0,
            "right": "C",
            "multiplier": "100",
        },
    },
]

# Snake_case normalization the model attempted next
# (request_id=retry_whatif_iova_with_normalized_contracts).
_NORMALIZED_NESTED_LEGS = [
    {
        "action": "BUY",
        "ratio": 1,
        "contract": {
            "contract_id": 913925915,
            "symbol": "IOVA",
            "local_symbol": "IOVA  261016C00015000",
            "sec_type": "OPT",
            "exchange": "SMART",
            "currency": "USD",
            "expiry": "20261016",
            "strike": "15",
            "right": "C",
            "multiplier": "100",
        },
    },
    {
        "action": "SELL",
        "ratio": 1,
        "contract": {
            "contract_id": 926221865,
            "symbol": "IOVA",
            "local_symbol": "IOVA  261016C00018000",
            "sec_type": "OPT",
            "exchange": "SMART",
            "currency": "USD",
            "expiry": "20261016",
            "strike": "18",
            "right": "C",
            "multiplier": "100",
        },
    },
]


def _combo_request(legs, request_id="feasibility-iova-call-spread"):
    return ResearchRequest(
        request_id=request_id,
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "action": "BUY",
            "currency": "USD",
            "exchange": "SMART",
            "legs": legs,
            "limit_price": "0.90",
            "order_type": "LMT",
            "quantity": "1",
            "sec_type": "BAG",
            "symbol": "IOVA",
        },
        purpose="authoritative paper combo what-if",
    )


@pytest.mark.parametrize(
    ("legs", "label"),
    (
        (_CANONICAL_NESTED_LEGS, "camel_case_serialize_contract"),
        (_NORMALIZED_NESTED_LEGS, "snake_case_normalized"),
    ),
)
def test_canonical_nested_leg_contract_reaches_authoritative_what_if(
    monkeypatch, legs, label
):
    """A combo leg carrying the repository's canonical nested contract identity
    must reach IBKR what-if instead of failing local request validation."""
    broker = _ComboBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)

    result = toolbox.execute(_combo_request(legs, f"feasibility-{label}"), _bundle())

    assert result.error is None
    assert result.success is True
    assert [contract.conId for contract in broker.qualified_contracts] == [
        913925915,
        926221865,
    ]
    assert len(broker.what_if_calls) == 1
    contract, order = broker.what_if_calls[0]
    assert contract.symbol == "IOVA"
    assert contract.secType == "BAG"
    assert [leg.conId for leg in contract.comboLegs] == [913925915, 926221865]
    assert [leg.action for leg in contract.comboLegs] == ["BUY", "SELL"]
    assert [leg.ratio for leg in contract.comboLegs] == [1, 1]
    assert order.whatIf is True
    assert order.transmit is True
    assert broker.disconnected is True


def test_nested_leg_contract_without_identity_fails_closed_before_broker_call(
    monkeypatch,
):
    """A nested contract lacking authoritative identity must still fail closed."""
    broker = _ComboBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    legs = [
        {
            "action": "BUY",
            "ratio": 1,
            "contract": {"symbol": "IOVA", "secType": "OPT", "strike": 15.0},
        },
        {
            "action": "SELL",
            "ratio": 1,
            "contract": {"conId": 926221865, "symbol": "IOVA"},
        },
    ]

    result = toolbox.execute(_combo_request(legs, "feasibility-nested-no-id"), _bundle())

    assert result.success is False
    assert result.data["error_code"] == "BROKER_FEASIBILITY_COMBO_LEG_CONTRACT_REQUIRED"
    assert result.data["stage"] == "REQUEST_VALIDATION"
    assert broker.what_if_calls == []


def test_duplicate_combo_leg_identity_is_rejected_before_broker_call(monkeypatch):
    """Ambiguous combo legs sharing one contract identity must be rejected."""
    broker = _ComboBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    legs = [
        {"action": "BUY", "ratio": 1, "contract": {"conId": 913925915}},
        {"action": "SELL", "ratio": 1, "contract": {"conId": 913925915}},
    ]

    result = toolbox.execute(_combo_request(legs, "feasibility-dupe-leg"), _bundle())

    assert result.success is False
    assert result.data["error_code"] == "BROKER_FEASIBILITY_COMBO_LEG_DUPLICATE"
    assert result.data["stage"] == "REQUEST_VALIDATION"
    assert broker.what_if_calls == []


@pytest.mark.parametrize(
    ("legs", "error_code"),
    (
        ([], "BROKER_FEASIBILITY_COMBO_LEGS_REQUIRED"),
        (
            [
                {
                    "action": "BUY",
                    "contract_id": 911011733,
                    "exchange": "SMART",
                    "ratio": 1,
                },
                {
                    "action": "SELL",
                    "exchange": "SMART",
                    "ratio": 1,
                },
            ],
            "BROKER_FEASIBILITY_COMBO_LEG_CONTRACT_REQUIRED",
        ),
        (
            [
                {
                    "action": "HOLD",
                    "contract_id": 911011733,
                    "exchange": "SMART",
                    "ratio": 1,
                },
                {
                    "action": "SELL",
                    "contract_id": 910640656,
                    "exchange": "SMART",
                    "ratio": 1,
                },
            ],
            "BROKER_FEASIBILITY_COMBO_LEG_ACTION_INVALID",
        ),
        (
            [
                {
                    "action": "BUY",
                    "contract_id": 911011733,
                    "exchange": "SMART",
                    "ratio": 0,
                },
                {
                    "action": "SELL",
                    "contract_id": 910640656,
                    "exchange": "SMART",
                    "ratio": 1,
                },
            ],
            "BROKER_FEASIBILITY_COMBO_LEG_RATIO_INVALID",
        ),
    ),
)
def test_flat_combo_request_rejects_invalid_legs_before_broker_call(
    monkeypatch, legs, error_code
):
    broker = WhatIfOnlyBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id="feasibility-invalid-combo",
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "action": "BUY",
            "legs": legs,
            "limit_price": 2.0,
            "order_type": "LMT",
            "quantity": 1,
            "sec_type": "BAG",
            "symbol": "QQQ",
        },
        purpose="reject malformed combo",
    )

    result = toolbox.execute(request, _bundle())

    assert result.success is False
    assert result.error == "BROKER_FEASIBILITY_ARGUMENTS_INVALID"
    assert result.data["error_code"] == error_code
    assert result.data["stage"] == "REQUEST_VALIDATION"
    assert broker.qualified_contracts == []
    assert broker.what_if_calls == []


def test_flat_runtime_request_missing_contract_fails_closed_without_broker_call(
    monkeypatch,
):
    broker = WhatIfOnlyBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id="feasibility-invalid",
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "action": "BUY",
            "quantity": 40,
            "order_type": "LMT",
            "limit_price": 6.32,
        },
        purpose="reject incomplete what-if request",
    )

    result = toolbox.execute(request, _bundle())

    assert result.success is False
    assert result.error == "BROKER_FEASIBILITY_ARGUMENTS_INVALID"
    assert result.data["error_code"] == "BROKER_FEASIBILITY_CONTRACT_REQUIRED"
    assert result.data["stage"] == "REQUEST_VALIDATION"
    assert broker.qualified_contracts == []
    assert broker.what_if_calls == []


def test_proposal_validation_what_if_uses_required_transmit_flag(monkeypatch):
    broker = WhatIfOnlyBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    proposal = AutonomousTradeProposal(
        thesis="test",
        catalyst="test",
        symbol="GENI",
        sec_type="STK",
        direction="LONG",
        action="BUY",
        quantity="40",
        order_type="LMT",
        limit_price="6.32",
        capital_required="252.80",
        maximum_loss="252.80",
        loss_is_bounded=True,
        probability_profit="0.55",
        probability_loss="0.45",
        expected_gain="20",
        expected_loss="10",
        expected_value="6.5",
        expected_reward_risk="2",
        expected_holding_period="1 day",
        entry_condition="test",
        invalidation_condition="test",
        exit_plan="test",
        why_now="test",
        alternatives_considered=["cash"],
        evidence_used=["quote"],
        disconfirming_evidence=[],
        confidence="0.6",
    )
    monkeypatch.setattr(
        toolbox,
        "_proposal_contract",
        lambda _ib, _proposal: SimpleNamespace(
            conId=482880561,
            symbol="GENI",
            localSymbol="GENI",
            secType="STK",
            exchange="SMART",
            primaryExchange="NYSE",
            currency="USD",
            lastTradeDateOrContractMonth="",
            strike=0,
            right="",
            multiplier="",
        ),
    )

    result = toolbox._broker_feasibility(proposal, ib=broker)

    assert result["success"] is True
    assert len(broker.what_if_calls) == 1
    _, order = broker.what_if_calls[0]
    assert order.whatIf is True
    assert order.transmit is True
    assert order.tif == "DAY"


@pytest.mark.parametrize(
    ("state_updates", "error_code"),
    (
        (
            {"initMarginChange": None, "maintMarginChange": None},
            "BROKER_MARGIN_EVIDENCE_MISSING",
        ),
        (
            {"commission": None, "minCommission": None, "maxCommission": None},
            "BROKER_COMMISSION_EVIDENCE_MISSING",
        ),
        (
            {"initMarginChange": "NaN", "maintMarginChange": "NaN"},
            "BROKER_MARGIN_EVIDENCE_MISSING",
        ),
    ),
)
def test_research_what_if_incomplete_evidence_is_not_reported_as_success(
    monkeypatch, state_updates, error_code
):
    broker = WhatIfOnlyBroker(state=_order_state(**state_updates))
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id="feasibility-incomplete",
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "action": "BUY",
            "con_id": 482880561,
            "quantity": 40,
            "order_type": "LMT",
            "limit_price": 6.32,
            "time_in_force": "DAY",
        },
        purpose="reject incomplete broker evidence",
    )

    result = toolbox.execute(request, _bundle())

    assert result.success is False
    assert result.error == "BROKER_FEASIBILITY_EVIDENCE_INCOMPLETE"
    assert result.data["error_code"] == error_code
    assert result.data["stage"] == "WHAT_IF_NORMALIZATION"
    for key, expected in state_updates.items():
        assert result.data[key] == expected


def test_research_what_if_accepts_explicit_zero_margin_and_commission(monkeypatch):
    broker = WhatIfOnlyBroker(
        state=_order_state(
            initMarginChange="0",
            maintMarginChange="0.00",
            commission="0",
            minCommission=None,
            maxCommission=None,
        )
    )
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id="feasibility-explicit-zero",
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "action": "BUY",
            "con_id": 482880561,
            "quantity": 40,
            "order_type": "LMT",
            "limit_price": 6.32,
        },
        purpose="accept explicit broker zero values",
    )

    result = toolbox.execute(request, _bundle())

    assert result.success is True
    assert result.data["initMarginChange"] == "0"
    assert result.data["maintMarginChange"] == "0.00"
    assert result.data["commission"] == "0"


def test_qualified_contract_mismatch_blocks_before_what_if(monkeypatch):
    class WrongContractBroker(WhatIfOnlyBroker):
        def qualifyContracts(self, contract):
            contract.conId = 999999999
            contract.symbol = "WRONG"
            contract.localSymbol = "WRONG"
            contract.secType = "STK"
            contract.exchange = "SMART"
            contract.currency = "USD"
            return [contract]

    broker = WrongContractBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id="feasibility-contract-mismatch",
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "action": "BUY",
            "con_id": 482880561,
            "symbol": "GENI",
            "quantity": 40,
            "order_type": "LMT",
            "limit_price": 6.32,
        },
        purpose="reject cross-contract evidence",
    )

    result = toolbox.execute(request, _bundle())

    assert result.success is False
    assert result.error == "BROKER_FEASIBILITY_CONTRACT_MISMATCH"
    assert result.data["error_code"] == "BROKER_FEASIBILITY_CONTRACT_MISMATCH"
    assert result.data["stage"] == "CONTRACT_QUALIFICATION"
    assert broker.what_if_calls == []


def test_what_if_timeout_is_sanitized_and_fails_closed(monkeypatch):
    class TimeoutBroker(WhatIfOnlyBroker):
        def whatIfOrder(self, contract, order):
            raise TimeoutError("account-sensitive broker message")

    broker = TimeoutBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id="feasibility-timeout",
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "action": "BUY",
            "con_id": 482880561,
            "quantity": 40,
            "order_type": "LMT",
            "limit_price": 6.32,
        },
        purpose="fail closed on timeout",
    )

    result = toolbox.execute(request, _bundle())

    assert result.success is False
    assert result.error == "TimeoutError:broker_operation_failed"
    assert result.data["error_type"] == "TimeoutError"
    assert result.data["error_code"] == "BROKER_FEASIBILITY_BROKER_OPERATION_FAILED"
    assert result.data["stage"] == "BROKER_WHAT_IF"
    assert "account-sensitive" not in str(result.model_dump(mode="json"))
