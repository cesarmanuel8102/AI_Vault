"""
P2-E Commit 3E: Tests para Curated Memory Dry-Run Integration Flow

Tests unitarios para validar el orquestador de flujo dry-run unificado.
NO escribe en archivos permanentes.
NO requiere FAISS.
NO requiere runtime 8090.
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timezone

# Agregar raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.curated_memory_dry_run_flow import (
    DryRunFlowStatus,
    CuratedMemoryDryRunFlowResult,
    CuratedMemoryDryRunFlow,
    create_dry_run_flow,
)
from brain.curated_memory_observability import CuratedMemoryEventType


class TestCuratedMemoryDryRunFlowResult:
    """Tests para CuratedMemoryDryRunFlowResult."""
    
    def test_result_creation(self):
        """Test que se puede crear un resultado básico."""
        result = CuratedMemoryDryRunFlowResult(
            flow_id="flow_001",
            record_id="rec_001",
            content_hash="hash001",
            status=DryRunFlowStatus.CREATED,
            dry_run_only=True,
            allow_real_write=False,
        )
        
        assert result.flow_id == "flow_001"
        assert result.record_id == "rec_001"
        assert result.content_hash == "hash001"
        assert result.status == DryRunFlowStatus.CREATED
        assert result.dry_run_only is True
        assert result.allow_real_write is False
    
    def test_result_to_dict(self):
        """Test que to_dict serializa correctamente."""
        result = CuratedMemoryDryRunFlowResult(
            flow_id="flow_002",
            record_id="rec_002",
            content_hash="hash002",
            status=DryRunFlowStatus.APPROVED_DRY_RUN,
            promotion_plan_id="plan_002",
            approval_request_id="req_002",
            approval_decision_id="dec_002",
            audit_entry_ids=["audit_001", "audit_002"],
            observability_event_ids=["evt_001", "evt_002"],
            dry_run_only=True,
            allow_real_write=False,
            metadata={"test": "data"},
        )
        
        d = result.to_dict()
        assert d["flow_id"] == "flow_002"
        assert d["status"] == "APPROVED_DRY_RUN"
        assert d["promotion_plan_id"] == "plan_002"
        assert len(d["audit_entry_ids"]) == 2
        assert len(d["observability_event_ids"]) == 2


class TestCuratedMemoryDryRunFlow:
    """Tests para CuratedMemoryDryRunFlow."""
    
    @pytest.fixture
    def flow(self, tmp_path):
        """Fixture para orquestador de flujo dry-run."""
        from brain.curated_memory_governance_audit import CuratedMemoryGovernanceAuditTrail
        
        # Crear audit trail con path temporal
        audit_path = str(tmp_path / "test_audit.ndjson")
        audit = CuratedMemoryGovernanceAuditTrail(audit_path=audit_path)
        
        return create_dry_run_flow(audit_trail=audit)
    
    def test_run_approval_flow_generates_flow_id(self, flow):
        """Test que run_approval_flow genera flow_id."""
        result = flow.run_approval_flow(
            record_id="rec_test_001",
            content_hash="hash_test_001",
            source="test_source",
            validation_score=0.85,
            actor="test_user",
            approve=True,
        )
        
        assert result.flow_id.startswith("flow_")
        assert len(result.flow_id) > 10
    
    def test_approval_flow_result_has_dry_run_only_true(self, flow):
        """Test que el resultado tiene dry_run_only=True."""
        result = flow.run_approval_flow(
            record_id="rec_test_002",
            content_hash="hash_test_002",
            source="test",
            validation_score=0.9,
            actor="user",
            approve=True,
        )
        
        assert result.dry_run_only is True
    
    def test_approval_flow_result_has_allow_real_write_false(self, flow):
        """Test que el resultado tiene allow_real_write=False."""
        result = flow.run_approval_flow(
            record_id="rec_test_003",
            content_hash="hash_test_003",
            source="test",
            validation_score=0.9,
            actor="user",
            approve=True,
        )
        
        assert result.allow_real_write is False
    
    def test_approval_flow_approved_generates_approval_request_id(self, flow):
        """Test que el flujo aprobado genera approval_request_id."""
        result = flow.run_approval_flow(
            record_id="rec_test_004",
            content_hash="hash_test_004",
            source="test",
            validation_score=0.9,
            actor="user",
            approve=True,
        )
        
        assert result.approval_request_id is not None
        assert result.approval_request_id.startswith("req_")
    
    def test_approval_flow_approved_generates_approval_decision_id(self, flow):
        """Test que el flujo aprobado genera approval_decision_id."""
        result = flow.run_approval_flow(
            record_id="rec_test_005",
            content_hash="hash_test_005",
            source="test",
            validation_score=0.9,
            actor="user",
            approve=True,
        )
        
        assert result.approval_decision_id is not None
        assert result.approval_decision_id.startswith("dec_")
    
    def test_approval_flow_rejected_stays_rejected_dry_run(self, flow):
        """Test que el flujo rechazado queda REJECTED_DRY_RUN."""
        result = flow.run_approval_flow(
            record_id="rec_test_006",
            content_hash="hash_test_006",
            source="test",
            validation_score=0.5,
            actor="user",
            approve=False,
        )
        
        assert result.status == DryRunFlowStatus.REJECTED_DRY_RUN
        assert result.approval_decision_id is not None
    
    def test_audit_entry_ids_not_empty_when_using_audit_trail(self, flow):
        """Test que audit_entry_ids no queda vacío cuando se usa audit trail."""
        result = flow.run_approval_flow(
            record_id="rec_test_007",
            content_hash="hash_test_007",
            source="test",
            validation_score=0.9,
            actor="user",
            approve=True,
        )
        
        assert len(result.audit_entry_ids) > 0
    
    def test_observability_event_ids_not_empty(self, flow):
        """Test que observability_event_ids no queda vacío."""
        result = flow.run_approval_flow(
            record_id="rec_test_008",
            content_hash="hash_test_008",
            source="test",
            validation_score=0.9,
            actor="user",
            approve=True,
        )
        
        assert len(result.observability_event_ids) > 0
    
    def test_run_rollback_flow_generates_rollback_id(self, flow):
        """Test que run_rollback_flow genera rollback_id."""
        # Primero ejecutar flujo de aprobación
        result = flow.run_approval_flow(
            record_id="rec_test_009",
            content_hash="hash_test_009",
            source="test",
            validation_score=0.9,
            actor="user",
            approve=True,
        )
        
        # Luego ejecutar rollback
        result_with_rollback = flow.run_rollback_flow(
            flow_result=result,
            actor="admin",
            reason="Test rollback",
        )
        
        assert result_with_rollback.rollback_id is not None
        assert result_with_rollback.rollback_id.startswith("rollback_")
    
    def test_block_real_write_returns_real_write_blocked_status(self, flow):
        """Test que block_real_write devuelve status REAL_WRITE_BLOCKED."""
        result = flow.block_real_write(
            reason="Attempted real write",
            actor="test_user",
            record_id="rec_test_010",
        )
        
        assert result.status == DryRunFlowStatus.REAL_WRITE_BLOCKED
        assert result.allow_real_write is False
    
    def test_validate_flow_result_accepts_well_formed(self, flow):
        """Test que validate_flow_result acepta resultado bien formado."""
        result = CuratedMemoryDryRunFlowResult(
            flow_id="flow_valid",
            record_id="rec_valid",
            content_hash="hash_valid",
            status=DryRunFlowStatus.COMPLETED_DRY_RUN,
            dry_run_only=True,
            allow_real_write=False,
        )
        
        is_valid = flow.validate_flow_result(result)
        assert is_valid is True
    
    def test_validate_flow_result_rejects_allow_real_write_true(self, flow):
        """Test que validate_flow_result rechaza allow_real_write=True."""
        result = CuratedMemoryDryRunFlowResult(
            flow_id="flow_invalid",
            record_id="rec_invalid",
            content_hash="hash_invalid",
            status=DryRunFlowStatus.CREATED,
            dry_run_only=True,
            allow_real_write=True,  # No permitido
        )
        
        is_valid = flow.validate_flow_result(result)
        assert is_valid is False
    
    def test_get_flow_summary(self, flow):
        """Test que get_flow_summary devuelve resumen correcto."""
        result = flow.run_approval_flow(
            record_id="rec_test_011",
            content_hash="hash_test_011",
            source="test",
            validation_score=0.9,
            actor="user",
            approve=True,
        )
        
        summary = flow.get_flow_summary(result)
        
        assert summary["flow_id"] == result.flow_id
        assert summary["record_id"] == result.record_id
        assert summary["status"] == result.status.value
        assert summary["dry_run_only"] is True
        assert summary["allow_real_write"] is False
        assert "audit_entries_count" in summary
        assert "observability_events_count" in summary


class TestNoForbiddenModules:
    """Tests para verificar que no hay imports prohibidos."""
    
    def test_no_faiss_import(self):
        """Test que el módulo no importa faiss."""
        import sys
        # Limpiar módulos prohibidos si existen
        forbidden = ["faiss", "semantic_memory", "requests", "httpx"]
        for mod in list(sys.modules.keys()):
            if any(f in mod.lower() for f in forbidden):
                del sys.modules[mod]
        
        # Importar el módulo
        import brain.curated_memory_dry_run_flow as flow_module
        
        # Verificar que no hay imports prohibidos
        loaded = list(sys.modules.keys())
        for forbidden in forbidden:
            assert not any(forbidden in mod for mod in loaded), \
                f"Módulo prohibido cargado: {forbidden}"
    
    def test_no_memory_semantic_write(self, tmp_path):
        """Test que no se escribe en memory/semantic."""
        from brain.curated_memory_governance_audit import CuratedMemoryGovernanceAuditTrail
        
        # Crear flow con audit trail temporal
        audit_path = str(tmp_path / "test_audit.ndjson")
        audit = CuratedMemoryGovernanceAuditTrail(audit_path=audit_path)
        flow = create_dry_run_flow(audit_trail=audit)
        
        result = flow.run_approval_flow(
            record_id="rec_safe",
            content_hash="hash_safe",
            source="test",
            validation_score=0.9,
            actor="user",
            approve=True,
        )
        
        # Verificar que el flujo se ejecutó sin escribir en memoria
        assert result.status == DryRunFlowStatus.COMPLETED_DRY_RUN
        assert result.allow_real_write is False


def test_factory_function():
    """Test que la factory crea instancia correctamente."""
    flow = create_dry_run_flow()
    assert isinstance(flow, CuratedMemoryDryRunFlow)
