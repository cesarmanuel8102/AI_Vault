from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
import ibkr_paper_30d.autonomous_state as state_module

from ibkr_paper_30d.autonomous_research import ResearchResult, ResearchTool
from ibkr_paper_30d.autonomous_state import (
    AutonomousStateBuildError,
    AutonomousStateBuilder,
)
from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
from ibkr_paper_30d.continuity_store import ContinuityStore
from ibkr_paper_30d.experiment_control import KillSwitchStore
from ibkr_paper_30d.open_order_management import canonical_open_order
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.successor_clock import BrokerTimeObservation, clock_for_epoch
from ibkr_paper_30d.successor_epoch import (
    BrokerTransitionEvidence,
    commit_successor_transition,
)
from successor_test_support import (
    ACCOUNT_HASH,
    OWNER_SID,
    SUCCESSOR_START,
    build_authorized_successor,
)


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


def test_state_builder_classifies_transient_broker_read_failure():
    class TimeoutToolbox:
        def execute(self, request, bundle):
            return ResearchResult(
                request_id=request.request_id,
                tool=request.tool,
                success=False,
                data={},
                error="TimeoutError:tool_failed",
            )

    subject = object.__new__(AutonomousStateBuilder)
    subject.toolbox = TimeoutToolbox()

    with pytest.raises(
        state_module.TransientBrokerStateBuildError,
        match="POSITIONS_FAILED:TimeoutError:tool_failed",
    ):
        subject._tool(ResearchTool.POSITIONS)


def test_state_builder_classifies_connection_subclass_as_transient():
    class ConnectionFailureToolbox:
        def execute(self, request, bundle):
            return ResearchResult(
                request_id=request.request_id,
                tool=request.tool,
                success=False,
                data={},
                error="ConnectionRefusedError:tool_failed",
            )

    subject = object.__new__(AutonomousStateBuilder)
    subject.toolbox = ConnectionFailureToolbox()

    with pytest.raises(state_module.TransientBrokerStateBuildError):
        subject._tool(ResearchTool.POSITIONS)


def test_state_builder_keeps_identity_failure_non_transient():
    class IdentityFailureToolbox:
        def execute(self, request, bundle):
            return ResearchResult(
                request_id=request.request_id,
                tool=request.tool,
                success=False,
                data={},
                error="PermissionError:tool_failed",
            )

    subject = object.__new__(AutonomousStateBuilder)
    subject.toolbox = IdentityFailureToolbox()

    with pytest.raises(AutonomousStateBuildError) as exc_info:
        subject._tool(ResearchTool.POSITIONS)

    assert not isinstance(
        exc_info.value, state_module.TransientBrokerStateBuildError
    )


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


def register_bag_binding(db):
    payload = {
        "schema": "EXPERIMENT_ORDER_REGISTRY_V3",
        "lifecycle_event": "BROKER_BOUND",
        "order_ref": "codex-ibkr-paper-30d-a-bag-cycle",
        "client_order_id": 13,
        "perm_id": 1401602203,
        "ibkr_order_id": 13,
        "contract_id": 28812380,
        "action": "BUY",
        "quantity": "1",
        "execution_client_id": 19761,
        "account": "DU1234567",
        "contract": {
            "conId": 28812380,
            "symbol": "IOVA",
            "secType": "BAG",
            "exchange": "SMART",
            "currency": "USD",
            "comboLegs": [
                {"conId": 913925915, "ratio": 1, "action": "BUY", "exchange": "SMART"},
                {"conId": 926221865, "ratio": 1, "action": "SELL", "exchange": "SMART"},
            ],
        },
    }
    db.execute(
        "INSERT INTO experiment_order_registry("
        "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
        "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
        ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            "bag-binding",
            payload["order_ref"],
            13,
            1401602203,
            13,
            28812380,
            "BUY",
            "1",
            canonical_bytes(payload).decode("utf-8"),
            sha256_json(payload),
            "2026-09-29T17:55:57Z",
        ),
    )


def bag_fill(*, con_id, side, account="DU1234567", quantity="1", cum_qty="1"):
    return {
        "execution_id_hash": f"exec-{con_id}-{side}",
        "orderRef": "codex-ibkr-paper-30d-a-bag-cycle",
        "orderId": 13,
        "permId": 1401602203,
        "clientId": 19761,
        "account": account,
        "execution_time": "2026-09-29T18:00:00Z",
        "cumQty": cum_qty,
        "side": side,
        "quantity": quantity,
        "price": "0.50",
        "commission": "0",
        "contract": {
            "conId": con_id,
            "symbol": "IOVA",
            "secType": "OPT",
            "multiplier": "100",
        },
    }


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


def test_state_builder_exposes_v3_continuity_context_without_strategy_guidance(tmp_path):
    from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
    from ibkr_paper_30d.successor_schema import install_successor_schema_v2

    with Database.open(tmp_path / "state.sqlite3") as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        value = builder(db, FakeToolbox()).build(trigger="SCHEDULED_SCAN")

    assert value.continuity_context["status"] == "AVAILABLE"
    assert value.continuity_context["authority_contract_required"] is True
    assert value.continuity_context["active_plans"] == []
    assert value.continuity_context["provider_states"] == []
    assert value.continuity_context["pending_factual_reports"] == []
    assert value.continuity_context["prior_reflections"] == []


def _persist_completed_cycle(
    db,
    *,
    index,
    trigger,
    decision,
    accepted,
    symbols,
    tools,
    scanner_queries=0,
    option_chains=0,
    feasibility_checks=0,
):
    cycle_id = f"cycle-observation-{index}"
    invocation_id = f"invocation-observation-{index}"
    bundle_id = f"bundle-observation-{index}"
    bundle_payload = {"decision_cycle_id": cycle_id}
    invocation_payload = {
        "decision_cycle_id": cycle_id,
        "invocation_id": invocation_id,
        "invocation_trigger": trigger,
    }
    final_payload = {
        "decision_cycle_id": cycle_id,
        "invocation_id": invocation_id,
        "accepted": accepted,
        "decision": decision,
        "reason_codes": [],
    }
    telemetry = {
        "schema": "CODEX_RESEARCH_TELEMETRY_V1",
        "telemetry_source": "SYSTEM_GENERATED",
        "research_requests_executed": len(tools),
        "tools_used": tools,
        "scanner_queries": scanner_queries,
        "scanner_results_received": len(symbols) if scanner_queries else 0,
        "symbols_examined": symbols,
        "asset_classes_examined": [],
        "option_chains_queried": option_chains,
        "candidates_generated": len(symbols),
        "feasibility_checks": feasibility_checks,
        "blocked_requests": 0,
    }
    db.execute(
        "INSERT INTO trader_input_bundles(bundle_id,decision_cycle_id,payload_json,"
        "payload_sha256,created_at_utc) VALUES(?,?,?,?,?)",
        (
            bundle_id,
            cycle_id,
            canonical_bytes(bundle_payload).decode("utf-8"),
            sha256_json(bundle_payload),
            f"2026-10-09T14:{index:02d}:00Z",
        ),
    )
    db.execute(
        "INSERT INTO trader_invocations(invocation_id,decision_cycle_id,bundle_id,"
        "payload_json,payload_sha256,created_at_utc) VALUES(?,?,?,?,?,?)",
        (
            invocation_id,
            cycle_id,
            bundle_id,
            canonical_bytes(invocation_payload).decode("utf-8"),
            sha256_json(invocation_payload),
            f"2026-10-09T14:{index:02d}:01Z",
        ),
    )
    for event_type, payload, round_index in (
        (
            "research_telemetry_summary",
            {
                "decision_cycle_id": cycle_id,
                "invocation_id": invocation_id,
                "event": telemetry,
            },
            1,
        ),
        ("final_outcome", final_payload, 2),
    ):
        db.execute(
            "INSERT INTO autonomous_research_events(event_id,decision_cycle_id,"
            "invocation_id,round_index,event_type,payload_json,payload_sha256,"
            "created_at_utc) VALUES(?,?,?,?,?,?,?,?)",
            (
                f"event-{event_type}-{index}",
                cycle_id,
                invocation_id,
                round_index,
                event_type,
                canonical_bytes(payload).decode("utf-8"),
                sha256_json(payload),
                f"2026-10-09T14:{index:02d}:02Z",
            ),
        )


def test_state_builder_projects_factual_process_observation_without_guidance(tmp_path):
    with Database.open(tmp_path / "state.sqlite3") as db:
        _persist_completed_cycle(
            db,
            index=1,
            trigger="SCHEDULED_SCAN",
            decision="NO_TRADE",
            accepted=True,
            symbols=["HAE"],
            tools=["QUOTE", "NEWS_SEARCH"],
        )
        _persist_completed_cycle(
            db,
            index=2,
            trigger="POSITION_EVENT",
            decision="MONITOR_POSITION",
            accepted=True,
            symbols=["HAE"],
            tools=["QUOTE"],
        )

        value = builder(db, FakeToolbox()).build(
            trigger="SCHEDULED_SCAN",
            benchmark_state={"owner_benchmark": "preserved"},
        )

    observation = value.benchmark_state["autonomous_process_observation"]
    assert value.benchmark_state["owner_benchmark"] == "preserved"
    assert observation["telemetry_source"] == "SYSTEM_GENERATED_DURABLE_EVENTS"
    assert observation["cycles_observed"] == 2
    assert observation["trigger_counts"] == {
        "POSITION_EVENT": 1,
        "SCHEDULED_SCAN": 1,
    }
    assert observation["decision_counts"] == {
        "MONITOR_POSITION": 1,
        "NO_TRADE": 1,
    }
    assert observation["symbols_examined"] == ["HAE"]
    assert observation["symbol_cycle_counts"] == {"HAE": 2}
    assert observation["scanner_queries"] == 0
    assert observation["feasibility_checks"] == 0
    assert observation["largest_position_share_of_equity"] == "0.5008"
    serialized = json.dumps(observation, sort_keys=True)
    assert "must" not in serialized.lower()
    assert "recommend" not in serialized.lower()


def test_expired_filled_plan_is_summarized_but_not_model_active(
    tmp_path, continuity_plan_factory
):
    from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
    from ibkr_paper_30d.successor_schema import install_successor_schema_v2

    with Database.open(tmp_path / "state.sqlite3") as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        plan = continuity_plan_factory(
            order_binding={"order_ref": "filled-order", "client_order_id": "filled-order"}
        )
        ContinuityStore(db).append_plan_event("ACTIVATED", plan)
        registry_payload = {
            "schema": "EXPERIMENT_ORDER_REGISTRY_V3",
            "lifecycle_event": "BROKER_BOUND",
            "order_ref": "filled-order",
            "contract_id": 101,
            "contract": {"conId": 101, "symbol": "HAE", "secType": "STK"},
        }
        db.execute(
            "INSERT INTO experiment_order_registry(registry_id,order_ref,client_order_id,"
            "perm_id,ibkr_order_id,contract_id,action,quantity,payload_json,"
            "payload_sha256,created_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                "filled-order-registry",
                "filled-order",
                78,
                225256222,
                78,
                101,
                "BUY",
                "1",
                canonical_bytes(registry_payload).decode("utf-8"),
                sha256_json(registry_payload),
                "2026-10-01T14:01:00Z",
            ),
        )
        subject = builder(db, FakeToolbox())
        context = subject._continuity_context(
            {"epoch_state": "PRE_EPOCH_HISTORY", "now_utc": "2026-10-02T14:00:00Z"},
            open_orders_snapshot=[],
            positions_snapshot=[{"contract_id": 101, "quantity": "1"}],
        )

    assert context["active_plans"] == []
    assert context["inactive_plan_summaries"] == [
        {
            "plan_id": plan.plan_id,
            "plan_sha256": plan.sha256,
            "order_ref": "filled-order",
            "plan_valid_until": "2026-10-01T20:00:00Z",
            "reason": "EXPIRED_NO_OPEN_ORDER_POSITION_PRESENT",
        }
    ]


def test_expired_plan_with_open_order_remains_model_active(
    tmp_path, continuity_plan_factory
):
    from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
    from ibkr_paper_30d.successor_schema import install_successor_schema_v2

    with Database.open(tmp_path / "state.sqlite3") as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        plan = continuity_plan_factory()
        ContinuityStore(db).append_plan_event("ACTIVATED", plan)
        subject = builder(db, FakeToolbox())
        context = subject._continuity_context(
            {"epoch_state": "PRE_EPOCH_HISTORY", "now_utc": "2026-10-02T14:00:00Z"},
            open_orders_snapshot=[{"orderRef": "order-78", "orderId": 78}],
            positions_snapshot=[],
        )

    assert len(context["active_plans"]) == 1
    assert context["inactive_plan_summaries"] == []


def test_continuity_provider_history_is_bounded_and_summarized(tmp_path):
    from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
    from ibkr_paper_30d.successor_schema import install_successor_schema_v2

    with Database.open(tmp_path / "state.sqlite3") as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        store = ContinuityStore(db)
        for index in range(7):
            store.append_provider_event(
                f"provider-{index}",
                "COMPLETED_ACCEPTED" if index % 2 else "TIMEOUT_CONFIRMED",
                {"index": index},
            )
        context = builder(db, FakeToolbox())._continuity_context(
            {"epoch_state": "PRE_EPOCH_HISTORY", "now_utc": "2026-10-09T15:00:00Z"}
        )

    assert len(context["provider_states"]) == 5
    assert [item["invocation_id"] for item in context["provider_states"]] == [
        "provider-6",
        "provider-5",
        "provider-4",
        "provider-3",
        "provider-2",
    ]
    assert context["provider_state_summary"] == {
        "total_invocations": 7,
        "state_counts": {"COMPLETED_ACCEPTED": 3, "TIMEOUT_CONFIRMED": 4},
        "recent_states_limit": 5,
    }


def _active_successor_state_builder(tmp_path):
    from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3

    db_path = tmp_path / "active-successor.sqlite3"
    receipt_path = tmp_path / "owner-successor.json"
    definition, receipt = build_authorized_successor(db_path, receipt_path)
    db = Database.open(db_path)
    evidence = BrokerTransitionEvidence(
        account_identity_sha256=ACCOUNT_HASH,
        collected_at_utc=SUCCESSOR_START + timedelta(seconds=1),
        observation=BrokerTimeObservation(
            server_time_utc=SUCCESSOR_START,
            observed_at_utc=SUCCESSOR_START + timedelta(seconds=1),
            authenticated=True,
            paper_session=True,
        ),
        positions_count=0,
        open_orders_count=0,
        broker_write_count=0,
    )
    transition = commit_successor_transition(
        db=db,
        launch_attempt_id="continuity-authority-test",
        target_successor_epoch_id=str(definition["epoch_id"]),
        target_successor_definition_sha256=str(definition["definition_sha256"]),
        expected_account_identity_sha256=ACCOUNT_HASH,
        expected_owner_sid=OWNER_SID,
        owner_authorization_receipt=receipt,
        execution_lock_verifier=lambda: True,
        broker_evidence_collector=lambda: evidence,
        now_utc=lambda: SUCCESSOR_START + timedelta(seconds=2),
    )
    install_continuity_schema_v3(db)
    clock = clock_for_epoch(db, str(definition["epoch_id"]))
    subject = AutonomousStateBuilder(
        db,
        FakeToolbox(),
        allocation=Decimal("500.00"),
        experiment_start_utc=clock.start_utc,
        experiment_clock=clock,
        duration_days=30,
        runtime_market_gate=FakeMarketGate(),
    )
    return db, subject, definition, receipt, transition


def test_continuity_context_projects_verified_successor_authority(tmp_path):
    db, subject, definition, receipt, transition = _active_successor_state_builder(
        tmp_path
    )
    try:
        clock = subject._clock(SUCCESSOR_START + timedelta(minutes=1))
        context = subject._continuity_context(clock)
    finally:
        db.close()

    assert context["epoch_id"] == definition["epoch_id"]
    assert context["definition_sha256"] == definition["definition_sha256"]
    assert context["clock_event_sha256"] == transition.clock_event_sha256
    assert context["owner_authorization_sha256"] == receipt["receipt_sha256"]


def test_continuity_context_rejects_forged_clock_authority(tmp_path):
    db, subject, _, _, _ = _active_successor_state_builder(tmp_path)
    try:
        clock = subject._clock(SUCCESSOR_START + timedelta(minutes=1))
        clock["clock_event_sha256"] = "f" * 64
        with pytest.raises(
            AutonomousStateBuildError,
            match="CONTINUITY_AUTHORITY_BINDING_MISMATCH",
        ):
            subject._continuity_context(clock)
    finally:
        db.close()


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


@pytest.mark.parametrize(
    ("con_id", "side"),
    [(913925915, "BUY"), (926221865, "SELL")],
)
def test_state_builder_accepts_only_authorized_bag_leg_side(tmp_path, con_id, side):
    with Database.open(tmp_path / f"bag-{con_id}.sqlite3") as db:
        subject = builder(db, FakeToolbox())
        register_bag_binding(db)

        assert subject._registered_fill(bag_fill(con_id=con_id, side=side)) is True


@pytest.mark.parametrize(
    "updates",
    [
        {"con_id": 999999999, "side": "BUY"},
        {"con_id": 913925915, "side": "SELL"},
        {"con_id": 926221865, "side": "BUY"},
        {"con_id": 913925915, "side": "BUY", "account": "DU7654321"},
        {"con_id": 913925915, "side": "BUY", "quantity": "2", "cum_qty": "2"},
        {"con_id": 913925915, "side": "BUY", "quantity": "1", "cum_qty": "2"},
    ],
)
def test_state_builder_blocks_unowned_or_oversized_bag_leg_fill(tmp_path, updates):
    with Database.open(tmp_path / "bag-invalid.sqlite3") as db:
        subject = builder(db, FakeToolbox())
        register_bag_binding(db)

        assert subject._registered_fill(bag_fill(**updates)) is False


def test_authorized_bag_leg_fill_remains_deduplicated_in_ledger(tmp_path):
    with Database.open(tmp_path / "bag-dedupe.sqlite3") as db:
        subject = builder(db, FakeToolbox())
        register_bag_binding(db)
        fill = bag_fill(con_id=913925915, side="BUY")

        assert subject._registered_fill(fill) is True
        first = subject.ledger.record_fill(fill)
        second = subject.ledger.record_fill(fill)

        assert not first.startswith("duplicate:")
        assert second.startswith("duplicate:")
        assert subject.ledger.project().event_count == 1
