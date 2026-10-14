from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from concurrent.futures import Future
import hashlib
import sqlite3

import pytest

from ibkr_paper_30d.day1_launch import _default_dependencies
from ibkr_paper_30d.ibkr_readonly import expected_identity_hash
from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.canonical import canonical_bytes
from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3, install_continuity_schema_v4
from ibkr_paper_30d.continuity_store import ContinuityStore, ContinuityStoreError
from ibkr_paper_30d.canary_authority import (
    CanaryBrokerLifecycleReceipt,
    CanaryLifecycleRecorder,
)
from ibkr_paper_30d.canary_execution import CanaryExecutionRequest
from ibkr_paper_30d.multi_universe_models import CanaryAuthorization
from ibkr_paper_30d.open_order_management import canonical_contract_identity
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.successor_schema import install_successor_schema_v2
from ibkr_paper_30d.experiment_control import KillSwitchStore
from ibkr_paper_30d.production_continuity_runtime import (
    OBSERVER_CLIENT_ID,
    WRITER_CLIENT_ID,
    ProductionRuntimeConfigurationError,
    ReadOnlyContinuityBroker,
    ProductionContinuityPoller,
    ProductionCriticalAlertReporter,
    _ProductionSnapshotReader,
    _ProductionSleeveAuthoritySnapshotReader,
    build_ibkr_session_factory,
    validate_production_runtime_configuration,
    _verified_registry_binding,
    _collect_continuity_liability_evidence,
    _broker_evidence_collector,
    _ProductionCanaryStore,
    create_canary_pilot_orchestrator,
    create_authoritative_writer,
    validate_production_composition,
)
from ibkr_paper_30d.broker_write_coordinator import BrokerWriteCoordinator
from ibkr_paper_30d.broker_write_coordinator import AuthorizedBrokerCommand


def _canary_write_fixture(store, execution_key):
    from ibkr_paper_30d.canary_candidate import (
        CanaryDiscoveryOutcome, validate_canary_candidate,
    )
    from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore
    from test_canary_pilot import _evidence, _proposal

    now = datetime.now(timezone.utc)
    proposal = _proposal()
    proposal = proposal.model_copy(update={
        "created_at_utc": now,
        "expires_at_utc": now + timedelta(minutes=30),
        "flat_return_plan": proposal.flat_return_plan.model_copy(update={
            "deadline_utc": now + timedelta(minutes=20),
        }),
    })
    authorization = CanaryAuthorization(
        authorization_id="canary-auth-1", owner_id="owner",
        account_identity_sha256=proposal.account_identity_sha256,
        successor_definition_sha256=proposal.successor_definition_sha256,
        product_family_sha256=proposal.product_family.sha256,
        contract_scope_sha256=tuple(member.sha256 for member in proposal.contract_group.member_contracts),
        maximum_debit_usd=proposal.maximum_debit_usd,
        maximum_loss_usd=proposal.maximum_loss_usd,
        fee_allowance_usd=proposal.fee_allowance_usd, maximum_order_count=2,
        issued_at_utc=now, expires_at_utc=proposal.expires_at_utc,
    )
    request = CanaryExecutionRequest(
        canary_id=proposal.candidate_id, durable_sequence=1, execution_key=execution_key,
        candidate_sha256=proposal.sha256, authorization_sha256=authorization.sha256,
        account_identity_sha256=proposal.account_identity_sha256,
        successor_definition_sha256=proposal.successor_definition_sha256,
        writer_binding_sha256="f" * 64, product_family=proposal.product_family,
        canonical_contract=proposal.canonical_contract, entry_terms=proposal.entry_terms,
        quantity=proposal.quantity, maximum_debit_usd=proposal.maximum_debit_usd,
        maximum_loss_usd=proposal.maximum_loss_usd,
        fee_allowance_usd=proposal.fee_allowance_usd,
        flat_return_plan=proposal.flat_return_plan, created_at_utc=now,
    )
    evidence = _evidence(proposal)
    evidence.update(observed_at_utc=now, expires_at_utc=now + timedelta(minutes=5))
    store.persist_candidate(CanaryDiscoveryOutcome(
        decision="CANDIDATE", proposal=proposal,
        invocation_sha256=proposal.invocation_sha256,
        result_sha256=proposal.result_sha256, transcript_sha256=sha256_json([]),
    ), evidence, validate_canary_candidate(
        proposal, read_only_capability_evidence=evidence, now_utc=now,
    ))
    store.persist_request(proposal.sha256, request)
    with Database.open(store.db_path) as db:
        SleeveLedgerStore(db).bootstrap_continuous()
    return proposal, authorization, request


def test_production_canary_store_persists_authority_claim_and_receipt_once(
    tmp_path,
) -> None:
    from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4

    db_path = tmp_path / "canary-store.sqlite3"
    with Database.open(db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        install_multi_universe_schema_v4(db)
        KillSwitchStore(db).set("KILL_SWITCH_CLEAR", reason="TEST_INITIAL_STATE")
    store = _ProductionCanaryStore(db_path)
    proposal, authorization, request = _canary_write_fixture(store, "canary-execution-1")

    first = store.persist_authorization(
        candidate_sha256=proposal.sha256, authorization=authorization
    )
    duplicate = store.persist_authorization(
        candidate_sha256=proposal.sha256, authorization=authorization
    )
    assert duplicate == first
    assert store.begin_write("canary-execution-1") is True
    assert store.begin_write("canary-execution-1") is False

    receipt = CanaryBrokerLifecycleReceipt(
        canary_id=request.canary_id,
        step="SUBMITTED",
        endpoint="PAPER",
        account_identity_sha256="a" * 64,
        product_family_sha256=request.product_family.sha256,
        contract_identity_sha256=request.canonical_contract.sha256,
        broker_event_id_sha256="f" * 64,
        broker_snapshot_sha256="1" * 64,
        observed_at_utc=request.created_at_utc,
        open_orders=0,
        positions=0,
    )
    store.persist_receipt(receipt)
    store.persist_receipt(receipt)

    with Database.open(db_path) as db:
        counts = dict(
            db.execute(
                "SELECT event_type,COUNT(*) FROM canary_authorization_events "
                "GROUP BY event_type"
            ).fetchall()
        )
    assert counts == {
        "CANDIDATE_SELECTED": 1,
        "EXECUTION_REQUEST": 1,
        "AUTHORIZED": 1,
        "EXECUTION_CLAIMED": 1,
        "LIFECYCLE_RECEIPT": 1,
    }


def test_production_canary_store_rejects_tampered_authority_chain(tmp_path) -> None:
    from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4

    db_path = tmp_path / "tampered-canary.sqlite3"
    with Database.open(db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        install_multi_universe_schema_v4(db)
        KillSwitchStore(db).set("KILL_SWITCH_CLEAR", reason="TEST_INITIAL_STATE")
    store = _ProductionCanaryStore(db_path)
    proposal, authorization, _ = _canary_write_fixture(store, "first")
    store.persist_authorization(candidate_sha256=proposal.sha256, authorization=authorization)
    assert store.begin_write("first") is True

    connection = sqlite3.connect(db_path)
    try:
        connection.execute("DROP TRIGGER canary_authorization_events_no_update")
        connection.execute("UPDATE canary_authorization_events SET payload_json='{}'")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        ProductionRuntimeConfigurationError,
        match="CANARY_AUTHORITY_CHAIN_INVALID",
    ):
        store.begin_write("second")


def test_production_canary_store_round_trips_selected_candidate_and_result(
    tmp_path,
) -> None:
    from ibkr_paper_30d.canary_candidate import (
        CanaryCandidateValidationReceipt,
        CanaryDiscoveryOutcome,
    )
    from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
    from test_canary_pilot import _evidence, _proposal

    db_path = tmp_path / "canary-candidate.sqlite3"
    with Database.open(db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        install_multi_universe_schema_v4(db)
    proposal = _proposal()
    outcome = CanaryDiscoveryOutcome(
        decision="CANDIDATE",
        invocation_sha256=proposal.invocation_sha256,
        result_sha256=proposal.result_sha256,
        transcript_sha256=sha256_json([]),
        proposal=proposal,
    )
    evidence = _evidence(proposal)
    validation = CanaryCandidateValidationReceipt(
        status="PASS",
        reason_codes=(),
        proposal_sha256=proposal.sha256,
        capability_evidence_sha256=sha256_json(evidence),
    )
    store = _ProductionCanaryStore(db_path)

    first = store.persist_candidate(outcome, evidence, validation)
    duplicate = store.persist_candidate(outcome, evidence, validation)
    loaded = store.load_candidate()
    recorder = CanaryLifecycleRecorder(
        proposal.candidate_id, proposal.account_identity_sha256,
        proposal.product_family.sha256, proposal.canonical_contract.sha256,
    )
    # Keep receipts absent from durable history to exercise the orphan guard.
    for ordinal, step in enumerate(("SUBMITTED", "BROKER_BOUND", "TERMINAL_NO_FILL"), 1):
        recorder.record(CanaryBrokerLifecycleReceipt(
            canary_id=proposal.candidate_id, step=step, endpoint="PAPER",
            account_identity_sha256=proposal.account_identity_sha256,
            product_family_sha256=proposal.product_family.sha256,
            contract_identity_sha256=proposal.canonical_contract.sha256,
            broker_event_id_sha256=f"{ordinal:064x}",
            broker_snapshot_sha256=f"{ordinal + 10:064x}",
            previous_receipt_sha256=recorder.last_receipt_sha256,
            observed_at_utc=proposal.created_at_utc + timedelta(seconds=ordinal),
            open_orders=1 if step == "BROKER_BOUND" else 0, positions=0,
        ))
    payload = {
        "status": "TERMINAL_NO_FILL", "candidate": proposal.sha256,
        "broker_write_boundary_crossed": True,
        "projection": recorder.projection().model_dump(mode="json"),
    }
    store.persist_result(proposal.sha256, payload)

    assert duplicate == first
    assert loaded[0] == outcome
    assert sha256_json(loaded[1]) == sha256_json(evidence)
    assert loaded[2] == validation
    assert store.load_result(proposal.sha256) == payload
    assert store.load_candidate() is None
    assert store.has_orphaned_durable_state() is True


def test_production_canary_store_replaces_only_expired_unused_candidate(
    tmp_path,
) -> None:
    from ibkr_paper_30d.canary_candidate import (
        CanaryCandidateValidationReceipt,
        CanaryDiscoveryOutcome,
    )
    from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
    from test_canary_pilot import _evidence, _proposal

    db_path = tmp_path / "expired-canary-candidate.sqlite3"
    with Database.open(db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        install_multi_universe_schema_v4(db)
    expired = _proposal()
    expired_outcome = CanaryDiscoveryOutcome(
        decision="CANDIDATE",
        invocation_sha256=expired.invocation_sha256,
        result_sha256=expired.result_sha256,
        transcript_sha256=sha256_json([]),
        proposal=expired,
    )
    expired_evidence = _evidence(expired)
    expired_validation = CanaryCandidateValidationReceipt(
        status="PASS",
        reason_codes=(),
        proposal_sha256=expired.sha256,
        capability_evidence_sha256=sha256_json(expired_evidence),
    )
    replacement = expired.model_copy(
        update={
            "candidate_id": "candidate-2",
            "invocation_id": "invocation-2",
            "invocation_sha256": "3" * 64,
            "result_sha256": "4" * 64,
            "created_at_utc": expired.created_at_utc + timedelta(hours=1),
            "expires_at_utc": expired.expires_at_utc + timedelta(hours=1),
            "flat_return_plan": expired.flat_return_plan.model_copy(
                update={
                    "deadline_utc": expired.flat_return_plan.deadline_utc
                    + timedelta(hours=1)
                }
            ),
        }
    )
    replacement_outcome = CanaryDiscoveryOutcome(
        decision="CANDIDATE",
        invocation_sha256=replacement.invocation_sha256,
        result_sha256=replacement.result_sha256,
        transcript_sha256=sha256_json([]),
        proposal=replacement,
    )
    replacement_evidence = _evidence(replacement)
    replacement_validation = CanaryCandidateValidationReceipt(
        status="PASS",
        reason_codes=(),
        proposal_sha256=replacement.sha256,
        capability_evidence_sha256=sha256_json(replacement_evidence),
    )
    store = _ProductionCanaryStore(db_path)
    store.persist_candidate(expired_outcome, expired_evidence, expired_validation)

    assert store.expire_unused_candidate(
        expired.sha256, expired.expires_at_utc
    ) is True
    assert store.load_candidate() is None
    store.persist_candidate(
        replacement_outcome,
        replacement_evidence,
        replacement_validation,
    )

    assert store.load_candidate()[0].proposal == replacement


def test_production_canary_store_does_not_expire_authorized_candidate(
    tmp_path,
) -> None:
    from ibkr_paper_30d.canary_candidate import (
        CanaryCandidateValidationReceipt,
        CanaryDiscoveryOutcome,
    )
    from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
    from test_canary_pilot import _evidence, _proposal

    db_path = tmp_path / "authorized-canary-candidate.sqlite3"
    with Database.open(db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        install_multi_universe_schema_v4(db)
    proposal = _proposal()
    outcome = CanaryDiscoveryOutcome(
        decision="CANDIDATE",
        invocation_sha256=proposal.invocation_sha256,
        result_sha256=proposal.result_sha256,
        transcript_sha256=sha256_json([]),
        proposal=proposal,
    )
    evidence = _evidence(proposal)
    validation = CanaryCandidateValidationReceipt(
        status="PASS",
        reason_codes=(),
        proposal_sha256=proposal.sha256,
        capability_evidence_sha256=sha256_json(evidence),
    )
    authorization = CanaryAuthorization(
        authorization_id="canary-auth-2",
        owner_id="owner",
        account_identity_sha256=proposal.account_identity_sha256,
        successor_definition_sha256=proposal.successor_definition_sha256,
        product_family_sha256=proposal.product_family.sha256,
        contract_scope_sha256=(proposal.canonical_contract.sha256,),
        maximum_debit_usd=proposal.maximum_debit_usd,
        maximum_loss_usd=proposal.maximum_loss_usd,
        fee_allowance_usd=proposal.fee_allowance_usd,
        maximum_order_count=2,
        issued_at_utc=proposal.created_at_utc,
        expires_at_utc=proposal.expires_at_utc,
    )
    store = _ProductionCanaryStore(db_path)
    store.persist_candidate(outcome, evidence, validation)
    store.persist_authorization(
        candidate_sha256=proposal.sha256,
        authorization=authorization,
    )

    assert store.expire_unused_candidate(
        proposal.sha256, proposal.expires_at_utc
    ) is False
    assert store.load_candidate()[0].proposal == proposal


def test_production_canary_store_recovers_terminal_no_fill_without_resubmission(
    tmp_path,
) -> None:
    from ibkr_paper_30d.canary_candidate import (
        CanaryCandidateValidationReceipt,
        CanaryDiscoveryOutcome,
    )
    from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
    from test_canary_pilot import _evidence, _proposal

    db_path = tmp_path / "recover-terminal-canary.sqlite3"
    with Database.open(db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        install_multi_universe_schema_v4(db)
        KillSwitchStore(db).set("KILL_SWITCH_CLEAR", reason="TEST_INITIAL_STATE")
        from ibkr_paper_30d.sleeve_ledger import SleeveLedgerStore

        SleeveLedgerStore(db).bootstrap_continuous()
    proposal = _proposal()
    now = datetime.now(timezone.utc)
    proposal = proposal.model_copy(update={
        "created_at_utc": now,
        "expires_at_utc": now + timedelta(minutes=30),
        "flat_return_plan": proposal.flat_return_plan.model_copy(update={
            "deadline_utc": now + timedelta(minutes=20),
        }),
    })
    outcome = CanaryDiscoveryOutcome(
        decision="CANDIDATE",
        invocation_sha256=proposal.invocation_sha256,
        result_sha256=proposal.result_sha256,
        transcript_sha256=sha256_json([]),
        proposal=proposal,
    )
    evidence = _evidence(proposal)
    validation = CanaryCandidateValidationReceipt(
        status="PASS",
        reason_codes=(),
        proposal_sha256=proposal.sha256,
        capability_evidence_sha256=sha256_json(evidence),
    )
    authorization = CanaryAuthorization(
        authorization_id="recover-auth",
        owner_id="owner",
        account_identity_sha256=proposal.account_identity_sha256,
        successor_definition_sha256=proposal.successor_definition_sha256,
        product_family_sha256=proposal.product_family.sha256,
        contract_scope_sha256=(proposal.canonical_contract.sha256,),
        maximum_debit_usd=proposal.maximum_debit_usd,
        maximum_loss_usd=proposal.maximum_loss_usd,
        fee_allowance_usd=proposal.fee_allowance_usd,
        maximum_order_count=2,
        issued_at_utc=proposal.created_at_utc,
        expires_at_utc=proposal.expires_at_utc,
    )
    request = CanaryExecutionRequest(
        canary_id=proposal.candidate_id,
        durable_sequence=1,
        execution_key=f"canary:{proposal.sha256}:{authorization.sha256}",
        candidate_sha256=proposal.sha256,
        authorization_sha256=authorization.sha256,
        account_identity_sha256=proposal.account_identity_sha256,
        successor_definition_sha256=proposal.successor_definition_sha256,
        writer_binding_sha256="f" * 64,
        product_family=proposal.product_family,
        canonical_contract=proposal.canonical_contract,
        entry_terms=proposal.entry_terms,
        quantity=proposal.quantity,
        maximum_debit_usd=proposal.maximum_debit_usd,
        maximum_loss_usd=proposal.maximum_loss_usd,
        fee_allowance_usd=proposal.fee_allowance_usd,
        flat_return_plan=proposal.flat_return_plan,
        created_at_utc=proposal.created_at_utc,
    )
    store = _ProductionCanaryStore(db_path)
    store.persist_candidate(outcome, evidence, validation)
    store.persist_authorization(
        candidate_sha256=proposal.sha256, authorization=authorization
    )
    store.persist_request(proposal.sha256, request)
    assert store.begin_write(request.execution_key) is True
    recorder = CanaryLifecycleRecorder(
        request.canary_id,
        request.account_identity_sha256,
        request.product_family.sha256,
        request.canonical_contract.sha256,
    )
    for ordinal, step in enumerate(
        ("SUBMITTED", "BROKER_BOUND", "TERMINAL_NO_FILL"), 1
    ):
        receipt = CanaryBrokerLifecycleReceipt(
            canary_id=request.canary_id,
            step=step,
            endpoint="PAPER",
            account_identity_sha256=request.account_identity_sha256,
            product_family_sha256=request.product_family.sha256,
            contract_identity_sha256=request.canonical_contract.sha256,
            broker_event_id_sha256=f"{ordinal:064x}",
            broker_snapshot_sha256=f"{ordinal + 10:064x}",
            previous_receipt_sha256=recorder.last_receipt_sha256,
            observed_at_utc=proposal.created_at_utc + timedelta(seconds=ordinal),
            open_orders=1 if step == "BROKER_BOUND" else 0,
            positions=0,
            economics_reconciled=False,
        )
        recorder.record(receipt)
        store.persist_receipt(receipt)
    recovered = store.recover_terminal_result(proposal.sha256)

    assert recovered is not None
    assert recovered["authorization_sha256"] == authorization.sha256
    assert recovered["result"].status == "TERMINAL_NO_FILL"
    assert recovered["result"].request_sha256 == request.sha256
    assert recovered["result"].projection.terminal_no_fill is True
    store.persist_result(
        proposal.sha256,
        {
            "status": recovered["result"].status,
            "request_sha256": recovered["result"].request_sha256,
            "broker_write_boundary_crossed": recovered["result"].broker_write_boundary_crossed,
            "projection": recovered["result"].projection.model_dump(mode="json"),
        },
    )
    assert store.load_candidate() is None
    assert store.has_orphaned_durable_state() is False


def test_recovered_canary_finalizes_against_its_certified_adapter_after_release(
    tmp_path,
) -> None:
    from ibkr_paper_30d.canary_execution import CanaryExecutionResult
    from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
    from ibkr_paper_30d.product_capability import (
        ProductFamilyCertificationStatus,
        ProductFamilyCertificationStore,
    )
    from test_canary_pilot import _owner, _proposal

    db_path = tmp_path / "adapter-drift-canary.sqlite3"
    with Database.open(db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        install_multi_universe_schema_v4(db)
        proposal = _proposal()
        certified_adapter = "a" * 64
        deployed_adapter = "b" * 64
        original_store = ProductFamilyCertificationStore(
            db, current_adapter_sha256=certified_adapter
        )
        original_store.record_read_only_candidate_evidence(
            proposal.product_family,
            evidence_sha256="c" * 64,
            account_sha256=proposal.account_identity_sha256,
            adapter_sha256=certified_adapter,
            observed_at_utc=proposal.created_at_utc,
            expires_at_utc=proposal.expires_at_utc,
            paper_limitations=("PAPER_SIMULATION_ONLY",),
        )
        recorder = CanaryLifecycleRecorder(
            proposal.candidate_id,
            proposal.account_identity_sha256,
            proposal.product_family.sha256,
            proposal.canonical_contract.sha256,
        )
        for ordinal, step in enumerate(
            ("SUBMITTED", "BROKER_BOUND", "TERMINAL_NO_FILL"), 1
        ):
            recorder.record(
                CanaryBrokerLifecycleReceipt(
                    canary_id=proposal.candidate_id,
                    step=step,
                    endpoint="PAPER",
                    account_identity_sha256=proposal.account_identity_sha256,
                    product_family_sha256=proposal.product_family.sha256,
                    contract_identity_sha256=proposal.canonical_contract.sha256,
                    broker_event_id_sha256=f"{ordinal:064x}",
                    broker_snapshot_sha256=f"{ordinal + 10:064x}",
                    previous_receipt_sha256=recorder.last_receipt_sha256,
                    observed_at_utc=proposal.created_at_utc
                    + timedelta(seconds=ordinal),
                    open_orders=1 if step == "BROKER_BOUND" else 0,
                    positions=0,
                    economics_reconciled=False,
                )
            )
        changed_store = ProductFamilyCertificationStore(
            db, current_adapter_sha256=deployed_adapter
        )
        orchestrator = create_canary_pilot_orchestrator(
            coordinator=BrokerWriteCoordinator(),
            db_path=db_path,
            provider=None,
            toolbox=None,
            owner_pilot_authorization=_owner(),
            writer_binding_sha256="d" * 64,
            model="test-model",
            reasoning_effort="low",
            timeout_seconds=30,
            product_certification_store=changed_store,
            effective_approved_head=proposal.approved_head,
        )

        orchestrator.lifecycle_finalizer(
            proposal,
            CanaryExecutionResult(
                status="TERMINAL_NO_FILL",
                request_sha256="e" * 64,
                projection=recorder.projection(),
                broker_write_boundary_crossed=True,
            ),
        )

        projection = changed_store.projection(proposal.product_family)
        assert (
            projection.status
            is ProductFamilyCertificationStatus.ORDER_TRANSMIT_VERIFIED
        )
        assert projection.adapter_sha256 == certified_adapter


def test_v4_writer_factory_wires_path_scoped_sleeve_authority(
    tmp_path, monkeypatch
) -> None:
    from ibkr_paper_30d.broker_write_coordinator import BrokerWriteCoordinator
    from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4

    smtp = tmp_path / "Secrets" / "email_alerts.env"
    smtp.parent.mkdir(parents=True)
    smtp.write_text("synthetic", encoding="utf-8")
    db_path = tmp_path / "runtime.sqlite3"
    with Database.open(db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        install_multi_universe_schema_v4(db)
    config = SimpleNamespace(
        repo_root=tmp_path,
        db_path=db_path,
        paper_host="127.0.0.1",
        paper_port=4002,
        target_successor_epoch_id="AUTONOMY_EPOCH_3",
        target_successor_definition_sha256="1" * 64,
        initial_allocation=Decimal("500"),
    )
    preflight = SimpleNamespace(expected_account_hash="a" * 64)
    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime._current_head",
        lambda _root: "b" * 40,
    )

    writer = create_authoritative_writer(
        coordinator=BrokerWriteCoordinator(),
        db_path=db_path,
        config=config,
        preflight=preflight,
        execution_lock_verifier=lambda: True,
        uncertainty_reporter=lambda _reason: None,
        toolbox=object(),
        production_validation_sha256="c" * 64,
        validation_broker_factory=lambda: object(),
        current_adapter_sha256="d" * 64,
    )

    assert writer.sleeve_authority_reservation_store is not None
    assert callable(writer.sleeve_authority_snapshot_reader)
    assert callable(writer.sleeve_broker_evidence_collector)
    assert writer.canary_execution_adapter is not None
    assert callable(writer.canary_execution_adapter.begin_write)
    assert callable(writer.canary_execution_adapter.receipt_persister)
    assert callable(writer.canary_evidence_collector)
    assert writer.model_execution_engine.final_write_authority_required is True
    assert (
        writer.model_execution_engine._load().mechanics._runtime_final_write_authority_required
        is True
    )


def test_bag_sleeve_evidence_resolves_every_leg_from_broker() -> None:
    from ibkr_paper_30d.contract_ownership import canonical_contract_identity
    from ibkr_paper_30d.production_continuity_runtime import (
        _sleeve_broker_evidence_collector,
    )

    parent = canonical_contract_identity(
        {
            "conId": 9000,
            "secType": "BAG",
            "currency": "USD",
            "exchange": "SMART",
            "comboLegs": [
                {"conId": 9001, "ratio": 1, "action": "BUY", "exchange": "SMART"},
                {"conId": 9002, "ratio": 1, "action": "SELL", "exchange": "SMART"},
            ],
        }
    )

    class Broker:
        def reqContractDetails(self, requested):
            con_id = int(requested.conId)
            return [
                SimpleNamespace(
                    contract=SimpleNamespace(
                        conId=con_id,
                        secType="OPT",
                        currency="USD",
                        exchange="SMART",
                        primaryExchange="",
                        localSymbol=f"LEG-{con_id}",
                        tradingClass="SPY",
                        multiplier="100",
                    )
                )
            ]

    request = SimpleNamespace(sha256="f" * 64)
    evidence = _sleeve_broker_evidence_collector("a" * 64)(
        Broker(),
        request,
        {
            "model_write_context": {
                "canonical_contract": parent.model_dump(mode="json"),
                "order_ref": "codex-order-1",
            },
            "production_authority": {"authority_snapshot_sha256": "b" * 64},
        },
    )

    assert evidence["contract_identity_sha256"] == parent.sha256
    assert evidence["order_ref"] == "codex-order-1"
    assert [item["con_id"] for item in evidence["ownership_contracts"]] == [
        9000,
        9001,
        9002,
    ]


def test_sleeve_broker_evidence_binds_target_writer_reconciliation_and_owner() -> None:
    from ibkr_paper_30d.contract_ownership import canonical_contract_identity
    from ibkr_paper_30d.production_continuity_runtime import (
        _sleeve_broker_evidence_collector,
    )

    contract = canonical_contract_identity(
        {
            "conId": 756733,
            "secType": "STK",
            "currency": "USD",
            "exchange": "SMART",
            "primaryExchange": "ARCA",
            "localSymbol": "SPY",
            "tradingClass": "SPY",
        }
    )
    request = SimpleNamespace(
        sha256="f" * 64,
        capital_sleeve=SimpleNamespace(value="CONTINUOUS_SLEEVE"),
        input_bundle=SimpleNamespace(
            multi_sleeve_portfolio={
                "transition_target_sha256": "1" * 64,
                "writer_binding_sha256": "2" * 64,
            },
            contract_ownership_snapshot={
                "contract_sleeves": {contract.sha256: "CONTINUOUS_SLEEVE"}
            },
            reconciliation_receipt={"status": "PASS"},
        ),
    )
    evidence = _sleeve_broker_evidence_collector("a" * 64)(
        SimpleNamespace(),
        request,
        {
            "model_write_context": {
                "canonical_contract": contract.model_dump(mode="json"),
                "order_ref": "codex-order-2",
            },
            "production_authority": {"authority_snapshot_sha256": "b" * 64},
        },
    )

    assert evidence["transition_target_sha256"] == "1" * 64
    assert evidence["writer_binding_sha256"] == "2" * 64
    assert evidence["reconciliation_status"] == "PASS"
    assert evidence["owned_contract_sleeve"] == "CONTINUOUS_SLEEVE"
    assert evidence["management_identity_match"] is True
    assert evidence["possible_live_connection"] is False


def test_v4_snapshot_reader_rejects_missing_or_non_hash_adapter_identity(tmp_path):
    config = SimpleNamespace(target_successor_definition_sha256="1" * 64)

    with pytest.raises(
        ProductionRuntimeConfigurationError,
        match="CURRENT_ADAPTER_SHA256_REQUIRED",
    ):
        _ProductionSleeveAuthoritySnapshotReader(
            tmp_path / "runtime.sqlite3", config, "process-policy-v4"
        )


def test_multi_universe_composition_has_one_of_each_authority(tmp_path) -> None:
    from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
    from ibkr_paper_30d.production_continuity_runtime import (
        build_multi_universe_runtime_stores,
        inject_multi_universe_runtime_stores,
        validate_multi_universe_runtime_topology,
    )

    with Database.open(tmp_path / "runtime.sqlite3") as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        install_multi_universe_schema_v4(db)
        stores = build_multi_universe_runtime_stores(
            db, current_adapter_sha256="a" * 64
        )

    provider = SimpleNamespace()
    service = SimpleNamespace()
    coordinator = SimpleNamespace()
    writer = SimpleNamespace(execution_client_id=WRITER_CLIENT_ID)
    lock = object()
    inject_multi_universe_runtime_stores(stores, provider, service, coordinator, writer)
    report = validate_multi_universe_runtime_topology(
        providers=(provider,),
        service_loops=(service,),
        coordinators=(coordinator,),
        writers=(writer,),
        write_capable_client_ids=(WRITER_CLIENT_ID,),
        execution_locks=(lock,),
        stores=stores,
        direct_executor_selected=False,
    )

    assert report["status"] == "PASS"
    assert report["authority_counts"] == {
        "providers": 1,
        "service_loops": 1,
        "coordinators": 1,
        "writers": 1,
        "write_capable_clients": 1,
        "execution_locks": 1,
    }
    assert set(report["injected_stores"]) == {
        "capability",
        "ledger",
        "ownership",
        "reconciliation",
        "transition",
    }
    assert provider.multi_universe_stores is stores
    assert service.multi_universe_stores is stores
    assert coordinator.multi_universe_stores is stores
    assert writer.multi_universe_stores is stores


def test_multi_universe_runtime_authority_is_exact_and_shared() -> None:
    from ibkr_paper_30d.production_continuity_runtime import (
        inject_multi_universe_runtime_authority,
        normalize_multi_universe_launch_authority,
    )

    decision = {
        "schema": "MULTI_UNIVERSE_LAUNCH_DECISION_V1",
        "transition_phase": "SUPERVISION_BOUND",
        "supervision_binding_sha256": "1" * 64,
        "continuous_authority_sha256": "2" * 64,
        "entry_authority_mode": "REGULAR_ONLY",
        "writer_start_allowed": True,
        "management_actions_allowed": True,
        "continuity_actions_allowed": True,
        "new_regular_entries_allowed": True,
        "new_continuous_entries_allowed": False,
        "legacy_predecessor_allowed": False,
    }

    authority = normalize_multi_universe_launch_authority(decision)
    provider = SimpleNamespace()
    service = SimpleNamespace()
    writer = SimpleNamespace()
    inject_multi_universe_runtime_authority(authority, provider, service, writer)

    assert authority.transition_phase == "SUPERVISION_BOUND"
    assert authority.entry_authority_mode == "REGULAR_ONLY"
    assert provider.multi_universe_runtime_authority is authority
    assert service.multi_universe_runtime_authority is authority
    assert writer.multi_universe_runtime_authority is authority


def test_active_runtime_may_idle_continuous_entries_when_family_is_closed() -> None:
    from ibkr_paper_30d.production_continuity_runtime import (
        normalize_multi_universe_launch_authority,
    )

    authority = normalize_multi_universe_launch_authority(
        {
            "schema": "MULTI_UNIVERSE_LAUNCH_DECISION_V1",
            "transition_phase": "ACTIVE",
            "supervision_binding_sha256": "1" * 64,
            "continuous_authority_sha256": "2" * 64,
            "entry_authority_mode": "NORMAL",
            "writer_start_allowed": True,
            "management_actions_allowed": True,
            "continuity_actions_allowed": True,
            "new_regular_entries_allowed": True,
            "new_continuous_entries_allowed": False,
            "legacy_predecessor_allowed": False,
        }
    )

    assert authority.new_regular_entries_allowed is True
    assert authority.new_continuous_entries_allowed is False


@pytest.mark.parametrize(
    ("update", "reason"),
    [
        ({"supervision_binding_sha256": "bad"}, "SUPERVISION_BINDING_AMBIGUOUS"),
        (
            {"continuous_authority_sha256": "bad"},
            "CONTINUOUS_ENTRY_AUTHORITY_AMBIGUOUS",
        ),
        ({"entry_authority_mode": "NORMAL"}, "ENTRY_AUTHORITY_PHASE_MISMATCH"),
        ({"legacy_predecessor_allowed": True}, "PREDECESSOR_REACTIVATION_ATTEMPT"),
        ({"management_actions_allowed": False}, "MANAGEMENT_AUTHORITY_PHASE_MISMATCH"),
        (
            {"new_regular_entries_allowed": "false"},
            "MULTI_UNIVERSE_LAUNCH_AUTHORITY_INVALID",
        ),
    ],
)
def test_multi_universe_runtime_authority_rejects_ambiguous_claims(update, reason):
    from ibkr_paper_30d.production_continuity_runtime import (
        ProductionRuntimeConfigurationError,
        normalize_multi_universe_launch_authority,
    )

    decision = {
        "schema": "MULTI_UNIVERSE_LAUNCH_DECISION_V1",
        "transition_phase": "SUPERVISION_BOUND",
        "supervision_binding_sha256": "1" * 64,
        "continuous_authority_sha256": "2" * 64,
        "entry_authority_mode": "REGULAR_ONLY",
        "writer_start_allowed": True,
        "management_actions_allowed": True,
        "continuity_actions_allowed": True,
        "new_regular_entries_allowed": True,
        "new_continuous_entries_allowed": False,
        "legacy_predecessor_allowed": False,
    }
    decision.update(update)

    with pytest.raises(ProductionRuntimeConfigurationError, match=reason):
        normalize_multi_universe_launch_authority(decision)


@pytest.mark.parametrize(
    ("update", "reason"),
    [
        ({"providers": (object(), object())}, "PROVIDER_COUNT_INVALID"),
        ({"service_loops": ()}, "SERVICE_LOOP_COUNT_INVALID"),
        ({"coordinators": (object(), object())}, "COORDINATOR_COUNT_INVALID"),
        ({"writers": (object(), object())}, "WRITER_COUNT_INVALID"),
        ({"write_capable_client_ids": (19761, 19763)}, "WRITE_CLIENT_COUNT_INVALID"),
        ({"execution_locks": ()}, "EXECUTION_LOCK_COUNT_INVALID"),
        ({"direct_executor_selected": True}, "DIRECT_EXECUTOR_FORBIDDEN"),
    ],
)
def test_multi_universe_composition_rejects_parallel_authority(update, reason) -> None:
    from ibkr_paper_30d.production_continuity_runtime import (
        MultiUniverseRuntimeStores,
        validate_multi_universe_runtime_topology,
    )

    values = {
        "providers": (object(),),
        "service_loops": (object(),),
        "coordinators": (object(),),
        "writers": (SimpleNamespace(execution_client_id=WRITER_CLIENT_ID),),
        "write_capable_client_ids": (WRITER_CLIENT_ID,),
        "execution_locks": (object(),),
        "stores": MultiUniverseRuntimeStores(
            ledger=object(),
            ownership=object(),
            capability=object(),
            reconciliation=object(),
            transition=object(),
        ),
        "direct_executor_selected": False,
    }
    values.update(update)

    report = validate_multi_universe_runtime_topology(**values)

    assert report["status"] == "BLOCK"
    assert reason in report["reason_codes"]


from ibkr_paper_30d.production_authority import ProductionBrokerEvidence
from production_epoch_v1_fixture import build_production_epoch_v1_fixture

NOW = datetime(2026, 10, 1, 14, tzinfo=timezone.utc)


def test_production_snapshot_accepts_anchored_legacy_epoch_history(tmp_path) -> None:
    path = tmp_path / "production.sqlite3"
    build_production_epoch_v1_fixture(path)
    with Database.open(path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
    receipt = tmp_path / "auditor.json"
    policy = tmp_path / "market-policy.json"
    validation = tmp_path / "market-validation.json"
    for artifact in (receipt, policy, validation):
        artifact.write_text("{}", encoding="utf-8")
    artifact_sha256 = hashlib.sha256(b"{}").hexdigest()
    account_hash = expected_identity_hash("DU123456")
    broker = SimpleNamespace(
        reqCurrentTime=lambda: NOW,
        managedAccounts=lambda: ["DU123456"],
        all_order_visibility=True,
    )
    _broker_evidence_collector(path)(
        broker,
        SimpleNamespace(),
        {"open_orders": [], "positions": [], "executions": []},
    )
    config = SimpleNamespace(
        target_successor_epoch_id=None,
        initial_allocation=Decimal("500"),
        repo_root=Path(__file__).parents[2],
        auditor_receipt_path=receipt,
        market_policy_path=policy,
        market_validation_path=validation,
    )
    preflight = SimpleNamespace(
        expected_account_hash=account_hash,
        auditor_receipt_sha256=artifact_sha256,
        market_policy_sha256=artifact_sha256,
        market_validation_sha256=artifact_sha256,
    )

    snapshot = _ProductionSnapshotReader(
        db_path=path,
        config=config,
        preflight=preflight,
        execution_lock_verifier=lambda: True,
    )(SimpleNamespace(accepted_result_sha256="a" * 64))

    assert snapshot.authority_chains_valid is True


class FakeIB:
    def __init__(self) -> None:
        self.connect_calls = []
        self.RequestTimeout = 0.0
        self.request_timeout_at_connect = None
        self.disconnected = False

    def connect(self, host, port, **kwargs):
        self.request_timeout_at_connect = getattr(self, "RequestTimeout", None)
        self.connect_calls.append((host, port, kwargs))

    def isConnected(self):
        return True

    def managedAccounts(self):
        return ["DU123456"]

    def disconnect(self):
        self.disconnected = True


def test_broker_evidence_collector_returns_typed_evidence_and_persists_schema(
    tmp_path,
) -> None:
    path = tmp_path / "authority.sqlite3"
    with Database.open(path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)

    broker = SimpleNamespace(
        reqCurrentTime=lambda: NOW,
        managedAccounts=lambda: ["DU123456"],
        all_order_visibility=True,
    )
    evidence = _broker_evidence_collector(path)(
        broker,
        SimpleNamespace(),
        {"open_orders": [], "positions": [], "executions": []},
    )

    assert isinstance(evidence, ProductionBrokerEvidence)
    assert evidence.account_identity_sha256 == expected_identity_hash("DU123456")
    with Database.open(path) as db:
        payload = db.execute(
            "SELECT payload_json FROM state_events "
            "WHERE event_type='BROKER_AUTHORITY_OBSERVATION_V1'"
        ).fetchone()[0]
    assert '"schema":"BROKER_AUTHORITY_OBSERVATION_V1"' in payload


def test_broker_evidence_collector_reuses_fresh_server_time_within_pacing_window(
    tmp_path,
) -> None:
    path = tmp_path / "authority.sqlite3"
    with Database.open(path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)

    class PacedBroker:
        all_order_visibility = True

        def __init__(self) -> None:
            self.current_time_calls = 0

        def reqCurrentTime(self):
            self.current_time_calls += 1
            if self.current_time_calls > 1:
                raise TimeoutError("duplicate server-time request was paced")
            return NOW

        @staticmethod
        def managedAccounts():
            return ["DU123456"]

    broker = PacedBroker()
    collector = _broker_evidence_collector(path)
    raw = {"open_orders": [], "positions": [], "executions": []}

    first = collector(broker, SimpleNamespace(), raw)
    second = collector(broker, SimpleNamespace(), raw)

    assert first.broker_time_utc == NOW
    assert second.broker_time_utc == NOW
    assert broker.current_time_calls == 1
    with Database.open(path) as db:
        persisted = db.execute(
            "SELECT COUNT(*) FROM state_events "
            "WHERE event_type='BROKER_AUTHORITY_OBSERVATION_V1'"
        ).fetchone()[0]
    assert persisted == 2


def test_broker_evidence_collector_refreshes_server_time_after_pacing_window(
    tmp_path,
) -> None:
    path = tmp_path / "authority.sqlite3"
    with Database.open(path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)

    current = [NOW]

    class Broker:
        all_order_visibility = True

        def __init__(self) -> None:
            self.current_time_calls = 0

        def reqCurrentTime(self):
            self.current_time_calls += 1
            return current[0]

        @staticmethod
        def managedAccounts():
            return ["DU123456"]

    broker = Broker()
    collector = _broker_evidence_collector(path, now_utc=lambda: current[0])
    raw = {"open_orders": [], "positions": [], "executions": []}

    first = collector(broker, SimpleNamespace(), raw)
    current[0] += timedelta(seconds=16)
    second = collector(broker, SimpleNamespace(), raw)

    assert first.broker_time_utc == NOW
    assert second.broker_time_utc == NOW + timedelta(seconds=16)
    assert broker.current_time_calls == 2


def test_default_day1_dependencies_have_concrete_continuity_factories() -> None:
    dependencies = _default_dependencies()

    assert callable(dependencies.broker_write_coordinator_factory)
    assert callable(dependencies.model_executor_factory)
    assert callable(dependencies.critical_alert_reporter_factory)
    assert callable(dependencies.authoritative_writer_factory)
    assert callable(dependencies.continuity_watchdog_factory)
    assert callable(dependencies.continuity_store_factory)


@pytest.mark.parametrize(
    ("client_id", "read_only"),
    [(WRITER_CLIENT_ID, False), (OBSERVER_CLIENT_ID, True)],
)
def test_ibkr_session_factory_binds_exact_client_and_readonly_mode(
    client_id, read_only
) -> None:
    created = []
    factory = build_ibkr_session_factory(
        host="127.0.0.1",
        port=4002,
        expected_account_hash=expected_identity_hash("DU123456"),
        client_id=client_id,
        read_only=read_only,
        ib_factory=lambda: created.append(FakeIB()) or created[-1],
    )

    broker = factory()

    assert broker.client_id == client_id
    assert broker.read_only is read_only
    assert broker.all_order_visibility is True
    assert created[0].request_timeout_at_connect == 15.0
    assert created[0].connect_calls == [
        (
            "127.0.0.1",
            4002,
            {"clientId": client_id, "timeout": 15.0, "readonly": read_only},
        )
    ]


def test_missing_external_alert_configuration_fails_with_exact_reason(tmp_path) -> None:
    config = SimpleNamespace(repo_root=Path(tmp_path))

    with pytest.raises(
        ProductionRuntimeConfigurationError,
        match="EXTERNAL_ALERT_CONFIGURATION_MISSING",
    ):
        validate_production_runtime_configuration(config)


def test_readonly_observer_returns_only_canonical_facts(
    continuity_plan_factory,
) -> None:
    contract = SimpleNamespace(
        conId=756733,
        symbol="UTHR",
        localSymbol="UTHR",
        secType="BAG",
        exchange="SMART",
        currency="USD",
        lastTradeDateOrContractMonth="",
        strike=0,
        right="",
        multiplier="100",
        comboLegs=[],
    )
    plan = continuity_plan_factory(
        order_binding={
            "execution_client_id": OBSERVER_CLIENT_ID - 1,
            "account_identity_sha256": expected_identity_hash("DU123456"),
            "contract_identity_sha256": sha256_json(
                canonical_contract_identity(contract)
            ),
        }
    )
    order = SimpleNamespace(
        orderRef=plan.order_binding.order_ref,
        orderId=plan.order_binding.ibkr_order_id,
        permId=plan.order_binding.perm_id,
        clientId=plan.order_binding.execution_client_id,
        account="DU123456",
        action="BUY",
        orderType="LMT",
        totalQuantity=Decimal("1"),
        lmtPrice=Decimal("4.90"),
        auxPrice=0,
        tif="DAY",
        outsideRth=False,
    )
    status = SimpleNamespace(status="PreSubmitted", filled=0, remaining=1)
    trade = SimpleNamespace(contract=contract, order=order, orderStatus=status)
    position = SimpleNamespace(
        account="DU123456", contract=contract, position=Decimal("0"), avgCost=0
    )
    ib = SimpleNamespace(
        reqAllOpenOrders=lambda: [trade],
        positions=lambda: [position],
    )
    observer = ReadOnlyContinuityBroker(
        ib,
        account_identity_sha256=expected_identity_hash("DU123456"),
    )

    facts = observer.collect_continuity_facts(plan.order_binding, NOW)

    assert facts["ORDER_STATUS"]["value"] == "UNFILLED"
    assert facts["ORDER_REMAINING_QUANTITY"]["value"] == "1"
    assert facts["POSITION_EXISTS"]["value"] is False
    assert observer.read_only is True
    assert observer.client_id == OBSERVER_CLIENT_ID
    assert not hasattr(observer, "placeOrder")
    assert not hasattr(observer, "cancelOrder")


def test_readonly_observer_reuses_server_time_within_watchdog_tick() -> None:
    current = [0.0]

    class PacedBroker:
        def __init__(self) -> None:
            self.calls = 0

        def reqCurrentTime(self):
            self.calls += 1
            if self.calls > 1 and current[0] < 4.0:
                raise TimeoutError("duplicate server-time request was paced")
            return NOW + timedelta(seconds=self.calls)

    raw = PacedBroker()
    observer = ReadOnlyContinuityBroker(
        raw,
        account_identity_sha256=expected_identity_hash("DU123456"),
        monotonic=lambda: current[0],
    )

    first = observer.reqCurrentTime()
    second = observer.reqCurrentTime()

    assert first == second
    assert raw.calls == 1

    current[0] = 5.0
    refreshed = observer.reqCurrentTime()

    assert refreshed == NOW + timedelta(seconds=2)
    assert raw.calls == 2


def test_production_poller_submits_at_most_one_exact_command(
    tmp_path, continuity_plan_factory, monkeypatch
) -> None:
    account_hash = expected_identity_hash("DU123456")
    contract = SimpleNamespace(
        conId=756733,
        symbol="UTHR",
        localSymbol="UTHR",
        secType="BAG",
        exchange="SMART",
        currency="USD",
        lastTradeDateOrContractMonth="",
        strike=0,
        right="",
        multiplier="100",
        comboLegs=[],
    )
    contract_identity = canonical_contract_identity(contract)
    plan = continuity_plan_factory(
        order_binding={
            "execution_client_id": WRITER_CLIENT_ID,
            "account_identity_sha256": account_hash,
            "contract_identity_sha256": sha256_json(contract_identity),
        }
    )
    order = SimpleNamespace(
        orderRef=plan.order_binding.order_ref,
        orderId=plan.order_binding.ibkr_order_id,
        permId=plan.order_binding.perm_id,
        clientId=WRITER_CLIENT_ID,
        account="DU123456",
        action="BUY",
        orderType="LMT",
        totalQuantity=Decimal("1"),
        lmtPrice=Decimal("4.90"),
        auxPrice=0,
        tif="DAY",
        outsideRth=False,
    )
    trade = SimpleNamespace(
        contract=contract,
        order=order,
        orderStatus=SimpleNamespace(status="PreSubmitted", filled=0, remaining=1),
    )
    raw = SimpleNamespace(
        reqCurrentTime=lambda: NOW,
        reqAllOpenOrders=lambda: [trade],
        positions=lambda: [],
        disconnect=lambda: None,
    )
    broker = ReadOnlyContinuityBroker(raw, account_identity_sha256=account_hash)

    path = tmp_path / "runtime.sqlite3"
    with Database.open(path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v4(db)
        store = ContinuityStore(db)
        store.append_plan_event("ACTIVATED", plan)
        store.append_provider_event(
            plan.invocation_id,
            "TIMEOUT_CONFIRMED",
            {"failure_code": "MODEL_TIMEOUT"},
        )
        registry = {
            "schema": "EXPERIMENT_ORDER_REGISTRY_V3",
            "lifecycle_event": "BROKER_BOUND",
            "continuity_state": "ACTIVE",
            "plan_id": plan.plan_id,
            "plan_sha256": plan.sha256,
            "order_ref": plan.order_binding.order_ref,
            "ibkr_order_id": plan.order_binding.ibkr_order_id,
            "perm_id": plan.order_binding.perm_id,
            "execution_client_id": WRITER_CLIENT_ID,
            "account": "DU123456",
            "action": "BUY",
            "contract": contract_identity,
        }
        db.execute(
            "INSERT INTO experiment_order_registry("
            "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
            "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                "registry-1",
                plan.order_binding.order_ref,
                plan.order_binding.ibkr_order_id,
                plan.order_binding.perm_id,
                plan.order_binding.ibkr_order_id,
                contract.conId,
                "BUY",
                "1",
                canonical_bytes(registry).decode("utf-8"),
                sha256_json(registry),
                NOW.isoformat(),
            ),
        )

        submitted = []

        class Coordinator:
            def submit(self, command):
                submitted.append(command)
                future = Future()
                future.set_result(
                    SimpleNamespace(
                        success=True,
                        status="RETAINED",
                        reason_codes=(),
                        broker_validation={
                            "post_write_order": {
                                "orderRef": getattr(command, "order_ref", "mock"),
                                "orderId": getattr(command, "order_id", 0),
                                "permId": getattr(command, "perm_id", 0),
                                "status": "PreSubmitted",
                            },
                        },
                    )
                )
                return future

        coordinator = Coordinator()
        config = SimpleNamespace(
            initial_allocation=Decimal("500"),
            target_successor_epoch_id=None,
        )
        preflight = SimpleNamespace(expected_account_hash=account_hash)
        monkeypatch.setattr(
            "ibkr_paper_30d.production_continuity_runtime._ProductionClock.state",
            lambda self: "ACTIVE",
        )
        poller = ProductionContinuityPoller(
            coordinator=coordinator,
            config=config,
            preflight=preflight,
        )

        poller(db, broker, coordinator)
        poller(db, broker, coordinator)

        assert len(submitted) == 1
        assert submitted[0].source == "WATCHDOG"
        assert submitted[0].execution_client_id == WRITER_CLIENT_ID
        assert (
            db.execute("SELECT COUNT(*) FROM continuity_execution_events").fetchone()[0]
            == 1
        )
        # Durable intent barrier: one RETAINED result, three intent events
        assert (
            db.execute("SELECT COUNT(*) FROM continuity_execution_intents").fetchone()[0]
            == 3
        )


def test_poller_does_not_retransmit_after_uncertain_result(
    tmp_path, monkeypatch, continuity_plan_factory
) -> None:
    """If coordinator.submit succeeds but future.result() times out,
    the COMMAND_SUBMITTED execution event must prevent a second poll
    from submitting an equivalent command without reconciliation."""
    from ibkr_paper_30d.open_order_management import canonical_contract_identity

    account_hash = expected_identity_hash("DU123456")
    contract = SimpleNamespace(
        conId=123,
        symbol="AAPL",
        secType="STK",
        exchange="SMART",
        currency="USD",
        multiplier="100",
        comboLegs=[],
    )
    contract_identity = canonical_contract_identity(contract)
    plan = continuity_plan_factory(
        order_binding={
            "execution_client_id": WRITER_CLIENT_ID,
            "account_identity_sha256": account_hash,
            "contract_identity_sha256": sha256_json(contract_identity),
        }
    )
    order = SimpleNamespace(
        orderRef=plan.order_binding.order_ref,
        orderId=plan.order_binding.ibkr_order_id,
        permId=plan.order_binding.perm_id,
        clientId=WRITER_CLIENT_ID,
        account="DU123456",
        action="BUY",
        orderType="LMT",
        totalQuantity=Decimal("1"),
        lmtPrice=Decimal("4.90"),
        auxPrice=0,
        tif="DAY",
        outsideRth=False,
    )
    trade = SimpleNamespace(
        contract=contract,
        order=order,
        orderStatus=SimpleNamespace(status="PreSubmitted", filled=0, remaining=1),
    )
    raw = SimpleNamespace(
        reqCurrentTime=lambda: NOW,
        reqAllOpenOrders=lambda: [trade],
        positions=lambda: [],
        disconnect=lambda: None,
    )
    broker = ReadOnlyContinuityBroker(raw, account_identity_sha256=account_hash)

    path = tmp_path / "uncertain.sqlite3"
    with Database.open(path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v4(db)
        store = ContinuityStore(db)
        store.append_plan_event("ACTIVATED", plan)
        store.append_provider_event(
            plan.invocation_id,
            "TIMEOUT_CONFIRMED",
            {"failure_code": "MODEL_TIMEOUT"},
        )
        registry = {
            "schema": "EXPERIMENT_ORDER_REGISTRY_V3",
            "lifecycle_event": "BROKER_BOUND",
            "continuity_state": "ACTIVE",
            "plan_id": plan.plan_id,
            "plan_sha256": plan.sha256,
            "order_ref": plan.order_binding.order_ref,
            "ibkr_order_id": plan.order_binding.ibkr_order_id,
            "perm_id": plan.order_binding.perm_id,
            "execution_client_id": WRITER_CLIENT_ID,
            "account": "DU123456",
            "action": "BUY",
            "contract": contract_identity,
        }
        db.execute(
            "INSERT INTO experiment_order_registry("
            "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
            "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                "registry-1",
                plan.order_binding.order_ref,
                plan.order_binding.ibkr_order_id,
                plan.order_binding.perm_id,
                plan.order_binding.ibkr_order_id,
                contract.conId,
                "BUY",
                "1",
                canonical_bytes(registry).decode("utf-8"),
                sha256_json(registry),
                NOW.isoformat(),
            ),
        )

        submitted = []

        class UncertainCoordinator:
            def submit(self, command):
                submitted.append(command)
                future = Future()
                # Simulate timeout: never set result
                return future

        coordinator = UncertainCoordinator()
        config = SimpleNamespace(
            initial_allocation=Decimal("500"),
            target_successor_epoch_id=None,
        )
        preflight = SimpleNamespace(expected_account_hash=account_hash)
        monkeypatch.setattr(
            "ibkr_paper_30d.production_continuity_runtime._ProductionClock.state",
            lambda self: "ACTIVE",
        )
        poller = ProductionContinuityPoller(
            coordinator=coordinator,
            config=config,
            preflight=preflight,
        )

        # First poll: submits command, intent transitions to RESULT_UNKNOWN, then times out
        with pytest.raises(RuntimeError, match="CONTINUITY_WRITER_RESULT_TIMEOUT"):
            poller(db, broker, coordinator)

        assert len(submitted) == 1
        # No confirmed execution event because result is unknown
        assert (
            db.execute("SELECT COUNT(*) FROM continuity_execution_events").fetchone()[0]
            == 0
        )
        # Durable intent barrier: INTENT_RECORDED → SUBMISSION_ATTEMPTED → RESULT_UNKNOWN
        intent_states = [
            str(r[0]) for r in
            db.execute(
                "SELECT intent_state FROM continuity_execution_intents ORDER BY sequence"
            ).fetchall()
        ]
        assert intent_states == ["INTENT_RECORDED", "SUBMISSION_ATTEMPTED", "RESULT_UNKNOWN"]

        # Second poll with a fresh coordinator (simulating restart):
        # The active intent barrier must block retransmission.
        class FreshCoordinator:
            def submit(self, command):
                submitted.append(command)
                future = Future()
                future.set_result(
                    SimpleNamespace(
                        success=True,
                        status="RETAINED",
                        reason_codes=(),
                        broker_validation={
                            "post_write_order": {
                                "orderRef": getattr(command, "order_ref", "mock"),
                                "orderId": getattr(command, "order_id", 0),
                                "permId": getattr(command, "perm_id", 0),
                                "status": "PreSubmitted",
                            },
                        },
                    )
                )
                return future

        poller2 = ProductionContinuityPoller(
            coordinator=FreshCoordinator(),
            config=config,
            preflight=preflight,
        )
        poller2(db, broker, FreshCoordinator())

        # No additional command should have been submitted
        assert len(submitted) == 1


# ---- 10 crash / idempotency / restart cases ----


def _make_test_context(tmp_path, continuity_plan_factory, intent_state_after_reserve=None):
    """Build a minimal real poller + real coordinator context for crash tests."""
    from types import SimpleNamespace
    from decimal import Decimal
    from ibkr_paper_30d.open_order_management import canonical_contract_identity

    account_hash = expected_identity_hash("DU123456")
    contract = SimpleNamespace(
        conId=123,
        symbol="AAPL",
        secType="STK",
        exchange="SMART",
        currency="USD",
        multiplier="100",
        comboLegs=[],
    )
    contract_identity = canonical_contract_identity(contract)
    plan = continuity_plan_factory(
        order_binding={
            "execution_client_id": WRITER_CLIENT_ID,
            "account_identity_sha256": account_hash,
            "contract_identity_sha256": sha256_json(contract_identity),
        }
    )
    order = SimpleNamespace(
        orderRef=plan.order_binding.order_ref,
        orderId=plan.order_binding.ibkr_order_id,
        permId=plan.order_binding.perm_id,
        clientId=WRITER_CLIENT_ID,
        account="DU123456",
        action="BUY",
        orderType="LMT",
        totalQuantity=Decimal("1"),
        lmtPrice=Decimal("4.90"),
        auxPrice=0,
        tif="DAY",
        outsideRth=False,
    )
    trade = SimpleNamespace(
        contract=contract,
        order=order,
        orderStatus=SimpleNamespace(status="PreSubmitted", filled=0, remaining=1),
    )
    raw = SimpleNamespace(
        reqCurrentTime=lambda: NOW,
        reqAllOpenOrders=lambda: [trade],
        positions=lambda: [],
        disconnect=lambda: None,
    )
    broker = ReadOnlyContinuityBroker(raw, account_identity_sha256=account_hash)

    path = tmp_path / "crash.sqlite3"
    db = Database.open(path)
    install_successor_schema_v2(db)
    install_continuity_schema_v4(db)
    store = ContinuityStore(db)
    store.append_plan_event("ACTIVATED", plan)
    store.append_provider_event(
        plan.invocation_id,
        "TIMEOUT_CONFIRMED",
        {"failure_code": "MODEL_TIMEOUT"},
    )
    registry = {
        "schema": "EXPERIMENT_ORDER_REGISTRY_V3",
        "lifecycle_event": "BROKER_BOUND",
        "continuity_state": "ACTIVE",
        "plan_id": plan.plan_id,
        "plan_sha256": plan.sha256,
        "order_ref": plan.order_binding.order_ref,
        "ibkr_order_id": plan.order_binding.ibkr_order_id,
        "perm_id": plan.order_binding.perm_id,
        "execution_client_id": WRITER_CLIENT_ID,
        "account": "DU123456",
        "action": "BUY",
        "contract": contract_identity,
    }
    db.execute(
        "INSERT INTO experiment_order_registry("
        "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
        "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
        ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            "registry-1",
            plan.order_binding.order_ref,
            plan.order_binding.ibkr_order_id,
            plan.order_binding.perm_id,
            plan.order_binding.ibkr_order_id,
            contract.conId,
            "BUY",
            "1",
            canonical_bytes(registry).decode("utf-8"),
            sha256_json(registry),
            NOW.isoformat(),
        ),
    )
    if intent_state_after_reserve:
        store.reserve_execution_intent(
            plan_id=plan.plan_id,
            order_ref=plan.order_binding.order_ref,
            evaluation_id="eval-pre",
            execution_key="key-pre",
            command_type="MODIFY",
            command_sha256="a" * 64,
            payload={"pre": True},
        )

    config = SimpleNamespace(
        initial_allocation=Decimal("500"),
        target_successor_epoch_id=None,
    )
    preflight = SimpleNamespace(expected_account_hash=account_hash)
    return db, broker, plan, config, preflight


def test_crash_01_before_intent_persisted_no_command_sent(
    tmp_path, monkeypatch, continuity_plan_factory
) -> None:
    """CASO 1: Crash before intent persisted. No command sent."""
    db, broker, plan, config, preflight = _make_test_context(
        tmp_path, continuity_plan_factory
    )
    submitted = []

    class FailingStore:
        def __getattr__(self, name):
            return getattr(ContinuityStore(db), name)

        def reserve_execution_intent(self, **kw):
            raise RuntimeError("CRASH_BEFORE_PERSIST")

    poller = ProductionContinuityPoller(
        coordinator=_MockCoordinator(submitted),
        config=config,
        preflight=preflight,
    )
    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime._ProductionClock.state",
        lambda self: "ACTIVE",
    )
    # Patch ContinuityStore inside poller to use our failing store
    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime.ContinuityStore",
        lambda db: FailingStore(),
    )
    with pytest.raises(RuntimeError, match="CRASH_BEFORE_PERSIST"):
        poller(db, broker, _MockCoordinator(submitted))
    assert len(submitted) == 0


def test_crash_02_intent_persisted_but_not_submitted(
    tmp_path, monkeypatch, continuity_plan_factory
) -> None:
    """CASO 2: Intent persisted but crash before submit. Intent remains. No auto-transmit."""
    db, broker, plan, config, preflight = _make_test_context(
        tmp_path, continuity_plan_factory
    )
    submitted = []

    class SubmitCrashCoordinator:
        def submit(self, command):
            raise RuntimeError("CRASH_AT_SUBMIT")

    poller = ProductionContinuityPoller(
        coordinator=SubmitCrashCoordinator(),
        config=config,
        preflight=preflight,
    )
    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime._ProductionClock.state",
        lambda self: "ACTIVE",
    )
    with pytest.raises(RuntimeError, match="CRASH_AT_SUBMIT"):
        poller(db, broker, SubmitCrashCoordinator())
    assert len(submitted) == 0
    # Intent was recorded before the crash
    intent_states = [
        str(r[0]) for r in
        db.execute(
            "SELECT intent_state FROM continuity_execution_intents ORDER BY sequence"
        ).fetchall()
    ]
    assert intent_states == ["INTENT_RECORDED"]
    # Next evaluation must NOT submit because barrier is active
    poller2 = ProductionContinuityPoller(
        coordinator=_MockCoordinator(submitted),
        config=config,
        preflight=preflight,
    )
    poller2(db, broker, _MockCoordinator(submitted))
    assert len(submitted) == 0


def test_crash_03_submitted_but_result_unknown_blocks_retransmission(
    tmp_path, monkeypatch, continuity_plan_factory
) -> None:
    """CASO 3: Submit accepted, crash before result known. Next eval must block."""
    db, broker, plan, config, preflight = _make_test_context(
        tmp_path, continuity_plan_factory
    )
    submitted = []

    class NeverSetFuture:
        def submit(self, command):
            submitted.append(command)
            from concurrent.futures import Future
            return Future()  # never completes

    poller = ProductionContinuityPoller(
        coordinator=NeverSetFuture(),
        config=config,
        preflight=preflight,
    )
    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime._ProductionClock.state",
        lambda self: "ACTIVE",
    )
    with pytest.raises(RuntimeError, match="CONTINUITY_WRITER_RESULT_TIMEOUT"):
        poller(db, broker, NeverSetFuture())
    assert len(submitted) == 1
    intent_states = [
        str(r[0]) for r in
        db.execute(
            "SELECT intent_state FROM continuity_execution_intents ORDER BY sequence"
        ).fetchall()
    ]
    assert intent_states == ["INTENT_RECORDED", "SUBMISSION_ATTEMPTED", "RESULT_UNKNOWN"]
    # Fresh coordinator restart
    poller2 = ProductionContinuityPoller(
        coordinator=_MockCoordinator(submitted),
        config=config,
        preflight=preflight,
    )
    poller2(db, broker, _MockCoordinator(submitted))
    assert len(submitted) == 1


def test_crash_04_different_evaluation_same_logical_operation_blocked(
    tmp_path, monkeypatch, continuity_plan_factory
) -> None:
    """CASO 4: Different eval_id / execution_key but same scope. Barrier must catch it."""
    db, broker, plan, config, preflight = _make_test_context(
        tmp_path, continuity_plan_factory
    )
    submitted = []

    class FirstCoordinator:
        def submit(self, command):
            submitted.append(command)
            from concurrent.futures import Future
            f = Future()
            f.set_result(SimpleNamespace(
                success=True,
                status="RETAINED",
                reason_codes=(),
                broker_validation={
                    "post_write_order": {
                        "orderRef": getattr(command, "order_ref", "mock"),
                        "orderId": getattr(command, "order_id", 0),
                        "permId": getattr(command, "perm_id", 0),
                        "status": "PreSubmitted",
                    },
                },
            ))
            return f

    poller = ProductionContinuityPoller(
        coordinator=FirstCoordinator(),
        config=config,
        preflight=preflight,
    )
    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime._ProductionClock.state",
        lambda self: "ACTIVE",
    )
    poller(db, broker, FirstCoordinator())
    assert len(submitted) == 1

    # The fabricated coordinator result is not writer-attested, so the first
    # attempt becomes uncertain and the durable barrier blocks a later poll.
    latest = ContinuityStore(db).latest_execution_intent(plan.plan_id, plan.order_binding.order_ref)
    assert latest is not None
    assert latest["intent_state"] == "RESULT_UNKNOWN"

    poller(db, broker, FirstCoordinator())
    assert len(submitted) == 1


def test_crash_05_coordinator_restart_barrier_survives(
    tmp_path, monkeypatch, continuity_plan_factory
) -> None:
    """CASO 5: Restart BrokerWriteCoordinator. Barrier must be reconstructed from DB."""
    db, broker, plan, config, preflight = _make_test_context(
        tmp_path, continuity_plan_factory
    )
    submitted = []

    class UncertainCoordinator:
        def submit(self, command):
            submitted.append(command)
            from concurrent.futures import Future
            return Future()  # never completes

    poller = ProductionContinuityPoller(
        coordinator=UncertainCoordinator(),
        config=config,
        preflight=preflight,
    )
    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime._ProductionClock.state",
        lambda self: "ACTIVE",
    )
    with pytest.raises(RuntimeError, match="CONTINUITY_WRITER_RESULT_TIMEOUT"):
        poller(db, broker, UncertainCoordinator())

    # Simulate coordinator restart: brand-new coordinator instance
    fresh_coordinator = _MockCoordinator(submitted)
    poller2 = ProductionContinuityPoller(
        coordinator=fresh_coordinator,
        config=config,
        preflight=preflight,
    )
    poller2(db, broker, fresh_coordinator)
    assert len(submitted) == 1


def test_crash_06_partial_fill_must_not_duplicate(
    tmp_path, monkeypatch, continuity_plan_factory
) -> None:
    """CASO 6: Broker shows partial fill. Must not emit equivalent order based on stale info."""
    # Covered by the broader barrier logic; here we assert the store rejects
    # an equivalent reservation when an active intent exists.
    db, broker, plan, config, preflight = _make_test_context(
        tmp_path, continuity_plan_factory, intent_state_after_reserve="INTENT_RECORDED"
    )
    store = ContinuityStore(db)
    with pytest.raises(ContinuityStoreError, match="ACTIVE_INTENT_BARRIER"):
        store.reserve_execution_intent(
            plan_id=plan.plan_id,
            order_ref=plan.order_binding.order_ref,
            evaluation_id="eval-2",
            execution_key="key-2",
            command_type="MODIFY",
            command_sha256="b" * 64,
            payload={},
        )


def test_crash_07_broker_unconfirmed_state_remains_blocked(
    tmp_path, monkeypatch, continuity_plan_factory
) -> None:
    """CASO 7: Broker cannot confirm. RESULT_UNKNOWN persists and blocks indefinitely."""
    db, broker, plan, config, preflight = _make_test_context(
        tmp_path, continuity_plan_factory
    )
    submitted = []

    class UncertainCoordinator:
        def submit(self, command):
            submitted.append(command)
            from concurrent.futures import Future
            return Future()

    poller = ProductionContinuityPoller(
        coordinator=UncertainCoordinator(),
        config=config,
        preflight=preflight,
    )
    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime._ProductionClock.state",
        lambda self: "ACTIVE",
    )
    with pytest.raises(RuntimeError, match="CONTINUITY_WRITER_RESULT_TIMEOUT"):
        poller(db, broker, UncertainCoordinator())

    latest = ContinuityStore(db).latest_execution_intent(plan.plan_id, plan.order_binding.order_ref)
    assert latest is not None
    assert latest["intent_state"] == "RESULT_UNKNOWN"


def test_crash_08_reconciliation_blocked_without_authentic_evidence(
    tmp_path, monkeypatch, continuity_plan_factory
) -> None:
    """CASO 8: reconcile_execution_intent must BLOCK all attempts because
    no authenticated broker read path is available with current components."""
    from datetime import datetime, timezone

    db, broker, plan, config, preflight = _make_test_context(
        tmp_path, continuity_plan_factory
    )
    store = ContinuityStore(db)
    _, intent_id = store.reserve_execution_intent(
        plan_id=plan.plan_id,
        order_ref=plan.order_binding.order_ref,
        evaluation_id="eval-1",
        execution_key="key-1",
        command_type="MODIFY",
        command_sha256="c" * 64,
        payload={},
    )
    store.transition_execution_intent(
        intent_id=intent_id,
        plan_id=plan.plan_id,
        order_ref=plan.order_binding.order_ref,
        evaluation_id="eval-1",
        execution_key="key-1",
        intent_state="SUBMISSION_ATTEMPTED",
        command_type="MODIFY",
        command_sha256="c" * 64,
        payload={},
    )
    store.transition_execution_intent(
        intent_id=intent_id,
        plan_id=plan.plan_id,
        order_ref=plan.order_binding.order_ref,
        evaluation_id="eval-1",
        execution_key="key-1",
        intent_state="RESULT_UNKNOWN",
        command_type="MODIFY",
        command_sha256="c" * 64,
        payload={"reason": "timeout"},
    )
    # Even WITH valid evidence, reconciliation must BLOCK.
    with pytest.raises(ContinuityStoreError, match="RECONCILIATION_NOT_AUTHENTICATED"):
        store.reconcile_execution_intent(
            intent_id=intent_id,
            broker_evidence={
                "order_snapshot": {
                    "status": "Filled",
                    "filled": "1",
                    "remaining": "0",
                    "order_id": int(plan.order_binding.ibkr_order_id),
                    "perm_id": int(plan.order_binding.perm_id),
                },
                "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                "command_sha256": "c" * 64,
                "order_ref": plan.order_binding.order_ref,
                "account_identity_sha256": plan.order_binding.account_identity_sha256,
                "contract_identity_sha256": plan.order_binding.contract_identity_sha256,
                "executions": [{"shares": "1", "price": "4.90"}],
            },
        )
    # RESULT_UNKNOWN remains blocked.
    latest = store.latest_execution_intent(plan.plan_id, plan.order_binding.order_ref)
    assert latest is not None
    assert latest["intent_state"] == "RESULT_UNKNOWN"


def test_reconciliation_rejects_all_evidence_authenticity_required(
    tmp_path, monkeypatch, continuity_plan_factory
) -> None:
    """Any call to reconcile_execution_intent must be blocked because
    authentic broker evidence cannot be verified with current components."""
    from datetime import datetime, timezone

    db, broker, plan, config, preflight = _make_test_context(
        tmp_path, continuity_plan_factory
    )
    store = ContinuityStore(db)
    _, intent_id = store.reserve_execution_intent(
        plan_id=plan.plan_id,
        order_ref=plan.order_binding.order_ref,
        evaluation_id="eval-1",
        execution_key="key-1",
        command_type="MODIFY",
        command_sha256="c" * 64,
        payload={},
    )
    store.transition_execution_intent(
        intent_id=intent_id,
        plan_id=plan.plan_id,
        order_ref=plan.order_binding.order_ref,
        evaluation_id="eval-1",
        execution_key="key-1",
        intent_state="SUBMISSION_ATTEMPTED",
        command_type="MODIFY",
        command_sha256="c" * 64,
        payload={},
    )
    store.transition_execution_intent(
        intent_id=intent_id,
        plan_id=plan.plan_id,
        order_ref=plan.order_binding.order_ref,
        evaluation_id="eval-1",
        execution_key="key-1",
        intent_state="RESULT_UNKNOWN",
        command_type="MODIFY",
        command_sha256="c" * 64,
        payload={},
    )
    # Even invalid evidence is blocked at the authenticity gate.
    with pytest.raises(ContinuityStoreError, match="RECONCILIATION_NOT_AUTHENTICATED"):
        store.reconcile_execution_intent(
            intent_id=intent_id,
            broker_evidence={
                "order_snapshot": {
                    "status": "Filled",
                    "filled": "1",
                    "remaining": "0",
                    "order_id": int(plan.order_binding.ibkr_order_id),
                    "perm_id": int(plan.order_binding.perm_id),
                },
                "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                "command_sha256": "c" * 64,
                "order_ref": plan.order_binding.order_ref,
                "account_identity_sha256": "bad",
                "contract_identity_sha256": plan.order_binding.contract_identity_sha256,
            },
        )


def test_broker_confirmed_rejects_fabricated_non_empty_broker_validation(
    tmp_path, monkeypatch, continuity_plan_factory
) -> None:
    """Untrusted callers cannot fabricate broker evidence to release the barrier."""
    db, broker, plan, config, preflight = _make_test_context(
        tmp_path, continuity_plan_factory
    )
    submitted = []

    class FabricatedCoordinator:
        def submit(self, command):
            submitted.append(command)
            from concurrent.futures import Future
            f = Future()
            f.set_result(SimpleNamespace(
                success=True,
                status="RETAINED",
                reason_codes=(),
                broker_validation={
                    "post_write_order": {
                        "orderRef": command.order_ref,
                        "orderId": command.order_id,
                        "permId": command.perm_id,
                        "status": "PreSubmitted",
                    },
                    "production_authority": {
                        "authority_snapshot_sha256": "a" * 64,
                        "broker_evidence_sha256": "b" * 64,
                    },
                },
            ))
            return f

    poller = ProductionContinuityPoller(
        coordinator=FabricatedCoordinator(),
        config=config,
        preflight=preflight,
    )
    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime._ProductionClock.state",
        lambda self: "ACTIVE",
    )
    poller(db, broker, FabricatedCoordinator())

    # The intent remains blocked because the result did not originate from the
    # coordinator's attached writer capability.
    latest = ContinuityStore(db).latest_execution_intent(plan.plan_id, plan.order_binding.order_ref)
    assert latest is not None
    assert latest["intent_state"] == "RESULT_UNKNOWN"


def test_crash_09_sqlite_write_failure_before_submit_no_command_sent(
    tmp_path, monkeypatch, continuity_plan_factory
) -> None:
    """CASO 9: SQLite write fails before submit. Zero commands sent."""
    db, broker, plan, config, preflight = _make_test_context(
        tmp_path, continuity_plan_factory
    )
    submitted = []

    class FailingTransaction:
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False

    class FailingStore(ContinuityStore):
        def reserve_execution_intent(self, **kw):
            # Simulate SQLite failure during transaction
            raise RuntimeError("SQLITE_IOERR")

    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime._ProductionClock.state",
        lambda self: "ACTIVE",
    )
    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime.ContinuityStore",
        lambda db: FailingStore(db),
    )
    poller = ProductionContinuityPoller(
        coordinator=_MockCoordinator(submitted),
        config=config,
        preflight=preflight,
    )
    with pytest.raises(RuntimeError, match="SQLITE_IOERR"):
        poller(db, broker, _MockCoordinator(submitted))
    assert len(submitted) == 0


def test_crash_10_concurrent_reservation_only_one_succeeds(
    tmp_path, monkeypatch, continuity_plan_factory
) -> None:
    """CASO 10: Two concurrent attempts to reserve same scope. Only one accepted."""
    db, broker, plan, config, preflight = _make_test_context(
        tmp_path, continuity_plan_factory
    )
    # Capture the DB file path so each thread opens its own connection
    db_path = db.connection.execute("PRAGMA database_list").fetchone()[2]
    successes = []
    failures = []

    def attempt(label):
        try:
            # Each thread uses its own connection to demonstrate file-level locking
            thread_db = Database.open(db_path)
            thread_store = ContinuityStore(thread_db)
            thread_store.reserve_execution_intent(
                plan_id=plan.plan_id,
                order_ref=plan.order_binding.order_ref,
                evaluation_id=f"eval-{label}",
                execution_key=f"key-{label}",
                command_type="MODIFY",
                command_sha256="d" * 64,
                payload={"attempt": label},
            )
            successes.append(label)
        except ContinuityStoreError as exc:
            if "ACTIVE_INTENT_BARRIER" in str(exc):
                failures.append(label)
            else:
                raise

    import threading
    t1 = threading.Thread(target=attempt, args=("first",))
    t2 = threading.Thread(target=attempt, args=("second",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert len(successes) == 1
    assert len(failures) == 1


def test_result_unknown_blocks_new_orders_at_writer_boundary(
    tmp_path, monkeypatch, continuity_plan_factory
) -> None:
    """RESULT_UNKNOWN barrier must prevent new incompatible orders from reaching
    the BrokerWriteCoordinator even with a healthy broker connection."""
    db, broker, plan, config, preflight = _make_test_context(
        tmp_path, continuity_plan_factory
    )
    store = ContinuityStore(db)
    _, intent_id = store.reserve_execution_intent(
        plan_id=plan.plan_id,
        order_ref=plan.order_binding.order_ref,
        evaluation_id="eval-1",
        execution_key="key-1",
        command_type="MODIFY",
        command_sha256="c" * 64,
        payload={},
    )
    store.transition_execution_intent(
        intent_id=intent_id,
        plan_id=plan.plan_id,
        order_ref=plan.order_binding.order_ref,
        evaluation_id="eval-1",
        execution_key="key-1",
        intent_state="SUBMISSION_ATTEMPTED",
        command_type="MODIFY",
        command_sha256="c" * 64,
        payload={},
    )
    store.transition_execution_intent(
        intent_id=intent_id,
        plan_id=plan.plan_id,
        order_ref=plan.order_binding.order_ref,
        evaluation_id="eval-1",
        execution_key="key-1",
        intent_state="RESULT_UNKNOWN",
        command_type="MODIFY",
        command_sha256="c" * 64,
        payload={"reason": "timeout"},
    )

    # Simulate a new poller cycle with a fresh coordinator
    submitted = []
    coordinator = _MockCoordinator(submitted)
    poller = ProductionContinuityPoller(
        coordinator=coordinator,
        config=config,
        preflight=preflight,
    )
    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime._ProductionClock.state",
        lambda self: "ACTIVE",
    )
    poller(db, broker, coordinator)
    # No commands should be submitted because RESULT_UNKNOWN blocks
    assert len(submitted) == 0

    # The barrier remains active
    latest = store.latest_execution_intent(plan.plan_id, plan.order_binding.order_ref)
    assert latest is not None
    assert latest["intent_state"] == "RESULT_UNKNOWN"


def test_unknown_barrier_supervises_other_plans_without_submitting(
    tmp_path, monkeypatch, continuity_plan_factory
) -> None:
    """All plans remain visible, but account-wide uncertainty blocks writes."""
    from decimal import Decimal
    from ibkr_paper_30d.open_order_management import canonical_contract_identity

    db, broker, plan, config, preflight = _make_test_context(
        tmp_path, continuity_plan_factory
    )
    store = ContinuityStore(db)

    # Create Plan B with different order_ref
    from ibkr_paper_30d.continuity_models import CodexOrderContinuityPlan
    second_plan = CodexOrderContinuityPlan.model_validate(
        {
            **plan.model_dump(mode="json"),
            "plan_id": "plan-2",
            "order_binding": {
                **plan.order_binding.model_dump(mode="json"),
                "order_ref": "order-79",
            },
        }
    )
    store.append_plan_event("ACTIVATED", second_plan)

    # Add registry entry for Plan B
    contract = SimpleNamespace(
        conId=123,
        symbol="AAPL",
        secType="STK",
        exchange="SMART",
        currency="USD",
        multiplier="100",
        comboLegs=[],
    )
    contract_identity = canonical_contract_identity(contract)
    registry_b = {
        "schema": "EXPERIMENT_ORDER_REGISTRY_V3",
        "lifecycle_event": "BROKER_BOUND",
        "continuity_state": "ACTIVE",
        "plan_id": second_plan.plan_id,
        "plan_sha256": second_plan.sha256,
        "order_ref": second_plan.order_binding.order_ref,
        "ibkr_order_id": second_plan.order_binding.ibkr_order_id,
        "perm_id": second_plan.order_binding.perm_id,
        "execution_client_id": WRITER_CLIENT_ID,
        "account": "DU123456",
        "action": "BUY",
        "contract": contract_identity,
    }
    db.execute(
        "INSERT INTO experiment_order_registry("
        "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
        "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
        ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            "registry-2",
            second_plan.order_binding.order_ref,
            second_plan.order_binding.ibkr_order_id,
            second_plan.order_binding.perm_id,
            second_plan.order_binding.ibkr_order_id,
            contract.conId,
            "BUY",
            "1",
            canonical_bytes(registry_b).decode("utf-8"),
            sha256_json(registry_b),
            NOW.isoformat(),
        ),
    )

    # Add broker trade for Plan B
    order_b = SimpleNamespace(
        orderRef=second_plan.order_binding.order_ref,
        orderId=second_plan.order_binding.ibkr_order_id,
        permId=second_plan.order_binding.perm_id,
        clientId=WRITER_CLIENT_ID,
        account="DU123456",
        action="BUY",
        orderType="LMT",
        totalQuantity=Decimal("1"),
        lmtPrice=Decimal("4.90"),
        auxPrice=0,
        tif="DAY",
        outsideRth=False,
    )
    trade_b = SimpleNamespace(
        contract=contract,
        order=order_b,
        orderStatus=SimpleNamespace(status="PreSubmitted", filled=0, remaining=1),
    )
    original_orders = broker._broker.reqAllOpenOrders
    broker._broker.reqAllOpenOrders = lambda: [*original_orders(), trade_b]

    # Block plan-1
    _, intent_id = store.reserve_execution_intent(
        plan_id=plan.plan_id,
        order_ref=plan.order_binding.order_ref,
        evaluation_id="eval-1",
        execution_key="key-1",
        command_type="MODIFY",
        command_sha256="c" * 64,
        payload={"plan": "plan-1"},
    )
    store.transition_execution_intent(
        intent_id=intent_id,
        plan_id=plan.plan_id,
        order_ref=plan.order_binding.order_ref,
        evaluation_id="eval-1",
        execution_key="key-1",
        intent_state="SUBMISSION_ATTEMPTED",
        command_type="MODIFY",
        command_sha256="c" * 64,
        payload={},
    )
    store.transition_execution_intent(
        intent_id=intent_id,
        plan_id=plan.plan_id,
        order_ref=plan.order_binding.order_ref,
        evaluation_id="eval-1",
        execution_key="key-1",
        intent_state="RESULT_UNKNOWN",
        command_type="MODIFY",
        command_sha256="c" * 64,
        payload={"reason": "timeout"},
    )

    submitted = []
    coordinator = _MockCoordinator(submitted)
    poller = ProductionContinuityPoller(
        coordinator=coordinator,
        config=config,
        preflight=preflight,
    )
    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime._ProductionClock.state",
        lambda self: "ACTIVE",
    )
    poller(db, broker, coordinator)

    # Plan A maintains its barrier
    latest_a = store.latest_execution_intent(plan.plan_id, plan.order_binding.order_ref)
    assert latest_a is not None
    assert latest_a["intent_state"] == "RESULT_UNKNOWN"

    # Plan B received explicit supervision without reaching the writer because
    # both plans share the same PAPER account and aggregate exposure.
    assert submitted == []
    latest_b = store.latest_execution_intent(second_plan.plan_id, second_plan.order_binding.order_ref)
    assert latest_b is None

    # Poll results must report supervision for BOTH plans explicitly
    assert len(poller.poll_results) == 2
    result_a = next(r for r in poller.poll_results if r["plan_id"] == plan.plan_id)
    result_b = next(r for r in poller.poll_results if r["plan_id"] == second_plan.plan_id)
    assert result_a["action"] == "BLOCKED"
    assert result_a["reason"] == "ACTIVE_INTENT_BARRIER"
    assert result_b["action"] == "BLOCKED"
    assert result_b["reason"] == "GLOBAL_ACTIVE_INTENT_BARRIER"


def test_coordinator_completion_is_bound_to_attached_writer_capability() -> None:
    coordinator = BrokerWriteCoordinator()
    command = SimpleNamespace(
        durable_sequence=1,
        execution_key="trusted-key",
        sha256="a" * 64,
    )
    future = coordinator.submit(command)
    capability = coordinator.attach_writer()
    claimed_command, claimed_future = coordinator.claim(capability, timeout=0.1)
    result = SimpleNamespace(success=True, status="RETAINED")

    assert coordinator.is_writer_completion(command, result) is False
    coordinator.complete(capability, claimed_command, claimed_future, result)

    assert future.result(timeout=0.1) is result
    assert coordinator.is_writer_completion(command, result) is True


class _MockCoordinator:
    """Mock coordinator that returns authenticated broker results."""

    def __init__(self, submitted):
        self.submitted = submitted
        self._trusted_result = None

    def submit(self, command):
        self.submitted.append(command)
        from concurrent.futures import Future
        f = Future()
        self._trusted_result = SimpleNamespace(
            success=True,
            status="RETAINED",
            reason_codes=(),
            broker_validation={
                "post_write_order": {
                    "orderRef": getattr(command, "order_ref", "mock"),
                    "orderId": getattr(command, "order_id", 0),
                    "permId": getattr(command, "perm_id", 0),
                    "status": "PreSubmitted",
                },
                "trades": [],
                "open_orders": [],
            },
        )
        f.set_result(self._trusted_result)
        return f

    def is_writer_completion(self, command, result):
        del command
        return result is self._trusted_result


def _hex64(n: str) -> str:
    return hashlib.sha256(n.encode()).hexdigest()


def test_coordinator_rejects_duplicate_execution_key_with_different_hash(
    tmp_path,
) -> None:
    """If two commands share the same execution_key but different sha256,
    the coordinator must reject the second with DUPLICATE_EXECUTION_KEY.
    This prevents ambiguous retransmissions."""
    coordinator = BrokerWriteCoordinator()

    from ibkr_paper_30d.continuity_models import ContinuityAuthorityClass
    from ibkr_paper_30d.continuity_liability import MaximumLiabilityRequirement

    liability = MaximumLiabilityRequirement(
        plan_id="plan-1",
        plan_sha256=_hex64("b"),
        maximum_authorized_liability=Decimal("500"),
        account_identity_sha256=_hex64("d"),
        contract_identity_sha256=_hex64("e"),
        proposed_order_sha256=_hex64("k"),
        required_leg_identity_sha256=(_hex64("leg"),),
        maximum_evidence_age_seconds=Decimal("30"),
    )
    cmd1 = AuthorizedBrokerCommand(
        command_id="cmd-1",
        durable_sequence=1,
        execution_key="key-1",
        source="WATCHDOG",
        command_type="MODIFY",
        evaluation_id="eval-1",
        evaluation_sha256=_hex64("a"),
        plan_id="plan-1",
        plan_sha256=_hex64("b"),
        fact_snapshot_sha256=_hex64("c"),
        order_ref="ref-1",
        order_id=1,
        perm_id=1,
        execution_client_id=WRITER_CLIENT_ID,
        account_identity_sha256=_hex64("d"),
        contract_identity_sha256=_hex64("e"),
        observed_state_sha256=_hex64("f"),
        epoch_id="epoch-1",
        definition_sha256=_hex64("g"),
        owner_authorization_sha256=_hex64("h"),
        authority_class=ContinuityAuthorityClass.NONEXPANDING_EXISTING_AUTHORITY,
        new_total_quantity=Decimal("1"),
        new_limit_price=Decimal("100"),
        new_tif="DAY",
        new_good_till_date_utc=None,
        canonical_contract_sha256=None,
        resolved_total_quantity=Decimal("1"),
        resolved_limit_price=Decimal("100"),
        proposed_order_sha256=_hex64("k"),
        maximum_authorized_liability=Decimal("500"),
        liability_requirement=liability,
        created_at_utc=datetime.now(timezone.utc),
    )
    cmd2 = cmd1.model_copy(update={"evaluation_sha256": _hex64("x")})

    future1 = coordinator.submit(cmd1)
    future2 = coordinator.submit(cmd2)

    assert future1 is not future2
    result = future2.result()
    assert result.status == "BLOCKED"
    assert "DUPLICATE_EXECUTION_KEY" in result.reason_codes


def test_coordinator_returns_same_future_for_identical_resubmission(
    tmp_path,
) -> None:
    """If the exact same command (same execution_key and sha256) is resubmitted,
    the coordinator must return the original Future, providing natural
    idempotency without creating duplicate queue entries."""
    coordinator = BrokerWriteCoordinator()

    from ibkr_paper_30d.continuity_models import ContinuityAuthorityClass
    from ibkr_paper_30d.continuity_liability import MaximumLiabilityRequirement

    liability = MaximumLiabilityRequirement(
        plan_id="plan-1",
        plan_sha256=_hex64("b"),
        maximum_authorized_liability=Decimal("500"),
        account_identity_sha256=_hex64("d"),
        contract_identity_sha256=_hex64("e"),
        proposed_order_sha256=_hex64("k"),
        required_leg_identity_sha256=(_hex64("leg"),),
        maximum_evidence_age_seconds=Decimal("30"),
    )
    cmd = AuthorizedBrokerCommand(
        command_id="cmd-1",
        durable_sequence=1,
        execution_key="key-1",
        source="WATCHDOG",
        command_type="MODIFY",
        evaluation_id="eval-1",
        evaluation_sha256=_hex64("a"),
        plan_id="plan-1",
        plan_sha256=_hex64("b"),
        fact_snapshot_sha256=_hex64("c"),
        order_ref="ref-1",
        order_id=1,
        perm_id=1,
        execution_client_id=WRITER_CLIENT_ID,
        account_identity_sha256=_hex64("d"),
        contract_identity_sha256=_hex64("e"),
        observed_state_sha256=_hex64("f"),
        epoch_id="epoch-1",
        definition_sha256=_hex64("g"),
        owner_authorization_sha256=_hex64("h"),
        authority_class=ContinuityAuthorityClass.NONEXPANDING_EXISTING_AUTHORITY,
        new_total_quantity=Decimal("1"),
        new_limit_price=Decimal("100"),
        new_tif="DAY",
        new_good_till_date_utc=None,
        canonical_contract_sha256=None,
        resolved_total_quantity=Decimal("1"),
        resolved_limit_price=Decimal("100"),
        proposed_order_sha256=_hex64("k"),
        maximum_authorized_liability=Decimal("500"),
        liability_requirement=liability,
        created_at_utc=datetime.now(timezone.utc),
    )

    future1 = coordinator.submit(cmd)
    future2 = coordinator.submit(cmd)

    assert future1 is future2


def test_production_alert_freezes_first_and_deduplicates_across_time(tmp_path) -> None:
    path = tmp_path / "alerts.sqlite3"
    with Database.open(path) as db:
        KillSwitchStore(db).set("KILL_SWITCH_CLEAR", reason="test setup", actor="TEST")
    trace = []
    times = iter(
        (
            datetime(2026, 10, 1, 14, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 1, 14, 5, tzinfo=timezone.utc),
        )
    )

    class SMTP:
        def send(self, message):
            trace.append("smtp")
            return "smtp-receipt"

    class EventLog:
        def write(self, alert):
            trace.append("eventlog")
            return "eventlog-receipt"

    reporter = ProductionCriticalAlertReporter(
        db_path=path,
        smtp_config_path=tmp_path / "unused.env",
        launch_attempt_id="launch-1",
        smtp_factory=lambda path: SMTP(),
        event_log_factory=EventLog,
        now_utc=lambda: next(times),
    )

    reporter("CONTINUITY_WATCHDOG_FAILED")
    reporter("CONTINUITY_WATCHDOG_FAILED")

    with Database.open(path) as db:
        assert KillSwitchStore(db).current() == "KILL_SWITCH_TRIGGERED"
        assert db.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == 1
    assert trace == ["eventlog", "smtp"]


def test_superseded_plan_reuses_only_exact_verified_broker_anchor(
    tmp_path, continuity_plan_factory
) -> None:
    account_hash = expected_identity_hash("DU123456")
    contract = {
        "conId": 756733,
        "symbol": "UTHR",
        "localSymbol": "UTHR",
        "secType": "BAG",
        "exchange": "SMART",
        "currency": "USD",
        "expiry": "",
        "strike": "0",
        "right": "",
        "multiplier": "100",
        "comboLegs": [],
        "attributes": {},
    }
    first = continuity_plan_factory(
        order_binding={
            "execution_client_id": WRITER_CLIENT_ID,
            "account_identity_sha256": account_hash,
            "contract_identity_sha256": sha256_json(contract),
        }
    )
    successor = continuity_plan_factory(
        plan_id="plan-test-2",
        plan_version=2,
        predecessor_plan_sha256=first.sha256,
        order_binding={
            "execution_client_id": WRITER_CLIENT_ID,
            "account_identity_sha256": account_hash,
            "contract_identity_sha256": sha256_json(contract),
        },
    )
    registry = {
        "plan_sha256": first.sha256,
        "order_ref": first.order_binding.order_ref,
        "ibkr_order_id": first.order_binding.ibkr_order_id,
        "perm_id": first.order_binding.perm_id,
        "execution_client_id": WRITER_CLIENT_ID,
        "account": "DU123456",
        "action": "BUY",
        "contract": contract,
    }
    path = tmp_path / "anchor.sqlite3"
    with Database.open(path) as db:
        db.execute(
            "INSERT INTO experiment_order_registry("
            "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
            "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                "registry-anchor",
                first.order_binding.order_ref,
                first.order_binding.ibkr_order_id,
                first.order_binding.perm_id,
                first.order_binding.ibkr_order_id,
                756733,
                "BUY",
                "1",
                canonical_bytes(registry).decode("utf-8"),
                sha256_json(registry),
                NOW.isoformat(),
            ),
        )

        binding = _verified_registry_binding(db, successor)

    assert binding is not None
    assert binding["plan_sha256"] == successor.sha256


def test_validate_only_constructs_composition_without_broker_io(
    tmp_path, monkeypatch
) -> None:
    smtp = tmp_path / "Secrets" / "email_alerts.env"
    smtp.parent.mkdir(parents=True)
    smtp.write_text("synthetic", encoding="utf-8")
    config = SimpleNamespace(
        repo_root=tmp_path,
        db_path=tmp_path / "runtime.sqlite3",
        launch_attempt_id="validate-only",
        target_successor_epoch_id="AUTONOMY_EPOCH_2",
        target_successor_definition_sha256="1" * 64,
        initial_allocation=Decimal("500"),
        paper_host="127.0.0.1",
        paper_port=4002,
    )
    preflight = SimpleNamespace(expected_account_hash="a" * 64)
    calls = []

    with Database.open(config.db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v4(db)
        from ibkr_paper_30d.multi_universe_schema import (
            install_multi_universe_schema_v4,
        )

        install_multi_universe_schema_v4(db)

    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime._current_head",
        lambda _root: "c" * 40,
    )

    def session_factory(**kwargs):
        calls.append(("configured", kwargs["client_id"], kwargs["read_only"]))

        def forbidden_connect():
            raise AssertionError("validate_only must not connect")

        return forbidden_connect

    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime.build_ibkr_session_factory",
        session_factory,
    )

    result = validate_production_composition(
        config=config,
        preflight=preflight,
        toolbox=object(),
        production_validation_sha256="b" * 64,
    )

    assert result["status"] == "PASS"
    assert result["broker_connections"] == 0
    assert result["broker_writes"] == 0
    assert result["model_executor_coordinated"] is True
    assert result["model_executor_armed"] is False
    assert result["writer_started"] is True
    assert result["writer_stopped"] is True
    assert result["watchdog_started"] is True
    assert result["watchdog_stopped"] is True
    assert result["writer_sole_capability"] is True
    assert result["legacy_direct_executor_selected"] is False
    assert result["production_gates_callable"] is True
    assert result["liability_evidence_collector_callable"] is True
    assert result["canary_execution_adapter_wired"] is True
    assert result["canary_evidence_collector_callable"] is True
    assert calls == [
        ("configured", WRITER_CLIENT_ID, False),
        ("configured", OBSERVER_CLIENT_ID, True),
    ]


def test_validate_only_accepts_v5_predecessor(tmp_path, monkeypatch) -> None:
    """Validate-only with continuity v4 and no multi-universe must pass."""
    smtp = tmp_path / "Secrets" / "email_alerts.env"
    smtp.parent.mkdir(parents=True)
    smtp.write_text("synthetic", encoding="utf-8")
    config = SimpleNamespace(
        repo_root=tmp_path,
        db_path=tmp_path / "runtime.sqlite3",
        launch_attempt_id="validate-only-v5",
        target_successor_epoch_id=None,
        target_successor_definition_sha256=None,
        initial_allocation=Decimal("500"),
        paper_host="127.0.0.1",
        paper_port=4002,
    )
    preflight = SimpleNamespace(expected_account_hash="a" * 64)

    with Database.open(config.db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v4(db)

    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime._current_head",
        lambda _root: "c" * 40,
    )

    def session_factory(**kwargs):
        def forbidden_connect():
            raise AssertionError("validate_only must not connect")
        return forbidden_connect

    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime.build_ibkr_session_factory",
        session_factory,
    )

    result = validate_production_composition(
        config=config,
        preflight=preflight,
        toolbox=object(),
        production_validation_sha256="b" * 64,
    )

    assert result["status"] == "PASS"
    assert result["broker_connections"] == 0
    assert result["broker_writes"] == 0


def test_validate_only_blocks_v4_without_continuity_v4(tmp_path) -> None:
    """Validate-only must block when multi-universe v4 exists but continuity v4 is missing."""
    from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4

    smtp = tmp_path / "Secrets" / "email_alerts.env"
    smtp.parent.mkdir(parents=True)
    smtp.write_text("synthetic", encoding="utf-8")

    db_path = tmp_path / "runtime.sqlite3"
    with Database.open(db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        install_multi_universe_schema_v4(db)

    config = SimpleNamespace(
        repo_root=tmp_path,
        db_path=db_path,
        launch_attempt_id="validate-only-v4-no-continuity",
        target_successor_epoch_id="AUTONOMY_EPOCH_2",
        target_successor_definition_sha256="1" * 64,
        initial_allocation=Decimal("500"),
        paper_host="127.0.0.1",
        paper_port=4002,
    )
    preflight = SimpleNamespace(expected_account_hash="a" * 64)

    result = validate_production_composition(
        config=config,
        preflight=preflight,
        toolbox=object(),
        production_validation_sha256="b" * 64,
    )
    assert result["status"] == "BLOCK"
    assert "CONTINUITY_SCHEMA_V4_INVALID" in result["reason_codes"]


def test_production_liability_collector_proves_exact_vertical_maximum_loss() -> None:
    account_hash = expected_identity_hash("DU123456")
    combo_legs = [
        SimpleNamespace(conId=550001, ratio=1, action="BUY", exchange="SMART"),
        SimpleNamespace(conId=560001, ratio=1, action="SELL", exchange="SMART"),
    ]
    contract = SimpleNamespace(
        conId=0,
        symbol="UTHR",
        localSymbol="UTHR",
        secType="BAG",
        exchange="SMART",
        currency="USD",
        lastTradeDateOrContractMonth="",
        strike=0,
        right="",
        multiplier="100",
        comboLegs=combo_legs,
    )
    order = SimpleNamespace(
        orderRef="codex-order-78",
        orderId=78,
        permId=225256222,
        clientId=WRITER_CLIENT_ID,
        account="DU123456",
        action="BUY",
        orderType="LMT",
        totalQuantity=1,
        lmtPrice=Decimal("4.90"),
        auxPrice=0,
        tif="DAY",
        outsideRth=False,
        transmit=True,
        whatIf=False,
    )
    trade = SimpleNamespace(
        contract=contract,
        order=order,
        orderStatus=SimpleNamespace(status="PreSubmitted", filled=0, remaining=1),
    )
    canonical_contract = canonical_contract_identity(contract)
    leg_hashes = tuple(sha256_json(value) for value in canonical_contract["comboLegs"])
    requirement = SimpleNamespace(
        required_leg_identity_sha256=leg_hashes,
        maximum_evidence_age_seconds=Decimal("30"),
    )
    command = SimpleNamespace(
        order_ref=order.orderRef,
        ibkr_order_id=order.orderId,
        perm_id=order.permId,
        execution_client_id=order.clientId,
        account_identity_sha256=account_hash,
        contract_identity_sha256=sha256_json(canonical_contract),
        proposed_order_sha256="a" * 64,
        liability_requirement=requirement,
        resolved_total_quantity=Decimal("1"),
        resolved_limit_price=Decimal("3.50"),
        new_tif=None,
        new_good_till_date_utc=None,
        sha256="b" * 64,
    )
    option_contracts = {
        550001: SimpleNamespace(
            conId=550001,
            symbol="UTHR",
            secType="OPT",
            currency="USD",
            lastTradeDateOrContractMonth="20261016",
            strike=550,
            right="C",
            multiplier="100",
        ),
        560001: SimpleNamespace(
            conId=560001,
            symbol="UTHR",
            secType="OPT",
            currency="USD",
            lastTradeDateOrContractMonth="20261016",
            strike=560,
            right="C",
            multiplier="100",
        ),
    }
    what_if_orders = []

    class Broker:
        def reqAllOpenOrders(self):
            return [trade]

        def reqContractDetails(self, query):
            return [SimpleNamespace(contract=option_contracts[query.conId])]

        def whatIfOrder(self, exact_contract, proposed_order):
            assert exact_contract is contract
            what_if_orders.append(proposed_order)
            return SimpleNamespace(
                commission="1.00",
                initMarginChange="0",
                maintMarginChange="0",
                warningText="",
            )

    evidence = _collect_continuity_liability_evidence(Broker(), command, {})

    assert evidence.bounded is True
    assert evidence.maximum_loss == Decimal("350.00")
    assert evidence.covered_leg_identity_sha256 == leg_hashes
    assert evidence.account_identity_sha256 == account_hash
    assert evidence.contract_identity_sha256 == command.contract_identity_sha256
    assert evidence.proposed_order_sha256 == command.proposed_order_sha256
    assert evidence.command_sha256 == command.sha256
    assert len(what_if_orders) == 1
    assert what_if_orders[0].whatIf is True
    assert what_if_orders[0].transmit is True
    assert Decimal(str(what_if_orders[0].lmtPrice)) == Decimal("3.50")


def test_validate_only_reports_missing_alert_configuration_without_broker_io(
    tmp_path,
) -> None:
    config = SimpleNamespace(
        repo_root=tmp_path,
        db_path=tmp_path / "runtime.sqlite3",
        launch_attempt_id="validate-only",
        target_successor_epoch_id="AUTONOMY_EPOCH_2",
        initial_allocation=Decimal("500"),
        paper_host="127.0.0.1",
        paper_port=4002,
    )

    result = validate_production_composition(
        config=config,
        preflight=SimpleNamespace(expected_account_hash="a" * 64),
        toolbox=object(),
        production_validation_sha256="b" * 64,
    )

    assert result == {
        "status": "BLOCK",
        "reason_codes": ["EXTERNAL_ALERT_CONFIGURATION_MISSING"],
        "broker_connections": 0,
        "broker_writes": 0,
    }


def test_validate_only_rejects_invalid_validation_authority_hash(tmp_path) -> None:
    smtp = tmp_path / "Secrets" / "email_alerts.env"
    smtp.parent.mkdir(parents=True)
    smtp.write_text("synthetic", encoding="utf-8")
    config = SimpleNamespace(
        repo_root=tmp_path,
        db_path=tmp_path / "runtime.sqlite3",
        launch_attempt_id="validate-only",
        target_successor_epoch_id="AUTONOMY_EPOCH_2",
        initial_allocation=Decimal("500"),
        paper_host="127.0.0.1",
        paper_port=4002,
    )
    with Database.open(config.db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)

    result = validate_production_composition(
        config=config,
        preflight=SimpleNamespace(expected_account_hash="a" * 64),
        toolbox=object(),
        production_validation_sha256="invalid",
    )

    assert result == {
        "status": "BLOCK",
        "reason_codes": ["PRODUCTION_VALIDATION_SHA256_INVALID"],
        "broker_connections": 0,
        "broker_writes": 0,
    }


def test_validate_only_blocks_an_armed_or_uncoordinated_model_executor(
    tmp_path, monkeypatch
) -> None:
    smtp = tmp_path / "Secrets" / "email_alerts.env"
    smtp.parent.mkdir(parents=True)
    smtp.write_text("synthetic", encoding="utf-8")
    config = SimpleNamespace(
        repo_root=tmp_path,
        db_path=tmp_path / "runtime.sqlite3",
        launch_attempt_id="validate-only",
        target_successor_epoch_id="AUTONOMY_EPOCH_2",
        initial_allocation=Decimal("500"),
        paper_host="127.0.0.1",
        paper_port=4002,
    )
    with Database.open(config.db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v4(db)
    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime._current_head",
        lambda _root: "c" * 40,
    )
    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime.create_model_executor",
        lambda **_kwargs: SimpleNamespace(
            armed=True,
            is_coordinated_model_executor=False,
        ),
    )

    result = validate_production_composition(
        config=config,
        preflight=SimpleNamespace(expected_account_hash="a" * 64),
        toolbox=object(),
        production_validation_sha256="b" * 64,
    )

    assert result == {
        "status": "BLOCK",
        "reason_codes": ["PRODUCTION_COMPOSITION_MODEL_EXECUTOR_INVALID"],
        "broker_connections": 0,
        "broker_writes": 0,
    }


def test_validate_only_reports_missing_schema_without_broker_io(tmp_path) -> None:
    smtp = tmp_path / "Secrets" / "email_alerts.env"
    smtp.parent.mkdir(parents=True)
    smtp.write_text("synthetic", encoding="utf-8")
    config = SimpleNamespace(
        repo_root=tmp_path,
        db_path=tmp_path / "runtime.sqlite3",
        launch_attempt_id="validate-only",
        target_successor_epoch_id="AUTONOMY_EPOCH_2",
        initial_allocation=Decimal("500"),
        paper_host="127.0.0.1",
        paper_port=4002,
    )
    with Database.open(config.db_path):
        pass

    result = validate_production_composition(
        config=config,
        preflight=SimpleNamespace(expected_account_hash="a" * 64),
        toolbox=object(),
        production_validation_sha256="b" * 64,
    )

    assert result == {
        "status": "BLOCK",
        "reason_codes": ["CONTINUITY_SCHEMA_V4_INVALID"],
        "broker_connections": 0,
        "broker_writes": 0,
    }


def test_validate_only_shuts_down_partial_startup_and_reports_exact_stage(
    tmp_path, monkeypatch
) -> None:
    smtp = tmp_path / "Secrets" / "email_alerts.env"
    smtp.parent.mkdir(parents=True)
    smtp.write_text("synthetic", encoding="utf-8")
    config = SimpleNamespace(
        repo_root=tmp_path,
        db_path=tmp_path / "runtime.sqlite3",
        launch_attempt_id="validate-only",
        target_successor_epoch_id="AUTONOMY_EPOCH_2",
        initial_allocation=Decimal("500"),
        paper_host="127.0.0.1",
        paper_port=4002,
    )
    with Database.open(config.db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v4(db)
    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime._current_head",
        lambda _root: "c" * 40,
    )
    trace = []

    class Writer:
        execution_client_id = WRITER_CLIENT_ID
        production_authority_validator = SimpleNamespace(
            validate_before_write=lambda: None
        )
        execution_lock_verifier = lambda self: False

        def start(self):
            trace.append("writer_start")

        def wait_until_ready(self, _timeout):
            return True

        def stop(self, _timeout):
            trace.append("writer_stop")
            return True

    class Watchdog:
        def start(self, _timeout):
            trace.append("watchdog_start")
            raise RuntimeError("synthetic watchdog failure")

        def stop(self, _timeout):
            trace.append("watchdog_stop")
            return SimpleNamespace(stopped=True, timed_out=False)

    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime.create_authoritative_writer",
        lambda **_kwargs: Writer(),
    )
    monkeypatch.setattr(
        "ibkr_paper_30d.production_continuity_runtime.create_continuity_watchdog",
        lambda **_kwargs: Watchdog(),
    )

    result = validate_production_composition(
        config=config,
        preflight=SimpleNamespace(expected_account_hash="a" * 64),
        toolbox=object(),
        production_validation_sha256="b" * 64,
    )

    assert result["status"] == "BLOCK"
    assert result["reason_codes"] == [
        "PRODUCTION_COMPOSITION_START_FAILED:RuntimeError"
    ]
    assert result["broker_connections"] == 0
    assert result["broker_writes"] == 0
    assert trace == [
        "writer_start",
        "watchdog_start",
        "watchdog_stop",
        "writer_stop",
    ]


def test_canary_pilot_restarts_certification_generation_after_adapter_drift(
    tmp_path, monkeypatch
) -> None:
    """End-to-end: canary discovery with adapter B after adapter A certification
    must append a generation-restart event and keep the service alive."""
    from ibkr_paper_30d.canary_candidate import CanaryDiscoveryOutcome
    from ibkr_paper_30d.canary_pilot import CanaryPilotOrchestrator
    from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
    from ibkr_paper_30d.product_capability import (
        ProductFamilyCertificationStatus,
        ProductFamilyCertificationStore,
    )
    import test_canary_pilot as tcp
    from test_canary_pilot import _evidence, _owner, _proposal

    now = datetime.now(timezone.utc)
    monkeypatch.setattr(tcp, "NOW", now)

    db_path = tmp_path / "canary-drift-integration.sqlite3"
    with Database.open(db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        install_multi_universe_schema_v4(db)
        proposal = _proposal()
        adapter_a = "a" * 64
        adapter_b = "b" * 64
        account = proposal.account_identity_sha256

        original_store = ProductFamilyCertificationStore(
            db, current_adapter_sha256=adapter_a
        )
        cert_steps = (
            "CONTRACT_QUALIFIED",
            "PERMISSIONS_VERIFIED",
            "MARKET_DATA_VERIFIED",
            "ORDER_SEMANTICS_VERIFIED",
            "BOUNDED_ECONOMICS_VERIFIED",
            "ORDER_TRANSMIT_VERIFIED",
        )
        for step in cert_steps:
            original_store.record_step(
                proposal.product_family,
                step,
                sha256_json({"step": step}),
                account_sha256=account,
                adapter_sha256=adapter_a,
                observed_at_utc=datetime.now(timezone.utc),
                expires_at_utc=datetime.now(timezone.utc) + timedelta(days=1),
                paper_limitations=("PAPER_SIMULATION_ONLY",),
            )
        recorder = CanaryLifecycleRecorder(
            proposal.candidate_id,
            account,
            proposal.product_family.sha256,
            proposal.canonical_contract.sha256,
        )
        for ordinal, step in enumerate(
            ("SUBMITTED", "BROKER_BOUND", "TERMINAL_NO_FILL"), 1
        ):
            recorder.record(
                CanaryBrokerLifecycleReceipt(
                    canary_id=proposal.candidate_id,
                    step=step,
                    endpoint="PAPER",
                    account_identity_sha256=account,
                    product_family_sha256=proposal.product_family.sha256,
                    contract_identity_sha256=proposal.canonical_contract.sha256,
                    broker_event_id_sha256=f"{ordinal:064x}",
                    broker_snapshot_sha256=f"{ordinal + 10:064x}",
                    previous_receipt_sha256=recorder.last_receipt_sha256,
                    observed_at_utc=datetime.now(timezone.utc)
                    + timedelta(seconds=ordinal),
                    open_orders=1 if step == "BROKER_BOUND" else 0,
                    positions=0,
                    economics_reconciled=False,
                )
            )
        original_store.record_canary_lifecycle(
            proposal.product_family,
            recorder.projection(),
            account_sha256=account,
            adapter_sha256=adapter_a,
            observed_at_utc=datetime.now(timezone.utc),
            expires_at_utc=datetime.now(timezone.utc) + timedelta(days=1),
            paper_limitations=("PAPER_SIMULATION_ONLY",),
        )
        assert (
            original_store.projection(proposal.product_family).status
            is ProductFamilyCertificationStatus.ORDER_TRANSMIT_VERIFIED
        )

        product_store = ProductFamilyCertificationStore(
            db, current_adapter_sha256=adapter_b
        )

        class FakeCanaryStore:
            def __init__(self):
                self.candidate = None
                self.discovery_events = []

            def load_candidate(self):
                return self.candidate

            def persist_candidate(self, outcome, evidence, validation):
                self.candidate = (outcome, evidence, validation)

            def persist_discovery_event(self, kind, payload):
                self.discovery_events.append((kind, payload))

            def has_orphaned_durable_state(self):
                return False

            def last_discovery_attempt_utc(self):
                return None

        fake_store = FakeCanaryStore()
        outcome = CanaryDiscoveryOutcome(
            decision="CANDIDATE",
            invocation_sha256=proposal.invocation_sha256,
            result_sha256=proposal.result_sha256,
            transcript_sha256=sha256_json([]),
            proposal=proposal,
        )
        bundle = SimpleNamespace(
            reconciliation_receipt={"status": "PASS"},
            multi_sleeve_portfolio={
                "account_observation": {
                    "open_order_count": 0,
                    "open_orders": [],
                    "positions": [],
                }
            },
            contract_ownership_snapshot={"contract_sleeves": {}},
            continuity_context={"active_plans": []},
        )

        def finalizer(proposal, evidence, validation, *, bundle=None):
            product_store.record_read_only_candidate_evidence(
                proposal.product_family,
                evidence_sha256=validation.capability_evidence_sha256,
                account_sha256=proposal.account_identity_sha256,
                adapter_sha256=adapter_b,
                observed_at_utc=evidence["observed_at_utc"],
                expires_at_utc=evidence["expires_at_utc"],
                paper_limitations=("PAPER_SIMULATION_ONLY",),
                runtime_authorization={
                    "allow_generation_restart": True,
                    "account_sha256": account,
                    "successor_definition_sha256": (
                        proposal.successor_definition_sha256
                    ),
                    "approved_git_head": proposal.approved_head,
                    "transition_phase": "CANARY_EXCLUSIVE",
                    "reconciliation_status": "PASS",
                    "family_open_orders": 0,
                    "family_positions": 0,
                },
            )

        orchestrator = CanaryPilotOrchestrator(
            discovery_runner=lambda _bundle, persister: outcome,
            capability_evidence_collector=lambda _bundle, actual: _evidence(actual),
            store=fake_store,
            coordinator=SimpleNamespace(submit=lambda request: Future()),
            owner_pilot_authorization=_owner(),
            writer_binding_sha256="d" * 64,
            effective_approved_head=proposal.approved_head,
            durable_sequence_allocator=lambda: 1,
            now_utc=lambda: datetime.now(timezone.utc),
            candidate_finalizer=finalizer,
        )

        result = orchestrator.discover(bundle)

        assert result["status"] == "PASS"
        assert result["decision"] == "CANDIDATE_READY"
        projection = product_store.projection(proposal.product_family)
        assert projection.status is ProductFamilyCertificationStatus.RESEARCH_ONLY
        assert projection.adapter_sha256 == adapter_b
        assert (
            db.execute(
                "SELECT COUNT(*) FROM product_family_certification_events "
                "WHERE event_type='CERTIFICATION_RESTARTED_AFTER_ADAPTER_CHANGE'"
            ).fetchone()[0]
            == 1
        )
