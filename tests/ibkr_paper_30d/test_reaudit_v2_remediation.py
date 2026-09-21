from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ibkr_paper_30d.autonomous_execution import AutonomousPaperExecutor
from ibkr_paper_30d.autonomous_research import (
    AutonomousPositionAction,
    CodexAutonomousCLIProvider,
    ProposalValidation,
)
from ibkr_paper_30d.ibkr_research_tools import IBKRResearchToolbox
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.trader_invocation import TraderDecision, TraderInputBundle


def _bundle() -> TraderInputBundle:
    return TraderInputBundle(
        decision_cycle_id="cycle-reaudit-v2-1",
        utc_timestamp="2026-09-21T14:00:00Z",
        market_session_state="REGULAR",
        reconciliation_receipt={"status": "PASS"},
        experiment_subledger_snapshot={
            "allocation": "500.00",
            "cash": "500.00",
            "market_value": "0.00",
            "equity": "500.00",
        },
        broker_account_snapshot={
            "paper_account": True,
            "declared_options_level": 4,
            "experiment_buying_power": "500.00",
            "global_broker_balances_redacted": True,
        },
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
        experiment_clock={"remaining_days": 30, "expired": False},
    )


class _AccountSummaryBroker:
    def accountSummary(self):
        return [
            SimpleNamespace(tag="NetLiquidation", value="50000"),
            SimpleNamespace(tag="TotalCashValue", value="49000"),
            SimpleNamespace(tag="SettledCash", value="48000"),
            SimpleNamespace(tag="BuyingPower", value="100000"),
            SimpleNamespace(tag="AvailableFunds", value="90000"),
            SimpleNamespace(tag="ExcessLiquidity", value="85000"),
            SimpleNamespace(tag="InitMarginReq", value="5000"),
            SimpleNamespace(tag="MaintMarginReq", value="4000"),
        ]

    def reqCurrentTime(self):
        return datetime(2026, 9, 21, 14, 0, tzinfo=timezone.utc)

    def disconnect(self):
        pass


def test_account_state_research_never_exposes_global_broker_balances(monkeypatch):
    toolbox = IBKRResearchToolbox(
        expected_account_hash="a" * 64,
        declared_options_level=4,
    )
    broker = _AccountSummaryBroker()
    monkeypatch.setattr(toolbox, "_connect", lambda: broker)

    result = toolbox._account_state({})

    encoded = json.dumps(result, sort_keys=True)
    forbidden = (
        "NetLiquidation",
        "TotalCashValue",
        "SettledCash",
        "BuyingPower",
        "AvailableFunds",
        "ExcessLiquidity",
        "InitMarginReq",
        "MaintMarginReq",
        "50000",
        "100000",
    )
    assert result["success"] is True
    assert result["paper_account"] is True
    assert result["global_broker_balances_redacted"] is True
    assert "summary" not in result
    assert not any(token in encoded for token in forbidden)

    manifest = toolbox.manifest()
    account_tool = next(item for item in manifest if item["tool"] == "ACCOUNT_STATE")
    assert "NLV" not in account_tool["purpose"]
    assert "balance" in account_tool["purpose"].lower()
    assert "redacted" in account_tool["purpose"].lower()


def test_actual_model_substitution_is_detected():
    output = "\n".join(
        [
            json.dumps(
                {
                    "type": "thread.started",
                    "model": "gpt-5.6-sol",
                    "actual_model": "gpt-5.5-codex",
                }
            ),
            json.dumps({"type": "turn.completed"}),
        ]
    )

    with pytest.raises(
        RuntimeError, match="AUTONOMOUS_CODEX_MODEL_SUBSTITUTION_DETECTED"
    ):
        CodexAutonomousCLIProvider._assert_effective_model(
            output, "gpt-5.6-sol"
        )


def test_actual_model_equal_to_requested_model_passes():
    output = json.dumps(
        {
            "type": "thread.started",
            "actual_model": "gpt-5.6-sol",
        }
    )
    CodexAutonomousCLIProvider._assert_effective_model(
        output, "gpt-5.6-sol"
    )


class _PositionInversionIB:
    def __init__(self):
        self.place_calls = 0
        self.client = SimpleNamespace(getReqId=lambda: 777)

    def placeOrder(self, contract, order):
        self.place_calls += 1
        raise AssertionError("placeOrder must not be reached after direction inversion")

    def disconnect(self):
        pass


class _LateInversionToolbox:
    def __init__(self):
        self.ib = _PositionInversionIB()
        self.resolve_calls = 0
        self.contract = SimpleNamespace(
            conId=123,
            symbol="XYZ",
            secType="OPT",
            lastTradeDateOrContractMonth="20261016",
            strike=40,
            right="C",
            multiplier="100",
        )

    def _connect(self):
        return self.ib

    def validate_position_action(self, action, bundle, decision, *, ib=None):
        return ProposalValidation(
            passed=True,
            reason_codes=(),
            broker_evidence={
                "whatIf": True,
                "initMarginChange": "0",
                "maintMarginChange": "0",
                "commission": "1.00",
            },
        )

    def _resolve_open_position(self, ib, action):
        self.resolve_calls += 1
        # First resolution: +2 long. Final pre-send resolution: -1 short.
        qty = Decimal("2") if self.resolve_calls == 1 else Decimal("-1")
        return SimpleNamespace(position=qty, contract=self.contract)

    def live_contract_quote_evidence(self, ib, contract):
        return {
            "success": True,
            "market_data_type": 1,
            "requested_market_data_type": "LIVE",
        }


def test_late_position_direction_inversion_blocks_before_send(tmp_path):
    action = AutonomousPositionAction(
        symbol="XYZ",
        sec_type="OPT",
        action="SELL",
        quantity="1",
        order_type="MKT",
        limit_price=None,
        contract_id=123,
        expiry="20261016",
        strike="40",
        right="C",
        reason="reduce long position",
    )
    toolbox = _LateInversionToolbox()

    with Database.open(tmp_path / "reaudit-v2.sqlite3") as db:
        executor = AutonomousPaperExecutor(
            toolbox,
            armed=True,
            database=db,
            fresh_safety_check=lambda scope: (),
            operator_control_check=lambda: (),
        )
        result = executor.execute_position_action(
            action,
            _bundle(),
            TraderDecision.REDUCE_POSITION,
        )

    assert result.success is False
    assert result.status == "BLOCKED"
    assert result.reason_codes == (
        "POSITION_ACTION_WOULD_INCREASE_EXPOSURE_BEFORE_SEND",
    )
    assert toolbox.ib.place_calls == 0
