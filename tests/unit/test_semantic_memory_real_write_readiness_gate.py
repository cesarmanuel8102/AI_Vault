"""
P2-E Commit 4D-0: Unit tests for SemanticMemoryRealWriteReadinessGate

Tests para validar el gate de readiness antes de escritura real.
NO habilitan escritura real.
NO llaman add_memory real.
NO importan FAISS.
"""

import pytest
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
os.environ.setdefault("BRAIN_APPROVAL_4D_DRY_GATE_TOKEN", "test_approval_token_front_sec_01")

from brain.semantic_memory_real_write_readiness_gate import (
    SemanticMemoryRealWriteReadinessGate,
    SemanticMemoryRealWriteReadinessStatus,
)


class FakeBackupContract:
    """Backup contract falso para testing."""
    pass


class FakeRealAdapter:
    """Real adapter falso para testing."""
    pass


class FakeRollbackSimulation:
    """Rollback simulation falso para testing."""
    pass


class TestSemanticMemoryRealWriteReadinessGate:
    """Tests para SemanticMemoryRealWriteReadinessGate."""
    
    def test_evaluate_without_snapshot_returns_not_ready(self):
        """Test que evaluate sin snapshot_id devuelve NOT_READY."""
        gate = SemanticMemoryRealWriteReadinessGate()
        
        report = gate.evaluate_readiness(
            snapshot_id=None,
            user_approval_token=None,
        )
        
        assert report.status == SemanticMemoryRealWriteReadinessStatus.NOT_READY
        assert "snapshot_id" in str(report.validation_errors)
    
    def test_evaluate_with_snapshot_no_token_returns_approval_required(self):
        """Test que evaluate con snapshot pero sin token devuelve USER_APPROVAL_REQUIRED."""
        gate = SemanticMemoryRealWriteReadinessGate(
            backup_contract=FakeBackupContract(),
            real_adapter=FakeRealAdapter(),
            rollback_simulation=FakeRollbackSimulation(),
        )
        
        report = gate.evaluate_readiness(
            snapshot_id="snap_test_001",
            user_approval_token=None,
        )
        
        assert report.status == SemanticMemoryRealWriteReadinessStatus.USER_APPROVAL_REQUIRED
        assert report.user_approval_required is True
        assert report.user_approval_present is False
    
    def test_evaluate_with_snapshot_and_token_returns_ready_blocked(self):
        """Test que evaluate con snapshot y token válido devuelve READY_BLOCKED."""
        gate = SemanticMemoryRealWriteReadinessGate(
            backup_contract=FakeBackupContract(),
            real_adapter=FakeRealAdapter(),
            rollback_simulation=FakeRollbackSimulation(),
        )
        
        report = gate.evaluate_readiness(
            snapshot_id="snap_test_001",
            user_approval_token=os.environ.get("BRAIN_APPROVAL_4D_DRY_GATE_TOKEN", ""),
        )
        
        assert report.status == SemanticMemoryRealWriteReadinessStatus.READY_BLOCKED
        assert report.backup_contract_ok is True
        assert report.real_adapter_ok is True
        assert report.rollback_simulation_ok is True
        assert report.user_approval_required is True
        assert report.user_approval_present is True
    
    def test_allow_real_write_always_false(self):
        """Test que allow_real_write siempre es False."""
        gate = SemanticMemoryRealWriteReadinessGate(
            backup_contract=FakeBackupContract(),
            real_adapter=FakeRealAdapter(),
            rollback_simulation=FakeRollbackSimulation(),
        )
        
        # Sin snapshot
        report = gate.evaluate_readiness(snapshot_id=None)
        assert report.allow_real_write is False
        
        # Con snapshot, sin token
        report = gate.evaluate_readiness(
            snapshot_id="snap_test",
            user_approval_token=None,
        )
        assert report.allow_real_write is False
        
        # Con snapshot y token
        report = gate.evaluate_readiness(
            snapshot_id="snap_test",
            user_approval_token=os.environ.get("BRAIN_APPROVAL_4D_DRY_GATE_TOKEN", ""),
        )
        assert report.allow_real_write is False
    
    def test_dry_run_only_always_true(self):
        """Test que dry_run_only siempre es True."""
        gate = SemanticMemoryRealWriteReadinessGate()
        
        report = gate.evaluate_readiness(snapshot_id=None)
        assert report.dry_run_only is True
        
        report = gate.evaluate_readiness(
            snapshot_id="snap_test",
            user_approval_token=os.environ.get("BRAIN_APPROVAL_4D_DRY_GATE_TOKEN", ""),
        )
        assert report.dry_run_only is True
    
    def test_user_approval_required_always_true(self):
        """Test que user_approval_required siempre es True."""
        gate = SemanticMemoryRealWriteReadinessGate()
        
        report = gate.evaluate_readiness(snapshot_id=None)
        assert report.user_approval_required is True
        
        report = gate.evaluate_readiness(
            snapshot_id="snap_test",
            user_approval_token=os.environ.get("BRAIN_APPROVAL_4D_DRY_GATE_TOKEN", ""),
        )
        assert report.user_approval_required is True
    
    def test_user_approval_present_false_without_token(self):
        """Test que user_approval_present es False sin token."""
        gate = SemanticMemoryRealWriteReadinessGate(
            backup_contract=FakeBackupContract(),
            real_adapter=FakeRealAdapter(),
            rollback_simulation=FakeRollbackSimulation(),
        )
        
        report = gate.evaluate_readiness(
            snapshot_id="snap_test",
            user_approval_token=None,
        )
        
        assert report.user_approval_present is False
    
    def test_user_approval_present_true_with_valid_token(self):
        """Test que user_approval_present es True con token válido."""
        gate = SemanticMemoryRealWriteReadinessGate(
            backup_contract=FakeBackupContract(),
            real_adapter=FakeRealAdapter(),
            rollback_simulation=FakeRollbackSimulation(),
        )
        
        report = gate.evaluate_readiness(
            snapshot_id="snap_test",
            user_approval_token=os.environ.get("BRAIN_APPROVAL_4D_DRY_GATE_TOKEN", ""),
        )
        
        assert report.user_approval_present is True
    
    def test_invalid_token_does_not_authorize(self):
        """Test que token inválido no autoriza."""
        gate = SemanticMemoryRealWriteReadinessGate(
            backup_contract=FakeBackupContract(),
            real_adapter=FakeRealAdapter(),
            rollback_simulation=FakeRollbackSimulation(),
        )
        
        report = gate.evaluate_readiness(
            snapshot_id="snap_test",
            user_approval_token="INVALID_TOKEN",
        )
        
        assert report.user_approval_present is False
        assert report.status == SemanticMemoryRealWriteReadinessStatus.USER_APPROVAL_REQUIRED
    
    def test_block_real_write_returns_blocked(self):
        """Test que block_real_write devuelve REAL_WRITE_BLOCKED."""
        gate = SemanticMemoryRealWriteReadinessGate()
        
        report = gate.block_real_write("Test block reason")
        
        assert report.status == SemanticMemoryRealWriteReadinessStatus.REAL_WRITE_BLOCKED
    
    def test_block_real_write_maintains_allow_real_write_false(self):
        """Test que block_real_write mantiene allow_real_write=False."""
        gate = SemanticMemoryRealWriteReadinessGate()
        
        report = gate.block_real_write("Test block reason")
        
        assert report.allow_real_write is False
        assert report.dry_run_only is True
    
    def test_summarize_contract_returns_allow_real_write_false(self):
        """Test que summarize devuelve allow_real_write=False."""
        gate = SemanticMemoryRealWriteReadinessGate()
        
        summary = gate.summarize_contract()
        
        assert summary["allow_real_write"] is False
        assert summary["dry_run_only"] is True
    
    def test_missing_backup_contract_shows_error(self):
        """Test que falta backup contract genera error."""
        gate = SemanticMemoryRealWriteReadinessGate(
            backup_contract=None,
            real_adapter=FakeRealAdapter(),
            rollback_simulation=FakeRollbackSimulation(),
        )
        
        report = gate.evaluate_readiness(
            snapshot_id="snap_test",
            user_approval_token=os.environ.get("BRAIN_APPROVAL_4D_DRY_GATE_TOKEN", ""),
        )
        
        assert report.backup_contract_ok is False
        assert any("Backup contract" in e for e in report.validation_errors)
    
    def test_missing_real_adapter_shows_error(self):
        """Test que falta real adapter genera error."""
        gate = SemanticMemoryRealWriteReadinessGate(
            backup_contract=FakeBackupContract(),
            real_adapter=None,
            rollback_simulation=FakeRollbackSimulation(),
        )
        
        report = gate.evaluate_readiness(
            snapshot_id="snap_test",
            user_approval_token=os.environ.get("BRAIN_APPROVAL_4D_DRY_GATE_TOKEN", ""),
        )
        
        assert report.real_adapter_ok is False
        assert any("Real adapter" in e for e in report.validation_errors)
    
    def test_missing_rollback_simulation_shows_error(self):
        """Test que falta rollback simulation genera error."""
        gate = SemanticMemoryRealWriteReadinessGate(
            backup_contract=FakeBackupContract(),
            real_adapter=FakeRealAdapter(),
            rollback_simulation=None,
        )
        
        report = gate.evaluate_readiness(
            snapshot_id="snap_test",
            user_approval_token=os.environ.get("BRAIN_APPROVAL_4D_DRY_GATE_TOKEN", ""),
        )
        
        assert report.rollback_simulation_ok is False
        assert any("Rollback simulation" in e for e in report.validation_errors)
    
    def test_no_faiss_import(self):
        """Test que el módulo no importa faiss."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_readiness_gate.py"
        if module_path.exists():
            content = module_path.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name != "faiss"
                elif isinstance(node, ast.ImportFrom):
                    assert node.module != "faiss"
    
    def test_no_requests_import(self):
        """Test que el módulo no importa requests."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_readiness_gate.py"
        if module_path.exists():
            content = module_path.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert alias.name not in ["requests", "httpx"]
    
    def test_no_semantic_memory_bridge_import(self):
        """Test que el módulo no importa semantic_memory_bridge."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_readiness_gate.py"
        if module_path.exists():
            content = module_path.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert "semantic_memory_bridge" not in alias.name
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        assert "semantic_memory_bridge" not in node.module
    
    def test_no_write_text_write_bytes_open(self):
        """Test que el módulo no usa write_text/write_bytes/open."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_readiness_gate.py"
        if module_path.exists():
            content = module_path.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        assert node.func.id not in ["open"]
                    elif isinstance(node.func, ast.Attribute):
                        assert node.func.attr not in ["write_text", "write_bytes", "unlink", "remove", "rmdir"]
    
    def test_no_add_memory_call(self):
        """Test que el módulo no llama .add_memory(."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_readiness_gate.py"
        if module_path.exists():
            content = module_path.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        assert node.func.attr != "add_memory"
    
    def test_no_promote_real(self):
        """Test que el módulo no implementa promote_real."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_readiness_gate.py"
        if module_path.exists():
            content = module_path.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    assert node.name != "promote_real"
    
    def test_no_execute_rollback_real(self):
        """Test que el módulo no implementa execute_rollback_real."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_readiness_gate.py"
        if module_path.exists():
            content = module_path.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    assert node.name != "execute_rollback_real"
    
    def test_no_allow_real_write_true_in_productive_code(self):
        """Test que no hay allow_real_write=True en código productivo."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_real_write_readiness_gate.py"
        if module_path.exists():
            content = module_path.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "allow_real_write":
                            if isinstance(node.value, ast.Constant):
                                assert node.value.value is False
                        if isinstance(target, ast.Attribute) and target.attr == "allow_real_write":
                            if isinstance(node.value, ast.Constant):
                                assert node.value.value is False
