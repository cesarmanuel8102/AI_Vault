from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from ibkr_paper_30d.autonomous_research import (
    AutonomousTradeProposal,
    ProposalLeg,
)
from ibkr_paper_30d.autonomous_runtime import build_request
from ibkr_paper_30d.experiment_control import (
    ExperimentClockStore,
    ExperimentControlError,
    KillSwitchStore,
    OwnerAuthorizationStore,
)
from ibkr_paper_30d.experiment_ledger import AutonomousExperimentLedger
from ibkr_paper_30d.ibkr_research_tools import IBKRResearchToolbox
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.reporting import FaultInjectionHarness
from ibkr_paper_30d.trader_invocation import TraderInputBundle


def bundle(equity="500.00") -> TraderInputBundle:
    return TraderInputBundle(
        decision_cycle_id="cycle-remediation-1",
        utc_timestamp="2026-09-21T13:30:00Z",
        market_session_state="REGULAR",
        reconciliation_receipt={"status": "PASS"},
        experiment_subledger_snapshot={
            "allocation": "500.00",
            "equity": equity,
        },
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
        experiment_clock={"remaining_days": 30},
    )


def proposal(**updates) -> AutonomousTradeProposal:
    values = dict(
        thesis="test",
        catalyst="test",
        symbol="XYZ",
        sec_type="OPT",
        direction="LONG",
        action="BUY",
        quantity="1",
        order_type="LMT",
        limit_price="1.00",
        expiry="20261016",
        strike="40",
        right="C",
        legs=[],
        capital_required="999.00",
        maximum_loss="100.00",
        loss_is_bounded=True,
        probability_profit="0.55",
        probability_loss="0.45",
        expected_gain="150",
        expected_loss="100",
        expected_value="37.5",
        expected_reward_risk="1.5",
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
    values.update(updates)
    return AutonomousTradeProposal(**values)


def test_experiment_clock_is_persisted_and_immutable_across_restart(tmp_path):
    start = datetime(2026, 9, 21, 13, 30, tzinfo=timezone.utc)
    with Database.open(tmp_path / "clock.sqlite3") as db:
        store = ExperimentClockStore(db)
        first = store.initialize_or_load(
            requested_start_utc=start,
            duration_days=30,
            initial_allocation=Decimal("500.00"),
        )
        restarted = store.initialize_or_load(
            requested_start_utc=None,
            duration_days=30,
            initial_allocation=Decimal("500.00"),
        )
        assert restarted.start_utc == first.start_utc
        assert restarted.end_utc == first.end_utc
        with pytest.raises(ExperimentControlError, match="EXPERIMENT_START_IMMUTABLE"):
            store.initialize_or_load(
                requested_start_utc=datetime(2026, 9, 22, 13, 30, tzinfo=timezone.utc),
                duration_days=30,
                initial_allocation=Decimal("500.00"),
            )


def test_kill_switch_has_production_write_and_read_path(tmp_path):
    with Database.open(tmp_path / "kill.sqlite3") as db:
        store = KillSwitchStore(db)
        assert store.current() == "KILL_SWITCH_TRIGGERED"
        store.set("KILL_SWITCH_CLEAR", reason="operator start")
        assert store.current() == "KILL_SWITCH_CLEAR"
        store.set("KILL_SWITCH_TRIGGERED", reason="operator halt")
        assert store.current() == "KILL_SWITCH_TRIGGERED"


def test_missing_exec_id_gets_deterministic_dedup_key(tmp_path):
    fill = {
        "execution_id_hash": None,
        "orderRef": "codex-ibkr-paper-30d-a-test",
        "permId": 10,
        "orderId": 11,
        "clientId": 12,
        "execution_time": "2026-09-21T13:31:00Z",
        "cumQty": "1",
        "avgPrice": "2.00",
        "side": "BUY",
        "quantity": "1",
        "price": "2.00",
        "commission": "1.00",
        "contract": {
            "conId": 123,
            "symbol": "XYZ",
            "secType": "OPT",
            "multiplier": "100",
        },
    }
    with Database.open(tmp_path / "ledger.sqlite3") as db:
        ledger = AutonomousExperimentLedger(db)
        first = ledger.record_fill(fill)
        second = ledger.record_fill(fill)
        assert not first.startswith("duplicate:")
        assert second.startswith("duplicate:")
        state = ledger.project()
        assert state.event_count == 1
        assert state.equity == Decimal("499.00")


def test_autonomous_ledger_detects_inserted_broken_hash_chain(tmp_path):
    with Database.open(tmp_path / "ledger.sqlite3") as db:
        ledger = AutonomousExperimentLedger(db)
        ledger.record_mark(contract_id=123, price=Decimal("1.00"), symbol="XYZ")
        payload = {
            "schema": ledger.SCHEMA,
            "event_type": "MARK",
            "contract_id": 123,
            "symbol": "XYZ",
            "price": "2.00",
        }
        db.execute(
            "INSERT INTO autonomous_ledger_events("
            "event_id,event_type,payload_json,payload_sha256,"
            "previous_event_sha256,event_sha256,created_at_utc"
            ") VALUES(?,?,?,?,?,?,?)",
            (
                "tampered",
                "MARK",
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                "0" * 64,
                "0" * 64,
                "1" * 64,
                "2026-09-21T13:32:00Z",
            ),
        )
        state = ledger.project()
        assert state.valid is False
        assert any("LEDGER_" in reason for reason in state.reason_codes)


class WhatIfNoneBroker:
    def disconnect(self):
        pass

    def whatIfOrder(self, contract, order):
        return None


def test_broker_whatif_none_is_fail_closed(monkeypatch):
    toolbox = IBKRResearchToolbox(
        expected_account_hash="a" * 64,
        declared_options_level=4,
    )
    monkeypatch.setattr(toolbox, "_proposal_contract", lambda ib, p: SimpleNamespace(
        conId=123,
        symbol="XYZ",
        localSymbol="XYZ",
        secType="OPT",
        exchange="SMART",
        primaryExchange="",
        currency="USD",
        lastTradeDateOrContractMonth="20261016",
        strike=40,
        right="C",
        multiplier="100",
    ))
    result = toolbox._broker_feasibility(proposal(), ib=WhatIfNoneBroker())
    assert result["success"] is False
    assert result["error"] == "WHAT_IF_RETURNED_NONE"


def test_missing_margin_or_commission_evidence_blocks():
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    ok, reasons = toolbox._feasibility_common(
        {
            "success": True,
            "warningText": "",
            "initMarginChange": None,
            "maintMarginChange": None,
            "commission": None,
            "minCommission": None,
            "maxCommission": None,
        },
        equity=Decimal("500"),
    )
    assert ok is False
    assert reasons == ("BROKER_MARGIN_EVIDENCE_MISSING",)


def test_multi_leg_market_buy_cannot_use_model_capital_as_loss_floor():
    p = proposal(
        order_type="MKT",
        limit_price=None,
        strike=None,
        right=None,
        legs=[
            ProposalLeg(
                symbol="XYZ",
                sec_type="OPT",
                action="BUY",
                ratio=1,
                expiry="20261016",
                strike="40",
                right="C",
            ),
            ProposalLeg(
                symbol="XYZ",
                sec_type="OPT",
                action="SELL",
                ratio=1,
                expiry="20261016",
                strike="45",
                right="C",
            ),
        ],
    )
    floor, reason = IBKRResearchToolbox._structure_loss_floor(p, bundle())
    assert floor is None
    assert reason == "MULTI_LEG_BUY_COST_NOT_PRETRADE_BOUNDED"


def test_runtime_rejects_lower_model_or_reasoning_floor():
    value = bundle()
    with pytest.raises(ValueError, match="gpt-5.6-sol"):
        build_request(
            value,
            model="gpt-5.5",
            reasoning_effort="max",
            experiment_id="x",
            timeout_seconds=60,
            trigger="SCHEDULED_SCAN",
        )
    with pytest.raises(ValueError, match="max reasoning"):
        build_request(
            value,
            model="gpt-5.6-sol",
            reasoning_effort="high",
            experiment_id="x",
            timeout_seconds=60,
            trigger="SCHEDULED_SCAN",
        )


def test_fault_harness_cannot_claim_pass_without_real_handler(tmp_path):
    harness = FaultInjectionHarness(tmp_path / "fault.jsonl")
    result = harness.run("broker_disconnect")
    assert result.passed is False
    assert result.reason_code == "FAULT_HANDLER_NOT_REGISTERED"


def test_auditor_probe_source_requires_network_denial_and_privilege_proof():
    root = Path(__file__).resolve().parents[2]
    probe = (root / "auditor_runtime" / "AUDITOR_GATE_V2_PROBE.ps1").read_text(
        encoding="utf-8"
    )
    denial = (root / "auditor_runtime" / "AUDITOR_DENIAL_PROBE_V1.ps1").read_text(
        encoding="utf-8"
    )
    assert "BROKER_NETWORK_SOCKET_NOT_DENIED" in probe
    assert "PAPER_BROKER_LOOPBACK_NOT_DENIED" in probe
    assert "AUDITOR_FORBIDDEN_PRIVILEGE_PRESENT" in probe
    assert "BROKER_NETWORK_SOCKET_ACCESS" in denial
    assert "TARGET_PATH_CHAIN_NOT_FULLY_INSPECTABLE" in denial


def test_finalizer_uses_pinned_trust_anchor_not_installed_manifest_as_authority():
    root = Path(__file__).resolve().parents[2]
    finalizer = (root / "FINALIZE_IBKR_PREREQUISITES.ps1").read_text(
        encoding="utf-8"
    )
    assert "ExpectedTrustAnchorSha256" in finalizer
    assert "evaluate-runtime-trust-anchor" in finalizer
    assert "AUDITOR_DEPLOYMENT_MANIFEST_TRUST_ANCHOR_MISMATCH" in finalizer


def test_validate_proposal_blocks_failed_whatif_branch(monkeypatch):
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(
        toolbox,
        "_broker_feasibility",
        lambda proposal, ib=None: {
            "success": False,
            "error": "WHAT_IF_RETURNED_NONE",
            "whatIf": True,
            "paper_only": True,
        },
    )

    result = toolbox.validate_proposal(proposal(), bundle())

    assert result.passed is False
    assert result.reason_codes == ("BROKER_FEASIBILITY_FAILED",)


def test_validate_proposal_blocks_broker_warning_branch(monkeypatch):
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    monkeypatch.setattr(
        toolbox,
        "_broker_feasibility",
        lambda proposal, ib=None: {
            "success": True,
            "warningText": "Order rejected: insufficient margin",
            "initMarginChange": "0",
            "maintMarginChange": "0",
            "commission": "1.00",
            "minCommission": "1.00",
            "maxCommission": "1.00",
            "whatIf": True,
            "paper_only": True,
        },
    )

    result = toolbox.validate_proposal(proposal(), bundle())

    assert result.passed is False
    assert result.reason_codes == ("BROKER_FEASIBILITY_WARNING_BLOCK",)


def test_unknown_contract_resolution_fails_closed():
    class MissingContractBroker:
        def qualifyContracts(self, contract):
            return []

    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)

    with pytest.raises(LookupError, match="IBKR contract not found"):
        toolbox._qualify(
            MissingContractBroker(),
            {
                "symbol": "NO_SUCH_CONTRACT",
                "sec_type": "STK",
                "exchange": "SMART",
                "currency": "USD",
            },
        )


def test_owner_authorization_is_bound_to_persisted_clock(tmp_path):
    start = datetime(2026, 9, 21, 13, 30, tzinfo=timezone.utc)
    with Database.open(tmp_path / "auth.sqlite3") as db:
        clock = ExperimentClockStore(db).initialize_or_load(
            requested_start_utc=start,
            duration_days=30,
            initial_allocation=Decimal("500.00"),
        )
        store = OwnerAuthorizationStore(db)
        assert store.current(clock_event_sha256=clock.event_sha256) == "NOT_AUTHORIZED"
        store.set(
            "AUTHORIZED",
            clock_event_sha256=clock.event_sha256,
            reason="explicit owner authorization",
        )
        assert store.current(clock_event_sha256=clock.event_sha256) == "AUTHORIZED"
        assert store.current(clock_event_sha256="f" * 64) == "NOT_AUTHORIZED"
        store.set(
            "REVOKED",
            clock_event_sha256=clock.event_sha256,
            reason="owner revoked",
        )
        assert store.current(clock_event_sha256=clock.event_sha256) == "REVOKED"


def test_experiment_clock_marks_future_start_not_started(tmp_path):
    start = datetime(2026, 9, 22, 13, 30, tzinfo=timezone.utc)
    now = datetime(2026, 9, 21, 13, 30, tzinfo=timezone.utc)
    with Database.open(tmp_path / "future-clock.sqlite3") as db:
        clock = ExperimentClockStore(db).initialize_or_load(
            requested_start_utc=start,
            duration_days=30,
            initial_allocation=Decimal("500.00"),
        )
        snapshot = clock.snapshot(now)
        assert snapshot["not_started"] is True
        assert snapshot["elapsed_days"] == 0
        assert snapshot["expired"] is False


class LiveQuoteBroker:
    def __init__(
        self,
        *,
        bid=1.0,
        ask=1.1,
        quote_time=None,
        broker_time=None,
        actual_market_data_type=1,
    ):
        self.bid = bid
        self.ask = ask
        self.quote_time = quote_time or datetime(2026, 9, 21, 13, 30, tzinfo=timezone.utc)
        self.broker_time = broker_time or datetime(2026, 9, 21, 13, 30, 5, tzinfo=timezone.utc)
        self.actual_market_data_type = actual_market_data_type
        self.requested_type = None

    def reqMarketDataType(self, value):
        self.requested_type = value

    def reqMktData(self, contract, genericTickList="", snapshot=True, regulatorySnapshot=False):
        return SimpleNamespace(
            bid=self.bid,
            ask=self.ask,
            time=self.quote_time,
            marketDataType=self.actual_market_data_type,
        )

    def reqCurrentTime(self):
        return self.broker_time

    def sleep(self, seconds):
        pass


def _simple_contract():
    return SimpleNamespace(
        conId=123,
        symbol="XYZ",
        localSymbol="XYZ",
        secType="OPT",
        exchange="SMART",
        primaryExchange="",
        currency="USD",
        lastTradeDateOrContractMonth="20261016",
        strike=40,
        right="C",
        multiplier="100",
    )


def test_trade_contract_live_quote_evidence_fails_closed():
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    contract = _simple_contract()

    delayed = LiveQuoteBroker(actual_market_data_type=3)
    result = toolbox.live_contract_quote_evidence(delayed, contract)
    assert result["success"] is False
    assert result["reason"] == "TRADE_CONTRACT_MARKET_DATA_NOT_REALTIME"
    assert result["market_data_type"] == 3
    assert delayed.requested_type == 1

    missing = LiveQuoteBroker(bid=float("nan"), ask=1.1)
    result = toolbox.live_contract_quote_evidence(missing, contract)
    assert result["success"] is False
    assert result["reason"] == "TRADE_CONTRACT_LIVE_BID_ASK_MISSING"
    assert missing.requested_type == 1

    stale = LiveQuoteBroker(
        quote_time=datetime(2026, 9, 21, 13, 29, tzinfo=timezone.utc),
        broker_time=datetime(2026, 9, 21, 13, 30, tzinfo=timezone.utc),
    )
    result = toolbox.live_contract_quote_evidence(stale, contract)
    assert result["success"] is False
    assert result["reason"] == "TRADE_CONTRACT_QUOTE_STALE"

    fresh = LiveQuoteBroker()
    result = toolbox.live_contract_quote_evidence(fresh, contract)
    assert result["success"] is True
    assert result["requested_market_data_type"] == "LIVE"


class ComboQuoteBroker(LiveQuoteBroker):
    def reqMktData(self, contract, genericTickList="", snapshot=True, regulatorySnapshot=False):
        if str(getattr(contract, "secType", "") or "").upper() == "BAG":
            return SimpleNamespace(
                bid=float("nan"),
                ask=float("nan"),
                time=self.quote_time,
                marketDataType=self.actual_market_data_type,
            )
        return SimpleNamespace(
            bid=1.0,
            ask=1.1,
            time=self.quote_time,
            marketDataType=self.actual_market_data_type,
        )

    def qualifyContracts(self, contract):
        return [
            SimpleNamespace(
                conId=int(getattr(contract, "conId", 0) or 0),
                symbol="XYZ",
                localSymbol="XYZ",
                secType="OPT",
                exchange="SMART",
                primaryExchange="",
                currency="USD",
                lastTradeDateOrContractMonth="20261016",
                strike=40,
                right="C",
                multiplier="100",
            )
        ]


def test_combo_live_market_data_falls_back_to_all_legs():
    toolbox = IBKRResearchToolbox(expected_account_hash="a" * 64)
    combo = SimpleNamespace(
        conId=0,
        symbol="XYZ",
        localSymbol="XYZ",
        secType="BAG",
        exchange="SMART",
        primaryExchange="",
        currency="USD",
        lastTradeDateOrContractMonth="",
        strike=0,
        right="",
        multiplier="",
        comboLegs=[
            SimpleNamespace(conId=101, exchange="SMART"),
            SimpleNamespace(conId=102, exchange="SMART"),
        ],
    )
    broker = ComboQuoteBroker()
    result = toolbox.live_contract_quote_evidence(broker, combo)
    assert result["success"] is True
    assert result["validation_mode"] == "ALL_COMBO_LEGS"
    assert len(result["leg_results"]) == 2
    assert all(item["success"] for item in result["leg_results"])


def test_runtime_market_gate_blocks_rejected_live_observation(tmp_path, monkeypatch):
    from ibkr_paper_30d import runtime_integrity
    from ibkr_paper_30d.market_data import MarketDataPolicy
    from ibkr_paper_30d.market_observation_collector import RawQuote
    from ibkr_paper_30d.runtime_integrity import RuntimeMarketDataGate

    now = datetime(2026, 9, 21, 14, 30, tzinfo=timezone.utc)

    class FakeSource:
        def __init__(self):
            self.started = False

        def start(self, symbols):
            self.started = True

        def identity_receipt_sha256(self):
            return "a" * 64

        def heartbeat_ok(self):
            return True

        def source_health(self):
            return "HEALTHY"

        def snapshot(self, symbol):
            return RawQuote(
                symbol=symbol,
                contract_id={"IEF": 1, "QQQ": 2, "SPY": 3}[symbol],
                liquid_hours="20260921:0930-20260921:1600",
                timezone_id="US/Eastern",
                realtime_or_delayed="DELAYED",
                entitlement_state="AVAILABLE",
                bid=Decimal("100"),
                ask=Decimal("100.01"),
                last=Decimal("100"),
                bid_size=Decimal("10"),
                ask_size=Decimal("10"),
                last_size=Decimal("1"),
                broker_quote_timestamp=now,
                local_receipt_timestamp=now,
                monotonic_receipt_ns=1,
                clock_skew_ms=0,
                round_trip_ms=1,
                source_health="HEALTHY",
            )

        def stop(self):
            pass

    monkeypatch.setattr(
        runtime_integrity,
        "load_verified_policy",
        lambda path: MarketDataPolicy(
            version="MARKET_DATA_POLICY_V1",
            max_new_trade_age_ms=1000,
            max_position_management_age_ms=2000,
            max_clock_skew_ms=500,
            require_realtime_for_new_trade=True,
            require_bid_ask_for_spread=True,
        ),
    )

    gate = RuntimeMarketDataGate(
        policy_path=tmp_path / "policy.json",
        expected_account_hash="a" * 64,
        source_factory=FakeSource,
        now_utc=lambda: now,
    )
    result = gate.evaluate()
    assert result["gate_status"] == "BLOCK"
    assert "DELAYED_DATA" in result["reason_codes"]
