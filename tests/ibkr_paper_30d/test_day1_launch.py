from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
from ibkr_paper_30d.day1_launch import (
    Day1LaunchConfig,
    LaunchDependencies,
    LaunchError,
    evaluate_launch_preflight,
    write_launch_evidence,
)
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
