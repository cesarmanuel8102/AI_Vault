"""
P2-E Commit 3G: SemanticMemory Adapter Dry-Run Contract

Adapter dry-run para integrar CuratedMemory con SemanticMemory/FAISS
SIN escribir en memoria semántica real, SIN modificar índices, SIN importar faiss.

Este módulo actúa como puente entre:
- CuratedMemoryDryRunFlow (orquestador)
- SemanticMemoryProbe (infraestructura descubierta)
- SemanticMemory real (futuro, bloqueado por ahora)

Responsabilidades:
1. Recibir solicitudes de write desde CuratedMemoryDryRunFlow
2. Simular escritura en SemanticMemory (dry-run)
3. Validar que el contrato es compatible con infraestructura descubierta
4. Registrar intentos de escritura en observabilidad
5. BLOQUEAR explícitamente escritura real (allow_real_write=False)

REGLAS DURAS:
- Solo dry-run (simulación)
- NO usar open(..., "w") ni open(..., "a")
- NO usar write_text, append_text
- NO usar unlink, remove, rmdir
- NO importar faiss
- NO importar requests/httpx
- NO construir índices reales
- NO llamar endpoints HTTP
- NO escribir en memory/semantic
- allow_real_write=False SIEMPRE
- dry_run_only=True SIEMPRE
- read_only=True SIEMPRE (en este commit)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid


class SemanticMemoryAdapterStatus(str, Enum):
    """Estados del adapter dry-run."""
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    DRY_RUN_READY = "DRY_RUN_READY"
    REAL_WRITE_BLOCKED = "REAL_WRITE_BLOCKED"


@dataclass
class SemanticMemoryPayload:
    """
    Payload para operación de SemanticMemory.
    
    Contiene los datos que SE HABRÍAN escrito en SemanticMemory,
    sin haberlo hecho realmente.
    """
    payload_id: str
    record_id: str
    text: str
    source: str
    content_hash: str
    metadata: Dict[str, Any]
    validation_score: float
    created_at_utc: str
    dry_run_only: bool = True
    allow_real_write: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "payload_id": self.payload_id,
            "record_id": self.record_id,
            "text": self.text,
            "source": self.source,
            "content_hash": self.content_hash,
            "metadata": self.metadata,
            "validation_score": self.validation_score,
            "created_at_utc": self.created_at_utc,
            "dry_run_only": self.dry_run_only,
            "allow_real_write": self.allow_real_write,
        }


@dataclass
class SemanticMemoryAdapterDryRunResult:
    """
    Resultado de operación dry-run del adapter.
    
    Este dataclass contiene información sobre lo que SE HABRÍA
    escrito en SemanticMemory, sin haberlo hecho realmente.
    """
    adapter_run_id: str
    payload_id: str
    record_id: str
    status: SemanticMemoryAdapterStatus
    would_call_method: Optional[str] = None
    candidate_module: Optional[str] = None
    candidate_class: Optional[str] = None
    validation_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    dry_run_only: bool = True
    allow_real_write: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "adapter_run_id": self.adapter_run_id,
            "payload_id": self.payload_id,
            "record_id": self.record_id,
            "status": self.status.value,
            "would_call_method": self.would_call_method,
            "candidate_module": self.candidate_module,
            "candidate_class": self.candidate_class,
            "validation_errors": self.validation_errors,
            "warnings": self.warnings,
            "dry_run_only": self.dry_run_only,
            "allow_real_write": self.allow_real_write,
            "metadata": self.metadata,
        }


class SemanticMemoryAdapterDryRun:
    """
    Adapter dry-run para integrar CuratedMemory con SemanticMemory.
    
    Responsabilidades:
    - Construir payloads validados
    - Validar payloads antes de simulación
    - Preparar dry-run sin escribir memoria real
    - Bloquear explícitamente escritura real
    - Registrar validaciones y errores
    
    Limitaciones (P2-E Commit 3G):
    - Solo simulación (dry-run)
    - NO escribe en memory/semantic
    - NO importa FAISS
    - NO construye índices reales
    - NO llama endpoints
    - SIEMPRE bloquea allow_real_write
    
    Para habilitar escritura real (futuro):
    1. Implementar add_memory_real()
    2. Permitir allow_real_write=True con governance completo
    3. Integrar con SemanticMemoryBridge real
    4. Implementar rollback sobre FAISS
    """
    
    # Método que se llamaría en el futuro (solo referencia textual)
    FUTURE_METHOD = "add_memory"
    
    def __init__(self, probe_result: Optional[Any] = None):
        """
        Inicializar adapter dry-run.
        
        Args:
            probe_result: Resultado de SemanticMemoryProbe (opcional)
        """
        self._probe_result = probe_result
        self._adapter_runs: List[SemanticMemoryAdapterDryRunResult] = []
    
    def build_payload(
        self,
        record_id: str,
        text: str,
        source: str,
        content_hash: str,
        metadata: Optional[Dict[str, Any]] = None,
        validation_score: float = 0.0,
    ) -> SemanticMemoryPayload:
        """
        Construir payload para operación de SemanticMemory.
        
        Este método construye un payload con los datos que se
        enviarían a SemanticMemory en una implementación real.
        
        Args:
            record_id: ID del registro
            text: Texto/contenido a almacenar
            source: Fuente del contenido
            content_hash: Hash del contenido
            metadata: Metadatos adicionales (opcional)
            validation_score: Score de validación
            
        Returns:
            SemanticMemoryPayload con los datos del payload
        """
        return SemanticMemoryPayload(
            payload_id=f"payload_{uuid.uuid4().hex[:16]}",
            record_id=record_id,
            text=text,
            source=source,
            content_hash=content_hash,
            metadata=metadata or {},
            validation_score=validation_score,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            dry_run_only=True,
            allow_real_write=False,
        )
    
    def validate_payload(self, payload: SemanticMemoryPayload) -> List[str]:
        """
        Validar payload antes de simulación.
        
        Este método valida que el payload cumple con el contrato
        mínimo requerido para operaciones de SemanticMemory.
        
        Args:
            payload: Payload a validar
            
        Returns:
            Lista de errores de validación (vacía si es válido)
        """
        errors = []
        
        # Validación: record_id requerido
        if not payload.record_id:
            errors.append("record_id es requerido")
        
        # Validación: text requerido y no vacío
        if not payload.text:
            errors.append("text es requerido y no puede estar vacío")
        
        # Validación: source requerido
        if not payload.source:
            errors.append("source es requerido")
        
        # Validación: content_hash requerido
        if not payload.content_hash:
            errors.append("content_hash es requerido")
        
        # Validación: metadata debe ser dict
        if not isinstance(payload.metadata, dict):
            errors.append("metadata debe ser un diccionario")
        
        # Validación: validation_score entre 0.0 y 1.0
        if payload.validation_score < 0.0:
            errors.append("validation_score no puede ser menor a 0.0")
        if payload.validation_score > 1.0:
            errors.append("validation_score no puede ser mayor a 1.0")
        
        return errors
    
    def _generate_warnings(self, payload: SemanticMemoryPayload) -> List[str]:
        """
        Generar warnings para payload.
        
        Args:
            payload: Payload a analizar
            
        Returns:
            Lista de warnings
        """
        warnings = []
        
        # Warning: text > 20,000 caracteres
        if len(payload.text) > 20000:
            warnings.append("text excede 20,000 caracteres - puede afectar rendimiento")
        
        # Warning: validation_score < 0.70
        if payload.validation_score < 0.70:
            warnings.append(f"validation_score ({payload.validation_score:.2f}) es bajo (< 0.70) - revisión conservadora recomendada")
        
        return warnings
    
    def prepare_dry_run(self, payload: SemanticMemoryPayload) -> SemanticMemoryAdapterDryRunResult:
        """
        Preparar operación dry-run.
        
        Este método simula lo que pasaría si se llamara a add_memory
        en la infraestructura real de SemanticMemory, SIN ejecutarlo.
        
        Args:
            payload: Payload a simular
            
        Returns:
            SemanticMemoryAdapterDryRunResult con resultado de simulación
        """
        adapter_run_id = f"adapter_run_{uuid.uuid4().hex[:16]}"
        
        # Validar payload
        validation_errors = self.validate_payload(payload)
        warnings = self._generate_warnings(payload)
        
        # Si hay errores de validación, rechazar
        if validation_errors:
            result = SemanticMemoryAdapterDryRunResult(
                adapter_run_id=adapter_run_id,
                payload_id=payload.payload_id,
                record_id=payload.record_id,
                status=SemanticMemoryAdapterStatus.REJECTED,
                would_call_method=None,
                validation_errors=validation_errors,
                warnings=warnings,
                dry_run_only=True,
                allow_real_write=False,
                metadata={
                    "rejected_reason": "validation_failed",
                    "validation_errors_count": len(validation_errors),
                },
            )
            self._adapter_runs.append(result)
            return result
        
        # Payload válido: preparar dry-run
        result = SemanticMemoryAdapterDryRunResult(
            adapter_run_id=adapter_run_id,
            payload_id=payload.payload_id,
            record_id=payload.record_id,
            status=SemanticMemoryAdapterStatus.DRY_RUN_READY,
            would_call_method=self.FUTURE_METHOD,  # Solo referencia textual
            candidate_module="brain.semantic_memory_bridge",  # Referencia futura
            candidate_class="SemanticMemoryBridge",  # Referencia futura
            validation_errors=[],
            warnings=warnings,
            dry_run_only=True,
            allow_real_write=False,
            metadata={
                "text_preview": payload.text[:100] if len(payload.text) > 100 else payload.text,
                "text_length": len(payload.text),
                "validation_score": payload.validation_score,
                "would_call": f"{self.FUTURE_METHOD}(text=..., metadata=...)",
            },
        )
        
        self._adapter_runs.append(result)
        return result
    
    def block_real_write(
        self,
        payload: SemanticMemoryPayload,
        reason: str = "Escritura real bloqueada por P2-E",
    ) -> SemanticMemoryAdapterDryRunResult:
        """
        Bloquear explícitamente escritura real.
        
        Este método actúa como guardia de seguridad para asegurar
        que nunca se escriba en SemanticMemory real durante P2-E.
        
        Args:
            payload: Payload que se intentó escribir
            reason: Razón del bloqueo
            
        Returns:
            SemanticMemoryAdapterDryRunResult con estado REAL_WRITE_BLOCKED
        """
        adapter_run_id = f"adapter_run_{uuid.uuid4().hex[:16]}"
        
        result = SemanticMemoryAdapterDryRunResult(
            adapter_run_id=adapter_run_id,
            payload_id=payload.payload_id,
            record_id=payload.record_id,
            status=SemanticMemoryAdapterStatus.REAL_WRITE_BLOCKED,
            would_call_method=None,
            validation_errors=[],
            warnings=[f"WRITE_BLOCKED: {reason}"],
            dry_run_only=True,
            allow_real_write=False,
            metadata={
                "blocked_reason": reason,
                "blocked_at": datetime.now(timezone.utc).isoformat(),
                "adapter_version": "P2-E-Commit-3G",
            },
        )
        
        self._adapter_runs.append(result)
        return result
    
    def validate_result(self, result: SemanticMemoryAdapterDryRunResult) -> bool:
        """
        Validar resultado del adapter.
        
        Verifica que el resultado cumple con las reglas de seguridad
        de P2-E.
        
        Args:
            result: Resultado a validar
            
        Returns:
            True si el resultado es válido, False en caso contrario
        """
        # Verificar que NO permite escritura real
        if result.allow_real_write:
            return False
        
        # Verificar que es dry-run
        if not result.dry_run_only:
            return False
        
        # Verificar estado válido
        valid_statuses = [
            SemanticMemoryAdapterStatus.CREATED,
            SemanticMemoryAdapterStatus.VALIDATED,
            SemanticMemoryAdapterStatus.REJECTED,
            SemanticMemoryAdapterStatus.DRY_RUN_READY,
            SemanticMemoryAdapterStatus.REAL_WRITE_BLOCKED,
        ]
        if result.status not in valid_statuses:
            return False
        
        return True
    
    def summarize_adapter_contract(self) -> Dict[str, Any]:
        """
        Resumir contrato del adapter.
        
        Returns:
            Dict con información del contrato
        """
        return {
            "adapter_version": "P2-E-Commit-3G",
            "dry_run_only": True,
            "allow_real_write": False,
            "read_only": True,
            "future_method": self.FUTURE_METHOD,
            "candidate_module": "brain.semantic_memory_bridge",
            "candidate_class": "SemanticMemoryBridge",
            "required_validations": [
                "record_id requerido",
                "text requerido y no vacío",
                "source requerido",
                "content_hash requerido",
                "metadata debe ser dict",
                "validation_score entre 0.0 y 1.0",
            ],
            "warnings": [
                "text > 20,000 caracteres",
                "validation_score < 0.70",
            ],
            "total_adapter_runs": len(self._adapter_runs),
            "blocked_writes": len([r for r in self._adapter_runs if r.status == SemanticMemoryAdapterStatus.REAL_WRITE_BLOCKED]),
            "dry_run_ready": len([r for r in self._adapter_runs if r.status == SemanticMemoryAdapterStatus.DRY_RUN_READY]),
            "rejected": len([r for r in self._adapter_runs if r.status == SemanticMemoryAdapterStatus.REJECTED]),
        }
