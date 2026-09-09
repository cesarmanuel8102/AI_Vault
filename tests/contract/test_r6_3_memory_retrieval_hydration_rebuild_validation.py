"""R6.3 contract: isolated semantic retrieval hydration and rebuild validation."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_agent"))

ARTIFACTS = (
    "semantic_memory.jsonl",
    "semantic_memory_faiss.index",
    "semantic_memory_faiss_ids.json",
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _artifact_hashes(root: Path) -> dict[str, str]:
    return {name: _sha256((root / name).read_bytes()) for name in ARTIFACTS}


def _records() -> list[dict[str, object]]:
    return [
        {
            "id": "memory-001",
            "source": "governed-evidence-001",
            "kind": "lesson",
            "text": "Memory hydration remains isolated and attributable.",
            "metadata": {"room_id": "room_alpha"},
        },
        {
            "id": "memory-002",
            "source": "governed-evidence-002",
            "kind": "lesson",
            "text": "Deterministic rebuild validates topology before retrieval.",
            "metadata": {"room_id": "room_alpha"},
        },
    ]


def _snapshot_root(tmp_path: Path) -> Path:
    root = tmp_path / "explicit-isolated-snapshot"
    root.mkdir()
    records = _records()
    (root / ".r6_3_isolated_retrieval_snapshot").write_text("isolated\n", encoding="utf-8")
    (root / "semantic_memory.jsonl").write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8"
    )
    (root / "semantic_memory_faiss_ids.json").write_text(
        json.dumps([record["id"] for record in records]) + "\n", encoding="utf-8"
    )
    (root / "semantic_memory_faiss.index").write_bytes(b"deterministic-source-index-v1")
    manifest = {
        "schema_version": 1,
        "snapshot_id": "r6-3-isolated-snapshot-001",
        "artifact_sha256": _artifact_hashes(root),
    }
    (root / "hydration_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    return root


def _isolated_root(tmp_path: Path) -> Path:
    root = tmp_path / "isolated-retrieval-target"
    root.mkdir()
    (root / ".r6_3_isolated_retrieval_root").write_text("isolated\n", encoding="utf-8")
    (root / "semantic_memory.jsonl").write_bytes(b'{"id":"before","source":"before"}\n')
    (root / "semantic_memory_faiss.index").write_bytes(b"before-index")
    (root / "semantic_memory_faiss_ids.json").write_bytes(b'["before"]\n')
    return root


def test_hydration_requires_explicit_attributable_snapshot_and_isolated_target(tmp_path, monkeypatch):
    from brain_v9.core.memory_service import MemoryService

    service = MemoryService(tmp_path / "configured-semantic")
    snapshot = _snapshot_root(tmp_path)
    target = _isolated_root(tmp_path)

    prepared = service.prepare_isolated_retrieval_hydration(snapshot)
    result = service.hydrate_isolated_retrieval(prepared["receipt"], target)

    assert prepared["ok"] is True
    assert prepared["receipt"]["snapshot_id"] == "r6-3-isolated-snapshot-001"
    assert prepared["receipt"]["record_provenance"] == [
        {"id": "memory-001", "source": "governed-evidence-001"},
        {"id": "memory-002", "source": "governed-evidence-002"},
    ]
    assert result["ok"] is True
    assert result["write_performed"] is True
    assert result["source_snapshot_id"] == prepared["receipt"]["snapshot_id"]
    assert _artifact_hashes(target) == _artifact_hashes(snapshot)
    isolated_service = MemoryService(target)
    monkeypatch.setattr(
        isolated_service,
        "_faiss_retrieve",
        lambda _query, _top_k: (_ for _ in ()).throw(RuntimeError("isolated backend unavailable")),
    )
    retrieval = isolated_service.retrieve("isolated attributable", top_k=2)
    assert retrieval["write_performed"] is False
    assert retrieval["backend"] == "jsonl_keyword"
    assert retrieval["hits"][0]["id"] == "memory-001"
    assert retrieval["hits"][0]["source"] == "governed-evidence-001"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("opaque_source", "snapshot_record_source_invalid"),
        ("ids_topology", "snapshot_faiss_topology_inconsistent"),
        ("manifest_hash", "snapshot_artifact_hash_mismatch"),
    ],
)
def test_hydration_rejects_opaque_or_inconsistent_snapshot_before_target_write(
    tmp_path, mutation, reason
):
    from brain_v9.core.memory_service import MemoryService

    service = MemoryService(tmp_path / "configured-semantic")
    snapshot = _snapshot_root(tmp_path)
    target = _isolated_root(tmp_path)
    before = _artifact_hashes(target)
    if mutation == "opaque_source":
        records = _records()
        records[0]["source"] = ""
        (snapshot / "semantic_memory.jsonl").write_text(
            "".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8"
        )
    elif mutation == "ids_topology":
        (snapshot / "semantic_memory_faiss_ids.json").write_text('["memory-001","foreign"]\n', encoding="utf-8")
    else:
        manifest = json.loads((snapshot / "hydration_manifest.json").read_text(encoding="utf-8"))
        manifest["artifact_sha256"]["semantic_memory.jsonl"] = "0" * 64
        (snapshot / "hydration_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if mutation in {"opaque_source", "ids_topology"}:
        manifest = json.loads((snapshot / "hydration_manifest.json").read_text(encoding="utf-8"))
        manifest["artifact_sha256"] = _artifact_hashes(snapshot)
        (snapshot / "hydration_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = service.prepare_isolated_retrieval_hydration(snapshot)

    assert result == {"ok": False, "reason": reason, "write_performed": False}
    assert _artifact_hashes(target) == before


def test_hydration_rejects_canonical_target_before_copy(tmp_path):
    from brain_v9.core.memory_service import MemoryService

    service = MemoryService(tmp_path / "configured-semantic")
    snapshot = _snapshot_root(tmp_path)
    prepared = service.prepare_isolated_retrieval_hydration(snapshot)

    assert service.hydrate_isolated_retrieval(prepared["receipt"], service.semantic_root) == {
        "ok": False,
        "reason": "canonical_hydration_not_enabled",
        "write_performed": False,
    }
    assert not service.semantic_root.exists()


def test_failed_rebuild_rolls_back_hydrated_isolated_artifacts_byte_for_byte(tmp_path, monkeypatch):
    from brain_v9.core.memory_service import MemoryService

    service = MemoryService(tmp_path / "configured-semantic")
    snapshot = _snapshot_root(tmp_path)
    target = _isolated_root(tmp_path)
    hydrated = service.hydrate_isolated_retrieval(
        service.prepare_isolated_retrieval_hydration(snapshot)["receipt"], target
    )
    before = _artifact_hashes(target)

    def corrupting_rebuild(_receipt, root):
        (root / "semantic_memory_faiss.index").write_bytes(b"partially-rebuilt")
        (root / "semantic_memory_faiss_ids.json").write_text('["missing"]\n', encoding="utf-8")
        return {"ok": True}

    monkeypatch.setattr(service, "_isolated_retrieval_rebuild", corrupting_rebuild, raising=False)
    result = service.rebuild_isolated_retrieval(hydrated["hydration_receipt"], target)

    assert result["ok"] is False
    assert result["reason"] == "isolated_rebuild_failed"
    assert result["rollback"]["ok"] is True
    assert _artifact_hashes(target) == before


def test_deterministic_rebuild_identity_requires_exact_hydration_receipt(tmp_path, monkeypatch):
    from brain_v9.core.memory_service import MemoryService

    service = MemoryService(tmp_path / "configured-semantic")
    snapshot = _snapshot_root(tmp_path)
    target = _isolated_root(tmp_path)
    hydrated = service.hydrate_isolated_retrieval(
        service.prepare_isolated_retrieval_hydration(snapshot)["receipt"], target
    )

    def deterministic_rebuild(receipt, root):
        (root / "semantic_memory_faiss.index").write_bytes(
            ("rebuild:" + receipt["rebuild_identity_sha256"]).encode("ascii")
        )
        return {"ok": True, "rebuild_identity_sha256": receipt["rebuild_identity_sha256"]}

    monkeypatch.setattr(service, "_isolated_retrieval_rebuild", deterministic_rebuild, raising=False)
    result = service.rebuild_isolated_retrieval(hydrated["hydration_receipt"], target)

    assert result["ok"] is True
    assert result["write_performed"] is True
    assert result["rebuild_identity_sha256"] == hydrated["hydration_receipt"]["rebuild_identity_sha256"]
    tampered = dict(hydrated["hydration_receipt"])
    tampered["snapshot_id"] = "substituted"
    assert service.rebuild_isolated_retrieval(tampered, target) == {
        "ok": False,
        "reason": "hydration_receipt_invalid",
        "write_performed": False,
    }


def test_r6_3_evidence_binds_isolated_validation_to_no_deploy_contract():
    evidence_path = (
        ROOT
        / "docs/roadmap/evidence/"
        "BRAIN_101_R6_3_MEMORY_RETRIEVAL_HYDRATION_REBUILD_VALIDATION.json"
    )
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert evidence["roadmap_item_id"] == "R6.3"
    assert evidence["base_commit"] == "0c1956ce64ceebe6e7f82352d7bde35214d54525"
    assert evidence["verification_head_before_evidence"] == "d2f307450d6298444416569c92eb3a544baa11f7"
    assert evidence["deployment_mode"] == "NO_DEPLOY"
    assert evidence["runtime_actions"] == {
        "worker_install": False,
        "scheduler_activation": False,
        "provider_call": False,
        "canonical_memory_mutation": False,
    }


def test_r6_3_closeout_authorizes_only_bound_r7_1_trace_successor():
    closeout = json.loads(
        (
            ROOT
            / "docs/roadmap/evidence/"
            "BRAIN_101_R6_3_MEMORY_RETRIEVAL_HYDRATION_REBUILD_VALIDATION_CLOSEOUT.json"
        ).read_text(encoding="utf-8")
    )
    manifest = json.loads((ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json").read_text(encoding="utf-8"))

    assert closeout["roadmap_item_id"] == "R6.3"
    assert closeout["parent_merge_commit"] == "31ab5832e443bc4e820c0cd502e898e1f924e10e"
    assert closeout["result"] == "CLOSED_RUNTIME_VERIFIED"
    assert manifest["roadmap_items"]["R6.3"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    assert closeout["next_item"] == {
        "roadmap_item_id": "R7.1",
        "front_id": "BRAIN-101-R7-1-GOVERNED-TRACE-SCHEMA-EVENT-WRITER-BASELINE-01",
        "executor": "codex_control_plane",
        "deployment_mode": "NO_DEPLOY",
        "expected_base_sha_source": (
            "sequenceRoadmap resolves the exact live canonical integration-branch head "
            "at governed dispatch"
        ),
        "jit_binding_completed": True,
    }
    active = [key for key, item in manifest["roadmap_items"].items() if item["status"] == "AUTHORIZED_ACTIVE"]
    assert active == ["R7.1"]
    automation = manifest["roadmap_items"]["R7.1"]["automation"]
    assert automation["dispatchable"] is True
    assert automation["closeout"]["front_id"] == (
        "BRAIN-101-R7-1-GOVERNED-TRACE-SCHEMA-EVENT-WRITER-BASELINE-CLOSEOUT-01"
    )
