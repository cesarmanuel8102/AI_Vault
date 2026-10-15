from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest


def test_what_if_without_broker_response_has_a_real_deadline():
    import subprocess
    import sys
    import textwrap

    # The subprocess bound also makes the pre-fix infinite wait testable.
    script = textwrap.dedent('''
        import asyncio
        from ib_insync import IB, Contract, Order
        from ibkr_paper_30d.ibkr_research_tools import IBKRResearchToolbox
        class SilentBroker(IB):
            async def whatIfOrderAsync(self, contract, order):
                await asyncio.Future()
        broker = SilentBroker()
        toolbox = IBKRResearchToolbox(timeout_seconds=0.02)
        try:
            toolbox._request_what_if(broker, Contract(), Order(whatIf=True, transmit=True))
        except TimeoutError:
            assert broker.RequestTimeout == 0
        else:
            raise AssertionError("missing timeout")
    ''')
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=5,
    )
    assert result.returncode == 0, result.stderr


def test_missing_what_if_fields_never_claim_computed_economics():
    from ib_insync import Contract

    broker = WhatIfOnlyBroker()
    broker.state = SimpleNamespace(warningText="")
    toolbox = IBKRResearchToolbox()
    evidence = toolbox._what_if_evidence(
        broker,
        Contract(secType="STK", exchange="SMART", currency="USD"),
        action="BUY", order_type="LMT", quantity=Decimal("0.2"),
        limit_price=Decimal("2422"), time_in_force="DAY",
    )
    assert evidence["success"] is False
    assert evidence["broker_economics_computed"] is False
    assert evidence["what_if_status"] == "BROKER_ECONOMICS_NOT_COMPUTED"
    assert broker.what_if_calls[0][1].tif == "DAY"


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_research_request_deadline_must_be_finite_positive(timeout):
    with pytest.raises(ValueError, match="finite positive"):
        IBKRResearchToolbox(timeout_seconds=timeout)


def test_what_if_timeout_is_actionable_without_transmitting_an_order():
    from ib_insync import Contract

    class TimedOutBroker(WhatIfOnlyBroker):
        def whatIfOrder(self, contract, order):
            assert self.RequestTimeout > 0
            assert order.whatIf is True
            raise TimeoutError()

    evidence = IBKRResearchToolbox()._what_if_evidence(
        TimedOutBroker(), Contract(secType="STK", exchange="SMART", currency="USD"),
        action="BUY", order_type="LMT", quantity=Decimal("0.2"),
        limit_price=Decimal("2422"), time_in_force="DAY",
    )
    assert evidence["error_code"] == "BROKER_WHATIF_TIMEOUT"
    assert evidence["broker_economics_computed"] is False
    assert evidence["requested_time_in_force"] == "DAY"


def test_qualified_crypto_proposal_reports_adapter_tif_without_rewriting():
    from ib_insync import Contract
    broker = WhatIfOnlyBroker()
    evidence = IBKRResearchToolbox()._what_if_evidence(
        broker, Contract(secType="CRYPTO", exchange="PAXOS", currency="USD"),
        action="BUY", order_type="LMT", quantity=Decimal("0.2"),
        limit_price=Decimal("2442"), time_in_force="DAY",
    )
    assert evidence["error_code"] == "BROKER_CRYPTO_BUY_IOC_REQUIRED"
    assert evidence["supported_adapter_time_in_force"] == ["IOC"]
    assert evidence["requested_time_in_force"] == "DAY"
    assert evidence["broker_whatif_reached"] is False
    assert broker.what_if_calls == []

from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.autonomous_research import (
    AutonomousTradeProposal,
    ResearchRequest,
    ResearchTool,
)
from ibkr_paper_30d.ibkr_research_tools import IBKRResearchToolbox
from ibkr_paper_30d.open_order_management import (
    EXECUTION_CLIENT_ID,
    canonical_contract_identity,
)
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


def test_crypto_proposal_qualification_does_not_assume_stock_routing():
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)

    class CryptoBroker(WhatIfOnlyBroker):
        def reqContractDetails(self, contract):
            self.qualified_contracts.append(contract)
            if contract.exchange == "SMART":
                return []
            assert contract.exchange == ""
            contract.exchange = "PAXOS"
            contract.conId = 495759171
            return [SimpleNamespace(contract=contract)]

    broker = CryptoBroker()
    proposal = SimpleNamespace(symbol="ETH", sec_type="CRYPTO", legs=[], product_family_sha256="a82d8a2e546cd4a33c9b4d9bf1b4dbb95739282f8ef65dcc2c5c97c6ffc8dcd7")
    contract = toolbox._proposal_contract(broker, proposal)
    assert contract.conId == 495759171
    assert contract.exchange == "PAXOS"


@pytest.mark.parametrize("case", ["missing", "ambiguous", "wrong_symbol", "wrong_currency", "no_venue"])
def test_crypto_proposal_qualification_rejects_unverified_identity(case):
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    contract = SimpleNamespace(symbol="ETH", secType="CRYPTO", currency="USD", exchange="PAXOS", conId=495759171)
    if case == "wrong_symbol":
        contract.symbol = "BTC"
    if case == "wrong_currency":
        contract.currency = "EUR"
    if case == "no_venue":
        contract.exchange = ""
    result = [] if case == "missing" else [contract, contract] if case == "ambiguous" else [contract]
    broker = SimpleNamespace(reqContractDetails=lambda _: [SimpleNamespace(contract=c) for c in result])
    proposal = SimpleNamespace(symbol="ETH", sec_type="CRYPTO", legs=[], product_family_sha256="a82d8a2e546cd4a33c9b4d9bf1b4dbb95739282f8ef65dcc2c5c97c6ffc8dcd7")
    with pytest.raises(LookupError):
        toolbox._proposal_contract(broker, proposal)


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
    assert {key: value for key, value in result.data["continuity_host_bindings"].items()
            if key != "canonical_contract_identity_v4"} == {
        "account_identity_sha256": "a" * 64,
        "contract_identity_sha256": sha256_json(
            canonical_contract_identity(contract)
        ),
        "execution_client_id": EXECUTION_CLIENT_ID,
    }
    assert broker.disconnected is True


def test_nested_contract_and_order_request_reaches_authoritative_what_if(
    monkeypatch,
):
    broker = WhatIfOnlyBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id="feasibility-nested-crypto-order",
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "contract": {
                "conId": 479624278,
                "symbol": "BTC",
                "secType": "CRYPTO",
                "exchange": "PAXOS",
                "currency": "USD",
            },
            "order": {
                "action": "BUY",
                "orderType": "LMT",
                "totalQuantity": "0.001",
                "lmtPrice": "84000",
                "tif": "IOC",
            },
        },
        purpose="authoritative nested PAPER what-if",
    )

    result = toolbox.execute(request, _bundle())

    assert result.success is True
    assert result.error is None
    assert len(broker.what_if_calls) == 1
    contract, order = broker.what_if_calls[0]
    assert contract.conId == 479624278
    assert contract.secType == "CRYPTO"
    assert order.action == "BUY"
    assert order.orderType == "LMT"
    assert Decimal(str(order.totalQuantity)) == Decimal("0.001")
    assert Decimal(str(order.lmtPrice)) == Decimal("84000")
    assert order.tif == "IOC"


def test_nested_order_conflict_fails_before_broker(monkeypatch):
    broker = WhatIfOnlyBroker()
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id="feasibility-nested-order-conflict",
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "con_id": 479624278,
            "action": "SELL",
            "order": {
                "action": "BUY",
                "order_type": "LMT",
                "quantity": "0.001",
                "limit_price": "84000",
                "time_in_force": "IOC",
            },
        },
        purpose="reject contradictory nested order authority",
    )

    result = toolbox.execute(request, _bundle())

    assert result.success is False
    assert result.data["error_code"] == "ORDER_ARGUMENT_IDENTITY_CONFLICT"
    assert broker.what_if_calls == []


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


def test_crypto_cash_buy_uses_bounded_debit_when_margin_is_not_applicable(
    monkeypatch,
):
    broker = WhatIfOnlyBroker(
        state=_order_state(
            commission="0.251373",
            minCommission=float("inf"),
            maxCommission=float("inf"),
            initMarginChange=float("inf"),
            maintMarginChange=float("inf"),
            equityWithLoanChange=float("inf"),
        )
    )
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id="crypto-cash-debit",
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "action": "BUY",
            "con_id": 479624278,
            "symbol": "BTC",
            "security_type": "CRYPTO",
            "exchange": "PAXOS",
            "currency": "USD",
            "quantity": "0.0003",
            "order_type": "LMT",
            "limit_price": "83791.00",
            "time_in_force": "IOC",
        },
        purpose="bound a fully paid PAPER crypto purchase",
    )

    result = toolbox.execute(request, _bundle())

    assert result.success is True
    assert result.error is None
    assert result.data["what_if_status"] == "BROKER_CASH_DEBIT_COMPUTED"
    assert result.data["economic_basis"] == "BROKER_COMMISSION_PLUS_LIMIT_CASH_DEBIT"
    assert result.data["cash_notional_usd"] == "25.137300"
    assert result.data["estimated_commission_usd"] == "0.251373"
    assert result.data["maximum_cash_debit_usd"] == "25.388673"
    assert result.data["broker_economics_computed"] is True
    assert result.data["initMarginChange"] is None
    assert result.data["maintMarginChange"] is None


def test_crypto_cash_buy_rejects_unsupported_tif_before_broker(monkeypatch):
    broker = WhatIfOnlyBroker(state=_order_state(commission="0.25"))
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id="crypto-buy-day-is-not-supported",
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "action": "BUY",
            "con_id": 479624278,
            "symbol": "BTC",
            "security_type": "CRYPTO",
            "exchange": "PAXOS",
            "currency": "USD",
            "quantity": "0.0003",
            "order_type": "LMT",
            "limit_price": "83791.00",
            "time_in_force": "DAY",
        },
        purpose="return the exact broker constraint to the autonomous model",
    )

    result = toolbox.execute(request, _bundle())

    assert result.success is False
    assert result.error == "BROKER_FEASIBILITY_ARGUMENTS_INVALID"
    assert result.data["error_code"] == "BROKER_CRYPTO_BUY_IOC_REQUIRED"
    assert result.data["stage"] == "REQUEST_VALIDATION"
    assert broker.what_if_calls == []


@pytest.mark.parametrize(
    ("security_type", "action", "order_type", "limit_price", "time_in_force"),
    (
        ("STK", "BUY", "LMT", "10.00", "IOC"),
        ("CRYPTO", "SELL", "LMT", "83791.00", "IOC"),
        ("CRYPTO", "BUY", "MKT", None, "IOC"),
    ),
)
def test_margin_sentinel_cash_debit_path_is_strictly_scoped(
    monkeypatch, security_type, action, order_type, limit_price, time_in_force
):
    broker = WhatIfOnlyBroker(
        state=_order_state(
            commission="0.25",
            minCommission=float("inf"),
            maxCommission=float("inf"),
            initMarginChange=float("inf"),
            maintMarginChange=float("inf"),
        )
    )
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id=(
            f"strict-cash-debit-{security_type}-{action}-{order_type}-{time_in_force}"
        ),
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "action": action,
            "con_id": 479624278,
            "symbol": "BTC" if security_type == "CRYPTO" else "GENI",
            "security_type": security_type,
            "exchange": "PAXOS" if security_type == "CRYPTO" else "SMART",
            "currency": "USD",
            "quantity": "0.0003" if security_type == "CRYPTO" else "1",
            "order_type": order_type,
            "limit_price": limit_price,
            "time_in_force": time_in_force,
        },
        purpose="prove the cash-debit exception cannot broaden",
    )

    result = toolbox.execute(request, _bundle())

    assert result.success is False
    assert result.data["error_code"] == "BROKER_ECONOMICS_SENTINEL_DETECTED"
    assert result.data["broker_economics_computed"] is False


@pytest.mark.parametrize(
    "state_updates",
    (
        {
            # Observed for XP, VEEA, ALEC, and PCVX stock what-if responses.
            "commission": 1.000036,
            "minCommission": 1.7976931348623157e308,
            "maxCommission": 1.7976931348623157e308,
            "initMarginBefore": 1.7976931348623157e308,
            "initMarginChange": "134.71",
            "initMarginAfter": 1.7976931348623157e308,
            "maintMarginBefore": 1.7976931348623157e308,
            "maintMarginChange": "122.47",
            "maintMarginAfter": 1.7976931348623157e308,
            "equityWithLoanBefore": 1.7976931348623157e308,
            "equityWithLoanChange": "-0.95",
            "equityWithLoanAfter": 1.7976931348623157e308,
        },
        {
            # Observed for BEAT, PDSB, NVAX, and option-combo what-if responses.
            "commission": 1.7976931348623157e308,
            "minCommission": 2.1515,
            "maxCommission": 2.5015,
            "initMarginBefore": 1.7976931348623157e308,
            "initMarginChange": "351.86",
            "initMarginAfter": 1.7976931348623157e308,
            "maintMarginBefore": 1.7976931348623157e308,
            "maintMarginChange": "320.19",
            "maintMarginAfter": 1.7976931348623157e308,
            "equityWithLoanBefore": 1.7976931348623157e308,
            "equityWithLoanChange": "1.31",
            "equityWithLoanAfter": 1.7976931348623157e308,
        },
    ),
)
def test_research_what_if_accepts_observed_ibkr_optional_sentinels(
    monkeypatch, state_updates
):
    broker = WhatIfOnlyBroker(state=_order_state(**state_updates))
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)
    request = ResearchRequest(
        request_id="feasibility-observed-optional-sentinels",
        tool=ResearchTool.BROKER_FEASIBILITY,
        arguments={
            "action": "BUY",
            "con_id": 482880561,
            "quantity": 40,
            "order_type": "LMT",
            "limit_price": 6.32,
            "time_in_force": "DAY",
        },
        purpose="accept authoritative economics when only optional fields are sentinel",
    )

    result = toolbox.execute(request, _bundle())

    assert result.success is True
    assert result.data["what_if_status"] == "BROKER_ECONOMICS_COMPUTED"
    assert result.data["broker_whatif_reached"] is True
    assert result.data["broker_economics_computed"] is True
    assert result.data["initMarginChange"] == state_updates["initMarginChange"]
    assert result.data["maintMarginChange"] == state_updates["maintMarginChange"]
    assert "initMarginBefore" not in result.data
    assert "initMarginAfter" not in result.data
    assert "equityWithLoanBefore" not in result.data
    assert "equityWithLoanAfter" not in result.data


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
    assert result.error == "BROKER_WHATIF_TIMEOUT"
    assert result.data["error_type"] == "TimeoutError"
    assert result.data["error_code"] == "BROKER_WHATIF_TIMEOUT"
    assert result.data["stage"] == "WHAT_IF_REQUEST"
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
def test_exact_ibkr_sentinel_is_sanitized_when_alternate_commission_exists(
    monkeypatch, sentinel_value, field
):
    """A sentinel commission is optional when a finite range is authoritative."""

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

    assert result.success is True
    assert result.data["what_if_status"] == "BROKER_ECONOMICS_COMPUTED"
    assert result.data["broker_whatif_reached"] is True
    assert result.data["broker_economics_computed"] is True
    assert result.data[field] is None
    assert result.data["minCommission"] == 0.0
    assert result.data["maxCommission"] == 0.0


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
                maxCommission=float("inf"),
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
    assert result.data["maxCommission"] is None


def test_exactly_one_what_if_evidence_definition_exists():
    """Dead/shadowed definitions in broker-safety code are unacceptable."""
    import inspect

    source = inspect.getsource(IBKRResearchToolbox)
    count = source.count("def _what_if_evidence(")
    assert count == 1, f"expected exactly one _what_if_evidence, found {count}"
