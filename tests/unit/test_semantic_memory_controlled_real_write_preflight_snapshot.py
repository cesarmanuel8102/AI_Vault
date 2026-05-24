"""
Unit tests for SemanticMemory Controlled Real Write Preflight Snapshot.

This test suite validates the read-only preflight snapshot for
SemanticMemory real write operations.
"""

import json
import pytest
from brain.semantic_memory_controlled_real_write_preflight_snapshot import (
    SemanticMemoryControlledRealWritePreflightSnapshot,
    SemanticMemoryPreflightSnapshotDecision,
    SemanticMemoryPreflightSnapshotSeverity,
    create_preflight_snapshot,
)


class TestValidEvidenceAndIntent:
    """Tests for valid evidence and intent combinations."""
    
    def get_valid_evidence(self):
        """Return valid evidence dictionary."""
        return {
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
    
    def get_valid_operator_intent(self):
        """Return valid operator intent dictionary."""
        return {
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
    
    def test_valid_evidence_and_intent_returns_ready(self):
        """Test that valid evidence and intent return PREFLIGHT_SNAPSHOT_READY."""
        snap = create_preflight_snapshot()
        evidence = self.get_valid_evidence()
        operator_intent = self.get_valid_operator_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.PREFLIGHT_SNAPSHOT_READY
    
    def test_valid_evidence_missing_intent_returns_manual_review(self):
        """Test that valid evidence with missing intent returns MANUAL_REVIEW_REQUIRED."""
        snap = create_preflight_snapshot()
        evidence = self.get_valid_evidence()
        
        report = snap.build_snapshot_read_only(evidence, None)
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.MANUAL_REVIEW_REQUIRED


class TestInvalidEvidence:
    """Tests for invalid evidence scenarios."""
    
    def get_base_evidence(self):
        """Return base valid evidence."""
        return {
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
    
    def get_base_intent(self):
        """Return base valid intent."""
        return {
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
    
    def test_invalid_execution_package_decision_blocks(self):
        """Test invalid execution_package_decision blocks execution."""
        snap = create_preflight_snapshot()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["execution_package_decision"] = "NOT_READY"
        operator_intent = self.get_base_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT
        assert any(f.code == "INVALID_EXECUTION_PACKAGE_DECISION" for f in report.findings)
    
    def test_invalid_execution_package_hash_blocks(self):
        """Test invalid execution_package_hash blocks execution."""
        snap = create_preflight_snapshot()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["execution_package_hash"] = "invalid_hash"
        operator_intent = self.get_base_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT
        assert any(f.code == "INVALID_EXECUTION_PACKAGE_HASH" for f in report.findings)
    
    def test_invalid_final_pre_execution_gate_hash_blocks(self):
        """Test invalid final_pre_execution_gate_hash blocks execution."""
        snap = create_preflight_snapshot()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["final_pre_execution_gate_hash"] = "invalid_hash"
        operator_intent = self.get_base_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT
        assert any(f.code == "INVALID_FINAL_PRE_EXECUTION_GATE_HASH" for f in report.findings)
    
    def test_invalid_candidate_design_hash_blocks(self):
        """Test invalid candidate_design_hash blocks execution."""
        snap = create_preflight_snapshot()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["candidate_design_hash"] = "invalid_hash"
        operator_intent = self.get_base_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT
        assert any(f.code == "INVALID_CANDIDATE_DESIGN_HASH" for f in report.findings)
    
    def test_invalid_authorization_hash_blocks(self):
        """Test invalid authorization_hash blocks execution."""
        snap = create_preflight_snapshot()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["authorization_hash"] = "invalid_hash"
        operator_intent = self.get_base_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT
        assert any(f.code == "INVALID_AUTHORIZATION_HASH" for f in report.findings)
    
    def test_invalid_go_no_go_hash_blocks(self):
        """Test invalid go_no_go_hash blocks execution."""
        snap = create_preflight_snapshot()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["go_no_go_hash"] = "invalid_hash"
        operator_intent = self.get_base_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT
        assert any(f.code == "INVALID_GO_NO_GO_HASH" for f in report.findings)
    
    def test_invalid_head_hash_blocks(self):
        """Test invalid head_hash blocks execution."""
        snap = create_preflight_snapshot()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["head_hash"] = "invalid_hash"
        operator_intent = self.get_base_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT
        assert any(f.code == "INVALID_HEAD_HASH" for f in report.findings)
    
    def test_invalid_origin_head_hash_blocks(self):
        """Test invalid origin_head_hash blocks execution."""
        snap = create_preflight_snapshot()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["origin_head_hash"] = "invalid_hash"
        operator_intent = self.get_base_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT
        assert any(f.code == "INVALID_ORIGIN_HEAD_HASH" for f in report.findings)
    
    def test_pending_commits_blocks(self):
        """Test pending commits block execution."""
        snap = create_preflight_snapshot()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["commits_pending"] = 5
        operator_intent = self.get_base_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT
        assert any(f.code == "PENDING_COMMITS_DETECTED" for f in report.findings)
    
    def test_staged_files_blocks(self):
        """Test staged files block execution."""
        snap = create_preflight_snapshot()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["staged_files"] = ["some_file.py"]
        operator_intent = self.get_base_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT
        assert any(f.code == "STAGED_FILES_DETECTED" for f in report.findings)
    
    def test_runtime_active_blocks(self):
        """Test runtime_active True blocks execution."""
        snap = create_preflight_snapshot()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["runtime_active"] = True
        operator_intent = self.get_base_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT
        assert any(f.code == "RUNTIME_ACTIVE" for f in report.findings)
    
    def test_allows_auto_execute_blocks(self):
        """Test allows_auto_execute True blocks execution."""
        snap = create_preflight_snapshot()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["allows_auto_execute"] = True
        operator_intent = self.get_base_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT
        assert any(f.code == "AUTO_EXECUTE_ENABLED" for f in report.findings)
    
    def test_execution_allowed_now_true_blocks(self):
        """Test execution_allowed_now True blocks execution."""
        snap = create_preflight_snapshot()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["execution_allowed_now"] = True
        operator_intent = self.get_base_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT
        assert any(f.code == "EXECUTION_ALLOWED_NOW_BLOCKED" for f in report.findings)
    
    def test_can_execute_real_write_true_blocks(self):
        """Test can_execute_real_write True blocks execution."""
        snap = create_preflight_snapshot()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["can_execute_real_write"] = True
        operator_intent = self.get_base_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT
        assert any(f.code == "CAN_EXECUTE_REAL_WRITE_BLOCKED" for f in report.findings)
    
    def test_allow_real_write_true_blocks(self):
        """Test allow_real_write True blocks execution."""
        snap = create_preflight_snapshot()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["allow_real_write"] = True
        operator_intent = self.get_base_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT
        assert any(f.code == "ALLOW_REAL_WRITE_BLOCKED" for f in report.findings)
    
    def test_memory_semantic_write_allowed_now_true_blocks(self):
        """Test memory_semantic_write_allowed_now True blocks execution."""
        snap = create_preflight_snapshot()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["memory_semantic_write_allowed_now"] = True
        operator_intent = self.get_base_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT
        assert any(f.code == "MEMORY_SEMANTIC_WRITE_ALLOWED_NOW_BLOCKED" for f in report.findings)


class TestInvalidOperatorIntent:
    """Tests for invalid operator intent scenarios."""
    
    def get_valid_evidence(self):
        """Return valid evidence."""
        return {
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
    
    def get_base_intent(self):
        """Return base valid intent."""
        return {
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
    
    def test_allows_execution_now_true_blocks(self):
        """Test allows_execution_now True blocks execution."""
        snap = create_preflight_snapshot()
        evidence = self.get_valid_evidence()
        operator_intent = json.loads(json.dumps(self.get_base_intent()))
        operator_intent["allows_execution_now"] = True
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT
        assert any(f.code == "EXECUTION_NOW_BLOCKED" for f in report.findings)
    
    def test_allows_memory_semantic_write_now_true_blocks(self):
        """Test allows_memory_semantic_write_now True blocks execution."""
        snap = create_preflight_snapshot()
        evidence = self.get_valid_evidence()
        operator_intent = json.loads(json.dumps(self.get_base_intent()))
        operator_intent["allows_memory_semantic_write_now"] = True
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT
        assert any(f.code == "MEMORY_SEMANTIC_WRITE_NOW_BLOCKED" for f in report.findings)
    
    def test_acknowledges_no_execution_now_false_blocks(self):
        """Test acknowledges_no_execution_now False blocks execution."""
        snap = create_preflight_snapshot()
        evidence = self.get_valid_evidence()
        operator_intent = json.loads(json.dumps(self.get_base_intent()))
        operator_intent["acknowledges_no_execution_now"] = False
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT
        assert any(f.code == "NO_EXECUTION_ACKNOWLEDGMENT_MISSING" for f in report.findings)


class TestSafetyInvariants:
    """Tests for safety invariants in the preflight snapshot."""
    
    def get_valid_evidence(self):
        """Return valid evidence."""
        return {
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
    
    def get_valid_intent(self):
        """Return valid intent."""
        return {
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
    
    def test_execution_allowed_now_always_false(self):
        """Test that execution_allowed_now is always False."""
        snap = create_preflight_snapshot()
        evidence = self.get_valid_evidence()
        operator_intent = self.get_valid_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.execution_allowed_now is False
    
    def test_memory_semantic_write_allowed_now_always_false(self):
        """Test that memory_semantic_write_allowed_now is always False."""
        snap = create_preflight_snapshot()
        evidence = self.get_valid_evidence()
        operator_intent = self.get_valid_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.memory_semantic_write_allowed_now is False
    
    def test_can_execute_real_write_always_false(self):
        """Test that can_execute_real_write is always False."""
        snap = create_preflight_snapshot()
        evidence = self.get_valid_evidence()
        operator_intent = self.get_valid_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.can_execute_real_write is False
    
    def test_allow_real_write_always_false(self):
        """Test that allow_real_write is always False."""
        snap = create_preflight_snapshot()
        evidence = self.get_valid_evidence()
        operator_intent = self.get_valid_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.allow_real_write is False
    
    def test_dry_run_only_always_true(self):
        """Test that dry_run_only is always True."""
        snap = create_preflight_snapshot()
        evidence = self.get_valid_evidence()
        operator_intent = self.get_valid_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.dry_run_only is True
    
    def test_simulated_only_always_true(self):
        """Test that simulated_only is always True."""
        snap = create_preflight_snapshot()
        evidence = self.get_valid_evidence()
        operator_intent = self.get_valid_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.simulated_only is True
    
    def test_snapshot_only_always_true(self):
        """Test that snapshot_only is always True."""
        snap = create_preflight_snapshot()
        evidence = self.get_valid_evidence()
        operator_intent = self.get_valid_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.snapshot_only is True
    
    def test_requires_second_confirmation_always_true(self):
        """Test that requires_second_confirmation is always True."""
        snap = create_preflight_snapshot()
        evidence = self.get_valid_evidence()
        operator_intent = self.get_valid_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.requires_second_confirmation is True
    
    def test_requires_runtime_down_always_true(self):
        """Test that requires_runtime_down is always True."""
        snap = create_preflight_snapshot()
        evidence = self.get_valid_evidence()
        operator_intent = self.get_valid_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.requires_runtime_down is True
    
    def test_requires_clean_git_gate_always_true(self):
        """Test that requires_clean_git_gate is always True."""
        snap = create_preflight_snapshot()
        evidence = self.get_valid_evidence()
        operator_intent = self.get_valid_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.requires_clean_git_gate is True
    
    def test_requires_real_backup_before_execution_always_true(self):
        """Test that requires_real_backup_before_execution is always True."""
        snap = create_preflight_snapshot()
        evidence = self.get_valid_evidence()
        operator_intent = self.get_valid_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.requires_real_backup_before_execution is True
    
    def test_requires_real_rollback_before_execution_always_true(self):
        """Test that requires_real_rollback_before_execution is always True."""
        snap = create_preflight_snapshot()
        evidence = self.get_valid_evidence()
        operator_intent = self.get_valid_intent()
        
        report = snap.build_snapshot_read_only(evidence, operator_intent)
        
        assert report.requires_real_rollback_before_execution is True


class TestBlockSnapshot:
    """Tests for manual block snapshot functionality."""
    
    def test_block_snapshot_returns_blocked_decision(self):
        """Test that block_snapshot returns BLOCK_PREFLIGHT_SNAPSHOT."""
        snap = create_preflight_snapshot()
        
        report = snap.block_snapshot("Manual block for testing")
        
        assert report.decision == SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT
        assert report.blocker_count == 1


class TestSummarizeContract:
    """Tests for contract summarization."""
    
    def test_summarize_contract_returns_safety_values(self):
        """Test that summarize_contract returns correct safety values."""
        snap = create_preflight_snapshot()
        
        contract = snap.summarize_contract()
        
        assert contract["allow_real_write"] is False
        assert contract["can_execute_real_write"] is False
        assert contract["execution_allowed_now"] is False
        assert contract["memory_semantic_write_allowed_now"] is False
        assert contract["dry_run_only"] is True
        assert contract["simulated_only"] is True
        assert contract["snapshot_only"] is True
        assert contract["requires_second_confirmation"] is True


class TestExpectedHashes:
    """Tests for expected hash constants."""
    
    def test_expected_hashes(self):
        """Test that snapshot has expected hash constants."""
        snap = create_preflight_snapshot()
        
        assert snap.EXPECTED_EXECUTION_PACKAGE_HASH == "5c41ba4b"
        assert snap.EXPECTED_FINAL_PRE_EXECUTION_GATE_HASH == "dcf2b72e"
        assert snap.EXPECTED_CANDIDATE_DESIGN_HASH == "b21c22dd"
        assert snap.EXPECTED_AUTHORIZATION_HASH == "819be9f2"
        assert snap.EXPECTED_GO_NO_GO_HASH == "433c5842"
        assert snap.EXPECTED_HEAD_HASH == "5c41ba4b"
        assert snap.EXPECTED_ORIGIN_HEAD_HASH == "5c41ba4b"
        assert snap.EXPECTED_BRANCH == "codex/own-capital-sustainable-return"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])