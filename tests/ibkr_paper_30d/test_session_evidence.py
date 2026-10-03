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
    ):
        from ibkr_paper_30d.market_policy import MarketPolicyFreezer

        self._liquid_hours = liquid_hours
        self._timezone_id = timezone_id
        self._open_order_refs = list(open_order_refs)
        self._symbols = sorted(MarketPolicyFreezer.REQUIRED_SYMBOLS)
        # per-symbol conIds
        self._conIds = {sym: 1000 + i for i, sym in enumerate(self._symbols)}
        self.disconnected = False

    def reqContractDetails(self, contract):
        sym = str(getattr(contract, "symbol", ""))
        if sym not in self._conIds:
            return []
        return [
            _FakeDetails(
                sym,
                self._conIds[sym],
                self._liquid_hours,
                self._timezone_id,
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

    evidence = toolbox.session_evidence()

    assert evidence is not None
    assert evidence["liquid_hours"] == "20261005:0930-20261005:1600"
    assert evidence["timezone_id"] == "US/Eastern"
    assert evidence["has_open_orders"] is False


def test_session_evidence_detects_experiment_open_order():
    toolbox, broker = _toolbox_with(
        FakeSessionIBKR(open_order_refs=["codex-ibkr-paper-30d-a-abc1"])
    )

    evidence = toolbox.session_evidence()

    assert evidence is not None
    assert evidence["has_open_orders"] is True


def test_session_evidence_ignores_non_experiment_orders():
    toolbox, broker = _toolbox_with(
        FakeSessionIBKR(open_order_refs=["manual-order-ref"])
    )

    evidence = toolbox.session_evidence()

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

    evidence = toolbox.session_evidence()

    assert evidence is None


def test_session_evidence_returns_none_on_broker_failure():
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)

    def boom(**kwargs):
        raise ConnectionError("no gateway")

    toolbox._connect = boom

    assert toolbox.session_evidence() is None


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
