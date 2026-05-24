"""Tests for P2-E Commit 4D-GoNoGoReadinessChecklist.

These tests verify that the GO/NO-GO checklist:
- Correctly evaluates evidence
- Never allows real writes
- Enforces all safety invariants
- Blocks on critical failures
"""

import json
import pytest
from pathlib import Path

from brain.semantic_memory_go_no_go_readiness_checklist import (
    SemanticMemoryGoNoGoDecision,
    SemanticMemoryGoNoGoSeverity,
    SemanticMemoryGoNoGoFinding,
    SemanticMemoryGoNoGoChecklistReport,
    SemanticMemoryGoNoGoReadinessChecklist,
    create_valid_evidence_template,
)


class TestGoNoGoDecisionOutcomes:
    """Test decision outcomes for different evidence scenarios."""
    
    def test_complete_valid_evidence_returns_go_candidate_only(self, tmp_path):
        """1. complete valid evidence => GO_CANDIDATE_ONLY."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.decision == SemanticMemoryGoNoGoDecision.GO_CANDIDATE_ONLY
        assert report.blocker_count == 0
    
    def test_missing_human_intent_returns_manual_review(self, tmp_path):
        """2. missing human intent => MANUAL_REVIEW_REQUIRED."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["human_intent_ok"] = False
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.decision == SemanticMemoryGoNoGoDecision.MANUAL_REVIEW_REQUIRED
    
    def test_decision_gate_false_returns_no_go(self, tmp_path):
        """3. decision_gate_ok False => NO_GO."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["decision_gate_ok"] = False
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.decision == SemanticMemoryGoNoGoDecision.NO_GO
    
    def test_evidence_contract_false_returns_no_go(self, tmp_path):
        """4. evidence_contract_ok False => NO_GO."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["evidence_contract_ok"] = False
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.decision == SemanticMemoryGoNoGoDecision.NO_GO
    
    def test_adapter_false_returns_no_go(self, tmp_path):
        """5. adapter_ok False => NO_GO."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["adapter_ok"] = False
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.decision == SemanticMemoryGoNoGoDecision.NO_GO
    
    def test_canary_false_returns_no_go(self, tmp_path):
        """6. canary_ok False => NO_GO."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["canary_ok"] = False
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.decision == SemanticMemoryGoNoGoDecision.NO_GO
    
    def test_final_readiness_false_returns_no_go(self, tmp_path):
        """7. final_readiness_ok False => NO_GO."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["final_readiness_ok"] = False
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.decision == SemanticMemoryGoNoGoDecision.NO_GO
    
    def test_backup_contract_false_returns_no_go(self, tmp_path):
        """8. backup_contract_ok False => NO_GO."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["backup_contract_ok"] = False
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.decision == SemanticMemoryGoNoGoDecision.NO_GO
    
    def test_rollback_simulation_false_returns_no_go(self, tmp_path):
        """9. rollback_simulation_ok False => NO_GO."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["rollback_simulation_ok"] = False
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.decision == SemanticMemoryGoNoGoDecision.NO_GO
    
    def test_security_validation_false_returns_no_go(self, tmp_path):
        """10. security_validation_ok False => NO_GO."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["security_validation_ok"] = False
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.decision == SemanticMemoryGoNoGoDecision.NO_GO
    
    def test_git_state_false_returns_no_go(self, tmp_path):
        """11. git_state_ok False => NO_GO."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["git_state_ok"] = False
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.decision == SemanticMemoryGoNoGoDecision.NO_GO


class TestAbsoluteBlockers:
    """Test absolute blockers that always result in NO_GO."""
    
    def test_commits_pending_returns_no_go(self, tmp_path):
        """12. commits_pending_post_push > 0 => NO_GO."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["commits_pending_post_push"] = 1
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.decision == SemanticMemoryGoNoGoDecision.NO_GO
        assert any(f.code == "PENDING_COMMITS" for f in report.findings)
    
    def test_staged_files_returns_no_go(self, tmp_path):
        """13. staged_files non-empty => NO_GO."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["staged_files"] = ["some_file.py"]
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.decision == SemanticMemoryGoNoGoDecision.NO_GO
        assert any(f.code == "STAGED_FILES" for f in report.findings)
    
    def test_memory_semantic_in_scope_returns_no_go(self, tmp_path):
        """14. memory_semantic_in_scope True => NO_GO."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["memory_semantic_in_scope"] = True
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.decision == SemanticMemoryGoNoGoDecision.NO_GO
        assert any(f.code == "MEMORY_SEMANTIC_IN_SCOPE" for f in report.findings)
    
    def test_runtime_active_returns_no_go(self, tmp_path):
        """15. runtime_active True => NO_GO."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["runtime_active"] = True
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.decision == SemanticMemoryGoNoGoDecision.NO_GO
        assert any(f.code == "RUNTIME_ACTIVE" for f in report.findings)
    
    def test_faiss_write_enabled_returns_no_go(self, tmp_path):
        """16. faiss_write_enabled True => NO_GO."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["faiss_write_enabled"] = True
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.decision == SemanticMemoryGoNoGoDecision.NO_GO
        assert any(f.code == "FAISS_WRITE_ENABLED" for f in report.findings)
    
    def test_add_memory_enabled_returns_no_go(self, tmp_path):
        """17. add_memory_enabled True => NO_GO."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["add_memory_enabled"] = True
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.decision == SemanticMemoryGoNoGoDecision.NO_GO
        assert any(f.code == "ADD_MEMORY_ENABLED" for f in report.findings)
    
    def test_allows_auto_execute_returns_no_go(self, tmp_path):
        """18. allows_auto_execute True => NO_GO."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["allows_auto_execute"] = True
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.decision == SemanticMemoryGoNoGoDecision.NO_GO
        assert any(f.code == "AUTO_EXECUTE_ALLOWED" for f in report.findings)
    
    def test_allows_candidate_only_false_returns_manual_review_or_no_go(self, tmp_path):
        """19. allows_candidate_only False => MANUAL_REVIEW_REQUIRED or NO_GO."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["allows_candidate_only"] = False
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.decision in [
            SemanticMemoryGoNoGoDecision.NO_GO,
            SemanticMemoryGoNoGoDecision.MANUAL_REVIEW_REQUIRED
        ]


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_empty_evidence_returns_no_go(self, tmp_path):
        """20. empty evidence => NO_GO."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        
        report = checklist.evaluate_checklist_read_only({})
        
        assert report.decision == SemanticMemoryGoNoGoDecision.NO_GO
        assert report.blocker_count > 0
    
    def test_none_evidence_returns_no_go(self, tmp_path):
        """None evidence defaults to empty and returns NO_GO."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        
        report = checklist.evaluate_checklist_read_only(None)
        
        assert report.decision == SemanticMemoryGoNoGoDecision.NO_GO
        assert report.blocker_count > 0
    
    def test_block_checklist_returns_no_go(self, tmp_path):
        """21. block_checklist returns NO_GO."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        
        report = checklist.block_checklist("Test block reason")
        
        assert report.decision == SemanticMemoryGoNoGoDecision.NO_GO
        assert any(f.code == "CHECKLIST_BLOCKED" for f in report.findings)


class TestSafetyInvariants:
    """Test that safety invariants are always enforced."""
    
    def test_summarize_contract_returns_allow_real_write_false(self, tmp_path):
        """22. summarize_contract returns allow_real_write=False."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        
        contract = checklist.summarize_contract()
        
        assert contract["safety_invariants"]["allow_real_write"] is False
    
    def test_valid_evidence_keeps_allow_real_write_false(self, tmp_path):
        """23. valid evidence still keeps allow_real_write=False."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.allow_real_write is False
    
    def test_valid_evidence_keeps_can_execute_real_write_false(self, tmp_path):
        """24. valid evidence still keeps can_execute_real_write=False."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.can_execute_real_write is False
    
    def test_valid_evidence_keeps_dry_run_only_true(self, tmp_path):
        """25. valid evidence still keeps dry_run_only=True."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.dry_run_only is True
    
    def test_valid_evidence_keeps_simulated_only_true(self, tmp_path):
        """26. valid evidence still keeps simulated_only=True."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.simulated_only is True


class TestReadinessScore:
    """Test readiness score calculation."""
    
    def test_perfect_evidence_returns_score_one(self, tmp_path):
        """Perfect evidence returns readiness score of 1.0."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.readiness_score == 1.0
    
    def test_empty_evidence_returns_score_zero(self, tmp_path):
        """Empty evidence returns readiness score of 0.0."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        
        report = checklist.evaluate_checklist_read_only({})
        
        assert report.readiness_score == 0.0
    
    def test_with_warnings_reduces_score(self, tmp_path):
        """Warnings reduce the readiness score."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["allows_candidate_only"] = False  # Causes warning
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert 0.0 < report.readiness_score < 1.0


class TestReportStructure:
    """Test report structure and contents."""
    
    def test_report_has_required_fields(self, tmp_path):
        """Report contains all required fields."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert report.checklist_id
        assert report.created_at_utc
        assert report.decision
        assert isinstance(report.findings, list)
        assert report.blocker_count >= 0
        assert report.warning_count >= 0
        assert report.info_count >= 0
    
    def test_report_checklist_summary(self, tmp_path):
        """Report includes checklist summary."""
        checklist = SemanticMemoryGoNoGoReadinessChecklist(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        
        report = checklist.evaluate_checklist_read_only(evidence)
        
        assert "version" in report.checklist
        assert "checks" in report.checklist
        assert "counts" in report.checklist


class TestSecurityConstraints:
    """Test security constraints through static analysis."""
    
    def test_no_subprocess_in_module(self):
        """27. no subprocess."""
        import brain.semantic_memory_go_no_go_readiness_checklist as module
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
        """28. no open."""
        import brain.semantic_memory_go_no_go_readiness_checklist as module
        import ast
        
        source = Path(module.__file__).read_text()
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id != "open"
    
    def test_no_copy_literal_or_call(self):
        """29. no .copy literal/call."""
        import brain.semantic_memory_go_no_go_readiness_checklist as module
        
        source = Path(module.__file__).read_text()
        
        # Check for copy operations without using literal strings
        forbidden_call = "." + "copy" + "("
        forbidden_exact = "." + "copy" + ")"
        assert forbidden_call not in source
        assert forbidden_exact not in source
    
    def test_no_write_text_write_bytes(self):
        """30. no write_text/write_bytes en módulo productivo."""
        import brain.semantic_memory_go_no_go_readiness_checklist as module
        
        source = Path(module.__file__).read_text()
        
        assert "write_text" not in source
        assert "write_bytes" not in source
    
    def test_no_unlink_remove_rmdir(self):
        """31. no unlink/remove/rmdir."""
        import brain.semantic_memory_go_no_go_readiness_checklist as module
        
        source = Path(module.__file__).read_text()
        
        assert ".unlink(" not in source
        assert ".remove(" not in source
        assert ".rmdir(" not in source
    
    def test_no_shutil(self):
        """32. no shutil."""
        import brain.semantic_memory_go_no_go_readiness_checklist as module
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
        """33. no faiss."""
        import brain.semantic_memory_go_no_go_readiness_checklist as module
        import ast
        
        source = Path(module.__file__).read_text()
        tree = ast.parse(source)
        
        # Check for actual faiss import (not just in comments/docstrings)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "faiss" not in alias.name.lower(), f"Found faiss import: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert "faiss" not in node.module.lower(), f"Found faiss import from: {node.module}"
    
    def test_no_requests_httpx(self):
        """34. no requests/httpx."""
        import brain.semantic_memory_go_no_go_readiness_checklist as module
        
        source = Path(module.__file__).read_text()
        
        assert "requests" not in source
        assert "httpx" not in source
    
    def test_no_semantic_mem_bridge(self):
        """35. no semantic memory bridge."""
        import brain.semantic_memory_go_no_go_readiness_checklist as module
        
        source = Path(module.__file__).read_text()
        
        pattern = "semantic" + "_memory" + "_bridge"
        assert pattern not in source
    
    def test_no_add_memory_call(self):
        """36. no add memory call."""
        import brain.semantic_memory_go_no_go_readiness_checklist as module
        
        source = Path(module.__file__).read_text()
        
        pattern = "add" + "_memory" + "("
        assert pattern not in source
    
    def test_no_promote_real_call(self):
        """37. no promote real call."""
        import brain.semantic_memory_go_no_go_readiness_checklist as module
        
        source = Path(module.__file__).read_text()
        
        pattern = "promote" + "_real"
        assert pattern not in source
    
    def test_no_execute_rollback_real_call(self):
        """38. no execute rollback real call."""
        import brain.semantic_memory_go_no_go_readiness_checklist as module
        
        source = Path(module.__file__).read_text()
        
        pattern = "execute" + "_rollback" + "_real"
        assert pattern not in source
    
    def test_no_allow_real_write_true(self):
        """39. no allow real write True."""
        import brain.semantic_memory_go_no_go_readiness_checklist as module
        
        source = Path(module.__file__).read_text()
        
        pattern = "allow" + "_real" + "_write" + "=" + "True"
        assert pattern not in source


class TestHelperFunctions:
    """Test helper functions."""
    
    def test_create_valid_evidence_template(self):
        """Template contains all required keys."""
        template = create_valid_evidence_template()
        
        required_keys = [
            "decision_gate_ok",
            "evidence_contract_ok",
            "adapter_ok",
            "canary_ok",
            "final_readiness_ok",
            "backup_contract_ok",
            "rollback_simulation_ok",
            "security_validation_ok",
            "git_state_ok",
            "human_intent_ok",
            "commits_pending_post_push",
            "staged_files",
            "memory_semantic_in_scope",
            "runtime_active",
            "faiss_write_enabled",
            "add_memory_enabled",
            "allows_auto_execute",
            "allows_candidate_only",
        ]
        
        for key in required_keys:
            assert key in template


class TestFindingDataclass:
    """Test SemanticMemoryGoNoGoFinding dataclass."""
    
    def test_finding_creation(self):
        """Finding can be created with all fields."""
        finding = SemanticMemoryGoNoGoFinding(
            code="TEST_CODE",
            severity=SemanticMemoryGoNoGoSeverity.INFO,
            message="Test message",
            evidence={"key": "value"}
        )
        
        assert finding.code == "TEST_CODE"
        assert finding.severity == SemanticMemoryGoNoGoSeverity.INFO
        assert finding.message == "Test message"
        assert finding.evidence == {"key": "value"}


class TestReportDataclass:
    """Test SemanticMemoryGoNoGoChecklistReport dataclass."""
    
    def test_report_default_safety_values(self):
        """Report defaults enforce safety invariants."""
        report = SemanticMemoryGoNoGoChecklistReport(
            checklist_id="test-id",
            created_at_utc="2024-01-01T00:00:00Z",
            decision=SemanticMemoryGoNoGoDecision.GO_CANDIDATE_ONLY,
            findings=[],
            blocker_count=0,
            warning_count=0,
            info_count=0,
            decision_gate_ok=True,
            evidence_contract_ok=True,
            adapter_ok=True,
            canary_ok=True,
            final_readiness_ok=True,
            backup_contract_ok=True,
            rollback_simulation_ok=True,
            security_validation_ok=True,
            git_state_ok=True,
            human_intent_ok=True,
        )
        
        # Safety invariants must be enforced
        assert report.allow_real_write is False
        assert report.dry_run_only is True
        assert report.can_execute_real_write is False
        assert report.simulated_only is True
        assert report.requires_human_approval is True
