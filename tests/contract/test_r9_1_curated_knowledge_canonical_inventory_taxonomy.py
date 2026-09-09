"""R9.1 contract: curated knowledge is static, versioned, and read-only."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_catalog_exposes_a_deterministic_versioned_inventory_with_provenance():
    from tmp_agent.brain_v9.core.curated_knowledge_catalog import curated_knowledge_inventory

    inventory = curated_knowledge_inventory()

    assert tuple(entry.knowledge_id for entry in inventory) == (
        "BRAIN-101-CURATED-GOVERNANCE",
        "BRAIN-101-CURATED-OPERATIONS",
    )
    assert all(entry.version == "1.0.0" for entry in inventory)
    assert all(entry.provenance_kind == "canonical_repository" for entry in inventory)
    assert all(entry.provenance_reference.startswith("docs/") for entry in inventory)
    with pytest.raises(FrozenInstanceError):
        inventory[0].version = "2.0.0"


def test_lookup_returns_only_the_exact_versioned_entry_and_read_only_provenance():
    from tmp_agent.brain_v9.core.curated_knowledge_catalog import lookup_curated_knowledge

    entry = lookup_curated_knowledge("BRAIN-101-CURATED-GOVERNANCE", version="1.0.0")

    assert entry.knowledge_id == "BRAIN-101-CURATED-GOVERNANCE"
    assert entry.taxonomy == "governance"
    assert entry.version == "1.0.0"
    assert entry.provenance_kind == "canonical_repository"
    assert entry.provenance_reference == "docs/roadmap/BRAIN_101_MANIFEST.json"
    assert entry.read_only is True


@pytest.mark.parametrize(
    ("knowledge_id", "version", "error"),
    [
        ("UNKNOWN", "1.0.0", "unknown_curated_knowledge"),
        ("BRAIN-101-CURATED-GOVERNANCE", None, "version_required"),
        ("BRAIN-101-CURATED-GOVERNANCE", "2.0.0", "unknown_curated_knowledge_version"),
        ("BRAIN-101-CURATED-GOVERNANCE", "", "version_required"),
    ],
)
def test_lookup_fails_closed_for_unknown_or_unversioned_knowledge(knowledge_id, version, error):
    from tmp_agent.brain_v9.core.curated_knowledge_catalog import lookup_curated_knowledge

    with pytest.raises(ValueError, match=error):
        lookup_curated_knowledge(knowledge_id, version=version)


def test_catalog_rejects_semantic_memory_writes_source_ingestion_network_and_provider_calls():
    from tmp_agent.brain_v9.core.curated_knowledge_catalog import reject_curated_knowledge_operation

    for operation in (
        "semantic_memory_write",
        "source_ingestion",
        "network_fetch",
        "provider_call",
        "catalog_mutation",
    ):
        with pytest.raises(ValueError, match="curated_knowledge_read_only"):
            reject_curated_knowledge_operation(operation)


@pytest.mark.parametrize("operation", ("", "unknown_operation", "semantic-memory-write"))
def test_catalog_rejects_unrecognized_operations_fail_closed(operation):
    from tmp_agent.brain_v9.core.curated_knowledge_catalog import reject_curated_knowledge_operation

    with pytest.raises(ValueError, match="curated_knowledge_operation_forbidden"):
        reject_curated_knowledge_operation(operation)


def test_evidence_records_static_catalog_and_no_runtime_effects():
    evidence_path = ROOT / "docs/roadmap/evidence/BRAIN_101_R9_1_CURATED_KNOWLEDGE_CANONICAL_INVENTORY_TAXONOMY.json"

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert evidence["roadmap_item"] == "R9.1"
    assert evidence["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert evidence["catalog"]["version"] == "1.0.0"
    assert evidence["runtime_actions"] == {
        "worker_install": False,
        "scheduler_activation": False,
        "semantic_memory_write": False,
        "source_ingestion": False,
        "provider_call": False,
        "network_access": False,
        "canonical_local_sync": False,
        "live_trading": False,
        "real_money": False,
    }


def test_closeout_authorizes_only_r9_2_with_a_no_deploy_canary_planning_scope():
    manifest = json.loads((ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json").read_text(encoding="utf-8"))
    closeout_path = ROOT / "docs/roadmap/evidence/BRAIN_101_R9_1_CURATED_KNOWLEDGE_CANONICAL_INVENTORY_TAXONOMY_CLOSEOUT.json"

    active = [
        item_id
        for item_id, item in manifest["roadmap_items"].items()
        if item["status"] == "AUTHORIZED_ACTIVE"
    ]
    r91 = manifest["roadmap_items"]["R9.1"]
    r92 = manifest["roadmap_items"]["R9.2"]
    closeout = json.loads(closeout_path.read_text(encoding="utf-8"))

    assert r91["status"] == "CLOSED_RUNTIME_VERIFIED"
    assert active == ["R9.2"]
    assert r92["automation"]["front_id"] == "BRAIN-101-R9-2-CURATED-KNOWLEDGE-CONTROLLED-INGESTION-BENCHMARK-01"
    assert r92["automation"]["work_branch"] == "control-plane/r9-2-curated-knowledge-controlled-ingestion-benchmark"
    assert r92["automation"]["deployment_mode"] == "NO_DEPLOY"
    assert r92["automation"]["allowed_paths"] == [
        "tmp_agent/brain_v9/core/curated_knowledge_ingestion.py",
        "docs/roadmap/evidence/BRAIN_101_R9_2_CURATED_KNOWLEDGE_CONTROLLED_INGESTION_BENCHMARK.json",
        "tests/contract/test_r9_2_curated_knowledge_controlled_ingestion_benchmark.py",
    ]
    assert closeout["parent_merge_commit"] == "b5105efaff840a4b4129c728207b28e9de1a5e71"
    assert closeout["verification_level"] == "CODE_AND_CI_VERIFIED_NO_DEPLOY"
    assert closeout["runtime_actions"]["worker_install"] is False
    assert closeout["runtime_actions"]["scheduler_activation"] is False
    assert closeout["runtime_actions"]["source_ingestion"] is False
