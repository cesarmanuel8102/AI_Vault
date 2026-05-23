"""
P2-E Commit 4B: SemanticMemory Real Adapter Skeleton

Esqueleto del adapter real para SemanticMemory, SIN escritura real.
Este módulo prepara la infraestructura pero bloquea explícitamente
escritura real hasta Commit 4D.

Relación con P2-E Commit 4A:
- Acepta snapshot_id de MemorySemanticBackupContract
- NO crea snapshots, solo recibe referencia
- Usa el snapshot para validar estado antes de escritura (futuro)

REGLAS DURAS:
- NO importar faiss
- NO importar requests/httpx
- NO importar semantic_memory_bridge
- NO importar SemanticMemory real
- NO llamar add_memory real
- NO escribir archivos
- NO usar write_text/write_bytes
- NO usar open write/append
- NO usar unlink/remove/rmdir
- NO usar shutil.copy/copytree/move
- dry_run_only=True SIEMPRE
- allow_real_write=False SIEMPRE
- prepare_blocked_real_write devuelve READY_BLOCKED/VALIDATED_BLOCKED
- block_real_write devuelve REAL_WRITE_BLOCKED
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid


class SemanticMemoryRealAdapterStatus(str, Enum):
    """Estados del adapter real (todos bloqueados en 4B)."""
    CREATED = "CREATED"
    READY_BLOCKED = "READY_BLOCKED"
    VALIDATED_BLOCKED = "VALIDATED_BLOCKED"
    REAL_WRITE_BLOCKED = "REAL_WRITE_BLOCKED"
    FAILED = "FAILED"


@dataclass
class SemanticMemoryRealWritePlan:
    """
    Plan de escritura para SemanticMemory.
    
    Contiene los datos que SE HABRÍAN escrito en SemanticMemory real,
    sin haberlo hecho. Incluye snapshot_id para vincular con 4A.
    """
    plan_id: str
    created_at_utc: str
    record_id: str
    text: str
    source: str
    content_hash: str
    metadata: Dict[str, Any]
    validation_score: float
    snapshot_id: Optional[str]  # Referencia a snapshot de 4A
    dry_run_only: bool = True
    allow_real_write: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "plan_id": self.plan_id,
            "created_at_utc": self.created_at_utc,
            "record_id": self.record_id,
            "text": self.text,
            "source": self.source,
            "content_hash": self.content_hash,
            "metadata": self.metadata,
            "validation_score": self.validation_score,
            "snapshot_id": self.snapshot_id,
            "dry_run_only": self.dry_run_only,
            "allow_real_write": self.allow_real_write,
        }


@dataclass
class SemanticMemoryRealAdapterResult:
    """
    Resultado de operación del adapter real.
    
    SIN escritura real, SIEMPRE bloqueado.
    """
    adapter_run_id: str
    created_at_utc: str
    status: SemanticMemoryRealAdapterStatus
    plan_id: Optional[str] = None
    snapshot_id: Optional[str] = None
    validation_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    dry_run_only: bool = True
    allow_real_write: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "adapter_run_id": self.adapter_run_id,
            "created_at_utc": self.created_at_utc,
            "status": self.status.value,
            "plan_id": self.plan_id,
            "snapshot_id": self.snapshot_id,
            "validation_errors": self.validation_errors,
            "warnings": self.warnings,
            "dry_run_only": self.dry_run_only,
            "allow_real_write": self.allow_real_write,
            "metadata": self.metadata,
        }


class SemanticMemoryRealAdapterSkeleton:
    """
    Esqueleto del adapter real para SemanticMemory.
    
    Responsabilidades (P2-E Commit 4B):
    - Preparar estructura para escritura real (futura)
    - Validar planes de escritura
    - Bloquear explícitamente escritura real
    - Vincular con snapshots de 4A (backup contract)
    
    Limitaciones (P2-E Commit 4B):
    - NO escribe en memory/semantic
    - NO importa FAISS
    - NO importa SemanticMemoryBridge
    - NO llama add_memory real
    - SIEMPRE bloquea allow_real_write
    
    Para escritura real (futuro, Commit 4D):
    1. Permitir allow_real_write=True con governance
    2. Implementar add_memory_real() con FAISS
    3. Validar con snapshot de 4A
    4. Integrar con rollback de 4C
    
    Args:
        backup_contract: Referencia a MemorySemanticBackupContract (4A)
    """
    
    def __init__(
        self,
        backup_contract: Optional[Any] = None,
    ):
        """
        Inicializar adapter skeleton.
        
        Args:
            backup_contract: Contract de backup para vincular snapshots
        """
        self._backup_contract = backup_contract
        self._adapter_runs: List[SemanticMemoryRealAdapterResult] = []
    
    def build_write_plan(
        self,
        record_id: str,
        text: str,
        source: str,
        content_hash: str,
        metadata: Optional[Dict[str, Any]] = None,
        validation_score: float = 0.0,
        snapshot_id: Optional[str] = None,
    ) -> SemanticMemoryRealWritePlan:
        """
        Construir plan de escritura para SemanticMemory.
        
        Este método prepara un plan con los datos que se escribirían
        en SemanticMemory real, SIN ejecutar la escritura.
        
        Args:
            record_id: ID del registro
            text: Texto/contenido a almacenar
            source: Fuente del contenido
            content_hash: Hash del contenido
            metadata: Metadatos adicionales
            validation_score: Score de validación
            snapshot_id: Referencia a snapshot de 4A (recomendado)
            
        Returns:
            SemanticMemoryRealWritePlan con el plan de escritura
        """
        plan_id = f"plan_{uuid.uuid4().hex[:16]}"
        
        return SemanticMemoryRealWritePlan(
            plan_id=plan_id,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            record_id=record_id,
            text=text,
            source=source,
            content_hash=content_hash,
            metadata=metadata or {},
            validation_score=validation_score,
            snapshot_id=snapshot_id,
            dry_run_only=True,
            allow_real_write=False,
        )
    
    def validate_write_plan(self, plan: SemanticMemoryRealWritePlan) -> tuple[List[str], List[str]]:
        """
        Validar plan de escritura.
        
        Args:
            plan: Plan a validar
            
        Returns:
            Lista de errores de validación (vacía si es válido)
        """
        errors = []
        warnings = []
        
        # Validación: record_id requerido
        if not plan.record_id:
            errors.append("record_id es requerido")
        
        # Validación: text requerido y no vacío
        if not plan.text:
            errors.append("text es requerido y no puede estar vacío")
        
        # Validación: source requerido
        if not plan.source:
            errors.append("source es requerido")
        
        # Validación: content_hash requerido
        if not plan.content_hash:
            errors.append("content_hash es requerido")
        
        # Validación: metadata debe ser dict
        if not isinstance(plan.metadata, dict):
            errors.append("metadata debe ser un diccionario")
        
        # Validación: validation_score entre 0.0 y 1.0
        if plan.validation_score < 0.0:
            errors.append("validation_score no puede ser menor a 0.0")
        if plan.validation_score > 1.0:
            errors.append("validation_score no puede ser mayor a 1.0")
        
        # Warning: snapshot_id recomendado
        if not plan.snapshot_id:
            warnings.append("snapshot_id es recomendado (para vincular con backup 4A)")
        
        # Warning: validation_score bajo
        if plan.validation_score < 0.70:
            warnings.append(f"validation_score ({plan.validation_score:.2f}) es bajo (< 0.70)")
        
        # Warning: text muy largo
        if len(plan.text) > 20000:
            warnings.append("text excede 20,000 caracteres - puede afectar rendimiento")
        
        return errors, warnings
    
    def prepare_blocked_real_write(
        self,
        plan: SemanticMemoryRealWritePlan,
    ) -> SemanticMemoryRealAdapterResult:
        """
        Preparar escritura real bloqueada.
        
        Este método simula la preparación para escritura real,
        pero SIEMPRE devuelve estado bloqueado.
        
        Args:
            plan: Plan de escritura
            
        Returns:
            SemanticMemoryRealAdapterResult con estado bloqueado
        """
        adapter_run_id = f"adapter_run_{uuid.uuid4().hex[:16]}"
        
        # Validar plan
        errors, warnings = self.validate_write_plan(plan)
        
        # Determinar estado
        if errors:
            status = SemanticMemoryRealAdapterStatus.FAILED
        else:
            # Si hay snapshot_id, consideramos VALIDATED_BLOCKED
            # Si no, consideramos READY_BLOCKED
            if plan.snapshot_id:
                status = SemanticMemoryRealAdapterStatus.VALIDATED_BLOCKED
                warnings.append("Plan validado con snapshot, pero escritura real bloqueada (4B)")
            else:
                status = SemanticMemoryRealAdapterStatus.READY_BLOCKED
                warnings.append("Plan listo pero escritura real bloqueada (4B)")
        
        # Agregar warnings sobre bloqueo
        warnings.append("Real write blocked until P2-E Commit 4D")
        warnings.append("use prepare_blocked_real_write (not add_memory_real)")
        
        result = SemanticMemoryRealAdapterResult(
            adapter_run_id=adapter_run_id,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            status=status,
            plan_id=plan.plan_id,
            snapshot_id=plan.snapshot_id,
            validation_errors=errors,
            warnings=warnings,
            dry_run_only=True,
            allow_real_write=False,
            metadata={
                "text_preview": plan.text[:100] if len(plan.text) > 100 else plan.text,
                "validation_score": plan.validation_score,
                "has_snapshot": plan.snapshot_id is not None,
                "blocked_reason": "P2-E Commit 4B - Real write not allowed",
            },
        )
        
        self._adapter_runs.append(result)
        return result
    
    def block_real_write(
        self,
        plan: SemanticMemoryRealWritePlan,
        reason: str = "Escritura real bloqueada por P2-E Commit 4B",
    ) -> SemanticMemoryRealAdapterResult:
        """
        Bloquear explícitamente escritura real.
        
        Guardia de seguridad para asegurar que nunca se escriba
        en SemanticMemory real durante P2-E 4B.
        
        Args:
            plan: Plan de escritura
            reason: Razón del bloqueo
            
        Returns:
            SemanticMemoryRealAdapterResult con REAL_WRITE_BLOCKED
        """
        adapter_run_id = f"adapter_run_{uuid.uuid4().hex[:16]}"
        
        result = SemanticMemoryRealAdapterResult(
            adapter_run_id=adapter_run_id,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            status=SemanticMemoryRealAdapterStatus.REAL_WRITE_BLOCKED,
            plan_id=plan.plan_id,
            snapshot_id=plan.snapshot_id,
            validation_errors=[],
            warnings=[f"REAL_WRITE_BLOCKED: {reason}"],
            dry_run_only=True,
            allow_real_write=False,
            metadata={
                "blocked": True,
                "blocked_reason": reason,
                "plan_id": plan.plan_id,
                "contract_version": "P2-E-Commit-4B",
                "next_step": "Commit 4C - Restore/Rollback Simulation",
            },
        )
        
        self._adapter_runs.append(result)
        return result
    
    def summarize_contract(self) -> Dict[str, Any]:
        """
        Resumir contrato del adapter.
        
        Returns:
            Dict con información del contrato
        """
        return {
            "contract_version": "P2-E-Commit-4B",
            "contract_type": "SemanticMemoryRealAdapterSkeleton",
            "dry_run_only": True,
            "allow_real_write": False,
            "has_backup_contract": self._backup_contract is not None,
            "total_adapter_runs": len(self._adapter_runs),
            "blocked_runs": len([
                r for r in self._adapter_runs
                if r.status == SemanticMemoryRealAdapterStatus.REAL_WRITE_BLOCKED
            ]),
            "ready_blocked_runs": len([
                r for r in self._adapter_runs
                if r.status == SemanticMemoryRealAdapterStatus.READY_BLOCKED
            ]),
            "validated_blocked_runs": len([
                r for r in self._adapter_runs
                if r.status == SemanticMemoryRealAdapterStatus.VALIDATED_BLOCKED
            ]),
            "capabilities": [
                "build_write_plan",
                "validate_write_plan",
                "prepare_blocked_real_write",
                "block_real_write",
            ],
            "limitations": [
                "NO real write (add_memory blocked)",
                "NO FAISS import",
                "NO SemanticMemoryBridge import",
                "NO file writes",
                "use prepare_blocked_real_write (not real write)",
                "Commit 4D required for real write",
            ],
            "dependencies": {
                "P2-E-4A": "MemorySemanticBackupContract (snapshot)",
                "P2-E-4C": "Restore/Rollback Simulation (required before 4D)",
            },
        }
