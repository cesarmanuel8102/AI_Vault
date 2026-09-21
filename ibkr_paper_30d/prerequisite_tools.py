from __future__ import annotations

import argparse
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path

from .auditor_export import AuditExporter


def create_audit_export(
    readonly_report: Path,
    export_root: Path,
) -> dict[str, str]:
    raw = readonly_report.read_bytes()
    payload = json.loads(raw)
    if payload.get("schema") != "REAL_IBKR_READ_ONLY_RECONCILIATION_V1":
        raise ValueError("READONLY_RECEIPT_SCHEMA_INVALID")
    if payload.get("status") != "PASS":
        raise ValueError("READONLY_RECEIPT_NOT_PASS")
    required = (
        "paper_account_identity_gate",
        "real_ibkr_read_only_identity_gate",
        "broker_reconciliation_gate",
    )
    if any(payload.get(name) != "PASS" for name in required):
        raise ValueError("READONLY_RECEIPT_GATES_NOT_PASS")

    export_root.mkdir(parents=True, exist_ok=True)
    context = {
        "schema": "AUDITOR_GATE_V2_FUNCTIONAL_CONTEXT_V1",
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "readonly_receipt_sha256": __import__("hashlib").sha256(raw).hexdigest(),
        "paper_only": True,
        "live_allowed": False,
        "real_money_allowed": False,
    }
    receipt = AuditExporter(export_root).publish(
        {
            "paper_identity.json": payload,
            "functional_context.json": context,
        }
    )

    identity_copy = export_root / "paper_identity_receipt.json"
    if identity_copy.exists():
        identity_copy.chmod(stat.S_IREAD | stat.S_IWRITE)
        identity_copy.unlink()
    identity_copy.write_bytes(raw)
    identity_copy.chmod(stat.S_IREAD)

    result = {
        "bundle_id": receipt.bundle_id,
        "bundle_path": str(receipt.path.resolve()),
        "manifest_sha256": receipt.manifest_sha256,
        "paper_identity_receipt_path": str(identity_copy.resolve()),
        "paper_identity_receipt_sha256": context["readonly_receipt_sha256"],
    }
    return result


def readiness(report_root: Path) -> dict[str, object]:
    auditor_receipt = report_root / "auditor_gate_v2_receipt.json"
    market_policy = report_root / "market_data_policy_v1.json"
    market_validation = report_root / "market_data_validation.json"

    auditor = None
    if auditor_receipt.is_file():
        try:
            auditor = json.loads(auditor_receipt.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            auditor = None
    market = None
    if market_validation.is_file():
        try:
            market = json.loads(market_validation.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            market = None

    return {
        "schema": "IBKR_AUTONOMOUS_PREREQUISITE_READINESS_V1",
        "auditor_receipt_present": auditor is not None,
        "auditor_receipt_schema": auditor.get("schema") if auditor else None,
        "market_policy_present": market_policy.is_file(),
        "market_validation_present": market is not None,
        "market_data_gate": market.get("market_data_gate") if market else None,
        "prerequisites_structurally_present": (
            auditor is not None
            and market_policy.is_file()
            and market is not None
            and market.get("market_data_gate") == "PASS"
        ),
        "paper_execution_armed": os.environ.get(
            "IBKR_AUTONOMOUS_PAPER_ARMED", "false"
        ).lower()
        == "true",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ibkr_paper_30d.prerequisite_tools")
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("create-audit-export")
    audit.add_argument("--readonly-report", type=Path, required=True)
    audit.add_argument("--export-root", type=Path, required=True)

    ready = sub.add_parser("readiness")
    ready.add_argument(
        "--report-root",
        type=Path,
        default=Path("state/ibkr_paper_30d/reports"),
    )

    args = parser.parse_args(argv)
    if args.command == "create-audit-export":
        result = create_audit_export(args.readonly_report, args.export_root)
    else:
        result = readiness(args.report_root)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
