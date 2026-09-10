"""BR0 contract: historical certification and current remediation cannot conflict."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RECEIPT = ROOT / "docs/roadmap/evidence/BRAIN_101_BR0_CANONICAL_CERTIFICATION_RECONCILIATION.json"


def _load(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_br0_reconciles_current_state_without_rewriting_historical_certification():
    manifest = _load("docs/roadmap/BRAIN_101_MANIFEST.json")
    scorecard = _load("docs/roadmap/BRAIN_101_SCORECARD.json")
    root_status = _load("ROADMAP_STATUS.json")
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    ledger = (ROOT / "docs/MIGRATION_CONTROL_LEDGER.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/roadmap/BRAIN_101_ROADMAP.md").read_text(encoding="utf-8")

    expected_current = {
        "program": "BRAIN-101-REMEDIATION",
        "status": "REMEDIATION_REQUIRED",
    }
    expected_external = {
        "accepted": False,
        "status": "REJECTED_PENDING_REMEDIATION",
    }

    for artifact in (manifest, scorecard, root_status["brain_101"], receipt):
        assert artifact["historical_internal_certification"]["event"] == "RECORDED"
        assert artifact["historical_internal_certification"]["owner_authority"] is True
        assert artifact["external_certification"] == expected_external
        assert artifact["current_program"] == expected_current

    assert manifest["brain_101_certified"] is False
    assert manifest["certification_status"] == "REJECTED_PENDING_REMEDIATION"
    assert manifest["current_phase"] == "BR0"
    assert scorecard["status"] == "BRAIN_101_REMEDIATION_REQUIRED"
    assert scorecard["historical_internal_certified_score"] == 101
    assert root_status["brain_101"]["status"] == "BRAIN_101_REMEDIATION_REQUIRED"
    assert receipt["historical_receipts_rewritten"] is False
    assert receipt["runtime_modified"] is False
    assert "BRAIN-101 BR0 Canonical Certification Reconciliation" in ledger
    assert "\nSTATUS: BRAIN_101_CERTIFIED\n" not in f"\n{roadmap}\n"
    assert "HISTORICAL_INTERNAL_STATUS: BRAIN_101_CERTIFIED" in roadmap
