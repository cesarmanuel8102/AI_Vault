from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import ibkr_paper_30d.day1_launch as launch_module
from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
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
from ibkr_paper_30d.execution_lock import ExecutionLock
from ibkr_paper_30d.experiment_control import (
    ExperimentClockStore,
    KillSwitchStore,
    OwnerAuthorizationStore,
)
from ibkr_paper_30d.experiment_ledger import AutonomousExperimentLedger
from ibkr_paper_30d.market_data import DecisionClass
from ibkr_paper_30d.market_observation_collector import (
    MARKET_OBSERVATION_COLLECTOR_VERSION,
)
from ibkr_paper_30d.owner_authorization import (
    OWNER_PHRASE,
    create_owner_authorization,
)
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.prerequisite_tools import bind_launch_attempt


OWNER_SID = "S-1-5-21-test-owner"
ACCOUNT_HASH = "a" * 64
ATTEMPT_ID = "11111111-1111-4111-8111-111111111111"
NOW = datetime(2026, 9, 23, 20, 0, tzinfo=timezone.utc)


class ExecutorTripwire:
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
        launch_attempt_binding_path=reports / "launch_attempt_binding_v1.json",
        launch_attempt_id=ATTEMPT_ID,
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
                "broker_calls_made": 0,
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
    )
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
    ctx.market_gate.evaluate.assert_called_once_with(DecisionClass.NEW_TRADE)
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
        ({"expected_account_identity_bound": False}, "EXPECTED_ACCOUNT_IDENTITY_REQUIRED"),
        ({"expected_account_identity_hash": "b" * 64}, "EXPECTED_ACCOUNT_IDENTITY_MISMATCH"),
        ({"raw_account_identity_persisted": True}, "RAW_ACCOUNT_IDENTITY_FORBIDDEN"),
        ({"real_order_writes_attempted": 1}, "BROKER_WRITE_DETECTED"),
        (
            {"query_completeness": {"positions": False, "executions": True, "open_orders": True}},
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
    ctx.dependencies.now_utc = lambda: datetime(2026, 9, 23, 13, 29, tzinfo=timezone.utc)

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
    write_identity_receipt(ctx, rebind=False, server_timestamp_utc="2026-09-23T20:00:01Z")

    with pytest.raises(LaunchError, match="LAUNCH_ATTEMPT_RECEIPT_HASH_MISMATCH"):
        evaluate_launch_preflight(ctx.config, ctx.dependencies)

    assert_no_write_authority(ctx)


def test_identity_receipt_changed_during_auditor_evaluation_blocks(tmp_path: Path) -> None:
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
    }

    with pytest.raises(LaunchError, match="MARKET_DATA_GATE_BLOCKED"):
        evaluate_launch_preflight(ctx.config, ctx.dependencies)

    assert_no_write_authority(ctx)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "BLOCK"),
        ("market_data_gate", "BLOCK"),
        ("market_data_policy_frozen", False),
        ("broker_calls_made", 1),
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


def test_launch_evidence_is_atomic_hashed_append_only_and_sanitized(tmp_path: Path) -> None:
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
    history = path.with_name("launch_events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(history) == 2
    assert [json.loads(line)["event"]["event_type"] for line in history] == [
        "PREFLIGHT_PASS",
        "START_DELAY",
    ]


@pytest.mark.parametrize("forbidden", ["account", "account_id", "credential", "token", "prompt"])
def test_launch_evidence_rejects_forbidden_keys(
    tmp_path: Path, forbidden: str
) -> None:
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


def install_fake_lock(ctx: LaunchTestContext, reason: str = "ACQUIRED") -> FakeExecutionLock:
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


def test_validate_launch_controls_only_consumes_preexisting_state(tmp_path: Path) -> None:
    ctx = passing_context(tmp_path)
    before = control_event_counts(ctx.config.db_path)

    with Database.open(ctx.config.db_path) as db:
        controls = validate_launch_controls(db, ctx.config)

    assert controls.kill_switch_state == "KILL_SWITCH_CLEAR"
    assert controls.authorization_event_id
    assert len(controls.clock_event_sha256) == 64
    assert control_event_counts(ctx.config.db_path) == before


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
        switch.set("KILL_SWITCH_CLEAR", reason="invalid later clear")
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
    assert after == before == (
        "KILL_SWITCH_CLEAR",
        "KILL_SWITCH_TRIGGERED",
        "KILL_SWITCH_CLEAR",
    )


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
            OwnerAuthorizationStore(db).current(
                clock_event_sha256=clock.event_sha256
            )
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


def test_missing_authorization_blocks_without_recreating_it(tmp_path: Path) -> None:
    ctx = passing_context(tmp_path)
    ctx.config.owner_authorization_path.unlink()

    with pytest.raises(LaunchError, match="OWNER_AUTHORIZATION_RECEIPT_MISSING"):
        run_day1_launch(ctx.config, ctx.dependencies)

    assert not ctx.config.owner_authorization_path.exists()
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

    def preflight(config, dependencies):
        events.append("preflight")
        return original_preflight(config, dependencies)

    def controls(db, config):
        events.append("controls")
        return original_controls(db, config)

    class OrderedLock(FakeExecutionLock):
        def acquire(self, owner):
            events.append("lock")
            return super().acquire(owner)

    lock = OrderedLock()
    ctx.dependencies.lock_factory = lambda _db: lock
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

    assert events == ["preflight", "lock", "controls", "service", "run"]
    assert ctx.executor_tripwire.calls == []
    assert ctx.ib_tripwire.calls == []


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

    exit_code = main(
        ["--repo-root", str(tmp_path), "--launch-attempt-id", ATTEMPT_ID]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == expected_exit
    assert payload == {"status": expected_status, "reason_codes": [code]}
    assert captured.out.count("\n") == 1
    assert "DU" not in captured.out
    assert "secret" not in captured.out
