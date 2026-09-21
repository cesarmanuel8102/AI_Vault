from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from ibkr_paper_30d.autonomous_research import ResearchResult, ResearchTool
from ibkr_paper_30d.autonomous_state import AutonomousStateBuilder
from ibkr_paper_30d.persistence import Database


class FakeToolbox:
    def __init__(self, broker_quantity="1"):
        self.broker_quantity = broker_quantity
        self.calls = []

    def execute(self, request, bundle):
        self.calls.append(request.tool)
        if request.tool == ResearchTool.EXECUTIONS:
            data = {
                "executions": [{
                    "execution_id_hash": "exec-1",
                    "orderRef": "codex-ibkr-paper-30d-autonomous",
                    "side": "BUY",
                    "quantity": "1",
                    "price": "2.00",
                    "commission": "1.00",
                    "contract": {
                        "conId": 101,
                        "symbol": "XYZ",
                        "secType": "OPT",
                        "multiplier": "100",
                    },
                }]
            }
        elif request.tool == ResearchTool.QUOTE:
            data = {"marketPrice": 3.0}
        elif request.tool == ResearchTool.ACCOUNT_STATE:
            data = {
                "paper_account": True,
                "declared_options_level": 4,
                "summary": {"BuyingPower": "10000", "NetLiquidation": "10000"},
            }
        elif request.tool == ResearchTool.POSITIONS:
            data = {
                "positions": [{
                    "contract": {"conId": 101, "symbol": "XYZ", "secType": "OPT"},
                    "position": self.broker_quantity,
                    "avgCost": 200.0,
                }]
            }
        elif request.tool == ResearchTool.OPEN_ORDERS:
            data = {
                "open_orders": [
                    {"orderRef": "unrelated", "orderId": 1},
                    {"orderRef": "codex-ibkr-paper-30d-position-management", "orderId": 2},
                ]
            }
        else:
            raise AssertionError(f"unexpected tool {request.tool}")
        return ResearchResult(
            request_id=request.request_id,
            tool=request.tool,
            success=True,
            data=data,
        )


def builder(db, toolbox):
    return AutonomousStateBuilder(
        db,
        toolbox,
        allocation=Decimal("500.00"),
        experiment_start_utc=datetime.now(timezone.utc) - timedelta(days=1),
        duration_days=30,
        kill_switch_state="KILL_SWITCH_CLEAR",
    )


def test_state_builder_refreshes_equity_and_keeps_discovery_unconstrained(tmp_path):
    with Database.open(tmp_path / "state.sqlite3") as db:
        subject = builder(db, FakeToolbox())
        value = subject.build(trigger="SCHEDULED_SCAN", market_session_state="REGULAR")

        assert value.experiment_subledger_snapshot["cash"] == "299.00"
        assert value.experiment_subledger_snapshot["market_value"] == "300.00"
        assert value.experiment_subledger_snapshot["equity"] == "599.00"
        assert value.positions_snapshot[0]["contract_id"] == 101
        assert value.positions_snapshot[0]["quantity"] == "1"
        assert value.candidate_screen_results == []
        assert value.reconciliation_receipt["status"] == "PASS"
        assert value.market_data_snapshot["gate_status"] == "PASS"
        assert value.broker_account_snapshot["declared_options_level"] == 4
        assert value.broker_account_snapshot["broker_summary"]["BuyingPower"] == "10000"
        assert "not available to the experiment" in value.broker_account_snapshot["note"]
        assert value.experiment_clock["remaining_days"] > 28
        assert value.open_orders_snapshot == [
            {"orderRef": "codex-ibkr-paper-30d-position-management", "orderId": 2}
        ]


def test_state_builder_blocks_when_tracked_position_does_not_match_broker(tmp_path):
    with Database.open(tmp_path / "state.sqlite3") as db:
        subject = builder(db, FakeToolbox(broker_quantity="2"))
        value = subject.build(trigger="POSITION_EVENT")

        assert value.reconciliation_receipt["status"] == "BLOCK"
        assert any(
            reason.startswith("POSITION_QUANTITY_MISMATCH")
            for reason in value.reconciliation_receipt["reason_codes"]
        )
        assert value.market_data_snapshot["gate_status"] == "BLOCK"


def test_repeated_build_does_not_duplicate_same_execution(tmp_path):
    with Database.open(tmp_path / "state.sqlite3") as db:
        subject = builder(db, FakeToolbox())
        first = subject.build(trigger="SCHEDULED_SCAN")
        second = subject.build(trigger="SCHEDULED_SCAN")

        assert first.experiment_subledger_snapshot["equity"] == "599.00"
        assert second.experiment_subledger_snapshot["equity"] == "599.00"
        assert second.experiment_subledger_snapshot["fees"] == "1.00"
