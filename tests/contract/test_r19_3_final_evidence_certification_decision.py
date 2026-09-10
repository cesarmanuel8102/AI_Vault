"""R19.3 contract: final evidence cannot self-certify BRAIN-101."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _assess(**overrides):
    from tmp_agent.brain_v9.core.brain_101_final_certification_decision import (
        assess_final_evidence_certification_decision,
    )

    values = {
        "r19_1_gate_matrix_verified": True,
        "r19_2_adversarial_resilience_verified": True,
        "all_governed_roadmap_evidence_verified": True,
        "persistent_agent_loop_deferred": True,
        "live_trading": False,
        "real_money": False,
        "canonical_local_sync": False,
        "auto_merge": False,
        "runtime_action_requested": False,
        "certification_claim_requested": False,
        "human_final_authority_asserted": False,
    }
    values.update(overrides)
    return assess_final_evidence_certification_decision(**values)


def test_complete_evidence_is_immutable_deterministic_and_requires_human_final_authority():
    first, second = _assess(), _assess()
    assert first == second
    assert first.decision == "FINAL_CERTIFICATION_EVIDENCE_VERIFIED"
    assert first.brain_101_certified is False
    assert first.runtime_permitted is False
    assert first.human_final_authority_required is True
    assert first.denial_reasons == ()
    assert first.deferred_capabilities == ("persistent_agent_loop",)
    assert len(first.receipt_sha256) == 64
    with pytest.raises(FrozenInstanceError):
        first.decision = "REJECT"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"r19_1_gate_matrix_verified": False}, "r19_1_gate_matrix_verification_required"),
        ({"r19_2_adversarial_resilience_verified": False}, "r19_2_adversarial_resilience_verification_required"),
        ({"all_governed_roadmap_evidence_verified": False}, "governed_roadmap_evidence_verification_required"),
        ({"persistent_agent_loop_deferred": False}, "persistent_agent_loop_must_remain_deferred"),
        ({"live_trading": True}, "live_trading_forbidden"),
        ({"real_money": True}, "real_money_forbidden"),
        ({"canonical_local_sync": True}, "canonical_local_sync_forbidden"),
        ({"auto_merge": True}, "auto_merge_forbidden"),
        ({"runtime_action_requested": True}, "runtime_action_forbidden"),
        ({"certification_claim_requested": True}, "certification_claim_requires_human_final_authority"),
        ({"human_final_authority_asserted": True}, "human_final_authority_requires_governed_closeout"),
        ({"r19_1_gate_matrix_verified": "true"}, "invalid_r19_1_gate_matrix_verified"),
    ],
)
def test_final_evidence_fails_closed_for_missing_gates_effects_or_unverified_authority(overrides, reason):
    receipt = _assess(**overrides)
    assert receipt.decision == "REJECT"
    assert receipt.brain_101_certified is False
    assert receipt.runtime_permitted is False
    assert reason in receipt.denial_reasons


def test_evidence_receipt_records_deferred_controls_without_a_final_certification_claim():
    evidence = json.loads(
        (ROOT / "docs/roadmap/evidence/BRAIN_101_R19_3_FINAL_EVIDENCE_CERTIFICATION_DECISION.json").read_text(
            encoding="utf-8"
        )
    )
    assert evidence["roadmap_item"] == "R19.3"
    assert evidence["decision"] == "FINAL_CERTIFICATION_EVIDENCE_VERIFIED"
    assert evidence["brain_101_certified"] is False
    assert evidence["human_final_authority_required"] is True
    assert evidence["deferred_capabilities"] == ["persistent_agent_loop"]
    assert all(value is False for value in evidence["runtime_actions"].values())


def test_human_final_authority_closeout_certifies_without_enabling_runtime():
    closeout = json.loads(
        (ROOT / "docs/roadmap/evidence/BRAIN_101_R19_3_FINAL_EVIDENCE_CERTIFICATION_DECISION_CLOSEOUT.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads((ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json").read_text(encoding="utf-8"))
    scorecard = json.loads((ROOT / "docs/roadmap/BRAIN_101_SCORECARD.json").read_text(encoding="utf-8"))
    assert closeout["implementation_merge"] == "9fcadfa198fac70ab3ea29d8e42891b17533596b"
    assert closeout["owner_final_authority"] is True
    assert closeout["brain_101_certified"] is True
    assert all(value is False for value in closeout["runtime_actions"].values())
    assert manifest["brain_101_certified"] is False
    assert manifest["historical_internal_certification"]["event"] == "RECORDED"
    assert manifest["historical_internal_certification"]["owner_authority"] is True
    assert manifest["external_certification"] == {
        "accepted": False,
        "status": "REJECTED_PENDING_REMEDIATION",
    }
    assert manifest["current_program"] == {
        "program": "BRAIN-101-REMEDIATION",
        "status": "REMEDIATION_REQUIRED",
    }
    assert manifest["roadmap_items"]["R19.3"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    assert [item_id for item_id, item in manifest["roadmap_items"].items() if item["status"] == "AUTHORIZED_ACTIVE"] == []
    assert scorecard["status"] == "BRAIN_101_REMEDIATION_REQUIRED"
    assert scorecard["certified_score"] == 101
    assert scorecard["historical_internal_certified_score"] == 101
