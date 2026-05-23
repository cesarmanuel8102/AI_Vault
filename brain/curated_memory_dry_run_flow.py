"""
P2-E Commit 3E: Curated Memory Dry-Run Integration Flow

Orquestador dry-run unificado que conecta los módulos:
- promotion (CuratedMemoryPromotionService)
- governance (CuratedMemoryGovernanceService)
- audit (CuratedMemoryGovernanceAuditTrail)
- rollback (CuratedMemoryRollbackService)
- observability (CuratedMemoryObservability)

Este módulo demuestra que todos los componentes funcionan juntos
en un flujo completo SIN escritura real en memoria semántica.

Flujo completo:
1. Crear plan de promoción dry-run
2. Crear solicitud de aprobación
3. Registrar en audit trail
4. Simular decisión de aprobación/rechazo
5. Registrar eventos de observability
6. Si es necesario, crear plan de rollback
7. Bloquear explícitamente escritura real

Requisitos futuros para promoción real:
1. Integración con SemanticMemory real
2. Permitir allow_real_write=True con governance completo
3. Implementar rollback real sobre FAISS
4. Persistencia de eventos observability
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

# Importar módulos existentes
from brain.curated_memory_promotion import (
    CuratedMemoryPromotionService,
    CuratedMemoryPromotionPlan,
    PromotionStatus,
)
from brain.curated_memory_governance import (
    CuratedMemoryGovernanceService,
    PromotionApprovalRequest,
    PromotionApprovalDecision,
    ApprovalStatus,
)
from brain.curated_memory_governance_audit import (
    CuratedMemoryGovernanceAuditTrail,
    GovernanceAuditEntry,
    AuditEntryType,
    AuditEntryStatus,
)
from brain.curated_memory_rollback import (
    CuratedMemoryRollbackService,
    CuratedMemoryRollbackPlan,
    RollbackStatus,
)
from brain.curated_memory_observability import (
    CuratedMemoryObservability,
    CuratedMemoryEventType,
)


class DryRunFlowStatus(str, Enum):
    """Estados del flujo dry-run de promoción curada."""
    CREATED = "CREATED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVED_DRY_RUN = "APPROVED_DRY_RUN"
    REJECTED_DRY_RUN = "REJECTED_DRY_RUN"
    AUDITED = "AUDITED"
    ROLLBACK_PLANNED = "ROLLBACK_PLANNED"
    COMPLETED_DRY_RUN = "COMPLETED_DRY_RUN"
    REAL_WRITE_BLOCKED = "REAL_WRITE_BLOCKED"


@dataclass
class CuratedMemoryDryRunFlowResult:
    """
    Resultado del flujo dry-run de promoción curada.
    
    Este dataclass contiene todas las referencias a las entidades
    creadas durante el flujo, sin modificar memoria semántica real.
    """
    # Identificación
    flow_id: str
    record_id: str
    content_hash: str
    
    # Estado del flujo
    status: DryRunFlowStatus
    
    # Referencias a entidades del flujo
    promotion_plan_id: Optional[str] = None
    approval_request_id: Optional[str] = None
    approval_decision_id: Optional[str] = None
    audit_entry_ids: List[str] = field(default_factory=list)
    rollback_id: Optional[str] = None
    observability_event_ids: List[str] = field(default_factory=list)
    
    # Control de seguridad - SIEMPRE True en este commit
    dry_run_only: bool = True
    
    # Control de escritura - SIEMPRE False en este commit
    allow_real_write: bool = False
    
    # Metadata adicional
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "flow_id": self.flow_id,
            "record_id": self.record_id,
            "content_hash": self.content_hash,
            "status": self.status.value,
            "promotion_plan_id": self.promotion_plan_id,
            "approval_request_id": self.approval_request_id,
            "approval_decision_id": self.approval_decision_id,
            "audit_entry_ids": self.audit_entry_ids,
            "rollback_id": self.rollback_id,
            "observability_event_ids": self.observability_event_ids,
            "dry_run_only": self.dry_run_only,
            "allow_real_write": self.allow_real_write,
            "metadata": self.metadata,
        }


class CuratedMemoryDryRunFlow:
    """
    Orquestador dry-run unificado para promoción curada gobernada.
    
    Responsabilidades:
    - Coordinar todos los servicios (promotion, governance, audit, rollback, observability)
    - Ejecutar flujo completo de aprobación en modo dry-run
    - Ejecutar flujo de rollback en modo dry-run
    - Bloquear explícitamente escritura real
    - Registrar eventos de observabilidad
    
    Limitaciones (P2-E Commit 3E):
    - NO escribe en memory/semantic
    - NO importa FAISS
    - NO llama endpoints HTTP
    - NO modifica runtime
    - SIEMPRE bloquea allow_real_write
    
    Para habilitar promoción real:
    1. Integrar con SemanticMemory real
    2. Permitir allow_real_write=True con governance completo
    3. Implementar rollback real sobre FAISS
    """
    
    def __init__(
        self,
        promotion_service: Optional[CuratedMemoryPromotionService] = None,
        governance_service: Optional[CuratedMemoryGovernanceService] = None,
        audit_trail: Optional[CuratedMemoryGovernanceAuditTrail] = None,
        rollback_service: Optional[CuratedMemoryRollbackService] = None,
        observability: Optional[CuratedMemoryObservability] = None,
    ):
        """
        Inicializar orquestador de flujo dry-run.
        
        Args:
            promotion_service: Servicio de promoción (opcional)
            governance_service: Servicio de governance (opcional)
            audit_trail: Servicio de audit trail (opcional)
            rollback_service: Servicio de rollback (opcional)
            observability: Servicio de observabilidad (opcional)
        """
        self._promotion = promotion_service or CuratedMemoryPromotionService()
        self._governance = governance_service or CuratedMemoryGovernanceService()
        self._audit = audit_trail or CuratedMemoryGovernanceAuditTrail()
        self._rollback = rollback_service or CuratedMemoryRollbackService()
        self._observability = observability or CuratedMemoryObservability()
    
    def run_approval_flow(
        self,
        record_id: str,
        content_hash: str,
        source: str,
        validation_score: float,
        actor: str,
        approve: bool = True,
        reason: str = "Dry-run approval flow",
    ) -> CuratedMemoryDryRunFlowResult:
        """
        Ejecutar flujo completo de aprobación en modo dry-run.
        
        Este método coordina todos los servicios para simular
        un flujo completo de promoción gobernada SIN escribir
        en memoria semántica real.
        
        Args:
            record_id: ID del registro curado
            content_hash: Hash del contenido
            source: Fuente del registro
            validation_score: Score de validación
            actor: Quien ejecuta el flujo
            approve: Si True, aprueba; si False, rechaza
            reason: Razón de la acción
            
        Returns:
            CuratedMemoryDryRunFlowResult con todas las referencias
        """
        flow_id = f"flow_{uuid.uuid4().hex[:16]}"
        
        # Crear resultado inicial
        result = CuratedMemoryDryRunFlowResult(
            flow_id=flow_id,
            record_id=record_id,
            content_hash=content_hash,
            status=DryRunFlowStatus.CREATED,
            dry_run_only=True,
            allow_real_write=False,
        )
        
        # 1. Registrar evento: PROMOTION_DRY_RUN_CREATED
        event = self._observability.record_event(
            event_type=CuratedMemoryEventType.PROMOTION_DRY_RUN_CREATED,
            actor=actor,
            record_id=record_id,
            metadata={"flow_id": flow_id, "validation_score": validation_score},
        )
        result.observability_event_ids.append(event.event_id)
        
        # 2. Crear plan de promoción (simulado - no tenemos CuratedRecord real)
        # Usamos un mock mínimo
        class MockPlan:
            def __init__(self, record_id, content_hash, source, validation_score):
                self.record_id = record_id
                self.content_hash = content_hash
                self.source = source
                self.validation_score = validation_score
        
        mock_plan = MockPlan(record_id, content_hash, source, validation_score)
        result.promotion_plan_id = f"plan_{uuid.uuid4().hex[:8]}"
        
        # 3. Crear solicitud de aprobación
        approval_request = self._governance.create_approval_request(
            plan=mock_plan,
            requested_by=actor,
            reason=reason,
        )
        result.approval_request_id = approval_request.request_id
        result.status = DryRunFlowStatus.APPROVAL_REQUESTED
        
        # Registrar evento
        event = self._observability.record_event(
            event_type=CuratedMemoryEventType.APPROVAL_REQUEST_CREATED,
            actor=actor,
            record_id=record_id,
            request_id=approval_request.request_id,
            metadata={"flow_id": flow_id},
        )
        result.observability_event_ids.append(event.event_id)
        
        # 4. Registrar en audit trail (request)
        audit_entry_request = self._audit.append_request(
            request_id=approval_request.request_id,
            actor=actor,
            evidence_hash=approval_request.content_hash,
            payload={"record_id": record_id, "source": source, "score": validation_score},
        )
        result.audit_entry_ids.append(audit_entry_request.entry_id)
        
        # 5. Simular decisión de aprobación
        if approve:
            approval_decision = self._governance.approve_request(
                request=approval_request,
                decided_by="governance_admin",
                reason="Approved in dry-run flow",
            )
            result.approval_decision_id = approval_decision.decision_id
            result.status = DryRunFlowStatus.APPROVED_DRY_RUN
            
            # Registrar evento de aprobación
            event = self._observability.record_event(
                event_type=CuratedMemoryEventType.APPROVAL_DECISION_APPROVED,
                actor="governance_admin",
                record_id=record_id,
                request_id=approval_request.request_id,
                decision_id=approval_decision.decision_id,
                metadata={"flow_id": flow_id},
            )
            result.observability_event_ids.append(event.event_id)
        else:
            approval_decision = self._governance.reject_request(
                request=approval_request,
                decided_by="governance_admin",
                reason="Rejected in dry-run flow",
            )
            result.approval_decision_id = approval_decision.decision_id
            result.status = DryRunFlowStatus.REJECTED_DRY_RUN
            
            # Registrar evento de rechazo
            event = self._observability.record_event(
                event_type=CuratedMemoryEventType.APPROVAL_DECISION_REJECTED,
                actor="governance_admin",
                record_id=record_id,
                request_id=approval_request.request_id,
                decision_id=approval_decision.decision_id,
                metadata={"flow_id": flow_id, "rejected": True},
            )
            result.observability_event_ids.append(event.event_id)
        
        # 6. Registrar en audit trail (decision)
        audit_entry_decision = self._audit.append_decision(
            request_id=approval_request.request_id,
            decision_id=approval_decision.decision_id,
            actor="governance_admin",
            evidence_hash=approval_decision.evidence_hash,
            approved=approve,
            payload={"decision": "approved" if approve else "rejected"},
        )
        result.audit_entry_ids.append(audit_entry_decision.entry_id)
        
        # Registrar evento de audit
        event = self._observability.record_event(
            event_type=CuratedMemoryEventType.AUDIT_ENTRY_APPENDED,
            actor="system",
            record_id=record_id,
            metadata={
                "flow_id": flow_id,
                "audit_entries": result.audit_entry_ids,
            },
        )
        result.observability_event_ids.append(event.event_id)
        
        # 7. Marcar como auditado (solo si no fue rechazado)
        if result.status != DryRunFlowStatus.REJECTED_DRY_RUN:
            result.status = DryRunFlowStatus.AUDITED
        
        # 8. Marcar como completado (dry-run) solo si no fue rechazado
        if result.status != DryRunFlowStatus.REJECTED_DRY_RUN:
            result.status = DryRunFlowStatus.COMPLETED_DRY_RUN
        
        return result
    
    def run_rollback_flow(
        self,
        flow_result: CuratedMemoryDryRunFlowResult,
        actor: str,
        reason: str = "Rollback requested",
    ) -> CuratedMemoryDryRunFlowResult:
        """
        Ejecutar flujo de rollback en modo dry-run.
        
        Este método simula la reversión de una promoción previamente
        aprobada SIN tocar memoria semántica real.
        
        Args:
            flow_result: Resultado del flujo de aprobación previo
            actor: Quien solicita el rollback
            reason: Razón del rollback
            
        Returns:
            CuratedMemoryDryRunFlowResult actualizado con rollback
        """
        # Crear plan de rollback
        rollback_plan = self._rollback.create_rollback_plan(
            promotion_request_id=flow_result.approval_request_id or "unknown",
            promotion_decision_id=flow_result.approval_decision_id or "unknown",
            record_id=flow_result.record_id,
            content_hash=flow_result.content_hash,
            requested_by=actor,
            reason=reason,
        )
        
        flow_result.rollback_id = rollback_plan.rollback_id
        flow_result.status = DryRunFlowStatus.ROLLBACK_PLANNED
        
        # Ejecutar rollback dry-run
        self._rollback.execute_rollback_dry_run(rollback_plan)
        
        # Registrar evento de rollback
        event = self._observability.record_event(
            event_type=CuratedMemoryEventType.ROLLBACK_PLAN_CREATED,
            actor=actor,
            record_id=flow_result.record_id,
            rollback_id=rollback_plan.rollback_id,
            metadata={"flow_id": flow_result.flow_id, "reason": reason},
        )
        flow_result.observability_event_ids.append(event.event_id)
        
        event = self._observability.record_event(
            event_type=CuratedMemoryEventType.ROLLBACK_DRY_RUN_EXECUTED,
            actor=actor,
            record_id=flow_result.record_id,
            rollback_id=rollback_plan.rollback_id,
            metadata={"flow_id": flow_result.flow_id},
        )
        flow_result.observability_event_ids.append(event.event_id)
        
        return flow_result
    
    def block_real_write(
        self,
        reason: str,
        actor: str,
        record_id: Optional[str] = None,
    ) -> CuratedMemoryDryRunFlowResult:
        """
        Bloquear explícitamente intento de escritura real.
        
        Este método se usa cuando se detecta un intento de escritura
        real en memoria semántica y debe ser bloqueado.
        
        Args:
            reason: Razón del bloqueo
            actor: Quien intentó la escritura
            record_id: ID del registro (opcional)
            
        Returns:
            CuratedMemoryDryRunFlowResult con status REAL_WRITE_BLOCKED
        """
        flow_id = f"blocked_{uuid.uuid4().hex[:16]}"
        
        # Registrar evento de bloqueo
        event = self._observability.record_event(
            event_type=CuratedMemoryEventType.REAL_WRITE_BLOCKED,
            actor=actor,
            record_id=record_id,
            metadata={"flow_id": flow_id, "reason": reason, "blocked": True},
        )
        
        result = CuratedMemoryDryRunFlowResult(
            flow_id=flow_id,
            record_id=record_id or "unknown",
            content_hash="blocked",
            status=DryRunFlowStatus.REAL_WRITE_BLOCKED,
            observability_event_ids=[event.event_id],
            dry_run_only=True,
            allow_real_write=False,
            metadata={"blocked_reason": reason, "blocked_by": actor},
        )
        
        return result
    
    def validate_flow_result(self, result: CuratedMemoryDryRunFlowResult) -> bool:
        """
        Validar que un resultado de flujo está bien formado.
        
        Reglas de validación:
        1. Debe tener flow_id no vacío
        2. Debe tener record_id no vacío
        3. NO debe tener allow_real_write=True (bloqueado)
        4. Debe tener dry_run_only=True
        5. Estado debe ser válido
        
        Args:
            result: Resultado a validar
            
        Returns:
            True si el resultado es válido
        """
        # Verificar flow_id
        if not result.flow_id or len(result.flow_id) == 0:
            return False
        
        # Verificar record_id
        if not result.record_id or len(result.record_id) == 0:
            return False
        
        # Bloquear allow_real_write=True
        if result.allow_real_write:
            return False
        
        # Verificar dry_run_only=True
        if not result.dry_run_only:
            return False
        
        # Verificar estado válido
        if not isinstance(result.status, DryRunFlowStatus):
            return False
        
        return True
    
    def get_flow_summary(self, flow_result: CuratedMemoryDryRunFlowResult) -> Dict[str, Any]:
        """
        Obtener resumen del flujo para debugging.
        
        Args:
            flow_result: Resultado del flujo
            
        Returns:
            Diccionario con resumen del flujo
        """
        return {
            "flow_id": flow_result.flow_id,
            "record_id": flow_result.record_id,
            "status": flow_result.status.value,
            "promotion_plan_id": flow_result.promotion_plan_id,
            "approval_request_id": flow_result.approval_request_id,
            "approval_decision_id": flow_result.approval_decision_id,
            "audit_entries_count": len(flow_result.audit_entry_ids),
            "rollback_id": flow_result.rollback_id,
            "observability_events_count": len(flow_result.observability_event_ids),
            "dry_run_only": flow_result.dry_run_only,
            "allow_real_write": flow_result.allow_real_write,
        }


def create_dry_run_flow(
    promotion_service: Optional[CuratedMemoryPromotionService] = None,
    governance_service: Optional[CuratedMemoryGovernanceService] = None,
    audit_trail: Optional[CuratedMemoryGovernanceAuditTrail] = None,
    rollback_service: Optional[CuratedMemoryRollbackService] = None,
    observability: Optional[CuratedMemoryObservability] = None,
) -> CuratedMemoryDryRunFlow:
    """
    Factory para crear instancia del orquestador de flujo dry-run.
    
    Args:
        promotion_service: Servicio de promoción (opcional)
        governance_service: Servicio de governance (opcional)
        audit_trail: Servicio de audit trail (opcional)
        rollback_service: Servicio de rollback (opcional)
        observability: Servicio de observabilidad (opcional)
    
    Returns:
        CuratedMemoryDryRunFlow configurado
    """
    return CuratedMemoryDryRunFlow(
        promotion_service=promotion_service,
        governance_service=governance_service,
        audit_trail=audit_trail,
        rollback_service=rollback_service,
        observability=observability,
    )
