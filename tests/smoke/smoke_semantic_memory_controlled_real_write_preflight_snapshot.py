#!/usr/bin/env python3
"""
Smoke test for SemanticMemory Controlled Real Write Preflight Snapshot.

This smoke test validates the read-only preflight snapshot
without running any real operations.
"""

import json
import sys
from pathlib import Path

# Ensure brain module is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.semantic_memory_controlled_real_write_preflight_snapshot import (
    SemanticMemoryControlledRealWritePreflightSnapshot,
    SemanticMemoryPreflightSnapshotDecision,
    create_preflight_snapshot,
)


def get_valid_evidence():
    """Return valid evidence dictionary using JSON clone."""
    evidence = {
        "execution_package_decision": "EXECUTION_PACKAGE_READY",
        "execution_package_hash": "5c41ba4b",
        "final_pre_execution_gate_hash": "dcf2b72e",
        "candidate_design_hash": "b21c22dd",
        "authorization_hash": "819be9f2",
        "go_no_go_hash": "433c5842",
        "branch": "codex/own-capital-sustainable-return",
        "head_hash": "5c41ba4b",
        "origin_head_hash": "5c41ba4b",
        "commits_pending": 0,
        "staged_files": [],
        "dirty_files": [],
        "runtime_active": False,
        "memory_semantic_dirty_known_out_of_scope": True,
        "memory_semantic_write_allowed_now": False,
        "backup_created": False,
        "rollback_created": False,
        "allows_auto_execute": False,
        "execution_allowed_now": False,
        "can_execute_real_write": False,
        "allow_real_write": False,
        "dry_run_only": True,
        "simulated_only": True,
        "security_validation_ok": True,
        "strict_security_audit_ok": True
    }
    return json.loads(json.dumps(evidence))


def get_valid_operator_intent():
    """Return valid operator intent dictionary using JSON clone."""
    intent = {
        "requested_by": "Cesar",
        "intent_scope": "preflight_snapshot_only",
        "acknowledges_no_execution_now": True,
        "allows_execution_now": False,
        "allows_memory_semantic_write_now": False,
        "requires_future_second_confirmation": True,
        "requires_future_runtime_down": True,
        "requires_future_clean_git": True,
        "requires_future_real_backup": True,
        "requires_future_real_rollback": True
    }
    return json.loads(json.dumps(intent))


def test_valid_evidence_and_intent():
    """Test valid evidence and intent returns PREFLIGHT_SNAPSHOT_READY."""
    print("TEST: Valid evidence + valid intent => PREFLIGHT_SNAPSHOT_READY")
    snap = create_preflight_snapshot()
    evidence = get_valid_evidence()
    operator_intent = get_valid_operator_intent()
    
    report = snap.build_snapshot_read_only(evidence, operator_intent)
    
    assert report.decision == SemanticMemoryPreflightSnapshotDecision.PREFLIGHT_SNAPSHOT_READY, \
        f"Expected PREFLIGHT_SNAPSHOT_READY, got {report.decision}"
    assert report.execution_allowed_now is False, "execution_allowed_now must be False"
    assert report.memory_semantic_write_allowed_now is False, "memory_semantic_write_allowed_now must be False"
    assert report.can_execute_real_write is False, "can_execute_real_write must be False"
    assert report.allow_real_write is False, "allow_real_write must be False"
    assert report.dry_run_only is True, "dry_run_only must be True"
    assert report.simulated_only is True, "simulated_only must be True"
    assert report.snapshot_only is True, "snapshot_only must be True"
    print("  PASSED")


def test_missing_operator_intent():
    """Test missing operator intent returns MANUAL_REVIEW_REQUIRED."""
    print("TEST: Valid evidence + missing intent => MANUAL_REVIEW_REQUIRED")
    snap = create_preflight_snapshot()
    evidence = get_valid_evidence()
    
    report = snap.build_snapshot_read_only(evidence, None)
    
    assert report.decision == SemanticMemoryPreflightSnapshotDecision.MANUAL_REVIEW_REQUIRED, \
        f"Expected MANUAL_REVIEW_REQUIRED, got {report.decision}"
    print("  PASSED")


def test_invalid_execution_package_decision():
    """Test invalid execution_package_decision blocks execution."""
    print("TEST: Invalid execution_package_decision => BLOCK_PREFLIGHT_SNAPSHOT")
    snap = create_preflight_snapshot()
    evidence = get_valid_evidence()
    evidence["execution_package_decision"] = "NOT_READY"
    operator_intent = get_valid_operator_intent()
    
    report = snap.build_snapshot_read_only(evidence, operator_intent)
    
    assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT, \
        f"Expected BLOCK_PREFLIGHT_SNAPSHOT, got {report.decision}"
    assert any(f.code == "INVALID_EXECUTION_PACKAGE_DECISION" for f in report.findings), \
        "Expected INVALID_EXECUTION_PACKAGE_DECISION finding"
    print("  PASSED")


def test_allows_execution_now_true():
    """Test allows_execution_now True blocks execution."""
    print("TEST: allows_execution_now=True => BLOCK_PREFLIGHT_SNAPSHOT")
    snap = create_preflight_snapshot()
    evidence = get_valid_evidence()
    operator_intent = get_valid_operator_intent()
    operator_intent["allows_execution_now"] = True
    
    report = snap.build_snapshot_read_only(evidence, operator_intent)
    
    assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT, \
        f"Expected BLOCK_PREFLIGHT_SNAPSHOT, got {report.decision}"
    assert any(f.code == "EXECUTION_NOW_BLOCKED" for f in report.findings), \
        "Expected EXECUTION_NOW_BLOCKED finding"
    print("  PASSED")


def test_memory_semantic_write_allowed_now_true():
    """Test memory_semantic_write_allowed_now True blocks execution."""
    print("TEST: memory_semantic_write_allowed_now=True => BLOCK_PREFLIGHT_SNAPSHOT")
    snap = create_preflight_snapshot()
    evidence = get_valid_evidence()
    operator_intent = get_valid_operator_intent()
    operator_intent["allows_memory_semantic_write_now"] = True
    
    report = snap.build_snapshot_read_only(evidence, operator_intent)
    
    assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT, \
        f"Expected BLOCK_PREFLIGHT_SNAPSHOT, got {report.decision}"
    assert any(f.code == "MEMORY_SEMANTIC_WRITE_NOW_BLOCKED" for f in report.findings), \
        "Expected MEMORY_SEMANTIC_WRITE_NOW_BLOCKED finding"
    print("  PASSED")


def test_runtime_active_true():
    """Test runtime_active True blocks execution."""
    print("TEST: runtime_active=True => BLOCK_PREFLIGHT_SNAPSHOT")
    snap = create_preflight_snapshot()
    evidence = get_valid_evidence()
    evidence["runtime_active"] = True
    operator_intent = get_valid_operator_intent()
    
    report = snap.build_snapshot_read_only(evidence, operator_intent)
    
    assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT, \
        f"Expected BLOCK_PREFLIGHT_SNAPSHOT, got {report.decision}"
    assert any(f.code == "RUNTIME_ACTIVE" for f in report.findings), \
        "Expected RUNTIME_ACTIVE finding"
    print("  PASSED")


def test_invariants():
    """Test that safety invariants are always enforced."""
    print("TEST: Safety invariants always enforced")
    snap = create_preflight_snapshot()
    evidence = get_valid_evidence()
    operator_intent = get_valid_operator_intent()
    
    report = snap.build_snapshot_read_only(evidence, operator_intent)
    
    # Verify all safety invariants
    assert report.execution_allowed_now is False, "execution_allowed_now must always be False"
    assert report.memory_semantic_write_allowed_now is False, "memory_semantic_write_allowed_now must always be False"
    assert report.can_execute_real_write is False, "can_execute_real_write must always be False"
    assert report.allow_real_write is False, "allow_real_write must always be False"
    assert report.dry_run_only is True, "dry_run_only must always be True"
    assert report.simulated_only is True, "simulated_only must always be True"
    assert report.snapshot_only is True, "snapshot_only must always be True"
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
    snap = create_preflight_snapshot()
    contract = snap.summarize_contract()
    
    assert contract["allow_real_write"] is False, "Contract allow_real_write must be False"
    assert contract["can_execute_real_write"] is False, "Contract can_execute_real_write must be False"
    assert contract["execution_allowed_now"] is False, "Contract execution_allowed_now must be False"
    assert contract["memory_semantic_write_allowed_now"] is False, "Contract memory_semantic_write_allowed_now must be False"
    assert contract["dry_run_only"] is True, "Contract dry_run_only must be True"
    assert contract["simulated_only"] is True, "Contract simulated_only must be True"
    assert contract["snapshot_only"] is True, "Contract snapshot_only must be True"
    assert contract["requires_second_confirmation"] is True, "Contract requires_second_confirmation must be True"
    print("  PASSED")


def test_block_snapshot():
    """Test manual block snapshot functionality."""
    print("TEST: Manual block snapshot => BLOCK_PREFLIGHT_SNAPSHOT")
    snap = create_preflight_snapshot()
    
    report = snap.block_snapshot("Test block reason")
    
    assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT, \
        f"Expected BLOCK_PREFLIGHT_SNAPSHOT, got {report.decision}"
    assert report.blocker_count == 1, f"Expected 1 blocker, got {report.blocker_count}"
    print("  PASSED")


def test_expected_hashes():
    """Test that snapshot has expected hash constants."""
    print("TEST: Snapshot has expected hash constants")
    snap = create_preflight_snapshot()
    
    assert snap.EXPECTED_EXECUTION_PACKAGE_HASH == "5c41ba4b", \
        f"Expected 5c41ba4b, got {snap.EXPECTED_EXECUTION_PACKAGE_HASH}"
    assert snap.EXPECTED_FINAL_PRE_EXECUTION_GATE_HASH == "dcf2b72e", \
        f"Expected dcf2b72e, got {snap.EXPECTED_FINAL_PRE_EXECUTION_GATE_HASH}"
    assert snap.EXPECTED_CANDIDATE_DESIGN_HASH == "b21c22dd", \
        f"Expected b21c22dd, got {snap.EXPECTED_CANDIDATE_DESIGN_HASH}"
    assert snap.EXPECTED_AUTHORIZATION_HASH == "819be9f2", \
        f"Expected 819be9f2, got {snap.EXPECTED_AUTHORIZATION_HASH}"
    assert snap.EXPECTED_GO_NO_GO_HASH == "433c5842", \
        f"Expected 433c5842, got {snap.EXPECTED_GO_NO_GO_HASH}"
    assert snap.EXPECTED_HEAD_HASH == "5c41ba4b", \
        f"Expected 5c41ba4b, got {snap.EXPECTED_HEAD_HASH}"
    assert snap.EXPECTED_ORIGIN_HEAD_HASH == "5c41ba4b", \
        f"Expected 5c41ba4b, got {snap.EXPECTED_ORIGIN_HEAD_HASH}"
    assert snap.EXPECTED_BRANCH == "codex/own-capital-sustainable-return", \
        f"Expected codex/own-capital-sustainable-return, got {snap.EXPECTED_BRANCH}"
    print("  PASSED")


def test_report_structure():
    """Test that report has required structure."""
    print("TEST: Report structure validation")
    snap = create_preflight_snapshot()
    evidence = get_valid_evidence()
    operator_intent = get_valid_operator_intent()
    
    report = snap.build_snapshot_read_only(evidence, operator_intent)
    
    # Verify all required fields
    assert report.snapshot_id, "Missing snapshot_id"
    assert report.created_at_utc, "Missing created_at_utc"
    assert report.decision, "Missing decision"
    assert isinstance(report.findings, list), "findings must be a list"
    assert isinstance(report.blocker_count, int), "blocker_count must be int"
    assert isinstance(report.warning_count, int), "warning_count must be int"
    assert isinstance(report.info_count, int), "info_count must be int"
    assert report.execution_package_hash, "Missing execution_package_hash"
    assert report.final_pre_execution_gate_hash, "Missing final_pre_execution_gate_hash"
    assert report.candidate_design_hash, "Missing candidate_design_hash"
    assert report.authorization_hash, "Missing authorization_hash"
    assert report.go_no_go_hash, "Missing go_no_go_hash"
    assert report.repo_root, "Missing repo_root"
    assert report.branch, "Missing branch"
    assert report.head_hash, "Missing head_hash"
    assert report.origin_head_hash, "Missing origin_head_hash"
    assert isinstance(report.commits_pending, int), "commits_pending must be int"
    assert isinstance(report.staged_files, list), "staged_files must be a list"
    assert isinstance(report.dirty_files, list), "dirty_files must be a list"
    assert isinstance(report.runtime_expected_down, bool), "runtime_expected_down must be bool"
    assert isinstance(report.backup_required, bool), "backup_required must be bool"
    assert isinstance(report.rollback_required, bool), "rollback_required must be bool"
    assert isinstance(report.second_confirmation_required, bool), "second_confirmation_required must be bool"
    print("  PASSED")


def main():
    """Run all smoke tests."""
    print("=" * 70)
    print("SMOKE TEST: SemanticMemory Controlled Real Write Preflight Snapshot")
    print("=" * 70)
    print()
    
    tests = [
        test_expected_hashes,
        test_valid_evidence_and_intent,
        test_missing_operator_intent,
        test_invalid_execution_package_decision,
        test_allows_execution_now_true,
        test_memory_semantic_write_allowed_now_true,
        test_runtime_active_true,
        test_invariants,
        test_contract_summary,
        test_block_snapshot,
        test_report_structure,
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
        print("SMOKE_SEMANTIC_MEMORY_CONTROLLED_REAL_WRITE_PREFLIGHT_SNAPSHOT_OK")
        return 0
    else:
        print("SMOKE_FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())