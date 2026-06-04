from dataclasses import replace
from pathlib import Path

from brain.curation_validation_adapter import CurationValidationResult, CurationValidationStatus
from brain.information_curator import ContentTopic, CuratedRecord, QualityLevel
from brain.promotion_gate_v1_coordinator import (
    DryRunPromotionInput,
    SemanticMemorySnapshot,
    build_candidate_from_curated_record,
    require_real_write_gate_denied,
    run_promotion_gate_dry_run,
    verify_no_semantic_memory_mutation,
)


def _record() -> CuratedRecord:
    return CuratedRecord(
        record_id="rec_test_1",
        content="Promotion Gate v1 dry-run validated knowledge with provenance.",
        topic=ContentTopic.TECHNOLOGY,
        quality=QualityLevel.HIGH,
        quality_score=0.91,
        source="manual_test",
        content_hash="a" * 64,
    )


def _source_context(**overrides):
    base = {
        "source_id": "manual_test",
        "source_type": "manual_text",
        "source_uri_or_path": "manual:test",
        "curation_score": 0.91,
        "validation_score": 0.9,
        "confidence": 0.88,
        "trust_score": 0.9,
    }
    base.update(overrides)
    return base


def _validation() -> CurationValidationResult:
    return CurationValidationResult(
        record_id="rec_test_1",
        content_hash="a" * 64,
        source="manual_test",
        topic="technical",
        status=CurationValidationStatus.VALIDATED,
        validator_status="VALIDATED",
        passed=True,
        score=0.9,
        reason="unit test",
        validation_id="validation_test_1",
    )


def test_build_candidate_from_curated_record_creates_promotion_candidate():
    candidate = build_candidate_from_curated_record(_record(), _source_context())

    assert candidate.candidate_id == "rec_test_1"
    assert candidate.source_type == "manual_text"
    assert candidate.dry_run_only is True
    assert candidate.provenance_bundle is not None


def test_blocked_candidate_returns_reason_codes():
    result = run_promotion_gate_dry_run(
        DryRunPromotionInput(
            record=_record(),
            source_context=_source_context(validation_score=0.1),
            validation_result=_validation(),
            semantic_memory_paths=[Path("tests/fixtures/nonexistent_semantic_memory")],
        )
    )

    assert result.status == "blocked"
    assert "validation_score_below_threshold" in result.reason_codes


def test_missing_provenance_blocks_before_dry_run():
    result = run_promotion_gate_dry_run(
        DryRunPromotionInput(
            record=_record(),
            source_context=_source_context(provenance_bundle=None),
            validation_result=_validation(),
            semantic_memory_paths=[Path("tests/fixtures/nonexistent_semantic_memory")],
        )
    )

    assert result.status == "blocked"
    assert "missing_provenance" in result.reason_codes
    assert result.artifacts.semantic_adapter_run_id is None


def test_dry_run_only_false_blocks():
    result = run_promotion_gate_dry_run(
        DryRunPromotionInput(
            record=_record(),
            source_context=_source_context(),
            validation_result=_validation(),
            dry_run_only=False,
            semantic_memory_paths=[Path("tests/fixtures/nonexistent_semantic_memory")],
        )
    )

    assert result.status == "blocked"
    assert result.reason_codes == ("dry_run_only_required",)


def test_real_write_requested_blocks():
    result = run_promotion_gate_dry_run(
        DryRunPromotionInput(
            record=_record(),
            source_context=_source_context(
                proposed_memory_payload={"allow_real_write": True, "source": "curated:test"}
            ),
            validation_result=_validation(),
            semantic_memory_paths=[Path("tests/fixtures/nonexistent_semantic_memory")],
        )
    )

    assert result.status == "blocked"
    assert "real_write_requested" in result.reason_codes


def test_require_real_write_gate_denied_returns_denied():
    decision = require_real_write_gate_denied()

    assert decision.allowed is True
    assert decision.blocked is False
    assert decision.details["allow_real_write"] is False
    assert decision.details["can_execute_real_write"] is False


def test_verify_no_semantic_memory_mutation_true_for_identical_snapshots():
    snapshot = SemanticMemorySnapshot(
        snapshot_id="s1",
        paths=("memory/semantic",),
        files={"memory/semantic/semantic_memory.jsonl": {"sha256": "abc", "line_count": 1}},
    )

    assert verify_no_semantic_memory_mutation(snapshot, snapshot) is True


def test_verify_no_semantic_memory_mutation_false_for_changed_hash_count():
    before = SemanticMemorySnapshot(
        snapshot_id="s1",
        paths=("memory/semantic",),
        files={"memory/semantic/semantic_memory.jsonl": {"sha256": "abc", "line_count": 1}},
    )
    after = replace(
        before,
        snapshot_id="s2",
        files={"memory/semantic/semantic_memory.jsonl": {"sha256": "def", "line_count": 2}},
    )

    assert verify_no_semantic_memory_mutation(before, after) is False


def test_coordinator_never_imports_real_adapter():
    source = Path("brain/promotion_gate_v1_coordinator.py").read_text(encoding="utf-8")

    assert "semantic_memory_adapter_real" not in source


def test_coordinator_never_imports_semantic_memory_bridge():
    source = Path("brain/promotion_gate_v1_coordinator.py").read_text(encoding="utf-8")

    assert "semantic_memory_bridge" not in source


def test_valid_dry_run_candidate_reaches_dry_run_verified_with_dry_run_components():
    result = run_promotion_gate_dry_run(
        DryRunPromotionInput(
            record=_record(),
            source_context=_source_context(),
            validation_result=_validation(),
            semantic_memory_paths=[Path("tests/fixtures/nonexistent_semantic_memory")],
        )
    )

    assert result.status == "dry_run_verified"
    assert result.semantic_memory_unchanged is True
    assert result.real_write_denied is True
    assert result.artifacts.audit_event_refs
    assert result.artifacts.observability_event_refs
    assert result.artifacts.semantic_adapter_run_id


class _NoAuditTuple(tuple):
    pass


def test_missing_audit_ref_blocks_dry_run_verified(monkeypatch):
    import brain.promotion_gate_v1_coordinator as coordinator

    monkeypatch.setattr(coordinator, "_collect_audit_refs", lambda *args, **kwargs: ())

    result = coordinator.run_promotion_gate_dry_run(
        DryRunPromotionInput(
            record=_record(),
            source_context=_source_context(),
            validation_result=_validation(),
            semantic_memory_paths=[Path("tests/fixtures/nonexistent_semantic_memory")],
        )
    )

    assert result.status == "blocked"
    assert "missing_audit_event" in result.reason_codes


def test_missing_observability_ref_blocks_dry_run_verified():
    class NoEventObservability:
        def record_event(self, **kwargs):
            class Event:
                event_id = ""

            return Event()

    result = run_promotion_gate_dry_run(
        DryRunPromotionInput(
            record=_record(),
            source_context=_source_context(),
            validation_result=_validation(),
            observability=NoEventObservability(),
            semantic_memory_paths=[Path("tests/fixtures/nonexistent_semantic_memory")],
        )
    )

    assert result.status == "blocked"
    assert "missing_observability_event" in result.reason_codes


def test_approved_for_real_write_is_rejected():
    result = run_promotion_gate_dry_run(
        DryRunPromotionInput(
            record=_record(),
            source_context=_source_context(operator_approval_status="approved_for_real_write"),
            validation_result=_validation(),
            semantic_memory_paths=[Path("tests/fixtures/nonexistent_semantic_memory")],
        )
    )

    assert result.status == "blocked"
    assert "operator_approval_real_write_forbidden" in result.reason_codes
