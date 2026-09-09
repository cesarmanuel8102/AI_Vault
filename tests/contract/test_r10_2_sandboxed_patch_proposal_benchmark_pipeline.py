"""R10.2 contract: sandboxed patch proposals remain deterministic and inert."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_benchmark_produces_immutable_canonical_proposal_and_receipt():
    from tmp_agent.brain_v9.core.sandboxed_patch_proposal import benchmark_sandboxed_patch_proposal

    kwargs = {
        "proposal_id": "proposal_r10_2_001",
        "base_revision": "a" * 40,
        "unified_diff": "--- a/example.py\n+++ b/example.py\n@@ -1 +1 @@\n-old\n+new\n",
        "benchmark_cases": ({"case_id": "syntax", "expected": "pass"}, {"case_id": "policy", "expected": "pass"}),
    }
    first = benchmark_sandboxed_patch_proposal(**kwargs)
    second = benchmark_sandboxed_patch_proposal(**{**kwargs, "benchmark_cases": tuple(reversed(kwargs["benchmark_cases"]))})

    assert first == second
    assert first.proposal.proposal_id == "proposal_r10_2_001"
    assert first.proposal.apply_permitted is False
    assert len(first.proposal.patch_sha256) == 64
    assert len(first.receipt.benchmark_sha256) == 64
    assert first.receipt.benchmark_case_ids == ("policy", "syntax")
    with pytest.raises(FrozenInstanceError):
        first.proposal.proposal_id = "changed"


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"proposal_id": "bad id"}, "invalid_proposal_id"),
        ({"base_revision": "not-a-sha"}, "invalid_base_revision"),
        ({"unified_diff": ""}, "invalid_unified_diff"),
        ({"benchmark_cases": ()}, "empty_benchmark_cases"),
        ({"benchmark_cases": ({"case_id": "duplicate", "expected": "pass"}, {"case_id": "duplicate", "expected": "pass"})}, "duplicate_benchmark_case_id"),
    ],
)
def test_benchmark_rejects_ambiguous_or_invalid_inputs(kwargs, error):
    from tmp_agent.brain_v9.core.sandboxed_patch_proposal import benchmark_sandboxed_patch_proposal

    valid = {
        "proposal_id": "proposal_r10_2_001",
        "base_revision": "a" * 40,
        "unified_diff": "--- a/example.py\n+++ b/example.py\n@@ -1 +1 @@\n-old\n+new\n",
        "benchmark_cases": ({"case_id": "syntax", "expected": "pass"},),
    }
    valid.update(kwargs)
    with pytest.raises(ValueError, match=error):
        benchmark_sandboxed_patch_proposal(**valid)


@pytest.mark.parametrize(
    "operation",
    (
        "patch_apply",
        "filesystem_write",
        "runtime_mutation",
        "self_governance_modification",
        "automatic_promotion",
        "provider_call",
        "network_fetch",
        "semantic_memory_write",
        "canonical_memory_write",
    ),
)
def test_pipeline_rejects_all_effectful_operations(operation):
    from tmp_agent.brain_v9.core.sandboxed_patch_proposal import reject_sandboxed_patch_execution

    with pytest.raises(ValueError, match="proposal_only"):
        reject_sandboxed_patch_execution(operation)


def test_evidence_records_no_deploy_and_no_patch_application():
    evidence = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/"
            "BRAIN_101_R10_2_SANDBOXED_PATCH_PROPOSAL_BENCHMARK_PIPELINE.json"
        ).read_text(encoding="utf-8")
    )

    assert evidence["roadmap_item"] == "R10.2"
    assert evidence["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert evidence["proposal_contract"]["apply_permitted"] is False
    assert all(value is False for value in evidence["runtime_actions"].values())
