"""R18.1 contract: record product/operator UX baseline without runtime effects."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _baseline(**overrides):
    from tmp_agent.brain_v9.core.product_operator_experience_baseline import (
        assess_product_operator_experience_baseline,
    )

    values = {
        "chat_dashboard_visible": True,
        "trace_console_visible": True,
        "notifications_visible": True,
        "operator_inbox_visible": True,
        "responsive_accessibility_verified": True,
        "approval_visibility_verified": True,
        "incident_visibility_verified": True,
        "private_reasoning_exposed": False,
        "runtime_start_requested": False,
        "network_call": False,
        "scheduler_activation": False,
        "canonical_local_sync": False,
        "live_trading": False,
        "real_money": False,
        "auto_merge": False,
    }
    values.update(overrides)
    return assess_product_operator_experience_baseline(**values)


def test_complete_baseline_is_immutable_deterministic_and_no_deploy():
    first, second = _baseline(), _baseline()
    assert first == second
    assert first.decision == "BASELINE_VERIFIED"
    assert first.runtime_permitted is False
    assert first.denial_reasons == ()
    assert len(first.receipt_sha256) == 64
    with pytest.raises(FrozenInstanceError):
        first.decision = "REJECT"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"chat_dashboard_visible": False}, "chat_dashboard_required"),
        ({"trace_console_visible": False}, "trace_console_required"),
        ({"notifications_visible": False}, "notifications_required"),
        ({"operator_inbox_visible": False}, "operator_inbox_required"),
        ({"responsive_accessibility_verified": False}, "responsive_accessibility_required"),
        ({"approval_visibility_verified": False}, "approval_visibility_required"),
        ({"incident_visibility_verified": False}, "incident_visibility_required"),
        ({"private_reasoning_exposed": True}, "private_reasoning_forbidden"),
        ({"runtime_start_requested": True}, "runtime_start_forbidden"),
        ({"network_call": True}, "network_call_forbidden"),
        ({"scheduler_activation": True}, "scheduler_activation_forbidden"),
        ({"canonical_local_sync": True}, "canonical_local_sync_forbidden"),
        ({"live_trading": True}, "live_trading_forbidden"),
        ({"real_money": True}, "real_money_forbidden"),
        ({"auto_merge": True}, "auto_merge_forbidden"),
    ],
)
def test_baseline_fails_closed_for_missing_visibility_or_prohibited_effects(overrides, reason):
    receipt = _baseline(**overrides)
    assert receipt.decision == "REJECT"
    assert receipt.runtime_permitted is False
    assert reason in receipt.denial_reasons


def test_evidence_records_operator_baseline_without_runtime_actions():
    evidence = json.loads(
        (ROOT / "docs/roadmap/evidence/BRAIN_101_R18_1_PRODUCT_OPERATOR_EXPERIENCE_BASELINE.json").read_text(encoding="utf-8")
    )
    assert evidence["roadmap_item"] == "R18.1"
    assert evidence["decision"] == "BASELINE_VERIFIED"
    assert evidence["private_reasoning_exposed"] is False
    assert all(value is False for value in evidence["runtime_actions"].values())
