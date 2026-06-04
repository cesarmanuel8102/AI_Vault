import pytest

from brain.promotion_gate_v1 import (
    CheckResult,
    EvidenceRef,
    FreshnessInfo,
    PromotionCandidate,
    ProvenanceBundle,
    RollbackPlan,
    validate_promotion_candidate,
    validate_transition,
)


def valid_candidate(**overrides):
    candidate = PromotionCandidate(
        candidate_id="cand_001",
        source_id="src_001",
        source_type="github",
        source_uri_or_path="https://github.com/example/repo",
        content_hash="a" * 64,
        extracted_text_hash="b" * 64,
        normalized_text_hash="c" * 64,
        curation_score=0.82,
        validation_score=0.86,
        confidence=0.81,
        freshness=FreshnessInfo(
            source_timestamp_utc="2026-06-01T00:00:00Z",
            evaluated_at_utc="2026-06-04T00:00:00Z",
            stale_after_days=90,
            is_stale=False,
        ),
        trust_score=0.84,
        duplicate_check=CheckResult(checked=True, method="hash", passed=True),
        contradiction_check=CheckResult(checked=True, method="semantic", passed=True),
        hallucination_risk_check=CheckResult(checked=True, method="evidence", passed=True, risk_level="low"),
        provenance_bundle=ProvenanceBundle(
            source_id="src_001",
            source_type="github",
            source_uri_or_path="https://github.com/example/repo",
            content_hash="a" * 64,
            extraction_method="github_tree",
            normalization_method="text_normalize_v1",
            operator_or_system="promotion_gate_test",
        ),
        evidence_refs=(
            EvidenceRef(
                ref_id="ev_001",
                source_id="src_001",
                path_or_uri="https://github.com/example/repo/README.md",
                quote_or_location="README.md#L1",
                hash="d" * 64,
            ),
        ),
        proposed_memory_payload={
            "text": "Validated curated knowledge.",
            "source": "curated:src_001",
            "kind": "curated_knowledge",
            "tags": ["curated", "validated", "dry_run"],
            "metadata": {"source_id": "src_001", "promotion_gate": "v1"},
        },
        rollback_plan=RollbackPlan(
            snapshot_required=True,
            affected_record_ids=(),
            inverse_operation="remove_inserted_record_and_restore_index",
            verification_steps=("record_count_matches", "hash_matches"),
            fixture_test_required=True,
        ),
        operator_approval_status="not_requested",
        dry_run_only=True,
        state="validated_candidate",
    )
    if not overrides:
        return candidate
    return PromotionCandidate(**{**candidate.__dict__, **overrides})


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("extracted_text_hash", "", "missing_extracted_text_hash"),
        ("normalized_text_hash", "", "missing_normalized_text_hash"),
        ("curation_score", 0.69, "curation_score_below_threshold"),
        ("validation_score", 0.74, "validation_score_below_threshold"),
        ("confidence", 0.69, "confidence_below_threshold"),
        ("trust_score", 0.69, "trust_score_below_threshold"),
    ],
)
def test_threshold_and_hash_no_go_conditions(field, value, reason):
    candidate = valid_candidate(**{field: value})
    decision = validate_promotion_candidate(candidate)
    assert decision.blocked is True
    assert reason in decision.reason_codes


def test_duplicate_check_not_checked_blocked():
    candidate = valid_candidate(duplicate_check=CheckResult(checked=False, method="hash"))
    decision = validate_promotion_candidate(candidate)
    assert "duplicate_check_not_checked" in decision.reason_codes


def test_contradiction_check_not_checked_blocked():
    candidate = valid_candidate(contradiction_check=CheckResult(checked=False, method="semantic"))
    decision = validate_promotion_candidate(candidate)
    assert "contradiction_check_not_checked" in decision.reason_codes


def test_hallucination_check_not_checked_blocked():
    candidate = valid_candidate(hallucination_risk_check=CheckResult(checked=False, method="evidence"))
    decision = validate_promotion_candidate(candidate)
    assert "hallucination_risk_check_not_checked" in decision.reason_codes


@pytest.mark.parametrize("risk", ["high", "critical"])
def test_hallucination_high_or_critical_blocked(risk):
    candidate = valid_candidate(
        hallucination_risk_check=CheckResult(checked=True, method="evidence", passed=True, risk_level=risk)
    )
    decision = validate_promotion_candidate(candidate)
    assert "hallucination_risk_high" in decision.reason_codes


def test_stale_source_blocked():
    freshness = valid_candidate().freshness
    stale = freshness.__class__(
        source_timestamp_utc=freshness.source_timestamp_utc,
        evaluated_at_utc=freshness.evaluated_at_utc,
        stale_after_days=freshness.stale_after_days,
        is_stale=True,
    )
    decision = validate_promotion_candidate(valid_candidate(freshness=stale))
    assert "stale_source" in decision.reason_codes


def test_missing_rollback_plan_blocked():
    decision = validate_promotion_candidate(valid_candidate(rollback_plan=None))
    assert "missing_rollback_plan" in decision.reason_codes


def test_incomplete_rollback_plan_blocked():
    plan = RollbackPlan(
        snapshot_required=True,
        inverse_operation="",
        verification_steps=(),
        fixture_test_required=True,
    )
    decision = validate_promotion_candidate(valid_candidate(rollback_plan=plan))
    assert "incomplete_rollback_plan" in decision.reason_codes


def test_path_outside_allowed_roots_blocked():
    decision = validate_promotion_candidate(valid_candidate(source_uri_or_path="C:/AI_VAULT/memory/semantic/x.jsonl"))
    assert "path_outside_allowed_roots" in decision.reason_codes


def test_nested_real_write_flag_in_payload_blocked():
    payload = {
        "text": "x",
        "source": "curated:src_001",
        "kind": "curated_knowledge",
        "tags": ["curated"],
        "metadata": {"allow_real_write": True},
    }
    decision = validate_promotion_candidate(valid_candidate(proposed_memory_payload=payload))
    assert "real_write_requested" in decision.reason_codes


def test_payload_without_source_label_blocked():
    payload = {"text": "x", "metadata": {"source_id": "src_001"}, "tags": ["curated"]}
    decision = validate_promotion_candidate(valid_candidate(proposed_memory_payload=payload))
    assert "payload_lacks_source_label" in decision.reason_codes


def test_transition_to_approval_requires_audit_and_observability_events():
    decision = validate_transition("promotion_plan_created", "approval_required", valid_candidate())
    assert decision.blocked is True
    assert "missing_audit_event" in decision.reason_codes
    assert "missing_observability_event" in decision.reason_codes


def test_transition_to_approved_for_dry_run_requires_operator_approval():
    candidate = valid_candidate(audit_event_created=True, observability_event_created=True)
    decision = validate_transition("approval_required", "approved_for_dry_run", candidate)
    assert decision.blocked is True
    assert "operator_approval_missing" in decision.reason_codes


def test_transition_to_dry_run_verified_requires_dry_run_proofs():
    candidate = valid_candidate(
        audit_event_created=True,
        observability_event_created=True,
        operator_approval_status="approved_for_dry_run",
    )
    decision = validate_transition("approved_for_dry_run", "dry_run_verified", candidate)
    assert decision.blocked is True
    assert "semantic_memory_unchanged_not_verified" in decision.reason_codes
    assert "failed_dry_run" in decision.reason_codes


def test_transition_to_readonly_lookup_requires_label():
    candidate = valid_candidate(
        audit_event_created=True,
        observability_event_created=True,
        semantic_memory_unchanged=True,
        dry_run_adapter_success=True,
    )
    decision = validate_transition("dry_run_verified", "ready_for_readonly_runtime_lookup", candidate)
    assert decision.blocked is True
    assert "missing_readonly_lookup_label" in decision.reason_codes


def test_valid_transition_to_readonly_lookup_allowed_with_label():
    candidate = valid_candidate(
        audit_event_created=True,
        observability_event_created=True,
        semantic_memory_unchanged=True,
        dry_run_adapter_success=True,
        readonly_lookup_label="verified_curated_readonly",
    )
    decision = validate_transition("dry_run_verified", "ready_for_readonly_runtime_lookup", candidate)
    assert decision.allowed is True
    assert decision.next_state == "ready_for_readonly_runtime_lookup"
