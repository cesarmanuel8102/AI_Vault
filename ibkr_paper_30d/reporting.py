from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence
from uuid import uuid4

from .canonical import canonical_bytes
from .redaction import redact_text


FAULT_SCENARIOS = (
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
)


_DEFAULT_OBSERVATIONS = {
    "crash_before_commit": ("EVIDENCE_COMMIT_REQUIRED", "evidence"),
    "crash_after_commit": ("DURABLE_RECONCILIATION_REQUIRED", "evidence"),
    "crash_during_submit": ("ORDER_SUBMIT_UNKNOWN", "broker"),
    "crash_after_ack": ("BROKER_RECONCILIATION_REQUIRED", "broker"),
    "partial_fill_crash": ("PARTIAL_FILL_RECONCILIATION_REQUIRED", "broker"),
    "broker_disconnect": ("BROKER_STATE_UNCERTAIN", "broker"),
    "two_factor_required": ("BROKER_2FA_REAUTH_REQUIRED", "broker"),
    "auth_failure": ("BROKER_AUTH_FAILED", "broker"),
    "duplicate_order": ("DUPLICATE_ORDER_DETECTED", "identity"),
    "db_lock": ("DATABASE_UNAVAILABLE", "persistence"),
    "db_corruption": ("DATABASE_INTEGRITY_FAILURE", "persistence"),
    "subledger_mismatch": ("SUBLEDGER_MISMATCH", "subledger"),
    "market_data_loss": ("MARKET_DATA_GATE_BLOCKED", "market_data"),
    "smtp_failure": ("EXTERNAL_ALERT_RETRY_REQUIRED", "alerts"),
    "event_log_failure": ("LOCAL_ALERT_CHANNEL_FAILED", "alerts"),
    "stale_execution_lock": ("EXECUTION_LOCK_AMBIGUOUS", "execution_lock"),
    "trader_timeout": ("TRADER_TIMEOUT_NO_TRADE", "trader_invocation"),
    "trader_malformed": ("TRADER_OUTPUT_INVALID", "trader_invocation"),
    "auditor_access_attempt": ("AUDITOR_ISOLATION_BLOCKED", "auditor"),
}


@dataclass(frozen=True)
class FaultObservation:
    blocked: bool
    recovery_required: bool
    reason_code: str


@dataclass(frozen=True)
class FaultResult:
    scenario: str
    subsystem: str
    passed: bool
    new_order_authority: bool
    evidence_persisted: bool
    recovery_required: bool
    reason_code: str


@dataclass(frozen=True)
class EvidenceVerification:
    valid: bool
    record_count: int
    first_invalid_record: int | None = None


@dataclass(frozen=True)
class ReportReceipts:
    fault_report: Path
    security_report: Path
    fault_report_sha256: str
    security_report_sha256: str


class FaultInjectionHarness:
    def __init__(self, evidence_path: str | Path):
        self.evidence_path = Path(evidence_path)
        self.evidence_path.parent.mkdir(parents=True, exist_ok=True)
        self.new_order_authority = True
        self._handlers: dict[str, Callable[[], FaultObservation]] = {}

    def register(
        self, scenario: str, handler: Callable[[], FaultObservation]
    ) -> None:
        if scenario not in FAULT_SCENARIOS:
            raise ValueError(f"unknown fault scenario: {scenario}")
        self._handlers[scenario] = handler

    def run(self, scenario: str) -> FaultResult:
        self.new_order_authority = False
        if scenario not in FAULT_SCENARIOS:
            raise ValueError(f"unknown fault scenario: {scenario}")
        _, subsystem = _DEFAULT_OBSERVATIONS[scenario]
        self._append_evidence(
            {"phase": "FAULT_INJECTED", "scenario": scenario, "authority": False}
        )
        handler = self._handlers.get(scenario)
        try:
            observation = (
                handler()
                if handler is not None
                else FaultObservation(
                    blocked=False,
                    recovery_required=True,
                    reason_code="FAULT_HANDLER_NOT_REGISTERED",
                )
            )
        except Exception as exc:
            observation = FaultObservation(
                blocked=True,
                recovery_required=True,
                reason_code=f"INJECTED_EXCEPTION:{type(exc).__name__}",
            )
        passed = bool(
            observation.blocked
            and observation.recovery_required
            and not self.new_order_authority
            and observation.reason_code
        )
        result = FaultResult(
            scenario=scenario,
            subsystem=subsystem,
            passed=passed,
            new_order_authority=self.new_order_authority,
            evidence_persisted=False,
            recovery_required=observation.recovery_required,
            reason_code=observation.reason_code,
        )
        self._append_evidence(
            {
                "phase": "FAULT_OBSERVED",
                "scenario": scenario,
                "subsystem": subsystem,
                "passed": passed,
                "authority": self.new_order_authority,
                "recovery_required": observation.recovery_required,
                "reason_code": observation.reason_code,
            }
        )
        return FaultResult(**{**asdict(result), "evidence_persisted": True})

    def verify_evidence(self) -> EvidenceVerification:
        if not self.evidence_path.exists():
            return EvidenceVerification(True, 0)
        previous = None
        count = 0
        for count, line in enumerate(
            self.evidence_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            try:
                record = json.loads(line)
                digest = record.pop("record_sha256")
            except (json.JSONDecodeError, KeyError, AttributeError):
                return EvidenceVerification(False, count, count)
            if record.get("previous_record_sha256") != previous:
                return EvidenceVerification(False, count, count)
            actual = hashlib.sha256(canonical_bytes(record)).hexdigest()
            if digest != actual:
                return EvidenceVerification(False, count, count)
            previous = digest
        return EvidenceVerification(True, count)

    def _append_evidence(self, payload: dict[str, object]) -> None:
        previous = self._last_hash()
        record = {**payload, "previous_record_sha256": previous}
        record["record_sha256"] = hashlib.sha256(canonical_bytes(record)).hexdigest()
        line = canonical_bytes(record) + b"\n"
        with self.evidence_path.open("ab") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def _last_hash(self) -> str | None:
        if not self.evidence_path.exists() or self.evidence_path.stat().st_size == 0:
            return None
        with self.evidence_path.open("rb") as handle:
            lines = handle.read().splitlines()
        return str(json.loads(lines[-1])["record_sha256"])


def build_fault_report(
    results: Sequence[FaultResult],
    *,
    generated_at_utc: datetime | None = None,
) -> dict[str, object]:
    generated = generated_at_utc or datetime.now(timezone.utc)
    passed = sum(result.passed for result in results)
    failed = len(results) - passed
    complete_matrix = {result.scenario for result in results} == set(FAULT_SCENARIOS)
    gate = "PASS" if failed == 0 and complete_matrix else "BLOCK"
    return {
        "schema": "CODEX_IBKR_FAULT_REPORT_V1",
        "generated_at_utc": generated.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "scenario_count": len(results),
        "pass": passed,
        "fail": failed,
        "gate": gate,
        "results": [asdict(result) for result in results],
    }


def write_local_reports(
    report_dir: str | Path,
    *,
    fault_results: Sequence[FaultResult],
    security_boundaries: Mapping[str, object],
    test_evidence_path: str | Path,
    generated_at_utc: datetime | None = None,
) -> ReportReceipts:
    destination = Path(report_dir)
    destination.mkdir(parents=True, exist_ok=True)
    evidence = Path(test_evidence_path)
    evidence_sha256 = hashlib.sha256(evidence.read_bytes()).hexdigest()

    fault_report = build_fault_report(
        fault_results, generated_at_utc=generated_at_utc
    )
    fault_report["test_evidence_path"] = str(evidence)
    fault_report["test_evidence_sha256"] = evidence_sha256
    security_report = {
        "schema": "CODEX_IBKR_SECURITY_BOUNDARY_REPORT_V1",
        "generated_at_utc": fault_report["generated_at_utc"],
        "test_evidence_sha256": evidence_sha256,
        "boundaries": _redact_value(dict(security_boundaries)),
    }

    fault_path = destination / "fault_injection_report.json"
    security_path = destination / "security_boundary_report.json"
    _atomic_write(fault_path, canonical_bytes(fault_report))
    _atomic_write(security_path, canonical_bytes(security_report))
    return ReportReceipts(
        fault_report=fault_path,
        security_report=security_path,
        fault_report_sha256=hashlib.sha256(fault_path.read_bytes()).hexdigest(),
        security_report_sha256=hashlib.sha256(security_path.read_bytes()).hexdigest(),
    )


def _redact_value(value: object) -> object:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {str(key): _redact_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_value(item) for item in value]
    return value


def _atomic_write(path: Path, payload: bytes) -> None:
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
