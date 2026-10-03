"""Session-evidence reader tests — production Day1 wiring + toolbox behavior.

Proves the production Day1 construction path supplies a real broker-backed
session_evidence_reader, and that the reader derives liquid_hours,
timezone_id, and has_open_orders from the existing read-only IBKR path only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import ibkr_paper_30d.day1_launch as launch_module
from ibkr_paper_30d.autonomous_service import AutonomousExperimentService
from ibkr_paper_30d.ibkr_research_tools import IBKRResearchToolbox
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.session_orchestration import OrchestrationAction
from ibkr_paper_30d.types import new_uuid7

from test_day1_launch import (
    StopTestService,
    install_fake_lock,
    passing_context,
)


# ---------------------------------------------------------------------------
# Fake broker plumbing for the toolbox session-evidence reader
# ---------------------------------------------------------------------------


class _FakeContract:
    def __init__(self, symbol, conId):
        self.symbol = symbol
        self.secType = "STK"
        self.exchange = "SMART"
        self.currency = "USD"
        self.conId = conId
        self.localSymbol = symbol
        self.primaryExchange = ""
        self.lastTradeDateOrContractMonth = ""
        self.strike = 0
        self.right = ""
        self.multiplier = ""


class _FakeDetails:
    def __init__(self, symbol, conId, liquidHours, timeZoneId):
        self.contract = _FakeContract(symbol, conId)
        self.liquidHours = liquidHours
        self.timeZoneId = timeZoneId


class _FakeOrder:
    def __init__(self, orderRef):
        self.orderRef = orderRef


class _FakeTrade:
    def __init__(self, order_ref, order_id=1, perm_id=2, client_id=3):
        self.order = _FakeOrder(order_ref)
        self.order.orderId = order_id
        self.order.permId = perm_id
        self.order.clientId = client_id
        self.order.account = "DUXXXX"
        self.order.action = "BUY"
        self.order.orderType = "LMT"
        self.order.totalQuantity = 1
        self.order.lmtPrice = 5.0
        self.order.tif = "DAY"
        self.order.goodTillDate = ""
        self.order.outsideRth = False
        self.order.parentId = 0
        self.order.ocaGroup = ""
        self.order.transmit = True
        self.order.conditions = []
        self.order.goodAfterTime = ""
        self.order.smartComboRoutingParams = []
        self.order.algoStrategy = ""
        self.order.algoParams = []
        self.order.orderMiscOptions = []
        self.orderStatus = SimpleNamespace(
            status="Submitted", filled=0, remaining=1, avgFillPrice=0
        )
        self.fills = []
        self.contract = _FakeContract("GENI", 1)


class FakeSessionIBKR:
    """Read-only IBKR stand-in: contractDetails + open orders."""

    def __init__(
        self,
        *,
        liquid_hours="20261005:0930-20261005:1600",
        timezone_id="US/Eastern",
        open_order_refs=(),
        now_utc=None,
        per_symbol=None,
    ):
        """per_symbol: dict[str, {"liquidHours": ..., "timeZoneId": ...}]
        overriding the global defaults for specific symbols."""
        from ibkr_paper_30d.market_policy import MarketPolicyFreezer

        self._liquid_hours = liquid_hours
        self._timezone_id = timezone_id
        self._open_order_refs = list(open_order_refs)
        self._per_symbol = per_symbol or {}
        self._now_utc = now_utc or datetime(2026, 10, 5, 14, 0, 0, tzinfo=timezone.utc)
        self._symbols = sorted(MarketPolicyFreezer.REQUIRED_SYMBOLS)
        self._conIds = {sym: 1000 + i for i, sym in enumerate(self._symbols)}
        self.disconnected = False

    def reqCurrentTime(self):
        return self._now_utc

    def reqContractDetails(self, contract):
        sym = str(getattr(contract, "symbol", ""))
        if sym not in self._conIds:
            return []
        override = self._per_symbol.get(sym, {})
        lh = override.get("liquidHours", self._liquid_hours)
        tz = override.get("timeZoneId", self._timezone_id)
        if not lh or not tz:
            return []
        return [
            _FakeDetails(
                sym,
                self._conIds[sym],
                lh,
                tz,
            )
        ]

    def reqAllOpenOrders(self):
        return [_FakeTrade(ref) for ref in self._open_order_refs]

    def disconnect(self):
        self.disconnected = True


def _toolbox_with(fake_broker):
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    toolbox._connect = lambda **kwargs: fake_broker
    return toolbox, fake_broker


# ---------------------------------------------------------------------------
# Toolbox reader correctness
# ---------------------------------------------------------------------------


def test_session_evidence_returns_liquid_hours_timezone_and_no_open_orders():
    toolbox, broker = _toolbox_with(
        FakeSessionIBKR(
            liquid_hours="20261005:0930-20261005:1600",
            timezone_id="US/Eastern",
        )
    )

    evidence = toolbox.session_evidence(reference_symbols=("SPY", "QQQ", "IEF"))

    assert evidence is not None
    assert evidence["liquid_hours"] == "20261005:0930-20261005:1600"
    assert evidence["timezone_id"] == "US/Eastern"
    assert evidence["has_open_orders"] is False


def test_session_evidence_detects_experiment_open_order():
    toolbox, broker = _toolbox_with(
        FakeSessionIBKR(open_order_refs=["codex-ibkr-paper-30d-a-abc1"])
    )

    evidence = toolbox.session_evidence(reference_symbols=("SPY", "QQQ", "IEF"))

    assert evidence is not None
    assert evidence["has_open_orders"] is True


def test_session_evidence_ignores_non_experiment_orders():
    toolbox, broker = _toolbox_with(
        FakeSessionIBKR(open_order_refs=["manual-order-ref"])
    )

    evidence = toolbox.session_evidence(reference_symbols=("SPY", "QQQ", "IEF"))

    assert evidence is not None
    assert evidence["has_open_orders"] is False


def test_session_evidence_returns_none_when_calendar_unavailable():
    toolbox, broker = _toolbox_with(
        FakeSessionIBKR(
            liquid_hours="", timezone_id=""
        )
    )
    # simulate resolution failure on every reference symbol
    broker.reqContractDetails = lambda contract: []

    evidence = toolbox.session_evidence(reference_symbols=("SPY", "QQQ", "IEF"))

    assert evidence is None


def test_session_evidence_returns_none_on_broker_failure():
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)

    def boom(**kwargs):
        raise ConnectionError("no gateway")

    toolbox._connect = boom

    assert toolbox.session_evidence(reference_symbols=("SPY", "QQQ", "IEF")) is None


# ---------------------------------------------------------------------------
# Regression: no hard-coded reference duplication in research layer
# ---------------------------------------------------------------------------


def test_research_tools_contain_no_hard_coded_session_reference_set():
    """The autonomous research layer must never duplicate the calibration
    reference symbols; they must come from the orchestration/policy caller."""
    import inspect

    source = inspect.getsource(IBKRResearchToolbox.session_evidence)
    assert "SPY" not in source
    assert "QQQ" not in source
    assert "IEF" not in source
    assert "_SESSION_EVIDENCE_PROBES" not in source


def test_mandate_still_has_no_predefined_symbol_universe():
    """No matter how session evidence resolves reference symbols, the
    autonomous mandate must remain without a predefined trading universe."""
    from ibkr_paper_30d.autonomous_research import CodexAutonomousCLIProvider
    from ibkr_paper_30d.trader_invocation import InvocationRequest, TraderInputBundle

    req = InvocationRequest(
        decision_cycle_id="c1",
        invocation_id="i1",
        utc_timestamp="2026-10-03T00:00:00Z",
        requested_model="m1",
        actual_model="m1",
        model_configuration={},
        reasoning_effort="medium",
        input_bundle_sha256="a" * 64,
        risk_policy_version="R1",
        experiment_id="e1",
        invocation_trigger="TEST",
        timeout_seconds=60,
    )
    bundle = TraderInputBundle(
        decision_cycle_id="c1",
        utc_timestamp="2026-10-03T00:00:00Z",
        market_session_state="REGULAR",
        reconciliation_receipt={"status": "PASS"},
        experiment_subledger_snapshot={"equity": "500.00"},
        broker_account_snapshot={"buying_power": "500.00"},
        positions_snapshot=[],
        open_orders_snapshot=[],
        risk_snapshot={"policy": "R1"},
        kill_switch_state="CLEAR",
        market_data_snapshot={"gate_status": "PASS"},
        candidate_screen_results=[],
        relevant_previous_immutable_decisions=[],
        process_policy_version="V1",
        execution_realism_version="PAPER_V1",
        benchmark_state={},
    )
    payload = CodexAutonomousCLIProvider._prompt_payload(req, bundle, [], [])
    assert payload["mandate"]["predefined_symbol_universe"] is False


# ---------------------------------------------------------------------------
# Production construction path wiring (requirement A)
# ---------------------------------------------------------------------------


def test_production_day1_construction_supplies_session_evidence_reader(tmp_path):
    """Day1 must hand AutonomousExperimentService a non-None session evidence
    reader through the real construction path."""
    ctx = passing_context(tmp_path)
    install_fake_lock(ctx)
    captured = {}

    def spy_factory(db, **kwargs):
        captured.update(kwargs)
        service = Mock()
        service.run_forever.side_effect = StopTestService
        return service

    ctx.dependencies.service_factory = spy_factory

    with pytest.raises(StopTestService):
        launch_module.run_day1_launch(ctx.config, ctx.dependencies)

    reader = captured.get("session_evidence_reader")
    assert reader is not None, "production service_factory never received session_evidence_reader"
    assert callable(reader)


def test_production_session_evidence_reader_is_broker_backed(tmp_path):
    """The production reader must resolve through the prepared toolbox's
    read-only IBKR path, not a static hard-coded value."""
    ctx = passing_context(tmp_path)
    install_fake_lock(ctx)
    captured = {}

    real_toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    fake_broker = FakeSessionIBKR()
    real_toolbox._connect = lambda **kwargs: fake_broker

    def record_service_factory(db, **kwargs):
        captured.update(kwargs)
        service = Mock()
        service.run_forever.side_effect = StopTestService
        return service

    ctx.dependencies.service_factory = record_service_factory
    ctx.dependencies.research_toolbox_factory = (
        lambda workspace, _preflight: launch_module.AutonomyToolbox(
            real_toolbox, workspace
        )
    )

    with pytest.raises(StopTestService):
        launch_module.run_day1_launch(ctx.config, ctx.dependencies)

    reader = captured.get("session_evidence_reader")
    assert reader is not None
    evidence = reader()
    assert evidence is not None
    assert evidence["liquid_hours"] == "20261005:0930-20261005:1600"
    assert evidence["timezone_id"] == "US/Eastern"
    assert isinstance(evidence["has_open_orders"], bool)


# ---------------------------------------------------------------------------
# Consensus / ALL-reference-requirement tests (second-audit hardening)
# ---------------------------------------------------------------------------


CONSENSUS_SYMBOLS = ("SPY", "QQQ", "IEF")


def test_all_references_regular_consensus_is_usable():
    """When all references agree on REGULAR at the same broker time,
    evidence is usable."""
    toolbox, broker = _toolbox_with(
        FakeSessionIBKR(
            liquid_hours="20261005:0930-20261005:1600",
            timezone_id="US/Eastern",
        )
    )
    evidence = toolbox.session_evidence(reference_symbols=CONSENSUS_SYMBOLS)
    assert evidence is not None
    assert evidence["session"] == "REGULAR"
    assert evidence["broker_time_utc"] is not None
    assert broker.disconnected is True


def test_all_references_after_hours_consensus_is_usable():
    """When all references agree on AFTER_HOURS, evidence is usable."""
    toolbox, broker = _toolbox_with(
        FakeSessionIBKR(
            liquid_hours="20261005:0930-20261005:1600",
            timezone_id="US/Eastern",
            now_utc=datetime(2026, 10, 5, 21, 0, 0, tzinfo=timezone.utc),
        )
    )
    evidence = toolbox.session_evidence(reference_symbols=CONSENSUS_SYMBOLS)
    assert evidence is not None
    assert evidence["session"] == "AFTER_HOURS"


def test_one_reference_missing_returns_none():
    """If one required reference cannot be resolved, fail-closed to None."""
    toolbox, broker = _toolbox_with(
        FakeSessionIBKR(
            per_symbol={
                "SPY": {"liquidHours": "20261005:0930-20261005:1600", "timeZoneId": "US/Eastern"},
                "QQQ": {"liquidHours": "", "timeZoneId": ""},
            }
        )
    )
    evidence = toolbox.session_evidence(reference_symbols=CONSENSUS_SYMBOLS)
    assert evidence is None


def test_references_disagree_session_returns_none():
    """One REGULAR and one AFTER_HOURS must fail-closed to None."""
    toolbox, broker = _toolbox_with(
        FakeSessionIBKR(
            per_symbol={
                "SPY": {"liquidHours": "20261005:0930-20261005:1600", "timeZoneId": "US/Eastern"},
                "QQQ": {"liquidHours": "20261005:0930-20261005:1600", "timeZoneId": "US/Eastern"},
                "IEF": {"liquidHours": "20261005:0930-20261005:1600", "timeZoneId": "US/Pacific"},
            }
        )
    )
    # IEF in US/Pacific at same UTC is AFTER_HOURS while SPY/QQQ are REGULAR
    evidence = toolbox.session_evidence(reference_symbols=CONSENSUS_SYMBOLS)
    assert evidence is None


def test_timezone_mismatch_returns_none():
    """References with incompatible timezones must fail-closed to None."""
    toolbox, broker = _toolbox_with(
        FakeSessionIBKR(
            per_symbol={
                "SPY": {"liquidHours": "20261005:0930-20261005:1600", "timeZoneId": "US/Eastern"},
                "QQQ": {"liquidHours": "20261005:0930-20261005:1600", "timeZoneId": "US/Eastern"},
                "IEF": {"liquidHours": "20261005:0930-20261005:1600", "timeZoneId": "US/Central"},
            }
        )
    )
    evidence = toolbox.session_evidence(reference_symbols=CONSENSUS_SYMBOLS)
    assert evidence is None


def test_malformed_liquid_hours_returns_none():
    toolbox, broker = _toolbox_with(
        FakeSessionIBKR(
            per_symbol={
                "SPY": {"liquidHours": "NOT_A_DATE:0930-1600", "timeZoneId": "US/Eastern"},
            }
        )
    )
    evidence = toolbox.session_evidence(reference_symbols=CONSENSUS_SYMBOLS)
    assert evidence is None


def test_broker_time_included_in_evidence():
    toolbox, broker = _toolbox_with(FakeSessionIBKR())
    evidence = toolbox.session_evidence(reference_symbols=CONSENSUS_SYMBOLS)
    assert evidence is not None
    assert "broker_time_utc" in evidence
    assert evidence["broker_time_utc"].endswith("Z")


def test_unrelated_manual_order_does_not_set_has_open_orders():
    toolbox, broker = _toolbox_with(
        FakeSessionIBKR(open_order_refs=["manual-123"])
    )
    evidence = toolbox.session_evidence(reference_symbols=CONSENSUS_SYMBOLS)
    assert evidence is not None
    assert evidence["has_open_orders"] is False


def test_experiment_order_sets_has_open_orders():
    toolbox, broker = _toolbox_with(
        FakeSessionIBKR(open_order_refs=["codex-ibkr-paper-30d-x-001"])
    )
    evidence = toolbox.session_evidence(reference_symbols=CONSENSUS_SYMBOLS)
    assert evidence is not None
    assert evidence["has_open_orders"] is True
