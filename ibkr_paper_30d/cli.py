from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import re
from dataclasses import asdict, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Sequence
from uuid import uuid4

from defusedxml import ElementTree as ET

from .alerts import (
    AlertEvent,
    AlertRepository,
    AlertService,
    InMemoryAuthority,
    WindowsEventLogChannel,
    load_smtp_channel,
)
from .auditor import write_isolation_report
from .autonomous_runtime import AutonomousDecisionRuntime
from .ibkr_research import IBKRResearchToolbox
from .auditor_gate_v2 import (
    AuditorGateV2Evaluation,
    IdentityBindingError,
    PaperIdentityBinding,
    load_and_evaluate_auditor_gate_v2,
    parse_auditor_gate_v2_receipt,
)
from .auditor_v2_artifacts import (
    build_residual_risk_acceptance,
    render_auditor_gate_v2_report,
    write_immutable_json,
)
from .ibkr_readonly import IBKRReadOnlyAdapter, ReadOnlySessionSnapshot
from .ibkr_readonly_session import (
    ExpectedPaperIdentityStore,
    IBKRReadOnlySessionCollector,
    ReadOnlyMessageGuard,
)
from .canonical import canonical_bytes
from .market_data import (
    DecisionClass,
    MarketDataGate,
    MarketDataPolicy,
    MarketDataSnapshot,
    QuoteSnapshot,
)
from .market_observation_collector import (
    IBKRMarketDataSource,
    MarketDataSource,
    MarketObservationCollector,
    ObservationAborted,
    ObservationConfig,
    ObservationPrerequisites,
)
from .market_observation_ledger import MarketObservationLedger
from .market_policy import MarketPolicyFreezer, load_verified_policy
from .persistence import Database
from .redaction import redact_text
from .reporting import FAULT_SCENARIOS, FaultInjectionHarness, write_local_reports
from .trader_invocation import (
    CodexCLIProvider,
    InvocationRequest,
    TraderInputBundle,
    TraderInvocationAdapter,
)


REPORT_ROOT = Path("state/ibkr_paper_30d/reports")
READONLY_REPORT = REPORT_ROOT / "read_only_real_paper_reconciliation.json"
ALERT_REPORT = REPORT_ROOT / "alert_delivery_simulation.json"
GATE_REPORT = REPORT_ROOT / "updated_gate_matrix.json"
REAL_CODEX_REPORT = REPORT_ROOT / "real_codex_trader_invocation.json"
AUTONOMOUS_RESEARCH_REPORT = REPORT_ROOT / "autonomous_research_cycle.json"
AUDITOR_REPORT = REPORT_ROOT / "auditor_isolation_probe.json"
AUDITOR_V2_RECEIPT = REPORT_ROOT / "auditor_gate_v2_receipt.json"
AUDITOR_V2_REPORT = Path("AUDITOR_ISOLATION_GATE_V2_REPORT.md")
AUDITOR_V2_ACCEPTANCE = Path("AUDITOR_MONTH1_PAPER_RESIDUAL_RISK_ACCEPTANCE_V1.json")
CAPABILITY_MATRIX = Path("IBKR_CAPABILITY_MATRIX_V1.md")
MARKET_LEDGER = REPORT_ROOT / "market_observations.jsonl"
MARKET_OBSERVATION_REPORT = REPORT_ROOT / "market_observation.json"
MARKET_POLICY = REPORT_ROOT / "market_data_policy_v1.json"
MARKET_POLICY_REPORT = REPORT_ROOT / "market_policy_freeze.json"
MARKET_VALIDATION_REPORT = REPORT_ROOT / "market_data_validation.json"


def inspect_readonly(
    *,
    host: str,
    port: int,
    expected_account_hash: str | None,
    output_path: str | Path = READONLY_REPORT,
) -> dict[str, object]:
    reasons: list[str] = []
    if port != 4002:
        reasons.append("PAPER_PORT_MISMATCH")
    if not _port_is_open(host, port):
        reasons.append("GATEWAY_UNAVAILABLE")
    if reasons:
        if not expected_account_hash:
            reasons.insert(0, "EXPECTED_ACCOUNT_IDENTITY_NOT_CONFIGURED")
        report = {
            "schema": "REAL_IBKR_READ_ONLY_RECONCILIATION_V1",
            "status": "BLOCK",
            "host": host,
            "port": port,
            "reason_codes": reasons,
            "gateway_started_by_codex": False,
            "broker_calls_made": 0,
            "expected_account_identity_hash": expected_account_hash,
            "raw_account_identity_persisted": False,
            "real_order_writes_attempted": 0,
        }
        _atomic_json(Path(output_path), report)
        return report

    gateway_mode, gateway_config_consistent = _gateway_mode()
    evidence = IBKRReadOnlySessionCollector().collect(host=host, port=port)
    identity_store = ExpectedPaperIdentityStore(
        Path("Secrets/expected_paper_account_identity_v1.json")
    )
    configured_hash = expected_account_hash
    binding_receipt = None
    if configured_hash is None and identity_store.path.exists():
        configured_hash = identity_store.load_hash()
    if configured_hash is None and len(evidence.managed_accounts) == 1:
        binding_receipt = identity_store.bind(
            evidence.managed_accounts[0],
            host=host,
            port=port,
            gateway_mode=gateway_mode,
            managed_account_count=len(evidence.managed_accounts),
        )
        configured_hash = binding_receipt.account_sha256
    if configured_hash is None:
        raise RuntimeError("expected paper identity could not be bound")

    summary_accounts = set(evidence.account_summary)
    managed_accounts = set(evidence.managed_accounts)
    account_summary_consistent = bool(summary_accounts) and summary_accounts.issubset(
        managed_accounts
    )
    selected_summary = (
        evidence.account_summary.get(evidence.managed_accounts[0], {})
        if len(evidence.managed_accounts) == 1
        else {}
    )
    snapshot = ReadOnlySessionSnapshot(
        port=port,
        connected=evidence.connected,
        authenticated=evidence.authenticated,
        paper_trading_mode=gateway_mode == "p" and gateway_config_consistent,
        managed_accounts=evidence.managed_accounts,
        connector_account_hash=None,
        cash=selected_summary.get("TotalCashValue"),
        settled_cash=_settled_cash(selected_summary),
        position_count=len(evidence.positions),
        open_order_count=len(evidence.open_orders),
        execution_visibility=(
            "AVAILABLE"
            if evidence.query_completeness.get("executions")
            else "UNAVAILABLE"
        ),
        market_data_entitlements=_market_behavior(evidence.quotes),
        server_timestamp_utc=(
            datetime.fromisoformat(evidence.server_timestamp_utc.replace("Z", "+00:00"))
            if evidence.server_timestamp_utc
            else None
        ),
        heartbeat_ok=evidence.heartbeat_ok,
    )
    inspection = IBKRReadOnlyAdapter(configured_hash).inspect(snapshot)
    query_complete = all(evidence.query_completeness.values())
    critical_errors = [
        item for item in evidence.errors if int(item.get("code", 0)) in {326, 502, 503, 504, 1100, 1300}
    ]
    summary_complete = _required_summary_complete(selected_summary)
    identity_pass = (
        inspection.identity.paper_identity_proven
        and account_summary_consistent
        and gateway_config_consistent
        and bool(binding_receipt is None or binding_receipt.acl_protected)
    )
    reconciliation_pass = (
        identity_pass and query_complete and summary_complete and not critical_errors
    )
    report_reasons = list(inspection.reason_codes)
    if not gateway_config_consistent:
        report_reasons.append("GATEWAY_CONFIG_MODE_CONFLICT")
    if not account_summary_consistent:
        report_reasons.append("ACCOUNT_SUMMARY_IDENTITY_MISMATCH")
    if not query_complete:
        report_reasons.append("BROKER_QUERY_INCOMPLETE")
    if not summary_complete:
        report_reasons.append("ACCOUNT_SUMMARY_FIELDS_INCOMPLETE")
    if critical_errors:
        report_reasons.append("BROKER_CRITICAL_ERROR")
    behavior = _market_behavior(evidence.quotes)
    report = {
        "schema": "REAL_IBKR_READ_ONLY_RECONCILIATION_V1",
        "status": "PASS" if reconciliation_pass else ("PARTIAL" if identity_pass else "BLOCK"),
        "reason_codes": sorted(set(report_reasons)),
        "host": host,
        "port": port,
        "gateway_mode": "PAPER" if gateway_mode == "p" else "UNPROVEN",
        "gateway_config_consistent": gateway_config_consistent,
        "server_version": evidence.server_version,
        "connection_time": evidence.connection_time,
        "paper_account_identity_gate": "PASS" if identity_pass else "BLOCK",
        "real_ibkr_read_only_identity_gate": "PASS" if identity_pass else "BLOCK",
        "broker_reconciliation_gate": "PASS" if reconciliation_pass else "BLOCK",
        "expected_account_identity_bound": identity_store.path.exists(),
        "expected_account_identity_hash": configured_hash,
        "account_fingerprint": inspection.identity.account_fingerprint,
        "identity_factor_count": inspection.identity.factor_count,
        "connector_comparison": "UNAVAILABLE",
        "account_summary_consistent": account_summary_consistent,
        "account_summary_complete": summary_complete,
        "cash": snapshot.cash,
        "settled_cash": snapshot.settled_cash,
        "buying_power": selected_summary.get("BuyingPower"),
        "net_liquidation": selected_summary.get("NetLiquidation"),
        "position_count": len(evidence.positions),
        "positions": [
            {key: value for key, value in position.items() if key != "account"}
            for position in evidence.positions
        ],
        "open_order_count": len(evidence.open_orders),
        "open_orders": list(evidence.open_orders),
        "execution_count": len(evidence.executions),
        "executions": list(evidence.executions),
        "execution_visibility": snapshot.execution_visibility,
        "market_data_behavior": behavior,
        "market_data_policy_frozen": False,
        "quotes": [asdict(quote) for quote in evidence.quotes],
        "server_timestamp_utc": evidence.server_timestamp_utc,
        "heartbeat_ok": evidence.heartbeat_ok,
        "query_completeness": evidence.query_completeness,
        "broker_errors": _redacted_errors(evidence.errors),
        "outbound_message_ids": list(evidence.outbound_message_ids),
        "outbound_allowlist_only": all(
            message_id in ReadOnlyMessageGuard.ALLOWED_MESSAGE_IDS
            for message_id in evidence.outbound_message_ids
        ),
        "raw_account_identity_persisted": False,
        "real_order_writes_attempted": 0,
    }
    _atomic_json(Path(output_path), report)
    return report


def observe_market_data(
    *,
    readonly_report: dict[str, object],
    output_root: str | Path = REPORT_ROOT,
    source: MarketDataSource | None = None,
    expected_account_hash: str | None = None,
    symbols: Sequence[str] = ("SPY", "QQQ", "IEF"),
    cadence_seconds: float = 5,
    window_seconds: float = 300,
    now_utc=None,
) -> dict[str, object]:
    root = Path(output_root)
    report_path = root / "market_observation.json"
    prerequisite_reasons = _market_prerequisite_reasons(readonly_report)
    if not expected_account_hash:
        prerequisite_reasons.append("EXPECTED_ACCOUNT_IDENTITY_NOT_CONFIGURED")
    if prerequisite_reasons:
        report = _blocked_market_report(
            "MARKET_DATA_OBSERVATION_V1", prerequisite_reasons
        )
        _write_market_report(report_path, report)
        return report

    assert expected_account_hash is not None
    reconciliation_hash = hashlib.sha256(
        canonical_bytes(readonly_report)
    ).hexdigest()
    data_source = source or IBKRMarketDataSource()
    collector = MarketObservationCollector(data_source, now_utc=now_utc)
    try:
        window = collector.collect_window(
            ObservationConfig(
                symbols=tuple(symbols),
                cadence_seconds=cadence_seconds,
                window_seconds=window_seconds,
            ),
            ObservationPrerequisites(
                identity_receipt_sha256=expected_account_hash,
                reconciliation_receipt_sha256=reconciliation_hash,
                paper_identity_proven=True,
                broker_reconciliation_gate="PASS",
            ),
        )
        receipt = MarketObservationLedger(
            root / "market_observations.jsonl"
        ).append_window(window)
    except (ObservationAborted, OSError, RuntimeError, ValueError) as exc:
        reason = redact_text(str(exc)).split(":", 1)[0] or type(exc).__name__
        report = _blocked_market_report("MARKET_DATA_OBSERVATION_V1", [reason])
        report["broker_calls_made"] = _market_source_call_count(data_source)
        _write_market_report(report_path, report)
        return report

    accepted = sum(item.accepted for item in window.observations)
    report = {
        "schema": "MARKET_DATA_OBSERVATION_V1",
        "status": "PASS",
        "reason_codes": [],
        "window_id": window.window_id,
        "observation_count": len(window.observations),
        "accepted_observation_count": accepted,
        "rejected_observation_count": len(window.observations) - accepted,
        "ledger_window_sha256": receipt.window_sha256,
        "ledger_last_record_sha256": receipt.last_record_sha256,
        "identity_receipt_sha256": expected_account_hash,
        "reconciliation_receipt_sha256": reconciliation_hash,
        "broker_calls_made": _market_source_call_count(data_source),
        "market_data_policy_frozen": False,
        "market_data_gate": "BLOCK",
        "new_order_authority": "FROZEN",
        "real_order_writes_attempted": 0,
        "autonomous_trading_status": "BLOCKED",
    }
    _write_market_report(report_path, report)
    return report


def freeze_market_policy(
    ledger: MarketObservationLedger | str | Path,
    destination: str | Path,
    *,
    output_path: str | Path | None = None,
) -> dict[str, object]:
    subject = (
        ledger
        if isinstance(ledger, MarketObservationLedger)
        else MarketObservationLedger(ledger)
    )
    result = MarketPolicyFreezer().freeze(subject, destination)
    frozen = result.status in {"PASS", "ALREADY_FROZEN"}
    report = {
        "schema": "MARKET_DATA_POLICY_FREEZE_REPORT_V1",
        "status": result.status,
        "reason_codes": list(result.reason_codes),
        "market_data_policy_frozen": frozen,
        "market_data_gate": "BLOCK",
        "policy_sha256": result.artifact_sha256,
        "policy_version": result.policy.version if result.policy else None,
        "broker_calls_made": 0,
        "new_order_authority": "FROZEN",
        "real_order_writes_attempted": 0,
        "autonomous_trading_status": "BLOCKED",
    }
    if output_path is not None:
        _write_market_report(Path(output_path), report)
    return report


def validate_market_observation(
    policy: MarketDataPolicy,
    quotes: Sequence[QuoteSnapshot],
    *,
    now: datetime,
) -> dict[str, object]:
    if not quotes:
        return _blocked_market_report(
            "REAL_MARKET_DATA_VALIDATION_V1", ["MARKET_QUOTES_MISSING"]
        )
    snapshot = MarketDataSnapshot.freeze(quotes, created_at_utc=now)
    result = MarketDataGate(policy).evaluate(
        snapshot, DecisionClass.NEW_TRADE, now=now
    )
    return {
        "schema": "REAL_MARKET_DATA_VALIDATION_V1",
        "status": result.status,
        "market_data_gate": result.status,
        "reason_codes": list(result.reason_codes),
        "market_data_snapshot_id": result.market_data_snapshot_id,
        "market_data_snapshot_sha256": result.market_data_snapshot_sha256,
        "policy_version": result.market_data_policy_version,
        "market_data_policy_frozen": True,
        "symbol_count": len(quotes),
        "broker_calls_made": 0,
        "new_order_authority": "FROZEN",
        "real_order_writes_attempted": 0,
        "autonomous_trading_status": "BLOCKED",
    }


def validate_real_market_data(
    *,
    readonly_report: dict[str, object],
    policy_path: str | Path,
    output_path: str | Path = MARKET_VALIDATION_REPORT,
    source: MarketDataSource | None = None,
    expected_account_hash: str | None = None,
    now_utc=None,
) -> dict[str, object]:
    reasons = _market_prerequisite_reasons(readonly_report)
    if not expected_account_hash:
        reasons.append("EXPECTED_ACCOUNT_IDENTITY_NOT_CONFIGURED")
    try:
        policy = load_verified_policy(policy_path)
    except ValueError:
        policy = None
        reasons.append("MARKET_POLICY_INVALID")
    if reasons:
        report = _blocked_market_report("REAL_MARKET_DATA_VALIDATION_V1", reasons)
        report["market_data_policy_frozen"] = policy is not None
        _write_market_report(Path(output_path), report)
        return report

    assert expected_account_hash is not None and policy is not None
    data_source = source or IBKRMarketDataSource()
    clock = now_utc or (lambda: datetime.now(timezone.utc))
    reconciliation_hash = hashlib.sha256(
        canonical_bytes(readonly_report)
    ).hexdigest()
    try:
        window = MarketObservationCollector(data_source, now_utc=clock).collect_window(
            ObservationConfig(
                symbols=("SPY", "QQQ", "IEF"),
                cadence_seconds=5,
                window_seconds=0,
            ),
            ObservationPrerequisites(
                identity_receipt_sha256=expected_account_hash,
                reconciliation_receipt_sha256=reconciliation_hash,
                paper_identity_proven=True,
                broker_reconciliation_gate="PASS",
            ),
        )
        quotes = [
            QuoteSnapshot(
                symbol=item.symbol,
                contract_id=item.contract_id,
                source=item.source,
                bid=item.bid,
                ask=item.ask,
                last=item.last,
                bid_size=item.bid_size,
                ask_size=item.ask_size,
                last_size=item.last_size,
                quote_timestamp=item.broker_quote_timestamp,
                local_receipt_timestamp=item.local_receipt_timestamp,
                market_session=item.market_session.value,
                realtime_or_delayed=item.realtime_or_delayed,
                data_entitlement_status=item.entitlement_state,
                declared_quote_age_ms=item.corrected_quote_age_ms,
                source_health=item.source_health,
            )
            for item in window.observations
        ]
        report = validate_market_observation(policy, quotes, now=clock())
        direct_reasons = list(report["reason_codes"])
        if any(
            item.clock_skew_ms is None
            or abs(item.clock_skew_ms) > policy.max_clock_skew_ms
            for item in window.observations
        ):
            direct_reasons.append("CLOCK_SKEW")
        if direct_reasons:
            report["status"] = "BLOCK"
            report["market_data_gate"] = "BLOCK"
            report["reason_codes"] = list(dict.fromkeys(direct_reasons))
        report["broker_calls_made"] = _market_source_call_count(data_source)
    except (ObservationAborted, OSError, RuntimeError, ValueError) as exc:
        reason = redact_text(str(exc)).split(":", 1)[0] or type(exc).__name__
        report = _blocked_market_report("REAL_MARKET_DATA_VALIDATION_V1", [reason])
        report["broker_calls_made"] = _market_source_call_count(data_source)
    _write_market_report(Path(output_path), report)
    return report


def _market_prerequisite_reasons(
    readonly_report: dict[str, object]
) -> list[str]:
    reasons = []
    if readonly_report.get("status") != "PASS":
        reasons.append("READ_ONLY_RECONCILIATION_REQUIRED")
    if readonly_report.get("paper_account_identity_gate") != "PASS":
        reasons.append("PAPER_IDENTITY_REQUIRED")
    if readonly_report.get("broker_reconciliation_gate") != "PASS":
        reasons.append("BROKER_RECONCILIATION_REQUIRED")
    if readonly_report.get("heartbeat_ok") is not True:
        reasons.append("BROKER_HEARTBEAT_REQUIRED")
    return reasons


def _blocked_market_report(schema: str, reasons: Sequence[str]) -> dict[str, object]:
    return {
        "schema": schema,
        "status": "BLOCK",
        "reason_codes": list(dict.fromkeys(reasons)),
        "broker_calls_made": 0,
        "market_data_policy_frozen": False,
        "market_data_gate": "BLOCK",
        "new_order_authority": "FROZEN",
        "real_order_writes_attempted": 0,
        "autonomous_trading_status": "BLOCKED",
    }


def _market_source_call_count(source: MarketDataSource) -> int:
    client = getattr(source, "client", None)
    outbound = getattr(client, "outbound_message_ids", None)
    if isinstance(outbound, list):
        return len(outbound)
    starts = getattr(source, "start_calls", 0)
    return int(starts) if isinstance(starts, int) else 0


def _write_market_report(path: Path, report: dict[str, object]) -> None:
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"), default=str)
    if redact_text(encoded) != encoded:
        raise ValueError("MARKET_REPORT_SECRET_SCAN_FAILED")
    _atomic_json(path, report)


def _gateway_mode() -> tuple[str, bool]:
    paths = (Path("C:/Jts/jts.ini"), Path("C:/Jts/ibgateway/1044/jts.ini"))
    modes = []
    for path in paths:
        if not path.exists():
            continue
        match = re.search(
            r"(?im)^tradingMode\s*=\s*([pl])\s*$",
            path.read_text(encoding="utf-8", errors="replace"),
        )
        if match:
            modes.append(match.group(1).lower())
    return (modes[0] if modes else "unknown", bool(modes) and set(modes) == {"p"})


def _market_behavior(quotes: Sequence[object]) -> str:
    if not any(
        getattr(quote, field, None) is not None
        for quote in quotes
        for field in ("bid", "ask", "last")
    ):
        return "UNAVAILABLE"
    types = {getattr(quote, "market_data_type", None) for quote in quotes}
    types.discard(None)
    if not types:
        return "UNAVAILABLE"
    if types <= {1}:
        return "REALTIME"
    if types <= {3, 4}:
        return "DELAYED"
    return "MIXED"


def _required_summary_complete(summary: dict[str, str]) -> bool:
    return {
        "TotalCashValue",
        "BuyingPower",
        "NetLiquidation",
    }.issubset(summary) and _settled_cash(summary) is not None


def _settled_cash(summary: dict[str, str]) -> str | None:
    direct = summary.get("SettledCash")
    if direct:
        return direct
    dated = summary.get("SettledCashByDate", "")
    match = re.fullmatch(r"\d{8}:([-+]?\d+(?:\.\d+)?)", dated)
    return match.group(1) if match else None


def _redacted_errors(errors: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "request_id": item.get("request_id"),
            "code": item.get("code"),
            "message": redact_text(str(item.get("message", ""))),
        }
        for item in errors
    ]


def build_capability_matrix(
    readonly_report: dict[str, object],
    real_codex_report: dict[str, object] | None = None,
    auditor_report: dict[str, object] | None = None,
) -> str:
    real_codex_report = real_codex_report or {}
    auditor_report = auditor_report or {}
    readonly_status = (
        "AVAILABLE" if readonly_report.get("status") == "PASS" else "UNAVAILABLE"
    )
    readonly_evidence = ", ".join(readonly_report.get("reason_codes", [])) or "PASS"
    rows = (
        ("Local deterministic infrastructure", "AVAILABLE", "Scoped test suite"),
        ("Fake broker lifecycle", "AVAILABLE", "Fake and fault suites"),
        ("Real IBKR read-only identity", readonly_status, readonly_evidence),
        ("Real IBKR order writes", "UNAVAILABLE", "Hard-disabled by authorization"),
        ("Test order lifecycle", "UNAVAILABLE", "Not authorized"),
        (
            "Real Codex Trader invocation",
            "AVAILABLE" if real_codex_report.get("gate") == "PASS" else "UNAVAILABLE",
            "Synthetic non-trading provider receipt",
        ),
        (
            "Auditor OS isolation",
            "AVAILABLE" if auditor_report.get("gate") == "PASS" else "UNAVAILABLE",
            ", ".join(auditor_report.get("reason_codes", [])) or "Not proven",
        ),
        ("30-day experiment start", "UNAVAILABLE", "Owner authorization required"),
    )
    lines = [
        "# IBKR Capability Matrix V1",
        "",
        "| Capability | Status | Evidence |",
        "|---|---|---|",
    ]
    lines.extend(f"| {name} | {status} | {evidence} |" for name, status, evidence in rows)
    lines.extend(
        (
            "",
            "`AUTONOMOUS_TRADING_STATUS=BLOCKED`",
            "",
            "No real broker order submission, cancellation, or modification is authorized.",
        )
    )
    return "\n".join(lines) + "\n"


def build_implementation_status(
    *,
    test_count: int,
    test_failures: int,
    readonly_report: dict[str, object] | None = None,
    alert_report: dict[str, object] | None = None,
    real_codex_report: dict[str, object] | None = None,
    auditor_report: dict[str, object] | None = None,
    auditor_v2_evaluation: AuditorGateV2Evaluation | None = None,
    implementation_head: str = "",
) -> dict[str, object]:
    local_pass = test_failures == 0 and test_count > 0
    readonly_report = readonly_report or {}
    alert_report = alert_report or {}
    real_codex_report = real_codex_report or {}
    auditor_report = auditor_report or {}
    auditor_v2_evaluation = auditor_v2_evaluation or AuditorGateV2Evaluation(
        canonical_gate="BLOCK",
        compatibility_gate="BLOCK",
        gate_version="V2",
        reason_codes=("V2_RECEIPT_NOT_VALIDATED",),
    )
    alert_events = {
        result.get("event_type")
        for result in alert_report.get("results", [])
        if isinstance(result, dict)
    }
    required_alert_events = {
        "BROKER_2FA_REAUTH_REQUIRED",
        "KILL_SWITCH_TRIGGERED",
        "BROKER_HEARTBEAT_TIMEOUT",
    }
    owner_alert_gate = (
        "PASS"
        if alert_report.get("gate") == "PASS"
        and required_alert_events.issubset(alert_events)
        else "BLOCK"
    )
    identity_gate = (
        "PASS"
        if readonly_report.get("real_ibkr_read_only_identity_gate") == "PASS"
        else "BLOCK"
    )
    paper_identity_gate = (
        "PASS"
        if readonly_report.get("paper_account_identity_gate") == "PASS"
        else "BLOCK"
    )
    reconciliation_gate = (
        "PASS"
        if readonly_report.get("broker_reconciliation_gate") == "PASS"
        else "BLOCK"
    )
    codex_gate = "PASS" if real_codex_report.get("gate") == "PASS" else "BLOCK"
    auditor_gate = (
        "PASS"
        if auditor_v2_evaluation.canonical_gate == "PASS"
        and auditor_v2_evaluation.compatibility_gate == "PASS"
        else "BLOCK"
    )
    market_policy_frozen = bool(
        readonly_report.get("market_data_policy_frozen", False)
    )
    two_factor_validated = (
        local_pass and "BROKER_2FA_REAUTH_REQUIRED" in alert_events
    )
    unresolved = []
    checks = (
        ("PAPER_ACCOUNT_IDENTITY_GATE", paper_identity_gate == "PASS"),
        ("REAL_IBKR_READ_ONLY_IDENTITY_GATE", identity_gate == "PASS"),
        ("BROKER_RECONCILIATION_GATE", reconciliation_gate == "PASS"),
        ("MARKET_DATA_POLICY_FROZEN", market_policy_frozen),
        ("TRADER_INVOCATION_REAL_CODEX_GATE", codex_gate == "PASS"),
        ("AUDITOR_ISOLATION_GATE", auditor_gate == "PASS"),
        ("OWNER_ALERT_GATE", owner_alert_gate == "PASS"),
        ("2FA_STATE_MACHINE_VALIDATED", two_factor_validated),
    )
    unresolved.extend(name for name, passed in checks if not passed)
    return {
        "schema": "CODEX_IBKR_PAPER_IMPLEMENTATION_STATUS_V1",
        "IMPLEMENTATION_HEAD": implementation_head,
        "TEST_COUNT": test_count,
        "PASS": test_count - test_failures,
        "FAIL": test_failures,
        "FAKE_BROKER_SUITE": "PASS" if local_pass else "BLOCK",
        "STATE_MACHINE_GATE": "PASS" if local_pass else "BLOCK",
        "EXECUTION_LOCK_GATE": "PASS" if local_pass else "BLOCK",
        "RISK_ENGINE_GATE": "PASS" if local_pass else "BLOCK",
        "SUBLEDGER_GATE": "PASS" if local_pass else "BLOCK",
        "PRETRADE_FREEZE_GATE": "PASS" if local_pass else "BLOCK",
        "TRADER_INVOCATION_LOCAL_GATE": "PASS" if local_pass else "BLOCK",
        "TRADER_INVOCATION_REAL_CODEX_GATE": codex_gate,
        "MARKET_DATA_GATE": "PASS" if market_policy_frozen else "BLOCK",
        "ALERT_GATE": (
            "PASS" if alert_report.get("gate") == "PASS" else "BLOCK"
        ),
        "OWNER_ALERT_GATE": owner_alert_gate,
        "ORCHESTRATOR_GATE": "PASS" if local_pass else "BLOCK",
        "RECOVERY_GATE": "PASS" if local_pass else "BLOCK",
        "AUDITOR_LEAST_PRIVILEGE_AND_RUNTIME_INTEGRITY_GATE_V2": auditor_gate,
        "AUDITOR_ISOLATION_GATE_V2": auditor_gate,
        "AUDITOR_ISOLATION_GATE": auditor_gate,
        "AUDITOR_GATE_VERSION": "V2",
        "AUDITOR_V2_REASON_CODES": list(auditor_v2_evaluation.reason_codes),
        "AUDITOR_TECHNICAL_SOCKET_REACHABILITY": True,
        "AUDITOR_NETWORK_ISOLATION_REQUIRED": False,
        "AUDITOR_UNAUTHORIZED_RAW_API_PATH_POSSIBLE": True,
        "AUDITOR_COMPROMISE_CONTAINMENT_NOT_CLAIMED": True,
        "LEGACY_FIREWALL_CONTROL": "INEFFECTIVE_FOR_LOOPBACK_REQUIREMENT",
        "WFP_AUDITOR_FRONT": "DEFERRED",
        "FAULT_INJECTION_GATE": "PASS" if local_pass else "BLOCK",
        "IBKR_GATEWAY_RUNNING": bool(
            readonly_report.get("heartbeat_ok")
            and readonly_report.get("status") in {"PASS", "PARTIAL"}
        ),
        "PAPER_IDENTITY_PROVEN": paper_identity_gate == "PASS",
        "EXPECTED_ACCOUNT_IDENTITY_BOUND": bool(
            readonly_report.get("expected_account_identity_bound", False)
        ),
        "REAL_IBKR_READ_ONLY_IDENTITY_GATE": identity_gate,
        "PAPER_ACCOUNT_IDENTITY_GATE": paper_identity_gate,
        "BROKER_RECONCILIATION_GATE": reconciliation_gate,
        "MARKET_DATA_POLICY_FROZEN": market_policy_frozen,
        "2FA_STATE_MACHINE_VALIDATED": two_factor_validated,
        "UNRESOLVED_BLOCKERS": unresolved,
        "READY_FOR_HARMLESS_PAPER_LIFECYCLE_TEST": False,
        "REAL_PAPER_ORDER_WRITE_AUTHORIZED": False,
        "TEST_ORDER_AUTHORIZED": False,
        "DIRECTIONAL_TRADING_AUTHORIZED": False,
        "LIVE_ALLOWED": False,
        "REAL_MONEY_ALLOWED": False,
        "AUTONOMOUS_TRADING_STATUS": "BLOCKED",
    }


def invoke_real_codex_test(
    *,
    model: str,
    reasoning_effort: str,
    timeout_seconds: int,
) -> dict[str, object]:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    run_id = uuid4().hex
    cycle_id = f"real-codex-test-{run_id}"
    invocation_id = f"invocation-{run_id}"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    bundle = TraderInputBundle(
        decision_cycle_id=cycle_id,
        utc_timestamp=now,
        market_session_state="SYNTHETIC_NON_TRADING",
        reconciliation_receipt={"status": "SYNTHETIC", "sha256": "r" * 64},
        experiment_subledger_snapshot={"equity": "500.00", "synthetic": True},
        broker_account_snapshot={"synthetic": True, "account_identity": None},
        positions_snapshot=[],
        open_orders_snapshot=[],
        risk_snapshot={"status": "BLOCK", "order_authority": False},
        kill_switch_state="KILL_SWITCH_TRIGGERED",
        market_data_snapshot={"gate_status": "PASS", "synthetic": True},
        candidate_screen_results=[],
        relevant_previous_immutable_decisions=[],
        process_policy_version="PROCESS_TEST_V1",
        execution_realism_version="NON_EXECUTABLE_TEST_V1",
        benchmark_state={"synthetic": True},
    )
    request = InvocationRequest(
        decision_cycle_id=cycle_id,
        invocation_id=invocation_id,
        utc_timestamp=now,
        requested_model=model,
        actual_model=model,
        model_configuration={"provider": "codex-cli", "synthetic": True},
        reasoning_effort=reasoning_effort,
        input_bundle_sha256=bundle.sha256,
        risk_policy_version="CAPITAL_BOUNDARY_V2",
        experiment_id="prelifecycle-provider-test",
        invocation_trigger="OWNER_AUTHORIZED_NON_TRADING_TEST",
        timeout_seconds=timeout_seconds,
    )
    provider = CodexCLIProvider()
    database = Database.open(REPORT_ROOT / "real_codex_invocations.sqlite3")
    try:
        adapter = TraderInvocationAdapter(database, provider)
        result = adapter.invoke(request, bundle)
    finally:
        database.close()
    gate = (
        "PASS"
        if result.accepted
        and result.effective_decision == "NO_TRADE"
        and result.order_authority is False
        and adapter.real_codex_gate_status == "PASS"
        and not provider.last_tool_activity_detected
        else "BLOCK"
    )
    report = {
        "schema": "CODEX_TRADER_INVOCATION_REAL_V1",
        "gate": gate,
        "requested_model": model,
        "actual_model": model,
        "reasoning_effort": reasoning_effort,
        "input_bundle_sha256": bundle.sha256,
        "decision_cycle_id": cycle_id,
        "invocation_id": invocation_id,
        "structured_output_valid": result.validation == "PASS",
        "effective_decision": result.effective_decision,
        "reason_codes": list(result.reason_codes),
        "order_authority": result.order_authority,
        "tool_activity_detected": provider.last_tool_activity_detected,
        "provider_event_count": provider.last_event_count,
        "provider_failure_code": provider.last_failure_code,
        "provider_failure_detail": provider.last_failure_detail,
        "provider_failure_diagnostic": provider.last_failure_diagnostic,
        "broker_access": False,
        "execution_lock_access": False,
    }
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    report["secret_scan"] = "PASS" if redact_text(encoded) == encoded else "BLOCK"
    if report["secret_scan"] != "PASS":
        report["gate"] = "BLOCK"
    _atomic_json(REAL_CODEX_REPORT, report)
    return report


def invoke_autonomous_research_cycle(
    *,
    host: str,
    port: int,
    model: str,
    reasoning_effort: str,
    timeout_seconds: int,
    experiment_equity: Decimal,
    experiment_start_utc: str,
    market_session_state: str,
) -> dict[str, object]:
    """
    Run one real multi-round Codex research/decision cycle against the paper
    broker's read-only/research surface.  No order is submitted by this command.
    """
    readonly = _read_json(READONLY_REPORT)
    market_validation = _read_json(MARKET_VALIDATION_REPORT)
    reasons: list[str] = []
    if readonly.get("paper_account_identity_gate") != "PASS":
        reasons.append("PAPER_ACCOUNT_IDENTITY_GATE")
    if readonly.get("broker_reconciliation_gate") != "PASS":
        reasons.append("BROKER_RECONCILIATION_GATE")
    if market_validation.get("market_data_gate") != "PASS":
        reasons.append("MARKET_DATA_GATE")
    if reasons:
        report = {
            "schema": "AUTONOMOUS_RESEARCH_CYCLE_REPORT_V1",
            "status": "BLOCK",
            "reason_codes": reasons,
            "order_authority": False,
            "real_order_writes_attempted": 0,
        }
        _atomic_json(AUTONOMOUS_RESEARCH_REPORT, report)
        return report

    toolbox = IBKRResearchToolbox(
        host=host,
        port=port,
        options_permission_level=4,
        timeout_seconds=float(timeout_seconds),
    )
    database = Database.open(REPORT_ROOT / "autonomous_trader.sqlite3")
    try:
        runtime = AutonomousDecisionRuntime(
            db=database,
            toolbox=toolbox,
            model=model,
            reasoning_effort=reasoning_effort,
            timeout_seconds=timeout_seconds,
            max_research_rounds=8,
        )
        result = runtime.run_cycle(
            readonly_report=readonly,
            experiment_equity=experiment_equity,
            experiment_start_utc=experiment_start_utc,
            market_data_gate="PASS",
            market_session_state=market_session_state,
        )
    finally:
        database.close()

    report = {
        "schema": "AUTONOMOUS_RESEARCH_CYCLE_REPORT_V1",
        "status": "PASS" if result.accepted else "BLOCK",
        **result.model_dump(mode="json"),
        "configured_options_permission_level": 4,
        "strategy_allowlist": None,
        "symbol_allowlist": None,
        "timeframe_allowlist": None,
        "fixed_percentage_risk_limits": False,
        "real_order_writes_attempted": 0,
    }
    _atomic_json(AUTONOMOUS_RESEARCH_REPORT, report)
    return report


def simulate_alerts(events: Sequence[str]) -> dict[str, object]:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    smtp = load_smtp_channel(Path("Secrets/email_alerts.env"))
    event_log = WindowsEventLogChannel()
    database = Database.open(REPORT_ROOT / "alert_simulation.sqlite3")
    authority = InMemoryAuthority()
    service = AlertService(AlertRepository(database), authority, smtp, event_log)
    run_id = uuid4().hex
    results = []
    for index, event_type in enumerate(events):
        correlation_id = f"simulation-{run_id}-{index}"
        result = service.raise_critical(
            AlertEvent(
                event_type=event_type,
                correlation_id=correlation_id,
                occurred_at_utc=datetime.now(timezone.utc),
                detail="Synthetic authorized delivery simulation; no broker action.",
            )
        )
        event_log_verified = event_log.verify_alert(f"alert-{correlation_id}")
        results.append(
            {
                **asdict(result),
                "event_type": event_type,
                "windows_event_log_query_verified": event_log_verified,
            }
        )
    database.close()
    gate = "PASS" if all(
        result["local_status"] == "CONFIRMED"
        and result["external_status"] == "CONFIRMED"
        and result["windows_event_log_query_verified"]
        for result in results
    ) else "BLOCK"
    report = {
        "schema": "OWNER_CRITICAL_ALERT_DELIVERY_SIMULATION_V1",
        "gate": gate,
        "new_order_authority": authority.new_order_authority,
        "broker_calls_made": 0,
        "results": results,
    }
    _atomic_json(ALERT_REPORT, report)
    return report


def _port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_auditor_v2_evaluation(
    receipt_path: Path = AUDITOR_V2_RECEIPT,
) -> tuple[AuditorGateV2Evaluation, PaperIdentityBinding | None]:
    now = datetime.now(timezone.utc)
    if not receipt_path.is_file():
        return load_and_evaluate_auditor_gate_v2(receipt_path, object(), now), None
    try:
        readonly_bytes = READONLY_REPORT.read_bytes()
        binding = PaperIdentityBinding.from_readonly_receipt(
            json.loads(readonly_bytes), readonly_bytes
        )
        binding = replace(
            binding,
            runtime_manifest_sha256=os.environ.get(
                "AUDITOR_RUNTIME_MANIFEST_V2_SHA256"
            ),
            deployment_manifest_sha256=os.environ.get(
                "AUDITOR_RUNTIME_DEPLOYMENT_MANIFEST_V2_SHA256"
            ),
            probe_sha256=os.environ.get("AUDITOR_GATE_V2_PROBE_SHA256"),
            probe_manifest_sha256=os.environ.get(
                "AUDITOR_PROBE_TARGET_MANIFEST_SHA256"
            ),
        )
    except (OSError, json.JSONDecodeError, IdentityBindingError) as exc:
        return (
            AuditorGateV2Evaluation(
                "BLOCK",
                "BLOCK",
                "V2",
                (f"PAPER_BINDING_INVALID:{type(exc).__name__}",),
            ),
            None,
        )
    return load_and_evaluate_auditor_gate_v2(receipt_path, binding, now), binding


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_auditor_v2_artifacts(
    *,
    receipt_path: Path = AUDITOR_V2_RECEIPT,
    report_path: Path = AUDITOR_V2_REPORT,
    acceptance_path: Path = AUDITOR_V2_ACCEPTANCE,
) -> dict[str, object]:
    evaluation, _ = _load_auditor_v2_evaluation(receipt_path)
    receipt = None
    evidence: dict[str, object] = {}
    if receipt_path.is_file():
        raw = receipt_path.read_bytes()
        evidence["receipt"] = {
            "path": str(receipt_path),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        if evaluation.canonical_gate == "PASS":
            receipt = parse_auditor_gate_v2_receipt(raw)
    report = render_auditor_gate_v2_report(receipt, evaluation, evidence)
    _atomic_text(report_path, report)
    acceptance_created = False
    if receipt is not None:
        acceptance = build_residual_risk_acceptance(
            receipt,
            evaluation,
            {
                "decision": "OWNER_AUTHORIZATION_IMPLEMENT_AUDITOR_GATE_V2",
                "design_commit": "322a79cb",
                "plan_commit": "7e8d4689",
                "month1_paper_only": True,
            },
        )
        write_immutable_json(acceptance_path, acceptance)
        acceptance_created = True
    return {
        "gate": evaluation.canonical_gate,
        "gate_version": "V2",
        "reason_codes": list(evaluation.reason_codes),
        "report_path": str(report_path),
        "acceptance_created": acceptance_created,
    }


def _junit_counts(path: Path) -> tuple[int, int]:
    root = ET.parse(path).getroot()
    nodes = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    tests = sum(int(node.attrib.get("tests", 0)) for node in nodes)
    failures = sum(
        int(node.attrib.get("failures", 0)) + int(node.attrib.get("errors", 0))
        for node in nodes
    )
    return tests, failures


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ibkr-paper-30d")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_parser = commands.add_parser("inspect-ibkr-readonly")
    inspect_parser.add_argument("--host", default="127.0.0.1")
    inspect_parser.add_argument("--port", type=int, default=4002)
    alert_parser = commands.add_parser("simulate-alerts")
    alert_parser.add_argument("--events", nargs="+", required=True)
    commands.add_parser("write-capability-matrix")
    commands.add_parser("write-implementation-status")
    auditor_v2_parser = commands.add_parser("write-auditor-v2-artifacts")
    auditor_v2_parser.add_argument("--receipt", type=Path, default=AUDITOR_V2_RECEIPT)
    auditor_v2_parser.add_argument("--report", type=Path, default=AUDITOR_V2_REPORT)
    auditor_v2_parser.add_argument(
        "--acceptance", type=Path, default=AUDITOR_V2_ACCEPTANCE
    )
    commands.add_parser("write-local-reports")
    commands.add_parser("probe-auditor-isolation")
    codex_parser = commands.add_parser("invoke-real-codex-test")
    codex_parser.add_argument("--model", default="gpt-5.5")
    codex_parser.add_argument("--reasoning-effort", default="medium")
    codex_parser.add_argument("--timeout-seconds", type=int, default=120)
    autonomous_parser = commands.add_parser("invoke-autonomous-research-cycle")
    autonomous_parser.add_argument("--host", default="127.0.0.1")
    autonomous_parser.add_argument("--port", type=int, default=4002)
    autonomous_parser.add_argument("--model", default="gpt-5.5")
    autonomous_parser.add_argument("--reasoning-effort", default="high")
    autonomous_parser.add_argument("--timeout-seconds", type=int, default=180)
    autonomous_parser.add_argument("--equity", type=Decimal, default=Decimal("500.00"))
    autonomous_parser.add_argument("--experiment-start-utc", required=True)
    autonomous_parser.add_argument("--market-session", default="REGULAR")
    observe_parser = commands.add_parser("observe-market-data")
    observe_parser.add_argument("--host", default="127.0.0.1")
    observe_parser.add_argument("--port", type=int, default=4002)
    observe_parser.add_argument("--symbols", nargs="+", default=["SPY", "QQQ", "IEF"])
    observe_parser.add_argument("--cadence-seconds", type=float, default=5)
    observe_parser.add_argument("--window-seconds", type=float, default=300)
    freeze_parser = commands.add_parser("freeze-market-policy")
    freeze_parser.add_argument("--ledger", type=Path, default=MARKET_LEDGER)
    freeze_parser.add_argument("--destination", type=Path, default=MARKET_POLICY)
    validate_parser = commands.add_parser("validate-real-market-data")
    validate_parser.add_argument("--host", default="127.0.0.1")
    validate_parser.add_argument("--port", type=int, default=4002)
    validate_parser.add_argument("--policy", type=Path, default=MARKET_POLICY)
    args = parser.parse_args(argv)

    if args.command == "inspect-ibkr-readonly":
        report = inspect_readonly(
            host=args.host,
            port=args.port,
            expected_account_hash=os.environ.get("IBKR_PAPER_ACCOUNT_SHA256"),
        )
    elif args.command == "simulate-alerts":
        report = simulate_alerts(args.events)
    elif args.command == "invoke-real-codex-test":
        report = invoke_real_codex_test(
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            timeout_seconds=args.timeout_seconds,
        )
    elif args.command == "invoke-autonomous-research-cycle":
        report = invoke_autonomous_research_cycle(
            host=args.host,
            port=args.port,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            timeout_seconds=args.timeout_seconds,
            experiment_equity=args.equity,
            experiment_start_utc=args.experiment_start_utc,
            market_session_state=args.market_session,
        )
    elif args.command == "observe-market-data":
        report = observe_market_data(
            readonly_report=_read_json(READONLY_REPORT),
            source=IBKRMarketDataSource(host=args.host, port=args.port),
            expected_account_hash=_configured_paper_account_hash(),
            symbols=args.symbols,
            cadence_seconds=args.cadence_seconds,
            window_seconds=args.window_seconds,
        )
    elif args.command == "freeze-market-policy":
        report = freeze_market_policy(
            args.ledger,
            args.destination,
            output_path=MARKET_POLICY_REPORT,
        )
    elif args.command == "validate-real-market-data":
        report = validate_real_market_data(
            readonly_report=_read_json(READONLY_REPORT),
            policy_path=args.policy,
            source=IBKRMarketDataSource(host=args.host, port=args.port),
            expected_account_hash=_configured_paper_account_hash(),
        )
    elif args.command == "probe-auditor-isolation":
        report = write_isolation_report(
            secrets_dir=Path("Secrets"),
            live_db=REPORT_ROOT / "real_codex_invocations.sqlite3",
            output_path=AUDITOR_REPORT,
            provisioning_status="ACCESS_DENIED_NON_ADMIN",
        )
    elif args.command == "write-capability-matrix":
        report = _read_json(READONLY_REPORT)
        CAPABILITY_MATRIX.write_text(
            build_capability_matrix(
                report,
                _read_json(REAL_CODEX_REPORT),
                _read_json(AUDITOR_REPORT),
            ),
            encoding="utf-8",
            newline="\n",
        )
        print(str(CAPABILITY_MATRIX))
        return 0
    elif args.command == "write-auditor-v2-artifacts":
        report = write_auditor_v2_artifacts(
            receipt_path=args.receipt,
            report_path=args.report,
            acceptance_path=args.acceptance,
        )
    elif args.command == "write-implementation-status":
        tests, failures = _junit_counts(REPORT_ROOT / "pytest.xml")
        auditor_v2_evaluation, _ = _load_auditor_v2_evaluation()
        report = build_implementation_status(
            test_count=tests,
            test_failures=failures,
            readonly_report=_read_json(READONLY_REPORT),
            alert_report=_read_json(ALERT_REPORT),
            real_codex_report=_read_json(REAL_CODEX_REPORT),
            auditor_report=_read_json(AUDITOR_REPORT),
            auditor_v2_evaluation=auditor_v2_evaluation,
            implementation_head=os.environ.get("IMPLEMENTATION_HEAD", ""),
        )
        _atomic_json(GATE_REPORT, report)
    else:
        junit = REPORT_ROOT / "pytest.xml"
        harness = FaultInjectionHarness(REPORT_ROOT / "fault_evidence.jsonl")
        results = [harness.run(name) for name in FAULT_SCENARIOS]
        receipts = write_local_reports(
            REPORT_ROOT,
            fault_results=results,
            security_boundaries={
                "real_broker_writes": "HARD_DISABLED",
                "auditor_isolation": "BLOCK_OS_DENIALS_UNPROVEN",
            },
            test_evidence_path=junit,
        )
        report = asdict(receipts)
    print(json.dumps(report, sort_keys=True, default=str))
    return 0


def _configured_paper_account_hash() -> str | None:
    configured = os.environ.get("IBKR_PAPER_ACCOUNT_SHA256")
    if configured:
        return configured
    store = ExpectedPaperIdentityStore(
        Path("Secrets/expected_paper_account_identity_v1.json")
    )
    return store.load_hash() if store.path.exists() else None


if __name__ == "__main__":
    raise SystemExit(main())
