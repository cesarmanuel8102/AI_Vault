from pathlib import Path

from brain.curation_validation_adapter import CurationValidationResult, CurationValidationStatus
from brain.information_curator import ContentTopic, CuratedRecord, QualityLevel
from brain.promotion_gate_v1_coordinator import (
    DryRunPromotionInput,
    make_semantic_memory_snapshot,
    run_promotion_gate_dry_run,
    verify_no_semantic_memory_mutation,
)


def test_promotion_gate_v1_coordinator_dry_run_smoke_no_semantic_mutation():
    semantic_paths = [Path("memory/semantic")]
    before = make_semantic_memory_snapshot(semantic_paths)
    record = CuratedRecord(
        record_id="smoke_rec_1",
        content="Smoke test curated knowledge for dry-run coordinator verification.",
        topic=ContentTopic.TECHNOLOGY,
        quality=QualityLevel.HIGH,
        quality_score=0.92,
        source="manual_smoke",
        content_hash="b" * 64,
    )
    validation = CurationValidationResult(
        record_id=record.record_id,
        content_hash=record.content_hash,
        source=record.source,
        topic="technical",
        status=CurationValidationStatus.VALIDATED,
        validator_status="VALIDATED",
        passed=True,
        score=0.91,
        reason="smoke",
        validation_id="smoke_validation_1",
    )

    result = run_promotion_gate_dry_run(
        DryRunPromotionInput(
            record=record,
            source_context={
                "source_id": "manual_smoke",
                "source_type": "manual_text",
                "source_uri_or_path": "manual:smoke",
                "curation_score": 0.92,
                "validation_score": 0.91,
                "confidence": 0.9,
                "trust_score": 0.9,
            },
            validation_result=validation,
            semantic_memory_paths=semantic_paths,
        )
    )
    after = make_semantic_memory_snapshot(semantic_paths)

    assert result.status == "dry_run_verified"
    assert result.allow_real_write is False
    assert result.real_write_denied is True
    assert result.semantic_memory_unchanged is True
    assert result.artifacts.semantic_adapter_run_id
    assert verify_no_semantic_memory_mutation(before, after) is True
