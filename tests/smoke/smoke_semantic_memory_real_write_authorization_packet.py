"""Smoke test for P2-E Commit 4D-RealWriteAuthorizationPacket.

This smoke test verifies the authorization packet produces correct decisions
for different scenarios without executing any real writes.
"""

import json
import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.semantic_memory_real_write_authorization_packet import (
    SemanticMemoryAuthorizationDecision,
    SemanticMemoryRealWriteAuthorizationPacket,
)


def create_valid_evidence():
    """Create valid evidence for authorization."""
    return {
        "go_no_go_decision": "GO_CANDIDATE_ONLY",
        "go_no_go_hash": "433c5842",
        "commits_pending_post_push": 0,
        "staged_files": [],
        "memory_semantic_in_scope": False,
        "runtime_active": False,
        "faiss_write_enabled": False,
        "add_memory_enabled": False,
        "allows_auto_execute": False,
        "dry_run_chain_complete": True,
        "backup_contract_ok": True,
        "rollback_simulation_ok": True,
        "security_validation_ok": True,
    }


def create_valid_human_intent():
    """Create valid human intent for authorization."""
    return {
        "approved_by": "Cesar",
        "approval_scope": "authorization_packet_only",
        "allowed_next_phase": "controlled_real_write_candidate_design",
        "understands_no_auto_execute": True,
        "allows_candidate_only": True,
        "allows_real_write_execution": False,
        "requires_second_confirmation": True,
    }


def deep_clone_dict(d):
    """Deep clone a dict using json without copy helpers."""
    return json.loads(json.dumps(d))


def run_smoke_tests():
    """Run all smoke tests."""
    print("=" * 70)
    print("SMOKE TEST: Semantic Memory Real Write Authorization Packet")
    print("=" * 70)
    print()
    
    packet = SemanticMemoryRealWriteAuthorizationPacket()
    passed = 0
    failed = 0
    
    # Test 1: Valid evidence + intent = AUTHORIZATION_PACKET_READY
    print("[TEST 1] Valid evidence + intent produces AUTHORIZATION_PACKET_READY...")
    evidence = create_valid_evidence()
    intent = create_valid_human_intent()
    report = packet.build_packet_read_only(evidence, intent)
    
    if report.decision == SemanticMemoryAuthorizationDecision.AUTHORIZATION_PACKET_READY:
        print("  PASSED: Valid evidence + intent produces AUTHORIZATION_PACKET_READY")
        passed += 1
    else:
        print(f"  FAILED: Expected AUTHORIZATION_PACKET_READY, got {report.decision.value}")
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
    
    print()
    
    # Test 2: Missing human intent = MANUAL_REVIEW_REQUIRED
    print("[TEST 2] Missing human intent produces MANUAL_REVIEW_REQUIRED...")
    evidence = create_valid_evidence()
    report = packet.build_packet_read_only(evidence, None)
    
    if report.decision == SemanticMemoryAuthorizationDecision.MANUAL_REVIEW_REQUIRED:
        print("  PASSED: Missing human intent produces MANUAL_REVIEW_REQUIRED")
        passed += 1
    else:
        print(f"  FAILED: Expected MANUAL_REVIEW_REQUIRED, got {report.decision.value}")
        failed += 1
    print()
    
    # Test 3: go_no_go_decision="NO_GO" = BLOCK_AUTHORIZATION
    print("[TEST 3] go_no_go_decision='NO_GO' produces BLOCK_AUTHORIZATION...")
    evidence = deep_clone_dict(create_valid_evidence())
    evidence["go_no_go_decision"] = "NO_GO"
    intent = create_valid_human_intent()
    report = packet.build_packet_read_only(evidence, intent)
    
    if report.decision == SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION:
        print("  PASSED: go_no_go_decision='NO_GO' produces BLOCK_AUTHORIZATION")
        passed += 1
    else:
        print(f"  FAILED: Expected BLOCK_AUTHORIZATION, got {report.decision.value}")
        failed += 1
    print()
    
    # Test 4: allows_real_write_execution=True = BLOCK_AUTHORIZATION
    print("[TEST 4] allows_real_write_execution=True produces BLOCK_AUTHORIZATION...")
    evidence = create_valid_evidence()
    intent = deep_clone_dict(create_valid_human_intent())
    intent["allows_real_write_execution"] = True
    report = packet.build_packet_read_only(evidence, intent)
    
    if report.decision == SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION:
        print("  PASSED: allows_real_write_execution=True produces BLOCK_AUTHORIZATION")
        passed += 1
    else:
        print(f"  FAILED: Expected BLOCK_AUTHORIZATION, got {report.decision.value}")
        failed += 1
    print()
    
    # Test 5: memory_semantic_in_scope=True = BLOCK_AUTHORIZATION
    print("[TEST 5] memory_semantic_in_scope=True produces BLOCK_AUTHORIZATION...")
    evidence = deep_clone_dict(create_valid_evidence())
    evidence["memory_semantic_in_scope"] = True
    intent = create_valid_human_intent()
    report = packet.build_packet_read_only(evidence, intent)
    
    if report.decision == SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION:
        print("  PASSED: memory_semantic_in_scope=True produces BLOCK_AUTHORIZATION")
        passed += 1
    else:
        print(f"  FAILED: Expected BLOCK_AUTHORIZATION, got {report.decision.value}")
        failed += 1
    print()
    
    # Test 6: faiss_write_enabled=True = BLOCK_AUTHORIZATION
    print("[TEST 6] faiss_write_enabled=True produces BLOCK_AUTHORIZATION...")
    evidence = deep_clone_dict(create_valid_evidence())
    evidence["faiss_write_enabled"] = True
    intent = create_valid_human_intent()
    report = packet.build_packet_read_only(evidence, intent)
    
    if report.decision == SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION:
        print("  PASSED: faiss_write_enabled=True produces BLOCK_AUTHORIZATION")
        passed += 1
    else:
        print(f"  FAILED: Expected BLOCK_AUTHORIZATION, got {report.decision.value}")
        failed += 1
    print()
    
    # Test 7: add_memory_enabled=True = BLOCK_AUTHORIZATION
    print("[TEST 7] add_memory_enabled=True produces BLOCK_AUTHORIZATION...")
    evidence = deep_clone_dict(create_valid_evidence())
    evidence["add_memory_enabled"] = True
    intent = create_valid_human_intent()
    report = packet.build_packet_read_only(evidence, intent)
    
    if report.decision == SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION:
        print("  PASSED: add_memory_enabled=True produces BLOCK_AUTHORIZATION")
        passed += 1
    else:
        print(f"  FAILED: Expected BLOCK_AUTHORIZATION, got {report.decision.value}")
        failed += 1
    print()
    
    # Test 8: runtime_active=True = BLOCK_AUTHORIZATION
    print("[TEST 8] runtime_active=True produces BLOCK_AUTHORIZATION...")
    evidence = deep_clone_dict(create_valid_evidence())
    evidence["runtime_active"] = True
    intent = create_valid_human_intent()
    report = packet.build_packet_read_only(evidence, intent)
    
    if report.decision == SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION:
        print("  PASSED: runtime_active=True produces BLOCK_AUTHORIZATION")
        passed += 1
    else:
        print(f"  FAILED: Expected BLOCK_AUTHORIZATION, got {report.decision.value}")
        failed += 1
    print()
    
    # Test 9: commits_pending_post_push > 0 = BLOCK_AUTHORIZATION
    print("[TEST 9] commits_pending_post_push > 0 produces BLOCK_AUTHORIZATION...")
    evidence = deep_clone_dict(create_valid_evidence())
    evidence["commits_pending_post_push"] = 1
    intent = create_valid_human_intent()
    report = packet.build_packet_read_only(evidence, intent)
    
    if report.decision == SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION:
        print("  PASSED: commits_pending_post_push > 0 produces BLOCK_AUTHORIZATION")
        passed += 1
    else:
        print(f"  FAILED: Expected BLOCK_AUTHORIZATION, got {report.decision.value}")
        failed += 1
    print()
    
    # Test 10: staged_files non-empty = BLOCK_AUTHORIZATION
    print("[TEST 10] staged_files non-empty produces BLOCK_AUTHORIZATION...")
    evidence = deep_clone_dict(create_valid_evidence())
    evidence["staged_files"] = ["test_file.py"]
    intent = create_valid_human_intent()
    report = packet.build_packet_read_only(evidence, intent)
    
    if report.decision == SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION:
        print("  PASSED: staged_files non-empty produces BLOCK_AUTHORIZATION")
        passed += 1
    else:
        print(f"  FAILED: Expected BLOCK_AUTHORIZATION, got {report.decision.value}")
        failed += 1
    print()
    
    # Summary
    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)
    
    if failed == 0:
        print()
        print("SMOKE_SEMANTIC_MEMORY_REAL_WRITE_AUTHORIZATION_PACKET_OK")
        return 0
    else:
        print()
        print(f"SMOKE_FAILED: {failed} tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(run_smoke_tests())
