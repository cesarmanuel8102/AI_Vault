"""R10.1 contract: capability-gap evaluation is deterministic and effect-free."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _requirements():
    return (
        {"capability_id": "auditable_retrieval", "risk": "P1", "required": True},
        {"capability_id": "provider_gateway", "risk": "P2", "required": True},
        {"capability_id": "optional_telemetry", "risk": "P3", "required": False},
    )


def test_evaluation_is_canonical_immutable_and_produces_proposal_provenance():
    from tmp_agent.brain_v9.core.self_improvement_capability import evaluate_capability_gaps

    first = evaluate_capability_gaps(
        requirements=_requirements(),
        available_capability_ids=("provider_gateway",),
        learning_journal_reference="journal://brain-101/r10-1/evaluation-001",
    )
    second = evaluate_capability_gaps(
        requirements=tuple(reversed(_requirements())),
        available_capability_ids=("provider_gateway",),
        learning_journal_reference="journal://brain-101/r10-1/evaluation-001",
    )

    assert first == second
    assert [gap.capability_id for gap in first.gaps] == ["auditable_retrieval"]
    assert first.gaps[0].risk == "P1"
    assert first.proposal.provenance_sha256 == second.proposal.provenance_sha256
    assert first.proposal.learning_journal_reference == "journal://brain-101/r10-1/evaluation-001"
    assert first.proposal.apply_permitted is False
    with pytest.raises(FrozenInstanceError):
        first.gaps[0].capability_id = "changed"


@pytest.mark.parametrize("risk", ("P0", "P1", "P2", "P3"))
def test_evaluation_preserves_each_supported_gap_risk(risk):
    from tmp_agent.brain_v9.core.self_improvement_capability import evaluate_capability_gaps

    evaluation = evaluate_capability_gaps(
        requirements=({"capability_id": "governed_capability", "risk": risk, "required": True},),
        available_capability_ids=(),
        learning_journal_reference="journal://brain-101/r10-1/evaluation-001",
    )

    assert evaluation.gaps == (type(evaluation.gaps[0])("governed_capability", risk),)


@pytest.mark.parametrize(
    ("requirements", "available", "error"),
    [
        (({"capability_id": "bad_risk", "risk": "P4", "required": True},), (), "invalid_risk"),
        (({"capability_id": "duplicate", "risk": "P0", "required": True}, {"capability_id": "duplicate", "risk": "P1", "required": True}), (), "duplicate_capability_id"),
        (({"capability_id": "unsafe id", "risk": "P0", "required": True},), (), "invalid_capability_id"),
    ],
)
def test_evaluation_rejects_ambiguous_or_invalid_capability_inputs(requirements, available, error):
    from tmp_agent.brain_v9.core.self_improvement_capability import evaluate_capability_gaps

    with pytest.raises(ValueError, match=error):
        evaluate_capability_gaps(
            requirements=requirements,
            available_capability_ids=available,
            learning_journal_reference="journal://brain-101/r10-1/evaluation-001",
        )


@pytest.mark.parametrize(
    "operation",
    (
        "self_governance_modification",
        "runtime_mutation",
        "automatic_promotion",
        "provider_call",
        "network_fetch",
        "semantic_memory_write",
        "canonical_memory_write",
    ),
)
def test_evaluation_contract_rejects_all_effectful_operations(operation):
    from tmp_agent.brain_v9.core.self_improvement_capability import reject_self_improvement_execution

    with pytest.raises(ValueError, match="evaluation_only"):
        reject_self_improvement_execution(operation)


def test_evidence_records_planning_only_and_no_runtime_effects():
    evidence = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/"
            "BRAIN_101_R10_1_GOVERNED_SELF_IMPROVEMENT_CAPABILITY_GAP_EVALUATION.json"
        ).read_text(encoding="utf-8")
    )

    assert evidence["roadmap_item"] == "R10.1"
    assert evidence["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert evidence["proposal_contract"]["apply_permitted"] is False
    assert all(value is False for value in evidence["runtime_actions"].values())
