from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from decimal import Decimal
from typing import Callable, Mapping, Sequence
from uuid import uuid4

from .canonical import canonical_bytes
from .redaction import redact_text

FAULT_SCENARIO_TEST_MATRIX = {
    "crash_before_commit": "tests/ibkr_paper_30d/test_evidence.py::test_crash_before_commit_rolls_back",
    "crash_after_commit": "tests/ibkr_paper_30d/test_evidence.py::test_crash_after_commit_preserves_record",
    "crash_during_submit": "tests/ibkr_paper_30d/test_fake_broker.py::test_unknown_submit_is_never_retried",
    "crash_after_ack": "tests/ibkr_paper_30d/test_reconciliation.py::test_completed_order_or_execution_recovers_crash_window",
    "partial_fill_crash": "tests/ibkr_paper_30d/test_fake_broker.py::test_fake_lifecycle_supports_partial_fill_modify_cancel",
    "broker_disconnect": "tests/ibkr_paper_30d/test_orchestrator.py::test_reconnecting_remains_paused_without_order_authority",
    "two_factor_required": "tests/ibkr_paper_30d/test_orchestrator.py::test_2fa_requires_owner_and_full_reconciliation",
    "auth_failure": "tests/ibkr_paper_30d/test_orchestrator.py::test_auth_failure_pauses_and_alerts",
    "duplicate_order": "tests/ibkr_paper_30d/test_fake_broker.py::test_duplicate_idempotency_key_transmits_once",
    "db_lock": "tests/ibkr_paper_30d/test_persistence.py::test_database_lock_fails_closed",
    "db_corruption": "tests/ibkr_paper_30d/test_persistence.py::test_tampered_hash_chain_is_detected",
    "subledger_mismatch": "tests/ibkr_paper_30d/test_subledger.py::test_broker_subledger_mismatch_blocks_reconciliation",
    "market_data_loss": "tests/ibkr_paper_30d/test_market_data.py::test_invalid_quotes_block",
    "smtp_failure": "tests/ibkr_paper_30d/test_alerts.py::test_smtp_failure_is_durable_and_due_for_retry",
    "event_log_failure": "tests/ibkr_paper_30d/test_alerts.py::test_event_log_failure_does_not_suppress_external_delivery",
    "stale_execution_lock": "tests/ibkr_paper_30d/test_execution_lock.py::test_dead_pid_and_stale_heartbeat_recover_and_acquire_new_generation",
    "trader_timeout": "tests/ibkr_paper_30d/test_trader_invocation.py::test_timeout_fails_to_no_trade",
    "trader_malformed": "tests/ibkr_paper_30d/test_trader_invocation.py::test_malformed_wrong_schema_and_authority_excess_fail_to_no_trade",
    "auditor_access_attempt": "tests/ibkr_paper_30d/test_auditor_isolation.py::test_isolation_report_stays_blocked_when_forbidden_capabilities_exist",
}

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
    production_test_nodeid: str | None


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
        self._production_test_nodeids: dict[str, str] = {}

    def register(
        self,
        scenario: str,
        handler: Callable[[], FaultObservation],
        *,
        production_test_nodeid: str | None = None,
    ) -> None:
        if scenario not in FAULT_SCENARIOS:
            raise ValueError(f"unknown fault scenario: {scenario}")
        self._handlers[scenario] = handler
        if production_test_nodeid is not None:
            expected = FAULT_SCENARIO_TEST_MATRIX.get(scenario)
            if production_test_nodeid != expected:
                raise ValueError(
                    f"production test nodeid mismatch for {scenario}: "
                    f"{production_test_nodeid!r} != {expected!r}"
                )
            self._production_test_nodeids[scenario] = production_test_nodeid

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
        production_test_nodeid = self._production_test_nodeids.get(scenario)
        passed = bool(
            observation.blocked
            and observation.recovery_required
            and not self.new_order_authority
            and observation.reason_code
            and production_test_nodeid
        )
        result = FaultResult(
            scenario=scenario,
            subsystem=subsystem,
            passed=passed,
            new_order_authority=self.new_order_authority,
            evidence_persisted=False,
            recovery_required=observation.recovery_required,
            reason_code=observation.reason_code,
            production_test_nodeid=production_test_nodeid,
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
                "production_test_nodeid": production_test_nodeid,
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


def build_multi_universe_performance_report(
    *,
    regular_principal_usd: Decimal,
    regular_opening_equity_usd: Decimal,
    regular_current_equity_usd: Decimal,
    extended_principal_usd: Decimal,
    extended_opening_equity_usd: Decimal,
    extended_current_equity_usd: Decimal,
    regular_currency_balances: Mapping[str, Decimal],
    extended_currency_balances: Mapping[str, Decimal],
    canary_adjustment_usd: Decimal,
    ownership: Mapping[str, Sequence[str]],
    certified_families: Sequence[str],
    paper_limitations: Sequence[str],
) -> dict[str, object]:
    def money(value: Decimal) -> str:
        return str(Decimal(value).quantize(Decimal("0.01")))

    regular_historical = regular_opening_equity_usd - regular_principal_usd
    regular_successor = regular_current_equity_usd - regular_opening_equity_usd
    extended_successor = extended_current_equity_usd - extended_opening_equity_usd
    successor_opening = regular_opening_equity_usd + extended_opening_equity_usd
    current_combined = regular_current_equity_usd + extended_current_equity_usd
    aggregate: dict[str, Decimal] = {}
    for balances in (regular_currency_balances, extended_currency_balances):
        for currency, amount in balances.items():
            code = str(currency).upper()
            aggregate[code] = aggregate.get(code, Decimal("0")) + Decimal(amount)
    return {
        "schema": "MULTI_UNIVERSE_PERFORMANCE_REPORT_V1",
        "regular_historical_pnl_usd": money(regular_historical),
        "regular_successor_pnl_usd": money(regular_successor),
        "extended_successor_pnl_usd": money(extended_successor),
        "combined_successor_pnl_usd": money(current_combined - successor_opening),
        "combined_lifetime_pnl_usd": money(
            current_combined - regular_principal_usd - extended_principal_usd
        ),
        "canary_adjustment_usd": money(canary_adjustment_usd),
        "currency_balances": {
            "REGULAR_SLEEVE": {
                str(key).upper(): money(value)
                for key, value in regular_currency_balances.items()
            },
            "EXTENDED_SLEEVE": {
                str(key).upper(): money(value)
                for key, value in extended_currency_balances.items()
            },
        },
        "aggregate_currency_balances": {
            key: money(value) for key, value in sorted(aggregate.items())
        },
        "ownership": {key: list(value) for key, value in ownership.items()},
        "certified_families": list(certified_families),
        "paper_limitations": list(paper_limitations),
        "capital_rebased": False,
        "cross_sleeve_netting": False,
    }


def build_supervision_first_pilot_report(
    evidence: Mapping[str, object],
    *,
    generated_at_utc: datetime | None = None,
) -> dict[str, object]:
    """Build a factual pilot report, blocking on incomplete authority evidence."""

    generated = (generated_at_utc or datetime.now(timezone.utc)).astimezone(
        timezone.utc
    )
    snapshot = deepcopy(dict(evidence))
    reasons: list[str] = []

    required_sections = (
        "transition",
        "account",
        "writer",
        "execution_lock",
        "inherited_bindings",
        "sleeve_economics",
        "family_lifecycle",
        "canary",
        "orders",
        "fills",
        "positions",
        "accepted_model_cycles",
        "alert_delivery",
        "broker_write_counts",
        "db_receipts",
        "broker_receipts",
    )
    for section in required_sections:
        if section not in snapshot:
            reasons.append(f"{section.upper()}_EVIDENCE_REQUIRED")

    exact_head = str(snapshot.get("exact_head") or "")
    if not _is_lower_hex(exact_head, 40):
        reasons.append("EXACT_HEAD_REQUIRED")

    transition = _mapping(snapshot.get("transition"))
    account = _mapping(snapshot.get("account"))
    writer = _mapping(snapshot.get("writer"))
    lock = _mapping(snapshot.get("execution_lock"))
    canary = _mapping(snapshot.get("canary"))
    alert_delivery = _mapping(snapshot.get("alert_delivery"))
    db_receipts = _mapping(snapshot.get("db_receipts"))
    broker_receipts = _mapping(snapshot.get("broker_receipts"))

    if not _is_sha256(writer.get("writer_binding_sha256")):
        reasons.append("WRITER_BINDING_HASH_REQUIRED")
    if any(
        receipt.get("fresh") is not True
        for receipt in (account, writer, lock, db_receipts)
    ):
        reasons.append("DATABASE_EVIDENCE_STALE")
    if broker_receipts.get("fresh") is not True:
        reasons.append("BROKER_EVIDENCE_STALE")
    if account.get("paper_only") is not True:
        reasons.append("PAPER_IDENTITY_NOT_PROVEN")
    if (
        account.get("account_identity_sha256")
        != broker_receipts.get("account_identity_sha256")
    ):
        reasons.append("ACCOUNT_IDENTITY_MISMATCH")
    if (
        writer.get("writer_binding_sha256")
        != broker_receipts.get("writer_binding_sha256")
    ):
        reasons.append("WRITER_BINDING_MISMATCH")
    if writer.get("pid") != lock.get("pid") or lock.get("state") != "ACTIVE":
        reasons.append("EXECUTION_LOCK_WRITER_MISMATCH")

    phase = str(transition.get("phase") or "")
    phase_event = transition.get("phase_event_sha256")
    if phase == "ACTIVE" and (
        db_receipts.get("phase") != "ACTIVE"
        or db_receipts.get("phase_event_sha256") != phase_event
    ):
        reasons.append("ACTIVE_PHASE_RECEIPT_MISMATCH")
    if phase == "ACTIVE" and not snapshot.get("accepted_model_cycles"):
        reasons.append("ACTIVE_ACCEPTED_CYCLE_REQUIRED")

    if (
        alert_delivery.get("windows_event_log") != "CONFIRMED"
        or alert_delivery.get("external_owner_channel") != "CONFIRMED"
    ):
        reasons.append("ALERT_DELIVERY_NOT_CONFIRMED")

    if canary.get("status") == "CANARY_PASS":
        lifecycle = canary.get("lifecycle_receipt_sha256")
        flat = canary.get("flat_state_sha256")
        if (
            db_receipts.get("canary_lifecycle_receipt_sha256") != lifecycle
            or broker_receipts.get("canary_lifecycle_receipt_sha256") != lifecycle
            or db_receipts.get("canary_flat_state_sha256") != flat
            or broker_receipts.get("canary_flat_state_sha256") != flat
        ):
            reasons.append("CANARY_PASS_RECEIPT_MISMATCH")

    positions = snapshot.get("positions")
    if (
        not _is_sha256(db_receipts.get("orders_state_sha256"))
        or db_receipts.get("orders_state_sha256")
        != broker_receipts.get("orders_state_sha256")
    ):
        reasons.append("ORDER_STATE_RECEIPT_MISMATCH")
    if (
        not _is_sha256(db_receipts.get("executions_state_sha256"))
        or db_receipts.get("executions_state_sha256")
        != broker_receipts.get("executions_state_sha256")
    ):
        reasons.append("EXECUTION_STATE_RECEIPT_MISMATCH")
    if isinstance(positions, Sequence) and not isinstance(positions, (str, bytes)):
        if len(positions) == 0 and (
            not _is_sha256(db_receipts.get("positions_state_sha256"))
            or db_receipts.get("positions_state_sha256")
            != broker_receipts.get("positions_state_sha256")
        ):
            reasons.append("ZERO_EXPOSURE_NOT_PROVEN")

    if _contains_invalid_sha256(snapshot):
        reasons.append("UNHASHED_EVIDENCE")

    counts = _mapping(snapshot.get("broker_write_counts"))
    normalized_counts: dict[str, int] = {}
    for key, value in counts.items():
        if str(key) == "total":
            continue
        try:
            count = int(value)
        except (TypeError, ValueError):
            reasons.append("BROKER_WRITE_COUNT_INVALID")
            continue
        if count < 0:
            reasons.append("BROKER_WRITE_COUNT_INVALID")
            continue
        normalized_counts[str(key)] = count
    normalized_counts["total"] = sum(normalized_counts.values())

    report: dict[str, object] = {
        "schema": "SUPERVISION_FIRST_PILOT_REPORT_V1",
        "generated_at_utc": generated.isoformat().replace("+00:00", "Z"),
        **snapshot,
        "broker_write_counts": normalized_counts,
        "gate": "PASS" if not reasons else "BLOCK",
        "reason_codes": list(dict.fromkeys(reasons)),
    }
    report["report_sha256"] = hashlib.sha256(canonical_bytes(report)).hexdigest()
    return report


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _is_lower_hex(value: object, length: int) -> bool:
    text = str(value or "")
    return len(text) == length and all(character in "0123456789abcdef" for character in text)


def _is_sha256(value: object) -> bool:
    return _is_lower_hex(value, 64)


def _contains_invalid_sha256(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).endswith("_sha256") and not _is_sha256(item):
                return True
            if _contains_invalid_sha256(item):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_invalid_sha256(item) for item in value)
    return False


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

    fault_report = build_fault_report(fault_results, generated_at_utc=generated_at_utc)
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
