"""R9.2 contract: canary ingestion is planned and benchmarked, never executed."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_canary_plan_is_bound_to_one_versioned_catalog_entry_and_a_bounded_benchmark():
    from tmp_agent.brain_v9.core.curated_knowledge_ingestion import plan_canary_ingestion

    plan = plan_canary_ingestion(
        knowledge_id="BRAIN-101-CURATED-GOVERNANCE",
        version="1.0.0",
        candidate_reference="candidate://governance/v1",
        benchmark_id="curated-governance-canary-v1",
        canary_limit=3,
    )

    assert plan.knowledge_id == "BRAIN-101-CURATED-GOVERNANCE"
    assert plan.version == "1.0.0"
    assert plan.catalog_provenance == "docs/roadmap/BRAIN_101_MANIFEST.json"
    assert plan.canary_limit == 3
    assert plan.benchmark_id == "curated-governance-canary-v1"
    assert plan.execution_permitted is False
    assert plan.automatic_promotion_permitted is False
    with pytest.raises(FrozenInstanceError):
        plan.canary_limit = 4


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"knowledge_id": "UNKNOWN"}, "unknown_curated_knowledge"),
        ({"version": None}, "version_required"),
        ({"candidate_reference": ""}, "candidate_reference_required"),
        ({"candidate_reference": "https://remote.example/source"}, "external_source_reference_forbidden"),
        ({"benchmark_id": ""}, "benchmark_id_required"),
        ({"canary_limit": 0}, "invalid_canary_limit"),
        ({"canary_limit": 11}, "invalid_canary_limit"),
    ],
)
def test_canary_plan_rejects_unbounded_or_untrusted_input(kwargs, error):
    from tmp_agent.brain_v9.core.curated_knowledge_ingestion import plan_canary_ingestion

    args = {
        "knowledge_id": "BRAIN-101-CURATED-GOVERNANCE",
        "version": "1.0.0",
        "candidate_reference": "candidate://governance/v1",
        "benchmark_id": "curated-governance-canary-v1",
        "canary_limit": 1,
    }
    args.update(kwargs)

    with pytest.raises(ValueError, match=error):
        plan_canary_ingestion(**args)


@pytest.mark.parametrize(
    "operation",
    ("source_ingestion", "semantic_memory_write", "network_fetch", "provider_call", "automatic_promotion"),
)
def test_canary_contract_rejects_all_effectful_operations(operation):
    from tmp_agent.brain_v9.core.curated_knowledge_ingestion import reject_canary_execution

    with pytest.raises(ValueError, match="canary_planning_only"):
        reject_canary_execution(operation)


def test_evidence_records_planning_only_and_no_deploy_effects():
    evidence = json.loads(
        (ROOT / "docs/roadmap/evidence/BRAIN_101_R9_2_CURATED_KNOWLEDGE_CONTROLLED_INGESTION_BENCHMARK.json").read_text(encoding="utf-8")
    )

    assert evidence["roadmap_item"] == "R9.2"
    assert evidence["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert evidence["canary_contract"]["execution_permitted"] is False
    assert evidence["canary_contract"]["automatic_promotion_permitted"] is False
    assert all(value is False for value in evidence["runtime_actions"].values())


def test_closeout_records_no_deploy_verification_and_the_only_authorized_successor():
    closeout = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/"
            "BRAIN_101_R9_2_CURATED_KNOWLEDGE_CONTROLLED_INGESTION_BENCHMARK_CLOSEOUT.json"
        ).read_text(encoding="utf-8")
    )

    assert closeout["roadmap_item"] == "R9.2"
    assert closeout["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert closeout["successor"] == {
        "roadmap_item": "R10.1",
        "front_id": "BRAIN-101-R10-1-GOVERNED-SELF-IMPROVEMENT-CAPABILITY-GAP-EVALUATION-01",
        "deployment_mode": "NO_DEPLOY",
    }
    assert all(value is False for value in closeout["runtime_actions"].values())
