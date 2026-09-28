from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ibkr_paper_30d.autonomous_research import ResearchResult, ResearchTool
from ibkr_paper_30d.autonomous_state import (
    AutonomousStateBuildError,
    AutonomousStateBuilder,
)
from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
from ibkr_paper_30d.experiment_control import KillSwitchStore
from ibkr_paper_30d.open_order_management import canonical_open_order
from ibkr_paper_30d.persistence import Database


def open_order_trade():
    return SimpleNamespace(
        contract=SimpleNamespace(
            conId=756733,
            symbol="SPY",
            localSymbol="SPY",
            secType="STK",
            exchange="SMART",
            currency="USD",
            lastTradeDateOrContractMonth="",
            strike=0,
            right="",
            multiplier="1",
        ),
        order=SimpleNamespace(
            orderRef="codex-ibkr-paper-30d-a-cycle",
            orderId=41,
            permId=9001,
            clientId=19761,
            account="DU1234567",
            action="BUY",
            orderType="LMT",
            totalQuantity=2,
            lmtPrice=10,
            auxPrice=0,
            tif="DAY",
            outsideRth=False,
        ),
        orderStatus=SimpleNamespace(status="Submitted", filled=0, remaining=2),
    )


class FakeMarketGate:
    def evaluate(self, decision_class):
        return {
            "gate_status": "PASS",
            "reason_codes": [],
            "policy_version": "MARKET_DATA_POLICY_V1",
            "snapshot_id": "fake",
            "snapshot_sha256": "a" * 64,
        }


class FakeToolbox:
    def __init__(
        self,
        broker_quantity="1",
        include_spoofed_fill=False,
        fill_updates=None,
    ):
        self.broker_quantity = broker_quantity
        self.include_spoofed_fill = include_spoofed_fill
        self.fill_updates = fill_updates or {}
        self.calls = []

    def execute(self, request, bundle):
        self.calls.append(request.tool)
        if request.tool == ResearchTool.EXECUTIONS:
            executions = [{
                    "execution_id_hash": "exec-1",
                    "orderRef": "codex-ibkr-paper-30d-autonomous",
                    "orderId": 44,
                    "permId": 55,
                    "clientId": 19761,
                    "execution_time": "2026-09-21T13:31:00Z",
                    "cumQty": "1",
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
                    **self.fill_updates,
                }]
            if self.include_spoofed_fill:
                executions.append(
                    {
                        **executions[0],
                        "execution_id_hash": "exec-spoofed",
                        "orderRef": "codex-ibkr-paper-30devil",
                    }
                )
            data = {"executions": executions}
        elif request.tool == ResearchTool.QUOTE:
            data = {"marketPrice": 3.0}
        elif request.tool == ResearchTool.ACCOUNT_STATE:
            data = {
                "paper_account": True,
                "declared_options_level": 4,
                "summary": {"BuyingPower": "10000", "NetLiquidation": "10000"},
                "server_time_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
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
            owned = canonical_open_order(open_order_trade())
            data = {
                "open_orders": [
                    {"orderRef": "unrelated", "orderId": 1},
                    {
                        "orderRef": "codex-ibkr-paper-30devil",
                        "orderId": 2,
                    },
                    owned,
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


def builder(
    db,
    toolbox,
    *,
    anchor_perm_id=55,
    payload_sha256=None,
):
    KillSwitchStore(db).set(
        "KILL_SWITCH_CLEAR",
        reason="explicit test Owner authorization boundary",
        actor="test-owner",
    )
    payload = {
        "schema": "EXPERIMENT_ORDER_REGISTRY_V2",
        "lifecycle_event": "ISSUED_PRE_SEND",
        "order_ref": "codex-ibkr-paper-30d-autonomous",
        "client_order_id": 44,
        "perm_id": anchor_perm_id,
        "ibkr_order_id": 44,
        "contract_id": 101,
        "action": "BUY",
        "quantity": "1",
        "execution_client_id": 19761,
        "account": "DU1234567",
    }
    db.execute(
        "INSERT INTO experiment_order_registry("
        "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
        "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
        ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            "registry-1",
            "codex-ibkr-paper-30d-autonomous",
            44,
            anchor_perm_id,
            44,
            101,
            "BUY",
            "1",
            canonical_bytes(payload).decode("utf-8"),
            payload_sha256 or sha256_json(payload),
            "2026-09-21T13:30:00Z",
        ),
    )
    return AutonomousStateBuilder(
        db,
        toolbox,
        allocation=Decimal("500.00"),
        experiment_start_utc=datetime.now(timezone.utc) - timedelta(days=1),
        duration_days=30,
        runtime_market_gate=FakeMarketGate(),
    )


def test_state_builder_cannot_override_default_kill_switch(tmp_path):
    with Database.open(tmp_path / "state.sqlite3") as db:
        with pytest.raises(
            AutonomousStateBuildError, match="KILL_SWITCH_OVERRIDE_FORBIDDEN"
        ):
            AutonomousStateBuilder(
                db,
                FakeToolbox(),
                experiment_start_utc=datetime.now(timezone.utc),
                kill_switch_state="KILL_SWITCH_CLEAR",
                runtime_market_gate=FakeMarketGate(),
            )
        assert KillSwitchStore(db).current() == "KILL_SWITCH_TRIGGERED"
        assert db.execute("SELECT COUNT(*) FROM kill_switch_events").fetchone()[0] == 0


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
        assert value.broker_account_snapshot["experiment_buying_power"] == "599.00"
        assert value.broker_account_snapshot["global_broker_balances_redacted"] is True
        assert value.experiment_clock["remaining_days"] > 28
        assert value.experiment_clock["epoch_state"] == "PRE_EPOCH_HISTORY"
        assert value.experiment_clock["epoch_id"] is None
        assert value.experiment_clock["epoch_activation_required"] is True
        assert len(value.open_orders_snapshot) == 1
        open_order = value.open_orders_snapshot[0]
        assert open_order["permId"] == 9001
        assert open_order["clientId"] == 19761
        assert open_order["contract"]["conId"] == 756733
        assert len(open_order["state_sha256"]) == 64


def test_state_builder_blocks_when_tracked_position_does_not_match_broker(tmp_path):
    with Database.open(tmp_path / "state.sqlite3") as db:
        subject = builder(db, FakeToolbox(broker_quantity="2"))
        value = subject.build(trigger="POSITION_EVENT")

        assert value.reconciliation_receipt["status"] == "BLOCK"
        assert any(
            reason.startswith("POSITION_QUANTITY_MISMATCH")
            for reason in value.reconciliation_receipt["reason_codes"]
        )
        assert value.market_data_snapshot["gate_status"] == "PASS"


def test_repeated_build_does_not_duplicate_same_execution(tmp_path):
    with Database.open(tmp_path / "state.sqlite3") as db:
        subject = builder(db, FakeToolbox())
        first = subject.build(trigger="SCHEDULED_SCAN")
        second = subject.build(trigger="SCHEDULED_SCAN")

        assert first.experiment_subledger_snapshot["equity"] == "599.00"
        assert second.experiment_subledger_snapshot["equity"] == "599.00"
        assert second.experiment_subledger_snapshot["fees"] == "1.00"


def test_state_builder_ignores_fill_without_namespace_boundary(tmp_path):
    with Database.open(tmp_path / "spoofed-fill.sqlite3") as db:
        subject = builder(db, FakeToolbox(include_spoofed_fill=True))
        value = subject.build(trigger="SCHEDULED_SCAN")

        assert value.reconciliation_receipt["status"] == "PASS"
        assert value.experiment_subledger_snapshot["cash"] == "299.00"
        assert value.experiment_subledger_snapshot["fees"] == "1.00"


def test_state_builder_rejects_fill_from_foreign_execution_client(tmp_path):
    with Database.open(tmp_path / "foreign-client-fill.sqlite3") as db:
        subject = builder(db, FakeToolbox(fill_updates={"clientId": 7}))
        value = subject.build(trigger="SCHEDULED_SCAN")

        assert value.reconciliation_receipt["status"] == "BLOCK"
        assert "UNREGISTERED_EXPERIMENT_FILL:44" in (
            value.reconciliation_receipt["reason_codes"]
        )


def test_state_builder_rejects_fill_without_hash_valid_v2_anchor(tmp_path):
    with Database.open(tmp_path / "invalid-anchor-fill.sqlite3") as db:
        subject = builder(db, FakeToolbox(), payload_sha256="0" * 64)
        value = subject.build(trigger="SCHEDULED_SCAN")

        assert value.reconciliation_receipt["status"] == "BLOCK"
        assert "UNREGISTERED_EXPERIMENT_FILL:44" in (
            value.reconciliation_receipt["reason_codes"]
        )


def test_state_builder_accepts_late_perm_id_when_v2_anchor_has_zero(tmp_path):
    with Database.open(tmp_path / "late-perm-fill.sqlite3") as db:
        subject = builder(db, FakeToolbox(), anchor_perm_id=0)
        value = subject.build(trigger="SCHEDULED_SCAN")

        assert value.reconciliation_receipt["status"] == "PASS"
        assert value.experiment_subledger_snapshot["equity"] == "599.00"


@pytest.mark.parametrize(
    "fill_updates",
    [
        {"quantity": "2", "cumQty": "2"},
        {"quantity": "1", "cumQty": "2"},
    ],
)
def test_state_builder_rejects_fill_quantity_exceeding_issuance(
    tmp_path, fill_updates
):
    with Database.open(tmp_path / "oversized-fill.sqlite3") as db:
        subject = builder(db, FakeToolbox(fill_updates=fill_updates))
        value = subject.build(trigger="SCHEDULED_SCAN")

        assert value.reconciliation_receipt["status"] == "BLOCK"
        assert "UNREGISTERED_EXPERIMENT_FILL:44" in (
            value.reconciliation_receipt["reason_codes"]
        )
