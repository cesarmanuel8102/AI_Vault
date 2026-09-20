from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import xml.etree.ElementTree as ET
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from uuid import uuid4

from .alerts import (
    AlertEvent,
    AlertRepository,
    AlertService,
    InMemoryAuthority,
    WindowsEventLogChannel,
    load_smtp_channel,
)
from .persistence import Database
from .reporting import FAULT_SCENARIOS, FaultInjectionHarness, write_local_reports


REPORT_ROOT = Path("state/ibkr_paper_30d/reports")
READONLY_REPORT = REPORT_ROOT / "read_only_real_paper_reconciliation.json"
ALERT_REPORT = REPORT_ROOT / "alert_delivery_simulation.json"
GATE_REPORT = REPORT_ROOT / "updated_gate_matrix.json"
CAPABILITY_MATRIX = Path("IBKR_CAPABILITY_MATRIX_V1.md")


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
    if not expected_account_hash:
        reasons.append("EXPECTED_ACCOUNT_IDENTITY_NOT_CONFIGURED")
    if not _port_is_open(host, port):
        reasons.append("GATEWAY_UNAVAILABLE")
    if not reasons:
        reasons.append("SAFE_READ_ONLY_SESSION_CAPTURE_UNAVAILABLE")
    report = {
        "schema": "IBKR_READ_ONLY_RECONCILIATION_V1",
        "status": "BLOCK",
        "host": host,
        "port": port,
        "reason_codes": reasons,
        "gateway_started_by_codex": False,
        "broker_calls_made": 0,
        "raw_account_identity_persisted": False,
        "real_order_writes_attempted": 0,
    }
    _atomic_json(Path(output_path), report)
    return report


def build_capability_matrix(readonly_report: dict[str, object]) -> str:
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
        ("Real Codex Trader invocation", "UNKNOWN", "Not tested"),
        ("Auditor OS isolation", "PARTIAL", "Restricted token and ACLs unproven"),
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
) -> dict[str, object]:
    local_pass = test_failures == 0 and test_count > 0
    return {
        "schema": "CODEX_IBKR_PAPER_IMPLEMENTATION_STATUS_V1",
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
        "TRADER_INVOCATION_REAL_CODEX_GATE": "NOT_TESTED",
        "MARKET_DATA_GATE": "PASS" if local_pass else "BLOCK",
        "ALERT_GATE": (
            "PASS" if alert_report and alert_report.get("gate") == "PASS" else "BLOCK"
        ),
        "ORCHESTRATOR_GATE": "PASS" if local_pass else "BLOCK",
        "AUDITOR_ISOLATION_GATE": "BLOCK",
        "FAULT_INJECTION_GATE": "PASS" if local_pass else "BLOCK",
        "REAL_IBKR_READ_ONLY_IDENTITY_GATE": (
            "PASS"
            if readonly_report and readonly_report.get("status") == "PASS"
            else "BLOCK"
        ),
        "BROKER_RECONCILIATION_GATE": "PASS" if local_pass else "BLOCK",
        "REAL_PAPER_ORDER_WRITE_AUTHORIZED": False,
        "TEST_ORDER_AUTHORIZED": False,
        "DIRECTIONAL_TRADING_AUTHORIZED": False,
        "LIVE_ALLOWED": False,
        "REAL_MONEY_ALLOWED": False,
        "AUTONOMOUS_TRADING_STATUS": "BLOCKED",
    }


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
    commands.add_parser("write-local-reports")
    args = parser.parse_args(argv)

    if args.command == "inspect-ibkr-readonly":
        report = inspect_readonly(
            host=args.host,
            port=args.port,
            expected_account_hash=os.environ.get("IBKR_PAPER_ACCOUNT_SHA256"),
        )
    elif args.command == "simulate-alerts":
        report = simulate_alerts(args.events)
    elif args.command == "write-capability-matrix":
        report = _read_json(READONLY_REPORT)
        CAPABILITY_MATRIX.write_text(
            build_capability_matrix(report), encoding="utf-8", newline="\n"
        )
        print(str(CAPABILITY_MATRIX))
        return 0
    elif args.command == "write-implementation-status":
        tests, failures = _junit_counts(REPORT_ROOT / "pytest.xml")
        report = build_implementation_status(
            test_count=tests,
            test_failures=failures,
            readonly_report=_read_json(READONLY_REPORT),
            alert_report=_read_json(ALERT_REPORT),
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


if __name__ == "__main__":
    raise SystemExit(main())
