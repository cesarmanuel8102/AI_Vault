from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from uuid import uuid4


@dataclass(frozen=True)
class IsolationProbe:
    status: str
    can_read_secrets: bool
    can_import_broker_adapter: bool
    can_acquire_execution_lock: bool
    can_mutate_live_database: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class AuditRunResult:
    status: str
    isolation_gate: str
    reason_codes: tuple[str, ...]
    report_path: Path | None = None


class Auditor:
    def run(self, export_dir: str | Path, report_dir: str | Path) -> AuditRunResult:
        source = Path(export_dir)
        destination = Path(report_dir)
        integrity_status, reasons, manifest, manifest_sha256 = self._verify(source)
        isolation_gate = "BLOCK"
        if integrity_status != "PASS":
            return AuditRunResult(integrity_status, isolation_gate, reasons)

        destination.mkdir(parents=True, exist_ok=True)
        report_path = destination / f"{manifest['bundle_id']}-{uuid4().hex}.json"
        report = {
            "schema": "AUDITOR_REPORT_V1",
            "status": integrity_status,
            "isolation_gate": isolation_gate,
            "isolation_reason": "OS_LEVEL_DENIALS_NOT_PROVEN",
            "bundle_id": manifest["bundle_id"],
            "manifest_sha256": manifest_sha256,
            "verified_file_count": len(manifest["files"]),
        }
        encoded = json.dumps(
            report,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        with report_path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
        return AuditRunResult("PASS", isolation_gate, (), report_path)

    def probe_environment(
        self,
        *,
        secrets_dir: str | Path,
        live_db: str | Path,
    ) -> IsolationProbe:
        secret_path = Path(secrets_dir)
        database_path = Path(live_db)
        can_read_secrets = os.access(secret_path, os.R_OK) and any(
            child.is_file() and os.access(child, os.R_OK)
            for child in secret_path.iterdir()
        )
        can_import_broker = (
            importlib.util.find_spec("ibkr_paper_30d.broker") is not None
        )
        can_import_lock = (
            importlib.util.find_spec("ibkr_paper_30d.execution_lock") is not None
        )
        can_mutate_database = os.access(database_path, os.W_OK)
        capabilities = (
            can_read_secrets,
            can_import_broker,
            can_import_lock,
            can_mutate_database,
        )
        reasons = ["RESTRICTED_WINDOWS_TOKEN_NOT_PROVEN"]
        labels = (
            "SECRET_READ_CAPABILITY_PRESENT",
            "BROKER_IMPORT_CAPABILITY_PRESENT",
            "EXECUTION_LOCK_CAPABILITY_PRESENT",
            "LIVE_DATABASE_WRITE_CAPABILITY_PRESENT",
        )
        reasons.extend(label for present, label in zip(capabilities, labels) if present)
        return IsolationProbe(
            status="BLOCK",
            can_read_secrets=can_read_secrets,
            can_import_broker_adapter=can_import_broker,
            can_acquire_execution_lock=can_import_lock,
            can_mutate_live_database=can_mutate_database,
            reasons=tuple(reasons),
        )

    @staticmethod
    def sanitized_environment(environment: Mapping[str, str]) -> dict[str, str]:
        allowed = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
        return {key: environment[key] for key in allowed if key in environment}

    @staticmethod
    def _verify(
        source: Path,
    ) -> tuple[str, tuple[str, ...], dict[str, object], str]:
        manifest_path = source / "manifest.json"
        try:
            manifest_bytes = manifest_path.read_bytes()
            manifest = json.loads(manifest_bytes)
        except (OSError, json.JSONDecodeError):
            return "MANIFEST_INVALID", ("MANIFEST_UNREADABLE",), {}, ""
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema") != "AUDIT_EXPORT_MANIFEST_V1"
            or not isinstance(manifest.get("files"), dict)
            or not isinstance(manifest.get("bundle_id"), str)
        ):
            return "MANIFEST_INVALID", ("MANIFEST_SCHEMA_INVALID",), {}, ""

        expected_files = set(manifest["files"])
        actual_files = {path.name for path in source.iterdir() if path.is_file()}
        if actual_files != expected_files | {"manifest.json"}:
            return "MANIFEST_MISMATCH", ("FILE_SET_MISMATCH",), manifest, ""

        for name, expected_hash in manifest["files"].items():
            if Path(name).name != name or name == "manifest.json":
                return "MANIFEST_INVALID", ("UNSAFE_MANIFEST_PATH",), manifest, ""
            actual_hash = hashlib.sha256((source / name).read_bytes()).hexdigest()
            if actual_hash != expected_hash:
                return "HASH_MISMATCH", (f"HASH_MISMATCH:{name}",), manifest, ""
        files_bytes = json.dumps(
            manifest["files"],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        bundle_digest = hashlib.sha256(files_bytes).hexdigest()
        if (
            manifest.get("bundle_sha256") != bundle_digest
            or manifest["bundle_id"] != f"audit-{bundle_digest[:24]}"
        ):
            return "MANIFEST_MISMATCH", ("BUNDLE_ID_MISMATCH",), manifest, ""
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        return "PASS", (), manifest, manifest_sha256


def write_isolation_report(
    *,
    secrets_dir: str | Path,
    live_db: str | Path,
    output_path: str | Path,
    provisioning_status: str,
) -> dict[str, object]:
    probe = Auditor().probe_environment(secrets_dir=secrets_dir, live_db=live_db)
    report = {
        "schema": "CODEX_DECISION_AUDITOR_ISOLATION_V1",
        "gate": probe.status,
        "os_level_denials_proven": False,
        "dedicated_account_provisioning": provisioning_status,
        "can_read_secrets": probe.can_read_secrets,
        "can_import_broker_adapter": probe.can_import_broker_adapter,
        "can_acquire_execution_lock": probe.can_acquire_execution_lock,
        "can_mutate_live_database": probe.can_mutate_live_database,
        "reason_codes": list(probe.reasons),
    }
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return report
