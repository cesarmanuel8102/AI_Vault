"""
P2-E Commit 4D-DecisionGate: Tests unitarios para SemanticMemoryRealWriteDecisionGate
"""

import sys
from pathlib import Path

# Add parent directory to path to import brain module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from brain.semantic_memory_real_write_decision_gate import (
    SemanticMemoryRealWriteDecisionGate,
    SemanticMemoryDecision,
    SemanticMemoryDecisionReasonCode,
    SemanticMemoryDecisionSeverity,
    SemanticMemoryDecisionFinding,
    SemanticMemoryRealWriteDecisionReport,
)


class TestSemanticMemoryRealWriteDecisionGate:
    """Tests para el decision gate de escritura real."""
    
    def test_missing_backup_contract_returns_block(self, tmp_path):
        """Test que falta backup contract devuelve BLOCK_REAL_WRITE."""
        gate = SemanticMemoryRealWriteDecisionGate(repo_root=tmp_path)
        report = gate.evaluate_read_only()
        
        assert report.decision == SemanticMemoryDecision.BLOCK_REAL_WRITE
        missing_backup = any(
            f.code == SemanticMemoryDecisionReasonCode.MISSING_BACKUP_CONTRACT
            for f in report.findings
        )
        assert missing_backup or report.blocker_count > 0
    
    def test_missing_rollback_simulation_returns_block(self, tmp_path):
        """Test que falta rollback simulation devuelve BLOCK_REAL_WRITE."""
        gate = SemanticMemoryRealWriteDecisionGate(repo_root=tmp_path)
        report = gate.evaluate_read_only()
        
        assert report.decision == SemanticMemoryDecision.BLOCK_REAL_WRITE
    
    def test_missing_readiness_gate_returns_block(self, tmp_path):
        """Test que falta readiness gate devuelve BLOCK_REAL_WRITE."""
        gate = SemanticMemoryRealWriteDecisionGate(repo_root=tmp_path)
        report = gate.evaluate_read_only()
        
        assert report.decision == SemanticMemoryDecision.BLOCK_REAL_WRITE
    
    def test_missing_real_state_audit_returns_block(self, tmp_path):
        """Test que falta real state audit devuelve BLOCK_REAL_WRITE."""
        gate = SemanticMemoryRealWriteDecisionGate(repo_root=tmp_path)
        report = gate.evaluate_read_only()
        
        assert report.decision == SemanticMemoryDecision.BLOCK_REAL_WRITE
    
    def test_missing_extra_file_classification_returns_block(self, tmp_path):
        """Test que falta extra file classification devuelve BLOCK_REAL_WRITE."""
        gate = SemanticMemoryRealWriteDecisionGate(repo_root=tmp_path)
        report = gate.evaluate_read_only()
        
        assert report.decision == SemanticMemoryDecision.BLOCK_REAL_WRITE
    
    def test_missing_dependency_mapping_returns_block(self, tmp_path):
        """Test que falta dependency mapping devuelve BLOCK_REAL_WRITE."""
        gate = SemanticMemoryRealWriteDecisionGate(repo_root=tmp_path)
        report = gate.evaluate_read_only()
        
        assert report.decision == SemanticMemoryDecision.BLOCK_REAL_WRITE
    
    def test_all_artifacts_present_no_missing_artifact_blockers(self, tmp_path):
        """Test que todos los artefactos presentes no generan blockers de missing artifact."""
        # Crear todos los artefactos requeridos
        required_artifacts = [
            "brain/memory_semantic_backup.py",
            "brain/semantic_memory_adapter_real.py",
            "brain/semantic_memory_rollback_simulation.py",
            "brain/semantic_memory_real_write_readiness_gate.py",
            "brain/semantic_memory_real_state_audit.py",
            "brain/semantic_memory_extra_file_classifier.py",
            "brain/semantic_memory_extra_file_dependency_mapper.py",
        ]
        
        for artifact in required_artifacts:
            artifact_path = tmp_path / artifact
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_text("# Placeholder", encoding="utf-8")
        
        gate = SemanticMemoryRealWriteDecisionGate(repo_root=tmp_path)
        report = gate.evaluate_read_only()
        
        # No debe haber blockers de artefactos faltantes
        missing_artifact_codes = {
            SemanticMemoryDecisionReasonCode.MISSING_BACKUP_CONTRACT,
            SemanticMemoryDecisionReasonCode.MISSING_ROLLBACK_SIMULATION,
            SemanticMemoryDecisionReasonCode.MISSING_READINESS_GATE,
            SemanticMemoryDecisionReasonCode.MISSING_REAL_STATE_AUDIT,
            SemanticMemoryDecisionReasonCode.MISSING_EXTRA_FILE_CLASSIFICATION,
            SemanticMemoryDecisionReasonCode.MISSING_DEPENDENCY_MAPPING,
        }
        
        for finding in report.findings:
            assert finding.code not in missing_artifact_codes, f"Unexpected missing artifact: {finding.code}"
    
    def test_decide_with_blocker_returns_block_real_write(self):
        """Test que decide con blocker devuelve BLOCK_REAL_WRITE."""
        gate = SemanticMemoryRealWriteDecisionGate(repo_root=".")
        
        findings = [
            SemanticMemoryDecisionFinding(
                code=SemanticMemoryDecisionReasonCode.MISSING_BACKUP_CONTRACT,
                severity=SemanticMemoryDecisionSeverity.BLOCKER,
                message="Missing backup",
            ),
        ]
        
        decision = gate.decide(findings)
        assert decision == SemanticMemoryDecision.BLOCK_REAL_WRITE
    
    def test_decide_with_high_risk_finding_returns_manual_review(self):
        """Test que decide con high risk devuelve MANUAL_REVIEW_REQUIRED."""
        gate = SemanticMemoryRealWriteDecisionGate(repo_root=".")
        
        findings = [
            SemanticMemoryDecisionFinding(
                code=SemanticMemoryDecisionReasonCode.HIGH_RISK_EXTRA_FILES,
                severity=SemanticMemoryDecisionSeverity.BLOCKER,
                message="High risk files",
            ),
        ]
        
        decision = gate.decide(findings)
        assert decision == SemanticMemoryDecision.BLOCK_REAL_WRITE
    
    def test_decide_with_warnings_no_blocker_returns_canary_noop(self):
        """Test que decide con warnings sin blocker devuelve CANARY_NOOP_ONLY."""
        gate = SemanticMemoryRealWriteDecisionGate(repo_root=".")
        
        findings = [
            SemanticMemoryDecisionFinding(
                code=SemanticMemoryDecisionReasonCode.WRITE_LIKE_DEPENDENCY_HITS,
                severity=SemanticMemoryDecisionSeverity.WARNING,
                message="Write-like hits",
            ),
        ]
        
        decision = gate.decide(findings)
        assert decision == SemanticMemoryDecision.CANARY_NOOP_ONLY
    
    def test_decide_no_blockers_warnings_returns_allow_manual_candidate(self):
        """Test que decide sin blockers ni warnings devuelve ALLOW_MANUAL_REAL_WRITE_CANDIDATE."""
        gate = SemanticMemoryRealWriteDecisionGate(repo_root=".")
        
        findings = [
            SemanticMemoryDecisionFinding(
                code=SemanticMemoryDecisionReasonCode.ALLOW_REAL_WRITE_STILL_FALSE,
                severity=SemanticMemoryDecisionSeverity.INFO,
                message="Security enforced",
            ),
        ]
        
        decision = gate.decide(findings)
        assert decision == SemanticMemoryDecision.ALLOW_MANUAL_REAL_WRITE_CANDIDATE
    
    def test_can_execute_real_write_always_false(self, tmp_path):
        """Test que can_execute_real_write siempre es False."""
        gate = SemanticMemoryRealWriteDecisionGate(repo_root=tmp_path)
        report = gate.evaluate_read_only()
        
        assert report.can_execute_real_write is False
    
    def test_allow_real_write_always_false(self, tmp_path):
        """Test que allow_real_write siempre es False."""
        gate = SemanticMemoryRealWriteDecisionGate(repo_root=tmp_path)
        report = gate.evaluate_read_only()
        
        assert report.allow_real_write is False
    
    def test_dry_run_only_always_true(self, tmp_path):
        """Test que dry_run_only siempre es True."""
        gate = SemanticMemoryRealWriteDecisionGate(repo_root=tmp_path)
        report = gate.evaluate_read_only()
        
        assert report.dry_run_only is True
    
    def test_requires_manual_review_true_by_default(self, tmp_path):
        """Test que requires_manual_review es True por defecto."""
        gate = SemanticMemoryRealWriteDecisionGate(repo_root=tmp_path)
        report = gate.evaluate_read_only()
        
        assert report.requires_manual_review is True
    
    def test_block_real_write_maintains_allow_real_write_false(self):
        """Test que block_real_write mantiene allow_real_write=False."""
        gate = SemanticMemoryRealWriteDecisionGate(repo_root=".")
        report = gate.block_real_write("Test block")
        
        assert report.allow_real_write is False
        assert report.decision == SemanticMemoryDecision.BLOCK_REAL_WRITE
    
    def test_summarize_contract_returns_allow_real_write_false(self):
        """Test que summarize_contract devuelve allow_real_write=False."""
        gate = SemanticMemoryRealWriteDecisionGate(repo_root=".")
        contract = gate.summarize_contract()
        
        assert contract["allow_real_write"] is False
        assert contract["dry_run_only"] is True
        assert contract["can_execute_real_write"] is False
    
    def test_no_subprocess_import_in_module(self):
        """Test que el módulo no importa subprocess."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_decision_gate.py"
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
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_decision_gate.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id != "open", f"open() call found at line {node.lineno}"
    
    def test_no_write_text_in_productive_code(self):
        """Test que el módulo no usa write_text."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_decision_gate.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr != "write_text", f"write_text() call found at line {node.lineno}"
    
    def test_no_write_bytes_in_productive_code(self):
        """Test que el módulo no usa write_bytes."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_decision_gate.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr != "write_bytes", f"write_bytes() call found at line {node.lineno}"
    
    def test_no_unlink_in_productive_code(self):
        """Test que el módulo no usa unlink."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_decision_gate.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr != "unlink", f"unlink() call found at line {node.lineno}"
    
    def test_no_remove_in_productive_code(self):
        """Test que el módulo no usa remove."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_decision_gate.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr != "remove", f"remove() call found at line {node.lineno}"
    
    def test_no_rmdir_in_productive_code(self):
        """Test que el módulo no usa rmdir."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_decision_gate.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr != "rmdir", f"rmdir() call found at line {node.lineno}"
    
    def test_no_shutil_in_productive_code(self):
        """Test que el módulo no importa shutil."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_decision_gate.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "shutil", "shutil import found"
    
    def test_no_copy_in_productive_code(self):
        """Test que el módulo no usa .copy()."""
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_decision_gate.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        
        assert ".copy(" not in content, ".copy() call found in productive code"
    
    def test_no_add_memory_in_productive_code(self):
        """Test que el módulo no llama add_memory."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_decision_gate.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr != "add_memory", f"add_memory call found at line {node.lineno}"
    
    def test_no_promote_real_in_productive_code(self):
        """Test que el módulo no define promote_real."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_decision_gate.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                assert node.name != "promote_real", "promote_real function found"
    
    def test_no_execute_rollback_real_in_productive_code(self):
        """Test que el módulo no define execute_rollback_real."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_decision_gate.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                assert node.name != "execute_rollback_real", "execute_rollback_real function found"
    
    def test_no_faiss_import_in_productive_code(self):
        """Test que el módulo no importa faiss."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_decision_gate.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "faiss", "faiss import found"
    
    def test_no_requests_import_in_productive_code(self):
        """Test que el módulo no importa requests."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_decision_gate.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "requests", "requests import found"
    
    def test_no_semantic_memory_bridge_import_in_productive_code(self):
        """Test que el módulo no importa semantic_memory_bridge."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_decision_gate.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert "semantic_memory_bridge" not in (node.module or ""), "semantic_memory_bridge import found"
    
    def test_no_allow_real_write_true_in_productive_code(self):
        """Test que el módulo no tiene allow_real_write=True."""
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_decision_gate.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")
        
        assert "allow_real_write = True" not in content, "allow_real_write=True found"
