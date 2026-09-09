"""R6.1 contract: MemoryService is the sole governed memory boundary."""
from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_agent"))
EVIDENCE = ROOT / "docs/roadmap/evidence/BRAIN_101_R6_1_MEMORY_SERVICE_OWNERSHIP_INTEGRITY_BASELINE.json"
CLOSEOUT_EVIDENCE = (
    ROOT
    / "docs/roadmap/evidence/BRAIN_101_R6_1_MEMORY_SERVICE_OWNERSHIP_INTEGRITY_BASELINE_CLOSEOUT.json"
)


def test_memory_service_exposes_read_only_governed_retrieval(tmp_path):
    """Agent V2 must use one explicit MemoryService, never a backend directly."""
    from brain_v9.core.memory_service import MemoryService

    semantic_root = tmp_path / "memory" / "semantic"
    semantic_root.mkdir(parents=True)
    (semantic_root / "semantic_memory.jsonl").write_text(
        json.dumps(
            {
                "id": "r6-1-record",
                "text": "Memory ownership must remain governed and read only.",
                "source": "r6-contract",
                "kind": "lesson",
                "metadata": {"domain": "memory_governance"},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = MemoryService(semantic_root=semantic_root).retrieve("memory ownership", top_k=2)

    assert result["ok"] is True
    assert result["ownership_boundary"] == "MemoryService"
    assert result["write_performed"] is False
    assert result["hits"]


def test_memory_service_prefers_faiss_for_read_only_retrieval(tmp_path, monkeypatch):
    """The ownership boundary must preserve the existing FAISS read capability."""
    from brain_v9.core.memory_service import MemoryService

    service = MemoryService(semantic_root=tmp_path / "semantic")
    monkeypatch.setattr(
        service,
        "_faiss_retrieve",
        lambda _query, _top_k: [{"id": "faiss-hit", "snippet": "vector hit"}],
        raising=False,
    )

    result = service.retrieve("vector", top_k=1)

    assert result["backend"] == "faiss"
    assert result["degraded"] is False
    assert result["hits"] == [{"id": "faiss-hit", "snippet": "vector hit"}]
    assert result["write_performed"] is False


def test_agent_v2_gateway_has_no_direct_backend_or_mutation_surface(tmp_path):
    """Agent V2 can only read through MemoryService in the R6.1 baseline."""
    from brain_v9.core.agent_kernel_v2.memory_gateway import MemoryGatewayV2
    from brain_v9.core.memory_service import MemoryService

    gateway_source = (ROOT / "tmp_agent/brain_v9/core/agent_kernel_v2/memory_gateway.py").read_text(encoding="utf-8")
    assert "SemanticMemoryFAISS" not in gateway_source
    assert ".read_text(" not in gateway_source
    assert not hasattr(MemoryGatewayV2(memory_service=MemoryService(tmp_path / "semantic")), "promote")

    with pytest.raises(PermissionError, match="disabled"):
        MemoryService(semantic_root=tmp_path / "semantic").promote({"text": "not yet"})


def test_agent_v2_gateway_delegates_retrieval_to_memory_service():
    """The Agent V2 gateway may filter results but cannot pick a storage backend."""
    from brain_v9.core.agent_kernel_v2.memory_gateway import MemoryGatewayV2

    class Service:
        def __init__(self):
            self.calls = []

        def retrieve(self, query, top_k):
            self.calls.append((query, top_k))
            return {
                "ok": True,
                "backend": "controlled-test",
                "ownership_boundary": "MemoryService",
                "hits": [
                    {
                        "id": "gateway-record",
                        "text": "governed semantic memory",
                        "snippet": "governed semantic memory",
                        "source": "contract",
                        "kind": "lesson",
                    }
                ],
                "write_performed": False,
            }

    service = Service()
    result = MemoryGatewayV2(memory_service=service).semantic_retrieve("governed", top_k=2)

    assert service.calls == [("governed", 6)]
    assert result["backend"] == "controlled-test"
    assert result["ownership_boundary"] == "MemoryService"
    assert result["write_performed"] is False


def test_memory_snapshot_records_hashes_and_provenance(tmp_path):
    """A snapshot must carry verifiable provenance without changing live data."""
    from brain_v9.memory.memory_snapshot import create_memory_snapshot

    canonical_root = tmp_path / "canonical"
    semantic_root = canonical_root / "memory" / "semantic"
    semantic_root.mkdir(parents=True)
    source = semantic_root / "semantic_memory.jsonl"
    source.write_bytes(b'{"id":"snapshot-record"}\n')

    snapshot = create_memory_snapshot(
        "r6-1-contract",
        snapshot_root=tmp_path / "snapshots",
        canonical_root=canonical_root,
    )
    manifest = json.loads((snapshot / "memory_snapshot_manifest.json").read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 1
    assert manifest["reason"] == "r6-1-contract"
    assert manifest["files"]["memory/semantic/semantic_memory.jsonl"] == {
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "size_bytes": len(source.read_bytes()),
    }
    assert (snapshot / "semantic_memory.jsonl").read_bytes() == source.read_bytes()


def test_r6_1_evidence_binds_read_only_memory_ownership_and_hard_limits():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert evidence["roadmap_item_id"] == "R6.1"
    assert evidence["deployment_mode"] == "NO_DEPLOY"
    assert evidence["memory_contract"] == {
        "agent_v2_read_owner": "MemoryService",
        "agent_v2_direct_faiss_access": False,
        "agent_v2_promotion_enabled": False,
        "semantic_curated_separation": True,
        "snapshot_integrity_manifest": "sha256_relative_paths",
    }
    assert evidence["hard_limits"] == {
        "human_final_authority": True,
        "auto_merge": False,
        "canonical_local_sync": False,
        "live_trading": False,
        "real_money": False,
        "persistent_agent_loop": "DEFERRED",
    }


def test_memory_service_reports_malformed_semantic_records_as_integrity_failure(tmp_path):
    """Integrity is fail-closed even when retrieval can ignore a bad record."""
    from brain_v9.core.memory_service import MemoryService

    semantic_root = tmp_path / "memory" / "semantic"
    semantic_root.mkdir(parents=True)
    (semantic_root / "semantic_memory.jsonl").write_text(
        '{"id":"valid","text":"valid"}\nnot-json\n', encoding="utf-8"
    )

    integrity = MemoryService(semantic_root=semantic_root).integrity_check()

    assert integrity["ok"] is False
    assert integrity["valid_record_count"] == 1
    assert integrity["invalid_record_lines"] == [2]
    assert integrity["write_performed"] is False


def test_memory_service_never_reads_curated_artifacts_as_semantic_records(tmp_path):
    """Curated artifacts remain a distinct authority domain from semantic recall."""
    from brain_v9.core.memory_service import MemoryService

    semantic_root = tmp_path / "memory" / "semantic"
    curated_root = tmp_path / "memory" / "curated"
    semantic_root.mkdir(parents=True)
    curated_root.mkdir(parents=True)
    (semantic_root / "semantic_memory.jsonl").write_text(
        '{"id":"semantic","text":"semantic governed result"}\n', encoding="utf-8"
    )
    (curated_root / "curated_memory.jsonl").write_text(
        '{"id":"curated","text":"curated must not leak into semantic result"}\n', encoding="utf-8"
    )

    result = MemoryService(semantic_root=semantic_root).retrieve("result", top_k=5)

    assert [hit["id"] for hit in result["hits"]] == ["semantic"]


def test_r6_1_closeout_activates_only_bound_r6_2_promotion_successor():
    closeout = json.loads(CLOSEOUT_EVIDENCE.read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json").read_text(encoding="utf-8"))

    assert closeout["roadmap_item_id"] == "R6.1"
    assert closeout["parent_merge_commit"] == "7b22aad8a003e33a29be1afcb563e027309d2d5f"
    assert closeout["result"] == "CLOSED_RUNTIME_VERIFIED"
    assert manifest["roadmap_items"]["R6.1"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    assert closeout["next_item"] == {
        "roadmap_item_id": "R6.2",
        "front_id": "BRAIN-101-R6-2-GOVERNED-MEMORY-CANDIDATE-PROMOTION-ROLLBACK-01",
        "executor": "codex_control_plane",
        "deployment_mode": "NO_DEPLOY",
        "expected_base_sha_source": (
            "sequenceRoadmap resolves the exact live canonical integration-branch head "
            "at governed dispatch"
        ),
        "jit_binding_completed": True,
    }
    active_items = [
        item_id
        for item_id, item in manifest["roadmap_items"].items()
        if item["status"] == "AUTHORIZED_ACTIVE"
    ]
    assert manifest["roadmap_items"]["R6.2"]["status"] in {
        "AUTHORIZED_ACTIVE",
        "CLOSED_RUNTIME_VERIFIED",
    }
    assert active_items == ["R6.3"]
    automation = manifest["roadmap_items"]["R6.2"]["automation"]
    assert automation["front_id"] == closeout["next_item"]["front_id"]
    assert automation["jit_binding_completed"] is True
    assert automation["dispatchable"] is True
    assert manifest["roadmap_items"]["R6.2"]["hard_limits"] == closeout["hard_limits"]
    assert automation["closeout"]["front_id"] == (
        "BRAIN-101-R6-2-GOVERNED-MEMORY-CANDIDATE-PROMOTION-ROLLBACK-CLOSEOUT-01"
    )
