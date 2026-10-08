from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence
from uuid import uuid4

from .autonomous_research import CodexAutonomousCLIProvider
from .autonomous_runtime import build_request
from .autonomous_service import AutonomousExperimentService, AutonomousServiceError
from .autonomy_bootstrap import AutonomyBootstrapBuilder
from .autonomy_toolbox import AutonomyToolbox
from .autonomy_workspace import AutonomyWorkspace
from .canonical import canonical_bytes, sha256_json
from .continuity_schema import verify_continuity_schema_v3
from .continuity_store import ContinuityStore, ContinuityStoreError
from .provider_lifecycle import BrokerTimeEvidence, ProviderLifecycleRecorder
from .epoch_manifest import (
    EpochManifestInputs,
    build_epoch_manifest,
    build_kernel_manifest,
    epoch_manifest_hash,
    verify_kernel_manifest,
)
from .execution_lock import ExecutionLock, LockIntegrityError, LockOwner
from .experiment_control import (
    ExperimentClock,
    ExperimentClockStore,
    ExperimentControlError,
    KillSwitchStore,
    OwnerAuthorizationStore,
)
from .experiment_ledger import AutonomousExperimentLedger
from .experiment_epoch import ExperimentEpochStore
from .ibkr_research_tools import IBKRResearchToolbox
from .market_data import DecisionClass
from .market_policy import load_verified_policy
from .owner_authorization import (
    OwnerAuthorizationError,
    validate_owner_authorization,
)
from .persistence import Database
from .prerequisite_tools import validate_launch_attempt_binding
from .repositories import EventRepository
from .research_sandbox import WSLResearchSandbox
from .risk import CapitalBoundaryRiskPolicy
from .runtime_integrity import RuntimeAuditorGate, RuntimeMarketDataGate
from .runtime_provenance import (
    RuntimeProvenanceError,
    build_approved_runtime_material,
    verify_runtime_provenance,
)
from .readonly_acceptance import is_safe_account_summary_partial
from .trader_invocation import TraderInputBundle
from .successor_authorization import (
    SuccessorAuthorizationError,
    validate_successor_authorization,
    validate_successor_authorization_record,
)
from .successor_clock import (
    BrokerTimeObservation,
    SuccessorClockError,
    clock_for_epoch,
)
from .successor_epoch import (
    BrokerTransitionEvidence,
    SuccessorEpochError,
    SuccessorEpochStore,
    SuccessorTransitionResult,
    commit_successor_transition,
    current_epoch_definition,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REASON_CODE_RE = re.compile(r"^[A-Z0-9_.:-]{1,100}$")
_MARKET_ERROR_CODE_RE = re.compile(r"^[A-Za-z]+:[A-Z0-9_]{1,100}$")
_QUERY_KEYS = frozenset(
    {
        "account_summary",
        "account_values",
        "current_time",
        "executions",
        "managed_accounts",
        "open_orders",
        "positions",
    }
)
_FORBIDDEN_EVIDENCE_KEYS = frozenset(
    {"account", "account_id", "credential", "token", "prompt"}
)


@dataclass(frozen=True)
class Day1LaunchConfig:
    repo_root: Path
    db_path: Path
    launch_root: Path
    expected_identity_path: Path
    identity_receipt_path: Path
    auditor_receipt_path: Path
    market_policy_path: Path
    market_validation_path: Path
    owner_authorization_path: Path
    model_attestation_exception_path: Path
    launch_attempt_binding_path: Path
    launch_attempt_id: str
    approved_head: str | None = None
    target_successor_epoch_id: str | None = None
    target_successor_definition_sha256: str | None = None
    epoch_manifest_path: Path | None = None
    scheduled_start_utc: datetime = datetime(2026, 9, 23, 13, 30, tzinfo=timezone.utc)
    duration_days: int = 30
    initial_allocation: Decimal = Decimal("500")
    paper_host: str = "127.0.0.1"
    paper_port: int = 4002
    model: str = "gpt-5.6-sol"
    reasoning_effort: str = "max"
    model_turn_timeout_seconds: int = 600

    def __post_init__(self) -> None:
        if self.approved_head is not None and not re.fullmatch(
            r"[0-9a-f]{40}", self.approved_head
        ):
            raise ValueError("APPROVED_HEAD_INVALID")
        value = self.model_turn_timeout_seconds
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 30 <= value <= 600
        ):
            raise ValueError("MODEL_TURN_TIMEOUT_INVALID")


@dataclass
class LaunchDependencies:
    now_utc: Callable[[], datetime]
    auditor_gate_factory: Callable[[Day1LaunchConfig], RuntimeAuditorGate]
    market_gate_factory: Callable[[Day1LaunchConfig, str], RuntimeMarketDataGate]
    database_factory: Callable[[Path], Database]
    lock_factory: Callable[[Database], ExecutionLock]
    service_factory: Callable[..., AutonomousExperimentService]
    lock_owner_factory: Callable[[datetime], LockOwner]
    current_sid: Callable[[], str]
    research_toolbox_factory: (
        Callable[[AutonomyWorkspace, "LaunchPreflight"], Any] | None
    ) = None
    runtime_provenance_validator: (
        Callable[[Day1LaunchConfig], dict[str, Any]] | None
    ) = None
    successor_broker_evidence_collector: (
        Callable[[Day1LaunchConfig, "LaunchPreflight"], BrokerTransitionEvidence] | None
    ) = None
    continuity_schema_verifier: Callable[[Database], dict[str, Any]] | None = None
    provider_abandonment_recoverer: Callable[..., dict[str, Any]] | None = None
    pending_binding_reconciler: Callable[..., dict[str, Any]] | None = None
    continuity_uncertainty_reader: Callable[[Database], Sequence[str]] | None = None
    broker_write_coordinator_factory: Callable[[], Any] | None = None
    model_executor_factory: Callable[..., Any] | None = None
    critical_alert_reporter_factory: Callable[..., Any] | None = None
    authoritative_writer_factory: Callable[..., Any] | None = None
    continuity_watchdog_factory: Callable[..., Any] | None = None
    continuity_store_factory: Callable[[Database], Any] | None = None


class LaunchError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        details: dict[str, object] | None = None,
    ):
        self.code = code
        self.details = details or {}
        super().__init__(code)


@dataclass(frozen=True)
class LaunchPreflight:
    launch_attempt_id: str
    authorization_event_id: str
    expected_account_hash: str
    identity_receipt_sha256: str
    auditor_receipt_sha256: str
    market_policy_sha256: str
    market_validation_sha256: str
    owner_authorization_receipt_sha256: str
    model_attestation_exception_sha256: str
    actual_start_utc: datetime
    owner_sid: str
    owner_authorization_receipt: dict[str, Any]
    target_successor_epoch_id: str | None = None
    target_successor_definition_sha256: str | None = None


@dataclass(frozen=True)
class LaunchControls:
    clock_event_sha256: str
    authorization_event_id: str
    kill_switch_state: str
    clock: ExperimentClock | None = None
    resume_started_epoch: bool = False


def _read_json(path: Path, code: str) -> tuple[bytes, dict[str, object]]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise LaunchError(code) from exc
    if not isinstance(payload, dict):
        raise LaunchError(code)
    return raw, payload


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _validate_expected_identity(config: Day1LaunchConfig) -> str:
    _, payload = _read_json(
        config.expected_identity_path, "EXPECTED_ACCOUNT_IDENTITY_INVALID"
    )
    account_hash = payload.get("account_sha256")
    if (
        payload.get("schema") != "EXPECTED_PAPER_ACCOUNT_IDENTITY_V1"
        or payload.get("gateway_mode") != "PAPER"
        or payload.get("host") != config.paper_host
        or payload.get("port") != config.paper_port
        or payload.get("managed_account_count") != 1
        or not isinstance(account_hash, str)
        or _SHA256_RE.fullmatch(account_hash) is None
    ):
        raise LaunchError("EXPECTED_ACCOUNT_IDENTITY_INVALID")
    return account_hash


def _validate_model_attestation_exception(
    config: Day1LaunchConfig,
    *,
    actual_start: datetime,
    expected_account_hash: str,
    owner_authorization_receipt_sha256: str,
) -> str:
    raw, payload = _read_json(
        config.model_attestation_exception_path,
        "MODEL_ATTESTATION_EXCEPTION_INVALID",
    )
    legacy_keys = {
        "schema",
        "authorization_state",
        "scope",
        "requested_model",
        "reasoning_effort",
        "actual_model_attestation_available",
        "requested_model_pin_required",
        "model_mismatch_forbidden",
        "paper_only",
        "live_allowed",
        "paper_host",
        "paper_port",
        "expected_account_identity_hash",
        "owner_authorization_receipt_sha256",
        "start_utc",
        "end_utc",
        "artifact_sha256",
    }
    successor_mode = config.target_successor_epoch_id is not None
    expected_keys = (
        legacy_keys
        if not successor_mode
        else (
            legacy_keys - {"start_utc", "end_utc"}
            | {
                "target_successor_epoch_id",
                "target_successor_definition_sha256",
                "clock_start_policy",
            }
        )
    )
    unsigned = dict(payload)
    artifact_sha256 = unsigned.pop("artifact_sha256", None)
    expected_start = config.scheduled_start_utc.isoformat().replace("+00:00", "Z")
    expected_end = (
        (config.scheduled_start_utc + timedelta(days=config.duration_days))
        .isoformat()
        .replace("+00:00", "Z")
    )
    if (
        set(payload) != expected_keys
        or payload.get("schema")
        != (
            "MODEL_ATTESTATION_OWNER_EXCEPTION_V2"
            if successor_mode
            else "MODEL_ATTESTATION_OWNER_EXCEPTION_V1"
        )
        or payload.get("authorization_state") != "AUTHORIZED"
        or payload.get("scope") != "MONTH1_PAPER_ONLY"
        or payload.get("requested_model") != config.model
        or payload.get("reasoning_effort") != config.reasoning_effort
        or payload.get("actual_model_attestation_available") is not False
        or payload.get("requested_model_pin_required") is not True
        or payload.get("model_mismatch_forbidden") is not True
        or payload.get("paper_only") is not True
        or payload.get("live_allowed") is not False
        or payload.get("paper_host") != config.paper_host
        or payload.get("paper_port") != config.paper_port
        or payload.get("expected_account_identity_hash") != expected_account_hash
        or payload.get("owner_authorization_receipt_sha256")
        != owner_authorization_receipt_sha256
        or (
            not successor_mode
            and (
                payload.get("start_utc") != expected_start
                or payload.get("end_utc") != expected_end
            )
        )
        or (
            successor_mode
            and (
                payload.get("target_successor_epoch_id")
                != config.target_successor_epoch_id
                or payload.get("target_successor_definition_sha256")
                != config.target_successor_definition_sha256
                or payload.get("clock_start_policy")
                != "BROKER_SERVER_TIME_AT_AUTHORIZED_LAUNCH"
            )
        )
        or not isinstance(artifact_sha256, str)
        or _SHA256_RE.fullmatch(artifact_sha256) is None
        or artifact_sha256 != sha256_json(unsigned)
        or (
            not successor_mode
            and actual_start
            >= config.scheduled_start_utc + timedelta(days=config.duration_days)
        )
    ):
        raise LaunchError("MODEL_ATTESTATION_EXCEPTION_INVALID")
    return _sha256(raw)


def _validate_identity_receipt(
    payload: dict[str, object], config: Day1LaunchConfig, expected_hash: str
) -> None:
    if payload.get("schema") != "REAL_IBKR_READ_ONLY_RECONCILIATION_V1":
        raise LaunchError("READONLY_RECEIPT_INVALID")
    if payload.get("gateway_mode") == "LIVE" or payload.get("port") == 4001:
        raise LaunchError("LIVE_ROUTE_FORBIDDEN")
    if (
        payload.get("host") != config.paper_host
        or payload.get("port") != config.paper_port
    ):
        raise LaunchError("PAPER_ROUTE_REQUIRED")
    if payload.get("gateway_mode") != "PAPER":
        raise LaunchError("PAPER_ROUTE_REQUIRED")
    completeness = payload.get("query_completeness")
    safe_account_summary_partial = is_safe_account_summary_partial(payload)
    if payload.get("status") != "PASS" and not safe_account_summary_partial:
        raise LaunchError("READONLY_RECONCILIATION_REQUIRED")
    if payload.get("managed_account_count") != 1:
        raise LaunchError("MANAGED_ACCOUNT_COUNT_INVALID")
    if payload.get("paper_account_namespace_ok") is not True:
        raise LaunchError("PAPER_ACCOUNT_NAMESPACE_INVALID")
    if payload.get("heartbeat_ok") is not True:
        raise LaunchError("BROKER_HEARTBEAT_REQUIRED")
    if payload.get("paper_account_identity_gate") != "PASS":
        raise LaunchError("PAPER_IDENTITY_REQUIRED")
    if payload.get("real_ibkr_read_only_identity_gate") != "PASS":
        raise LaunchError("READONLY_IDENTITY_REQUIRED")
    if (
        payload.get("broker_reconciliation_gate") != "PASS"
        and not safe_account_summary_partial
    ):
        raise LaunchError("BROKER_RECONCILIATION_REQUIRED")
    if payload.get("expected_account_identity_bound") is not True:
        raise LaunchError("EXPECTED_ACCOUNT_IDENTITY_REQUIRED")
    if payload.get("expected_account_identity_hash") != expected_hash:
        raise LaunchError("EXPECTED_ACCOUNT_IDENTITY_MISMATCH")
    if payload.get("raw_account_identity_persisted") is not False:
        raise LaunchError("RAW_ACCOUNT_IDENTITY_FORBIDDEN")
    if payload.get("real_order_writes_attempted") != 0:
        raise LaunchError("BROKER_WRITE_DETECTED")
    if (
        not isinstance(completeness, dict)
        or not _QUERY_KEYS.issubset(completeness)
        or any(value is not True for value in completeness.values())
    ):
        raise LaunchError("READONLY_QUERY_INCOMPLETE")


def _validate_market_artifacts(config: Day1LaunchConfig) -> tuple[str, str]:
    try:
        load_verified_policy(config.market_policy_path)
        policy_raw = config.market_policy_path.read_bytes()
    except (OSError, ValueError) as exc:
        raise LaunchError("MARKET_POLICY_INVALID_OR_MISSING") from exc

    validation_raw, validation = _read_json(
        config.market_validation_path, "MARKET_VALIDATION_INVALID"
    )
    expected = {
        "schema": "REAL_MARKET_DATA_VALIDATION_V1",
        "status": "PASS",
        "market_data_gate": "PASS",
        "market_data_policy_frozen": True,
        "real_order_writes_attempted": 0,
    }
    if any(validation.get(key) != value for key, value in expected.items()):
        raise LaunchError("MARKET_VALIDATION_INVALID")
    broker_calls_made = validation.get("broker_calls_made")
    if (
        isinstance(broker_calls_made, bool)
        or not isinstance(broker_calls_made, int)
        or broker_calls_made <= 0
    ):
        raise LaunchError("MARKET_VALIDATION_INVALID")
    return _sha256(policy_raw), _sha256(validation_raw)


def evaluate_launch_preflight(
    config: Day1LaunchConfig, dependencies: LaunchDependencies
) -> LaunchPreflight:
    actual_start = dependencies.now_utc()
    if actual_start.tzinfo is None or actual_start.utcoffset() is None:
        raise LaunchError("SYSTEM_TIME_INVALID")
    if actual_start < config.scheduled_start_utc:
        raise LaunchError("EXPERIMENT_NOT_STARTED")

    successor_values = (
        config.target_successor_epoch_id,
        config.target_successor_definition_sha256,
    )
    if any(value is not None for value in successor_values) and not all(
        isinstance(value, str) and value for value in successor_values
    ):
        raise LaunchError("SUCCESSOR_TARGET_BINDING_INCOMPLETE")
    successor_mode = config.target_successor_epoch_id is not None
    owner_sid = dependencies.current_sid()
    try:
        if successor_mode:
            authorization = validate_successor_authorization(
                db_path=config.db_path,
                receipt_path=config.owner_authorization_path,
                epoch_id=str(config.target_successor_epoch_id),
                definition_sha256=str(config.target_successor_definition_sha256),
                expected_actor_sid=owner_sid,
            )
        else:
            authorization = validate_owner_authorization(
                db_path=config.db_path,
                receipt_path=config.owner_authorization_path,
                expected_actor_sid=owner_sid,
            )
    except (OwnerAuthorizationError, SuccessorAuthorizationError) as exc:
        raise LaunchError(str(exc)) from exc

    try:
        binding = validate_launch_attempt_binding(
            config.launch_attempt_id,
            config.identity_receipt_path,
            config.auditor_receipt_path,
            config.launch_attempt_binding_path,
            target_successor_epoch_id=config.target_successor_epoch_id,
            target_successor_definition_sha256=(
                config.target_successor_definition_sha256
            ),
        )
    except ValueError as exc:
        raise LaunchError(str(exc)) from exc

    expected_hash = _validate_expected_identity(config)
    try:
        owner_authorization_raw = config.owner_authorization_path.read_bytes()
    except OSError as exc:
        raise LaunchError("MODEL_ATTESTATION_EXCEPTION_INVALID") from exc
    model_exception_hash = _validate_model_attestation_exception(
        config,
        actual_start=actual_start,
        expected_account_hash=expected_hash,
        owner_authorization_receipt_sha256=_sha256(owner_authorization_raw),
    )
    identity_raw, identity = _read_json(
        config.identity_receipt_path, "READONLY_RECEIPT_INVALID"
    )
    _validate_identity_receipt(identity, config, expected_hash)
    identity_hash = _sha256(identity_raw)
    if binding.get("expected_account_identity_hash") != expected_hash:
        raise LaunchError("LAUNCH_ATTEMPT_ACCOUNT_HASH_MISMATCH")

    auditor_hash = _sha256(config.auditor_receipt_path.read_bytes())
    auditor_result = dependencies.auditor_gate_factory(config).evaluate()
    try:
        identity_after = config.identity_receipt_path.read_bytes()
    except OSError as exc:
        raise LaunchError("IDENTITY_RECEIPT_CHANGED_DURING_PREFLIGHT") from exc
    if identity_after != identity_raw:
        raise LaunchError("IDENTITY_RECEIPT_CHANGED_DURING_PREFLIGHT")
    if (
        not isinstance(auditor_result, dict)
        or auditor_result.get("gate_status") != "PASS"
    ):
        raise LaunchError("AUDITOR_GATE_BLOCKED")
    if auditor_result.get("receipt_sha256") != auditor_hash:
        raise LaunchError("AUDITOR_RECEIPT_BINDING_INVALID")

    policy_hash, market_validation_hash = _validate_market_artifacts(config)
    market_result = dependencies.market_gate_factory(config, expected_hash).evaluate(
        DecisionClass.NEW_TRADE
    )
    if (
        not isinstance(market_result, dict)
        or market_result.get("gate_status") != "PASS"
    ):
        raw_reasons = (
            market_result.get("reason_codes", [])
            if isinstance(market_result, dict)
            else []
        )
        market_reasons = [
            reason
            for reason in raw_reasons
            if isinstance(reason, str) and _REASON_CODE_RE.fullmatch(reason)
        ][:10]
        details: dict[str, object] = {"market_data_reason_codes": market_reasons}
        market_error = (
            market_result.get("error") if isinstance(market_result, dict) else None
        )
        if isinstance(market_error, str) and _MARKET_ERROR_CODE_RE.fullmatch(
            market_error
        ):
            details["market_data_error_code"] = market_error
        raise LaunchError(
            "MARKET_DATA_GATE_BLOCKED",
            details=details,
        )

    authorization_event_id = authorization.get("authorization_event_id")
    if not isinstance(authorization_event_id, str) or not authorization_event_id:
        raise LaunchError("OWNER_AUTHORIZATION_INVALID")
    return LaunchPreflight(
        launch_attempt_id=config.launch_attempt_id,
        authorization_event_id=authorization_event_id,
        expected_account_hash=expected_hash,
        identity_receipt_sha256=identity_hash,
        auditor_receipt_sha256=auditor_hash,
        market_policy_sha256=policy_hash,
        market_validation_sha256=market_validation_hash,
        owner_authorization_receipt_sha256=_sha256(owner_authorization_raw),
        model_attestation_exception_sha256=model_exception_hash,
        actual_start_utc=actual_start,
        owner_sid=owner_sid,
        owner_authorization_receipt=dict(authorization),
        target_successor_epoch_id=config.target_successor_epoch_id,
        target_successor_definition_sha256=(config.target_successor_definition_sha256),
    )


def _contains_forbidden_key(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).lower() in _FORBIDDEN_EVIDENCE_KEYS
            or _contains_forbidden_key(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_launch_evidence(
    config: Day1LaunchConfig, event_type: str, payload: dict[str, object]
) -> Path:
    if _contains_forbidden_key(payload):
        raise LaunchError("LAUNCH_EVIDENCE_FORBIDDEN_KEY")
    event = {
        "schema": (
            "DAY1_LAUNCH_EVENT_V2"
            if config.target_successor_epoch_id is not None
            else "DAY1_LAUNCH_EVENT_V1"
        ),
        "event_type": event_type,
        "launch_attempt_id": config.launch_attempt_id,
        "created_at_utc": datetime.now(timezone.utc),
        "payload": payload,
    }
    if config.target_successor_epoch_id is not None:
        event.update(
            {
                "target_successor_epoch_id": config.target_successor_epoch_id,
                "target_successor_definition_sha256": (
                    config.target_successor_definition_sha256
                ),
            }
        )
    envelope = {
        "schema": "DAY1_LAUNCH_EVIDENCE_V1",
        "event": event,
        "event_sha256": sha256_json(event),
    }
    encoded = canonical_bytes(envelope)
    latest = config.launch_root / "latest.json"
    _atomic_write(latest, encoded)
    history = config.launch_root / "launch_events.jsonl"
    with history.open("ab") as handle:
        handle.write(encoded + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    return latest


def assert_integrity_check_ok(db: Database) -> None:
    try:
        rows = [str(row[0]) for row in db.execute("PRAGMA integrity_check").fetchall()]
    except Exception as exc:
        raise LaunchError("DATABASE_INTEGRITY_CHECK_FAILED") from exc
    if rows != ["ok"]:
        raise LaunchError("DATABASE_INTEGRITY_CHECK_FAILED")


def _latest_authorization_event_id(db: Database) -> str:
    row = db.execute(
        "SELECT event_id FROM experiment_authorization_events "
        "ORDER BY sequence DESC LIMIT 1"
    ).fetchone()
    if row is None:
        raise LaunchError("OWNER_AUTHORIZATION_MISSING")
    return str(row[0])


def validate_launch_controls(
    db: Database,
    config: Day1LaunchConfig,
    *,
    preflight: LaunchPreflight | None = None,
) -> LaunchControls:
    assert_integrity_check_ok(db)
    schema_rows = db.execute(
        "SELECT version FROM schema_versions ORDER BY version"
    ).fetchall()
    successor_mode = config.target_successor_epoch_id is not None
    expected_schema_versions = [1, 2, 3]
    if [int(row[0]) for row in schema_rows] != expected_schema_versions:
        raise LaunchError("DATABASE_SCHEMA_INVALID")
    clock: ExperimentClock | None = None
    if successor_mode:
        failed = db.execute(
            "SELECT 1 FROM state_events WHERE event_type='EPOCH_PRE_START_FAILED' "
            "AND json_extract(payload_json,'$.epoch_id')=? LIMIT 1",
            (config.target_successor_epoch_id,),
        ).fetchone()
        if failed is not None:
            raise LaunchError("FAILED_EPOCH_REQUIRES_EXPLICIT_SUCCESSOR")
        try:
            target_epoch_id = str(config.target_successor_epoch_id)
            target_definition_sha256 = str(
                config.target_successor_definition_sha256
            )
            successor_store = SuccessorEpochStore(db)
            definition = successor_store.definition(target_epoch_id)
            if definition.get("definition_sha256") != target_definition_sha256:
                raise SuccessorEpochError("SUCCESSOR_DEFINITION_HASH_MISMATCH")
            current = current_epoch_definition(db)
            resume_started_epoch = (
                current is not None and current.epoch_id == target_epoch_id
            )
            if resume_started_epoch:
                if current.definition_sha256 != target_definition_sha256:
                    raise SuccessorEpochError("SUCCESSOR_DEFINITION_HASH_MISMATCH")
                clock = clock_for_epoch(db, target_epoch_id)
                manifest_rows = db.execute(
                    "SELECT payload_json FROM state_events "
                    "WHERE event_type='EPOCH_MANIFEST_CREATED' "
                    "AND json_extract(payload_json,'$.epoch_id')=? ORDER BY sequence",
                    (target_epoch_id,),
                ).fetchall()
                started_rows = db.execute(
                    "SELECT payload_json FROM state_events "
                    "WHERE event_type='EPOCH_STARTED' "
                    "AND json_extract(payload_json,'$.epoch_id')=? ORDER BY sequence",
                    (target_epoch_id,),
                ).fetchall()
                if len(manifest_rows) != 1 or len(started_rows) != 1:
                    raise SuccessorEpochError(
                        "STARTED_SUCCESSOR_RESUME_EVIDENCE_INVALID"
                    )
                manifest_event = json.loads(str(manifest_rows[0][0]))
                started_event = json.loads(str(started_rows[0][0]))
                expected_bindings = {
                    "epoch_id": target_epoch_id,
                    "definition_sha256": target_definition_sha256,
                    "clock_event_sha256": clock.event_sha256,
                }
                if (
                    manifest_event.get("schema") != "EPOCH_MANIFEST_CREATED_V1"
                    or started_event.get("schema") != "EPOCH_STARTED_V1"
                    or any(
                        manifest_event.get(key) != value
                        or started_event.get(key) != value
                        for key, value in expected_bindings.items()
                    )
                    or started_event.get("epoch_manifest_sha256")
                    != manifest_event.get("epoch_manifest_sha256")
                    or started_event.get("service_constructed") is not True
                    or started_event.get("initial_safety_gate") != "PASS"
                ):
                    raise SuccessorEpochError(
                        "STARTED_SUCCESSOR_RESUME_EVIDENCE_INVALID"
                    )
            else:
                definition = successor_store.validate_transition_eligibility(
                    target_epoch_id,
                    target_definition_sha256,
                )
            _, receipt = _read_json(
                config.owner_authorization_path,
                "SUCCESSOR_AUTHORIZATION_RECEIPT_MISSING",
            )
            authorization = validate_successor_authorization_record(
                db=db,
                epoch_id=str(config.target_successor_epoch_id),
                definition_sha256=str(config.target_successor_definition_sha256),
                expected_actor_sid=str(receipt.get("actor_sid") or ""),
                receipt=receipt,
            )
        except (
            json.JSONDecodeError,
            SuccessorClockError,
            SuccessorEpochError,
            SuccessorAuthorizationError,
        ) as exc:
            raise LaunchError(str(exc)) from exc
        if (
            definition.get("duration_days") != config.duration_days
            or Decimal(str(definition.get("initial_allocation")))
            != config.initial_allocation
        ):
            raise LaunchError("SUCCESSOR_POLICY_MISMATCH")
        authorization_event_id = str(authorization["authorization_event_id"])
        clock_event_sha256 = "" if clock is None else clock.event_sha256
    else:
        try:
            clock = ExperimentClockStore(db).load()
        except ExperimentControlError as exc:
            raise LaunchError(str(exc)) from exc
        if clock is None:
            raise LaunchError("EXPERIMENT_CLOCK_MISSING")
        expected_end = config.scheduled_start_utc + timedelta(days=config.duration_days)
        if (
            clock.start_utc != config.scheduled_start_utc
            or clock.end_utc != expected_end
            or clock.duration_days != config.duration_days
            or clock.initial_allocation != config.initial_allocation
        ):
            raise LaunchError("EXPERIMENT_CLOCK_MISMATCH")
        if (
            OwnerAuthorizationStore(db).current(clock_event_sha256=clock.event_sha256)
            != "AUTHORIZED"
        ):
            raise LaunchError("OWNER_AUTHORIZATION_INVALID")
        authorization_event_id = _latest_authorization_event_id(db)
        clock_event_sha256 = clock.event_sha256
    try:
        kill_switch_state = KillSwitchStore(db).validate_history(
            expected_owner_sid=("" if preflight is None else preflight.owner_sid),
            expected_account_identity_sha256=(
                "" if preflight is None else preflight.expected_account_hash
            ),
            expected_approved_head=(config.approved_head or ""),
            expected_authorization_event_id=authorization_event_id,
            expected_clock_event_sha256=clock_event_sha256,
        )
    except ExperimentControlError as exc:
        raise LaunchError(str(exc)) from exc
    ledger = AutonomousExperimentLedger(
        db, allocation=config.initial_allocation
    ).project()
    if not ledger.valid:
        raise LaunchError("EXPERIMENT_LEDGER_INVALID")
    return LaunchControls(
        clock_event_sha256=clock_event_sha256,
        authorization_event_id=authorization_event_id,
        kill_switch_state=kill_switch_state,
        clock=clock,
        resume_started_epoch=(successor_mode and resume_started_epoch),
    )


def _consume_launch_attempt(
    db: Database,
    config: Day1LaunchConfig,
    preflight: LaunchPreflight,
    controls: LaunchControls,
) -> None:
    with db.transaction():
        rows = db.execute(
            "SELECT payload_json FROM state_events "
            "WHERE event_type='DAY1_LAUNCH_ATTEMPT_ACCEPTED'"
        ).fetchall()
        for row in rows:
            try:
                prior = json.loads(str(row[0]))
            except json.JSONDecodeError as exc:
                raise LaunchError("LAUNCH_ATTEMPT_HISTORY_INVALID") from exc
            if prior.get("launch_attempt_id") == config.launch_attempt_id:
                raise LaunchError("LAUNCH_ATTEMPT_REUSED")

        payload = {
            "schema": (
                "DAY1_LAUNCH_ATTEMPT_ACCEPTED_V2"
                if config.target_successor_epoch_id is not None
                else "DAY1_LAUNCH_ATTEMPT_ACCEPTED_V1"
            ),
            "launch_attempt_id": config.launch_attempt_id,
            "authorization_event_id": controls.authorization_event_id,
            "clock_event_sha256": controls.clock_event_sha256,
            "identity_receipt_sha256": preflight.identity_receipt_sha256,
            "auditor_receipt_sha256": preflight.auditor_receipt_sha256,
            "market_policy_sha256": preflight.market_policy_sha256,
            "market_validation_sha256": preflight.market_validation_sha256,
            "created_at_utc": preflight.actual_start_utc,
        }
        if config.target_successor_epoch_id is not None:
            payload.update(
                {
                    "target_successor_epoch_id": config.target_successor_epoch_id,
                    "target_successor_definition_sha256": (
                        config.target_successor_definition_sha256
                    ),
                }
            )
        EventRepository(db).append("DAY1_LAUNCH_ATTEMPT_ACCEPTED", payload)


def _restore_environment(name: str, previous: str | None) -> None:
    if previous is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = previous


@contextmanager
def paper_arm_environment(expected_account_hash: str) -> Iterator[None]:
    previous_arm = os.environ.get("IBKR_AUTONOMOUS_PAPER_ARMED")
    previous_hash = os.environ.get("IBKR_PAPER_ACCOUNT_SHA256")
    os.environ["IBKR_AUTONOMOUS_PAPER_ARMED"] = "true"
    os.environ["IBKR_PAPER_ACCOUNT_SHA256"] = expected_account_hash
    try:
        yield
    finally:
        _restore_environment("IBKR_AUTONOMOUS_PAPER_ARMED", previous_arm)
        _restore_environment("IBKR_PAPER_ACCOUNT_SHA256", previous_hash)


class _LockHeartbeat:
    def __init__(
        self,
        *,
        config: Day1LaunchConfig,
        dependencies: LaunchDependencies,
        receipt: Any,
        service: Any,
        interval_seconds: float = 30.0,
    ) -> None:
        self.config = config
        self.dependencies = dependencies
        self.receipt = receipt
        self.service = service
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.failure_code: str | None = None
        self.thread = threading.Thread(
            target=self._run,
            name="ibkr-paper-launch-lock-heartbeat",
            daemon=True,
        )

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=max(self.interval_seconds + 1.0, 2.0))

    def _stop_service(self, reason: str) -> None:
        self.failure_code = reason
        try:
            write_launch_evidence(
                self.config,
                "OWNER_ACTION_REQUIRED",
                {"reason_codes": [reason]},
            )
        finally:
            stop = getattr(self.service, "stop", None)
            if callable(stop):
                stop()

    def _run(self) -> None:
        while not self.stop_event.wait(self.interval_seconds):
            try:
                with self.dependencies.database_factory(self.config.db_path) as db:
                    result = self.dependencies.lock_factory(db).heartbeat(self.receipt)
                if result.accepted is not True:
                    self._stop_service("EXECUTION_LOCK_HEARTBEAT_REJECTED")
                    return
            except Exception:
                self._stop_service("EXECUTION_LOCK_HEARTBEAT_FAILED")
                return


@dataclass(frozen=True)
class PreparedEpochLaunch:
    manifest: dict[str, Any]
    provider: CodexAutonomousCLIProvider
    toolbox: AutonomyToolbox
    session_evidence_reader: Callable[[], dict[str, Any] | None] | None = None


def _launch_bootstrap_bundle(
    db: Database,
    config: Day1LaunchConfig,
    preflight: LaunchPreflight,
    controls: LaunchControls,
) -> TraderInputBundle:
    clock = controls.clock or ExperimentClockStore(db).load()
    if clock is None:
        raise LaunchError("EXPERIMENT_CLOCK_MISSING")
    clock_snapshot = clock.snapshot(preflight.actual_start_utc)
    epoch = ExperimentEpochStore(db).projection(preflight.actual_start_utc)
    clock_snapshot.update(
        {
            "epoch_state": epoch["state"],
            "epoch_id": epoch["epoch_id"],
            "epoch_activation_required": epoch["activation_required"],
            "historical_cycle_count": epoch["historical_cycle_count"],
            "historical_ledger_event_count": epoch["historical_ledger_event_count"],
            "previous_history_classification": epoch["previous_history_classification"],
        }
    )
    if epoch["state"] == "ACTIVE":
        clock_snapshot.update(
            {
                key: value
                for key, value in epoch.items()
                if key not in {"state", "activation_required"}
            }
        )
    ledger = AutonomousExperimentLedger(
        db, allocation=config.initial_allocation
    ).project()
    return TraderInputBundle(
        decision_cycle_id=f"launch-bootstrap-{config.launch_attempt_id}",
        utc_timestamp=preflight.actual_start_utc.isoformat().replace("+00:00", "Z"),
        market_session_state="LAUNCH_PREFLIGHT",
        reconciliation_receipt={"status": "PASS"},
        experiment_subledger_snapshot={
            "allocation": str(ledger.allocation),
            "cash": str(ledger.cash),
            "market_value": str(ledger.market_value),
            "equity": str(ledger.equity),
            "high_water_mark": str(ledger.high_water_mark),
            "drawdown": str(ledger.drawdown),
            "fees": str(ledger.fees),
        },
        broker_account_snapshot={
            "paper_account": True,
            "declared_options_level": 4,
            "global_broker_balances_redacted": True,
        },
        positions_snapshot=[
            {
                "contract_id": position.contract_id,
                "symbol": position.symbol,
                "sec_type": position.sec_type,
                "quantity": str(position.quantity),
            }
            for position in ledger.positions
        ],
        open_orders_snapshot=[],
        risk_snapshot={"policy": "AGGRESSIVE_CAPITAL_BOUNDARY_V1"},
        kill_switch_state=controls.kill_switch_state,
        market_data_snapshot={
            "gate_status": "PASS",
            "policy_version": "MARKET_DATA_POLICY_V1",
        },
        candidate_screen_results=[],
        relevant_previous_immutable_decisions=[],
        process_policy_version="AUTONOMOUS_RESEARCH_V1",
        execution_realism_version="IBKR_PAPER_WHATIF_AND_PAPER_EXECUTION_V1",
        benchmark_state={},
        experiment_clock=clock_snapshot,
    )


def _write_epoch_manifest(
    db: Database,
    config: Day1LaunchConfig,
    preflight: LaunchPreflight,
    controls: LaunchControls,
    dependencies: LaunchDependencies,
    *,
    persist: bool = True,
) -> PreparedEpochLaunch:
    repo_root = Path(config.repo_root).resolve()
    code_root = Path(__file__).resolve().parents[1]
    kernel = build_kernel_manifest(code_root)
    try:
        stored_kernel = json.loads(
            (code_root / "IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise LaunchError("IMMUTABLE_KERNEL_MANIFEST_INVALID") from exc
    if verify_kernel_manifest(code_root, stored_kernel).get("verified") is not True:
        raise LaunchError("IMMUTABLE_KERNEL_MANIFEST_MISMATCH")

    workspace_root = repo_root / "state" / "ibkr_paper_30d" / "autonomy_workspace"
    workspace = AutonomyWorkspace(
        workspace_root,
        sandbox=WSLResearchSandbox(repo_root=code_root),
    )
    if dependencies.research_toolbox_factory is None:
        toolbox = AutonomyToolbox(
            IBKRResearchToolbox(
                declared_options_level=4,
                expected_account_hash=preflight.expected_account_hash,
            ),
            workspace,
        )
    else:
        toolbox = dependencies.research_toolbox_factory(workspace, preflight)
        if not isinstance(toolbox, AutonomyToolbox):
            raise LaunchError("RESEARCH_TOOLBOX_FACTORY_INVALID")
    provider = CodexAutonomousCLIProvider(
        owner_model_attestation_exception_sha256=(
            preflight.model_attestation_exception_sha256
        )
    )
    bundle = _launch_bootstrap_bundle(db, config, preflight, controls)
    bootstrap = AutonomyBootstrapBuilder(db).build(
        bundle=bundle,
        toolbox=toolbox,
        execute_paper=True,
    )
    provider.install_first_process_bootstrap(bootstrap)
    provider._autonomy_bootstrap_initialized = True
    tool_manifest = toolbox.manifest()
    request = build_request(
        bundle,
        model=config.model,
        reasoning_effort=config.reasoning_effort,
        experiment_id=str(
            bundle.experiment_clock.get("epoch_id") or "PRE_EPOCH_HISTORY"
        ),
        timeout_seconds=config.model_turn_timeout_seconds,
        trigger="DAY1_LAUNCH",
    )
    prompt = provider._prompt_payload(
        request,
        bundle,
        [],
        tool_manifest,
        first_process_bootstrap=bootstrap,
    )
    risk_policy = CapitalBoundaryRiskPolicy().model_dump(mode="json")
    manifest = build_epoch_manifest(
        EpochManifestInputs(
            epoch_id=str(bundle.experiment_clock.get("epoch_id") or "AUTONOMY_EPOCH_1"),
            definition_sha256=str(
                bundle.experiment_clock.get("definition_sha256") or "0" * 64
            ),
            clock_event_sha256=controls.clock_event_sha256,
            created_at_utc=preflight.actual_start_utc.isoformat().replace(
                "+00:00", "Z"
            ),
            git_commit_sha=_current_git_commit(repo_root),
            model=config.model,
            reasoning_effort=config.reasoning_effort,
            mandate_payload=prompt["mandate"],
            first_process_bootstrap=bootstrap,
            tool_manifest=tool_manifest,
            immutable_kernel_manifest_hash=kernel["kernel_manifest_sha256"],
            market_policy_sha256=preflight.market_policy_sha256,
            risk_policy_payload=risk_policy,
            receipt_sha256={
                "auditor": preflight.auditor_receipt_sha256,
                "launch_attempt_binding": hashlib.sha256(
                    config.launch_attempt_binding_path.read_bytes()
                ).hexdigest(),
                "market_validation": preflight.market_validation_sha256,
                "model_attestation_exception": (
                    preflight.model_attestation_exception_sha256
                ),
                "owner_authorization": (preflight.owner_authorization_receipt_sha256),
                "paper_identity": preflight.identity_receipt_sha256,
            },
            expected_paper_identity_hash=preflight.expected_account_hash,
            quantconnect_capability=str(
                bootstrap["quantconnect"].get("status") or "OPTIONAL_UNAVAILABLE"
            ),
            self_tooling_enabled=True,
            persistent_workspace_enabled=True,
            model_turn_timeout_seconds=config.model_turn_timeout_seconds,
        )
    )
    destination = config.epoch_manifest_path or (
        repo_root
        / "state"
        / "ibkr_paper_30d"
        / "reports"
        / "autonomy_epoch_manifest.json"
    )
    if persist:
        _atomic_write(destination, canonical_bytes(manifest))
        EventRepository(db).append(
            "EPOCH_MANIFEST_CREATED",
            {
                "schema": "EPOCH_MANIFEST_CREATED_V1",
                "epoch_id": manifest["epoch_id"],
                "definition_sha256": manifest["definition_sha256"],
                "clock_event_sha256": manifest["clock_event_sha256"],
                "launch_attempt_id": config.launch_attempt_id,
                "epoch_manifest_sha256": manifest["epoch_manifest_sha256"],
                "immutable_kernel_manifest_hash": manifest[
                    "immutable_kernel_manifest_hash"
                ],
                "created_at_utc": preflight.actual_start_utc,
            },
        )
    return PreparedEpochLaunch(
        manifest=manifest,
        provider=provider,
        toolbox=toolbox,
        session_evidence_reader=_session_evidence_reader(toolbox),
    )


def _session_evidence_reader(
    toolbox: AutonomyToolbox,
) -> Callable[[], dict[str, Any] | None] | None:
    """Bind the production session-evidence reader to the prepared toolbox.

    Reuses the existing read-only IBKR path inside the same service process;
    does not create a second IBKR client identity for orchestration. Returns
    None whenever the toolbox cannot supply evidence, which leaves the service
    on its prior fail-closed market-data behaviour (never fabricated CLOSED).

    The canonical reference symbols come from the market-policy authority so
    the research layer never hard-codes them.
    """
    from .market_policy import MarketPolicyFreezer

    base = getattr(toolbox, "base", None)
    getter = getattr(base, "session_evidence", None)
    if not callable(getter):
        return None
    symbols = tuple(sorted(MarketPolicyFreezer.REQUIRED_SYMBOLS))
    return lambda: getter(reference_symbols=symbols)


def _current_git_commit(repo_root: Path) -> str:
    import subprocess

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(repo_root),
            check=False,
        )
        return completed.stdout.strip() or "UNKNOWN"
    except (OSError, subprocess.SubprocessError):
        return "UNKNOWN"


def _verify_current_runtime_provenance(
    _config: Day1LaunchConfig,
) -> dict[str, Any]:
    code_root = Path(__file__).resolve().parents[1]
    approved_commit = _current_git_commit(code_root)
    if approved_commit == "UNKNOWN":
        raise RuntimeProvenanceError("approved runtime commit is unavailable")
    material = build_approved_runtime_material(code_root, approved_commit)
    return verify_runtime_provenance(code_root, material)


def _lock_receipt_is_current(db: Database, receipt: Any) -> bool:
    row = db.execute(
        "SELECT payload_json,payload_sha256 FROM experiment_state "
        "WHERE experiment_id='EXECUTION_LOCK_V1'"
    ).fetchone()
    if row is None:
        return False
    try:
        payload = json.loads(str(row[0]))
    except json.JSONDecodeError:
        return False
    return bool(
        isinstance(payload, dict)
        and sha256_json(payload) == str(row[1])
        and payload.get("state") == "ACTIVE"
        and payload.get("owner_id") == receipt.owner_id
        and int(payload.get("generation", -1)) == receipt.generation
        and receipt.acquired is True
    )


def _fresh_lock_receipt_is_current(db_path: Path, receipt: Any) -> bool:
    with Database.open(db_path) as db:
        return _lock_receipt_is_current(db, receipt)


def _collect_successor_broker_evidence(
    config: Day1LaunchConfig, preflight: LaunchPreflight
) -> BrokerTransitionEvidence:
    toolbox = IBKRResearchToolbox(
        host=config.paper_host,
        port=config.paper_port,
        declared_options_level=4,
        expected_account_hash=preflight.expected_account_hash,
    )
    broker = toolbox._connect()
    try:
        broker.accountSummary()
        server_time = broker.reqCurrentTime()
        positions = [
            position
            for position in broker.positions()
            if Decimal(str(getattr(position, "position", 0) or 0)) != 0
        ]
        open_orders = list(broker.reqAllOpenOrders())
        collected_at = datetime.now(timezone.utc)
        return BrokerTransitionEvidence(
            account_identity_sha256=preflight.expected_account_hash,
            collected_at_utc=collected_at,
            observation=BrokerTimeObservation(
                server_time_utc=server_time,
                observed_at_utc=collected_at,
                authenticated=bool(broker.isConnected()),
                paper_session=True,
            ),
            positions_count=len(positions),
            open_orders_count=len(open_orders),
            broker_write_count=0,
        )
    finally:
        broker.disconnect()


def _append_successor_pre_start_failure(
    db: Database,
    config: Day1LaunchConfig,
    transition: SuccessorTransitionResult,
    exc: Exception,
    manifest: dict[str, Any] | None,
) -> None:
    already_started = db.execute(
        "SELECT 1 FROM state_events WHERE event_type='EPOCH_STARTED' "
        "AND json_extract(payload_json,'$.epoch_id')=? LIMIT 1",
        (transition.epoch_id,),
    ).fetchone()
    if already_started is not None:
        return
    existing = db.execute(
        "SELECT 1 FROM state_events WHERE event_type='EPOCH_PRE_START_FAILED' "
        "AND json_extract(payload_json,'$.epoch_id')=? LIMIT 1",
        (transition.epoch_id,),
    ).fetchone()
    if existing is not None:
        return
    reason = (
        exc.code if isinstance(exc, LaunchError) else "UNEXPECTED_PRE_START_FAILURE"
    )
    if not _REASON_CODE_RE.fullmatch(reason):
        reason = "UNEXPECTED_PRE_START_FAILURE"
    EventRepository(db).append(
        "EPOCH_PRE_START_FAILED",
        {
            "schema": "EPOCH_PRE_START_FAILED_V1",
            "epoch_id": transition.epoch_id,
            "definition_sha256": transition.definition_sha256,
            "clock_event_sha256": transition.clock_event_sha256,
            "launch_attempt_id": config.launch_attempt_id,
            "epoch_manifest_sha256": (
                None if manifest is None else manifest.get("epoch_manifest_sha256")
            ),
            "reason_codes": [reason],
        },
    )


def run_day1_launch(config: Day1LaunchConfig, dependencies: LaunchDependencies) -> str:
    try:
        preflight = evaluate_launch_preflight(config, dependencies)
    except LaunchError as exc:
        if exc.code == "KILL_SWITCH_HISTORY_INVALID":
            raise LaunchError("KILL_SWITCH_TRIGGERED") from exc
        raise

    validator = dependencies.runtime_provenance_validator
    if validator is None:
        raise LaunchError("RUNTIME_SOURCE_PROVENANCE_GATE_UNAVAILABLE")
    try:
        provenance = validator(config)
    except RuntimeProvenanceError as exc:
        raise LaunchError("RUNTIME_SOURCE_PROVENANCE_BLOCK") from exc
    if not isinstance(provenance, dict) or provenance.get("gate_status") != "PASS":
        raise LaunchError("RUNTIME_SOURCE_PROVENANCE_BLOCK")

    with dependencies.database_factory(config.db_path) as db:
        lock = dependencies.lock_factory(db)
        owner = dependencies.lock_owner_factory(preflight.actual_start_utc)
        try:
            receipt = lock.acquire(owner)
        except LockIntegrityError as exc:
            raise LaunchError("EXECUTION_LOCK_OWNER_ACTION_REQUIRED") from exc
        if receipt.reason == "OS_MUTEX_HELD":
            status = "AUTONOMOUS_PAPER_EXPERIMENT_ALREADY_RUNNING"
            write_launch_evidence(config, status, {"reason_codes": []})
            return status
        if not receipt.acquired:
            raise LaunchError("EXECUTION_LOCK_OWNER_ACTION_REQUIRED")

        transition: SuccessorTransitionResult | None = None
        prepared: PreparedEpochLaunch | None = None
        try:
            verifier = dependencies.continuity_schema_verifier
            if verifier is None:
                raise LaunchError("CONTINUITY_SCHEMA_V3_REQUIRED")
            try:
                schema_result = verifier(db)
            except Exception as exc:
                raise LaunchError("CONTINUITY_SCHEMA_V3_REQUIRED") from exc
            if not isinstance(schema_result, dict) or schema_result.get(
                "status"
            ) != "PASS":
                raise LaunchError("CONTINUITY_SCHEMA_V3_REQUIRED")

            controls = validate_launch_controls(db, config, preflight=preflight)
            if controls.authorization_event_id != preflight.authorization_event_id:
                raise LaunchError("OWNER_AUTHORIZATION_CHANGED_DURING_PREFLIGHT")
            recover_provider = dependencies.provider_abandonment_recoverer
            if recover_provider is None:
                raise LaunchError("CONTINUITY_PROVIDER_RECOVERY_BLOCK")
            try:
                provider_recovery = recover_provider(
                    db, owner, config, preflight
                )
            except ContinuityStoreError as exc:
                raise LaunchError("CONTINUITY_AUTHORITY_CORRUPT") from exc
            except Exception as exc:
                raise LaunchError("CONTINUITY_PROVIDER_RECOVERY_BLOCK") from exc
            if not isinstance(provider_recovery, dict) or provider_recovery.get(
                "status"
            ) != "PASS":
                raise LaunchError("CONTINUITY_PROVIDER_RECOVERY_BLOCK")

            reconcile_bindings = dependencies.pending_binding_reconciler
            if reconcile_bindings is None:
                raise LaunchError("CONTINUITY_PENDING_BINDING_AMBIGUOUS")
            try:
                binding_recovery = reconcile_bindings(db, config, preflight)
            except ContinuityStoreError as exc:
                raise LaunchError("CONTINUITY_AUTHORITY_CORRUPT") from exc
            except Exception as exc:
                raise LaunchError("CONTINUITY_PENDING_BINDING_AMBIGUOUS") from exc
            if not isinstance(binding_recovery, dict) or binding_recovery.get(
                "status"
            ) != "PASS":
                raise LaunchError("CONTINUITY_PENDING_BINDING_AMBIGUOUS")

            read_uncertainty = dependencies.continuity_uncertainty_reader
            if read_uncertainty is None:
                raise LaunchError("CONTINUITY_UNCERTAINTY_UNRESOLVED")
            try:
                unresolved = tuple(read_uncertainty(db))
            except Exception as exc:
                raise LaunchError("CONTINUITY_AUTHORITY_CORRUPT") from exc
            if unresolved:
                raise LaunchError(
                    "CONTINUITY_UNCERTAINTY_UNRESOLVED",
                    details={"reason_codes": list(unresolved)},
                )
            if config.target_successor_epoch_id is not None:
                fresh_auditor = dependencies.auditor_gate_factory(config).evaluate()
                if (
                    not isinstance(fresh_auditor, dict)
                    or fresh_auditor.get("gate_status") != "PASS"
                    or fresh_auditor.get("receipt_sha256")
                    != preflight.auditor_receipt_sha256
                ):
                    raise LaunchError("AUDITOR_GATE_CHANGED_AFTER_LOCK")
                fresh_market = dependencies.market_gate_factory(
                    config, preflight.expected_account_hash
                ).evaluate(DecisionClass.NEW_TRADE)
                if (
                    not isinstance(fresh_market, dict)
                    or fresh_market.get("gate_status") != "PASS"
                ):
                    raise LaunchError("MARKET_DATA_GATE_CHANGED_AFTER_LOCK")
                if not controls.resume_started_epoch:
                    collector = dependencies.successor_broker_evidence_collector
                    if collector is None:
                        raise LaunchError(
                            "SUCCESSOR_BROKER_EVIDENCE_COLLECTOR_UNAVAILABLE"
                        )
                    try:
                        transition = commit_successor_transition(
                            db=db,
                            launch_attempt_id=config.launch_attempt_id,
                            target_successor_epoch_id=str(
                                config.target_successor_epoch_id
                            ),
                            target_successor_definition_sha256=str(
                                config.target_successor_definition_sha256
                            ),
                            expected_account_identity_sha256=(
                                preflight.expected_account_hash
                            ),
                            expected_owner_sid=preflight.owner_sid,
                            owner_authorization_receipt=(
                                preflight.owner_authorization_receipt
                            ),
                            execution_lock_verifier=lambda: _lock_receipt_is_current(
                                db, receipt
                            ),
                            broker_evidence_collector=lambda: collector(
                                config, preflight
                            ),
                            now_utc=dependencies.now_utc,
                        )
                    except SuccessorEpochError as exc:
                        raise LaunchError(str(exc)) from exc
                    exact_clock = clock_for_epoch(
                        db, str(config.target_successor_epoch_id)
                    )
                    if exact_clock.event_sha256 != transition.clock_event_sha256:
                        raise LaunchError("SUCCESSOR_CLOCK_BINDING_MISMATCH")
                    controls = replace(
                        controls,
                        clock_event_sha256=transition.clock_event_sha256,
                        clock=exact_clock,
                    )
            _consume_launch_attempt(db, config, preflight, controls)
            if controls.resume_started_epoch:
                prepared = _write_epoch_manifest(
                    db,
                    config,
                    preflight,
                    controls,
                    dependencies,
                    persist=False,
                )
            else:
                prepared = _write_epoch_manifest(
                    db, config, preflight, controls, dependencies
                )
            required_factories = (
                dependencies.broker_write_coordinator_factory,
                dependencies.model_executor_factory,
                dependencies.critical_alert_reporter_factory,
                dependencies.authoritative_writer_factory,
                dependencies.continuity_watchdog_factory,
                dependencies.continuity_store_factory,
            )
            if any(factory is None for factory in required_factories):
                raise LaunchError("CONTINUITY_RUNTIME_FACTORY_UNAVAILABLE")
            coordinator = dependencies.broker_write_coordinator_factory()
            model_executor = dependencies.model_executor_factory(
                coordinator=coordinator,
                db_path=config.db_path,
                config=config,
                preflight=preflight,
                production_validation_sha256=prepared.manifest[
                    "epoch_manifest_sha256"
                ],
            )
            critical_alert_reporter = (
                dependencies.critical_alert_reporter_factory(
                    db_path=config.db_path,
                    config=config,
                    preflight=preflight,
                )
            )
            continuity_store = dependencies.continuity_store_factory(db)
            provider_lifecycle = ProviderLifecycleRecorder(
                continuity_store,
                launch_attempt_id=config.launch_attempt_id,
                pid=owner.pid,
                boot_session_identity=owner.boot_session_id,
                expected_account_identity_sha256=preflight.expected_account_hash,
            )
            writer = dependencies.authoritative_writer_factory(
                coordinator=coordinator,
                db_path=config.db_path,
                config=config,
                preflight=preflight,
                execution_lock_verifier=lambda: _fresh_lock_receipt_is_current(
                    config.db_path, receipt
                ),
                uncertainty_reporter=critical_alert_reporter,
                toolbox=prepared.toolbox,
                production_validation_sha256=prepared.manifest[
                    "epoch_manifest_sha256"
                ],
            )
            watchdog = dependencies.continuity_watchdog_factory(
                coordinator=coordinator,
                db_path=config.db_path,
                config=config,
                preflight=preflight,
                uncertainty_reporter=critical_alert_reporter,
            )
            arm_context = None
            writer_start_attempted = False
            primary_failure: BaseException | None = None
            try:
                writer_start_attempted = True
                try:
                    writer.start()
                    wait_until_ready = getattr(writer, "wait_until_ready", None)
                    if callable(wait_until_ready) and not wait_until_ready(5.0):
                        raise LaunchError("CONTINUITY_WRITER_START_FAILURE")
                except LaunchError:
                    raise
                except Exception as exc:
                    raise LaunchError("CONTINUITY_WRITER_START_FAILURE") from exc
                arm_context = paper_arm_environment(
                    preflight.expected_account_hash
                )
                arm_context.__enter__()
                auditor_gate = dependencies.auditor_gate_factory(config)
                market_gate = dependencies.market_gate_factory(
                    config, preflight.expected_account_hash
                )
                try:
                    service = dependencies.service_factory(
                        db,
                        experiment_start_utc=(
                            controls.clock.start_utc
                            if controls.clock is not None
                            else config.scheduled_start_utc
                        ),
                        experiment_clock=(
                            controls.clock
                            if config.target_successor_epoch_id is not None
                            else None
                        ),
                        successor_owner_authorization_receipt=(
                            preflight.owner_authorization_receipt
                            if config.target_successor_epoch_id is not None
                            else None
                        ),
                        successor_owner_sid=(
                            preflight.owner_sid
                            if config.target_successor_epoch_id is not None
                            else None
                        ),
                        allocation=config.initial_allocation,
                        duration_days=config.duration_days,
                        scan_interval_seconds=300.0,
                        position_interval_seconds=60.0,
                        model=config.model,
                        reasoning_effort=config.reasoning_effort,
                        timeout_seconds=config.model_turn_timeout_seconds,
                        execute_paper=True,
                        runtime_market_gate=market_gate,
                        runtime_auditor_gate=auditor_gate,
                        launch_attempt_id=config.launch_attempt_id,
                        provider=prepared.provider,
                        toolbox=prepared.toolbox,
                        executor=model_executor,
                        continuity_watchdog=watchdog,
                        continuity_store=continuity_store,
                        provider_lifecycle=provider_lifecycle,
                        provider_account_identity_sha256=(
                            preflight.expected_account_hash
                        ),
                        critical_alert_reporter=critical_alert_reporter,
                        session_evidence_reader=(
                            prepared.session_evidence_reader
                        ),
                    )
                except AutonomousServiceError as exc:
                    reason_codes = [
                        code
                        for code in exc.reason_codes
                        if isinstance(code, str) and _REASON_CODE_RE.fullmatch(code)
                    ]
                    if not reason_codes:
                        reason_codes = ["AUTONOMOUS_SERVICE_PREREQUISITE_BLOCK"]
                    raise LaunchError(
                        "AUTONOMOUS_SERVICE_CONSTRUCTION_BLOCK",
                        details={"service_reason_codes": reason_codes},
                    ) from exc
                if not controls.resume_started_epoch:
                    EventRepository(db).append(
                        "EPOCH_STARTED",
                        {
                            "schema": "EPOCH_STARTED_V1",
                            "epoch_id": prepared.manifest["epoch_id"],
                            "definition_sha256": prepared.manifest[
                                "definition_sha256"
                            ],
                            "clock_event_sha256": prepared.manifest[
                                "clock_event_sha256"
                            ],
                            "launch_attempt_id": config.launch_attempt_id,
                            "epoch_manifest_sha256": prepared.manifest[
                                "epoch_manifest_sha256"
                            ],
                            "service_constructed": True,
                            "initial_safety_gate": "PASS",
                            "started_at_utc": datetime.now(timezone.utc),
                        },
                    )
                heartbeat = _LockHeartbeat(
                    config=config,
                    dependencies=dependencies,
                    receipt=receipt,
                    service=service,
                )
                heartbeat.start()
                try:
                    service.run_forever()
                finally:
                    heartbeat.stop()
                if heartbeat.failure_code is not None:
                    raise LaunchError("EXECUTION_LOCK_OWNER_ACTION_REQUIRED")
            except BaseException as exc:
                primary_failure = exc
                raise
            finally:
                if arm_context is not None:
                    arm_context.__exit__(None, None, None)
                if writer_start_attempted:
                    stopped = writer.stop(5.0)
                    if stopped is False:
                        if isinstance(primary_failure, LaunchError):
                            primary_failure.details.setdefault(
                                "cleanup_reason_codes", []
                            ).append("CONTINUITY_WRITER_SHUTDOWN_TIMEOUT")
                        elif primary_failure is None:
                            raise LaunchError("CONTINUITY_WRITER_SHUTDOWN_TIMEOUT")
            return "AUTONOMOUS_PAPER_EXPERIMENT_STOPPED"
        except Exception as exc:
            if transition is not None:
                try:
                    _append_successor_pre_start_failure(
                        db,
                        config,
                        transition,
                        exc,
                        None if prepared is None else prepared.manifest,
                    )
                except Exception as audit_exc:
                    raise LaunchError(
                        "EPOCH_PRE_START_FAILURE_AUDIT_FAILED"
                    ) from audit_exc
            raise
        finally:
            lock.release(receipt)


def current_process_sid() -> str:
    token = None
    try:
        import win32api
        import win32con
        import win32security

        token = win32security.OpenProcessToken(
            win32api.GetCurrentProcess(), win32con.TOKEN_QUERY
        )
        sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
        return str(win32security.ConvertSidToStringSid(sid))
    except Exception as exc:
        raise LaunchError("CURRENT_OWNER_SID_UNAVAILABLE") from exc
    finally:
        if token is not None:
            try:
                win32api.CloseHandle(token)
            except Exception:
                pass


def _lock_owner(now: datetime) -> LockOwner:
    import psutil

    host = socket.gethostname().encode("utf-8")
    process_start = (
        datetime.fromtimestamp(psutil.Process(os.getpid()).create_time(), timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    boot_epoch = int(psutil.boot_time())
    return LockOwner(
        owner_id=str(uuid4()),
        pid=os.getpid(),
        process_start=process_start,
        host_fingerprint=hashlib.sha256(host).hexdigest(),
        boot_session_id=hashlib.sha256(str(boot_epoch).encode("ascii")).hexdigest(),
    )


def _default_config(
    repo_root: Path,
    launch_attempt_id: str,
    *,
    approved_head: str | None = None,
    target_successor_epoch_id: str | None = None,
    target_successor_definition_sha256: str | None = None,
) -> Day1LaunchConfig:
    reports = repo_root / "state" / "ibkr_paper_30d" / "reports"
    return Day1LaunchConfig(
        repo_root=repo_root,
        db_path=repo_root / "state" / "ibkr_paper_30d" / "autonomous.sqlite3",
        launch_root=repo_root / "state" / "ibkr_paper_30d" / "launch",
        expected_identity_path=(
            repo_root / "Secrets" / "expected_paper_account_identity_v1.json"
        ),
        identity_receipt_path=reports / "read_only_real_paper_reconciliation.json",
        auditor_receipt_path=reports / "auditor_gate_v2_receipt.json",
        market_policy_path=reports / "market_data_policy_v1.json",
        market_validation_path=reports / "market_data_validation.json",
        owner_authorization_path=reports
        / (
            "owner_successor_authorization_v2.json"
            if target_successor_epoch_id is not None
            else "owner_authorization_v1.json"
        ),
        model_attestation_exception_path=(
            reports
            / (
                "model_attestation_owner_exception_v2.json"
                if target_successor_epoch_id is not None
                else "model_attestation_owner_exception_v1.json"
            )
        ),
        launch_attempt_binding_path=reports
        / (
            "launch_attempt_binding_v2.json"
            if target_successor_epoch_id is not None
            else "launch_attempt_binding_v1.json"
        ),
        launch_attempt_id=launch_attempt_id,
        approved_head=approved_head,
        target_successor_epoch_id=target_successor_epoch_id,
        target_successor_definition_sha256=(target_successor_definition_sha256),
    )


def _default_provider_recovery(
    db: Database,
    owner: LockOwner,
    config: Day1LaunchConfig,
    preflight: LaunchPreflight,
    *,
    broker_evidence_collector: (
        Callable[[Day1LaunchConfig, LaunchPreflight], BrokerTransitionEvidence] | None
    ) = None,
) -> dict[str, Any]:
    store = ContinuityStore(db)

    def unresolved_invocations() -> list[str]:
        unresolved: list[str] = []
        rows = db.execute(
            "SELECT invocation_id FROM provider_invocation_events "
            "GROUP BY invocation_id"
        ).fetchall()
        for row in rows:
            invocation_id = str(row[0])
            if store.provider_projection(invocation_id)["state"] == "IN_FLIGHT":
                unresolved.append(invocation_id)
        return unresolved

    unresolved = unresolved_invocations()
    if not unresolved:
        return {
            "status": "PASS",
            "reason_codes": [],
            "unresolved_invocation_ids": [],
            "recovered_invocation_ids": [],
        }

    collector = broker_evidence_collector or _collect_successor_broker_evidence
    broker_evidence = collector(config, preflight)
    if (
        broker_evidence.account_identity_sha256 != preflight.expected_account_hash
        or broker_evidence.observation.authenticated is not True
        or broker_evidence.observation.paper_session is not True
        or broker_evidence.broker_write_count != 0
    ):
        return {
            "status": "BLOCK",
            "reason_codes": ["PROVIDER_ABANDONMENT_BROKER_EVIDENCE_INVALID"],
            "unresolved_invocation_ids": unresolved,
            "recovered_invocation_ids": [],
        }

    broker_time = BrokerTimeEvidence.create_authenticated_paper(
        time_utc=broker_evidence.observation.server_time_utc,
        observed_at_utc=broker_evidence.observation.observed_at_utc,
        account_identity_sha256=preflight.expected_account_hash,
    )
    recorder = ProviderLifecycleRecorder(
        store,
        launch_attempt_id=config.launch_attempt_id,
        pid=owner.pid,
        boot_session_identity=owner.boot_session_id,
        expected_account_identity_sha256=preflight.expected_account_hash,
    )
    recovered = list(
        recorder.recover_abandoned(
            {
                "status": "OWNED",
                "pid": owner.pid,
                "boot_session_identity": owner.boot_session_id,
            },
            broker_time,
        )
    )
    unresolved = unresolved_invocations()
    return {
        "status": "PASS" if not unresolved else "BLOCK",
        "reason_codes": (
            [] if not unresolved else ["PROVIDER_ABANDONMENT_RECOVERY_REQUIRED"]
        ),
        "unresolved_invocation_ids": unresolved,
        "recovered_invocation_ids": recovered,
    }


def _default_pending_binding_recovery(
    db: Database, config: Day1LaunchConfig, preflight: LaunchPreflight
) -> dict[str, Any]:
    rows = db.execute(
        "SELECT payload_json,payload_sha256 "
        "FROM experiment_order_registry ORDER BY sequence"
    ).fetchall()
    latest_by_plan: dict[str, dict[str, Any]] = {}
    try:
        for payload_json, payload_sha256 in rows:
            payload = json.loads(str(payload_json))
            if sha256_json(payload) != str(payload_sha256):
                raise ValueError("registry hash mismatch")
            plan_id = str(payload.get("plan_id") or "")
            if plan_id:
                latest_by_plan[plan_id] = payload
    except (TypeError, ValueError, json.JSONDecodeError):
        return {
            "status": "BLOCK",
            "reason_codes": ["PENDING_BINDING_REGISTRY_CORRUPT"],
            "pending_plan_ids": [],
        }
    pending = [
        plan_id
        for plan_id, payload in latest_by_plan.items()
        if payload.get("continuity_state") == "CONTINUITY_BIND_PENDING"
    ]
    return {
        "status": "PASS" if not pending else "BLOCK",
        "reason_codes": (
            [] if not pending else ["PENDING_BINDING_RECONCILIATION_REQUIRED"]
        ),
        "pending_plan_ids": pending,
    }


def _default_continuity_uncertainty(db: Database) -> tuple[str, ...]:
    ContinuityStore(db).verify_all_chains()
    rows = db.execute(
        "SELECT payload_json FROM continuity_execution_events ORDER BY sequence"
    ).fetchall()
    reasons = []
    for row in rows:
        try:
            payload = json.loads(str(row[0]))
        except (TypeError, json.JSONDecodeError) as exc:
            raise LaunchError("CONTINUITY_AUTHORITY_CORRUPT") from exc
        status = str(payload.get("status") or "").upper()
        if status == "UNCERTAIN":
            reasons.append("CONTINUITY_ORDER_STATE_UNCERTAIN")
    return tuple(dict.fromkeys(reasons))


def _default_dependencies() -> LaunchDependencies:
    from .production_continuity_runtime import (
        create_authoritative_writer,
        create_broker_write_coordinator,
        create_continuity_store,
        create_continuity_watchdog,
        create_critical_alert_reporter,
        create_model_executor,
    )

    return LaunchDependencies(
        now_utc=lambda: datetime.now(timezone.utc),
        auditor_gate_factory=lambda config: RuntimeAuditorGate(
            readonly_receipt_path=config.identity_receipt_path,
            auditor_receipt_path=config.auditor_receipt_path,
        ),
        market_gate_factory=lambda config, expected_hash: RuntimeMarketDataGate(
            policy_path=config.market_policy_path,
            expected_account_hash=expected_hash,
        ),
        database_factory=Database.open,
        lock_factory=ExecutionLock,
        service_factory=AutonomousExperimentService,
        lock_owner_factory=_lock_owner,
        current_sid=current_process_sid,
        runtime_provenance_validator=_verify_current_runtime_provenance,
        successor_broker_evidence_collector=_collect_successor_broker_evidence,
        continuity_schema_verifier=verify_continuity_schema_v3,
        provider_abandonment_recoverer=_default_provider_recovery,
        pending_binding_reconciler=_default_pending_binding_recovery,
        continuity_uncertainty_reader=_default_continuity_uncertainty,
        broker_write_coordinator_factory=create_broker_write_coordinator,
        model_executor_factory=create_model_executor,
        critical_alert_reporter_factory=create_critical_alert_reporter,
        authoritative_writer_factory=create_authoritative_writer,
        continuity_watchdog_factory=create_continuity_watchdog,
        continuity_store_factory=create_continuity_store,
    )


def _is_owner_action_required(code: str) -> bool:
    return code in {
        "EXECUTION_LOCK_OWNER_ACTION_REQUIRED",
        "KILL_SWITCH_TRIGGERED",
        "DATABASE_INTEGRITY_CHECK_FAILED",
        "DATABASE_SCHEMA_INVALID",
        "EXPERIMENT_LEDGER_INVALID",
        "OWNER_AUTHORIZATION_CHANGED_DURING_PREFLIGHT",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ibkr_paper_30d.day1_launch")
    parser.add_argument("--launch-attempt-id", required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--approved-head")
    parser.add_argument("--target-successor-epoch-id")
    parser.add_argument("--target-successor-definition-sha256")
    args = parser.parse_args(argv)
    config = _default_config(
        args.repo_root.resolve(),
        args.launch_attempt_id,
        approved_head=args.approved_head,
        target_successor_epoch_id=args.target_successor_epoch_id,
        target_successor_definition_sha256=(args.target_successor_definition_sha256),
    )
    try:
        status = run_day1_launch(config, _default_dependencies())
        result = {"status": status, "reason_codes": []}
        exit_code = 0
    except LaunchError as exc:
        owner_action = _is_owner_action_required(exc.code)
        status = "OWNER_ACTION_REQUIRED" if owner_action else "BLOCK"
        result = {
            "status": status,
            "reason_codes": [exc.code],
            **exc.details,
        }
        exit_code = 30 if owner_action else 20
        try:
            write_launch_evidence(
                config,
                status,
                {"reason_codes": [exc.code], **exc.details},
            )
        except Exception:
            pass
    except Exception as exc:
        result = {
            "status": "FAILED",
            "reason_codes": ["UNEXPECTED_LAUNCH_FAILURE"],
            "error_type": type(exc).__name__,
        }
        exit_code = 1
        try:
            write_launch_evidence(
                config,
                "FAILED",
                {
                    "reason_codes": ["UNEXPECTED_LAUNCH_FAILURE"],
                    "error_type": type(exc).__name__,
                },
            )
        except Exception:
            pass
    print(canonical_bytes(result).decode("utf-8"))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
