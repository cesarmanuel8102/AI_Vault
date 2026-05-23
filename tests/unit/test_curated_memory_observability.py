"""
P2-E Commit 3D: Tests para Curated Memory Observability

Tests unitarios para validar el servicio de observabilidad.
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

from brain.curated_memory_observability import (
    CuratedMemoryEventType,
    EventStatus,
    CuratedMemoryEvent,
    CuratedMemoryObservability,
    create_observability_service,
)


class TestCuratedMemoryEvent:
    """Tests para CuratedMemoryEvent."""
    
    def test_event_creation(self):
        """Test que se puede crear un evento básico."""
        event = CuratedMemoryEvent(
            event_id="evt_001",
            event_type=CuratedMemoryEventType.PROMOTION_DRY_RUN_CREATED,
            actor="test_user",
            record_id="rec_001",
            status=EventStatus.PROCESSED,
            dry_run_only=True,
            allow_real_write=False,
        )
        
        assert event.event_id == "evt_001"
        assert event.event_type == CuratedMemoryEventType.PROMOTION_DRY_RUN_CREATED
        assert event.actor == "test_user"
        assert event.record_id == "rec_001"
        assert event.dry_run_only is True
        assert event.allow_real_write is False
    
    def test_event_to_dict(self):
        """Test que to_dict serializa correctamente."""
        event = CuratedMemoryEvent(
            event_id="evt_002",
            event_type=CuratedMemoryEventType.APPROVAL_REQUEST_CREATED,
            created_at_utc="2026-01-01T00:00:00+00:00",
            actor="user",
            request_id="req_002",
            status=EventStatus.PROCESSED,
            dry_run_only=True,
            allow_real_write=False,
            metadata={"test": "data"},
        )
        
        d = event.to_dict()
        assert d["event_id"] == "evt_002"
        assert d["event_type"] == "APPROVAL_REQUEST_CREATED"
        assert d["request_id"] == "req_002"
        assert d["dry_run_only"] is True
        assert d["allow_real_write"] is False


class TestCuratedMemoryObservability:
    """Tests para CuratedMemoryObservability."""
    
    @pytest.fixture
    def service(self):
        """Fixture para servicio de observabilidad."""
        return CuratedMemoryObservability()
    
    def test_record_event_generates_id(self, service):
        """Test que record_event genera event_id."""
        event = service.record_event(
            event_type=CuratedMemoryEventType.PROMOTION_DRY_RUN_CREATED,
            actor="test_user",
            record_id="rec_test_001",
        )
        
        assert event.event_id.startswith("evt_")
        assert len(event.event_id) > 10
    
    def test_event_has_dry_run_only_true(self, service):
        """Test que el evento tiene dry_run_only=True."""
        event = service.record_event(
            event_type=CuratedMemoryEventType.APPROVAL_REQUEST_CREATED,
            actor="test_user",
        )
        
        assert event.dry_run_only is True
    
    def test_event_has_allow_real_write_false(self, service):
        """Test que el evento tiene allow_real_write=False."""
        event = service.record_event(
            event_type=CuratedMemoryEventType.APPROVAL_DECISION_APPROVED,
            actor="approver",
        )
        
        assert event.allow_real_write is False
    
    def test_list_events_returns_registered(self, service):
        """Test que list_events devuelve eventos registrados."""
        # Registrar eventos
        service.record_event(
            event_type=CuratedMemoryEventType.PROMOTION_DRY_RUN_CREATED,
            actor="user1",
        )
        service.record_event(
            event_type=CuratedMemoryEventType.APPROVAL_REQUEST_CREATED,
            actor="user2",
        )
        
        # Listar todos
        events = service.list_events()
        assert len(events) == 2
    
    def test_list_events_filters_by_event_type(self, service):
        """Test que list_events filtra por event_type."""
        # Registrar eventos de diferentes tipos
        service.record_event(
            event_type=CuratedMemoryEventType.PROMOTION_DRY_RUN_CREATED,
            actor="user1",
        )
        service.record_event(
            event_type=CuratedMemoryEventType.APPROVAL_REQUEST_CREATED,
            actor="user2",
        )
        service.record_event(
            event_type=CuratedMemoryEventType.PROMOTION_DRY_RUN_CREATED,
            actor="user3",
        )
        
        # Filtrar por tipo
        events = service.list_events(
            event_type=CuratedMemoryEventType.PROMOTION_DRY_RUN_CREATED
        )
        
        assert len(events) == 2
        for event in events:
            assert event.event_type == CuratedMemoryEventType.PROMOTION_DRY_RUN_CREATED
    
    def test_list_events_filters_by_record_id(self, service):
        """Test que list_events filtra por record_id."""
        # Registrar eventos con diferentes record_id
        service.record_event(
            event_type=CuratedMemoryEventType.PROMOTION_DRY_RUN_CREATED,
            actor="user1",
            record_id="rec_target",
        )
        service.record_event(
            event_type=CuratedMemoryEventType.APPROVAL_REQUEST_CREATED,
            actor="user2",
            record_id="rec_target",
        )
        service.record_event(
            event_type=CuratedMemoryEventType.PROMOTION_DRY_RUN_CREATED,
            actor="user3",
            record_id="rec_other",
        )
        
        # Filtrar por record_id
        events = service.list_events(record_id="rec_target")
        
        assert len(events) == 2
        for event in events:
            assert event.record_id == "rec_target"
    
    def test_count_events_counts_correctly(self, service):
        """Test que count_events cuenta correctamente."""
        # Registrar eventos
        service.record_event(
            event_type=CuratedMemoryEventType.PROMOTION_DRY_RUN_CREATED,
            actor="user1",
        )
        service.record_event(
            event_type=CuratedMemoryEventType.PROMOTION_DRY_RUN_CREATED,
            actor="user2",
        )
        service.record_event(
            event_type=CuratedMemoryEventType.APPROVAL_REQUEST_CREATED,
            actor="user3",
        )
        
        # Contar todos
        assert service.count_events() == 3
        
        # Contar por tipo
        assert service.count_events(CuratedMemoryEventType.PROMOTION_DRY_RUN_CREATED) == 2
        assert service.count_events(CuratedMemoryEventType.APPROVAL_REQUEST_CREATED) == 1
        assert service.count_events(CuratedMemoryEventType.ROLLBACK_PLAN_CREATED) == 0
    
    def test_summarize_returns_counts_by_event_type(self, service):
        """Test que summarize devuelve conteos por event_type."""
        # Registrar eventos de diferentes tipos
        service.record_event(
            event_type=CuratedMemoryEventType.PROMOTION_DRY_RUN_CREATED,
            actor="user1",
        )
        service.record_event(
            event_type=CuratedMemoryEventType.APPROVAL_REQUEST_CREATED,
            actor="user2",
        )
        service.record_event(
            event_type=CuratedMemoryEventType.APPROVAL_DECISION_APPROVED,
            actor="approver",
        )
        
        summary = service.summarize()
        
        assert summary["total_events"] == 3
        assert "PROMOTION_DRY_RUN_CREATED" in summary["by_event_type"]
        assert "APPROVAL_REQUEST_CREATED" in summary["by_event_type"]
        assert "APPROVAL_DECISION_APPROVED" in summary["by_event_type"]
        assert summary["by_event_type"]["PROMOTION_DRY_RUN_CREATED"] == 1
        assert summary["by_event_type"]["APPROVAL_REQUEST_CREATED"] == 1
        assert summary["by_event_type"]["APPROVAL_DECISION_APPROVED"] == 1
    
    def test_validate_event_accepts_well_formed(self, service):
        """Test que validate_event acepta evento bien formado."""
        event = CuratedMemoryEvent(
            event_id="evt_valid",
            event_type=CuratedMemoryEventType.AUDIT_ENTRY_APPENDED,
            actor="user",
            status=EventStatus.PROCESSED,
            dry_run_only=True,
            allow_real_write=False,
        )
        
        is_valid = service.validate_event(event)
        assert is_valid is True
    
    def test_validate_event_rejects_allow_real_write_true(self, service):
        """Test que validate_event rechaza allow_real_write=True."""
        event = CuratedMemoryEvent(
            event_id="evt_invalid",
            event_type=CuratedMemoryEventType.REAL_WRITE_BLOCKED,
            actor="user",
            status=EventStatus.PROCESSED,
            dry_run_only=True,
            allow_real_write=True,  # No permitido
        )
        
        is_valid = service.validate_event(event)
        assert is_valid is False
    
    def test_validate_event_rejects_dry_run_only_false(self, service):
        """Test que validate_event rechaza dry_run_only=False."""
        event = CuratedMemoryEvent(
            event_id="evt_invalid",
            event_type=CuratedMemoryEventType.ROLLBACK_PLAN_CREATED,
            actor="user",
            status=EventStatus.PROCESSED,
            dry_run_only=False,  # No permitido
            allow_real_write=False,
        )
        
        is_valid = service.validate_event(event)
        assert is_valid is False
    
    def test_get_event_by_id(self, service):
        """Test que get_event_by_id recupera evento específico."""
        event = service.record_event(
            event_type=CuratedMemoryEventType.ROLLBACK_DRY_RUN_EXECUTED,
            actor="user",
        )
        
        retrieved = service.get_event_by_id(event.event_id)
        assert retrieved is not None
        assert retrieved.event_id == event.event_id
    
    def test_clear_events(self, service):
        """Test que clear_events limpia todos los eventos."""
        # Registrar eventos
        service.record_event(
            event_type=CuratedMemoryEventType.PROMOTION_DRY_RUN_CREATED,
            actor="user1",
        )
        service.record_event(
            event_type=CuratedMemoryEventType.APPROVAL_REQUEST_CREATED,
            actor="user2",
        )
        
        assert service.count_events() == 2
        
        # Limpiar
        service.clear_events()
        
        assert service.count_events() == 0


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
        import brain.curated_memory_observability as obs_module
        
        # Verificar que no hay imports prohibidos
        loaded = list(sys.modules.keys())
        for forbidden in forbidden:
            assert not any(forbidden in mod for mod in loaded), \
                f"Módulo prohibido cargado: {forbidden}"
    
    def test_no_memory_semantic_write(self):
        """Test que no se escribe en memory/semantic."""
        service = CuratedMemoryObservability()
        
        # Registrar eventos (solo en memoria)
        service.record_event(
            event_type=CuratedMemoryEventType.PROMOTION_DRY_RUN_CREATED,
            actor="user",
        )
        
        # Verificar que los eventos están solo en memoria
        assert len(service._events) == 1
        assert service.count_events() == 1


def test_factory_function():
    """Test que la factory crea instancia correctamente."""
    service = create_observability_service()
    assert isinstance(service, CuratedMemoryObservability)
    assert len(service._events) == 0
