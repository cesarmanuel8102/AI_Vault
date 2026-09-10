"""R18.2 contract: record runbook and support requirements without runtime effects."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _assess(**overrides):
    from tmp_agent.brain_v9.core.operational_runbook_support_baseline import (
        assess_operational_runbook_support_baseline,
    )

    values = {
        "install_runbook_documented": True,
        "upgrade_runbook_documented": True,
        "backup_runbook_documented": True,
        "restore_rollback_documented": True,
        "release_notes_documented": True,
        "health_version_visible": True,
        "support_bundle_redacted": True,
        "actionable_errors_documented": True,
        "destructive_restore_requested": False,
        "secret_in_support_bundle": False,
        "runtime_start_requested": False,
        "network_call": False,
        "scheduler_activation": False,
        "canonical_local_sync": False,
        "live_trading": False,
        "real_money": False,
        "auto_merge": False,
    }
    values.update(overrides)
    return assess_operational_runbook_support_baseline(**values)


def test_complete_support_surface_is_immutable_deterministic_and_no_deploy():
    first, second = _assess(), _assess()
    assert first == second
    assert first.decision == "SUPPORT_SURFACE_VERIFIED"
    assert first.runtime_permitted is False
    assert first.denial_reasons == ()
    assert len(first.receipt_sha256) == 64
    with pytest.raises(FrozenInstanceError):
        first.decision = "REJECT"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"install_runbook_documented": False}, "install_runbook_required"),
        ({"upgrade_runbook_documented": False}, "upgrade_runbook_required"),
        ({"backup_runbook_documented": False}, "backup_runbook_required"),
        ({"restore_rollback_documented": False}, "restore_rollback_runbook_required"),
        ({"release_notes_documented": False}, "release_notes_required"),
        ({"health_version_visible": False}, "health_version_visibility_required"),
        ({"support_bundle_redacted": False}, "support_bundle_redaction_required"),
        ({"actionable_errors_documented": False}, "actionable_errors_required"),
        ({"destructive_restore_requested": True}, "destructive_restore_forbidden"),
        ({"secret_in_support_bundle": True}, "secret_in_support_bundle_forbidden"),
        ({"runtime_start_requested": True}, "runtime_start_forbidden"),
        ({"network_call": True}, "network_call_forbidden"),
        ({"scheduler_activation": True}, "scheduler_activation_forbidden"),
        ({"canonical_local_sync": True}, "canonical_local_sync_forbidden"),
        ({"live_trading": True}, "live_trading_forbidden"),
        ({"real_money": True}, "real_money_forbidden"),
        ({"auto_merge": True}, "auto_merge_forbidden"),
    ],
)
def test_support_surface_fails_closed_for_missing_requirements_or_effects(overrides, reason):
    receipt = _assess(**overrides)
    assert receipt.decision == "REJECT"
    assert receipt.runtime_permitted is False
    assert reason in receipt.denial_reasons


def test_evidence_records_support_surface_without_runtime_actions():
    evidence = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/BRAIN_101_R18_2_OPERATIONAL_RUNBOOKS_SUPPORT_SURFACE.json"
        ).read_text(encoding="utf-8")
    )
    assert evidence["roadmap_item"] == "R18.2"
    assert evidence["decision"] == "SUPPORT_SURFACE_VERIFIED"
    assert evidence["support_surface"]["support_bundle_redacted"] is True
    assert all(value is False for value in evidence["runtime_actions"].values())


def test_closeout_closes_r18_2_and_jit_binds_only_r18_3_without_deploy():
    closeout = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/BRAIN_101_R18_2_OPERATIONAL_RUNBOOKS_SUPPORT_SURFACE_CLOSEOUT.json"
        ).read_text(encoding="utf-8")
    )
    manifest = json.loads((ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["roadmap_items"]["R18.2"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    active = [item_id for item_id, item in manifest["roadmap_items"].items() if item["status"] == "AUTHORIZED_ACTIVE"]
    assert active == ["R18.3"]
    binding = manifest["roadmap_items"]["R18.3"]["automation"]
    assert binding["front_id"] == "BRAIN-101-R18-3-PRODUCT-OPERATIONS-ACCEPTANCE-ACCESSIBILITY-VALIDATION-01"
    assert binding["work_branch"] == "control-plane/r18-3-product-operations-acceptance-accessibility-validation"
    assert binding["deployment_mode"] == "NO_DEPLOY"
    assert binding["allowed_paths"] == [
        "tmp_agent/brain_v9/core/product_operations_acceptance_accessibility_validation.py",
        "docs/roadmap/evidence/BRAIN_101_R18_3_PRODUCT_OPERATIONS_ACCEPTANCE_ACCESSIBILITY_VALIDATION.json",
        "tests/contract/test_r18_3_product_operations_acceptance_accessibility_validation.py",
    ]
    assert closeout["implementation_merge"] == "b943b0ff24ee22c5c2c1f702ebcc7138c608ac63"
    assert all(value is False for value in closeout["runtime_actions"].values())
