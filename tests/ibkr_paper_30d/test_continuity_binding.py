from __future__ import annotations

from copy import deepcopy

import pytest

from ibkr_paper_30d.continuity_binding import (
    ContinuityBindingError,
    ContinuityBindingService,
    PendingBindingReconciler,
)
from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.continuity_store import ContinuityStore
from ibkr_paper_30d.ibkr_readonly import expected_identity_hash
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.successor_schema import install_successor_schema_v2


def _open(path) -> Database:
    db = Database.open(path)
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    return db


def _snapshot(**changes):
    value = {
        "orderRef": "order-78", "orderId": 78, "permId": 225256222,
        "clientId": 17, "account": "DU123456", "action": "BUY",
        "orderType": "LMT", "totalQuantity": "1", "limitPrice": "4.90",
        "tif": "DAY", "status": "Submitted", "filled": "0", "remaining": "1",
        "contract": {
            "conId": 756733, "symbol": "UTHR", "localSymbol": "UTHR",
            "secType": "STK", "exchange": "SMART", "currency": "USD",
            "expiry": "", "strike": "0", "right": "", "multiplier": "1",
            "comboLegs": [], "attributes": {},
        },
    }
    value.update(changes)
    return value


def _stage(service, plan):
    return service.stage_new_order(
        plan,
        proposal_sha256="3" * 64,
        order_ref="order-78",
        client_order_id=78,
        contract_identity=_snapshot()["contract"],
        account="DU123456",
        action="BUY",
        quantity="1",
        order_type="LMT",
        routing="SMART",
        execution_client_id=17,
        invocation_id=plan.invocation_id,
        attempt_id="attempt-1",
    )


def _new_plan(continuity_plan_factory, **overrides):
    binding = {
        "binding_type": "NEW_PROPOSAL",
        "account_identity_sha256": expected_identity_hash("DU123456"),
        "order_ref": "order-78",
        "client_order_id": "client-order-78",
        "ibkr_order_id": None,
        "perm_id": None,
        "execution_client_id": 17,
        "contract_identity_sha256": sha256_json(_snapshot()["contract"]),
        "action": "BUY",
        "order_type": "LMT",
        "original_total_quantity": "1",
        "original_limit_price": "4.90",
        "original_tif": "DAY",
        "original_good_till_date_utc": None,
        "original_order_state_sha256": None,
        "original_intent_sha256": "3" * 64,
        "proposal_sha256": "3" * 64,
    }
    binding.update(overrides.pop("order_binding", {}))
    return continuity_plan_factory(order_binding=binding, **overrides)


def test_stage_persists_registry_and_pending_plan_atomically(tmp_path, continuity_plan_factory) -> None:
    plan = _new_plan(continuity_plan_factory)
    with _open(tmp_path / "state.sqlite3") as db:
        service = ContinuityBindingService(db, ContinuityStore(db))
        pending = _stage(service, plan)
        registry = db.execute(
            "SELECT payload_json FROM experiment_order_registry"
        ).fetchone()[0]
        plan_event = db.execute(
            "SELECT event_type,payload_json FROM continuity_plan_events"
        ).fetchone()

    assert pending.plan_sha256 == plan.sha256
    assert '"lifecycle_event":"ISSUED_PRE_SEND"' in registry
    assert '"attempt_id":"attempt-1"' in registry
    assert plan_event[0] == "BIND_PENDING"
    assert plan.sha256 in plan_event[1]


def test_stage_failure_rolls_back_and_send_callback_is_never_called(
    tmp_path, continuity_plan_factory, monkeypatch
) -> None:
    called = []
    with _open(tmp_path / "state.sqlite3") as db:
        store = ContinuityStore(db)
        service = ContinuityBindingService(db, store)
        monkeypatch.setattr(
            store, "_append", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disk"))
        )
        with pytest.raises(RuntimeError, match="disk"):
            service.stage_and_send(
                lambda: _stage(service, _new_plan(continuity_plan_factory)),
                lambda: called.append("placeOrder"),
            )
        assert db.execute("SELECT COUNT(*) FROM experiment_order_registry").fetchone()[0] == 0
    assert called == []


def test_exact_positive_broker_identity_activates_plan(tmp_path, continuity_plan_factory) -> None:
    plan = _new_plan(continuity_plan_factory)
    with _open(tmp_path / "state.sqlite3") as db:
        service = ContinuityBindingService(db, ContinuityStore(db))
        pending = _stage(service, plan)
        active = service.activate_broker_binding(pending, _snapshot(), plan_sha256=plan.sha256)
        events = db.execute(
            "SELECT event_type FROM continuity_plan_events ORDER BY sequence"
        ).fetchall()
        lifecycle = db.execute(
            "SELECT payload_json FROM experiment_order_registry ORDER BY sequence DESC LIMIT 1"
        ).fetchone()[0]

        assert active.perm_id == 225256222
        assert events == [("BIND_PENDING",), ("ACTIVATED",)]
        assert '"lifecycle_event":"BROKER_BOUND"' in lifecycle
        assert ContinuityStore(db).active_plan("order-78") == plan


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda s: s.update(account="DU999"), "ACCOUNT"),
        (lambda s: s.update(orderId=79), "ORDER_ID"),
        (lambda s: s.update(action="SELL"), "DIRECTION"),
        (lambda s: s.update(orderType="MKT"), "ORDER_TYPE"),
        (lambda s: s["contract"].update(exchange="NYSE"), "ROUTING"),
        (lambda s: s["contract"].update(conId=999), "CONTRACT"),
    ],
)
def test_activation_blocks_every_identity_mismatch(
    tmp_path, continuity_plan_factory, mutation, reason
) -> None:
    plan = _new_plan(continuity_plan_factory)
    with _open(tmp_path / f"{reason}.sqlite3") as db:
        service = ContinuityBindingService(db, ContinuityStore(db))
        pending = _stage(service, plan)
        snapshot = _snapshot()
        mutation(snapshot)
        with pytest.raises(ContinuityBindingError, match=reason):
            service.activate_broker_binding(pending, snapshot, plan_sha256=plan.sha256)


def test_activation_blocks_plan_hash_mismatch(tmp_path, continuity_plan_factory) -> None:
    with _open(tmp_path / "state.sqlite3") as db:
        service = ContinuityBindingService(db, ContinuityStore(db))
        pending = _stage(service, _new_plan(continuity_plan_factory))
        with pytest.raises(ContinuityBindingError, match="PLAN_HASH"):
            service.activate_broker_binding(pending, _snapshot(), plan_sha256="0" * 64)


class FakeBrokerEvidence:
    def __init__(self, orders=(), executions=(), positions=()):
        self.orders = list(orders)
        self.executions = list(executions)
        self.position_items = list(positions)
        self.cancel_calls = 0

    def reqAllOpenOrders(self):
        return self.orders

    def reqExecutions(self):
        return self.executions

    def positions(self):
        return self.position_items


def test_recovery_completes_only_one_exact_open_order(tmp_path, continuity_plan_factory) -> None:
    plan = _new_plan(continuity_plan_factory)
    with _open(tmp_path / "state.sqlite3") as db:
        service = ContinuityBindingService(db, ContinuityStore(db))
        _stage(service, plan)
        result = PendingBindingReconciler(service, FakeBrokerEvidence([_snapshot()])).reconcile(plan.plan_id)
        assert result.status == "ACTIVE"
        assert result.write_authority_frozen is False


@pytest.mark.parametrize(
    ("orders", "status", "frozen"),
    [
        ([], "EVIDENCE_UNAVAILABLE", True),
        ([_snapshot(), deepcopy(_snapshot())], "AMBIGUOUS", True),
        ([_snapshot(status="Cancelled")], "TERMINAL", False),
        ([_snapshot(status="Rejected")], "TERMINAL", False),
    ],
)
def test_recovery_matrix_never_cancels_or_guesses(
    tmp_path, continuity_plan_factory, orders, status, frozen
) -> None:
    plan = _new_plan(continuity_plan_factory)
    broker = FakeBrokerEvidence(orders)
    with _open(tmp_path / f"{status}-{len(orders)}.sqlite3") as db:
        service = ContinuityBindingService(db, ContinuityStore(db))
        _stage(service, plan)
        result = PendingBindingReconciler(service, broker).reconcile(plan.plan_id)
    assert result.status == status
    assert result.write_authority_frozen is frozen
    assert broker.cancel_calls == 0


def test_supersession_requires_prior_hash_and_leaves_one_active(
    tmp_path, continuity_plan_factory
) -> None:
    first = _new_plan(continuity_plan_factory)
    second = continuity_plan_factory(
        plan_id="plan-2",
        predecessor_plan_sha256=first.sha256,
        order_binding={
            "account_identity_sha256": expected_identity_hash("DU123456"),
            "contract_identity_sha256": sha256_json(_snapshot()["contract"]),
        },
    )
    with _open(tmp_path / "state.sqlite3") as db:
        service = ContinuityBindingService(db, ContinuityStore(db))
        pending = _stage(service, first)
        service.activate_broker_binding(pending, _snapshot(), plan_sha256=first.sha256)
        service.supersede_existing_order_plan(
            second, accepted_result_sha256="9" * 64, expected_prior_sha256=first.sha256
        )
        assert ContinuityStore(db).active_plan("order-78") == second
        with pytest.raises(ContinuityBindingError, match="STALE"):
            service.assert_plan_current(first.plan_id, first.sha256)


@pytest.mark.parametrize(
    ("binding_change", "reason"),
    [
        ({"account_identity_sha256": "0" * 64}, "ACCOUNT"),
        ({"order_ref": "forged-ref"}, "ORDER_REF"),
        ({"execution_client_id": 99}, "CLIENT_ID"),
        ({"contract_identity_sha256": "0" * 64}, "CONTRACT"),
        ({"action": "SELL"}, "DIRECTION"),
        ({"order_type": "MKT"}, "ORDER_TYPE"),
        ({"original_total_quantity": "2"}, "QUANTITY"),
    ],
)
def test_stage_rejects_plan_to_order_identity_mismatch(
    tmp_path, continuity_plan_factory, binding_change, reason
) -> None:
    plan = _new_plan(continuity_plan_factory, order_binding=binding_change)
    with _open(tmp_path / f"stage-{reason}.sqlite3") as db:
        service = ContinuityBindingService(db, ContinuityStore(db))
        with pytest.raises(ContinuityBindingError, match=reason):
            _stage(service, plan)
        assert db.execute(
            "SELECT COUNT(*) FROM experiment_order_registry"
        ).fetchone()[0] == 0


def test_pending_binding_rejects_corrupt_latest_registry_anchor(
    tmp_path, continuity_plan_factory
) -> None:
    plan = _new_plan(continuity_plan_factory)
    with _open(tmp_path / "corrupt.sqlite3") as db:
        service = ContinuityBindingService(db, ContinuityStore(db))
        pending = _stage(service, plan)
        payload = {
            "schema": "EXPERIMENT_ORDER_REGISTRY_V3",
            "lifecycle_event": "ISSUED_PRE_SEND",
            "continuity_state": "CONTINUITY_BIND_PENDING",
            "plan_id": plan.plan_id,
            "plan_sha256": plan.sha256,
            "proposal_sha256": "3" * 64,
            "invocation_id": plan.invocation_id,
            "attempt_id": "attempt-corrupt",
            "order_ref": pending.order_ref,
            "client_order_id": pending.client_order_id,
            "perm_id": 0,
            "ibkr_order_id": pending.client_order_id,
            "contract_id": pending.contract_identity["conId"],
            "action": pending.action,
            "quantity": pending.quantity,
            "execution_client_id": 17,
            "account": pending.account,
            "contract": pending.contract_identity,
            "order_type": pending.order_type,
            "routing": pending.routing,
            "created_at_utc": "2026-10-01T14:00:00Z",
        }
        db.execute(
            "INSERT INTO experiment_order_registry("
            "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
            "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                "corrupt-anchor", pending.order_ref, pending.client_order_id, 0,
                pending.client_order_id, pending.contract_identity["conId"],
                pending.action, pending.quantity,
                canonical_bytes(payload).decode("utf-8"), "0" * 64,
                payload["created_at_utc"],
            ),
        )
        with pytest.raises(ContinuityBindingError, match="REGISTRY_HASH"):
            service.pending_binding(plan.plan_id)


def test_recovery_records_exact_execution_as_filled_terminal(
    tmp_path, continuity_plan_factory
) -> None:
    plan = _new_plan(continuity_plan_factory)
    execution = {
        **_snapshot(status="Filled"),
        "shares": "1",
        "cumQty": "1",
    }
    position = {
        "account": "DU123456",
        "position": "1",
        "contract": _snapshot()["contract"],
    }
    with _open(tmp_path / "filled.sqlite3") as db:
        service = ContinuityBindingService(db, ContinuityStore(db))
        _stage(service, plan)
        result = PendingBindingReconciler(
            service,
            FakeBrokerEvidence(executions=[execution], positions=[position]),
        ).reconcile(plan.plan_id)
        terminal = db.execute(
            "SELECT payload_json FROM experiment_order_registry "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()[0]

    assert result.status == "TERMINAL"
    assert result.reason_codes == ("BROKER_ORDER_FILLED",)
    assert result.write_authority_frozen is False
    assert '"status":"FILLED"' in terminal


def test_position_without_exact_execution_cannot_guess_order_identity(
    tmp_path, continuity_plan_factory
) -> None:
    plan = _new_plan(continuity_plan_factory)
    position = {
        "account": "DU123456",
        "position": "1",
        "contract": _snapshot()["contract"],
    }
    with _open(tmp_path / "position-only.sqlite3") as db:
        service = ContinuityBindingService(db, ContinuityStore(db))
        _stage(service, plan)
        result = PendingBindingReconciler(
            service, FakeBrokerEvidence(positions=[position])
        ).reconcile(plan.plan_id)

    assert result.status == "EVIDENCE_UNAVAILABLE"
    assert result.write_authority_frozen is True


def test_two_activation_contenders_leave_exactly_one_active_event(
    tmp_path, continuity_plan_factory
) -> None:
    plan = _new_plan(continuity_plan_factory)
    with _open(tmp_path / "race.sqlite3") as db:
        service = ContinuityBindingService(db, ContinuityStore(db))
        first = _stage(service, plan)
        first_result = service.activate_broker_binding(
            first, _snapshot(), plan_sha256=plan.sha256
        )
        retry_result = service.activate_broker_binding(
            first, _snapshot(), plan_sha256=plan.sha256
        )
        count = db.execute(
            "SELECT COUNT(*) FROM continuity_plan_events WHERE event_type='ACTIVATED'"
        ).fetchone()[0]

    assert count == 1
    assert retry_result == first_result


def test_stage_rejects_existing_order_plan(tmp_path, continuity_plan_factory) -> None:
    with _open(tmp_path / "existing.sqlite3") as db:
        service = ContinuityBindingService(db, ContinuityStore(db))
        with pytest.raises(ContinuityBindingError, match="NEW_PROPOSAL"):
            _stage(service, continuity_plan_factory())
