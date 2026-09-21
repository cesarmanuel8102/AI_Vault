from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .auditor_export import AuditExporter
from .auditor_gate_v2 import (
    PaperIdentityBinding,
    load_and_evaluate_auditor_gate_v2,
)



def _git_blob(repo_root: Path, commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{commit}:{path}"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"TRUST_ANCHOR_GIT_BLOB_UNAVAILABLE:{path}")
    return result.stdout


def _manifest_text(schema: str, hashes: dict[str, str]) -> bytes:
    files_json = json.dumps(
        {key: hashes[key] for key in sorted(hashes)},
        separators=(",", ":"),
        ensure_ascii=True,
    )
    body = f'{{"files":{files_json},"schema":"{schema}"}}'
    manifest_hash = __import__("hashlib").sha256(body.encode("utf-8")).hexdigest()
    return (
        f'{{"files":{files_json},"manifest_sha256":"{manifest_hash}","schema":"{schema}"}}'
    ).encode("utf-8")


def evaluate_runtime_trust_anchor(
    repo_root: Path,
    anchor_path: Path,
) -> dict[str, object]:
    anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
    if anchor.get("schema") != "AUDITOR_RUNTIME_V2_TRUST_ANCHOR_V1":
        raise ValueError("TRUST_ANCHOR_SCHEMA_INVALID")
    commit = str(anchor.get("source_commit") or "")
    files = list(anchor.get("runtime_files") or [])
    manifest_name = str(anchor.get("runtime_manifest_name") or "")
    if not commit or len(commit) != 40 or not files or not manifest_name:
        raise ValueError("TRUST_ANCHOR_INVALID")

    ancestor = subprocess.run(
        ["git", "-C", str(repo_root), "merge-base", "--is-ancestor", commit, "HEAD"],
        capture_output=True,
        check=False,
    )
    if ancestor.returncode != 0:
        raise ValueError("TRUST_ANCHOR_COMMIT_NOT_ANCESTOR")

    payload_hashes: dict[str, str] = {}
    source_matches = True
    for name in files:
        blob = _git_blob(repo_root, commit, f"auditor_runtime/{name}")
        digest = __import__("hashlib").sha256(blob).hexdigest()
        payload_hashes[name] = digest
        current = repo_root / "auditor_runtime" / name
        if not current.is_file() or __import__("hashlib").sha256(current.read_bytes()).hexdigest() != digest:
            source_matches = False

    runtime_text = _manifest_text("AUDITOR_RUNTIME_MANIFEST_V2", payload_hashes)
    deployment_hashes = dict(payload_hashes)
    deployment_hashes[manifest_name] = __import__("hashlib").sha256(runtime_text).hexdigest()
    deployment_text = _manifest_text(
        "AUDITOR_RUNTIME_DEPLOYMENT_MANIFEST_V2", deployment_hashes
    )
    anchor_sha = __import__("hashlib").sha256(anchor_path.read_bytes()).hexdigest()
    return {
        "schema": "AUDITOR_RUNTIME_V2_TRUST_ANCHOR_EVALUATION_V1",
        "source_commit": commit,
        "anchor_sha256": anchor_sha,
        "source_matches_anchor": source_matches,
        "payload_sha256": payload_hashes,
        "runtime_manifest_sha256": __import__("hashlib").sha256(runtime_text).hexdigest(),
        "deployment_manifest_sha256": __import__("hashlib").sha256(deployment_text).hexdigest(),
    }

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


def evaluate_auditor(
    receipt_path: Path,
    readonly_report: Path,
    runtime_manifest_sha256: str,
    deployment_manifest_sha256: str,
    probe_sha256: str,
    probe_manifest_sha256: str,
) -> dict[str, object]:
    readonly_bytes = readonly_report.read_bytes()
    binding = PaperIdentityBinding.from_readonly_receipt(
        json.loads(readonly_bytes), readonly_bytes
    )
    binding = replace(
        binding,
        runtime_manifest_sha256=runtime_manifest_sha256,
        deployment_manifest_sha256=deployment_manifest_sha256,
        probe_sha256=probe_sha256,
        probe_manifest_sha256=probe_manifest_sha256,
    )
    evaluation = load_and_evaluate_auditor_gate_v2(
        receipt_path, binding, datetime.now(timezone.utc)
    )
    return {
        "canonical_gate": evaluation.canonical_gate,
        "compatibility_gate": evaluation.compatibility_gate,
        "gate_version": evaluation.gate_version,
        "reason_codes": list(evaluation.reason_codes),
    }


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

    evaluate = sub.add_parser("evaluate-auditor")
    evaluate.add_argument("--receipt", type=Path, required=True)
    evaluate.add_argument("--readonly-report", type=Path, required=True)
    evaluate.add_argument("--runtime-manifest-sha256", required=True)
    evaluate.add_argument("--deployment-manifest-sha256", required=True)
    evaluate.add_argument("--probe-sha256", required=True)
    evaluate.add_argument("--probe-manifest-sha256", required=True)

    trust = sub.add_parser("evaluate-runtime-trust-anchor")
    trust.add_argument("--repo-root", type=Path, required=True)
    trust.add_argument("--anchor", type=Path, required=True)

    ready = sub.add_parser("readiness")
    ready.add_argument(
        "--report-root",
        type=Path,
        default=Path("state/ibkr_paper_30d/reports"),
    )

    args = parser.parse_args(argv)
    if args.command == "create-audit-export":
        result = create_audit_export(args.readonly_report, args.export_root)
    elif args.command == "evaluate-auditor":
        result = evaluate_auditor(
            args.receipt,
            args.readonly_report,
            args.runtime_manifest_sha256,
            args.deployment_manifest_sha256,
            args.probe_sha256,
            args.probe_manifest_sha256,
        )
    elif args.command == "evaluate-runtime-trust-anchor":
        result = evaluate_runtime_trust_anchor(args.repo_root, args.anchor)
    else:
        result = readiness(args.report_root)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
