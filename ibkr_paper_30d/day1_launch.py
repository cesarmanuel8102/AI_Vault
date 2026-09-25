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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence
from uuid import uuid4

from .autonomous_service import AutonomousExperimentService
from .canonical import canonical_bytes, sha256_json
from .execution_lock import ExecutionLock, LockOwner
from .experiment_control import (
    ExperimentClockStore,
    ExperimentControlError,
    KillSwitchStore,
    OwnerAuthorizationStore,
)
from .experiment_ledger import AutonomousExperimentLedger
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
_REASON_CODE_RE = re.compile(r"^[A-Z0-9_.:-]{1,100}$")
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
    actual_start_utc: datetime


@dataclass(frozen=True)
class LaunchControls:
    clock_event_sha256: str
    authorization_event_id: str
    kill_switch_state: str


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
        raw_reasons = market_result.get("reason_codes", []) if isinstance(
            market_result, dict
        ) else []
        market_reasons = [
            reason
            for reason in raw_reasons
            if isinstance(reason, str) and _REASON_CODE_RE.fullmatch(reason)
        ][:10]
        raise LaunchError(
            "MARKET_DATA_GATE_BLOCKED",
            details={"market_data_reason_codes": market_reasons},
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


def validate_launch_controls(db: Database, config: Day1LaunchConfig) -> LaunchControls:
    assert_integrity_check_ok(db)
    schema_rows = db.execute(
        "SELECT version FROM schema_versions ORDER BY version"
    ).fetchall()
    if [int(row[0]) for row in schema_rows] != [1]:
        raise LaunchError("DATABASE_SCHEMA_INVALID")
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
        OwnerAuthorizationStore(db).current(
            clock_event_sha256=clock.event_sha256
        )
        != "AUTHORIZED"
    ):
        raise LaunchError("OWNER_AUTHORIZATION_INVALID")
    authorization_event_id = _latest_authorization_event_id(db)
    states = tuple(
        str(row[0])
        for row in db.execute(
            "SELECT state FROM kill_switch_events ORDER BY sequence"
        ).fetchall()
    )
    if states != ("KILL_SWITCH_CLEAR",):
        raise LaunchError("KILL_SWITCH_TRIGGERED")
    ledger = AutonomousExperimentLedger(
        db, allocation=config.initial_allocation
    ).project()
    if not ledger.valid:
        raise LaunchError("EXPERIMENT_LEDGER_INVALID")
    return LaunchControls(
        clock_event_sha256=clock.event_sha256,
        authorization_event_id=authorization_event_id,
        kill_switch_state=states[0],
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

        predecessor = db.execute(
            "SELECT event_sha256 FROM state_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_sha = str(predecessor[0]) if predecessor is not None else None
        payload = {
            "schema": "DAY1_LAUNCH_ATTEMPT_ACCEPTED_V1",
            "launch_attempt_id": config.launch_attempt_id,
            "authorization_event_id": controls.authorization_event_id,
            "clock_event_sha256": controls.clock_event_sha256,
            "identity_receipt_sha256": preflight.identity_receipt_sha256,
            "auditor_receipt_sha256": preflight.auditor_receipt_sha256,
            "market_policy_sha256": preflight.market_policy_sha256,
            "market_validation_sha256": preflight.market_validation_sha256,
            "created_at_utc": preflight.actual_start_utc,
        }
        event_sha = sha256_json(
            {"previous_event_sha256": previous_sha, "payload": payload}
        )
        db.execute(
            "INSERT INTO state_events("
            "sequence,event_id,event_type,payload_json,payload_sha256,"
            "previous_event_sha256,event_sha256,created_at_utc"
            ") VALUES((SELECT COALESCE(MAX(sequence),0)+1 FROM state_events),?,?,?,?,?,?,?)",
            (
                str(uuid4()),
                "DAY1_LAUNCH_ATTEMPT_ACCEPTED",
                canonical_bytes(payload).decode("utf-8"),
                sha256_json(payload),
                previous_sha,
                event_sha,
                preflight.actual_start_utc.isoformat().replace("+00:00", "Z"),
            ),
        )


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


def run_day1_launch(
    config: Day1LaunchConfig, dependencies: LaunchDependencies
) -> str:
    try:
        preflight = evaluate_launch_preflight(config, dependencies)
    except LaunchError as exc:
        if exc.code == "KILL_SWITCH_HISTORY_INVALID":
            raise LaunchError("KILL_SWITCH_TRIGGERED") from exc
        raise

    with dependencies.database_factory(config.db_path) as db:
        lock = dependencies.lock_factory(db)
        owner = dependencies.lock_owner_factory(preflight.actual_start_utc)
        receipt = lock.acquire(owner)
        if receipt.reason == "OS_MUTEX_HELD":
            status = "AUTONOMOUS_PAPER_EXPERIMENT_ALREADY_RUNNING"
            write_launch_evidence(config, status, {"reason_codes": []})
            return status
        if not receipt.acquired:
            raise LaunchError("EXECUTION_LOCK_OWNER_ACTION_REQUIRED")

        try:
            controls = validate_launch_controls(db, config)
            if controls.authorization_event_id != preflight.authorization_event_id:
                raise LaunchError("OWNER_AUTHORIZATION_CHANGED_DURING_PREFLIGHT")
            _consume_launch_attempt(db, config, preflight, controls)
            with paper_arm_environment(preflight.expected_account_hash):
                auditor_gate = dependencies.auditor_gate_factory(config)
                market_gate = dependencies.market_gate_factory(
                    config, preflight.expected_account_hash
                )
                service = dependencies.service_factory(
                    db,
                    experiment_start_utc=config.scheduled_start_utc,
                    allocation=config.initial_allocation,
                    duration_days=config.duration_days,
                    scan_interval_seconds=300.0,
                    position_interval_seconds=60.0,
                    model=config.model,
                    reasoning_effort=config.reasoning_effort,
                    execute_paper=True,
                    runtime_market_gate=market_gate,
                    runtime_auditor_gate=auditor_gate,
                    launch_attempt_id=config.launch_attempt_id,
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
            return "AUTONOMOUS_PAPER_EXPERIMENT_STOPPED"
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
    host = socket.gethostname().encode("utf-8")
    try:
        import win32api

        boot_epoch = int(time.time() - (win32api.GetTickCount64() / 1000.0))
    except Exception:
        boot_epoch = 0
    return LockOwner(
        owner_id=str(uuid4()),
        pid=os.getpid(),
        process_start=now.isoformat().replace("+00:00", "Z"),
        host_fingerprint=hashlib.sha256(host).hexdigest(),
        boot_session_id=hashlib.sha256(str(boot_epoch).encode("ascii")).hexdigest(),
    )


def _default_config(repo_root: Path, launch_attempt_id: str) -> Day1LaunchConfig:
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
        owner_authorization_path=reports / "owner_authorization_v1.json",
        launch_attempt_binding_path=reports / "launch_attempt_binding_v1.json",
        launch_attempt_id=launch_attempt_id,
    )


def _default_dependencies() -> LaunchDependencies:
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
    args = parser.parse_args(argv)
    config = _default_config(args.repo_root.resolve(), args.launch_attempt_id)
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
