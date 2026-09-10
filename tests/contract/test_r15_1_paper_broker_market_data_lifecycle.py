"""R15.1 contract: deterministic simulated paper execution lifecycle receipts."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _receipt(**overrides):
    from tmp_agent.brain_v9.core.paper_execution_lifecycle import (
        evaluate_paper_execution_lifecycle,
    )

    values = {
        "order_id": "paper-order-001",
        "event_sequence": ("SUBMITTED", "CANCELLED", "RECONCILED"),
        "paper_only": True,
        "market_data_source": "local_fixture",
        "broker_action": False,
        "provider_call": False,
        "network_call": False,
        "runtime_execution": False,
        "scheduler_activation": False,
        "live_trading": False,
        "real_money": False,
    }
    values.update(overrides)
    return evaluate_paper_execution_lifecycle(**values)


def test_simulated_paper_lifecycle_receipt_is_deterministic_and_immutable():
    receipt = _receipt()
    assert receipt == _receipt()
    assert receipt.accepted is True
    assert receipt.phase == "RECONCILED"
    assert receipt.cancellation_recorded is True
    assert receipt.duplicate_prevented is True
    assert receipt.reconciliation_status == "MATCHED"
    assert receipt.paper_only is True
    assert len(receipt.receipt_id) == 64
    with pytest.raises(FrozenInstanceError):
        receipt.accepted = False


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"paper_only": False}, "paper_only_required"),
        ({"market_data_source": "provider"}, "local_market_data_required"),
        ({"broker_action": True}, "broker_action_forbidden"),
        ({"provider_call": True}, "provider_action_forbidden"),
        ({"network_call": True}, "network_action_forbidden"),
        ({"runtime_execution": True}, "runtime_execution_forbidden"),
        ({"scheduler_activation": True}, "scheduler_activation_forbidden"),
        ({"live_trading": True}, "live_trading_forbidden"),
        ({"real_money": True}, "real_money_forbidden"),
        ({"event_sequence": ("SUBMITTED", "RECONCILED")}, "cancellation_required"),
        ({"event_sequence": ("SUBMITTED", "CANCELLED", "CANCELLED", "RECONCILED")}, "duplicate_event_detected"),
    ],
)
def test_simulated_paper_lifecycle_fails_closed_for_external_or_invalid_inputs(overrides, reason):
    receipt = _receipt(**overrides)
    assert receipt.accepted is False
    assert receipt.reason == reason


def test_simulated_paper_lifecycle_rejects_effects_and_declares_no_deploy_evidence():
    from tmp_agent.brain_v9.core.paper_execution_lifecycle import reject_paper_execution_effect

    with pytest.raises(ValueError, match="paper_execution_lifecycle_no_effects"):
        reject_paper_execution_effect("broker_order")
    evidence = json.loads(
        (
            ROOT / "docs/roadmap/evidence/"
            "BRAIN_101_R15_1_PAPER_BROKER_MARKET_DATA_LIFECYCLE.json"
        ).read_text(encoding="utf-8")
    )
    assert evidence["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert all(value is False for value in evidence["runtime_actions"].values())


def test_closeout_closes_r15_1_and_jit_binds_r15_2_without_deploy():
    manifest = json.loads(
        (ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json").read_text(encoding="utf-8")
    )
    closeout = json.loads(
        (
            ROOT / "docs/roadmap/evidence/"
            "BRAIN_101_R15_1_PAPER_BROKER_MARKET_DATA_LIFECYCLE_CLOSEOUT.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["roadmap_items"]["R15.1"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    successor = manifest["roadmap_items"]["R15.2"]
    assert successor["status"] == "AUTHORIZED_ACTIVE"
    assert successor["dependencies"] == ["R15.1"]
    assert successor["automation"]["deployment_mode"] == "NO_DEPLOY"
    assert closeout["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert closeout["successor"]["roadmap_item"] == "R15.2"
    assert all(value is False for value in closeout["runtime_actions"].values())


def test_r15_2_active_binding_predeclares_a_no_deploy_closeout_contract():
    manifest = json.loads(
        (ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json").read_text(encoding="utf-8")
    )
    successor = manifest["roadmap_items"]["R15.2"]
    closeout = successor["automation"]["closeout"]
    assert closeout["risk"] == "MEDIUM"
    assert closeout["executor"] == "codex_control_plane"
    assert "docs/roadmap/BRAIN_101_MANIFEST.json" in closeout["allowed_paths"]
    assert "tmp_agent/brain_v9/trading/" in closeout["forbidden_paths"]
