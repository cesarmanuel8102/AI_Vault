from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
from ibkr_paper_30d.continuity_schema import install_continuity_schema_v3
from ibkr_paper_30d.continuity_store import ContinuityStore
from ibkr_paper_30d.persistence import Database
from ibkr_paper_30d.provider_lifecycle import (
    BrokerTimeEvidence,
    ProviderLifecycleError,
    ProviderLifecycleRecorder,
)
from ibkr_paper_30d.successor_schema import install_successor_schema_v2
from ibkr_paper_30d.trader_invocation import InvocationRequest


UTC = timezone.utc
NOW = datetime(2026, 10, 1, 14, 0, tzinfo=UTC)


def _request(invocation_id: str = "invocation-1") -> InvocationRequest:
    return InvocationRequest(
        decision_cycle_id="cycle-1",
        invocation_id=invocation_id,
        utc_timestamp=NOW.isoformat(),
        requested_model="gpt-5.6-sol",
        actual_model="gpt-5.6-sol",
        model_configuration={"provider": "codex-cli"},
        reasoning_effort="max",
        input_bundle_sha256="a" * 64,
        risk_policy_version="AGGRESSIVE_CAPITAL_BOUNDARY_V1",
        experiment_id="ibkr-paper-30d",
        invocation_trigger="SCHEDULED_SCAN",
        timeout_seconds=180,
    )


def _time(value: datetime = NOW, environment: str = "PAPER") -> BrokerTimeEvidence:
    return BrokerTimeEvidence.create_authenticated_paper(
        time_utc=value,
        observed_at_utc=value,
        account_identity_sha256="b" * 64,
        environment=environment,
    )


def _recorder(db: Database) -> ProviderLifecycleRecorder:
    return ProviderLifecycleRecorder(
        ContinuityStore(db),
        launch_attempt_id="launch-1",
        pid=4242,
        boot_session_identity="boot-1",
        expected_account_identity_sha256="b" * 64,
    )


def _open(path) -> Database:
    db = Database.open(path)
    install_successor_schema_v2(db)
    install_continuity_schema_v3(db)
    return db


def _persist_result(db: Database, *, accepted: bool, result_hash: str) -> None:
    payload = {"accepted": accepted}
    db.execute(
        "INSERT INTO trader_input_bundles(bundle_id,decision_cycle_id,payload_json,payload_sha256,created_at_utc) "
        "VALUES('bundle-1','cycle-1','{}','x','2026-10-01T14:00:00Z')"
    )
    request = _request().model_dump(mode="json")
    db.execute(
        "INSERT INTO trader_invocations(invocation_id,decision_cycle_id,bundle_id,payload_json,payload_sha256,created_at_utc) "
        "VALUES(?,?,?,?,?,?)",
        ("invocation-1", "cycle-1", "bundle-1", canonical_bytes(request).decode(), sha256_json(request), NOW.isoformat()),
    )
    db.execute(
        "INSERT INTO trader_results(result_id,invocation_id,decision_cycle_id,accepted,accepted_cycle_key,payload_json,payload_sha256,created_at_utc) "
        "VALUES(?,?,?,?,?,?,?,?)",
        ("result-1", "invocation-1", "cycle-1", int(accepted), "cycle-1" if accepted else None,
         canonical_bytes(payload).decode(), result_hash, NOW.isoformat()),
    )


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        ("timeout", "TIMEOUT_CONFIRMED"),
        ("error", "PROCESS_ERROR"),
        ("unaccepted", "COMPLETED_UNACCEPTED"),
    ],
)
def test_records_start_to_terminal_predecessor_linkage(tmp_path, operation: str, expected: str) -> None:
    with _open(tmp_path / f"{operation}.sqlite3") as db:
        recorder = _recorder(db)
        token = recorder.begin(_request(), _time())
        if operation == "timeout":
            recorder.fail(token, "PROVIDER_TIMEOUT", _time(NOW + timedelta(seconds=5)))
        elif operation == "error":
            recorder.fail(token, "SUBPROCESS_EXIT", _time(NOW + timedelta(seconds=5)))
        else:
            _persist_result(db, accepted=False, result_hash="d" * 64)
            recorder.complete(
                token,
                "COMPLETED_UNACCEPTED",
                _time(NOW + timedelta(seconds=5)),
                result_sha256="d" * 64,
            )
        projection = ContinuityStore(db).provider_projection("invocation-1")
        rows = db.execute(
            "SELECT event_type,previous_event_sha256,event_sha256 "
            "FROM provider_invocation_events ORDER BY sequence"
        ).fetchall()

        assert [row[0] for row in rows] == ["IN_FLIGHT", expected]
        assert rows[1][1] == rows[0][2]
        assert projection["state"] == expected


def test_accepted_completion_requires_matching_durable_result(tmp_path) -> None:
    with _open(tmp_path / "state.sqlite3") as db:
        recorder = _recorder(db)
        assert ContinuityStore(db).provider_projection("invocation-1")["state"] == "IDLE"
        token = recorder.begin(_request(), _time())
        with pytest.raises(ProviderLifecycleError, match="RESULT_NOT_DURABLE"):
            recorder.complete(
                token, "COMPLETED_ACCEPTED", _time(NOW + timedelta(seconds=1)),
                result_sha256="d" * 64,
            )
        _persist_result(db, accepted=True, result_hash="d" * 64)
        recorder.complete(
            token, "COMPLETED_ACCEPTED", _time(NOW + timedelta(seconds=2)),
            result_sha256="d" * 64,
        )
        assert ContinuityStore(db).provider_projection("invocation-1")["state"] == "COMPLETED_ACCEPTED"


def test_duplicate_terminal_replays_exactly_but_conflicting_terminal_blocks(tmp_path) -> None:
    with _open(tmp_path / "state.sqlite3") as db:
        recorder = _recorder(db)
        token = recorder.begin(_request(), _time())
        first = recorder.fail(token, "PROVIDER_TIMEOUT", _time(NOW + timedelta(seconds=1)))
        assert recorder.fail(token, "PROVIDER_TIMEOUT", _time(NOW + timedelta(seconds=1))) == first
        with pytest.raises(ProviderLifecycleError, match="TERMINAL_CONFLICT"):
            recorder.fail(token, "SUBPROCESS_EXIT", _time(NOW + timedelta(seconds=2)))


@pytest.mark.parametrize(
    "kind",
    ["missing", "naive", "live"],
)
def test_rejects_missing_naive_or_non_paper_broker_time(tmp_path, kind) -> None:
    if kind == "missing":
        evidence = None
    else:
        evidence = _time(environment="LIVE" if kind == "live" else "PAPER")
        if kind == "naive":
            evidence = evidence.model_copy(update={"time_utc": NOW.replace(tzinfo=None)})
    with _open(tmp_path / "state.sqlite3") as db:
        with pytest.raises(ProviderLifecycleError, match="BROKER_TIME"):
            _recorder(db).begin(_request(), evidence)


def test_rejects_broker_time_moving_backwards(tmp_path) -> None:
    with _open(tmp_path / "state.sqlite3") as db:
        recorder = _recorder(db)
        token = recorder.begin(_request(), _time())
        with pytest.raises(ProviderLifecycleError, match="BACKWARD"):
            recorder.fail(token, "PROVIDER_TIMEOUT", _time(NOW - timedelta(seconds=1)))


def test_restart_abandons_only_definitively_dead_owner(tmp_path) -> None:
    with _open(tmp_path / "state.sqlite3") as db:
        recorder = _recorder(db)
        recorder.begin(_request("dead"), _time())
        recorder.begin(_request("live"), _time(NOW + timedelta(seconds=1)))

        abandoned = recorder.recover_abandoned(
            {"status": "OWNED", "pid": 4242, "boot_session_identity": "boot-1", "invocation_id": "live"},
            _time(NOW + timedelta(seconds=2)),
        )
        assert abandoned == ("dead",)
        assert ContinuityStore(db).provider_projection("dead")["state"] == "ABANDONED"
        assert ContinuityStore(db).provider_projection("live")["state"] == "IN_FLIGHT"


def test_uncertain_lock_owner_does_not_invent_abandonment(tmp_path) -> None:
    with _open(tmp_path / "state.sqlite3") as db:
        recorder = _recorder(db)
        recorder.begin(_request(), _time())
        assert recorder.recover_abandoned(
            {"status": "UNCERTAIN"}, _time(NOW + timedelta(seconds=2))
        ) == ()
        assert ContinuityStore(db).provider_projection("invocation-1")["state"] == "IN_FLIGHT"


def test_broker_time_evidence_is_authenticated_and_hash_bound() -> None:
    evidence = _time()

    assert evidence.authenticated is True
    assert evidence.observed_at_utc == NOW
    with pytest.raises(ValueError, match="BROKER_TIME_EVIDENCE_HASH_MISMATCH"):
        BrokerTimeEvidence.model_validate(
            {**evidence.model_dump(mode="python"), "evidence_sha256": "0" * 64}
        )


def test_provider_lifecycle_rejects_other_account_time(tmp_path) -> None:
    with _open(tmp_path / "account.sqlite3") as db:
        with pytest.raises(ProviderLifecycleError, match="BROKER_TIME_ACCOUNT_MISMATCH"):
            _recorder(db).begin(
                _request(),
                BrokerTimeEvidence.create_authenticated_paper(
                    time_utc=NOW,
                    observed_at_utc=NOW,
                    account_identity_sha256="d" * 64,
                ),
            )
