from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import ibkr_paper_30d.day1_launch as launch_module
from ibkr_paper_30d.autonomous_research import (
    AutonomousTurn,
    AutonomousTurnMode,
    CodexAutonomousCLIProvider,
    ResearchResult,
    ResearchTool,
)
from ibkr_paper_30d.autonomous_service import (
    AutonomousExperimentService,
    AutonomousServiceError,
)
from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.continuity_store import ContinuityStore
from ibkr_paper_30d.day1_launch import (
    Day1LaunchConfig,
    LaunchDependencies,
    LaunchError,
    evaluate_launch_preflight,
    main,
    run_day1_launch,
    validate_launch_controls,
    write_launch_evidence,
)


def _multi_universe_launch_evidence(**updates):
    from ibkr_paper_30d.day1_launch import MultiUniverseLaunchEvidence

    values = {
        "schema_v4_valid": True,
        "transition_phase": "SUCCESSOR_COMMITTED",
        "approved_head": "a" * 40,
        "expected_approved_head": "a" * 40,
        "account_identity_sha256": "b" * 64,
        "expected_account_identity_sha256": "b" * 64,
        "owner_authorization_sha256": "c" * 64,
        "expected_owner_authorization_sha256": "c" * 64,
        "clock_authority_sha256": "d" * 64,
        "expected_clock_authority_sha256": "d" * 64,
        "regular_sleeve_authority_sha256": "e" * 64,
        "expected_regular_sleeve_authority_sha256": "e" * 64,
        "continuous_sleeve_authority_sha256": "f" * 64,
        "expected_continuous_sleeve_authority_sha256": "f" * 64,
        "economic_risk_authorization_sha256": "1" * 64,
        "expected_economic_risk_authorization_sha256": "1" * 64,
        "certified_family_set_sha256": "2" * 64,
        "expected_certified_family_set_sha256": "2" * 64,
        "successor_definition_sha256": "3" * 64,
        "expected_successor_definition_sha256": "3" * 64,
        "retirement_tombstone_sha256": "4" * 64,
        "predecessor_path_active": False,
        "extended_family_available_within_24h": True,
        "extended_family_tradable_now": True,
        "continuity_gap": False,
        "continuity_action_due": False,
        "same_committed_successor": False,
    }
    values.update(updates)
    return MultiUniverseLaunchEvidence(**values)


@pytest.mark.parametrize(
    ("update", "reason"),
    [
        ({"schema_v4_valid": False}, "MULTI_UNIVERSE_SCHEMA_V4_REQUIRED"),
        ({"transition_phase": "PREDECESSOR_RETIRED"}, "SUCCESSOR_TRANSITION_NOT_ELIGIBLE"),
        ({"approved_head": "9" * 40}, "SUCCESSOR_APPROVED_HEAD_MISMATCH"),
        ({"account_identity_sha256": "9" * 64}, "SUCCESSOR_ACCOUNT_MISMATCH"),
        (
            {"owner_authorization_sha256": "9" * 64},
            "SUCCESSOR_OWNER_AUTHORIZATION_MISMATCH",
        ),
        ({"clock_authority_sha256": "9" * 64}, "SUCCESSOR_CLOCK_AUTHORITY_MISMATCH"),
        (
            {"regular_sleeve_authority_sha256": "9" * 64},
            "REGULAR_SLEEVE_AUTHORITY_MISMATCH",
        ),
        (
            {"continuous_sleeve_authority_sha256": "9" * 64},
            "CONTINUOUS_SLEEVE_AUTHORITY_MISMATCH",
        ),
        (
            {"economic_risk_authorization_sha256": "9" * 64},
            "ECONOMIC_RISK_AUTHORIZATION_MISMATCH",
        ),
        ({"certified_family_set_sha256": "9" * 64}, "CERTIFIED_FAMILY_SET_MISMATCH"),
        (
            {"successor_definition_sha256": "9" * 64},
            "SUCCESSOR_DEFINITION_HASH_MISMATCH",
        ),
        ({"retirement_tombstone_sha256": None}, "PREDECESSOR_RETIREMENT_REQUIRED"),
        ({"predecessor_path_active": True}, "PREDECESSOR_PATH_STILL_ACTIVE"),
        ({"continuity_gap": True}, "SUCCESSOR_CONTINUITY_GAP"),
    ],
)
def test_initial_multi_universe_activation_blocks_before_writer(update, reason) -> None:
    from ibkr_paper_30d.day1_launch import evaluate_multi_universe_successor_launch

    with pytest.raises(LaunchError, match=reason):
        evaluate_multi_universe_successor_launch(
            _multi_universe_launch_evidence(**update), initial_activation=True
        )


def test_successor_restart_skips_24h_predicate_and_enters_idle() -> None:
    from ibkr_paper_30d.day1_launch import evaluate_multi_universe_successor_launch

    result = evaluate_multi_universe_successor_launch(
        _multi_universe_launch_evidence(
            transition_phase="ACTIVE",
            same_committed_successor=True,
            extended_family_available_within_24h=False,
            extended_family_tradable_now=False,
        ),
        initial_activation=False,
    )

    assert result["status"] == "MARKET_CLOSED_IDLE"
    assert result["writer_start_allowed"] is True
    assert result["new_continuous_entries_allowed"] is False
    assert result["reconciliation_required"] is True


def test_successor_restart_prioritizes_due_continuity_when_market_closed() -> None:
    from ibkr_paper_30d.day1_launch import evaluate_multi_universe_successor_launch

    result = evaluate_multi_universe_successor_launch(
        _multi_universe_launch_evidence(
            transition_phase="SUCCESSOR_COMMITTED",
            same_committed_successor=True,
            extended_family_available_within_24h=False,
            extended_family_tradable_now=False,
            continuity_action_due=True,
        ),
        initial_activation=False,
    )

    assert result["status"] == "CONTINUITY_ACTION_DUE"
    assert result["continuity_actions_allowed"] is True
    assert result["new_continuous_entries_allowed"] is False


def test_initial_successor_supervision_does_not_require_available_family() -> None:
    from ibkr_paper_30d.day1_launch import evaluate_multi_universe_successor_launch

    result = evaluate_multi_universe_successor_launch(
        _multi_universe_launch_evidence(
            transition_phase="SUPERVISION_BOUND",
            extended_family_available_within_24h=False,
            extended_family_tradable_now=False,
        ),
        initial_activation=True,
    )

    assert result["status"] == "SUPERVISION_ONLY"
    assert result["writer_start_allowed"] is True
    assert result["management_actions_allowed"] is True
    assert result["new_regular_entries_allowed"] is False
    assert result["new_continuous_entries_allowed"] is False


def test_schema_mode_accepts_v4_only_for_explicit_successor(tmp_path) -> None:
    from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
    from ibkr_paper_30d.persistence import Database
    from ibkr_paper_30d.successor_schema import install_successor_schema_v2

    path = tmp_path / "schema-mode.sqlite3"
    with Database.open(path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        install_multi_universe_schema_v4(db)
        launch_module._validate_launch_database_mode(db, successor_mode=True)
        with pytest.raises(LaunchError, match="DATABASE_SCHEMA_INVALID"):
            launch_module._validate_launch_database_mode(db, successor_mode=False)


def test_legacy_launcher_rejects_committed_successor_before_schema_gate(tmp_path) -> None:
    from ibkr_paper_30d.multi_universe_models import TransitionPhase, TransitionTarget
    from ibkr_paper_30d.multi_universe_schema import install_multi_universe_schema_v4
    from ibkr_paper_30d.multi_universe_transition import MultiUniverseTransitionCoordinator
    from ibkr_paper_30d.persistence import Database
    from ibkr_paper_30d.successor_schema import install_successor_schema_v2

    target = TransitionTarget(
        transition_id="transition-launch-guard",
        predecessor_epoch_id="AUTONOMY_EPOCH_2",
        successor_epoch_id="AUTONOMY_EPOCH_3",
        successor_definition_sha256="1" * 64,
        owner_authorization_sha256="2" * 64,
        approved_git_head="3" * 40,
        account_identity_sha256="4" * 64,
        clock_authority_sha256="5" * 64,
        regular_sleeve_authority_sha256="6" * 64,
        extended_sleeve_authority_sha256="7" * 64,
        economic_risk_authorization_sha256="8" * 64,
        certified_family_set_sha256="9" * 64,
        canary_authorization_sha256="a" * 64,
        writer_binding_sha256="b" * 64,
    )
    path = tmp_path / "retired.sqlite3"
    with Database.open(path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        install_multi_universe_schema_v4(db)
        coordinator = MultiUniverseTransitionCoordinator(db)
        coordinator.prepare(target)
        for phase in (
            TransitionPhase.PREDECESSOR_QUIESCED,
            TransitionPhase.PREDECESSOR_RETIRED,
            TransitionPhase.SUCCESSOR_COMMITTED,
        ):
            evidence = {
                "phase_evidence_sha256": phase.value.encode().hex().ljust(64, "0")[:64],
                "canary_flat": True,
                "continuity_exact": True,
            }
            if phase is TransitionPhase.CANARY_PASS:
                evidence["canary_status"] = "PASS"
            if phase is TransitionPhase.PREDECESSOR_RETIRED:
                evidence.update(
                    retirement_status="PASS",
                    retirement_tombstone_sha256="c" * 64,
                )
            if phase is TransitionPhase.SUCCESSOR_COMMITTED:
                evidence["successor_commit_sha256"] = "d" * 64
            coordinator.advance(phase, evidence)

        with pytest.raises(LaunchError, match="PREDECESSOR_RETIRED"):
            launch_module._validate_launch_database_mode(db, successor_mode=False)


def test_launch_authority_file_cannot_self_attest_runtime_decision(tmp_path) -> None:
    authority = tmp_path / "authority.json"
    authority.write_text(
        json.dumps(
            {
                "schema": "MULTI_UNIVERSE_LAUNCH_AUTHORITY_V1",
                "successor_epoch_id": "AUTONOMY_EPOCH_3",
                "successor_definition_sha256": "1" * 64,
                "initial_activation": False,
                "owner_authorization_receipt_sha256": "2" * 64,
                "evidence": asdict(_multi_universe_launch_evidence(
                    transition_phase="ACTIVE",
                    predecessor_path_active=False,
                    same_committed_successor=True,
                )),
            }
        ),
        encoding="utf-8",
    )
    config = SimpleNamespace(
        multi_universe_authority_path=authority,
        target_successor_epoch_id="AUTONOMY_EPOCH_3",
        target_successor_definition_sha256="1" * 64,
    )

    envelope = launch_module._load_multi_universe_launch_authority(config)

    assert "status" not in envelope
    assert "evidence" not in envelope
    assert envelope["owner_authorization_receipt_sha256"] == "2" * 64


from ibkr_paper_30d.execution_lock import ExecutionLock, LockIntegrityError, LockOwner
from ibkr_paper_30d.experiment_control import (
    ExperimentClockStore,
    KillSwitchStore,
    OwnerAuthorizationStore,
)
from ibkr_paper_30d.experiment_ledger import AutonomousExperimentLedger
from ibkr_paper_30d.experiment_epoch import ExperimentEpochStore
from ibkr_paper_30d.market_data import DecisionClass
from ibkr_paper_30d.market_observation_collector import (
    MARKET_OBSERVATION_COLLECTOR_VERSION,
)
from ibkr_paper_30d.open_order_management import append_order_registry_event
from ibkr_paper_30d.owner_authorization import (
    OWNER_PHRASE,
    create_owner_authorization,
)
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.repositories import EventRepository
from ibkr_paper_30d.prerequisite_tools import bind_launch_attempt
from ibkr_paper_30d.successor_epoch import (
    BrokerTransitionEvidence,
    SuccessorEpochStore,
)
from ibkr_paper_30d.successor_clock import BrokerTimeObservation
from ibkr_paper_30d.successor_schema import install_successor_schema_v2
from ibkr_paper_30d.trader_invocation import TraderDecision
from successor_test_support import (
    SUCCESSOR_START,
    build_authorized_successor,
)

OWNER_SID = "S-1-5-21-test-owner"
ACCOUNT_HASH = "a" * 64
ATTEMPT_ID = "11111111-1111-4111-8111-111111111111"
NOW = datetime(2026, 9, 23, 20, 0, tzinfo=timezone.utc)


def _registry_state_payload(plan_id: str, continuity_state: str, sequence: int):
    return {
        "schema": "EXPERIMENT_ORDER_REGISTRY_V3",
        "lifecycle_event": (
            "ISSUED_PRE_SEND"
            if continuity_state == "CONTINUITY_BIND_PENDING"
            else "CONTINUITY_BIND_TERMINAL"
        ),
        "continuity_state": continuity_state,
        "plan_id": plan_id,
        "order_ref": f"order-{plan_id}",
        "client_order_id": sequence,
        "perm_id": 0,
        "ibkr_order_id": sequence,
        "contract_id": 1,
        "action": "BUY",
        "quantity": "1",
        "created_at_utc": f"2026-10-06T20:00:{sequence:02d}Z",
    }


def test_pending_recovery_uses_latest_registry_state_per_plan(tmp_path) -> None:
    with Database.open(tmp_path / "latest-state.sqlite3") as db:
        append_order_registry_event(
            db, _registry_state_payload("closed-plan", "CONTINUITY_BIND_PENDING", 1)
        )
        append_order_registry_event(
            db, _registry_state_payload("closed-plan", "BIND_TERMINAL", 2)
        )
        result = launch_module._default_pending_binding_recovery(db, None, None)

    assert result == {
        "status": "PASS",
        "reason_codes": [],
        "pending_plan_ids": [],
    }


def test_pending_recovery_rejects_corrupt_latest_registry_state(tmp_path) -> None:
    with Database.open(tmp_path / "corrupt-latest-state.sqlite3") as db:
        append_order_registry_event(
            db, _registry_state_payload("hidden-plan", "CONTINUITY_BIND_PENDING", 1)
        )
        terminal = _registry_state_payload("hidden-plan", "BIND_TERMINAL", 2)
        db.execute(
            "INSERT INTO experiment_order_registry("
            "registry_id,order_ref,client_order_id,perm_id,ibkr_order_id,"
            "contract_id,action,quantity,payload_json,payload_sha256,created_at_utc"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                "corrupt-terminal-registry-id",
                terminal["order_ref"],
                terminal["client_order_id"],
                terminal["perm_id"],
                terminal["ibkr_order_id"],
                terminal["contract_id"],
                terminal["action"],
                terminal["quantity"],
                canonical_bytes(terminal).decode("utf-8"),
                "0" * 64,
                terminal["created_at_utc"],
            ),
        )
        result = launch_module._default_pending_binding_recovery(db, None, None)

    assert result == {
        "status": "BLOCK",
        "reason_codes": ["PENDING_BINDING_REGISTRY_CORRUPT"],
        "pending_plan_ids": [],
    }


def test_default_provider_recovery_abandons_replaced_owner_invocation(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "provider-recovery.sqlite3"
    old_invocation_id = "autonomous-abandoned-owner"
    old_payload = {
        "decision_cycle_id": "cycle-abandoned-owner",
        "launch_attempt_id": "old-launch-attempt",
        "pid": 999999,
        "boot_session_identity": "old-boot",
        "broker_time_utc": "2026-09-23T19:50:00+00:00",
        "declared_deadline_broker_utc": "2026-09-23T19:55:00+00:00",
        "broker_time_evidence_sha256": "b" * 64,
        "broker_time_observed_at_utc": "2026-09-23T19:50:00+00:00",
        "broker_time_authenticated": True,
        "account_identity_sha256": ACCOUNT_HASH,
    }
    owner = LockOwner(
        owner_id="replacement-owner",
        pid=os.getpid(),
        process_start="2026-09-23T19:59:00Z",
        host_fingerprint="same-host",
        boot_session_id="new-boot",
    )
    broker_evidence = BrokerTransitionEvidence(
        account_identity_sha256=ACCOUNT_HASH,
        collected_at_utc=NOW,
        observation=BrokerTimeObservation(
            server_time_utc=NOW,
            observed_at_utc=NOW,
            authenticated=True,
            paper_session=True,
        ),
        positions_count=0,
        open_orders_count=0,
        broker_write_count=0,
    )

    with Database.open(db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
        store = ContinuityStore(db)
        store.append_provider_event(
            old_invocation_id,
            "IN_FLIGHT",
            old_payload,
            event_id=f"provider:{old_invocation_id}:in-flight",
        )

        result = launch_module._default_provider_recovery(
            db,
            owner,
            SimpleNamespace(launch_attempt_id="replacement-launch-attempt"),
            SimpleNamespace(expected_account_hash=ACCOUNT_HASH),
            broker_evidence_collector=lambda *_: broker_evidence,
        )
        projection = store.provider_projection(old_invocation_id)

    assert result == {
        "status": "PASS",
        "reason_codes": [],
        "unresolved_invocation_ids": [],
        "recovered_invocation_ids": [old_invocation_id],
    }
    assert projection["state"] == "ABANDONED"
    assert projection["payload"]["failure_code"] == "EXECUTION_LOCK_OWNER_REPLACED"


class ExecutorTripwire:
    armed = True
    is_coordinated_model_executor = True

    def __init__(self) -> None:
        self.calls: list[str] = []

    def _fail(self, name: str):
        self.calls.append(name)
        raise AssertionError(f"broker write authority reached: {name}")

    def execute(self, *args, **kwargs):
        return self._fail("execute")

    def execute_open_order_action(self, *args, **kwargs):
        return self._fail("execute_open_order_action")

    def execute_position_action(self, *args, **kwargs):
        return self._fail("execute_position_action")


class IBWriteTripwire:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def _fail(self, name: str):
        self.calls.append(name)
        raise AssertionError(f"IB write reached: {name}")

    def placeOrder(self, *args, **kwargs):
        return self._fail("placeOrder")

    def cancelOrder(self, *args, **kwargs):
        return self._fail("cancelOrder")

    def reqGlobalCancel(self, *args, **kwargs):
        return self._fail("reqGlobalCancel")


@dataclass
class LaunchTestContext:
    config: Day1LaunchConfig
    dependencies: LaunchDependencies
    identity_payload: dict[str, object]
    auditor_gate: Mock
    market_gate: Mock
    service_factory: Mock
    executor_tripwire: ExecutorTripwire
    ib_tripwire: IBWriteTripwire


def _distribution() -> dict[str, object]:
    return {
        "count": 540,
        "minimum_ms": 10,
        "median_ms": 25,
        "p95_ms": 50,
        "p99_ms": 75,
        "maximum_ms": 100,
        "iqr_ms": 20,
        "missing_rate": 0.0,
        "rejection_rate": 0.0,
    }


def _write_verified_market_policy(path: Path) -> None:
    stats = {
        "accepted_count": 540,
        "rejected_count": 0,
        "per_symbol_accepted_count": {"IEF": 180, "QQQ": 180, "SPY": 180},
        "quote_age": _distribution(),
        "receipt_latency": _distribution(),
        "absolute_clock_skew": _distribution(),
        "by_symbol": {
            symbol: {
                "quote_age": _distribution(),
                "receipt_latency": _distribution(),
                "absolute_clock_skew": _distribution(),
            }
            for symbol in ("IEF", "QQQ", "SPY")
        },
    }
    unsigned = {
        "schema": "MARKET_DATA_POLICY_V1",
        "policy_version": "MARKET_DATA_POLICY_V1",
        "predecessor_sha256": None,
        "created_at_utc": "2026-09-23T19:00:00Z",
        "evidence": {"collector_version": MARKET_OBSERVATION_COLLECTOR_VERSION},
        "statistics": stats,
        "controls": {
            "version": "MARKET_DATA_POLICY_V1",
            "max_new_trade_age_ms": 2000,
            "max_position_management_age_ms": 5000,
            "max_clock_skew_ms": 250,
            "require_realtime_for_new_trade": True,
            "require_bid_ask_for_spread": True,
        },
        "rationale": {
            "p99_quote_age_ms": 75,
            "quote_age_iqr_ms": 20,
            "age_margin_ms": 250,
            "p99_absolute_clock_skew_ms": 75,
            "clock_skew_iqr_ms": 20,
            "skew_margin_ms": 100,
        },
    }
    path.write_bytes(
        canonical_bytes(
            {
                **unsigned,
                "policy_sha256": hashlib.sha256(canonical_bytes(unsigned)).hexdigest(),
            }
        )
    )


def _bind(ctx: LaunchTestContext) -> None:
    bind_launch_attempt(
        ctx.config.launch_attempt_id,
        ctx.config.identity_receipt_path,
        ctx.config.auditor_receipt_path,
        ctx.config.launch_attempt_binding_path,
    )


def _write_model_attestation_exception(config: Day1LaunchConfig) -> None:
    owner_receipt_sha256 = hashlib.sha256(
        config.owner_authorization_path.read_bytes()
    ).hexdigest()
    unsigned = {
        "schema": "MODEL_ATTESTATION_OWNER_EXCEPTION_V1",
        "authorization_state": "AUTHORIZED",
        "scope": "MONTH1_PAPER_ONLY",
        "requested_model": "gpt-5.6-sol",
        "reasoning_effort": "max",
        "actual_model_attestation_available": False,
        "requested_model_pin_required": True,
        "model_mismatch_forbidden": True,
        "paper_only": True,
        "live_allowed": False,
        "paper_host": "127.0.0.1",
        "paper_port": 4002,
        "expected_account_identity_hash": ACCOUNT_HASH,
        "owner_authorization_receipt_sha256": owner_receipt_sha256,
        "start_utc": "2026-09-23T13:30:00Z",
        "end_utc": "2026-10-23T13:30:00Z",
    }
    config.model_attestation_exception_path.write_bytes(
        canonical_bytes({**unsigned, "artifact_sha256": sha256_json(unsigned)})
    )


def _write_successor_model_attestation_exception(
    config: Day1LaunchConfig,
) -> None:
    unsigned = {
        "schema": "MODEL_ATTESTATION_OWNER_EXCEPTION_V2",
        "authorization_state": "AUTHORIZED",
        "scope": "MONTH1_PAPER_ONLY",
        "requested_model": config.model,
        "reasoning_effort": config.reasoning_effort,
        "actual_model_attestation_available": False,
        "requested_model_pin_required": True,
        "model_mismatch_forbidden": True,
        "paper_only": True,
        "live_allowed": False,
        "paper_host": config.paper_host,
        "paper_port": config.paper_port,
        "expected_account_identity_hash": ACCOUNT_HASH,
        "owner_authorization_receipt_sha256": hashlib.sha256(
            config.owner_authorization_path.read_bytes()
        ).hexdigest(),
        "target_successor_epoch_id": config.target_successor_epoch_id,
        "target_successor_definition_sha256": (
            config.target_successor_definition_sha256
        ),
        "clock_start_policy": "BROKER_SERVER_TIME_AT_AUTHORIZED_LAUNCH",
    }
    config.model_attestation_exception_path.write_bytes(
        canonical_bytes({**unsigned, "artifact_sha256": sha256_json(unsigned)})
    )


def write_identity_receipt(
    ctx: LaunchTestContext, *, rebind: bool = True, **updates: object
) -> None:
    ctx.identity_payload.update(updates)
    ctx.config.identity_receipt_path.write_bytes(canonical_bytes(ctx.identity_payload))
    if rebind:
        _bind(ctx)


def passing_context(tmp_path: Path) -> LaunchTestContext:
    reports = tmp_path / "state" / "ibkr_paper_30d" / "reports"
    reports.mkdir(parents=True)
    config = Day1LaunchConfig(
        repo_root=tmp_path,
        db_path=tmp_path / "state" / "ibkr_paper_30d" / "autonomous.sqlite3",
        launch_root=tmp_path / "state" / "ibkr_paper_30d" / "launch",
        expected_identity_path=tmp_path
        / "Secrets"
        / "expected_paper_account_identity_v1.json",
        identity_receipt_path=reports / "read_only_real_paper_reconciliation.json",
        auditor_receipt_path=reports / "auditor_gate_v2_receipt.json",
        market_policy_path=reports / "market_data_policy_v1.json",
        market_validation_path=reports / "market_data_validation.json",
        owner_authorization_path=reports / "owner_authorization_v1.json",
        model_attestation_exception_path=(
            reports / "model_attestation_owner_exception_v1.json"
        ),
        launch_attempt_binding_path=reports / "launch_attempt_binding_v1.json",
        launch_attempt_id=ATTEMPT_ID,
        approved_head="b" * 40,
    )
    config.expected_identity_path.parent.mkdir(parents=True)
    config.expected_identity_path.write_bytes(
        canonical_bytes(
            {
                "schema": "EXPECTED_PAPER_ACCOUNT_IDENTITY_V1",
                "account_sha256": ACCOUNT_HASH,
                "gateway_mode": "PAPER",
                "host": "127.0.0.1",
                "port": 4002,
                "managed_account_count": 1,
            }
        )
    )
    identity_payload: dict[str, object] = {
        "schema": "REAL_IBKR_READ_ONLY_RECONCILIATION_V1",
        "status": "PASS",
        "gateway_mode": "PAPER",
        "host": "127.0.0.1",
        "port": 4002,
        "paper_account_identity_gate": "PASS",
        "real_ibkr_read_only_identity_gate": "PASS",
        "broker_reconciliation_gate": "PASS",
        "expected_account_identity_bound": True,
        "expected_account_identity_hash": ACCOUNT_HASH,
        "heartbeat_ok": True,
        "raw_account_identity_persisted": False,
        "real_order_writes_attempted": 0,
        "managed_account_count": 1,
        "paper_account_namespace_ok": True,
        "query_completeness": {
            "account_summary": True,
            "account_values": True,
            "current_time": True,
            "executions": True,
            "managed_accounts": True,
            "open_orders": True,
            "positions": True,
        },
    }
    config.identity_receipt_path.write_bytes(canonical_bytes(identity_payload))
    config.auditor_receipt_path.write_bytes(canonical_bytes({"gate": "PASS"}))
    _write_verified_market_policy(config.market_policy_path)
    config.market_validation_path.write_bytes(
        canonical_bytes(
            {
                "schema": "REAL_MARKET_DATA_VALIDATION_V1",
                "status": "PASS",
                "market_data_gate": "PASS",
                "market_data_policy_frozen": True,
                "broker_calls_made": 25,
                "real_order_writes_attempted": 0,
                "reason_codes": [],
            }
        )
    )
    create_owner_authorization(
        db_path=config.db_path,
        phrase=OWNER_PHRASE,
        actor_sid=OWNER_SID,
        elevated=True,
        receipt_path=config.owner_authorization_path,
    )
    with Database.open(config.db_path) as db:
        install_successor_schema_v2(db)
        install_continuity_schema_v3(db)
    _write_model_attestation_exception(config)
    bind_launch_attempt(
        config.launch_attempt_id,
        config.identity_receipt_path,
        config.auditor_receipt_path,
        config.launch_attempt_binding_path,
    )
    auditor_gate = Mock()
    auditor_gate.evaluate.return_value = {
        "gate_status": "PASS",
        "reason_codes": [],
        "receipt_sha256": hashlib.sha256(
            config.auditor_receipt_path.read_bytes()
        ).hexdigest(),
    }
    market_gate = Mock()
    market_gate.evaluate.return_value = {
        "gate_status": "PASS",
        "reason_codes": [],
        "policy_version": "MARKET_DATA_POLICY_V1",
    }
    service_factory = Mock()
    dependencies = LaunchDependencies(
        now_utc=lambda: NOW,
        auditor_gate_factory=lambda _: auditor_gate,
        market_gate_factory=lambda _config, _hash: market_gate,
        database_factory=Database.open,
        lock_factory=Mock(),
        service_factory=service_factory,
        lock_owner_factory=Mock(),
        current_sid=lambda: OWNER_SID,
        runtime_provenance_validator=lambda _config: {
            "gate_status": "PASS",
            "reason_codes": [],
            "material_sha256": "a" * 64,
        },
    )
    writer = Mock()
    writer.wait_until_ready.return_value = True
    dependencies.continuity_schema_verifier = lambda db: {"status": "PASS"}
    dependencies.provider_abandonment_recoverer = lambda db, owner, config, preflight: {
        "status": "PASS",
        "recovered": [],
    }
    dependencies.pending_binding_reconciler = lambda db, config, preflight: {
        "status": "PASS",
        "reconciled": [],
    }
    dependencies.continuity_uncertainty_reader = lambda db: ()
    dependencies.broker_write_coordinator_factory = Mock(return_value=object())
    dependencies.model_executor_factory = Mock(return_value=object())
    dependencies.critical_alert_reporter_factory = Mock(return_value=Mock())
    dependencies.authoritative_writer_factory = Mock(return_value=writer)
    dependencies.continuity_watchdog_factory = Mock(return_value=Mock())
    dependencies.continuity_store_factory = ContinuityStore
    return LaunchTestContext(
        config=config,
        dependencies=dependencies,
        identity_payload=identity_payload,
        auditor_gate=auditor_gate,
        market_gate=market_gate,
        service_factory=service_factory,
        executor_tripwire=ExecutorTripwire(),
        ib_tripwire=IBWriteTripwire(),
    )


def assert_no_write_authority(ctx: LaunchTestContext) -> None:
    assert ctx.service_factory.mock_calls == []
    assert ctx.executor_tripwire.calls == []
    assert ctx.ib_tripwire.calls == []


def test_passing_preflight_returns_only_sanitized_bindings(tmp_path: Path) -> None:
    ctx = passing_context(tmp_path)

    result = evaluate_launch_preflight(ctx.config, ctx.dependencies)

    assert result.launch_attempt_id == ATTEMPT_ID
    assert result.expected_account_hash == ACCOUNT_HASH
    assert result.authorization_event_id
    assert result.actual_start_utc == NOW
    assert len(result.identity_receipt_sha256) == 64
    assert len(result.auditor_receipt_sha256) == 64
    assert len(result.market_policy_sha256) == 64
    assert len(result.market_validation_sha256) == 64
    assert len(result.model_attestation_exception_sha256) == 64
    ctx.market_gate.evaluate.assert_called_once_with(DecisionClass.NEW_TRADE)
    assert_no_write_authority(ctx)


def test_model_attestation_exception_wrong_model_blocks_before_write(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    payload = json.loads(ctx.config.model_attestation_exception_path.read_bytes())
    payload["requested_model"] = "gpt-5.5"
    unsigned = {k: v for k, v in payload.items() if k != "artifact_sha256"}
    payload["artifact_sha256"] = sha256_json(unsigned)
    ctx.config.model_attestation_exception_path.write_bytes(canonical_bytes(payload))

    with pytest.raises(LaunchError, match="MODEL_ATTESTATION_EXCEPTION_INVALID"):
        evaluate_launch_preflight(ctx.config, ctx.dependencies)

    assert_no_write_authority(ctx)


def test_passing_preflight_accepts_real_read_only_market_validation(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    payload = json.loads(ctx.config.market_validation_path.read_bytes())
    payload["broker_calls_made"] = 25
    ctx.config.market_validation_path.write_bytes(canonical_bytes(payload))

    result = evaluate_launch_preflight(ctx.config, ctx.dependencies)

    assert (
        result.market_validation_sha256
        == hashlib.sha256(ctx.config.market_validation_path.read_bytes()).hexdigest()
    )
    assert_no_write_authority(ctx)


def test_preflight_accepts_only_account_summary_partial_when_core_reconciliation_passes(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    write_identity_receipt(
        ctx,
        status="PARTIAL",
        reason_codes=["ACCOUNT_SUMMARY_FIELDS_INCOMPLETE"],
        broker_reconciliation_gate="BLOCK",
        account_summary_consistent=True,
        account_summary_complete=False,
        gateway_config_consistent=True,
        outbound_allowlist_only=True,
    )

    result = evaluate_launch_preflight(ctx.config, ctx.dependencies)

    assert result.expected_account_hash == ACCOUNT_HASH
    assert_no_write_authority(ctx)


@pytest.mark.parametrize(
    ("updates", "code"),
    [
        ({"port": 4001}, "LIVE_ROUTE_FORBIDDEN"),
        ({"host": "localhost"}, "PAPER_ROUTE_REQUIRED"),
        ({"gateway_mode": "LIVE"}, "LIVE_ROUTE_FORBIDDEN"),
        ({"managed_account_count": 2}, "MANAGED_ACCOUNT_COUNT_INVALID"),
        ({"paper_account_namespace_ok": False}, "PAPER_ACCOUNT_NAMESPACE_INVALID"),
        ({"heartbeat_ok": False}, "BROKER_HEARTBEAT_REQUIRED"),
        ({"broker_reconciliation_gate": "BLOCK"}, "BROKER_RECONCILIATION_REQUIRED"),
        ({"paper_account_identity_gate": "BLOCK"}, "PAPER_IDENTITY_REQUIRED"),
        (
            {"expected_account_identity_bound": False},
            "EXPECTED_ACCOUNT_IDENTITY_REQUIRED",
        ),
        (
            {"expected_account_identity_hash": "b" * 64},
            "EXPECTED_ACCOUNT_IDENTITY_MISMATCH",
        ),
        ({"raw_account_identity_persisted": True}, "RAW_ACCOUNT_IDENTITY_FORBIDDEN"),
        ({"real_order_writes_attempted": 1}, "BROKER_WRITE_DETECTED"),
        (
            {
                "query_completeness": {
                    "positions": False,
                    "executions": True,
                    "open_orders": True,
                }
            },
            "READONLY_QUERY_INCOMPLETE",
        ),
    ],
)
def test_readonly_identity_failures_block_before_write(
    tmp_path: Path, updates: dict[str, object], code: str
) -> None:
    ctx = passing_context(tmp_path)
    write_identity_receipt(ctx, **updates)

    with pytest.raises(LaunchError, match=code):
        evaluate_launch_preflight(ctx.config, ctx.dependencies)

    assert_no_write_authority(ctx)


def test_preflight_rejects_time_before_immutable_start(tmp_path: Path) -> None:
    ctx = passing_context(tmp_path)
    ctx.dependencies.now_utc = lambda: datetime(
        2026, 9, 23, 13, 29, tzinfo=timezone.utc
    )

    with pytest.raises(LaunchError, match="EXPERIMENT_NOT_STARTED"):
        evaluate_launch_preflight(ctx.config, ctx.dependencies)

    assert_no_write_authority(ctx)


def test_missing_external_owner_authorization_is_never_created(tmp_path: Path) -> None:
    ctx = passing_context(tmp_path)
    ctx.config.owner_authorization_path.unlink()

    with pytest.raises(LaunchError, match="OWNER_AUTHORIZATION_RECEIPT_MISSING"):
        evaluate_launch_preflight(ctx.config, ctx.dependencies)

    assert not ctx.config.owner_authorization_path.exists()
    assert_no_write_authority(ctx)


def test_owner_sid_mismatch_blocks(tmp_path: Path) -> None:
    ctx = passing_context(tmp_path)
    ctx.dependencies.current_sid = lambda: "S-1-5-21-other-owner"

    with pytest.raises(LaunchError, match="OWNER_AUTHORIZATION_OWNER_MISMATCH"):
        evaluate_launch_preflight(ctx.config, ctx.dependencies)

    assert_no_write_authority(ctx)


def test_launch_attempt_id_mismatch_blocks(tmp_path: Path) -> None:
    ctx = passing_context(tmp_path)
    payload = json.loads(ctx.config.launch_attempt_binding_path.read_bytes())
    payload["launch_attempt_id"] = "22222222-2222-4222-8222-222222222222"
    ctx.config.launch_attempt_binding_path.write_bytes(canonical_bytes(payload))

    with pytest.raises(LaunchError, match="LAUNCH_ATTEMPT_ID_MISMATCH"):
        evaluate_launch_preflight(ctx.config, ctx.dependencies)

    assert_no_write_authority(ctx)


def test_receipt_mutation_after_attempt_binding_blocks(tmp_path: Path) -> None:
    ctx = passing_context(tmp_path)
    write_identity_receipt(
        ctx, rebind=False, server_timestamp_utc="2026-09-23T20:00:01Z"
    )

    with pytest.raises(LaunchError, match="LAUNCH_ATTEMPT_RECEIPT_HASH_MISMATCH"):
        evaluate_launch_preflight(ctx.config, ctx.dependencies)

    assert_no_write_authority(ctx)


def test_identity_receipt_changed_during_auditor_evaluation_blocks(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)

    def mutate_then_pass():
        write_identity_receipt(
            ctx, rebind=False, server_timestamp_utc="2026-09-23T20:00:01Z"
        )
        return {"gate_status": "PASS", "reason_codes": []}

    ctx.auditor_gate.evaluate.side_effect = mutate_then_pass

    with pytest.raises(LaunchError, match="IDENTITY_RECEIPT_CHANGED_DURING_PREFLIGHT"):
        evaluate_launch_preflight(ctx.config, ctx.dependencies)

    assert_no_write_authority(ctx)


def test_runtime_auditor_block_is_fail_closed(tmp_path: Path) -> None:
    ctx = passing_context(tmp_path)
    ctx.auditor_gate.evaluate.return_value = {
        "gate_status": "BLOCK",
        "reason_codes": ["AUDITOR_DENIED"],
    }

    with pytest.raises(LaunchError, match="AUDITOR_GATE_BLOCKED"):
        evaluate_launch_preflight(ctx.config, ctx.dependencies)

    assert_no_write_authority(ctx)


def test_runtime_market_block_is_fail_closed(tmp_path: Path) -> None:
    ctx = passing_context(tmp_path)
    ctx.market_gate.evaluate.return_value = {
        "gate_status": "BLOCK",
        "reason_codes": ["DELAYED_DATA"],
        "error": "ObservationAborted:INITIAL_REALTIME_QUOTE_TIMEOUT",
    }

    with pytest.raises(LaunchError, match="MARKET_DATA_GATE_BLOCKED") as caught:
        evaluate_launch_preflight(ctx.config, ctx.dependencies)

    assert caught.value.details == {
        "market_data_reason_codes": ["DELAYED_DATA"],
        "market_data_error_code": "ObservationAborted:INITIAL_REALTIME_QUOTE_TIMEOUT",
    }
    assert_no_write_authority(ctx)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "BLOCK"),
        ("market_data_gate", "BLOCK"),
        ("market_data_policy_frozen", False),
        ("broker_calls_made", 0),
        ("broker_calls_made", -1),
        ("broker_calls_made", True),
        ("broker_calls_made", "25"),
        ("real_order_writes_attempted", 1),
    ],
)
def test_persisted_market_validation_must_be_strict_pass(
    tmp_path: Path, field: str, value: object
) -> None:
    ctx = passing_context(tmp_path)
    payload = json.loads(ctx.config.market_validation_path.read_bytes())
    payload[field] = value
    ctx.config.market_validation_path.write_bytes(canonical_bytes(payload))

    with pytest.raises(LaunchError, match="MARKET_VALIDATION_INVALID"):
        evaluate_launch_preflight(ctx.config, ctx.dependencies)

    assert_no_write_authority(ctx)


def test_invalid_frozen_market_policy_blocks(tmp_path: Path) -> None:
    ctx = passing_context(tmp_path)
    ctx.config.market_policy_path.write_bytes(canonical_bytes({}))

    with pytest.raises(LaunchError, match="MARKET_POLICY_INVALID_OR_MISSING"):
        evaluate_launch_preflight(ctx.config, ctx.dependencies)

    assert_no_write_authority(ctx)


def test_launch_evidence_is_atomic_hashed_append_only_and_sanitized(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)

    path = write_launch_evidence(
        ctx.config,
        "PREFLIGHT_PASS",
        {"expected_account_hash": ACCOUNT_HASH, "reason_codes": []},
    )
    first = json.loads(path.read_bytes())
    second_path = write_launch_evidence(
        ctx.config,
        "START_DELAY",
        {"delay_seconds": 60},
    )

    assert path == second_path
    assert first["event_sha256"] == sha256_json(first["event"])
    assert "DU" not in path.read_text(encoding="utf-8")
    assert not list(path.parent.glob("*.tmp"))
    history = (
        path.with_name("launch_events.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(history) == 2
    assert [json.loads(line)["event"]["event_type"] for line in history] == [
        "PREFLIGHT_PASS",
        "START_DELAY",
    ]


@pytest.mark.parametrize(
    "forbidden", ["account", "account_id", "credential", "token", "prompt"]
)
def test_launch_evidence_rejects_forbidden_keys(tmp_path: Path, forbidden: str) -> None:
    ctx = passing_context(tmp_path)

    with pytest.raises(LaunchError, match="LAUNCH_EVIDENCE_FORBIDDEN_KEY"):
        write_launch_evidence(ctx.config, "BLOCK", {forbidden: "secret"})

    assert not ctx.config.launch_root.exists()


class StopTestService(RuntimeError):
    pass


class FakeExecutionLock:
    def __init__(self, reason: str = "ACQUIRED") -> None:
        self.reason = reason
        self.calls: list[str] = []

    def acquire(self, owner):
        self.calls.append("acquire")
        return SimpleNamespace(
            acquired=self.reason == "ACQUIRED",
            reason=self.reason,
            owner_id=owner.owner_id,
            generation=1,
            recovery_required=self.reason != "OS_MUTEX_HELD",
            abandoned=self.reason == "ABANDONED_MUTEX",
            handle=None,
        )

    def heartbeat(self, receipt):
        self.calls.append("heartbeat")
        return SimpleNamespace(accepted=True, reason="ACCEPTED")

    def release(self, receipt):
        self.calls.append("release")
        return SimpleNamespace(released=True, reason="RELEASED")


def install_fake_lock(
    ctx: LaunchTestContext, reason: str = "ACQUIRED"
) -> FakeExecutionLock:
    lock = FakeExecutionLock(reason)
    ctx.dependencies.lock_factory = lambda _db: lock
    ctx.dependencies.lock_owner_factory = lambda now: SimpleNamespace(
        owner_id="test-owner",
        pid=1234,
        process_start=now.isoformat(),
        host_fingerprint="test-host",
        boot_session_id="test-boot",
    )
    return lock


def control_event_counts(path: Path) -> tuple[int, int, int]:
    with Database.open(path) as db:
        return tuple(
            int(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "experiment_clock_events",
                "experiment_authorization_events",
                "kill_switch_events",
            )
        )


def test_validate_launch_controls_only_consumes_preexisting_state(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    before = control_event_counts(ctx.config.db_path)

    with Database.open(ctx.config.db_path) as db:
        controls = validate_launch_controls(db, ctx.config)

    assert controls.kill_switch_state == "KILL_SWITCH_CLEAR"
    assert controls.authorization_event_id
    assert len(controls.clock_event_sha256) == 64
    assert control_event_counts(ctx.config.db_path) == before


def test_successor_launch_remains_bound_to_a_when_b_is_defined_later(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = passing_context(tmp_path)
    successor_receipt_path = (
        ctx.config.owner_authorization_path.parent
        / "owner_successor_authorization_v2.json"
    )
    definition_a, _ = build_authorized_successor(
        ctx.config.db_path, successor_receipt_path
    )
    with Database.open(ctx.config.db_path) as db:
        store = SuccessorEpochStore(db)
        definition_b = store.define(
            store.preview(
                epoch_id="AUTONOMY_EPOCH_B",
                predecessor_epoch_id="AUTONOMY_EPOCH_1",
                duration_days=30,
                initial_allocation=Decimal("500"),
                approved_git_head="3" * 40,
                objective_sha256="b" * 64,
                configuration_sha256="c" * 64,
                reason="PRE_START_RUNTIME_FAILURE",
            )
        )
    config = replace(
        ctx.config,
        owner_authorization_path=successor_receipt_path,
        model_attestation_exception_path=(
            successor_receipt_path.parent / "model_attestation_owner_exception_v2.json"
        ),
        launch_attempt_binding_path=(
            successor_receipt_path.parent / "launch_attempt_binding_v2.json"
        ),
        target_successor_epoch_id=str(definition_a["epoch_id"]),
        target_successor_definition_sha256=str(definition_a["definition_sha256"]),
    )
    _write_successor_model_attestation_exception(config)
    bind_launch_attempt(
        config.launch_attempt_id,
        config.identity_receipt_path,
        config.auditor_receipt_path,
        config.launch_attempt_binding_path,
        target_successor_epoch_id=config.target_successor_epoch_id,
        target_successor_definition_sha256=(config.target_successor_definition_sha256),
    )
    ctx.config = config
    ctx.dependencies.now_utc = lambda: SUCCESSOR_START + timedelta(seconds=2)
    ctx.dependencies.successor_broker_evidence_collector = (
        lambda _config, _preflight: BrokerTransitionEvidence(
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
    )
    install_fake_lock(ctx)
    monkeypatch.setattr(launch_module, "_lock_receipt_is_current", lambda *_: True)

    def stop_after_transition(db, _config, _preflight, controls, _dependencies):
        assert controls.clock is not None
        assert controls.clock.epoch_id == "AUTONOMY_EPOCH_2"
        raise StopTestService

    monkeypatch.setattr(launch_module, "_write_epoch_manifest", stop_after_transition)

    with pytest.raises(StopTestService):
        run_day1_launch(config, ctx.dependencies)

    with Database.open(config.db_path) as db:
        assert ExperimentEpochStore(db).current().epoch_id == "AUTONOMY_EPOCH_2"
        assert (
            db.execute(
                "SELECT COUNT(*) FROM experiment_epoch_clock_events_v2 "
                "WHERE epoch_id=?",
                (definition_b.epoch_id,),
            ).fetchone()[0]
            == 0
        )
        accepted = json.loads(
            db.execute(
                "SELECT payload_json FROM state_events "
                "WHERE event_type='DAY1_LAUNCH_ATTEMPT_ACCEPTED'"
            ).fetchone()[0]
        )
        assert accepted["target_successor_epoch_id"] == "AUTONOMY_EPOCH_2"
        assert (
            accepted["target_successor_definition_sha256"]
            == definition_a["definition_sha256"]
        )
        failed = json.loads(
            db.execute(
                "SELECT payload_json FROM state_events "
                "WHERE event_type='EPOCH_PRE_START_FAILED'"
            ).fetchone()[0]
        )
        clock_sha = str(
            db.execute(
                "SELECT event_sha256 FROM experiment_epoch_clock_events_v2 "
                "WHERE epoch_id='AUTONOMY_EPOCH_2'"
            ).fetchone()[0]
        )
        assert failed["epoch_id"] == "AUTONOMY_EPOCH_2"
        assert failed["clock_event_sha256"] == clock_sha

    with pytest.raises(LaunchError, match="FAILED_EPOCH_REQUIRES_EXPLICIT_SUCCESSOR"):
        run_day1_launch(config, ctx.dependencies)


def test_started_successor_resumes_with_fresh_attempt_without_duplicate_transition(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = passing_context(tmp_path)
    successor_receipt_path = (
        ctx.config.owner_authorization_path.parent
        / "owner_successor_authorization_v2.json"
    )
    definition, _ = build_authorized_successor(
        ctx.config.db_path, successor_receipt_path
    )
    config = replace(
        ctx.config,
        owner_authorization_path=successor_receipt_path,
        model_attestation_exception_path=(
            successor_receipt_path.parent / "model_attestation_owner_exception_v2.json"
        ),
        launch_attempt_binding_path=(
            successor_receipt_path.parent / "launch_attempt_binding_v2.json"
        ),
        target_successor_epoch_id=str(definition["epoch_id"]),
        target_successor_definition_sha256=str(definition["definition_sha256"]),
    )
    _write_successor_model_attestation_exception(config)
    bind_launch_attempt(
        config.launch_attempt_id,
        config.identity_receipt_path,
        config.auditor_receipt_path,
        config.launch_attempt_binding_path,
        target_successor_epoch_id=config.target_successor_epoch_id,
        target_successor_definition_sha256=(config.target_successor_definition_sha256),
    )
    ctx.config = config
    ctx.dependencies.now_utc = lambda: SUCCESSOR_START + timedelta(seconds=2)
    collector = Mock(
        return_value=BrokerTransitionEvidence(
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
    )
    ctx.dependencies.successor_broker_evidence_collector = collector
    install_fake_lock(ctx)
    monkeypatch.setattr(launch_module, "_lock_receipt_is_current", lambda *_: True)
    monkeypatch.setattr(
        launch_module, "verify_kernel_manifest", lambda *_: {"verified": True}
    )

    assert (
        run_day1_launch(config, ctx.dependencies)
        == "AUTONOMOUS_PAPER_EXPERIMENT_STOPPED"
    )
    manifest_path = (
        tmp_path
        / "state"
        / "ibkr_paper_30d"
        / "reports"
        / "autonomy_epoch_manifest.json"
    )
    original_manifest = manifest_path.read_bytes()

    resumed = replace(
        config,
        launch_attempt_id="22222222-2222-4222-8222-222222222222",
    )
    bind_launch_attempt(
        resumed.launch_attempt_id,
        resumed.identity_receipt_path,
        resumed.auditor_receipt_path,
        resumed.launch_attempt_binding_path,
        target_successor_epoch_id=resumed.target_successor_epoch_id,
        target_successor_definition_sha256=(resumed.target_successor_definition_sha256),
    )

    assert (
        run_day1_launch(resumed, ctx.dependencies)
        == "AUTONOMOUS_PAPER_EXPERIMENT_STOPPED"
    )

    assert collector.call_count == 1
    assert manifest_path.read_bytes() == original_manifest
    with Database.open(config.db_path) as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM experiment_epoch_clock_events_v2 "
                "WHERE epoch_id='AUTONOMY_EPOCH_2'"
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM state_events "
                "WHERE event_type='EXPERIMENT_EPOCH_ACTIVATED' "
                "AND json_extract(payload_json,'$.epoch_id')='AUTONOMY_EPOCH_2'"
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM state_events "
                "WHERE event_type='EPOCH_MANIFEST_CREATED' "
                "AND json_extract(payload_json,'$.epoch_id')='AUTONOMY_EPOCH_2'"
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM state_events WHERE event_type='EPOCH_STARTED' "
                "AND json_extract(payload_json,'$.epoch_id')='AUTONOMY_EPOCH_2'"
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT COUNT(*) FROM state_events "
                "WHERE event_type='DAY1_LAUNCH_ATTEMPT_ACCEPTED' "
                "AND json_extract(payload_json,'$.target_successor_epoch_id')="
                "'AUTONOMY_EPOCH_2'"
            ).fetchone()[0]
            == 2
        )


def test_validate_launch_controls_rejects_clock_mismatch_without_writes(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    mismatched = replace(
        ctx.config,
        scheduled_start_utc=datetime(2026, 9, 23, 13, 31, tzinfo=timezone.utc),
    )
    before = control_event_counts(ctx.config.db_path)

    with Database.open(ctx.config.db_path) as db:
        with pytest.raises(LaunchError, match="EXPERIMENT_CLOCK_MISMATCH"):
            validate_launch_controls(db, mismatched)

    assert control_event_counts(ctx.config.db_path) == before


def test_validate_launch_controls_rejects_any_triggered_kill_history(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    with Database.open(ctx.config.db_path) as db:
        switch = KillSwitchStore(db)
        switch.set("KILL_SWITCH_TRIGGERED", reason="owner stop")
        before = tuple(
            str(row[0])
            for row in db.execute(
                "SELECT state FROM kill_switch_events ORDER BY sequence"
            ).fetchall()
        )

        with pytest.raises(LaunchError, match="KILL_SWITCH_TRIGGERED"):
            validate_launch_controls(db, ctx.config)

        after = tuple(
            str(row[0])
            for row in db.execute(
                "SELECT state FROM kill_switch_events ORDER BY sequence"
            ).fetchall()
        )
    assert (
        after
        == before
        == (
            "KILL_SWITCH_CLEAR",
            "KILL_SWITCH_TRIGGERED",
        )
    )


def test_validate_launch_controls_accepts_exact_verified_recovery(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    preflight = evaluate_launch_preflight(ctx.config, ctx.dependencies)
    with Database.open(ctx.config.db_path) as db:
        switch = KillSwitchStore(db)
        trigger_event_id = switch.set(
            "KILL_SWITCH_TRIGGERED",
            reason="watchdog pacing failure",
            actor="CONTINUITY_V3_RUNTIME",
        )
        trigger_payload_sha256 = str(
            db.execute(
                "SELECT payload_sha256 FROM kill_switch_events WHERE event_id=?",
                (trigger_event_id,),
            ).fetchone()[0]
        )
        receipt = {
            "schema": "KILL_SWITCH_RECOVERY_RECEIPT_V1",
            "trigger_event_id": trigger_event_id,
            "trigger_payload_sha256": trigger_payload_sha256,
            "approved_head": ctx.config.approved_head,
            "owner_sid": OWNER_SID,
            "account_identity_sha256": ACCOUNT_HASH,
            "authorization_event_id": preflight.authorization_event_id,
            "clock_event_sha256": ExperimentClockStore(db).load().event_sha256,
            "broker_evidence_sha256": "d" * 64,
            "broker_server_time_utc": NOW.isoformat().replace("+00:00", "Z"),
            "collected_at_utc": NOW.isoformat().replace("+00:00", "Z"),
            "expires_at_utc": (NOW + timedelta(seconds=30))
            .isoformat()
            .replace("+00:00", "Z"),
            "positions_count": 1,
            "open_orders_count": 0,
            "executions_count": 1,
            "broker_write_count": 0,
            "query_completeness": {
                "managed_accounts": True,
                "positions": True,
                "open_orders": True,
                "executions": True,
                "current_time": True,
            },
            "recovery_reason_code": "CONTINUITY_WATCHDOG_PACING_DEFECT_REMEDIATED",
        }
        switch.recover(
            receipt,
            now_utc=NOW,
            expected_owner_sid=OWNER_SID,
            expected_account_identity_sha256=ACCOUNT_HASH,
            expected_approved_head=str(ctx.config.approved_head),
            expected_authorization_event_id=preflight.authorization_event_id,
            expected_clock_event_sha256=ExperimentClockStore(db).load().event_sha256,
        )

        controls = validate_launch_controls(db, ctx.config, preflight=preflight)

    assert controls.kill_switch_state == "KILL_SWITCH_CLEAR"


def test_validate_launch_controls_rejects_invalid_ledger_projection(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    with Database.open(ctx.config.db_path) as db:
        AutonomousExperimentLedger(db).append("UNKNOWN_EVENT", {})
        with pytest.raises(LaunchError, match="EXPERIMENT_LEDGER_INVALID"):
            validate_launch_controls(db, ctx.config)


def test_validate_launch_controls_rejects_integrity_check_failure(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    with Database.open(ctx.config.db_path) as db:
        real_execute = db.execute

        def execute(sql, parameters=()):
            if sql == "PRAGMA integrity_check":
                return SimpleNamespace(fetchall=lambda: [("corrupt",)])
            return real_execute(sql, parameters)

        db.execute = execute  # type: ignore[method-assign]
        with pytest.raises(LaunchError, match="DATABASE_INTEGRITY_CHECK_FAILED"):
            validate_launch_controls(db, ctx.config)


def test_run_launch_arms_only_inside_foreground_service_and_restores_env(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    lock = install_fake_lock(ctx)
    previous_arm = os.environ.pop("IBKR_AUTONOMOUS_PAPER_ARMED", None)
    previous_hash = os.environ.pop("IBKR_PAPER_ACCOUNT_SHA256", None)
    observations: list[tuple[str | None, str | None]] = []
    service = Mock()

    def service_factory(*args, **kwargs):
        observations.append(
            (
                os.environ.get("IBKR_AUTONOMOUS_PAPER_ARMED"),
                os.environ.get("IBKR_PAPER_ACCOUNT_SHA256"),
            )
        )
        return service

    def stop_service():
        observations.append(
            (
                os.environ.get("IBKR_AUTONOMOUS_PAPER_ARMED"),
                os.environ.get("IBKR_PAPER_ACCOUNT_SHA256"),
            )
        )
        raise StopTestService

    service.run_forever.side_effect = stop_service
    ctx.dependencies.service_factory = service_factory
    try:
        with pytest.raises(StopTestService):
            run_day1_launch(ctx.config, ctx.dependencies)
        assert observations == [("true", ACCOUNT_HASH), ("true", ACCOUNT_HASH)]
        assert os.environ.get("IBKR_AUTONOMOUS_PAPER_ARMED") is None
        assert os.environ.get("IBKR_PAPER_ACCOUNT_SHA256") is None
    finally:
        if previous_arm is not None:
            os.environ["IBKR_AUTONOMOUS_PAPER_ARMED"] = previous_arm
        if previous_hash is not None:
            os.environ["IBKR_PAPER_ACCOUNT_SHA256"] = previous_hash

    assert lock.calls[0] == "acquire"
    assert lock.calls[-1] == "release"
    assert ctx.executor_tripwire.calls == []
    assert ctx.ib_tripwire.calls == []


def test_continuity_recovery_gates_precede_writer_watchdog_and_codex(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    lock = install_fake_lock(ctx)
    trace = []

    class Writer:
        def start(self):
            trace.append("writer_start")

        def wait_until_ready(self, timeout_seconds):
            trace.append("writer_ready")
            return True

        def stop(self, timeout_seconds):
            trace.append("writer_stop")
            return True

    class Watchdog:
        def start(self):
            trace.append("watchdog_start")

        def stop(self, timeout_seconds):
            trace.append("watchdog_stop")
            return SimpleNamespace(stopped=True, timed_out=False)

    watchdog = Watchdog()

    class Service:
        def run_forever(self):
            watchdog.start()
            trace.append("codex")
            watchdog.stop(5)

    original_provenance = ctx.dependencies.runtime_provenance_validator
    ctx.dependencies.runtime_provenance_validator = lambda config: (
        trace.append("runtime_integrity") or original_provenance(config)
    )
    ctx.dependencies.continuity_schema_verifier = lambda db: (
        trace.append("schema_v3") or {"status": "PASS"}
    )
    ctx.dependencies.provider_abandonment_recoverer = (
        lambda db, owner, config, preflight: trace.append("provider_recovery")
        or {"status": "PASS"}
    )
    ctx.dependencies.pending_binding_reconciler = (
        lambda db, config, preflight: trace.append("binding_recovery")
        or {"status": "PASS"}
    )
    ctx.dependencies.continuity_uncertainty_reader = lambda db: (
        trace.append("uncertainty_check") or ()
    )
    ctx.dependencies.broker_write_coordinator_factory = lambda: (
        trace.append("coordinator") or object()
    )
    ctx.dependencies.authoritative_writer_factory = lambda *args, **kwargs: Writer()
    ctx.dependencies.continuity_watchdog_factory = lambda *args, **kwargs: watchdog
    ctx.dependencies.service_factory = lambda *args, **kwargs: Service()

    status = run_day1_launch(ctx.config, ctx.dependencies)

    assert status == "AUTONOMOUS_PAPER_EXPERIMENT_STOPPED"
    assert trace == [
        "runtime_integrity",
        "schema_v3",
        "provider_recovery",
        "binding_recovery",
        "uncertainty_check",
        "coordinator",
        "writer_start",
        "writer_ready",
        "watchdog_start",
        "codex",
        "watchdog_stop",
        "writer_stop",
    ]
    assert lock.calls[-1] == "release"


def test_writer_readiness_failure_stops_writer_before_releasing_lock(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    lock = install_fake_lock(ctx)
    writer = Mock()
    writer.wait_until_ready.return_value = False
    writer.stop.return_value = True
    ctx.dependencies.authoritative_writer_factory = Mock(return_value=writer)

    with pytest.raises(LaunchError, match="CONTINUITY_WRITER_START_FAILURE"):
        run_day1_launch(ctx.config, ctx.dependencies)

    writer.stop.assert_called_once_with(5.0)
    assert lock.calls[-1] == "release"
    assert ctx.service_factory.mock_calls == []


def test_writer_shutdown_timeout_does_not_mask_start_failure(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    lock = install_fake_lock(ctx)
    writer = Mock()
    writer.wait_until_ready.return_value = False
    writer.stop.return_value = False
    ctx.dependencies.authoritative_writer_factory = Mock(return_value=writer)

    with pytest.raises(LaunchError) as caught:
        run_day1_launch(ctx.config, ctx.dependencies)

    assert caught.value.code == "CONTINUITY_WRITER_START_FAILURE"
    assert caught.value.details == {
        "cleanup_reason_codes": ["CONTINUITY_WRITER_SHUTDOWN_TIMEOUT"]
    }
    writer.stop.assert_called_once_with(5.0)
    assert lock.calls[-1] == "release"
    assert ctx.service_factory.mock_calls == []


def test_launch_passes_only_writer_command_interface_to_model_service(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    install_fake_lock(ctx)
    coordinator = object()
    model_executor = object()
    captured = {}
    ctx.dependencies.broker_write_coordinator_factory = Mock(return_value=coordinator)
    ctx.dependencies.model_executor_factory = Mock(return_value=model_executor)

    class Service:
        def run_forever(self):
            return None

    def service_factory(*args, **kwargs):
        captured.update(kwargs)
        return Service()

    ctx.dependencies.service_factory = service_factory

    assert run_day1_launch(ctx.config, ctx.dependencies) == (
        "AUTONOMOUS_PAPER_EXPERIMENT_STOPPED"
    )
    ctx.dependencies.model_executor_factory.assert_called_once()
    executor_args = ctx.dependencies.model_executor_factory.call_args.kwargs
    assert executor_args["coordinator"] is coordinator
    assert executor_args["db_path"] == ctx.config.db_path
    assert executor_args["config"] == ctx.config
    assert executor_args["preflight"].expected_account_hash == ACCOUNT_HASH
    assert len(executor_args["production_validation_sha256"]) == 64
    assert captured["executor"] is model_executor
    lifecycle = captured["provider_lifecycle"]
    assert lifecycle.launch_attempt_id == ATTEMPT_ID
    assert lifecycle.pid == 1234
    assert lifecycle.boot_session_identity == "test-boot"
    assert lifecycle.expected_account_identity_sha256 == ACCOUNT_HASH


def test_launch_shares_external_critical_alert_reporter_with_runtime_components(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    install_fake_lock(ctx)
    reporter = Mock()
    captured = {}
    ctx.dependencies.critical_alert_reporter_factory = Mock(return_value=reporter)

    class Service:
        def run_forever(self):
            return None

    def service_factory(*args, **kwargs):
        captured.update(kwargs)
        return Service()

    ctx.dependencies.service_factory = service_factory

    run_day1_launch(ctx.config, ctx.dependencies)

    writer_kwargs = ctx.dependencies.authoritative_writer_factory.call_args.kwargs
    watchdog_kwargs = ctx.dependencies.continuity_watchdog_factory.call_args.kwargs
    assert writer_kwargs["uncertainty_reporter"] is reporter
    assert watchdog_kwargs["uncertainty_reporter"] is reporter
    assert captured["critical_alert_reporter"] is reporter


@pytest.mark.parametrize(
    ("gate", "expected"),
    [
        ("schema", "CONTINUITY_SCHEMA_V3_REQUIRED"),
        ("provider", "CONTINUITY_PROVIDER_RECOVERY_BLOCK"),
        ("binding", "CONTINUITY_PENDING_BINDING_AMBIGUOUS"),
        ("uncertainty", "CONTINUITY_UNCERTAINTY_UNRESOLVED"),
    ],
)
def test_continuity_recovery_failure_blocks_before_writer_or_service(
    tmp_path: Path, gate: str, expected: str
) -> None:
    ctx = passing_context(tmp_path)
    install_fake_lock(ctx)
    if gate == "schema":
        ctx.dependencies.continuity_schema_verifier = lambda db: (_ for _ in ()).throw(
            RuntimeError("missing schema")
        )
    elif gate == "provider":
        ctx.dependencies.provider_abandonment_recoverer = lambda *args: {
            "status": "BLOCK"
        }
    elif gate == "binding":
        ctx.dependencies.pending_binding_reconciler = lambda *args: {
            "status": "BLOCK",
            "reason_codes": ["ORDER_IDENTITY_AMBIGUOUS"],
        }
    else:
        ctx.dependencies.continuity_uncertainty_reader = lambda db: (
            "CONTINUITY_ORDER_STATE_UNCERTAIN",
        )

    with pytest.raises(LaunchError, match=expected):
        run_day1_launch(ctx.config, ctx.dependencies)

    ctx.dependencies.authoritative_writer_factory.assert_not_called()
    assert ctx.service_factory.mock_calls == []


def test_corrupt_continuity_chain_blocks_before_writer_or_service(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    install_fake_lock(ctx)
    payload = {"status": "CONFIRMED"}
    with Database.open(ctx.config.db_path) as db:
        db.execute(
            "INSERT INTO continuity_execution_events("
            "event_id,execution_id,evaluation_id,plan_id,order_ref,"
            "execution_ordinal,event_type,payload_json,payload_sha256,"
            "previous_event_sha256,event_sha256,created_at_utc) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "event-corrupt",
                "execution-corrupt",
                "evaluation-corrupt",
                "plan-corrupt",
                "order-corrupt",
                1,
                "RESULT",
                canonical_bytes(payload).decode("utf-8"),
                "0" * 64,
                None,
                "1" * 64,
                NOW.isoformat(),
            ),
        )
    ctx.dependencies.continuity_uncertainty_reader = (
        launch_module._default_continuity_uncertainty
    )

    with pytest.raises(LaunchError, match="CONTINUITY_AUTHORITY_CORRUPT"):
        run_day1_launch(ctx.config, ctx.dependencies)

    ctx.dependencies.authoritative_writer_factory.assert_not_called()
    assert ctx.service_factory.mock_calls == []


def test_corrupt_provider_chain_is_not_misclassified_as_recovery_block(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    install_fake_lock(ctx)
    payload = {"state": "IN_FLIGHT", "payload": {}}
    with Database.open(ctx.config.db_path) as db:
        db.execute(
            "INSERT INTO provider_invocation_events("
            "event_id,invocation_id,event_type,payload_json,payload_sha256,"
            "previous_event_sha256,event_sha256,created_at_utc) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                "provider-event-corrupt",
                "provider-invocation-corrupt",
                "IN_FLIGHT",
                canonical_bytes(payload).decode("utf-8"),
                "0" * 64,
                None,
                "1" * 64,
                NOW.isoformat(),
            ),
        )
    ctx.dependencies.provider_abandonment_recoverer = (
        launch_module._default_provider_recovery
    )

    with pytest.raises(LaunchError, match="CONTINUITY_AUTHORITY_CORRUPT"):
        run_day1_launch(ctx.config, ctx.dependencies)

    ctx.dependencies.authoritative_writer_factory.assert_not_called()
    assert ctx.service_factory.mock_calls == []


def test_launcher_does_not_append_control_events_and_consumes_attempt_once(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    install_fake_lock(ctx)
    before = control_event_counts(ctx.config.db_path)
    ctx.service_factory.return_value.run_forever.side_effect = StopTestService

    with pytest.raises(StopTestService):
        run_day1_launch(ctx.config, ctx.dependencies)

    assert control_event_counts(ctx.config.db_path) == before
    with Database.open(ctx.config.db_path) as db:
        clock = ExperimentClockStore(db).load()
        assert clock is not None
        assert clock.start_utc == datetime(2026, 9, 23, 13, 30, tzinfo=timezone.utc)
        assert clock.duration_days == 30
        assert clock.initial_allocation == Decimal("500")
        assert (
            OwnerAuthorizationStore(db).current(clock_event_sha256=clock.event_sha256)
            == "AUTHORIZED"
        )
        accepted = db.execute(
            "SELECT COUNT(*) FROM state_events WHERE event_type='DAY1_LAUNCH_ATTEMPT_ACCEPTED'"
        ).fetchone()[0]
    assert accepted == 1

    with pytest.raises(LaunchError, match="LAUNCH_ATTEMPT_REUSED"):
        run_day1_launch(ctx.config, ctx.dependencies)
    assert ctx.service_factory.call_count == 1
    assert ctx.executor_tripwire.calls == []
    assert ctx.ib_tripwire.calls == []


@pytest.mark.parametrize("reason", ["ABANDONED_MUTEX", "LOCK_RECORD_ACTIVE"])
def test_ambiguous_execution_lock_requires_owner_action(
    tmp_path: Path, reason: str
) -> None:
    ctx = passing_context(tmp_path)
    lock = install_fake_lock(ctx, reason)

    with pytest.raises(LaunchError, match="EXECUTION_LOCK_OWNER_ACTION_REQUIRED"):
        run_day1_launch(ctx.config, ctx.dependencies)

    assert lock.calls == ["acquire"]
    assert_no_write_authority(ctx)


def test_live_execution_lock_is_idempotent_without_service(tmp_path: Path) -> None:
    ctx = passing_context(tmp_path)
    lock = install_fake_lock(ctx, "OS_MUTEX_HELD")

    status = run_day1_launch(ctx.config, ctx.dependencies)

    assert status == "AUTONOMOUS_PAPER_EXPERIMENT_ALREADY_RUNNING"
    assert lock.calls == ["acquire"]
    assert_no_write_authority(ctx)


def test_corrupt_execution_lock_projection_requires_owner_action(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)

    class CorruptLock:
        def acquire(self, owner):
            raise LockIntegrityError("execution lock projection hash is invalid")

    ctx.dependencies.lock_factory = lambda _db: CorruptLock()

    with pytest.raises(LaunchError, match="EXECUTION_LOCK_OWNER_ACTION_REQUIRED"):
        run_day1_launch(ctx.config, ctx.dependencies)

    assert_no_write_authority(ctx)


def test_missing_authorization_blocks_without_recreating_it(tmp_path: Path) -> None:
    ctx = passing_context(tmp_path)
    ctx.config.owner_authorization_path.unlink()

    with pytest.raises(LaunchError, match="OWNER_AUTHORIZATION_RECEIPT_MISSING"):
        run_day1_launch(ctx.config, ctx.dependencies)

    assert not ctx.config.owner_authorization_path.exists()
    assert not (
        tmp_path
        / "state"
        / "ibkr_paper_30d"
        / "reports"
        / "autonomy_epoch_manifest.json"
    ).exists()
    with Database.open(ctx.config.db_path) as db:
        epoch_events = db.execute(
            "SELECT COUNT(*) FROM state_events WHERE event_type LIKE 'EPOCH_%'"
        ).fetchone()[0]
    assert epoch_events == 0
    assert_no_write_authority(ctx)


def test_restart_after_crash_requires_fresh_attempt_and_reconciliation(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    install_fake_lock(ctx)
    ctx.service_factory.return_value.run_forever.side_effect = RuntimeError("crash")

    with pytest.raises(RuntimeError, match="crash"):
        run_day1_launch(ctx.config, ctx.dependencies)
    with pytest.raises(LaunchError, match="LAUNCH_ATTEMPT_REUSED"):
        run_day1_launch(ctx.config, ctx.dependencies)

    ctx.config = replace(
        ctx.config,
        launch_attempt_id="22222222-2222-4222-8222-222222222222",
    )
    write_identity_receipt(ctx, broker_reconciliation_gate="BLOCK")
    with pytest.raises(LaunchError, match="BROKER_RECONCILIATION_REQUIRED"):
        run_day1_launch(ctx.config, ctx.dependencies)

    assert ctx.service_factory.call_count == 1
    assert ctx.executor_tripwire.calls == []
    assert ctx.ib_tripwire.calls == []


def test_launch_order_is_preflight_lock_controls_arm_service(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = passing_context(tmp_path)
    events: list[str] = []
    original_preflight = launch_module.evaluate_launch_preflight
    original_controls = launch_module.validate_launch_controls
    original_provenance = ctx.dependencies.runtime_provenance_validator

    def preflight(config, dependencies):
        events.append("preflight")
        return original_preflight(config, dependencies)

    def controls(db, config, *, preflight=None):
        events.append("controls")
        return original_controls(db, config, preflight=preflight)

    def provenance(config):
        events.append("provenance")
        assert original_provenance is not None
        return original_provenance(config)

    class OrderedLock(FakeExecutionLock):
        def acquire(self, owner):
            events.append("lock")
            return super().acquire(owner)

    lock = OrderedLock()
    ctx.dependencies.lock_factory = lambda _db: lock
    ctx.dependencies.runtime_provenance_validator = provenance
    ctx.dependencies.lock_owner_factory = lambda now: SimpleNamespace(
        owner_id="ordered-owner",
        pid=1234,
        process_start=now.isoformat(),
        host_fingerprint="test-host",
        boot_session_id="test-boot",
    )
    service = Mock()

    def service_factory(*args, **kwargs):
        assert os.environ["IBKR_AUTONOMOUS_PAPER_ARMED"] == "true"
        events.append("service")
        return service

    def stop():
        events.append("run")
        raise StopTestService

    service.run_forever.side_effect = stop
    ctx.dependencies.service_factory = service_factory
    monkeypatch.setattr(launch_module, "evaluate_launch_preflight", preflight)
    monkeypatch.setattr(launch_module, "validate_launch_controls", controls)

    with pytest.raises(StopTestService):
        run_day1_launch(ctx.config, ctx.dependencies)

    assert events == [
        "preflight",
        "provenance",
        "lock",
        "controls",
        "service",
        "run",
    ]
    assert ctx.executor_tripwire.calls == []
    assert ctx.ib_tripwire.calls == []


def test_runtime_provenance_block_occurs_before_lock_or_manifest(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    lock = install_fake_lock(ctx)
    ctx.dependencies.runtime_provenance_validator = lambda _config: {
        "gate_status": "BLOCK",
        "reason_codes": ["UNTRACKED_RUNTIME_SOURCE"],
    }

    with pytest.raises(LaunchError, match="RUNTIME_SOURCE_PROVENANCE_BLOCK"):
        run_day1_launch(ctx.config, ctx.dependencies)

    assert lock.calls == []
    assert not (
        tmp_path
        / "state"
        / "ibkr_paper_30d"
        / "reports"
        / "autonomy_epoch_manifest.json"
    ).exists()
    assert_no_write_authority(ctx)


def test_active_database_projection_without_live_mutex_requires_owner_action(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    payload = {
        "state": "ACTIVE",
        "owner_id": "stale-owner",
        "pid": 999999,
        "process_start": "2026-09-23T19:00:00Z",
        "host_fingerprint": "test-host",
        "boot_session_id": "old-boot",
        "generation": 1,
        "heartbeat_at_utc": "2026-09-23T19:00:00Z",
        "order_authority": False,
    }
    with Database.open(ctx.config.db_path) as db:
        db.execute(
            "INSERT INTO experiment_state("
            "experiment_id,version,payload_json,payload_sha256,updated_at_utc"
            ") VALUES(?,?,?,?,?)",
            (
                "EXECUTION_LOCK_V1",
                1,
                canonical_bytes(payload).decode("utf-8"),
                sha256_json(payload),
                "2026-09-23T19:00:00Z",
            ),
        )
    mutex_name = f"Local\\CodexIbkrPaper30DTest-{tmp_path.name}"
    ctx.dependencies.lock_factory = lambda db: ExecutionLock(db, mutex_name=mutex_name)
    ctx.dependencies.lock_owner_factory = lambda now: launch_module._lock_owner(now)

    with pytest.raises(LaunchError, match="EXECUTION_LOCK_OWNER_ACTION_REQUIRED"):
        run_day1_launch(ctx.config, ctx.dependencies)

    assert_no_write_authority(ctx)


def test_day1_launch_recovers_proven_stale_lock_before_service(tmp_path: Path) -> None:
    ctx = passing_context(tmp_path)
    stale = LockOwner(
        owner_id="stale-owner",
        pid=999999,
        process_start="2026-09-20T00:00:00Z",
        host_fingerprint="same-host",
        boot_session_id="same-boot",
    )
    replacement = LockOwner(
        owner_id="replacement-owner",
        pid=os.getpid(),
        process_start="2026-09-23T19:59:00Z",
        host_fingerprint="same-host",
        boot_session_id="same-boot",
    )
    payload = {
        "state": "ACTIVE",
        **stale.model_dump(),
        "generation": 11,
        "acquired_at_utc": "2026-09-20T00:00:00Z",
        "heartbeat_at_utc": "2026-09-20T00:00:00Z",
        "order_authority": False,
    }
    with Database.open(ctx.config.db_path) as db:
        db.execute(
            "INSERT INTO experiment_state(experiment_id,version,payload_json,payload_sha256,updated_at_utc) "
            "VALUES(?,?,?,?,?)",
            (
                "EXECUTION_LOCK_V1",
                1,
                canonical_bytes(payload).decode("utf-8"),
                sha256_json(payload),
                "2026-09-20T00:00:00Z",
            ),
        )

    class DeadObserver:
        def observe(self, pid):
            return None

        def has_other_execution_authority(self, *, excluding_pid):
            return False

        def current_boot_session_id(self):
            return "same-boot"

    mutex_name = f"Local\\CodexIbkrPaper30DRecovery-{tmp_path.name}"
    ctx.dependencies.lock_factory = lambda db: ExecutionLock(
        db,
        mutex_name=mutex_name,
        process_observer=DeadObserver(),
        now_utc=lambda: NOW,
    )
    ctx.dependencies.lock_owner_factory = lambda now: replacement
    ctx.service_factory.return_value.run_forever.side_effect = StopTestService

    with pytest.raises(StopTestService):
        run_day1_launch(ctx.config, ctx.dependencies)

    with Database.open(ctx.config.db_path) as db:
        events = [
            row[0]
            for row in db.execute(
                "SELECT event_type FROM execution_lock_events WHERE generation IN (11,12) ORDER BY sequence"
            ).fetchall()
        ]
    assert events[:2] == ["STALE_OWNER_RECOVERED", "ACQUIRED"]
    assert ctx.executor_tripwire.calls == []
    assert ctx.ib_tripwire.calls == []


def test_rejected_lock_heartbeat_stops_service_and_records_owner_action(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = passing_context(tmp_path)
    service = Mock()
    evidence: list[tuple[str, dict[str, object]]] = []
    database_opens = 0

    class RejectedHeartbeat:
        def heartbeat(self, receipt):
            return SimpleNamespace(accepted=False, reason="OWNER_MISMATCH")

    def database_factory(path):
        nonlocal database_opens
        database_opens += 1
        return Database.open(path)

    ctx.dependencies.database_factory = database_factory
    ctx.dependencies.lock_factory = lambda _db: RejectedHeartbeat()
    monkeypatch.setattr(
        launch_module,
        "write_launch_evidence",
        lambda _config, event_type, payload: evidence.append((event_type, payload)),
    )
    worker = launch_module._LockHeartbeat(
        config=ctx.config,
        dependencies=ctx.dependencies,
        receipt=SimpleNamespace(),
        service=service,
        interval_seconds=0.01,
    )

    worker.start()
    deadline = time.time() + 1.0
    while not service.stop.called and time.time() < deadline:
        time.sleep(0.01)
    worker.stop()

    assert service.stop.called
    assert worker.failure_code == "EXECUTION_LOCK_HEARTBEAT_REJECTED"
    assert database_opens == 1
    assert evidence == [
        (
            "OWNER_ACTION_REQUIRED",
            {"reason_codes": ["EXECUTION_LOCK_HEARTBEAT_REJECTED"]},
        )
    ]


@pytest.mark.parametrize(
    ("code", "expected_status", "expected_exit"),
    [
        ("AUDITOR_GATE_BLOCKED", "BLOCK", 20),
        ("EXECUTION_LOCK_OWNER_ACTION_REQUIRED", "OWNER_ACTION_REQUIRED", 30),
    ],
)
def test_cli_emits_one_sanitized_status_line(
    tmp_path: Path,
    monkeypatch,
    capsys,
    code: str,
    expected_status: str,
    expected_exit: int,
) -> None:
    def fail(*args, **kwargs):
        raise LaunchError(code)

    monkeypatch.setattr(launch_module, "run_day1_launch", fail)
    monkeypatch.setattr(launch_module, "_default_dependencies", lambda: object())
    monkeypatch.setattr(launch_module, "write_launch_evidence", Mock())

    exit_code = main(["--repo-root", str(tmp_path), "--launch-attempt-id", ATTEMPT_ID])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == expected_exit
    assert payload == {"status": expected_status, "reason_codes": [code]}
    assert captured.out.count("\n") == 1
    assert "DU" not in captured.out
    assert "secret" not in captured.out


class NoTradeProvider:
    def next_turn(self, request, bundle, history, toolbox_manifest):
        return AutonomousTurn(
            mode=AutonomousTurnMode.FINAL,
            research_requests=[],
            decision=TraderDecision.NO_TRADE,
            proposal=None,
            confidence="0.8",
            reasoning_summary="No qualified opportunity in the current evidence.",
            reason_codes=["NO_EDGE"],
        )


class ReadOnlyLaunchToolbox:
    expected_account_hash = ACCOUNT_HASH

    def __init__(self, ib_client: IBWriteTripwire) -> None:
        self.ib_client = ib_client

    def manifest(self):
        return [{"tool": item.value} for item in ResearchTool]

    def execute(self, request, bundle):
        payloads = {
            ResearchTool.EXECUTIONS: {"executions": []},
            ResearchTool.ACCOUNT_STATE: {
                "server_time_utc": "2026-09-23T20:00:00Z",
                "paper_account": True,
                "declared_options_level": 4,
            },
            ResearchTool.POSITIONS: {"positions": []},
            ResearchTool.OPEN_ORDERS: {"open_orders": []},
        }
        return ResearchResult(
            request_id=request.request_id,
            tool=request.tool,
            success=request.tool in payloads,
            data=payloads.get(request.tool, {}),
            error=(
                None if request.tool in payloads else "unsupported read-only test tool"
            ),
        )


def test_complete_fake_launch_persists_running_without_broker_write(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    install_fake_lock(ctx)
    holder: dict[str, AutonomousExperimentService] = {}
    toolbox = ReadOnlyLaunchToolbox(ctx.ib_tripwire)

    def stop_after_first_wait(_seconds: float) -> None:
        holder["service"].stop()

    def real_service_factory(db, **kwargs):
        kwargs["provider"] = NoTradeProvider()
        service = AutonomousExperimentService(
            db,
            **kwargs,
            broker_now=lambda: NOW,
            sleep=stop_after_first_wait,
            monotonic=lambda: 0.0,
        )
        holder["service"] = service
        return service

    ctx.dependencies.service_factory = real_service_factory
    ctx.dependencies.model_executor_factory = Mock(return_value=ctx.executor_tripwire)
    ctx.dependencies.research_toolbox_factory = (
        lambda workspace, _preflight: launch_module.AutonomyToolbox(toolbox, workspace)
    )

    status = run_day1_launch(ctx.config, ctx.dependencies)

    assert status == "AUTONOMOUS_PAPER_EXPERIMENT_STOPPED"
    with Database.open(ctx.config.db_path) as db:
        row = db.execute(
            "SELECT payload_json FROM state_events "
            "WHERE event_type='AUTONOMOUS_PAPER_EXPERIMENT_RUNNING' "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        running = json.loads(str(row[0]))
        chain = EventRepository(db).verify_chain()
    assert running["decision"] == "NO_TRADE"
    assert running["launch_attempt_id"] == ctx.config.launch_attempt_id
    assert chain.valid is True
    assert ctx.executor_tripwire.calls == []
    assert ctx.ib_tripwire.calls == []


def test_launch_writes_epoch_observational_manifest(tmp_path: Path) -> None:
    """AUTONOMY_EPOCH_1: launch writes the observational epoch manifest with
    provenance hashes. It must never influence strategy and must not leak
    secrets."""

    ctx = passing_context(tmp_path)
    install_fake_lock(ctx)
    ctx.service_factory.return_value.run_forever.side_effect = StopTestService

    with pytest.raises(StopTestService):
        run_day1_launch(ctx.config, ctx.dependencies)

    manifest_path = (
        tmp_path
        / "state"
        / "ibkr_paper_30d"
        / "reports"
        / "autonomy_epoch_manifest.json"
    )
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "AUTONOMY_EPOCH_MANIFEST_V2"
    assert manifest["epoch_id"] == "AUTONOMY_EPOCH_1"
    assert manifest["model"] == "gpt-5.6-sol"
    assert manifest["reasoning_effort"] == "max"
    assert manifest["self_tooling_enabled"] is True
    assert manifest["persistent_workspace_enabled"] is True
    assert manifest["quantconnect_capability"] in {
        "OPTIONAL_AVAILABLE",
        "OPTIONAL_UNAVAILABLE",
    }
    assert manifest["observational_only"] is True
    assert len(manifest["immutable_kernel_manifest_hash"]) == 64
    assert len(manifest["effective_payload_sha256"]) == 64
    assert len(manifest["first_process_bootstrap_sha256"]) == 64
    assert len(manifest["tool_manifest_sha256"]) == 64
    assert len(manifest["risk_policy_sha256"]) == 64
    assert len(manifest["epoch_manifest_sha256"]) == 64
    assert manifest["effective_payload_sha256"] == sha256_json(
        manifest["effective_payload"]
    )
    assert manifest["receipt_sha256"] == {
        "auditor": hashlib.sha256(
            ctx.config.auditor_receipt_path.read_bytes()
        ).hexdigest(),
        "launch_attempt_binding": hashlib.sha256(
            ctx.config.launch_attempt_binding_path.read_bytes()
        ).hexdigest(),
        "market_validation": hashlib.sha256(
            ctx.config.market_validation_path.read_bytes()
        ).hexdigest(),
        "model_attestation_exception": hashlib.sha256(
            ctx.config.model_attestation_exception_path.read_bytes()
        ).hexdigest(),
        "owner_authorization": hashlib.sha256(
            ctx.config.owner_authorization_path.read_bytes()
        ).hexdigest(),
        "paper_identity": hashlib.sha256(
            ctx.config.identity_receipt_path.read_bytes()
        ).hexdigest(),
    }
    service_kwargs = ctx.service_factory.call_args.kwargs
    assert service_kwargs["timeout_seconds"] == 600
    assert (
        service_kwargs["toolbox"].manifest()
        == manifest["effective_payload"]["tool_manifest"]
    )
    assert (
        service_kwargs["provider"]._first_process_bootstrap
        == manifest["effective_payload"]["first_process_bootstrap"]
    )
    with Database.open(ctx.config.db_path) as db:
        epoch_events = [
            row[0]
            for row in db.execute(
                "SELECT event_type FROM state_events "
                "WHERE event_type IN ('EPOCH_MANIFEST_CREATED','EPOCH_STARTED') "
                "ORDER BY sequence"
            ).fetchall()
        ]
    assert epoch_events == ["EPOCH_MANIFEST_CREATED", "EPOCH_STARTED"]
    # No raw account identity in the manifest (hash only).
    assert "DU" not in manifest_path.read_text(encoding="utf-8")
    # Strategy-free: no trading prescriptions.
    lowered = json.dumps(manifest).lower()
    for forbidden in (
        "must trade",
        "required strategy",
        "target sharpe",
        "quota",
        "minimum trades",
    ):
        assert forbidden not in lowered, forbidden


@pytest.mark.parametrize(
    "value",
    (None, True, 0, -1, 29, 601, float("inf"), float("nan")),
)
def test_launch_config_rejects_invalid_model_turn_timeout(
    tmp_path: Path, value
) -> None:
    ctx = passing_context(tmp_path)

    with pytest.raises(ValueError, match="MODEL_TURN_TIMEOUT_INVALID"):
        replace(ctx.config, model_turn_timeout_seconds=value)


def test_launch_uses_authority_bound_model_turn_timeout(tmp_path: Path) -> None:
    ctx = passing_context(tmp_path)
    install_fake_lock(ctx)
    ctx.config = replace(ctx.config, model_turn_timeout_seconds=321)
    captured = {}

    class Service:
        def run_forever(self):
            return None

    def service_factory(*args, **kwargs):
        captured.update(kwargs)
        return Service()

    ctx.dependencies.service_factory = service_factory

    assert run_day1_launch(ctx.config, ctx.dependencies) == (
        "AUTONOMOUS_PAPER_EXPERIMENT_STOPPED"
    )
    assert captured["timeout_seconds"] == 321
    manifest_path = (
        tmp_path
        / "state"
        / "ibkr_paper_30d"
        / "reports"
        / "autonomy_epoch_manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["model_turn_timeout_seconds"] == 321


def test_service_construction_failure_never_emits_epoch_started(tmp_path: Path) -> None:
    ctx = passing_context(tmp_path)
    install_fake_lock(ctx)
    ctx.dependencies.service_factory.side_effect = RuntimeError("construction failed")

    with pytest.raises(RuntimeError, match="construction failed"):
        run_day1_launch(ctx.config, ctx.dependencies)

    with Database.open(ctx.config.db_path) as db:
        epoch_events = [
            row[0]
            for row in db.execute(
                "SELECT event_type FROM state_events "
                "WHERE event_type IN ('EPOCH_MANIFEST_CREATED','EPOCH_STARTED') "
                "ORDER BY sequence"
            ).fetchall()
        ]
    assert epoch_events == ["EPOCH_MANIFEST_CREATED"]


def test_service_prerequisite_failure_is_sanitized_into_launch_reason_codes(
    tmp_path: Path,
) -> None:
    ctx = passing_context(tmp_path)
    install_fake_lock(ctx)
    failure = AutonomousServiceError(
        "secret-account-id DU123456",
        reason_codes=(
            "BROKER_TIME_UNAVAILABLE_FRESH",
            "EXPERIMENT_NOT_STARTED_FRESH",
            "EXPERIMENT_EXPIRED_FRESH",
        ),
    )
    ctx.dependencies.service_factory.side_effect = failure

    with pytest.raises(LaunchError) as caught:
        run_day1_launch(ctx.config, ctx.dependencies)

    assert caught.value.code == "AUTONOMOUS_SERVICE_CONSTRUCTION_BLOCK"
    assert caught.value.details == {"service_reason_codes": list(failure.reason_codes)}
    assert "DU123456" not in json.dumps(caught.value.details)
    with Database.open(ctx.config.db_path) as db:
        epoch_events = [
            row[0]
            for row in db.execute(
                "SELECT event_type FROM state_events "
                "WHERE event_type IN ('EPOCH_MANIFEST_CREATED','EPOCH_STARTED') "
                "ORDER BY sequence"
            ).fetchall()
        ]
    assert epoch_events == ["EPOCH_MANIFEST_CREATED"]
