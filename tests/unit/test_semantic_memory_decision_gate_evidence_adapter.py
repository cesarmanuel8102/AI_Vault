"""
P2-E Commit 4D-DecisionGateEvidenceAdapter: Tests unitarios
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from brain.semantic_memory_decision_gate_evidence_adapter import (
    SemanticMemoryDecisionGateEvidenceAdapter,
    SemanticMemoryEvidenceAdapterStatus,
    SemanticMemoryEvidenceAdapterFinding,
)
from brain.semantic_memory_external_evidence_contract import SemanticMemoryEvidenceStatus
from brain.semantic_memory_real_write_decision_gate import SemanticMemoryDecision


class TestSemanticMemoryDecisionGateEvidenceAdapter:
    """Tests para el adaptador de evidencia."""
    
    def _create_valid_bundle(self):
        """Helper para crear bundle válido."""
        return {
            "bundle_id": "test-valid",
            "created_at_utc": "2026-01-01T00:00:00",
            "producer": "test",
            "repo_root": "C:/AI_VAULT",
            "branch": "codex/own-capital-sustainable-return",
            "head_hash": "abc123",
            "git_state": {
                "verified": True,
                "pending_commits_vs_origin": 0,
                "staged_files": [],
                "memory_semantic_in_commit": False,
                "tmp_agent_strategies_in_commit": False,
                "nul_in_commit": False,
                "runtime_active": False,
            },
            "risk_summary": {
                "verified": True,
                "unresolved_high_risk_count": 0,
                "unresolved_write_like_count": 0,
                "unresolved_runtime_like_count": 0,
            },
            "security_validation": {
                "verified": True,
                "no_open": True,
                "no_subprocess": True,
                "no_faiss": True,
                "no_add_memory": True,
                "no_allow_real_write_true": True,
                "no_requests_httpx": True,
                "no_semantic_memory_bridge": True,
                "no_write_ops": True,
                "no_delete_ops": True,
                "no_move_ops": True,
            },
            "test_summary": {
                "verified": True,
                "failed": 0,
                "passed": 100,
                "decision_gate_tests_passed": True,
                "p2e_regression_tests_passed": True,
            },
            "smoke_summary": {
                "verified": True,
                "failed": 0,
                "passed": 10,
                "decision_gate_smoke_ok": True,
                "p2e_regression_smokes_ok": True,
            },
        }
    
    def test_valid_bundle_returns_accepted_for_gate(self, tmp_path):
        """Test que bundle válido devuelve ACCEPTED_FOR_GATE."""
        adapter = SemanticMemoryDecisionGateEvidenceAdapter(repo_root=tmp_path)
        bundle = self._create_valid_bundle()
        
        report = adapter.evaluate_with_evidence_read_only(bundle)
        
        assert report.status == SemanticMemoryEvidenceAdapterStatus.ACCEPTED_FOR_GATE
        assert report.evidence_status == SemanticMemoryEvidenceStatus.ACCEPTED.value
    
    def test_valid_bundle_returns_allow_manual_candidate(self, tmp_path):
        """Test que bundle válido devuelve decisión ALLOW_MANUAL_REAL_WRITE_CANDIDATE."""
        adapter = SemanticMemoryDecisionGateEvidenceAdapter(repo_root=tmp_path)
        bundle = self._create_valid_bundle()
        
        report = adapter.evaluate_with_evidence_read_only(bundle)
        
        assert report.decision == SemanticMemoryDecision.ALLOW_MANUAL_REAL_WRITE_CANDIDATE.value
    
    def test_valid_bundle_can_execute_false(self, tmp_path):
        """Test que bundle válido mantiene can_execute_real_write=False."""
        adapter = SemanticMemoryDecisionGateEvidenceAdapter(repo_root=tmp_path)
        bundle = self._create_valid_bundle()
        
        report = adapter.evaluate_with_evidence_read_only(bundle)
        
        assert report.can_execute_real_write is False
    
    def test_invalid_git_pending_commits_returns_blocked(self, tmp_path):
        """Test que git con commits pendientes devuelve BLOCKED."""
        adapter = SemanticMemoryDecisionGateEvidenceAdapter(repo_root=tmp_path)
        bundle = self._create_valid_bundle()
        bundle["git_state"]["pending_commits_vs_origin"] = 1
        
        report = adapter.evaluate_with_evidence_read_only(bundle)
        
        assert report.decision == SemanticMemoryDecision.BLOCK_REAL_WRITE.value
        assert report.status != SemanticMemoryEvidenceAdapterStatus.ACCEPTED_FOR_GATE
    
    def test_invalid_git_staged_files_returns_blocked(self, tmp_path):
        """Test que git con archivos staged devuelve BLOCKED."""
        adapter = SemanticMemoryDecisionGateEvidenceAdapter(repo_root=tmp_path)
        bundle = self._create_valid_bundle()
        bundle["git_state"]["staged_files"] = ["file.py"]
        
        report = adapter.evaluate_with_evidence_read_only(bundle)
        
        assert report.decision == SemanticMemoryDecision.BLOCK_REAL_WRITE.value
    
    def test_invalid_risk_high_risk_returns_blocked(self, tmp_path):
        """Test que riesgo alto sin resolver devuelve BLOCKED."""
        adapter = SemanticMemoryDecisionGateEvidenceAdapter(repo_root=tmp_path)
        bundle = self._create_valid_bundle()
        bundle["risk_summary"]["unresolved_high_risk_count"] = 1
        
        report = adapter.evaluate_with_evidence_read_only(bundle)
        
        assert report.decision == SemanticMemoryDecision.BLOCK_REAL_WRITE.value
    
    def test_partial_evidence_returns_canary_noop(self, tmp_path):
        """Test que evidencia parcial devuelve CANARY_NOOP_ONLY."""
        adapter = SemanticMemoryDecisionGateEvidenceAdapter(repo_root=tmp_path)
        bundle = self._create_valid_bundle()
        # Hacer que el test tenga warning pero no blocker
        bundle["test_summary"]["decision_gate_tests_passed"] = False
        
        report = adapter.evaluate_with_evidence_read_only(bundle)
        
        # Con warnings, el bundle es PARTIAL, no ACCEPTED
        assert report.status == SemanticMemoryEvidenceAdapterStatus.PARTIAL_EVIDENCE
        assert report.decision == SemanticMemoryDecision.CANARY_NOOP_ONLY.value
    
    def test_empty_bundle_returns_blocked(self, tmp_path):
        """Test que bundle vacío devuelve BLOCKED."""
        adapter = SemanticMemoryDecisionGateEvidenceAdapter(repo_root=tmp_path)
        
        report = adapter.evaluate_with_evidence_read_only({})
        
        assert report.decision == SemanticMemoryDecision.BLOCK_REAL_WRITE.value
        # Bundle vacío genera REJECTED_BY_EVIDENCE debido a validaciones requeridas faltantes
        assert report.status == SemanticMemoryEvidenceAdapterStatus.REJECTED_BY_EVIDENCE
    
    def test_allow_real_write_always_false(self, tmp_path):
        """Test que allow_real_write siempre es False."""
        adapter = SemanticMemoryDecisionGateEvidenceAdapter(repo_root=tmp_path)
        bundle = self._create_valid_bundle()
        
        report = adapter.evaluate_with_evidence_read_only(bundle)
        
        assert report.allow_real_write is False
    
    def test_dry_run_only_always_true(self, tmp_path):
        """Test que dry_run_only siempre es True."""
        adapter = SemanticMemoryDecisionGateEvidenceAdapter(repo_root=tmp_path)
        bundle = self._create_valid_bundle()
        
        report = adapter.evaluate_with_evidence_read_only(bundle)
        
        assert report.dry_run_only is True
    
    def test_accepted_for_decision_gate_true_only_when_evidence_accepted(self, tmp_path):
        """Test que accepted_for_decision_gate=True solo cuando evidencia aceptada."""
        adapter = SemanticMemoryDecisionGateEvidenceAdapter(repo_root=tmp_path)
        
        # Bundle válido
        valid_bundle = self._create_valid_bundle()
        valid_report = adapter.evaluate_with_evidence_read_only(valid_bundle)
        assert valid_report.accepted_for_decision_gate is True
        
        # Bundle inválido
        invalid_bundle = self._create_valid_bundle()
        invalid_bundle["git_state"]["pending_commits_vs_origin"] = 1
        invalid_report = adapter.evaluate_with_evidence_read_only(invalid_bundle)
        assert invalid_report.accepted_for_decision_gate is False
    
    def test_summarize_contract_returns_allow_real_write_false(self):
        """Test que summarize_contract devuelve allow_real_write=False."""
        adapter = SemanticMemoryDecisionGateEvidenceAdapter(repo_root=".")
        contract = adapter.summarize_contract()
        
        assert contract["allow_real_write"] is False
        assert contract["dry_run_only"] is True
        assert contract["can_execute_real_write"] is False
    
    def test_block_adapter_returns_blocked_and_allow_real_write_false(self):
        """Test que block_adapter devuelve BLOCKED y allow_real_write=False."""
        adapter = SemanticMemoryDecisionGateEvidenceAdapter(repo_root=".")
        report = adapter.block_adapter("Test block")
        
        assert report.status == SemanticMemoryEvidenceAdapterStatus.BLOCKED
        assert report.allow_real_write is False
        assert report.decision == SemanticMemoryDecision.BLOCK_REAL_WRITE.value
    
    def test_no_subprocess_in_module(self):
        """Test que el módulo no importa subprocess."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_decision_gate_evidence_adapter.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "subprocess", "subprocess import found"
            if isinstance(node, ast.ImportFrom):
                assert node.module != "subprocess", "subprocess import found"
    
    def test_no_open_in_productive_code(self):
        """Test que el módulo no usa open()."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_decision_gate_evidence_adapter.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id != "open", f"open() call found at line {node.lineno}"
    
    def test_no_copy_in_productive_code(self):
        """Test que el módulo no usa copy calls."""
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_decision_gate_evidence_adapter.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        
        assert "." + "copy" + "(" not in content, "copy call found in productive code"
    
    def test_no_write_text_in_productive_code(self):
        """Test que el módulo no usa write_text."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_decision_gate_evidence_adapter.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr != "write_text", f"write_text() call found at line {node.lineno}"
    
    def test_no_unlink_in_productive_code(self):
        """Test que el módulo no usa unlink."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_decision_gate_evidence_adapter.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr != "unlink", f"unlink() call found at line {node.lineno}"
    
    def test_no_shutil_in_productive_code(self):
        """Test que el módulo no importa shutil."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_decision_gate_evidence_adapter.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "shutil", "shutil import found"
    
    def test_no_faiss_import_in_productive_code(self):
        """Test que el módulo no importa faiss."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_decision_gate_evidence_adapter.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "faiss", "faiss import found"
    
    def test_no_requests_import_in_productive_code(self):
        """Test que el módulo no importa requests."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_decision_gate_evidence_adapter.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "requests", "requests import found"
    
    def test_no_semantic_memory_bridge_import_in_productive_code(self):
        """Test que el módulo no importa semantic_memory_bridge."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_decision_gate_evidence_adapter.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert "semantic_memory_bridge" not in (node.module or ""), "semantic_memory_bridge import found"
    
    def test_no_add_memory_in_productive_code(self):
        """Test que el módulo no llama add_memory."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_decision_gate_evidence_adapter.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr != "add_memory", f"add_memory call found at line {node.lineno}"
    
    def test_no_promote_real_in_productive_code(self):
        """Test que el módulo no define promote_real."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_decision_gate_evidence_adapter.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                assert node.name != "promote_real", "promote_real function found"
    
    def test_no_execute_rollback_real_in_productive_code(self):
        """Test que el módulo no define execute_rollback_real."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_decision_gate_evidence_adapter.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                assert node.name != "execute_rollback_real", "execute_rollback_real function found"
    
    def test_no_allow_real_write_true_in_productive_code(self):
        """Test que el módulo no tiene allow_real_write=True."""
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_decision_gate_evidence_adapter.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        
        assert "allow_real_write = True" not in content, "allow_real_write=True found"
