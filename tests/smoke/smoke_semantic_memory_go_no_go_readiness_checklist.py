"""Smoke test for P2-E Commit 4D-GoNoGoReadinessChecklist.

This smoke test verifies the GO/NO-GO checklist produces correct decisions
for different evidence scenarios without executing any real writes.
"""

import json
import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.semantic_memory_go_no_go_readiness_checklist import (
    SemanticMemoryGoNoGoDecision,
    SemanticMemoryGoNoGoReadinessChecklist,
)


def create_valid_evidence():
    """Create valid evidence for all checks."""
    return {
        "decision_gate_ok": True,
        "evidence_contract_ok": True,
        "adapter_ok": True,
        "canary_ok": True,
        "final_readiness_ok": True,
        "backup_contract_ok": True,
        "rollback_simulation_ok": True,
        "security_validation_ok": True,
        "git_state_ok": True,
        "human_intent_ok": True,
        "commits_pending_post_push": 0,
        "staged_files": [],
        "memory_semantic_in_scope": False,
        "runtime_active": False,
        "faiss_write_enabled": False,
        "add_memory_enabled": False,
        "allows_auto_execute": False,
        "allows_candidate_only": True,
    }


def deep_copy_dict(d):
    """Clone a dict using json without copy helpers."""
    return json.loads(json.dumps(d))


def run_smoke_tests():
    """Run all smoke tests."""
    print("=" * 70)
    print("SMOKE TEST: Semantic Memory Go/No-Go Readiness Checklist")
    print("=" * 70)
    print()
    
    checklist = SemanticMemoryGoNoGoReadinessChecklist()
    passed = 0
    failed = 0
    
    # Test 1: Valid evidence = GO_CANDIDATE_ONLY
    print("[TEST 1] Valid evidence produces GO_CANDIDATE_ONLY...")
    evidence = create_valid_evidence()
    report = checklist.evaluate_checklist_read_only(evidence)
    
    if report.decision == SemanticMemoryGoNoGoDecision.GO_CANDIDATE_ONLY:
        print("  PASSED: Valid evidence produces GO_CANDIDATE_ONLY")
        passed += 1
    else:
        print(f"  FAILED: Expected GO_CANDIDATE_ONLY, got {report.decision.value}")
        failed += 1
    
    # Verify safety invariants
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
    
    if report.can_execute_real_write is False:
        print("  PASSED: can_execute_real_write is False")
        passed += 1
    else:
        print("  FAILED: can_execute_real_write should be False")
        failed += 1
    
    if report.simulated_only is True:
        print("  PASSED: simulated_only is True")
        passed += 1
    else:
        print("  FAILED: simulated_only should be True")
        failed += 1
    
    if report.requires_human_approval is True:
        print("  PASSED: requires_human_approval is True")
        passed += 1
    else:
        print("  FAILED: requires_human_approval should be True")
        failed += 1
    
    print()
    
    # Test 2: Missing human intent = MANUAL_REVIEW_REQUIRED
    print("[TEST 2] Missing human intent produces MANUAL_REVIEW_REQUIRED...")
    evidence = deep_copy_dict(create_valid_evidence())
    evidence["human_intent_ok"] = False
    report = checklist.evaluate_checklist_read_only(evidence)
    
    if report.decision == SemanticMemoryGoNoGoDecision.MANUAL_REVIEW_REQUIRED:
        print("  PASSED: Missing human intent produces MANUAL_REVIEW_REQUIRED")
        passed += 1
    else:
        print(f"  FAILED: Expected MANUAL_REVIEW_REQUIRED, got {report.decision.value}")
        failed += 1
    print()
    
    # Test 3: add_memory_enabled=True = NO_GO
    print("[TEST 3] add_memory_enabled=True produces NO_GO...")
    evidence = deep_copy_dict(create_valid_evidence())
    evidence["add_memory_enabled"] = True
    report = checklist.evaluate_checklist_read_only(evidence)
    
    if report.decision == SemanticMemoryGoNoGoDecision.NO_GO:
        print("  PASSED: add_memory_enabled=True produces NO_GO")
        passed += 1
    else:
        print(f"  FAILED: Expected NO_GO, got {report.decision.value}")
        failed += 1
    print()
    
    # Test 4: memory_semantic_in_scope=True = NO_GO
    print("[TEST 4] memory_semantic_in_scope=True produces NO_GO...")
    evidence = deep_copy_dict(create_valid_evidence())
    evidence["memory_semantic_in_scope"] = True
    report = checklist.evaluate_checklist_read_only(evidence)
    
    if report.decision == SemanticMemoryGoNoGoDecision.NO_GO:
        print("  PASSED: memory_semantic_in_scope=True produces NO_GO")
        passed += 1
    else:
        print(f"  FAILED: Expected NO_GO, got {report.decision.value}")
        failed += 1
    print()
    
    # Test 5: faiss_write_enabled=True = NO_GO
    print("[TEST 5] faiss_write_enabled=True produces NO_GO...")
    evidence = deep_copy_dict(create_valid_evidence())
    evidence["faiss_write_enabled"] = True
    report = checklist.evaluate_checklist_read_only(evidence)
    
    if report.decision == SemanticMemoryGoNoGoDecision.NO_GO:
        print("  PASSED: faiss_write_enabled=True produces NO_GO")
        passed += 1
    else:
        print(f"  FAILED: Expected NO_GO, got {report.decision.value}")
        failed += 1
    print()
    
    # Test 6: runtime_active=True = NO_GO
    print("[TEST 6] runtime_active=True produces NO_GO...")
    evidence = deep_copy_dict(create_valid_evidence())
    evidence["runtime_active"] = True
    report = checklist.evaluate_checklist_read_only(evidence)
    
    if report.decision == SemanticMemoryGoNoGoDecision.NO_GO:
        print("  PASSED: runtime_active=True produces NO_GO")
        passed += 1
    else:
        print(f"  FAILED: Expected NO_GO, got {report.decision.value}")
        failed += 1
    print()
    
    # Test 7: allows_auto_execute=True = NO_GO
    print("[TEST 7] allows_auto_execute=True produces NO_GO...")
    evidence = deep_copy_dict(create_valid_evidence())
    evidence["allows_auto_execute"] = True
    report = checklist.evaluate_checklist_read_only(evidence)
    
    if report.decision == SemanticMemoryGoNoGoDecision.NO_GO:
        print("  PASSED: allows_auto_execute=True produces NO_GO")
        passed += 1
    else:
        print(f"  FAILED: Expected NO_GO, got {report.decision.value}")
        failed += 1
    print()
    
    # Test 8: commits_pending_post_push > 0 = NO_GO
    print("[TEST 8] commits_pending_post_push > 0 produces NO_GO...")
    evidence = deep_copy_dict(create_valid_evidence())
    evidence["commits_pending_post_push"] = 1
    report = checklist.evaluate_checklist_read_only(evidence)
    
    if report.decision == SemanticMemoryGoNoGoDecision.NO_GO:
        print("  PASSED: commits_pending_post_push > 0 produces NO_GO")
        passed += 1
    else:
        print(f"  FAILED: Expected NO_GO, got {report.decision.value}")
        failed += 1
    print()
    
    # Test 9: staged_files non-empty = NO_GO
    print("[TEST 9] staged_files non-empty produces NO_GO...")
    evidence = deep_copy_dict(create_valid_evidence())
    evidence["staged_files"] = ["test_file.py"]
    report = checklist.evaluate_checklist_read_only(evidence)
    
    if report.decision == SemanticMemoryGoNoGoDecision.NO_GO:
        print("  PASSED: staged_files non-empty produces NO_GO")
        passed += 1
    else:
        print(f"  FAILED: Expected NO_GO, got {report.decision.value}")
        failed += 1
    print()
    
    # Summary
    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)
    
    if failed == 0:
        print()
        print("SMOKE_SEMANTIC_MEMORY_GO_NO_GO_READINESS_CHECKLIST_OK")
        return 0
    else:
        print()
        print(f"SMOKE_FAILED: {failed} tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(run_smoke_tests())
