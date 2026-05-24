"""
Smoke test for semantic_memory_final_readiness_review.py
P2-E Commit 4D-FinalReadinessReview

This smoke test validates the basic functionality of the final readiness review
module without requiring full test infrastructure.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.semantic_memory_final_readiness_review import (
    SemanticMemoryFinalReadinessDecision,
    SemanticMemoryFinalReadinessSeverity,
    SemanticMemoryFinalReadinessFinding,
    SemanticMemoryFinalReadinessReport,
    SemanticMemoryFinalReadinessReview,
)
from brain.semantic_memory_real_write_canary_plan import (
    SemanticMemoryCanaryDecision,
    SemanticMemoryRealWriteCanaryPlanReport,
)
from brain.semantic_memory_decision_gate_evidence_adapter import (
    SemanticMemoryEvidenceAdapterStatus,
    SemanticMemoryDecisionGateEvidenceAdapterReport,
)


def create_valid_canary_report():
    """Create a valid canary report with CANDIDATE_READY decision."""
    return SemanticMemoryRealWriteCanaryPlanReport(
        canary_id="canary_smoke_test",
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        decision=SemanticMemoryCanaryDecision.CANDIDATE_READY,
        status="CANDIDATE",
        findings=[],
        blocker_count=0,
        warning_count=0,
        info_count=0,
        critical_count=0,
        allow_real_write=False,
        dry_run_only=True,
        can_execute_real_write=False,
        requires_manual_review=False,
    )


def create_valid_adapter_report():
    """Create a valid adapter report with ACCEPTED_FOR_GATE status."""
    return SemanticMemoryDecisionGateEvidenceAdapterReport(
        adapter_id="adapter_smoke_test",
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        status=SemanticMemoryEvidenceAdapterStatus.ACCEPTED_FOR_GATE,
        evidence_status="ACCEPTED",
        decision="ALLOW_MANUAL_REAL_WRITE_CANDIDATE",
        findings=[],
        blocker_count=0,
        warning_count=0,
        info_count=0,
        git_state_verified=True,
        risk_summary_verified=True,
        security_validation_verified=True,
        tests_verified=True,
        smokes_verified=True,
        accepted_for_decision_gate=True,
        allow_real_write=False,
        dry_run_only=True,
        can_execute_real_write=False,
        requires_manual_review=False,
    )


def create_invalid_canary_report():
    """Create an invalid canary report (not CANDIDATE_READY)."""
    return SemanticMemoryRealWriteCanaryPlanReport(
        canary_id="canary_invalid",
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        decision=SemanticMemoryCanaryDecision.BLOCK,
        status="BLOCKED",
        findings=[],
        blocker_count=1,
        warning_count=0,
        info_count=0,
        critical_count=0,
        allow_real_write=False,
        dry_run_only=True,
        can_execute_real_write=False,
        requires_manual_review=True,
    )


def test_valid_without_approval():
    """Test valid reports without approval - should require manual review."""
    print("\n[TEST] Valid reports without approval...")
    review = SemanticMemoryFinalReadinessReview()
    canary_report = create_valid_canary_report()
    adapter_report = create_valid_adapter_report()
    
    result = review.evaluate_final_readiness(
        canary_report=canary_report,
        adapter_report=adapter_report,
    )
    
    assert result.decision == SemanticMemoryFinalReadinessDecision.MANUAL_REVIEW_REQUIRED
    assert result.all_previous_stages_passed is True
    assert result.human_approval_obtained is False
    assert result.requires_human_approval is True
    assert result.allow_real_write is False
    assert result.dry_run_only is True
    assert result.can_execute_real_write is False
    print("  PASSED: Valid without approval produces MANUAL_REVIEW_REQUIRED")
    return True


def test_valid_with_approval():
    """Test valid reports with approval - should be candidate."""
    print("\n[TEST] Valid reports with approval...")
    review = SemanticMemoryFinalReadinessReview()
    canary_report = create_valid_canary_report()
    adapter_report = create_valid_adapter_report()
    human_approval = {
        "approved": True,
        "approver": "TestApprover",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    result = review.evaluate_final_readiness(
        canary_report=canary_report,
        adapter_report=adapter_report,
        human_approval=human_approval,
    )
    
    assert result.decision == SemanticMemoryFinalReadinessDecision.ALLOW_MANUAL_REAL_WRITE_CANDIDATE
    assert result.all_previous_stages_passed is True
    assert result.human_approval_obtained is True
    assert result.human_approver == "TestApprover"
    assert result.allow_real_write is False
    assert result.dry_run_only is True
    assert result.can_execute_real_write is False
    print("  PASSED: Valid with approval produces ALLOW_MANUAL_REAL_WRITE_CANDIDATE")
    return True


def test_invalid_canary():
    """Test invalid canary report - should block."""
    print("\n[TEST] Invalid canary report...")
    review = SemanticMemoryFinalReadinessReview()
    canary_report = create_invalid_canary_report()
    adapter_report = create_valid_adapter_report()
    
    result = review.evaluate_final_readiness(
        canary_report=canary_report,
        adapter_report=adapter_report,
    )
    
    assert result.decision == SemanticMemoryFinalReadinessDecision.BLOCK_REAL_WRITE
    assert result.all_previous_stages_passed is False
    assert result.allow_real_write is False
    print("  PASSED: Invalid canary produces BLOCK_REAL_WRITE")
    return True


def test_safety_invariants():
    """Test that safety invariants are enforced."""
    print("\n[TEST] Safety invariants...")
    review = SemanticMemoryFinalReadinessReview()
    
    # Test all scenarios - safety invariants should always hold
    result1 = review.evaluate_final_readiness()
    assert result1.allow_real_write is False
    assert result1.dry_run_only is True
    assert result1.can_execute_real_write is False
    assert result1.requires_human_approval is True
    
    result2 = review.create_blocked_report()
    assert result2.allow_real_write is False
    assert result2.dry_run_only is True
    assert result2.can_execute_real_write is False
    
    canary_report = create_valid_canary_report()
    adapter_report = create_valid_adapter_report()
    result3 = review.evaluate_final_readiness(
        canary_report=canary_report,
        adapter_report=adapter_report,
        human_approval={"approved": True, "approver": "Test", "timestamp": datetime.now(timezone.utc).isoformat()},
    )
    assert result3.allow_real_write is False
    assert result3.dry_run_only is True
    assert result3.can_execute_real_write is False
    
    print("  PASSED: Safety invariants enforced in all scenarios")
    return True


def test_no_add_memory_execution():
    """Verify no actual add_memory calls are made."""
    print("\n[TEST] No add_memory execution...")
    review = SemanticMemoryFinalReadinessReview()
    
    # Check that the module has ADD_MEMORY_BLOCKED in its codes
    assert "ADD_MEMORY_BLOCKED" in review.REVIEW_CODES
    
    # Verify findings include add_memory blocked
    findings = []
    review._enforce_safety_invariants(findings)
    add_mem_findings = [f for f in findings if f.code == "ADD_MEMORY_BLOCKED"]
    assert len(add_mem_findings) >= 1
    
    print("  PASSED: add_memory is blocked by design")
    return True


def test_human_approval_validation():
    """Test human approval validation logic."""
    print("\n[TEST] Human approval validation...")
    review = SemanticMemoryFinalReadinessReview()
    
    # Valid approval
    valid = {"approved": True, "approver": "Tester", "timestamp": datetime.now(timezone.utc).isoformat()}
    assert review._validate_human_approval(valid) is True
    
    # Invalid - not approved
    invalid1 = {"approved": False, "approver": "Tester", "timestamp": datetime.now(timezone.utc).isoformat()}
    assert review._validate_human_approval(invalid1) is False
    
    # Invalid - no approver
    invalid2 = {"approved": True, "timestamp": datetime.now(timezone.utc).isoformat()}
    assert review._validate_human_approval(invalid2) is False
    
    # Invalid - empty approver
    invalid3 = {"approved": True, "approver": "", "timestamp": datetime.now(timezone.utc).isoformat()}
    assert review._validate_human_approval(invalid3) is False
    
    # Invalid - no timestamp
    invalid4 = {"approved": True, "approver": "Tester"}
    assert review._validate_human_approval(invalid4) is False
    
    # Invalid - invalid timestamp
    invalid5 = {"approved": True, "approver": "Tester", "timestamp": "not-a-timestamp"}
    assert review._validate_human_approval(invalid5) is False
    
    print("  PASSED: Human approval validation works correctly")
    return True


def main():
    """Run all smoke tests."""
    print("=" * 70)
    print("SMOKE TEST: Semantic Memory Final Readiness Review")
    print("=" * 70)
    
    tests = [
        test_valid_without_approval,
        test_valid_with_approval,
        test_invalid_canary,
        test_safety_invariants,
        test_no_add_memory_execution,
        test_human_approval_validation,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1
    
    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)
    
    if failed == 0:
        print("SMOKE_SEMANTIC_MEMORY_FINAL_READINESS_REVIEW_OK")
        return 0
    else:
        print("SMOKE_TEST_FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
