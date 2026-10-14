from datetime import datetime, timedelta, timezone
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor

import pytest

import test_canary_pilot as pilot
from ibkr_paper_30d.canary_candidate import (
    CanaryDiscoveryOutcome, bind_canary_authorization, validate_canary_candidate,
)
from ibkr_paper_30d.canary_execution import CanaryExecutionRequest, CanaryPreWriteBlocked
from ibkr_paper_30d.contract_ownership import ContractOwnershipStore
from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.experiment_control import KillSwitchStore
from ibkr_paper_30d.multi_universe_models import CapitalSleeve
from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.production_continuity_runtime import _ProductionCanaryStore
from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore
from ibkr_paper_30d.successor_schema import install_successor_schema_v2


def _setup(tmp_path, *, request_updates=None, authorization_updates=None, missing=None,
           proposal_updates=None, age=timedelta(0)):
    path = tmp_path / "reservation.sqlite3"
    now = datetime.now(timezone.utc) - age
    proposal = pilot._proposal()
    proposal = proposal.model_copy(update={
        "created_at_utc": now, "expires_at_utc": now + timedelta(minutes=30),
        "flat_return_plan": proposal.flat_return_plan.model_copy(update={
            "deadline_utc": now + timedelta(minutes=20)}),
    })
    proposal = proposal.model_copy(update=proposal_updates or {})
    owner = pilot._owner().model_copy(update={
        "issued_at_utc": now - timedelta(minutes=1),
        "expires_at_utc": now + timedelta(minutes=30),
    })
    authorization = bind_canary_authorization(proposal, owner, now)
    authorization = authorization.model_copy(update=authorization_updates or {})
    request = CanaryExecutionRequest(
        canary_id=proposal.candidate_id, durable_sequence=1,
        execution_key=f"canary:{proposal.sha256}:{authorization.sha256}",
        candidate_sha256=proposal.sha256, authorization_sha256=authorization.sha256,
        account_identity_sha256=proposal.account_identity_sha256,
        successor_definition_sha256=proposal.successor_definition_sha256,
        writer_binding_sha256=pilot.WRITER, product_family=proposal.product_family,
        canonical_contract=proposal.canonical_contract, entry_terms=proposal.entry_terms,
        quantity=proposal.quantity, maximum_debit_usd=proposal.maximum_debit_usd,
        maximum_loss_usd=proposal.maximum_loss_usd,
        fee_allowance_usd=proposal.fee_allowance_usd,
        flat_return_plan=proposal.flat_return_plan, created_at_utc=now,
    ).model_copy(update=request_updates or {})
    with Database.open(path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        install_multi_universe_schema_v4(db)
        KillSwitchStore(db).set("KILL_SWITCH_CLEAR", reason="TEST")
        SleeveLedgerStore(db).bootstrap_continuous()
    store = _ProductionCanaryStore(path)
    if missing != "candidate":
        evidence = pilot._evidence(proposal)
        evidence.update(observed_at_utc=now, expires_at_utc=now + timedelta(minutes=5))
        store.persist_candidate(CanaryDiscoveryOutcome.model_construct(
            decision="CANDIDATE", proposal=proposal,
            invocation_sha256=proposal.invocation_sha256,
            result_sha256=proposal.result_sha256, transcript_sha256="e" * 64,
        ), evidence, validate_canary_candidate(
            proposal, read_only_capability_evidence=evidence, now_utc=now))
    if missing != "authorization":
        store.persist_authorization(candidate_sha256=proposal.sha256, authorization=authorization)
    if missing != "request":
        store.persist_request(proposal.sha256, request)
    return path, store, proposal, request


def _state(path):
    with Database.open(path) as db:
        return (
            ContractOwnershipStore(db).projection(),
            SleeveLedgerStore(db).project(CapitalSleeve.CONTINUOUS_SLEEVE),
            _ProductionCanaryStore._verified_events(db),
        )


def test_claim_reserves_exact_candidate_group_and_liability_once(tmp_path):
    path, store, proposal, request = _setup(tmp_path)
    before_request = store.load_request(proposal.sha256).sha256
    assert store.begin_write(request.execution_key) is True
    assert store.begin_write(request.execution_key) is False
    ownership, ledger, events = _state(path)
    assert len(ownership.active_contracts) == 1
    owner = ownership.owner_of(proposal.canonical_contract.sha256)
    assert owner.sleeve is CapitalSleeve.CONTINUOUS_SLEEVE
    assert owner.group_id == "group-1"
    assert owner.group_sha256 == proposal.contract_group.sha256
    assert ledger.reserved_liability_usd == Decimal("10")
    claims = [event for event in events if event["event_type"] == "EXECUTION_CLAIMED"]
    assert len(claims) == 1
    assert claims[0]["candidate_sha256"] == proposal.sha256
    assert claims[0]["request_sha256"] == before_request
    assert store.load_request(proposal.sha256).sha256 == before_request


@pytest.mark.parametrize("missing", ["candidate", "authorization", "request"])
def test_missing_durable_binding_cannot_claim(tmp_path, missing):
    path, store, _, request = _setup(tmp_path, missing=missing)
    with pytest.raises(CanaryPreWriteBlocked):
        store.begin_write(request.execution_key)
    ownership, ledger, events = _state(path)
    assert ownership.active_contracts == ()
    assert ledger.reserved_liability_usd == 0
    assert not any(event["event_type"] == "EXECUTION_CLAIMED" for event in events)


@pytest.mark.parametrize("updates", [
    {"candidate_sha256": "f" * 64}, {"authorization_sha256": "f" * 64},
    {"canary_id": "another"}, {"account_identity_sha256": "f" * 64},
    {"successor_definition_sha256": "f" * 64},
    {"maximum_loss_usd": Decimal("9")}, {"maximum_debit_usd": Decimal("9")},
    {"fee_allowance_usd": Decimal("0")},
    {"entry_terms": pilot._proposal().entry_terms.model_copy(update={"time_in_force": "IOC"})},
    {"canonical_contract": pilot._contract().model_copy(update={"con_id": 123})},
    {"product_family": pilot._family().model_copy(update={"venue_or_routing": "OTHER"})},
])
def test_request_must_match_durable_candidate(tmp_path, updates):
    path, store, _, request = _setup(tmp_path, request_updates=updates)
    with pytest.raises(CanaryPreWriteBlocked):
        store.begin_write(request.execution_key)
    ownership, ledger, _ = _state(path)
    assert ownership.active_contracts == ()
    assert ledger.reserved_liability_usd == 0
    assert not store.execution_claimed(request.execution_key)


@pytest.mark.parametrize("updates", [
    {"account_identity_sha256": "f" * 64},
    {"successor_definition_sha256": "f" * 64},
    {"product_family_sha256": "f" * 64},
    {"contract_scope_sha256": ("f" * 64,)},
    {"maximum_loss_usd": Decimal("9")},
    {"maximum_debit_usd": Decimal("9")},
    {"fee_allowance_usd": Decimal("0")}, {"maximum_order_count": 1},
])
def test_authorization_must_cover_candidate(tmp_path, updates):
    path, store, _, request = _setup(tmp_path, authorization_updates=updates)
    with pytest.raises(CanaryPreWriteBlocked):
        store.begin_write(request.execution_key)
    ownership, ledger, _ = _state(path)
    assert ownership.active_contracts == ()
    assert ledger.reserved_liability_usd == 0
    assert not store.execution_claimed(request.execution_key)


def test_insufficient_capital_rolls_back_ownership_and_claim(tmp_path):
    path, store, _, request = _setup(tmp_path)
    with Database.open(path) as db, db.transaction():
        SleeveLedgerStore(db).reserve_liability_in_transaction(
            CapitalSleeve.CONTINUOUS_SLEEVE, amount_usd=Decimal("495"),
            reservation_key="other")
    with pytest.raises(CanaryPreWriteBlocked, match="SLEEVE_AGGREGATE_LIABILITY_EXCEEDED"):
        store.begin_write(request.execution_key)
    ownership, ledger, _ = _state(path)
    assert ownership.active_contracts == ()
    assert ledger.reserved_liability_usd == Decimal("495")
    assert not store.execution_claimed(request.execution_key)


@pytest.mark.parametrize("sleeve", list(CapitalSleeve))
def test_existing_conflicting_group_cannot_claim(tmp_path, sleeve):
    path, store, proposal, request = _setup(tmp_path)
    with Database.open(path) as db:
        ContractOwnershipStore(db).reserve_group(proposal.contract_group.model_copy(
            update={"group_id": "other", "sleeve": sleeve}))
    with pytest.raises(CanaryPreWriteBlocked, match="CONTRACT_"):
        store.begin_write(request.execution_key)
    ownership, ledger, _ = _state(path)
    assert ownership.owner_of(proposal.canonical_contract.sha256).group_id == "other"
    assert ledger.reserved_liability_usd == 0
    assert not store.execution_claimed(request.execution_key)


def test_concurrent_claims_reserve_once(tmp_path):
    path, store, _, request = _setup(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(store.begin_write, [request.execution_key] * 2))
    assert sorted(results) == [False, True]
    assert _state(path)[1].reserved_liability_usd == Decimal("10")


def _legacy_claim(path, request):
    with Database.open(path) as db, db.transaction():
        _ProductionCanaryStore._append_in_transaction(
            db, authorization_id=request.execution_key, event_type="EXECUTION_CLAIMED",
            body={"execution_key": request.execution_key})
        KillSwitchStore(db).set("KILL_SWITCH_TRIGGERED", reason="TEST_FAILURE")


@pytest.mark.parametrize("existing", ["none", "ownership", "liability", "both"])
def test_recovery_reserves_only_missing_original_state_and_keeps_kill(tmp_path, existing):
    path, store, proposal, request = _setup(tmp_path)
    _legacy_claim(path, request)
    store.persist_result(proposal.sha256, {"status": "UNCERTAIN", "broker_write_boundary_crossed": True})
    with Database.open(path) as db, db.transaction():
        if existing in {"ownership", "both"}:
            ContractOwnershipStore(db).reserve_group_in_transaction(proposal.contract_group)
        if existing in {"liability", "both"}:
            SleeveLedgerStore(db).reserve_liability_in_transaction(
                CapitalSleeve.CONTINUOUS_SLEEVE, amount_usd=Decimal("10"),
                reservation_key=request.execution_key)
    receipt = store.reserve_recovery_ownership(request)
    assert store.reserve_recovery_ownership(request) == receipt
    ownership, ledger, events = _state(path)
    assert ownership.owner_of(proposal.canonical_contract.sha256).group_sha256 == proposal.contract_group.sha256
    assert ledger.reserved_liability_usd == Decimal("10")
    recovery = [event for event in events if event["event_type"] == "RECOVERY_OWNERSHIP_RESERVED"]
    assert len(recovery) == 1
    assert recovery[0]["request_sha256"] == request.sha256
    assert recovery[0]["contract_group_sha256"] == proposal.contract_group.sha256
    assert not any(event["event_type"] == "LIFECYCLE_RECEIPT" for event in events)
    with Database.open(path) as db:
        assert KillSwitchStore(db).current() == "KILL_SWITCH_TRIGGERED"


def test_recovery_requires_original_claim(tmp_path):
    path, store, _, request = _setup(tmp_path)
    with pytest.raises(CanaryPreWriteBlocked, match="CANARY_EXECUTION_CLAIM_REQUIRED"):
        store.reserve_recovery_ownership(request)
    assert _state(path)[0].active_contracts == ()


def test_recovery_rejects_changed_original_request(tmp_path):
    path, store, _, request = _setup(tmp_path)
    _legacy_claim(path, request)
    with pytest.raises(CanaryPreWriteBlocked):
        store.reserve_recovery_ownership(request.model_copy(update={"writer_binding_sha256": "f" * 64}))
    assert _state(path)[1].reserved_liability_usd == 0


def test_recovery_insufficient_capital_rolls_back(tmp_path):
    path, store, _, request = _setup(tmp_path)
    _legacy_claim(path, request)
    with Database.open(path) as db, db.transaction():
        SleeveLedgerStore(db).reserve_liability_in_transaction(
            CapitalSleeve.CONTINUOUS_SLEEVE, amount_usd=Decimal("495"), reservation_key="other")
    with pytest.raises(CanaryPreWriteBlocked, match="SLEEVE_AGGREGATE_LIABILITY_EXCEEDED"):
        store.reserve_recovery_ownership(request)
    ownership, ledger, events = _state(path)
    assert ownership.active_contracts == ()
    assert ledger.reserved_liability_usd == Decimal("495")
    assert not any(event["event_type"] == "RECOVERY_OWNERSHIP_RESERVED" for event in events)


def test_exact_group_includes_members_and_contingent_contracts(tmp_path):
    group = pilot._proposal().contract_group
    leg = pilot._contract().model_copy(update={"con_id": 123, "local_symbol": "ETH.USD"})
    contingent = pilot._contract().model_copy(update={"con_id": 456, "local_symbol": "SOL.USD"})
    group = group.model_copy(update={
        "member_contracts": (*group.member_contracts, leg),
        "contingent_contracts": (contingent,),
    })
    path, store, _, request = _setup(tmp_path, proposal_updates={"contract_group": group})
    assert store.begin_write(request.execution_key) is True
    ownership, _, _ = _state(path)
    assert len(ownership.active_contracts) == 3
    assert {item.group_sha256 for item in ownership.active_contracts} == {group.sha256}


def test_regular_sleeve_candidate_cannot_reserve(tmp_path):
    group = pilot._proposal().contract_group.model_copy(update={"sleeve": CapitalSleeve.REGULAR_SLEEVE})
    path, store, _, request = _setup(tmp_path, proposal_updates={"contract_group": group})
    with pytest.raises(CanaryPreWriteBlocked):
        store.begin_write(request.execution_key)
    assert _state(path)[0].active_contracts == ()


def test_recovery_uses_expired_original_authorization_without_granting_new_entry(tmp_path):
    path, store, _, request = _setup(tmp_path, age=timedelta(days=1))
    with pytest.raises(CanaryPreWriteBlocked, match="CANARY_CANDIDATE_NOT_ACTIVE"):
        store.begin_write(request.execution_key)
    _legacy_claim(path, request)
    assert store.reserve_recovery_ownership(request)
    assert _state(path)[1].reserved_liability_usd == Decimal("10")


@pytest.mark.parametrize("recovery", [False, True])
def test_final_event_failure_rolls_back_both_reservations(tmp_path, recovery, monkeypatch):
    import sqlite3
    path, store, _, request = _setup(tmp_path)
    if recovery:
        _legacy_claim(path, request)
    def fail_append(*args, **kwargs):
        raise sqlite3.IntegrityError("TEST_EVENT_FAILURE")
    monkeypatch.setattr(store, "_append_in_transaction", fail_append)
    with pytest.raises(sqlite3.IntegrityError, match="TEST_EVENT_FAILURE"):
        if recovery:
            store.reserve_recovery_ownership(request)
        else:
            store.begin_write(request.execution_key)
    ownership, ledger, _ = _state(path)
    assert ownership.active_contracts == ()
    assert ledger.reserved_liability_usd == 0


def test_existing_liability_with_wrong_amount_cannot_be_reused(tmp_path):
    path, store, _, request = _setup(tmp_path)
    _legacy_claim(path, request)
    with Database.open(path) as db, db.transaction():
        SleeveLedgerStore(db).reserve_liability_in_transaction(
            CapitalSleeve.CONTINUOUS_SLEEVE, amount_usd=Decimal("1"),
            reservation_key=request.execution_key)
    with pytest.raises(CanaryPreWriteBlocked, match="CANARY_LIABILITY_RESERVATION_CONFLICT"):
        store.reserve_recovery_ownership(request)
    assert _state(path)[0].active_contracts == ()


FULL_STEPS = ["SUBMITTED", "BROKER_BOUND", "ENTRY_FILL", "POSITION_VISIBLE",
              "MANAGEMENT_OBSERVED", "EXIT_FILL", "FLAT_STATE", "ECONOMICS_RECONCILED"]


def _terminal_result(proposal, status):
    return {
        "status": status, "broker_write_boundary_crossed": True,
        "projection": {
            "canary_id": proposal.candidate_id,
            "account_identity_sha256": proposal.account_identity_sha256,
            "product_family_sha256": proposal.product_family.sha256,
            "contract_identity_sha256": proposal.canonical_contract.sha256,
            "status": "PASS" if status == "PASS" else "TRANSMIT_ONLY",
            "completed_steps": FULL_STEPS if status == "PASS" else ["SUBMITTED", "BROKER_BOUND", "TERMINAL_NO_FILL"],
            "full_lifecycle_verified": status == "PASS", "flat": status == "PASS",
            "terminal_no_fill": status == "TERMINAL_NO_FILL", "terminal_event_sha256": "a" * 64,
        },
    }


@pytest.mark.parametrize("status", ["UNCERTAIN", "IN_PROGRESS", "PASS", "TERMINAL_NO_FILL", "BLOCKED"])
def test_unproven_result_keeps_candidate_active(tmp_path, status):
    _, store, proposal, _ = _setup(tmp_path)
    store.persist_result(proposal.sha256, {"status": status, "broker_write_boundary_crossed": True})
    assert store.load_candidate()[0].proposal.sha256 == proposal.sha256


@pytest.mark.parametrize("status", ["PASS", "TERMINAL_NO_FILL", "BLOCKED"])
def test_proven_terminal_result_retires_candidate(tmp_path, status):
    _, store, proposal, _ = _setup(tmp_path)
    result = ({"status": "BLOCKED", "broker_write_boundary_crossed": False}
              if status == "BLOCKED" else _terminal_result(proposal, status))
    store.persist_result(proposal.sha256, result)
    assert store.load_candidate() is None


@pytest.mark.parametrize("update", [
    {"flat": False}, {"full_lifecycle_verified": False},
    {"completed_steps": FULL_STEPS[:-1]}, {"terminal_event_sha256": None},
])
def test_pass_without_full_flat_economics_keeps_candidate(tmp_path, update):
    _, store, proposal, _ = _setup(tmp_path)
    result = _terminal_result(proposal, "PASS")
    result["projection"].update(update)
    store.persist_result(proposal.sha256, result)
    assert store.load_candidate() is not None


@pytest.mark.parametrize("status", ["UNCERTAIN", "IN_PROGRESS", "PASS", "TERMINAL_NO_FILL"])
def test_result_plus_submitted_is_not_completed_orphan_history(tmp_path, status):
    path, store, proposal, request = _setup(tmp_path)
    store.persist_result(proposal.sha256, {"status": status, "broker_write_boundary_crossed": True})
    with Database.open(path) as db, db.transaction():
        store._append_in_transaction(db, authorization_id=request.canary_id,
            event_type="LIFECYCLE_RECEIPT", body={"receipt": {"canary_id": request.canary_id, "step": "SUBMITTED"}})
        store._append_in_transaction(db, authorization_id="new-candidate",
            event_type="CANDIDATE_SELECTED", body={"candidate_sha256": "f" * 64,
            "outcome": {"proposal": {"candidate_id": "new-candidate"}}})
    assert store.has_orphaned_durable_state() is True


@pytest.mark.parametrize("status", ["PASS", "TERMINAL_NO_FILL"])
def test_terminal_projection_plus_only_submitted_is_still_orphaned(tmp_path, status):
    path, store, proposal, request = _setup(tmp_path)
    store.persist_result(proposal.sha256, _terminal_result(proposal, status))
    with Database.open(path) as db, db.transaction():
        store._append_in_transaction(db, authorization_id=request.canary_id,
            event_type="LIFECYCLE_RECEIPT", body={"receipt": {"canary_id": request.canary_id, "step": "SUBMITTED"}})
    assert store.has_orphaned_durable_state() is True


@pytest.mark.parametrize("status", ["PASS", "TERMINAL_NO_FILL"])
def test_terminal_result_with_verified_full_receipts_is_completed(tmp_path, status):
    from ibkr_paper_30d.canary_authority import CanaryBrokerLifecycleReceipt, CanaryLifecycleRecorder
    _, store, proposal, request = _setup(tmp_path)
    recorder = CanaryLifecycleRecorder(request.canary_id, request.account_identity_sha256,
        request.product_family.sha256, request.canonical_contract.sha256)
    steps = FULL_STEPS if status == "PASS" else ["SUBMITTED", "BROKER_BOUND", "TERMINAL_NO_FILL"]
    for index, step in enumerate(steps):
        receipt = CanaryBrokerLifecycleReceipt(
            canary_id=request.canary_id, step=step, endpoint="PAPER",
            account_identity_sha256=request.account_identity_sha256,
            product_family_sha256=request.product_family.sha256,
            contract_identity_sha256=request.canonical_contract.sha256,
            broker_event_id_sha256=f"{index + 1:064x}", broker_snapshot_sha256=f"{index + 20:064x}",
            previous_receipt_sha256=recorder.last_receipt_sha256,
            observed_at_utc=request.created_at_utc + timedelta(seconds=index),
            open_orders=0, positions=0, economics_reconciled=step == "ECONOMICS_RECONCILED")
        recorder.record(receipt)
        store.persist_receipt(receipt)
    store.persist_result(proposal.sha256, {"status": status, "broker_write_boundary_crossed": True,
        "projection": recorder.projection().model_dump(mode="json")})
    assert store.load_candidate() is None
    assert store.has_orphaned_durable_state() is False


@pytest.mark.parametrize("v4", [True, False])
def test_writer_factory_wires_canary_accounting_only_with_canary_store(tmp_path, monkeypatch, v4):
    from types import SimpleNamespace
    from ibkr_paper_30d import production_continuity_runtime as runtime
    from ibkr_paper_30d.broker_write_coordinator import BrokerWriteCoordinator
    from ibkr_paper_30d.canary_broker_accounting import CanaryBrokerAccounting
    monkeypatch.setattr(runtime, "validate_production_runtime_configuration", lambda _: None)
    monkeypatch.setattr(runtime, "_current_head", lambda _: "b" * 40)
    monkeypatch.setattr(runtime, "build_ibkr_session_factory",
        lambda **kwargs: lambda: pytest.fail("No broker connection permitted"))
    path = tmp_path / "factory.sqlite3"
    writer = runtime.create_authoritative_writer(
        coordinator=BrokerWriteCoordinator(), db_path=path,
        config=SimpleNamespace(repo_root=tmp_path, paper_host="127.0.0.1", paper_port=4002,
            target_successor_definition_sha256="a" * 64 if v4 else None),
        preflight=SimpleNamespace(expected_account_hash="a" * 64),
        execution_lock_verifier=lambda: True, uncertainty_reporter=lambda _: None,
        toolbox=object(), production_validation_sha256="c" * 64,
        current_adapter_sha256="d" * 64)
    if v4:
        assert isinstance(writer.canary_broker_accounting, CanaryBrokerAccounting)
        assert writer.canary_broker_accounting.db_path == path
    else:
        assert writer.canary_broker_accounting is None
