from __future__ import annotations

import copy
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ibkr_paper_30d.authoritative_broker_writer import AuthoritativeBrokerWriter
from ibkr_paper_30d.broker_write_coordinator import (
    AuthorizedBrokerCommand,
    BrokerCommandType,
    BrokerWriteCoordinator,
)
from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.continuity_evaluator import (
    ContinuityEvaluationError,
    ContinuityEvaluator,
    ContinuityFactCollector,
)
from ibkr_paper_30d.continuity_models import (
    ContinuityFactEvidence,
    ContinuityFactSnapshot,
)
from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.continuity_store import ContinuityStore
from ibkr_paper_30d.ibkr_readonly import expected_identity_hash
from ibkr_paper_30d.open_order_management import canonical_open_order
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.provider_lifecycle import (
    BrokerTimeEvidence,
    ProviderLifecycleRecorder,
)
from ibkr_paper_30d.successor_schema import install_successor_schema_v2
from ibkr_paper_30d.trader_invocation import InvocationRequest


NOW = datetime(2026, 10, 1, 14, tzinfo=timezone.utc)


def _trade():
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
            orderRef="codex-ibkr-paper-30d-a-fault",
            orderId=41,
            permId=9001,
            clientId=19761,
            account="DU123456",
            action="BUY",
            orderType="LMT",
            totalQuantity=2,
            lmtPrice=10,
            auxPrice=0,
            tif="DAY",
            goodTillDate="",
            outsideRth=False,
            parentId=0,
            ocaGroup="",
            transmit=True,
            conditions=[],
            goodAfterTime="",
            smartComboRoutingParams=[],
            algoStrategy="",
            algoParams=[],
            orderMiscOptions=[],
        ),
        orderStatus=SimpleNamespace(
            status="Submitted", filled=0, remaining=2, avgFillPrice=0
        ),
        fills=[],
    )


def _command(
    trade,
    *,
    sequence: int = 1,
    execution_key: str | None = None,
    command_type: BrokerCommandType = BrokerCommandType.CANCEL,
    **updates,
) -> AuthorizedBrokerCommand:
    snapshot = canonical_open_order(trade)
    payload = {
        "command_id": f"fault-command-{sequence}",
        "durable_sequence": sequence,
        "execution_key": execution_key or f"fault-execution-{sequence}",
        "source": "WATCHDOG",
        "command_type": command_type,
        "evaluation_id": f"fault-evaluation-{sequence}",
        "evaluation_sha256": "1" * 64,
        "plan_id": "fault-plan",
        "plan_sha256": "2" * 64,
        "fact_snapshot_sha256": "3" * 64,
        "order_ref": snapshot["orderRef"],
        "order_id": snapshot["orderId"],
        "perm_id": snapshot["permId"],
        "execution_client_id": snapshot["clientId"],
        "account_identity_sha256": expected_identity_hash(snapshot["account"]),
        "contract_identity_sha256": sha256_json(snapshot["contract"]),
        "observed_state_sha256": snapshot["state_sha256"],
        "authority_class": "PREAUTHORIZED_CONTINUITY",
        "new_total_quantity": None,
        "new_limit_price": None,
        "new_tif": None,
        "new_good_till_date_utc": None,
        "created_at_utc": NOW,
    }
    payload.update(updates)
    return AuthorizedBrokerCommand.model_validate(payload)


class FaultGateway:
    def __init__(self):
        self.client_id = 19761
        self.trade = _trade()
        self.extra_trades = []
        self.cancel_calls = 0
        self.place_calls = 0
        self.read_calls = 0
        self.disconnect_before_evidence = False
        self.disconnect_before_confirmation = False
        self.disconnect_after_write = False
        self.partial_fill_during_modify = False
        self.all_order_visibility = True
        self.after_second_evidence_read = None

    def reqAllOpenOrders(self):
        self.read_calls += 1
        if self.disconnect_before_evidence and self.read_calls == 1:
            raise ConnectionError("disconnect before evidence")
        if self.disconnect_before_confirmation and self.read_calls > 2:
            raise ConnectionError("disconnect before confirmation")
        if self.read_calls == 2 and self.after_second_evidence_read is not None:
            self.after_second_evidence_read()
        return [self.trade, *self.extra_trades]

    def reqExecutions(self):
        return []

    def positions(self):
        return []

    def cancelOrder(self, order):
        self.cancel_calls += 1
        if self.disconnect_after_write:
            raise ConnectionError("disconnect after cancel")
        self.trade.orderStatus.status = "PendingCancel"

    def placeOrder(self, contract, order):
        self.place_calls += 1
        if self.partial_fill_during_modify:
            self.trade.orderStatus.filled = 1.5
            self.trade.orderStatus.remaining = 0.5
            raise RuntimeError("partial fill raced modification")
        if self.disconnect_after_write:
            raise ConnectionError("disconnect after modify")
        self.trade.order = order

    def disconnect(self):
        return None


def _run_writer(
    gateway: FaultGateway,
    command: AuthorizedBrokerCommand,
    *,
    validator=lambda command, evidence: (),
    attempt_persister=None,
):
    coordinator = BrokerWriteCoordinator()
    writer = AuthoritativeBrokerWriter(
        coordinator,
        broker_factory=lambda client_id: gateway,
        execution_client_id=19761,
        execution_lock_verifier=lambda: True,
        authority_validator=validator,
        attempt_persister=attempt_persister,
    )
    writer.start()
    assert writer.wait_until_ready(2)
    try:
        return coordinator.submit(command).result(2), coordinator
    finally:
        writer.stop(2)


def test_fill_between_evaluation_and_write_is_reread_and_blocks():
    gateway = FaultGateway()
    command = _command(gateway.trade)

    def fill_after_authority_read(command, evidence):
        gateway.trade.orderStatus.status = "Filled"
        gateway.trade.orderStatus.filled = 2
        gateway.trade.orderStatus.remaining = 0
        return ()

    result, _ = _run_writer(gateway, command, validator=fill_after_authority_read)

    assert result.status == "BLOCKED"
    assert set(result.reason_codes) & {
        "OPEN_ORDER_STATE_CHANGED",
        "OPEN_ORDER_NOT_ACTIONABLE",
    }
    assert gateway.cancel_calls == 0


def test_partial_fill_before_modify_is_stale_and_during_modify_is_uncertain():
    gateway = FaultGateway()
    stale_command = _command(
        gateway.trade,
        command_type=BrokerCommandType.MODIFY,
        new_total_quantity=Decimal("1.75"),
    )
    gateway.trade.orderStatus.filled = 0.5
    gateway.trade.orderStatus.remaining = 1.5
    stale, _ = _run_writer(gateway, stale_command)
    assert stale.status == "BLOCKED"
    assert "OPEN_ORDER_STATE_CHANGED" in stale.reason_codes
    assert gateway.place_calls == 0

    racing = FaultGateway()
    racing.partial_fill_during_modify = True
    command = _command(
        racing.trade,
        command_type=BrokerCommandType.MODIFY,
        new_total_quantity=Decimal("1.75"),
    )
    uncertain, _ = _run_writer(racing, command)
    assert uncertain.status == "UNCERTAIN"
    assert uncertain.reason_codes == ("CONTINUITY_ORDER_STATE_UNCERTAIN",)
    assert racing.place_calls == 1


@pytest.mark.parametrize(
    "reason",
    [
        "PLAN_SUPERSEDED_DURING_FINAL_READ",
        "MODEL_RECOVERED_DURING_CONTINGENCY",
        "MODEL_COMPLETED_BEFORE_ACTIVATION",
    ],
)
def test_final_authority_reread_blocks_concurrent_state_changes(reason):
    gateway = FaultGateway()
    result, _ = _run_writer(
        gateway,
        _command(gateway.trade),
        validator=lambda command, evidence: (reason,),
    )
    assert result.status == "BLOCKED"
    assert result.reason_codes == (reason,)
    assert gateway.cancel_calls == 0


def test_db_authority_change_during_final_broker_refresh_blocks_write():
    gateway = FaultGateway()
    authority_current = True
    validator_calls = []

    def invalidate_authority():
        nonlocal authority_current
        authority_current = False

    def validate(command, evidence):
        validator_calls.append(authority_current)
        return () if authority_current else ("PLAN_SUPERSEDED_DURING_FINAL_READ",)

    gateway.after_second_evidence_read = invalidate_authority
    result, _ = _run_writer(gateway, _command(gateway.trade), validator=validate)

    assert result.status == "BLOCKED"
    assert result.reason_codes == ("PLAN_SUPERSEDED_DURING_FINAL_READ",)
    assert validator_calls == [True, False]
    assert gateway.cancel_calls == 0


@pytest.mark.parametrize(
    ("fault", "expected"),
    [
        ("disconnect_before_evidence", "BLOCKED"),
        ("disconnect_after_write", "UNCERTAIN"),
        ("disconnect_before_confirmation", "UNCERTAIN"),
    ],
)
def test_disconnect_boundaries_never_claim_unconfirmed_success(fault, expected):
    gateway = FaultGateway()
    setattr(gateway, fault, True)
    result, _ = _run_writer(gateway, _command(gateway.trade))
    assert result.status == expected
    assert result.success is False


def test_duplicate_evaluator_and_conflicting_identity_cannot_write_twice():
    gateway = FaultGateway()
    duplicate = copy.deepcopy(gateway.trade)
    gateway.extra_trades.append(duplicate)
    command = _command(gateway.trade, execution_key="same-evaluation")
    result, _ = _run_writer(gateway, command)
    assert result.status == "BLOCKED"
    assert result.reason_codes == ("OPEN_ORDER_IDENTITY_AMBIGUOUS",)
    assert gateway.cancel_calls == 0

    coordinator = BrokerWriteCoordinator()
    first = coordinator.submit(command)
    second = coordinator.submit(command)
    assert first.done() is False
    assert second.result().reason_codes == ("DUPLICATE_EXECUTION_KEY",)


def test_db_lock_contention_blocks_before_broker_write():
    gateway = FaultGateway()

    def locked(command, evidence):
        raise sqlite3.OperationalError("database is locked")

    result, _ = _run_writer(
        gateway, _command(gateway.trade), attempt_persister=locked
    )
    assert result.status == "BLOCKED"
    assert result.reason_codes == ("CONTINUITY_ATTEMPT_PERSISTENCE_FAILED",)
    assert gateway.cancel_calls == 0


def _fact(name: str, value, *, age_seconds: int = 0, max_age: int = 30):
    collected = NOW - timedelta(seconds=age_seconds)
    body = {
        "fact": name,
        "source": "PAPER_BROKER",
        "collected_at_utc": collected.isoformat(),
        "max_age_seconds": str(max_age),
        "canonical_value": value,
    }
    return ContinuityFactEvidence(
        fact=name,
        source="PAPER_BROKER",
        collected_at_utc=collected,
        max_age_seconds=max_age,
        canonical_value=value,
        evidence_sha256=sha256_json(body),
    )


def test_stale_fact_uses_only_model_authored_unavailable_branch(
    continuity_plan_factory,
):
    plan = continuity_plan_factory()
    facts = (
        _fact("PROVIDER_STATE", "TIMEOUT_CONFIRMED"),
        _fact("ORDER_STATUS", "UNFILLED"),
        _fact("ORDER_REMAINING_QUANTITY", "1", age_seconds=60, max_age=30),
    )
    snapshot = ContinuityFactSnapshot(
        snapshot_id="fault-snapshot",
        collected_at_utc=NOW,
        broker_time_utc=NOW,
        facts=facts,
        evidence_sha256=sha256_json(
            [item.model_dump(mode="json") for item in facts]
        ),
    )
    evaluation = ContinuityEvaluator().evaluate(plan, snapshot)
    assert "EVIDENCE_UNAVAILABLE" in evaluation.reason_codes
    assert evaluation.selected_action == plan.contingencies[0].unavailable_data_action


def test_missing_broker_time_never_activates_continuity(continuity_plan_factory):
    collector = ContinuityFactCollector(
        store=SimpleNamespace(),
        broker=SimpleNamespace(),
        ledger=SimpleNamespace(),
        clock=SimpleNamespace(),
    )
    with pytest.raises(
        ContinuityEvaluationError,
        match="AUTHENTICATED_PAPER_BROKER_TIME_REQUIRED",
    ):
        collector.collect(continuity_plan_factory(), broker_time_utc=None)


def test_restart_marks_foreign_inflight_provider_invocation_abandoned(tmp_path):
    path = tmp_path / "restart.sqlite3"
    with Database.open(path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        store = ContinuityStore(db)
        old = ProviderLifecycleRecorder(
            store,
            launch_attempt_id="launch-old",
            pid=111,
            boot_session_identity="boot-old",
            expected_account_identity_sha256="b" * 64,
        )
        request = InvocationRequest(
            decision_cycle_id="cycle-restart",
            invocation_id="invocation-restart",
            utc_timestamp=NOW.isoformat(),
            requested_model="gpt-5.6-sol",
            actual_model="gpt-5.6-sol",
            model_configuration={"provider": "codex-cli"},
            reasoning_effort="max",
            input_bundle_sha256="a" * 64,
            risk_policy_version="AGGRESSIVE_CAPITAL_BOUNDARY_V1",
            experiment_id="ibkr-paper-30d",
            invocation_trigger="SCHEDULED_SCAN",
            timeout_seconds=180,
        )
        time = BrokerTimeEvidence.create_authenticated_paper(
            time_utc=NOW,
            observed_at_utc=NOW,
            account_identity_sha256="b" * 64,
        )
        old.begin(request, time)
        restarted = ProviderLifecycleRecorder(
            store,
            launch_attempt_id="launch-new",
            pid=222,
            boot_session_identity="boot-new",
            expected_account_identity_sha256="b" * 64,
        )
        recovered = restarted.recover_abandoned(
            {
                "status": "OWNED",
                "pid": 222,
                "boot_session_identity": "boot-new",
            },
            BrokerTimeEvidence.create_authenticated_paper(
                time_utc=NOW + timedelta(seconds=1),
                observed_at_utc=NOW + timedelta(seconds=1),
                account_identity_sha256="b" * 64,
            ),
        )
        projection = store.provider_projection("invocation-restart")

    assert recovered == ("invocation-restart",)
    assert projection["state"] == "ABANDONED"
