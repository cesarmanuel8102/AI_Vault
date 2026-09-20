from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ibkr_paper_30d.alerts import (
    CRITICAL_EVENT_TYPES,
    AlertEvent,
    AlertRepository,
    AlertService,
    InMemoryAuthority,
    InjectedCrash,
    RETRY_DELAYS_SECONDS,
    load_smtp_channel,
)
from ibkr_paper_30d.persistence import Database


NOW = datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)


class FakeSMTP:
    def __init__(self, trace, *, fail=False):
        self.trace = trace
        self.fail = fail
        self.attempt_count = 0
        self.message_ids = []

    def send(self, message):
        self.trace.append("smtp")
        self.attempt_count += 1
        self.message_ids.append(message.message_id)
        if self.fail:
            raise OSError("synthetic SMTP failure")
        return "smtp-receipt-001"


class FakeEventLog:
    def __init__(self, trace, *, fail=False):
        self.trace = trace
        self.fail = fail
        self.records = []

    def write(self, alert):
        self.trace.append("event_log")
        if self.fail:
            raise OSError("synthetic Event Log failure")
        self.records.append(alert)
        return "eventlog-receipt-001"


@pytest.fixture
def repo(tmp_path) -> AlertRepository:
    return AlertRepository(Database.open(tmp_path / "alerts.sqlite3"))


def event(event_type="KILL_SWITCH_TRIGGERED", correlation_id="corr-001"):
    return AlertEvent(
        event_type=event_type,
        correlation_id=correlation_id,
        occurred_at_utc=NOW,
        detail="account=DU123456 PASSWORD=super-secret",
    )


def build(repo, *, smtp_fail=False, event_log_fail=False):
    trace = []
    authority = InMemoryAuthority(trace)
    smtp = FakeSMTP(trace, fail=smtp_fail)
    event_log = FakeEventLog(trace, fail=event_log_fail)
    service = AlertService(repo, authority, smtp, event_log)
    return service, authority, smtp, event_log, trace


def test_fail_closed_and_persist_precede_delivery(repo) -> None:
    service, authority, smtp, event_log, trace = build(repo)

    result = service.raise_critical(event())

    assert authority.new_order_authority is False
    assert trace[:3] == ["freeze", "persist", "event_log"]
    assert trace[3] == "smtp"
    assert repo.persisted_count() == 1
    assert result.local_status == "CONFIRMED"
    assert result.external_status == "CONFIRMED"


def test_alert_payload_is_redacted_on_both_channels(repo) -> None:
    service, _, smtp, event_log, _ = build(repo)

    service.raise_critical(event())

    persisted = repo.read_alert("alert-corr-001")
    assert "DU123456" not in persisted.payload_json
    assert "super-secret" not in persisted.payload_json
    assert "[REDACTED_ACCOUNT]" in persisted.payload_json
    assert "[REDACTED]" in persisted.payload_json
    assert "super-secret" not in event_log.records[0].detail
    assert smtp.message_ids == ["<alert-corr-001@ibkr-paper-30d.local>"]


def test_2fa_alert_requires_owner_action_and_keeps_authority_paused(repo) -> None:
    service, authority, _, _, _ = build(repo)

    result = service.raise_critical(event("BROKER_2FA_REAUTH_REQUIRED"))

    assert result.owner_action_required is True
    assert authority.new_order_authority is False
    assert authority.recovery_required is True


def test_all_mandated_critical_events_are_accepted(repo) -> None:
    service, _, _, _, _ = build(repo)

    for index, event_type in enumerate(sorted(CRITICAL_EVENT_TYPES)):
        result = service.raise_critical(event(event_type, f"corr-{index}"))
        assert result.alert_id == f"alert-corr-{index}"

    assert repo.persisted_count() == len(CRITICAL_EVENT_TYPES)


def test_noncritical_event_is_rejected_before_persistence(repo) -> None:
    service, _, smtp, _, _ = build(repo)

    with pytest.raises(ValueError, match="not an OWNER_CRITICAL_ALERT_V1 event"):
        service.raise_critical(event("INFORMATIONAL"))

    assert repo.persisted_count() == 0
    assert smtp.attempt_count == 0


def test_smtp_failure_is_durable_and_due_for_retry(repo) -> None:
    service, authority, smtp, _, _ = build(repo, smtp_fail=True)

    result = service.raise_critical(event())

    assert result.external_status == "RETRY_SCHEDULED"
    assert repo.latest_channel_state(result.alert_id, "SMTP") == "FAILED"
    assert repo.due_alert_ids("SMTP") == (result.alert_id,)
    assert authority.new_order_authority is False
    assert smtp.attempt_count == 1


def test_event_log_failure_does_not_suppress_external_delivery(repo) -> None:
    service, _, smtp, _, _ = build(repo, event_log_fail=True)

    result = service.raise_critical(event())

    assert result.local_status == "FAILED"
    assert result.external_status == "CONFIRMED"
    assert smtp.attempt_count == 1


def test_smtp_success_before_receipt_crash_requires_review_without_duplicate(repo) -> None:
    service, authority, smtp, event_log, _ = build(repo)
    service.inject("CRASH_AFTER_SMTP_BEFORE_RECEIPT")

    with pytest.raises(InjectedCrash):
        service.raise_critical(event("BROKER_2FA_REAUTH_REQUIRED"))

    resumed = AlertService(repo, authority, smtp, event_log)
    states = resumed.reconcile_delivery_outbox()

    assert states["alert-corr-001"] == "OWNER_REVIEW_REQUIRED"
    assert smtp.attempt_count == 1
    assert authority.new_order_authority is False


def test_repeated_correlation_id_is_deduplicated_across_restart(repo) -> None:
    service, authority, smtp, event_log, _ = build(repo)
    first = service.raise_critical(event())
    restarted = AlertService(repo, authority, smtp, event_log)

    second = restarted.raise_critical(event())

    assert second.alert_id == first.alert_id
    assert repo.persisted_count() == 1
    assert smtp.attempt_count == 1


def test_retry_schedule_is_bounded() -> None:
    assert RETRY_DELAYS_SECONDS == (0, 15, 60, 300, 900, 900, 900, 900)


def test_smtp_loader_accepts_authorized_email_aliases_without_exposing_secret(
    tmp_path,
) -> None:
    config = tmp_path / "email.env"
    config.write_text(
        "EMAIL_USER=owner@example.test\n"
        "EMAIL_PASS=synthetic-secret\n"
        "EMAIL_TO=owner@example.test\n"
        "SMTP_HOST=smtp.example.test\n"
        "SMTP_PORT=587\n",
        encoding="utf-8",
    )

    channel = load_smtp_channel(config)

    assert "synthetic-secret" not in repr(channel)
    assert "[REDACTED]" in repr(channel)
    assert channel._use_ssl is False
    assert channel._starttls is True
