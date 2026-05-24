"""Tests for P2-E Commit 4D-ControlledRealWriteCandidateDesign.

These tests verify that the candidate design:
- Correctly validates evidence and candidate request
- Never allows real writes
- Enforces all safety invariants
- Blocks on critical failures
"""

import json
import pytest
from pathlib import Path

from brain.semantic_memory_controlled_real_write_candidate_design import (
    SemanticMemoryCandidateDesignDecision,
    SemanticMemoryCandidateDesignSeverity,
    SemanticMemoryCandidateDesignFinding,
    SemanticMemoryControlledRealWriteCandidateDesignReport,
    SemanticMemoryControlledRealWriteCandidateDesign,
    create_valid_evidence_template,
    create_valid_candidate_request_template,
)


class TestCandidateDesignDecisions:
    """Test decision outcomes for different scenarios."""
    
    def test_valid_evidence_and_request_returns_ready(self, tmp_path):
        """1. valid evidence + valid request => CANDIDATE_DESIGN_READY."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        request = create_valid_candidate_request_template()
        
        report = design.build_candidate_design_read_only(evidence, request)
        
        assert report.decision == SemanticMemoryCandidateDesignDecision.CANDIDATE_DESIGN_READY
        assert report.blocker_count == 0
    
    def test_valid_evidence_missing_request_returns_manual_review(self, tmp_path):
        """2. valid evidence + missing request => MANUAL_REVIEW_REQUIRED."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        
        report = design.build_candidate_design_read_only(evidence, None)
        
        assert report.decision == SemanticMemoryCandidateDesignDecision.MANUAL_REVIEW_REQUIRED
    
    def test_invalid_authorization_decision_returns_block(self, tmp_path):
        """3. authorization_decision invalid => BLOCK_CANDIDATE_DESIGN."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["authorization_decision"] = "BLOCK_AUTHORIZATION"
        request = create_valid_candidate_request_template()
        
        report = design.build_candidate_design_read_only(evidence, request)
        
        assert report.decision == SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
    
    def test_invalid_authorization_hash_returns_block(self, tmp_path):
        """4. authorization_hash invalid => BLOCK_CANDIDATE_DESIGN."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["authorization_hash"] = "invalid_hash"
        request = create_valid_candidate_request_template()
        
        report = design.build_candidate_design_read_only(evidence, request)
        
        assert report.decision == SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
    
    def test_commits_pending_returns_block(self, tmp_path):
        """5. commits_pending_post_push > 0 => BLOCK_CANDIDATE_DESIGN."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["commits_pending_post_push"] = 1
        request = create_valid_candidate_request_template()
        
        report = design.build_candidate_design_read_only(evidence, request)
        
        assert report.decision == SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
    
    def test_staged_files_returns_block(self, tmp_path):
        """6. staged_files non-empty => BLOCK_CANDIDATE_DESIGN."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["staged_files"] = ["test.py"]
        request = create_valid_candidate_request_template()
        
        report = design.build_candidate_design_read_only(evidence, request)
        
        assert report.decision == SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
    
    def test_memory_semantic_in_scope_returns_block(self, tmp_path):
        """7. memory_semantic_in_scope True => BLOCK_CANDIDATE_DESIGN."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["memory_semantic_in_scope"] = True
        request = create_valid_candidate_request_template()
        
        report = design.build_candidate_design_read_only(evidence, request)
        
        assert report.decision == SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
    
    def test_runtime_active_returns_block(self, tmp_path):
        """8. runtime_active True => BLOCK_CANDIDATE_DESIGN."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["runtime_active"] = True
        request = create_valid_candidate_request_template()
        
        report = design.build_candidate_design_read_only(evidence, request)
        
        assert report.decision == SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
    
    def test_faiss_write_enabled_returns_block(self, tmp_path):
        """9. faiss_write_enabled True => BLOCK_CANDIDATE_DESIGN."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["faiss_write_enabled"] = True
        request = create_valid_candidate_request_template()
        
        report = design.build_candidate_design_read_only(evidence, request)
        
        assert report.decision == SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
    
    def test_add_memory_enabled_returns_block(self, tmp_path):
        """10. add_memory_enabled True => BLOCK_CANDIDATE_DESIGN."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["add_memory_enabled"] = True
        request = create_valid_candidate_request_template()
        
        report = design.build_candidate_design_read_only(evidence, request)
        
        assert report.decision == SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
    
    def test_allows_auto_execute_returns_block(self, tmp_path):
        """11. allows_auto_execute True => BLOCK_CANDIDATE_DESIGN."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["allows_auto_execute"] = True
        request = create_valid_candidate_request_template()
        
        report = design.build_candidate_design_read_only(evidence, request)
        
        assert report.decision == SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
    
    def test_operation_mode_not_design_only_returns_block(self, tmp_path):
        """12. operation_mode not design_only => BLOCK_CANDIDATE_DESIGN."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        request = create_valid_candidate_request_template()
        request["operation_mode"] = "execute"
        
        report = design.build_candidate_design_read_only(evidence, request)
        
        assert report.decision == SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
    
    def test_expects_no_write_false_returns_block(self, tmp_path):
        """13. expects_no_write False => BLOCK_CANDIDATE_DESIGN."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        request = create_valid_candidate_request_template()
        request["expects_no_write"] = False
        
        report = design.build_candidate_design_read_only(evidence, request)
        
        assert report.decision == SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN


class TestSafetyInvariants:
    """Test that safety invariants are always enforced."""
    
    def test_valid_design_keeps_can_execute_real_write_false(self, tmp_path):
        """14. valid design keeps can_execute_real_write=False."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        request = create_valid_candidate_request_template()
        
        report = design.build_candidate_design_read_only(evidence, request)
        
        assert report.can_execute_real_write is False
    
    def test_valid_design_keeps_allow_real_write_false(self, tmp_path):
        """15. valid design keeps allow_real_write=False."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        request = create_valid_candidate_request_template()
        
        report = design.build_candidate_design_read_only(evidence, request)
        
        assert report.allow_real_write is False
    
    def test_valid_design_keeps_dry_run_only_true(self, tmp_path):
        """16. valid design keeps dry_run_only=True."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        request = create_valid_candidate_request_template()
        
        report = design.build_candidate_design_read_only(evidence, request)
        
        assert report.dry_run_only is True
    
    def test_valid_design_keeps_simulated_only_true(self, tmp_path):
        """17. valid design keeps simulated_only=True."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        request = create_valid_candidate_request_template()
        
        report = design.build_candidate_design_read_only(evidence, request)
        
        assert report.simulated_only is True
    
    def test_valid_design_requires_second_confirmation_true(self, tmp_path):
        """18. valid design requires_second_confirmation=True."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        request = create_valid_candidate_request_template()
        
        report = design.build_candidate_design_read_only(evidence, request)
        
        assert report.requires_second_confirmation is True
    
    def test_valid_design_requires_runtime_down_true(self, tmp_path):
        """19. valid design requires_runtime_down=True."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        request = create_valid_candidate_request_template()
        
        report = design.build_candidate_design_read_only(evidence, request)
        
        assert report.requires_runtime_down is True
    
    def test_valid_design_requires_clean_git_gate_true(self, tmp_path):
        """20. valid design requires_clean_git_gate=True."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        request = create_valid_candidate_request_template()
        
        report = design.build_candidate_design_read_only(evidence, request)
        
        assert report.requires_clean_git_gate is True
    
    def test_block_design_returns_block_candidate_design(self, tmp_path):
        """21. block_design returns BLOCK_CANDIDATE_DESIGN."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        
        report = design.block_design("Test block reason")
        
        assert report.decision == SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
        assert any(f.code == "DESIGN_BLOCKED" for f in report.findings)
    
    def test_summarize_contract_returns_allow_real_write_false(self, tmp_path):
        """22. summarize_contract returns allow_real_write=False."""
        design = SemanticMemoryControlledRealWriteCandidateDesign(repo_root=tmp_path)
        
        contract = design.summarize_contract()
        
        assert contract["safety_invariants"]["allow_real_write"] is False


class TestSecurityConstraints:
    """Test security constraints through static analysis."""
    
    def test_no_subprocess_in_module(self):
        """23. no subprocess."""
        import brain.semantic_memory_controlled_real_write_candidate_design as module
        import ast
        
        source = Path(module.__file__).read_text()
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "subprocess"
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "subprocess"
    
    def test_no_open_in_module(self):
        """24. no open."""
        import brain.semantic_memory_controlled_real_write_candidate_design as module
        import ast
        
        source = Path(module.__file__).read_text()
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id != "open"
    
    def test_no_copy_literal_or_call(self):
        """25. no copy literal/call."""
        import brain.semantic_memory_controlled_real_write_candidate_design as module
        
        source = Path(module.__file__).read_text()
        
        # Check for copy operations without using literal strings
        forbidden_call = "." + "copy" + "("
        forbidden_exact = "." + "copy" + ")"
        assert forbidden_call not in source
        assert forbidden_exact not in source
    
    def test_no_write_text_write_bytes(self):
        """26. no write_text/write_bytes."""
        import brain.semantic_memory_controlled_real_write_candidate_design as module
        
        source = Path(module.__file__).read_text()
        
        assert "write_text" not in source
        assert "write_bytes" not in source
    
    def test_no_unlink_remove_rmdir(self):
        """27. no unlink/remove/rmdir."""
        import brain.semantic_memory_controlled_real_write_candidate_design as module
        
        source = Path(module.__file__).read_text()
        
        assert ".unlink(" not in source
        assert ".remove(" not in source
        assert ".rmdir(" not in source
    
    def test_no_shutil(self):
        """28. no shutil."""
        import brain.semantic_memory_controlled_real_write_candidate_design as module
        import ast
        
        source = Path(module.__file__).read_text()
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "shutil"
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "shutil"
    
    def test_no_faiss(self):
        """29. no faiss import/object."""
        import brain.semantic_memory_controlled_real_write_candidate_design as module
        import ast
        
        source = Path(module.__file__).read_text()
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] != "faiss"
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] != "faiss"
            elif isinstance(node, ast.Name):
                assert node.id != "faiss"
    
    def test_no_requests_httpx(self):
        """30. no requests/httpx."""
        import brain.semantic_memory_controlled_real_write_candidate_design as module
        
        source = Path(module.__file__).read_text()
        
        assert "requests" not in source
        assert "httpx" not in source
    
    def test_no_semantic_mem_bridge_literal(self):
        """31. no semantic memory bridge literal."""
        import brain.semantic_memory_controlled_real_write_candidate_design as module
        
        source = Path(module.__file__).read_text()
        
        pattern = "semantic" + "_memory" + "_bridge"
        assert pattern not in source
    
    def test_no_add_mem_call_literal(self):
        """32. no add memory call literal."""
        import brain.semantic_memory_controlled_real_write_candidate_design as module
        
        source = Path(module.__file__).read_text()
        
        pattern = "add" + "_memory" + "("
        assert pattern not in source
    
    def test_no_promote_action_literal(self):
        """33. no promote real literal."""
        import brain.semantic_memory_controlled_real_write_candidate_design as module
        
        source = Path(module.__file__).read_text()
        
        pattern = "promote" + "_real"
        assert pattern not in source
    
    def test_no_rollback_execution_literal(self):
        """34. no execute rollback real literal."""
        import brain.semantic_memory_controlled_real_write_candidate_design as module
        
        source = Path(module.__file__).read_text()
        
        pattern = "execute" + "_rollback" + "_real"
        assert pattern not in source
    
    def test_no_allow_real_write_true_literal(self):
        """35. no allow real write true literal."""
        import brain.semantic_memory_controlled_real_write_candidate_design as module
        
        source = Path(module.__file__).read_text()
        
        pattern = "allow" + "_real" + "_write" + "=" + "True"
        assert pattern not in source


class TestHelperFunctions:
    """Test helper functions."""
    
    def test_create_valid_evidence_template(self):
        """Template contains all required keys."""
        template = create_valid_evidence_template()
        
        required_keys = [
            "authorization_decision",
            "authorization_hash",
            "go_no_go_hash",
            "commits_pending_post_push",
            "staged_files",
            "memory_semantic_in_scope",
            "runtime_active",
            "faiss_write_enabled",
            "add_memory_enabled",
            "allows_auto_execute",
        ]
        
        for key in required_keys:
            assert key in template
    
    def test_create_valid_candidate_request_template(self):
        """Template contains all required keys."""
        template = create_valid_candidate_request_template()
        
        required_keys = [
            "requested_by",
            "candidate_scope",
            "target_room",
            "candidate_fact_key",
            "candidate_fact_value",
            "operation_mode",
            "expects_no_runtime",
            "expects_no_write",
            "expects_second_confirmation",
        ]
        
        for key in required_keys:
            assert key in template


class TestFindingDataclass:
    """Test SemanticMemoryCandidateDesignFinding dataclass."""
    
    def test_finding_creation(self):
        """Finding can be created with all fields."""
        finding = SemanticMemoryCandidateDesignFinding(
            code="TEST_CODE",
            severity=SemanticMemoryCandidateDesignSeverity.INFO,
            message="Test message",
            evidence={"key": "value"}
        )
        
        assert finding.code == "TEST_CODE"
        assert finding.severity == SemanticMemoryCandidateDesignSeverity.INFO
        assert finding.message == "Test message"
        assert finding.evidence == {"key": "value"}


class TestReportDataclass:
    """Test SemanticMemoryControlledRealWriteCandidateDesignReport dataclass."""
    
    def test_report_default_safety_values(self):
        """Report defaults enforce safety invariants."""
        report = SemanticMemoryControlledRealWriteCandidateDesignReport(
            candidate_id="test-id",
            created_at_utc="2024-01-01T00:00:00Z",
            decision=SemanticMemoryCandidateDesignDecision.CANDIDATE_DESIGN_READY,
            findings=[],
            blocker_count=0,
            warning_count=0,
            info_count=0,
            authorization_hash="819be9f2",
            target_operation_type="test",
            scope={},
            candidate_payload={},
            expected_diff={},
            backup_plan={},
            rollback_plan={},
            preflight_checklist={},
            dry_run_verification={},
            second_confirmation={},
            hard_blockers=[],
        )
        
        # Safety invariants must be enforced
        assert report.can_execute_real_write is False
        assert report.allow_real_write is False
        assert report.dry_run_only is True
        assert report.simulated_only is True
        assert report.requires_second_confirmation is True
        assert report.requires_runtime_down is True
        assert report.requires_clean_git_gate is True
