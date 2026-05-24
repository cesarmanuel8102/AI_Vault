"""Tests for P2-E Commit 4D-RealWriteAuthorizationPacket.

These tests verify that the authorization packet:
- Correctly validates evidence and human intent
- Never allows real writes
- Enforces all safety invariants
- Blocks on critical failures
"""

import json
import pytest
from pathlib import Path

from brain.semantic_memory_real_write_authorization_packet import (
    SemanticMemoryAuthorizationDecision,
    SemanticMemoryAuthorizationSeverity,
    SemanticMemoryAuthorizationFinding,
    SemanticMemoryRealWriteAuthorizationPacketReport,
    SemanticMemoryRealWriteAuthorizationPacket,
    create_valid_evidence_template,
    create_valid_human_intent_template,
)


class TestAuthorizationPacketDecisions:
    """Test decision outcomes for different scenarios."""
    
    def test_valid_evidence_and_intent_returns_ready(self, tmp_path):
        """1. valid evidence + valid human intent => AUTHORIZATION_PACKET_READY."""
        packet = SemanticMemoryRealWriteAuthorizationPacket(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        intent = create_valid_human_intent_template()
        
        report = packet.build_packet_read_only(evidence, intent)
        
        assert report.decision == SemanticMemoryAuthorizationDecision.AUTHORIZATION_PACKET_READY
        assert report.blocker_count == 0
    
    def test_valid_evidence_missing_intent_returns_manual_review(self, tmp_path):
        """2. valid evidence + missing human intent => MANUAL_REVIEW_REQUIRED."""
        packet = SemanticMemoryRealWriteAuthorizationPacket(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        
        report = packet.build_packet_read_only(evidence, None)
        
        assert report.decision == SemanticMemoryAuthorizationDecision.MANUAL_REVIEW_REQUIRED
    
    def test_invalid_go_no_go_decision_returns_block(self, tmp_path):
        """3. go_no_go_decision != GO_CANDIDATE_ONLY => BLOCK_AUTHORIZATION."""
        packet = SemanticMemoryRealWriteAuthorizationPacket(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["go_no_go_decision"] = "NO_GO"
        intent = create_valid_human_intent_template()
        
        report = packet.build_packet_read_only(evidence, intent)
        
        assert report.decision == SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION
    
    def test_commits_pending_returns_block(self, tmp_path):
        """4. commits_pending_post_push > 0 => BLOCK_AUTHORIZATION."""
        packet = SemanticMemoryRealWriteAuthorizationPacket(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["commits_pending_post_push"] = 1
        intent = create_valid_human_intent_template()
        
        report = packet.build_packet_read_only(evidence, intent)
        
        assert report.decision == SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION
    
    def test_staged_files_returns_block(self, tmp_path):
        """5. staged_files non-empty => BLOCK_AUTHORIZATION."""
        packet = SemanticMemoryRealWriteAuthorizationPacket(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["staged_files"] = ["test.py"]
        intent = create_valid_human_intent_template()
        
        report = packet.build_packet_read_only(evidence, intent)
        
        assert report.decision == SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION
    
    def test_memory_semantic_in_scope_returns_block(self, tmp_path):
        """6. memory_semantic_in_scope True => BLOCK_AUTHORIZATION."""
        packet = SemanticMemoryRealWriteAuthorizationPacket(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["memory_semantic_in_scope"] = True
        intent = create_valid_human_intent_template()
        
        report = packet.build_packet_read_only(evidence, intent)
        
        assert report.decision == SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION
    
    def test_runtime_active_returns_block(self, tmp_path):
        """7. runtime_active True => BLOCK_AUTHORIZATION."""
        packet = SemanticMemoryRealWriteAuthorizationPacket(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["runtime_active"] = True
        intent = create_valid_human_intent_template()
        
        report = packet.build_packet_read_only(evidence, intent)
        
        assert report.decision == SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION
    
    def test_faiss_write_enabled_returns_block(self, tmp_path):
        """8. faiss_write_enabled True => BLOCK_AUTHORIZATION."""
        packet = SemanticMemoryRealWriteAuthorizationPacket(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["faiss_write_enabled"] = True
        intent = create_valid_human_intent_template()
        
        report = packet.build_packet_read_only(evidence, intent)
        
        assert report.decision == SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION
    
    def test_add_memory_enabled_returns_block(self, tmp_path):
        """9. add_memory_enabled True => BLOCK_AUTHORIZATION."""
        packet = SemanticMemoryRealWriteAuthorizationPacket(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["add_memory_enabled"] = True
        intent = create_valid_human_intent_template()
        
        report = packet.build_packet_read_only(evidence, intent)
        
        assert report.decision == SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION
    
    def test_allows_auto_execute_returns_block(self, tmp_path):
        """10. allows_auto_execute True => BLOCK_AUTHORIZATION."""
        packet = SemanticMemoryRealWriteAuthorizationPacket(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        evidence["allows_auto_execute"] = True
        intent = create_valid_human_intent_template()
        
        report = packet.build_packet_read_only(evidence, intent)
        
        assert report.decision == SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION
    
    def test_human_intent_allows_real_write_returns_block(self, tmp_path):
        """11. human intent allows_real_write_execution=True => BLOCK_AUTHORIZATION."""
        packet = SemanticMemoryRealWriteAuthorizationPacket(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        intent = create_valid_human_intent_template()
        intent["allows_real_write_execution"] = True
        
        report = packet.build_packet_read_only(evidence, intent)
        
        assert report.decision == SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION


class TestSafetyInvariants:
    """Test that safety invariants are always enforced."""
    
    def test_valid_packet_keeps_allow_real_write_false(self, tmp_path):
        """12. valid packet keeps allow_real_write=False."""
        packet = SemanticMemoryRealWriteAuthorizationPacket(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        intent = create_valid_human_intent_template()
        
        report = packet.build_packet_read_only(evidence, intent)
        
        assert report.allow_real_write is False
    
    def test_valid_packet_keeps_can_execute_real_write_false(self, tmp_path):
        """13. valid packet keeps can_execute_real_write=False."""
        packet = SemanticMemoryRealWriteAuthorizationPacket(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        intent = create_valid_human_intent_template()
        
        report = packet.build_packet_read_only(evidence, intent)
        
        assert report.can_execute_real_write is False
    
    def test_valid_packet_keeps_dry_run_only_true(self, tmp_path):
        """14. valid packet keeps dry_run_only=True."""
        packet = SemanticMemoryRealWriteAuthorizationPacket(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        intent = create_valid_human_intent_template()
        
        report = packet.build_packet_read_only(evidence, intent)
        
        assert report.dry_run_only is True
    
    def test_valid_packet_keeps_simulated_only_true(self, tmp_path):
        """15. valid packet keeps simulated_only=True."""
        packet = SemanticMemoryRealWriteAuthorizationPacket(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        intent = create_valid_human_intent_template()
        
        report = packet.build_packet_read_only(evidence, intent)
        
        assert report.simulated_only is True
    
    def test_valid_packet_requires_second_confirmation_true(self, tmp_path):
        """16. valid packet requires_second_confirmation=True."""
        packet = SemanticMemoryRealWriteAuthorizationPacket(repo_root=tmp_path)
        evidence = create_valid_evidence_template()
        intent = create_valid_human_intent_template()
        
        report = packet.build_packet_read_only(evidence, intent)
        
        assert report.requires_second_confirmation is True
    
    def test_block_packet_returns_block_authorization(self, tmp_path):
        """17. block_packet returns BLOCK_AUTHORIZATION."""
        packet = SemanticMemoryRealWriteAuthorizationPacket(repo_root=tmp_path)
        
        report = packet.block_packet("Test block reason")
        
        assert report.decision == SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION
        assert any(f.code == "PACKET_BLOCKED" for f in report.findings)
    
    def test_summarize_contract_returns_allow_real_write_false(self, tmp_path):
        """18. summarize_contract returns allow_real_write=False."""
        packet = SemanticMemoryRealWriteAuthorizationPacket(repo_root=tmp_path)
        
        contract = packet.summarize_contract()
        
        assert contract["safety_invariants"]["allow_real_write"] is False


class TestSecurityConstraints:
    """Test security constraints through static analysis."""
    
    def test_no_subprocess_in_module(self):
        """19. no subprocess."""
        import brain.semantic_memory_real_write_authorization_packet as module
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
        """20. no open."""
        import brain.semantic_memory_real_write_authorization_packet as module
        import ast
        
        source = Path(module.__file__).read_text()
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id != "open"
    
    def test_no_copy_literal_or_call(self):
        """21. no copy literal/call."""
        import brain.semantic_memory_real_write_authorization_packet as module
        
        source = Path(module.__file__).read_text()
        
        # Check for copy operations without using literal strings
        forbidden_call = "." + "copy" + "("
        forbidden_exact = "." + "copy" + ")"
        assert forbidden_call not in source
        assert forbidden_exact not in source
    
    def test_no_write_text_write_bytes(self):
        """22. no write_text/write_bytes."""
        import brain.semantic_memory_real_write_authorization_packet as module
        
        source = Path(module.__file__).read_text()
        
        assert "write_text" not in source
        assert "write_bytes" not in source
    
    def test_no_unlink_remove_rmdir(self):
        """23. no unlink/remove/rmdir."""
        import brain.semantic_memory_real_write_authorization_packet as module
        
        source = Path(module.__file__).read_text()
        
        assert ".unlink(" not in source
        assert ".remove(" not in source
        assert ".rmdir(" not in source
    
    def test_no_shutil(self):
        """24. no shutil."""
        import brain.semantic_memory_real_write_authorization_packet as module
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
        """25. no faiss import/object."""
        import brain.semantic_memory_real_write_authorization_packet as module
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
        """26. no requests/httpx."""
        import brain.semantic_memory_real_write_authorization_packet as module
        
        source = Path(module.__file__).read_text()
        
        assert "requests" not in source
        assert "httpx" not in source
    
    def test_no_semantic_mem_bridge_literal(self):
        """27. no semantic memory bridge literal."""
        import brain.semantic_memory_real_write_authorization_packet as module
        
        source = Path(module.__file__).read_text()
        
        pattern = "semantic" + "_memory" + "_bridge"
        assert pattern not in source
    
    def test_no_add_memory_call_literal(self):
        """28. no add memory call literal."""
        import brain.semantic_memory_real_write_authorization_packet as module
        
        source = Path(module.__file__).read_text()
        
        pattern = "add" + "_memory" + "("
        assert pattern not in source
    
    def test_no_promote_action_call(self):
        """29. no promote action call."""
        import brain.semantic_memory_real_write_authorization_packet as module
        import ast
        
        source = Path(module.__file__).read_text()
        tree = ast.parse(source)
        
        # Check for promote action calls using concatenated string
        target = "promote" + "_real"
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == target:
                    assert False, "Found promote action call"
            elif isinstance(node, ast.Attribute):
                if node.attr == target:
                    assert False, "Found promote action attribute access"
    
    def test_no_rollback_execution_action_call(self):
        """30. no rollback execution action call."""
        import brain.semantic_memory_real_write_authorization_packet as module
        import ast
        
        source = Path(module.__file__).read_text()
        tree = ast.parse(source)
        
        # Check for rollback execution action calls using concatenated string
        target = "execute" + "_rollback" + "_real"
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == target:
                    assert False, "Found rollback execution action call"
            elif isinstance(node, ast.Attribute):
                if node.attr == target:
                    assert False, "Found rollback execution action attribute access"
    
    def test_no_allow_real_write_true_literal(self):
        """31. no allow real write true literal."""
        import brain.semantic_memory_real_write_authorization_packet as module
        
        source = Path(module.__file__).read_text()
        
        pattern = "allow" + "_real" + "_write" + "=" + "True"
        assert pattern not in source


class TestHelperFunctions:
    """Test helper functions."""
    
    def test_create_valid_evidence_template(self):
        """Template contains all required keys."""
        template = create_valid_evidence_template()
        
        required_keys = [
            "go_no_go_decision",
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
    
    def test_create_valid_human_intent_template(self):
        """Template contains all required keys."""
        template = create_valid_human_intent_template()
        
        required_keys = [
            "approved_by",
            "approval_scope",
            "allowed_next_phase",
            "understands_no_auto_execute",
            "allows_candidate_only",
            "allows_real_write_execution",
            "requires_second_confirmation",
        ]
        
        for key in required_keys:
            assert key in template


class TestFindingDataclass:
    """Test SemanticMemoryAuthorizationFinding dataclass."""
    
    def test_finding_creation(self):
        """Finding can be created with all fields."""
        finding = SemanticMemoryAuthorizationFinding(
            code="TEST_CODE",
            severity=SemanticMemoryAuthorizationSeverity.INFO,
            message="Test message",
            evidence={"key": "value"}
        )
        
        assert finding.code == "TEST_CODE"
        assert finding.severity == SemanticMemoryAuthorizationSeverity.INFO
        assert finding.message == "Test message"
        assert finding.evidence == {"key": "value"}


class TestReportDataclass:
    """Test SemanticMemoryRealWriteAuthorizationPacketReport dataclass."""
    
    def test_report_default_safety_values(self):
        """Report defaults enforce safety invariants."""
        report = SemanticMemoryRealWriteAuthorizationPacketReport(
            authorization_packet_id="test-id",
            created_at_utc="2024-01-01T00:00:00Z",
            decision=SemanticMemoryAuthorizationDecision.AUTHORIZATION_PACKET_READY,
            findings=[],
            blocker_count=0,
            warning_count=0,
            info_count=0,
            go_no_go_decision="GO_CANDIDATE_ONLY",
            approval_scope="test",
            allowed_next_phase="test",
            human_approval_intent=True,
            requires_second_confirmation=True,
        )
        
        # Safety invariants must be enforced
        assert report.can_execute_real_write is False
        assert report.allow_real_write is False
        assert report.dry_run_only is True
        assert report.simulated_only is True
        assert report.requires_second_confirmation is True
