"""
P2-E Commit 4A: Memory Semantic Backup Contract

Contrato de backup/snapshot para memory/semantic.
SOLO read-only y dry-run. NO escribe backups reales.
NO modifica memory/semantic.
NO borra archivos.
NO copia archivos.
NO ejecuta runtime.

Este módulo proporciona:
1. Creación de snapshots (metadatos read-only)
2. Verificación de integridad
3. Simulación de backup dry-run
4. Simulación de restore dry-run
5. Bloqueo explícito de restore real

REGLAS DURAS:
- Solo read_bytes() para fingerprinting
- NO write_text/write_bytes
- NO open(..., "w") ni open(..., "a")
- NO shutil.copy/copy2/copytree/move/rmtree
- NO unlink/remove/rmdir
- NO import faiss
- NO import requests/httpx
- dry_run_only=True siempre
- allow_real_write=False siempre
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib
import uuid


class MemorySemanticBackupStatus(str, Enum):
    """Estados del backup contract."""
    CREATED = "CREATED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    RESTORE_SIMULATED = "RESTORE_SIMULATED"
    REAL_RESTORE_BLOCKED = "REAL_RESTORE_BLOCKED"


@dataclass
class MemorySemanticFileFingerprint:
    """
    Fingerprint de un archivo en memory/semantic.
    
    Contiene metadatos del archivo SIN copiar el contenido.
    """
    relative_path: str
    size_bytes: int
    sha256: str
    modified_at_utc: Optional[str] = None


@dataclass
class MemorySemanticSnapshot:
    """
    Snapshot de estado de memory/semantic.
    
    Contiene fingerprints de todos los archivos.
    NO contiene copias de archivos.
    """
    snapshot_id: str
    created_at_utc: str
    source_root: str
    file_count: int
    total_bytes: int
    fingerprints: List[MemorySemanticFileFingerprint] = field(default_factory=list)
    dry_run_only: bool = True
    allow_real_write: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "snapshot_id": self.snapshot_id,
            "created_at_utc": self.created_at_utc,
            "source_root": self.source_root,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "fingerprints": [
                {
                    "relative_path": f.relative_path,
                    "size_bytes": f.size_bytes,
                    "sha256": f.sha256,
                    "modified_at_utc": f.modified_at_utc,
                }
                for f in self.fingerprints
            ],
            "dry_run_only": self.dry_run_only,
            "allow_real_write": self.allow_real_write,
            "metadata": self.metadata,
        }


@dataclass
class MemorySemanticBackupResult:
    """
    Resultado de operación de backup/restore.
    
    SIN escritura real de archivos.
    """
    backup_id: str
    created_at_utc: str
    status: MemorySemanticBackupStatus
    snapshot_id: Optional[str] = None
    backup_root: Optional[str] = None
    validation_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    dry_run_only: bool = True
    allow_real_write: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "backup_id": self.backup_id,
            "created_at_utc": self.created_at_utc,
            "status": self.status.value,
            "snapshot_id": self.snapshot_id,
            "backup_root": self.backup_root,
            "validation_errors": self.validation_errors,
            "warnings": self.warnings,
            "dry_run_only": self.dry_run_only,
            "allow_real_write": self.allow_real_write,
            "metadata": self.metadata,
        }


class MemorySemanticBackupContract:
    """
    Contrato de backup/snapshot para memory/semantic.
    
    Responsabilidades:
    - Crear snapshots read-only (metadatos, no copias)
    - Verificar integridad de snapshots
    - Simular backup dry-run
    - Simular restore dry-run
    - Bloquear explícitamente restore real
    
    Limitaciones (P2-E Commit 4A):
    - Solo snapshots (metadatos)
    - NO copia archivos reales
    - NO modifica memory/semantic
    - NO escribe en disco (excepto tests con tmp_path)
    - dry_run_only=True siempre
    - allow_real_write=False siempre
    
    Para backup real (futuro):
    1. Permitir allow_real_write=True con governance
    2. Implementar copy_files_real()
    3. Implementar restore_real()
    4. Validar con smoke test de restore real
    """
    
    def __init__(
        self,
        source_root: str | Path,
        backup_root: Optional[str | Path] = None,
    ):
        """
        Inicializar contrato de backup.
        
        Args:
            source_root: Directorio fuente (memory/semantic o tmp_path)
            backup_root: Directorio de backup (solo referencia, NO escribe)
        """
        self._source_root = Path(source_root)
        self._backup_root = Path(backup_root) if backup_root else None
        self._snapshots: List[MemorySemanticSnapshot] = []
    
    def create_snapshot(self) -> MemorySemanticSnapshot:
        """
        Crear snapshot de metadatos del directorio fuente.
        
        Este método:
        1. Lista archivos en source_root
        2. Calcula fingerprints (sha256, size, modified)
        3. NO copia archivos
        4. NO modifica archivos
        
        Returns:
            MemorySemanticSnapshot con fingerprints
        """
        snapshot_id = f"snapshot_{uuid.uuid4().hex[:16]}"
        created_at = datetime.now(timezone.utc).isoformat()
        
        fingerprints = []
        total_bytes = 0
        file_count = 0
        
        # Solo si existe el directorio fuente
        if self._source_root.exists():
            for file_path in self._source_root.rglob("*"):
                if file_path.is_file():
                    # Calcular fingerprint (read-only)
                    try:
                        # Leer bytes para sha256 (read-only)
                        content = file_path.read_bytes()
                        sha256 = hashlib.sha256(content).hexdigest()
                        size = len(content)
                        modified = datetime.fromtimestamp(
                            file_path.stat().st_mtime, tz=timezone.utc
                        ).isoformat()
                        
                        relative = str(file_path.relative_to(self._source_root))
                        
                        fingerprint = MemorySemanticFileFingerprint(
                            relative_path=relative,
                            size_bytes=size,
                            sha256=sha256,
                            modified_at_utc=modified,
                        )
                        fingerprints.append(fingerprint)
                        total_bytes += size
                        file_count += 1
                    except Exception as e:
                        # Archivo no legible, agregar warning
                        pass
        
        snapshot = MemorySemanticSnapshot(
            snapshot_id=snapshot_id,
            created_at_utc=created_at,
            source_root=str(self._source_root),
            file_count=file_count,
            total_bytes=total_bytes,
            fingerprints=fingerprints,
            dry_run_only=True,
            allow_real_write=False,
            metadata={
                "contract_version": "P2-E-Commit-4A",
                "snapshot_type": "read_only_metadata",
            },
        )
        
        self._snapshots.append(snapshot)
        return snapshot
    
    def verify_snapshot(self, snapshot: MemorySemanticSnapshot) -> MemorySemanticBackupResult:
        """
        Verificar integridad de snapshot contra fuente actual.
        
        Compara fingerprints actuales con los del snapshot.
        
        Args:
            snapshot: Snapshot a verificar
            
        Returns:
            MemorySemanticBackupResult con estado VERIFIED o FAILED
        """
        backup_id = f"verify_{uuid.uuid4().hex[:16]}"
        created_at = datetime.now(timezone.utc).isoformat()
        errors = []
        warnings = []
        
        # Verificar que source_root existe
        if not self._source_root.exists():
            errors.append(f"Source root no existe: {self._source_root}")
            return MemorySemanticBackupResult(
                backup_id=backup_id,
                created_at_utc=created_at,
                status=MemorySemanticBackupStatus.FAILED,
                snapshot_id=snapshot.snapshot_id,
                validation_errors=errors,
                warnings=warnings,
                dry_run_only=True,
                allow_real_write=False,
            )
        
        # Verificar cada fingerprint
        for fingerprint in snapshot.fingerprints:
            file_path = self._source_root / fingerprint.relative_path
            
            if not file_path.exists():
                errors.append(f"Archivo faltante: {fingerprint.relative_path}")
                continue
            
            try:
                content = file_path.read_bytes()
                current_sha256 = hashlib.sha256(content).hexdigest()
                current_size = len(content)
                
                if current_sha256 != fingerprint.sha256:
                    errors.append(
                        f"Hash mismatch: {fingerprint.relative_path}"
                    )
                elif current_size != fingerprint.size_bytes:
                    errors.append(
                        f"Size mismatch: {fingerprint.relative_path}"
                    )
            except Exception as e:
                errors.append(f"Error leyendo {fingerprint.relative_path}: {e}")
        
        status = (
            MemorySemanticBackupStatus.VERIFIED
            if not errors
            else MemorySemanticBackupStatus.FAILED
        )
        
        return MemorySemanticBackupResult(
            backup_id=backup_id,
            created_at_utc=created_at,
            status=status,
            snapshot_id=snapshot.snapshot_id,
            validation_errors=errors,
            warnings=warnings,
            dry_run_only=True,
            allow_real_write=False,
            metadata={
                "files_checked": len(snapshot.fingerprints),
                "errors_found": len(errors),
            },
        )
    
    def simulate_backup(self, snapshot: MemorySemanticSnapshot) -> MemorySemanticBackupResult:
        """
        Simular operación de backup.
        
        Este método:
        1. Calcula qué se copiaría
        2. NO copia archivos reales
        3. Genera metadatos de simulación
        
        Args:
            snapshot: Snapshot a "respaldar"
            
        Returns:
            MemorySemanticBackupResult con simulación
        """
        backup_id = f"backup_sim_{uuid.uuid4().hex[:16]}"
        created_at = datetime.now(timezone.utc).isoformat()
        
        # Simular destino
        backup_root = str(self._backup_root) if self._backup_root else "simulated_backup_location"
        
        return MemorySemanticBackupResult(
            backup_id=backup_id,
            created_at_utc=created_at,
            status=MemorySemanticBackupStatus.CREATED,
            snapshot_id=snapshot.snapshot_id,
            backup_root=backup_root,
            validation_errors=[],
            warnings=[
                f"SIMULATED: Se copiarían {snapshot.file_count} archivos",
                f"SIMULATED: Total: {snapshot.total_bytes} bytes",
                f"SIMULATED: Destino: {backup_root}",
            ],
            dry_run_only=True,
            allow_real_write=False,
            metadata={
                "simulation": True,
                "would_copy_files": snapshot.file_count,
                "would_copy_bytes": snapshot.total_bytes,
                "actual_write": False,
            },
        )
    
    def simulate_restore(self, snapshot: MemorySemanticSnapshot) -> MemorySemanticBackupResult:
        """
        Simular operación de restore.
        
        Este método:
        1. Calcula qué se restauraría
        2. NO restaura archivos reales
        3. Genera metadatos de simulación
        
        Args:
            snapshot: Snapshot a "restaurar"
            
        Returns:
            MemorySemanticBackupResult con simulación
        """
        backup_id = f"restore_sim_{uuid.uuid4().hex[:16]}"
        created_at = datetime.now(timezone.utc).isoformat()
        
        return MemorySemanticBackupResult(
            backup_id=backup_id,
            created_at_utc=created_at,
            status=MemorySemanticBackupStatus.RESTORE_SIMULATED,
            snapshot_id=snapshot.snapshot_id,
            backup_root=str(self._backup_root) if self._backup_root else None,
            validation_errors=[],
            warnings=[
                f"SIMULATED: Se restaurarían {snapshot.file_count} archivos",
                f"SIMULATED: Total: {snapshot.total_bytes} bytes",
                "SIMULATED: NO se modificaron archivos reales",
            ],
            dry_run_only=True,
            allow_real_write=False,
            metadata={
                "simulation": True,
                "would_restore_files": snapshot.file_count,
                "would_restore_bytes": snapshot.total_bytes,
                "actual_write": False,
            },
        )
    
    def block_real_restore(self, reason: str = "Restore real bloqueado por P2-E") -> MemorySemanticBackupResult:
        """
        Bloquear explícitamente restore real.
        
        Este método actúa como guardia de seguridad para asegurar
        que nunca se ejecute restore real durante P2-E.
        
        Args:
            reason: Razón del bloqueo
            
        Returns:
            MemorySemanticBackupResult con estado REAL_RESTORE_BLOCKED
        """
        backup_id = f"block_{uuid.uuid4().hex[:16]}"
        created_at = datetime.now(timezone.utc).isoformat()
        
        return MemorySemanticBackupResult(
            backup_id=backup_id,
            created_at_utc=created_at,
            status=MemorySemanticBackupStatus.REAL_RESTORE_BLOCKED,
            validation_errors=[],
            warnings=[f"REAL_RESTORE_BLOCKED: {reason}"],
            dry_run_only=True,
            allow_real_write=False,
            metadata={
                "blocked": True,
                "reason": reason,
                "contract_version": "P2-E-Commit-4A",
            },
        )
    
    def summarize_contract(self) -> Dict[str, Any]:
        """
        Resumir contrato de backup.
        
        Returns:
            Dict con información del contrato
        """
        return {
            "contract_version": "P2-E-Commit-4A",
            "contract_type": "MemorySemanticBackupContract",
            "dry_run_only": True,
            "allow_real_write": False,
            "source_root": str(self._source_root),
            "backup_root": str(self._backup_root) if self._backup_root else None,
            "total_snapshots": len(self._snapshots),
            "capabilities": [
                "create_snapshot",
                "verify_snapshot",
                "simulate_backup",
                "simulate_restore",
                "block_real_restore",
            ],
            "limitations": [
                "NO real backup writes",
                "NO real restore writes",
                "NO file copies",
                "NO file deletions",
                "read_only snapshot metadata",
            ],
        }
