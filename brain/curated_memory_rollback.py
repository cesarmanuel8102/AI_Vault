"""
P2-E Commit 3C: Curated Memory Rollback Contract/Stub

Contrato de rollback para promociones de conocimiento curado.
Este módulo es PÚRAMENTE UN CONTRATO/STUB:
- NO ejecuta rollback real sobre memoria semántica.
- NO borra archivos de memory/semantic.
- NO importa FAISS ni SemanticMemory.
- NO implementa rollback real (execute_rollback_real).
- SÓLO define la estructura y validación de planes de rollback.

Requisitos futuros para habilitar rollback real:
1. Audit trail completo con trazabilidad.
2. Identificación de registros promovidos.
3. Procedimiento de reversión de memoria semántica.
4. Observability y métricas de rollback.
5. Pruebas de integración validadas.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
import hashlib
import uuid


class RollbackStatus(str, Enum):
    """Estados posibles de un plan de rollback."""
    PLANNED = "PLANNED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    EXECUTED_DRY_RUN = "EXECUTED_DRY_RUN"
    BLOCKED_REAL_WRITE = "BLOCKED_REAL_WRITE"


@dataclass
class CuratedMemoryRollbackPlan:
    """
    Plan de rollback para una promoción de conocimiento curado.
    
    Este dataclass representa la intención de revertir una promoción,
    pero NO ejecuta la reversión real sobre memoria semántica.
    Siempre opera en modo dry-run.
    """
    # Identificación
    rollback_id: str
    
    # Referencias a la promoción original
    promotion_request_id: str
    promotion_decision_id: str
    record_id: str
    content_hash: str
    
    # Metadata del rollback
    reason: str
    requested_by: str
    requested_at_utc: str
    
    # Estado del rollback
    status: RollbackStatus
    
    # Hash de evidencia para trazabilidad
    evidence_hash: str
    
    # Control de seguridad - SIEMPRE True en este commit
    dry_run_only: bool = True
    
    # Control de escritura - SIEMPRE False en este commit
    allow_real_write: bool = False
    
    # Metadata adicional
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "rollback_id": self.rollback_id,
            "promotion_request_id": self.promotion_request_id,
            "promotion_decision_id": self.promotion_decision_id,
            "record_id": self.record_id,
            "content_hash": self.content_hash,
            "reason": self.reason,
            "requested_by": self.requested_by,
            "requested_at_utc": self.requested_at_utc,
            "status": self.status.value,
            "evidence_hash": self.evidence_hash,
            "dry_run_only": self.dry_run_only,
            "allow_real_write": self.allow_real_write,
            "metadata": self.metadata,
        }


class CuratedMemoryRollbackService:
    """
    Servicio de rollback para promociones de conocimiento curado.
    
    Responsabilidades:
    - Crear planes de rollback documentados.
    - Validar planes de rollback.
    - Ejecutar rollback en modo dry-run (sin tocar memoria real).
    - Registrar decisiones de rechazo de rollback.
    
    Limitaciones (P2-E Commit 3C):
    - NO ejecuta rollback real sobre memory/semantic.
    - NO borra archivos de memoria.
    - NO importa FAISS ni SemanticMemory.
    - NO llama endpoints HTTP.
    - NO implementa execute_rollback_real.
    - SÓLO crea contratos/stubs en memoria.
    
    Para habilitar rollback real se requiere:
    1. Audit trail completo con trazabilidad de promociones.
    2. Identificación de registros en memoria semántica.
    3. Procedimiento de reversión de índices FAISS.
    4. Observability y métricas de rollback.
    5. Pruebas de integración con SemanticMemory validadas.
    """
    
    def __init__(self):
        """
        Inicializar servicio de rollback.
        
        En este commit, el servicio opera completamente en memoria
        sin side effects sobre memoria semántica.
        """
        # En memoria: planes de rollback
        self._plans: Dict[str, CuratedMemoryRollbackPlan] = {}
    
    def create_rollback_plan(
        self,
        promotion_request_id: str,
        promotion_decision_id: str,
        record_id: str,
        content_hash: str,
        requested_by: str,
        reason: str,
        evidence: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CuratedMemoryRollbackPlan:
        """
        Crear un plan de rollback documentado.
        
        Args:
            promotion_request_id: ID de la solicitud de promoción original
            promotion_decision_id: ID de la decisión de promoción original
            record_id: ID del registro curado promovido
            content_hash: Hash del contenido promovido
            requested_by: Identificador del solicitante de rollback
            reason: Razón del rollback
            evidence: Evidencia del rollback (opcional)
            metadata: Metadata adicional (opcional)
            
        Returns:
            CuratedMemoryRollbackPlan con estado PLANNED
        """
        rollback_id = f"rollback_{uuid.uuid4().hex[:16]}"
        
        # Generar evidence_hash
        evidence_str = evidence or f"{promotion_request_id}:{promotion_decision_id}:{reason}"
        evidence_hash = hashlib.sha256(evidence_str.encode()).hexdigest()
        
        plan = CuratedMemoryRollbackPlan(
            rollback_id=rollback_id,
            promotion_request_id=promotion_request_id,
            promotion_decision_id=promotion_decision_id,
            record_id=record_id,
            content_hash=content_hash,
            reason=reason,
            requested_by=requested_by,
            requested_at_utc=datetime.now(timezone.utc).isoformat(),
            status=RollbackStatus.PLANNED,
            evidence_hash=evidence_hash,
            dry_run_only=True,  # SIEMPRE True en este commit
            allow_real_write=False,  # SIEMPRE False en este commit
            metadata=metadata or {},
        )
        
        # Almacenar en memoria (no persiste)
        self._plans[rollback_id] = plan
        
        return plan
    
    def validate_rollback_plan(self, plan: CuratedMemoryRollbackPlan) -> bool:
        """
        Validar que un plan de rollback está bien formado.
        
        Reglas de validación:
        1. Debe tener rollback_id no vacío
        2. Debe tener promotion_request_id no vacío
        3. Debe tener promotion_decision_id no vacío
        4. Debe tener evidence_hash no vacío
        5. NO debe tener allow_real_write=True (bloqueado en este commit)
        6. Debe tener dry_run_only=True
        
        Args:
            plan: Plan a validar
            
        Returns:
            True si el plan es válido, False en caso contrario
        """
        # Verificar rollback_id
        if not plan.rollback_id or len(plan.rollback_id) == 0:
            return False
        
        # Verificar promotion_request_id
        if not plan.promotion_request_id or len(plan.promotion_request_id) == 0:
            return False
        
        # Verificar promotion_decision_id
        if not plan.promotion_decision_id or len(plan.promotion_decision_id) == 0:
            return False
        
        # Verificar evidence_hash
        if not plan.evidence_hash or len(plan.evidence_hash) == 0:
            return False
        
        # Bloquear allow_real_write=True
        if plan.allow_real_write:
            return False
        
        # Verificar dry_run_only=True
        if not plan.dry_run_only:
            return False
        
        return True
    
    def execute_rollback_dry_run(
        self,
        plan: CuratedMemoryRollbackPlan,
    ) -> CuratedMemoryRollbackPlan:
        """
        Ejecutar rollback en modo dry-run.
        
        Este método NUNCA ejecuta rollback real sobre memoria semántica.
        Solo simula la ejecución y actualiza el estado del plan.
        
        Args:
            plan: Plan de rollback a ejecutar
            
        Returns:
            Plan con estado actualizado a EXECUTED_DRY_RUN
        """
        # Validar el plan primero
        if not self.validate_rollback_plan(plan):
            plan.status = RollbackStatus.REJECTED
            return plan
        
        # Simular rollback (sin tocar memoria real)
        # En un futuro, aquí se ejecutaría el rollback real
        # Por ahora, solo marcamos como ejecutado en dry-run
        plan.status = RollbackStatus.EXECUTED_DRY_RUN
        
        return plan
    
    def reject_rollback_plan(
        self,
        plan: CuratedMemoryRollbackPlan,
        reason: str,
    ) -> CuratedMemoryRollbackPlan:
        """
        Rechazar un plan de rollback.
        
        Args:
            plan: Plan a rechazar
            reason: Razón del rechazo
            
        Returns:
            Plan con estado REJECTED
        """
        plan.status = RollbackStatus.REJECTED
        plan.metadata["rejection_reason"] = reason
        
        return plan
    
    def get_plan(self, rollback_id: str) -> Optional[CuratedMemoryRollbackPlan]:
        """Obtener plan por ID."""
        return self._plans.get(rollback_id)
    
    def list_plans(
        self,
        status: Optional[RollbackStatus] = None,
        record_id: Optional[str] = None,
    ) -> list:
        """
        Listar planes de rollback con filtros opcionales.
        
        Args:
            status: Filtrar por estado
            record_id: Filtrar por ID de registro
            
        Returns:
            Lista de planes filtrados
        """
        results = list(self._plans.values())
        
        if status:
            results = [p for p in results if p.status == status]
        
        if record_id:
            results = [p for p in results if p.record_id == record_id]
        
        return results
    
    def get_rollback_stats(self) -> Dict[str, int]:
        """
        Obtener estadísticas de rollback.
        
        Returns:
            Diccionario con conteos por estado
        """
        stats = {
            "total_plans": len(self._plans),
            "planned": len([p for p in self._plans.values() if p.status == RollbackStatus.PLANNED]),
            "validated": len([p for p in self._plans.values() if p.status == RollbackStatus.VALIDATED]),
            "rejected": len([p for p in self._plans.values() if p.status == RollbackStatus.REJECTED]),
            "executed_dry_run": len([p for p in self._plans.values() if p.status == RollbackStatus.EXECUTED_DRY_RUN]),
            "blocked_real_write": len([p for p in self._plans.values() if p.status == RollbackStatus.BLOCKED_REAL_WRITE]),
        }
        return stats


def create_rollback_service() -> CuratedMemoryRollbackService:
    """Factory para crear instancia del servicio de rollback."""
    return CuratedMemoryRollbackService()
