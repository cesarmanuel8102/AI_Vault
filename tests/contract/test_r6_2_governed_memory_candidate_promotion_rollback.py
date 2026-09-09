"""R6.2 contract: governed memory promotion is approval-bound and isolated."""
from __future__ import annotations

import hashlib
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_agent"))


def _canonical_sha256(value: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def governed_candidate(*, text: str = "Stable governed memory lesson.", extra: dict[str, object] | None = None) -> dict[str, object]:
    candidate: dict[str, object] = {
        "schema_version": 1,
        "candidate_id": "r6-2-candidate-001",
        "room_id": "room_alpha",
        "source_id": "source-001",
        "evidence_id": "evidence-001",
        "retention_class": "governed",
        "text": text,
    }
    if extra:
        candidate.update(extra)
    candidate["candidate_sha256"] = _canonical_sha256(candidate)
    return candidate


def manual_decision(candidate: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "decision_id": "decision-r6-2-001",
        "approver_principal": "cesarmanuel8102",
        "approval_source": "human_owner",
        "action": "APPROVE_SINGLE_CANDIDATE",
        "candidate_id": candidate["candidate_id"],
        "candidate_sha256": candidate["candidate_sha256"],
        "room_id": candidate["room_id"],
        "expires_utc": "2099-01-01T00:00:00Z",
    }


def test_exact_candidate_and_manual_decision_bind_by_canonical_hash(tmp_path):
    from brain_v9.core.memory_service import MemoryService

    service = MemoryService(tmp_path / "configured-semantic")
    candidate = governed_candidate()
    result = service.validate_governed_candidate(candidate)

    assert result == {
        "ok": True,
        "candidate_id": candidate["candidate_id"],
        "candidate_sha256": candidate["candidate_sha256"],
        "errors": [],
    }
    prepared = service.prepare_governed_promotion(candidate, manual_decision(candidate), tmp_path / "staging")
    assert prepared["ok"] is True
    assert prepared["write_performed"] is False
    assert not (tmp_path / "configured-semantic").exists()


def test_unknown_fields_or_mismatched_candidate_hash_fail_closed(tmp_path):
    from brain_v9.core.memory_service import MemoryService

    service = MemoryService(tmp_path / "configured-semantic")
    unknown = governed_candidate(extra={"unexpected": "denied"})
    assert service.validate_governed_candidate(unknown)["ok"] is False

    candidate = governed_candidate()
    mismatched = manual_decision(governed_candidate(text="Different content."))
    result = service.prepare_governed_promotion(candidate, mismatched, tmp_path / "staging")
    assert result == {
        "ok": False,
        "reason": "manual_decision_candidate_mismatch",
        "write_performed": False,
    }


def _isolated_root(tmp_path: Path) -> Path:
    root = tmp_path / "isolated-store"
    root.mkdir()
    (root / ".r6_2_isolated_root").write_text("isolated\n", encoding="utf-8")
    (root / "semantic_memory.jsonl").write_bytes(b'{"id":"before"}\n')
    (root / "semantic_memory_faiss.index").write_bytes(b"index-before")
    (root / "semantic_memory_faiss_ids.json").write_bytes(b'["before"]\n')
    return root


def _artifact_hashes(root: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.glob("semantic_memory_*"))
    }


def test_isolated_rollback_restores_each_artifact_byte_for_byte(tmp_path):
    from brain_v9.memory.memory_rollback import rollback_isolated_snapshot
    from brain_v9.memory.memory_snapshot import create_isolated_memory_snapshot

    root = _isolated_root(tmp_path)
    before = _artifact_hashes(root)
    snapshot = create_isolated_memory_snapshot(root, "a" * 64)
    for path in root.glob("semantic_memory_*"):
        path.write_bytes(b"changed-" + path.name.encode("ascii"))

    result = rollback_isolated_snapshot(root, snapshot, "a" * 64)

    assert result == {"ok": True, "reason": "rollback_applied", "receipt_sha256": "a" * 64}
    assert _artifact_hashes(root) == before


def test_canonical_traversal_or_corrupt_manifest_fails_before_copy(tmp_path):
    from brain_v9.memory.memory_rollback import rollback_isolated_snapshot
    from brain_v9.memory.memory_snapshot import create_isolated_memory_snapshot

    assert create_isolated_memory_snapshot(Path("memory"), "a" * 64)["ok"] is False
    root = _isolated_root(tmp_path)
    before = _artifact_hashes(root)
    result = rollback_isolated_snapshot(root, {"../escape": {}}, "a" * 64)
    assert result["ok"] is False
    assert _artifact_hashes(root) == before

def _prepared_receipt(service, tmp_path: Path) -> dict[str, object]:
    candidate = governed_candidate()
    prepared = service.prepare_governed_promotion(candidate, manual_decision(candidate), tmp_path / "staging")
    assert prepared["ok"] is True
    return prepared["receipt"]


def test_exact_receipt_executes_once_in_isolated_root_and_can_roll_back(tmp_path, monkeypatch):
    from brain_v9.core.memory_service import MemoryService

    service = MemoryService(tmp_path / "configured-semantic")
    root = _isolated_root(tmp_path)
    receipt = _prepared_receipt(service, tmp_path)
    before = _artifact_hashes(root)

    def deterministic_fake_write(_receipt, target_root):
        for path in target_root.glob("semantic_memory_*"):
            path.write_bytes(b"after-" + path.name.encode("ascii"))
        return {"ok": True, "writer": "contract-fake"}

    monkeypatch.setattr(service, "_isolated_storage_write", deterministic_fake_write, raising=False)
    execution = service.execute_isolated_governed_promotion(receipt, root)

    assert execution["ok"] is True
    assert execution["promotion_receipt_sha256"] == receipt["receipt_sha256"]
    assert execution["write_performed"] is True
    assert _artifact_hashes(root) != before
    rollback = service.rollback_isolated_governed_promotion(execution, root)
    assert rollback["ok"] is True
    assert _artifact_hashes(root) == before


def test_execution_rejects_configured_semantic_root(tmp_path):
    from brain_v9.core.memory_service import MemoryService

    service = MemoryService(tmp_path / "configured-semantic")
    receipt = _prepared_receipt(service, tmp_path)

    assert service.execute_isolated_governed_promotion(receipt, service.semantic_root) == {
        "ok": False,
        "reason": "canonical_promotion_not_enabled",
        "write_performed": False,
    }


def test_legacy_promoter_requires_typed_receipt_and_has_no_direct_storage_primitives(tmp_path):
    from brain_v9.memory import promotion_candidate_promoter as promoter

    legacy = promoter.promote_candidate(
        "candidate-1", "all", "promotion", "legacy-token", "human", "legacy-confirmation"
    )
    candidate = governed_candidate()
    prepared = promoter.promote_candidate(
        "ignored-legacy-id",
        "all",
        "promotion",
        "legacy-token",
        "human",
        "legacy-confirmation",
        candidate=candidate,
        decision=manual_decision(candidate),
        semantic_root=tmp_path / "configured-semantic",
        staging_root=tmp_path / "staging",
    )

    assert legacy == {
        "ok": False,
        "reason": "governed_receipt_required",
        "promotion_performed": False,
        "write_performed": False,
    }
    assert prepared["ok"] is True
    assert prepared["write_performed"] is False
    assert not (tmp_path / "configured-semantic").exists()
    source = inspect.getsource(promoter)
    assert "promote_record(" not in source
    assert "rollback_from_snapshot(" not in source
    assert "append_promotion_audit(" not in source


def test_partial_isolated_write_rolls_back_when_artifact_topology_changes(tmp_path, monkeypatch):
    from brain_v9.core.memory_service import MemoryService

    service = MemoryService(tmp_path / "configured-semantic")
    root = _isolated_root(tmp_path)
    receipt = _prepared_receipt(service, tmp_path)
    before = _artifact_hashes(root)

    def corrupting_write(_receipt, target_root):
        artifacts = sorted(target_root.glob("semantic_memory_*"))
        artifacts[0].write_bytes(b"partially-written")
        artifacts[1].unlink()
        return {"ok": True}

    monkeypatch.setattr(service, "_isolated_storage_write", corrupting_write, raising=False)
    result = service.execute_isolated_governed_promotion(receipt, root)

    assert result["ok"] is False
    assert result["reason"] == "isolated_promotion_failed"
    assert result["rollback"]["ok"] is True
    assert _artifact_hashes(root) == before


def test_tampered_promotion_receipt_is_rejected_before_isolated_mutation(tmp_path):
    from brain_v9.core.memory_service import MemoryService

    service = MemoryService(tmp_path / "configured-semantic")
    root = _isolated_root(tmp_path)
    receipt = _prepared_receipt(service, tmp_path)
    receipt["candidate_id"] = "substituted-candidate"
    before = _artifact_hashes(root)

    assert service.execute_isolated_governed_promotion(receipt, root) == {
        "ok": False,
        "reason": "promotion_receipt_invalid",
        "write_performed": False,
    }
    assert _artifact_hashes(root) == before


def test_unconfigured_writer_fails_closed_and_restores_isolated_artifacts(tmp_path):
    from brain_v9.core.memory_service import MemoryService

    service = MemoryService(tmp_path / "configured-semantic")
    root = _isolated_root(tmp_path)
    receipt = _prepared_receipt(service, tmp_path)
    before = _artifact_hashes(root)

    result = service.execute_isolated_governed_promotion(receipt, root)

    assert result["ok"] is False
    assert result["reason"] == "isolated_promotion_failed"
    assert result["rollback"]["ok"] is True
    assert _artifact_hashes(root) == before


def test_r6_2_closeout_activates_only_bound_r6_3_hydration_successor():
    closeout_path = (
        ROOT
        / "docs/roadmap/evidence/"
        "BRAIN_101_R6_2_GOVERNED_MEMORY_CANDIDATE_PROMOTION_ROLLBACK_CLOSEOUT.json"
    )
    closeout = json.loads(closeout_path.read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "docs/roadmap/BRAIN_101_MANIFEST.json").read_text(encoding="utf-8"))

    assert closeout["roadmap_item_id"] == "R6.2"
    assert closeout["parent_merge_commit"] == "70d89d89ce036a03fd52784c252e802159eec373"
    assert closeout["result"] == "CLOSED_RUNTIME_VERIFIED"
    assert manifest["roadmap_items"]["R6.2"]["status"] == "CLOSED_RUNTIME_VERIFIED"
    assert closeout["next_item"] == {
        "roadmap_item_id": "R6.3",
        "front_id": "BRAIN-101-R6-3-MEMORY-RETRIEVAL-HYDRATION-REBUILD-VALIDATION-01",
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
    assert active_items == ["R6.3"]
    automation = manifest["roadmap_items"]["R6.3"]["automation"]
    assert automation["front_id"] == closeout["next_item"]["front_id"]
    assert automation["jit_binding_completed"] is True
    assert automation["dispatchable"] is True
    assert manifest["roadmap_items"]["R6.3"]["hard_limits"] == closeout["hard_limits"]
