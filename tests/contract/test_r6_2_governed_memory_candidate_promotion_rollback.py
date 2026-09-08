"""R6.2 contract: governed memory promotion is approval-bound and isolated."""
from __future__ import annotations

import hashlib
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
