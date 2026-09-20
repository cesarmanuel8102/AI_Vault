from __future__ import annotations

import hashlib
import sqlite3
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol

from .canonical import canonical_bytes
from .persistence import Database
from .redaction import redact_text
from .repositories import utc_now
from .types import new_uuid7


RETRY_DELAYS_SECONDS = (0, 15, 60, 300, 900, 900, 900, 900)

CRITICAL_EVENT_TYPES = frozenset(
    {
        "BROKER_2FA_REAUTH_REQUIRED",
        "BROKER_AUTH_FAILED",
        "BROKER_HEARTBEAT_TIMEOUT",
        "KILL_SWITCH_TRIGGERED",
        "FAIL_CLOSED",
        "MAX_DRAWDOWN_REACHED",
        "MAX_DAILY_LOSS_REACHED",
        "MAX_WEEKLY_DRAWDOWN_REACHED",
        "BROKER_STATE_UNCERTAIN",
        "ORDER_STATE_UNCERTAIN",
        "DUPLICATE_ORDER_DETECTED",
        "POSSIBLE_LIVE_CONNECTION",
        "SUBLEDGER_MISMATCH",
        "RECOVERY_GATE_FAILURE",
        "RUNTIME_CRASH_WITH_OPEN_POSITION",
        "EXECUTION_LOCK_AMBIGUOUS",
    }
)


class InjectedCrash(RuntimeError):
    pass


@dataclass(frozen=True)
class AlertEvent:
    event_type: str
    correlation_id: str
    occurred_at_utc: datetime
    detail: str


@dataclass(frozen=True)
class CriticalAlert:
    alert_id: str
    event_type: str
    correlation_id: str
    occurred_at_utc: datetime
    detail: str
    owner_action_required: bool


@dataclass(frozen=True)
class AlertMessage:
    message_id: str
    subject: str
    body: str


@dataclass(frozen=True)
class AlertResult:
    alert_id: str
    local_status: str
    external_status: str
    owner_action_required: bool


@dataclass(frozen=True)
class StoredAlert:
    alert_id: str
    event_type: str
    payload_json: str
    payload_sha256: str


class NewOrderAuthority(Protocol):
    def revoke_new_orders(self, correlation_id: str) -> None: ...


class SMTPTransport(Protocol):
    def send(self, message: AlertMessage) -> str: ...


class EventLogTransport(Protocol):
    def write(self, alert: CriticalAlert) -> str: ...


class InMemoryAuthority:
    def __init__(self, trace: list[str] | None = None):
        self.trace = trace
        self.new_order_authority = True
        self.recovery_required = False

    def revoke_new_orders(self, correlation_id: str) -> None:
        if self.trace is not None:
            self.trace.append("freeze")
        self.new_order_authority = False
        self.recovery_required = True


class AlertRepository:
    def __init__(self, db: Database):
        self.db = db

    def persist(self, alert: CriticalAlert) -> bool:
        payload = canonical_bytes(alert)
        digest = hashlib.sha256(payload).hexdigest()
        try:
            self.db.execute(
                "INSERT INTO alerts(alert_id,event_type,payload_json,payload_sha256,created_at_utc) "
                "VALUES(?,?,?,?,?)",
                (
                    alert.alert_id,
                    alert.event_type,
                    payload.decode("utf-8"),
                    digest,
                    utc_now(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            if not self.exists(alert.alert_id):
                raise
            stored = self.read_alert(alert.alert_id)
            if stored.payload_sha256 != digest:
                raise ValueError("alert correlation identity collision") from exc
            return False
        return True

    def exists(self, alert_id: str) -> bool:
        return (
            self.db.execute(
                "SELECT 1 FROM alerts WHERE alert_id=?", (alert_id,)
            ).fetchone()
            is not None
        )

    def persisted_count(self) -> int:
        return int(self.db.execute("SELECT COUNT(*) FROM alerts").fetchone()[0])

    def read_alert(self, alert_id: str) -> StoredAlert:
        row = self.db.execute(
            "SELECT alert_id,event_type,payload_json,payload_sha256 FROM alerts "
            "WHERE alert_id=?",
            (alert_id,),
        ).fetchone()
        if row is None:
            raise KeyError(alert_id)
        return StoredAlert(*map(str, row))

    def record_delivery(
        self,
        alert_id: str,
        channel: str,
        status: str,
        payload: dict[str, object],
    ) -> str:
        safe_payload = _redact_mapping(payload)
        payload_bytes = canonical_bytes(safe_payload)
        delivery_id = str(new_uuid7())
        self.db.execute(
            "INSERT INTO alert_deliveries(delivery_id,alert_id,channel,status,payload_json,payload_sha256,created_at_utc) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                delivery_id,
                alert_id,
                channel,
                status,
                payload_bytes.decode("utf-8"),
                hashlib.sha256(payload_bytes).hexdigest(),
                utc_now(),
            ),
        )
        return delivery_id

    def latest_channel_state(self, alert_id: str, channel: str) -> str | None:
        row = self.db.execute(
            "SELECT status FROM alert_deliveries WHERE alert_id=? AND channel=? "
            "ORDER BY rowid DESC LIMIT 1",
            (alert_id, channel),
        ).fetchone()
        return None if row is None else str(row[0])

    def alert_ids(self) -> tuple[str, ...]:
        rows = self.db.execute("SELECT alert_id FROM alerts ORDER BY rowid").fetchall()
        return tuple(str(row[0]) for row in rows)

    def due_alert_ids(self, channel: str) -> tuple[str, ...]:
        due = []
        for alert_id in self.alert_ids():
            if self.latest_channel_state(alert_id, channel) == "FAILED":
                due.append(alert_id)
        return tuple(due)


class AlertService:
    def __init__(
        self,
        repo: AlertRepository,
        authority: NewOrderAuthority,
        smtp: SMTPTransport,
        event_log: EventLogTransport,
    ):
        self.repo = repo
        self.authority = authority
        self.smtp = smtp
        self.event_log = event_log
        self._faults: set[str] = set()

    def inject(self, fault: str) -> None:
        self._faults.add(fault)

    def raise_critical(self, event: AlertEvent) -> AlertResult:
        if event.event_type not in CRITICAL_EVENT_TYPES:
            raise ValueError(
                f"{event.event_type} is not an OWNER_CRITICAL_ALERT_V1 event"
            )
        self.authority.revoke_new_orders(event.correlation_id)
        alert = _to_redacted_alert(event)
        created = self.repo.persist(alert)
        trace = getattr(self.authority, "trace", None)
        if trace is not None:
            trace.append("persist")
        if not created:
            return self._existing_result(alert)

        local_status = self._write_event_log(alert)
        external_status = self._send_smtp(alert)
        return AlertResult(
            alert.alert_id,
            local_status,
            external_status,
            alert.owner_action_required,
        )

    def reconcile_delivery_outbox(self) -> dict[str, str]:
        states: dict[str, str] = {}
        for alert_id in self.repo.alert_ids():
            state = self.repo.latest_channel_state(alert_id, "SMTP")
            if state == "INTENT":
                self.repo.record_delivery(
                    alert_id,
                    "SMTP",
                    "OWNER_REVIEW_REQUIRED",
                    {"reason": "SEND_MAY_HAVE_SUCCEEDED_WITHOUT_DURABLE_RECEIPT"},
                )
                state = "OWNER_REVIEW_REQUIRED"
            elif state == "FAILED":
                state = "RETRY_SCHEDULED"
            states[alert_id] = state or "NOT_ATTEMPTED"
        return states

    def _write_event_log(self, alert: CriticalAlert) -> str:
        self.repo.record_delivery(
            alert.alert_id,
            "WINDOWS_EVENT_LOG",
            "INTENT",
            {"event_type": alert.event_type},
        )
        try:
            receipt = self.event_log.write(alert)
        except Exception as exc:
            self.repo.record_delivery(
                alert.alert_id,
                "WINDOWS_EVENT_LOG",
                "FAILED",
                {"error": redact_text(str(exc))},
            )
            return "FAILED"
        self.repo.record_delivery(
            alert.alert_id,
            "WINDOWS_EVENT_LOG",
            "CONFIRMED",
            {"receipt": receipt},
        )
        return "CONFIRMED"

    def _send_smtp(self, alert: CriticalAlert) -> str:
        message = _message_for(alert)
        self.repo.record_delivery(
            alert.alert_id,
            "SMTP",
            "INTENT",
            {"message_id": message.message_id},
        )
        try:
            receipt = self.smtp.send(message)
        except Exception as exc:
            self.repo.record_delivery(
                alert.alert_id,
                "SMTP",
                "FAILED",
                {"error": redact_text(str(exc))},
            )
            return "RETRY_SCHEDULED"
        if "CRASH_AFTER_SMTP_BEFORE_RECEIPT" in self._faults:
            self._faults.remove("CRASH_AFTER_SMTP_BEFORE_RECEIPT")
            raise InjectedCrash("synthetic crash after SMTP send")
        self.repo.record_delivery(
            alert.alert_id,
            "SMTP",
            "CONFIRMED",
            {"receipt": receipt, "message_id": message.message_id},
        )
        return "CONFIRMED"

    def _existing_result(self, alert: CriticalAlert) -> AlertResult:
        local = self.repo.latest_channel_state(alert.alert_id, "WINDOWS_EVENT_LOG")
        external = self.repo.latest_channel_state(alert.alert_id, "SMTP")
        return AlertResult(
            alert.alert_id,
            local or "NOT_ATTEMPTED",
            external or "NOT_ATTEMPTED",
            alert.owner_action_required,
        )


class SMTPChannel:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        recipient: str,
        use_ssl: bool,
        starttls: bool,
    ):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender
        self._recipient = recipient
        self._use_ssl = use_ssl
        self._starttls = starttls

    def __repr__(self) -> str:
        return "SMTPChannel(configured=True, credentials=[REDACTED])"

    def send(self, message: AlertMessage) -> str:
        email = EmailMessage()
        email["From"] = self._sender
        email["To"] = self._recipient
        email["Subject"] = message.subject
        email["Message-ID"] = message.message_id
        email.set_content(message.body)
        context = ssl.create_default_context()
        client_class = smtplib.SMTP_SSL if self._use_ssl else smtplib.SMTP
        with client_class(self._host, self._port, timeout=30) as client:
            if self._starttls and not self._use_ssl:
                client.starttls(context=context)
            if self._username:
                client.login(self._username, self._password)
            client.send_message(email)
        return message.message_id


class WindowsEventLogChannel:
    def __init__(self, source: str = "CodexIBKRPaper30D"):
        self.source = source

    def write(self, alert: CriticalAlert) -> str:
        import win32evtlog
        import win32evtlogutil

        event_id = int(hashlib.sha256(alert.alert_id.encode()).hexdigest()[:7], 16)
        win32evtlogutil.ReportEvent(
            self.source,
            event_id,
            eventType=win32evtlog.EVENTLOG_ERROR_TYPE,
            strings=[
                alert.event_type,
                f"correlation_id={alert.correlation_id}",
                alert.detail,
                f"OWNER_ACTION_REQUIRED={str(alert.owner_action_required).lower()}",
            ],
        )
        return f"Application:{self.source}:{event_id}"


def load_smtp_channel(path: str | Path) -> SMTPChannel:
    values = _read_env(path)
    host = _required(values, "SMTP_HOST")
    port = int(values.get("SMTP_PORT", "465"))
    username = values.get("SMTP_USERNAME", values.get("EMAIL_USER", ""))
    password = values.get("SMTP_PASSWORD", values.get("EMAIL_PASS", ""))
    sender = values.get("SMTP_FROM", username)
    recipient = values.get("SMTP_TO", values.get("EMAIL_TO", "")).strip()
    if not recipient:
        raise ValueError("SMTP_TO or EMAIL_TO is required")
    if not sender:
        raise ValueError("SMTP_FROM or SMTP_USERNAME is required")
    use_ssl = _as_bool(values.get("SMTP_SSL", str(port == 465)))
    starttls = _as_bool(values.get("SMTP_STARTTLS", str(not use_ssl)))
    return SMTPChannel(
        host=host,
        port=port,
        username=username,
        password=password,
        sender=sender,
        recipient=recipient,
        use_ssl=use_ssl,
        starttls=starttls,
    )


def _to_redacted_alert(event: AlertEvent) -> CriticalAlert:
    return CriticalAlert(
        alert_id=f"alert-{event.correlation_id}",
        event_type=event.event_type,
        correlation_id=event.correlation_id,
        occurred_at_utc=event.occurred_at_utc,
        detail=redact_text(event.detail),
        owner_action_required=event.event_type == "BROKER_2FA_REAUTH_REQUIRED",
    )


def _message_for(alert: CriticalAlert) -> AlertMessage:
    body = "\n".join(
        (
            "OWNER_CRITICAL_ALERT_V1",
            f"EVENT_TYPE={alert.event_type}",
            f"CORRELATION_ID={alert.correlation_id}",
            f"OCCURRED_AT_UTC={alert.occurred_at_utc.isoformat()}",
            f"OWNER_ACTION_REQUIRED={str(alert.owner_action_required).lower()}",
            "AUTONOMOUS_TRADING_STATUS=PAUSED",
            f"DETAIL={alert.detail}",
        )
    )
    return AlertMessage(
        message_id=f"<{alert.alert_id}@ibkr-paper-30d.local>",
        subject=f"[CRITICAL] IBKR Paper: {alert.event_type}",
        body=body,
    )


def _redact_mapping(payload: dict[str, object]) -> dict[str, object]:
    return {key: redact_text(str(value)) for key, value in payload.items()}


def _read_env(path: str | Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _required(values: dict[str, str], key: str) -> str:
    value = values.get(key, "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}
