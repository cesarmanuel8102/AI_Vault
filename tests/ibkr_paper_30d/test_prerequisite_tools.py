from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

import ibkr_paper_30d.prerequisite_tools as prerequisite_tools
from ibkr_paper_30d.prerequisite_tools import (
    bind_launch_attempt,
    create_audit_export,
    readiness,
    validate_launch_attempt_binding,
    validate_successor_owner_authorization,
)


def readonly_payload():
    return {
        "schema": "REAL_IBKR_READ_ONLY_RECONCILIATION_V1",
        "status": "PASS",
        "paper_account_identity_gate": "PASS",
        "real_ibkr_read_only_identity_gate": "PASS",
        "broker_reconciliation_gate": "PASS",
        "gateway_mode": "PAPER",
        "port": 4002,
        "expected_account_identity_hash": "a" * 64,
    }


def test_create_audit_export_preserves_readonly_receipt_bytes(tmp_path):
    source = tmp_path / "readonly.json"
    payload = readonly_payload()
    source.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    output = create_audit_export(source, tmp_path / "exports")

    bundle = Path(output["bundle_path"])
    assert (bundle / "manifest.json").is_file()
    assert (bundle / "paper_identity.json").is_file()
    copied = Path(output["paper_identity_receipt_path"])
    assert copied.read_bytes() == source.read_bytes()


def test_create_audit_export_accepts_only_safe_account_summary_partial(tmp_path):
    source = tmp_path / "readonly-partial.json"
    payload = {
        **readonly_payload(),
        "status": "PARTIAL",
        "reason_codes": ["ACCOUNT_SUMMARY_FIELDS_INCOMPLETE"],
        "broker_reconciliation_gate": "BLOCK",
        "expected_account_identity_bound": True,
        "paper_account_namespace_ok": True,
        "managed_account_count": 1,
        "heartbeat_ok": True,
        "outbound_allowlist_only": True,
        "real_order_writes_attempted": 0,
        "account_summary_consistent": True,
        "account_summary_complete": False,
        "gateway_config_consistent": True,
        "query_completeness": {
            "managed_accounts": True,
            "positions": True,
            "open_orders": True,
            "executions": True,
            "current_time": True,
        },
    }
    source.write_text(json.dumps(payload), encoding="utf-8")

    result = create_audit_export(source, tmp_path / "safe-exports")

    assert Path(result["bundle_path"]).is_dir()

    payload["reason_codes"].append("EXECUTION_VISIBILITY_UNAVAILABLE")
    source.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="READONLY_RECEIPT_NOT_PASS"):
        create_audit_export(source, tmp_path / "unsafe-exports")


def test_readiness_requires_both_auditor_and_market_pass(tmp_path, monkeypatch):
    root = tmp_path / "reports"
    root.mkdir()
    monkeypatch.delenv("IBKR_AUTONOMOUS_PAPER_ARMED", raising=False)

    first = readiness(root)
    assert first["prerequisites_structurally_present"] is False
    assert first["paper_execution_armed"] is False

    (root / "auditor_gate_v2_receipt.json").write_text(
        json.dumps({"schema": "AUDITOR_GATE_V2_RECEIPT_V1"}), encoding="utf-8"
    )
    (root / "market_data_policy_v1.json").write_text("{}", encoding="utf-8")
    (root / "market_data_validation.json").write_text(
        json.dumps({"market_data_gate": "PASS"}), encoding="utf-8"
    )

    final = readiness(root)
    assert final["prerequisites_structurally_present"] is True
    assert final["paper_execution_armed"] is False


def test_successor_authorization_validation_reports_pass(tmp_path, monkeypatch):
    captured = {}

    def validate(**kwargs):
        captured.update(kwargs)
        return {
            "authorization_event_id": "owner-v2",
            "epoch_id": "AUTONOMY_EPOCH_2",
            "definition_sha256": "d" * 64,
        }

    monkeypatch.setattr(
        prerequisite_tools, "validate_successor_authorization", validate
    )
    result = validate_successor_owner_authorization(
        db_path=tmp_path / "state.sqlite3",
        receipt_path=tmp_path / "owner-v2.json",
        epoch_id="AUTONOMY_EPOCH_2",
        definition_sha256="d" * 64,
        actor_sid="S-1-5-21-owner",
    )

    assert result == {
        "status": "PASS",
        "authorization_event_id": "owner-v2",
        "epoch_id": "AUTONOMY_EPOCH_2",
        "definition_sha256": "d" * 64,
    }
    assert captured["expected_actor_sid"] == "S-1-5-21-owner"


def test_attempt_binding_hashes_receipts_and_requires_same_attempt(tmp_path: Path):
    readonly = tmp_path / "readonly.json"
    readonly.write_text(
        json.dumps(readonly_payload(), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    auditor = tmp_path / "auditor.json"
    auditor.write_text('{"gate_status":"PASS"}', encoding="utf-8")
    target = tmp_path / "binding.json"
    attempt_id = str(uuid4())

    binding = bind_launch_attempt(attempt_id, readonly, auditor, target)

    assert binding["launch_attempt_id"] == attempt_id
    assert binding["expected_account_identity_hash"] == "a" * 64
    assert binding["real_order_writes_attempted"] == 0
    assert (
        validate_launch_attempt_binding(attempt_id, readonly, auditor, target)
        == binding
    )
    with pytest.raises(ValueError, match="LAUNCH_ATTEMPT_ID_MISMATCH"):
        validate_launch_attempt_binding(str(uuid4()), readonly, auditor, target)


def test_successor_attempt_binding_requires_and_validates_exact_target(tmp_path: Path):
    readonly = tmp_path / "readonly.json"
    readonly.write_text(json.dumps(readonly_payload()), encoding="utf-8")
    auditor = tmp_path / "auditor.json"
    auditor.write_text('{"gate_status":"PASS"}', encoding="utf-8")
    target = tmp_path / "binding-v2.json"
    attempt_id = str(uuid4())
    definition_sha = "b" * 64

    binding = bind_launch_attempt(
        attempt_id,
        readonly,
        auditor,
        target,
        target_successor_epoch_id="AUTONOMY_EPOCH_2",
        target_successor_definition_sha256=definition_sha,
    )

    assert binding["schema"] == "DAY1_LAUNCH_ATTEMPT_BINDING_V2"
    assert binding["target_successor_epoch_id"] == "AUTONOMY_EPOCH_2"
    assert (
        validate_launch_attempt_binding(
            attempt_id,
            readonly,
            auditor,
            target,
            target_successor_epoch_id="AUTONOMY_EPOCH_2",
            target_successor_definition_sha256=definition_sha,
        )
        == binding
    )
    with pytest.raises(ValueError, match="SUCCESSOR_TARGET_BINDING_MISMATCH"):
        validate_launch_attempt_binding(
            attempt_id,
            readonly,
            auditor,
            target,
            target_successor_epoch_id="AUTONOMY_EPOCH_3",
            target_successor_definition_sha256=definition_sha,
        )
    with pytest.raises(ValueError, match="SUCCESSOR_TARGET_BINDING_INCOMPLETE"):
        bind_launch_attempt(
            attempt_id,
            readonly,
            auditor,
            target,
            target_successor_epoch_id="AUTONOMY_EPOCH_2",
        )


@pytest.mark.parametrize("which", ["readonly", "auditor"])
def test_attempt_binding_rejects_receipt_mutation(tmp_path: Path, which: str):
    readonly = tmp_path / "readonly.json"
    readonly.write_text(json.dumps(readonly_payload()), encoding="utf-8")
    auditor = tmp_path / "auditor.json"
    auditor.write_text('{"gate_status":"PASS"}', encoding="utf-8")
    target = tmp_path / "binding.json"
    attempt_id = str(uuid4())
    bind_launch_attempt(attempt_id, readonly, auditor, target)
    selected = readonly if which == "readonly" else auditor
    selected.write_bytes(selected.read_bytes() + b" ")

    with pytest.raises(ValueError, match="LAUNCH_ATTEMPT_RECEIPT_HASH_MISMATCH"):
        validate_launch_attempt_binding(attempt_id, readonly, auditor, target)


@pytest.mark.parametrize(
    "attempt_id", ["", "not-a-uuid", "{11111111-1111-1111-1111-111111111111}"]
)
def test_attempt_binding_rejects_noncanonical_uuid(tmp_path: Path, attempt_id: str):
    readonly = tmp_path / "readonly.json"
    readonly.write_text(json.dumps(readonly_payload()), encoding="utf-8")
    auditor = tmp_path / "auditor.json"
    auditor.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="LAUNCH_ATTEMPT_ID_INVALID"):
        bind_launch_attempt(attempt_id, readonly, auditor, tmp_path / "binding.json")
