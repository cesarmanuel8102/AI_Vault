"""
P2-E Commit 3A: Curated Memory Governance — Approval Contract/Stub

Capa de governance para planes de promoción curada.
Este módulo es PÚRAMENTE UN CONTRATO/STUB:
- NO escribe en memoria real.
- NO llama endpoints HTTP.
- NO importa FAISS ni SemanticMemory.
- NO implementa promoción real (promote_real).
- SÓLO crea requests/decisiones de approval en memoria.

Requisitos futuros para habilitar promoción real:
1. Audit trail persistente.
2. Rollback capability.
3. Observability completa.
4. Pruebas de integración con SemanticMemory.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
import hashlib
import uuid


class ApprovalStatus(str, Enum):
    """Estados posibles de una solicitud de aprobación."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    INVALID = "INVALID"


@dataclass
class PromotionApprovalRequest:
    """
    Solicitud de aprobación para promoción de conocimiento curado.
    
    Este dataclass representa la intención de promover un registro,
    pero NO realiza la promoción. Siempre opera en modo dry_run.
    """
    # Identificación
    request_id: str
    plan_id: str
    record_id: str
    content_hash: str
    
    # Fuente y validación
    source: str
    validation_score: float
    
    # Metadata de solicitud
    requested_by: str
    requested_at_utc: str
    reason: str
    
    # Control de seguridad - SIEMPRE True en este commit
    dry_run_only: bool = True
    
    # Estado
    status: ApprovalStatus = ApprovalStatus.PENDING
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "request_id": self.request_id,
            "plan_id": self.plan_id,
            "record_id": self.record_id,
            "content_hash": self.content_hash,
            "source": self.source,
            "validation_score": self.validation_score,
            "requested_by": self.requested_by,
            "requested_at_utc": self.requested_at_utc,
            "reason": self.reason,
            "dry_run_only": self.dry_run_only,
            "status": self.status.value,
        }


@dataclass
class PromotionApprovalDecision:
    """
    Decisión de aprobación/rechazo de una solicitud de promoción.
    
    Esta decisión documenta quién aprobó/rechazó y por qué,
    pero NO ejecuta la promoción real.
    """
    # Identificación
    decision_id: str
    request_id: str
    
    # Estado de la decisión
    status: ApprovalStatus
    
    # Metadata de decisión
    decided_by: str
    decided_at_utc: str
    reason: str
    
    # Hash de evidencia (para trazabilidad)
    evidence_hash: str
    
    # Control de seguridad - SIEMPRE False en este commit
    allow_real_write: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "decision_id": self.decision_id,
            "request_id": self.request_id,
            "status": self.status.value,
            "decided_by": self.decided_by,
            "decided_at_utc": self.decided_at_utc,
            "reason": self.reason,
            "evidence_hash": self.evidence_hash,
            "allow_real_write": self.allow_real_write,
        }


class CuratedMemoryGovernanceService:
    """
    Servicio de governance para promoción de conocimiento curado.
    
    Responsabilidades:
    - Crear solicitudes de aprobación.
    - Registrar decisiones de aprobación/rechazo.
    - Validar decisiones antes de cualquier acción real.
    
    Limitaciones (P2-E Commit 3A):
    - NO escribe en archivos de memoria.
    - NO llama endpoints HTTP.
    - NO importa FAISS ni SemanticMemory.
    - NO implementa promote_real.
    - SÓLO crea contratos/stubs en memoria.
    
    Para habilitar escritura real se requiere:
    1. Audit trail persistente.
    2. Rollback capability.
    3. Observability completa.
    4. Pruebas de integración validadas.
    """
    
    def __init__(self):
        """
        Inicializar servicio de governance.
        
        En este commit, el servicio opera completamente en memoria
        sin persistencia ni side effects.
        """
        # En memoria: solicitudes y decisiones
        self._requests: Dict[str, PromotionApprovalRequest] = {}
        self._decisions: Dict[str, PromotionApprovalDecision] = {}
    
    def create_approval_request(
        self,
        plan: Any,  # CuratedMemoryPromotionPlan
        requested_by: str,
        reason: str,
    ) -> PromotionApprovalRequest:
        """
        Crear una solicitud de aprobación para un plan de promoción.
        
        Args:
            plan: Plan de promoción (CuratedMemoryPromotionPlan)
            requested_by: Identificador del solicitante
            reason: Razón de la solicitud
            
        Returns:
            PromotionApprovalRequest con estado PENDING
        """
        request_id = f"req_{uuid.uuid4().hex[:16]}"
        
        request = PromotionApprovalRequest(
            request_id=request_id,
            plan_id=getattr(plan, 'record_id', 'unknown'),
            record_id=getattr(plan, 'record_id', 'unknown'),
            content_hash=getattr(plan, 'content_hash', 'unknown'),
            source=getattr(plan, 'source', 'unknown'),
            validation_score=getattr(plan, 'validation_score', 0.0),
            requested_by=requested_by,
            requested_at_utc=datetime.now(timezone.utc).isoformat(),
            reason=reason,
            dry_run_only=True,  # SIEMPRE True en este commit
            status=ApprovalStatus.PENDING,
        )
        
        # Almacenar en memoria (no persiste)
        self._requests[request_id] = request
        
        return request
    
    def approve_request(
        self,
        request: PromotionApprovalRequest,
        decided_by: str,
        reason: str,
        evidence: Optional[str] = None,
    ) -> PromotionApprovalDecision:
        """
        Aprobar una solicitud de promoción.
        
        Args:
            request: Solicitud a aprobar
            decided_by: Identificador del aprobador
            reason: Razón de la aprobación
            evidence: Evidencia de la decisión (opcional)
            
        Returns:
            PromotionApprovalDecision con status APPROVED
            y allow_real_write=False (SIEMPRE en este commit)
        """
        decision_id = f"dec_{uuid.uuid4().hex[:16]}"
        
        # Generar evidence_hash
        evidence_str = evidence or f"{request.request_id}:{decided_by}:{reason}"
        evidence_hash = hashlib.sha256(evidence_str.encode()).hexdigest()
        
        decision = PromotionApprovalDecision(
            decision_id=decision_id,
            request_id=request.request_id,
            status=ApprovalStatus.APPROVED,
            decided_by=decided_by,
            decided_at_utc=datetime.now(timezone.utc).isoformat(),
            reason=reason,
            evidence_hash=evidence_hash,
            allow_real_write=False,  # SIEMPRE False en este commit
        )
        
        # Actualizar estado de la solicitud
        request.status = ApprovalStatus.APPROVED
        
        # Almacenar decisión en memoria
        self._decisions[decision_id] = decision
        
        return decision
    
    def reject_request(
        self,
        request: PromotionApprovalRequest,
        decided_by: str,
        reason: str,
        evidence: Optional[str] = None,
    ) -> PromotionApprovalDecision:
        """
        Rechazar una solicitud de promoción.
        
        Args:
            request: Solicitud a rechazar
            decided_by: Identificador del que rechaza
            reason: Razón del rechazo
            evidence: Evidencia de la decisión (opcional)
            
        Returns:
            PromotionApprovalDecision con status REJECTED
        """
        decision_id = f"dec_{uuid.uuid4().hex[:16]}"
        
        # Generar evidence_hash
        evidence_str = evidence or f"{request.request_id}:{decided_by}:{reason}"
        evidence_hash = hashlib.sha256(evidence_str.encode()).hexdigest()
        
        decision = PromotionApprovalDecision(
            decision_id=decision_id,
            request_id=request.request_id,
            status=ApprovalStatus.REJECTED,
            decided_by=decided_by,
            decided_at_utc=datetime.now(timezone.utc).isoformat(),
            reason=reason,
            evidence_hash=evidence_hash,
            allow_real_write=False,  # Nunca permite escritura en rechazo
        )
        
        # Actualizar estado de la solicitud
        request.status = ApprovalStatus.REJECTED
        
        # Almacenar decisión en memoria
        self._decisions[decision_id] = decision
        
        return decision
    
    def validate_decision(self, decision: PromotionApprovalDecision) -> bool:
        """
        Validar que una decisión está bien formada y puede ejecutarse.
        
        En P2-E Commit 3A:
        - Rechaza decisiones sin evidence_hash.
        - Rechaza allow_real_write=True (no permitido aún).
        
        Args:
            decision: Decisión a validar
            
        Returns:
            True si la decisión es válida, False en caso contrario
        """
        # Debe tener evidence_hash
        if not decision.evidence_hash or len(decision.evidence_hash) == 0:
            return False
        
        # En este commit, NO permitir allow_real_write
        if decision.allow_real_write:
            return False
        
        # El estado debe ser válido
        if decision.status not in [ApprovalStatus.APPROVED, ApprovalStatus.REJECTED]:
            return False
        
        return True
    
    def get_request(self, request_id: str) -> Optional[PromotionApprovalRequest]:
        """Obtener solicitud por ID."""
        return self._requests.get(request_id)
    
    def get_decision(self, decision_id: str) -> Optional[PromotionApprovalDecision]:
        """Obtener decisión por ID."""
        return self._decisions.get(decision_id)
    
    def get_pending_requests(self) -> list:
        """Obtener todas las solicitudes pendientes."""
        return [
            req for req in self._requests.values()
            if req.status == ApprovalStatus.PENDING
        ]


def create_governance_service() -> CuratedMemoryGovernanceService:
    """Factory para crear instancia del servicio de governance."""
    return CuratedMemoryGovernanceService()
