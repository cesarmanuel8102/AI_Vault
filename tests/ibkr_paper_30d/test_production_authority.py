from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ibkr_paper_30d.coordinated_model_executor import (
    ModelExecutionOperation,
    ModelExecutionRequest,
)
from ibkr_paper_30d.production_authority import (
    ProductionAuthoritySnapshot,
    ProductionAuthorityValidator,
    ProductionBrokerEvidence,
)
from ibkr_paper_30d.trader_invocation import TraderDecision


NOW = datetime(2026, 10, 2, 14, 0, tzinfo=timezone.utc)


def _request(**updates) -> ModelExecutionRequest:
    values = {
        "request_id": "request-1",
        "durable_sequence": 1,
        "execution_key": "execution-1",
        "source": "MODEL",
        "operation": ModelExecutionOperation.NEW_TRADE,
        "launch_attempt_id": "launch-1",
        "epoch_id": "AUTONOMY_EPOCH_2",
        "approved_head": "a" * 40,
        "account_identity_sha256": "b" * 64,
        "invocation_id": "invocation-1",
        "decision_cycle_id": "cycle-1",
        "accepted_decision": TraderDecision.PROPOSE_TRADE,
        "accepted_result_sha256": "c" * 64,
        "payload": object(),
        "payload_sha256": "d" * 64,
        "input_bundle": object(),
        "input_bundle_sha256": "e" * 64,
        "continuity_plan": None,
        "continuity_plan_sha256": None,
        "created_at_utc": NOW,
    }
    values.update(updates)
    return ModelExecutionRequest.model_construct(**values)


def _snapshot(**updates) -> ProductionAuthoritySnapshot:
    values = {
        "snapshot_id": "authority-1",
        "observed_at_utc": NOW,
        "lock_owned_by_process": True,
        "approved_head": "a" * 40,
        "runtime_provenance_valid": True,
        "environment": "PAPER",
        "account_identity_sha256": "b" * 64,
        "owner_authorization_valid": True,
        "epoch_id": "AUTONOMY_EPOCH_2",
        "clock_active": True,
        "kill_switch_clear": True,
        "auditor_gate_pass": True,
        "market_data_gate_pass": True,
        "continuity_schema_valid": True,
        "authority_chains_valid": True,
        "active_plan_sha256": None,
        "binding_plan_sha256": None,
        "provider_state_allows": True,
        "accepted_result_sha256": "c" * 64,
        "review_allows": True,
        "execution_count": 0,
        "maximum_execution_count": 1,
        "used_execution_keys": (),
        "order_state_sha256": "f" * 64,
        "positions_sha256": "1" * 64,
        "executions_sha256": "2" * 64,
        "experiment_capital_boundary": "500",
        "sqlite_write_transaction_active": False,
    }
    values.update(updates)
    return ProductionAuthoritySnapshot.model_validate(values)


def _broker(**updates) -> ProductionBrokerEvidence:
    values = {
        "evidence_id": "broker-1",
        "collected_at_utc": NOW,
        "broker_time_utc": NOW,
        "fresh_until_utc": NOW + timedelta(seconds=30),
        "account_identity_sha256": "b" * 64,
        "all_order_visibility": True,
        "open_orders_sha256": "3" * 64,
        "positions_sha256": "1" * 64,
        "executions_sha256": "2" * 64,
        "target_order_state_sha256": "f" * 64,
        "evidence_sha256": "4" * 64,
    }
    values.update(updates)
    return ProductionBrokerEvidence.model_validate(values)


@pytest.mark.parametrize(
    ("snapshot_updates", "broker_updates", "request_updates", "reason"),
    [
        ({"lock_owned_by_process": False}, {}, {}, "EXECUTION_LOCK_NOT_OWNED"),
        ({"approved_head": "0" * 40}, {}, {}, "APPROVED_HEAD_MISMATCH"),
        ({"runtime_provenance_valid": False}, {}, {}, "RUNTIME_PROVENANCE_BLOCK"),
        ({"environment": "LIVE"}, {}, {}, "PAPER_ENVIRONMENT_REQUIRED"),
        ({"account_identity_sha256": "0" * 64}, {}, {}, "PAPER_ACCOUNT_MISMATCH"),
        ({"owner_authorization_valid": False}, {}, {}, "OWNER_AUTHORIZATION_BLOCK"),
        ({"epoch_id": "OTHER"}, {}, {}, "EPOCH_BINDING_MISMATCH"),
        ({"clock_active": False}, {}, {}, "EXPERIMENT_CLOCK_BLOCK"),
        ({"kill_switch_clear": False}, {}, {}, "KILL_SWITCH_TRIGGERED"),
        ({"auditor_gate_pass": False}, {}, {}, "AUDITOR_GATE_BLOCK"),
        ({"market_data_gate_pass": False}, {}, {}, "MARKET_DATA_GATE_BLOCK"),
        ({"continuity_schema_valid": False}, {}, {}, "CONTINUITY_SCHEMA_BLOCK"),
        ({"authority_chains_valid": False}, {}, {}, "AUTHORITY_CHAIN_BLOCK"),
        ({"provider_state_allows": False}, {}, {}, "PROVIDER_STATE_BLOCK"),
        ({"accepted_result_sha256": "0" * 64}, {}, {}, "ACCEPTED_DECISION_MISMATCH"),
        ({"review_allows": False}, {}, {}, "CONTINUITY_REVIEW_BLOCK"),
        ({"execution_count": 1}, {}, {}, "MAXIMUM_EXECUTION_COUNT_REACHED"),
        ({"used_execution_keys": ("execution-1",)}, {}, {}, "EXECUTION_KEY_ALREADY_USED"),
        ({"sqlite_write_transaction_active": True}, {}, {}, "SQLITE_WRITE_TRANSACTION_ACTIVE"),
        ({}, {"all_order_visibility": False}, {}, "ALL_ORDER_VISIBILITY_UNCERTAIN"),
        ({}, {"positions_sha256": "0" * 64}, {}, "BROKER_POSITIONS_CHANGED"),
        ({}, {"executions_sha256": "0" * 64}, {}, "BROKER_EXECUTIONS_CHANGED"),
        ({}, {"account_identity_sha256": "0" * 64}, {}, "BROKER_ACCOUNT_MISMATCH"),
    ],
)
def test_every_mutable_authority_gate_fails_closed(
    snapshot_updates, broker_updates, request_updates, reason
) -> None:
    snapshot = _snapshot(**snapshot_updates)
    validator = ProductionAuthorityValidator(snapshot_reader=lambda request: snapshot)

    decision = validator.validate_before_write(
        request=_request(**request_updates),
        broker_evidence=_broker(**broker_updates),
        liability_evidence=None,
        now_utc=NOW,
    )

    assert decision.allowed is False
    assert reason in decision.reason_codes


def test_fresh_complete_authority_passes() -> None:
    validator = ProductionAuthorityValidator(snapshot_reader=lambda request: _snapshot())

    decision = validator.validate_before_write(
        request=_request(), broker_evidence=_broker(), liability_evidence=None,
        now_utc=NOW,
    )

    assert decision.allowed is True
    assert decision.reason_codes == ()


def test_authority_change_between_reads_blocks_even_when_both_snapshots_pass() -> None:
    snapshots = iter(
        [
            _snapshot(snapshot_id="first", experiment_capital_boundary="500"),
            _snapshot(snapshot_id="second", experiment_capital_boundary="499"),
        ]
    )
    validator = ProductionAuthorityValidator(snapshot_reader=lambda request: next(snapshots))
    first = validator.validate_before_write(
        request=_request(), broker_evidence=_broker(), liability_evidence=None,
        now_utc=NOW,
    )
    second = validator.validate_before_write(
        request=_request(), broker_evidence=_broker(), liability_evidence=None,
        now_utc=NOW, prior_authority_snapshot=first.authority_snapshot,
    )

    assert first.allowed is True
    assert second.allowed is False
    assert second.reason_codes == ("AUTHORITY_STATE_CHANGED_DURING_VALIDATION",)


def test_stale_broker_evidence_blocks() -> None:
    validator = ProductionAuthorityValidator(snapshot_reader=lambda request: _snapshot())
    evidence = _broker(
        collected_at_utc=NOW - timedelta(seconds=60),
        fresh_until_utc=NOW - timedelta(seconds=30),
    )

    decision = validator.validate_before_write(
        request=_request(), broker_evidence=evidence, liability_evidence=None,
        now_utc=NOW,
    )

    assert "BROKER_EVIDENCE_STALE" in decision.reason_codes


def test_invalid_capital_boundary_blocks() -> None:
    validator = ProductionAuthorityValidator(
        snapshot_reader=lambda request: _snapshot(experiment_capital_boundary="0")
    )

    decision = validator.validate_before_write(
        request=_request(), broker_evidence=_broker(), liability_evidence=None,
        now_utc=NOW,
    )

    assert decision.allowed is False
    assert "EXPERIMENT_CAPITAL_BOUNDARY_INVALID" in decision.reason_codes
