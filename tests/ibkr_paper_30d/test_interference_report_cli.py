from __future__ import annotations

from ibkr_paper_30d.canonical import canonical_bytes, sha256_json
from ibkr_paper_30d.interference_observability import build_interference_report
from ibkr_paper_30d.persistence import Database


def _insert_observation(db, *, event_id, observation):
    payload = {
        "decision_cycle_id": f"cycle-{event_id}",
        "invocation_id": f"inv-{event_id}",
        "observation": observation,
    }
    db.execute(
        "INSERT INTO autonomous_research_events("
        "event_id,decision_cycle_id,invocation_id,round_index,event_type,"
        "payload_json,payload_sha256,created_at_utc"
        ") VALUES(?,?,?,?,?,?,?,?)",
        (
            event_id,
            f"cycle-{event_id}",
            f"inv-{event_id}",
            1,
            "interference_observation",
            canonical_bytes(payload).decode("utf-8"),
            sha256_json(payload),
            "2026-09-22T05:30:00Z",
        ),
    )


def _insert_provider_failure(db, *, alert_id, code):
    payload = {
        "schema": "AUTONOMOUS_SERVICE_ALERT_V1",
        "event_type": "AUTONOMOUS_PROVIDER_FAILURE_OBSERVATION",
        "created_at_utc": "2026-09-22T05:31:00Z",
        "provider_failure_code": code,
        "error_type": "RuntimeError",
        "provider_policy_attribution": "UNDETERMINED",
        "provider_policy_visibility": "NOT_DIRECTLY_OBSERVABLE",
    }
    db.execute(
        "INSERT INTO alerts(alert_id,event_type,payload_json,payload_sha256,created_at_utc) "
        "VALUES(?,?,?,?,?)",
        (
            alert_id,
            "AUTONOMOUS_PROVIDER_FAILURE_OBSERVATION",
            canonical_bytes(payload).decode("utf-8"),
            sha256_json(payload),
            "2026-09-22T05:31:00Z",
        ),
    )


def test_read_only_report_separates_execution_and_provider_failures(tmp_path):
    path = tmp_path / "autonomous.sqlite3"
    with Database.open(path) as db:
        _insert_observation(
            db,
            event_id="evt-1",
            observation={
                "model_decision": "PROPOSE_TRADE",
                "blocked": False,
                "interference_source": "NONE",
                "disposition": "EXECUTED",
            },
        )
        _insert_observation(
            db,
            event_id="evt-2",
            observation={
                "model_decision": "PROPOSE_TRADE",
                "blocked": True,
                "interference_source": "HOST_CAPABILITY_LIMITATION",
                "disposition": "BLOCKED_BEFORE_EXECUTION",
            },
        )
        _insert_observation(
            db,
            event_id="evt-3",
            observation={
                "model_decision": "NO_TRADE",
                "blocked": False,
                "interference_source": "MODEL_DECISION",
                "disposition": "MODEL_CHOSE_NO_NEW_EXECUTION",
            },
        )
        _insert_provider_failure(db, alert_id="alert-1", code="RETURN_CODE_1")

    report = build_interference_report(path)

    assert report["summary"]["observation_count"] == 3
    assert report["summary"]["proposed_action_count"] == 2
    assert report["summary"]["blocked_proposed_action_count"] == 1
    assert report["summary"]["infrastructure_block_rate"] == 0.5
    assert report["summary"]["auditor_interference_rate"] == 0.0
    assert report["summary"]["host_capability_limit_rate"] == 0.5
    assert report["model_decisions"] == {"PROPOSE_TRADE": 2, "NO_TRADE": 1}
    assert report["provider_failure_count"] == 1
    assert report["provider_failure_codes"] == {"RETURN_CODE_1": 1}
    assert report["provider_policy_attribution"] == "UNDETERMINED"


def test_missing_database_reports_empty_observation_set(tmp_path):
    report = build_interference_report(tmp_path / "missing.sqlite3")

    assert report["summary"]["observation_count"] == 0
    assert report["summary"]["proposed_action_count"] == 0
    assert report["summary"]["infrastructure_block_rate"] is None
    assert report["provider_failure_count"] == 0
