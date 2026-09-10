"""R17.2 contract: contain a candidate without creating distributed runtime effects."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _decide(**overrides):
    from tmp_agent.brain_v9.core.microservice_containment_decision import (
        decide_microservice_containment,
    )

    values = {
        "component_id": "provider_gateway",
        "candidate_eligible": True,
        "source_evidence_verified": True,
        "feature_flag_required": True,
        "versioned_api_required": True,
        "shared_filesystem_dependency": False,
        "distributed_runtime_requested": False,
        "deployment_requested": False,
        "scheduler_activation": False,
        "network_call": False,
        "canonical_local_sync": False,
        "live_trading": False,
        "real_money": False,
        "auto_merge": False,
    }
    values.update(overrides)
    return decide_microservice_containment(**values)


def test_evidence_backed_candidate_is_justifiably_deferred_with_immutable_containment_receipt():
    first = _decide()
    second = _decide()

    assert first == second
    assert first.decision == "JUSTIFIABLY_DEFERRED"
    assert first.containment_required is True
    assert first.extraction_authorized is False
    assert first.deployment_permitted is False
    assert first.denial_reasons == ()
    assert len(first.receipt_sha256) == 64
    with pytest.raises(FrozenInstanceError):
        first.decision = "SELECTIVE_EXTRACTION_COMPLETE"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"candidate_eligible": False}, "eligible_candidate_required"),
        ({"source_evidence_verified": False}, "source_evidence_required"),
        ({"feature_flag_required": False}, "feature_flag_required"),
        ({"versioned_api_required": False}, "versioned_api_required"),
        ({"shared_filesystem_dependency": True}, "shared_filesystem_dependency_forbidden"),
        ({"distributed_runtime_requested": True}, "distributed_runtime_forbidden"),
        ({"deployment_requested": True}, "deployment_forbidden"),
        ({"scheduler_activation": True}, "scheduler_activation_forbidden"),
        ({"network_call": True}, "network_call_forbidden"),
        ({"canonical_local_sync": True}, "canonical_local_sync_forbidden"),
        ({"live_trading": True}, "live_trading_forbidden"),
        ({"real_money": True}, "real_money_forbidden"),
        ({"auto_merge": True}, "auto_merge_forbidden"),
    ],
)
def test_containment_fails_closed_for_missing_evidence_or_effects(overrides, reason):
    receipt = _decide(**overrides)

    assert receipt.decision == "REJECT"
    assert receipt.extraction_authorized is False
    assert receipt.deployment_permitted is False
    assert reason in receipt.denial_reasons


def test_evidence_records_justified_deferral_without_runtime_actions():
    evidence = json.loads(
        (ROOT / "docs/roadmap/evidence/BRAIN_101_R17_2_SELECTIVE_MICROSERVICE_DECISION_CONTAINMENT.json").read_text(encoding="utf-8")
    )
    assert evidence["roadmap_item"] == "R17.2"
    assert evidence["decision"] == "JUSTIFIABLY_DEFERRED"
    assert evidence["containment"]["feature_flag_required"] is True
    assert evidence["containment"]["versioned_api_required"] is True
    assert all(value is False for value in evidence["runtime_actions"].values())
