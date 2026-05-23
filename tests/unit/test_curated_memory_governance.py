"""
P2-E Commit 3A: Tests para Curated Memory Governance Service

Tests unitarios para validar el contrato/stub de governance.
NO escribe en archivos.
NO requiere FAISS.
NO requiere runtime 8090.
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timezone

# Agregar raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.curated_memory_governance import (
    ApprovalStatus,
    PromotionApprovalRequest,
    PromotionApprovalDecision,
    CuratedMemoryGovernanceService,
    create_governance_service,
)


class TestPromotionApprovalRequest:
    """Tests para PromotionApprovalRequest."""
    
    def test_request_creation(self):
        """Test que se puede crear un request básico."""
        request = PromotionApprovalRequest(
            request_id="req_001",
            plan_id="plan_001",
            record_id="rec_001",
            content_hash="hash123",
            source="test",
            validation_score=0.85,
            requested_by="test_user",
            requested_at_utc=datetime.now(timezone.utc).isoformat(),
            reason="Test request",
            dry_run_only=True,
            status=ApprovalStatus.PENDING,
        )
        
        assert request.request_id == "req_001"
        assert request.plan_id == "plan_001"
        assert request.record_id == "rec_001"
        assert request.content_hash == "hash123"
        assert request.dry_run_only is True
        assert request.status == ApprovalStatus.PENDING
    
    def test_request_to_dict(self):
        """Test que to_dict serializa correctamente."""
        request = PromotionApprovalRequest(
            request_id="req_002",
            plan_id="plan_002",
            record_id="rec_002",
            content_hash="hash456",
            source="test",
            validation_score=0.9,
            requested_by="test_user",
            requested_at_utc="2026-01-01T00:00:00+00:00",
            reason="Test",
            dry_run_only=True,
            status=ApprovalStatus.PENDING,
        )
        
        d = request.to_dict()
        assert d["request_id"] == "req_002"
        assert d["plan_id"] == "plan_002"
        assert d["content_hash"] == "hash456"
        assert d["dry_run_only"] is True
        assert d["status"] == "PENDING"


class TestPromotionApprovalDecision:
    """Tests para PromotionApprovalDecision."""
    
    def test_decision_creation_approved(self):
        """Test creación de decisión aprobada."""
        decision = PromotionApprovalDecision(
            decision_id="dec_001",
            request_id="req_001",
            status=ApprovalStatus.APPROVED,
            decided_by="approver_001",
            decided_at_utc=datetime.now(timezone.utc).isoformat(),
            reason="Approved for promotion",
            evidence_hash="abc123hash",
            allow_real_write=False,  # SIEMPRE False
        )
        
        assert decision.decision_id == "dec_001"
        assert decision.status == ApprovalStatus.APPROVED
        assert decision.allow_real_write is False
    
    def test_decision_to_dict(self):
        """Test que to_dict serializa correctamente."""
        decision = PromotionApprovalDecision(
            decision_id="dec_002",
            request_id="req_002",
            status=ApprovalStatus.REJECTED,
            decided_by="rejector_001",
            decided_at_utc="2026-01-01T00:00:00+00:00",
            reason="Low quality",
            evidence_hash="def456hash",
            allow_real_write=False,
        )
        
        d = decision.to_dict()
        assert d["decision_id"] == "dec_002"
        assert d["status"] == "REJECTED"
        assert d["allow_real_write"] is False


class TestCuratedMemoryGovernanceService:
    """Tests para CuratedMemoryGovernanceService."""
    
    @pytest.fixture
    def service(self):
        """Fixture para servicio de governance."""
        return CuratedMemoryGovernanceService()
    
    @pytest.fixture
    def mock_plan(self):
        """Mock de un plan de promoción."""
        class MockPlan:
            record_id = "rec_test_001"
            content_hash = "hash_test_001"
            source = "test_source"
            validation_score = 0.85
        return MockPlan()
    
    def test_create_approval_request_generates_id(self, service, mock_plan):
        """Test que create_approval_request genera request_id."""
        request = service.create_approval_request(
            plan=mock_plan,
            requested_by="test_user",
            reason="Test promotion",
        )
        
        assert request.request_id.startswith("req_")
        assert len(request.request_id) > 10
    
    def test_request_preserves_plan_data(self, service, mock_plan):
        """Test que request conserva plan_id, record_id, content_hash."""
        request = service.create_approval_request(
            plan=mock_plan,
            requested_by="test_user",
            reason="Test",
        )
        
        assert request.plan_id == "rec_test_001"
        assert request.record_id == "rec_test_001"
        assert request.content_hash == "hash_test_001"
    
    def test_request_has_dry_run_only_true(self, service, mock_plan):
        """Test que request tiene dry_run_only=True."""
        request = service.create_approval_request(
            plan=mock_plan,
            requested_by="test_user",
            reason="Test",
        )
        
        assert request.dry_run_only is True
    
    def test_approve_request_produces_approved_status(self, service, mock_plan):
        """Test que approve_request produce status APPROVED."""
        request = service.create_approval_request(
            plan=mock_plan,
            requested_by="test_user",
            reason="Test",
        )
        
        decision = service.approve_request(
            request=request,
            decided_by="approver",
            reason="Good quality",
        )
        
        assert decision.status == ApprovalStatus.APPROVED
        assert request.status == ApprovalStatus.APPROVED
    
    def test_approve_request_maintains_allow_real_write_false(self, service, mock_plan):
        """Test que approve_request mantiene allow_real_write=False."""
        request = service.create_approval_request(
            plan=mock_plan,
            requested_by="test_user",
            reason="Test",
        )
        
        decision = service.approve_request(
            request=request,
            decided_by="approver",
            reason="Good quality",
        )
        
        assert decision.allow_real_write is False
    
    def test_reject_request_produces_rejected_status(self, service, mock_plan):
        """Test que reject_request produce status REJECTED."""
        request = service.create_approval_request(
            plan=mock_plan,
            requested_by="test_user",
            reason="Test",
        )
        
        decision = service.reject_request(
            request=request,
            decided_by="rejector",
            reason="Low quality",
        )
        
        assert decision.status == ApprovalStatus.REJECTED
        assert request.status == ApprovalStatus.REJECTED
    
    def test_validate_decision_accepts_well_formed(self, service, mock_plan):
        """Test que validate_decision acepta decisiones bien formadas."""
        request = service.create_approval_request(
            plan=mock_plan,
            requested_by="test_user",
            reason="Test",
        )
        
        decision = service.approve_request(
            request=request,
            decided_by="approver",
            reason="Good quality",
        )
        
        is_valid = service.validate_decision(decision)
        assert is_valid is True
    
    def test_validate_decision_rejects_without_evidence_hash(self, service):
        """Test que validate_decision rechaza decision sin evidence_hash."""
        decision = PromotionApprovalDecision(
            decision_id="dec_003",
            request_id="req_003",
            status=ApprovalStatus.APPROVED,
            decided_by="approver",
            decided_at_utc=datetime.now(timezone.utc).isoformat(),
            reason="Test",
            evidence_hash="",  # Vacío
            allow_real_write=False,
        )
        
        is_valid = service.validate_decision(decision)
        assert is_valid is False
    
    def test_validate_decision_rejects_allow_real_write_true(self, service, mock_plan):
        """Test que validate_decision rechaza allow_real_write=True."""
        decision = PromotionApprovalDecision(
            decision_id="dec_004",
            request_id="req_004",
            status=ApprovalStatus.APPROVED,
            decided_by="approver",
            decided_at_utc=datetime.now(timezone.utc).isoformat(),
            reason="Test",
            evidence_hash="somehash",
            allow_real_write=True,  # No permitido
        )
        
        is_valid = service.validate_decision(decision)
        assert is_valid is False
    
    def test_get_request(self, service, mock_plan):
        """Test que get_request recupera solicitud."""
        request = service.create_approval_request(
            plan=mock_plan,
            requested_by="test_user",
            reason="Test",
        )
        
        retrieved = service.get_request(request.request_id)
        assert retrieved is not None
        assert retrieved.request_id == request.request_id
    
    def test_get_decision(self, service, mock_plan):
        """Test que get_decision recupera decisión."""
        request = service.create_approval_request(
            plan=mock_plan,
            requested_by="test_user",
            reason="Test",
        )
        
        decision = service.approve_request(
            request=request,
            decided_by="approver",
            reason="Good",
        )
        
        retrieved = service.get_decision(decision.decision_id)
        assert retrieved is not None
        assert retrieved.decision_id == decision.decision_id
    
    def test_get_pending_requests(self, service, mock_plan):
        """Test que get_pending_requests retorna solo pendientes."""
        # Crear dos solicitudes
        req1 = service.create_approval_request(
            plan=mock_plan,
            requested_by="user1",
            reason="Test1",
        )
        req2 = service.create_approval_request(
            plan=mock_plan,
            requested_by="user2",
            reason="Test2",
        )
        
        # Aprobar una
        service.approve_request(req1, "approver", "Approved")
        
        # Verificar pendientes
        pending = service.get_pending_requests()
        assert len(pending) == 1
        assert pending[0].request_id == req2.request_id


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
        import brain.curated_memory_governance as gov_module
        
        # Verificar que no hay imports prohibidos
        loaded = list(sys.modules.keys())
        for forbidden in forbidden:
            assert not any(forbidden in mod for mod in loaded), \
                f"Módulo prohibido cargado: {forbidden}"
    
    def test_no_file_writes_in_memory_semantic(self):
        """Test que no se escriben archivos en memory/semantic."""
        from brain.curated_memory_governance import CuratedMemoryGovernanceService
        
        # Crear mock plan
        class MockPlan:
            record_id = "rec_test_001"
            content_hash = "hash_test_001"
            source = "test_source"
            validation_score = 0.85
        
        service = CuratedMemoryGovernanceService()
        
        # Verificar directorio memory/semantic
        semantic_dir = Path("memory/semantic")
        if semantic_dir.exists():
            initial_files = set(semantic_dir.glob("*"))
            
            # Ejecutar operaciones
            request = service.create_approval_request(
                plan=MockPlan(),
                requested_by="test_user",
                reason="Test",
            )
            service.approve_request(request, "approver", "Good")
            
            # Verificar que no hay cambios
            final_files = set(semantic_dir.glob("*"))
            assert initial_files == final_files, \
                "Se modificaron archivos en memory/semantic"


def test_factory_function():
    """Test que la factory crea instancia correctamente."""
    service = create_governance_service()
    assert isinstance(service, CuratedMemoryGovernanceService)
    assert len(service._requests) == 0
    assert len(service._decisions) == 0
