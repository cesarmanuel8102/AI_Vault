"""R15.3 contract: deterministic paper-only soak and incident evidence."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_paper_soak_incident_receipt_is_deterministic_immutable_and_paper_only():
    from tmp_agent.brain_v9.core.paper_soak_incident_evidence import evaluate_paper_soak_incident

    values = dict(
        soak_window="SIMULATED_30D",
        incident_id="paper-incident-001",
        reconciliation_complete=True,
        rollback_reference="paper-rollback-001",
        paper_only=True,
        broker_action=False,
        provider_call=False,
        network_call=False,
        runtime_execution=False,
        scheduler_activation=False,
        live_trading=False,
        real_money=False,
    )
    receipt = evaluate_paper_soak_incident(**values)
    assert receipt == evaluate_paper_soak_incident(**values)
    assert receipt.accepted is True
    assert receipt.incident_recovered is True
    assert receipt.rollback_validated is True
    assert len(receipt.receipt_id) == 64
    with pytest.raises(FrozenInstanceError):
        receipt.accepted = False


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"paper_only": False}, "paper_only_required"),
        ({"soak_window": ""}, "soak_window_required"),
        ({"incident_id": ""}, "incident_required"),
        ({"reconciliation_complete": False}, "reconciliation_required"),
        ({"rollback_reference": ""}, "rollback_reference_required"),
        ({"broker_action": True}, "broker_action_forbidden"),
        ({"provider_call": True}, "provider_action_forbidden"),
        ({"network_call": True}, "network_action_forbidden"),
        ({"runtime_execution": True}, "runtime_execution_forbidden"),
        ({"scheduler_activation": True}, "scheduler_activation_forbidden"),
        ({"live_trading": True}, "live_trading_forbidden"),
        ({"real_money": True}, "real_money_forbidden"),
    ],
)
def test_paper_soak_incident_fails_closed(overrides, reason):
    from tmp_agent.brain_v9.core.paper_soak_incident_evidence import evaluate_paper_soak_incident

    values = dict(soak_window="SIMULATED_30D", incident_id="paper-incident-001", reconciliation_complete=True, rollback_reference="paper-rollback-001", paper_only=True, broker_action=False, provider_call=False, network_call=False, runtime_execution=False, scheduler_activation=False, live_trading=False, real_money=False)
    assert evaluate_paper_soak_incident(**(values | overrides)).reason == reason


def test_closeout_closes_r15_3_and_binds_disabled_r16_1_without_deploy():
    closeout = json.loads((ROOT / "docs/roadmap/evidence/BRAIN_101_R15_3_PAPER_SOAK_INCIDENT_EVIDENCE_CLOSEOUT.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["roadmap_items"]["R15.3"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    successor = manifest["roadmap_items"]["R16.1"]
    assert successor["status"] == "AUTHORIZED_ACTIVE"
    assert successor["automation"]["deployment_mode"] == "NO_DEPLOY"
    assert successor["automation"]["live_trading_enabled"] is False
    assert closeout["successor"]["roadmap_item"] == "R16.1"
    assert all(value is False for value in closeout["runtime_actions"].values())
