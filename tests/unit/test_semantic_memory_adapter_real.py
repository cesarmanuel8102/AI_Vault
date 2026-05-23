"""
P2-E Commit 4B: Tests unitarios para SemanticMemoryRealAdapterSkeleton

Tests para validar el esqueleto del adapter real.
NO escriben en memory/semantic real.
NO llaman add_memory real.
NO importan FAISS.
"""

import pytest
import sys
from pathlib import Path

# Agregar raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.semantic_memory_adapter_real import (
    SemanticMemoryRealAdapterSkeleton,
    SemanticMemoryRealAdapterStatus,
    SemanticMemoryRealWritePlan,
)


class TestSemanticMemoryRealWritePlan:
    """Tests para SemanticMemoryRealWritePlan."""
    
    def test_plan_creation(self):
        """Test que se puede crear un plan básico."""
        plan = SemanticMemoryRealWritePlan(
            plan_id="plan_001",
            created_at_utc="2026-01-01T00:00:00+00:00",
            record_id="rec_001",
            text="Test content",
            source="test",
            content_hash="abc123",
            metadata={"key": "value"},
            validation_score=0.95,
            snapshot_id="snap_001",
        )
        
        assert plan.plan_id == "plan_001"
        assert plan.record_id == "rec_001"
        assert plan.text == "Test content"
        assert plan.source == "test"
        assert plan.content_hash == "abc123"
        assert plan.snapshot_id == "snap_001"
        assert plan.dry_run_only is True
        assert plan.allow_real_write is False
    
    def test_plan_to_dict(self):
        """Test que to_dict serializa correctamente."""
        plan = SemanticMemoryRealWritePlan(
            plan_id="plan_002",
            created_at_utc="2026-01-01T00:00:00+00:00",
            record_id="rec_002",
            text="Content",
            source="src",
            content_hash="hash",
            metadata={},
            validation_score=0.85,
            snapshot_id="snap_002",
        )
        
        d = plan.to_dict()
        assert d["plan_id"] == "plan_002"
        assert d["record_id"] == "rec_002"
        assert d["dry_run_only"] is True
        assert d["allow_real_write"] is False
        assert d["snapshot_id"] == "snap_002"


class TestSemanticMemoryRealAdapterSkeleton:
    """Tests para SemanticMemoryRealAdapterSkeleton."""
    
    def test_adapter_initialization(self):
        """Test que el adapter se inicializa correctamente."""
        adapter = SemanticMemoryRealAdapterSkeleton()
        
        summary = adapter.summarize_contract()
        assert summary["contract_version"] == "P2-E-Commit-4B"
        assert summary["dry_run_only"] is True
        assert summary["allow_real_write"] is False
    
    def test_build_write_plan_generates_plan_id(self):
        """Test que build_write_plan genera plan_id."""
        adapter = SemanticMemoryRealAdapterSkeleton()
        
        plan = adapter.build_write_plan(
            record_id="rec_001",
            text="Test content",
            source="test",
            content_hash="abc123",
        )
        
        assert plan.plan_id.startswith("plan_")
        assert len(plan.plan_id) > len("plan_")
    
    def test_plan_maintains_dry_run_only(self):
        """Test que plan mantiene dry_run_only=True."""
        adapter = SemanticMemoryRealAdapterSkeleton()
        
        plan = adapter.build_write_plan(
            record_id="rec_002",
            text="Content",
            source="src",
            content_hash="hash",
        )
        
        assert plan.dry_run_only is True
    
    def test_plan_maintains_allow_real_write_false(self):
        """Test que plan mantiene allow_real_write=False."""
        adapter = SemanticMemoryRealAdapterSkeleton()
        
        plan = adapter.build_write_plan(
            record_id="rec_003",
            text="Content",
            source="src",
            content_hash="hash",
        )
        
        assert plan.allow_real_write is False
    
    def test_validate_write_plan_accepts_valid(self):
        """Test que validate_write_plan acepta plan válido."""
        adapter = SemanticMemoryRealAdapterSkeleton()
        
        plan = adapter.build_write_plan(
            record_id="rec_valid",
            text="Valid content",
            source="test",
            content_hash="abc123",
            metadata={"key": "value"},
            validation_score=0.95,
            snapshot_id="snap_001",
        )
        
        errors, warnings = adapter.validate_write_plan(plan)
        
        assert len(errors) == 0
    
    def test_validate_write_plan_rejects_empty_record_id(self):
        """Test que validate_write_plan rechaza record_id vacío."""
        adapter = SemanticMemoryRealAdapterSkeleton()
        
        plan = adapter.build_write_plan(
            record_id="",
            text="Content",
            source="src",
            content_hash="hash",
        )
        
        errors, _ = adapter.validate_write_plan(plan)
        
        assert "record_id es requerido" in errors
    
    def test_validate_write_plan_rejects_empty_text(self):
        """Test que validate_write_plan rechaza text vacío."""
        adapter = SemanticMemoryRealAdapterSkeleton()
        
        plan = adapter.build_write_plan(
            record_id="rec_001",
            text="",
            source="src",
            content_hash="hash",
        )
        
        errors, _ = adapter.validate_write_plan(plan)
        
        assert any("text es requerido" in e for e in errors)
    
    def test_validate_write_plan_rejects_empty_source(self):
        """Test que validate_write_plan rechaza source vacío."""
        adapter = SemanticMemoryRealAdapterSkeleton()
        
        plan = adapter.build_write_plan(
            record_id="rec_001",
            text="Content",
            source="",
            content_hash="hash",
        )
        
        errors, _ = adapter.validate_write_plan(plan)
        
        assert "source es requerido" in errors
    
    def test_validate_write_plan_rejects_empty_content_hash(self):
        """Test que validate_write_plan rechaza content_hash vacío."""
        adapter = SemanticMemoryRealAdapterSkeleton()
        
        plan = adapter.build_write_plan(
            record_id="rec_001",
            text="Content",
            source="src",
            content_hash="",
        )
        
        errors, _ = adapter.validate_write_plan(plan)
        
        assert "content_hash es requerido" in errors
    
    def test_validate_write_plan_rejects_non_dict_metadata(self):
        """Test que validate_write_plan rechaza metadata no dict."""
        adapter = SemanticMemoryRealAdapterSkeleton()
        
        plan = adapter.build_write_plan(
            record_id="rec_001",
            text="Content",
            source="src",
            content_hash="hash",
            metadata="not_a_dict",
        )
        
        errors, _ = adapter.validate_write_plan(plan)
        
        assert "metadata debe ser un diccionario" in errors
    
    def test_validate_write_plan_rejects_negative_validation_score(self):
        """Test que validate_write_plan rechaza validation_score negativo."""
        adapter = SemanticMemoryRealAdapterSkeleton()
        
        plan = adapter.build_write_plan(
            record_id="rec_001",
            text="Content",
            source="src",
            content_hash="hash",
            validation_score=-0.5,
        )
        
        errors, _ = adapter.validate_write_plan(plan)
        
        assert "validation_score no puede ser menor a 0.0" in errors
    
    def test_validate_write_plan_rejects_validation_score_greater_than_one(self):
        """Test que validate_write_plan rechaza validation_score > 1."""
        adapter = SemanticMemoryRealAdapterSkeleton()
        
        plan = adapter.build_write_plan(
            record_id="rec_001",
            text="Content",
            source="src",
            content_hash="hash",
            validation_score=1.5,
        )
        
        errors, _ = adapter.validate_write_plan(plan)
        
        assert "validation_score no puede ser mayor a 1.0" in errors
    
    def test_prepare_blocked_real_write_no_real_add_memory(self):
        """Test que prepare_blocked_real_write no llama add_memory real."""
        adapter = SemanticMemoryRealAdapterSkeleton()
        
        plan = adapter.build_write_plan(
            record_id="rec_001",
            text="Content",
            source="src",
            content_hash="hash",
            validation_score=0.95,
            snapshot_id="snap_001",
        )
        
        result = adapter.prepare_blocked_real_write(plan)
        
        # Verificar que es dry-run y bloqueado
        assert result.dry_run_only is True
        assert result.allow_real_write is False
        assert "blocked" in result.status.value.lower() or "blocked" in str(result.warnings).lower()
    
    def test_prepare_blocked_real_write_returns_blocked_status(self):
        """Test que prepare_blocked_real_write devuelve estado bloqueado."""
        adapter = SemanticMemoryRealAdapterSkeleton()
        
        plan = adapter.build_write_plan(
            record_id="rec_001",
            text="Content",
            source="src",
            content_hash="hash",
            validation_score=0.95,
            snapshot_id="snap_001",
        )
        
        result = adapter.prepare_blocked_real_write(plan)
        
        assert result.status in [
            SemanticMemoryRealAdapterStatus.VALIDATED_BLOCKED,
            SemanticMemoryRealAdapterStatus.READY_BLOCKED,
        ]
    
    def test_block_real_write_returns_real_write_blocked(self):
        """Test que block_real_write devuelve REAL_WRITE_BLOCKED."""
        adapter = SemanticMemoryRealAdapterSkeleton()
        
        plan = adapter.build_write_plan(
            record_id="rec_001",
            text="Content",
            source="src",
            content_hash="hash",
        )
        
        result = adapter.block_real_write(plan)
        
        assert result.status == SemanticMemoryRealAdapterStatus.REAL_WRITE_BLOCKED
        assert result.dry_run_only is True
        assert result.allow_real_write is False
    
    def test_missing_snapshot_id_generates_warning(self):
        """Test que falta snapshot_id genera warning."""
        adapter = SemanticMemoryRealAdapterSkeleton()
        
        plan = adapter.build_write_plan(
            record_id="rec_001",
            text="Content",
            source="src",
            content_hash="hash",
            snapshot_id=None,  # Falta
        )
        
        errors, warnings = adapter.validate_write_plan(plan)
        
        assert any("snapshot_id" in w.lower() for w in warnings)
    
    def test_summarize_contract_returns_allow_real_write_false(self):
        """Test que summarize_contract devuelve allow_real_write=False."""
        adapter = SemanticMemoryRealAdapterSkeleton()
        
        summary = adapter.summarize_contract()
        
        assert summary["allow_real_write"] is False
        assert summary["dry_run_only"] is True


class TestSecurityNoForbiddenOperations:
    """Tests de seguridad para operaciones prohibidas."""
    
    def test_no_faiss_import(self):
        """Test que el módulo NO importa faiss."""
        import ast
        import brain.semantic_memory_adapter_real as module
        
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] != "faiss"
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                assert root != "faiss"
    
    def test_no_requests_import(self):
        """Test que el módulo NO importa requests."""
        import ast
        import brain.semantic_memory_adapter_real as module
        
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] != "requests"
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                assert root != "requests"
    
    def test_no_httpx_import(self):
        """Test que el módulo NO importa httpx."""
        import ast
        import brain.semantic_memory_adapter_real as module
        
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] != "httpx"
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                assert root != "httpx"
    
    def test_no_semantic_memory_bridge_import(self):
        """Test que el módulo NO importa semantic_memory_bridge."""
        import brain.semantic_memory_adapter_real as module
        
        source = Path(module.__file__).read_text(encoding="utf-8")
        
        assert "brain.semantic_memory_bridge" not in source
        assert "from brain.semantic_memory_bridge" not in source
    
    def test_no_write_text_in_productive_code(self):
        """Test que el módulo NO usa write_text."""
        import ast
        import brain.semantic_memory_adapter_real as module
        
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "write_text":
                    assert False, f"write_text found at line {node.lineno}"
    
    def test_no_write_bytes_in_productive_code(self):
        """Test que el módulo NO usa write_bytes."""
        import ast
        import brain.semantic_memory_adapter_real as module
        
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "write_bytes":
                    assert False, f"write_bytes found at line {node.lineno}"
    
    def test_no_open_in_productive_code(self):
        """Test que el módulo NO usa open."""
        import ast
        import brain.semantic_memory_adapter_real as module
        
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "open":
                    assert False, f"open() found at line {node.lineno}"
    
    def test_no_unlink_remove_rmdir(self):
        """Test que el módulo NO usa unlink/remove/rmdir."""
        import ast
        import brain.semantic_memory_adapter_real as module
        
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        
        forbidden = {"unlink", "remove", "rmdir"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in forbidden:
                    assert False, f"{func.attr}() found at line {node.lineno}"
    
    def test_no_add_memory_call(self):
        """Test que el módulo NO usa .add_memory(."""
        import brain.semantic_memory_adapter_real as module
        
        source = Path(module.__file__).read_text(encoding="utf-8")
        
        assert ".add_memory(" not in source
    
    def test_no_promote_real(self):
        """Test que el módulo NO implementa promote_real."""
        import brain.semantic_memory_adapter_real as module
        
        source = Path(module.__file__).read_text(encoding="utf-8")
        
        assert "def promote_real(" not in source
    
    def test_no_execute_rollback_real(self):
        """Test que el módulo NO implementa execute_rollback_real."""
        import brain.semantic_memory_adapter_real as module
        
        source = Path(module.__file__).read_text(encoding="utf-8")
        
        assert "def execute_rollback_real(" not in source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
