"""
P2-C Adapter: CuratedRecord → LearningValidator

Conector mínimo entre InformationCurator y LearningValidator.
NO conecta a runtime/chat.
NO conecta a SemanticMemoryBridge/FAISS.
NO valida automáticamente.
Preserva trazabilidad completa.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sys
sys.path.insert(0, str(Path(__file__).parent))

from brain.information_curator import CuratedRecord, QualityLevel
from brain.learning_validator import LearningValidator, ValidationResult, ValidationStatus


class CurationValidationStatus(str, Enum):
    """Estado de validación de un registro curado."""
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    UNVALIDATED = "UNVALIDATED"
    ERROR = "ERROR"


@dataclass
class CurationValidationResult:
    """Resultado de validar un registro curado."""
    record_id: str
    content_hash: str
    source: str
    topic: str
    status: CurationValidationStatus
    validator_status: Optional[str]
    passed: bool
    score: float
    reason: str
    validation_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class CurationValidationAdapter:
    """
    Adapter que conecta CuratedRecord con LearningValidator.
    
    Responsabilidades:
    - Convertir CuratedRecord → llamada a LearningValidator.validate()
    - NO modificar record.validated_at
    - NO escribir en SemanticMemoryBridge
    - NO escribir en FAISS
    - Preservar trazabilidad
    """
    
    def __init__(self, validator: Optional[LearningValidator] = None):
        """
        Inicializar adapter.
        
        Args:
            validator: Instancia de LearningValidator. Si es None, se crea una nueva.
        """
        self._validator = validator or LearningValidator()
    
    def _create_test_answers_from_record(
        self,
        record: CuratedRecord,
        knowledge_base: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Crear test_answers mínimo y determinístico a partir del registro.
        
        IMPORTANTE: NO inventa evidencia fuerte.
        Solo crea respuestas mínimas necesarias para la validación.
        
        Args:
            record: Registro curado
            knowledge_base: Base de conocimiento previa
            
        Returns:
            Dict con test_answers mínimo
        """
        # Crear un test answer mínimo basado en el contenido del registro
        # NO es evidencia fuerte, es solo para completar la API
        test_answers = {
            "source": record.source,
            "topic": str(record.topic),
            "quality": record.quality.value if hasattr(record.quality, 'value') else str(record.quality),
            "content_sample": record.content[:200] if record.content else "",  # Solo muestra
            "timestamp": time.time(),
        }
        
        if knowledge_base:
            test_answers["knowledge_context"] = list(knowledge_base.keys())[:5]  # Solo keys
        
        return test_answers
    
    def validate_record(
        self,
        record: CuratedRecord,
        *,
        knowledge_base: Optional[Dict] = None,
        contradictions: Optional[List[Tuple]] = None,
        min_score: float = 0.70,
        max_retries: int = 1
    ) -> CurationValidationResult:
        """
        Validar un registro curado usando LearningValidator.
        
        Reglas:
        1. Si record es None → ERROR
        2. Si record.content está vacío → REJECTED
        3. Si record.source está vacío → REJECTED
        4. Si record.quality_score < 0.30 → REJECTED/UNVALIDATED
        5. Si contradictions no vacío → NO auto-validar (UNVALIDATED)
        6. NO modificar record.validated_at
        7. NO escribir en SemanticMemoryBridge/FAISS
        8. Preservar trazabilidad
        9. Si validator falla → ERROR
        10. Solo VALIDATED si passed=True y score >= min_score
        
        Args:
            record: Registro curado a validar
            knowledge_base: Base de conocimiento previa
            contradictions: Lista de contradicciones detectadas
            min_score: Score mínimo para considerar validado
            max_retries: Número máximo de reintentos en caso de error
            
        Returns:
            CurationValidationResult con el resultado de la validación
        """
        # 1. Validar record no es None (ANTES de usar cualquier atributo)
        if record is None:
            return CurationValidationResult(
                record_id="",
                content_hash="",
                source="",
                topic="",
                status=CurationValidationStatus.ERROR,
                validator_status=None,
                passed=False,
                score=0.0,
                reason="record is None",
                validation_id=f"curation_val_error_{int(time.time())}",
                metadata={"error": "null_record"}
            )
        
        # Ahora podemos generar validation_id con seguridad
        validation_id = f"curation_val_{int(time.time())}_{hash(record.record_id) % 10000}"
        
        # Preparar resultado base con trazabilidad
        base_result = {
            "record_id": record.record_id,
            "content_hash": record.content_hash,
            "source": record.source,
            "topic": str(record.topic),
            "validation_id": validation_id,
        }
        
        # 2. Validar content no vacío
        if not record.content or not record.content.strip():
            return CurationValidationResult(
                **base_result,
                status=CurationValidationStatus.REJECTED,
                validator_status=None,
                passed=False,
                score=0.0,
                reason="content is empty",
                metadata={"rejection_reason": "empty_content"}
            )
        
        # 3. Validar source no vacío
        if not record.source or not record.source.strip():
            return CurationValidationResult(
                **base_result,
                status=CurationValidationStatus.REJECTED,
                validator_status=None,
                passed=False,
                score=0.0,
                reason="source is empty",
                metadata={"rejection_reason": "empty_source"}
            )
        
        # 4. Validar quality_score no muy bajo
        if record.quality_score < 0.30:
            return CurationValidationResult(
                **base_result,
                status=CurationValidationStatus.UNVALIDATED,
                validator_status=None,
                passed=False,
                score=record.quality_score,
                reason=f"quality_score too low: {record.quality_score}",
                metadata={
                    "rejection_reason": "low_quality",
                    "quality_score": record.quality_score,
                    "threshold": 0.30
                }
            )
        
        # 5. Validar que no hay contradicciones
        if contradictions and len(contradictions) > 0:
            return CurationValidationResult(
                **base_result,
                status=CurationValidationStatus.UNVALIDATED,
                validator_status=None,
                passed=False,
                score=record.quality_score,
                reason=f"contradictions detected: {len(contradictions)}",
                metadata={
                    "rejection_reason": "contradictions",
                    "contradiction_count": len(contradictions),
                    "contradictions": [(c[0].record_id, c[1].record_id) for c in contradictions[:3]]
                }
            )
        
        # Intentar validación con LearningValidator
        attempt = 0
        last_error = None
        
        while attempt < max_retries:
            attempt += 1
            
            try:
                # Preparar argumentos para LearningValidator.validate()
                learning_id = record.record_id
                
                before_state = {"knowledge": ""}
                
                after_state = {
                    "knowledge": record.content,
                    "source": record.source,
                    "topic": str(record.topic),
                    "quality": record.quality.value if hasattr(record.quality, 'value') else str(record.quality),
                    "quality_score": record.quality_score,
                }
                
                topic = str(record.topic)
                
                gap_id = "curated_record_validation"
                
                kb = knowledge_base or {}
                
                # Crear test_answers mínimo y determinístico
                test_answers = self._create_test_answers_from_record(record, kb)
                
                # Llamar a LearningValidator.validate()
                validation_result: ValidationResult = self._validator.validate(
                    learning_id=learning_id,
                    before_state=before_state,
                    after_state=after_state,
                    topic=topic,
                    gap_id=gap_id,
                    knowledge_base=kb,
                    test_answers=test_answers,
                )
                
                # Mapear resultado del validator a nuestro resultado
                validator_status = validation_result.status
                validator_passed = validation_result.passed
                validator_score = validation_result.overall_score
                
                # Extraer mensajes del validator (recommendations, no reasons)
                validator_recs = getattr(validation_result, "recommendations", [])
                if isinstance(validator_recs, list) and validator_recs:
                    validator_messages = "; ".join(str(r) for r in validator_recs)
                else:
                    validator_messages = str(validator_recs) if validator_recs else ""
                
                # Decidir estado final basado en resultado del validator y su status
                # Mapeo de ValidationStatus del validator a CurationValidationStatus
                # VALIDATED → VALIDATED (si passed=True y score >= min_score)
                # UNVALIDATED → UNVALIDATED
                # PARTIAL → UNVALIDATED (no completamente validado)
                # PENDING → UNVALIDATED (aún no validado)
                
                # Mapeo según el status del validator
                if validator_status == ValidationStatus.VALIDATED:
                    # Status VALIDATED del validator
                    if validator_passed and validator_score >= min_score:
                        return CurationValidationResult(
                            **base_result,
                            status=CurationValidationStatus.VALIDATED,
                            validator_status=str(validator_status.value),
                            passed=True,
                            score=validator_score,
                            reason=validator_messages if validator_messages else "validation passed",
                            metadata={
                                "validator_result": validation_result.to_dict(),
                                "attempt": attempt,
                                "min_score_threshold": min_score,
                            }
                        )
                    else:
                        # VALIDATED pero no pasa score → REJECTED
                        reason = f"validator VALIDATED but insufficient: score={validator_score:.3f} < {min_score}"
                        return CurationValidationResult(
                            **base_result,
                            status=CurationValidationStatus.REJECTED,
                            validator_status=str(validator_status.value),
                            passed=False,
                            score=validator_score,
                            reason=reason,
                            metadata={
                                "validator_result": validation_result.to_dict(),
                                "attempt": attempt,
                                "min_score_threshold": min_score,
                                "rejection": "insufficient_score"
                            }
                        )
                
                elif validator_status == ValidationStatus.UNVALIDATED:
                    # Status UNVALIDATED → mapear a UNVALIDATED
                    return CurationValidationResult(
                        **base_result,
                        status=CurationValidationStatus.UNVALIDATED,
                        validator_status=str(validator_status.value),
                        passed=False,
                        score=validator_score,
                        reason=validator_messages if validator_messages else "validator returned UNVALIDATED",
                        metadata={
                            "validator_result": validation_result.to_dict(),
                            "attempt": attempt,
                            "rejection": "validator_unvalidated"
                        }
                    )
                
                else:
                    # PARTIAL, PENDING u otros → REJECTED
                    reason = f"validation failed: score={validator_score:.3f}, status={validator_status.value}"
                    if validator_messages:
                        reason += f" | info: {validator_messages}"
                    
                    return CurationValidationResult(
                        **base_result,
                        status=CurationValidationStatus.REJECTED,
                        validator_status=str(validator_status.value),
                        passed=False,
                        score=validator_score,
                        reason=reason,
                        metadata={
                            "validator_result": validation_result.to_dict(),
                            "attempt": attempt,
                            "rejection": "validator_rejected"
                        }
                    )
                
            except Exception as e:
                last_error = e
                if attempt >= max_retries:
                    # Agotamos reintentos → ERROR
                    return CurationValidationResult(
                        **base_result,
                        status=CurationValidationStatus.ERROR,
                        validator_status=None,
                        passed=False,
                        score=0.0,
                        reason=f"validator exception: {str(e)}",
                        metadata={
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "attempt": attempt,
                            "max_retries": max_retries,
                        }
                    )
                # Si no agotamos reintentos, continuar loop
                continue
        
        # No deberíamos llegar aquí, pero por seguridad
        return CurationValidationResult(
            **base_result,
            status=CurationValidationStatus.ERROR,
            validator_status=None,
            passed=False,
            score=0.0,
            reason="unexpected execution path",
            metadata={"error": "unexpected_path"}
        )


# =============================================================================
# Factory para crear adaptador con configuración por defecto
# =============================================================================

def create_curation_validation_adapter(
    validator: Optional[LearningValidator] = None
) -> CurationValidationAdapter:
    """
    Factory para crear un CurationValidationAdapter.
    
    Args:
        validator: LearningValidator opcional. Si no se proporciona, se crea uno nuevo.
        
    Returns:
        CurationValidationAdapter configurado
    """
    return CurationValidationAdapter(validator=validator)
