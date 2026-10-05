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


# ---------------------------------------------------------------------------
# Adversarial contradictory-identity cases (second-audit hardening)
# ---------------------------------------------------------------------------


class _ConflictComboBroker(WhatIfOnlyBroker):
    """Any broker call would prove the validator leaked an ambiguous identity."""

    def qualifyContracts(self, contract):  # pragma: no cover - must never run
        raise AssertionError("validator must reject before broker contact")

    def whatIfOrder(self, contract, order):  # pragma: no cover - must never run
        raise AssertionError("validator must reject before what-if")


@pytest.mark.parametrize(
    ("legs", "error_code"),
    (
        (
            [
                {
                    "conId": 111,  # flat identity
                    "contract": {"conId": 222},  # conflicting nested identity
                    "action": "BUY",
                    "ratio": 1,
                },
                {
                    "contract": {"conId": 926221865},
                    "action": "SELL",
                    "ratio": 1,
                },
            ],
            "BROKER_FEASIBILITY_COMBO_LEG_IDENTITY_CONFLICT",
        ),
        (
            [
                {
                    "con_id": 111,
                    "contract": {"contract_id": 222},
                    "action": "BUY",
                    "ratio": 1,
                },
                {
                    "contract": {"conId": 926221865},
                    "action": "SELL",
                    "ratio": 1,
                },
            ],
            "BROKER_FEASIBILITY_COMBO_LEG_IDENTITY_CONFLICT",
        ),
        (
            [
                {
                    "contract_id": 111,
                    "contract": {"conId": 222},
                    "action": "BUY",
                    "ratio": 1,
                },
                {
                    "contract": {"conId": 926221865},
                    "action": "SELL",
                    "ratio": 1,
                },
            ],
            "BROKER_FEASIBILITY_COMBO_LEG_IDENTITY_CONFLICT",
        ),
        (
            [
                {
                    "contract": {"conId": 913925915, "contract_id": 926221865},
                    "action": "BUY",
                    "ratio": 1,
                },
                {
                    "contract": {"conId": 926221865},
                    "action": "SELL",
                    "ratio": 1,
                },
            ],
            "BROKER_FEASIBILITY_COMBO_LEG_IDENTITY_CONFLICT",
        ),
    ),
)
def test_contradictory_combo_leg_identity_fails_closed(monkeypatch, legs, error_code):
    broker = _ConflictComboBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)

    result = toolbox.execute(_combo_request(legs, "feasibility-conflict"), _bundle())

    assert result.success is False
    assert result.data["error_code"] == error_code
    assert result.data["stage"] == "REQUEST_VALIDATION"


# ---------------------------------------------------------------------------
# Vertical structural semantics (declared intent)
# ---------------------------------------------------------------------------


def _vertical_leg(action, con_id, *, strike, right="C", expiry="20261016"):
    return {
        "action": action,
        "ratio": 1,
        "contract": {
            "conId": con_id,
            "symbol": "IOVA",
            "secType": "OPT",
            "exchange": "SMART",
            "currency": "USD",
            "expiry": expiry,
            "strike": strike,
            "right": right,
            "multiplier": "100",
        },
    }


@pytest.mark.parametrize(
    ("legs", "error_code"),
    (
        (
            [  # same strike — not a vertical
                _vertical_leg("BUY", 913925915, strike=15.0),
                _vertical_leg("SELL", 926221865, strike=15.0),
            ],
            "BROKER_FEASIBILITY_VERTICAL_STRUCTURAL_INCONSISTENT",
        ),
        (
            [  # mismatched expiries
                _vertical_leg("BUY", 913925915, strike=15.0, expiry="20261016"),
                _vertical_leg("SELL", 926221865, strike=18.0, expiry="20261120"),
            ],
            "BROKER_FEASIBILITY_VERTICAL_STRUCTURAL_INCONSISTENT",
        ),
        (
            [  # mismatched right
                _vertical_leg("BUY", 913925915, strike=15.0, right="C"),
                _vertical_leg("SELL", 926221865, strike=18.0, right="P"),
            ],
            "BROKER_FEASIBILITY_VERTICAL_STRUCTURAL_INCONSISTENT",
        ),
        (
            [  # same-side actions — not a vertical spread
                _vertical_leg("BUY", 913925915, strike=15.0),
                _vertical_leg("BUY", 926221865, strike=18.0),
            ],
            "BROKER_FEASIBILITY_VERTICAL_STRUCTURAL_INCONSISTENT",
        ),
    ),
)
def test_declared_vertical_rejects_structural_inconsistency(monkeypatch, legs, error_code):
    broker = _ComboBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id="feasibility-vertical-bad",
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
            "structure": "VERTICAL",  # declared intent triggers structural rule
        },
        purpose="reject malformed declared vertical",
    )

    result = toolbox.execute(request, _bundle())

    assert result.success is False
    assert result.data["error_code"] == error_code
    assert result.data["stage"] == "REQUEST_VALIDATION"
    assert broker.what_if_calls == []


def test_declared_vertical_accepts_consistent_structure(monkeypatch):
    broker = _ComboBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id="feasibility-vertical-ok",
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "action": "BUY",
            "currency": "USD",
            "exchange": "SMART",
            "legs": [
                _vertical_leg("BUY", 913925915, strike=15.0),
                _vertical_leg("SELL", 926221865, strike=18.0),
            ],
            "limit_price": "0.90",
            "order_type": "LMT",
            "quantity": "1",
            "sec_type": "BAG",
            "symbol": "IOVA",
            "structure": "VERTICAL",
        },
        purpose="authoritative paper vertical what-if",
    )

    result = toolbox.execute(request, _bundle())

    assert result.error is None
    assert result.success is True
    assert len(broker.what_if_calls) == 1


def test_generic_bag_without_vertical_declaration_remains_valid(monkeypatch):
    """A generic multi-leg combo that does not declare 'VERTICAL' must not be
    subject to vertical structural rules."""
    broker = _ComboBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id="feasibility-generic-bag",
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "action": "BUY",
            "currency": "USD",
            "exchange": "SMART",
            "legs": [
                _vertical_leg("BUY", 913925915, strike=15.0, right="C"),
                _vertical_leg("BUY", 926221865, strike=18.0, right="P"),
            ],
            "limit_price": "0.90",
            "order_type": "LMT",
            "quantity": "1",
            "sec_type": "BAG",
            "symbol": "IOVA",
            # no structure declaration
        },
        purpose="generic combo without vertical declaration stays valid",
    )

    result = toolbox.execute(request, _bundle())

    # Generic BAG: opposite sides / mixed right would not be a vertical, but
    # we did not declare one, so no vertical structural rule applies. The leg
    # identities are real and resolvable, so the request must reach what-if.
    assert result.error is None
    assert result.success is True
    assert len(broker.what_if_calls) == 1


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


def test_flat_runtime_request_accepts_canonical_nested_contract(monkeypatch):
    broker = WhatIfOnlyBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id="feasibility-nested-contract",
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "action": "BUY",
            "contract": {
                "conId": 482880561,
                "symbol": "GENI",
                "secType": "STK",
                "exchange": "SMART",
                "currency": "USD",
            },
            "quantity": 40,
            "order_type": "LMT",
            "limit_price": 6.32,
        },
        purpose="accept canonical broker-resolved identity",
    )

    result = toolbox.execute(request, _bundle())

    assert result.success is True
    assert broker.qualified_contracts[0].conId == 482880561
    assert len(broker.what_if_calls) == 1


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
            "BROKER_ECONOMICS_SENTINEL_DETECTED",
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
    if error_code == "BROKER_ECONOMICS_SENTINEL_DETECTED":
        assert result.error == "BROKER_WHATIF_DBL_MAX_SENTINEL"
        assert result.data["error_code"] == "BROKER_ECONOMICS_SENTINEL_DETECTED"
        assert result.data["what_if_status"] == "BROKER_ECONOMICS_NOT_COMPUTED"
        assert result.data["broker_whatif_reached"] is True
        assert result.data["broker_economics_computed"] is False
        assert result.data["stage"] == "WHAT_IF_NORMALIZATION"
    else:
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


# ---------------------------------------------------------------------------
# What-if evidence semantics (second-audit hardening)
# ---------------------------------------------------------------------------


def test_what_if_none_returns_broker_whatif_reached_not_computed(monkeypatch):
    broker = WhatIfOnlyBroker()
    broker.whatIfOrder = lambda _c, _o: None
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id="feasibility-whatif-none",
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "action": "BUY",
            "conId": 911011733,
            "order_type": "LMT",
            "limit_price": 6.32,
            "quantity": 40,
            "sec_type": "STK",
            "symbol": "GENI",
        },
        purpose="what-if returned None",
    )

    result = toolbox.execute(request, _bundle())

    assert result.success is False
    assert result.data["what_if_status"] == "BROKER_WHATIF_NO_RESPONSE"
    assert result.data["broker_whatif_reached"] is False
    assert result.data["broker_economics_computed"] is False
    assert "error_code" not in result.data


@pytest.mark.parametrize(
    ("sentinel_value", "field"),
    (
        (float("inf"), "commission"),
        (float("-inf"), "commission"),
        (float("nan"), "commission"),
        (1.7976931348623157e308, "commission"),
        ("1.7976931348623157E308", "commission"),
        ("1.7976931348623157E+308", "commission"),
        ("INF", "commission"),
        ("NAN", "commission"),
    ),
)
def test_exact_ibkr_sentinel_rejects_economics(monkeypatch, sentinel_value, field):
    """The exact IBKR DBL_MAX sentinel and its string form must be detected."""

    class SentinelBroker(WhatIfOnlyBroker):
        def whatIfOrder(self, contract, order):
            base = {
                "commission": 0.0,
                "minCommission": 0.0,
                "maxCommission": 0.0,
                "initMarginBefore": 0.0,
                "initMarginChange": 0.0,
                "initMarginAfter": 0.0,
                "maintMarginBefore": 0.0,
                "maintMarginChange": 0.0,
                "maintMarginAfter": 0.0,
                "equityWithLoanBefore": 0.0,
                "equityWithLoanChange": 0.0,
                "equityWithLoanAfter": 0.0,
                "warningText": "",
            }
            base[field] = sentinel_value
            return SimpleNamespace(**base)

    broker = SentinelBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id=f"feasibility-sentinel-{field}",
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "action": "BUY",
            "conId": 911011733,
            "order_type": "LMT",
            "limit_price": 6.32,
            "quantity": 40,
            "sec_type": "STK",
            "symbol": "GENI",
        },
        purpose="exact IBKR sentinel detection",
    )

    result = toolbox.execute(request, _bundle())

    assert result.success is False
    assert result.data["what_if_status"] == "BROKER_ECONOMICS_NOT_COMPUTED"
    assert result.data["broker_whatif_reached"] is True
    assert result.data["broker_economics_computed"] is False
    assert result.data["error_code"] == "BROKER_ECONOMICS_SENTINEL_DETECTED"
    assert result.data[field] is None


def test_zero_and_ordinary_economics_are_valid(monkeypatch):
    """Zero commissions/margins and ordinary finite values must not be
    confused with the IBKR sentinel."""

    class CleanBroker(WhatIfOnlyBroker):
        def whatIfOrder(self, contract, order):
            return SimpleNamespace(
                commission=0.0,
                minCommission=0.0,
                maxCommission=0.0,
                initMarginBefore=0.0,
                initMarginChange=252.80,
                initMarginAfter=252.80,
                maintMarginBefore=0.0,
                maintMarginChange=252.80,
                maintMarginAfter=252.80,
                equityWithLoanBefore=500.0,
                equityWithLoanChange=-252.80,
                equityWithLoanAfter=247.20,
                warningText="",
            )

    broker = CleanBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id="feasibility-clean",
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "action": "BUY",
            "conId": 911011733,
            "order_type": "LMT",
            "limit_price": 6.32,
            "quantity": 40,
            "sec_type": "STK",
            "symbol": "GENI",
        },
        purpose="ordinary economics must be accepted",
    )

    result = toolbox.execute(request, _bundle())

    assert result.success is True
    assert result.data["broker_whatif_reached"] is True
    assert result.data["broker_economics_computed"] is True
    assert result.data["commission"] == 0.0
    assert result.data["initMarginChange"] == 252.80


def test_what_if_dbl_max_sentinel_rejects_economics(monkeypatch):
    class SentinelBroker(WhatIfOnlyBroker):
        def whatIfOrder(self, contract, order):
            state = SimpleNamespace(
                commission=float("inf"),
                minCommission=float("inf"),
                maxCommission=1.0,
                initMarginBefore=float("inf"),
                initMarginChange=0.0,
                initMarginAfter=0.0,
                maintMarginBefore=0.0,
                maintMarginChange=0.0,
                maintMarginAfter=0.0,
                equityWithLoanBefore=0.0,
                equityWithLoanChange=0.0,
                equityWithLoanAfter=0.0,
                warningText="",
            )
            return state

    broker = SentinelBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id="feasibility-dblmax",
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "action": "BUY",
            "conId": 911011733,
            "order_type": "LMT",
            "limit_price": 6.32,
            "quantity": 40,
            "sec_type": "STK",
            "symbol": "GENI",
        },
        purpose="detect IBKR DBL_MAX sentinel",
    )

    result = toolbox.execute(request, _bundle())

    assert result.success is False
    assert result.data["what_if_status"] == "BROKER_ECONOMICS_NOT_COMPUTED"
    assert result.data["broker_whatif_reached"] is True
    assert result.data["broker_economics_computed"] is False
    assert result.data["error_code"] == "BROKER_ECONOMICS_SENTINEL_DETECTED"
    assert result.data["commission"] is None
    assert result.data["minCommission"] is None
    assert result.data["maxCommission"] == 1.0


def test_exactly_one_what_if_evidence_definition_exists():
    """Dead/shadowed definitions in broker-safety code are unacceptable."""
    import inspect

    source = inspect.getsource(IBKRResearchToolbox)
    count = source.count("def _what_if_evidence(")
    assert count == 1, f"expected exactly one _what_if_evidence, found {count}"
