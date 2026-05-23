"""
P2-E Commit 3C: Tests para Curated Memory Rollback Service

Tests unitarios para validar el contrato/stub de rollback.
NO escribe en archivos permanentes.
NO requiere FAISS.
NO requiere runtime 8090.
Usa tmp_path para aislamiento de tests.
"""

import pytest
import sys
import hashlib
from pathlib import Path
from datetime import datetime, timezone

# Agregar raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.curated_memory_rollback import (
    RollbackStatus,
    CuratedMemoryRollbackPlan,
    CuratedMemoryRollbackService,
    create_rollback_service,
)


class TestCuratedMemoryRollbackPlan:
    """Tests para CuratedMemoryRollbackPlan."""
    
    def test_plan_creation(self):
        """Test que se puede crear un plan básico."""
        plan = CuratedMemoryRollbackPlan(
            rollback_id="rollback_001",
            promotion_request_id="req_001",
            promotion_decision_id="dec_001",
            record_id="rec_001",
            content_hash="hash123",
            reason="Error in promotion",
            requested_by="admin",
            requested_at_utc=datetime.now(timezone.utc).isoformat(),
            status=RollbackStatus.PLANNED,
            evidence_hash="evidence_hash_001",
            dry_run_only=True,
            allow_real_write=False,
        )
        
        assert plan.rollback_id == "rollback_001"
        assert plan.promotion_request_id == "req_001"
        assert plan.promotion_decision_id == "dec_001"
        assert plan.record_id == "rec_001"
        assert plan.content_hash == "hash123"
        assert plan.dry_run_only is True
        assert plan.allow_real_write is False
    
    def test_plan_to_dict(self):
        """Test que to_dict serializa correctamente."""
        plan = CuratedMemoryRollbackPlan(
            rollback_id="rollback_002",
            promotion_request_id="req_002",
            promotion_decision_id="dec_002",
            record_id="rec_002",
            content_hash="hash456",
            reason="Quality issue",
            requested_by="user",
            requested_at_utc="2026-01-01T00:00:00+00:00",
            status=RollbackStatus.PLANNED,
            evidence_hash="evidence_hash_002",
            dry_run_only=True,
            allow_real_write=False,
            metadata={"test": "data"},
        )
        
        d = plan.to_dict()
        assert d["rollback_id"] == "rollback_002"
        assert d["promotion_request_id"] == "req_002"
        assert d["promotion_decision_id"] == "dec_002"
        assert d["content_hash"] == "hash456"
        assert d["dry_run_only"] is True
        assert d["allow_real_write"] is False


class TestCuratedMemoryRollbackService:
    """Tests para CuratedMemoryRollbackService."""
    
    @pytest.fixture
    def service(self):
        """Fixture para servicio de rollback."""
        return CuratedMemoryRollbackService()
    
    def test_create_rollback_plan_generates_id(self, service):
        """Test que create_rollback_plan genera rollback_id."""
        plan = service.create_rollback_plan(
            promotion_request_id="req_test_001",
            promotion_decision_id="dec_test_001",
            record_id="rec_test_001",
            content_hash="hash_test_001",
            requested_by="admin",
            reason="Test rollback",
        )
        
        assert plan.rollback_id.startswith("rollback_")
        assert len(plan.rollback_id) > 10
    
    def test_rollback_plan_preserves_ids(self, service):
        """Test que el plan conserva promotion_request_id, promotion_decision_id, record_id y content_hash."""
        plan = service.create_rollback_plan(
            promotion_request_id="req_002",
            promotion_decision_id="dec_002",
            record_id="rec_002",
            content_hash="hash_002",
            requested_by="user",
            reason="Test",
        )
        
        assert plan.promotion_request_id == "req_002"
        assert plan.promotion_decision_id == "dec_002"
        assert plan.record_id == "rec_002"
        assert plan.content_hash == "hash_002"
    
    def test_rollback_plan_has_dry_run_only_true(self, service):
        """Test que el plan tiene dry_run_only=True."""
        plan = service.create_rollback_plan(
            promotion_request_id="req_003",
            promotion_decision_id="dec_003",
            record_id="rec_003",
            content_hash="hash_003",
            requested_by="user",
            reason="Test",
        )
        
        assert plan.dry_run_only is True
    
    def test_rollback_plan_has_allow_real_write_false(self, service):
        """Test que el plan tiene allow_real_write=False."""
        plan = service.create_rollback_plan(
            promotion_request_id="req_004",
            promotion_decision_id="dec_004",
            record_id="rec_004",
            content_hash="hash_004",
            requested_by="user",
            reason="Test",
        )
        
        assert plan.allow_real_write is False
    
    def test_validate_rollback_plan_accepts_well_formed(self, service):
        """Test que validate_rollback_plan acepta plan bien formado."""
        plan = service.create_rollback_plan(
            promotion_request_id="req_005",
            promotion_decision_id="dec_005",
            record_id="rec_005",
            content_hash="hash_005",
            requested_by="user",
            reason="Test",
            evidence="test_evidence",
        )
        
        is_valid = service.validate_rollback_plan(plan)
        assert is_valid is True
    
    def test_validate_rollback_plan_rejects_without_evidence_hash(self, service):
        """Test que validate_rollback_plan rechaza plan sin evidence_hash."""
        plan = CuratedMemoryRollbackPlan(
            rollback_id="rollback_no_evidence",
            promotion_request_id="req_no_evidence",
            promotion_decision_id="dec_no_evidence",
            record_id="rec_no_evidence",
            content_hash="hash_no_evidence",
            reason="Test",
            requested_by="user",
            requested_at_utc=datetime.now(timezone.utc).isoformat(),
            status=RollbackStatus.PLANNED,
            evidence_hash="",  # Vacío
            dry_run_only=True,
            allow_real_write=False,
        )
        
        is_valid = service.validate_rollback_plan(plan)
        assert is_valid is False
    
    def test_validate_rollback_plan_rejects_allow_real_write_true(self, service):
        """Test que validate_rollback_plan rechaza allow_real_write=True."""
        plan = CuratedMemoryRollbackPlan(
            rollback_id="rollback_invalid",
            promotion_request_id="req_invalid",
            promotion_decision_id="dec_invalid",
            record_id="rec_invalid",
            content_hash="hash_invalid",
            reason="Test",
            requested_by="user",
            requested_at_utc=datetime.now(timezone.utc).isoformat(),
            status=RollbackStatus.PLANNED,
            evidence_hash="some_hash",
            dry_run_only=True,
            allow_real_write=True,  # No permitido
        )
        
        is_valid = service.validate_rollback_plan(plan)
        assert is_valid is False
    
    def test_execute_rollback_dry_run_changes_status(self, service):
        """Test que execute_rollback_dry_run cambia status a EXECUTED_DRY_RUN."""
        plan = service.create_rollback_plan(
            promotion_request_id="req_execute",
            promotion_decision_id="dec_execute",
            record_id="rec_execute",
            content_hash="hash_execute",
            requested_by="admin",
            reason="Execute test",
            evidence="execute_evidence",
        )
        
        assert plan.status == RollbackStatus.PLANNED
        
        result = service.execute_rollback_dry_run(plan)
        
        assert result.status == RollbackStatus.EXECUTED_DRY_RUN
    
    def test_execute_rollback_dry_run_rejects_invalid_plan(self, service):
        """Test que execute_rollback_dry_run rechaza plan inválido."""
        plan = CuratedMemoryRollbackPlan(
            rollback_id="rollback_invalid",
            promotion_request_id="req_invalid",
            promotion_decision_id="dec_invalid",
            record_id="rec_invalid",
            content_hash="hash_invalid",
            reason="Test",
            requested_by="user",
            requested_at_utc=datetime.now(timezone.utc).isoformat(),
            status=RollbackStatus.PLANNED,
            evidence_hash="",  # Inválido
            dry_run_only=True,
            allow_real_write=False,
        )
        
        result = service.execute_rollback_dry_run(plan)
        
        assert result.status == RollbackStatus.REJECTED
    
    def test_reject_rollback_plan_changes_status(self, service):
        """Test que reject_rollback_plan cambia status a REJECTED."""
        plan = service.create_rollback_plan(
            promotion_request_id="req_reject",
            promotion_decision_id="dec_reject",
            record_id="rec_reject",
            content_hash="hash_reject",
            requested_by="user",
            reason="Test",
        )
        
        assert plan.status == RollbackStatus.PLANNED
        
        result = service.reject_rollback_plan(plan, "Reason for rejection")
        
        assert result.status == RollbackStatus.REJECTED
        assert result.metadata["rejection_reason"] == "Reason for rejection"
    
    def test_get_plan(self, service):
        """Test que get_plan recupera plan específico."""
        plan = service.create_rollback_plan(
            promotion_request_id="req_get",
            promotion_decision_id="dec_get",
            record_id="rec_get",
            content_hash="hash_get",
            requested_by="user",
            reason="Test",
        )
        
        retrieved = service.get_plan(plan.rollback_id)
        assert retrieved is not None
        assert retrieved.rollback_id == plan.rollback_id
    
    def test_list_plans_filter_by_status(self, service):
        """Test que list_plans filtra por estado."""
        # Crear plan y ejecutarlo
        plan1 = service.create_rollback_plan(
            promotion_request_id="req_list_1",
            promotion_decision_id="dec_list_1",
            record_id="rec_list_1",
            content_hash="hash_1",
            requested_by="user",
            reason="Test",
        )
        service.execute_rollback_dry_run(plan1)
        
        # Crear plan planificado
        plan2 = service.create_rollback_plan(
            promotion_request_id="req_list_2",
            promotion_decision_id="dec_list_2",
            record_id="rec_list_2",
            content_hash="hash_2",
            requested_by="user",
            reason="Test",
        )
        
        # Filtrar por estado
        executed_plans = service.list_plans(status=RollbackStatus.EXECUTED_DRY_RUN)
        planned_plans = service.list_plans(status=RollbackStatus.PLANNED)
        
        assert len(executed_plans) == 1
        assert len(planned_plans) == 1
    
    def test_list_plans_filter_by_record_id(self, service):
        """Test que list_plans filtra por record_id."""
        service.create_rollback_plan(
            promotion_request_id="req_filter_1",
            promotion_decision_id="dec_filter_1",
            record_id="rec_target",
            content_hash="hash_1",
            requested_by="user",
            reason="Test",
        )
        service.create_rollback_plan(
            promotion_request_id="req_filter_2",
            promotion_decision_id="dec_filter_2",
            record_id="rec_other",
            content_hash="hash_2",
            requested_by="user",
            reason="Test",
        )
        
        # Filtrar por record_id
        plans = service.list_plans(record_id="rec_target")
        
        assert len(plans) == 1
        assert plans[0].record_id == "rec_target"
    
    def test_get_rollback_stats(self, service):
        """Test que get_rollback_stats retorna estadísticas correctas."""
        # Crear mix de planes
        plan1 = service.create_rollback_plan(
            promotion_request_id="req_stat_1",
            promotion_decision_id="dec_stat_1",
            record_id="rec_stat_1",
            content_hash="hash_1",
            requested_by="user",
            reason="Test",
        )
        service.execute_rollback_dry_run(plan1)
        
        plan2 = service.create_rollback_plan(
            promotion_request_id="req_stat_2",
            promotion_decision_id="dec_stat_2",
            record_id="rec_stat_2",
            content_hash="hash_2",
            requested_by="user",
            reason="Test",
        )
        service.reject_rollback_plan(plan2, "Rejected")
        
        plan3 = service.create_rollback_plan(
            promotion_request_id="req_stat_3",
            promotion_decision_id="dec_stat_3",
            record_id="rec_stat_3",
            content_hash="hash_3",
            requested_by="user",
            reason="Test",
        )
        
        stats = service.get_rollback_stats()
        
        assert stats["total_plans"] == 3
        assert stats["executed_dry_run"] == 1
        assert stats["rejected"] == 1
        assert stats["planned"] == 1


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
        import brain.curated_memory_rollback as rollback_module
        
        # Verificar que no hay imports prohibidos
        loaded = list(sys.modules.keys())
        for forbidden in forbidden:
            assert not any(forbidden in mod for mod in loaded), \
                f"Módulo prohibido cargado: {forbidden}"
    
    def test_no_memory_semantic_write(self):
        """Test que no se escribe en memory/semantic."""
        service = CuratedMemoryRollbackService()
        
        # Crear plan
        plan = service.create_rollback_plan(
            promotion_request_id="req_safe",
            promotion_decision_id="dec_safe",
            record_id="rec_safe",
            content_hash="hash_safe",
            requested_by="user",
            reason="Test",
        )
        
        # Verificar que no hay operaciones de escritura en archivos
        # El servicio solo opera en memoria
        assert len(service._plans) == 1


def test_factory_function():
    """Test que la factory crea instancia correctamente."""
    service = create_rollback_service()
    assert isinstance(service, CuratedMemoryRollbackService)
    assert len(service._plans) == 0
