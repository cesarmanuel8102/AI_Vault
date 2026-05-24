"""Smoke test for P2-E Commit 4D-ControlledRealWriteCandidateDesign.

This smoke test verifies the candidate design produces correct decisions
for different scenarios without executing any real writes.
"""

import json
import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.semantic_memory_controlled_real_write_candidate_design import (
    SemanticMemoryCandidateDesignDecision,
    SemanticMemoryControlledRealWriteCandidateDesign,
)


def create_valid_evidence():
    """Create valid evidence for candidate design."""
    return {
        "authorization_decision": "AUTHORIZATION_PACKET_READY",
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
        "security_validation_ok": True,
    }


def create_valid_request():
    """Create valid candidate request."""
    return {
        "requested_by": "Cesar",
        "candidate_scope": "single_curated_fact_probe",
        "target_room": "migration_p2e_probe",
        "candidate_fact_key": "p2e_real_write_probe",
        "candidate_fact_value": "controlled candidate design only; not executed",
        "operation_mode": "design_only",
        "expects_no_runtime": True,
        "expects_no_write": True,
        "expects_second_confirmation": True,
    }


def deep_clone_dict(d):
    """Deep clone a dict using json without copy helpers."""
    return json.loads(json.dumps(d))


def run_smoke_tests():
    """Run all smoke tests."""
    print("=" * 70)
    print("SMOKE TEST: Semantic Memory Controlled Real Write Candidate Design")
    print("=" * 70)
    print()
    
    design = SemanticMemoryControlledRealWriteCandidateDesign()
    passed = 0
    failed = 0
    
    # Test 1: Valid evidence + request = CANDIDATE_DESIGN_READY
    print("[TEST 1] Valid evidence + request produces CANDIDATE_DESIGN_READY...")
    evidence = create_valid_evidence()
    request = create_valid_request()
    report = design.build_candidate_design_read_only(evidence, request)
    
    if report.decision == SemanticMemoryCandidateDesignDecision.CANDIDATE_DESIGN_READY:
        print("  PASSED: Valid evidence + request produces CANDIDATE_DESIGN_READY")
        passed += 1
    else:
        print(f"  FAILED: Expected CANDIDATE_DESIGN_READY, got {report.decision.value}")
        failed += 1
    
    # Verify safety invariants
    if report.can_execute_real_write is False:
        print("  PASSED: can_execute_real_write is False")
        passed += 1
    else:
        print("  FAILED: can_execute_real_write should be False")
        failed += 1
    
    if report.allow_real_write is False:
        print("  PASSED: allow_real_write is False")
        passed += 1
    else:
        print("  FAILED: allow_real_write should be False")
        failed += 1
    
    if report.dry_run_only is True:
        print("  PASSED: dry_run_only is True")
        passed += 1
    else:
        print("  FAILED: dry_run_only should be True")
        failed += 1
    
    if report.simulated_only is True:
        print("  PASSED: simulated_only is True")
        passed += 1
    else:
        print("  FAILED: simulated_only should be True")
        failed += 1
    
    if report.requires_second_confirmation is True:
        print("  PASSED: requires_second_confirmation is True")
        passed += 1
    else:
        print("  FAILED: requires_second_confirmation should be True")
        failed += 1
    
    if report.requires_runtime_down is True:
        print("  PASSED: requires_runtime_down is True")
        passed += 1
    else:
        print("  FAILED: requires_runtime_down should be True")
        failed += 1
    
    if report.requires_clean_git_gate is True:
        print("  PASSED: requires_clean_git_gate is True")
        passed += 1
    else:
        print("  FAILED: requires_clean_git_gate should be True")
        failed += 1
    
    print()
    
    # Test 2: Missing request = MANUAL_REVIEW_REQUIRED
    print("[TEST 2] Missing request produces MANUAL_REVIEW_REQUIRED...")
    evidence = create_valid_evidence()
    report = design.build_candidate_design_read_only(evidence, None)
    
    if report.decision == SemanticMemoryCandidateDesignDecision.MANUAL_REVIEW_REQUIRED:
        print("  PASSED: Missing request produces MANUAL_REVIEW_REQUIRED")
        passed += 1
    else:
        print(f"  FAILED: Expected MANUAL_REVIEW_REQUIRED, got {report.decision.value}")
        failed += 1
    print()
    
    # Test 3: authorization_decision="BLOCK_AUTHORIZATION" = BLOCK_CANDIDATE_DESIGN
    print("[TEST 3] authorization_decision='BLOCK_AUTHORIZATION' produces BLOCK_CANDIDATE_DESIGN...")
    evidence = deep_clone_dict(create_valid_evidence())
    evidence["authorization_decision"] = "BLOCK_AUTHORIZATION"
    request = create_valid_request()
    report = design.build_candidate_design_read_only(evidence, request)
    
    if report.decision == SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN:
        print("  PASSED: authorization_decision='BLOCK_AUTHORIZATION' produces BLOCK_CANDIDATE_DESIGN")
        passed += 1
    else:
        print(f"  FAILED: Expected BLOCK_CANDIDATE_DESIGN, got {report.decision.value}")
        failed += 1
    print()
    
    # Test 4: operation_mode="execute" = BLOCK_CANDIDATE_DESIGN
    print("[TEST 4] operation_mode='execute' produces BLOCK_CANDIDATE_DESIGN...")
    evidence = create_valid_evidence()
    request = deep_clone_dict(create_valid_request())
    request["operation_mode"] = "execute"
    report = design.build_candidate_design_read_only(evidence, request)
    
    if report.decision == SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN:
        print("  PASSED: operation_mode='execute' produces BLOCK_CANDIDATE_DESIGN")
        passed += 1
    else:
        print(f"  FAILED: Expected BLOCK_CANDIDATE_DESIGN, got {report.decision.value}")
        failed += 1
    print()
    
    # Test 5: expects_no_write=False = BLOCK_CANDIDATE_DESIGN
    print("[TEST 5] expects_no_write=False produces BLOCK_CANDIDATE_DESIGN...")
    evidence = create_valid_evidence()
    request = deep_clone_dict(create_valid_request())
    request["expects_no_write"] = False
    report = design.build_candidate_design_read_only(evidence, request)
    
    if report.decision == SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN:
        print("  PASSED: expects_no_write=False produces BLOCK_CANDIDATE_DESIGN")
        passed += 1
    else:
        print(f"  FAILED: Expected BLOCK_CANDIDATE_DESIGN, got {report.decision.value}")
        failed += 1
    print()
    
    # Test 6: runtime_active=True = BLOCK_CANDIDATE_DESIGN
    print("[TEST 6] runtime_active=True produces BLOCK_CANDIDATE_DESIGN...")
    evidence = deep_clone_dict(create_valid_evidence())
    evidence["runtime_active"] = True
    request = create_valid_request()
    report = design.build_candidate_design_read_only(evidence, request)
    
    if report.decision == SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN:
        print("  PASSED: runtime_active=True produces BLOCK_CANDIDATE_DESIGN")
        passed += 1
    else:
        print(f"  FAILED: Expected BLOCK_CANDIDATE_DESIGN, got {report.decision.value}")
        failed += 1
    print()
    
    # Summary
    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)
    
    if failed == 0:
        print()
        print("SMOKE_SEMANTIC_MEMORY_CONTROLLED_REAL_WRITE_CANDIDATE_DESIGN_OK")
        return 0
    else:
        print()
        print(f"SMOKE_FAILED: {failed} tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(run_smoke_tests())
