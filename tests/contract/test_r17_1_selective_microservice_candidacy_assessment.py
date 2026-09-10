"""R17.1 contract: assess extraction candidacy without a distributed runtime."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import json

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _assess(**overrides):
    from tmp_agent.brain_v9.core.microservice_candidacy_assessment import (
        assess_microservice_candidacy,
    )

    values = {
        "component_id": "provider_gateway",
        "ownership_stable": True,
        "contract_e2e_verified": True,
        "rollback_evidence_verified": True,
        "operational_justification": True,
        "economic_justification": True,
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
    return assess_microservice_candidacy(**values)


def test_eligible_candidate_emits_immutable_deterministic_no_deploy_receipt():
    first = _assess()
    second = _assess()

    assert first == second
    assert first.component_id == "provider_gateway"
    assert first.candidate_eligible is True
    assert first.recommended_action == "R17_2_CONTAINMENT_REVIEW"
    assert first.extraction_authorized is False
    assert first.deployment_permitted is False
    assert first.denial_reasons == ()
    assert len(first.receipt_sha256) == 64
    with pytest.raises(FrozenInstanceError):
        first.candidate_eligible = False


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"ownership_stable": False}, "ownership_stability_required"),
        ({"contract_e2e_verified": False}, "contract_e2e_required"),
        ({"rollback_evidence_verified": False}, "rollback_evidence_required"),
        ({"operational_justification": False}, "operational_justification_required"),
        ({"economic_justification": False}, "economic_justification_required"),
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
def test_candidacy_fails_closed_for_every_missing_or_forbidden_invariant(overrides, reason):
    receipt = _assess(**overrides)

    assert receipt.candidate_eligible is False
    assert receipt.extraction_authorized is False
    assert receipt.deployment_permitted is False
    assert reason in receipt.denial_reasons


@pytest.mark.parametrize(
    "operation",
    (
        "service_process_start",
        "container_start",
        "deployment",
        "scheduler_mutation",
        "network_fetch",
        "canonical_local_sync",
        "live_trading",
        "real_money",
        "auto_merge",
    ),
)
def test_assessment_rejects_every_external_or_distributed_effect(operation):
    from tmp_agent.brain_v9.core.microservice_candidacy_assessment import (
        reject_candidacy_effect,
    )

    with pytest.raises(ValueError, match="microservice_candidacy_no_effects"):
        reject_candidacy_effect(operation)


def test_evidence_records_a_non_deploy_candidate_without_extraction_authority():
    evidence = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/"
            "BRAIN_101_R17_1_SELECTIVE_MICROSERVICE_CANDIDACY_ASSESSMENT.json"
        ).read_text(encoding="utf-8")
    )

    assert evidence["roadmap_item"] == "R17.1"
    assert evidence["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert evidence["candidate"]["component_id"] == "provider_gateway"
    assert evidence["candidate"]["candidate_eligible"] is True
    assert evidence["candidate"]["extraction_authorized"] is False
    assert all(value is False for value in evidence["runtime_actions"].values())


def test_module_is_pure_and_does_not_introduce_a_distributed_runtime():
    source = (
        ROOT / "tmp_agent/brain_v9/core/microservice_candidacy_assessment.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "subprocess",
        "requests",
        "httpx",
        "socket",
        "docker",
        "kubernetes",
        "multiprocessing",
        "import trading",
        "from trading",
        "import financial_autonomy",
        "from financial_autonomy",
    ):
        assert forbidden not in source
