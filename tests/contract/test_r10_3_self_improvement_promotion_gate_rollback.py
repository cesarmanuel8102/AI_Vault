"""R10.3 contract: self-improvement promotion remains human-approved and inert."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_promotion_decision_requires_exact_human_approval_and_emits_immutable_receipts():
    from tmp_agent.brain_v9.core.self_improvement_promotion import evaluate_self_improvement_promotion

    kwargs = {
        "proposal_id": "proposal_r10_3_001",
        "proposal_sha256": "a" * 64,
        "human_approval_id": "owner_approval_r10_3_001",
        "approved_proposal_sha256": "a" * 64,
    }
    first = evaluate_self_improvement_promotion(**kwargs)
    second = evaluate_self_improvement_promotion(**kwargs)

    assert first == second
    assert first.decision.proposal_id == "proposal_r10_3_001"
    assert first.decision.human_final_authority is True
    assert first.decision.apply_permitted is False
    assert len(first.decision.decision_sha256) == 64
    assert first.rollback_receipt.rollback_required is True
    assert len(first.rollback_receipt.receipt_sha256) == 64
    with pytest.raises(FrozenInstanceError):
        first.decision.proposal_id = "changed"


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"proposal_id": "bad id"}, "invalid_proposal_id"),
        ({"proposal_sha256": "not-a-sha"}, "invalid_proposal_sha256"),
        ({"human_approval_id": ""}, "invalid_human_approval_id"),
        ({"approved_proposal_sha256": "b" * 64}, "human_approval_provenance_mismatch"),
    ],
)
def test_promotion_rejects_missing_or_mismatched_human_authority(kwargs, error):
    from tmp_agent.brain_v9.core.self_improvement_promotion import evaluate_self_improvement_promotion

    valid = {
        "proposal_id": "proposal_r10_3_001",
        "proposal_sha256": "a" * 64,
        "human_approval_id": "owner_approval_r10_3_001",
        "approved_proposal_sha256": "a" * 64,
    }
    valid.update(kwargs)
    with pytest.raises(ValueError, match=error):
        evaluate_self_improvement_promotion(**valid)


@pytest.mark.parametrize(
    "operation",
    (
        "patch_apply",
        "filesystem_write",
        "runtime_mutation",
        "automatic_promotion",
        "provider_call",
        "network_fetch",
        "semantic_memory_write",
        "canonical_memory_write",
        "scheduler_mutation",
        "canonical_local_sync",
        "live_trading",
        "real_money",
        "auto_merge",
    ),
)
def test_promotion_gate_rejects_all_effectful_operations(operation):
    from tmp_agent.brain_v9.core.self_improvement_promotion import reject_promotion_effect

    with pytest.raises(ValueError, match="promotion_gate_only"):
        reject_promotion_effect(operation)


def test_evidence_records_human_authority_and_no_deploy_boundaries():
    evidence = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/"
            "BRAIN_101_R10_3_SELF_IMPROVEMENT_PROMOTION_GATE_ROLLBACK.json"
        ).read_text(encoding="utf-8")
    )

    assert evidence["roadmap_item"] == "R10.3"
    assert evidence["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert evidence["promotion_contract"]["human_final_authority_required"] is True
    assert evidence["promotion_contract"]["apply_permitted"] is False
    assert all(value is False for value in evidence["runtime_actions"].values())


def test_closeout_records_merged_evidence_and_only_authorizes_r11_1():
    closeout = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/"
            "BRAIN_101_R10_3_SELF_IMPROVEMENT_PROMOTION_GATE_ROLLBACK_CLOSEOUT.json"
        ).read_text(encoding="utf-8")
    )

    assert closeout["roadmap_item"] == "R10.3"
    assert closeout["implementation_merge_commit"] == "efc1b39d943051392a519b8027ad0bc784e2d3e9"
    assert closeout["successor"] == {
        "roadmap_item": "R11.1",
        "front_id": "BRAIN-101-R11-1-FINANCIAL-AUTONOMY-PAPER-ONLY-RUNTIME-INVENTORY-01",
        "deployment_mode": "NO_DEPLOY",
    }
    assert all(value is False for value in closeout["runtime_actions"].values())
