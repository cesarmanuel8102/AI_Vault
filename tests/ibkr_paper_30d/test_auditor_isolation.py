from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from ibkr_paper_30d.auditor import Auditor
from ibkr_paper_30d.auditor_export import AuditExporter


@pytest.fixture
def exporter(tmp_path) -> AuditExporter:
    return AuditExporter(tmp_path / "exports")


@pytest.fixture
def records():
    return {
        "decision.json": {"decision_id": "d-001", "result": "NO_TRADE"},
        "risk.json": {"status": "PASS", "equity": "500.00"},
    }


def test_publish_is_atomic_canonical_and_deterministic(exporter, records) -> None:
    first = exporter.publish(records)
    second = exporter.publish(records)

    assert first.bundle_id == second.bundle_id
    assert first.path == second.path
    assert not list(exporter.root.glob(".*-staging"))
    assert (first.path / "manifest.json").is_file()
    assert (first.path / "decision.json").read_text(encoding="utf-8") == (
        '{"decision_id":"d-001","result":"NO_TRADE"}'
    )
    assert first.manifest_sha256 == second.manifest_sha256


def test_export_rejects_path_traversal_and_manifest_name(exporter) -> None:
    for name in ("../escape.json", "nested/value.json", "manifest.json"):
        with pytest.raises(ValueError):
            exporter.publish({name: {"unsafe": True}})


def test_modified_export_is_rejected(exporter, records, tmp_path) -> None:
    receipt = exporter.publish(records)
    target = receipt.path / "decision.json"
    target.chmod(stat.S_IWRITE | stat.S_IREAD)
    target.write_text('{"tampered":true}', encoding="utf-8")

    result = Auditor().run(receipt.path, tmp_path / "reports")

    assert result.status == "HASH_MISMATCH"
    assert result.isolation_gate == "BLOCK"


def test_unexpected_export_file_is_rejected(exporter, records, tmp_path) -> None:
    receipt = exporter.publish(records)
    extra = receipt.path / "extra.json"
    extra.write_text("{}", encoding="utf-8")

    result = Auditor().run(receipt.path, tmp_path / "reports")

    assert result.status == "MANIFEST_MISMATCH"


def test_rewritten_file_hash_cannot_forge_bundle_identity(
    exporter, records, tmp_path
) -> None:
    receipt = exporter.publish(records)
    target = receipt.path / "decision.json"
    manifest_path = receipt.path / "manifest.json"
    target.chmod(stat.S_IWRITE | stat.S_IREAD)
    manifest_path.chmod(stat.S_IWRITE | stat.S_IREAD)
    target.write_text('{"tampered":true}', encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["decision.json"] = hashlib.sha256(
        target.read_bytes()
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    result = Auditor().run(receipt.path, tmp_path / "reports")

    assert result.status == "MANIFEST_MISMATCH"
    assert "BUNDLE_ID_MISMATCH" in result.reason_codes


def test_valid_export_produces_hash_bound_append_only_report(
    exporter, records, tmp_path
) -> None:
    receipt = exporter.publish(records)
    reports = tmp_path / "reports"

    result = Auditor().run(receipt.path, reports)

    assert result.status == "PASS"
    assert result.report_path is not None
    payload = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert payload["bundle_id"] == receipt.bundle_id
    assert payload["manifest_sha256"] == receipt.manifest_sha256
    assert payload["isolation_gate"] == "BLOCK"
    with pytest.raises(FileExistsError):
        result.report_path.open("x", encoding="utf-8")


def test_normal_process_cannot_claim_os_isolation_pass(tmp_path) -> None:
    secrets = tmp_path / "Secrets"
    secrets.mkdir()
    (secrets / "credential.env").write_text("SECRET=fake", encoding="utf-8")
    live_db = tmp_path / "live.sqlite3"
    live_db.write_bytes(b"not-a-real-db")

    probe = Auditor().probe_environment(secrets_dir=secrets, live_db=live_db)

    assert probe.status == "BLOCK"
    assert probe.can_read_secrets is True
    assert probe.can_import_broker_adapter is True
    assert probe.can_acquire_execution_lock is True
    assert probe.can_mutate_live_database is True
    assert "RESTRICTED_WINDOWS_TOKEN_NOT_PROVEN" in probe.reasons


def test_auditor_source_has_no_runtime_capability_imports() -> None:
    source = Path(Auditor.__module__.replace(".", os.sep) + ".py")
    if not source.exists():
        source = Path(__file__).parents[2] / "ibkr_paper_30d" / "auditor.py"
    text = source.read_text(encoding="utf-8")

    assert "from .broker" not in text
    assert "from .execution_lock" not in text
    assert "from .persistence" not in text
    assert "Secrets" not in text


def test_sanitized_environment_keeps_only_explicit_runtime_values() -> None:
    env = Auditor.sanitized_environment(
        {
            "PATH": "safe-path",
            "SYSTEMROOT": "C:\\Windows",
            "EMAIL_PASS": "secret",
            "IBKR_ACCOUNT": "DU123456",
        }
    )

    assert env == {"PATH": "safe-path", "SYSTEMROOT": "C:\\Windows"}
