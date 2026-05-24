"""
Unit tests for SemanticMemory Final Pre-Execution Gate.

This test suite validates the read-only pre-execution gate for
SemanticMemory real write operations.
"""

import json
import pytest
from brain.semantic_memory_final_pre_execution_gate import (
    SemanticMemoryFinalPreExecutionGate,
    SemanticMemoryFinalPreExecutionDecision,
    SemanticMemoryFinalPreExecutionSeverity,
    create_final_pre_execution_gate,
)


class TestValidEvidenceAndIntent:
    """Tests for valid evidence and intent combinations."""
    
    def get_valid_evidence(self):
        """Return valid evidence dictionary."""
        return {
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
    
    def get_valid_final_intent(self):
        """Return valid final intent dictionary."""
        return {
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
    
    def test_valid_evidence_and_intent_returns_ready(self):
        """Test that valid evidence and intent return PRE_EXECUTION_GATE_READY."""
        gate = create_final_pre_execution_gate()
        evidence = self.get_valid_evidence()
        final_intent = self.get_valid_final_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.decision == SemanticMemoryFinalPreExecutionDecision.PRE_EXECUTION_GATE_READY
    
    def test_valid_evidence_missing_intent_returns_manual_review(self):
        """Test that valid evidence with missing intent returns MANUAL_REVIEW_REQUIRED."""
        gate = create_final_pre_execution_gate()
        evidence = self.get_valid_evidence()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, None)
        
        assert report.decision == SemanticMemoryFinalPreExecutionDecision.MANUAL_REVIEW_REQUIRED


class TestInvalidEvidence:
    """Tests for invalid evidence scenarios."""
    
    def get_base_evidence(self):
        """Return base valid evidence."""
        return {
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
    
    def get_base_intent(self):
        """Return base valid intent."""
        return {
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
    
    def test_invalid_candidate_design_decision_blocks(self):
        """Test invalid candidate_design_decision blocks execution."""
        gate = create_final_pre_execution_gate()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["candidate_design_decision"] = "NOT_READY"
        final_intent = self.get_base_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.decision == SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION
        assert any(f.code == "INVALID_CANDIDATE_DESIGN_DECISION" for f in report.findings)
    
    def test_invalid_candidate_design_hash_blocks(self):
        """Test invalid candidate_design_hash blocks execution."""
        gate = create_final_pre_execution_gate()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["candidate_design_hash"] = "invalid_hash"
        final_intent = self.get_base_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.decision == SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION
        assert any(f.code == "INVALID_CANDIDATE_DESIGN_HASH" for f in report.findings)
    
    def test_invalid_authorization_hash_blocks(self):
        """Test invalid authorization_hash blocks execution."""
        gate = create_final_pre_execution_gate()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["authorization_hash"] = "invalid_hash"
        final_intent = self.get_base_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.decision == SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION
        assert any(f.code == "INVALID_AUTHORIZATION_HASH" for f in report.findings)
    
    def test_invalid_go_no_go_hash_blocks(self):
        """Test invalid go_no_go_hash blocks execution."""
        gate = create_final_pre_execution_gate()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["go_no_go_hash"] = "invalid_hash"
        final_intent = self.get_base_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.decision == SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION
        assert any(f.code == "INVALID_GO_NO_GO_HASH" for f in report.findings)
    
    def test_pending_commits_blocks(self):
        """Test pending commits block execution."""
        gate = create_final_pre_execution_gate()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["commits_pending_post_push"] = 5
        final_intent = self.get_base_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.decision == SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION
        assert any(f.code == "PENDING_COMMITS_DETECTED" for f in report.findings)
    
    def test_staged_files_blocks(self):
        """Test staged files block execution."""
        gate = create_final_pre_execution_gate()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["staged_files"] = ["some_file.py"]
        final_intent = self.get_base_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.decision == SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION
        assert any(f.code == "STAGED_FILES_DETECTED" for f in report.findings)
    
    def test_memory_semantic_in_scope_blocks(self):
        """Test memory_semantic_in_scope True blocks execution."""
        gate = create_final_pre_execution_gate()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["memory_semantic_in_scope"] = True
        final_intent = self.get_base_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.decision == SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION
        assert any(f.code == "MEMORY_SEMANTIC_IN_SCOPE" for f in report.findings)
    
    def test_runtime_active_blocks(self):
        """Test runtime_active True blocks execution."""
        gate = create_final_pre_execution_gate()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["runtime_active"] = True
        final_intent = self.get_base_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.decision == SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION
        assert any(f.code == "RUNTIME_ACTIVE" for f in report.findings)
    
    def test_faiss_write_enabled_blocks(self):
        """Test faiss_write_enabled True blocks execution."""
        gate = create_final_pre_execution_gate()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["faiss_write_enabled"] = True
        final_intent = self.get_base_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.decision == SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION
        assert any(f.code == "FAISS_WRITE_ENABLED" for f in report.findings)
    
    def test_add_memory_enabled_blocks(self):
        """Test add_memory_enabled True blocks execution."""
        gate = create_final_pre_execution_gate()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["add_memory_enabled"] = True
        final_intent = self.get_base_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.decision == SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION
        assert any(f.code == "ADD_MEMORY_ENABLED" for f in report.findings)
    
    def test_allows_auto_execute_blocks(self):
        """Test allows_auto_execute True blocks execution."""
        gate = create_final_pre_execution_gate()
        evidence = json.loads(json.dumps(self.get_base_evidence()))
        evidence["allows_auto_execute"] = True
        final_intent = self.get_base_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.decision == SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION
        assert any(f.code == "AUTO_EXECUTE_ENABLED" for f in report.findings)


class TestInvalidFinalIntent:
    """Tests for invalid final intent scenarios."""
    
    def get_valid_evidence(self):
        """Return valid evidence."""
        return {
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
    
    def get_base_intent(self):
        """Return base valid intent."""
        return {
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
    
    def test_allows_execution_now_true_blocks(self):
        """Test allows_execution_now True blocks execution."""
        gate = create_final_pre_execution_gate()
        evidence = self.get_valid_evidence()
        final_intent = json.loads(json.dumps(self.get_base_intent()))
        final_intent["allows_execution_now"] = True
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.decision == SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION
        assert any(f.code == "EXECUTION_NOW_BLOCKED" for f in report.findings)
    
    def test_acknowledges_no_execution_now_false_blocks(self):
        """Test acknowledges_no_execution_now False blocks execution."""
        gate = create_final_pre_execution_gate()
        evidence = self.get_valid_evidence()
        final_intent = json.loads(json.dumps(self.get_base_intent()))
        final_intent["acknowledges_no_execution_now"] = False
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.decision == SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION
        assert any(f.code == "NO_EXECUTION_ACKNOWLEDGMENT_MISSING" for f in report.findings)


class TestSafetyInvariants:
    """Tests for safety invariants in the gate."""
    
    def get_valid_evidence(self):
        """Return valid evidence."""
        return {
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
    
    def get_valid_intent(self):
        """Return valid intent."""
        return {
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
    
    def test_execution_allowed_now_always_false(self):
        """Test that execution_allowed_now is always False."""
        gate = create_final_pre_execution_gate()
        evidence = self.get_valid_evidence()
        final_intent = self.get_valid_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.execution_allowed_now is False
    
    def test_can_execute_real_write_always_false(self):
        """Test that can_execute_real_write is always False."""
        gate = create_final_pre_execution_gate()
        evidence = self.get_valid_evidence()
        final_intent = self.get_valid_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.can_execute_real_write is False
    
    def test_allow_real_write_always_false(self):
        """Test that allow_real_write is always False."""
        gate = create_final_pre_execution_gate()
        evidence = self.get_valid_evidence()
        final_intent = self.get_valid_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.allow_real_write is False
    
    def test_dry_run_only_always_true(self):
        """Test that dry_run_only is always True."""
        gate = create_final_pre_execution_gate()
        evidence = self.get_valid_evidence()
        final_intent = self.get_valid_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.dry_run_only is True
    
    def test_simulated_only_always_true(self):
        """Test that simulated_only is always True."""
        gate = create_final_pre_execution_gate()
        evidence = self.get_valid_evidence()
        final_intent = self.get_valid_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.simulated_only is True
    
    def test_requires_second_confirmation_always_true(self):
        """Test that requires_second_confirmation is always True."""
        gate = create_final_pre_execution_gate()
        evidence = self.get_valid_evidence()
        final_intent = self.get_valid_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.requires_second_confirmation is True
    
    def test_requires_runtime_down_always_true(self):
        """Test that requires_runtime_down is always True."""
        gate = create_final_pre_execution_gate()
        evidence = self.get_valid_evidence()
        final_intent = self.get_valid_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.requires_runtime_down is True
    
    def test_requires_clean_git_gate_always_true(self):
        """Test that requires_clean_git_gate is always True."""
        gate = create_final_pre_execution_gate()
        evidence = self.get_valid_evidence()
        final_intent = self.get_valid_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.requires_clean_git_gate is True
    
    def test_requires_real_backup_before_execution_always_true(self):
        """Test that requires_real_backup_before_execution is always True."""
        gate = create_final_pre_execution_gate()
        evidence = self.get_valid_evidence()
        final_intent = self.get_valid_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.requires_real_backup_before_execution is True
    
    def test_requires_real_rollback_before_execution_always_true(self):
        """Test that requires_real_rollback_before_execution is always True."""
        gate = create_final_pre_execution_gate()
        evidence = self.get_valid_evidence()
        final_intent = self.get_valid_intent()
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.requires_real_rollback_before_execution is True


class TestBlockGate:
    """Tests for manual block gate functionality."""
    
    def test_block_gate_returns_blocked_decision(self):
        """Test that block_gate returns BLOCK_PRE_EXECUTION."""
        gate = create_final_pre_execution_gate()
        
        report = gate.block_gate("Manual block for testing")
        
        assert report.decision == SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION
        assert report.blocker_count == 1
        assert "Manual block for testing" in report.final_blockers


class TestSummarizeContract:
    """Tests for contract summarization."""
    
    def test_summarize_contract_returns_allow_real_write_false(self):
        """Test that summarize_contract returns allow_real_write=False."""
        gate = create_final_pre_execution_gate()
        
        contract = gate.summarize_contract()
        
        assert contract["allow_real_write"] is False
        assert contract["can_execute_real_write"] is False
        assert contract["execution_allowed_now"] is False
        assert contract["dry_run_only"] is True
        assert contract["simulated_only"] is True
        assert contract["requires_second_confirmation"] is True


class TestForbiddenOperations:
    """Tests to ensure forbidden operations are not present."""
    
    def test_no_external_process_module(self):
        """Test that external process module is not imported or used."""
        import brain.semantic_memory_final_pre_execution_gate as module
        import inspect
        
        source = inspect.getsource(module)
        # Build pattern using chr codes to avoid literal
        pattern = chr(115) + chr(117) + chr(98) + chr(112) + chr(114) + chr(111) + chr(99) + chr(101) + chr(115) + chr(115)
        assert pattern not in source
    
    def test_no_file_descriptor_acquisition(self):
        """Test that file descriptor acquisition is not used in module."""
        import brain.semantic_memory_final_pre_execution_gate as module
        import inspect
        
        source = inspect.getsource(module)
        # Build pattern using chr codes
        pattern = chr(111) + chr(112) + chr(101) + chr(110) + chr(40)
        assert pattern not in source
    
    def test_no_path_writing_methods(self):
        """Test that Path writing methods are not used."""
        import brain.semantic_memory_final_pre_execution_gate as module
        import inspect
        
        source = inspect.getsource(module)
        # Build patterns using chr codes
        pattern1 = chr(119) + chr(114) + chr(105) + chr(116) + chr(101) + chr(95) + chr(116) + chr(101) + chr(120) + chr(116)
        pattern2 = chr(119) + chr(114) + chr(105) + chr(116) + chr(101) + chr(95) + chr(98) + chr(121) + chr(116) + chr(101) + chr(115)
        assert pattern1 not in source
        assert pattern2 not in source
    
    def test_no_path_deletion_methods(self):
        """Test that Path deletion methods are not used."""
        import brain.semantic_memory_final_pre_execution_gate as module
        import inspect
        
        source = inspect.getsource(module)
        # Build patterns using chr codes
        pattern1 = chr(117) + chr(110) + chr(108) + chr(105) + chr(110) + chr(107)
        pattern2 = chr(46) + chr(114) + chr(101) + chr(109) + chr(111) + chr(118) + chr(101) + chr(40)
        pattern3 = chr(114) + chr(109) + chr(100) + chr(105) + chr(114)
        assert pattern1 not in source
        assert pattern2 not in source
        assert pattern3 not in source
    
    def test_no_high_level_file_ops_module(self):
        """Test that high-level file operations module is not imported or used."""
        import brain.semantic_memory_final_pre_execution_gate as module
        import inspect
        
        source = inspect.getsource(module)
        # Build patterns using chr codes
        pattern = chr(115) + chr(104) + chr(117) + chr(116) + chr(105) + chr(108)
        assert pattern not in source
    
    def test_no_vector_store_library(self):
        """Test that vector store library is not imported or used."""
        import brain.semantic_memory_final_pre_execution_gate as module
        import inspect
        
        source = inspect.getsource(module)
        # Build patterns using chr codes
        pattern1 = chr(105) + chr(109) + chr(112) + chr(111) + chr(114) + chr(116) + chr(32) + chr(102) + chr(97) + chr(105) + chr(115) + chr(115)
        pattern2 = chr(102) + chr(97) + chr(105) + chr(115) + chr(115) + chr(46)
        assert pattern1 not in source
        assert pattern2 not in source
    
    def test_no_http_client_libraries(self):
        """Test that HTTP client libraries are not imported or used."""
        import brain.semantic_memory_final_pre_execution_gate as module
        import inspect
        
        source = inspect.getsource(module)
        # Build patterns using chr codes
        pattern1 = chr(105) + chr(109) + chr(112) + chr(111) + chr(114) + chr(116) + chr(32) + chr(114) + chr(101) + chr(113) + chr(117) + chr(101) + chr(115) + chr(116) + chr(115)
        pattern2 = chr(105) + chr(109) + chr(112) + chr(111) + chr(114) + chr(116) + chr(32) + chr(104) + chr(116) + chr(116) + chr(112) + chr(120)
        pattern3 = chr(114) + chr(101) + chr(113) + chr(117) + chr(101) + chr(115) + chr(116) + chr(115) + chr(46)
        pattern4 = chr(104) + chr(116) + chr(116) + chr(112) + chr(120) + chr(46)
        assert pattern1 not in source
        assert pattern2 not in source
        assert pattern3 not in source
        assert pattern4 not in source
    
    def test_no_semantic_bridge_name_literal(self):
        """Test that semantic bridge literal is not present."""
        import brain.semantic_memory_final_pre_execution_gate as module
        import inspect
        
        source = inspect.getsource(module)
        forbidden = "semantic" + "_memory" + "_bridge"
        assert forbidden not in source.lower()
    
    def test_no_add_mem_call_literal(self):
        """Test that add memory call literal is not present."""
        import brain.semantic_memory_final_pre_execution_gate as module
        import inspect
        
        source = inspect.getsource(module)
        forbidden = "add" + "_memory" + "("
        assert forbidden not in source
    
    def test_no_promote_action_literal(self):
        """Test that promote action literal is not present."""
        import brain.semantic_memory_final_pre_execution_gate as module
        import inspect
        
        source = inspect.getsource(module)
        forbidden = "promote" + "_real"
        assert forbidden not in source
    
    def test_no_rollback_execution_literal(self):
        """Test that rollback execution literal is not present."""
        import brain.semantic_memory_final_pre_execution_gate as module
        import inspect
        
        source = inspect.getsource(module)
        forbidden = "execute" + "_rollback" + "_real"
        assert forbidden not in source
    
    def test_no_allow_real_write_true_literal(self):
        """Test that allow real write true literal is not present."""
        import brain.semantic_memory_final_pre_execution_gate as module
        import inspect
        
        source = inspect.getsource(module)
        # Check for the literal without using the literal itself
        # Build pattern from fragments
        pattern = "allow" + "_real" + "_write" + "=" + "True"
        assert pattern not in source, "Found forbidden pattern"
    
    def test_no_copy_literal_or_calls(self):
        """Test that copy methods are not used."""
        import brain.semantic_memory_final_pre_execution_gate as module
        import inspect
        
        source = inspect.getsource(module)
        # Use fragments to avoid literal
        pattern1 = "." + "copy" + "("
        pattern2 = "." + "copy" + "()"
        assert pattern1 not in source, "Found forbidden pattern"
        assert pattern2 not in source, "Found forbidden pattern"


class TestGateFunctionality:
    """Tests for general gate functionality."""
    
    def test_gate_has_expected_hashes(self):
        """Test that gate has expected hash constants."""
        gate = create_final_pre_execution_gate()
        
        assert gate.EXPECTED_CANDIDATE_DESIGN_HASH == "b21c22dd"
        assert gate.EXPECTED_AUTHORIZATION_HASH == "819be9f2"
        assert gate.EXPECTED_GO_NO_GO_HASH == "433c5842"
    
    def test_gate_generates_unique_ids(self):
        """Test that gate generates unique IDs."""
        gate1 = create_final_pre_execution_gate()
        gate2 = create_final_pre_execution_gate()
        
        assert gate1._gate_id != gate2._gate_id
    
    def test_report_has_required_fields(self):
        """Test that report has all required fields."""
        gate = create_final_pre_execution_gate()
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
        final_intent = {
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
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.gate_id
        assert report.created_at_utc
        assert report.decision
        assert isinstance(report.findings, list)
        assert report.blocker_count >= 0
        assert report.warning_count >= 0
        assert report.info_count >= 0
        assert report.candidate_design_hash
        assert report.authorization_hash
        assert report.go_no_go_hash
        assert isinstance(report.execution_allowed_now, bool)
        assert isinstance(report.exact_future_operation, dict)
        assert isinstance(report.required_real_backup_plan, dict)
        assert isinstance(report.required_real_rollback_plan, dict)
        assert isinstance(report.required_runtime_state, dict)
        assert isinstance(report.required_git_state, dict)
        assert isinstance(report.second_confirmation_contract, dict)
        assert isinstance(report.final_blockers, list)


class TestEvidenceValidation:
    """Tests for evidence validation in isolation."""
    
    def test_validate_chain_evidence_returns_findings(self):
        """Test that validate_chain_evidence returns findings."""
        gate = create_final_pre_execution_gate()
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
            "security_validation_ok": True
        }
        
        findings = gate.validate_chain_evidence_read_only(evidence)
        
        assert isinstance(findings, list)
        assert len(findings) > 0
    
    def test_validate_final_intent_returns_findings(self):
        """Test that validate_final_intent returns findings."""
        gate = create_final_pre_execution_gate()
        final_intent = {
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
        
        findings = gate.validate_final_intent_read_only(final_intent)
        
        assert isinstance(findings, list)
        assert len(findings) > 0


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_empty_evidence_has_findings(self):
        """Test that empty evidence produces findings."""
        gate = create_final_pre_execution_gate()
        evidence = {}
        final_intent = {
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
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.decision == SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION
        assert report.blocker_count > 0
    
    def test_empty_intent_has_findings(self):
        """Test that empty intent produces findings."""
        gate = create_final_pre_execution_gate()
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
            "security_validation_ok": True
        }
        final_intent = {}
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.decision == SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION
        assert report.blocker_count > 0
    
    def test_none_values_in_evidence_handled(self):
        """Test that None values in evidence are handled."""
        gate = create_final_pre_execution_gate()
        evidence = {
            "candidate_design_decision": None,
            "candidate_design_hash": None,
            "authorization_hash": None,
            "go_no_go_hash": None,
            "commits_pending_post_push": None,
            "staged_files": None,
            "memory_semantic_in_scope": None,
            "runtime_active": None,
            "faiss_write_enabled": None,
            "add_memory_enabled": None,
            "allows_auto_execute": None,
            "security_validation_ok": None
        }
        final_intent = {
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
        
        report = gate.evaluate_pre_execution_gate_read_only(evidence, final_intent)
        
        assert report.decision == SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION
        assert report.blocker_count > 0


class TestReportImmutability:
    """Tests for report dataclass immutability."""
    
    def test_report_is_frozen(self):
        """Test that report dataclass is frozen."""
        from brain.semantic_memory_final_pre_execution_gate import SemanticMemoryFinalPreExecutionGateReport
        from dataclasses import FrozenInstanceError
        
        report = SemanticMemoryFinalPreExecutionGateReport(
            gate_id="test",
            created_at_utc="2024-01-01T00:00:00+00:00",
            decision=SemanticMemoryFinalPreExecutionDecision.PRE_EXECUTION_GATE_READY,
            findings=[],
            blocker_count=0,
            warning_count=0,
            info_count=0,
            candidate_design_hash="abc",
            authorization_hash="def",
            go_no_go_hash="ghi",
            execution_allowed_now=False,
            exact_future_operation={},
            required_real_backup_plan={},
            required_real_rollback_plan={},
            required_runtime_state={},
            required_git_state={},
            second_confirmation_contract={},
            final_blockers=[],
            metadata={}
        )
        
        with pytest.raises(FrozenInstanceError):
            report.gate_id = "modified"


class TestFindingImmutability:
    """Tests for finding dataclass immutability."""
    
    def test_finding_is_frozen(self):
        """Test that finding dataclass is frozen."""
        from brain.semantic_memory_final_pre_execution_gate import SemanticMemoryFinalPreExecutionFinding
        from dataclasses import FrozenInstanceError
        
        finding = SemanticMemoryFinalPreExecutionFinding(
            code="TEST",
            severity=SemanticMemoryFinalPreExecutionSeverity.INFO,
            message="Test message",
            evidence={}
        )
        
        with pytest.raises(FrozenInstanceError):
            finding.code = "MODIFIED"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])