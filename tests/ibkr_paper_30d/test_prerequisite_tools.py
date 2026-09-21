from __future__ import annotations

import json
from pathlib import Path

from ibkr_paper_30d.prerequisite_tools import create_audit_export, readiness


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
    source.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    output = create_audit_export(source, tmp_path / "exports")

    bundle = Path(output["bundle_path"])
    assert (bundle / "manifest.json").is_file()
    assert (bundle / "paper_identity.json").is_file()
    copied = Path(output["paper_identity_receipt_path"])
    assert copied.read_bytes() == source.read_bytes()


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
