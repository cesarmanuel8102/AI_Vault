"""
P2-E Commit 4C: SemanticMemory Rollback Simulation

Simulación de rollback/restore coordinada para SemanticMemory.
Este módulo prepara la infraestructura para restore/rollback pero
bloquea explícitamente restore real hasta Commit 4D.

Relación con commits anteriores:
- 4A: MemorySemanticBackupContract provee snapshots
- 4B: SemanticMemoryRealAdapterSkeleton provee write_plans
- 4C: Este módulo simula restore/rollback usando snapshot + write_plan

REGLAS DURAS:
- NO importar faiss
- NO importar requests/httpx
- NO importar semantic_memory_bridge
- NO escribir archivos
- NO copiar archivos
- NO borrar archivos
- NO usar shutil.copy/copytree/move/rmtree
- NO usar write_text/write_bytes
- NO usar open
- NO usar unlink/remove/rmdir
- NO llamar add_memory real
- NO implementar promote_real real
- NO implementar execute_rollback_real real
- dry_run_only=True SIEMPRE
- allow_real_write=False SIEMPRE
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid

from brain.memory_semantic_backup import (
    MemorySemanticBackupContract,
    MemorySemanticBackupStatus,
)
from brain.semantic_memory_adapter_real import (
    SemanticMemoryRealAdapterSkeleton,
    SemanticMemoryRealWritePlan,
    SemanticMemoryRealAdapterStatus,
)


class SemanticMemoryRollbackSimulationStatus(str, Enum):
    """Estados de la simulación de rollback (todos son simulación en 4C)."""
    CREATED = "CREATED"
    PLAN_VALIDATED = "PLAN_VALIDATED"
    RESTORE_SIMULATED = "RESTORE_SIMULATED"
    ROLLBACK_SIMULATED = "ROLLBACK_SIMULATED"
    REAL_ROLLBACK_BLOCKED = "REAL_ROLLBACK_BLOCKED"
    FAILED = "FAILED"


@dataclass
class SemanticMemoryRollbackSimulationPlan:
    """
    Plan de simulación de rollback.
    
    Contiene la información necesaria para simular un rollback,
    vinculando snapshot (4A) con write_plan (4B).
    """
    rollback_plan_id: str
    created_at_utc: str
    snapshot_id: str
    write_plan_id: Optional[str] = None
    adapter_run_id: Optional[str] = None
    reason: str = ""
    affected_files: List[str] = field(default_factory=list)
    expected_restore_files: int = 0
    expected_restore_bytes: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    dry_run_only: bool = True
    allow_real_write: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "rollback_plan_id": self.rollback_plan_id,
            "created_at_utc": self.created_at_utc,
            "snapshot_id": self.snapshot_id,
            "write_plan_id": self.write_plan_id,
            "adapter_run_id": self.adapter_run_id,
            "reason": self.reason,
            "affected_files": self.affected_files,
            "expected_restore_files": self.expected_restore_files,
            "expected_restore_bytes": self.expected_restore_bytes,
            "metadata": self.metadata,
            "dry_run_only": self.dry_run_only,
            "allow_real_write": self.allow_real_write,
        }


@dataclass
class SemanticMemoryRollbackSimulationResult:
    """
    Resultado de la simulación de rollback.
    
    SIEMPRE bloqueado, nunca ejecuta restore real.
    """
    rollback_run_id: str
    created_at_utc: str
    status: SemanticMemoryRollbackSimulationStatus
    rollback_plan_id: Optional[str] = None
    snapshot_id: Optional[str] = None
    validation_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    simulated_actions: List[str] = field(default_factory=list)
    dry_run_only: bool = True
    allow_real_write: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "rollback_run_id": self.rollback_run_id,
            "created_at_utc": self.created_at_utc,
            "status": self.status.value,
            "rollback_plan_id": self.rollback_plan_id,
            "snapshot_id": self.snapshot_id,
            "validation_errors": self.validation_errors,
            "warnings": self.warnings,
            "simulated_actions": self.simulated_actions,
            "dry_run_only": self.dry_run_only,
            "allow_real_write": self.allow_real_write,
            "metadata": self.metadata,
        }


class SemanticMemoryRollbackSimulation:
    """
    Simulador de rollback/restore para SemanticMemory.
    
    Responsabilidades:
    - Crear planes de rollback vinculando snapshot (4A) + write_plan (4B)
    - Simular restore desde snapshot
    - Simular rollback después de write fallido
    - Bloquear explícitamente rollback real
    
    Limitaciones (P2-E Commit 4C):
    - Solo simulación (dry-run)
    - NO restaura archivos reales
    - NO escribe en memory/semantic
    - NO importa FAISS
    - SIEMPRE bloquea allow_real_write
    
    Para habilitar rollback real (futuro):
    1. Implementar execute_restore_real() con governance
    2. Permitir allow_real_write=True con aprobación
    3. Integrar con backup contract real
    4. Implementar rollback sobre índices FAISS
    """
    
    def __init__(
        self,
        backup_contract: Optional[Any] = None,
    ):
        """
        Inicializar simulador de rollback.
        
        Args:
            backup_contract: Contrato de backup (opcional, no se usa en simulación)
        """
        self._backup_contract = backup_contract
    
    def build_rollback_plan(
        self,
        snapshot: Any,
        write_plan_id: Optional[str] = None,
        adapter_run_id: Optional[str] = None,
        reason: str = "",
    ) -> SemanticMemoryRollbackSimulationPlan:
        """
        Crear plan de rollback vinculando snapshot y write_plan.
        
        Este método crea un plan que vincula:
        - Snapshot de 4A (backup contract)
        - Write plan de 4B (real adapter skeleton)
        - Razón del rollback
        
        Args:
            snapshot: Objeto snapshot de MemorySemanticBackupContract
            write_plan_id: ID del write plan (opcional)
            adapter_run_id: ID de la corrida del adapter (opcional)
            reason: Razón del rollback
            
        Returns:
            SemanticMemoryRollbackSimulationPlan con datos del plan
        """
        rollback_plan_id = f"rollback_plan_{uuid.uuid4().hex[:16]}"
        
        # Extraer información del snapshot
        snapshot_id = getattr(snapshot, 'snapshot_id', str(snapshot))
        affected_files = getattr(snapshot, 'affected_files', [])
        total_files = getattr(snapshot, 'total_files', 0)
        total_bytes = getattr(snapshot, 'total_bytes', 0)
        
        plan = SemanticMemoryRollbackSimulationPlan(
            rollback_plan_id=rollback_plan_id,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            snapshot_id=snapshot_id,
            write_plan_id=write_plan_id,
            adapter_run_id=adapter_run_id,
            reason=reason,
            affected_files=affected_files if affected_files else [],
            expected_restore_files=total_files,
            expected_restore_bytes=total_bytes,
            metadata={
                "snapshot_type": type(snapshot).__name__,
                "has_write_plan": write_plan_id is not None,
                "has_adapter_run": adapter_run_id is not None,
            },
            dry_run_only=True,
            allow_real_write=False,
        )
        
        return plan
    
    def validate_rollback_plan(
        self,
        plan: SemanticMemoryRollbackSimulationPlan,
    ) -> Tuple[List[str], List[str]]:
        """
        Validar un plan de rollback.
        
        Args:
            plan: Plan a validar
            
        Returns:
            Tuple[List[str], List[str]] - (errors, warnings)
        """
        errors: List[str] = []
        warnings: List[str] = []
        
        # Validaciones requeridas
        if not plan.snapshot_id:
            errors.append("snapshot_id es requerido")
        
        if not plan.reason:
            errors.append("reason es requerido")
        
        if plan.expected_restore_files < 0:
            errors.append("expected_restore_files no puede ser negativo")
        
        if plan.expected_restore_bytes < 0:
            errors.append("expected_restore_bytes no puede ser negativo")
        
        if not isinstance(plan.affected_files, list):
            errors.append("affected_files debe ser una lista")
        
        # Warnings
        if not plan.write_plan_id:
            warnings.append("write_plan_id no proporcionado (recomendado para trazabilidad)")
        
        if not plan.adapter_run_id:
            warnings.append("adapter_run_id no proporcionado (recomendado para trazabilidad)")
        
        if not plan.affected_files:
            warnings.append("affected_files está vacío (no hay archivos para restaurar)")
        
        return errors, warnings
    
    def simulate_restore_from_snapshot(
        self,
        plan: SemanticMemoryRollbackSimulationPlan,
    ) -> SemanticMemoryRollbackSimulationResult:
        """
        Simular restore desde snapshot.
        
        Este método simula lo que pasaría si se restaurara desde
        el snapshot, SIN modificar archivos reales.
        
        Args:
            plan: Plan de rollback
            
        Returns:
            SemanticMemoryRollbackSimulationResult con simulación
        """
        rollback_run_id = f"restore_sim_{uuid.uuid4().hex[:16]}"
        
        simulated_actions = [
            f"SIMULATED: Se restaurarían {plan.expected_restore_files} archivos",
            f"SIMULATED: Total: {plan.expected_restore_bytes} bytes",
            f"SIMULATED: Desde snapshot: {plan.snapshot_id}",
            "SIMULATED: NO se modificaron archivos reales",
        ]
        
        result = SemanticMemoryRollbackSimulationResult(
            rollback_run_id=rollback_run_id,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            status=SemanticMemoryRollbackSimulationStatus.RESTORE_SIMULATED,
            rollback_plan_id=plan.rollback_plan_id,
            snapshot_id=plan.snapshot_id,
            validation_errors=[],
            warnings=[
                "SIMULATED: Restore es simulación",
                "SIMULATED: Commit 4C no permite restore real",
            ],
            simulated_actions=simulated_actions,
            dry_run_only=True,
            allow_real_write=False,
            metadata={
                "restore_type": "simulated",
                "affected_files_count": len(plan.affected_files),
                "expected_bytes": plan.expected_restore_bytes,
            },
        )
        
        return result
    
    def simulate_rollback_after_failed_write(
        self,
        plan: SemanticMemoryRollbackSimulationPlan,
    ) -> SemanticMemoryRollbackSimulationResult:
        """
        Simular rollback después de un write fallido.
        
        Este método simula el rollback que se ejecutaría si un
        write_plan fallara, SIN modificar archivos reales.
        
        Args:
            plan: Plan de rollback
            
        Returns:
            SemanticMemoryRollbackSimulationResult con simulación
        """
        rollback_run_id = f"rollback_sim_{uuid.uuid4().hex[:16]}"
        
        simulated_actions = [
            f"SIMULATED: Rollback por write fallido",
            f"SIMULATED: Write plan: {plan.write_plan_id or 'N/A'}",
            f"SIMULATED: Adapter run: {plan.adapter_run_id or 'N/A'}",
            f"SIMULATED: Razón: {plan.reason}",
            f"SIMULATED: Se restaurarían {plan.expected_restore_files} archivos",
            "SIMULATED: NO se modificaron archivos reales",
        ]
        
        result = SemanticMemoryRollbackSimulationResult(
            rollback_run_id=rollback_run_id,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            status=SemanticMemoryRollbackSimulationStatus.ROLLBACK_SIMULATED,
            rollback_plan_id=plan.rollback_plan_id,
            snapshot_id=plan.snapshot_id,
            validation_errors=[],
            warnings=[
                "SIMULATED: Rollback es simulación",
                "SIMULATED: Commit 4C no permite rollback real",
            ],
            simulated_actions=simulated_actions,
            dry_run_only=True,
            allow_real_write=False,
            metadata={
                "rollback_type": "simulated_after_failed_write",
                "write_plan_id": plan.write_plan_id,
                "adapter_run_id": plan.adapter_run_id,
                "reason": plan.reason,
            },
        )
        
        return result
    
    def block_real_rollback(
        self,
        plan: SemanticMemoryRollbackSimulationPlan,
        reason: str = "Rollback real bloqueado por Commit 4C",
    ) -> SemanticMemoryRollbackSimulationResult:
        """
        Bloquear explícitamente rollback real.
        
        Este método bloquea cualquier intento de rollback real
        y documenta el bloqueo.
        
        Args:
            plan: Plan de rollback
            reason: Razón del bloqueo
            
        Returns:
            SemanticMemoryRollbackSimulationResult con status REAL_ROLLBACK_BLOCKED
        """
        rollback_run_id = f"block_{uuid.uuid4().hex[:16]}"
        
        result = SemanticMemoryRollbackSimulationResult(
            rollback_run_id=rollback_run_id,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            status=SemanticMemoryRollbackSimulationStatus.REAL_ROLLBACK_BLOCKED,
            rollback_plan_id=plan.rollback_plan_id,
            snapshot_id=plan.snapshot_id,
            validation_errors=[],
            warnings=[
                f"BLOCKED: {reason}",
                "BLOCKED: Commit 4C bloquea rollback real",
                "BLOCKED: Usar simulate_restore_from_snapshot() o simulate_rollback_after_failed_write()",
            ],
            simulated_actions=[
                "BLOCKED: Rollback real no ejecutado",
                f"BLOCKED: Razón: {reason}",
            ],
            dry_run_only=True,
            allow_real_write=False,
            metadata={
                "block_reason": reason,
                "blocked_by": "P2-E Commit 4C",
                "next_step": "Commit 4D para rollback real controlado",
            },
        )
        
        return result
    
    def summarize_contract(self) -> Dict[str, Any]:
        """
        Resumir el contrato de seguridad.
        
        Returns:
            Dict con información del contrato
        """
        return {
            "contract_version": "P2-E-Commit-4C",
            "contract_type": "RollbackSimulation",
            "dry_run_only": True,
            "allow_real_write": False,
            "capabilities": [
                "build_rollback_plan",
                "validate_rollback_plan",
                "simulate_restore_from_snapshot",
                "simulate_rollback_after_failed_write",
                "block_real_rollback",
            ],
            "limitations": [
                "NO real restore",
                "NO real rollback",
                "NO file operations",
                "NO FAISS",
                "NO semantic_memory_bridge",
            ],
            "dependencies": [
                "brain.memory_semantic_backup (4A)",
                "brain.semantic_memory_adapter_real (4B)",
            ],
            "next_step": "Commit 4D: Controlled real write",
        }
