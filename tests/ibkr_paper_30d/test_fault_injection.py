from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pytest

from ibkr_paper_30d.reporting import (
    FAULT_SCENARIOS,
    FaultInjectionHarness,
    FaultObservation,
    build_fault_report,
    write_local_reports,
)


NOW = datetime(2026, 9, 20, 16, 0, tzinfo=timezone.utc)


@pytest.fixture
def harness(tmp_path) -> FaultInjectionHarness:
    subject = FaultInjectionHarness(tmp_path / "fault-evidence.jsonl")
    for scenario in FAULT_SCENARIOS:
        subject.register(
            scenario,
            lambda scenario=scenario: FaultObservation(
                blocked=True,
                recovery_required=True,
                reason_code=f"TESTED_{scenario.upper()}",
            ),
        )
    return subject


@pytest.mark.parametrize("scenario", FAULT_SCENARIOS)
def test_fault_scenario_fails_closed_with_durable_evidence(scenario, harness) -> None:
    result = harness.run(scenario)

    assert result.passed is True
    assert result.new_order_authority is False
    assert result.evidence_persisted is True
    assert result.recovery_required is True
    assert result.reason_code


def test_fault_matrix_contains_every_approved_scenario() -> None:
    assert set(FAULT_SCENARIOS) == {
        "crash_before_commit",
        "crash_after_commit",
        "crash_during_submit",
        "crash_after_ack",
        "partial_fill_crash",
        "broker_disconnect",
        "two_factor_required",
        "auth_failure",
        "duplicate_order",
        "db_lock",
        "db_corruption",
        "subledger_mismatch",
        "market_data_loss",
        "smtp_failure",
        "event_log_failure",
        "stale_execution_lock",
        "trader_timeout",
        "trader_malformed",
        "auditor_access_attempt",
    }


def test_unrecognized_fault_is_rejected_without_authority(harness) -> None:
    with pytest.raises(ValueError, match="unknown fault scenario"):
        harness.run("invented_fault")

    assert harness.new_order_authority is False


def test_fault_hook_that_does_not_block_causes_failed_result(harness) -> None:
    harness.register(
        "market_data_loss",
        lambda: FaultObservation(
            blocked=False,
            recovery_required=False,
            reason_code="UNSAFE_CONTINUATION",
        ),
    )

    result = harness.run("market_data_loss")

    assert result.passed is False
    assert result.new_order_authority is False
    assert result.evidence_persisted is True


def test_fault_evidence_is_append_only_hash_chained(harness) -> None:
    harness.run("broker_disconnect")
    harness.run("two_factor_required")

    verification = harness.verify_evidence()

    assert verification.valid is True
    assert verification.record_count == 4


def test_fault_report_counts_results_and_is_deterministic(harness) -> None:
    results = [harness.run(name) for name in FAULT_SCENARIOS]

    first = build_fault_report(results, generated_at_utc=NOW)
    second = build_fault_report(results, generated_at_utc=NOW)

    assert first == second
    assert first["schema"] == "CODEX_IBKR_FAULT_REPORT_V1"
    assert first["scenario_count"] == 19
    assert first["pass"] == 19
    assert first["fail"] == 0
    assert first["gate"] == "PASS"


def test_reports_bind_test_evidence_and_redact_security_detail(harness, tmp_path) -> None:
    results = [harness.run(name) for name in FAULT_SCENARIOS]
    pytest_xml = tmp_path / "pytest.xml"
    pytest_xml.write_text("<testsuite tests='1' failures='0'/>", encoding="utf-8")
    reports = write_local_reports(
        tmp_path / "reports",
        fault_results=results,
        security_boundaries={
            "broker_writes": "BLOCKED",
            "detail": "account=DU123456 PASSWORD=synthetic-secret",
        },
        test_evidence_path=pytest_xml,
        generated_at_utc=NOW,
    )

    fault_payload = json.loads(reports.fault_report.read_text(encoding="utf-8"))
    security_text = reports.security_report.read_text(encoding="utf-8")

    assert fault_payload["test_evidence_sha256"] == hashlib.sha256(
        pytest_xml.read_bytes()
    ).hexdigest()
    assert "DU123456" not in security_text
    assert "synthetic-secret" not in security_text
    assert "[REDACTED_ACCOUNT]" in security_text
    assert reports.fault_report_sha256 == hashlib.sha256(
        reports.fault_report.read_bytes()
    ).hexdigest()
