"""
P2-E Commit 3D: Curated Memory Observability Contract

Módulo de observabilidad para el flujo de promoción curada gobernada.
Este módulo es PÚRAMENTE UN CONTRATO/STUB:
- NO escribe memoria real.
- NO toca FAISS.
- NO llama endpoints.
- NO modifica runtime.
- SÓLO registra eventos en memoria para métricas/alertas futuras.

Eventos medidos:
- PROMOTION_DRY_RUN_CREATED
- APPROVAL_REQUEST_CREATED
- APPROVAL_DECISION_APPROVED/REJECTED
- AUDIT_ENTRY_APPENDED
- ROLLBACK_PLAN_CREATED
- ROLLBACK_DRY_RUN_EXECUTED
- REAL_WRITE_BLOCKED

Requisitos futuros:
1. Persistencia de eventos (opcional)
2. Dashboard de métricas
3. Alertas de anomalías
4. Integración con servicios de monitoreo
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class CuratedMemoryEventType(str, Enum):
    """Tipos de eventos del flujo de promoción curada."""
    PROMOTION_DRY_RUN_CREATED = "PROMOTION_DRY_RUN_CREATED"
    APPROVAL_REQUEST_CREATED = "APPROVAL_REQUEST_CREATED"
    APPROVAL_DECISION_APPROVED = "APPROVAL_DECISION_APPROVED"
    APPROVAL_DECISION_REJECTED = "APPROVAL_DECISION_REJECTED"
    AUDIT_ENTRY_APPENDED = "AUDIT_ENTRY_APPENDED"
    ROLLBACK_PLAN_CREATED = "ROLLBACK_PLAN_CREATED"
    ROLLBACK_DRY_RUN_EXECUTED = "ROLLBACK_DRY_RUN_EXECUTED"
    REAL_WRITE_BLOCKED = "REAL_WRITE_BLOCKED"


class EventStatus(str, Enum):
    """Estado del evento."""
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    ALERTED = "ALERTED"
    IGNORED = "IGNORED"


@dataclass
class CuratedMemoryEvent:
    """
    Evento de observabilidad del flujo de promoción curada.
    
    Este dataclass representa un evento registrado para métricas
    y monitoreo, pero NO ejecuta acciones sobre el sistema.
    """
    # Identificación
    event_id: str
    event_type: CuratedMemoryEventType
    
    # Timestamp UTC ISO 8601
    created_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    # Actor que generó el evento
    actor: str = "system"
    
    # Referencias a entidades del flujo (opcionales)
    record_id: Optional[str] = None
    request_id: Optional[str] = None
    decision_id: Optional[str] = None
    rollback_id: Optional[str] = None
    
    # Estado del evento
    status: EventStatus = EventStatus.PENDING
    
    # Control de seguridad - SIEMPRE True en este commit
    dry_run_only: bool = True
    
    # Control de escritura - SIEMPRE False en este commit
    allow_real_write: bool = False
    
    # Metadata adicional
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "created_at_utc": self.created_at_utc,
            "actor": self.actor,
            "record_id": self.record_id,
            "request_id": self.request_id,
            "decision_id": self.decision_id,
            "rollback_id": self.rollback_id,
            "status": self.status.value,
            "dry_run_only": self.dry_run_only,
            "allow_real_write": self.allow_real_write,
            "metadata": self.metadata,
        }


class CuratedMemoryObservability:
    """
    Servicio de observabilidad para promoción curada.
    
    Responsabilidades:
    - Registrar eventos del flujo de promoción
    - Contar eventos por tipo
    - Proporcionar resumen de métricas
    - Validar integridad de eventos
    
    Limitaciones (P2-E Commit 3D):
    - NO escribe en archivos (solo memoria)
    - NO importa FAISS ni SemanticMemory
    - NO llama endpoints HTTP
    - NO modifica runtime
    - SÓLO registra eventos para métricas
    
    Para habilitar observabilidad completa:
    1. Persistencia de eventos (opcional)
    2. Dashboard de métricas
    3. Alertas de anomalías
    4. Integración con servicios externos (si aplica)
    """
    
    def __init__(self):
        """
        Inicializar servicio de observabilidad.
        
        En este commit, el servicio opera completamente en memoria
        sin persistencia ni side effects.
        """
        # En memoria: lista de eventos
        self._events: List[CuratedMemoryEvent] = []
    
    def record_event(
        self,
        event_type: CuratedMemoryEventType,
        actor: str,
        record_id: Optional[str] = None,
        request_id: Optional[str] = None,
        decision_id: Optional[str] = None,
        rollback_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CuratedMemoryEvent:
        """
        Registrar un evento de observabilidad.
        
        Args:
            event_type: Tipo de evento
            actor: Quién generó el evento
            record_id: ID del registro (opcional)
            request_id: ID de la solicitud (opcional)
            decision_id: ID de la decisión (opcional)
            rollback_id: ID del rollback (opcional)
            metadata: Metadata adicional (opcional)
            
        Returns:
            CuratedMemoryEvent registrado
        """
        event_id = f"evt_{uuid.uuid4().hex[:16]}"
        
        event = CuratedMemoryEvent(
            event_id=event_id,
            event_type=event_type,
            actor=actor,
            record_id=record_id,
            request_id=request_id,
            decision_id=decision_id,
            rollback_id=rollback_id,
            status=EventStatus.PROCESSED,
            dry_run_only=True,  # SIEMPRE True
            allow_real_write=False,  # SIEMPRE False
            metadata=metadata or {},
        )
        
        # Agregar a memoria
        self._events.append(event)
        
        return event
    
    def list_events(
        self,
        event_type: Optional[CuratedMemoryEventType] = None,
        record_id: Optional[str] = None,
        status: Optional[EventStatus] = None,
    ) -> List[CuratedMemoryEvent]:
        """
        Listar eventos con filtros opcionales.
        
        Args:
            event_type: Filtrar por tipo de evento
            record_id: Filtrar por ID de registro
            status: Filtrar por estado
            
        Returns:
            Lista de eventos filtrados
        """
        results = self._events.copy()
        
        if event_type:
            results = [e for e in results if e.event_type == event_type]
        
        if record_id:
            results = [e for e in results if e.record_id == record_id]
        
        if status:
            results = [e for e in results if e.status == status]
        
        return results
    
    def count_events(
        self,
        event_type: Optional[CuratedMemoryEventType] = None,
    ) -> int:
        """
        Contar eventos, opcionalmente filtrados por tipo.
        
        Args:
            event_type: Tipo de evento a contar
            
        Returns:
            Número de eventos
        """
        if event_type:
            return len([e for e in self._events if e.event_type == event_type])
        return len(self._events)
    
    def summarize(self) -> Dict[str, Any]:
        """
        Obtener resumen de métricas del flujo de promoción.
        
        Returns:
            Diccionario con conteos por tipo de evento
        """
        summary = {
            "total_events": len(self._events),
            "by_event_type": {},
            "by_status": {},
        }
        
        # Contar por tipo de evento
        for event_type in CuratedMemoryEventType:
            count = self.count_events(event_type)
            if count > 0:
                summary["by_event_type"][event_type.value] = count
        
        # Contar por estado
        for status in EventStatus:
            count = len([e for e in self._events if e.status == status])
            if count > 0:
                summary["by_status"][status.value] = count
        
        return summary
    
    def validate_event(self, event: CuratedMemoryEvent) -> bool:
        """
        Validar que un evento está bien formado.
        
        Reglas de validación:
        1. Debe tener event_id no vacío
        2. Debe tener event_type válido
        3. NO debe tener allow_real_write=True (bloqueado)
        4. Debe tener dry_run_only=True
        
        Args:
            event: Evento a validar
            
        Returns:
            True si el evento es válido
        """
        # Verificar event_id
        if not event.event_id or len(event.event_id) == 0:
            return False
        
        # Verificar event_type
        if not isinstance(event.event_type, CuratedMemoryEventType):
            return False
        
        # Bloquear allow_real_write=True
        if event.allow_real_write:
            return False
        
        # Verificar dry_run_only=True
        if not event.dry_run_only:
            return False
        
        return True
    
    def get_event_by_id(self, event_id: str) -> Optional[CuratedMemoryEvent]:
        """Obtener evento por ID."""
        for event in self._events:
            if event.event_id == event_id:
                return event
        return None
    
    def clear_events(self) -> None:
        """Limpiar todos los eventos (útil para tests)."""
        self._events.clear()


def create_observability_service() -> CuratedMemoryObservability:
    """Factory para crear instancia del servicio de observabilidad."""
    return CuratedMemoryObservability()
