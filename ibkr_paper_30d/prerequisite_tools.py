from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from .canonical import canonical_bytes
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


def _normalized_text_bytes(value: bytes) -> bytes:
    try:
        text = value.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("TRUST_ANCHOR_SOURCE_NOT_UTF8") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


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

    source_commit = subprocess.run(
        ["git", "-C", str(repo_root), "cat-file", "-e", f"{commit}^{{commit}}"],
        capture_output=True,
        check=False,
    )
    if source_commit.returncode != 0:
        raise ValueError("TRUST_ANCHOR_COMMIT_UNAVAILABLE")

    payload_hashes: dict[str, str] = {}
    source_matches = True
    source_blob_sha256: dict[str, str] = {}
    for name in files:
        blob = _git_blob(repo_root, commit, f"auditor_runtime/{name}")
        source_blob_sha256[name] = __import__("hashlib").sha256(blob).hexdigest()
        current = repo_root / "auditor_runtime" / name
        if not current.is_file():
            source_matches = False
            continue
        current_bytes = current.read_bytes()
        if _normalized_text_bytes(current_bytes) != _normalized_text_bytes(blob):
            source_matches = False
        payload_hashes[name] = __import__("hashlib").sha256(current_bytes).hexdigest()

    if set(payload_hashes) != set(files):
        source_matches = False

    runtime_text = _manifest_text("AUDITOR_RUNTIME_MANIFEST_V2", payload_hashes)
    deployment_hashes = dict(payload_hashes)
    deployment_hashes[manifest_name] = (
        __import__("hashlib").sha256(runtime_text).hexdigest()
    )
    deployment_text = _manifest_text(
        "AUDITOR_RUNTIME_DEPLOYMENT_MANIFEST_V2", deployment_hashes
    )
    anchor_sha = __import__("hashlib").sha256(anchor_path.read_bytes()).hexdigest()
    return {
        "schema": "AUDITOR_RUNTIME_V2_TRUST_ANCHOR_EVALUATION_V1",
        "source_commit": commit,
        "anchor_sha256": anchor_sha,
        "source_matches_anchor": source_matches,
        "source_blob_sha256": source_blob_sha256,
        "payload_sha256": payload_hashes,
        "runtime_manifest_sha256": __import__("hashlib")
        .sha256(runtime_text)
        .hexdigest(),
        "deployment_manifest_sha256": __import__("hashlib")
        .sha256(deployment_text)
        .hexdigest(),
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


def _canonical_attempt_id(value: str) -> str:
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError("LAUNCH_ATTEMPT_ID_INVALID") from exc
    canonical = str(parsed)
    if canonical != value:
        raise ValueError("LAUNCH_ATTEMPT_ID_INVALID")
    return canonical


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        raise ValueError("LAUNCH_ATTEMPT_RECEIPT_MISSING")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_canonical_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(canonical_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def bind_launch_attempt(
    launch_attempt_id: str,
    readonly_receipt: Path,
    auditor_receipt: Path,
    destination: Path,
    *,
    target_successor_epoch_id: str | None = None,
    target_successor_definition_sha256: str | None = None,
) -> dict[str, object]:
    canonical_id = _canonical_attempt_id(launch_attempt_id)
    try:
        readonly = json.loads(readonly_receipt.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("LAUNCH_ATTEMPT_READONLY_RECEIPT_INVALID") from exc
    expected_hash = str(readonly.get("expected_account_identity_hash") or "")
    if len(expected_hash) != 64 or any(
        c not in "0123456789abcdef" for c in expected_hash
    ):
        raise ValueError("LAUNCH_ATTEMPT_EXPECTED_ACCOUNT_HASH_INVALID")
    successor_values = (
        target_successor_epoch_id,
        target_successor_definition_sha256,
    )
    if any(value is not None for value in successor_values) and not all(
        isinstance(value, str) and value for value in successor_values
    ):
        raise ValueError("SUCCESSOR_TARGET_BINDING_INCOMPLETE")
    if target_successor_definition_sha256 is not None and (
        len(target_successor_definition_sha256) != 64
        or any(c not in "0123456789abcdef" for c in target_successor_definition_sha256)
    ):
        raise ValueError("SUCCESSOR_TARGET_DEFINITION_HASH_INVALID")
    successor_mode = target_successor_epoch_id is not None
    payload: dict[str, object] = {
        "schema": (
            "DAY1_LAUNCH_ATTEMPT_BINDING_V2"
            if successor_mode
            else "DAY1_LAUNCH_ATTEMPT_BINDING_V1"
        ),
        "launch_attempt_id": canonical_id,
        "readonly_receipt_sha256": _sha256_file(readonly_receipt),
        "auditor_receipt_sha256": _sha256_file(auditor_receipt),
        "expected_account_identity_hash": expected_hash,
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "real_order_writes_attempted": 0,
    }
    if successor_mode:
        payload.update(
            {
                "target_successor_epoch_id": target_successor_epoch_id,
                "target_successor_definition_sha256": (
                    target_successor_definition_sha256
                ),
            }
        )
    _atomic_canonical_json(destination, payload)
    return payload


def validate_launch_attempt_binding(
    launch_attempt_id: str,
    readonly_receipt: Path,
    auditor_receipt: Path,
    binding_path: Path,
    *,
    target_successor_epoch_id: str | None = None,
    target_successor_definition_sha256: str | None = None,
) -> dict[str, object]:
    canonical_id = _canonical_attempt_id(launch_attempt_id)
    try:
        payload = json.loads(binding_path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("LAUNCH_ATTEMPT_BINDING_INVALID") from exc
    successor_mode = target_successor_epoch_id is not None or (
        target_successor_definition_sha256 is not None
    )
    expected_schema = (
        "DAY1_LAUNCH_ATTEMPT_BINDING_V2"
        if successor_mode
        else "DAY1_LAUNCH_ATTEMPT_BINDING_V1"
    )
    if payload.get("schema") != expected_schema:
        raise ValueError("LAUNCH_ATTEMPT_BINDING_SCHEMA_INVALID")
    if payload.get("launch_attempt_id") != canonical_id:
        raise ValueError("LAUNCH_ATTEMPT_ID_MISMATCH")
    if payload.get("readonly_receipt_sha256") != _sha256_file(
        readonly_receipt
    ) or payload.get("auditor_receipt_sha256") != _sha256_file(auditor_receipt):
        raise ValueError("LAUNCH_ATTEMPT_RECEIPT_HASH_MISMATCH")
    try:
        readonly = json.loads(readonly_receipt.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("LAUNCH_ATTEMPT_READONLY_RECEIPT_INVALID") from exc
    if payload.get("expected_account_identity_hash") != readonly.get(
        "expected_account_identity_hash"
    ):
        raise ValueError("LAUNCH_ATTEMPT_ACCOUNT_HASH_MISMATCH")
    if payload.get("real_order_writes_attempted") != 0:
        raise ValueError("LAUNCH_ATTEMPT_WRITE_COUNT_INVALID")
    if successor_mode and (
        not target_successor_epoch_id
        or not target_successor_definition_sha256
        or payload.get("target_successor_epoch_id") != target_successor_epoch_id
        or payload.get("target_successor_definition_sha256")
        != target_successor_definition_sha256
    ):
        raise ValueError("SUCCESSOR_TARGET_BINDING_MISMATCH")
    return payload


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

    bind = sub.add_parser("bind-launch-attempt")
    bind.add_argument("--launch-attempt-id", required=True)
    bind.add_argument("--readonly-receipt", type=Path, required=True)
    bind.add_argument("--auditor-receipt", type=Path, required=True)
    bind.add_argument("--destination", type=Path, required=True)
    bind.add_argument("--target-successor-epoch-id")
    bind.add_argument("--target-successor-definition-sha256")

    validate = sub.add_parser("validate-launch-attempt")
    validate.add_argument("--launch-attempt-id", required=True)
    validate.add_argument("--readonly-receipt", type=Path, required=True)
    validate.add_argument("--auditor-receipt", type=Path, required=True)
    validate.add_argument("--binding", type=Path, required=True)
    validate.add_argument("--target-successor-epoch-id")
    validate.add_argument("--target-successor-definition-sha256")

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
    elif args.command == "bind-launch-attempt":
        result = bind_launch_attempt(
            args.launch_attempt_id,
            args.readonly_receipt,
            args.auditor_receipt,
            args.destination,
            target_successor_epoch_id=args.target_successor_epoch_id,
            target_successor_definition_sha256=(
                args.target_successor_definition_sha256
            ),
        )
    elif args.command == "validate-launch-attempt":
        result = validate_launch_attempt_binding(
            args.launch_attempt_id,
            args.readonly_receipt,
            args.auditor_receipt,
            args.binding,
            target_successor_epoch_id=args.target_successor_epoch_id,
            target_successor_definition_sha256=(
                args.target_successor_definition_sha256
            ),
        )
    else:
        result = readiness(args.report_root)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
