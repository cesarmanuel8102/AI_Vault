from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ibkr_paper_30d.broker_write_coordinator import BrokerWriteCoordinator
from ibkr_paper_30d.authoritative_broker_writer import AuthoritativeBrokerWriter
from ibkr_paper_30d.canary_candidate import CanaryEntryTerms, CanaryFlatReturnPlan
from ibkr_paper_30d.canary_execution import (
    CanaryExecutionAdapter,
    CanaryExecutionRequest,
    CanaryRecoveryAction,
    recover_canary,
)
from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.multi_universe_models import (
    CanaryAuthorization,
    CanonicalContractIdentity,
    ProductFamilyKey,
)


NOW = datetime(2026, 10, 10, 20, 0, tzinfo=timezone.utc)
ACCOUNT = "a" * 64
SUCCESSOR = "b" * 64
WRITER = "c" * 64
CANDIDATE = "d" * 64


def _family() -> ProductFamilyKey:
    return ProductFamilyKey(
        security_type="CRYPTO",
        venue_or_routing="PAXOS",
        quantity_semantics="BASE_UNITS",
        order_representation="LIMIT",
        lifecycle_behavior="CONTINUOUS",
    )


def _contract() -> CanonicalContractIdentity:
    return CanonicalContractIdentity(
        con_id=479624278,
        security_type="CRYPTO",
        currency="USD",
        exchange="PAXOS",
        primary_exchange="",
        local_symbol="BTC.USD",
        trading_class="BTC",
        multiplier="1",
    )


def _authorization(contract: CanonicalContractIdentity | None = None):
    contract = contract or _contract()
    return CanaryAuthorization(
        authorization_id="canary-auth",
        owner_id="owner",
        account_identity_sha256=ACCOUNT,
        successor_definition_sha256=SUCCESSOR,
        product_family_sha256=_family().sha256,
        contract_scope_sha256=(contract.sha256,),
        maximum_debit_usd=Decimal("12"),
        maximum_loss_usd=Decimal("12"),
        fee_allowance_usd=Decimal("1"),
        maximum_order_count=2,
        issued_at_utc=NOW - timedelta(minutes=1),
        expires_at_utc=NOW + timedelta(minutes=30),
    )


def _request(**updates) -> CanaryExecutionRequest:
    contract = _contract()
    authorization = _authorization(contract)
    values = {
        "canary_id": "canary-1",
        "durable_sequence": 1,
        "execution_key": "canary-execution-1",
        "candidate_sha256": CANDIDATE,
        "authorization_sha256": authorization.sha256,
        "account_identity_sha256": ACCOUNT,
        "successor_definition_sha256": SUCCESSOR,
        "writer_binding_sha256": WRITER,
        "product_family": _family(),
        "canonical_contract": contract,
        "entry_terms": CanaryEntryTerms(
            action="BUY",
            order_type="LMT",
            limit_price=Decimal("10"),
            time_in_force="DAY",
            outside_regular_hours=True,
        ),
        "quantity": Decimal("0.001"),
        "maximum_debit_usd": Decimal("10"),
        "maximum_loss_usd": Decimal("10"),
        "fee_allowance_usd": Decimal("1"),
        "flat_return_plan": CanaryFlatReturnPlan(
            action="SELL",
            order_type="LMT",
            quantity=Decimal("0.001"),
            limit_price_rule="MODEL_REFRESHED_MARKETABLE_LIMIT",
            deadline_utc=NOW + timedelta(minutes=15),
            terminal_state="FLAT",
        ),
        "created_at_utc": NOW,
    }
    values.update(updates)
    return CanaryExecutionRequest(**values)


def _evidence(request: CanaryExecutionRequest, authorization=None, **updates):
    authorization = authorization or _authorization(request.canonical_contract)
    values = {
        "transition_phase": "CANARY_EXCLUSIVE",
        "ordinary_entry_authority": False,
        "paper_only": True,
        "fresh": True,
        "candidate_sha256": request.candidate_sha256,
        "authorization": authorization,
        "authorization_sha256": authorization.sha256,
        "account_identity_sha256": request.account_identity_sha256,
        "successor_definition_sha256": request.successor_definition_sha256,
        "writer_binding_sha256": request.writer_binding_sha256,
        "request_sha256": request.sha256,
    }
    values.update(updates)
    return values


class LifecycleBroker:
    def __init__(self, events):
        self.events = events
        self.calls = 0

    def execute_canary_through_writer(self, request, evidence):
        self.calls += 1
        return list(self.events)


def _full_events():
    return [
        ("SUBMITTED", 1, 0, False),
        ("BROKER_BOUND", 1, 0, False),
        ("ENTRY_FILL", 0, 1, False),
        ("POSITION_VISIBLE", 0, 1, False),
        ("MANAGEMENT_OBSERVED", 0, 1, False),
        ("EXIT_FILL", 0, 0, False),
        ("FLAT_STATE", 0, 0, False),
        ("ECONOMICS_RECONCILED", 0, 0, True),
    ]


def test_canary_uses_existing_queue_and_writer_capability_only() -> None:
    coordinator = BrokerWriteCoordinator()
    capability = coordinator.attach_writer()
    with pytest.raises(RuntimeError, match="AUTHORITATIVE_WRITER_ALREADY_ATTACHED"):
        coordinator.attach_writer()

    request = _request()
    future = coordinator.submit(request)
    claimed, claimed_future = coordinator.claim(capability)

    assert claimed == request
    assert claimed_future is future
    source = inspect.getsource(__import__("ibkr_paper_30d.canary_execution", fromlist=["*"]))
    assert "placeOrder" not in source


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"transition_phase": "SUPERVISION_BOUND"}, "CANARY_EXCLUSIVE_REQUIRED"),
        ({"ordinary_entry_authority": True}, "ORDINARY_ENTRY_AUTHORITY_MUST_BE_FROZEN"),
        ({"paper_only": False}, "POSSIBLE_LIVE_CONNECTION"),
        ({"fresh": False}, "CANARY_EVIDENCE_STALE"),
        ({"candidate_sha256": "0" * 64}, "CANARY_CANDIDATE_MISMATCH"),
        ({"authorization_sha256": "0" * 64}, "CANARY_AUTHORIZATION_MISMATCH"),
        ({"writer_binding_sha256": "0" * 64}, "CANARY_WRITER_MISMATCH"),
    ],
)
def test_canary_final_authority_reread_blocks_every_mismatch(change, reason) -> None:
    request = _request()
    broker = LifecycleBroker(_full_events())
    adapter = CanaryExecutionAdapter(begin_write=lambda _key: True, now_utc=lambda: NOW)

    result = adapter.execute(request, broker, _evidence(request, **change))

    assert result.status == "BLOCKED"
    assert reason in result.reason_codes
    assert broker.calls == 0


def test_full_lifecycle_is_ordered_flat_and_reconciled() -> None:
    request = _request()
    persisted = []
    broker = LifecycleBroker(_full_events())
    adapter = CanaryExecutionAdapter(
        begin_write=lambda _key: True,
        receipt_persister=persisted.append,
        now_utc=lambda: NOW,
    )

    result = adapter.execute(request, broker, _evidence(request))

    assert result.status == "PASS"
    assert result.projection.full_lifecycle_verified is True
    assert [item.step for item in persisted] == [item[0] for item in _full_events()]
    assert broker.calls == 1


def test_terminal_no_fill_is_transmit_only_not_certified() -> None:
    request = _request()
    broker = LifecycleBroker(
        [("SUBMITTED", 1, 0, False), ("BROKER_BOUND", 1, 0, False), ("TERMINAL_NO_FILL", 0, 0, False)]
    )
    result = CanaryExecutionAdapter(
        begin_write=lambda _key: True, now_utc=lambda: NOW
    ).execute(request, broker, _evidence(request))

    assert result.status == "TERMINAL_NO_FILL"
    assert result.projection.full_lifecycle_verified is False


def test_duplicate_broker_callback_is_idempotent() -> None:
    request = _request()
    events = _full_events()
    events.insert(2, events[1])
    persisted = []

    result = CanaryExecutionAdapter(
        begin_write=lambda _key: True,
        receipt_persister=persisted.append,
        now_utc=lambda: NOW,
    ).execute(request, LifecycleBroker(events), _evidence(request))

    assert result.status == "PASS"
    assert len(persisted) == 8


@pytest.mark.parametrize(
    "broker",
    [
        LifecycleBroker(
            [
                ("SUBMITTED", 1, 0, False),
                ("BROKER_BOUND", 1, 0, False),
                ("PARTIAL_FILL", 1, 1, False),
            ]
        ),
        type(
            "CancelRaceBroker",
            (),
            {
                "execute_canary_through_writer": lambda *_args: (_ for _ in ()).throw(
                    ConnectionError("cancel race")
                )
            },
        )(),
    ],
)
def test_partial_fill_or_cancel_race_freezes_as_uncertain(broker) -> None:
    request = _request()
    result = CanaryExecutionAdapter(
        begin_write=lambda _key: True, now_utc=lambda: NOW
    ).execute(request, broker, _evidence(request))

    assert result.status == "UNCERTAIN"
    assert result.reason_codes == ("CANARY_STATE_UNCERTAIN",)


def test_broker_rejection_with_proven_no_fill_is_terminal_transmit_only() -> None:
    request = _request()
    broker = LifecycleBroker(
        [
            ("SUBMITTED", 1, 0, False),
            ("BROKER_BOUND", 1, 0, False),
            ("TERMINAL_NO_FILL", 0, 0, False),
        ]
    )

    result = CanaryExecutionAdapter(
        begin_write=lambda _key: True, now_utc=lambda: NOW
    ).execute(request, broker, _evidence(request))

    assert result.status == "TERMINAL_NO_FILL"
    assert result.broker_write_boundary_crossed is True


@pytest.mark.parametrize(
    ("snapshot", "action"),
    [
        ({"identity_exact": True, "open_order": True, "position_quantity": "0"}, "RESUME_OBSERVATION"),
        ({"identity_exact": True, "open_order": False, "position_quantity": "0.001"}, "EXACT_RISK_REDUCTION"),
        ({"identity_exact": True, "open_order": False, "position_quantity": "0", "terminal_no_fill": True}, "TERMINAL_NO_FILL"),
        ({"identity_exact": True, "open_order": False, "position_quantity": "0", "economics_reconciled": True}, "PASS"),
        ({"identity_exact": False, "open_order": True, "position_quantity": "0"}, "UNCERTAIN_FREEZE"),
        ({"identity_exact": True, "open_order": True, "position_quantity": "0.0005"}, "UNCERTAIN_FREEZE"),
    ],
)
def test_recovery_never_duplicates_and_only_allows_exact_risk_reduction(snapshot, action):
    decision = recover_canary(None, snapshot, _request())

    assert decision.action is CanaryRecoveryAction(action)
    assert decision.submit_new_entry is False
    assert decision.freeze_ordinary_entries is True


def test_timeout_before_write_is_blocked_and_after_write_is_uncertain() -> None:
    request = _request()
    broker = LifecycleBroker(_full_events())
    before = CanaryExecutionAdapter(
        begin_write=lambda _key: False, now_utc=lambda: NOW
    ).execute(request, broker, _evidence(request))
    assert before.status == "BLOCKED"
    assert before.reason_codes == ("CANARY_REQUEST_EXPIRED",)
    assert broker.calls == 0

    class TimeoutBroker:
        def execute_canary_through_writer(self, request, evidence):
            raise TimeoutError("after broker write boundary")

    after = CanaryExecutionAdapter(
        begin_write=lambda _key: True, now_utc=lambda: NOW
    ).execute(request, TimeoutBroker(), _evidence(request))
    assert after.status == "UNCERTAIN"
    assert after.reason_codes == ("CANARY_STATE_UNCERTAIN",)


def test_failed_prewrite_receipt_persistence_prevents_broker_write() -> None:
    request = _request()
    broker = LifecycleBroker(_full_events())

    def fail_persistence(_receipt):
        raise OSError("disk unavailable")

    result = CanaryExecutionAdapter(
        begin_write=lambda _key: True,
        receipt_persister=fail_persistence,
        now_utc=lambda: NOW,
    ).execute(request, broker, _evidence(request))

    assert result.status == "BLOCKED"
    assert result.reason_codes == ("CANARY_ATTEMPT_PERSISTENCE_FAILED",)
    assert result.broker_write_boundary_crossed is False
    assert broker.calls == 0


def test_changed_duplicate_execution_key_is_rejected() -> None:
    coordinator = BrokerWriteCoordinator()
    first = coordinator.submit(_request())
    changed = coordinator.submit(_request(candidate_sha256="f" * 64))

    assert changed is not first
    assert changed.result().reason_codes == ("DUPLICATE_EXECUTION_KEY",)


def test_authoritative_writer_dispatches_canary_with_fresh_evidence() -> None:
    request = _request()
    expected = CanaryExecutionAdapter(
        begin_write=lambda _key: True, now_utc=lambda: NOW
    ).execute(request, LifecycleBroker(_full_events()), _evidence(request))

    class Adapter:
        def __init__(self):
            self.calls = []

        def execute(self, actual_request, broker, evidence):
            self.calls.append((actual_request, broker, evidence))
            return expected

    class Broker:
        all_order_visibility = True

        def reqAllOpenOrders(self):
            return []

        def reqExecutions(self):
            return []

        def positions(self):
            return []

    adapter = Adapter()
    writer = AuthoritativeBrokerWriter(
        BrokerWriteCoordinator(),
        broker_factory=lambda _client_id: Broker(),
        execution_client_id=19761,
        execution_lock_verifier=lambda: True,
        authority_validator=lambda _command, _evidence: (),
        canary_execution_adapter=adapter,
        canary_evidence_collector=lambda _broker, _request, _base: _evidence(request),
    )
    broker = Broker()

    result = writer._execute(request, broker)

    assert result == expected
    assert adapter.calls[0][0] == request
    assert adapter.calls[0][1] is broker
    assert adapter.calls[0][2]["executions_count"] == 0


def test_authoritative_writer_blocks_canary_without_execution_lock() -> None:
    request = _request()
    writer = AuthoritativeBrokerWriter(
        BrokerWriteCoordinator(),
        broker_factory=lambda _client_id: object(),
        execution_client_id=19761,
        execution_lock_verifier=lambda: False,
        authority_validator=lambda _command, _evidence: (),
        canary_execution_adapter=object(),
        canary_evidence_collector=lambda *_args: _evidence(request),
    )

    result = writer._execute(request, object())

    assert result.status == "BLOCKED"
    assert result.reason_codes == ("EXECUTION_LOCK_REQUIRED",)


def test_real_writer_port_completes_exact_entry_and_flat_return() -> None:
    request = _request()
    coordinator = BrokerWriteCoordinator()

    class ImmediateFillBroker:
        all_order_visibility = True

        def __init__(self):
            self.client = SimpleNamespace(getReqId=iter((101, 102)).__next__)
            self.refs = []

        def qualifyContracts(self, contract):
            return [contract]

        def placeOrder(self, contract, order):
            self.refs.append(order.orderRef)
            order.permId = 9000 + len(self.refs)
            order.clientId = 19761
            return SimpleNamespace(
                contract=contract,
                order=order,
                orderStatus=SimpleNamespace(
                    status="Filled",
                    filled=order.totalQuantity,
                    remaining=0,
                    avgFillPrice=10,
                ),
                fills=[],
            )

        def reqAllOpenOrders(self):
            return []

        def reqExecutions(self):
            return []

        def positions(self):
            return []

    broker = ImmediateFillBroker()
    adapter = CanaryExecutionAdapter(
        begin_write=coordinator.begin_write,
        now_utc=lambda: NOW,
    )
    writer = AuthoritativeBrokerWriter(
        coordinator,
        broker_factory=lambda _client_id: broker,
        execution_client_id=19761,
        execution_lock_verifier=lambda: True,
        authority_validator=lambda _command, _evidence: (),
        canary_execution_adapter=adapter,
        canary_evidence_collector=lambda _broker, _request, _base: {
            **_evidence(request),
            "flat_return_limit_price": "9.50",
        },
    )

    result = writer._execute(request, broker)

    assert result.status == "PASS"
    assert result.projection.flat is True
    assert len(broker.refs) == 2
    assert broker.refs[0] != broker.refs[1]
