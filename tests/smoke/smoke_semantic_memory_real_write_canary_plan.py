"""
P2-E Commit 4D-RealWriteCanaryPlan Smoke Test

Smoke test for SemanticMemoryRealWriteCanaryPlan.
Must print: SMOKE_SEMANTIC_MEMORY_REAL_WRITE_CANARY_PLAN_OK
"""

import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from brain.semantic_memory_real_write_canary_plan import (
    SemanticMemoryCanaryDecision,
    SemanticMemoryCanarySeverity,
    SemanticMemoryCanaryFinding,
    SemanticMemoryRealWriteCanaryPlanReport,
    SemanticMemoryRealWriteCanaryPlan,
)
from brain.semantic_memory_decision_gate_evidence_adapter import (
    SemanticMemoryEvidenceAdapterStatus,
)


def test_canary_decision_enum():
    """Test 1: Canary decision enum values."""
    assert SemanticMemoryCanaryDecision.BLOCK == "BLOCK"
    assert SemanticMemoryCanaryDecision.NOOP_ONLY == "NOOP_ONLY"
    assert SemanticMemoryCanaryDecision.CANDIDATE_READY == "CANDIDATE_READY"
    assert SemanticMemoryCanaryDecision.MANUAL_REVIEW == "MANUAL_REVIEW"


def test_canary_severity_enum():
    """Test 2: Canary severity enum values."""
    assert SemanticMemoryCanarySeverity.INFO == "INFO"
    assert SemanticMemoryCanarySeverity.WARNING == "WARNING"
    assert SemanticMemoryCanarySeverity.BLOCKER == "BLOCKER"
    assert SemanticMemoryCanarySeverity.CRITICAL == "CRITICAL"


def test_finding_creation():
    """Test 3: Finding creation."""
    finding = SemanticMemoryCanaryFinding(
        code="TEST_CODE",
        severity=SemanticMemoryCanarySeverity.INFO,
        message="Test message",
    )
    assert finding.code == "TEST_CODE"
    assert finding.severity == SemanticMemoryCanarySeverity.INFO


def test_report_creation():
    """Test 4: Report creation with invariants."""
    report = SemanticMemoryRealWriteCanaryPlanReport(
        canary_id="test",
        created_at_utc=datetime.now().isoformat(),
        decision=SemanticMemoryCanaryDecision.NOOP_ONLY,
        status="TEST",
        findings=[],
        blocker_count=0,
        warning_count=0,
        info_count=0,
        critical_count=0,
    )
    assert report.allow_real_write == False
    assert report.dry_run_only == True
    assert report.can_execute_real_write == False


def test_canary_plan_initialization():
    """Test 5: Canary plan initialization."""
    plan = SemanticMemoryRealWriteCanaryPlan(repo_root=".")
    assert plan._canary_id.startswith("canary_")


def test_canary_codes_exist():
    """Test 6: Canary codes exist."""
    plan = SemanticMemoryRealWriteCanaryPlan()
    assert "ADAPTER_VALIDATION_PASSED" in plan.CANARY_CODES
    assert "REAL_WRITE_BLOCKED" in plan.CANARY_CODES


def test_valid_noop():
    """Test 7: Valid noop report generation."""
    plan = SemanticMemoryRealWriteCanaryPlan()
    report = plan.create_noop_canary_report()
    assert report.decision == SemanticMemoryCanaryDecision.NOOP_ONLY
    assert report.allow_real_write == False
    assert report.dry_run_only == True


def test_invalid_write_blocked():
    """Test 8: Invalid write is blocked."""
    plan = SemanticMemoryRealWriteCanaryPlan()
    report = plan.evaluate_canary_plan()
    # Any real write attempt should be blocked
    assert report.allow_real_write == False
    assert report.can_execute_real_write == False


def test_invalid_add_memory_blocked():
    """Test 9: add_memory is conceptually blocked."""
    plan = SemanticMemoryRealWriteCanaryPlan()
    # The module does not allow add_memory calls
    # This is verified by code inspection
    findings = [f.code for f in plan.create_noop_canary_report().findings]
    # Check that safety invariants include add_memory blocking
    assert "ADD_MEMORY_BLOCKED" in findings


def test_invalid_git_blocked():
    """Test 10: git operations are conceptually blocked."""
    plan = SemanticMemoryRealWriteCanaryPlan()
    # The module does not execute git commands
    findings = [f.code for f in plan.create_noop_canary_report().findings]
    assert "GIT_OPERATION_BLOCKED" in findings


def test_block_canary():
    """Test 11: Block canary creates blocked report."""
    plan = SemanticMemoryRealWriteCanaryPlan()
    report = plan.block_canary(reason="Test block")
    assert report.decision == SemanticMemoryCanaryDecision.BLOCK
    assert report.status == "BLOCKED"


def test_safety_invariants_passed():
    """Test 12: Safety invariants always passed."""
    plan = SemanticMemoryRealWriteCanaryPlan()
    report = plan.evaluate_canary_plan()
    assert report.safety_invariants_passed == True


def test_evaluate_with_bundle():
    """Test 13: Evaluate with evidence bundle."""
    plan = SemanticMemoryRealWriteCanaryPlan()
    
    bundle = {
        "bundle_id": "smoke_test_bundle",
        "producer": "smoke_test",
        "created_at_utc": datetime.now().isoformat(),
        "git_state": {
            "head_commit": "abc123",
            "branch": "main",
            "commits_ahead": 0,
            "dirty_files_count": 0,
            "staged_files_count": 0,
        },
        "risk_summary": {
            "total_extra_files": 0,
            "critical_extra_files": [],
            "dependency_hits": [],
            "high_risk_hits": 0,
        },
        "security_validation": {
            "passed": True,
            "has_subprocess": False,
            "has_faiss": False,
            "has_bridge": False,
            "has_add_memory": False,
        },
        "test_results": {
            "all_tests_passed": True,
            "test_count": 5,
        },
        "smoke_results": {
            "all_smokes_passed": True,
            "smoke_count": 2,
        },
    }
    
    report = plan.evaluate_canary_plan(evidence_bundle=bundle)
    assert report.allow_real_write == False
    assert report.dry_run_only == True


def test_summarize_canary_plan():
    """Test 14: Summarize canary plan."""
    plan = SemanticMemoryRealWriteCanaryPlan()
    summary = plan.summarize_canary_plan()
    assert summary["canary_version"] == "P2-E-Commit-4D-RealWriteCanaryPlan"
    assert summary["allow_real_write"] == False


def run_all_smoke_tests():
    """Run all smoke tests."""
    tests = [
        test_canary_decision_enum,
        test_canary_severity_enum,
        test_finding_creation,
        test_report_creation,
        test_canary_plan_initialization,
        test_canary_codes_exist,
        test_valid_noop,
        test_invalid_write_blocked,
        test_invalid_add_memory_blocked,
        test_invalid_git_blocked,
        test_block_canary,
        test_safety_invariants_passed,
        test_evaluate_with_bundle,
        test_summarize_canary_plan,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"FAIL: {test.__name__}: {e}")
            failed += 1
    
    return passed, failed


if __name__ == "__main__":
    passed, failed = run_all_smoke_tests()
    
    if failed == 0:
        print("SMOKE_SEMANTIC_MEMORY_REAL_WRITE_CANARY_PLAN_OK")
        sys.exit(0)
    else:
        print(f"SMOKE_FAILED: {failed} tests failed")
        sys.exit(1)
