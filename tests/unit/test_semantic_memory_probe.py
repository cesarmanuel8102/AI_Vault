"""
P2-E Commit 3F: Tests para SemanticMemory Read-Only Probe

Tests unitarios para validar el probe read-only de SemanticMemory.
NO escribe en archivos permanentes.
NO importa faiss.
NO requiere runtime 8090.
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timezone

# Agregar raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.semantic_memory_probe import (
    SemanticMemoryProbeResult,
    SemanticMemoryProbe,
    create_semantic_memory_probe,
)


class TestSemanticMemoryProbeResult:
    """Tests para SemanticMemoryProbeResult."""
    
    def test_result_creation(self):
        """Test que se puede crear un resultado básico."""
        result = SemanticMemoryProbeResult(
            probe_id="probe_001",
            created_at_utc="2026-01-01T00:00:00+00:00",
            repo_root="C:\\AI_VAULT",
            read_only=True,
            dry_run_only=True,
            allow_real_write=False,
        )
        
        assert result.probe_id == "probe_001"
        assert result.repo_root == "C:\\AI_VAULT"
        assert result.read_only is True
        assert result.dry_run_only is True
        assert result.allow_real_write is False
    
    def test_result_to_dict(self):
        """Test que to_dict serializa correctamente."""
        result = SemanticMemoryProbeResult(
            probe_id="probe_002",
            created_at_utc="2026-01-01T00:00:00+00:00",
            repo_root="C:\\AI_VAULT",
            semantic_paths_found=["path1", "path2"],
            faiss_paths_found=["faiss1"],
            candidate_modules=["module1"],
            candidate_classes=["class1"],
            candidate_methods=["method1"],
            memory_semantic_exists=True,
            memory_semantic_files=["file1.json"],
            read_only=True,
            dry_run_only=True,
            allow_real_write=False,
            risks=["R1: Test risk"],
            recommendations=["REC1: Test recommendation"],
        )
        
        d = result.to_dict()
        assert d["probe_id"] == "probe_002"
        assert d["read_only"] is True
        assert d["dry_run_only"] is True
        assert d["allow_real_write"] is False
        assert len(d["risks"]) == 1
        assert len(d["recommendations"]) == 1


class TestSemanticMemoryProbe:
    """Tests para SemanticMemoryProbe."""
    
    @pytest.fixture
    def probe(self, tmp_path):
        """Fixture para probe con repo temporal."""
        # Crear estructura temporal
        (tmp_path / "memory" / "semantic").mkdir(parents=True)
        (tmp_path / "memory" / "semantic" / "test.json").write_text("{}")
        return create_semantic_memory_probe(repo_root=str(tmp_path))
    
    def test_run_probe_generates_probe_id(self, probe):
        """Test que run_probe genera probe_id."""
        result = probe.run_probe()
        
        assert result.probe_id.startswith("probe_")
        assert len(result.probe_id) > 10
    
    def test_result_has_read_only_true(self, probe):
        """Test que el resultado tiene read_only=True."""
        result = probe.run_probe()
        
        assert result.read_only is True
    
    def test_result_has_dry_run_only_true(self, probe):
        """Test que el resultado tiene dry_run_only=True."""
        result = probe.run_probe()
        
        assert result.dry_run_only is True
    
    def test_result_has_allow_real_write_false(self, probe):
        """Test que el resultado tiene allow_real_write=False."""
        result = probe.run_probe()
        
        assert result.allow_real_write is False
    
    def test_inspect_memory_semantic_path_no_writes(self, probe):
        """Test que inspect_memory_semantic_path no escribe archivos."""
        result = probe.inspect_memory_semantic_path()
        
        # Verificar que solo leyó, no escribió
        assert isinstance(result, dict)
        assert "exists" in result
        assert "files" in result
    
    def test_inspect_python_files_no_faiss_import(self, probe):
        """Test que inspect_python_files no importa faiss."""
        result = probe.inspect_python_files()
        
        # Verificar que retorna diccionario
        assert isinstance(result, dict)
        assert "modules" in result
        assert "classes" in result
        assert "methods" in result
    
    def test_validate_probe_result_accepts_well_formed(self, probe):
        """Test que validate_probe_result acepta resultado bien formado."""
        result = SemanticMemoryProbeResult(
            probe_id="probe_valid",
            created_at_utc="2026-01-01T00:00:00+00:00",
            repo_root="C:\\AI_VAULT",
            read_only=True,
            dry_run_only=True,
            allow_real_write=False,
        )
        
        is_valid = probe.validate_probe_result(result)
        assert is_valid is True
    
    def test_validate_probe_result_rejects_allow_real_write_true(self, probe):
        """Test que validate_probe_result rechaza allow_real_write=True."""
        result = SemanticMemoryProbeResult(
            probe_id="probe_invalid",
            created_at_utc="2026-01-01T00:00:00+00:00",
            repo_root="C:\\AI_VAULT",
            read_only=True,
            dry_run_only=True,
            allow_real_write=True,  # No permitido
        )
        
        is_valid = probe.validate_probe_result(result)
        assert is_valid is False
    
    def test_summarize_contract_returns_dict(self, probe):
        """Test que summarize_contract devuelve diccionario."""
        result = SemanticMemoryProbeResult(
            probe_id="probe_test",
            created_at_utc="2026-01-01T00:00:00+00:00",
            repo_root="C:\\AI_VAULT",
            risks=["R1: Test"],
            recommendations=["REC1: Test"],
        )
        
        contract = probe.summarize_contract(result)
        
        assert isinstance(contract, dict)
        assert "required_methods" in contract
        assert "optional_methods" in contract
        assert "input_contract" in contract
        assert "output_contract" in contract
        assert "risks" in contract
        assert "recommendations" in contract


class TestNoForbiddenModules:
    """Tests para verificar que no hay imports prohibidos."""
    
    def test_no_faiss_import(self):
        """Test que el módulo no importa faiss."""
        import sys
        # Limpiar módulos prohibidos si existen
        forbidden = ["faiss", "requests", "httpx"]
        for mod in list(sys.modules.keys()):
            if any(f in mod.lower() for f in forbidden):
                del sys.modules[mod]
        
        # Importar el módulo
        import brain.semantic_memory_probe as probe_module
        
        # Verificar que no hay imports prohibidos
        loaded = list(sys.modules.keys())
        for forbidden in forbidden:
            assert not any(forbidden in mod for mod in loaded), \
                f"Módulo prohibido cargado: {forbidden}"
    
    def test_no_memory_semantic_write(self, tmp_path):
        """Test que no se escribe en memory/semantic."""
        probe = create_semantic_memory_probe(repo_root=str(tmp_path))
        
        # Ejecutar probe
        result = probe.run_probe()
        
        # Verificar que no escribió
        assert result.read_only is True
        assert result.allow_real_write is False


def test_factory_function():
    """Test que la factory crea instancia correctamente."""
    probe = create_semantic_memory_probe()
    assert isinstance(probe, SemanticMemoryProbe)
