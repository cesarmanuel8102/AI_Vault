"""R18.3 contract: validate product operations acceptance without runtime effects."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _assess(**overrides):
    from tmp_agent.brain_v9.core.product_operations_acceptance_accessibility_validation import (
        assess_product_operations_acceptance_accessibility,
    )

    values = {
        "operator_workflow_accepted": True,
        "accessibility_verified": True,
        "responsive_behavior_verified": True,
        "incident_ui_verified": True,
        "hidden_operational_dependency": False,
        "unaudited_release": False,
        "runtime_start_requested": False,
        "network_call": False,
        "scheduler_activation": False,
        "canonical_local_sync": False,
        "live_trading": False,
        "real_money": False,
        "auto_merge": False,
    }
    values.update(overrides)
    return assess_product_operations_acceptance_accessibility(**values)


def test_complete_acceptance_is_immutable_deterministic_and_no_deploy():
    first, second = _assess(), _assess()
    assert first == second
    assert first.decision == "ACCEPTANCE_VERIFIED"
    assert first.runtime_permitted is False
    assert first.denial_reasons == ()
    assert len(first.receipt_sha256) == 64
    with pytest.raises(FrozenInstanceError):
        first.decision = "REJECT"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"operator_workflow_accepted": False}, "operator_workflow_acceptance_required"),
        ({"accessibility_verified": False}, "accessibility_verification_required"),
        ({"responsive_behavior_verified": False}, "responsive_behavior_required"),
        ({"incident_ui_verified": False}, "incident_ui_verification_required"),
        ({"hidden_operational_dependency": True}, "hidden_operational_dependency_forbidden"),
        ({"unaudited_release": True}, "unaudited_release_forbidden"),
        ({"runtime_start_requested": True}, "runtime_start_forbidden"),
        ({"network_call": True}, "network_call_forbidden"),
        ({"scheduler_activation": True}, "scheduler_activation_forbidden"),
        ({"canonical_local_sync": True}, "canonical_local_sync_forbidden"),
        ({"live_trading": True}, "live_trading_forbidden"),
        ({"real_money": True}, "real_money_forbidden"),
        ({"auto_merge": True}, "auto_merge_forbidden"),
    ],
)
def test_acceptance_fails_closed_for_missing_requirements_or_effects(overrides, reason):
    receipt = _assess(**overrides)
    assert receipt.decision == "REJECT"
    assert receipt.runtime_permitted is False
    assert reason in receipt.denial_reasons


def test_evidence_records_acceptance_without_runtime_actions():
    evidence = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/BRAIN_101_R18_3_PRODUCT_OPERATIONS_ACCEPTANCE_ACCESSIBILITY_VALIDATION.json"
        ).read_text(encoding="utf-8")
    )
    assert evidence["roadmap_item"] == "R18.3"
    assert evidence["decision"] == "ACCEPTANCE_VERIFIED"
    assert evidence["acceptance"]["accessibility_verified"] is True
    assert all(value is False for value in evidence["runtime_actions"].values())
