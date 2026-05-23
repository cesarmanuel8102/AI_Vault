"""
P2-E: CuratedMemoryPromotion — Governed Curated Knowledge Promotion Service

Servicio de promoción controlada de conocimiento curado validado hacia memoria semántica.
Modo dry-run: nunca escribe archivos ni llama endpoints.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple

# Importar solo tipos de P2-C para interoperabilidad
from brain.information_curator import CuratedRecord
from brain.curation_validation_adapter import CurationValidationResult, CurationValidationStatus


class PromotionStatus(str, Enum):
    """Estados posibles de la promoción a memoria semántica."""
    ELIGIBLE = "eligible"
    REJECTED_NOT_VALIDATED = "rejected_not_validated"
    REJECTED_LOW_SCORE = "rejected_low_score"
    REJECTED_MISSING_TRACEABILITY = "rejected_missing_traceability"
    REQUIRES_APPROVAL = "requires_approval"
    APPROVED_NOT_EXECUTED = "approved_not_executed"
    PROMOTED = "promoted"
    ERROR = "error"


@dataclass
class CuratedMemoryPromotionPlan:
    """Plan de promoción de conocimiento curado a memoria semántica."""
    
    # Identificación
    record_id: str
    content_hash: str
    source: str
    topic: str
    text: str
    
    # Estado de validación
    validation_status: str
    validation_score: float
    
    # Estado de promoción
    status: PromotionStatus
    dry_run: bool = True
    rejection_reason: Optional[str] = None
    
    # Destino y payload
    target: str = "brain_v9_semantic_memory"
    memory_payload: Optional[Dict[str, Any]] = None
    
    # Governance
    governance_required: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir plan a diccionario serializable."""
        return {
            "record_id": self.record_id,
            "content_hash": self.content_hash,
            "source": self.source,
            "topic": self.topic,
            "validation_status": self.validation_status,
            "validation_score": self.validation_score,
            "promotion_status": self.status.value,
            "dry_run": self.dry_run,
            "rejection_reason": self.rejection_reason,
            "target": self.target,
            "governance_required": self.governance_required,
            "memory_payload": self.memory_payload,
        }


class CuratedMemoryPromotionService:
    """
    Servicio de promoción gobernada de conocimiento curado a memoria semántica.
    
    Responsabilidades:
    - Validar elegibilidad de CuratedRecord para promoción
    - Construir payload de memoria con provenance completo
    - Operar en modo dry-run (nunca escribe archivos ni llama endpoints)
    - Requerir aprobación explícita antes de promoción real
    
    Limitaciones:
    - NO importa FAISS ni SemanticMemory
    - NO escribe en archivos de memoria
    - NO llama endpoints HTTP
    - NO conecta a SemanticMemoryBridge histórico
    """
    
    def __init__(
        self,
        min_validation_score: float = 0.7,
        require_approval: bool = True,
    ):
        """
        Inicializar servicio de promoción.
        
        Args:
            min_validation_score: Score mínimo de validación para considerar elegible
            require_approval: Si True, requiere aprobación explícita antes de promoción
        """
        self.min_validation_score = min_validation_score
        self.require_approval = require_approval
    
    def promote_dry_run(
        self,
        record: CuratedRecord,
        validation_result: CurationValidationResult,
        *,
        target: str = "brain_v9_semantic_memory",
    ) -> CuratedMemoryPromotionPlan:
        """
        Evaluar promoción de un CuratedRecord validado en modo dry-run.
        
        Este método NUNCA escribe archivos ni llama endpoints. Solo construye
        un plan de promociación con el payload preparado.
        
        Args:
            record: CuratedRecord a evaluar para promoción
            validation_result: Resultado de validación de P2-C
            target: Destino de la promoción (default: brain_v9_semantic_memory)
            
        Returns:
            CuratedMemoryPromotionPlan con estado y payload preparado
        """
        # Validar elegibilidad
        is_eligible, status, rejection_reason = self.validate_promotion_eligibility(
            record, validation_result
        )
        
        # Construir payload de memoria (solo si es elegible)
        memory_payload = None
        if is_eligible:
            memory_payload = self.build_memory_payload(record, validation_result)
        
        # Determinar estado final
        if is_eligible and self.require_approval:
            final_status = PromotionStatus.REQUIRES_APPROVAL
        elif is_eligible:
            final_status = PromotionStatus.ELIGIBLE
        else:
            final_status = status
        
        return CuratedMemoryPromotionPlan(
            record_id=record.record_id,
            content_hash=record.content_hash,
            source=record.source,
            topic=record.topic if hasattr(record, 'topic') else "general",
            text=record.content if hasattr(record, 'content') else "",
            validation_status=validation_result.status.value,
            validation_score=validation_result.score,
            status=final_status,
            dry_run=True,  # Siempre dry-run en este método
            rejection_reason=rejection_reason,
            target=target,
            memory_payload=memory_payload,
            governance_required=self.require_approval,
        )
    
    def validate_promotion_eligibility(
        self,
        record: CuratedRecord,
        validation_result: CurationValidationResult,
    ) -> Tuple[bool, PromotionStatus, Optional[str]]:
        """
        Validar si un registro es elegible para promoción a memoria.
        
        Reglas de rechazo:
        1. validation_result.status != VALIDATED
        2. validation_result.score < min_validation_score
        3. Falta record_id, source, content_hash, topic o content
        
        Args:
            record: CuratedRecord a validar
            validation_result: Resultado de validación
            
        Returns:
            Tuple de (is_eligible, status, rejection_reason)
        """
        # Regla 1: Debe estar validado
        if validation_result.status != CurationValidationStatus.VALIDATED:
            return (
                False,
                PromotionStatus.REJECTED_NOT_VALIDATED,
                f"Record not validated: status={validation_result.status.value}"
            )
        
        # Regla 2: Score debe ser suficiente
        if validation_result.score < self.min_validation_score:
            return (
                False,
                PromotionStatus.REJECTED_LOW_SCORE,
                f"Score below threshold: {validation_result.score} < {self.min_validation_score}"
            )
        
        # Regla 3: Trazabilidad completa requerida
        missing_fields = []
        if not record.record_id:
            missing_fields.append("record_id")
        if not record.source:
            missing_fields.append("source")
        if not record.content_hash:
            missing_fields.append("content_hash")
        if not hasattr(record, 'topic') or not record.topic:
            missing_fields.append("topic")
        if not hasattr(record, 'content') or not record.content:
            missing_fields.append("content")
        
        if missing_fields:
            return (
                False,
                PromotionStatus.REJECTED_MISSING_TRACEABILITY,
                f"Missing traceability fields: {', '.join(missing_fields)}"
            )
        
        # Todas las reglas pasaron
        return (True, PromotionStatus.ELIGIBLE, None)
    
    def build_memory_payload(
        self,
        record: CuratedRecord,
        validation_result: CurationValidationResult,
    ) -> Dict[str, Any]:
        """
        Construir payload de memoria semántica con provenance completo.
        
        Args:
            record: CuratedRecord validado
            validation_result: Resultado de validación
            
        Returns:
            Diccionario con estructura de memoria semántica
        """
        # Obtener valores del record con defaults seguros
        topic = getattr(record, 'topic', 'general')
        content = getattr(record, 'content', '')
        
        return {
            "text": content,
            "source": f"curated:{record.source}",
            "session_id": "curated_knowledge_promotion",
            "kind": "validated_knowledge",
            "metadata": {
                "record_id": record.record_id,
                "content_hash": record.content_hash,
                "topic": topic,
                "source_original": record.source,
                "validation_status": validation_result.status.value,
                "validation_score": validation_result.score,
                "promotion_policy": "P2-E",
                "promotion_dry_run": True,
                "target": "brain_v9_semantic_memory",
                "provenance": {
                    "ingested_by": "InformationCurator",
                    "validated_by": "CurationValidationAdapter",
                    "promotion_service": "CuratedMemoryPromotionService",
                },
                "tags": ["curated", "validated", "p2e_dry_run"],
            }
        }


def create_curated_memory_promotion_service(
    min_validation_score: float = 0.7,
    require_approval: bool = True,
) -> CuratedMemoryPromotionService:
    """
    Factory para crear instancia del servicio de promoción.
    
    Args:
        min_validation_score: Score mínimo de validación
        require_approval: Si requiere aprobación explícita
        
    Returns:
        CuratedMemoryPromotionService configurado
    """
    return CuratedMemoryPromotionService(
        min_validation_score=min_validation_score,
        require_approval=require_approval,
    )
