from brain.promotion_gate_v1 import (
    CheckResult,
    EvidenceRef,
    FreshnessInfo,
    PromotionCandidate,
    ProvenanceBundle,
    RollbackPlan,
    assert_v1_never_writes,
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


def assert_blocked_with(candidate, reason):
    decision = validate_promotion_candidate(candidate)
    assert decision.blocked is True
    assert decision.allowed is False
    assert reason in decision.reason_codes


def test_valid_candidate_reaches_promotion_plan_created():
    candidate = valid_candidate(state="validated_candidate")
    decision = validate_transition("validated_candidate", "promotion_plan_created", candidate)
    assert decision.allowed is True
    assert decision.blocked is False
    assert decision.next_state == "promotion_plan_created"


def test_missing_candidate_id_blocked():
    assert_blocked_with(valid_candidate(candidate_id=""), "missing_candidate_id")


def test_missing_source_id_blocked():
    assert_blocked_with(valid_candidate(source_id=""), "missing_source_id")


def test_missing_content_hash_blocked():
    assert_blocked_with(valid_candidate(content_hash=""), "missing_content_hash")


def test_missing_provenance_blocked():
    assert_blocked_with(valid_candidate(provenance_bundle=None), "missing_provenance")


def test_forbidden_state_promoted_real_write_blocked():
    assert_blocked_with(valid_candidate(state="promoted_real_write"), "forbidden_state_v1")


def test_allow_real_write_true_blocked():
    candidate = valid_candidate(details={"allow_real_write": True})
    assert_blocked_with(candidate, "real_write_requested")


def test_dry_run_only_false_blocked():
    assert_blocked_with(valid_candidate(dry_run_only=False), "dry_run_only_required")


def test_approved_for_real_write_blocked():
    candidate = valid_candidate(operator_approval_status="approved_for_real_write")
    decision = validate_promotion_candidate(candidate)
    assert decision.blocked is True
    assert "operator_approval_real_write_forbidden" in decision.reason_codes
    assert "real_write_requested" in decision.reason_codes


def test_assert_v1_never_writes_allows_valid_dry_run_candidate():
    decision = assert_v1_never_writes(valid_candidate())
    assert decision.allowed is True
    assert decision.real_write_allowed is False


def test_transition_forbidden_target_blocks():
    decision = validate_transition("validated_candidate", "promoted_real_write", valid_candidate())
    assert decision.blocked is True
    assert "forbidden_state_v1" in decision.reason_codes
