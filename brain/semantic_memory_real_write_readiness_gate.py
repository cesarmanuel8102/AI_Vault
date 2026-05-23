"""
P2-E Commit 4D-0: Controlled Real Write Readiness Gate

Gate de readiness antes de escritura real en SemanticMemory.
Este módulo verifica que todo está listo pero NO habilita escritura real.

Relación con commits anteriores:
- 4A: Backup contract provee snapshots
- 4B: Real adapter skeleton prepara infraestructura
- 4C: Rollback simulation valida flujo de rollback
- 4D-0: Este gate verifica readiness pero sigue bloqueado

REGLAS DURAS:
- NO importar faiss
- NO importar requests/httpx
- NO importar semantic_memory_bridge
- NO importar tmp_agent.brain_v9.core.semantic_memory
- NO importar tmp_agent.brain_v9.core.semantic_memory_faiss
- NO llamar add_memory real
- NO implementar promote_real
- NO implementar execute_rollback_real
- NO escribir archivos
- NO modificar allow_real_write=True
- dry_run_only=True SIEMPRE
- allow_real_write=False SIEMPRE
- Aun con token válido, status sigue READY_BLOCKED (no 4D aún)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import uuid


class SemanticMemoryRealWriteReadinessStatus(str, Enum):
    """Estados del readiness gate."""
    NOT_READY = "NOT_READY"
    READY_BLOCKED = "READY_BLOCKED"
    USER_APPROVAL_REQUIRED = "USER_APPROVAL_REQUIRED"
    REAL_WRITE_BLOCKED = "REAL_WRITE_BLOCKED"
    FAILED = "FAILED"


@dataclass
class SemanticMemoryRealWriteReadinessReport:
    """
    Reporte de readiness para escritura real.
    
    Este dataclass contiene el estado de readiness del sistema
    antes de permitir escritura real. SIEMPRE bloqueado.
    """
    readiness_id: str
    created_at_utc: str
    status: SemanticMemoryRealWriteReadinessStatus
    snapshot_id: Optional[str] = None
    backup_contract_ok: bool = False
    real_adapter_ok: bool = False
    rollback_simulation_ok: bool = False
    user_approval_required: bool = True
    user_approval_present: bool = False
    allow_real_write: bool = False
    dry_run_only: bool = True
    validation_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "readiness_id": self.readiness_id,
            "created_at_utc": self.created_at_utc,
            "status": self.status.value,
            "snapshot_id": self.snapshot_id,
            "backup_contract_ok": self.backup_contract_ok,
            "real_adapter_ok": self.real_adapter_ok,
            "rollback_simulation_ok": self.rollback_simulation_ok,
            "user_approval_required": self.user_approval_required,
            "user_approval_present": self.user_approval_present,
            "allow_real_write": self.allow_real_write,
            "dry_run_only": self.dry_run_only,
            "validation_errors": self.validation_errors,
            "warnings": self.warnings,
            "blockers": self.blockers,
            "metadata": self.metadata,
        }


class SemanticMemoryRealWriteReadinessGate:
    """
    Gate de readiness para escritura real en SemanticMemory.
    
    Responsabilidades:
    - Evaluar si el sistema está listo para escritura real
    - Verificar dependencias (4A, 4B, 4C)
    - Requerir aprobación de usuario
    - Bloquear explícitamente escritura real hasta 4D
    
    Limitaciones (P2-E Commit 4D-0):
    - Solo evalúa readiness
    - NO habilita escritura real
    - SIEMPRE bloquea allow_real_write
    - Aun con aprobación, status es READY_BLOCKED (no READY)
    
    Token de aprobación para pruebas:
    - CESAR_APPROVES_4D_DRY_GATE_ONLY
    - Este token NO autoriza escritura real, solo prueba el flujo
    """
    
    # Token válido para pruebas (no habilita escritura real)
    APPROVAL_TOKEN = "CESAR_APPROVES_4D_DRY_GATE_ONLY"
    
    def __init__(
        self,
        backup_contract: Optional[Any] = None,
        real_adapter: Optional[Any] = None,
        rollback_simulation: Optional[Any] = None,
    ):
        """
        Inicializar readiness gate.
        
        Args:
            backup_contract: Instancia de backup contract (4A)
            real_adapter: Instancia de real adapter skeleton (4B)
            rollback_simulation: Instancia de rollback simulation (4C)
        """
        self._backup_contract = backup_contract
        self._real_adapter = real_adapter
        self._rollback_simulation = rollback_simulation
    
    def evaluate_readiness(
        self,
        snapshot_id: Optional[str] = None,
        user_approval_token: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SemanticMemoryRealWriteReadinessReport:
        """
        Evaluar readiness del sistema para escritura real.
        
        Este método verifica:
        1. Que haya snapshot_id (requerido)
        2. Que las dependencias estén disponibles (4A, 4B, 4C)
        3. Que haya aprobación de usuario
        
        IMPORTANTE: Aun si todo pasa, allow_real_write sigue False
        y status es READY_BLOCKED (no READY hasta 4D).
        
        Args:
            snapshot_id: ID del snapshot de 4A
            user_approval_token: Token de aprobación de usuario
            metadata: Metadata adicional
            
        Returns:
            SemanticMemoryRealWriteReadinessReport con estado de readiness
        """
        readiness_id = f"readiness_{uuid.uuid4().hex[:16]}"
        
        errors: List[str] = []
        warnings: List[str] = []
        blockers: List[str] = []
        
        # Verificar snapshot_id
        if not snapshot_id:
            errors.append("snapshot_id es requerido para readiness")
            return SemanticMemoryRealWriteReadinessReport(
                readiness_id=readiness_id,
                created_at_utc=datetime.now(timezone.utc).isoformat(),
                status=SemanticMemoryRealWriteReadinessStatus.NOT_READY,
                snapshot_id=None,
                validation_errors=errors,
                warnings=warnings,
                blockers=blockers,
                dry_run_only=True,
                allow_real_write=False,
                metadata=metadata or {},
            )
        
        # Verificar dependencias
        backup_ok = self._backup_contract is not None
        adapter_ok = self._real_adapter is not None
        rollback_ok = self._rollback_simulation is not None
        
        if not backup_ok:
            errors.append("Backup contract (4A) no disponible")
        if not adapter_ok:
            errors.append("Real adapter (4B) no disponible")
        if not rollback_ok:
            errors.append("Rollback simulation (4C) no disponible")
        
        # Verificar aprobación de usuario
        user_approval_present = self.validate_user_approval_token(user_approval_token)
        
        if not user_approval_present:
            warnings.append("Aprobación de usuario requerida")
            return SemanticMemoryRealWriteReadinessReport(
                readiness_id=readiness_id,
                created_at_utc=datetime.now(timezone.utc).isoformat(),
                status=SemanticMemoryRealWriteReadinessStatus.USER_APPROVAL_REQUIRED,
                snapshot_id=snapshot_id,
                backup_contract_ok=backup_ok,
                real_adapter_ok=adapter_ok,
                rollback_simulation_ok=rollback_ok,
                user_approval_required=True,
                user_approval_present=False,
                validation_errors=errors,
                warnings=warnings,
                blockers=blockers,
                dry_run_only=True,
                allow_real_write=False,
                metadata=metadata or {},
            )
        
        # Si hay errores, no está listo
        if errors:
            return SemanticMemoryRealWriteReadinessReport(
                readiness_id=readiness_id,
                created_at_utc=datetime.now(timezone.utc).isoformat(),
                status=SemanticMemoryRealWriteReadinessStatus.NOT_READY,
                snapshot_id=snapshot_id,
                backup_contract_ok=backup_ok,
                real_adapter_ok=adapter_ok,
                rollback_simulation_ok=rollback_ok,
                user_approval_required=True,
                user_approval_present=True,
                validation_errors=errors,
                warnings=warnings,
                blockers=blockers,
                dry_run_only=True,
                allow_real_write=False,
                metadata=metadata or {},
            )
        
        # Todo listo pero aún bloqueado (hasta 4D)
        blockers.append("Commit 4D-0: Gate de readiness solo, NO habilita escritura real")
        blockers.append("Commit 4D: Controlled real write aún no implementado")
        
        return SemanticMemoryRealWriteReadinessReport(
            readiness_id=readiness_id,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            status=SemanticMemoryRealWriteReadinessStatus.READY_BLOCKED,
            snapshot_id=snapshot_id,
            backup_contract_ok=backup_ok,
            real_adapter_ok=adapter_ok,
            rollback_simulation_ok=rollback_ok,
            user_approval_required=True,
            user_approval_present=True,
            validation_errors=errors,
            warnings=warnings,
            blockers=blockers,
            dry_run_only=True,
            allow_real_write=False,
            metadata=metadata or {},
        )
    
    def validate_user_approval_token(self, token: Optional[str]) -> bool:
        """
        Validar token de aprobación de usuario.
        
        Args:
            token: Token de aprobación
            
        Returns:
            True si el token es válido
        """
        return token == self.APPROVAL_TOKEN
    
    def block_real_write(
        self,
        reason: str = "Escritura real bloqueada por gate 4D-0",
    ) -> SemanticMemoryRealWriteReadinessReport:
        """
        Bloquear explícitamente escritura real.
        
        Args:
            reason: Razón del bloqueo
            
        Returns:
            SemanticMemoryRealWriteReadinessReport con status REAL_WRITE_BLOCKED
        """
        readiness_id = f"blocked_{uuid.uuid4().hex[:16]}"
        
        return SemanticMemoryRealWriteReadinessReport(
            readiness_id=readiness_id,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            status=SemanticMemoryRealWriteReadinessStatus.REAL_WRITE_BLOCKED,
            snapshot_id=None,
            backup_contract_ok=False,
            real_adapter_ok=False,
            rollback_simulation_ok=False,
            user_approval_required=True,
            user_approval_present=False,
            validation_errors=[],
            warnings=[f"BLOCKED: {reason}"],
            blockers=[
                "BLOCKED: Escritura real bloqueada",
                "BLOCKED: Usar evaluate_readiness() antes de escritura real",
            ],
            dry_run_only=True,
            allow_real_write=False,
            metadata={"block_reason": reason},
        )
    
    def summarize_contract(self) -> Dict[str, Any]:
        """
        Resumir el contrato de seguridad.
        
        Returns:
            Dict con información del contrato
        """
        return {
            "contract_version": "P2-E-Commit-4D-0",
            "contract_type": "RealWriteReadinessGate",
            "dry_run_only": True,
            "allow_real_write": False,
            "capabilities": [
                "evaluate_readiness",
                "validate_user_approval_token",
                "block_real_write",
            ],
            "limitations": [
                "NO real write enabled",
                "NO FAISS",
                "NO semantic_memory_bridge",
                "NO add_memory real",
                "User approval required (but still blocked)",
            ],
            "dependencies": [
                "brain.memory_semantic_backup (4A)",
                "brain.semantic_memory_adapter_real (4B)",
                "brain.semantic_memory_rollback_simulation (4C)",
            ],
            "approval_token": self.APPROVAL_TOKEN,
            "token_purpose": "Test only - does not enable real write",
            "next_step": "Commit 4D: Controlled real write",
        }
