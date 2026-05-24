#!/usr/bin/env python3
"""
Smoke test for SemanticMemory Controlled Real Write Execution Package.

This smoke test validates the read-only execution package
without running any real operations.
"""

import json
import sys
from pathlib import Path

# Ensure brain module is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.semantic_memory_controlled_real_write_execution_package import (
    SemanticMemoryControlledRealWriteExecutionPackage,
    SemanticMemoryExecutionPackageDecision,
    create_execution_package,
)


def get_valid_evidence():
    """Return valid evidence dictionary using JSON clone."""
    evidence = {
        "final_pre_execution_decision": "PRE_EXECUTION_GATE_READY",
        "final_pre_execution_gate_hash": "dcf2b72e",
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
        "execution_allowed_now": False,
        "can_execute_real_write": False,
        "allow_real_write": False,
        "dry_run_only": True,
        "simulated_only": True,
        "requires_second_confirmation": True,
        "requires_runtime_down": True,
        "requires_clean_git_gate": True,
        "requires_real_backup_before_execution": True,
        "requires_real_rollback_before_execution": True,
        "security_validation_ok": True
    }
    return json.loads(json.dumps(evidence))


def get_valid_execution_intent():
    """Return valid execution intent dictionary using JSON clone."""
    intent = {
        "requested_by": "Cesar",
        "intent_scope": "execution_package_only",
        "target_operation": "single_curated_fact_probe",
        "target_room": "migration_p2e_probe",
        "candidate_fact_key": "p2e_real_write_probe",
        "candidate_fact_value": "controlled execution package only; not executed",
        "acknowledges_no_execution_now": True,
        "allows_execution_now": False,
        "requires_future_second_confirmation": True,
        "requires_future_runtime_down": True,
        "requires_future_clean_git": True,
        "requires_future_real_backup": True,
        "requires_future_real_rollback": True
    }
    return json.loads(json.dumps(intent))


def test_valid_evidence_and_intent():
    """Test valid evidence and intent returns EXECUTION_PACKAGE_READY."""
    print("TEST: Valid evidence + valid intent => EXECUTION_PACKAGE_READY")
    pkg = create_execution_package()
    evidence = get_valid_evidence()
    execution_intent = get_valid_execution_intent()
    
    report = pkg.build_execution_package_read_only(evidence, execution_intent)
    
    assert report.decision == SemanticMemoryExecutionPackageDecision.EXECUTION_PACKAGE_READY, \
        f"Expected EXECUTION_PACKAGE_READY, got {report.decision}"
    assert report.execution_allowed_now is False, "execution_allowed_now must be False"
    assert report.can_execute_real_write is False, "can_execute_real_write must be False"
    assert report.allow_real_write is False, "allow_real_write must be False"
    assert report.dry_run_only is True, "dry_run_only must be True"
    assert report.simulated_only is True, "simulated_only must be True"
    assert report.package_only is True, "package_only must be True"
    print("  PASSED")


def test_missing_execution_intent():
    """Test missing execution intent returns MANUAL_REVIEW_REQUIRED."""
    print("TEST: Valid evidence + missing intent => MANUAL_REVIEW_REQUIRED")
    pkg = create_execution_package()
    evidence = get_valid_evidence()
    
    report = pkg.build_execution_package_read_only(evidence, None)
    
    assert report.decision == SemanticMemoryExecutionPackageDecision.MANUAL_REVIEW_REQUIRED, \
        f"Expected MANUAL_REVIEW_REQUIRED, got {report.decision}"
    print("  PASSED")


def test_invalid_final_pre_execution_decision():
    """Test invalid final_pre_execution_decision blocks execution."""
    print("TEST: Invalid final_pre_execution_decision => BLOCK_EXECUTION_PACKAGE")
    pkg = create_execution_package()
    evidence = get_valid_evidence()
    evidence["final_pre_execution_decision"] = "NOT_READY"
    execution_intent = get_valid_execution_intent()
    
    report = pkg.build_execution_package_read_only(evidence, execution_intent)
    
    assert report.decision == SemanticMemoryExecutionPackageDecision.BLOCK_EXECUTION_PACKAGE, \
        f"Expected BLOCK_EXECUTION_PACKAGE, got {report.decision}"
    assert any(f.code == "INVALID_FINAL_PRE_EXECUTION_DECISION" for f in report.findings), \
        "Expected INVALID_FINAL_PRE_EXECUTION_DECISION finding"
    print("  PASSED")


def test_allows_execution_now_true():
    """Test allows_execution_now True blocks execution."""
    print("TEST: allows_execution_now=True => BLOCK_EXECUTION_PACKAGE")
    pkg = create_execution_package()
    evidence = get_valid_evidence()
    execution_intent = get_valid_execution_intent()
    execution_intent["allows_execution_now"] = True
    
    report = pkg.build_execution_package_read_only(evidence, execution_intent)
    
    assert report.decision == SemanticMemoryExecutionPackageDecision.BLOCK_EXECUTION_PACKAGE, \
        f"Expected BLOCK_EXECUTION_PACKAGE, got {report.decision}"
    assert any(f.code == "EXECUTION_NOW_BLOCKED" for f in report.findings), \
        "Expected EXECUTION_NOW_BLOCKED finding"
    print("  PASSED")


def test_runtime_active_true():
    """Test runtime_active True blocks execution."""
    print("TEST: runtime_active=True => BLOCK_EXECUTION_PACKAGE")
    pkg = create_execution_package()
    evidence = get_valid_evidence()
    evidence["runtime_active"] = True
    execution_intent = get_valid_execution_intent()
    
    report = pkg.build_execution_package_read_only(evidence, execution_intent)
    
    assert report.decision == SemanticMemoryExecutionPackageDecision.BLOCK_EXECUTION_PACKAGE, \
        f"Expected BLOCK_EXECUTION_PACKAGE, got {report.decision}"
    assert any(f.code == "RUNTIME_ACTIVE" for f in report.findings), \
        "Expected RUNTIME_ACTIVE finding"
    print("  PASSED")


def test_invariants():
    """Test that safety invariants are always enforced."""
    print("TEST: Safety invariants always enforced")
    pkg = create_execution_package()
    evidence = get_valid_evidence()
    execution_intent = get_valid_execution_intent()
    
    report = pkg.build_execution_package_read_only(evidence, execution_intent)
    
    # Verify all safety invariants
    assert report.execution_allowed_now is False, "execution_allowed_now must always be False"
    assert report.can_execute_real_write is False, "can_execute_real_write must always be False"
    assert report.allow_real_write is False, "allow_real_write must always be False"
    assert report.dry_run_only is True, "dry_run_only must always be True"
    assert report.simulated_only is True, "simulated_only must always be True"
    assert report.package_only is True, "package_only must always be True"
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
    pkg = create_execution_package()
    contract = pkg.summarize_contract()
    
    assert contract["allow_real_write"] is False, "Contract allow_real_write must be False"
    assert contract["can_execute_real_write"] is False, "Contract can_execute_real_write must be False"
    assert contract["execution_allowed_now"] is False, "Contract execution_allowed_now must be False"
    assert contract["dry_run_only"] is True, "Contract dry_run_only must be True"
    assert contract["simulated_only"] is True, "Contract simulated_only must be True"
    assert contract["package_only"] is True, "Contract package_only must be True"
    assert contract["requires_second_confirmation"] is True, "Contract requires_second_confirmation must be True"
    print("  PASSED")


def test_block_package():
    """Test manual block package functionality."""
    print("TEST: Manual block package => BLOCK_EXECUTION_PACKAGE")
    pkg = create_execution_package()
    
    report = pkg.block_package("Test block reason")
    
    assert report.decision == SemanticMemoryExecutionPackageDecision.BLOCK_EXECUTION_PACKAGE, \
        f"Expected BLOCK_EXECUTION_PACKAGE, got {report.decision}"
    assert report.blocker_count == 1, f"Expected 1 blocker, got {report.blocker_count}"
    print("  PASSED")


def test_expected_hashes():
    """Test that package has expected hash constants."""
    print("TEST: Package has expected hash constants")
    pkg = create_execution_package()
    
    assert pkg.EXPECTED_FINAL_PRE_EXECUTION_GATE_HASH == "dcf2b72e", \
        f"Expected dcf2b72e, got {pkg.EXPECTED_FINAL_PRE_EXECUTION_GATE_HASH}"
    assert pkg.EXPECTED_CANDIDATE_DESIGN_HASH == "b21c22dd", \
        f"Expected b21c22dd, got {pkg.EXPECTED_CANDIDATE_DESIGN_HASH}"
    assert pkg.EXPECTED_AUTHORIZATION_HASH == "819be9f2", \
        f"Expected 819be9f2, got {pkg.EXPECTED_AUTHORIZATION_HASH}"
    assert pkg.EXPECTED_GO_NO_GO_HASH == "433c5842", \
        f"Expected 433c5842, got {pkg.EXPECTED_GO_NO_GO_HASH}"
    print("  PASSED")


def test_future_execution_command_structure():
    """Test that future execution command has required structure."""
    print("TEST: Future execution command structure")
    pkg = create_execution_package()
    evidence = get_valid_evidence()
    execution_intent = get_valid_execution_intent()
    
    report = pkg.build_execution_package_read_only(evidence, execution_intent)
    
    cmd = report.future_execution_command
    assert "command" in cmd, "Missing 'command' in future_execution_command"
    assert "target_operation" in cmd, "Missing 'target_operation' in future_execution_command"
    assert "requires_prior" in cmd, "Missing 'requires_prior' in future_execution_command"
    assert "authorized_by" in cmd, "Missing 'authorized_by' in future_execution_command"
    print("  PASSED")


def test_future_payload_structure():
    """Test that future payload has required structure."""
    print("TEST: Future payload structure")
    pkg = create_execution_package()
    evidence = get_valid_evidence()
    execution_intent = get_valid_execution_intent()
    
    report = pkg.build_execution_package_read_only(evidence, execution_intent)
    
    payload = report.future_payload
    assert "fact_key" in payload, "Missing 'fact_key' in future_payload"
    assert "fact_value" in payload, "Missing 'fact_value' in future_payload"
    assert "target_room" in payload, "Missing 'target_room' in future_payload"
    assert "metadata" in payload, "Missing 'metadata' in future_payload"
    print("  PASSED")


def test_backup_manifest_structure():
    """Test that backup manifest has required structure."""
    print("TEST: Backup manifest structure")
    pkg = create_execution_package()
    evidence = get_valid_evidence()
    execution_intent = get_valid_execution_intent()
    
    report = pkg.build_execution_package_read_only(evidence, execution_intent)
    
    manifest = report.required_backup_manifest
    assert "manifest_type" in manifest, "Missing 'manifest_type' in required_backup_manifest"
    assert "target" in manifest, "Missing 'target' in required_backup_manifest"
    assert "verification" in manifest, "Missing 'verification' in required_backup_manifest"
    print("  PASSED")


def test_rollback_manifest_structure():
    """Test that rollback manifest has required structure."""
    print("TEST: Rollback manifest structure")
    pkg = create_execution_package()
    evidence = get_valid_evidence()
    execution_intent = get_valid_execution_intent()
    
    report = pkg.build_execution_package_read_only(evidence, execution_intent)
    
    manifest = report.required_rollback_manifest
    assert "manifest_type" in manifest, "Missing 'manifest_type' in required_rollback_manifest"
    assert "trigger" in manifest, "Missing 'trigger' in required_rollback_manifest"
    assert "authorization" in manifest, "Missing 'authorization' in required_rollback_manifest"
    print("  PASSED")


def main():
    """Run all smoke tests."""
    print("=" * 70)
    print("SMOKE TEST: SemanticMemory Controlled Real Write Execution Package")
    print("=" * 70)
    print()
    
    tests = [
        test_expected_hashes,
        test_valid_evidence_and_intent,
        test_missing_execution_intent,
        test_invalid_final_pre_execution_decision,
        test_allows_execution_now_true,
        test_runtime_active_true,
        test_invariants,
        test_contract_summary,
        test_block_package,
        test_future_execution_command_structure,
        test_future_payload_structure,
        test_backup_manifest_structure,
        test_rollback_manifest_structure,
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
        print("SMOKE_SEMANTIC_MEMORY_CONTROLLED_REAL_WRITE_EXECUTION_PACKAGE_OK")
        return 0
    else:
        print("SMOKE_FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())