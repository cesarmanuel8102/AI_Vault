from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .autonomous_service import AutonomousExperimentService
from .canonical import canonical_bytes, sha256_json
from .execution_lock import ExecutionLock, LockOwner
from .market_data import DecisionClass
from .market_policy import load_verified_policy
from .owner_authorization import (
    OwnerAuthorizationError,
    validate_owner_authorization,
)
from .persistence import Database
from .prerequisite_tools import validate_launch_attempt_binding
from .runtime_integrity import RuntimeAuditorGate, RuntimeMarketDataGate


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
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
    launch_attempt_binding_path: Path
    launch_attempt_id: str
    scheduled_start_utc: datetime = datetime(
        2026, 9, 23, 13, 30, tzinfo=timezone.utc
    )
    duration_days: int = 30
    initial_allocation: Decimal = Decimal("500")
    paper_host: str = "127.0.0.1"
    paper_port: int = 4002
    model: str = "gpt-5.6-sol"
    reasoning_effort: str = "max"


@dataclass
class LaunchDependencies:
    now_utc: Callable[[], datetime]
    auditor_gate_factory: Callable[[Day1LaunchConfig], RuntimeAuditorGate]
    market_gate_factory: Callable[
        [Day1LaunchConfig, str], RuntimeMarketDataGate
    ]
    database_factory: Callable[[Path], Database]
    lock_factory: Callable[[Database], ExecutionLock]
    service_factory: Callable[..., AutonomousExperimentService]
    lock_owner_factory: Callable[[datetime], LockOwner]
    current_sid: Callable[[], str]


class LaunchError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
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
    actual_start_utc: datetime


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


def _validate_identity_receipt(
    payload: dict[str, object], config: Day1LaunchConfig, expected_hash: str
) -> None:
    if payload.get("schema") != "REAL_IBKR_READ_ONLY_RECONCILIATION_V1":
        raise LaunchError("READONLY_RECEIPT_INVALID")
    if payload.get("gateway_mode") == "LIVE" or payload.get("port") == 4001:
        raise LaunchError("LIVE_ROUTE_FORBIDDEN")
    if payload.get("host") != config.paper_host or payload.get("port") != config.paper_port:
        raise LaunchError("PAPER_ROUTE_REQUIRED")
    if payload.get("gateway_mode") != "PAPER":
        raise LaunchError("PAPER_ROUTE_REQUIRED")
    if payload.get("status") != "PASS":
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
    if payload.get("broker_reconciliation_gate") != "PASS":
        raise LaunchError("BROKER_RECONCILIATION_REQUIRED")
    if payload.get("expected_account_identity_bound") is not True:
        raise LaunchError("EXPECTED_ACCOUNT_IDENTITY_REQUIRED")
    if payload.get("expected_account_identity_hash") != expected_hash:
        raise LaunchError("EXPECTED_ACCOUNT_IDENTITY_MISMATCH")
    if payload.get("raw_account_identity_persisted") is not False:
        raise LaunchError("RAW_ACCOUNT_IDENTITY_FORBIDDEN")
    if payload.get("real_order_writes_attempted") != 0:
        raise LaunchError("BROKER_WRITE_DETECTED")
    completeness = payload.get("query_completeness")
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
        "broker_calls_made": 0,
        "real_order_writes_attempted": 0,
    }
    if any(validation.get(key) != value for key, value in expected.items()):
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

    try:
        authorization = validate_owner_authorization(
            db_path=config.db_path,
            receipt_path=config.owner_authorization_path,
            expected_actor_sid=dependencies.current_sid(),
        )
    except OwnerAuthorizationError as exc:
        raise LaunchError(str(exc)) from exc

    try:
        binding = validate_launch_attempt_binding(
            config.launch_attempt_id,
            config.identity_receipt_path,
            config.auditor_receipt_path,
            config.launch_attempt_binding_path,
        )
    except ValueError as exc:
        raise LaunchError(str(exc)) from exc

    expected_hash = _validate_expected_identity(config)
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
    if not isinstance(auditor_result, dict) or auditor_result.get("gate_status") != "PASS":
        raise LaunchError("AUDITOR_GATE_BLOCKED")
    if auditor_result.get("receipt_sha256") != auditor_hash:
        raise LaunchError("AUDITOR_RECEIPT_BINDING_INVALID")

    policy_hash, market_validation_hash = _validate_market_artifacts(config)
    market_result = dependencies.market_gate_factory(config, expected_hash).evaluate(
        DecisionClass.NEW_TRADE
    )
    if not isinstance(market_result, dict) or market_result.get("gate_status") != "PASS":
        raise LaunchError("MARKET_DATA_GATE_BLOCKED")

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
        actual_start_utc=actual_start,
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
        "schema": "DAY1_LAUNCH_EVENT_V1",
        "event_type": event_type,
        "launch_attempt_id": config.launch_attempt_id,
        "created_at_utc": datetime.now(timezone.utc),
        "payload": payload,
    }
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


def current_process_sid() -> str:
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
