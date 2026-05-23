"""
P2-E Commit 4C: Unit tests for SemanticMemoryRollbackSimulation

Tests para validar la simulación de rollback/restore.
NO escriben en memory/semantic real.
NO llaman restore real.
NO importan FAISS.
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.semantic_memory_rollback_simulation import (
    SemanticMemoryRollbackSimulation,
    SemanticMemoryRollbackSimulationStatus,
    SemanticMemoryRollbackSimulationPlan,
)
from brain.memory_semantic_backup import (
    MemorySemanticBackupContract,
    MemorySemanticBackupStatus,
)


class FakeSnapshot:
    """Snapshot falso para testing."""
    def __init__(self):
        self.snapshot_id = "snapshot_test_001"
        self.affected_files = ["file1.txt", "file2.txt"]
        self.total_files = 2
        self.total_bytes = 100


class TestSemanticMemoryRollbackSimulationPlan:
    """Tests para SemanticMemoryRollbackSimulationPlan."""
    
    def test_plan_creation(self):
        """Test que se puede crear un plan básico."""
        plan = SemanticMemoryRollbackSimulationPlan(
            rollback_plan_id="plan_001",
            created_at_utc="2026-01-01T00:00:00+00:00",
            snapshot_id="snap_001",
        )
        
        assert plan.rollback_plan_id == "plan_001"
        assert plan.snapshot_id == "snap_001"
        assert plan.dry_run_only is True
        assert plan.allow_real_write is False
    
    def test_plan_to_dict(self):
        """Test que to_dict serializa correctamente."""
        plan = SemanticMemoryRollbackSimulationPlan(
            rollback_plan_id="plan_002",
            created_at_utc="2026-01-01T00:00:00+00:00",
            snapshot_id="snap_002",
            write_plan_id="wp_002",
            adapter_run_id="ar_002",
            reason="Test rollback",
            affected_files=["f1.txt", "f2.txt"],
            expected_restore_files=2,
            expected_restore_bytes=100,
        )
        
        d = plan.to_dict()
        assert d["rollback_plan_id"] == "plan_002"
        assert d["snapshot_id"] == "snap_002"
        assert d["write_plan_id"] == "wp_002"
        assert d["dry_run_only"] is True
        assert d["allow_real_write"] is False


class TestSemanticMemoryRollbackSimulation:
    """Tests para SemanticMemoryRollbackSimulation."""
    
    def test_initialization(self):
        """Test que el simulador se inicializa correctamente."""
        sim = SemanticMemoryRollbackSimulation()
        # El simulador no requiere backup_contract para funcionar
        assert sim is not None
    
    def test_build_rollback_plan_generates_id(self):
        """Test que build_rollback_plan genera rollback_plan_id."""
        sim = SemanticMemoryRollbackSimulation()
        fake_snapshot = FakeSnapshot()
        
        plan = sim.build_rollback_plan(
            snapshot=fake_snapshot,
            write_plan_id="wp_001",
            adapter_run_id="ar_001",
            reason="Test reason",
        )
        
        assert plan.rollback_plan_id.startswith("rollback_plan_")
        assert len(plan.rollback_plan_id) > len("rollback_plan_")
    
    def test_build_rollback_plan_maintains_dry_run_only(self):
        """Test que plan mantiene dry_run_only=True."""
        sim = SemanticMemoryRollbackSimulation()
        fake_snapshot = FakeSnapshot()
        
        plan = sim.build_rollback_plan(snapshot=fake_snapshot)
        
        assert plan.dry_run_only is True
        assert plan.allow_real_write is False
    
    def test_build_rollback_plan_with_write_plan_id(self):
        """Test que plan incluye write_plan_id."""
        sim = SemanticMemoryRollbackSimulation()
        fake_snapshot = FakeSnapshot()
        
        plan = sim.build_rollback_plan(
            snapshot=fake_snapshot,
            write_plan_id="wp_test",
            adapter_run_id="ar_test",
            reason="Test reason",
        )
        
        assert plan.write_plan_id == "wp_test"
        assert plan.adapter_run_id == "ar_test"
        assert plan.reason == "Test reason"
    
    def test_validate_rollback_plan_accepts_valid(self):
        """Test que validate acepta plan válido."""
        sim = SemanticMemoryRollbackSimulation()
        fake_snapshot = FakeSnapshot()
        
        plan = sim.build_rollback_plan(
            snapshot=fake_snapshot,
            write_plan_id="wp_001",
            adapter_run_id="ar_001",
            reason="Test reason",
        )
        
        errors, warnings = sim.validate_rollback_plan(plan)
        
        assert len(errors) == 0
    
    def test_validate_rejects_empty_snapshot_id(self):
        """Test que validate rechaza snapshot_id vacío."""
        sim = SemanticMemoryRollbackSimulation()
        
        plan = SemanticMemoryRollbackSimulationPlan(
            rollback_plan_id="plan_001",
            created_at_utc="2026-01-01T00:00:00+00:00",
            snapshot_id="",  # Empty
            reason="Test",
        )
        
        errors, _ = sim.validate_rollback_plan(plan)
        
        assert any("snapshot_id" in e.lower() for e in errors)
    
    def test_validate_rejects_empty_reason(self):
        """Test que validate rechaza reason vacío."""
        sim = SemanticMemoryRollbackSimulation()
        
        plan = SemanticMemoryRollbackSimulationPlan(
            rollback_plan_id="plan_001",
            created_at_utc="2026-01-01T00:00:00+00:00",
            snapshot_id="snap_001",
            reason="",  # Empty
        )
        
        errors, _ = sim.validate_rollback_plan(plan)
        
        assert any("reason" in e.lower() for e in errors)
    
    def test_validate_rejects_negative_files(self):
        """Test que validate rechaza expected_restore_files negativo."""
        sim = SemanticMemoryRollbackSimulation()
        
        plan = SemanticMemoryRollbackSimulationPlan(
            rollback_plan_id="plan_001",
            created_at_utc="2026-01-01T00:00:00+00:00",
            snapshot_id="snap_001",
            reason="Test",
            expected_restore_files=-1,
        )
        
        errors, _ = sim.validate_rollback_plan(plan)
        
        assert any("expected_restore_files" in e.lower() for e in errors)
    
    def test_validate_rejects_negative_bytes(self):
        """Test que validate rechaza expected_restore_bytes negativo."""
        sim = SemanticMemoryRollbackSimulation()
        
        plan = SemanticMemoryRollbackSimulationPlan(
            rollback_plan_id="plan_001",
            created_at_utc="2026-01-01T00:00:00+00:00",
            snapshot_id="snap_001",
            reason="Test",
            expected_restore_bytes=-1,
        )
        
        errors, _ = sim.validate_rollback_plan(plan)
        
        assert any("expected_restore_bytes" in e.lower() for e in errors)
    
    def test_validate_rejects_non_list_affected_files(self):
        """Test que validate rechaza affected_files no lista."""
        sim = SemanticMemoryRollbackSimulation()
        
        plan = SemanticMemoryRollbackSimulationPlan(
            rollback_plan_id="plan_001",
            created_at_utc="2026-01-01T00:00:00+00:00",
            snapshot_id="snap_001",
            reason="Test",
            affected_files="not_a_list",  # Not a list
        )
        
        errors, _ = sim.validate_rollback_plan(plan)
        
        assert any("affected_files" in e.lower() for e in errors)
    
    def test_validate_warns_missing_write_plan_id(self):
        """Test que validate genera warning si falta write_plan_id."""
        sim = SemanticMemoryRollbackSimulation()
        fake_snapshot = FakeSnapshot()
        
        plan = sim.build_rollback_plan(
            snapshot=fake_snapshot,
            write_plan_id=None,
            adapter_run_id="ar_001",
            reason="Test reason",
        )
        
        _, warnings = sim.validate_rollback_plan(plan)
        
        assert any("write_plan_id" in w.lower() for w in warnings)
    
    def test_validate_warns_missing_adapter_run_id(self):
        """Test que validate genera warning si falta adapter_run_id."""
        sim = SemanticMemoryRollbackSimulation()
        fake_snapshot = FakeSnapshot()
        
        plan = sim.build_rollback_plan(
            snapshot=fake_snapshot,
            write_plan_id="wp_001",
            adapter_run_id=None,
            reason="Test reason",
        )
        
        _, warnings = sim.validate_rollback_plan(plan)
        
        assert any("adapter_run_id" in w.lower() for w in warnings)
    
    def test_validate_warns_empty_affected_files(self):
        """Test que validate genera warning si affected_files está vacío."""
        sim = SemanticMemoryRollbackSimulation()
        
        plan = SemanticMemoryRollbackSimulationPlan(
            rollback_plan_id="plan_001",
            created_at_utc="2026-01-01T00:00:00+00:00",
            snapshot_id="snap_001",
            reason="Test",
            affected_files=[],  # Empty
        )
        
        _, warnings = sim.validate_rollback_plan(plan)
        
        assert any("affected_files" in w.lower() for w in warnings)
    
    def test_simulate_restore_from_snapshot_returns_simulated(self):
        """Test que simulate_restore devuelve RESTORE_SIMULATED."""
        sim = SemanticMemoryRollbackSimulation()
        fake_snapshot = FakeSnapshot()
        
        plan = sim.build_rollback_plan(snapshot=fake_snapshot)
        
        result = sim.simulate_restore_from_snapshot(plan)
        
        assert result.status == SemanticMemoryRollbackSimulationStatus.RESTORE_SIMULATED
        assert result.dry_run_only is True
        assert result.allow_real_write is False
    
    def test_simulate_restore_does_not_modify_files(self):
        """Test que simulate_restore no modifica archivos."""
        sim = SemanticMemoryRollbackSimulation()
        fake_snapshot = FakeSnapshot()
        
        plan = sim.build_rollback_plan(snapshot=fake_snapshot)
        
        result = sim.simulate_restore_from_snapshot(plan)
        
        # Verificar que no hay acciones reales
        assert "SIMULATED" in str(result.simulated_actions)
        assert "NO se modificaron" in str(result.simulated_actions)
    
    def test_simulate_rollback_after_failed_write_returns_rollback(self):
        """Test que simulate_rollback devuelve ROLLBACK_SIMULATED."""
        sim = SemanticMemoryRollbackSimulation()
        fake_snapshot = FakeSnapshot()
        
        plan = sim.build_rollback_plan(
            snapshot=fake_snapshot,
            write_plan_id="wp_001",
            adapter_run_id="ar_001",
            reason="Write failed",
        )
        
        result = sim.simulate_rollback_after_failed_write(plan)
        
        assert result.status == SemanticMemoryRollbackSimulationStatus.ROLLBACK_SIMULATED
        assert result.dry_run_only is True
        assert result.allow_real_write is False
    
    def test_block_real_rollback_returns_blocked(self):
        """Test que block_real_rollback devuelve REAL_ROLLBACK_BLOCKED."""
        sim = SemanticMemoryRollbackSimulation()
        fake_snapshot = FakeSnapshot()
        
        plan = sim.build_rollback_plan(snapshot=fake_snapshot)
        
        result = sim.block_real_rollback(plan, "Test block reason")
        
        assert result.status == SemanticMemoryRollbackSimulationStatus.REAL_ROLLBACK_BLOCKED
        assert result.dry_run_only is True
        assert result.allow_real_write is False
    
    def test_summarize_contract_returns_false_allow_real_write(self):
        """Test que summarize devuelve allow_real_write=False."""
        sim = SemanticMemoryRollbackSimulation()
        
        summary = sim.summarize_contract()
        
        assert summary["allow_real_write"] is False
        assert summary["dry_run_only"] is True
    
    def test_no_faiss_import(self):
        """Test que el módulo no importa faiss."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_rollback_simulation.py"
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
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_rollback_simulation.py"
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
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_rollback_simulation.py"
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
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_rollback_simulation.py"
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
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_rollback_simulation.py"
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
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_rollback_simulation.py"
        if module_path.exists():
            content = module_path.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    assert node.name != "promote_real"
    
    def test_no_execute_rollback_real(self):
        """Test que el módulo no implementa execute_rollback_real."""
        import ast
        
        module_path = Path(__file__).parent.parent.parent / "brain" / "semantic_memory_rollback_simulation.py"
        if module_path.exists():
            content = module_path.read_text()
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    assert node.name != "execute_rollback_real"
