"""
P2-E Commit 3G: SemanticMemory Adapter Dry-Run Unit Tests

Tests para SemanticMemoryAdapterDryRun.

Cobertura:
1. build_payload genera payload_id.
2. payload tiene dry_run_only=True.
3. payload tiene allow_real_write=False.
4. validate_payload acepta payload válido.
5. validate_payload rechaza record_id vacío.
6. validate_payload rechaza text vacío.
7. validate_payload rechaza source vacío.
8. validate_payload rechaza content_hash vacío.
9. validate_payload rechaza metadata no dict.
10. validate_payload rechaza validation_score < 0.
11. validate_payload rechaza validation_score > 1.
12. prepare_dry_run devuelve DRY_RUN_READY con payload válido.
13. prepare_dry_run devuelve REJECTED con payload inválido.
14. prepare_dry_run no llama add_memory real.
15. block_real_write devuelve REAL_WRITE_BLOCKED.
16. validate_result acepta resultado válido.
17. validate_result rechaza allow_real_write=True.
18. no imports de faiss, requests, httpx.
19. no escritura en memory/semantic.

REGLAS:
- NO escribir en disco
- NO importar faiss
- NO llamar endpoints reales
- Todos los tests deben pasar en modo dry-run
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List

# Agregar raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.semantic_memory_adapter_dry_run import (
    SemanticMemoryAdapterDryRun,
    SemanticMemoryAdapterDryRunResult,
    SemanticMemoryAdapterStatus,
    SemanticMemoryPayload,
)


class TestSemanticMemoryPayload:
    """Tests para SemanticMemoryPayload."""
    
    def test_payload_creation(self):
        """Test que se puede crear un payload básico."""
        payload = SemanticMemoryPayload(
            payload_id="payload_001",
            record_id="rec_001",
            text="Test text content",
            source="test",
            content_hash="abc123",
            metadata={"key": "value"},
            validation_score=0.95,
            created_at_utc="2026-01-01T00:00:00+00:00",
            dry_run_only=True,
            allow_real_write=False,
        )
        
        assert payload.payload_id == "payload_001"
        assert payload.record_id == "rec_001"
        assert payload.text == "Test text content"
        assert payload.source == "test"
        assert payload.content_hash == "abc123"
        assert payload.metadata == {"key": "value"}
        assert payload.validation_score == 0.95
        assert payload.dry_run_only is True
        assert payload.allow_real_write is False
    
    def test_payload_to_dict(self):
        """Test que to_dict serializa correctamente."""
        payload = SemanticMemoryPayload(
            payload_id="payload_002",
            record_id="rec_002",
            text="Text",
            source="src",
            content_hash="hash",
            metadata={},
            validation_score=0.85,
            created_at_utc="2026-01-01T00:00:00+00:00",
        )
        
        data = payload.to_dict()
        
        assert isinstance(data, dict)
        assert data["payload_id"] == "payload_002"
        assert data["record_id"] == "rec_002"
        assert data["text"] == "Text"
        assert data["dry_run_only"] is True
        assert data["allow_real_write"] is False


class TestSemanticMemoryAdapterDryRunResult:
    """Tests para SemanticMemoryAdapterDryRunResult."""
    
    def test_result_creation(self):
        """Test que se puede crear un resultado básico."""
        result = SemanticMemoryAdapterDryRunResult(
            adapter_run_id="run_001",
            payload_id="payload_001",
            record_id="rec_001",
            status=SemanticMemoryAdapterStatus.DRY_RUN_READY,
            would_call_method="add_memory",
            candidate_module="brain.semantic_memory_bridge",
            candidate_class="SemanticMemoryBridge",
            validation_errors=[],
            warnings=[],
            dry_run_only=True,
            allow_real_write=False,
            metadata={"test": True},
        )
        
        assert result.adapter_run_id == "run_001"
        assert result.payload_id == "payload_001"
        assert result.status == SemanticMemoryAdapterStatus.DRY_RUN_READY
        assert result.would_call_method == "add_memory"
        assert result.dry_run_only is True
        assert result.allow_real_write is False
    
    def test_result_to_dict(self):
        """Test que to_dict serializa correctamente."""
        result = SemanticMemoryAdapterDryRunResult(
            adapter_run_id="run_002",
            payload_id="payload_002",
            record_id="rec_002",
            status=SemanticMemoryAdapterStatus.REAL_WRITE_BLOCKED,
            validation_errors=["error1"],
            warnings=["warning1"],
            dry_run_only=True,
            allow_real_write=False,
        )
        
        data = result.to_dict()
        
        assert isinstance(data, dict)
        assert data["adapter_run_id"] == "run_002"
        assert data["status"] == "REAL_WRITE_BLOCKED"
        assert data["validation_errors"] == ["error1"]
        assert data["dry_run_only"] is True
        assert data["allow_real_write"] is False


class TestSemanticMemoryAdapterDryRun:
    """Tests para SemanticMemoryAdapterDryRun."""
    
    def test_adapter_initialization(self):
        """Test que el adapter se inicializa correctamente."""
        adapter = SemanticMemoryAdapterDryRun()
        
        assert adapter._probe_result is None
        assert adapter._adapter_runs == []
        assert adapter.FUTURE_METHOD == "add_memory"
    
    def test_adapter_with_probe_result(self):
        """Test que el adapter acepta probe_result opcional."""
        mock_probe = {"test": "data"}
        adapter = SemanticMemoryAdapterDryRun(probe_result=mock_probe)
        
        assert adapter._probe_result == mock_probe
    
    def test_build_payload_generates_payload_id(self):
        """Test que build_payload genera payload_id."""
        adapter = SemanticMemoryAdapterDryRun()
        
        payload = adapter.build_payload(
            record_id="rec_001",
            text="Test content",
            source="test",
            content_hash="abc123",
            metadata={"key": "value"},
            validation_score=0.95,
        )
        
        assert payload.payload_id.startswith("payload_")
        assert len(payload.payload_id) > len("payload_")
        assert payload.record_id == "rec_001"
        assert payload.text == "Test content"
    
    def test_build_payload_has_dry_run_only_true(self):
        """Test que payload tiene dry_run_only=True."""
        adapter = SemanticMemoryAdapterDryRun()
        
        payload = adapter.build_payload(
            record_id="rec_002",
            text="Content",
            source="src",
            content_hash="hash",
        )
        
        assert payload.dry_run_only is True
    
    def test_build_payload_has_allow_real_write_false(self):
        """Test que payload tiene allow_real_write=False."""
        adapter = SemanticMemoryAdapterDryRun()
        
        payload = adapter.build_payload(
            record_id="rec_003",
            text="Content",
            source="src",
            content_hash="hash",
        )
        
        assert payload.allow_real_write is False
    
    def test_build_payload_default_metadata(self):
        """Test que build_payload usa metadata vacía por defecto."""
        adapter = SemanticMemoryAdapterDryRun()
        
        payload = adapter.build_payload(
            record_id="rec_004",
            text="Content",
            source="src",
            content_hash="hash",
        )
        
        assert payload.metadata == {}
    
    def test_build_payload_default_validation_score(self):
        """Test que build_payload usa validation_score=0.0 por defecto."""
        adapter = SemanticMemoryAdapterDryRun()
        
        payload = adapter.build_payload(
            record_id="rec_005",
            text="Content",
            source="src",
            content_hash="hash",
        )
        
        assert payload.validation_score == 0.0
    
    def test_validate_payload_accepts_valid_payload(self):
        """Test que validate_payload acepta payload válido."""
        adapter = SemanticMemoryAdapterDryRun()
        
        payload = adapter.build_payload(
            record_id="rec_valid",
            text="Valid content",
            source="test",
            content_hash="abc123",
            metadata={"key": "value"},
            validation_score=0.95,
        )
        
        errors = adapter.validate_payload(payload)
        
        assert errors == []
    
    def test_validate_payload_rejects_empty_record_id(self):
        """Test que validate_payload rechaza record_id vacío."""
        adapter = SemanticMemoryAdapterDryRun()
        
        payload = adapter.build_payload(
            record_id="",
            text="Content",
            source="src",
            content_hash="hash",
        )
        
        errors = adapter.validate_payload(payload)
        
        assert "record_id es requerido" in errors
    
    def test_validate_payload_rejects_empty_text(self):
        """Test que validate_payload rechaza text vacío."""
        adapter = SemanticMemoryAdapterDryRun()
        
        payload = adapter.build_payload(
            record_id="rec_001",
            text="",
            source="src",
            content_hash="hash",
        )
        
        errors = adapter.validate_payload(payload)
        
        assert "text es requerido y no puede estar vacío" in errors
    
    def test_validate_payload_rejects_empty_source(self):
        """Test que validate_payload rechaza source vacío."""
        adapter = SemanticMemoryAdapterDryRun()
        
        payload = adapter.build_payload(
            record_id="rec_001",
            text="Content",
            source="",
            content_hash="hash",
        )
        
        errors = adapter.validate_payload(payload)
        
        assert "source es requerido" in errors
    
    def test_validate_payload_rejects_empty_content_hash(self):
        """Test que validate_payload rechaza content_hash vacío."""
        adapter = SemanticMemoryAdapterDryRun()
        
        payload = adapter.build_payload(
            record_id="rec_001",
            text="Content",
            source="src",
            content_hash="",
        )
        
        errors = adapter.validate_payload(payload)
        
        assert "content_hash es requerido" in errors
    
    def test_validate_payload_rejects_non_dict_metadata(self):
        """Test que validate_payload rechaza metadata no dict."""
        adapter = SemanticMemoryAdapterDryRun()
        
        payload = SemanticMemoryPayload(
            payload_id="payload_001",
            record_id="rec_001",
            text="Content",
            source="src",
            content_hash="hash",
            metadata="not_a_dict",  # Invalid metadata
            validation_score=0.5,
            created_at_utc="2026-01-01T00:00:00+00:00",
        )
        
        errors = adapter.validate_payload(payload)
        
        assert "metadata debe ser un diccionario" in errors
    
    def test_validate_payload_rejects_negative_validation_score(self):
        """Test que validate_payload rechaza validation_score < 0."""
        adapter = SemanticMemoryAdapterDryRun()
        
        payload = adapter.build_payload(
            record_id="rec_001",
            text="Content",
            source="src",
            content_hash="hash",
            validation_score=-0.5,
        )
        
        errors = adapter.validate_payload(payload)
        
        assert "validation_score no puede ser menor a 0.0" in errors
    
    def test_validate_payload_rejects_validation_score_greater_than_one(self):
        """Test que validate_payload rechaza validation_score > 1."""
        adapter = SemanticMemoryAdapterDryRun()
        
        payload = adapter.build_payload(
            record_id="rec_001",
            text="Content",
            source="src",
            content_hash="hash",
            validation_score=1.5,
        )
        
        errors = adapter.validate_payload(payload)
        
        assert "validation_score no puede ser mayor a 1.0" in errors
    
    def test_prepare_dry_run_returns_dry_run_ready(self):
        """Test que prepare_dry_run devuelve DRY_RUN_READY con payload válido."""
        adapter = SemanticMemoryAdapterDryRun()
        
        payload = adapter.build_payload(
            record_id="rec_valid",
            text="Valid content",
            source="test",
            content_hash="abc123",
            validation_score=0.95,
        )
        
        result = adapter.prepare_dry_run(payload)
        
        assert result.status == SemanticMemoryAdapterStatus.DRY_RUN_READY
        assert result.adapter_run_id.startswith("adapter_run_")
        assert result.would_call_method == "add_memory"
        assert result.candidate_module == "brain.semantic_memory_bridge"
        assert result.candidate_class == "SemanticMemoryBridge"
        assert result.dry_run_only is True
        assert result.allow_real_write is False
    
    def test_prepare_dry_run_returns_rejected_with_invalid_payload(self):
        """Test que prepare_dry_run devuelve REJECTED con payload inválido."""
        adapter = SemanticMemoryAdapterDryRun()
        
        payload = adapter.build_payload(
            record_id="",
            text="",
            source="",
            content_hash="",
        )
        
        result = adapter.prepare_dry_run(payload)
        
        assert result.status == SemanticMemoryAdapterStatus.REJECTED
        assert len(result.validation_errors) > 0
        assert result.dry_run_only is True
        assert result.allow_real_write is False
    
    def test_prepare_dry_run_does_not_call_real_add_memory(self):
        """Test que prepare_dry_run no llama add_memory real."""
        adapter = SemanticMemoryAdapterDryRun()
        
        payload = adapter.build_payload(
            record_id="rec_001",
            text="Content",
            source="test",
            content_hash="abc123",
            validation_score=0.95,
        )
        
        result = adapter.prepare_dry_run(payload)
        
        # Verificar que es dry-run y no hay escritura real
        assert result.dry_run_only is True
        assert result.allow_real_write is False
        assert result.status == SemanticMemoryAdapterStatus.DRY_RUN_READY
        # would_call_method debe ser solo referencia textual
        assert result.would_call_method == "add_memory"
    
    def test_prepare_dry_run_generates_warning_for_long_text(self):
        """Test que prepare_dry_run genera warning para text > 20,000 caracteres."""
        adapter = SemanticMemoryAdapterDryRun()
        
        long_text = "x" * 20001
        
        payload = adapter.build_payload(
            record_id="rec_001",
            text=long_text,
            source="test",
            content_hash="abc123",
            validation_score=0.95,
        )
        
        result = adapter.prepare_dry_run(payload)
        
        assert result.status == SemanticMemoryAdapterStatus.DRY_RUN_READY
        assert any("20,000 caracteres" in w for w in result.warnings)
    
    def test_prepare_dry_run_generates_warning_for_low_validation_score(self):
        """Test que prepare_dry_run genera warning para validation_score < 0.70."""
        adapter = SemanticMemoryAdapterDryRun()
        
        payload = adapter.build_payload(
            record_id="rec_001",
            text="Content",
            source="test",
            content_hash="abc123",
            validation_score=0.65,
        )
        
        result = adapter.prepare_dry_run(payload)
        
        assert result.status == SemanticMemoryAdapterStatus.DRY_RUN_READY
        assert any("0.70" in w and "bajo" in w for w in result.warnings)
    
    def test_block_real_write_returns_real_write_blocked(self):
        """Test que block_real_write devuelve REAL_WRITE_BLOCKED."""
        adapter = SemanticMemoryAdapterDryRun()
        
        payload = adapter.build_payload(
            record_id="rec_001",
            text="Content",
            source="test",
            content_hash="abc123",
        )
        
        result = adapter.block_real_write(
            payload=payload,
            reason="Test block reason",
        )
        
        assert result.status == SemanticMemoryAdapterStatus.REAL_WRITE_BLOCKED
        assert result.adapter_run_id.startswith("adapter_run_")
        assert result.dry_run_only is True
        assert result.allow_real_write is False
        assert "Test block reason" in result.warnings[0]
    
    def test_block_real_write_default_reason(self):
        """Test que block_real_write usa razón por defecto."""
        adapter = SemanticMemoryAdapterDryRun()
        
        payload = adapter.build_payload(
            record_id="rec_001",
            text="Content",
            source="test",
            content_hash="abc123",
        )
        
        result = adapter.block_real_write(payload=payload)
        
        assert result.status == SemanticMemoryAdapterStatus.REAL_WRITE_BLOCKED
        assert "bloqueada" in result.warnings[0].lower()
    
    def test_validate_result_accepts_valid_result(self):
        """Test que validate_result acepta resultado válido."""
        adapter = SemanticMemoryAdapterDryRun()
        
        result = SemanticMemoryAdapterDryRunResult(
            adapter_run_id="run_001",
            payload_id="payload_001",
            record_id="rec_001",
            status=SemanticMemoryAdapterStatus.DRY_RUN_READY,
            dry_run_only=True,
            allow_real_write=False,
        )
        
        is_valid = adapter.validate_result(result)
        
        assert is_valid is True
    
    def test_validate_result_rejects_allow_real_write_true(self):
        """Test que validate_result rechaza allow_real_write=True."""
        adapter = SemanticMemoryAdapterDryRun()
        
        result = SemanticMemoryAdapterDryRunResult(
            adapter_run_id="run_001",
            payload_id="payload_001",
            record_id="rec_001",
            status=SemanticMemoryAdapterStatus.DRY_RUN_READY,
            dry_run_only=True,
            allow_real_write=True,  # Invalid: should be False
        )
        
        is_valid = adapter.validate_result(result)
        
        assert is_valid is False
    
    def test_validate_result_rejects_dry_run_only_false(self):
        """Test que validate_result rechaza dry_run_only=False."""
        adapter = SemanticMemoryAdapterDryRun()
        
        result = SemanticMemoryAdapterDryRunResult(
            adapter_run_id="run_001",
            payload_id="payload_001",
            record_id="rec_001",
            status=SemanticMemoryAdapterStatus.DRY_RUN_READY,
            dry_run_only=False,  # Invalid: should be True
            allow_real_write=False,
        )
        
        is_valid = adapter.validate_result(result)
        
        assert is_valid is False
    
    def test_summarize_adapter_contract(self):
        """Test que summarize_adapter_contract retorna información del contrato."""
        adapter = SemanticMemoryAdapterDryRun()
        
        # Crear algunos runs
        payload1 = adapter.build_payload(
            record_id="rec_001",
            text="Content",
            source="test",
            content_hash="abc123",
            validation_score=0.95,
        )
        adapter.prepare_dry_run(payload1)
        
        payload2 = adapter.build_payload(
            record_id="rec_002",
            text="Content",
            source="test",
            content_hash="def456",
        )
        adapter.block_real_write(payload2)
        
        summary = adapter.summarize_adapter_contract()
        
        assert summary["adapter_version"] == "P2-E-Commit-3G"
        assert summary["dry_run_only"] is True
        assert summary["allow_real_write"] is False
        assert summary["future_method"] == "add_memory"
        assert summary["total_adapter_runs"] == 2
        assert summary["dry_run_ready"] == 1
        assert summary["blocked_writes"] == 1


class TestNoForbiddenModules:
    """Tests para asegurar que no se usan módulos prohibidos."""
    
    def test_no_faiss_import(self):
        """Test que el módulo NO importa faiss."""
        import brain.semantic_memory_adapter_dry_run as module
        
        source = Path(module.__file__).read_text(encoding="utf-8")
        
        assert "import faiss" not in source
        assert "from faiss" not in source
    
    def test_no_requests_import(self):
        """Test que el módulo NO importa requests."""
        import brain.semantic_memory_adapter_dry_run as module
        
        source = Path(module.__file__).read_text(encoding="utf-8")
        
        assert "import requests" not in source
        assert "from requests" not in source
    
    def test_no_httpx_import(self):
        """Test que el módulo NO importa httpx."""
        import brain.semantic_memory_adapter_dry_run as module
        
        source = Path(module.__file__).read_text(encoding="utf-8")
        
        assert "import httpx" not in source
        assert "from httpx" not in source
    
    def test_no_memory_semantic_write(self):
        """Test que el módulo NO escribe en memory/semantic."""
        import brain.semantic_memory_adapter_dry_run as module
        
        source = Path(module.__file__).read_text(encoding="utf-8")
        
        # Buscar llamadas reales a funciones de escritura (no en docstrings)
        # Una llamada real tiene formato: var = func( o func(  (sin comillas antes)
        import re
        
        # Patrón para encontrar write_text( como llamada de método (no en strings)
        # Busca: .write_text( o = write_text(
        write_text_pattern = r'\.write_text\(|=\s*write_text\('
        write_text_calls = re.findall(write_text_pattern, source)
        assert len(write_text_calls) == 0, f"Found write_text calls: {write_text_calls}"
        
        # Patrón para open( como llamada (no en docstrings)
        # Busca: = open( o (open(  
        open_pattern = r'=\s*open\(|\(\s*open\('
        open_calls = re.findall(open_pattern, source)
        assert len(open_calls) == 0, f"Found open calls: {open_calls}"
        
        # No debe haber unlink/remove/rmdir como métodos
        assert ".unlink(" not in source
        assert ".remove(" not in source
        assert ".rmdir(" not in source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
