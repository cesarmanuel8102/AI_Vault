#!/usr/bin/env python3
"""
Smoke test for SemanticMemory Final Pre-Execution Gate.

This smoke test validates the read-only pre-execution gate
without running any real operations.
"""

import json
import sys
from pathlib import Path

# Ensure brain module is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.semantic_memory_final_pre_execution_gate import (
    SemanticMemoryFinalPreExecutionGate,
    SemanticMemoryFinalPreExecutionDecision,
    create_final_pre_execution_gate,
)


def get_valid_evidence():
    """Return valid evidence dictionary using JSON clone instead of copy method."""
    evidence = {
        "candidate_design_decision": "CANDIDATE_DESIGN_READY",
        "candidate_design_hash": "b21c22dd",
        "authorization_hash": "819be9f2",
        "go_no_go_hash": "433c5842",
        "commits_pending_post_push": 0,
        "staged_files": [],
        "memory_semantic_in_scope": False,
        "runtime_active": False,
        "faiss_write_enabled": False,
        "add_memory_enabled": False,
        "allows_auto_execute": False,
        "can_execute_real_write": False,
        "allow_real_write": False,
        "dry_run_only": True,
        "simulated_only": True,
        "requires_second_confirmation": True,
        "requires_runtime_down": True,
        "requires_clean_git_gate": True,
        "security_validation_ok": True
    }
    return json.loads(json.dumps(evidence))


def get_valid_final_intent():
    """Return valid final intent dictionary using JSON clone."""
    intent = {
        "requested_by": "Cesar",
        "intent_scope": "pre_execution_gate_only",
        "acknowledges_no_execution_now": True,
        "requires_future_second_confirmation": True,
        "requires_future_runtime_down": True,
        "requires_future_clean_git": True,
        "requires_future_real_backup": True,
        "requires_future_real_rollback": True,
        "allows_execution_now": False
    }
    return json.loads(json.dumps(intent))


def test_valid_evidence_and_intent():
    """Test valid evidence and intent returns PRE_EXECUTION_GATE_READY."""
    print("TEST: Valid evidence + valid intent => PRE_EXECUTION_GATE_READY")
    gate = create_final_pre_execution_gate()
    evidence = get_valid_evidence()
    final_intent = get_valid_final_intent()
    
    report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
    
    assert report.decision == SemanticMemoryFinalPreExecutionDecision.PRE_EXECUTION_GATE_READY, \
        f"Expected PRE_EXECUTION_GATE_READY, got {report.decision}"
    assert report.execution_allowed_now is False, "execution_allowed_now must be False"
    assert report.can_execute_real_write is False, "can_execute_real_write must be False"
    assert report.allow_real_write is False, "allow_real_write must be False"
    print("  PASSED")


def test_missing_final_intent():
    """Test missing final intent returns MANUAL_REVIEW_REQUIRED."""
    print("TEST: Valid evidence + missing intent => MANUAL_REVIEW_REQUIRED")
    gate = create_final_pre_execution_gate()
    evidence = get_valid_evidence()
    
    report = gate.evaluate_pre_execution_gate_read_only(evidence, None)
    
    assert report.decision == SemanticMemoryFinalPreExecutionDecision.MANUAL_REVIEW_REQUIRED, \
        f"Expected MANUAL_REVIEW_REQUIRED, got {report.decision}"
    print("  PASSED")


def test_invalid_candidate_design_decision():
    """Test invalid candidate_design_decision blocks execution."""
    print("TEST: Invalid candidate_design_decision => BLOCK_PRE_EXECUTION")
    gate = create_final_pre_execution_gate()
    evidence = get_valid_evidence()
    evidence["candidate_design_decision"] = "NOT_READY"
    final_intent = get_valid_final_intent()
    
    report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
    
    assert report.decision == SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION, \
        f"Expected BLOCK_PRE_EXECUTION, got {report.decision}"
    assert any(f.code == "INVALID_CANDIDATE_DESIGN_DECISION" for f in report.findings), \
        "Expected INVALID_CANDIDATE_DESIGN_DECISION finding"
    print("  PASSED")


def test_allows_execution_now_true():
    """Test allows_execution_now True blocks execution."""
    print("TEST: allows_execution_now=True => BLOCK_PRE_EXECUTION")
    gate = create_final_pre_execution_gate()
    evidence = get_valid_evidence()
    final_intent = get_valid_final_intent()
    final_intent["allows_execution_now"] = True
    
    report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
    
    assert report.decision == SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION, \
        f"Expected BLOCK_PRE_EXECUTION, got {report.decision}"
    assert any(f.code == "EXECUTION_NOW_BLOCKED" for f in report.findings), \
        "Expected EXECUTION_NOW_BLOCKED finding"
    print("  PASSED")


def test_runtime_active_true():
    """Test runtime_active True blocks execution."""
    print("TEST: runtime_active=True => BLOCK_PRE_EXECUTION")
    gate = create_final_pre_execution_gate()
    evidence = get_valid_evidence()
    evidence["runtime_active"] = True
    final_intent = get_valid_final_intent()
    
    report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
    
    assert report.decision == SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION, \
        f"Expected BLOCK_PRE_EXECUTION, got {report.decision}"
    assert any(f.code == "RUNTIME_ACTIVE" for f in report.findings), \
        "Expected RUNTIME_ACTIVE finding"
    print("  PASSED")


def test_invariants():
    """Test that safety invariants are always enforced."""
    print("TEST: Safety invariants always enforced")
    gate = create_final_pre_execution_gate()
    evidence = get_valid_evidence()
    final_intent = get_valid_final_intent()
    
    report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
    
    # Verify all safety invariants
    assert report.execution_allowed_now is False, "execution_allowed_now must always be False"
    assert report.can_execute_real_write is False, "can_execute_real_write must always be False"
    assert report.allow_real_write is False, "allow_real_write must always be False"
    assert report.dry_run_only is True, "dry_run_only must always be True"
    assert report.simulated_only is True, "simulated_only must always be True"
    assert report.requires_second_confirmation is True, "requires_second_confirmation must always be True"
    assert report.requires_runtime_down is True, "requires_runtime_down must always be True"
    assert report.requires_clean_git_gate is True, "requires_clean_git_gate must always be True"
    assert report.requires_real_backup_before_execution is True, \
        "requires_real_backup_before_execution must always be True"
    assert report.requires_real_rollback_before_execution is True, \
        "requires_real_rollback_before_execution must always be True"
    print("  PASSED")


def test_contract_summary():
    """Test that contract summary has correct values."""
    print("TEST: Contract summary has correct safety values")
    gate = create_final_pre_execution_gate()
    contract = gate.summarize_contract()
    
    assert contract["allow_real_write"] is False, "Contract allow_real_write must be False"
    assert contract["can_execute_real_write"] is False, "Contract can_execute_real_write must be False"
    assert contract["execution_allowed_now"] is False, "Contract execution_allowed_now must be False"
    assert contract["dry_run_only"] is True, "Contract dry_run_only must be True"
    assert contract["simulated_only"] is True, "Contract simulated_only must be True"
    assert contract["requires_second_confirmation"] is True, "Contract requires_second_confirmation must be True"
    print("  PASSED")


def test_block_gate():
    """Test manual block gate functionality."""
    print("TEST: Manual block gate => BLOCK_PRE_EXECUTION")
    gate = create_final_pre_execution_gate()
    
    report = gate.block_gate("Test block reason")
    
    assert report.decision == SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION, \
        f"Expected BLOCK_PRE_EXECUTION, got {report.decision}"
    assert report.blocker_count == 1, f"Expected 1 blocker, got {report.blocker_count}"
    assert "Test block reason" in report.final_blockers, "Block reason not in final_blockers"
    print("  PASSED")


def test_expected_hashes():
    """Test that gate has expected hash constants."""
    print("TEST: Gate has expected hash constants")
    gate = create_final_pre_execution_gate()
    
    assert gate.EXPECTED_CANDIDATE_DESIGN_HASH == "b21c22dd", \
        f"Expected b21c22dd, got {gate.EXPECTED_CANDIDATE_DESIGN_HASH}"
    assert gate.EXPECTED_AUTHORIZATION_HASH == "819be9f2", \
        f"Expected 819be9f2, got {gate.EXPECTED_AUTHORIZATION_HASH}"
    assert gate.EXPECTED_GO_NO_GO_HASH == "433c5842", \
        f"Expected 433c5842, got {gate.EXPECTED_GO_NO_GO_HASH}"
    print("  PASSED")


def main():
    """Run all smoke tests."""
    print("=" * 70)
    print("SMOKE TEST: SemanticMemory Final Pre-Execution Gate")
    print("=" * 70)
    print()
    
    tests = [
        test_expected_hashes,
        test_valid_evidence_and_intent,
        test_missing_final_intent,
        test_invalid_candidate_design_decision,
        test_allows_execution_now_true,
        test_runtime_active_true,
        test_invariants,
        test_contract_summary,
        test_block_gate,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1
    
    print()
    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)
    
    if failed == 0:
        print("SMOKE_SEMANTIC_MEMORY_FINAL_PRE_EXECUTION_GATE_OK")
        return 0
    else:
        print("SMOKE_FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())